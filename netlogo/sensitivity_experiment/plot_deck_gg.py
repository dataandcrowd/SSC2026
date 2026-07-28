#!/usr/bin/env python3
"""Plotnine versions of the three charts used in the presentation deck.

  entry_trajectory_gg.png   cordon entry rate by simulated day, per rule
  hourly_profile_gg.png     hour-of-day inner-cordon V/C, no charge vs ToU
  arms_comparison_gg.png    ToU effect by arm, and the no-charge boundary load

The map figure stays in matplotlib: it draws network geometry, which is not a
grammar-of-graphics job.
"""
import csv, os, statistics as st
import pandas as pd
from plotnine import (ggplot, aes, geom_col, geom_line, geom_point, geom_text,
                      geom_rect, geom_hline, facet_wrap, labs, theme_minimal,
                      theme, element_text, element_blank, element_rect,
                      scale_colour_manual, scale_fill_manual, scale_x_continuous,
                      scale_y_continuous, position_dodge)

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

RULES = [("Exp-Decay", "Pay"), ("ElFarol", "Oscillate"), ("Q-Learning", "Learn")]
BURN_IN = 7
BASE_THEME = (theme_minimal()
              + theme(figure_size=(12, 4.4),
                      plot_title=element_text(size=12, weight="bold", ha="left"),
                      plot_subtitle=element_text(size=9, colour="#555555", ha="left"),
                      plot_caption=element_text(size=8, colour="#777777", ha="left"),
                      strip_text=element_text(size=10, weight="bold"),
                      strip_background=element_rect(fill="#eef3f8", colour="none"),
                      legend_position="top", legend_title=element_blank(),
                      panel_grid_minor=element_blank()))
FEE_COLOURS = ["#9e9e9e", "#2f6fa8"]


def read(kind, rule, fee, tag=""):
    path = os.path.join(TABLES, f"{kind}_{rule}_{fee}{tag}.csv")
    return list(csv.DictReader(open(path))) if os.path.exists(path) else None


# --- 1. entry trajectory ---------------------------------------------------
rows = []
for rule, short in RULES:
    for fee, lab in [("No-Charge", "No charge"), ("tou", "ToU")]:
        d = read("days", rule, fee)
        if not d:
            continue
        for r in d:
            rows.append(dict(rule=short, series=lab, day=int(float(r["day"])),
                             value=float(r["attendance"])))
df = pd.DataFrame(rows)
df["rule"] = pd.Categorical(df["rule"], [s for _, s in RULES])
df["series"] = pd.Categorical(df["series"], ["No charge", "ToU"])
ends = df[df["day"] == df["day"].max()].copy()
ends["label"] = ends["value"].map(lambda v: f"{v:.2f}")

p = (ggplot(df, aes("day", "value", colour="series"))
     + geom_line(size=1.1) + geom_point(size=1.8)
     + geom_text(ends, aes(label="label"), nudge_x=0.9, size=8, show_legend=False)
     + facet_wrap("rule")
     + scale_colour_manual(values=FEE_COLOURS)
     + scale_x_continuous(breaks=[2, 4, 6, 8, 10, 12, 14], limits=(0.5, 16))
     + scale_y_continuous(limits=(0, 1))
     + labs(title="The charge acts immediately under Pay, cumulatively under "
                  "Learn, and is undone under Oscillate",
            subtitle="Share of agents entering the cordon, by simulated day.\n"
                     "Learn starts at the no-charge level because the fee never "
                     "enters its decision, only its reward.",
            x="simulated day", y="share entering the cordon")
     + BASE_THEME)
out = os.path.join(FIGS, "entry_trajectory_gg.png")
p.save(out, dpi=200, verbose=False)
print("wrote", out)

# --- 2. hour-of-day profile ------------------------------------------------
rows = []
for rule, short in RULES:
    for fee, lab in [("No-Charge", "No charge"), ("tou", "ToU")]:
        d = read("hourly", rule, fee)
        if not d:
            continue
        by_hour = {}
        for r in d:
            if int(float(r["day"])) <= BURN_IN:
                continue
            by_hour.setdefault(int(float(r["hour"])), []).append(float(r["vc_inner"]))
        for h, vals in by_hour.items():
            rows.append(dict(rule=short, series=lab, hour=h,
                             value=sum(vals) / len(vals)))
