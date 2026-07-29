#!/usr/bin/env python3
"""Redraw NetLogo's own interface plots, exported from the GUI, in plotnine.

`export-plot` writes data, not a picture, in a layout of its own: a settings
block, a pen table, then one group of four columns (x, y, colour, pen down?)
per pen side by side. This script parses that layout and redraws the three
plots exported on 2026-07-29:

  cbd vc over time.csv   inner / boundary / peripheral V/C, per tick
  mean flow vc.csv       flow V/C by reporting group, per tick
  %los.csv               % of each group's traffic at LoS E/F, per tick

Ticks are converted to clock hours (tick 0 = sim-start-hour), so the shape is
readable as a day rather than as a tick index.

Reads  output/tables/{cbd vc over time,mean flow vc,%los}.csv
Writes output/figures/netlogo_cbd_vc_gg.png
       output/figures/netlogo_groups_gg.png
"""
import csv, os
import pandas as pd
from plotnine import (ggplot, aes, geom_line, geom_hline, facet_wrap, labs,
                      theme_minimal, theme, element_text, element_blank,
                      element_rect, scale_colour_manual, scale_x_continuous)

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

TICKS_PER_HOUR = 600
SIM_START_HOUR = 5
BASE_THEME = (theme_minimal()
              + theme(plot_title=element_text(size=12, weight="bold", ha="left"),
                      plot_subtitle=element_text(size=9, colour="#555555", ha="left"),
                      plot_caption=element_text(size=8, colour="#777777", ha="left"),
                      strip_text=element_text(size=10, weight="bold"),
                      strip_background=element_rect(fill="#eef3f8", colour="none"),
                      legend_position="top", legend_title=element_blank(),
                      panel_grid_minor=element_blank()))


def read_netlogo_plot(path):
    """-> (settings dict, tidy DataFrame with pen / tick / hour / value)."""
    rows = list(csv.reader(open(path)))
    # settings: the row after the "MODEL SETTINGS" marker is the header
    si = next(i for i, r in enumerate(rows) if r and r[0] == "MODEL SETTINGS")
    settings = dict(zip(rows[si + 1], [v.strip('"') for v in rows[si + 2]]))
    # data: the pen names sit one row above the repeated x,y,color,pen-down header
    hi = next(i for i, r in enumerate(rows) if r[:2] == ["x", "y"])
    # names arrive as """MWY""" -> csv gives '"MWY"'; strip the quotes
    pens = [c.strip('"') for c in rows[hi - 1] if c]
    out = []
    for r in rows[hi + 1:]:
        if not r or not r[0]:
            continue
        for k, pen in enumerate(pens):
            x, y = r[4 * k], r[4 * k + 1]
            if x == "" or y == "":
                continue
            tick = float(x)
            out.append(dict(pen=pen, tick=tick, value=float(y),
                            hour=SIM_START_HOUR + tick / TICKS_PER_HOUR))
    df = pd.DataFrame(out)
    df["pen"] = pd.Categorical(df["pen"], pens)
    return settings, df


def scenario_line(settings):
    return (f"{settings['decision-rule']}, {settings['fee-regime']}, "
            f"scale-factor {settings['scale-factor']}, seed {settings['current-seed']}, "
            f"retiming {settings['allow-retiming?']}, rerouting {settings['allow-rerouting?']}")


HOURS = dict(breaks=[5, 8, 11, 14, 17, 20, 23, 26, 29],
             labels=["05", "08", "11", "14", "17", "20", "23", "02", "05"])

# --- 1. CBD V/C over time --------------------------------------------------
path = os.path.join(TABLES, "cbd vc over time.csv")
settings, vc = read_netlogo_plot(path)
p = (ggplot(vc, aes("hour", "value", colour="pen"))
     + geom_line(size=0.8)
     + geom_hline(yintercept=0.85, linetype="dashed", colour="#c04040", size=0.5)
     + scale_colour_manual(values=["#2f6fa8", "#c0504d", "#4a8f5a"])
     + scale_x_continuous(**HOURS)
     + labs(title="CBD V/C over time, as NetLogo plots it",
            subtitle="One simulated day, per tick. The dashed line is the "
                     "V/C 0.85 congestion threshold.\nThe cordon boundary "
                     "carries the load; the interior barely moves.",
            x="clock hour", y="mean V/C",
            caption=scenario_line(settings))
     + theme(figure_size=(11, 4.0)) + BASE_THEME)
out = os.path.join(FIGS, "netlogo_cbd_vc_gg.png")
p.save(out, dpi=200, verbose=False)
print("wrote", out)

# --- 2. the two group plots, side by side ----------------------------------
frames = []
for fname, panel in [("mean flow vc.csv", "Mean flow V/C by group"),
                     ("%los.csv", "% of group traffic at LoS E/F")]:
    fpath = os.path.join(TABLES, fname)
    if not os.path.exists(fpath):
        print(f"(missing {fname})")
        continue
    s, df = read_netlogo_plot(fpath)
    df["panel"] = panel
    frames.append(df)
if frames:
    grp = pd.concat(frames, ignore_index=True)
    grp["panel"] = pd.Categorical(grp["panel"], [f["panel"].iloc[0] for f in frames])
    grp["pen"] = pd.Categorical(grp["pen"], ["MWY", "CBD", "East", "West"])
    p = (ggplot(grp, aes("hour", "value", colour="pen"))
         + geom_line(size=0.8)
         + facet_wrap("panel", scales="free_y")
         + scale_colour_manual(values=["#333333", "#c0504d", "#2f6fa8", "#4a8f5a"])
         + scale_x_continuous(**HOURS)
         + labs(title="Level of service by road group, as NetLogo plots it",
                subtitle="One simulated day, per tick. MWY is the motorway "
                         "corridors; CBD, East and West are arterial groups.\n"
                         "Flow V/C is an hour-long moving average, so it lags "
                         "the departure peak and decays slowly after it.",
                x="clock hour", y="",
                caption=scenario_line(settings))
         + theme(figure_size=(12, 4.2)) + BASE_THEME)
    out = os.path.join(FIGS, "netlogo_groups_gg.png")
    p.save(out, dpi=200, verbose=False)
    print("wrote", out)
