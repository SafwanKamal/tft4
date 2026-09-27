# TI_C_Bench: the benchmark on TI's C driver

This is the same program as `TFT4_Bench`, built on TI's C driver instead of tft4:

- MSP Graphics Library (grlib)
- `Crystalfontz128x128_ST7735`
- the FR6989 HAL from `FR6989_Invaders`

It runs the same 14 scenes, in the same order, with the same data, buttons and screens. Flash one, then the other, and compare the numbers on the board.

It was made from a copy of the `FR6989_Invaders` CCS project, with the same settings, GrLib, DriverLib and HAL. The game and `Canvas1bpp` were left out, and `main.c` is replaced by `bench_c.c`.

## Clock

`bench_clock.h` sets `BENCH_MHZ`, which is 16 by default, the same as TFT4_Bench. The HAL header (`LcdDriver/HAL_...h`) reads it too, so the SPI runs at the same speed as the CPU, and so do the driver's delays. Set it to 8 for the earlier 8 MHz results.

## Using it

| Button | Does |
|---|---|
| S1 (P1.1) | Runs the next scene, then shows its average and worst frame time |
| S2 (P1.2) | Runs all 14 scenes, then shows a table of averages |

The segment LCD shows the scene number and its average in ms. Each scene runs 1 warm-up frame and 64 timed frames. The timing covers only the drawing calls: this driver sends while it draws, so there is nothing left to wait for afterwards.

How the scenes are drawn is the usual way with this driver:

- **Moving sprites:** erase the old rectangle with the sky color, then `Graphics_drawImage` at the new place. There is no transparency, so balls get black corners and wipe out stars.
- **Palette:** the panel has no palette, so the scene changes the sky entry of the color table and redraws the background.
- **Idle:** nothing is drawn, so it takes 0 ms.

## Board results (2026-09-26, 8 MHz, 64 frames per scene)

Both programs ran on the same LaunchPad and BoosterPack. The C side was built with TI's compiler at -O3 (the Debug configuration inherited from FR6989_Invaders).

| # | Scene | TI C ms | tft4 ms | tft4 vs C |
|---|---|---|---|---|
| 1 | Idle | 0.01 | 0.01 | same |
| 2 | 1 ball 8x8 | 2.01 | 1.03 | 2.0x faster |
| 3 | 4 balls 8x8 | 8.03 | 3.52 | 2.3x faster |
| 4 | 16 balls 8x8 | 32.08 | 14.30 | 2.2x faster |
| 5 | 32 balls 8x8 | 64.15 | 27.06 | 2.4x faster |
| 6 | 1 ball 16x16 | 5.36 | 2.00 | 2.7x faster |
| 7 | 1 ball 32x32 | 17.58 | 5.42 | 3.2x faster |
| 8 | 1 ball 64x64 | 64.10 | 19.64 | 3.3x faster |
| 9 | 8 overlap 16 | 42.84 | 10.04 | 4.3x faster |
| 10 | HUD counter | 8.30 | 1.56 | 5.3x faster |
| 11 | 64 pixels | 11.28 | 9.59 | 1.2x faster |
| 12 | Full fill | 88.18 | 46.20 | 1.9x faster |
| 13 | Stripes | 89.98 | 60.99 | 1.5x faster |
| 14 | Palette | 103.58 | 34.40 | 3.0x faster |

- tft4 is faster in all 13 scenes that draw something, by 1.2x (64 pixels) to 5.3x (HUD). Idle is a tie; the 0.01 ms on both sides is the timer read.
- The 64-pixel scene, the one the emulator gave to C, goes to tft4 on the board (9.59 vs 11.28 ms).
- TI's compiler at -O3 is ~20% *slower* than the clang emulator build for image drawing (1 ball 8x8: 2.01 vs 1.67 ms) and about the same for fills. So the emulator comparison was, if anything, generous to C.

## Emulator prediction (clang build, 8 MHz)

The table comes from `test/test_cbench.py`. The clang build uses software multiply. TI's compiler uses the hardware multiplier and optimizes differently, so the board may well be faster than this. Measuring that is what this program is for.

| # | Scene | TI C avg ms | tft4 avg ms (TFT4_Bench) |
|---|---|---|---|
| 1 | Idle | 0.00 | 0.01 |
| 2 | 1 ball 8x8 | 1.67 | 1.12 |
| 3 | 4 balls 8x8 | 6.67 | 3.81 |
| 4 | 16 balls 8x8 | 26.66 | 15.39 |
| 5 | 32 balls 8x8 | 53.31 | 29.02 |
| 6 | 1 ball 16x16 | 4.76 | 2.17 |
| 7 | 1 ball 32x32 | 16.06 | 5.79 |
| 8 | 1 ball 64x64 | 59.09 | 20.69 |
| 9 | 8 overlap 16 | 38.06 | 10.63 |
| 10 | HUD counter | 6.57 | 1.65 |
| 11 | 64 pixels | 9.19 | 10.43 |
| 12 | Full fill | 90.22 | 49.04 |
| 13 | Stripes | 91.86 | 64.33 |
| 14 | Palette | 105.59 | 35.55 |

## Files

| File | What |
|---|---|
| `bench_c.c` | The program. It replaces the game's `main.c`. |
| `bench_data.h` | **Generated** by `../TFT4_Bench/tools/gen_bench_data.py`: scenes, images, background |
| `GrLib/`, `driverlib/`, `LcdDriver/` | Copied from `FR6989_Invaders` (TI's driver and the FR6989 HAL). The HAL header now takes its clock from `bench_clock.h`. |
| `bench_clock.h` | `BENCH_MHZ`: 16 or 8 |
| `test/` | Emulator build and test with clang. `emu_stubs.c.txt` isn't named `.c`, so CCS doesn't compile it. |

RAM is tight: grlib's image drawing keeps a 1 KB palette buffer in the 2 KB of RAM. So the scene state is a union, since only one scene runs at a time. That leaves about 500 B for the stack.

Emulator test:

```
sh test/build_emu.sh <TI's msp430 include_gcc folder>
python3 test/test_cbench.py test/bench_c.elf ../../tools/test /tmp/out 2 10   # scenes 2 and 10
python3 test/test_cbench.py test/bench_c.elf ../../tools/test /tmp/out all
```
