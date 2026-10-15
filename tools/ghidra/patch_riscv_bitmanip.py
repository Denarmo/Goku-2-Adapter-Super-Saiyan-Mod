#!/usr/bin/env python3
"""Give Ghidra's RISC-V bitmanip instructions real p-code semantics.

Ghidra (12.1.x) decodes Zba/Zbb/Zbs instructions (riscv.rv32b.sinc) but marks
them `unimpl`, so the decompiler stops at every `zext.h`/`sext.b`/`min`/`sh2add`.
The WCH QingKe core in the Goku 2's USB-host co-processor uses them, so this
script patches the sinc in place (keeping a .orig backup). Ghidra recompiles the
language automatically the next time it loads it.

    python tools/ghidra/patch_riscv_bitmanip.py [GHIDRA_INSTALL_DIR]
    python tools/ghidra/patch_riscv_bitmanip.py --revert [GHIDRA_INSTALL_DIR]

Semantics are XLEN-generic except where noted (bit index masked to 5 bits: RV32).
"""
import os
import re
import shutil
import sys

SEM = {
    "andn":   "rd = rs1 & ~rs2;",
    "orn":    "rd = rs1 | ~rs2;",
    "xnor":   "rd = ~(rs1 ^ rs2);",
    "max":    "local c = rs1 s< rs2; rd = (zext(c) * rs2) + (zext(!c) * rs1);",
    "maxu":   "local c = rs1 < rs2;  rd = (zext(c) * rs2) + (zext(!c) * rs1);",
    "min":    "local c = rs1 s< rs2; rd = (zext(c) * rs1) + (zext(!c) * rs2);",
    "minu":   "local c = rs1 < rs2;  rd = (zext(c) * rs1) + (zext(!c) * rs2);",
    "pack":   "rd = (rs2 << 16) | (rs1 & 0xffff);",            # RV32 pack (rs2=zero: zext.h)
    "sext.b": "rd = sext(rs1:1);",
    "sext.h": "rd = sext(rs1:2);",
    "sh1add": "rd = rs2 + (rs1 << 1);",
    "sh2add": "rd = rs2 + (rs1 << 2);",
    "sh3add": "rd = rs2 + (rs1 << 3);",
    "sbclr":  "rd = rs1 & ~(1 << (rs2 & 31));",
    "sbclri": "rd = rs1 & ~(1 << op2026);",
    "sbext":  "rd = (rs1 >> (rs2 & 31)) & 1;",
    "sbexti": "rd = (rs1 >> op2026) & 1;",
    "sbinv":  "rd = rs1 ^ (1 << (rs2 & 31));",
    "sbinvi": "rd = rs1 ^ (1 << op2026);",
    "sbset":  "rd = rs1 | (1 << (rs2 & 31));",
    "sbseti": "rd = rs1 | (1 << op2026);",
}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ghidra = args[0] if args else os.environ.get("GHIDRA_INSTALL_DIR")
    if not ghidra:
        sys.exit("usage: patch_riscv_bitmanip.py [--revert] GHIDRA_INSTALL_DIR")
    sinc = os.path.join(ghidra, "Ghidra", "Processors", "RISCV", "data", "languages", "riscv.rv32b.sinc")
    orig = sinc + ".orig"
    if "--revert" in sys.argv:
        if os.path.exists(orig):
            shutil.copy2(orig, sinc)
            print("reverted", sinc)
        return
    if not os.path.exists(orig):
        shutil.copy2(sinc, orig)
    src = open(orig).read()
    n = 0

    def repl(m):
        nonlocal n
        sem = SEM.get(m.group(2))
        if not sem:
            return m.group(0)
        n += 1
        return f"{m.group(1)}\n{{\n\t{sem}\n}}"

    out = re.sub(r"^(:(\S+)\s.*?)\s+unimpl\s*$", repl, src, flags=re.M)
    open(sinc, "w", newline="\n").write(out)
    # force recompilation of every RISC-V language that includes this file
    for f in os.listdir(os.path.dirname(sinc)):
        if f.startswith("riscv") and f.endswith(".slaspec"):
            os.utime(os.path.join(os.path.dirname(sinc), f))
    print(f"patched {n} instructions in {sinc} (backup: {orig})")


if __name__ == "__main__":
    main()
