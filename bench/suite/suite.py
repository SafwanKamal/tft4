#!/usr/bin/env python3
"""
suite.py - comprehensive benchmark: the same scenes on tft4 (assembly) and on
TI's C driver (grlib + Crystalfontz128x128_ST7735 + FR6989 HAL), in the MSP430
emulator. Per scene and driver: average / worst frame time (drawing + sending),
SPI bytes per frame, and how many pixels on the glass end up wrong compared
with an ideal rendering (transparency, overlaps, background under sprites).

  python3 suite.py <tft4.elf> <bench_api.elf> [frames] [out.json]
"""
import json, os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools', 'test'))
from msp430emu import CPU

MHZ = float(os.environ.get("TFT4_MHZ", 8)) * 1000   # cycles per ms (the suite compares at 8 MHz)
W = H = 128
PAL = [0x000000, 0x1D2B53, 0x7E2553, 0x008751, 0xAB5236, 0x5F574F, 0xC2C3C7, 0xFFF1E8,
       0xFF004D, 0xFFA300, 0xFFEC27, 0x00E436, 0x29ADFF, 0x83769C, 0xFF77A8, 0xFFCCAA]
SKY, STAR, GROUND, GRASS = 1, 7, 3, 11
s16 = lambda v: v & 0xFFFF


def rgb565(c):
    return (((c >> 19) & 31) << 11) | (((c >> 10) & 63) << 5) | ((c >> 3) & 31)


