#!/usr/bin/env python3
"""Emulator test for mods/super_saiyan: USB descriptors, the companion-app config
channel (HID feature report 2 via the real class-request / EP0 paths), saving to
flash, the button/stick features and the touchpad mouse.

    python tools/test_super_saiyan.py build/NS36_ss.bin
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from emu_test import Emu, LOAD, test_boot, UC_HOOK_CODE  # noqa: E402
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,  # noqa: E402
                               UC_ARM_REG_R3, UC_ARM_REG_LR, UC_ARM_REG_PC)
import modkit  # noqa: E402

img = open(sys.argv[1], "rb").read()
base = open(os.path.join(os.path.dirname(__file__), "..", "firmware", "NS36_V3.4.bin"), "rb").read()
e, ok = test_boot(img, base)
u = e.u
R = lambda r: u.reg_read(r)
SCRATCH, SETUP, BUF, LENP, STATE = 0x2000F400, 0x2000F380, 0x2000F200, 0x2000F3F0, 0x2000F800
ptr = lambda a: struct.unpack("<I", img[a - LOAD:a - LOAD + 4])[0] & ~1
results = []


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"[{name}] {'PASS' if cond else 'FAIL'} {detail}")


def ret(uc, r0=0):
    uc.reg_write(UC_ARM_REG_R0, r0)
    uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR) | 1)


# ---- ROM / USB stand-ins ----------------------------------------------------
sent, ep0_in, ep0_out, flash_ops, timers = [], [], [], [], []


def h_alloc(uc, a, s, d): ret(uc, SCRATCH)
def h_send(uc, a, s, d):
    sent.append((R(UC_ARM_REG_R2), bytes(uc.mem_read(R(UC_ARM_REG_R0), R(UC_ARM_REG_R1))), R(UC_ARM_REG_R3)))
    ret(uc, 1)
def h_ep0(uc, a, s, d):                       # usb_ep0_reply(dir_in, data, len)
    if R(UC_ARM_REG_R0):
        ep0_in.append(bytes(uc.mem_read(R(UC_ARM_REG_R1), R(UC_ARM_REG_R2))))
    else:
        ep0_out.append((bytes(uc.mem_read(R(UC_ARM_REG_R1), 8)), R(UC_ARM_REG_R2)))
    ret(uc, 0)
def h_prog(uc, a, s, d): flash_ops.append(("prog", R(UC_ARM_REG_R0), bytes(uc.mem_read(R(UC_ARM_REG_R1), R(UC_ARM_REG_R2))))); ret(uc)
def h_erase(uc, a, s, d): flash_ops.append(("erase", R(UC_ARM_REG_R0))); ret(uc)
def h_timer(uc, a, s, d): timers.append((R(UC_ARM_REG_R0), R(UC_ARM_REG_R1), R(UC_ARM_REG_R2))); ret(uc)


for addr, fn in ((0x24FF4, h_alloc), (0x100115BC, h_send), (0x2000C034, h_ep0), (0x45E4, h_prog),
                 (0x43A4, h_erase), (0x2557C, h_timer)):
    u.hook_add(UC_HOOK_CODE, fn, begin=addr, end=addr)
u.mem_write(0x2000D318, struct.pack("<I", 2))             # output mode: Xbox 360

# ---- descriptors --------------------------------------------------------------
def desc(t, i=0):
    e.call(0x1000DF9C, t, i, LENP)
    p, n = R(UC_ARM_REG_R0), struct.unpack("<I", u.mem_read(LENP, 4))[0]
    return bytes(u.mem_read(p, n)) if p else b""


d = desc(1)
check("desc", d[8:12] == bytes.fromhex("09120100") and d[2:4] == b"\x00\x02", f"device {d.hex(' ')}")
c = desc(2)
ifs, i = [], 0
while i < len(c) and c[i]:
    if c[i + 1] == 4:
        ifs.append(f"if{c[i+2]}:{c[i+5]:02x}")
    i += c[i]
check("desc", c[2] == len(c) == 74 and ifs == ["if0:ff", "if1:03"], f"config {ifs}")
rd = desc(0x22)
check("desc", b"\x85\x01" in rd and b"\x85\x02" in rd and b"\xb1\x02" in rd, f"report descriptor {len(rd)} bytes")

# ---- config channel -------------------------------------------------------------
class_fn, ep0_out_fn = ptr(0x1001C214), 0x2000C000


def set_report(payload):
    data = bytes([2]) + payload + bytes(63 - len(payload))
    setup = bytes([0x21, 0x09, 0x02, 0x03, 0x01, 0x00, 64, 0])
    u.mem_write(SETUP, setup)
    ep0_out.clear()
    _, r0 = e.call(class_fn, SETUP)
    assert r0 == 0 and ep0_out and ep0_out[-1] == (setup, 64), "SET_REPORT not accepted"
    u.mem_write(BUF - 8, setup + data)                     # buffer = setup + data stage
    u.mem_write(BUF + 0x100, struct.pack("<II", 0, BUF))   # xfer: +4 = data
    e.call(ep0_out_fn, BUF + 0x100)


def get_report():
    u.mem_write(SETUP, bytes([0xA1, 0x01, 0x02, 0x03, 0x01, 0x00, 64, 0]))
    ep0_in.clear()
    _, r0 = e.call(class_fn, SETUP)
    assert r0 == 0 and ep0_in
    return ep0_in[-1]


def cmd(c, a0=0, a1=0, data=b""):
    set_report(bytes([c, a0, a1]) + data)
    return get_report()


r = cmd(1)
size = r[6]
check("info", r[:3] == b"\x02\x01\x00" and r[3] == 2, f"proto {r[3]} fw {r[4] | r[5] << 8:#06x} settings {size} bytes mode {r[7]}")
r = cmd(2, 0, size)
settings = bytearray(r[5:5 + size])
check("read", r[2] == 0 and settings[0] == 1 and settings[1] == size and settings[2] == 1,
      f"defaults {settings.hex(' ')}")
OFF = dict(tm_slop=6, tm_drag_slop=8, tm_hold_ms=10, remap=12, turbo_mask=32, turbo_rate=36,
           toggle_mask=37, socd=41, stick_dz=42, stick_anti_dz=44, stick_curve=46, stick_flags=48,
           trig_dz=49, trig_flags=51)
check("read", struct.unpack_from("<HHH", settings, 6) == (48, 160, 500) and settings[12:32] == bytes(range(20)),
      "touch slop/drag/hold + identity remap")
check("write", cmd(3, 0, 1, b"\x09")[2] == 1, "version byte is read-only")
check("write", cmd(3, size - 1, 2, b"\0\0")[2] == 1, "out-of-range write rejected")

# ---- features (DualSense, type 6) ---------------------------------------------
site = 0x10012976
glue = modkit.dec_bl(img[site - LOAD:site - LOAD + 4], site)
u.mem_write(0x1000FABC, b"\x70\x47")                       # stub the vendor settings engine
nbit = lambda lb: 1 << img[0x1001C228 - LOAD + 6 * 20 + lb]
T = [1000]


def frame(lbs=(), lx=0, ly=0, zl=0, dt=32):
    T[0] += dt
    st = bytearray(0x54)
    struct.pack_into("<III", st, 0, 6, T[0], sum(nbit(b) for b in lbs))
    struct.pack_into("<hhhhHH", st, 0x0C, lx, ly, 0, 0, zl, 0)
    st[0x31] = st[0x35] = 0x80                             # no touch
    u.mem_write(STATE, bytes(st))
    e.call(glue, STATE)
    b = struct.unpack("<I", u.mem_read(STATE + 8, 4))[0]
    out = {lb for lb in range(20) if nbit(lb) and b & nbit(lb)}
    return out, struct.unpack("<hhhhHH", u.mem_read(STATE + 0x0C, 12))


check("features", frame([0, 3])[0] == {0, 3}, "defaults pass buttons through")
remap = bytearray(range(20)); remap[0], remap[1] = 1, 0
cmd(3, OFF["remap"], 20, bytes(remap))
check("remap", frame([0])[0] == {1} and frame([1])[0] == {0}, "south <-> east")
cmd(5)
cmd(3, OFF["turbo_mask"], 5, struct.pack("<IB", 1 << 2, 10))   # turbo on west, 10/s
seq = [2 in frame([2], dt=40)[0] for _ in range(12)]
check("turbo", any(seq) and not all(seq), f"west held: {''.join('#' if x else '.' for x in seq)}")
cmd(5)
cmd(3, OFF["toggle_mask"], 4, struct.pack("<I", 1 << 4))
seq = [4 in frame(p)[0] for p in ([4], [], [], [4], [])]
check("toggle", seq == [True, True, True, False, False], f"L latch {seq}")
cmd(5)
cmd(3, OFF["socd"], 1, b"\x01")
check("socd", frame([12, 13])[0] == set() and frame([10, 11])[0] == set(), "neutral")
cmd(3, OFF["socd"], 1, b"\x03")
check("socd", frame([10, 11])[0] == {10}, "up priority")
cmd(5)
cmd(3, OFF["stick_dz"], 2, b"\x0a\x0a")                     # 10 % deadzone
_, sticks = frame(lx=3000, ly=0)
_, sticks2 = frame(lx=32767, ly=0)
check("sticks", sticks[0] == 0 and sticks2[0] > 32000, f"10% deadzone: 3000 -> {sticks[0]}, full -> {sticks2[0]}")
cmd(5)
cmd(3, OFF["stick_flags"], 1, b"\x02")                      # invert LY
_inv = frame(ly=20000)[1]
check("sticks", _inv[1] < -19000, f"invert LY: 20000 -> {_inv}")
cmd(5)
cmd(3, OFF["trig_dz"], 3, b"\x05\x00\x01")                  # L 5 % + hair trigger L
check("triggers", frame(zl=1000)[1][4] == 0 and frame(zl=5000)[1][4] == 32767, "deadzone + hair trigger")

# ---- save ------------------------------------------------------------------
cmd(5)
cmd(3, OFF["tm_hold_ms"], 2, struct.pack("<H", 650))
timers.clear()
check("save", cmd(4)[2] == 0 and timers and timers[-1][0] == 3, f"SAVE starts timer event 3: {timers}")
flash_ops.clear()
e.call(0x1000F938)                                         # timer event 3 -> vendor writer (replaced)
progs = [op for op in flash_ops if op[0] == "prog"]
check("save", flash_ops and flash_ops[0] == ("erase", 0x7B000) and len(progs) == 2
      and progs[0][1] == 0x7B000 and progs[0][2][:4] == b"2NUF" and progs[1][1] == 0x7B040
      and progs[1][2][:4] == b"GKSS", f"{[(o[0], hex(o[1])) for o in flash_ops]}")
u.mem_write(0x1007B000, progs[0][2])
u.mem_write(0x1007B040, progs[1][2])
cmd(5)                                                     # forget in RAM, then reload from flash
init = None
for line in open(os.path.join(os.path.dirname(__file__), "..", "build", "mods", "mods.map")):
    if line.rstrip().endswith(" ss_load"):
        init = int(line.split()[0], 16)
e.call(init)
r = cmd(2, OFF["tm_hold_ms"], 2)
check("save", struct.unpack_from("<H", r, 5)[0] == 650, "settings survive a reload from flash")

# ---- touchpad mouse (report ID 1) -----------------------------------------------
cmd(5)
e.call(ptr(0x1001C224))                                    # SET_CONFIGURATION: opens EP 0x82


def touch(fid=None, x=0, y=0, click=False):
    T[0] += 32
    st = bytearray(0x54)
    struct.pack_into("<III", st, 0, 6, T[0], (1 << 17) if click else 0)
    st[0x31:0x35] = bytes([fid, x & 0xFF, (x >> 8) | (y & 0xF) << 4, y >> 4]) if fid is not None else b"\x80\0\0\0"
    st[0x35] = 0x80
    u.mem_write(STATE, bytes(st))
    sent.clear()
    e.call(glue, STATE)
    for ep, data, cb in list(sent):                        # complete the transfer
        u.mem_write(BUF + 0x200, struct.pack("<II", 0, SCRATCH))
        e.call(cb & ~1, BUF + 0x200)
    return [d for ep, d, _ in sent if ep == 0x82]


touch(1, 500, 500)
touch(1, 600, 500)
rep = touch(1, 680, 500)
check("mouse", rep and rep[-1][0] == 1 and len(rep[-1]) == 5 and struct.unpack("b", rep[-1][2:3])[0] > 0,
      f"report id 1, moves right: {[r.hex(' ') for r in rep]}")
touch(1, 680, 500, click=True)
rep = touch(1, 680, 500)
check("mouse", rep and rep[-1][1] == 1, "tap -> left click")

# ---- battery (DS4 parse hook + INFO) ----------------------------------------------
parse = None
for line in open(os.path.join(os.path.dirname(__file__), "..", "build", "mods", "mods.map")):
    if line.rstrip().endswith(" ss_ps_parse"):
        parse = int(line.split()[0], 16)
ds4 = bytearray(64); ds4[0] = 0x01; ds4[1:5] = bytes([0x80] * 4); ds4[5] = 0x08; ds4[30] = 0x17
u.mem_write(BUF, bytes(ds4))
u.mem_write(STATE, bytes(0x54))
e.call(parse | 1, 0, BUF, 64, STATE)
bat = struct.unpack("<I", u.mem_read(STATE + 0x44, 4))[0]
check("battery", bat == 0x17, f"DS4 status byte -> state +0x44: {bat:#x}")
u.mem_write(0x2000D478 + 0x44, struct.pack("<I", 0x00002A00))
r = cmd(1)
check("battery", r[10:14] == bytes([0, 0x2A, 0, 0]), f"INFO battery bytes {r[10:14].hex(' ')}")

print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
