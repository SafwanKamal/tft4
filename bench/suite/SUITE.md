# tft4 vs TI's C driver: benchmark suite

The same 14 scenes run on both drivers in the MSP430 emulator (8 MHz, SPI at 8 MHz).

- Every scene draws on the demo background: sky, 24 stars and ground.
- Each number is the average of 64 frames after 1 warm-up frame, drawing and sending included.
- `wrong px` counts the pixels on the emulated glass, after the last frame, that differ from an ideal rendering (transparent sprites over the real background).

On the real board, `TFT4_Bench` (tft4) and `TI_C_Bench` (TI's C driver) run exactly these scenes. The data comes from the same generator, and S1/S2 step through the scenes.

How each driver draws the moving scenes:

- **TI C driver:** the usual way. Erase the old sprite rectangle with the sky color, then `Graphics_drawImage` at the new place.
- **tft4:** `FbRestore` the old rectangle, `FbBlit` the sprite, `LcdPresent`, `LcdWait`.

| Scene | TI C avg ms | TI C wrong px | tft4 v3 avg ms | tft4 v4 avg ms | tft4 v4 worst | tft4 wrong px | v4 vs C |
|---|---|---|---|---|---|---|---|
| Idle (nothing changes) | 0.00 | 0 | 0.20 | 0.01 | 0.01 | 0 | C: 0 ms (no work) |
| 1 sprite 8x8 | 1.66 | 22 | 1.23 | 1.11 | 1.22 | 0 | 1.5x faster |
| 4 sprites 8x8 | 6.64 | 89 | 4.11 | 3.79 | 4.31 | 0 | 1.8x faster |
| 16 sprites 8x8 | 26.57 | 330 | 17.43 | 15.31 | 16.50 | 0 | 1.7x faster |
| 32 sprites 8x8 | 53.15 | 600 | 33.18 | 28.85 | 30.68 | 0 | 1.8x faster |
| 1 sprite 16x16 | 4.75 | 69 | 2.88 | 2.16 | 2.19 | 0 | 2.2x faster |
| 1 sprite 32x32 | 16.05 | 242 | 8.88 | 5.78 | 5.97 | 0 | 2.8x faster |
| 1 sprite 64x64 | 59.08 | 928 | 32.55 | 20.68 | 23.44 | 0 | 2.9x faster |
| 8 overlapping 16x16 in 48x48 | 38.02 | 320 | 15.78 | 10.59 | 12.39 | 0 | 3.6x faster |
| HUD: 5-digit counter (6x10) | 6.56 | 0 | 2.41 | 1.62 | 2.07 | 0 | 4.0x faster |
| 64 single pixels change | 9.28 | 7 | 11.14 | 10.13 | 10.75 | 0 | 1.1x slower |
| Full-screen fill, new color | 90.22 | 0 | 59.10 | 49.04 | 49.04 | 0 | 1.8x faster |
| Scrolling stripes (all rows) | 91.80 | 0 | 68.67 | 64.30 | 66.71 | 0 | 1.4x faster |
| Palette animation (sky color) | 105.49 | 0 | 35.55 | 35.55 | 35.55 | 0 | 3.0x faster |

v3 numbers are from the earlier 10-frame run. The 64-pixel scene used a different random sequence then.

Memory (C side built with clang -Os; TI's compiler will differ):

| | TI C driver | tft4 v4 |
|---|---|---|
| Code + constants (FRAM) | ~13.6 KB (driver + grlib subset + DriverLib + 6x8 font) | ~3.9 KB (2.6 KB code, 0.6 KB tables, 0.76 KB font) |
| Frame buffers + PairTab (FRAM) | 0 | 25 KB (Back, Front, Bg + 1 KB) |
| RAM | ~1.1 KB (1 KB is grlib's image palette buffer) | 596 B (256 B line buffers, 256 B dirty ranges, 32 B text tables) |

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

## What the suite shows

- **tft4 v4 is faster in 12 of 14 scenes**, by 1.4x to 4.0x.
  - The biggest gaps: HUD (4.0x), overlapping sprites (3.6x), palette animation (3.0x) and big sprites (2.8–2.9x).
- **What v4 changed compared with v3:** faster drawing (word fills and copies, byte-wise blits) and an early return when nothing was drawn. So the time per frame dropped the most where drawing mattered:
  - 64x64 sprite: −37%
  - 32x32 sprite: −35%
  - HUD: −33%
  - Overlapping sprites: −33%
  - Full-screen fill: −17%
- **Where tft4 loses:**
  - *Idle:* 0.01 ms, against 0 for C.
  - *64 scattered single pixels:* 1.1x slower. Every pixel needs its own panel window (~75 µs each), and the C driver pays about the same per pixel.
- **Correctness:** tft4 is pixel-exact in all 14 scenes. The C driver ends up with wrong pixels in every scene with sprites. The causes are black corners (no transparency), stars erased under sprites, and overlapping sprites erasing each other.

## Files

- `suite.py`: the runner.
  - Command: `python3 suite.py <tft4.elf> bench_api.elf 64 suite.json [scene filter]`.
  - `tft4.elf` comes from `tools/test/build.sh`.
  - `REUSE_C=old.json` skips re-running the C side.
  - `TFT4_MHZ=16` reports the times at 16 MHz.
- `bench_api.c`: the C entry points (`c_init`, `c_fill`, `c_image`, `c_pixel`).
- `build_c.sh`: builds `bench_api.elf` with clang from TI_C_Bench's GrLib, driverlib and LcdDriver.
- `rt.c`: the runtime helpers clang needs.
- `link_c.lds`: the linker script for the C build.
- `chart.py`: makes `suite.png`.
- `suite.json`: raw results.
- `suite_v3.json`: the v3 run.