# ---------------------------------------------------------------- art
def ball(n, c1, c2, c3):
    r = n / 2 - 0.5
    rows = []
    for y in range(n):
        row = []
        for x in range(n):
            d = ((x - r) ** 2 + (y - r) ** 2) ** 0.5
            row.append(0 if d > r + 0.3 else (c3 if d > r - max(1, n // 8) else (c2 if (x + y) % 4 == 0 else c1)))
        rows.append(row)
    return rows

DIGITS3x5 = ["111101101101111", "010110010010111", "111001111100111", "111001111001111", "101101111001001",
             "111100111001111", "111100111101111", "111001001001001", "111101111101111", "111101111001111"]

def digit(d):                       # 6x10, opaque (background = SKY)
    g = DIGITS3x5[d]
    return [[(7 if g[(y // 2) * 3 + (x // 2)] == '1' else SKY) for x in range(6)] for y in range(10)]

ART = {'b8': ball(8, 10, 9, 8), 'b16': ball(16, 12, 7, 1 + 12 % 15), 'b32': ball(32, 14, 15, 2),
       'b64': ball(64, 11, 10, 3)}
for d in range(10):
    ART[f'd{d}'] = digit(d)


def background_ops():
    ops = [(0, 0, 128, 128, SKY)]
    rnd = random.Random(7)
    for _ in range(24):
        ops.append((rnd.randrange(128), rnd.randrange(110), 1, 1, STAR))
    ops += [(0, 112, 128, 16, GROUND), (0, 112, 128, 2, GRASS)]
    return ops


# ---------------------------------------------------------------- ideal model
class Ideal:
    def __init__(self):
        self.bg = [[0] * W for _ in range(H)]
        self.pal = list(PAL)

    def fill(self, img, x, y, w, h, c):
        for yy in range(max(0, y), min(H, y + h)):
            for xx in range(max(0, x), min(W, x + w)):
                img[yy][xx] = c

    def compose(self, sprites, extra=()):
        img = [r[:] for r in self.bg]
        for (x, y, w, h, c) in extra:
            self.fill(img, x, y, w, h, c)
        for (name, x, y) in sprites:
            rows = ART[name]
            for r, row in enumerate(rows):
                for cc, v in enumerate(row):
                    if v and 0 <= x + cc < W and 0 <= y + r < H:
                        img[y + r][x + cc] = v
        return [[rgb565(self.pal[v]) for v in row] for row in img]


# ---------------------------------------------------------------- drivers
class Tft4:
    name = 'tft4 (asm)'

    def __init__(self, elf):
        self.cpu = CPU(elf); self.cpu.r[1] = 0x2400
        self.cpu.call('LcdInit')
        self.addr = {}
        a = 0xC000                                  # free FRAM in the test image
        for k, rows in ART.items():
            w, h = len(rows[0]), len(rows)
            data = [w, h]
            for row in rows:
                rr = row + [0] * (w % 2)
                data += [(rr[i] << 4) | rr[i + 1] for i in range(0, len(rr), 2)]
            self.cpu.mem[a:a + len(data)] = bytes(data)
            self.addr[k] = a
            a += len(data) + (len(data) & 1)
        assert a < 0xFF00
        self.prev_sprites, self.prev_extra = [], []

    def c(self, fn, *args):
        return self.cpu.call(fn, *args)[1]

    def setup(self, ops):
        for (x, y, w, h, c) in ops:
            self.c('FbFillRect', s16(x), s16(y), w | (h << 8), c)
        self.c('FbSaveBg')
        self.c('LcdPresentFull'); self.c('LcdWait')
        self.prev_sprites, self.prev_extra = [], []

    def frame(self, sprites, extra=(), mode='retained'):
        cyc = 0
        if mode == 'retained':
            for (n, x, y) in self.prev_sprites:
                rows = ART[n]
                cyc += self.c('FbRestore', s16(x), s16(y), len(rows[0]) | (len(rows) << 8))
            for (x, y, w, h, c) in self.prev_extra:
                cyc += self.c('FbRestore', s16(x), s16(y), w | (h << 8))
        for (x, y, w, h, c) in extra:
            if w == 1 and h == 1:
                cyc += self.c('FbPixel', s16(x), s16(y), c)
            else:
                cyc += self.c('FbFillRect', s16(x), s16(y), w | (h << 8), c)
        for (n, x, y) in sprites:
            cyc += self.c('FbBlit', self.addr[n], s16(x), s16(y))
        cyc += self.c('LcdPresent') + self.c('LcdWait')
        self.prev_sprites, self.prev_extra = list(sprites), list(extra)
        return cyc

    def palette_frame(self, idx, color):
        return self.c('PaletteSet', idx, rgb565(color)) + self.c('LcdPresentFull') + self.c('LcdWait')


class TiC:
    name = 'TI C driver'

    def __init__(self, elf):
        self.cpu = CPU(elf); self.cpu.r[1] = 0x2400
        self.cpu.call('c_init', check_abi=False)
        pal = self.cpu.sym('kPal')
        self.addr = {}
        a = 0x8000
        for k, rows in ART.items():
            w, h = len(rows[0]), len(rows)
            pix = []
            for row in rows:
                rr = row + [0] * (w % 2)
                pix += [(rr[i] << 4) | rr[i + 1] for i in range(0, len(rr), 2)]
            img = bytes([4, 0, w & 255, w >> 8, h & 255, h >> 8, 16, 0, pal & 255, pal >> 8,
                         (a + 12) & 255, (a + 12) >> 8])
            self.cpu.mem[a:a + 12] = img
            self.cpu.mem[a + 12:a + 12 + len(pix)] = bytes(pix)
            self.addr[k] = a
            a += 12 + len(pix) + (len(pix) & 1)
        assert a < 0xFF00
        self.prev_sprites, self.prev_extra, self.bg_ops = [], [], []

    def c(self, fn, *args):
        return self.cpu.call(fn, *args, check_abi=False)[1]

    def setup(self, ops):
        self.bg_ops = ops
        for (x, y, w, h, c) in ops:
            self.c('c_fill', s16(x), s16(y), w | (h << 8), c)
        self.prev_sprites, self.prev_extra = [], []

    def frame(self, sprites, extra=(), mode='retained'):
        cyc = 0
        if mode == 'retained':                  # usual C way: erase with the sky color
            for (n, x, y) in self.prev_sprites:
                rows = ART[n]
                cyc += self.c('c_fill', s16(x), s16(y), len(rows[0]) | (len(rows) << 8), SKY)
            for (x, y, w, h, c) in self.prev_extra:
                if w == 1 and h == 1:
                    cyc += self.c('c_pixel', s16(x), s16(y), SKY)
                else:
                    cyc += self.c('c_fill', s16(x), s16(y), w | (h << 8), SKY)
        for (x, y, w, h, c) in extra:
            if w == 1 and h == 1:
                cyc += self.c('c_pixel', s16(x), s16(y), c)
            else:
                cyc += self.c('c_fill', s16(x), s16(y), w | (h << 8), c)
        for (n, x, y) in sprites:
            cyc += self.c('c_image', self.addr[n], s16(x), s16(y))
        self.prev_sprites, self.prev_extra = list(sprites), list(extra)
        return cyc

    def palette_frame(self, idx, color, sprites=()):
        # no palette on the panel side: the program changes its color table and
        # redraws everything that uses the color (here: the whole background)
        a = self.cpu.sym('kPal') + 4 * idx
        self.cpu.mem[a:a + 4] = bytes([color & 255, (color >> 8) & 255, color >> 16, 0])
        cyc = 0
        for (x, y, w, h, c) in self.bg_ops:
            cyc += self.c('c_fill', s16(x), s16(y), w | (h << 8), c)
        for (n, x, y) in sprites:
            cyc += self.c('c_image', self.addr[n], s16(x), s16(y))
        return cyc


def glass(cpu):
    g = cpu.lcd.gram
    return [[g[y + 3][x + 2] for x in range(W)] for y in range(H)]


# ---------------------------------------------------------------- scenes
def xorshift16(x):
    x ^= (x << 7) & 0xFFFF
    x ^= x >> 9
    x ^= (x << 8) & 0xFFFF
    return x


class PixelGen:
    """64 random pixels per frame; the hardware bench uses the same generator."""
    def __init__(self):
        self.r = 0xACE1

    def next(self):
        self.r = xorshift16(self.r)
        return self.r

    def frame(self):
        out = []
        for _ in range(64):
            x = self.next() & 127
            y = self.next() & 127
            while y >= 110:
                y = self.next() & 127
            c = 8 + (self.next() & 7)
            out.append((x, y, 1, 1, c))
        return out


class Mover:
    def __init__(self, name, n, seed, box=(0, 0, 128, 110), speed=3):
        rnd = random.Random(seed)
        w, h = len(ART[name][0]), len(ART[name])
        self.name, self.w, self.h, self.box = name, w, h, box
        bx, by, bw, bh = box
        self.p = [[rnd.randint(bx, bx + bw - w), rnd.randint(by, by + bh - h),
                   rnd.choice([-1, 1]) * rnd.randint(1, speed), rnd.choice([-1, 1]) * rnd.randint(1, speed)]
                  for _ in range(n)]

    def step(self):
        bx, by, bw, bh = self.box
        for s in self.p:
            s[0] += s[2]; s[1] += s[3]
            if s[0] < bx or s[0] > bx + bw - self.w: s[2] = -s[2]; s[0] = max(bx, min(s[0], bx + bw - self.w))
            if s[1] < by or s[1] > by + bh - self.h: s[3] = -s[3]; s[1] = max(by, min(s[1], by + bh - self.h))
        return [(self.name, s[0], s[1]) for s in self.p]


def scenes():
    S = []
    S.append(('Idle (nothing changes)', 'movers', lambda: []))
    for n in (1, 4, 16, 32):
        S.append((f'{n} sprite{"s" if n > 1 else ""} 8x8', 'movers', lambda n=n: [Mover('b8', n, 10 + n)]))
    for sz in (16, 32, 64):
        S.append((f'1 sprite {sz}x{sz}', 'movers', lambda sz=sz: [Mover(f'b{sz}', 1, 20 + sz, speed=2)]))
    S.append(('8 overlapping 16x16 in 48x48', 'movers', lambda: [Mover('b16', 8, 5, box=(40, 30, 48, 48), speed=2)]))
    S.append(('HUD: 5-digit counter (6x10)', 'hud', None))
    S.append(('64 single pixels change', 'pixels', None))
    S.append(('Full-screen fill, new color', 'fill', None))
    S.append(('Scrolling stripes (all rows)', 'stripes', None))
    S.append(('Palette animation (sky color)', 'palette', None))
    return S


def run_scene(drv, ideal, kind, factory, frames):
    drv.setup(background_ops())
    times, spi = [], []
    last_sprites, last_extra = [], []
    movers = factory() if factory else []
    counter = 12345
    pixgen = PixelGen()
    for f in range(frames + 1):                        # frame 0 = warm-up, not timed
        d0 = drv.cpu.lcd.data + drv.cpu.lcd.cmds
        extra, sprites = [], []
        if kind == 'movers':
            for m in movers:
                sprites += m.step() if f else [(m.name, p[0], p[1]) for p in m.p]
            cyc = drv.frame(sprites)
        elif kind == 'hud':
            counter += 7
            s = f'{counter % 100000:05d}'
            sprites = [(f'd{int(ch)}', 90 + 7 * i, 2) for i, ch in enumerate(s)]
            cyc = drv.frame(sprites, mode='opaque')
            sprites = sprites
        elif kind == 'pixels':
            extra = pixgen.frame()
            cyc = drv.frame([], extra)
        elif kind == 'fill':
            extra = [(0, 0, 128, 128, 2 + f % 12)]
            cyc = drv.frame([], extra, mode='immediate')
        elif kind == 'stripes':
            off = f % 16                               # 1 px per frame, covers every column
            extra = [(i * 8 - 16 + off, 0, 8, 128, 9 if i % 2 else 12) for i in range(18)]
            cyc = drv.frame([], extra, mode='immediate')
        elif kind == 'palette':
            color = [0x1D2B53, 0x2B3B73, 0x3B4B93, 0x4B5BB3][f % 4]
            cyc = drv.palette_frame(SKY, color)
            ideal.pal[SKY] = color
        if f:
            times.append(cyc)
            spi.append(drv.cpu.lcd.data + drv.cpu.lcd.cmds - d0)
        last_sprites, last_extra = sprites, extra
    # ideal picture for the last frame
    ideal.bg = [[0] * W for _ in range(H)]
    for (x, y, w, h, c) in background_ops():
        ideal.fill(ideal.bg, x, y, w, h, c)
    want = ideal.compose(last_sprites, last_extra)
    ideal.pal = list(PAL)
    got = glass(drv.cpu)
    wrong = sum(1 for y in range(H) for x in range(W) if got[y][x] != want[y][x])
    err = drv.cpu.lcd.errors + drv.cpu.spi_log_errors
    return dict(avg=sum(times) / len(times) / MHZ, worst=max(times) / MHZ,
                spi=sum(spi) / len(spi), wrong=wrong, errors=len(err))


def main():
    tft4_elf, c_elf = sys.argv[1], sys.argv[2]
    frames = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    out = sys.argv[4] if len(sys.argv) > 4 else 'suite.json'
    only = sys.argv[5] if len(sys.argv) > 5 else None
    results = []
    # REUSE_C=old.json: take the C driver's numbers from an earlier run
    import os
    old = {r['scene']: r for r in json.load(open(os.environ['REUSE_C']))} if os.environ.get('REUSE_C') else {}
    for (title, kind, factory) in scenes():
        if only and only not in title:
            continue
        row = {'scene': title}
        for cls, elf in ((TiC, c_elf), (Tft4, tft4_elf)):
            if cls is TiC and title in old:
                row[cls.name] = old[title][cls.name]
                continue
            drv = cls(elf)
            ideal = Ideal()
            if kind == 'palette':
                drv.setup(background_ops())
            row[cls.name] = run_scene(drv, ideal, kind, factory, frames)
        results.append(row)
        a, b = row['TI C driver'], row['tft4 (asm)']
        print(f"{title:34s} C {a['avg']:7.2f} ms (worst {a['worst']:6.2f}, wrong px {a['wrong']:5d})"
              f" | tft4 {b['avg']:7.2f} ms (worst {b['worst']:6.2f}, wrong px {b['wrong']:5d})", flush=True)
    json.dump(results, open(out, 'w'), indent=1)


if __name__ == '__main__':
    main()
