#!/usr/bin/env bash
# Regenerate src/{arm,msp}/decompiled and reference/*_functions.csv with Ghidra headless.
# Requires GHIDRA_INSTALL_DIR (tested with Ghidra 12.1.4) and Python 3.
# Manual names: reference/names_arm.csv, reference/names_msp.csv
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="${1:-$ROOT/firmware/NS36_V3.4.bin}"
WORK="$ROOT/build/ghidra"; mkdir -p "$WORK"
PY="${PYTHON:-python3}"; "$PY" -c "" 2>/dev/null || PY=python
HEADLESS="$GHIDRA_INSTALL_DIR/support/analyzeHeadless"
[ -f "$HEADLESS" ] || HEADLESS="$HEADLESS.bat"
native() { if command -v cygpath >/dev/null; then cygpath -w "$1"; else echo "$1"; fi; }

rm -f "$WORK"/arm.c* "$WORK"/msp.c*   # a failed Ghidra script must not leave stale output
"$PY" "$ROOT/tools/ns36fw.py" unpack "$BIN" "$WORK/unpacked"

"$HEADLESS" "$(native "$WORK")" ns36 -import "$(native "$BIN")" -overwrite \
  -loader BinaryLoader -loader-baseAddr 0x10003000 -processor "ARM:LE:32:Cortex" \
  -scriptPath "$(native "$ROOT/tools/ghidra")" -preScript SetupMemoryArm.java \
  -postScript ExportAll.java "$(native "$WORK/arm.c")" "$(native "$ROOT/reference/names_arm.csv")" \
    "$(native "$ROOT/reference/types_arm.h")" "$(native "$ROOT/reference/prototypes_arm.csv")" \
    "$(native "$ROOT/reference/globals_arm.csv")" "$(native "$ROOT/reference/data_arm.csv")" \
    "$(native "$ROOT/reference/modules_arm.csv")"

"$HEADLESS" "$(native "$WORK")" msp -import "$(native "$WORK/unpacked/aux.bin")" -overwrite \
  -loader BinaryLoader -loader-baseAddr 0x0 -processor "RISCV:LE:32:default" \
  -scriptPath "$(native "$ROOT/tools/ghidra")" -preScript SetupMemoryMsp.java \
  -postScript ExportRiscv.java "$(native "$WORK/msp.c")" "$(native "$ROOT/reference/names_msp.csv")"

"$PY" "$ROOT/tools/split_decomp.py" "$WORK/arm.c" "$ROOT/src/arm/decompiled" "NS36 main MCU, ARM Cortex-M"
"$PY" "$ROOT/tools/split_decomp.py" "$WORK/msp.c" "$ROOT/src/msp/decompiled" "MSP USB-host co-processor, WCH RISC-V"
cp "$WORK/arm.c.functions.csv" "$ROOT/reference/arm_functions.csv"
cp "$WORK/msp.c.functions.csv" "$ROOT/reference/msp_functions.csv"
