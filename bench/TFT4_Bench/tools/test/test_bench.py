#!/usr/bin/env python3
"""
test_bench.py - run TFT4_Bench from RESET in the emulator, press S1 for the
scenes given (or S2 for all), check the results and save the screens as PNGs.

  python3 test_bench.py <bench.elf> <TFT4_Driver/tools/test> <out dir> [s1 N | all]
"""
import os, sys
sys.path.insert(0, sys.argv[2])
from msp430emu import CPU
from PIL import Image

elf, outdir = sys.argv[1], sys.argv[3]
mode = sys.argv[4:] or ['s1', '3']
os.makedirs(outdir, exist_ok=True)
cpu = CPU(elf)
MHZ = 16000.0   # cycles per ms (CLOCK_MHZ 16)


def rgb(c):
    return ((c >> 11) << 3, ((c >> 5) & 63) << 2, (c & 31) << 3)


def save(name):
    g = cpu.lcd.gram
    img = Image.new('RGB', (128, 128))
    img.putdata([rgb(g[y + 3][x + 2]) for y in range(128) for x in range(128)])
    img.resize((384, 384), Image.NEAREST).save(os.path.join(outdir, name))


def seg():
    digit = cpu.sym('DIGIT')
    pats = {cpu.rw(digit + 2 * i): '0123456789 -'[i] for i in range(12)}
    tab = cpu.sym('SegTable')
    s = ''
    for pos in range(5, -1, -1):
        lo, hi = cpu.rw(tab + 4 * pos), cpu.rw(tab + 4 * pos + 2)
        p = cpu.mem[lo] | (cpu.mem[hi] << 8)
        s += pats.get(p & ~1, '?')
        if p & 1 and pos == 1:
            s += '.'
    return s


def run_until_idle(limit=2_000_000_000):
    lo, hi = cpu.sym('Mainloop'), cpu.sym('DoNext')
    start = cpu.cycles
    for _ in range(100):                         # leave the idle loop first
        if not (lo <= cpu.r[0] < hi):
            break
        cpu.step()
    while not (lo <= cpu.r[0] < hi):
        cpu.step()
        if cpu.cycles - start > limit:
            raise RuntimeError('no idle')
    for _ in range(20):                          # a few loop turns
        cpu.step()


errs = lambda: cpu.lcd.errors + cpu.spi_log_errors


def glass_check(what):
    """after a screen is shown, the glass must match Back through the palette"""
    for _ in range(3000):                        # let the last DMA chunk out
        cpu.step()
    b = cpu.sym('FbBack')
    pal = [cpu.rw(cpu.sym('Palette') + 2 * i) for i in range(16)]
    g = cpu.lcd.gram
    bad = sum(1 for y in range(128) for x in range(128)
              if g[y + 3][x + 2] != pal[(cpu.mem[b + y * 64 + x // 2] >> (4 if x % 2 == 0 else 0)) & 15])
    assert bad == 0, f"{what}: {bad} pixels on the glass differ from Back"
cpu.r[0] = cpu.sym('RESET')
# no frame pacing in the emulator (the wait is not timed anyway)
fp = cpu.sym('FramePeriod'); cpu.mem[fp] = 50; cpu.mem[fp + 1] = 0
run_until_idle()
glass_check('start screen')
save('start.png')
names = []
count = cpu.rw(cpu.sym('SceneCount'))
tab = cpu.sym('SceneTable')
for i in range(count):
    a = cpu.rw(tab + 18 * i + 2)
    n = bytes(cpu.mem[a:a + 13]).split(b'\0')[0].decode()
    names.append(n)


def result(i):
    avg = cpu.rw(cpu.sym('AvgHund') + 2 * i) / 100
    worst = cpu.rw(cpu.sym('WorstHund') + 2 * i) / 100
    return avg, worst


if mode[0] == 'scene':                           # start at scene N (1-based)
    cpu.ww(cpu.sym('SceneNo'), int(mode[1]) - 1)
    mode = ['s1', '1']
if mode[0] == 's1':
    for k in range(int(mode[1])):
        i = cpu.rw(cpu.sym('SceneNo'))
        c0 = cpu.cycles
        cpu.ww(cpu.sym('ButtonS1'), 1)
        run_until_idle()
        avg, worst = result(i)
        print(f"S1 -> scene {i + 1:2d} {names[i]:13s} avg {avg:7.2f} ms  worst {worst:7.2f} ms  "
              f"seg '{seg()}'  ({(cpu.cycles - c0) / MHZ / 1000:.1f} s simulated)", flush=True)
        glass_check(f'result screen {i + 1}')
        save(f'result_{i + 1:02d}.png')
else:
    cpu.ww(cpu.sym('ButtonS2'), 1)
    run_until_idle(limit=10 ** 10)
    for i in range(count):
        avg, worst = result(i)
        print(f"scene {i + 1:2d} {names[i]:13s} avg {avg:7.2f} ms  worst {worst:7.2f} ms")
    glass_check('summary')
    save('summary.png')
print('errors:', errs()[:5])
assert not errs()
