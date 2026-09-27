# tft4 demo

Twelve sprites bounce over a sky with stars and a ground strip. The demo draws in retained mode: the scenery is drawn once and saved with `FbSaveBg`. Each frame it erases every sprite (`FbRestoreSpr`), moves them, and draws them again.

| Button | Does |
|---|---|
| S1 | Switch between `LcdPresent` (delta, `d`) and `LcdPresentFull` (`F`) |
| S2 | Switch between 4 and 12 sprites |

The segment LCD shows the mode and how long the last present took, e.g. `d   3.8`.

This is a CCS project: **File → Import Projects** → this folder.

- The driver files here are copies of `../driver/`. Run `sh ../tools/sync_driver.sh` after changing the driver.
- `tft4_config.inc` holds this project's settings.
- The sprites are generated from `sprites.txt` with `python3 ../tools/sprite2asm.py sprites.txt -o sprites.asm`.
