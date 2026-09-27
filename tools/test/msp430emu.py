#!/usr/bin/env python3
"""
msp430emu.py - Small MSP430 (base ISA) emulator for testing tft4.asm.

- 16-bit MSP430 instruction set (no MSP430X extensions), all addressing modes,
  constant generators, flags, byte/word ops.
- Approximate cycle counting (classic MSP430 table) for benchmarks.
- eUSCI_B0 SPI model with TX buffer + shift register timing, feeding an
  ST7735 model that decodes commands (D/C on P2.3, CS on P2.5, RST on P9.4).
- ABI checks on call(): R4-R10 and SP must be preserved.
"""
from elftools.elf.elffile import ELFFile

# ---- peripheral addresses (MSP430FR6989) ---------------------------------
P2OUT, P9OUT = 0x0203, 0x0282
UCB0CTLW0, UCB0BRW, UCB0STATW, UCB0TXBUF, UCB0IFG = 0x0640, 0x0646, 0x0648, 0x064E, 0x066C
DC_BIT, CS_BIT, RST_BIT = 0x08, 0x20, 0x10
SENTINEL = 0xFFF0
DMACTL0, DMACTL4, DMA0CTL, DMA0SA, DMA0DA, DMA0SZ = 0x0500, 0x0508, 0x0510, 0x0512, 0x0516, 0x051A
TA0CTL, TA0CCTL0, TA0CCR0, TA1CTL, TA1R = 0x0340, 0x0342, 0x0352, 0x0380, 0x0390


class ST7735:
    """Decodes the byte stream the way the panel would."""
    def __init__(self):
        self.gram = [[0] * 132 for _ in range(162)]
        self.reset_seen = False
        self.sleeping = True
        self.display_on = False
        self.colmod = None
        self.madctl = None
        self.cmd = None
        self.params = []
        self.xs = self.xe = self.ys = self.ye = 0
        self.cx = self.cy = 0
        self.hi = None
        self.errors = []
        self.cmds = 0
        self.data = 0

    def hw_reset(self):
        self.reset_seen = True
        self.sleeping = True
        self.display_on = False
        self.cmd = None

    def err(self, m):
        if len(self.errors) < 20:
            self.errors.append(m)

    def byte(self, b, dc):
        if not self.reset_seen:
            self.err("byte before hardware reset")
        if dc == 0:                                     # command
            self.cmds += 1
            if self.cmd in (0x2A, 0x2B) and len(self.params) != 4:
                self.err(f"short CASET/RASET ({len(self.params)} params)")
            self.cmd, self.params, self.hi = b, [], None
            if b == 0x11: self.sleeping = False
            elif b == 0x29: self.display_on = True
            elif b == 0x2C: self.cx, self.cy = self.xs, self.ys
            return
        self.data += 1
        c = self.cmd
        if c in (0x2A, 0x2B):
            self.params.append(b)
            if len(self.params) == 4:
                a = (self.params[0] << 8) | self.params[1]
                e = (self.params[2] << 8) | self.params[3]
                if e < a: self.err(f"window end < start {a}>{e}")
                if c == 0x2A: self.xs, self.xe = a, e
                else:         self.ys, self.ye = a, e
        elif c == 0x2C:
            if self.colmod != 0x05: self.err("RAMWR without 16-bit COLMOD")
            if self.sleeping: self.err("RAMWR while sleeping")
            if self.hi is None:
                self.hi = b
            else:
                v = (self.hi << 8) | b
                self.hi = None
                if 0 <= self.cx < 132 and 0 <= self.cy < 162:
                    self.gram[self.cy][self.cx] = v
                else:
                    self.err(f"pixel outside GRAM {self.cx},{self.cy}")
                self.cx += 1
                if self.cx > self.xe:
                    self.cx = self.xs
                    self.cy += 1
                    if self.cy > self.ye: self.cy = self.ys
        elif c == 0x3A:
            self.colmod = b
        elif c == 0x36:
            self.madctl = b


