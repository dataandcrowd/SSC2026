#!/usr/bin/env python3
"""Figure: three real agents and what the same charge does to each of them.

Attributes are measured at setup on seed 11 (agent_examples.xml): the agents
with the lowest, median and highest value of time out of the 2,500. Entry
probabilities are the model's own price rule evaluated at each fee step:

    p = clip(base-trip-rate * exp(-beta * fee / vot), 0.05, 0.95)

Because `beta` is itself set inversely to VoT, the exponent behaves like
fee / vot^2 — halving income roughly quadruples the deterrent. That is the
mechanism behind the equity result, shown here on individuals rather than
on aggregated quintiles.

Writes output/figures/agent_personas.png
"""
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyBboxPatch, Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

NAVY, INK, MUTED = "#0D2137", "#334155", "#64748B"
FEES = [0, 2, 4, 6]

# name, vot, beta, base-trip-rate, essential-trip-prob, depart hour, colour, tint
PERSONAS = [
    ("Lowest value of time", 1.34, 2.00, 0.4194, 0.15, 21, "#C0504D", "#FBE9E8"),
    ("Median value of time", 9.67, 0.4999, 0.5349, 0.08, 9, "#2E75B6", "#E8F1FA"),
    ("Highest value of time", 68.79, 0.10, 0.3943, 0.05, 17, "#3F7D58", "#E8F3ED"),
]


def entry_probs(vot, beta, btr):
    return [min(0.95, max(0.05, btr * math.exp(-beta * f / vot))) for f in FEES]


def axes_aspect(ax, fig):
    """Width/height of the axes box in inches. The card axes span 0-1 in both
    directions but are far wider than tall, so any circle drawn in data units
    comes out as an ellipse unless x-radii are divided by this."""
    bb = ax.get_position()
    w_in, h_in = fig.get_size_inches()
    return (bb.width * w_in) / (bb.height * h_in)


def car(ax, cx, cy, h, asp, colour):
    """A small side-on car, drawn from primitives so the figure needs no assets.
    `h` is the height in data units; widths are divided by `asp` to stay round."""
    w = h * 2.05 / asp                      # visual width, aspect-corrected
    ax.add_patch(FancyBboxPatch((cx - w * 0.46, cy - h * 0.16), w * 0.92, h * 0.34,
                                boxstyle="round,pad=0,rounding_size=" + str(h * 0.12),
                                facecolor=colour, edgecolor="none", zorder=4))
    ax.add_patch(Polygon([[cx - w * 0.27, cy + h * 0.16],
                          [cx - w * 0.15, cy + h * 0.46],
                          [cx + w * 0.14, cy + h * 0.46],
                          [cx + w * 0.27, cy + h * 0.16]],
                         closed=True, facecolor=colour, edgecolor="none", zorder=4))
    for dx in (-w * 0.25, w * 0.25):        # wheels: ellipse in data = circle on page
        ax.add_patch(Ellipse((cx + dx, cy - h * 0.20), 2 * h * 0.15 / asp, 2 * h * 0.15,
                             facecolor="white", edgecolor=colour,
                             linewidth=1.6, zorder=5))


fig = plt.figure(figsize=(12.4, 4.95))
gs = fig.add_gridspec(2, 3, height_ratios=[1.12, 1.15], hspace=0.30, wspace=0.22,
                      left=0.055, right=0.975, top=0.90, bottom=0.10)

for col, (name, vot, beta, btr, ess, dep, colour, tint) in enumerate(PERSONAS):
    probs = entry_probs(vot, beta, btr)
    cut = (probs[-1] - probs[0]) / probs[0] * 100

    # ---- card header: icon, the headline number, the two attributes ----
    ax = fig.add_subplot(gs[0, col])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.01, 0.02), 0.98, 0.96,
                                boxstyle="round,pad=0,rounding_size=0.05",
                                facecolor=tint, edgecolor="none", zorder=1))
    asp = axes_aspect(ax, fig)
    ax.add_patch(Ellipse((0.115, 0.71), 2 * 0.145 / asp, 2 * 0.145,
                         facecolor="white", edgecolor=colour, linewidth=2.0, zorder=3))
    car(ax, 0.115, 0.705, 0.145, asp, colour)

    # One statement per line — the card is narrow, so nothing shares a baseline.
    ax.text(0.235, 0.845, name.upper(), fontsize=9, fontweight="bold",
            color=colour, va="center")
    ax.text(0.235, 0.605, f"NZ${vot:,.2f} /h", fontsize=19, fontweight="bold",
            color=NAVY, va="center")
    ax.text(0.055, 0.345, f"price sensitivity  β = {beta:.2f}"
                          f"{'  (capped)' if beta >= 2 or beta <= 0.1 else ''}",
            fontsize=8.8, color=INK, va="center")
    ax.text(0.055, 0.205, f"essential prob {ess:.2f}   ·   departs {dep:02d}:00",
            fontsize=8.8, color=MUTED, va="center")
    # the disparity, stated in the agent's own currency
    ax.text(0.055, 0.065, f"$6 fee  =  {6 / vot:.2f} hours of own time",
            fontsize=9.6, fontweight="bold", color=colour, va="center")

    # ---- the same charge, three outcomes ----
    ax2 = fig.add_subplot(gs[1, col])
    ax2.plot(FEES, probs, "-o", color=colour, lw=2.6, markersize=8, zorder=3)
    ax2.fill_between(FEES, 0, probs, color=colour, alpha=0.10, zorder=2)
    ax2.set_xticks(FEES)
    ax2.set_xticklabels([f"${f}" for f in FEES], fontsize=9.5, color=INK)
    ax2.set_ylim(0, 0.62)
    ax2.set_xlim(-0.4, 6.4)
    ax2.grid(axis="y", color="#EEF2F6", zorder=0)
    ax2.set_axisbelow(True)
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax2.spines[s].set_color("#CBD5E1")
    ax2.tick_params(colors=INK, labelsize=9)
    if col == 0:
        ax2.set_ylabel("probability of entering", fontsize=9.5, color=INK)
    else:
        ax2.set_yticklabels([])
    ax2.set_xlabel("cordon fee", fontsize=9.5, color=INK)

    ax2.annotate(f"{probs[0]:.2f}", (0, probs[0]), textcoords="offset points",
                 xytext=(2, 10), fontsize=9, color=MUTED)
    ax2.annotate(f"{probs[-1]:.2f}", (6, probs[-1]), textcoords="offset points",
                 xytext=(-4, 11), ha="right", fontsize=10.5,
                 fontweight="bold", color=colour)
    ax2.text(0.97, 0.93, f"{cut:+.0f}%", transform=ax2.transAxes, ha="right",
             va="top", fontsize=15, fontweight="bold", color=colour)

fig.text(0.055, 0.955,
         "Three real agents, one charge: p = base-trip-rate × exp(−β × fee ÷ VoT), "
         "with β itself set inversely to VoT",
         fontsize=10.5, color=INK, ha="left")

out = os.path.join(FIGS, "agent_personas.png")
fig.savefig(out, dpi=190, facecolor="white")
print("wrote", out)
