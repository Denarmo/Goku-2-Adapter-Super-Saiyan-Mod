#!/usr/bin/env python3
"""modkit - compile C mods and link them into the NS36 (Goku 2) main firmware.

    python tools/modkit.py build [--base firmware/NS36_V3.4.bin] [-o build/NS36_mod.bin]
    python tools/modkit.py list
    python tools/modkit.py symbols          # write build/mods/firmware_syms.ld only

Requires clang + ld.lld + llvm-objcopy (any LLVM >= 15) on PATH, or set LLVM_BIN.

How it works
------------
1. Every mods/<name>/mod.json with "enabled": true contributes its C sources.
2. Sources are compiled for Cortex-M3 Thumb-2 and linked by ld.lld into the free
   flash right after the vendor code (runtime 0x1001EA94..0x1001F000) and a
   small RAM window after the vendor .bss.  Firmware functions/globals are
   available as symbols generated from reference/*.csv.
3. ARMCC's scatter-load table is relocated next to the mod code and extended
   with a copy entry (mod .data) and a zero entry (mod .bss), so mod globals are
   initialized at boot exactly like the vendor's own.
4. Hooks from mod.json are applied:
     {"type": "call",    "site": "0x10012976", "to": "my_fn"}  retarget one BL
     {"type": "replace", "site": "0x1000fabc", "to": "my_fn"}  B.W at function entry
     {"type": "pointer", "site": "0x1001c000", "to": "my_fn"}  overwrite a code pointer
     {"type": "ram_replace", "site": "0x2000c000", "to": "my_fn"}  jump from RAM code
                                               (patches its boot-time copy source)
     {"type": "input_filter", "to": "my_fn"}   void my_fn(cntlr_state_t *s), runs on
                                               every input frame before the vendor
                                               settings/turbo engine (chainable)
     {"type": "report_filter", "to": "my_fn"}  void my_fn(uint8_t *report, uint32_t len,
                                               uint32_t mode), edits the encoded USB
                                               report just before it is sent (chainable)
   plus "init": "fn" to run fn() once at boot before the vendor main().
5. The header code length is updated; the image is re-validated.
"""
import argparse
import csv
import json
import re
import os
import shutil
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ns36fw  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOAD = ns36fw.LOAD_ADDR                    # 0x10003000
FLASH_LIMIT = LOAD + ns36fw.AUX_OFF        # MSP blob starts here (0x1001F000)
RAM_ORIGIN = 0x2000DF40                    # after vendor .bss (ends 0x2000DF24)
RAM_LENGTH = 0x800
# Reclaimed flash: blocks of vendor log_printf format strings (reference/reclaim_arm.csv,
# made by tools/find_reclaimable.py). When mods are packed into them, log_printf is turned
# into a no-op by patching both of its veneers (flash, and the RAM copy's load image).
# Mods that need the debug log set "uses_log": true, which disables reclaiming.
# (The 0xFF tail of the file after the MSP image is NOT written by the bootloader.)
LOG_VENEERS = (0x1000442E, 0x1001DA14 + (0x2000CCA0 - 0x2000C000))
LOG_VENEER_BYTES = bytes.fromhex("46f6496cc0f2010c6047")   # movw/movt r12, 0x16e49; bx r12
SCATTER_REF = LOAD + 0x1218                # adr target used by __scatterload
MAIN_CALL_SITE = LOAD + 0x11FE             # final "bl __rt_entry" at the end of __scatterload
ROM_COPY, ROM_ZERO = 0x000114C8, 0x000114D8  # mask-ROM scatter routines (from vendor table)


def rel(*p):
    return os.path.join(ROOT, *p)


def tool(name):
    d = os.environ.get("LLVM_BIN")
    exe = os.path.join(d, name) if d else shutil.which(name)
    if not exe or not (shutil.which(exe) or os.path.exists(exe) or os.path.exists(exe + ".exe")):
        sys.exit(f"error: {name} not found (install LLVM or set LLVM_BIN)")
    return exe


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"error: {' '.join(cmd)}\n{r.stdout}{r.stderr}")
    return r.stdout


