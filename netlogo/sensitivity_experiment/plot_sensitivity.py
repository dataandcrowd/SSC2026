#!/usr/bin/env python3
"""Boxplots for the BehaviorSpace sensitivity tables.

Each run's 20 daily values (peak-vc-inner, or peak % traffic at LoS E/F per
group for the k-factor sweep) become one box, paired No-Charge vs ToU at each
parameter value, so the day-to-day spread that the mean/SD summary hides is
visible directly.

Reads  netlogo/output/tables/sensitivity-*.csv
Writes netlogo/output/figures/sensitivity_box_behaviour.png
       netlogo/output/figures/sensitivity_box_kfactor.png
"""
import csv, os
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

FEE_ORDER = ["No-Charge", "tou"]
FEE_LABEL = {"No-Charge": "No charge", "tou": "ToU"}
FEE_COLOR = {"No-Charge": "#9e9e9e", "tou": "#4878a8"}


def load(path):
    with open(path) as f:
        rows = list(csv.reader(f))
    hdr_i = next(i for i, r in enumerate(rows) if r and r[0] == "[run number]")
    return rows[hdr_i], [r for r in rows[hdr_i + 1:] if r]


def daily_series(path, pvar, metric):
    """{(param value, fee): [one value per day 1..n]} with day-0 and duplicate
    day rows dropped (BehaviorSpace records a step-0 row before the first day)."""
    hdr, data = load(path)
    cm, cf, cp = hdr.index(metric), hdr.index("fee-regime"), hdr.index(pvar)
    cr, cd = hdr.index("[run number]"), hdr.index("current-sim-day")
    per_run = defaultdict(dict)  # run -> {day: value}, last row per day wins
    meta = {}
    for r in data:
        day = int(float(r[cd]))
        if day < 1:
            continue
        per_run[r[cr]][day] = float(r[cm])
        meta[r[cr]] = (r[cp].strip('"'), r[cf].strip('"'))
    series = {}
    for run, by_day in per_run.items():
        series[meta[run]] = [by_day[d] for d in sorted(by_day)]
    return series


def paired_boxes(ax, series, params, ylabel, title):
    """Draw No-Charge/ToU box pairs at each parameter value on one axis."""
    width, gap = 0.32, 0.18
    for j, fee in enumerate(FEE_ORDER):
        offs = (j - 0.5) * (width + gap)
        pos = [i + offs for i in range(len(params))]
        vals = [series.get((p, fee), []) for p in params]
        bp = ax.boxplot(vals, positions=pos, widths=width, patch_artist=True,
                        medianprops=dict(color="black"),
                        flierprops=dict(marker="o", markersize=3, alpha=0.5))
        for box in bp["boxes"]:
            box.set(facecolor=FEE_COLOR[fee], alpha=0.75)
    ax.set_xticks(range(len(params)))
    ax.set_xticklabels(params)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10)
    ax.grid(axis="y", alpha=0.3)


def legend_handles():
    from matplotlib.patches import Patch
    return [Patch(facecolor=FEE_COLOR[f], alpha=0.75, label=FEE_LABEL[f])
            for f in FEE_ORDER]


# --- Figure 1: behavioural parameters, daily peak inner-cordon V/C ----------
BEHAVIOUR = [
    ("sensitivity-pay", "base-beta", "Exp-Decay: price sensitivity"),
    ("sensitivity-elfarol", "el-farol-threshold", "El Farol: comfort threshold"),
    ("sensitivity-ql-alpha", "ql-alpha", "Q-Learning: learning rate"),
    ("sensitivity-ql-epsilon", "ql-epsilon-init", "Q-Learning: exploration"),
]
fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharey=True)
drew = False
for ax, (exp, pvar, title) in zip(axes.flat, BEHAVIOUR):
    path = os.path.join(TABLES, f"{exp}.csv")
    if not os.path.exists(path):
        ax.set_axis_off(); continue
    series = daily_series(path, pvar, "peak-vc-inner")
    params = sorted({p for p, _ in series}, key=float)
    paired_boxes(ax, series, params, "daily peak inner V/C", title)
    ax.set_xlabel(pvar)
    drew = True
