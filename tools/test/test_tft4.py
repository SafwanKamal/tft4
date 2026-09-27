#!/usr/bin/env python3
"""
test_tft4.py - run tft4.asm (assembled for the emulator) against a Python
reference model. Checks buffers after every drawing call, and the panel's
visible pixels after every present. Prints cycle counts at 8 MHz.
"""
import os, random, sys
from msp430emu import CPU

W = H = 128
XOFF, YOFF = 2, 3
SPRITE_AREA = 0xE000                 # unused FRAM in the test image
MHZ = float(os.environ.get("TFT4_MHZ", 16))   # CLOCK_MHZ in tft4.asm


class Ref:
    def __init__(self):
        self.back = [[0] * W for _ in range(H)]
        self.front = [[0] * W for _ in range(H)]

    def clear(self, c):
        self.back = [[c & 15] * W for _ in range(H)]

    def fill(self, x, y, w, h, c):
        for yy in range(max(0, y), min(H, y + h)):
            for xx in range(max(0, x), min(W, x + w)):
                self.back[yy][xx] = c & 15

    def blit(self, spr, x, y):
        w, h, rows = spr
        for r in range(h):
            for cc in range(w):
                v = rows[r][cc]
                if v and 0 <= x + cc < W and 0 <= y + r < H:
                    self.back[y + r][x + cc] = v

    def present(self):
        self.front = [r[:] for r in self.back]

    def save_bg(self):
        self.bg = [r[:] for r in self.back]

    def text(self, txt, x, y, fg, bg):
        for ch in txt:
            o = ord(ch) - 32
            if not 0 <= o < 95:
                o = ord('?') - 32
            if 0 <= x <= 122 and 0 <= y <= 120:
                for r in range(8):
                    bits = FONT[o][r]
                    for c in range(6):
                        if bits & (0x20 >> c):
                            self.back[y + r][x + c] = fg & 15
                        elif bg < 16:
                            self.back[y + r][x + c] = bg
            x += 6
        return x

    def restore(self, x, y, w, h):
        for yy in range(max(0, y), min(H, y + h)):
            for xx in range(max(0, x), min(W, x + w)):
                self.back[yy][xx] = self.bg[yy][xx]


HERE = os.path.dirname(os.path.abspath(__file__))
sys.path += [os.path.join(HERE, '..'), os.path.join(HERE, '..', 'tools')]   # tools/font6x8.py
from font6x8 import glyphs
FONT = glyphs()


def s16(v):
    return v & 0xFFFF


