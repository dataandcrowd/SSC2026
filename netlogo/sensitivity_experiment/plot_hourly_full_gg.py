#!/usr/bin/env python3
"""Hour-of-day profiles for all three rules, no charge against ToU, in plotnine.

Reads the widened `save-hourly` export (experiment `hourly-full`), which now
carries, per simulated day and clock hour: inner / boundary / peripheral V/C,
and per reporting group the flow V/C and the % of traffic at LoS E/F.

Each line is the mean across the 14 simulated days and the band is ± one
standard deviation across those days, so the spread is day-to-day variation
within one seed — not run-to-run uncertainty.

Writes
  hourly_positions_gg.png   inner / boundary / peripheral, rule x position
  hourly_group_vcf_gg.png   flow V/C by reporting group
  hourly_group_ef_gg.png    % of group traffic at LoS E/F
"""
import os
import pandas as pd
from plotnine import (ggplot, aes, geom_line, geom_ribbon, geom_rect, facet_grid,
                      labs, theme_minimal, theme, element_text, element_blank,
                      element_rect, scale_colour_manual, scale_fill_manual,
                      scale_x_continuous)

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

RULES = [("Exp-Decay", "Pay"), ("ElFarol", "Oscillate"), ("Q-Learning", "Learn")]
FEES = [("No-Charge", "No charge"), ("tou", "ToU")]
COLOURS = ["#9e9e9e", "#2f6fa8"]
PEAKS = pd.DataFrame([dict(xmin=8, xmax=9), dict(xmin=16, xmax=18)])
BASE_THEME = (theme_minimal()
              + theme(plot_title=element_text(size=12, weight="bold", ha="left"),
                      plot_subtitle=element_text(size=9, colour="#555555", ha="left"),
                      plot_caption=element_text(size=8, colour="#777777", ha="left"),
                      strip_text=element_text(size=9.5, weight="bold"),
                      strip_background=element_rect(fill="#eef3f8", colour="none"),
                      legend_position="top", legend_title=element_blank(),
                      panel_grid_minor=element_blank()))


def load():
    frames = []
    for rule, short in RULES:
        for fee, flab in FEES:
            path = os.path.join(TABLES, f"hourly_{rule}_{fee}.csv")
            if not os.path.exists(path):
                continue
            df = pd.read_csv(path)
            df["rule"], df["fee"] = short, flab
            frames.append(df)
    if not frames:
        raise SystemExit("no hourly_*.csv found — run the hourly-full experiment")
    out = pd.concat(frames, ignore_index=True)
    if "vc_boundary" not in out.columns:
        raise SystemExit("hourly_*.csv predates the widened export — re-run "
                         "hourly-full before plotting")
    return out


def summarise(df, series):
    """mean and ±1 SD across days, per rule x fee x hour, for the given columns."""
    long = df.melt(id_vars=["rule", "fee", "day", "hour"], value_vars=list(series),
                   var_name="series", value_name="value")
    g = (long.groupby(["rule", "fee", "hour", "series"], observed=True)["value"]
              .agg(["mean", "std"]).reset_index())
    g["lo"] = g["mean"] - g["std"].fillna(0)
    g["hi"] = g["mean"] + g["std"].fillna(0)
    g["rule"] = pd.Categorical(g["rule"], [s for _, s in RULES])
    g["fee"] = pd.Categorical(g["fee"], [f for _, f in FEES])
    return g


def draw(g, labels, title, subtitle, ylab, fname, clip_zero=False):
    g = g.copy()
    g["series"] = pd.Categorical(g["series"].map(labels), list(labels.values()))
    if clip_zero:
        g["lo"] = g["lo"].clip(lower=0)
    p = (ggplot(g, aes("hour", "mean"))
         + geom_rect(PEAKS, aes(xmin="xmin", xmax="xmax", ymin=-float("inf"),
                                ymax=float("inf")), inherit_aes=False,
                     fill="#c04040", alpha=0.07)
         + geom_ribbon(aes(ymin="lo", ymax="hi", fill="fee"), alpha=0.20,
                       colour=None)
         + geom_line(aes(colour="fee"), size=1.0)
         + facet_grid("series ~ rule", scales="free_y")
         + scale_colour_manual(values=COLOURS)
         + scale_fill_manual(values=COLOURS)
         + scale_x_continuous(breaks=[0, 6, 12, 18, 24])
         + labs(title=title, subtitle=subtitle, x="hour of day", y=ylab,
                caption="Line = mean of 14 simulated days, band = ±1 SD across "
                        "those days (one seed).\nShaded columns are the peak fee "
                        "windows.")
         + theme(figure_size=(11, 7.2)) + BASE_THEME)
    out = os.path.join(FIGS, fname)
    p.save(out, dpi=200, verbose=False)
    print("wrote", out)


