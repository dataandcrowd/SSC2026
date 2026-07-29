#!/usr/bin/env python3
"""Figure: the assumed departure-hour weight profiles.

These two lists ARE the model's time-of-day input — there is no observed
profile behind them, so the figure doubles as the provenance statement.
Values are read straight from `outbound-demand` / `return-demand` in
akl_pricing.nls; keep them in sync if those lists change.

Writes output/figures/demand_profile.png
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

# akl_pricing.nls: to-report outbound-demand / return-demand
OUTBOUND = [1, 1, 1, 1, 1, 3, 8, 20, 30, 16, 7, 5, 5, 5, 5, 6, 9, 8, 5, 3, 2, 1, 1, 1]
RETURN   = [1, 1, 1, 1, 1, 1, 2, 3, 4, 5, 6, 6, 6, 7, 8, 10, 14, 17, 13, 8, 5, 3, 2, 1]

NAVY, BLUE, GREY, AMBER = "#0D2137", "#2E75B6", "#94A3B8", "#F59E0B"

fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.0), sharey=False)
hours = list(range(24))

for ax, weights, title, colour in (
    (axes[0], OUTBOUND, "Outbound departure hour", BLUE),
    (axes[1], RETURN, "Return-home departure hour", NAVY),
):
    total = sum(weights)
    pct = [100 * w / total for w in weights]
    peak = max(range(24), key=lambda h: weights[h])
    bars = ax.bar(hours, pct, color=[colour if h == peak else GREY for h in hours],
                  width=0.78, zorder=3)
    ax.set_title(f"{title}   (weights sum to {total})", fontsize=11.5,
                 fontweight="bold", color=NAVY, pad=9)
    ax.set_xlabel("clock hour", fontsize=9.5, color="#475569")
    ax.set_ylabel("probability an agent departs in this hour (%)",
                  fontsize=9, color="#475569")
    ax.set_xticks(range(0, 24, 2))
    ax.set_xlim(-0.8, 23.8)
    ax.set_ylim(0, max(pct) * 1.24)
    ax.grid(axis="y", color="#E2E8F0", zorder=0)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#CBD5E1")
    ax.tick_params(colors="#475569", labelsize=9)
    # annotate the peak and its neighbour
    ax.annotate(f"{pct[peak]:.1f}%\n(weight {weights[peak]})",
                xy=(peak, pct[peak]), xytext=(peak, pct[peak] * 1.055),
                ha="center", fontsize=9.5, fontweight="bold", color=colour)
    nb = peak - 1 if weights[peak - 1] >= weights[(peak + 1) % 24] else peak + 1
    ax.annotate(f"{pct[nb]:.1f}%", xy=(nb, pct[nb]), xytext=(nb, pct[nb] * 1.07),
                ha="center", fontsize=8.5, color="#475569")

# The slide carries the headline, so the figure keeps only a one-line note.
fig.text(0.008, 0.955,
         "Every agent draws its own hour from these weights, independently, each simulated day "
         "— the minute is then uniform within that hour.",
         fontsize=10, color="#475569", ha="left")
fig.tight_layout(rect=(0, 0, 1, 0.93))
out = os.path.join(FIGS, "demand_profile.png")
fig.savefig(out, dpi=190, facecolor="white")
print("wrote", out)
