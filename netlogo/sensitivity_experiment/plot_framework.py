#!/usr/bin/env python3
"""Publication framework diagram for the SSC2026 model, POLARIS-style.

Three time-resolution columns (Preprocessing / Each simulated day / Continuous
time), agent panels (commuter agent, policy layer, routing, traffic simulation,
measurement), and the end-of-day learning feedback loop that closes the
pricing-response cycle.

Writes output/figures/framework_diagram.png (300 dpi) and .pdf (vector).
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Ellipse, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

BOX_FC = "#7591c9"      # main process boxes (POLARIS blue)
BOX_EC = "#4a629b"
DB_FC = "#2e4272"       # data cylinders (dark blue)
PANEL_PERSON = "#f0dedd"  # commuter-agent backdrop (warm)
PANEL_POLICY = "#d8e4bc"  # policy layer (green)
PANEL_ROUTE = "#cdd9ef"   # routing agent (light blue)
PANEL_SIM = "#dbe4f0"     # traffic simulation (blue-gray)
PANEL_MEAS = "#e4e9f2"    # measurement layer

fig, ax = plt.subplots(figsize=(12, 7))
ax.set_xlim(0, 100)
ax.set_ylim(0, 64)
ax.set_axis_off()


def box(x, y, w, h, text, fc=BOX_FC, ec=BOX_EC, tc="white", fs=8.3, lw=1.0,
        style="round,pad=0.25"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=style,
                                fc=fc, ec=ec, lw=lw, zorder=3))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc, zorder=4, linespacing=1.35)
    return (x, y, w, h)


def panel(x, y, w, h, label, fc, label_pos="sw", fs=9.5):
    ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec="none", zorder=1))
    lx, ly, ha, va = {
        "sw": (x + 1.2, y + 1.0, "left", "bottom"),
        "se": (x + w - 1.2, y + 1.0, "right", "bottom"),
        "nw": (x + 1.2, y + h - 1.0, "left", "top"),
    }[label_pos]
    ax.text(lx, ly, label, ha=ha, va=va, fontsize=fs, color="#333333",
            zorder=2, style="italic")


def cylinder(x, y, w, h, text, fs=8.0):
    body = Rectangle((x, y), w, h - 1.4, fc=DB_FC, ec="none", zorder=3)
    ax.add_patch(body)
    ax.add_patch(Ellipse((x + w / 2, y), w, 2.6, fc=DB_FC, ec="none", zorder=3))
    ax.add_patch(Ellipse((x + w / 2, y + h - 1.4), w, 2.6, fc=DB_FC,
                         ec="#1e2f55", lw=0.8, zorder=4))
    ax.text(x + w / 2, y + (h - 1.4) / 2 - 0.2, text, ha="center", va="center",
            fontsize=fs, color="white", zorder=5, linespacing=1.35)
    return (x, y, w, h)


def arrow(p1, p2, connectionstyle="arc3,rad=0", color="black", lw=1.4,
          ls="-", label=None, label_dxy=(0, 1.2), fs=7.5):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=13,
                                 color=color, lw=lw, linestyle=ls,
                                 connectionstyle=connectionstyle, zorder=5))
    if label:
        mx, my = (p1[0] + p2[0]) / 2 + label_dxy[0], (p1[1] + p2[1]) / 2 + label_dxy[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=fs,
                color="#222222", zorder=6, style="italic")


# ---- column headers --------------------------------------------------------
for x, w, t in [(1, 25, "Preprocessing"), (28, 33, "Each simulated day"),
                (63, 36, "In continuous time (6-s ticks)")]:
    ax.add_patch(Rectangle((x, 59.5), w, 3.6, fc="white", ec="black", lw=1.1))
    ax.text(x + w / 2, 61.3, t, ha="center", va="center", fontsize=10.5,
            fontweight="bold")

# ---- backdrop panels -------------------------------------------------------
panel(1, 1.5, 60, 56.5, "Commuter agent", PANEL_PERSON, "sw")
panel(28, 47.5, 33, 10.0, "Policy layer", PANEL_POLICY, "sw", fs=9)
panel(63, 40.5, 36, 17.0, "Routing agent", PANEL_ROUTE, "se", fs=9)
panel(63, 20.5, 36, 18.5, "Traffic simulation model", PANEL_SIM, "se", fs=9)
panel(63, 1.5, 36, 17.5, "Measurement layer", PANEL_MEAS, "se", fs=9)

# ---- preprocessing column --------------------------------------------------
cyl = cylinder(4, 46, 19, 10.5,
               "Input / scenario data\nOSM network · AT observed ADT\nbuildings · cordon geometry")
pop = box(3.5, 30, 20, 8.5,
          "Population synthesis\n2,500 agents (1 : 160 veh)\nhome sector · VOT · activity\nchains · decision-rule mix")
cal = box(3.5, 14, 20, 8.5,
          "Demand calibration\nscale-factor + suburban\ndestinations fitted to ADT\n(ratio = 1.01)")
arrow((13.5, 46 - 1.2), (13.5, 30 + 8.5 + 0.4))
arrow((13.5, 30 - 0.3), (13.5, 14 + 8.5 + 0.4))

# ---- each-simulated-day column ---------------------------------------------
fee = box(33.5, 50.5, 24.5, 5.2,
          "Congestion pricing scheme\ncordon charge · ToU fee schedule ($2–6)",
          fc="#79975c", ec="#5a7444")
rst = box(31, 39.5, 27, 5.5, "New-day reset\ndepartures re-anchored to today's clock")
dec = box(31, 28.5, 27, 7.5,
          "CBD entry & timing decision\nExp-Decay  |  El Farol  |  Q-Learning\n(fee at drawn trip hour · VOT)")
dep = box(31, 18.5, 27, 6,
          "Schedule departures\nAM / PM peak demand profiles")
lrn = box(31, 4.5, 27, 6.5,
          "End-of-day learning\nattendance history · El Farol\npredictor scores · Q-table update",
          fc="#8a7fb3", ec="#6a5f93", fs=7.8)

# fee schedule -> decision (routed right of the reset box)
arrow((58 + 0.5, 52.0), (58 + 0.5, 33.5), "arc3,rad=-0.35",
      label="fee lookup", label_dxy=(4.6, 0), fs=7.5)
arrow((44.5, 39.5 - 0.3), (44.5, 28.5 + 7.5 + 0.4))          # reset -> decision
arrow((44.5, 28.5 - 0.3), (44.5, 18.5 + 6 + 0.4))            # decision -> departures
# learning -> next day's decision (routed left of the departures box)
arrow((31 - 0.5, 8.5), (31 - 0.5, 31.5), "arc3,rad=0.25",
      label="next day", label_dxy=(-4.6, 0), fs=7.5)

# population -> commuter loop
arrow((23.5 + 0.4, 34.2), (31 - 0.5, 42.2), "arc3,rad=0.25")

# ---- continuous-time column ------------------------------------------------
rte = box(66, 45.5, 30, 7.5,
          "Get route\ncached free-flow shortest paths\n(one per OD pair)")
sim = box(66, 26.5, 30, 9.5,
          "Link traffic dynamics\nV/C from agent loads · BPR speed\nfactor · signalised g/C capacities")
mea = box(66, 4.5, 30, 10.5,
          "Flow-based LoS\nhourly flow EMA → V/C → LoS A–F\ngroup / time-band MOEs",
          fc="#5e7ba6", ec="#44608c")

arrow((58 + 0.5, 22.0), (66 - 0.6, 45.8), "arc3,rad=0.12")    # departures -> route
arrow((81, 45.5 - 0.3), (81, 26.5 + 9.5 + 0.4))               # route -> sim
arrow((81, 26.5 - 0.3), (81, 4.5 + 10.5 + 0.4))               # sim -> measurement

# calibration informs link capacities (dashed, routed under the learning box)
arrow((23.5 + 0.4, 14.5), (70, 26.5 - 0.3), "arc3,rad=-0.2",
      ls="--", lw=1.2, color="#555555")

# feedback: realised congestion -> end-of-day learning (thick, distinct)
arrow((66 - 0.5, 8.0), (58 + 0.5, 8.0), color="#8a2f2f", lw=2.0,
      label="realised congestion", label_dxy=(0, 1.6), fs=8)

ax.text(50, 0.6, "", fontsize=7)
fig.tight_layout(pad=0.4)
for ext in ("png", "pdf"):
    out = os.path.join(FIGS, f"framework_diagram.{ext}")
    fig.savefig(out, dpi=300, bbox_inches="tight")
    print("wrote", out)
