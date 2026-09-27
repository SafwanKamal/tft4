# TFT4_Bench: the benchmark on the real board

This runs the same 14 scenes as the emulator suite (`bench/suite/suite.py`) on the MSP-EXP430FR6989 LaunchPad with the Educational BoosterPack MKII. It uses the tft4 driver.

`TI_C_Bench` is the same program built on TI's C driver, so the two can be compared on hardware.

## Using it

Flash the board, and the title screen appears.

| Button | Does |
|---|---|
| S1 (P1.1) | Runs the next scene, then shows its result on the TFT: average and worst frame time. The bottom of the screen names the scene S1 will run next. |
| S2 (P1.2) | Runs all 14 scenes, one after the other, then shows a table with every scene's average time. That takes about 40 s. |

While a scene runs, the segment LCD shows its number and `----`. When it finishes, it shows the number and the average in ms, e.g. `04 15.4`.

Each scene draws the background first: sky, 24 stars and ground. It then runs 1 warm-up frame and 64 timed frames. A frame is timed from before the drawing until the last byte is on the wire: drawing, then `LcdPresent`, then `LcdWait`.

Frames are paced to at most 25 per second so you can watch them. The pacing wait is not timed. Timer1 counts in 2 µs steps.

## Clock

It runs at **16 MHz** by default: CPU, SMCLK and SPI. `CLOCK_MHZ` is set in both `bench.asm` and `tft4.asm`; set both to 8 to repeat the 8 MHz results below. At 16 MHz the emulator predicts exactly half of every 8 MHz number. For example: 32 balls 14.5 ms, full fill 24.5 ms, palette 17.8 ms. The board shows how much the FRAM wait state costs.

If the picture is garbled at 16 MHz, the panel doesn't keep up with 16 MHz SPI. Set `SPI_DIV` to 2 in `tft4.asm`.

## Scenes

| # | Scene | Each frame |
|---|---|---|
| 1 | Idle | Nothing drawn, only `LcdPresent` |
| 2–5 | 1 / 4 / 16 / 32 balls 8x8 | Erase each ball (`FbRestore`), move it, draw it (`FbBlit`) |
| 6–8 | 1 ball 16x16 / 32x32 / 64x64 | Same, one bigger ball |
| 9 | 8 overlap 16 | 8 balls, 16x16, bouncing inside a 48x48 box, so they overlap |
| 10 | HUD counter | 5 opaque 6x10 digits, the counter goes up by 7 |
| 11 | 64 pixels | Erase the previous 64 pixels, then draw 64 new random ones (`FbPixel`) |
| 12 | Full fill | The whole screen in a new color |
| 13 | Stripes | 18 vertical stripes scrolling 1 px per frame, so every row changes |
| 14 | Palette | Change the sky color with `PaletteSet`, then `LcdPresentFull` |

The start positions, speeds, star places, random pixels (xorshift16) and colors all match `suite.py`. `tools/gen_bench_data.py` writes them into `bench_data.asm` from `suite.py`. So a scene here is the same frame sequence the emulator runs.

## Results (tft4, 8 MHz)

This is what `tools/test/test_bench.py` measures when it runs this program from RESET in the emulator. The board column is the first hardware run (2026-09-26). The board is 3–8% faster than the emulator in every scene, so the emulator is slightly pessimistic.

| # | Scene | emulator avg ms | emulator worst ms | **board avg ms** |
|---|---|---|---|---|
| 1 | Idle | 0.01 | 0.01 | 0.01 |
| 2 | 1 ball 8x8 | 1.12 | 1.24 | 1.03 |
| 3 | 4 balls 8x8 | 3.81 | 4.34 | 3.52 |
| 4 | 16 balls 8x8 | 15.39 | 16.59 | 14.30 |
| 5 | 32 balls 8x8 | 29.02 | 30.85 | 27.06 |
| 6 | 1 ball 16x16 | 2.17 | 2.20 | 2.00 |
| 7 | 1 ball 32x32 | 5.79 | 5.98 | 5.42 |
| 8 | 1 ball 64x64 | 20.69 | 23.45 | 19.64 |
| 9 | 8 overlap 16 | 10.63 | 12.44 | 10.04 |
| 10 | HUD counter | 1.65 | 2.10 | 1.56 |
| 11 | 64 pixels | 10.43 | 11.06 | 9.59 |
| 12 | Full fill | 49.04 | 49.04 | 46.20 |
| 13 | Stripes | 64.33 | 66.75 | 60.99 |
| 14 | Palette | 35.55 | 35.55 | 34.40 |

## Files

| File | What |
|---|---|
| `bench.asm` | The program: buttons, scenes, timing, result screens, segment LCD |
| `bench_data.asm` | **Generated**: scenes, start tables, background, ball and digit sprites |
| `tft4.asm`, `font6x8.asm`, `tft4.h` | Copies of `driver/`, kept in step by `tools/sync_driver.sh` (from the repo root) |
| `tft4_config.inc` | This project's driver settings (`CLOCK_MHZ`, `SPI_DIV`, ...); `bench.asm` includes it too |
| `tools/gen_bench_data.py` | `python3 tools/gen_bench_data.py ../suite bench_data.asm ../TI_C_Bench/bench_data.h` |
| `tools/test/build.sh`, `test_bench.py` | Emulator test: runs it from RESET, presses S1/S2, checks the glass, saves the screens |

```
sh tools/test/build.sh ../.. /tmp/bb
python3 tools/test/test_bench.py /tmp/bb/bench.elf ../../tools/test /tmp/out s1 3   # 3 scenes
python3 tools/test/test_bench.py /tmp/bb/bench.elf ../../tools/test /tmp/out all    # S2
```