prof = pd.DataFrame(rows)
prof["rule"] = pd.Categorical(prof["rule"], [s for _, s in RULES])
prof["series"] = pd.Categorical(prof["series"], ["No charge", "ToU"])
peaks = pd.DataFrame([dict(xmin=8, xmax=9), dict(xmin=16, xmax=18)])

p = (ggplot(prof, aes("hour", "value"))
     + geom_rect(peaks, aes(xmin="xmin", xmax="xmax", ymin=-float("inf"),
                            ymax=float("inf")), inherit_aes=False,
                 fill="#c04040", alpha=0.08)
     + geom_line(aes(colour="series"), size=1.1)
     + geom_point(aes(colour="series"), size=1.6)
     + facet_wrap("rule")
     + scale_colour_manual(values=FEE_COLOURS)
     + scale_x_continuous(breaks=[0, 3, 6, 9, 12, 15, 18, 21, 24])
     + labs(title="Where within the day the charge acts",
            subtitle="Mean inner-cordon V/C by hour, days 8-14. Shaded bands are "
                     "the peak fee windows.\nThe whole-day mean falls as much as "
                     "the peaks do, so the charge deters trips rather than "
                     "spreading them.",
            x="hour of day", y="mean inner-cordon V/C")
     + BASE_THEME)
out = os.path.join(FIGS, "hourly_profile_gg.png")
p.save(out, dpi=200, verbose=False)
print("wrote", out)

# --- 3. arms comparison ----------------------------------------------------
ARMS = [("", "fixed hour, fixed route"), ("_rt", "may retime"),
        ("_rr", "may reroute"), ("_rt_rr", "both")]
rows = []
for tag, arm in ARMS:
    for rule, short in RULES:
        nc, tou = read("days", rule, "No-Charge", tag), read("days", rule, "tou", tag)
        if not nc or not tou:
            continue
        m = lambda d, f: st.mean(float(r[f]) for r in d)
        rows.append(dict(rule=short, arm=arm, panel="ToU reduction in peak inner V/C (%)",
                         value=100 * (m(nc, "vc_inner") - m(tou, "vc_inner")) / m(nc, "vc_inner")))
        rows.append(dict(rule=short, arm=arm, panel="No-charge peak V/C on the cordon boundary",
                         value=m(nc, "vc_boundary")))
arms = pd.DataFrame(rows)
arms["rule"] = pd.Categorical(arms["rule"], [s for _, s in RULES])
arms["arm"] = pd.Categorical(arms["arm"], [a for _, a in ARMS])
# facets are ordered alphabetically unless told otherwise, which would put the
# boundary panel first and contradict the caption
arms["panel"] = pd.Categorical(arms["panel"],
                               ["ToU reduction in peak inner V/C (%)",
                                "No-charge peak V/C on the cordon boundary"])
arms["label"] = arms.apply(lambda r: f'{r["value"]:.0f}' if "%" in r["panel"]
                           else f'{r["value"]:.2f}', axis=1)

p = (ggplot(arms, aes("rule", "value", fill="arm"))
     + geom_col(position=position_dodge(width=0.85), width=0.8)
     + geom_text(aes(label="label", group="arm"),
                 position=position_dodge(width=0.85), va="bottom", size=7)
     + geom_hline(yintercept=0, colour="black", size=0.4)
     + facet_wrap("panel", scales="free_y")
     + scale_fill_manual(values=["#9e9e9e", "#4878a8", "#c07a3a", "#4a8f5a"])
     + scale_y_continuous(expand=(0.02, 0, 0.14, 0))
     + labs(title="What we let agents do changes the answer",
            subtitle="Same network, population and fee schedule; only the set of "
                     "permitted responses differs.\nPay is robust at 12-26 %; "
                     "Learn swings from 39 % to 14 %; Oscillate is zero "
                     "throughout.",
            x="", y="")
     + BASE_THEME)
out = os.path.join(FIGS, "arms_comparison_gg.png")
p.save(out, dpi=200, verbose=False)
print("wrote", out)
