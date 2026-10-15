#!/usr/bin/env python3
"""Turn a modkit build into a firmware patch that contains no GuliKit code.

The companion app ships this patch and applies it to the user's own official
firmware file, so the project never hosts or distributes GuliKit's firmware.

Every byte range that differs from the official image becomes either
  - a literal write of our own bytes (mod code, our tables, patched instructions), or
  - a copy from elsewhere in the user's file, for anything that matches the official
    image (e.g. the relocated scatter-load table), so no vendor bytes are embedded.
The app checks the official file's SHA-256 before patching and the result's after.

    python tools/modkit.py build -o build/NS36_mod.bin
    python tools/make_patch.py firmware/NS36_V3.4.bin build/NS36_mod.bin app/assets/firmware_patch.json [version]
"""
import hashlib
import json
import sys

MIN_COPY = 8       # vendor sequences this long or longer are always copied, never embedded


def ranges(a, b):
    i, n = 0, len(a)
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            yield i, j
            i = j
        else:
            i += 1


def main():
    if len(sys.argv) not in (4, 5):
        sys.exit(__doc__)
    base = open(sys.argv[1], "rb").read()
    mod = open(sys.argv[2], "rb").read()
    if len(base) != len(mod):
        sys.exit("error: images differ in size")
    grams = {}
    for i in range(len(base) - MIN_COPY + 1):
        grams.setdefault(base[i:i + MIN_COPY], i)
    ops, literal, copied = [], 0, 0
    for start, end in ranges(base, mod):
        i, lit = start, bytearray()
        while i < end:
            src = grams.get(mod[i:i + MIN_COPY]) if end - i >= MIN_COPY else None
            if src is not None:
                n = MIN_COPY
                while i + n < end and src + n < len(base) and base[src + n] == mod[i + n]:
                    n += 1
                if lit:
                    ops.append({"at": i - len(lit), "write": lit.hex()})
                    literal += len(lit)
                    lit = bytearray()
                ops.append({"at": i, "copy_from": src, "len": n})
                copied += n
                i += n
            else:
                lit.append(mod[i])
                i += 1
        if lit:
            ops.append({"at": end - len(lit), "write": lit.hex()})
            literal += len(lit)
    # self-check: no vendor sequence of MIN_COPY bytes or more survives in the literals
    for op in ops:
        if "write" in op:
            w = bytes.fromhex(op["write"])
            assert not any(w[k:k + MIN_COPY] in grams for k in range(len(w) - MIN_COPY + 1))
    patch = {
        "name": "Goku 2 Adapter Super Saiyan Mod",
        "version": sys.argv[4] if len(sys.argv) > 4 else "1.0.0",
        "base": {"name": "GuliKit NS36 (Goku 2) firmware V3.4", "size": len(base),
                 "sha256": hashlib.sha256(base).hexdigest()},
        "result_sha256": hashlib.sha256(mod).hexdigest(),
        "ops": ops,
    }
    # applying the patch to the base must reproduce the build exactly
    out = bytearray(base)
    for op in ops:
        if "write" in op:
            w = bytes.fromhex(op["write"])
            out[op["at"]:op["at"] + len(w)] = w
        else:
            out[op["at"]:op["at"] + op["len"]] = base[op["copy_from"]:op["copy_from"] + op["len"]]
    assert bytes(out) == mod
    with open(sys.argv[3], "w", newline="\n") as f:
        json.dump(patch, f, indent=1)
    print(f"{len(ops)} ops: {literal} bytes of mod code/data, {copied} bytes copied from the user's file")


if __name__ == "__main__":
    main()
