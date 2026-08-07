#!/usr/bin/env python3
"""Q3 in one figure: what the ToU charge appears to achieve, by behavioural margin.

Diverging lollipops, computed live from the days_* tables so the figure can
never drift from the data. Rows are the three measures that tell the story
(inner peak, boundary peak, entries), columns the three rules, and within a
panel the four arms (what agents are allowed to do). Blue = reduction under
ToU, red = increase — the same polarity convention as the redistribution map.
Sign is also encoded by direction from the zero line, so colour is never the
only carrier.

Writes q3_margins_gg.png
"""
import os
import pandas as pd
from plotnine import (ggplot, aes, geom_segment, geom_point, geom_text,
                      geom_vline, facet_grid, labs, theme_minimal, theme,
                      element_text, element_blank, element_rect,
                      scale_colour_manual, scale_x_continuous,
                      scale_y_discrete, coord_cartesian)

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

RULES = [("Exp-Decay", "Pay"), ("ElFarol", "Oscillate"), ("Q-Learning", "Learn")]
ARMS = [("", "base\n(forgo only)"), ("_rt", "+ retime"), ("_rr", "+ reroute"),
        ("_rt_rr", "+ both")]
MEASURES = [("vc_inner", "inner peak V/C"), ("vc_boundary", "boundary peak V/C"),
            ("attendance", "CBD entries")]
NOISE = 5.0  # |change| below this is within day-to-day noise -> grey

rows = []
for rule, rlab in RULES:
    for arm, alab in ARMS:
        nc = pd.read_csv(os.path.join(TABLES, f"days_{rule}_No-Charge{arm}.csv"))
        tou = pd.read_csv(os.path.join(TABLES, f"days_{rule}_tou{arm}.csv"))
        for col, mlab in MEASURES:
            pct = 100 * (tou[col].mean() / nc[col].mean() - 1)
            rows.append(dict(rule=rlab, arm=alab, measure=mlab, pct=pct))
df = pd.DataFrame(rows)
df["rule"] = pd.Categorical(df["rule"], [r for _, r in RULES])
df["arm"] = pd.Categorical(df["arm"], [a for _, a in ARMS][::-1])  # base on top
df["measure"] = pd.Categorical(df["measure"], [m for _, m in MEASURES])
df["sign"] = pd.cut(df.pct, [-100, -NOISE, NOISE, 100],
                    labels=["falls", "within noise", "rises"])
df["lab"] = df.pct.map(lambda v: f"{v:+.0f}%")
df["lab_x"] = df.pct + df.pct.map(lambda v: 6.5 if v >= 0 else -6.5)

p = (ggplot(df, aes("pct", "arm"))
     + geom_vline(xintercept=0, colour="#9a988f", size=0.6)
     + geom_segment(aes(x=0, xend="pct", y="arm", yend="arm", colour="sign"),
                    size=1.6, show_legend=False)
     + geom_point(aes(colour="sign"), size=3.4)
     + geom_text(aes(x="lab_x", label="lab", colour="sign"), size=8.2,
                 show_legend=False)
     + facet_grid("measure ~ rule")
     + scale_colour_manual(values={"falls": "#2f6fa8", "rises": "#c0504d",
                                   "within noise": "#9e9e9e"},
                           limits=["falls", "within noise", "rises"],
                           labels=["falls under ToU", "within day-to-day noise",
                                   "rises under ToU"])
     + scale_x_continuous(breaks=[-40, -20, 0, 20, 40],
                          labels=lambda l: [f"{v:+.0f}%" for v in l])
     + coord_cartesian(xlim=(-47, 36))
     + labs(title="What the charge appears to achieve depends on what drivers may do",
            subtitle="ToU change vs no charge (14-day means) when agents may only forgo the trip (base), also\n"
                     "shift departure by ±1 h (+ retime), also choose routes by congestion (+ reroute), or both.\n"
                     "Learn's −24 % needs forgoing to be the only option; displacement appears only for\n"
                     "Oscillate + reroute; Pay's entry cut is invariant across every arm.",
            x="change under ToU", y="",
            caption="Calibrated model, 14 simulated days, one seed; base cells from the "
                    "2026-08-06 morning batch,\narm cells from the 2026-08-06 evening "
                    "batch (same model). Grey = |change| < 5 %, within day-to-day SD.")
     + theme_minimal()
     + theme(plot_title=element_text(size=12, weight="bold", ha="left"),
             plot_subtitle=element_text(size=9, colour="#555555", ha="left"),
             plot_caption=element_text(size=8, colour="#777777", ha="left"),
             strip_text=element_text(size=9.5, weight="bold"),
             strip_background=element_rect(fill="#eef3f8", colour="none"),
             legend_position="top", legend_title=element_blank(),
             panel_grid_minor=element_blank(),
             panel_grid_major_y=element_blank(),
             axis_text_y=element_text(size=8.5),
             figure_size=(11, 7)))
out = os.path.join(FIGS, "q3_margins_gg.png")
p.save(out, dpi=200, verbose=False)
print("wrote", out)
