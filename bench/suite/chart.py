#!/usr/bin/env python3
"""chart.py - suite.png from suite.json (and suite_v3.json for the earlier tft4)."""
import json, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

rows = [r for r in json.load(open('suite.json')) if not r['scene'].startswith('Idle')]
old = {r['scene']: r for r in json.load(open('suite_v3.json'))} if len(sys.argv) < 2 else {}
BLUE, ORANGE, GREY = '#2a78d6', '#eb6834', '#9aa4b1'
fig, ax = plt.subplots(figsize=(9, 6.2), dpi=130)
ys = list(range(len(rows)))[::-1]
for y, r in zip(ys, rows):
    c, t = r['TI C driver']['avg'], r['tft4 (asm)']['avg']
    ax.plot([min(c, t), max(c, t)], [y, y], color='#d5dae1', lw=3, zorder=1, solid_capstyle='round')
    if r['scene'] in old:
        v3 = old[r['scene']]['tft4 (asm)']['avg']
        ax.scatter([v3], [y], s=46, facecolors='none', edgecolors=BLUE, linewidths=1.2, alpha=0.55, zorder=2)
    ax.scatter([c], [y], s=60, color=ORANGE, zorder=3, edgecolors='white', linewidths=1.5)
    ax.scatter([t], [y], s=60, color=BLUE, zorder=3, edgecolors='white', linewidths=1.5)
    q = c / t
    lab = f'{q:.1f}x faster' if q >= 1 else f'{1 / q:.1f}x slower'
    right = max(c, t, old[r['scene']]['tft4 (asm)']['avg'] if r['scene'] in old else 0)
    ax.text(right * 1.14, y, lab, va='center', fontsize=8.5, color='#333')
    w = r['TI C driver']['wrong']
    if w:
        ax.text(min(c, t) / 1.12, y, f'C: {w} wrong px', va='center', ha='right', fontsize=7.5, color='#8a4a2e')
ax.set_yticks(ys)
ax.set_yticklabels([r['scene'] for r in rows], fontsize=9)
ax.set_xscale('log')
ax.set_xlim(0.25, 400)
ax.set_xticks([0.5, 1, 2, 5, 10, 20, 50, 100])
ax.set_xticklabels(['0.5', '1', '2', '5', '10', '20', '50', '100'])
ax.set_xlabel('ms per frame (drawing + sending), log scale, emulator at 8 MHz, 64 frames')
ax.grid(axis='x', color='#eceff3', lw=0.8)
for s in ('top', 'right', 'left'):
    ax.spines[s].set_visible(False)
ax.tick_params(axis='y', length=0)
from matplotlib.lines import Line2D
leg = [Line2D([0], [0], marker='o', color='w', markerfacecolor=BLUE, markersize=8, label='tft4 v4 (assembly)'),
       Line2D([0], [0], marker='o', color='w', markerfacecolor='none', markeredgecolor=BLUE, alpha=0.6, markersize=7, label='tft4 v3'),
       Line2D([0], [0], marker='o', color='w', markerfacecolor=ORANGE, markersize=8, label="TI's C driver (grlib)")]
ax.legend(handles=leg, loc='upper right', fontsize=8.5, frameon=False)
ax.set_title('tft4 vs TI C driver: same 13 scenes (idle left out)', fontsize=11, loc='left')
fig.tight_layout()
fig.savefig('suite.png')
print('wrote suite.png')
