#!/usr/bin/env python3
"""V/C-based LoS figures from the hourly LoS-mix tables (`save-los-hours`).

For each day x clock hour the model records the network flow (real veh/h)
carried at each LoS grade A-F (flow-weighted over all 1,634 links). This
script aggregates those into:

  sensitivity_los_bands.png   stacked A-F shares by 2-hour band
                              (7-9, 9-11, ... 21-23, + all day),
                              No-Charge vs ToU bars side by side, per rule
  sensitivity_los_daily.png   same stacked shares by simulated day
  los_bpr_schematic.png       theoretical BPR speed curve S = sf/(1+a(v/c)^b)
                              with the HCM LoS bands shaded (model a=0.15, b=4)

Reads  output/tables/los_hours_<Rule>_{No-Charge,tou}.csv
Writes output/figures/

Band/day aggregation uses days > BURN_IN so learning rules are converged.
"""
import csv, os
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

FEE_ORDER = ["No-Charge", "tou"]
FEE_LABEL = {"No-Charge": "NC", "tou": "ToU"}
RULES = [("Exp-Decay", "Exp-Decay"), ("ElFarol", "El Farol"), ("Q-Learning", "Q-Learning")]
GRADES = ["A", "B", "C", "D", "E", "F"]
GRADE_COLOR = {"A": "#4a9a4a", "B": "#a5c85a", "C": "#f2d349",
               "D": "#e8973a", "E": "#d64545", "F": "#7d1f1f"}
BANDS = [(7, 9), (9, 11), (11, 13), (13, 15), (15, 17), (17, 19), (19, 21), (21, 23)]
BURN_IN = 7


def load(rule_fname, fee):
    """[(day, hour, [fA..fF])] rows for one rule x fee table."""
    path = os.path.join(TABLES, f"los_hours_{rule_fname}_{fee}.csv")
    if not os.path.exists(path):
        return None
    out = []
    with open(path) as f:
        for r in csv.DictReader(f):
            out.append((int(float(r["day"])), int(float(r["hour"])),
                        [float(r[f"f{g}"]) for g in GRADES]))
    return out


def shares(rows, hours=None):
    """Flow-weighted LoS shares (%) over converged days, optionally an hour set."""
    tot = [0.0] * 6
    for day, hour, fs in rows:
        if day <= BURN_IN or (hours is not None and hour not in hours):
            continue
        tot = [a + b for a, b in zip(tot, fs)]
    s = sum(tot)
    return [100 * t / s for t in tot] if s > 0 else [0.0] * 6


def daily_shares(rows, day):
    tot = [0.0] * 6
    for d, _, fs in rows:
        if d == day:
            tot = [a + b for a, b in zip(tot, fs)]
    s = sum(tot)
    return [100 * t / s for t in tot] if s > 0 else [0.0] * 6


def stacked_pair(ax, x, sh_nc, sh_tou, width=0.38):
    for dx, sh in ((-width / 2 - 0.02, sh_nc), (width / 2 + 0.02, sh_tou)):
        if sh is None:
            continue
        bottom = 0.0
        for g, v in zip(GRADES, sh):
            ax.bar(x + dx, v, width, bottom=bottom, color=GRADE_COLOR[g],
                   edgecolor="white", lw=0.3)
            bottom += v


def annotate_fees(ax, positions, labels):
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, fontsize=8)


# --- Figure 1: LoS mix by 2-hour band -------------------------------------
have_any = False
fig, axes = plt.subplots(3, 1, figsize=(10.5, 9.5), sharex=True, sharey=True)
for ax, (fname_rule, title) in zip(axes, RULES):
    data = {fee: load(fname_rule, fee) for fee in FEE_ORDER}
    if not any(data.values()):
        ax.set_axis_off(); continue
    have_any = True
    labels = []
    for i, (h1, h2) in enumerate(BANDS):
        hours = set(range(h1, h2))
        stacked_pair(ax, i,
                     shares(data["No-Charge"], hours) if data["No-Charge"] else None,
                     shares(data["tou"], hours) if data["tou"] else None)
        labels.append(f"{h1:02d}–{h2:02d}")
    stacked_pair(ax, len(BANDS),
                 shares(data["No-Charge"]) if data["No-Charge"] else None,
                 shares(data["tou"]) if data["tou"] else None)
    labels.append("all day")
    annotate_fees(ax, range(len(labels)), labels)
    ax.set_ylabel("% of traffic")
    ax.set_ylim(0, 100)
    ax.set_title(f"{title}   (left bar = No charge, right = ToU)", fontsize=10)
    ax.grid(axis="y", alpha=0.25)
