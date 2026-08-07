#!/usr/bin/env python3
"""Agent-interaction diagram for the SSC2026 model (POLARIS Fig-style).

Five agent panels — routing, commuter, link, signal control, pricing — with
data stores (cylinders), models (boxes), and states/decisions (diamonds),
connected by orthogonal flows, mirroring the POLARIS network-model figure.

Writes output/figures/agents_diagram.png (300 dpi) and .pdf (vector).
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import (FancyBboxPatch, FancyArrowPatch, Ellipse,
                                Rectangle, Polygon)

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

BOX_FC, BOX_EC = "#7591c9", "#4a629b"
DB_FC = "#2e4272"
P_ROUTE = "#c9d6ee"   # routing agent (blue)
P_PERSON = "#ecdccb"  # commuter agent (tan)
P_LINK = "#ecdccb"    # link agent (tan)
P_SIGNAL = "#e8cfd4"  # signal control agent (pink)
P_PRICE = "#d8e4bc"   # pricing agent (green)

fig, ax = plt.subplots(figsize=(12.5, 6.8))
ax.set_xlim(0, 100)
ax.set_ylim(0, 52)
ax.set_axis_off()


def panel(x, y, w, h, label, fc, pos="sw", fs=9.5):
    ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec="#aaaaaa", lw=0.6, zorder=1))
    lx, ly, ha, va = {"sw": (x + 1.1, y + 0.8, "left", "bottom"),
                      "se": (x + w - 1.1, y + 0.8, "right", "bottom"),
                      "nw": (x + 1.1, y + h - 0.8, "left", "top"),
                      "ne": (x + w - 1.1, y + h - 0.8, "right", "top")}[pos]
    ax.text(lx, ly, label, ha=ha, va=va, fontsize=fs, color="#333333",
            zorder=2, style="italic")


def box(x, y, w, h, text, fc=BOX_FC, ec=BOX_EC, tc="white", fs=7.8):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2",
                                fc=fc, ec=ec, lw=1.0, zorder=3))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            color=tc, zorder=4, linespacing=1.3)


def cylinder(x, y, w, h, text, fs=7.4):
    ax.add_patch(Rectangle((x, y), w, h - 1.2, fc=DB_FC, ec="none", zorder=3))
    ax.add_patch(Ellipse((x + w / 2, y), w, 2.2, fc=DB_FC, ec="none", zorder=3))
    ax.add_patch(Ellipse((x + w / 2, y + h - 1.2), w, 2.2, fc=DB_FC,
                         ec="#1e2f55", lw=0.8, zorder=4))
    ax.text(x + w / 2, y + (h - 1.2) / 2 - 0.2, text, ha="center", va="center",
            fontsize=fs, color="white", zorder=5, linespacing=1.3)


def diamond(cx, cy, w, h, text, fs=7.4):
    ax.add_patch(Polygon([(cx - w / 2, cy), (cx, cy + h / 2),
                          (cx + w / 2, cy), (cx, cy - h / 2)],
                         closed=True, fc="white", ec="black", lw=1.0, zorder=3))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, zorder=4,
            linespacing=1.25)


def head(p1, p2, color="black", lw=1.4):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=12,
                                 color=color, lw=lw, zorder=5))


def polyline(points, color="black", lw=1.4, label=None, lxy=None, fs=7.2,
             ls="-"):
    xs, ys = zip(*points)
    ax.plot(xs[:-1] + (points[-2][0],), ys[:-1] + (points[-2][1],),
            color=color, lw=lw, ls=ls, zorder=5, solid_capstyle="round")
    head(points[-2], points[-1], color=color, lw=lw)
    if label:
        ax.text(*lxy, label, fontsize=fs, style="italic", color="#222222",
                ha="center", va="center", zorder=6,
                bbox=dict(fc="white", ec="none", alpha=0.75, pad=0.6))


# ================= panels ===================================================
panel(1, 36.5, 46, 14.5, "Routing agent", P_ROUTE, "sw")
panel(1, 1, 46, 34, "Commuter agent", P_PERSON, "sw")
panel(49, 33, 50, 18, "Link agent", P_LINK, "nw")
panel(49, 18, 50, 13.5, "Signal control agent", P_SIGNAL, "se")
panel(49, 1, 50, 15.5, "Pricing agent (policy)", P_PRICE, "se")

# ================= routing agent ============================================
cylinder(3, 40.5, 12.5, 9, "Network topology\nOSM nodes · links\nspeed limits")
box(19, 43.5, 18, 5, "Route generation model\nfree-flow shortest path")
diamond(28, 40.2, 9, 5.2, "Routes")
cylinder(38.5, 37.5, 8, 6.5, "Path cache\n(per OD pair)")
head((15.8, 46), (18.7, 46))
head((28, 43.1), (28, 42.6))          # generation -> routes (short)
head((32.6, 40.2), (38.2, 40.2))      # routes -> cache
polyline([(42.5, 37.3), (42.5, 35.6), (38, 35.6), (38, 34.2)],
         label="trip routes", lxy=(34.8, 36.7))

# ================= commuter agent ===========================================
cylinder(3, 25, 12.5, 9, "Traveler characteristics\nVOT · home sector\nactivities · rule")
box(19, 26.5, 21, 7.5,
    "Person planner\nCBD entry & timing decision\nExp-Decay | El Farol | Q-Learning")
diamond(28, 21.3, 13.5, 5.6, "Activity plan\ndepart · return")
box(21, 11, 19, 5, "Person mover\nlink-by-link movement")
box(3, 4, 15.5, 6, "End-of-day learning\nEl Farol scores\nQ-table update",
    fc="#8a7fb3", ec="#6a5f93", fs=7.2)
head((15.8, 30), (18.7, 30))
head((28, 26.2), (28, 24.4))          # planner -> plan
head((28, 18.4), (28, 16.3))          # plan -> mover
polyline([(16.2, 10.2), (16.2, 21.5), (20, 21.5), (20, 26.2)],
         label="next day", lxy=(13.6, 17.5))

# ================= link agent ===============================================
box(52, 42, 20.5, 6.5, "Link simulation model\nagent loads → V/C →\nBPR speed factor")
diamond(59, 37.2, 13, 5.4, "Link speeds")
box(76.5, 42, 20, 6.5, "LoS measurement\nflow EMA → V/C → LoS A–F",
    fc="#5e7ba6", ec="#44608c")
diamond(85.5, 37.2, 17.5, 5.6, "Network performance\nrealised congestion")
head((62.2, 41.7), (60.5, 40.2))      # link sim -> speeds (short)
head((72.9, 45.2), (76.1, 45.2))      # link sim -> LoS
head((85.5, 41.7), (85.5, 40.2))      # LoS -> performance

# mover -> link sim (vehicle loads), via the inter-panel channel
polyline([(40.4, 13.5), (48.2, 13.5), (48.2, 45.2), (51.6, 45.2)],
         label="vehicle loads", lxy=(44.2, 12.3))
# link speeds -> mover (speed feedback)
polyline([(52.3, 37.2), (47.4, 37.2), (47.4, 14.5), (40.5, 14.5)],
         label="speeds", lxy=(44.2, 15.8))
# network performance -> end-of-day learning
polyline([(85.5, 34.3), (85.5, 32.3), (45.8, 32.3), (45.8, 7), (18.9, 7)],
         color="#8a2f2f", lw=1.8, label="realised congestion",
         lxy=(64, 33.5))

# ================= signal control agent =====================================
box(52, 21, 21, 6, "Signalised intersections\nconflict-node detection")
diamond(84, 24, 17, 5.6, "Signal state\ng/C capacity factor")
head((73.4, 24), (75.4, 24))
polyline([(84, 27, ), (84, 33.5), (66, 33.5), (66, 41.7)],
         label="approach capacities", lxy=(75.5, 34.9))

# ================= pricing agent ============================================
cylinder(52, 4.5, 13.5, 9.5, "ToU fee schedule\n$2–6 by hour\n(cordon charge)")
diamond(76, 9, 16, 5.8, "Fee at trip hour")
head((66, 9), (67.8, 9))
# fee -> person planner (via channels right of the commuter boxes)
polyline([(76, 12.2), (76, 17.2), (43.2, 17.2), (43.2, 29), (40.6, 29)],
         label="fee lookup", lxy=(60, 15.7))

fig.tight_layout(pad=0.4)
for ext in ("png", "pdf"):
    out = os.path.join(FIGS, f"agents_diagram.{ext}")
    fig.savefig(out, dpi=300, bbox_inches="tight")
    print("wrote", out)
