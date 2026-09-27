#!/usr/bin/env python3
"""
ti2gnu.py - Convert the TI-assembler subset used by tft4.asm into GNU/LLVM
syntax so it can be assembled with llvm-mc for the emulator tests.

Handles: column-0 labels (with or without ':'), .cdecls, .def/.ref/.global,
.sect/.text/.data, .bss, NAME .set/.equ, NAME .macro ... .endm (parameters are
rewritten to \\param), .retain/.retainrefs/.end, R4 -> r4, 0101b binary.
"""
import os, re, sys

DROP = {'.retain', '.retainrefs', '.end', '.newblock', '.nolist', '.list'}


def conv_operands(s):
    s = re.sub(r'\b[Rr](1[0-5]|[0-9])\b', lambda m: 'r' + m.group(1), s)
    s = re.sub(r'\b(SP|PC|SR)\b', lambda m: m.group(1).lower(), s)
    s = re.sub(r'\b([01]+)[bB]\b', r'0b\1', s)
    return s


OPC = {'mov': 4, 'add': 5, 'addc': 6, 'subc': 7, 'sub': 8, 'cmp': 9, 'dadd': 10,
       'bit': 11, 'bic': 12, 'bis': 13, 'xor': 14, 'and': 15}


def encode_autoinc_to_indexed(mnem, rest):
    """llvm-mc rejects `op @Rs+, X(Rd)` (valid on MSP430); emit it as raw words."""
    m = re.match(r'@r(\d+)\+\s*,\s*(-?\w+)\(r(\d+)\)\s*$', rest.strip())
    base, _, sz = mnem.partition('.')
    if not m or base not in OPC:
        return None
    bw = 1 if sz == 'b' else 0
    w = (OPC[base] << 12) | (int(m.group(1)) << 8) | (1 << 7) | (bw << 6) | (3 << 4) | int(m.group(3))
    return f'\t.word\t0x{w:04X}, {m.group(2)}'


def split_comment(line):
    out, q = [], False
    for i, ch in enumerate(line):
        if ch == '"': q = not q
        if ch == ';' and not q and not (0 < i < len(line) - 1 and line[i - 1] == "'" and line[i + 1] == "'"):
            return line[:i], line[i:]
    return line, ''


def section(name):
    n = name.strip().strip('"')
    if n == '.const': return '\t.section .rodata,"a"'
    if n == '.TI.persistent': return '\t.section .persistent,"aw"'
    if n in ('.text', '.data'): return '\t' + n
    return '\t.section .vec_' + re.sub(r'\W', '_', n) + ',"a"'


SRC_DIR = '.'


def convert(lines, equ_file):
    out, macro_params = [], None
    for raw in lines:
        line = raw.rstrip('\n').replace('\r', '')
        code, comment = split_comment(line)
        if macro_params is not None:
            code = re.sub(r'(\w+)\?', r'\1\\@', code)      # TI unique macro labels
        if not code.strip():
            out.append(comment.replace(';', ';', 1) if comment else '')
            continue
        label = None
        if code[0] not in ' \t':
            m = re.match(r'([A-Za-z_$.][\w$.\\@]*):?(.*)', code)
            label, code = m.group(1), m.group(2)
        toks = code.split(None, 1)
        mnem = toks[0] if toks else ''
        rest = toks[1] if len(toks) > 1 else ''
        ml = mnem.lower()

        if ml in ('.set', '.equ') and label:
            out.append(f'\t.set\t{label}, {conv_operands(rest)}'); continue
        if ml == '.macro' and label:
            params = [p.strip() for p in rest.split(',') if p.strip()]
            macro_params = params
            out.append(f'\t.macro\t{label} ' + ', '.join(params)); continue
        if ml == '.endm':
            macro_params = None
            out.append('\t.endm'); continue

        if label:
            out.append(f'{label}:')
        if not mnem:
            continue
        if ml in ('.include', '.copy') and rest.strip().strip('"').endswith('.inc'):
            name = rest.strip().strip('"')         # TI syntax: expand it here; look next
            dirs = [SRC_DIR] + [d for d in os.environ.get('TI2GNU_INCLUDE', '').split(':') if d]
            path = next((os.path.join(d, name) for d in dirs if os.path.exists(os.path.join(d, name))),
                        os.path.join(SRC_DIR, name))      # to the source, then TI2GNU_INCLUDE
            out.append(f'; ---- {rest.strip()} ----')
            out.append(convert(open(path).readlines(), equ_file).rstrip('\n'))
            continue
        if ml == '.cdecls':
            out.append(f'\t.include "{equ_file}"'); continue
        if ml in ('.def', '.ref', '.global', '.globl'):
            for s in rest.split(','):
                out.append(f'\t.global\t{s.strip()}')
            continue
        if ml in DROP:
            continue
        if ml == '.sect':
            out.append(section(rest)); continue
        if ml in ('.text', '.data'):
            out.append('\t' + ml); continue
        if ml == '.bss':
            parts = [p.strip() for p in rest.split(',')]
            name, size = parts[0], parts[1]
            al = parts[2] if len(parts) > 2 else '2'
            out += ['\t.pushsection .bss,"aw",@nobits', f'\t.balign {al}',
                    f'{name}:', f'\t.space {size}', '\t.popsection']
            continue
        if ml == '.align':
            out.append(f'\t.balign {rest}'); continue
        if ml == '.byte' and '"' in rest:              # TI: strings in .byte
            vals = []
            for m in re.finditer(r'"([^"]*)"|([^,]+)', rest):
                if m.group(1) is not None:
                    vals += [str(ord(c)) for c in m.group(1)]
                elif m.group(2).strip():
                    vals.append(conv_operands(m.group(2).strip()))
            out.append('\t.byte\t' + ', '.join(vals)); continue
        rest = re.sub(r"'(.)'", lambda m: str(ord(m.group(1))), rest)   # 'c' constants
        rest = conv_operands(rest)
        enc = encode_autoinc_to_indexed(ml, rest)
        if enc:
            out.append(enc + '\t; ' + mnem + ' ' + rest); continue
        if macro_params:
            for p in macro_params:
                rest = re.sub(r'(?<![\\\w])' + re.escape(p) + r'\b', '\\\\' + p, rest)
        out.append(f'\t{mnem}\t{rest}')
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    src, dst, equ = sys.argv[1], sys.argv[2], sys.argv[3]
    SRC_DIR = os.path.dirname(os.path.abspath(src))
    open(dst, 'w').write(convert(open(src).readlines(), equ))
