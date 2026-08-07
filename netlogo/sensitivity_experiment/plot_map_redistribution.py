#!/usr/bin/env python3
"""Link-level map of the spatial response to ToU pricing, one panel per rule.

Reads the per-link peak V/C exported by `save-links` (BehaviorSpace experiment
`paper-figs`) for the No-Charge and ToU cells of each decision rule and draws
the network with every link coloured by the change

    delta = peak V/C under ToU  -  peak V/C under No-Charge

blue where pricing lowers the peak, red where it raises it (displacement).
Line width scales with |delta| so the links that actually move stand out
against the network. The dashed outline is the cordon: the convex hull of the
links tagged `inner`.

Reads  output/tables/links_<Rule>_{No-Charge,tou}.csv
Writes output/figures/map_redistribution.png
       output/figures/map_baseline_los.png   (No-Charge peak LoS, if exported)

Coordinates are NetLogo patch coordinates (the model's own projection of the
Auckland network), so the axes are unlabelled - the map is topological, not
georeferenced.
"""
import csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import TwoSlopeNorm, ListedColormap, BoundaryNorm

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

RULES = [("Exp-Decay", "Pay (exponential decay)"),
         ("ElFarol", "Oscillate (El Farol)"),
         ("Q-Learning", "Learn (Q-learning)")]
GRADE_COLOR = {"A": "#4a9a4a", "B": "#a5c85a", "C": "#f2d349",
               "D": "#e8973a", "E": "#d64545", "F": "#7d1f1f"}


def load(rule, fee):
    path = os.path.join(TABLES, f"links_{rule}_{fee}.csv")
    if not os.path.exists(path):
        return None
    out = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            # prefer the flow-based hourly V/C (LoS measure); fall back to the
            # density-style vc_peak on tables written before it was exported
            vc = float(r.get("vcf_peak") or r["vc_peak"])
            out[r["link_id"]] = {
                "vc": vc,
                "pos": r["position"],
                "los": r.get("los_peak", ""),
                "seg": ((float(r["x1"]), float(r["y1"])),
                        (float(r["x2"]), float(r["y2"]))),
            }
    return out


