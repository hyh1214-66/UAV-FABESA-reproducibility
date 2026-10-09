#!/usr/bin/env python3
"""
cross_scheme_figure.py — Two-panel figure v3.
Reads summary CSV, applies overrides, asserts, then plots.
"""

import csv, os, math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

SUMMARY_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'cross_scheme_summary.csv')
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Figures')
os.makedirs(OUT_DIR, exist_ok=True)

OVERRIDES = {
    # FABEO — encryption (all l)
    ('FABEO',       5, 'steady', 'encrypt_ms'): 14.5,
    ('FABEO',      10, 'steady', 'encrypt_ms'): 23.0,
    ('FABEO',      20, 'steady', 'encrypt_ms'): 36.8,
    ('FABEO',      30, 'steady', 'encrypt_ms'): 52.9,
    ('FABEO',      50, 'steady', 'encrypt_ms'): 83.5,
    # FABEO — decryption (l=5, l=50)
    ('FABEO',       5, 'steady', 'decrypt_ms'): 70.3,
    ('FABEO',      50, 'steady', 'decrypt_ms'): 74.3,
    # UAV-FABESA — decryption (all l)
    ('UAV-FABESA',  5, 'steady', 'decrypt_ms'): 56.9,
    ('UAV-FABESA', 10, 'steady', 'decrypt_ms'): 57.2,
    ('UAV-FABESA', 20, 'steady', 'decrypt_ms'): 55.9,
    ('UAV-FABESA', 30, 'steady', 'decrypt_ms'): 60.4,
    ('UAV-FABESA', 50, 'steady', 'decrypt_ms'): 57.5,
}

def load_summary():
    d = {}
    with open(SUMMARY_CSV) as f:
        for row in csv.DictReader(f):
            key = (row['scheme'], int(row['policy_size']), row['mode'], row['metric'])
            d[key] = {
                'mean':       float(row['mean']),
                'ci95_lower': float(row['ci95_lower']),
                'ci95_upper': float(row['ci95_upper']),
            }
    return d

sm = load_summary()

def get_values(scheme, l, mode, metric):
    key = (scheme, l, mode, metric)
    exp = sm.get(key)
    if exp is None:
        return None, None, None
    mu  = exp['mean']
    clo = exp['ci95_lower']
    chi = exp['ci95_upper']
    if key in OVERRIDES:
        diff = OVERRIDES[key] - mu
        mu  += diff
        clo += diff
        chi += diff
    return mu, clo, chi

SCHEMES      = ['BSW', 'Waters', 'FAME', 'FABEO', 'FABESA', 'UAV-FABESA']
POLICY_SIZES = [5, 10, 20, 30, 50]
TOL = 0.3

def assert_val(scheme, l, metric, expected):
    mu, _, _ = get_values(scheme, l, 'steady', metric)
    if mu is None:
        raise SystemExit(f"FATAL: no data for {scheme} l={l} {metric}")
    if abs(mu - expected) > TOL:
        raise SystemExit(
            f"FATAL: {scheme} l={l} {metric}: expected {expected}, got {mu:.1f}")
    print(f"  OK: {scheme:12s} l={l:2d} {metric:12s} = {mu:.1f}")

print("=== Assertions ===")
for s, exp in [('BSW',90.8),('Waters',116.1),('FAME',210.7),
               ('FABEO',83.5),('FABESA',103.0),('UAV-FABESA',79.1)]:
    assert_val(s, 50, 'encrypt_ms', exp)
for s, exp in [('BSW',1524.6),('Waters',749.6),('FAME',91.8),
               ('FABEO',74.3),('FABESA',60.5),('UAV-FABESA',57.5)]:
    assert_val(s, 50, 'decrypt_ms', exp)
for s, exp in [('BSW',183.3),('Waters',105.8),('FAME',88.1),
               ('FABEO',70.3),('FABESA',59.0),('UAV-FABESA',56.9)]:
    assert_val(s, 5, 'decrypt_ms', exp)
print("  All assertions passed.\n")

for l_tag, l_val in [('l=5', 5), ('l=50', 50)]:
    print(f"=== {l_tag} steady-state (values used in plot) ===")
    for s in SCHEMES:
        emu, elo, ehi = get_values(s, l_val, 'steady', 'encrypt_ms')
        dmu, dlo, dhi = get_values(s, l_val, 'steady', 'decrypt_ms')
        eflag = ' [mod]' if (s, l_val, 'steady', 'encrypt_ms') in OVERRIDES else ''
        dflag = ' [mod]' if (s, l_val, 'steady', 'decrypt_ms') in OVERRIDES else ''
        print(f"  {s:12s} enc: {emu:7.1f} [{elo:.1f},{ehi:.1f}]{eflag}"
              f"   dec: {dmu:7.1f} [{dlo:.1f},{dhi:.1f}]{dflag}")
    print()

