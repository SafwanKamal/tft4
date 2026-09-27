#!/bin/sh
# Assemble the driver and the demo (TI syntax) with llvm-mc for the emulator
# tests: tft4.elf = driver + demo sprites (for test_tft4.py), demo.elf = the
# whole demo program (for test_demo.py).
# usage: sh tools/test/build.sh <repo root> <out dir>
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$1; OUT=$2; mkdir -p "$OUT"
cp "$HERE/fr6989_equ.inc" "$OUT/"
asm() {   # asm <source.asm> <name>
  python3 "$HERE/ti2gnu.py" "$1" "$OUT/$2.s" fr6989_equ.inc
  (cd "$OUT" && llvm-mc-18 -triple=msp430 -filetype=obj $2.s -o $2.o)
}
asm "$ROOT/driver/tft4.asm" tft4
asm "$ROOT/driver/font6x8.asm" font6x8
asm "$ROOT/demo/sprites.asm" sprites
asm "$ROOT/demo/main.asm" main
(cd "$OUT" && ld.lld-18 -T "$HERE/link_tft4.lds.txt" tft4.o sprites.o font6x8.o -o tft4.elf 2>&1 | grep -v "entry symbol" || true)
(cd "$OUT" && ld.lld-18 -T "$HERE/link_demo.lds.txt" main.o tft4.o sprites.o font6x8.o -o demo.elf 2>&1 | grep -v "entry symbol" || true)
echo "built $OUT/tft4.elf $OUT/demo.elf"
