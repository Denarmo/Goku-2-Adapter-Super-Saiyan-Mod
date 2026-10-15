# Goku 2 (NS36) firmware architecture

What the V3.4 firmware is made of, as recovered by reverse engineering.
**Observed** = read directly from the image or verified in emulation;
**inferred** = best explanation of the evidence, not yet confirmed on hardware.

## Two processors, one update file

| | Main MCU | MSP co-processor |
|---|---|---|
| Role | Bluetooth host + controller drivers + USB device to the console/PC | USB **host** for wired controllers |
| CPU | ARM Cortex-M3/M4 class, Thumb-2, hardware divide, no FPU (observed) | WCH QingKe RISC-V RV32IMC + Zba/Zbb/Zbs (observed) |
| Chip | unidentified BT SoC with a ~384 KB mask ROM holding the BT stack | WCH CH57x/CH58x family (register map matches, inferred) |
| Code in update file | `0x01000 + code_len` (106 KB) | `0x1C000 + aux_len` (14.8 KB) |
| Toolchain | Keil ARMCC + MicroLib (`__scatterload`, fplib, RW compression) | GCC-style RISC-V startup (`gp`-relative data) |
| Decompiled | `src/arm/decompiled/` — 970 functions | `src/msp/decompiled/` — 154 functions |

The two talk over a UART with a small framed protocol (see *MSP link* below).
The update file carries both images; the bootloader (not in the file) programs them.

## Main MCU memory map

| Address | Size | Contents |
|---|---|---|
| `0x00000000` | ~0x60000 | Mask ROM: boot code, C runtime helpers, RivieraWaves-style BT stack (`co_list`, heap, scheduler, HCI/L2CAP/GATT/SMP). Reached only through 141 `movw/movt/bx r12` veneers. Contents unknown — calls appear as `rom_XXXXX()`. |
| `0x10000000` | 0x3000 | Bootloader / USB mass-storage updater (inferred; not in the update file) |
| `0x10003000` | 0x1000 | Update header (the whole file is written here) |
| `0x10004000` | | Vector table, app header (`RUNP` magic @ `0x10004138`, `NS36` tag @ `0x100041DC`) |
| `0x100041E4` | | `__main` → `__scatterload` → `__rt_entry` (`0x1000428E`) |
| `0x10004000–0x1001DA14` | | code + rodata |
| `0x1001DA14–0x1001EA94` | 0x1080 | `.data` load image (plain + LZ-compressed) |
| `0x1001EA94–0x1001F000` | 0x56C | **free flash** — used by mods |
| `0x1001F000–0x100229C8` | 0x39C8 | MSP firmware blob (not executed by the ARM) |
| `0x20000000–0x2000BFFF` | 48 KB | RAM used by mask ROM / BT controller |
| `0x2000C000` | 0x1308 | `.data` incl. RAM-resident USB/flash routines (`ramfn_*`) |
| `0x2000D308` | 0xC1C | `.bss` |
| `0x2000DF40` | 0x800 | **mod RAM** (unreferenced by vendor code; verify on hardware) |
| `0x2000FFFC` | 4 | warm-boot mailbox `AA mode ~mode 55` (survives reset) |

Initial SP in the vector table is `0x20000000` (stack grows down into RAM below it);
the app never sets SP itself.

### Boot sequence (observed in emulation)

1. Mask ROM / bootloader jumps into the app at `__main` (`0x100041E4`).
2. `__scatterload` walks the table at `0x1001A9E4` (bounds are PC-relative words at
   `0x10004218`): copy `0xD70` bytes → `0x2000C000` (ROM routine `0x114C8`),
   decompress `0x310`→`0x598` bytes → `0x2000CD70` (flash routine `0x10004220`),
   zero `0xC1C` bytes at `0x2000D308` (ROM routine `0x114D8`).
3. Final `bl 0x1000428E` (`__rt_entry`, at `0x100041FE`) enters the application.
   **modkit hooks this BL** to run mod `init` functions first.

## Module map (ARM)

ARMCC lays out code object file by object file, so named functions cluster:

