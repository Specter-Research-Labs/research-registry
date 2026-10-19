#!/usr/bin/env python3
"""Render published topology/transport figures from archived analysis packets."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt

plt.switch_backend('Agg')

COHORTS = [
    ('lenia_all', 'Broad Lenia · 4,096 landmarks'),
    ('lenia_nofood8192', 'Single-family Lenia · 8,192'),
    ('dryad_fish', 'Fish · 232'),
    ('embryomaker', 'EmbryoMaker · 859'),
]
TRANSPORT_RUNS = [
    ('00049-flow-map-elite-53-7d70ce0c-square-ms0-medium-dense', 'Square loop'),
    ('flow-map-elite-53-7d70ce0c-medium-zeroarea-sm-dense', 'Retraced control'),
]
ROW_FIELDS = ['coordinateValues', 'sequenceIndex', 'transportedStateDistanceFromStart', 'phenotypeDistanceFromStart']
COLORS = ['#526bcc', '#368477', '#aa684e', '#8661a4']

parser = argparse.ArgumentParser()
parser.add_argument('--source-dir', type=Path, required=True)
parser.add_argument('--output-dir', type=Path, required=True)
args = parser.parse_args()
args.output_dir.mkdir(parents=True, exist_ok=True)
provenance = []


def read(name):
    raw = (args.source_dir / name).read_bytes()
    provenance.append({'file': name, 'sha256': hashlib.sha256(raw).hexdigest()})
    return json.loads(raw)


cohorts = []
for name, label in COHORTS:
    d = read(f'tda_profile_common_{name}_current.json')
    if name == 'lenia_all':
        t = next(x for x in d['landmarks'] if x['landmarkCount'] == 4096)['topology']
    else:
        t = d['exact']['topology']
    intervals = sorted(t['diagrams'][1], key=lambda x: x['persistence'], reverse=True)[:8]
    cohorts.append({'label': label, 'intervals': intervals})
paths = []
for folder, label in TRANSPORT_RUNS:
    d = read(f'localized-loop-validation-fish/runs/{folder}/stateful-continuation-packet.json')
    paths.append({'label': label, 'rows': [{k: r[k] for k in ROW_FIELDS} for r in d['rows']]})
(args.output_dir / 'topology-transport-data.json').write_text(
    json.dumps({'cohorts': cohorts, 'transport': paths, 'sources': provenance}, indent=2) + '\n')

plt.rcParams.update({
    'font.family': 'DejaVu Sans', 'font.size': 11, 'svg.fonttype': 'none',
    'axes.spines.top': False, 'axes.spines.right': False,
    'figure.facecolor': '#f8f5ec', 'axes.facecolor': '#f8f5ec',
    'text.color': '#202536', 'axes.labelcolor': '#202536',
})
fig, axs = plt.subplots(4, 1, figsize=(10, 9), sharex=True, layout='constrained')
for ax, c, color in zip(axs, cohorts, COLORS, strict=True):
    for i, v in enumerate(c['intervals']):
        ax.plot([v['birth'], v['death']], [8 - i] * 2, color=color, lw=3, solid_capstyle='round')
    ax.set_title(c['label'], loc='left', fontsize=12)
    ax.set_yticks([])
    ax.set_ylim(.3, 8.7)
    ax.spines['left'].set_visible(False)
    ax.grid(axis='x', alpha=.18)
axs[-1].set_xlabel('Connection distance in normalized shape coordinates')
axs[-1].set_xlim(0, 15)
fig.savefig(args.output_dir / 'fig-persistence-intervals.svg')
plt.close(fig)

fig, axs = plt.subplots(1, 2, figsize=(11, 4.8), layout='constrained')
for entry, color in zip(paths, COLORS[:len(paths)], strict=True):
    rows = entry['rows']
    x = [r['coordinateValues']['m.0'] for r in rows]
    y = [r['coordinateValues']['s.0'] for r in rows]
    axs[0].plot(x, y, '.-', color=color, label=entry['label'], alpha=.8)
    axs[0].plot(x[0], y[0], 'o', mfc='none', mec='#202536', ms=11)
    axs[1].plot(range(len(rows)), [r['transportedStateDistanceFromStart'] for r in rows], color=color, label=entry['label'])
axs[0].set(xlabel='Rule parameter m₀', ylabel='Rule parameter s₀', title='Parameters return to their start')
axs[1].set(xlabel='Recorded step', ylabel='State distance from first recorded state', title='The state continues to evolve')
axs[1].ticklabel_format(axis='y', style='sci', scilimits=(0, 0))
axs[1].legend(frameon=False, fontsize=10)
for ax in axs:
    ax.grid(alpha=.18)
fig.savefig(args.output_dir / 'fig-measured-transport.svg')
fig.set_size_inches(6, 8)
# Reuse the measured artists in a vertical layout for narrow screens.
grid = fig.add_gridspec(2, 1)
for i, ax in enumerate(axs):
    ax.set_subplotspec(grid[i, 0])
fig.savefig(args.output_dir / 'fig-measured-transport-mobile.svg')
plt.close(fig)
print('Rendered two figures and sanitized source data.')
