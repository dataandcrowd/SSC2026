#!/usr/bin/env python3
"""Demand calibration: modelled daily link volumes vs observed ADT.

Reads the per-link CSV written by `save-calibration` (No-Charge baseline run),
compares modelled veh/day against AT observed ADT on the matched links, and
reports the scaling correction to apply to number_of_vehicles x scale-factor.

The headline statistic is the flow-weighted ratio sum(model)/sum(observed):
scaling every agent's real-vehicle weight by 1/ratio makes total modelled
daily travel on counted links equal total observed travel, so
    suggested scale-factor = current scale-factor / ratio.
Per-class and per-group ratios show how much residual distribution mismatch
a single scalar cannot fix.

Reads  netlogo/output/tables/calibration_*.csv
Writes netlogo/output/figures/calibration_scatter.png
       netlogo/output/tables/calibration_summary.txt
"""
import csv, glob, os, math, re, sys
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)


def newest_calibration_csv():
    paths = sorted(glob.glob(os.path.join(TABLES, "calibration_*_n*_sf*.csv")),
                   key=os.path.getmtime)
    if not paths:
        sys.exit("No calibration_*.csv found in output/tables — run the "
                 "calibration-demand experiment first.")
    return paths[-1]


def load(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["adt_obs"] = float(r["adt_obs"])
        r["veh_day_model"] = float(r["veh_day_model"])
        r["implied_k"] = float(r.get("implied_k", 0) or 0)
        r["vcf_am"] = float(r.get("vcf_am", 0) or 0)
    return rows


def ratio_stats(rows):
    """Flow-weighted ratio, plus median of per-link ratios (matched links only)."""
    m = [r for r in rows if r["adt_obs"] > 0]
    tot_obs = sum(r["adt_obs"] for r in m)
    tot_mod = sum(r["veh_day_model"] for r in m)
    per_link = sorted(r["veh_day_model"] / r["adt_obs"] for r in m
                      if r["veh_day_model"] > 0)
    med = per_link[len(per_link) // 2] if per_link else float("nan")
    return tot_mod / tot_obs if tot_obs else float("nan"), med, len(m)


def main():
    path = newest_calibration_csv()
    fname = os.path.basename(path)
    sf = float(re.search(r"_sf([\d.]+?)\.csv$", fname).group(1))
    nveh = int(re.search(r"_n(\d+)_", fname).group(1))
    rows = load(path)
    matched = [r for r in rows if r["adt_obs"] > 0]

    ratio, med, n = ratio_stats(rows)
    if ratio == 0:
        sys.exit(f"All modelled volumes are zero in {fname} — the run did not "
                 "move vehicles (interrupted or errored). Re-run the "
                 "calibration-demand experiment.")
    lines = [f"Demand calibration — {fname}",
             f"number_of_vehicles = {nveh}, scale-factor = {sf:g}",
             f"Matched links (with observed ADT): {n} of {len(rows)}",
             "",
             f"Flow-weighted ratio sum(model)/sum(obs): {ratio:.3f}",
             f"Median per-link ratio:                   {med:.3f}",
             "",
             f"Suggested scale-factor = {sf:g} / {ratio:.3f} = {sf / ratio:.1f}"
             f"  (keep number_of_vehicles = {nveh})"]

    # implied design-hour factor k = peak clock-hour volume / daily volume,
    # flow-weighted over matched links. r-cap-hr uses k=0.10; if the model's
    # implied k exceeds that, peak-hour flow exceeds design-hour capacity even
    # when daily volumes match — the residual driver of high peak-hour LoS E/F.
    busy = [r for r in matched if r["veh_day_model"] > 0 and r["implied_k"] > 0]
    if busy:
        tot = sum(r["veh_day_model"] for r in busy)
        k_fw = sum(r["implied_k"] * r["veh_day_model"] for r in busy) / tot
        ks = sorted(r["implied_k"] for r in busy)
        k_med = ks[len(ks) // 2]
        lines += ["",
                  f"Implied design-hour k (peak-hour/daily): "
                  f"flow-wtd {k_fw:.3f}, median {k_med:.3f}  (model uses k=0.10)"]
    lines += ["", "Breakdown (flow-weighted ratio / median / n links):"]
    for key in ("class", "group"):
        groups = defaultdict(list)
        for r in matched:
            groups[r[key]].append(r)
        for g in sorted(groups):
            rt, md, ng = ratio_stats(groups[g])
            lines.append(f"  {key:8s} {g:10s} {rt:6.3f} / {md:6.3f} / {ng}")

    out = "\n".join(lines)
    print(out)
    with open(os.path.join(TABLES, "calibration_summary.txt"), "w") as f:
        f.write(out + "\n")

    # log-log scatter, coloured by group, with y=x and y=ratio*x guides
    fig, ax = plt.subplots(figsize=(6.5, 6))
    colors = {"MWY": "black", "CBD": "#c04040", "East": "#4878a8", "West": "#4a9a4a"}
    for g, c in colors.items():
        xs = [r["adt_obs"] for r in matched if r["group"] == g]
        ys = [max(r["veh_day_model"], 1) for r in matched if r["group"] == g]
        ax.scatter(xs, ys, s=10, alpha=0.5, color=c, label=g, edgecolors="none")
    lo, hi = 100, max(r["adt_obs"] for r in matched) * 2
    ax.plot([lo, hi], [lo, hi], "k-", lw=1, label="y = x")
    ax.plot([lo, hi], [lo * ratio, hi * ratio], "k--", lw=1,
            label=f"y = {ratio:.2f}x (fitted)")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("Observed ADT (veh/day)")
    ax.set_ylabel("Modelled volume (veh/day)")
    ax.set_title(f"Link volumes vs observed ADT (scale-factor {sf:g})")
    ax.legend(fontsize=8)
    ax.grid(True, which="both", alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(FIGS, "calibration_scatter.png"), dpi=150)
    print(f"\nWrote {os.path.join(FIGS, 'calibration_scatter.png')}")


if __name__ == "__main__":
    main()
