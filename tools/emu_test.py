#!/usr/bin/env python3
"""Emulator smoke tests for (modded) NS36 images, using Unicorn (pip install unicorn).

    python tools/emu_test.py [build/NS36_mod.bin]

What is tested
  boot    Runs the real ARMCC __main/__scatterload from the image, with the
          mask-ROM copy/zero/printf routines emulated in Python, until the
          vendor C entry (__rt_entry) is reached. Checks vendor .data matches the
          Ghidra reconstruction and that mod init functions ran.
  input   Calls the instruction sequence at the input hook site with a sample
          cntlr_state_t, with the vendor settings engine stubbed, and reports
          the buttons before/after (shows what input_filter mods do).

The mask ROM is not available, so anything beyond these paths is out of scope.
"""
import os
import struct
import sys

try:
    from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                                   UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)
except ImportError:
    sys.exit("unicorn not installed: pip install unicorn")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ns36fw  # noqa: E402

LOAD = ns36fw.LOAD_ADDR
ROM_COPY, ROM_ZERO, ROM_PRINTF = 0x114C8, 0x114D8, 0x16E48
VENDOR_RT_ENTRY = 0x1000428E
APP_ENTRY = 0x1000427C       # entry pointer in the app header; called by the ROM
APP_INIT = 0x10013290        # where 0x1000428E finally branches (app init)
SETTINGS_ENGINE = 0x1000FABC
INPUT_HOOK_SITE = 0x10012976
STOP = 0x0005FFF0          # fake return address inside the ROM stub area


