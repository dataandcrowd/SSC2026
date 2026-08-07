#!/usr/bin/env python3
"""Results-slide remake of fig_akl_behaviour panels (a) and (c), from the
current calibrated tables: 14 days, No-Charge vs ToU only (no flat arm),
numbers therefore agree with the results matrix and daily_peak_gg.

(a) Q-Learning share of agents entering the CBD, day by day — the learning
    trajectory that produces the −37 % entry cut.
(b) Hour-of-day inner-cordon V/C under ToU for the three rules, with the fee
    schedule shown as background bands ($6 dark, $4 light) instead of the
    old dual fee axis.

Writes fig_akl_behaviour_14d.png
"""
import os
import pandas as pd
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")

FEE_GREY, FEE_BLUE = "#9e9e9e", "#2f6fa8"
RULE_COLOUR = {"Pay": "#534AB7", "Oscillate": "#0F6E56", "Learn": "#993C1D"}
RULES = [("Exp-Decay", "Pay"), ("ElFarol", "Oscillate"), ("Q-Learning", "Learn")]
# (start, end, fee) bands of the ToU schedule above the $2 base
FEE_BANDS = [(6.0, 7.5, 4), (7.5, 9.5, 6), (9.5, 15.5, 4), (15.5, 18.5, 6),
             (18.5, 21.0, 4)]

plt.rcParams.update({"font.family": "Helvetica Neue", "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25})

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.2))

# (a) Q-Learning entry share, day by day
nc = pd.read_csv(os.path.join(TABLES, "days_Q-Learning_No-Charge.csv"))
tou = pd.read_csv(os.path.join(TABLES, "days_Q-Learning_tou.csv"))
ax1.plot(nc.day, 100 * nc.attendance, color=FEE_GREY, lw=2, label="No charge")
ax1.plot(tou.day, 100 * tou.attendance, color=FEE_BLUE, lw=2, label="ToU ($2–$6)")
ax1.annotate(f"{100*nc.attendance.iloc[-1]:.0f}%", (14, 100 * nc.attendance.iloc[-1]),
             xytext=(5, 0), textcoords="offset points", color=FEE_GREY, weight="bold")
ax1.annotate(f"{100*tou.attendance.iloc[-1]:.0f}%", (14, 100 * tou.attendance.iloc[-1]),
             xytext=(5, 0), textcoords="offset points", color=FEE_BLUE, weight="bold")
ax1.set_title("(a) Q-Learning: share of agents entering the CBD",
              loc="left", weight="bold")
ax1.set_xlabel("simulated day")
ax1.set_ylabel("agents entering (%)")
ax1.set_xticks([1, 4, 7, 10, 14])
ax1.set_xlim(0.6, 15.4)
ax1.legend(frameon=False, loc="lower left")
ax1.text(0, -0.16, "14-day mean entries: −37 % under ToU",
         transform=ax1.transAxes, fontsize=9.5, color="#555555")

# (b) hour-of-day inner V/C under ToU, three rules, fee bands behind
for lo, hi, fee in FEE_BANDS:
    ax2.axvspan(lo, hi, color="#c04040", alpha=0.20 if fee == 6 else 0.07, lw=0)
for rule, short in RULES:
    h = pd.read_csv(os.path.join(TABLES, f"hourly_{rule}_tou.csv"))
    prof = h.groupby("hour")["vc_inner"].mean()
    ax2.plot(prof.index, prof.values, color=RULE_COLOUR[short], lw=2, label=short)
ax2.set_title("(b) Inner-cordon V/C through the day under ToU",
              loc="left", weight="bold")
ax2.set_xlabel("hour of day")
ax2.set_ylabel("mean inner V/C")
ax2.set_xticks([0, 6, 12, 18, 24])
ax2.set_xlim(0, 23)
ax2.legend(frameon=False, loc="upper left")
ax2.text(0, -0.16, "Shading = ToU fee bands: dark $6 (peaks), light $4 "
                   "(shoulders), unshaded $2.",
         transform=ax2.transAxes, fontsize=9.5, color="#555555")

fig.suptitle("Behavioural response to time-of-use charging "
             "(calibrated Auckland CBD model, 14 days, one seed)",
             weight="bold", y=1.0)
fig.tight_layout(rect=(0, 0.02, 1, 0.97))
out = os.path.join(FIGS, "fig_akl_behaviour_14d.png")
fig.savefig(out, dpi=280, bbox_inches="tight")
print("wrote", out)