def hull(points):
    """Convex hull (monotone chain) - the cordon outline, no scipy needed."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def half(seq):
        out = []
        for p in seq:
            while len(out) >= 2:
                (x1, y1), (x2, y2) = out[-2], out[-1]
                if (x2 - x1) * (p[1] - y1) - (y2 - y1) * (p[0] - x1) > 0:
                    break
                out.pop()
            out.append(p)
        return out

    return half(pts)[:-1] + half(reversed(pts))[:-1]


def draw_cordon(ax, links):
    pts = [p for d in links.values() if d["pos"] == "inner" for p in d["seg"]]
    if not pts:
        return
    h = hull(pts)
    ax.plot([p[0] for p in h] + [h[0][0]], [p[1] for p in h] + [h[0][1]],
            "--", color="#333333", lw=1.1, alpha=0.8, zorder=5)


# --- Figure 1: change in peak V/C under ToU --------------------------------
panels = []
for rule, title in RULES:
    nc, tou = load(rule, "No-Charge"), load(rule, "tou")
    if nc and tou:
        panels.append((rule, title, nc, tou))

if not panels:
    print("(skip redistribution map: no links_*.csv — run the paper-figs experiment)")
else:
    deltas_all = [tou[k]["vc"] - nc[k]["vc"]
                  for _, _, nc, tou in panels for k in nc if k in tou]
    # robust symmetric scale: outliers would otherwise wash the whole map out
    lim = sorted(abs(d) for d in deltas_all)[int(0.95 * len(deltas_all))] or 1e-6
    norm = TwoSlopeNorm(vmin=-lim, vcenter=0.0, vmax=lim)
    cmap = plt.get_cmap("RdBu_r")   # reduction (negative) = blue, increase = red
    base_all = [nc[k]["vc"] for _, _, nc, _ in panels for k in nc]
    base_lim = sorted(base_all)[int(0.95 * len(base_all))] or 1e-6

    fig, axes = plt.subplots(1, len(panels), figsize=(5.0 * len(panels), 5.6))
    axes = [axes] if len(panels) == 1 else list(axes)
    for ax, (rule, title, nc, tou) in zip(axes, panels):
        keys = [k for k in nc if k in tou]
        # base network shaded by the no-charge peak V/C, so the change layer is
        # read against where congestion actually sits without a charge
        ax.add_collection(LineCollection(
            [nc[k]["seg"] for k in keys],
            array=[min(nc[k]["vc"], base_lim) for k in keys],
            cmap="Greys", clim=(0, base_lim * 1.35),
            linewidths=[0.4 + 1.1 * min(nc[k]["vc"] / base_lim, 1.0) for k in keys],
            zorder=1))
        deltas = [tou[k]["vc"] - nc[k]["vc"] for k in keys]
        order = sorted(range(len(keys)), key=lambda i: abs(deltas[i]))
        segs = [nc[keys[i]]["seg"] for i in order]
        dv = [deltas[i] for i in order]
        widths = [0.4 + 3.0 * min(abs(d) / lim, 1.0) for d in dv]
        lc = LineCollection(segs, array=dv, cmap=cmap, norm=norm,
                            linewidths=widths, zorder=3)
        ax.add_collection(lc)
        draw_cordon(ax, nc)
        inner = [tou[k]["vc"] - nc[k]["vc"] for k in keys if nc[k]["pos"] == "inner"]
        bound = [tou[k]["vc"] - nc[k]["vc"] for k in keys if nc[k]["pos"] == "boundary"]
        peri = [tou[k]["vc"] - nc[k]["vc"] for k in keys if nc[k]["pos"] == "peripheral"]
        ax.set_title(title, fontsize=11)
        ax.text(0.02, 0.02,
                f"mean Δ  inner {sum(inner)/len(inner):+.3f}\n"
                f"       boundary {sum(bound)/len(bound):+.3f}\n"
                f"       peripheral {sum(peri)/len(peri):+.3f}",
                transform=ax.transAxes, fontsize=8, va="bottom", family="monospace")
        ax.autoscale()
        ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
    cb = fig.colorbar(lc, ax=axes, fraction=0.025, pad=0.02, extend="both")
    cb.set_label("change in peak flow V/C under ToU  (blue = reduction)")
    fig.suptitle("Link-level response to the ToU cordon charge, by decision rule "
                 "(14 days, calibrated model; dashed line = cordon)", y=0.95)
    out = os.path.join(FIGS, "map_redistribution.png")
    fig.savefig(out, dpi=400, bbox_inches="tight")
    print("wrote", out)
    plt.close(fig)

# --- Figure 2: baseline LoS map (No-Charge peak grade) ---------------------
have = [(r, t, load(r, "No-Charge")) for r, t in RULES]
have = [(r, t, d) for r, t, d in have if d and any(v["los"] for v in d.values())]
if not have:
    print("(skip baseline LoS map: links_*.csv has no los_peak column)")
else:
    grades = list(GRADE_COLOR)
    cmap = ListedColormap([GRADE_COLOR[g] for g in grades])
    norm = BoundaryNorm(range(len(grades) + 1), cmap.N)
    fig, axes = plt.subplots(1, len(have), figsize=(5.0 * len(have), 5.6))
    axes = [axes] if len(have) == 1 else list(axes)
    for ax, (rule, title, d) in zip(axes, have):
        keys = list(d)
        vals = [grades.index(d[k]["los"]) if d[k]["los"] in grades else 0 for k in keys]
        order = sorted(range(len(keys)), key=lambda i: vals[i])
        lc = LineCollection([d[keys[i]]["seg"] for i in order],
                            array=[vals[i] for i in order], cmap=cmap, norm=norm,
                            linewidths=[0.5 + 0.45 * vals[i] for i in order])
        ax.add_collection(lc)
        draw_cordon(ax, d)
        ax.set_title(f"{title} — no charge", fontsize=11)
        ax.autoscale()
        ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
    handles = [plt.Line2D([], [], color=GRADE_COLOR[g], lw=3, label=f"LoS {g}")
               for g in grades]
    fig.legend(handles=handles, loc="lower center", ncol=6, frameon=False,
               bbox_to_anchor=(0.5, 0.02))
    fig.suptitle("Daily peak Level of Service by link under no charge "
                 "(calibrated model, 14 days)", y=0.95)
    out = os.path.join(FIGS, "map_baseline_los.png")
    fig.savefig(out, dpi=400, bbox_inches="tight")
    print("wrote", out)
    plt.close(fig)
