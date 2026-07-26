#!/usr/bin/env python3
"""Hour-of-day inner-cordon V/C profile, No-Charge vs ToU, one panel per rule.

The daily-peak time series hides the within-day pattern where ToU actually
acts (AM-peak shaving, departure-time shifting). This reads the day x hour
tables written by `save-hourly` (BehaviorSpace experiment `hourly-profile`,
calibrated model) and draws the mean hourly profile with a min-max band,
with the ToU fee windows shaded behind.

Reads  output/tables/hourly_<Rule>_{No-Charge,tou}.csv
Writes output/figures/sensitivity_hourly_profile.png

Mean is taken over days >= BURN_IN+1 so the learning rules (Q-Learning) are
shown in their converged regime; the band is the min-max across those days.
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

FEE_ORDER = ["No-Charge", "tou"]
FEE_LABEL = {"No-Charge": "No charge", "tou": "ToU"}
FEE_COLOR = {"No-Charge": "#9e9e9e", "tou": "#4878a8"}
RULES = [("Exp-Decay", "Exp-Decay"), ("ElFarol", "El Farol"), ("Q-Learning", "Q-Learning")]
BURN_IN = 7  # days 8+ = converged regime for the learning rules

# ToU fee schedule breakpoints (mirror of get-tou-fee in akl_pricing.nls)
TOU_PTS = [(0.0, 2.0), (5.5, 2.0), (6.0, 4.0), (7.5, 4.0), (8.0, 6.0),
           (9.0, 6.0), (9.5, 4.0), (15.5, 4.0), (16.0, 6.0), (18.0, 6.0),
           (18.5, 4.0), (20.5, 4.0), (21.0, 2.0), (24.0, 2.0)]


def tou_fee(t):
    for (t1, f1), (t2, f2) in zip(TOU_PTS, TOU_PTS[1:]):
        if t1 <= t <= t2:
            return f1 if t2 == t1 else f1 + (f2 - f1) * (t - t1) / (t2 - t1)
    return 2.0


def shade_fee_windows(ax):
    """Shade $6 peak windows dark and $4 shoulder light, from the schedule."""
    step = 0.05
    t = 0.0
    while t < 24:
        fee = tou_fee(t + step / 2)
        if fee >= 6:
            ax.axvspan(t, t + step, color="#c04040", alpha=0.10, lw=0)
        elif fee >= 4:
            ax.axvspan(t, t + step, color="#d1893a", alpha=0.06, lw=0)
        t += step


def hourly(path):
    """{fee: {hour: [vc per day (days > BURN_IN)]}} from one save-hourly CSV."""
    out = defaultdict(lambda: defaultdict(list))
    with open(path) as f:
        for row in csv.DictReader(f):
            day = int(float(row["day"]))
            if day <= BURN_IN:
                continue
            out[row["regime"]][int(float(row["hour"]))].append(float(row["vc_inner"]))
    return out


fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)
ndays = None
for ax, (fname_rule, title) in zip(axes, RULES):
    shade_fee_windows(ax)
    for fee in FEE_ORDER:
        path = os.path.join(TABLES, f"hourly_{fname_rule}_{fee}.csv")
        if not os.path.exists(path):
            continue
        by_hour = hourly(path).get(fee, {})
        hours = sorted(by_hour)
        if not hours:
            continue
        mean = [sum(by_hour[h]) / len(by_hour[h]) for h in hours]
        lo = [min(by_hour[h]) for h in hours]
        hi = [max(by_hour[h]) for h in hours]
        ax.plot(hours, mean, "o-", ms=3.5, lw=1.8, color=FEE_COLOR[fee],
                label=FEE_LABEL[fee])
        ax.fill_between(hours, lo, hi, color=FEE_COLOR[fee], alpha=0.18, lw=0)
        ndays = len(by_hour[hours[0]])
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("hour of day")
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlim(0, 24)
    ax.grid(alpha=0.3)
axes[0].set_ylabel("mean inner-cordon V/C")
handles, labels = axes[0].get_legend_handles_labels()
from matplotlib.patches import Patch
handles += [Patch(facecolor="#c04040", alpha=0.18, label="ToU $6 peak"),
            Patch(facecolor="#d1893a", alpha=0.15, label="ToU $4 shoulder")]
fig.legend(handles=handles, loc="upper right", ncol=4, frameon=False,
           bbox_to_anchor=(0.99, 1.0))
fig.suptitle(f"Hour-of-day inner-cordon V/C at each rule's baseline "
             f"(mean of days {BURN_IN + 1}+, band = min-max)", y=1.06)
fig.tight_layout()
out = os.path.join(FIGS, "sensitivity_hourly_profile.png")
fig.savefig(out, dpi=200, bbox_inches="tight")
print("wrote", out)
