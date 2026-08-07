#!/usr/bin/env python3
"""Presentation flow figures (16:9) for the SSC2026 model.

One bold overview of the daily pricing-response loop, then one variant per
agent persona with the rest of the diagram dimmed and a persona card added —
a progressive-reveal sequence for slides.

Writes output/figures/pres_flow_overview.png and
       output/figures/pres_flow_persona_<agent>.png  (5 variants), 16:9.
"""
import os, math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

W, H = 100, 56.25  # 16:9 canvas

AGENTS = {
    "pricing": dict(
        name="PRICING", tag="ToU cordon charge · $2–6 by hour",
        color="#3e7d4f", pos=(52, 42.2),
        card_title="The Regulator",
        card=["Sets the cordon charge: ToU $2 / $4 / $6 by hour",
              "Goal: push demand out of the 8–9 am peak",
              "Static schedule here — adaptive pricing is the extension"]),
    "commuter": dict(
        name="COMMUTERS", tag="2,500 agents · 1 : 160 vehicles",
        color="#c0662b", pos=(79, 31.5),
        card_title="The Travellers",
        card=["Know: value of time, activity chain, today's fee",
              "Decide each morning: enter the CBD? at what hour?",
              "Learn day by day: Exp-Decay · El Farol · Q-Learning"]),
    "routing": dict(
        name="ROUTING", tag="cached shortest paths",
        color="#2f5f8f", pos=(67.5, 12.5),
        card_title="The Navigator",
        card=["Free-flow shortest paths on the OSM network",
              "Cached once per origin–destination pair",
              "Simplification: no en-route re-routing"]),
    "link": dict(
        name="NETWORK", tag="1,634 links · V/C → BPR speeds → LoS A–F",
        color="#54595f", pos=(32.5, 12.5),
        card_title="The Roads",
        card=["Vehicle loads → V/C → BPR speed feedback",
              "Reports flow-based Level of Service A–F hourly",
              "Calibrated to AT observed ADT (ratio 1.01)"]),
    "signal": dict(
        name="SIGNALS", tag="g/C capacity at conflict nodes",
        color="#9d4a5e", pos=(21, 31.5),
        card_title="The Intersections",
        card=["Signalised conflict nodes on the arterial grid",
              "Cut approach capacity by the green share g/C",
              "Why arterials congest while motorways flow"]),
}
NW, NH = 24, 9  # node box size

FLOWS = [  # (src, dst, label, rad, color, label-xy override)
    ("pricing", "commuter", "fee at trip hour", -0.25, "black", (69.5, 41.5)),
    ("commuter", "routing", "today's trips", -0.25, "black", None),
    ("routing", "link", "routes", 0.0, "black", None),
    ("signal", "link", "capacities", 0.25, "black", None),
    ("link", "commuter", "realised congestion → learn overnight", -0.15,
     "#a03030", (57.5, 19.6)),
    ("link", "pricing", "future: adaptive pricing", -0.35, "#888888",
     (33.5, 39.3)),
]


def edge_point(src, dst):
    """Point on src's box border toward dst's centre."""
    (x1, y1), (x2, y2) = AGENTS[src]["pos"], AGENTS[dst]["pos"]
    dx, dy = x2 - x1, y2 - y1
    tx = (NW / 2 + 1.0) / abs(dx) if dx else math.inf
    ty = (NH / 2 + 1.0) / abs(dy) if dy else math.inf
    t = min(tx, ty)
    return (x1 + dx * t, y1 + dy * t)


