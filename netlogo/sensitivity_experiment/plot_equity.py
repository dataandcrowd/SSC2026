#!/usr/bin/env python3
"""Figure + tables for the equity-quintile run (who pays, measured in-run).

The equity-quintile experiment records, for all three decision rules under
No-Charge and ToU (baseline flat outside option, seed 11, 14 days):
  - CBD entry rate by VOT quintile (optin-q 1..5)
  - fee burden in hours of own time for the bottom and top quintile of
    entrants (burden-quintile 1 and 5; q = 2..4 are defective and not
    recorded - see paper_update/decisions_log.md)

Reads  output/tables/equity-quintile.csv     (override dir with SENS_TABLES)
Writes output/figures/equity_quintile_optin.png
       output/tables/equity_quintile_summary.csv
       and prints the settled-window summary.

Mean is taken over days >= BURN_IN+1 so learners are judged on settled
behaviour, matching plot_transit_sensitivity.py.
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

TABLE = os.path.join(TABLES, "equity-quintile.csv")
BURN_IN = 7          # days 8..14 are the settled window
RULE_ORDER = ["Exp-Decay", "El Farol", "Q-Learning"]
RULE_LABEL = {"Exp-Decay": "Pay (Exp-Decay)", "El Farol": "El Farol",
              "Q-Learning": "Q-Learning"}
FEE_ORDER = ["No-Charge", "tou"]
FEE_LABEL = {"No-Charge": "No charge", "tou": "ToU"}
Q_METRICS = [f"optin-q {q}" for q in range(1, 6)]
BURDEN_METRICS = ["burden-quintile 1", "burden-quintile 5"]
EXTRA = ["peak-vc-inner", "mean [fee-paid-today] of vehicles"]


def load(path):
    with open(path) as f:
        rows = list(csv.reader(f))
    hdr_i = next(i for i, r in enumerate(rows) if r and r[0] == "[run number]")
    return rows[hdr_i], [r for r in rows[hdr_i + 1:] if r]


def settled_means(path, metrics):
    """{(rule, fee): {metric: mean over days > BURN_IN}} (last row per day)."""
    hdr, data = load(path)
    cr, cd = hdr.index("[run number]"), hdr.index("current-sim-day")
    cf, cp = hdr.index("fee-regime"), hdr.index("decision-rule")
    cols = {m: hdr.index(m) for m in metrics}
    per_run = defaultdict(dict)       # run -> {day: {metric: value}}
    meta = {}
    for r in data:
        day = int(float(r[cd]))
        if day < 1:
            continue
        per_run[r[cr]][day] = {m: float(r[c]) for m, c in cols.items()}
        meta[r[cr]] = (r[cp].strip('"'), r[cf].strip('"'))
    out = {}
    for run, by_day in per_run.items():
        days = [d for d in sorted(by_day) if d > BURN_IN]
        out[meta[run]] = {m: sum(by_day[d][m] for d in days) / len(days)
                          for m in metrics}
    return out


means = settled_means(TABLE, Q_METRICS + BURDEN_METRICS + EXTRA)
rules = [r for r in RULE_ORDER if any(k[0] == r for k in means)]

# ---------------------------------------------------------------- summary ----
print(f"Settled-window (days {BURN_IN + 1}+) means, equity-quintile (seed 11)")
print(f"{'rule':>12} {'fee':>10} " + " ".join(f"{m:>10}" for m in Q_METRICS)
      + "  burden-Q1  burden-Q5  vc-inner")
for rule in rules:
    for fee in FEE_ORDER:
        m = means[(rule, fee)]
        print(f"{rule:>12} {FEE_LABEL[fee]:>10} "
              + " ".join(f"{m[q]:>10.3f}" for q in Q_METRICS)
              + f"  {m['burden-quintile 1']:>9.3f}"
              + f"  {m['burden-quintile 5']:>9.3f}"
              + f"  {m['peak-vc-inner']:.3f}")

print("\nToU effect on entry (No-Charge minus ToU, percentage points):")
print(f"{'rule':>12} " + " ".join(f"{'Q' + str(q):>8}" for q in range(1, 6)))
for rule in rules:
    diffs = [100 * (means[(rule, 'No-Charge')][m] - means[(rule, 'tou')][m])
             for m in Q_METRICS]
    print(f"{rule:>12} " + " ".join(f"{d:>8.1f}" for d in diffs))

print("\nFee burden under ToU (hours of own time per entry, entrants only):")
for rule in rules:
    m = means[(rule, "tou")]
    print(f"{rule:>12}  Q1 {m['burden-quintile 1']:.3f} h"
          f"   Q5 {m['burden-quintile 5']:.3f} h")

# ------------------------------------------------------------ summary CSV ----
out_csv = os.path.join(TABLES, "equity_quintile_summary.csv")
with open(out_csv, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["decision-rule", "fee-regime"] + Q_METRICS + BURDEN_METRICS
               + ["peak-vc-inner"])
    for rule in rules:
        for fee in FEE_ORDER:
            m = means[(rule, fee)]
            w.writerow([rule, fee] + [f"{m[x]:.4f}" for x in
                                      Q_METRICS + BURDEN_METRICS + ["peak-vc-inner"]])
print("wrote", out_csv)

# ---------------------------------------------------------------- figure -----
# Entry rate by VOT quintile: one panel per rule, No-Charge vs ToU bars.
fig, axes = plt.subplots(1, len(rules), figsize=(4.2 * len(rules), 4.0),
                         sharey=True)
if len(rules) == 1:
    axes = [axes]
x = range(1, 6)
w = 0.36
for ax, rule in zip(axes, rules):
    for j, fee in enumerate(FEE_ORDER):
        vals = [means[(rule, fee)][m] for m in Q_METRICS]
        ax.bar([i + (j - 0.5) * w for i in x], vals, w,
               color=("#9e9e9e" if fee == "No-Charge" else "#4878a8"),
               label=FEE_LABEL[fee])
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"Q{q}" for q in range(1, 6)])
    ax.set_xlabel("VOT quintile (Q1 = poorest)")
    ax.set_title(RULE_LABEL[rule])
    ax.grid(axis="y", alpha=0.25)
axes[0].set_ylabel("CBD entry rate (settled days)")
axes[0].legend(frameon=False)
fig.suptitle("Who is priced off the road (measured in-run, seed 11, "
             "flat outside option)", y=1.02)
fig.tight_layout()
out1 = os.path.join(FIGS, "equity_quintile_optin.png")
fig.savefig(out1, dpi=150, bbox_inches="tight")
print("wrote", out1)