if have_any:
    handles = [Patch(facecolor=GRADE_COLOR[g], label=f"LoS {g}") for g in GRADES]
    fig.legend(handles=handles, loc="upper right", ncol=6, frameon=False,
               bbox_to_anchor=(0.99, 1.0))
    axes[-1].set_xlabel("time band (clock hours)")
    fig.suptitle(f"Flow-weighted LoS mix by time of day "
                 f"(days {BURN_IN + 1}+, network-wide)", y=1.02)
    fig.tight_layout()
    out = os.path.join(FIGS, "sensitivity_los_bands.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print("wrote", out)
else:
    print("(skip LoS band figure: no los_hours_*.csv yet — run the los-bands experiment)")
plt.close(fig)

# --- Figure 2: LoS mix by day ----------------------------------------------
have_any = False
fig, axes = plt.subplots(3, 1, figsize=(10.5, 9.5), sharex=True, sharey=True)
for ax, (fname_rule, title) in zip(axes, RULES):
    data = {fee: load(fname_rule, fee) for fee in FEE_ORDER}
    if not any(data.values()):
        ax.set_axis_off(); continue
    have_any = True
    days = sorted({d for rows in data.values() if rows for d, _, _ in rows})
    for i, day in enumerate(days):
        stacked_pair(ax, i,
                     daily_shares(data["No-Charge"], day) if data["No-Charge"] else None,
                     daily_shares(data["tou"], day) if data["tou"] else None)
    annotate_fees(ax, range(len(days)), [str(d) for d in days])
    ax.set_ylabel("% of traffic")
    ax.set_ylim(0, 100)
    ax.set_title(f"{title}   (left bar = No charge, right = ToU)", fontsize=10)
    ax.grid(axis="y", alpha=0.25)
if have_any:
    handles = [Patch(facecolor=GRADE_COLOR[g], label=f"LoS {g}") for g in GRADES]
    fig.legend(handles=handles, loc="upper right", ncol=6, frameon=False,
               bbox_to_anchor=(0.99, 1.0))
    axes[-1].set_xlabel("simulated day")
    fig.suptitle("Flow-weighted LoS mix by day (whole day, network-wide)", y=1.02)
    fig.tight_layout()
    out = os.path.join(FIGS, "sensitivity_los_daily.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print("wrote", out)
else:
    print("(skip daily LoS figure: no los_hours_*.csv yet)")
plt.close(fig)

# --- Figure 3: theoretical BPR speed curve with LoS bands -------------------
# S = sf / (1 + a (v/c)^b), the model's congestion function (a=0.15, b=4),
# drawn over the class-specific HCM LoS thresholds used by los-grade.
A, B = 0.15, 4.0
CLASSES = [("Motorway (80 km/h)", 80, [0.30, 0.48, 0.70, 0.90, 1.0]),
           ("Arterial (50 km/h)", 50, [0.26, 0.43, 0.62, 0.82, 1.0])]
fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharex=True)
for ax, (title, sf, thr) in zip(axes, CLASSES):
    edges = [0.0] + thr + [1.3]
    for g, (t1, t2) in zip(GRADES, zip(edges, edges[1:])):
        ax.axvspan(t1, t2, color=GRADE_COLOR[g], alpha=0.18, lw=0)
        ax.text((t1 + min(t2, 1.28)) / 2, 3, g, ha="center", fontsize=11,
                fontweight="bold")
    vc = [i / 200 for i in range(0, 261)]
    ax.plot(vc, [sf / (1 + A * v ** B) for v in vc], "k--", lw=2)
    ax.set_xlim(0, 1.3)
    ax.set_ylim(0, sf * 1.08)
    ax.set_xlabel("V/C ratio")
    ax.set_title(title, fontsize=10)
axes[0].set_ylabel("speed (km/h)")
fig.suptitle("Model congestion function  S = sf / (1 + 0.15 (v/c)$^4$)  "
             "and LoS bands on the V/C axis", y=1.03)
fig.tight_layout()
out = os.path.join(FIGS, "los_bpr_schematic.png")
fig.savefig(out, dpi=200, bbox_inches="tight")
print("wrote", out)
plt.close(fig)