def draw(spotlight=None):
    fig, ax = plt.subplots(figsize=(13.33, 7.5))
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_axis_off()
    fig.patch.set_facecolor("white")

    # title
    ax.text(2.5, 55.4, "A day in the model", fontsize=26, fontweight="bold",
            color="#1a1a1a", va="top")
    ax.text(2.5, 51.2, "cordon pricing · behavioural adaptation\n"
            "· Level of Service", fontsize=12, color="#555555", va="top",
            linespacing=1.35)
    # loop badge (centre)
    ax.text(50, 30.6, "×14", ha="center", va="center", fontsize=30,
            fontweight="bold",
            color="#c9c9c9" if spotlight else "#9a9a9a")
    ax.text(50, 26.9, "days — learning\ncloses the loop", ha="center",
            va="center", fontsize=10.5,
            color="#c9c9c9" if spotlight else "#777777", linespacing=1.3)

    # flows
    for src, dst, label, rad, color, lxy in FLOWS:
        dim = spotlight is not None and spotlight not in (src, dst)
        a = 0.15 if dim else 1.0
        lw = 2.2 if color == "black" else 2.6
        ls = (0, (5, 3)) if "future" in label else "-"
        p1, p2 = edge_point(src, dst), edge_point(dst, src)
        ax.add_patch(FancyArrowPatch(
            p1, p2, arrowstyle="-|>", mutation_scale=22, lw=lw, color=color,
            alpha=a, linestyle=ls, connectionstyle=f"arc3,rad={rad}", zorder=2))
        if not dim:
            if lxy is not None:
                mx, my = lxy
            else:
                mx = (p1[0] + p2[0]) / 2 - rad * (p2[1] - p1[1]) * 0.9
                my = (p1[1] + p2[1]) / 2 + rad * (p2[0] - p1[0]) * 0.9
            ax.text(mx, my, label, ha="center", va="center", fontsize=10,
                    style="italic", color=color if color != "black" else "#333",
                    zorder=6,
                    bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.2))

    # nodes
    for key, a in AGENTS.items():
        x, y = a["pos"]
        focal = spotlight == key
        dim = spotlight is not None and not focal
        w, h = (NW + 2.5, NH + 1.6) if focal else (NW, NH)
        # shadow
        if not dim:
            ax.add_patch(FancyBboxPatch((x - w / 2 + 0.5, y - h / 2 - 0.5), w, h,
                                        boxstyle="round,pad=0.4,rounding_size=1.2",
                                        fc="#000000", ec="none", alpha=0.18,
                                        zorder=3))
        ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                    boxstyle="round,pad=0.4,rounding_size=1.2",
                                    fc=a["color"], ec="white",
                                    lw=3.0 if focal else 1.5,
                                    alpha=0.18 if dim else 1.0, zorder=4))
        ax.text(x, y + 1.3, a["name"], ha="center", va="center",
                fontsize=17 if focal else 15, fontweight="bold", color="white",
                alpha=0.35 if dim else 1.0, zorder=5)
        ax.text(x, y - 1.9, a["tag"], ha="center", va="center",
                fontsize=9.5 if focal else 8.5, color="white",
                alpha=0.35 if dim else 1.0, zorder=5)

    # persona card
    if spotlight:
        a = AGENTS[spotlight]
        cw, ch = 40, 15
        cx = 3 if a["pos"][0] > 50 else W - cw - 3
        cy = 2.5
        ax.add_patch(FancyBboxPatch((cx, cy), cw, ch,
                                    boxstyle="round,pad=0.5,rounding_size=1.0",
                                    fc="white", ec=a["color"], lw=2.5, zorder=7))
        ax.add_patch(Rectangle((cx - 0.2, cy + ch - 3.4), cw + 0.4, 3.6,
                               fc=a["color"], ec="none", zorder=8))
        ax.text(cx + 1.5, cy + ch - 1.6, f"{a['name']} — {a['card_title']}",
                fontsize=13, fontweight="bold", color="white", va="center",
                zorder=9)
        for i, line in enumerate(a["card"]):
            ax.text(cx + 2.2, cy + ch - 5.8 - i * 3.3, f"•  {line}",
                    fontsize=10.5, color="#222222", va="center", zorder=9)

    fig.tight_layout(pad=0.3)
    name = f"pres_flow_persona_{spotlight}" if spotlight else "pres_flow_overview"
    out = os.path.join(FIGS, f"{name}.png")
    fig.savefig(out, dpi=200, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print("wrote", out)


draw(None)
for key in AGENTS:
    draw(key)
