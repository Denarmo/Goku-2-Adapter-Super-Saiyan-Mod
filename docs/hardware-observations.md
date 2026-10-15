# Hardware observations

Read-only captures from a real Goku 2 (firmware V3.4) connected to a Windows PC.
Each entry says what was observed and which reverse-engineered claim it confirms.

## 2026-10-14 — PS5 output mode, DualSense paired over Bluetooth

USB enumeration: `054C:0CE6` "DualSense Wireless Controller" (Sony Interactive
Entertainment), serial "0", HID on interface 3. Windows' device history also shows the
adapter earlier as `045E:028E` **"GuliKit X"** (Xbox 360 output mode).

Feature reports (GET_FEATURE, read-only):

| ID | Data | Notes |
|---|---|---|
| `0x09` | `<6-byte MAC> 08 25 00 0b 00 00 0e 7f 04 …` | MAC bytes are in the firmware's `.data` at `0x2000CDD6` (load image file offset `0x1B791`) → answered by the Goku, not forwarded |
| `0x20` | `"Jun 24 2024" "11:55:41"` + version words | string not present in the firmware → most likely forwarded from the paired DualSense (unverified) |
| `0x05` | all zero | |

Input report 0x01 at rest (64 bytes):
```
01 81 84 7a 7f 00 00 98 08 00 00 00 98 9b 00 00 0c 00 f7 ff 0a 00 d1 01 10 e0 32 fb ...
```
Confirms `out_encode_ps5` (output mode 5): sticks at bytes 1–4 (`(s16>>8)+0x80`, Y
inverted), L2/R2 at 5–6, buttons u32 at 8 with the D-pad hat in the low nibble
(`8` = neutral), byte 7 increments per report, IMU at 16–27 (gravity visible on accel).

Tool: `tools/hid_probe.py` (ctypes, no dependencies).

## 2026-10-14 — first flash tests (bootloader "GuliKit 2.3"/"3.4" drive label)

The update drive label changed from "GuliKit 2.3" to "GuliKit 3.4" after the first
flash; after an update the receiver sometimes needs a **replug** before it starts.

| # | Image | Result | Conclusion |
|---|---|---|---|
| 1 | `boot_banner` (old modkit) | no LED, no USB | bug: boot stub was not stack-neutral (see below) |
| 2 | `hw_probe` no-op (old modkit) | no LED, no USB | same bug |
| A | official + 1 byte changed in a log string | **boots** | content is not checksummed; the 4 header u16s are not enforced as a content checksum |
| B | official + `code_len` grown by 0x80 | **boots** | a longer code section is accepted |
| 3 | `hw_probe` no-op, fixed boot stub | **boots** | modkit layout (code after vendor image, relocated scatter table, boot hook) works |
| 4 | `button_swap` v1 (Nintendo bit layout) | boots, no visible swap | `cntlr_state_t.buttons` is in each controller's *native* layout |
| 5 | `button_swap` v2 (logical buttons via firmware table) | **boots, A↔B and X↔Y swapped** | input_filter hook works on hardware |

Boot-path finding: the ROM calls the app entry `0x1000427C`, which saves registers,
runs `__main`/`__scatterload`, then `0x1000428E` pops those registers and branches to
the app init `0x10013290`, which *returns* to the ROM. A mod boot stub must therefore be
stack-neutral (fixed in modkit; `tools/emu_test.py` now checks registers/stack at the
app init against a stock boot and reproduces the old failure).

Test #5 capture (Xbox 360 output mode, DualSense over BT, `tools/xinput_probe.py`):
Cross→B, Circle→A, Square→Y, Triangle→X (stock: Cross→A, Circle→B, Square→X, Triangle→Y).
