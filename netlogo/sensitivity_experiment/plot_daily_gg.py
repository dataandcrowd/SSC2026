#!/usr/bin/env python3
"""Day-by-day peak V/C, no charge against ToU, for the three rules.

Reads the `save-records` daily export (days_<Rule>_<fee>.csv, base arm:
fixed departure hour and route). One point per simulated day, so nothing
is averaged away: the gap between the two lines IS the daily-peak effect
quoted in the results matrix (Pay -12 %, Oscillate 0 %, Learn -39 %).

Writes
  daily_peak_gg.png   rows = cordon position, cols = rule, x = day
"""
import os
import pandas as pd
from plotnine import (ggplot, aes, geom_line, geom_point, facet_grid, labs,
                      theme_minimal, theme, element_text, element_blank,
                      element_rect, scale_colour_manual, scale_x_continuous)

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

RULES = [("Exp-Decay", "Pay"), ("ElFarol", "Oscillate"), ("Q-Learning", "Learn")]
FEES = [("No-Charge", "No charge"), ("tou", "ToU")]
COLOURS = ["#9e9e9e", "#2f6fa8"]
POSITIONS = {"vc_inner": "inner", "vc_boundary": "cordon boundary",
             "vc_peripheral": "peripheral"}

frames = []
for rule, short in RULES:
    for fee, flab in FEES:
        path = os.path.join(TABLES, f"days_{rule}_{fee}.csv")
        df = pd.read_csv(path)
        df["rule"], df["fee"] = short, flab
        frames.append(df)
df = pd.concat(frames, ignore_index=True)

long = df.melt(id_vars=["rule", "fee", "day"], value_vars=list(POSITIONS),
               var_name="position", value_name="peak_vc")
long["position"] = pd.Categorical(long["position"].map(POSITIONS),
                                  list(POSITIONS.values()))
long["rule"] = pd.Categorical(long["rule"], [s for _, s in RULES])
long["fee"] = pd.Categorical(long["fee"], [f for _, f in FEES])

p = (ggplot(long, aes("day", "peak_vc", colour="fee"))
     + geom_line(size=0.9)
     + geom_point(size=1.6)
     + facet_grid("position ~ rule", scales="free_y")
     + scale_colour_manual(values=COLOURS)
     + scale_x_continuous(breaks=[1, 4, 7, 10, 14])
     + labs(title="Daily peak V/C, day by day: no charge against ToU",
            subtitle="One point per simulated day — nothing averaged away. The gap "
                     "between the lines is the\ndaily-peak effect quoted in the "
                     "results matrix: Pay −12 %, Oscillate 0 %, Learn −39 % "
                     "(inner).",
            x="simulated day", y="daily peak V/C",
            caption="Calibrated model, base arm (fixed departure hour and route), "
                    "one seed.\nRows have their own scale: the cordon boundary "
                    "carries several times the load of the interior.")
     + theme_minimal()
     + theme(plot_title=element_text(size=12, weight="bold", ha="left"),
             plot_subtitle=element_text(size=9, colour="#555555", ha="left"),
             plot_caption=element_text(size=8, colour="#777777", ha="left"),
             strip_text=element_text(size=9.5, weight="bold"),
             strip_background=element_rect(fill="#eef3f8", colour="none"),
             legend_position="top", legend_title=element_blank(),
             panel_grid_minor=element_blank(),
             figure_size=(11, 6.5)))
out = os.path.join(FIGS, "daily_peak_gg.png")
p.save(out, dpi=400, verbose=False)
print("wrote", out)
