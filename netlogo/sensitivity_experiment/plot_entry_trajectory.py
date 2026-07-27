#!/usr/bin/env python3
"""Cordon entry rate by simulated day, per rule, no charge vs ToU.

This is the figure that explains *how* each rule reaches its result. The
exponential-decay rule reads the fee directly, so its entry rate is already
lower on day 1 and then stays flat. Q-learning never sees the fee when it
decides — the fee only enters through the reward it collects afterwards — so
it starts at the no-charge level and slides down day after day as the penalty
accumulates in its Q-values. El Farol tracks congestion rather than price, so
its initial deterrence is learned away and both regimes converge upward.

Reads  output/tables/days_<Rule>_<fee>.csv
Writes output/figures/entry_trajectory.png
"""
import csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

RULES = [("Exp-Decay", "Pay (exponential decay)"),
         ("ElFarol", "Oscillate (El Farol)"),
         ("Q-Learning", "Learn (Q-learning)")]
FEES = [("No-Charge", "No charge", "#9e9e9e"), ("tou", "ToU", "#4878a8")]


def series(rule, fee, field):
    path = os.path.join(TABLES, f"days_{rule}_{fee}.csv")
    if not os.path.exists(path):
        return None, None
    rows = list(csv.DictReader(open(path)))
    return ([int(float(r["day"])) for r in rows],
            [float(r[field]) for r in rows])


fig, axes = plt.subplots(1, 3, figsize=(13, 4.0), sharey=True)
for ax, (rule, title) in zip(axes, RULES):
    for fee, label, colour in FEES:
        days, vals = series(rule, fee, "attendance")
        if not days:
            continue
        ax.plot(days, vals, "o-", ms=4, lw=1.9, color=colour, label=label)
        ax.annotate(f"{vals[-1]:.2f}", (days[-1], vals[-1]), textcoords="offset points",
                    xytext=(6, -2), fontsize=9, color=colour)
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("simulated day")
    ax.set_xlim(0.5, 15.6)
    ax.set_ylim(0, 1.0)
    ax.grid(alpha=0.3)
axes[0].set_ylabel("share of agents entering the cordon")
axes[0].legend(frameon=False, loc="lower left", fontsize=9)
fig.suptitle("Cordon entry rate by day: the charge acts immediately under Pay, "
             "cumulatively under Learn, and is undone under Oscillate", y=1.02)
fig.tight_layout()
out = os.path.join(FIGS, "entry_trajectory.png")
fig.savefig(out, dpi=200, bbox_inches="tight")
print("wrote", out)