| Range | Subsystem | Anchors |
|---|---|---|
| `10004000–100042A6` | vectors, app header, C runtime | `__main`, `__rt_entry` |
| `100042A6–1000D000` | Bluetooth host glue: HCI, ACL, L2CAP, GATT client | `hci_send`, `hci_recv`, `GATTC_ReadValue` |
| `1000D000–1000E300` | SMP / pairing | `master_key_distrib` |
| `1000E300–1000F100` | system + BT discovery (inquiry, name request, role switch, BLE scan) | `app_system_reset`, `inquiry_complete` |
| `1000F100–10011000` | controller manager: `IM_*` connection state machine, settings, turbo, rumble | `cntlr_conn_ind`, `cntlr_settings_process`, `cntlr_save_config` |
| `10011000–10013000` | USB device + HID class + **input pipeline** | `cntlr_submit_input`, `usb_send_input_report`, `hid_init` |
| `10013000–10014600` | P-256 big-number math for Secure Simple Pairing | `bn_add`, `bn_sub`, `bn_cmp` |
| `10014600–10016000` | MSP link (UART to the USB-host co-processor) | `msp_uart_rx_poll`, `msp_uart_send_frame` |
| `10016000–10017000` | PlayStation driver, PS4/PS5 encoders, stick/hat helpers | `ps_in_report`, `out_encode_ps5` |
| `10017000–10018400` | RF calibration, timers, bond storage | `timer_start`, `smp_bondcount` |
| `10018400–10018DD8` | Bluetooth HID host callbacks | `sdk_hid_host_cbk`, `sdk_set_conn` |
| `10018DD8–1001A6FC` | Switch Pro / Switch 2 Pro drivers and encoders | `switchpro_in_report`, `out_encode_switch2` |
| `1001A6FC–1001B500` | USB enumeration / control requests, Xbox encoder | `usb_set_config`, `out_encode_xbox` |
| `1001B500–1001C200` | ARMCC runtime (fplib soft-float, string helpers) | `__fplib_dcmp` |
| `1001C200–1001DA14` | rodata: per-controller tables, strings, descriptors, `crc8_table` | |
| `2000C000–2000D308` | RAM-resident functions (USB endpoint DMA, vendor requests) | `ramfn_2000c034` |

## The input pipeline (observed)

```
 controller driver (BT or MSP)               settings engine           USB output
 ─────────────────────────────               ───────────────           ──────────
 switchpro_in_report ─┐
 ps_in_report ────────┤  cntlr_state_t      cntlr_submit_input()
 switch2_in_process ──┼──(0x54 bytes)──────► rate-limit, timestamp
 xbox / MSP paths ────┘                      │
                                 [input_filter mods] ◄── modkit hook @ 0x10012976
                                             │
                                  cntlr_settings_process()  hotkeys, turbo, sensitivity
                                             │
                          switch (g_output_mode)
                           1 out_encode_switchpro   4 out_encode_ps4
                           2/3 out_encode_xbox      5 out_encode_ps5
                                                    6 out_encode_switch2
                                             │
                                 [report_filter mods] ◄── modkit hook @ 0x10012A14
                                             │
                                  usb_send_input_report()
```

`cntlr_state_t` layout: see `reference/types_arm.h` / `mods/include/ns36.h`.
Buttons use the Nintendo layout (bit 0 = Y … bit 23 = ZL); sticks are signed 16-bit,
already calibrated and dead-zoned; triggers are `0..0x7FFF`.

## MSP link (observed in ARM code)

UART frames, both directions: `sync`, `cmd`, `u16 len`, `payload[len]`, `checksum`
(`msp_frame_checksum`). ARM→MSP frames start with `0x51`, MSP→ARM with `0xA3`;
payloads are capped at `0x408` bytes. RX errors are logged as `MSP_EC_CHECKSUM_ERROR`,
`MSP_EC_LENGTH_ERROR`, `MSP_ST_GET_OUTSYNC`.

## MSP co-processor

- Startup (`_start` @ `0x0`) copies flash `0x4–0x75C` to RAM `0x1FFFC000` (RAM-resident
  code), `.data` from `0x3920`, zeroes `.bss` to `0x1FFFD1B4`, sets `gp = 0x1FFFCFC0`,
  programs QingKe CSRs `0xBC0`/`0x804`, then `mret`s into `main` (`0x870`).
- Peripherals used: USB host controller (`0x40008000`), UART1 (`0x40003400`), system
  control (`0x40001000`), PFIC (`0xE000E000`). Register names are applied in the
  decompiled output.
- Logic follows WCH's USB-host examples (`EnumAllRootDev`, `InitRootDev`,
  `AnalyzeHidIntEndp`, `CtrlSetUsbConfig`).
