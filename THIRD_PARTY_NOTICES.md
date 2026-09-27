# Third-party notices

The tft4 driver, tools, examples, demo, benchmarks and tests are Safwan Kamal's work, under the MIT License (`LICENSE`).

The parts below come from Texas Instruments' MSP430Ware. They keep their own license: TI's BSD 3-clause license, whose full text is in `licenses/TI-BSD-3-Clause.txt`. Their files keep TI's copyright headers where TI supplied them.

| Part | Where | Origin | License |
|---|---|---|---|
| MSP Graphics Library (grlib) | `bench/TI_C_Bench/GrLib/` | MSP430Ware 3.80.14.01, `grlib` | BSD-3-Clause, © 2014 Texas Instruments |
| MSP430 Driver Library | `bench/TI_C_Bench/driverlib/` | MSP430Ware 3.80.14.01, `driverlib` 2.91.13.01 | BSD-3-Clause, © 2013 Texas Instruments |
| Crystalfontz128x128_ST7735 LCD driver | `bench/TI_C_Bench/LcdDriver/Crystalfontz128x128_ST7735.*` | TI's Educational BoosterPack MKII examples | BSD-3-Clause, © 2015 Texas Instruments |
| FR6989 HAL for that driver | `bench/TI_C_Bench/LcdDriver/HAL_MSP_EXP430FR6989_*` | Written for this project, modeled on TI's MSP432 HAL | Distributed under TI's BSD-3-Clause license, like the driver it serves |
| 6x8 font data | `driver/font6x8.asm` (and its copies in the projects) | Converted by `tools/font6x8.py` from grlib's `fontfixed6x8.c` | BSD-3-Clause, © 2014 Texas Instruments |

TI's C driver is included only so the benchmarks can compare against it; the tft4 driver itself doesn't use it. The font is the only TI-derived part that goes into a program built with tft4, so programs built with tft4 must include the BSD notice for the font.
