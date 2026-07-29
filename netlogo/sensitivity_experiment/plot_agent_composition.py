#!/usr/bin/env python3
"""Figure: who the 2,500 agents are, and which of them the charge can reach.

Counts are measured at setup on seed 11 by the `agent-census` experiment
(agent_census.xml), not derived from the slider values.

Writes output/figures/agent_composition.png
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

NAVY, INK, WARN = "#0D2137", "#334155", "#B45309"

# (label, count, colour) — measured, agent-census, seed 11
HOME = [("Arterial edge", 767, "#1F5C8B"),
        ("Southern", 484, "#2E75B6"),
        ("Northern", 309, "#5B9BD5"),
        ("Western", 205, "#9DC3E6"),
        ("Isthmus residents", 735, "#B9C6D4")]
REACH = [("CBD-bound — the charge reaches these", 1500, "#C0504D"),
         ("Never enter the cordon (544 pass-through)", 1000, "#CBD5E1")]

# Both rows live on one axes so the spacing between them is set here, not by
# subplot machinery that fights the tight bounding box.
ROW_Y = {"home": 1.0, "reach": 0.0}
BAR_H = 0.46

fig, ax = plt.subplots(figsize=(12.4, 4.2))

def stack(parts, y):
    left = 0
    for label, n, colour in parts:
        ax.barh([y], [n], left=left, color=colour, height=BAR_H,
                edgecolor="white", linewidth=1.6, zorder=3)
        if n >= 430:                      # fits inside the segment
            ax.text(left + n / 2, y, f"{label}\n{n:,}", ha="center", va="center",
                    fontsize=9.2, color="white", fontweight="bold",
                    zorder=4, linespacing=1.5)
        else:                             # too narrow — label above it
            ax.text(left + n / 2, y + BAR_H / 2 + 0.05, f"{label} {n:,}",
                    ha="center", va="bottom", fontsize=8.6, color=INK, zorder=4)
        left += n

stack(HOME, ROW_Y["home"])
stack(REACH, ROW_Y["reach"])

for y, text in ((ROW_Y["home"], "Where they live"),
                (ROW_Y["reach"], "Whether the charge can reach them")):
    ax.text(0, y - BAR_H / 2 - 0.07, text, ha="left", va="top",
            fontsize=10.5, fontweight="bold", color=NAVY)

ax.text(2500, ROW_Y["home"] - BAR_H / 2 - 0.07, "0 agents live inside the cordon",
        ha="right", va="top", fontsize=11, fontweight="bold", color=WARN)
ax.text(2500, ROW_Y["home"] + BAR_H / 2 + 0.30,
        "2,500 agents   ·   1 agent = 160 real vehicles   ·   ~400,000 vehicle-trips a day",
        ha="right", va="bottom", fontsize=9.5, color=INK)

ax.set_xlim(0, 2500)
ax.set_ylim(-0.45, 1.62)
ax.axis("off")

fig.tight_layout(pad=0.4)
out = os.path.join(FIGS, "agent_composition.png")
fig.savefig(out, dpi=190, facecolor="white")
print("wrote", out)
