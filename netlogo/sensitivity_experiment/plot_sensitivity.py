#!/usr/bin/env python3
"""Figures for the BehaviorSpace sensitivity tables.

Reads  output/tables/sensitivity-*.csv  (override dir with SENS_TABLES)
Writes output/figures/                  (override dir with SENS_FIGS)

  sensitivity_box_behaviour.png    daily peak inner V/C, one box per run
  sensitivity_box_kfactor.png      group LoS E/F over the k-factor sweep
  sensitivity_reduction.png        ToU reduction by cordon position
  sensitivity_positions.png        peak V/C by position at each rule baseline
  sensitivity_elfarol_timeseries.png  El Farol day-by-day oscillation

A box is one run's per-day values, paired No-Charge vs ToU, so the day-to-day
spread the mean/SD summary hides stays visible.

The two position figures need peak-vc-boundary / peak-vc-peripheral, which only
exist in tables written after the metric set was expanded (2026-07-25). Older
tables are handled: those series are skipped and a note is printed.
"""
import csv, os
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
# Paths can be redirected (SENS_TABLES / SENS_FIGS) to run the figures against
# a test fixture without touching output/.
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

FEE_ORDER = ["No-Charge", "tou"]
FEE_LABEL = {"No-Charge": "No charge", "tou": "ToU"}
FEE_COLOR = {"No-Charge": "#9e9e9e", "tou": "#4878a8"}


def load(path):
    with open(path) as f:
        rows = list(csv.reader(f))
    hdr_i = next(i for i, r in enumerate(rows) if r and r[0] == "[run number]")
    return rows[hdr_i], [r for r in rows[hdr_i + 1:] if r]


def has_metric(path, metric):
    """True if the table carries this metric column. Tables written before the
    metric set was expanded (2026-07-25) only have peak-vc-inner, so the
    position figures must degrade gracefully rather than crash."""
    return metric in load(path)[0]


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

# --- Figure 3: ToU reduction (%) by cordon position, per parameter ----------
# Three positions on one axis: if pricing relieves the inner cordon while
# pushing queues onto the boundary, the boundary line drops below zero.
POSITIONS = [("peak-vc-inner", "inner", "#4878a8"),
             ("peak-vc-boundary", "boundary", "#d1893a"),
             ("peak-vc-peripheral", "peripheral", "#5aa469")]


def reductions(series, params):
    """ToU reduction (%) off the No-Charge mean, per parameter value."""
    out = []
    for p in params:
        none = series.get((p, "No-Charge")); tou = series.get((p, "tou"))
        if not (none and tou):
            out.append(float("nan")); continue
        m0 = sum(none) / len(none); m1 = sum(tou) / len(tou)
        out.append(100 * (m0 - m1) / m0 if m0 else 0.0)
    return out


fig, axes = plt.subplots(2, 2, figsize=(9.5, 6.5), sharey=True)
drew = False
missing_pos = []
for ax, (exp, pvar, title) in zip(axes.flat, BEHAVIOUR):
    path = os.path.join(TABLES, f"{exp}.csv")
    if not os.path.exists(path):
        ax.set_axis_off(); continue
    for metric, label, colour in POSITIONS:
        if not has_metric(path, metric):
            missing_pos.append(f"{exp}:{label}")
            continue
        series = daily_series(path, pvar, metric)
        params = sorted({p for p, _ in series}, key=float)
        ax.plot([float(p) for p in params], reductions(series, params),
                "o-", color=colour, lw=2, label=label)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel(pvar)
    ax.set_ylabel("ToU reduction in daily peak V/C (%)")
    ax.grid(axis="y", alpha=0.3)
    ax.margins(y=0.18)
    drew = True
if drew:
    handles, labels = axes.flat[0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper right", ncol=3, frameon=False,
                   title="cordon position", bbox_to_anchor=(0.99, 0.97))
    fig.suptitle("ToU effect by cordon position (reduction in mean daily peak V/C)")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = os.path.join(FIGS, "sensitivity_reduction.png")
    fig.savefig(out, dpi=200)
    print("wrote", out)
    if missing_pos:
        print("  note: boundary/peripheral absent from older tables —",
              f"{len(missing_pos)} series skipped (re-run to populate)")
plt.close(fig)

# --- Figure 3b: absolute levels by position, at each rule's baseline --------
# Reduction percentages off a small base can mislead, so show the levels too.
BASELINE = {"sensitivity-pay": 0.5, "sensitivity-elfarol": 0.6,
            "sensitivity-ql-alpha": 0.1, "sensitivity-ql-epsilon": 0.4}
if any(os.path.exists(os.path.join(TABLES, f"{e}.csv"))
       and has_metric(os.path.join(TABLES, f"{e}.csv"), "peak-vc-boundary")
       for e, _, _ in BEHAVIOUR):
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 6.5), sharey=True)
    for ax, (exp, pvar, title) in zip(axes.flat, BEHAVIOUR):
        path = os.path.join(TABLES, f"{exp}.csv")
        if not (os.path.exists(path) and has_metric(path, "peak-vc-boundary")):
            ax.set_axis_off(); continue
        base = BASELINE[exp]
        per_pos = {}
        for metric, label, _ in POSITIONS:
            series = daily_series(path, pvar, metric)
            for (p, fee), vals in series.items():
                if abs(float(p) - base) < 1e-9:
                    per_pos[(label, fee)] = vals
        labels = [lab for _, lab, _ in POSITIONS]
        paired_boxes(ax, {(lab, fee): per_pos.get((lab, fee), [])
                          for lab in labels for fee in FEE_ORDER},
                     labels, "daily peak V/C", f"{title}  ({pvar} = {base})")
        ax.set_xlabel("cordon position")
    fig.legend(handles=legend_handles(), loc="upper right", ncol=2,
               frameon=False, bbox_to_anchor=(0.99, 0.97))
    fig.suptitle("Daily peak V/C by cordon position, at each rule's baseline parameter")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = os.path.join(FIGS, "sensitivity_positions.png")
    fig.savefig(out, dpi=200)
    print("wrote", out)
    plt.close(fig)
else:
    print("(skip position-levels figure: no table has peak-vc-boundary yet)")

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