class CPU:
    def __init__(self, elf_path):
        self.mem = bytearray(0x10000)
        self.r = [0] * 16
        self.cycles = 0
        self.instrs = 0
        self.lcd = ST7735()
        # SPI model
        self.spi_busy_until = 0
        self.spi_buf = None          # byte waiting in TXBUF
        self.spi_buf_time = 0
        self.spi_txifg = True
        self.dma_sa = 0
        self.dma_sz = 0
        self.dma_transfers = 0
        self.spi_log_errors = []
        self.brw = 1
        self.symbols = {}
        self.ta0_start = None
        self.ta0_seen = 0
        self.ta1_start = 0
        self._load(elf_path)

    # ---------------------------------------------------------------- loading
    def _load(self, path):
        with open(path, 'rb') as f:
            elf = ELFFile(f)
            for seg in elf.iter_segments():
                if seg['p_type'] == 'PT_LOAD':
                    data = seg.data()
                    a = seg['p_paddr']
                    self.mem[a:a + len(data)] = data
            st = elf.get_section_by_name('.symtab')
            for s in st.iter_symbols():
                if s.name:
                    self.symbols[s.name] = s['st_value']

    def sym(self, name):
        return self.symbols[name]

    # ---------------------------------------------------------------- SPI + DMA model
    # eUSCI_B0: TXBUF (one byte) -> shift register (8 * BRW cycles per byte).
    # TXIFG is set when TXBUF is empty. A 0->1 edge of TXIFG triggers DMA
    # channel 0 when it is enabled (DMA0TSEL = UCB0TXIFG0); each DMA transfer
    # moves one byte SA -> UCB0TXBUF and steals 2 CPU cycles.
    def _spi_update(self):
        while self.spi_buf is not None:
            t0 = max(self.spi_buf_time, self.spi_busy_until)
            if t0 > self.cycles:
                break
            b = self.spi_buf
            self.spi_buf = None
            self._spi_start(b, t0)
            self.spi_txifg = True                     # rising edge at t0
            self._dma_trigger(t0)

    def _spi_start(self, b, start):
        cs = self.mem[P2OUT] & CS_BIT
        dc = 1 if self.mem[P2OUT] & DC_BIT else 0
        self.spi_busy_until = start + 8 * self.brw
        if self.mem[UCB0CTLW0] & 1:
            self.spi_log_errors.append("TXBUF written while UCSWRST set")
        if cs:
            self.spi_log_errors.append("byte sent with CS high")
        else:
            self.lcd.byte(b, dc)

    def _txbuf_write(self, v, t):
        if self.spi_buf is not None:
            self.spi_log_errors.append("TXBUF overwritten (TXIFG not checked)")
        self.spi_buf, self.spi_buf_time = v & 0xFF, t
        self.spi_txifg = False

    def _dma_trigger(self, t):
        ctl = self.mem[DMA0CTL] | (self.mem[DMA0CTL + 1] << 8)
        tsel = self.mem[DMACTL0] & 0x1F
        if not (ctl & 0x10) or tsel != 19 or self.dma_sz <= 0:
            return
        b = self.mem[self.dma_sa & 0xFFFF]
        self.dma_sa += 1
        self.dma_sz -= 1
        self.dma_transfers += 1
        self.cycles += 2                               # CPU halted during transfer
        self._txbuf_write(b, t + 2)
        if self.dma_sz == 0:
            self.mem[DMA0CTL] = (self.mem[DMA0CTL] & ~0x10) | 0x08   # DMAEN off, DMAIFG
        # the byte may start right away if the shifter is idle
        # (handled by the caller's loop in _spi_update)

    def _p2_write_check(self, new):
        # D/C must not change while a byte is shifting
        self._spi_update()
        if (self.cycles < self.spi_busy_until or self.spi_buf is not None) and ((self.mem[P2OUT] ^ new) & DC_BIT):
            self.spi_log_errors.append(f"D/C changed mid-byte at cycle {self.cycles}")

    # ---------------------------------------------------------------- memory
    def _timer_div(self, ctl):
        return 1 << ((ctl >> 6) & 3)

    def rb(self, a):
        a &= 0xFFFF
        if a in (TA0CCTL0, TA0CCTL0 + 1) and self.ta0_start is not None:
            ctl = self.mem[TA0CTL] | (self.mem[TA0CTL + 1] << 8)
            period = ((self.mem[TA0CCR0] | (self.mem[TA0CCR0 + 1] << 8)) + 1) * self._timer_div(ctl)
            n = (self.cycles - self.ta0_start) // period
            if n > self.ta0_seen:
                self.ta0_seen = n
                self.mem[TA0CCTL0] |= 0x01          # CCIFG
        if a in (TA1R, TA1R + 1):
            ctl = self.mem[TA1CTL] | (self.mem[TA1CTL + 1] << 8)
            ex = (self.mem[0x03A0] & 7) + 1                 # TA1EX0: TAIDEX
            v = ((self.cycles - self.ta1_start) // (self._timer_div(ctl) * ex)) & 0xFFFF
            return (v & 0xFF) if a == TA1R else (v >> 8)
        if a in (UCB0IFG, UCB0STATW, DMA0CTL):
            self._spi_update()
            if a == UCB0IFG:
                return 0x02 if self.spi_txifg else 0x00
            if a == DMA0CTL:
                return self.mem[a]
            busy = self.spi_buf is not None or self.cycles < self.spi_busy_until
            return 0x01 if busy else 0x00
        return self.mem[a]

    def rw(self, a):
        a &= 0xFFFE
        return self.rb(a) | (self.rb(a + 1) << 8)

    def wb(self, a, v):
        a &= 0xFFFF
        v &= 0xFF
        if a == UCB0TXBUF:
            self._spi_update()
            self._txbuf_write(v, self.cycles)
            self._spi_update()
            return
        if a == UCB0IFG:
            self._spi_update()
            new = bool(v & 0x02)
            if new and not self.spi_txifg and self.spi_buf is None:
                self.spi_txifg = True
                self._dma_trigger(self.cycles)          # software-made rising edge
                self._spi_update()
            elif not new:
                self.spi_txifg = False
            self.mem[a] = v
            return
        if a == DMA0CTL:
            self._spi_update()
            old = self.mem[a]
            self.mem[a] = v
            if (v & 0x10) and not (old & 0x10):          # DMAEN 0 -> 1: latch SA/SZ
                self.dma_sa = self.mem[DMA0SA] | (self.mem[DMA0SA + 1] << 8)
                self.dma_sz = self.mem[DMA0SZ] | (self.mem[DMA0SZ + 1] << 8)
                da = self.mem[DMA0DA] | (self.mem[DMA0DA + 1] << 8)
                if da != UCB0TXBUF:
                    self.spi_log_errors.append(f"DMA0DA = {da:04X}, expected UCB0TXBUF")
            return
        if a == P2OUT:
            self._p2_write_check(v)
        if a == P9OUT:
            old = self.mem[P9OUT]
            if (old & RST_BIT) == 0 and (v & RST_BIT):
                self.lcd.hw_reset()
        if a == TA0CTL:
            self.ta0_start, self.ta0_seen = self.cycles, 0
        if a == TA1CTL:
            self.ta1_start = self.cycles
        if a == UCB0BRW:
            self.brw = max(1, v | (self.mem[a + 1] << 8))
        self.mem[a] = v

    def ww(self, a, v):
        a &= 0xFFFE
        if a == UCB0TXBUF:
            self.wb(a, v)
            return
        self.wb(a, v & 0xFF)
        self.wb(a + 1, (v >> 8) & 0xFF)

    # ---------------------------------------------------------------- flags
    C, Z, N, V = 0x01, 0x02, 0x04, 0x100

    def setf(self, c=None, z=None, n=None, v=None):
        sr = self.r[2]
        for bit, val in ((self.C, c), (self.Z, z), (self.N, n), (self.V, v)):
            if val is not None:
                sr = (sr | bit) if val else (sr & ~bit)
        self.r[2] = sr & 0xFFFF

    def flag(self, bit):
        return 1 if self.r[2] & bit else 0

    # ---------------------------------------------------------------- fetch
    def fetch(self):
        w = self.rw(self.r[0])
        self.r[0] = (self.r[0] + 2) & 0xFFFF
        return w

    def src_operand(self, reg, As, byte):
        """returns (value, mode_class) mode_class for cycle table: 'r','@','@+','#','x'"""
        if reg == 3:                                   # constant generator 2
            return ((0, 1, 2, 0xFFFF)[As] & (0xFF if byte else 0xFFFF)), 'r'
        if reg == 2 and As >= 2:                       # constant generator 1
            return (4 if As == 2 else 8), 'r'
        if As == 0:
            v = self.r[reg]
            return (v & 0xFF if byte else v), 'r'
        if As == 1:
            ext_addr = self.r[0]
            x = self.fetch()
            if reg == 2:   addr = x                     # &abs
            elif reg == 0: addr = (ext_addr + x) & 0xFFFF   # symbolic
            else:          addr = (self.r[reg] + x) & 0xFFFF
            return (self.rb(addr) if byte else self.rw(addr)), 'x'
        if As == 2:
            addr = self.r[reg]
            return (self.rb(addr) if byte else self.rw(addr)), '@'
        # As == 3
        if reg == 0:                                    # immediate
            v = self.fetch()
            return (v & 0xFF if byte else v), '#'
        addr = self.r[reg]
        inc = 1 if (byte and reg not in (0, 1)) else 2
        self.r[reg] = (self.r[reg] + inc) & 0xFFFF
        return (self.rb(addr) if byte else self.rw(addr)), '@+'

    def dst_addr(self, reg, Ad):
        if Ad == 0:
            return None
        ext_addr = self.r[0]
        x = self.fetch()
        if reg == 2:   return x
        if reg == 0:   return (ext_addr + x) & 0xFFFF
        return (self.r[reg] + x) & 0xFFFF

    # ---------------------------------------------------------------- step
    CYC_I = {  # (src class, dst is memory)
        ('r', 0): 1, ('@', 0): 2, ('@+', 0): 2, ('#', 0): 2, ('x', 0): 3,
        ('r', 1): 4, ('@', 1): 5, ('@+', 1): 5, ('#', 1): 5, ('x', 1): 6,
    }

    def step(self):
        pc0 = self.r[0]
        op = self.fetch()
        self.instrs += 1
        if op & 0xE000 == 0x2000:                       # jumps
            cond = (op >> 10) & 7
            off = op & 0x3FF
            if off & 0x200: off -= 0x400
            c, z, n, v = self.flag(self.C), self.flag(self.Z), self.flag(self.N), self.flag(self.V)
            take = (not z, z, not c, c, n, n == v, n != v, True)[cond]
            if take:
                self.r[0] = (self.r[0] + 2 * off) & 0xFFFF
            self.cycles += 2
            return
        if op & 0xFC00 == 0x1000:                       # format II
            opc = (op >> 7) & 7
            byte = (op >> 6) & 1
            As = (op >> 4) & 3
            reg = op & 0xF
            if opc == 6:                                # RETI
                self.r[2] = self.rw(self.r[1]); self.r[1] += 2
                self.r[0] = self.rw(self.r[1]); self.r[1] += 2
                self.cycles += 5
                return
            # operand location
            addr = None
            if reg == 3 or (reg == 2 and As >= 2):
                val, cls = self.src_operand(reg, As, byte)
            elif As == 0:
                val, cls = (self.r[reg] & (0xFF if byte else 0xFFFF)), 'r'
            elif As == 1:
                ext_addr = self.r[0]; x = self.fetch()
                addr = x if reg == 2 else ((ext_addr + x) if reg == 0 else (self.r[reg] + x)) & 0xFFFF
                val, cls = (self.rb(addr) if byte else self.rw(addr)), 'x'
            elif As == 2:
                addr = self.r[reg]; val = self.rb(addr) if byte else self.rw(addr); cls = '@'
            else:
                if reg == 0:
                    val = self.fetch(); cls = '#'
                    if byte: val &= 0xFF
                else:
                    addr = self.r[reg]
                    val = self.rb(addr) if byte else self.rw(addr)
                    self.r[reg] = (self.r[reg] + (1 if byte and reg != 1 else 2)) & 0xFFFF
                    cls = '@+'
            msb = 0x80 if byte else 0x8000
            mask = 0xFF if byte else 0xFFFF
            res = None
            if opc == 0:                                # RRC
                c = self.flag(self.C)
                res = (val >> 1) | (msb if c else 0)
                self.setf(c=val & 1, z=res == 0, n=res & msb, v=0)
            elif opc == 1:                              # SWPB
                res = ((val << 8) | (val >> 8)) & 0xFFFF
            elif opc == 2:                              # RRA
                res = (val >> 1) | (val & msb)
                self.setf(c=val & 1, z=res == 0, n=res & msb, v=0)
            elif opc == 3:                              # SXT
                res = (val | 0xFF00) if val & 0x80 else (val & 0xFF)
                self.setf(c=res != 0, z=res == 0, n=res & 0x8000, v=0)
            elif opc == 4:                              # PUSH
                self.r[1] = (self.r[1] - 2) & 0xFFFF
                if byte: self.wb(self.r[1], val)
                else:    self.ww(self.r[1], val)
                self.cycles += {'r': 3, '@': 4, '@+': 4, '#': 4, 'x': 5}[cls]
                return
            elif opc == 5:                              # CALL
                self.r[1] = (self.r[1] - 2) & 0xFFFF
                self.ww(self.r[1], self.r[0])
                self.r[0] = val & 0xFFFE
                self.cycles += {'r': 4, '@': 4, '@+': 5, '#': 5, 'x': 5}[cls]
                return
            else:
                raise RuntimeError(f"bad format II opcode at {pc0:04X}")
            res &= mask
            if addr is None:
                self.r[reg] = res
            elif byte:
                self.wb(addr, res)
            else:
                self.ww(addr, res)
            self.cycles += {'r': 1, '@': 3, '@+': 3, '#': 3, 'x': 4}[cls]
            return
        # format I
        opc = op >> 12
        if opc < 4:
            raise RuntimeError(f"illegal opcode {op:04X} at {pc0:04X}")
        sreg = (op >> 8) & 0xF
        Ad = (op >> 7) & 1
        byte = (op >> 6) & 1
        As = (op >> 4) & 3
        dreg = op & 0xF
        src, cls = self.src_operand(sreg, As, byte)
        daddr = self.dst_addr(dreg, Ad)
        mask = 0xFF if byte else 0xFFFF
        msb = 0x80 if byte else 0x8000
        if opc == 4:                                    # MOV (no dst read)
            dst = 0
        elif daddr is None:
            dst = self.r[dreg] & mask
        else:
            dst = self.rb(daddr) if byte else self.rw(daddr)
        write = True
        if opc in (5, 6):                               # ADD, ADDC
            c = self.flag(self.C) if opc == 6 else 0
            t = src + dst + c
            res = t & mask
            self.setf(c=t > mask, z=res == 0, n=res & msb,
                      v=((src ^ res) & (dst ^ res) & msb) != 0)
        elif opc in (7, 8, 9):                          # SUBC, SUB, CMP
            c = self.flag(self.C) if opc == 7 else 1
            t = dst + ((~src) & mask) + c
            res = t & mask
            self.setf(c=t > mask, z=res == 0, n=res & msb,
                      v=((dst ^ src) & (dst ^ res) & msb) != 0)
            if opc == 9: write = False
        elif opc == 0xA:                                # DADD
            c = self.flag(self.C); res = 0
            for i in range(0, 16 if not byte else 8, 4):
                d = ((src >> i) & 15) + ((dst >> i) & 15) + c
                c = 1 if d > 9 else 0
                if c: d -= 10
                res |= d << i
            self.setf(c=c, z=res == 0, n=res & msb)
        elif opc == 0xB:                                # BIT
            res = src & dst
            self.setf(c=res != 0, z=res == 0, n=res & msb, v=0)
            write = False
        elif opc == 0xC:                                # BIC
            res = dst & ~src & mask
        elif opc == 0xD:                                # BIS
            res = dst | src
        elif opc == 0xE:                                # XOR
            res = (src ^ dst) & mask
            self.setf(c=res != 0, z=res == 0, n=res & msb, v=(src & msb) and (dst & msb))
        elif opc == 0xF:                                # AND
            res = src & dst
            self.setf(c=res != 0, z=res == 0, n=res & msb, v=0)
        else:
            res = src                                   # MOV
        cyc = self.CYC_I[(cls, 1 if daddr is not None else 0)]
        if daddr is None and dreg == 0:
            cyc += 1
        self.cycles += cyc
        if not write:
            return
        res &= mask
        if daddr is None:
            if dreg == 3 or (dreg == 2 and False):
                return
            self.r[dreg] = res                          # byte op clears high byte
            if dreg == 0: self.r[0] &= 0xFFFE
        elif byte:
            self.wb(daddr, res)
        else:
            self.ww(daddr, res)

    # ---------------------------------------------------------------- calls
    def run(self, start, cycles):
        """Run a whole program from `start` for `cycles` CPU cycles."""
        self.r[0] = self.sym(start) if isinstance(start, str) else start
        end = self.cycles + cycles
        while self.cycles < end:
            self.step()

    def call(self, name_or_addr, *args, max_instr=50_000_000, check_abi=True):
        addr = self.sym(name_or_addr) if isinstance(name_or_addr, str) else name_or_addr
        for i, a in enumerate(args):
            self.r[12 + i] = a & 0xFFFF
        # poison scratch regs we did not pass
        for i in range(len(args), 4):
            self.r[12 + i] = 0xDEAD
        self.r[11] = 0xBEEF
        saved = self.r[4:11]
        sp0 = self.r[1]
        self.r[1] = (self.r[1] - 2) & 0xFFFF
        self.ww(self.r[1], SENTINEL)
        self.r[0] = addr
        c0 = self.cycles
        n = 0
        while self.r[0] != SENTINEL:
            self.step()
            n += 1
            if n > max_instr:
                raise RuntimeError(f"{name_or_addr}: runaway at PC={self.r[0]:04X}")
        if check_abi:
            if self.r[1] != sp0:
                raise RuntimeError(f"{name_or_addr}: SP not restored ({self.r[1]:04X} vs {sp0:04X})")
            if self.r[4:11] != saved:
                raise RuntimeError(f"{name_or_addr}: clobbered R4-R10 {saved} -> {self.r[4:11]}")
        # let the last SPI byte finish
        self._spi_update()
        return self.r[12], self.cycles - c0
