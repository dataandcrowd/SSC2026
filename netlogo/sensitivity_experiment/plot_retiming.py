#!/usr/bin/env python3
"""What changes when agents may move their departure by an hour.

Two arms of the same model, run together (experiment `retiming`): agents either
keep the departure hour drawn from the demand profile, or may move it one clock
hour either way, trading the fee saved against a schedule-delay cost of
sched-delay-cost x VoT per hour (1.6x for arriving late).

Panels are one per decision rule, showing the hour-of-day inner-cordon V/C for
no charge and ToU in both arms. The question the figure answers is whether the
charge spreads the peak (retiming arm dips at the charged hours and rises at
the shoulders) or merely suppresses trips (both arms fall together).

Reads  output/tables/hourly_<Rule>_<fee>{,_rt}.csv
Writes output/figures/retiming_profiles.png
       output/figures/retiming_summary.png
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

RULES = [("Exp-Decay", "Pay (exponential decay)"),
         ("ElFarol", "Oscillate (El Farol)"),
         ("Q-Learning", "Learn (Q-learning)")]
SERIES = [("No-Charge", "", "#b0b0b0", "--", "No charge, fixed hour"),
          ("tou", "", "#c26a3a", "--", "ToU, fixed hour"),
          ("No-Charge", "_rt", "#6b6b6b", "-", "No charge, may retime"),
          ("tou", "_rt", "#2f6fa8", "-", "ToU, may retime")]
BURN_IN = 7
TOU_PEAK = [(8, 9), (16, 18)]


def profile(rule, fee, tag):
    path = os.path.join(TABLES, f"hourly_{rule}_{fee}{tag}.csv")
    if not os.path.exists(path):
        return None, None
    by_hour = defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            if int(float(r["day"])) <= BURN_IN:
                continue
            by_hour[int(float(r["hour"]))].append(float(r["vc_inner"]))
    hours = sorted(by_hour)
    return hours, [sum(by_hour[h]) / len(by_hour[h]) for h in hours]


def daily(rule, fee, tag, field):
    path = os.path.join(TABLES, f"days_{rule}_{fee}{tag}.csv")
    if not os.path.exists(path):
        return None
    rows = list(csv.DictReader(open(path)))
    return sum(float(r[field]) for r in rows) / len(rows)


# --- Figure 1: hour-of-day profiles, both arms ----------------------------
fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.3), sharey=True)
for ax, (rule, title) in zip(axes, RULES):
    for h1, h2 in TOU_PEAK:
        ax.axvspan(h1, h2, color="#c04040", alpha=0.08, lw=0)
    for fee, tag, colour, style, label in SERIES:
        hours, vals = profile(rule, fee, tag)
        if not hours:
            continue
        ax.plot(hours, vals, style, color=colour, lw=1.8, label=label)
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("hour of day")
    ax.set_xticks(range(0, 25, 3))
    ax.set_xlim(0, 24)
    ax.grid(alpha=0.3)
axes[0].set_ylabel("mean inner-cordon V/C")
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc="upper right", ncol=4, frameon=False,
           bbox_to_anchor=(0.99, 1.0), fontsize=9)
fig.suptitle("Departure-time choice: hour-of-day inner-cordon V/C with the "
             "departure hour fixed (dashed) and free to move by an hour (solid). "
             "Shaded = $6 peak windows.", y=1.07, fontsize=11)
fig.tight_layout()
out = os.path.join(FIGS, "retiming_profiles.png")
fig.savefig(out, dpi=200, bbox_inches="tight")
print("wrote", out)
plt.close(fig)

# --- Figure 2: what the extension does to the headline --------------------
fig, axes = plt.subplots(1, 2, figsize=(11, 4.0))
x = range(len(RULES))
w = 0.36
for arm, tag, colour, label in [(0, "", "#b0b0b0", "departure hour fixed"),
                                (1, "_rt", "#2f6fa8", "may retime by 1 h")]:
    reds, entries = [], []
    for rule, _ in RULES:
        nc = daily(rule, "No-Charge", tag, "vc_inner")
        tou = daily(rule, "tou", tag, "vc_inner")
        reds.append(100 * (nc - tou) / nc if nc else 0)
        e_nc = daily(rule, "No-Charge", tag, "attendance")
        e_tou = daily(rule, "tou", tag, "attendance")
        entries.append(100 * (e_nc - e_tou) / e_nc if e_nc else 0)
    off = (arm - 0.5) * w
    axes[0].bar([i + off for i in x], reds, w, color=colour, label=label)
    axes[1].bar([i + off for i in x], entries, w, color=colour, label=label)
    for i, v in zip(x, reds):
        axes[0].text(i + off, v + 0.6, f"{v:.1f}", ha="center", fontsize=8)
    for i, v in zip(x, entries):
        axes[1].text(i + off, v + 0.6, f"{v:.1f}", ha="center", fontsize=8)
for ax, title in zip(axes, ["ToU reduction in daily peak inner V/C (%)",
                            "ToU reduction in cordon entries (%)"]):
    ax.set_xticks(list(x))
    ax.set_xticklabels([t.split(" (")[0] for _, t in RULES])
    ax.set_title(title, fontsize=10)
    ax.grid(axis="y", alpha=0.25)
    ax.axhline(0, color="black", lw=0.8)
axes[0].legend(frameon=False, fontsize=9)
fig.suptitle("Giving agents a departure-time choice changes what the charge does: "
             "the price rule gains, the learner stops forgoing trips", y=1.03)
fig.tight_layout()
out = os.path.join(FIGS, "retiming_summary.png")
fig.savefig(out, dpi=200, bbox_inches="tight")
print("wrote", out)