GROUP_COLOUR = {"MWY": "#222222", "CBD": "#c0504d",
                "East": "#2f6fa8", "West": "#4a8f5a"}


def draw_groups(g, labels, colours, title, subtitle, ylab, fname):
    """Groups as coloured lines inside one panel, fee regimes as rows.

    Series belong on the same axes when the question is which one is worse and
    by how much, which separate rows with free scales cannot answer.
    """
    g = g.copy()
    g["series"] = pd.Categorical(g["series"].map(labels), list(labels.values()))
    g["lo"] = g["lo"].clip(lower=0)
    p = (ggplot(g, aes("hour", "mean", colour="series", fill="series"))
         + geom_rect(PEAKS, aes(xmin="xmin", xmax="xmax", ymin=-float("inf"),
                                ymax=float("inf")), inherit_aes=False,
                     fill="#c04040", alpha=0.07)
         + geom_ribbon(aes(ymin="lo", ymax="hi"), alpha=0.13, colour=None)
         + geom_line(size=1.0)
         + facet_grid("fee ~ rule")
         + scale_colour_manual(values=colours)
         + scale_fill_manual(values=colours)
         + scale_x_continuous(breaks=[0, 6, 12, 18, 24])
         + labs(title=title, subtitle=subtitle, x="hour of day", y=ylab,
                caption="Line = mean of 14 simulated days, band = ±1 SD across "
                        "those days (one seed).\nShaded columns are the peak fee "
                        "windows. Rows share a scale, so read top against bottom.")
         + theme(figure_size=(11, 5.4)) + BASE_THEME)
    out = os.path.join(FIGS, fname)
    p.save(out, dpi=200, verbose=False)
    print("wrote", out)


df = load()

POSITION_COLOUR = {"cordon boundary": "#c0504d", "inner": "#2f6fa8",
                   "peripheral": "#4a8f5a"}

draw_groups(summarise(df, ["vc_boundary", "vc_inner", "vc_peripheral"]),
            {"vc_boundary": "cordon boundary", "vc_inner": "inner",
             "vc_peripheral": "peripheral"}, POSITION_COLOUR,
            "Where and when the charge bites, by cordon position",
            "All three positions on one axis. The cordon boundary carries five "
            "to six times the\nload of the interior it protects, which is the "
            "point — on a shared scale the inner\nand peripheral curves are "
            "necessarily flat.",
            "mean V/C", "hourly_positions_gg.png")

draw_groups(summarise(df, ["vcf_mwy", "vcf_cbd", "vcf_east", "vcf_west"]),
            {"vcf_mwy": "MWY", "vcf_cbd": "CBD", "vcf_east": "East",
             "vcf_west": "West"}, GROUP_COLOUR,
            "Flow V/C by road group through the day",
            "All four groups on one axis so they can be compared. MWY is the "
            "motorway corridors,\nthe rest are arterial. The measure is an "
            "hour-long moving average, so each curve\nlags the departure peak.",
            "flow V/C", "hourly_group_vcf_gg.png")

draw_groups(summarise(df, ["ef_mwy", "ef_cbd", "ef_east", "ef_west"]),
            {"ef_mwy": "MWY", "ef_cbd": "CBD", "ef_east": "East",
             "ef_west": "West"}, GROUP_COLOUR,
            "Share of traffic at LoS E or worse, by road group",
            "Flow-weighted, all four groups on one axis. Arterials sit worse "
            "than the motorway\ncorridors all day. Absolute levels are inflated "
            "by the temporal residual — read\nthe top row against the bottom.",
            "% of traffic at LoS E/F", "hourly_group_ef_gg.png")
