#!/usr/bin/env python3
"""test_cbench.py - run TI_C_Bench's functions in the MSP430 emulator (clang
build): init, the scenes given, the result/summary screens; saves PNGs.

  python3 test/test_cbench.py <bench_c.elf> <TFT4_Driver/tools/test> <out dir> [scene numbers (1-based) | all]
"""
import os, sys
sys.path.insert(0, sys.argv[2])
from msp430emu import CPU
from PIL import Image

elf, outdir = sys.argv[1], sys.argv[3]
os.makedirs(outdir, exist_ok=True)
cpu = CPU(elf)
cpu.r[1] = 0x2400
TA0CCR0 = 0x0352


def rgb(c):
    return ((c >> 11) << 3, ((c >> 5) & 63) << 2, (c & 31) << 3)


def save(name):
    g = cpu.lcd.gram
    img = Image.new('RGB', (128, 128))
    img.putdata([rgb(g[y + 3][x + 2]) for y in range(128) for x in range(128)])
    img.resize((384, 384), Image.NEAREST).save(os.path.join(outdir, name))


def call(fn, *a):
    return cpu.call(fn, *a, check_abi=False, max_instr=10 ** 9)


call('benchInit')
cpu.ww(TA0CCR0, 50)                  # no frame pacing in the emulator
call('showStart'); save('start.png')
n = cpu.rw(cpu.sym('sceneNo'))
which = sys.argv[4:] or ['2']
scenes = range(14) if which == ['all'] else [int(w) - 1 for w in which]
for i in scenes:
    call('runScene', i)
    avg = cpu.rw(cpu.sym('avgHund') + 2 * i) / 100
    worst = cpu.rw(cpu.sym('worstHund') + 2 * i) / 100
    print(f"scene {i + 1:2d}  avg {avg:7.2f} ms  worst {worst:7.2f} ms", flush=True)
    if which != ['all']:
        call('showResult', i); save(f'result_{i + 1:02d}.png')
if which == ['all']:
    call('showSummary'); save('summary.png')
err = cpu.lcd.errors + cpu.spi_log_errors
print('errors:', err[:5])
