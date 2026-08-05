#!/usr/bin/env python3
"""Figure: the full attribute list an agent carries, grouped by what it drives.

A reference map rather than a result: four families of attribute, with how each
is generated. Distributions quoted are the measured ones from the agent-census
and agent-examples runs (seed 11), not the nominal slider values.

Built with plotnine: the tiles are geom_tile over a (column, row) grid and the
labels are two geom_text layers offset within each tile.

Writes output/figures/agent_attributes_gg.png
"""
import os

import pandas as pd
from plotnine import (ggplot, aes, geom_tile, geom_text, scale_fill_manual,
                      scale_colour_manual,
                      scale_x_continuous, scale_y_reverse, labs, theme, theme_void,
                      element_text, element_blank, element_rect)

HERE = os.path.dirname(os.path.abspath(__file__))
FIGS = os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

# column -> (header, subtitle, tile fill, ink for the attribute name)
COLUMNS = {
    1: ("ECONOMIC", "decides the fee response", "#FBE9E8", "#A03B38"),
    2: ("LEARNING STATE", "one family per rule", "#E8F1FA", "#1F5C8B"),
    3: ("ITINERARY", "rebuilt every simulated day", "#E8F3ED", "#2F6B4A"),
    4: ("MOVEMENT", "inherited from the base model", "#EEF2F6", "#475569"),
}

# (column, row, attribute, how it is generated)
ROWS = [
    (1, 1, "vot", "value of time, NZ$/h\nlognormal exp(N(2.3, 0.6)); median 9.67"),
    (1, 2, "beta", "price sensitivity\nclip(0.5 x medianVoT / vot, 0.1, 2.0)"),
    (1, 3, "base-trip-rate", "propensity with no charge\nUniform(0.3, 0.7); mean 0.50"),
    (1, 4, "essential-trip-prob", "fee-insensitive trip\n0.15 / 0.08 / 0.05 by VoT band"),
    (1, 5, "through?", "pass-through, never charged\n30 % of boundary agents; 544 of 2,500"),

    (2, 1, "el-weights, el-scores", "El Farol predictor set\n5 predictors, weights U(0, 1)"),
    (2, 2, "q-table", "Q-learning action values\n24 states x 4 actions, init U(-0.1, 0.1)"),
    (2, 3, "q-epsilon", "exploration rate\nstarts 0.40, decays x0.999 per day"),
    (2, 4, "q-action", "action chosen today\n0 stay out / 1 travel / 2 earlier / 3 later"),

    (3, 1, "v-home", "home building\nCensus sector shares; none inside the cordon"),
    (3, 2, "b-destinations", "the day's stops\nuniform draw, 1-4 plus home; 2.98 mean"),
    (3, 3, "depart-tick, return-tick", "clock-anchored departure\ndrawn from the hourly weight lists"),
    (3, 4, "trip-hour", "the hour the fee is charged\nread off the departure actually made"),
    (3, 5, "hour-shift", "today's retiming\n-1 / 0 / +1 hour, when retiming is on"),

    (4, 1, "location, destination", "position on the network\nnode-to-node along the current link"),
    (4, 2, "speed, top-speed", "current and free-flow speed\nBPR-damped by link V/C"),
    (4, 3, "trip", "the route being followed\ncached list of links per OD pair"),
    (4, 4, "active?, at-activity?", "on the road, or stopped\nactive? false ends the agent's day"),
    (4, 5, "tolerance, buffer-period", "delay tolerance, early start\ntruncated normal / U(0, max)"),
]

df = pd.DataFrame(ROWS, columns=["col", "row", "name", "detail"])
df["fill"] = df["col"].map(lambda c: COLUMNS[c][2])
df["ink"] = df["col"].map(lambda c: COLUMNS[c][3])

# Header band drawn as a row 0 tile so it shares the grid geometry.
hdr = pd.DataFrame([
    {"col": c, "row": 0, "name": COLUMNS[c][0], "detail": COLUMNS[c][1],
     "fill": COLUMNS[c][3], "ink": COLUMNS[c][3]} for c in COLUMNS
])

TILE_W, TILE_H = 0.94, 0.88
FILLS = {v[2]: v[2] for v in COLUMNS.values()} | {v[3]: v[3] for v in COLUMNS.values()}
INKS = {v[3]: v[3] for v in COLUMNS.values()}

p = (
    ggplot()
    # header band
    + geom_tile(hdr, aes(x="col", y="row", fill="fill"),
                width=TILE_W, height=0.60)
    + geom_text(hdr, aes(x="col", y="row - 0.10", label="name"),
                colour="white", size=10, fontweight="bold", ha="center")
    + geom_text(hdr, aes(x="col", y="row + 0.13", label="detail"),
                colour="white", size=7.6, ha="center")
    # attribute tiles
    + geom_tile(df, aes(x="col", y="row", fill="fill"),
                width=TILE_W, height=TILE_H)
    + geom_text(df, aes(x="col - 0.44", y="row - 0.26", label="name", colour="ink"),
                size=9.2, fontweight="bold", ha="left")
    + geom_text(df, aes(x="col - 0.44", y="row + 0.13", label="detail"),
                colour="#475569", size=7.8, ha="left", lineheight=1.35)
    + scale_fill_manual(values=FILLS, guide=None)
    # identity scale: the ink column already holds the hex we want
    + scale_colour_manual(values=INKS, guide=None)
    + scale_x_continuous(expand=(0, 0.06))
    + scale_y_reverse(expand=(0, 0.10))
    + theme_void()
    + theme(figure_size=(13.0, 4.6),
            plot_background=element_rect(fill="white", colour="none"),
            axis_text=element_blank(), axis_title=element_blank(),
            legend_position="none")
)

out = os.path.join(FIGS, "agent_attributes_gg.png")
p.save(out, dpi=190, verbose=False)
print("wrote", out)
