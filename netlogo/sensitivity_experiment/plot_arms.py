#!/usr/bin/env python3
"""What the agents are allowed to do, against what the charge is found to do.

Four arms of the same calibrated model, same seed, same fee schedule:

  base     departure hour fixed by the demand profile, fixed shortest paths
  retime   departure may move one clock hour either way
  reroute  routes recomputed on congested travel times, per time band
  both     both extensions at once

Left panel: the ToU reduction in daily peak V/C, by rule and arm — the headline
the paper would quote, shown to depend on the action space as much as on the
decision rule. Right panel: the no-charge levels, which show that the routing
assumption alone moves congestion off the cordon boundary and into the interior
before any charge is applied.

Reads  output/tables/days_<Rule>_<fee>{,_rt,_rr,_rt_rr}.csv
Writes output/figures/arms_comparison.png
"""
import csv, os, statistics as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

RULES = [("Exp-Decay", "Pay"), ("ElFarol", "Oscillate"), ("Q-Learning", "Learn")]
ARMS = [("", "fixed hour, fixed route", "#9e9e9e"),
        ("_rt", "may retime", "#4878a8"),
        ("_rr", "may reroute", "#c07a3a"),
        ("_rt_rr", "both", "#4a8f5a")]


def days(rule, fee, tag):
    path = os.path.join(TABLES, f"days_{rule}_{fee}{tag}.csv")
    if not os.path.exists(path):
        return None
    return list(csv.DictReader(open(path)))


def mean(rows, field):
    return st.mean(float(r[field]) for r in rows)


fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
w = 0.2
x = range(len(RULES))

# --- left: ToU reduction in peak inner V/C, by arm ------------------------
for k, (tag, label, colour) in enumerate(ARMS):
    vals = []
    for rule, _ in RULES:
        nc, tou = days(rule, "No-Charge", tag), days(rule, "tou", tag)
        vals.append(100 * (mean(nc, "vc_inner") - mean(tou, "vc_inner")) / mean(nc, "vc_inner")
                    if nc and tou else 0)
    off = (k - 1.5) * w
    axes[0].bar([i + off for i in x], vals, w, color=colour, label=label)
    for i, v in zip(x, vals):
        axes[0].text(i + off, v + 0.5, f"{v:.0f}", ha="center", fontsize=8)
axes[0].set_title("ToU reduction in daily peak inner-cordon V/C (%)", fontsize=10)
axes[0].set_ylabel("% reduction")
axes[0].axhline(0, color="black", lw=0.8)
axes[0].legend(frameon=False, fontsize=8.5, ncol=2)

# --- right: where congestion sits with no charge at all -------------------
for k, (tag, label, colour) in enumerate(ARMS):
    vals = []
    for rule, _ in RULES:
        nc = days(rule, "No-Charge", tag)
        vals.append(mean(nc, "vc_boundary") if nc else 0)
    off = (k - 1.5) * w
    axes[1].bar([i + off for i in x], vals, w, color=colour, label=label)
    for i, v in zip(x, vals):
        axes[1].text(i + off, v + 0.01, f"{v:.2f}", ha="center", fontsize=8)
axes[1].set_title("No-charge peak V/C on the cordon boundary", fontsize=10)
axes[1].set_ylabel("peak V/C")

for ax in axes:
    ax.set_xticks(list(x))
    ax.set_xticklabels([t for _, t in RULES])
    ax.grid(axis="y", alpha=0.25)

fig.suptitle("The action space moves the answer as much as the decision rule does: "
             "ToU effect by arm (left), and where routing alone puts the load (right)",
             y=1.02)
fig.tight_layout()
out = os.path.join(FIGS, "arms_comparison.png")
fig.savefig(out, dpi=200, bbox_inches="tight")
print("wrote", out)