# --------------------------------------------------------------------------- symbols
def load_symbols():
    """name -> (address, is_function) from the decompilation indexes + manual tables."""
    syms = {}
    with open(rel("reference", "arm_functions.csv")) as f:
        rank = {}
        for row in csv.DictReader(f):
            name, src = row["name"], row.get("source", "")
            r = {"manual": 3, "": 1, "log-string": 2, "thunk": 0}.get(src, 1)
            if name not in syms or r > rank[name]:
                syms[name], rank[name] = (int(row["address"], 16), True), r
    # Calls into the mask ROM (0x0..0x60000) or RAM code are out of BL range from flash, so lld would
    # add a range-extension thunk per caller section. The vendor already has a veneer in
    # flash for each ROM function it uses (thunk_<name>): link mod calls to that instead.
    with open(rel("reference", "arm_functions.csv")) as f:
        veneers = {row["name"][6:]: int(row["address"], 16) for row in csv.DictReader(f)
                   if row["name"].startswith("thunk_") and 0x10000000 <= int(row["address"], 16) < 0x20000000}
    for name, (addr, is_fn) in list(syms.items()):
        if is_fn and (addr < 0x60000 or addr >= 0x20000000) and name in veneers:
            syms[name] = (veneers[name], True)
    gpath = rel("reference", "globals_arm.csv")
    if os.path.exists(gpath):
        with open(gpath) as f:
            for row in csv.DictReader(r for r in f if not r.startswith("#")):
                syms[row["name"].strip()] = (int(row["address"], 16), False)
    # SDK-facing aliases (stable names used by mods/include/ns36.h)
    alias = {
        "cntlr_settings_process": "cntlr_settings_process",
        "cntlr_submit_input": "cntlr_submit_input",
        "log_printf": "log_printf",
        "rom_memcpy": "rom_memcpy",
        "rom_memcmp": "rom_memcmp",
    }
    for a, target in alias.items():
        if target not in syms:
            sys.exit(f"error: SDK symbol {target} missing from reference/names_arm.csv")
    return syms