class Rig:
    def __init__(self, elf):
        self.cpu = CPU(elf)
        self.cpu.r[1] = 0x2400
        self.ref = Ref()
        self.sprite_ptr = SPRITE_AREA
        self.pal = None

    def call(self, name, *args):
        return self.cpu.call(name, *args)

    def fb(self, which):
        base = self.cpu.sym(which)
        m = self.cpu.mem
        out = []
        for y in range(H):
            row = []
            for x in range(W // 2):
                b = m[base + y * 64 + x]
                row += [b >> 4, b & 15]
            out.append(row)
        return out

    def palette(self):
        a = self.cpu.sym('Palette')
        return [self.cpu.rw(a + 2 * i) for i in range(16)]

    def glass(self):
        g = self.cpu.lcd.gram
        return [[g[y + YOFF][x + XOFF] for x in range(W)] for y in range(H)]

    def load_sprite(self, w, h, rows):
        a = self.sprite_ptr
        data = [w, h]
        for r in rows:
            rr = r + [0] * (w % 2)
            data += [(rr[i] << 4) | rr[i + 1] for i in range(0, len(rr), 2)]
        self.cpu.mem[a:a + len(data)] = bytes(data)
        self.sprite_ptr += len(data) + (len(data) & 1)
        return a

    def check_back(self, what):
        got = self.fb('FbBack')
        if got != self.ref.back:
            for y in range(H):
                if got[y] != self.ref.back[y]:
                    bad = [x for x in range(W) if got[y][x] != self.ref.back[y][x]]
                    raise AssertionError(f"{what}: Back differs at row {y}, x={bad[:8]} "
                                         f"got {[got[y][x] for x in bad[:8]]} want {[self.ref.back[y][x] for x in bad[:8]]}")

    def check_glass(self, what):
        pal = self.palette()
        g = self.glass()
        for y in range(H):
            for x in range(W):
                if g[y][x] != pal[self.ref.front[y][x]]:
                    raise AssertionError(f"{what}: glass differs at ({x},{y}): "
                                         f"{g[y][x]:04X} vs {pal[self.ref.front[y][x]]:04X}")
        if self.cpu.lcd.errors or self.cpu.spi_log_errors:
            raise AssertionError(f"{what}: panel/SPI errors {self.cpu.lcd.errors[:3]} {self.cpu.spi_log_errors[:3]}")

    def present(self, full=False):
        d0 = self.cpu.lcd.data
        c0 = self.cpu.lcd.cmds
        ret, cyc = self.call('LcdPresentFull' if full else 'LcdPresent')
        _, cyc_wait = self.call('LcdWait')              # let the DMA finish
        cyc += cyc_wait
        self.ref.present()
        self.check_glass('present')
        if self.fb('FbFront') != self.ref.front:
            raise AssertionError("Front buffer != reference after present")
        return ret, cyc, self.cpu.lcd.data - d0, self.cpu.lcd.cmds - c0


def main():
    elf = sys.argv[1]
    rnd = random.Random(1234)
    rig = Rig(elf)
    cpu = rig.cpu

    # ---- init
    _, cyc = rig.call('LcdInit')
    lcd = cpu.lcd
    assert lcd.colmod == 0x05 and lcd.madctl == 0xC8, (lcd.colmod, lcd.madctl)
    assert lcd.display_on and not lcd.sleeping
    assert cpu.brw == 1, cpu.brw
    rig.check_glass('init')
    print(f"LcdInit ok: {cyc/MHZ/1000:.1f} ms (incl. 250 ms of reset/sleep-out delays)")

    # ---- FbClear
    for c in (0, 5, 15, 7):
        rig.call('FbClear', c); rig.ref.clear(c); rig.check_back(f'FbClear({c})')
    _, cyc = rig.call('FbClear', 3); rig.ref.clear(3)
    print(f"FbClear ok: {cyc} cycles = {cyc/MHZ/1000:.2f} ms")

    # ---- FbFillRect: random + edge cases
    cases = [(0, 0, 128, 128, 1), (-5, -5, 10, 10, 2), (120, 120, 20, 20, 4), (1, 1, 1, 1, 9),
             (3, 7, 2, 1, 10), (5, 0, 0, 5, 11), (127, 127, 1, 1, 12), (-200, 3, 255, 4, 13),
             (130, 5, 4, 4, 14), (10, -10, 4, 5, 15), (0, 64, 128, 1, 6)]
    for _ in range(300):
        cases.append((rnd.randint(-20, 140), rnd.randint(-20, 140), rnd.randint(0, 60), rnd.randint(0, 60), rnd.randint(0, 15)))
    for (x, y, w, h, c) in cases:
        rig.call('FbFillRect', s16(x), s16(y), w | (h << 8), c)
        rig.ref.fill(x, y, w, h, c)
        rig.check_back(f'FbFillRect{(x, y, w, h, c)}')
    _, cyc = rig.call('FbFillRect', 10, 10, 64 | (32 << 8), 8); rig.ref.fill(10, 10, 64, 32, 8)
    print(f"FbFillRect ok ({len(cases)} cases): 64x32 = {cyc} cycles")

    # ---- FbPixel: random + clipping
    pcases = [(0, 0, 5), (127, 127, 6), (-1, 5, 7), (5, -1, 7), (128, 5, 8), (5, 128, 8), (1, 0, 9)]
    pcases += [(rnd.randint(-5, 132), rnd.randint(-5, 132), rnd.randint(0, 15)) for _ in range(300)]
    for (x, y, c) in pcases:
        rig.call('FbPixel', s16(x), s16(y), c); rig.ref.fill(x, y, 1, 1, c)
    rig.check_back('FbPixel')
    _, cyc = rig.call('FbPixel', 33, 44, 5); rig.ref.fill(33, 44, 1, 1, 5)
    _, cyc_r = rig.call('FbFillRect', 34, 44, 1 | (1 << 8), 5); rig.ref.fill(34, 44, 1, 1, 5)
    print(f"FbPixel ok ({len(pcases)} cases): {cyc} cycles (1x1 FbFillRect: {cyc_r})")

    # ---- FbText: all characters, both parities, opaque and transparent, clipping
    str_addr = 0xDF00
    def text(t, x, y, fg, bg):
        data = t.encode('latin-1') + b'\0'
        rig.cpu.mem[str_addr:str_addr + len(data)] = data
        ret, cyc = rig.call('FbText', str_addr, s16(x), s16(y), fg | (bg << 8))
        want = rig.ref.text(t, x, y, fg, bg)
        assert ret == want & 0xFFFF, f"FbText returned x={ret}, want {want}"
        rig.check_back(f'FbText({t!r}, {x}, {y}, {fg}, {bg})')
        return cyc
    allch = ''.join(chr(c) for c in range(32, 127))
    for i in range(0, 95, 20):
        text(allch[i:i + 20], 1 + (i % 2), 10 + i // 20 * 9, 7, 1)       # odd and even x
    text('\x01\x7f\xff', 3, 60, 8, 0)                                 # not in the font -> '?'
    for _ in range(80):
        t = ''.join(rnd.choice(allch) for _ in range(rnd.randint(1, 8)))
        text(t, rnd.randint(-15, 130), rnd.randint(-10, 130), rnd.randint(0, 15), rnd.choice([rnd.randint(0, 15), 16, 255]))
    cyc = text('SCORE 01234', 10, 100, 10, 1)
    cyc_t = text('SCORE 01234', 11, 110, 10, 255)
    print(f"FbText ok: 11 characters = {cyc/MHZ:.0f} us opaque, {cyc_t/MHZ:.0f} us transparent (odd x)")

    # ---- FbBlit: random sprites, all positions incl. clipping
    sprites = []
    for w, h in [(8, 6), (9, 6), (1, 1), (16, 16), (3, 5), (15, 2)] + [(rnd.randint(1, 16), rnd.randint(1, 16)) for _ in range(10)]:
        rows = [[rnd.choice([0, 0, rnd.randint(1, 15)]) for _ in range(w)] for _ in range(h)]
        sprites.append(((w, h, rows), rig.load_sprite(w, h, rows)))
    for i in range(400):
        spr, addr = rnd.choice(sprites)
        x, y = rnd.randint(-20, 135), rnd.randint(-20, 135)
        rig.call('FbBlit', addr, s16(x), s16(y))
        rig.ref.blit(spr, x, y)
        rig.check_back(f'FbBlit #{i} {spr[0]}x{spr[1]} at {x},{y}')
    spr8 = next(a for (s, a) in sprites if s[0] == 8 and s[1] == 6)
    _, cyc_even = rig.call('FbBlit', spr8, 20, 20)
    _, cyc_odd = rig.call('FbBlit', spr8, 21, 20)
    rig.ref.blit(next(s for (s, a) in sprites if a == spr8), 20, 20)
    rig.ref.blit(next(s for (s, a) in sprites if a == spr8), 21, 20)
    rig.check_back('FbBlit timing')
    print(f"FbBlit ok (400 random, clipped): 8x6 sprite = {cyc_even} cycles ({cyc_even/MHZ:.0f} us)")

    # ---- Present correctness over random scene sequences
    rig.present()
    for frame in range(40):
        kind = frame % 5
        rig.call('FbClear', 0); rig.ref.clear(0)
        if kind == 1:                       # full-screen change
            rig.call('FbClear', frame % 16); rig.ref.clear(frame % 16)
        for _ in range(rnd.randint(0, 12)):
            spr, addr = rnd.choice(sprites)
            x, y = rnd.randint(-10, 130), rnd.randint(-10, 130)
            rig.call('FbBlit', addr, s16(x), s16(y)); rig.ref.blit(spr, x, y)
        if kind == 2:
            for _ in range(5):
                x, y, w, h, c = rnd.randint(-5, 128), rnd.randint(-5, 128), rnd.randint(1, 40), rnd.randint(1, 40), rnd.randint(0, 15)
                rig.call('FbFillRect', s16(x), s16(y), w | (h << 8), c); rig.ref.fill(x, y, w, h, c)
        rig.check_back(f'scene {frame}')
        rig.present(full=(kind == 4))
    print("LcdPresent / LcdPresentFull ok: 40 random frames, glass == reference every frame")

    # ---- Retained mode: no clears, restore from Bg + blit + fill, random
    rig.call('FbClear', 1); rig.ref.clear(1)
    for _ in range(20):
        x, y, w, h, c = rnd.randint(-5, 128), rnd.randint(-5, 128), rnd.randint(1, 40), rnd.randint(1, 40), rnd.randint(0, 15)
        rig.call('FbFillRect', s16(x), s16(y), w | (h << 8), c); rig.ref.fill(x, y, w, h, c)
    rig.call('FbSaveBg'); rig.ref.save_bg()
    rig.present()
    live = []
    for frame in range(60):
        for (spr, addr, x, y) in live:                       # erase old places
            rig.call('FbRestore', s16(x), s16(y), spr[0] | (spr[1] << 8)); rig.ref.restore(x, y, spr[0], spr[1])
        if frame % 7 == 3:                                    # random restore of any area
            x, y, w, h = rnd.randint(-10, 130), rnd.randint(-10, 130), rnd.randint(0, 70), rnd.randint(0, 70)
            rig.call('FbRestore', s16(x), s16(y), w | (h << 8)); rig.ref.restore(x, y, w, h)
        live = [(s, a, rnd.randint(-12, 132), rnd.randint(-12, 132)) for (s, a) in rnd.sample(sprites, rnd.randint(0, 8))]
        for (spr, addr, x, y) in live:
            rig.call('FbBlit', addr, s16(x), s16(y)); rig.ref.blit(spr, x, y)
        if frame % 4 == 1:                                    # scattered pixels
            for _ in range(rnd.randint(1, 40)):
                x, y, c = rnd.randint(-2, 129), rnd.randint(-2, 129), rnd.randint(0, 15)
                rig.call('FbPixel', s16(x), s16(y), c); rig.ref.fill(x, y, 1, 1, c)
        if frame % 9 == 5:
            x, y, w, h, c = rnd.randint(-5, 128), rnd.randint(-5, 128), rnd.randint(1, 30), rnd.randint(1, 30), rnd.randint(0, 15)
            rig.call('FbFillRect', s16(x), s16(y), w | (h << 8), c); rig.ref.fill(x, y, w, h, c)
        rig.check_back(f'retained frame {frame}')
        rig.present(full=(frame % 13 == 12))
    ret, cyc = rig.call('LcdPresent')
    assert ret == 0, f"nothing changed, but {ret} windows were sent"
    print(f"Retained mode ok: 60 random frames (FbRestore/FbBlit/FbFillRect), nothing-changed present = {cyc/MHZ:.0f} us")

    # ---- Palette change
    rig.call('PaletteSet', 3, 0x1234)
    rig.ref.clear(3); rig.call('FbClear', 3)
    rig.present(full=True)
    print("PaletteSet ok")

    # ---- Benchmarks
    print("\nBenchmark at 8 MHz (MCLK = SMCLK, SPI 8 MHz), cycles from the emulator:")
    def scene(bg, sprite_pos, rects=()):
        rig.call('FbClear', bg); rig.ref.clear(bg)
        for (x, y, w, h, c) in rects:
            rig.call('FbFillRect', s16(x), s16(y), w | (h << 8), c); rig.ref.fill(x, y, w, h, c)
        for (spr, addr, x, y) in sprite_pos:
            rig.call('FbBlit', addr, s16(x), s16(y)); rig.ref.blit(spr, x, y)
    ground = [(0, 110, 128, 18, 3), (0, 0, 128, 10, 1)]
    spr, addr = next((s, a) for (s, a) in sprites if s[0] == 8 and s[1] == 6)
    pos = [(spr, addr, 10 + (i % 5) * 22, 20 + (i // 5) * 30) for i in range(10)]

    rows = []
    scene(0, pos, ground); rig.present(full=True)
    scene(0, pos, ground); r = rig.present(); rows.append(("nothing changed", r))
    moved = [(s, a, x + 1, y) for (s, a, x, y) in pos]
    scene(0, moved, ground); r = rig.present(); rows.append(("10 sprites move 1 px", r))
    moved2 = [(s, a, x + 3, y + 2) for (s, a, x, y) in moved]
    scene(0, moved2, ground); r = rig.present(); rows.append(("10 sprites move 3,2 px", r))
    scene(12, moved2, ground); r = rig.present(); rows.append(("background color change", r))
    scene(12, moved2, ground); r = rig.present(full=True); rows.append(("LcdPresentFull (any scene)", r))
    # retained: background once, then restore + blit per frame
    rig.call('FbClear', 0); rig.ref.clear(0)
    for (x, y, w, h, c) in ground:
        rig.call('FbFillRect', s16(x), s16(y), w | (h << 8), c); rig.ref.fill(x, y, w, h, c)
    rig.call('FbSaveBg'); rig.ref.save_bg(); rig.present(full=True)
    cur = pos
    for (s_, a_, x_, y_) in cur:
        rig.call('FbBlit', a_, s16(x_), s16(y_)); rig.ref.blit(s_, x_, y_)
    rig.present()
    def retained(newpos):
        tot = 0
        for (s_, a_, x_, y_) in cur:
            tot += rig.call('FbRestore', s16(x_), s16(y_), s_[0] | (s_[1] << 8))[1]; rig.ref.restore(x_, y_, s_[0], s_[1])
        for (s_, a_, x_, y_) in newpos:
            tot += rig.call('FbBlit', a_, s16(x_), s16(y_))[1]; rig.ref.blit(s_, x_, y_)
        wins, cyc, data, cmds = rig.present()
        return wins, cyc, data, cmds, tot
    r = retained(moved); cur = moved
    rows.append(("retained: 10 sprites 1 px (present)", r[:4])); draw1 = r[4]
    r = retained(moved2); cur = moved2
    rows.append(("retained: 10 sprites 3,2 px (present)", r[:4])); draw2 = r[4]
    r = retained(moved2)
    rows.append(("retained: nothing moved (present)", r[:4]))
    for name, (wins, cyc, data, cmds) in rows:
        print(f"  {name:28s} {cyc/MHZ/1000:6.2f} ms  windows={wins:3d}  SPI data={data:6d} B  cmds={cmds}")

    print(f"  retained drawing (restore + blit, 10 sprites): {draw1/MHZ/1000:.2f} / {draw2/MHZ/1000:.2f} ms")
    print(f"  (DMA transfers so far: {cpu.dma_transfers:,}; full refresh is now SPI-bound: 8 cycles per byte)")
    print(f"\nAll checks passed. Instructions executed: {cpu.instrs:,}")


if __name__ == '__main__':
    main()
