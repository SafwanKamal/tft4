#!/usr/bin/env python3
"""Build GNU-as equates (fr6989_equ.inc) from TI's GCC device header + symbols .ld,
standing in for TI's `.cdecls C,LIST,"msp430.h"` when assembling with llvm-mc."""
import re, sys
syms = {}
for m in re.finditer(r'PROVIDE\((\w+)\s*=\s*(0x[0-9A-Fa-f]+)\);', open(sys.argv[1]).read()):
    syms[m.group(1)] = int(m.group(2), 16)
defs = {}
for line in open(sys.argv[2]):
    m = re.match(r'#define\s+(\w+)\s+(.+?)\s*(/\*.*)?$', line)
    if m and '(' not in m.group(1):
        defs[m.group(1)] = m.group(2)
vals = dict(syms)
for _ in range(6):
    for k, e in defs.items():
        if k in vals: continue
        ex = re.sub(r'\b(0x[0-9A-Fa-f]+|\d+)[uUlL]*\b', r'\1', e)
        try:
            v = eval(ex, {"__builtins__": {}}, vals)
            if isinstance(v, int): vals[k] = v & 0xFFFFFFFF
        except Exception:
            pass
with open(sys.argv[3], 'w') as f:
    for k in sorted(vals):
        f.write(f"\t.set\t{k}, 0x{vals[k]:X}\n")
print(len(vals), "equates")
