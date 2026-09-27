#!/usr/bin/env python3
"""
test_demo.py - run the whole demo program (main.asm + tft4.asm + sprites.asm)
from RESET in the emulator: clocks, timers, LcdInit, the frame loop, the
segment LCD readout. Saves what the TFT shows as PNGs.
"""
import os, sys
from msp430emu import CPU

XOFF, YOFF = 2, 3
MHZ = float(os.environ.get("TFT4_MHZ", 16))   # CLOCK_MHZ in tft4.asm


def glass(cpu):
    g = cpu.lcd.gram
    return [[g[y + YOFF][x + XOFF] for x in range(128)] for y in range(128)]


def front_colors(cpu):
    base = cpu.sym('FbFront')
    pal = [cpu.rw(cpu.sym('Palette') + 2 * i) for i in range(16)]
    out = []
    for y in range(128):
        row = []
        for x in range(64):
            b = cpu.mem[base + y * 64 + x]
            row += [pal[b >> 4], pal[b & 15]]
        out.append(row)
    return out


def run_to_frame_boundary(cpu):
    lo = cpu.sym('WaitFrame')
    while not (lo <= cpu.r[0] < lo + 12):
        cpu.step()


def seg_text(cpu):
    """Decode the 6 segment-LCD positions back to characters via CHAR."""
    char = cpu.sym('CHAR')
    table = {}
    for i in list(range(26, 38)) + list(range(26)):     # prefer digits, space, d
        table.setdefault(cpu.rw(char + 2 * i), i)
    seg = cpu.sym('SegTable')
    s = ''
    for pos in range(5, -1, -1):
        lo_a, hi_a = cpu.rw(seg + 4 * pos), cpu.rw(seg + 4 * pos + 2)
        pat = cpu.mem[lo_a] | (cpu.mem[hi_a] << 8)
        i = table.get(pat)
        dp = pat & 1
        i = table.get(pat & ~1)
        s += '?' if i is None else ('ABCDEFGHIJKLMNOPQRSTUVWXYZ '[i] if i < 27 else ('d' if i == 37 else str(i - 27)))
        if dp: s += '.'
    return s


def save_png(img, path):
    from PIL import Image
    im = Image.new('RGB', (128, 128))
    for y in range(128):
        for x in range(128):
            c = img[y][x]
            im.putpixel((x, y), (((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31))
    im.resize((384, 384), Image.NEAREST).save(path)


def main():
    elf, outdir = sys.argv[1], sys.argv[2]
    cpu = CPU(elf)
    cpu.r[1] = 0x2400
    cpu.r[0] = cpu.sym('RESET')

    frames_cycles = int(0.040 * (MHZ * 1e6))
    cpu.run('RESET', int(0.46 * (MHZ * 1e6)) + 10 * frames_cycles)      # init + ~10 frames
    run_to_frame_boundary(cpu)
    assert not cpu.lcd.errors and not cpu.spi_log_errors, (cpu.lcd.errors, cpu.spi_log_errors)
    g = glass(cpu)
    assert g == front_colors(cpu), "glass != Front buffer"
    pal = [cpu.rw(cpu.sym('Palette') + 2 * i) for i in range(16)]
    sky = sum(row.count(pal[1]) for row in g[:112])
    ground = sum(row.count(pal[3]) + row.count(pal[11]) for row in g[112:])
    other = sum(1 for row in g[:112] for c in row if c not in (pal[1], pal[7]))
    print(f"delta mode: sky px={sky}, ground px={ground}/2048, sprite px={other}")
    assert ground == 2048 and sky > 10000 and other > 200
    t_delta = cpu.rw(cpu.sym('PresentTime')) * 2
    print(f"  PresentTime = {t_delta} us, segment LCD shows '{seg_text(cpu)}'")
    save_png(g, f"{outdir}/demo_delta.png")

    cpu.ww(cpu.sym('ButtonS1'), 1)                              # press S1
    cpu.run(cpu.r[0], 10 * frames_cycles + int(0.070 * (MHZ * 1e6)) * 10)
    run_to_frame_boundary(cpu)
    assert cpu.rw(cpu.sym('FullMode')) == 1
    assert glass(cpu) == front_colors(cpu)
    t_full = cpu.rw(cpu.sym('PresentTime')) * 2
    print(f"full mode: PresentTime = {t_full} us, segment LCD shows '{seg_text(cpu)}'")
    save_png(glass(cpu), f"{outdir}/demo_full.png")

    cpu.ww(cpu.sym('ButtonS2'), 1)                              # press S2: 4 sprites
    cpu.ww(cpu.sym('ButtonS1'), 1)                              # back to delta
    cpu.run(cpu.r[0], 12 * frames_cycles)
    run_to_frame_boundary(cpu)
    t4 = cpu.rw(cpu.sym('PresentTime')) * 2
    print(f"delta, 4 sprites: PresentTime = {t4} us, segment LCD shows '{seg_text(cpu)}'")
    assert glass(cpu) == front_colors(cpu)
    assert not cpu.lcd.errors and not cpu.spi_log_errors
    print(f"demo ok ({cpu.instrs:,} instructions, {cpu.cycles/(MHZ * 1e6):.2f} s of MCU time)")


if __name__ == '__main__':
    main()
