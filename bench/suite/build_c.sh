#!/bin/sh
# Build bench_api.elf (TI's C driver + the entry points suite.py calls) with
# clang, from TI_C_Bench's GrLib / driverlib / LcdDriver.
# usage: sh bench/suite/build_c.sh <msp430 include dir (TI's include_gcc)>
set -e
INC=$1
HERE=$(cd "$(dirname "$0")" && pwd); ROOT=$HERE/../..; C=$ROOT/bench/TI_C_Bench; OUT=$HERE/obj
STUB=$ROOT/tools/test/libcstub
mkdir -p $OUT
CFL="--target=msp430 -Os -ffreestanding -ffunction-sections -fdata-sections -I$STUB -include $STUB/ti_shim.h -I$INC -I$C/driverlib/MSP430FR5xx_6xx -I$C/GrLib/grlib -I$C/LcdDriver -I$C -D__MSP430FR6989__ -Wno-macro-redefined -Wno-unknown-pragmas"
for f in $C/GrLib/grlib/context.c $C/GrLib/grlib/display.c $C/GrLib/grlib/image.c $C/GrLib/grlib/line.c \
         $C/GrLib/grlib/rectangle.c $C/GrLib/grlib/string.c $C/GrLib/fonts/fontfixed6x8.c \
         $C/LcdDriver/Crystalfontz128x128_ST7735.c $C/LcdDriver/HAL_MSP_EXP430FR6989_Crystalfontz128x128_ST7735.c \
         $C/driverlib/MSP430FR5xx_6xx/gpio.c $C/driverlib/MSP430FR5xx_6xx/eusci_b_spi.c $HERE/rt.c $HERE/bench_api.c; do
  clang $CFL -c $f -o $OUT/$(basename ${f%.c}).o
done
ld.lld-18 -T $HERE/link_c.lds -L $ROOT/tools/test $OUT/*.o -o $HERE/bench_api.elf
echo "built bench/suite/bench_api.elf"
