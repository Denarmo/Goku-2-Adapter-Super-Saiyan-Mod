# NS36 update file format

`NS36_V3.4.bin`, 131072 bytes. The bootloader writes the whole file to flash at
**`0x10003000`**, so *runtime address = file offset + 0x10003000* for the ARM part.

| File offset | Size | Contents |
|---|---|---|
| `0x00000` | 24 | Magic `GULIKIT_NS36_UPDATE_BIN\0` |
| `0x00018` | 4 × u16 | `3D 00 43 00 3B 00 4C 00` — **unknown** (see below) |
| `0x00020` | u32 | `code_len` = `0x1AA94` — ARM code + rodata + `.data` load image |
| `0x00024` | u32 | `aux_len` = `0x39C8` — MSP RISC-V firmware |
| `0x00028` | | `0xFF` padding |
| `0x01000` | `code_len` | ARM image (vector table first) |
| `0x01000+code_len` | to `0x1C000` | `0xFF` — free (mods go here; `code_len` is grown to cover them) |
| `0x1C000` | `aux_len` | MSP image (starts with `j 0x760`) |
| | to `0x20000` | `0xFF` padding |

`tools/ns36fw.py info|unpack|pack` reads and writes this layout; repacking an unpacked
image is byte-identical.

## The unknown header words

`3D 43 3B 4C` are not a byte sum, XOR, CRC-16 (CCITT, both inits), CRC-32 or modular
sum of the whole file, either section, or quarters of them (tested exhaustively for
those families). They may be bootloader parameters (IDs, flash layout) or a
checksum with an unusual algorithm. **Comparing other firmware versions would settle
it** — GuliKit's download page requires a CAPTCHA, so they must be fetched by hand:

| Version | Official download (gulikit.com) |
|---|---|
| V2.8 (2026-05-28) | `https://gulikit.com/filedownload/2998601` |
| V2.9 (2026-06-03) | `https://gulikit.com/filedownload/3023372` |
| V3.0 (2026-06-22) | `https://gulikit.com/filedownload/3024457` |
| V3.4 (2026-07-27) | `https://gulikit.com/filedownload/3026283` (this repo's base) |

(IDs taken from Wayback Machine snapshots of
`https://www.gulikit.com/newsinfo/3196031.html`.) Put extracted `.bin` files in
`firmware/` and run `python tools/ns36fw.py info` on each.

Until this is solved, modded images keep the original four words. If the bootloader
does validate them, a modded file will simply be rejected (the receiver stays in update
mode, the old firmware is untouched — inferred, not yet observed).

## Vendor update procedure

Hold the side button while plugging in → USB drive `GuliKit *` appears → copy the
`.bin` to its root → the receiver flashes and reboots. Unplug before copying to abort.
Extract the zip first; dragging straight out of an archive can fail.
