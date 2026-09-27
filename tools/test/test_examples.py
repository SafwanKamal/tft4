#!/usr/bin/env python3
"""
test_examples.py - build every program in examples/ with the driver (llvm-mc
for assembly, clang for C), run it in the emulator, check that the panel
matches the Back buffer and save what the panel shows as a PNG.

  python3 tools/test/test_examples.py <repo root> <msp430 include dir> <out dir> [name ...]

<msp430 include dir> has msp430.h / msp430fr6989.h (TI's include_gcc folder,
e.g. /Applications/ti/ccs2040/ccs/ccs_base/msp430/include_gcc).
"""
import glob, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from msp430emu import CPU
from PIL import Image

root, inc, out = (os.path.abspath(a) for a in sys.argv[1:4])
only = sys.argv[4:]
os.makedirs(out, exist_ok=True)
MHZ = 16e6


def sh(*cmd, cwd=out):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"{' '.join(cmd)}\n{r.stdout}{r.stderr}")


def asm(src, name):
    sh('python3', f'{HERE}/ti2gnu.py', src, f'{out}/{name}.s', 'fr6989_equ.inc')
    sh('llvm-mc-18', '-triple=msp430', '-filetype=obj', f'{name}.s', '-o', f'{name}.o')
    return f'{name}.o'


def cc(src, name):
    sh('clang', '--target=msp430', '-Os', '-ffreestanding', '-Wall', '-Wno-unknown-pragmas',
       '-D__MSP430FR6989__', f'-I{root}/driver', f'-I{inc}', f'-I{HERE}/libcstub',
       '-include', f'{HERE}/libcstub/ti_shim.h', '-x', 'c', '-c', src, '-o', f'{name}.o')
    return f'{name}.o'


def rgb(c):
    return ((c >> 11) << 3, ((c >> 5) & 63) << 2, (c & 31) << 3)


os.environ['TI2GNU_INCLUDE'] = f'{root}/driver'   # tft4_config.inc
sh('cp', f'{HERE}/fr6989_equ.inc', f'{HERE}/msp430fr6989_symbols.ld', out)
drv = [asm(f'{root}/driver/tft4.asm', 'tft4'), asm(f'{root}/driver/font6x8.asm', 'font6x8'),
       cc(f'{HERE}/emu_rt.c.txt', 'emu_rt')]
for src in sorted(glob.glob(f'{root}/examples/*.asm') + glob.glob(f'{root}/examples/*.c')):
    name = os.path.splitext(os.path.basename(src))[0] + ('_c' if src.endswith('.c') else '_asm')
    if only and not any(o in name for o in only):
        continue
    obj = cc(src, name) if src.endswith('.c') else asm(src, name)
    elf = f'{out}/{name}.elf'
    r = subprocess.run(['ld.lld-18', '-T', f'{HERE}/link_app.lds.txt', obj, *drv, '-o', elf],
                       cwd=out, capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stderr)
    cpu = CPU(elf)
    cpu.r[1] = 0x2400
    cpu.run('RESET' if src.endswith('.asm') else 'main', int(1.2 * MHZ))   # init + ~1 s
    for _ in range(40000):                  # let the last DMA chunk out
        cpu.step()
    b = cpu.sym('FbBack')
    pal = [cpu.rw(cpu.sym('Palette') + 2 * i) for i in range(16)]
    g = cpu.lcd.gram
    img = [g[y + 3][x + 2] for y in range(128) for x in range(128)]
    want = [pal[(cpu.mem[b + y * 64 + x // 2] >> (4 if x % 2 == 0 else 0)) & 15]
            for y in range(128) for x in range(128)]
    bad = sum(1 for a, w in zip(img, want) if a != w)
    im = Image.new('RGB', (128, 128))
    im.putdata([rgb(c) for c in img])
    im.resize((256, 256), Image.NEAREST).save(f'{out}/{name}.png')
    err = cpu.lcd.errors + cpu.spi_log_errors
    print(f"{name:16s} panel vs Back: {bad} pixels differ, errors: {len(err)}  -> {name}.png")
    assert not err, err[:3]
    # palette_fade resends the whole screen with a new palette every frame, so
    # the run always stops in the middle of one; the others hold still
    assert bad == 0 or 'palette' in name, name + ': panel differs from Back'