if drew:
    fig.legend(handles=legend_handles(), loc="upper right",
               bbox_to_anchor=(0.99, 0.93), ncol=2, frameon=False)
    fig.suptitle("Sensitivity: daily peak inner-cordon V/C (20 days per box)")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = os.path.join(FIGS, "sensitivity_box_behaviour.png")
    fig.savefig(out, dpi=200)
    print("wrote", out)
plt.close(fig)

# --- Figure 2: k-factor sweep, daily peak % traffic at LoS E/F per group ----
GROUPS = [("peak-ef-mwy", "Motorways (MWY)"), ("peak-ef-cbd", "CBD"),
          ("peak-ef-east", "Arterial East"), ("peak-ef-west", "Arterial West")]
path = os.path.join(TABLES, "sensitivity-kfactor.csv")
if os.path.exists(path):
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharey=True)
    for ax, (metric, title) in zip(axes.flat, GROUPS):
        series = daily_series(path, "k-factor", metric)
        params = sorted({p for p, _ in series}, key=float)
        paired_boxes(ax, series, params, "daily peak % at LoS E/F", title)
        ax.set_xlabel("k-factor")
    fig.legend(handles=legend_handles(), loc="upper right",
               bbox_to_anchor=(0.99, 0.93), ncol=2, frameon=False)
    fig.suptitle("k-factor sweep: daily peak share of traffic at LoS E/F (20 days per box)")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = os.path.join(FIGS, "sensitivity_box_kfactor.png")
    fig.savefig(out, dpi=200)
    print("wrote", out)
    plt.close(fig)
else:
    print(f"(skip k-factor figure: {path} not found)")

# --- Figure 3: ToU reduction (%) in mean daily peak inner V/C, by parameter -
fig, axes = plt.subplots(2, 2, figsize=(9, 6), sharey=True)
drew = False
for ax, (exp, pvar, title) in zip(axes.flat, BEHAVIOUR):
    path = os.path.join(TABLES, f"{exp}.csv")
    if not os.path.exists(path):
        ax.set_axis_off(); continue
    series = daily_series(path, pvar, "peak-vc-inner")
    params = sorted({p for p, _ in series}, key=float)
    reds = []
    for p in params:
        none = series.get((p, "No-Charge")); tou = series.get((p, "tou"))
        if not (none and tou):
            reds.append(float("nan")); continue
        m0 = sum(none) / len(none); m1 = sum(tou) / len(tou)
        reds.append(100 * (m0 - m1) / m0 if m0 else 0.0)
    ax.plot([float(p) for p in params], reds, "o-", color="#4878a8", lw=2)
    for x, y in zip(params, reds):
        ax.annotate(f"{y:.1f}%", (float(x), y), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=8)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel(pvar)
    ax.set_ylabel("ToU reduction in peak inner V/C (%)")
    ax.grid(axis="y", alpha=0.3)
    ax.margins(y=0.15)
    drew = True
if drew:
    fig.suptitle("ToU effect vs behavioural parameters (reduction in 20-day mean of daily peak inner V/C)")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = os.path.join(FIGS, "sensitivity_reduction.png")
    fig.savefig(out, dpi=200)
    print("wrote", out)
plt.close(fig)

# --- Figure 4: El Farol daily time series (oscillation made visible) --------
path = os.path.join(TABLES, "sensitivity-elfarol.csv")
if os.path.exists(path):
    series = daily_series(path, "el-farol-threshold", "peak-vc-inner")
    params = sorted({p for p, _ in series}, key=float)
    fig, axes = plt.subplots(1, len(params), figsize=(11, 3.6), sharey=True)
    for ax, p in zip(axes, params):
        for fee in FEE_ORDER:
            vals = series.get((p, fee), [])
            ax.plot(range(1, len(vals) + 1), vals, "o-", ms=3, lw=1.4,
                    color=FEE_COLOR[fee], label=FEE_LABEL[fee])
        ax.set_title(f"threshold = {p}", fontsize=10)
        ax.set_xlabel("day")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("daily peak inner V/C")
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("El Farol: day-to-day oscillation of peak inner-cordon V/C")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = os.path.join(FIGS, "sensitivity_elfarol_timeseries.png")
    fig.savefig(out, dpi=200)
    print("wrote", out)
    plt.close(fig)
else:
    print(f"(skip El Farol time-series figure: {path} not found)")
