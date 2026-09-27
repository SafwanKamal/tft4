#!/bin/sh
# Assemble TFT4_Bench with llvm-mc for the emulator test (needs TFT4_Driver's
# tools/test for ti2gnu.py, fr6989_equ.inc and the linker script).
# usage: sh build.sh <TFT4_Driver dir> <out dir>
set -e
HERE=$(cd "$(dirname "$0")/../.." && pwd)
DRV=$1/tools/test; OUT=$2; mkdir -p "$OUT"
[ -d "$DRV" ] || DRV=$1/test
cp "$DRV/fr6989_equ.inc" "$OUT/"
for f in bench bench_data tft4 font6x8; do
  python3 "$DRV/ti2gnu.py" "$HERE/$f.asm" "$OUT/$f.s" fr6989_equ.inc
  (cd "$OUT" && llvm-mc-18 -triple=msp430 -filetype=obj $f.s -o $f.o)
done
(cd "$OUT" && ld.lld-18 -T "$DRV/link_demo.lds.txt" bench.o bench_data.o tft4.o font6x8.o -o bench.elf 2>&1 | grep -v "entry symbol" || true)
echo "built $OUT/bench.elf"