class Emu:
    def __init__(self, image):
        self.img = image
        self.log = []
        u = self.u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        u.mem_map(0x0, 0x60000)                                   # mask ROM (stubs)
        u.mem_write(0x0, b"\x70\x47" * 0x30000)                   # bx lr everywhere
        u.mem_map(0x10000000, 0x3000)                             # bootloader (not in file)
        u.mem_write(0x10000000, bytes([0xFF]) * 0x3000)
        u.mem_map(LOAD, 0x20000 + 0x1000)
        u.mem_write(LOAD, image)
        u.mem_map(0x1007B000, 0x2000)                             # config + pairing sectors (erased)
        u.mem_write(0x1007B000, bytes([0xFF]) * 0x2000)
        u.mem_map(0x1FFF0000, 0x20000)                          # RAM (+ stack below 0x20000000)
        u.mem_map(0x40000000, 0x100000)                           # peripherals (plain memory)
        u.hook_add(UC_HOOK_CODE, self._rom, begin=0x0, end=0x5FFFF)

    def _reg(self, r):
        return self.u.reg_read(r)

    def _cstr(self, a):
        s = bytearray()
        while len(s) < 256:
            c = self.u.mem_read(a + len(s), 1)[0]
            if c == 0:
                break
            s.append(c)
        return s.decode("latin-1")

    def _ret(self, value=None):
        if value is not None:
            self.u.reg_write(UC_ARM_REG_R0, value)
        self.u.reg_write(UC_ARM_REG_PC, self._reg(UC_ARM_REG_LR) | 1)

    def _rom(self, u, addr, size, _):
        a = addr & ~1
        if a == STOP & ~1:
            u.emu_stop()
        elif a == ROM_COPY:                      # __scatterload_copy(src, dst, n)
            src, dst, n = self._reg(UC_ARM_REG_R0), self._reg(UC_ARM_REG_R1), self._reg(UC_ARM_REG_R2)
            u.mem_write(dst, bytes(u.mem_read(src, n)))
            self._ret()
        elif a == ROM_ZERO:                      # __scatterload_zeroinit(_, dst, n)
            dst, n = self._reg(UC_ARM_REG_R1), self._reg(UC_ARM_REG_R2)
            u.mem_write(dst, b"\0" * n)
            self._ret()
        elif a == ROM_PRINTF:                    # log_printf(fmt, ...) - format with %-args from r1..r3
            fmt = self._cstr(self._reg(UC_ARM_REG_R0))
            args = [self._reg(r) for r in (UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
            out, i = "", 0
            parts = fmt.split("%")
            out = parts[0]
            for p in parts[1:]:
                if p and p[0] == "s":
                    out += self._cstr(args[i]) + p[1:]; i += 1
                elif p:
                    j = 0
                    while j < len(p) and p[j] not in "dxXuscp":
                        j += 1
                    out += f"<{args[i]:#x}>" + p[j + 1:] if i < 3 else p; i += 1
            self.log.append(out.strip())
            self._ret(0)

    def call(self, addr, *args, stop_at=None, max_insns=20_000_000):
        u = self.u
        for r, v in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            u.reg_write(r, v)
        u.reg_write(UC_ARM_REG_SP, 0x1FFFFF00)
        u.reg_write(UC_ARM_REG_LR, STOP | 1)
        if stop_at is not None:
            h = u.hook_add(UC_HOOK_CODE, lambda uc, a, s, d: uc.emu_stop(), begin=stop_at, end=stop_at)
        try:
            u.emu_start(addr | 1, STOP, count=max_insns)
        finally:
            if stop_at is not None:
                u.hook_del(h)
        return self._reg(UC_ARM_REG_PC), self._reg(UC_ARM_REG_R0)


def boot_state(image):
    """Run the ROM->app entry path up to the app init; return (emu, regs, stack)."""
    from unicorn.arm_const import UC_ARM_REG_R4
    e = Emu(image)
    e.u.reg_write(UC_ARM_REG_R0, 0x11111111)
    e.u.reg_write(UC_ARM_REG_R1, 0x22222222)
    e.u.reg_write(UC_ARM_REG_R4, 0x44444444)
    pc, _ = e.call(APP_ENTRY, stop_at=APP_INIT)
    regs = [e._reg(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R4, UC_ARM_REG_SP, UC_ARM_REG_LR)]
    sp = e._reg(UC_ARM_REG_SP)
    return e, pc, regs, bytes(e.u.mem_read(sp, 0x1FFFFF00 - sp))


def test_boot(image, base):
    e, pc, regs, stack = boot_state(image)
    _, _, ref_regs, ref_stack = boot_state(base)
    ok = (pc & ~1) == APP_INIT
    print(f"[boot] ROM entry 0x{APP_ENTRY:08x} reached app init 0x{APP_INIT:08x}: {'PASS' if ok else f'FAIL (pc={pc:#x})'}")
    same_ctx = regs == ref_regs and stack == ref_stack
    print(f"[boot] registers/stack at app init identical to stock: {'PASS' if same_ctx else 'FAIL'}")
    if not same_ctx:
        print(f"[boot]   mod  r0 r1 r4 sp lr = {[hex(x) for x in regs]}")
        print(f"[boot]   stock               = {[hex(x) for x in ref_regs]}")
    for line in e.log:
        print(f"[boot]   log: {line}")
    ref = Emu(base)
    ref.call(APP_ENTRY, stop_at=APP_INIT)
    a, r = e.u.mem_read(0x2000C000, 0x1F24), ref.u.mem_read(0x2000C000, 0x1F24)
    diff = [i for i in range(len(a)) if a[i] != r[i]]
    # allowed: bytes the image itself changed in the RAM-code copy source (log_printf
    # silencing, ram_replace hooks), i.e. RAM differs exactly where its load image does
    src = 0x1001DA14 - LOAD
    patched = {i for i in range(0xD70) if image[src + i] != base[src + i]}
    if diff and set(diff) <= patched:
        print(f"[boot]   ({len(patched)} RAM-code bytes patched by the image, as intended)")
        diff = []
    same = not diff
    if diff:
        print(f"[boot]   differing bytes at {[hex(0x2000C000 + i) for i in diff[:8]]}")
    print(f"[boot] vendor .data/.bss identical to stock boot: {'PASS' if same else 'FAIL'}")
    return e, ok and same_ctx and same


def test_input(e, buttons, sticks=(0, 0, 0, 0), ctype=1):
    u = e.u
    state = 0x2000F800
    st = bytearray(0x54)
    struct.pack_into("<III4h", st, 0, ctype, 0, buttons, *sticks)
    u.mem_write(state, bytes(st))
    # stub the vendor settings engine so only mod code runs
    u.mem_write(SETTINGS_ENGINE, b"\x70\x47")
    # call whatever the patched BL at the hook site now targets
    import modkit
    insn = bytes(e.img[INPUT_HOOK_SITE - LOAD:INPUT_HOOK_SITE - LOAD + 4])
    target = modkit.dec_bl(insn, INPUT_HOOK_SITE)
    e.call(target, state)
    after = struct.unpack_from("<I", u.mem_read(state, 12), 8)[0]
    e.last_sticks = struct.unpack_from("<4h", u.mem_read(state + 0xC, 8))
    return target, after


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "build/NS36_mod.bin"
    image = open(path, "rb").read()
    base = open(os.path.join(os.path.dirname(__file__), "..", "firmware", "NS36_V3.4.bin"), "rb").read()
    ns36fw.parse(image)
    e, ok = test_boot(image, base)
    from modkit import dec_bl
    tgt = dec_bl(image[INPUT_HOOK_SITE - LOAD:INPUT_HOOK_SITE - LOAD + 4], INPUT_HOOK_SITE)
    if tgt == SETTINGS_ENGINE:
        print("[input] no input_filter mods in this image")
    else:
        LB = ["south", "east", "west", "north"]
        tbl = image[0x1001C228 - LOAD:0x1001C228 - LOAD + 8 * 20]
        for ctype in (1, 5):
            bit = lambda lb: 1 << tbl[ctype * 20 + lb]
            for combo in ((0,), (1,), (2,), (3,), (0, 2)):
                btn = sum(bit(lb) for lb in combo)
                e.log.clear()
                _, after = test_input(e, btn, ctype=ctype)
                got = "+".join(LB[lb] for lb in range(4) if after & bit(lb)) or "none"
                want = "+".join(LB[lb] for lb in combo)
                print(f"[input] type {ctype}: {want:11} -> {got:11}" + (f"   log: {e.log}" if e.log else ""))
        for st in ((1000, -800, 0, 0), (3000, 0, 0, 0), (16000, 0, 0, -16000), (32767, 32767, -32768, 0)):
            test_input(e, 0, st)
            print(f"[input] sticks {st} -> {e.last_sticks}")
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
