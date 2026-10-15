# Reverse-engineering workflow

The decompiled sources in `src/*/decompiled/` are **generated locally** from your own
official firmware file (`firmware/NS36_V3.4.bin`, git-ignored) and are never committed. Knowledge lives in the
`reference/` tables; the pipeline re-applies it on every run, so improvements are
reviewable diffs instead of hand edits to 40k lines of pseudo-C.

## Regenerate

```bash
export GHIDRA_INSTALL_DIR=/path/to/ghidra_12.1.4_PUBLIC
python tools/ghidra/patch_riscv_bitmanip.py "$GHIDRA_INSTALL_DIR"   # once per Ghidra install
bash tools/decompile.sh                                            # ~2 minutes
```

`patch_riscv_bitmanip.py` gives Ghidra's Zba/Zbb/Zbs instructions real semantics (stock
Ghidra marks them `unimpl`; the MSP uses them). It keeps a `.orig` backup;
`--revert` restores it.

## What the pipeline does

ARM (`SetupMemoryArm.java` pre-script, `ExportAll.java` post-script):
- loads the file at `0x10003000`, marks flash read-only (literal pools fold to constants);
- maps a stub mask ROM so ROM calls show as `rom_XXXXX()`;
- rebuilds `.data` exactly like `__scatterload` (incl. the LZ decompression) so RAM
  functions and initial values are visible;
- finds functions via vectors, `__main`, ARMCC veneers, code pointers and prologues;
- types literal-pool words as pointers; drops code found in the `.data` load image;
- applies `names_arm.csv`, `types_arm.h`, `prototypes_arm.csv`, `globals_arm.csv`,
  `data_arm.csv`; auto-names the rest from their log strings;
- decompiles everything, split into 8 KB files by address.

MSP (`SetupMemoryMsp.java`, `ExportRiscv.java`): reproduces the startup copy to
`0x1FFFC000`, sets `gp`, labels WCH peripheral registers, applies `names_msp.csv`.

## Contributing knowledge

| To record… | Edit | Format |
|---|---|---|
| a function name | `reference/names_arm.csv` / `names_msp.csv` | `0xADDR,name,"how you know"` |
| a function signature | `reference/prototypes_arm.csv` | `0xADDR\|C prototype` |
| a struct/enum | `reference/types_arm.h` (+ mirror in `mods/include/ns36.h`) | plain C |
| a global variable | `reference/globals_arm.csv` | `0xADDR,name,"comment",type` |
| a data table in code | `reference/data_arm.csv` | `0xADDR,len,name,"comment"` |

Conventions: say how a name was established in its comment (`[inferred]` when it's
a guess). Prefer names from the firmware's own log strings. ROM functions keep the
`rom_` prefix. Run `bash tools/decompile.sh` and commit the regenerated output with the
table change.

## Coverage today

- ARM: 970 functions decompiled; ~92 KB of 109 KB in the code region is disassembled,
  the rest is rodata/tables. 3 ARMCC fplib routines show "bad instruction" because
  their error helpers take inline literals after `BL` (harmless; library code).
- Naming (ARM): 53 manual, 68 from log strings, 145 veneers/thunks, and **712 tagged by
  subsystem** from `reference/modules_arm.csv` (`<module>[_role]_<addr>`, e.g.
  `bt_gatt_pdu_10004b48`, role = `_pdu` builds an ATT/L2CAP packet, `_hcicmd` sends an
  HCI command, `_post` posts to the scheduler, `_log` logs). No `FUN_*` names remain.
  A module tag tells you *where* a function lives, not exactly *what* it does —
  replacing tags with real names in `names_arm.csv` is the main ongoing task.
- Fully understood so far: boot/scatter-load, the input pipeline, all six USB output
  encoders, Switch Pro input parsing, config block, MSP framing, P-256 bignum helpers,
  heap/list/scheduler/IRQ primitives.
- MSP: 154 functions, no unimplemented instructions after the bitmanip patch; all named
  (`_start`, `msp_main`, log-string names, and `msp_[ram_]{usbh,uart,sys,fn}_<addr>` by
  the peripheral each function touches).
- **Not decompilable from the update file:** the main SoC's ~384 KB mask ROM
  (`0x0–0x60000`: boot ROM and most of the Bluetooth stack) and the bootloader at
  `0x10000000`. They aren't in the update file; obtaining them needs a dump from a
  physical device (SWD/JTAG, or a code-read mod running on hardware). Calls into them
  are named `rom_*` and documented where their role is known.

## Open questions (good first issues)

1. The four u16 header words (`docs/firmware-format.md`) — needs another firmware version.
2. Identify the main BT SoC (mask-ROM layout at `0x0`, peripheral map). This would let
   us name the `rom_*` functions from the vendor SDK.
3. Remaining `cntlr_state_t` fields (`+0x24..+0x53`: rumble, touchpad, battery).
4. The USB output path for each mode (descriptors, rumble/LED feedback to controllers).
5. MSP command set over the UART link.
6. Whether RAM `0x2000DF40–0x2000E740` (mod RAM) is truly unused at runtime.
