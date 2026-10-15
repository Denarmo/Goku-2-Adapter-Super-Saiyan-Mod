# Writing firmware mods

Mods are small C programs compiled with clang and linked **into** the vendor V3.4
firmware. They hook defined points of the firmware, so they can change controller input,
the USB reports sent to the console, or run code at boot — without rebuilding the
vendor code.

## Requirements

- Your own copy of GuliKit's official firmware V3.4 at `firmware/NS36_V3.4.bin`
  (git-ignored). Builds contain GuliKit's code: test them on your own adapter and never
  share them. To ship a mod to others, ship a patch (`tools/make_patch.py`), as the
  companion app does.
- Python 3
- LLVM: `clang`, `lld`, `llvm-objcopy`, `llvm-nm` on `PATH` (or set `LLVM_BIN`).
  Any recent LLVM works; Windows: `winget install LLVM.LLVM` or the WinLibs build.
- Optional: `pip install unicorn` for `tools/emu_test.py`.

## Build

```bash
python tools/modkit.py list                 # show mods and whether they're enabled
python tools/modkit.py build                # -> build/NS36_mod.bin
python tools/emu_test.py build/NS36_mod.bin # boot + hook smoke test in an emulator
```

Enable a mod by setting `"enabled": true` in its `mods/<name>/mod.json`.

## Anatomy of a mod

```
mods/my_mod/
  mod.json
  my_mod.c
```

```json
{
  "description": "One line shown by modkit list",
  "enabled": true,
  "sources": ["my_mod.c"],
  "init": "my_mod_init",
  "hooks": [
    { "type": "input_filter",  "to": "my_input" },
    { "type": "report_filter", "to": "my_report" }
  ]
}
```

```c
#include "ns36.h"

static uint8_t enabled = 1;          /* .data and .bss work: initialized at boot */

void my_mod_init(void) { log_printf("my_mod ready\r\n"); }

void my_input(cntlr_state_t *s)       /* every input frame, before turbo/hotkeys */
{
    if (enabled && (s->buttons & BTN_ZL)) s->ly = -s->ly;
}

void my_report(uint8_t *report, uint32_t len, uint32_t mode)  /* final USB report */
{
    if (mode == OUT_PS5 && len > 6) { /* edit DualSense report bytes */ }
}
```

The SDK header `mods/include/ns36.h` documents `cntlr_state_t`, the `BTN_*` bits, the
`OUT_*` output modes and the firmware functions/globals you can call. Every named
function in `reference/arm_functions.csv` and every global in
`reference/globals_arm.csv` is also available as a linker symbol.

## Hook types

| Type | Signature | Runs |
|---|---|---|
| `init` (key in mod.json) | `void fn(void)` | once at boot, after RAM init, **before the vendor app init**: only touch your own RAM — no `log_printf`, heap or peripherals yet |
| `input_filter` | `void fn(cntlr_state_t *s)` | every frame, after a driver normalized the controller input, before the settings/turbo engine. Chainable. |
| `report_filter` | `void fn(uint8_t *report, uint32_t len, uint32_t mode)` | after encoding, just before `usb_send_input_report`. Chainable. |
| `call` | any | `{"site": "0x...", "to": fn, "expect": "0x..."}` retargets one BL; the original target is reachable by its symbol name |
| `replace` | any | `{"site": "0x<function entry>", "to": fn}` B.W over a function entry |
| `pointer` | any | `{"site": "0x...", "to": fn}` overwrites a 32-bit code pointer in a table |
| `ram_replace` | any | `{"site": "0x2000....", "to": fn}` jumps from a function the firmware copies to RAM at boot (patches its copy source); the site must be 4-aligned |

Chained hooks of all mods run in alphabetical mod order.

## Limits

- **Flash: 1388 bytes** in the free gap after the vendor code (before the MSP image at
  `0x1C000`), **plus ~3.6 KB reclaimed** from the vendor's debug-log format strings
  (`reference/reclaim_arm.csv`, from `tools/find_reclaimable.py`: only blocks whose every
  string is used solely by `log_printf`). modkit links once to measure every function and
  table, packs them into the reclaimed blocks (largest first, knapsack fit), keeps the rest
  in the main gap, and turns `log_printf` into a no-op. The blocks are small (16–256
  bytes), so keep functions small: split big ones into `__attribute__((noinline))`
  helpers. A mod that needs the debug log sets `"uses_log": true`, which turns reclaiming off.
- Mods are built with `-Oz`. Calls into the mask ROM and RAM code go through the vendor's
  flash veneers, or shared veneers modkit generates, so they cost no per-call thunks.
- The update file's header page (0x1000 bytes) and the tail after the MSP image are **not**
  written by the bootloader (hardware-checked), so they can't hold mod code.
- **RAM: 2048 bytes** at `0x2000DF40` for mod `.data` + `.bss`.
- No heap of your own; `rom_malloc`/`rom_free` exist but are shared with the BT stack.
- Code runs in the firmware's main loop: keep `input_filter`/`report_filter` short
  (they run at the controller report rate, ~125–1000 Hz).
- Soft-float only (no FPU). Prefer integer math.

## How a mod build is put together

1. `firmware_syms.ld` is generated from `reference/*.csv`.
2. Mods + generated glue are compiled (`thumbv7m`, `-Os`) and linked by `ld.lld` at
   `0x1001EA94`; calls into the mask ROM get lld long-branch thunks automatically.
3. The ARMCC scatter-load table is relocated after the mod code and extended with a
   copy entry (mod `.data`) and a zero entry (mod `.bss`), and the two PC-relative
   table pointers at `0x10004218` are updated.
4. BL patches: `0x100041FE` → `__mods_boot` (runs `init`s, then `__rt_entry`);
   `0x10012976` → `__mods_input`; `0x10012A14` → `__mods_report`. Each site is checked
   against its expected original target, so a different firmware version fails loudly.
5. `code_len` in the header is increased to cover the mod area.

`tools/emu_test.py` then executes the real boot path (`__main` → scatter-load → mod init
→ vendor `__rt_entry`) and the input hook in Unicorn, and checks that vendor RAM is
byte-identical to a stock boot.

## Testing on hardware — read first

Verified on a real Goku 2 (see `docs/hardware-observations.md`): modded images are
accepted by the bootloader, the boot hook and `input_filter` work.

1. Keep the official `NS36_V3.4.bin` at hand to flash back.
2. Run `python tools/emu_test.py <image>` first — it must PASS (it checks the exact
   register/stack state the vendor code expects at boot).
3. Flash: hold the side button while plugging in, copy the `.bin` to the `GuliKit` drive.
   **Replug afterwards** — the receiver does not always restart by itself.
4. LED off / no USB after a replug = the image doesn't run. Re-enter update mode and copy
   the official file back; the bootloader is not touched by updates.
5. Use logical buttons (`lb_get`/`lb_set`, `LB_*`), never raw bit numbers — the bit
   layout of `cntlr_state_t.buttons` depends on the connected controller.
6. Check results from a PC: `tools/xinput_probe.py` (Xbox 360 mode) or
   `tools/hid_probe.py` (PS5 mode).
