#!/usr/bin/env python3
"""Figures + summary for the outside-option (transit access) sensitivity run.

The sensitivity-transit experiment varies `transit-penalty`, the dollar cost of
NOT driving for boundary-sector homes (local homes pay half; 0 = the original
spatially-flat outside option), under No-Charge and ToU with the Q-Learning
rule. Unlike the old equity figure (derived analytically from the reward
function), the entry rate by VOT quintile is MEASURED in-run here.

Reads  output/tables/sensitivity-transit.csv   (override dir with SENS_TABLES)
Writes output/figures/sensitivity_transit_optin.png
       output/figures/sensitivity_transit_tier.png
       and prints a summary table.

Mean is taken over days >= BURN_IN+1 so the learner is judged on settled
behaviour, matching plot_hourly_profile.py.
"""
import csv, os
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

TABLE = os.path.join(TABLES, "sensitivity-transit.csv")
BURN_IN = 7          # days 8..14 are the settled window
PVAR = "transit-penalty"
FEE_ORDER = ["No-Charge", "tou"]
FEE_LABEL = {"No-Charge": "No charge", "tou": "ToU"}
Q_METRICS = [f"optin-q {q}" for q in range(1, 6)]
TIER_METRICS = ["optin-tier 1", "optin-tier 2"]
TIER_LABEL = {"optin-tier 1": "local (urban) homes", "optin-tier 2": "boundary (outer) homes"}


def load(path):
    with open(path) as f:
        rows = list(csv.reader(f))
    hdr_i = next(i for i, r in enumerate(rows) if r and r[0] == "[run number]")
    return rows[hdr_i], [r for r in rows[hdr_i + 1:] if r]


def settled_means(path, metrics):
    """{(penalty, fee): {metric: mean over days > BURN_IN}} (last row per day)."""
    hdr, data = load(path)
    cr, cd = hdr.index("[run number]"), hdr.index("current-sim-day")
    cf, cp = hdr.index("fee-regime"), hdr.index(PVAR)
    cols = {m: hdr.index(m) for m in metrics}
    per_run = defaultdict(dict)       # run -> {day: {metric: value}}
    meta = {}
    for r in data:
        day = int(float(r[cd]))
        if day < 1:
            continue
        per_run[r[cr]][day] = {m: float(r[c]) for m, c in cols.items()}
        meta[r[cr]] = (float(r[cp].strip('"')), r[cf].strip('"'))
    out = {}
    for run, by_day in per_run.items():
        days = [d for d in sorted(by_day) if d > BURN_IN]
        out[meta[run]] = {m: sum(by_day[d][m] for d in days) / len(days)
                          for m in metrics}
    return out


means = settled_means(TABLE, Q_METRICS + TIER_METRICS + ["peak-vc-inner"])
penalties = sorted({k[0] for k in means})

# ---------------------------------------------------------------- summary ----
print(f"Settled-window (days {BURN_IN + 1}+) means, sensitivity-transit")
print(f"{'penalty':>8} {'fee':>10} " + " ".join(f"{m:>10}" for m in Q_METRICS)
      + "  vc-inner")
for p in penalties:
    for fee in FEE_ORDER:
        m = means[(p, fee)]
        print(f"{p:>8} {FEE_LABEL[fee]:>10} "
              + " ".join(f"{m[q]:>10.3f}" for q in Q_METRICS)
              + f"  {m['peak-vc-inner']:.3f}")
print("\nToU effect on entry (No-Charge minus ToU, percentage points):")
print(f"{'penalty':>8} " + " ".join(f"{'Q' + str(q):>8}" for q in range(1, 6)))
for p in penalties:
    diffs = [100 * (means[(p, 'No-Charge')][m] - means[(p, 'tou')][m])
             for m in Q_METRICS]
    print(f"{p:>8} " + " ".join(f"{d:>8.1f}" for d in diffs))

# ------------------------------------------------------------- figure 1 ------
# Entry rate by VOT quintile: one panel per penalty, No-Charge vs ToU bars.
fig, axes = plt.subplots(1, len(penalties), figsize=(4.2 * len(penalties), 4.0),
                         sharey=True)
x = range(1, 6)
w = 0.36
for ax, p in zip(axes, penalties):
    for j, fee in enumerate(FEE_ORDER):
        vals = [means[(p, fee)][m] for m in Q_METRICS]
        ax.bar([i + (j - 0.5) * w for i in x], vals, w,
               color=("#9e9e9e" if fee == "No-Charge" else "#4878a8"),
               label=FEE_LABEL[fee])
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"Q{q}" for q in range(1, 6)])
    ax.set_xlabel("VOT quintile (Q1 = poorest)")
    ax.set_title(("flat outside option\n(original spec)" if p == 0
                  else f"transit penalty ${p:g}\n(boundary homes)"))
    ax.grid(axis="y", alpha=0.25)
axes[0].set_ylabel("CBD entry rate (settled days)")
axes[0].legend(frameon=False)
fig.suptitle("Who is priced off the road depends on the outside option "
             "(Q-Learning, measured in-run)", y=1.02)
fig.tight_layout()
out1 = os.path.join(FIGS, "sensitivity_transit_optin.png")
fig.savefig(out1, dpi=150, bbox_inches="tight")
print("wrote", out1)

# ------------------------------------------------------------- figure 2 ------
# Entry rate by home tier across the penalty sweep, ToU only.
fig2, ax2 = plt.subplots(figsize=(6.4, 4.0))
for m, color in zip(TIER_METRICS, ["#4878a8", "#c0504d"]):
    for fee, ls in [("No-Charge", "--"), ("tou", "-")]:
        ax2.plot(penalties, [means[(p, fee)][m] for p in penalties],
                 ls, color=color, marker="o",
                 label=f"{TIER_LABEL[m]}, {FEE_LABEL[fee]}")
ax2.set_xlabel("transit-penalty ($, boundary homes; local homes pay half)")
ax2.set_ylabel("CBD entry rate (settled days)")
ax2.set_xticks(penalties)
ax2.grid(alpha=0.25)
ax2.legend(frameon=False, fontsize=8)
ax2.set_title("Entry by home location as the outside option worsens")
fig2.tight_layout()
out2 = os.path.join(FIGS, "sensitivity_transit_tier.png")
fig2.savefig(out2, dpi=150, bbox_inches="tight")
print("wrote", out2)
