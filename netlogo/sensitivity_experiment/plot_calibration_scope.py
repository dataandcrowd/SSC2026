#!/usr/bin/env python3
"""Figure: what the calibration actually fitted, and what it left assumed.

Left  — total volume: flow-weighted modelled/observed ratio at each step.
Right — spatial distribution: per-group ratio before and after the suburban
        destinations were added.
Both converge on the 1.0 target line; the two assumed inputs are named in the
strip beneath so the scope of the fit is visible in one look.

Numbers from output/tables/calibration_summary.txt (see numbers.md).

Writes output/figures/calibration_scope.png
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

NAVY, INK, GOOD, WARN = "#0D2137", "#475569", "#2E75B6", "#B45309"

STEPS = [("scale factor 300\nCBD-only destinations", 1.543),
         ("scale factor 195\n+ suburban destinations", 1.225),
         ("scale factor 160\nfinal", 1.013)]
GROUPS = [("CBD", 1.80, 1.12), ("East", 1.30, 1.20),
          ("West", 0.76, 1.04), ("Motorway", 0.75, 0.82)]

fig, (axL, axR) = plt.subplots(1, 2, figsize=(12.4, 4.15),
                               gridspec_kw={"width_ratios": [1, 1.08]})

# ---- left: total volume converging on the target -------------------------
xs = range(len(STEPS))
vals = [v for _, v in STEPS]
axL.axhline(1.0, color="#94A3B8", lw=1.3, ls="--", zorder=1)
axL.plot(xs, vals, "-o", color=GOOD, lw=2.4, markersize=11, zorder=3)
for x, (lab, v) in zip(xs, STEPS):
    axL.annotate(f"{v:.3f}", (x, v), textcoords="offset points",
                 xytext=(0, 14), ha="center", fontsize=11, fontweight="bold",
                 color=GOOD if x == len(STEPS) - 1 else INK)
axL.set_xticks(list(xs))
axL.set_xticklabels([lab for lab, _ in STEPS], fontsize=8.8, color=INK)
axL.set_ylim(0.92, 1.68)
axL.set_ylabel("modelled ÷ observed daily volume", fontsize=9.5, color=INK)
axL.set_title("FITTED ①  Total volume, all 1,634 links",
              fontsize=11.5, fontweight="bold", color=NAVY, pad=10, loc="left")
axL.text(len(STEPS) - 1, 1.0, "  perfect match", va="bottom", ha="right",
         fontsize=8.5, color="#94A3B8")

# ---- right: per-group ratios, before vs after ---------------------------
axR.axvline(1.0, color="#94A3B8", lw=1.3, ls="--", zorder=1)
ys = range(len(GROUPS))
for y, (g, before, after) in zip(ys, GROUPS):
    axR.plot([before, after], [y, y], color="#CBD5E1", lw=3.4, zorder=2,
             solid_capstyle="round")
    axR.plot(before, y, "o", color="#CBD5E1", markersize=11,
             markeredgecolor="#94A3B8", zorder=3)
    axR.plot(after, y, "o", color=GOOD, markersize=11, zorder=4)
    axR.annotate(f"{before:.2f}", (before, y), textcoords="offset points",
                 xytext=(0, 13), ha="center", fontsize=8.6, color=INK)
    axR.annotate(f"{after:.2f}", (after, y), textcoords="offset points",
                 xytext=(0, -21), ha="center", fontsize=9.2,
                 fontweight="bold", color=GOOD)
axR.set_yticks(list(ys))
axR.set_yticklabels([g for g, _, _ in GROUPS], fontsize=10, color=INK)
axR.set_ylim(-0.65, len(GROUPS) - 0.35)
axR.set_xlim(0.55, 2.0)
axR.set_xlabel("modelled ÷ observed daily volume", fontsize=9.5, color=INK)
axR.set_title("FITTED ②  Spatial distribution, by group",
              fontsize=11.5, fontweight="bold", color=NAVY, pad=10, loc="left")
axR.plot([], [], "o", color="#CBD5E1", markeredgecolor="#94A3B8",
         label="before (CBD-only destinations)")
axR.plot([], [], "o", color=GOOD, label="after (+1,400 suburban destinations)")
axR.legend(fontsize=8.6, frameon=False, ncol=2,
           loc="lower center", bbox_to_anchor=(0.5, -0.32))

for ax in (axL, axR):
    ax.grid(axis="both", color="#EEF2F6", zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#CBD5E1")
    ax.tick_params(colors=INK, labelsize=9)

fig.text(0.5, 0.015,
         "NOT FITTED:  the origin–destination matrix (destinations drawn uniformly)   ·   "
         "the time-of-day profile (fixed weight lists)",
         ha="center", fontsize=10, fontweight="bold", color=WARN)

fig.tight_layout(rect=(0, 0.06, 1, 1))
out = os.path.join(FIGS, "calibration_scope.png")
fig.savefig(out, dpi=190, facecolor="white")
print("wrote", out)
