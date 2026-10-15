#!/usr/bin/env python3
"""Write reference/strings_{arm,msp}.txt: printable strings with runtime addresses."""
import os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
from ns36fw import parse, CODE_OFF, LOAD_ADDR

img = open(sys.argv[1] if len(sys.argv) > 1 else "firmware/NS36_V3.4.bin", "rb").read()
h = parse(img)
out = os.path.join(os.path.dirname(__file__), "..", "reference")
for name, blob, base in (("arm", h["code"], LOAD_ADDR + CODE_OFF), ("msp", h["aux"], 0)):
    with open(os.path.join(out, f"strings_{name}.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# runtime address\tstring\n")
        for m in re.finditer(rb"[\x20-\x7e\t\r\n]{5,}", blob):
            s = m.group().decode().replace("\r", "\r").replace("\n", "\n")
            f.write(f"0x{base + m.start():08x}\t{s}\n")
