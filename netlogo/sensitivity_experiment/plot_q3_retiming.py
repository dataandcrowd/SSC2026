#!/usr/bin/env python3
"""Q3, retiming only: who shifts, what they pay, and whether the V/C gain holds.

Three questions, one panel each, computed live from the current tables
(retiming BehaviorSpace export + days_* daily records, steady-state days 8-14
for shifter counts, 14-day means elsewhere).

(a) Share of entrants who move their departure hour, no charge vs ToU.
(b) Mean daily fee outlay per agent under ToU, fixed hour vs may-retime.
(c) ToU reduction in daily-peak inner V/C, fixed hour vs may-retime.

Writes q3_retiming.png
"""
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")

GREY, BLUE = "#9e9e9e", "#2f6fa8"
RULES = [("Exp-Decay", "Exp-Decay", "Pay"), ("El Farol", "ElFarol", "Oscillate"),
         ("Q-Learning", "Q-Learning", "Learn")]

# shifter shares from the retiming BehaviorSpace table, steady state
raw = pd.read_csv(os.path.join(TABLES, "retiming.csv"), skiprows=6)
raw.columns = [c.strip('"') for c in raw.columns]
raw = raw[(raw["allow-retiming?"] == True) & (raw["current-sim-day"] >= 8)]
share = {}
for (rule, fee), g in raw.groupby(["decision-rule", "fee-regime"]):
    ent = g["count vehicles with [enters-cbd? = true]"].mean()
    mov = g["count vehicles with [hour-shift != 0]"].mean()
    share[(rule, fee)] = 100 * mov / max(ent, 1)

# fee outlay and inner-peak reductions from the daily records
fee, red = {}, {}
for bs, fname, short in RULES:
    for arm, alab in [("", "fixed"), ("_rt", "retime")]:
        nc = pd.read_csv(os.path.join(TABLES, f"days_{fname}_No-Charge{arm}.csv"))
        tou = pd.read_csv(os.path.join(TABLES, f"days_{fname}_tou{arm}.csv"))
        fee[(short, alab)] = tou.mean_fee.mean()
        red[(short, alab)] = 100 * (1 - tou.vc_inner.mean() / nc.vc_inner.mean())

plt.rcParams.update({"font.family": "Helvetica Neue", "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "axes.grid.axis": "y", "grid.alpha": 0.25})
fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 4.8))
x = np.arange(3)
labels = [s for _, _, s in RULES]

# (a) who retimes
w = 0.36
nc_v = [share[(r, "No-Charge")] for r, _, _ in RULES]
tou_v = [share[(r, "tou")] for r, _, _ in RULES]
ax1.bar(x - w / 2, nc_v, w, color=GREY, label="No charge")
ax1.bar(x + w / 2, tou_v, w, color=BLUE, label="ToU")
for xi, v in zip(x - w / 2, nc_v):
    ax1.text(xi, v + 1.2, f"{v:.0f}%", ha="center", fontsize=9.5, color="#555555")
for xi, v in zip(x + w / 2, tou_v):
    ax1.text(xi, v + 1.2, f"{v:.0f}%", ha="center", fontsize=9.5, color=BLUE,
             weight="bold")
ax1.set_title("(a) Who retimes?", loc="left", weight="bold")
ax1.set_ylabel("entrants shifting departure (%)")
ax1.set_xticks(x, labels)
ax1.legend(frameon=False, loc="upper left")
ax1.text(0, -0.2, "Pay: 3 % move, 9 in 10 to before the $6 window.\n"
                  "Oscillate shifts identically with no fee at all.",
         transform=ax1.transAxes, fontsize=9.5, color="#555555")

# (b) fee outlay under ToU
f_fix = [fee[(s, "fixed")] for s in labels]
f_rt = [fee[(s, "retime")] for s in labels]
ax2.bar(x - w / 2, f_fix, w, color=GREY, label="fixed hour")
ax2.bar(x + w / 2, f_rt, w, color=BLUE, label="may retime")
for xi, v in zip(x - w / 2, f_fix):
    ax2.text(xi, v + 0.05, f"${v:.2f}", ha="center", fontsize=9.5, color="#555555")
for xi, v in zip(x + w / 2, f_rt):
    ax2.text(xi, v + 0.05, f"${v:.2f}", ha="center", fontsize=9.5, color=BLUE,
             weight="bold")
ax2.set_title("(b) Fee outlay per agent per day (ToU)", loc="left", weight="bold")
ax2.set_ylabel("mean fee paid (NZ$)")
ax2.set_xticks(x, labels)
ax2.legend(frameon=False, loc="upper left")
ax2.text(0, -0.2, "Pay's shifters each save $2 ($6 to $4) but are too few to "
                  "move the mean.\nLearn re-enters once it can retime: outlay "
                  "+82 %.", transform=ax2.transAxes, fontsize=9.5, color="#555555")

# (c) does the V/C gain hold
for i, s in enumerate(labels):
    a, b = red[(s, "fixed")], red[(s, "retime")]
    ax3.plot([a, b], [i, i], color="#c9c7bd", lw=2, zorder=1)
    ax3.scatter([a], [i], s=70, color=GREY, zorder=2)
    ax3.scatter([b], [i], s=70, color=BLUE, zorder=2)
    ax3.annotate(f"−{a:.0f}%", (a, i), xytext=(0, 9), ha="center",
                 textcoords="offset points", fontsize=9.5, color="#555555")
    ax3.annotate(f"−{b:.0f}%" if b > 0.5 else "0%", (b, i), xytext=(0, -17),
                 ha="center", textcoords="offset points", fontsize=9.5,
                 color=BLUE, weight="bold")
ax3.axvline(0, color="#9a988f", lw=0.8)
ax3.set_title("(c) Does the V/C gain hold?", loc="left", weight="bold")
ax3.set_xlabel("ToU reduction in daily-peak inner V/C (%)")
ax3.set_yticks(range(3), labels)
ax3.set_xlim(-2, 30)
ax3.invert_yaxis()
ax3.grid(axis="x", alpha=0.25)
ax3.grid(axis="y", visible=False)
ax3.scatter([], [], s=70, color=GREY, label="fixed hour")
ax3.scatter([], [], s=70, color=BLUE, label="may retime")
ax3.set_ylim(2.45, -0.55)
ax3.legend(frameon=False, loc="center right", bbox_to_anchor=(1.0, 0.42))
ax3.text(0, -0.2, "Pay's gain strengthens (19 to 24 %); Learn's collapses (24 to 10 %).",
         transform=ax3.transAxes, fontsize=9.5, color="#555555")

fig.suptitle("Retiming: a small, cheap shift for price-takers — an escape route "
             "for the learner (calibrated model, 14 days, ToU)",
             weight="bold", y=1.02)
fig.tight_layout(rect=(0, 0.04, 1, 0.98))
out = os.path.join(FIGS, "q3_retiming.png")
fig.savefig(out, dpi=280, bbox_inches="tight")
print("wrote", out)