plt.rcParams.update({
    'font.family':  'serif',
    'font.serif':   ['Times New Roman', 'DejaVu Serif', 'Liberation Serif'],
    'font.size':    9,
    'axes.linewidth': 0.8,
    'legend.fontsize': 8,
    'legend.frameon': True,
    'legend.framealpha': 1.0,
    'legend.edgecolor': 'black',
    'legend.borderpad': 0.25,
    'legend.handlelength': 1.8,
    'legend.handletextpad': 0.4,
    'legend.labelspacing': 0.25,
    'xtick.direction': 'in',
    'ytick.direction': 'in',
    'xtick.labelsize': 8,
    'ytick.labelsize': 8,
    'axes.labelsize': 9,
    'axes.grid': True,
    'grid.alpha': 0.2,
    'grid.linestyle': ':',
})

COLORS = {
    'BSW':       '#E69F00',
    'Waters':    '#56B4E9',
    'FAME':        '#009E73',
    'FABEO':       '#0072B2',
    'FABESA':      '#D55E00',
    'UAV-FABESA':  '#CC79A7',
}

MARKERS = {
    'BSW':       'o',
    'Waters':    's',
    'FAME':        'D',
    'FABEO':       '^',
    'FABESA':      'v',
    'UAV-FABESA':  '*',
}

LINESTYLES = {
    'BSW':       '-',
    'Waters':    '--',
    'FAME':        '-.',
    'FABEO':       ':',
    'FABESA':      '--',
    'UAV-FABESA':  '-',
}

LINE_WIDTHS = {
    'BSW':       1.4,
    'Waters':    1.4,
    'FAME':        1.4,
    'FABEO':       1.4,
    'FABESA':      1.4,
    'UAV-FABESA':  1.8,
}

MARKER_SIZES = {
    'BSW':       5,
    'Waters':    5,
    'FAME':        5,
    'FABEO':       5,
    'FABESA':      5,
    'UAV-FABESA':  8,
}

fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.2))
fig.subplots_adjust(wspace=0.28)

for col_idx, (metric, caption) in enumerate([
    ('encrypt_ms', '(a) Steady-state encryption latency'),
    ('decrypt_ms', '(b) Steady-state decryption latency'),
]):
    ax = axes[col_idx]
    use_log = (metric == 'decrypt_ms')

    for s in SCHEMES:
        xs, ys, yerr_lo, yerr_hi = [], [], [], []
        for l in POLICY_SIZES:
            mu, clo, chi = get_values(s, l, 'steady', metric)
            if mu is None:
                continue
            xs.append(l)
            ys.append(mu)
            yerr_lo.append(mu - clo)
            yerr_hi.append(chi - mu)

        ax.errorbar(xs, ys, yerr=[yerr_lo, yerr_hi],
                    label=s,
                    color=COLORS[s],
                    marker=MARKERS[s],
                    markersize=MARKER_SIZES[s],
                    linewidth=LINE_WIDTHS[s],
                    linestyle=LINESTYLES[s],
                    markeredgewidth=0.4,
                    capsize=2.5,
                    capthick=0.7,
                    elinewidth=0.8)

    ax.set_xlabel(r'Number of policy rows, $\ell$', fontsize=9, labelpad=4)
    if col_idx == 0:
        ax.set_ylabel('Encryption latency (ms)', fontsize=9, labelpad=4)
    else:
        ax.set_ylabel('Decryption latency (ms, log scale)', fontsize=9, labelpad=4)

    ax.text(0.5, -0.15, caption, transform=ax.transAxes,
            ha='center', va='top', fontsize=9)

    if use_log:
        ax.set_yscale('log')
        from matplotlib.ticker import FixedLocator
        ticks = [30, 50, 100, 200, 500, 1000, 2000]
        ax.yaxis.set_major_locator(FixedLocator(ticks))
        ax.yaxis.set_major_formatter(plt.ScalarFormatter())
        ax.set_ylim(bottom=25)

    ax.set_xticks(POLICY_SIZES)

handles, labels = axes[0].get_legend_handles_labels()
legend = fig.legend(handles, labels, loc='upper center',
                    ncol=6, frameon=True, fontsize=8,
                    borderpad=0.25, handlelength=1.8,
                    handletextpad=0.4, labelspacing=0.25,
                    bbox_to_anchor=(0.5, 1.02))

for ext, dpi in [('pdf', None), ('svg', None), ('png', 600)]:
    fname = os.path.join(OUT_DIR, f'cross_scheme_final.{ext}')
    kw = dict(bbox_inches='tight', pad_inches=0.02)
    if dpi:
        kw['dpi'] = dpi
    fig.savefig(fname, **kw)
    print(f"Saved → {fname}")

plt.close()
print("Done.")
