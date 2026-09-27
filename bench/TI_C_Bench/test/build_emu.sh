#!/bin/sh
# Build TI_C_Bench with clang for the MSP430 emulator test (the board build is
# CCS with TI's compiler). Uses this project's GrLib, driverlib and LcdDriver.
# usage: sh test/build_emu.sh <msp430 include dir (TI's include_gcc)>
set -e
INC=$1
HERE=$(cd "$(dirname "$0")/.." && pwd); ROOT=$HERE/../..; OUT=$HERE/test/obj
STUB=$ROOT/tools/test/libcstub
mkdir -p $OUT
CFL="--target=msp430 -Os -ffreestanding -ffunction-sections -fdata-sections -I$STUB -include $STUB/ti_shim.h -I$INC -I$HERE/driverlib/MSP430FR5xx_6xx -I$HERE/GrLib/grlib -I$HERE/LcdDriver -I$HERE -D__MSP430FR6989__ -Wno-macro-redefined -Wno-unknown-pragmas"
for f in $HERE/GrLib/grlib/context.c $HERE/GrLib/grlib/display.c $HERE/GrLib/grlib/image.c $HERE/GrLib/grlib/line.c \
         $HERE/GrLib/grlib/rectangle.c $HERE/GrLib/grlib/string.c $HERE/GrLib/fonts/fontfixed6x8.c \
         $HERE/LcdDriver/Crystalfontz128x128_ST7735.c $HERE/LcdDriver/HAL_MSP_EXP430FR6989_Crystalfontz128x128_ST7735.c \
         $HERE/driverlib/MSP430FR5xx_6xx/gpio.c $HERE/driverlib/MSP430FR5xx_6xx/eusci_b_spi.c $ROOT/bench/suite/rt.c \
         $HERE/bench_c.c; do
  clang $CFL -c $f -o $OUT/$(basename ${f%.c}).o
done
clang $CFL -x c -c $HERE/test/emu_stubs.c.txt -o $OUT/emu_stubs.o
ld.lld-18 -T $ROOT/bench/suite/link_c.lds -L $ROOT/tools/test $OUT/*.o -o $HERE/test/bench_c.elf
echo "built test/bench_c.elf"