def write_symbols(syms, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write("/* generated by tools/modkit.py from reference/*.csv - do not edit */\n")
        for name, (addr, is_fn) in sorted(syms.items(), key=lambda kv: kv[1][0]):
            if not name.replace("_", "a").isalnum() or name[0].isdigit():
                continue
            f.write(f"PROVIDE({name} = 0x{addr | (1 if is_fn else 0):08x});\n")


# --------------------------------------------------------------------------- mods
def load_mods():
    mods = []
    mdir = rel("mods")
    for name in sorted(os.listdir(mdir)):
        spec = os.path.join(mdir, name, "mod.json")
        if not os.path.isfile(spec):
            continue
        with open(spec) as f:
            m = json.load(f)
        m["name"], m["dir"] = name, os.path.join(mdir, name)
        mods.append(m)
    return mods


LINKER_SCRIPT = """
ENTRY(__mods_boot)
INCLUDE "firmware_syms.ld"
MEMORY {{
  FLASH (rx)  : ORIGIN = 0x{flash:08x}, LENGTH = 0x{flash_len:x}
  RAM   (rwx) : ORIGIN = 0x{ram:08x},   LENGTH = 0x{ram_len:x}
{regions}}}
SECTIONS {{
{reclaim}  .text : {{
    KEEP(*(.text.__mods_boot))
    *(.text .text.*)
    *(.rodata .rodata.*)
    . = ALIGN(4);
  }} > FLASH
  .data : {{
    __mod_data_start = .;
    *(.data .data.*)
    . = ALIGN(4);
    __mod_data_end = .;
  }} > RAM AT > FLASH
  __mod_data_load = LOADADDR(.data);
  .bss (NOLOAD) : {{
    __mod_bss_start = .;
    *(.bss .bss.* COMMON)
    . = ALIGN(4);
    __mod_bss_end = .;
  }} > RAM
  /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) }}
}}
"""


def ram_code_source(base, ram_addr):
    """Flash address holding the boot-time copy of RAM code at ram_addr (plain copy entries)."""
    ref = lambda a: struct.unpack_from("<I", base, a - LOAD)[0]
    t0, t1 = SCATTER_REF + ref(SCATTER_REF), SCATTER_REF + ref(SCATTER_REF + 4)
    for e in range(t0, t1, 16):
        src, dst, n, fn = struct.unpack_from("<4I", base, e - LOAD)
        if fn == ROM_COPY and dst <= ram_addr < dst + n:
            return src + ram_addr - dst
    sys.exit(f"error: {ram_addr:#x} is not in a plainly copied RAM region")


def gen_veneers(syms, path):
    """One shared veneer per far firmware function (mask ROM / RAM code) that has no
    vendor veneer in flash, so mod code anywhere in flash reaches it with a plain BL
    (no per-section linker thunks). Unused ones are dropped by --gc-sections; the
    definitions take precedence over the PROVIDE()d addresses."""
    out = [".syntax unified", ".thumb"]
    for name, (addr, is_fn) in sorted(syms.items()):
        if is_fn and (addr < 0x60000 or addr >= 0x20000000) and not name.startswith("thunk_"):
            t = addr | 1
            out += [f'.section .text.vnr.{name},"ax",%progbits', f".global {name}", f".type {name}, %function",
                    ".thumb_func", f"{name}:", f"  movw r12, #0x{t & 0xFFFF:x}", f"  movt r12, #0x{t >> 16:x}",
                    "  bx r12"]
    with open(path, "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    return path


def load_reclaim():
    path = rel("reference", "reclaim_arm.csv")
    if not os.path.isfile(path):
        return []
    with open(path) as f:
        return [(int(r[0], 16), int(r[1], 16)) for r in csv.reader(f) if r and r[0].startswith("0x")]


MAP_LINE = re.compile(r"^\s*([0-9a-f]+)\s+[0-9a-f]+\s+([0-9a-f]+)\s+(\d+)\s+(.+\.o):\((\.(?:text|rodata)\.\S+)\)\s*$")


def map_input_sections(path):
    """(obj, section, size, align) of every live packable input section in an lld map."""
    out = []
    for line in open(path):
        m = MAP_LINE.match(line)
        if m and m.group(5) != ".text.__mods_boot":
            out.append((os.path.basename(m.group(4)), m.group(5), int(m.group(2), 16), int(m.group(3))))
    return out


def pack(items, regions, cap):
    """Fill the reclaimed blocks, largest first, each with the subset of the remaining
    sections that fills it best (0/1 knapsack, ties -> bigger sections). Returns
    {region index: [(obj, sec)]}; whatever is left goes to the main mod area."""
    left = [(obj, sec, (size + 3) & ~3) for obj, sec, size, align in items]   # 4-byte slots
    place = {}
    for i in sorted(range(len(regions)), key=lambda i: -cap[i]):
        c = cap[i] & ~3
        best = {0: (0, ())}                    # used bytes -> (sum of squares, item indices)
        for k, (_, _, n) in enumerate(left):
            if n > c:
                continue
            for used, (sq, ids) in list(best.items()):
                u = used + n
                if u <= c and (u not in best or best[u][0] < sq + n * n):
                    best[u] = (sq + n * n, ids + (k,))
        ids = best[max(best)][1]
        if ids:
            place[i] = [left[k][:2] for k in ids]
            left = [x for k, x in enumerate(left) if k not in ids]
    return place


# Chained hook points: every mod hook of this type runs in mod order, then the
# original vendor call. (site = the BL instruction, expect = its original target)
CHAIN_HOOKS = {
    "input_filter": dict(
        site=LOAD + 0xF976, expect=0x1000FABC, glue="__mods_input",
        proto="void {fn}(cntlr_state_t *s);",
        head="MOD_KEEP uint32_t __mods_input(cntlr_state_t *s) {",
        call="    {fn}(s);", tail="    return cntlr_settings_process(s);"),
    "report_filter": dict(
        site=LOAD + 0xFA14, expect=0x10012A70, glue="__mods_report",
        proto="void {fn}(uint8_t *report, uint32_t len, uint32_t mode);",
        head="MOD_KEEP uint32_t __mods_report(uint8_t *r, uint32_t len, uint32_t a2, uint32_t a3) {",
        call="    {fn}(r, len, NS36_OUTPUT_MODE);",
        tail="    return usb_send_input_report(r, len, a2, a3);"),
}


def gen_glue_c(inits, chains, path):
    """Boot chain (mod init functions, then vendor __rt_entry) and chained-hook dispatchers."""
    lines = ["/* generated by tools/modkit.py - do not edit */", '#include "ns36.h"']
    lines += [f"void {fn}(void);" for fn in inits]
    for kind, fns in chains.items():
        lines += [CHAIN_HOOKS[kind]["proto"].format(fn=fn) for fn in fns]
    # __mods_boot replaces "bl 0x1000428E" at the end of __scatterload. 0x1000428E
    # pops registers that the ROM-called app entry (0x1000427C) pushed, so this
    # stub must leave the stack exactly as it found it and *branch* onward.
    lines += ["void __mods_init_all(void) {"]
    lines += [f"    {fn}();" for fn in inits]
    lines += ["}",
              '__attribute__((naked, used, section(".text.__mods_boot")))',
              "void __mods_boot(void) {",
              r'    __asm volatile("push {r0-r4, lr}\n"      /* 6 regs: keeps 8-byte alignment */',
              r'                   "bl __mods_init_all\n"',
              r'                   "pop {r0-r4, lr}\n"',
              r'                   "b.w __vendor_main\n");',
              "}"]
    for kind, fns in chains.items():
        h = CHAIN_HOOKS[kind]
        lines += [h["head"]] + [h["call"].format(fn=fn) for fn in fns] + [h["tail"], "}"]
    with open(path, "w", newline="") as f:
        f.write(chr(10).join(lines) + chr(10))


# --------------------------------------------------------------------------- thumb encoders
def enc_bl(src, dst, link=True):
    """Thumb-2 BL (link) or B.W (no link) from src to dst."""
    off = (dst & ~1) - (src + 4)
    if not -(1 << 24) <= off < (1 << 24):
        raise ValueError(f"branch out of range {src:#x} -> {dst:#x}")
    s = (off >> 24) & 1
    i1, i2 = (off >> 23) & 1, (off >> 22) & 1
    j1, j2 = (~i1 ^ s) & 1, (~i2 ^ s) & 1
    imm10, imm11 = (off >> 12) & 0x3FF, (off >> 1) & 0x7FF
    hw1 = 0xF000 | (s << 10) | imm10
    hw2 = (0xD000 if link else 0x9000) | (j1 << 13) | (j2 << 11) | imm11
    return struct.pack("<HH", hw1, hw2)


def dec_bl(b, src):
    hw1, hw2 = struct.unpack("<HH", b)
    if hw1 & 0xF800 != 0xF000 or hw2 & 0xD000 != 0xD000:
        return None
    s = (hw1 >> 10) & 1
    j1, j2 = (hw2 >> 13) & 1, (hw2 >> 11) & 1
    i1, i2 = ~(j1 ^ s) & 1, ~(j2 ^ s) & 1
    off = (s << 24) | (i1 << 23) | (i2 << 22) | ((hw1 & 0x3FF) << 12) | ((hw2 & 0x7FF) << 1)
    if s:
        off -= 1 << 25
    return src + 4 + off


# --------------------------------------------------------------------------- build
def build(args):
    base = open(args.base, "rb").read()
    hdr = ns36fw.parse(base)
    code_end = LOAD + ns36fw.CODE_OFF + hdr["code_len"]
    mods = [m for m in load_mods() if m.get("enabled", False)]
    out_dir = rel("build", "mods")
    os.makedirs(out_dir, exist_ok=True)

    syms = load_symbols()
    write_symbols(syms, os.path.join(out_dir, "firmware_syms.ld"))
    syms["__vendor_main"] = (dec_bl(base[MAIN_CALL_SITE - LOAD:MAIN_CALL_SITE - LOAD + 4], MAIN_CALL_SITE), True)
    with open(os.path.join(out_dir, "firmware_syms.ld"), "a", newline="\n") as f:
        f.write(f"PROVIDE(__vendor_main = 0x{syms['__vendor_main'][0] | 1:08x});\n")

    if not mods:
        print("no enabled mods; output equals base image")
        img = base
    else:
        flash = (code_end + 3) & ~3
        clang, lld, objcopy = tool("clang"), tool("lld"), tool("llvm-objcopy")
        inits = [m["init"] for m in mods if m.get("init")]
        chains = {}
        for m in mods:
            for h in m.get("hooks", []):
                if h["type"] in CHAIN_HOOKS:
                    chains.setdefault(h["type"], []).append(h["to"])
        gen_glue_c(inits, chains, os.path.join(out_dir, "glue.c"))
        sources = [os.path.join(out_dir, "glue.c"), rel("mods", "runtime", "rt.c"),
                   gen_veneers(syms, os.path.join(out_dir, "veneers.s"))]
        for m in mods:
            sources += [os.path.join(m["dir"], s) for s in m.get("sources", [])]
            print(f"mod: {m['name']} - {m.get('description', '')}")
        objs = []
        for src in sources:
            obj = os.path.join(out_dir, os.path.basename(os.path.dirname(src)) + "_" + os.path.basename(src) + ".o")
            run([clang, "--target=thumbv7m-none-eabi", "-mcpu=cortex-m3", "-mthumb", "-Oz", "-std=c11",
                 "-ffreestanding", "-fno-builtin", "-fno-pic", "-ffunction-sections", "-fdata-sections",
                 "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-Wall", "-Werror=implicit-function-declaration",
                 "-I", rel("mods", "include"), "-c", src, "-o", obj])
            objs.append(obj)
        elf = os.path.join(out_dir, "mods.elf")
        ld = os.path.join(out_dir, "mods.ld")
        mapf = os.path.join(out_dir, "mods.map")
        keep = [CHAIN_HOOKS[k]["glue"] for k in chains]
        keep += [h["to"] for m in mods for h in m.get("hooks", [])]
        keep_args = [a for k in keep for a in ("-u", k)]

        def link(regions, place, flash_len):
            mem = "".join(f"  R{i} (rx) : ORIGIN = 0x{a:08x}, LENGTH = 0x{e - a:x}\n"
                          for i, (a, e) in enumerate(regions) if i in place)
            sec = "".join(f"  .reclaim{i} : {{\n" + "".join(f"    KEEP(*{o}({s}))\n" for o, s in place[i])
                          + f"  }} > R{i}\n" for i in sorted(place))
            with open(ld, "w", newline="\n") as f:
                f.write(LINKER_SCRIPT.format(flash=flash, flash_len=flash_len, ram=RAM_ORIGIN,
                                             ram_len=RAM_LENGTH, regions=mem, reclaim=sec))
            return subprocess.run([lld, "-flavor", "gnu", "-m", "armelf", "-T", ld, "-L", out_dir,
                                   "--gc-sections", "-e", "__mods_boot", "--no-undefined", "-Map", mapf,
                                   "-o", elf] + keep_args + objs, capture_output=True, text=True)

        # leave room for the relocated scatter table (5 entries * 16 bytes)
        flash_len = FLASH_LIMIT - flash - 5 * 16
        regions = [] if any(m.get("uses_log") for m in mods) else load_reclaim()
        for a, e in regions:   # the image must still hold the strings these blocks were made from
            if any(c not in b"\0\r\n\t" and not 0x20 <= c < 0x7F for c in base[a - LOAD:e - LOAD]):
                sys.exit(f"error: reclaim block {a:#x} does not hold log strings in this firmware")
        place = {}
        if regions:   # pass 1: measure every live function/table, then pack them
            r = link([], {}, 0x10000)
            if r.returncode:
                sys.exit(r.stdout + r.stderr)
            items = map_input_sections(mapf)
            cap = [e - a for a, e in regions]
            for _ in range(32):   # range-extension thunks are only known after linking
                place = pack(items, regions, cap)
                r = link(regions, place, flash_len)
                over = re.findall(r"section '\.reclaim(\d+)' will not fit in region 'R\d+': overflowed by (\d+)", r.stderr)
                if not over:
                    break
                for i, n in over:
                    cap[int(i)] -= int(n)
        else:
            r = link([], {}, flash_len)
        if r.returncode:
            sys.exit(r.stdout + r.stderr)
        binp = os.path.join(out_dir, "mods.bin")
        run([objcopy, "-O", "binary", "--only-section=.text", "--only-section=.data", elf, binp])
        blob = open(binp, "rb").read()
        reclaimed = {}
        for i in place:
            p = os.path.join(out_dir, f"reclaim{i}.bin")
            run([objcopy, "-O", "binary", f"--only-section=.reclaim{i}", elf, p])
            reclaimed[i] = open(p, "rb").read()
        nm = {}
        for line in run([tool("llvm-nm"), elf]).splitlines():
            p = line.split()
            if len(p) == 3:
                nm[p[2]] = int(p[0], 16)
        data_sz = nm["__mod_data_end"] - nm["__mod_data_start"]
        bss_sz = nm["__mod_bss_end"] - nm["__mod_bss_start"]

        img = bytearray(base)
        off = flash - LOAD
        img[off:off + len(blob)] = blob
        end = flash + len(blob)
        if reclaimed:   # mod code/data over the log strings; silence log_printf
            for v in LOG_VENEERS:
                if bytes(base[v - LOAD:v - LOAD + 10]) != LOG_VENEER_BYTES:
                    sys.exit(f"error: log_printf veneer at {v:#x} does not match this firmware")
                img[v - LOAD:v - LOAD + 4] = bytes.fromhex("00207047")   # movs r0, #0; bx lr
            for i, data in reclaimed.items():
                a, e = regions[i]
                assert len(data) <= e - a
                img[a - LOAD:a - LOAD + len(data)] = data
        rec_used = sum(len(d) for d in reclaimed.values())
        rec_total = sum(e - a for a, e in regions)

        # relocated + extended scatter-load table
        ref_val = lambda a: struct.unpack_from("<I", img, a - LOAD)[0]
        t0, t1 = SCATTER_REF + ref_val(SCATTER_REF), SCATTER_REF + ref_val(SCATTER_REF + 4)
        table = bytearray(img[t0 - LOAD:t1 - LOAD])
        if data_sz:
            table += struct.pack("<4I", nm["__mod_data_load"], nm["__mod_data_start"], data_sz, ROM_COPY)
        if bss_sz:
            table += struct.pack("<4I", 0, nm["__mod_bss_start"], bss_sz, ROM_ZERO)
        end = (end + 3) & ~3
        if end + len(table) > FLASH_LIMIT:
            sys.exit(f"error: mods too large: {end + len(table) - flash} bytes, limit {FLASH_LIMIT - flash}")
        img[end - LOAD:end - LOAD + len(table)] = table
        struct.pack_into("<II", img, SCATTER_REF - LOAD, end - SCATTER_REF, end + len(table) - SCATTER_REF)
        end += len(table)

        # hooks
        def resolve(n):
            if n in nm:
                return nm[n]
            if n in syms:
                return syms[n][0] | 1
            sys.exit(f"error: unknown hook target {n}")

        img[MAIN_CALL_SITE - LOAD:MAIN_CALL_SITE - LOAD + 4] = enc_bl(MAIN_CALL_SITE, nm["__mods_boot"])
        for kind, fns in chains.items():
            h = CHAIN_HOOKS[kind]
            o = h["site"] - LOAD
            if dec_bl(bytes(base[o:o + 4]), h["site"]) != h["expect"]:
                sys.exit(f"error: {kind} hook site does not match this firmware version")
            img[o:o + 4] = enc_bl(h["site"], nm[h["glue"]])
            print(f"  hook {kind:13} {h['site']:#010x} -> {h['glue']} ({', '.join(fns)})")
        for m in mods:
            for h in m.get("hooks", []):
                if h["type"] in CHAIN_HOOKS:
                    continue
                site = int(h["site"], 16)
                o = site - LOAD
                tgt = resolve(h["to"])
                if h["type"] == "call":
                    if dec_bl(bytes(img[o:o + 4]), site) is None:
                        sys.exit(f"error: {m['name']}: no BL instruction at {site:#x}")
                    if "expect" in h and dec_bl(bytes(base[o:o + 4]), site) != int(h["expect"], 16):
                        sys.exit(f"error: {m['name']}: BL at {site:#x} does not call {h['expect']} (wrong firmware?)")
                    img[o:o + 4] = enc_bl(site, tgt)
                elif h["type"] == "replace":
                    img[o:o + 4] = enc_bl(site, tgt, link=False)
                elif h["type"] == "pointer":
                    struct.pack_into("<I", img, o, tgt | 1)
                elif h["type"] == "ram_replace":
                    # function copied to RAM at boot: patch its copy source in flash
                    # with "ldr.w pc, [pc, #0]; .word fn" (needs a 4-aligned entry)
                    src = ram_code_source(base, site)
                    if site & 3:
                        sys.exit(f"error: {m['name']}: ram_replace site {site:#x} must be 4-aligned")
                    o = src - LOAD
                    img[o:o + 8] = bytes.fromhex("dff800f0") + struct.pack("<I", tgt | 1)
                else:
                    sys.exit(f"error: {m['name']}: unknown hook type {h['type']}")
                print(f"  hook {h['type']:7} {site:#010x} -> {h['to']} ({tgt:#010x})")

        struct.pack_into("<I", img, 0x20, end - LOAD - ns36fw.CODE_OFF)
        img = bytes(img)
        used = end - flash
        print(f"mods: {used} bytes flash ({FLASH_LIMIT - end} free), {data_sz + bss_sz} bytes RAM "
              f"({RAM_LENGTH - data_sz - bss_sz} free), {rec_used} bytes in {len(reclaimed)} reclaimed "
              f"log-string blocks ({rec_total - rec_used} free" + (", log_printf disabled)" if reclaimed else ")"))

    ns36fw.parse(img)
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    open(args.output, "wb").write(img)
    print(f"wrote {args.output}")


def cmd_list(_):
    for m in load_mods():
        print(f"{'[x]' if m.get('enabled') else '[ ]'} {m['name']:20} {m.get('description', '')}")


def cmd_symbols(_):
    path = rel("build", "mods", "firmware_syms.ld")
    write_symbols(load_symbols(), path)
    print(f"wrote {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("build")
    p.add_argument("--base", default=rel("firmware", "NS36_V3.4.bin"))
    p.add_argument("-o", "--output", default=rel("build", "NS36_mod.bin"))
    p.set_defaults(fn=build)
    sp.add_parser("list").set_defaults(fn=cmd_list)
    sp.add_parser("symbols").set_defaults(fn=cmd_symbols)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
