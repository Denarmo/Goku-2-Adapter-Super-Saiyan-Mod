#!/usr/bin/env python3
"""ns36fw - inspect, unpack and repack GuliKit NS36 (Goku 2) update images.

Update image layout (see docs/firmware-format.md):

    0x00000  header  "GULIKIT_NS36_UPDATE_BIN\\0", 4x u16 (unknown), u32 code_len, u32 aux_len
    0x01000  code    Cortex-M vector table + Thumb code/rodata, code_len bytes
    0x1C000  aux     auxiliary table (pointers into code/RAM), aux_len bytes
    ...      0xFF padding up to 128 KiB

Usage:
    python tools/ns36fw.py info   <image.bin>
    python tools/ns36fw.py unpack <image.bin> <outdir>
    python tools/ns36fw.py pack   <dir> <out.bin>
"""
import argparse
import json
import os
import struct
import sys

MAGIC = b"GULIKIT_NS36_UPDATE_BIN\0"
IMAGE_SIZE = 0x20000
CODE_OFF = 0x1000
AUX_OFF = 0x1C000
LOAD_ADDR = 0x10003000  # flash address the whole update file is written to
HDR_FMT = "<24s4HII"  # magic, unk[4], code_len, aux_len


def parse(data):
    if len(data) != IMAGE_SIZE:
        raise ValueError(f"image must be {IMAGE_SIZE:#x} bytes, got {len(data):#x}")
    magic, u0, u1, u2, u3, code_len, aux_len = struct.unpack_from(HDR_FMT, data, 0)
    if magic != MAGIC:
        raise ValueError("bad magic (not an NS36 update image)")
    if CODE_OFF + code_len > AUX_OFF or AUX_OFF + aux_len > IMAGE_SIZE:
        raise ValueError("section lengths out of range")
    return {
        "unknown_u16": [u0, u1, u2, u3],
        "code_len": code_len,
        "aux_len": aux_len,
        "code": data[CODE_OFF:CODE_OFF + code_len],
        "aux": data[AUX_OFF:AUX_OFF + aux_len],
    }


def assemble(unknown_u16, code, aux):
    if CODE_OFF + len(code) > AUX_OFF:
        raise ValueError(f"code too large: {len(code):#x} > {AUX_OFF - CODE_OFF:#x}")
    if AUX_OFF + len(aux) > IMAGE_SIZE:
        raise ValueError("aux too large")
    img = bytearray(b"\xff" * IMAGE_SIZE)
    struct.pack_into(HDR_FMT, img, 0, MAGIC, *unknown_u16, len(code), len(aux))
    img[CODE_OFF:CODE_OFF + len(code)] = code
    img[AUX_OFF:AUX_OFF + len(aux)] = aux
    return bytes(img)


def cmd_info(a):
    data = open(a.image, "rb").read()
    h = parse(data)
    vec = struct.unpack_from("<4I", data, CODE_OFF)
    print(f"magic        : {MAGIC[:-1].decode()}")
    print(f"unknown u16  : {[hex(x) for x in h['unknown_u16']]}")
    print(f"code         : {CODE_OFF:#07x} + {h['code_len']:#x}")
    print(f"aux          : {AUX_OFF:#07x} + {h['aux_len']:#x}")
    print(f"initial SP   : {vec[0]:#010x}")
    print(f"reset vector : {vec[1]:#010x}")


def cmd_unpack(a):
    data = open(a.image, "rb").read()
    h = parse(data)
    os.makedirs(a.outdir, exist_ok=True)
    open(os.path.join(a.outdir, "code.bin"), "wb").write(h["code"])
    open(os.path.join(a.outdir, "aux.bin"), "wb").write(h["aux"])
    with open(os.path.join(a.outdir, "header.json"), "w") as f:
        json.dump({"unknown_u16": h["unknown_u16"]}, f, indent=2)
    print(f"unpacked to {a.outdir}")


def cmd_pack(a):
    hdr = json.load(open(os.path.join(a.dir, "header.json")))
    code = open(os.path.join(a.dir, "code.bin"), "rb").read()
    aux = open(os.path.join(a.dir, "aux.bin"), "rb").read()
    open(a.out, "wb").write(assemble(hdr["unknown_u16"], code, aux))
    print(f"wrote {a.out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("info"); p.add_argument("image"); p.set_defaults(fn=cmd_info)
    p = sp.add_parser("unpack"); p.add_argument("image"); p.add_argument("outdir"); p.set_defaults(fn=cmd_unpack)
    p = sp.add_parser("pack"); p.add_argument("dir"); p.add_argument("out"); p.set_defaults(fn=cmd_pack)
    a = ap.parse_args()
    try:
        a.fn(a)
    except ValueError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
