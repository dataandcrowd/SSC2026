#!/usr/bin/env python3
"""Same three figures as plot_equity_optin.py, drawn with plotnine.

  equity_by_income_gg.png   who the charge removes, by value-of-time quintile
  optin_retiming_gg.png     peak V/C and entry rate, departure hour fixed vs free
  optin_rerouting_gg.png    the same for fixed vs congestion-dependent routes

The equity panels are DERIVED from the model's decision and reward functions
applied to the calibrated VoT distribution; the opt-in panels are MEASURED in
the 14-day runs.
"""
import csv, math, os, random, statistics as st
import pandas as pd
from plotnine import (ggplot, aes, geom_col, geom_line, geom_point, geom_text,
                      geom_hline, facet_wrap, labs, scale_fill_manual,
                      scale_colour_manual, scale_y_continuous, theme_minimal,
                      theme, element_text, element_blank, element_rect,
                      position_dodge, expand_limits)

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

RULES = [("Exp-Decay", "Pay"), ("ElFarol", "Oscillate"), ("Q-Learning", "Learn")]
N_AGENTS, BASE_BETA, VC = 2500, 0.5, 0.12

BASE_THEME = (theme_minimal()
              + theme(figure_size=(12, 4.6),
                      plot_title=element_text(size=12, weight="bold", ha="left"),
                      plot_subtitle=element_text(size=9, colour="#555555", ha="left"),
                      plot_caption=element_text(size=8, colour="#777777", ha="left"),
                      strip_text=element_text(size=10, weight="bold"),
                      strip_background=element_rect(fill="#eef3f8", colour="none"),
                      legend_position="top",
                      legend_title=element_blank(),
                      panel_grid_minor=element_blank()))

# ------------------------------------------------------------ equity data --
random.seed(11)
N = 200000
vots = [math.exp(random.gauss(2.3, 0.6)) for _ in range(N)]
srt = sorted(vots)
cuts = [srt[int(k * N / 5)] for k in range(1, 5)]
med, q20, q80 = st.median(vots), srt[int(.2 * N)], srt[int(.8 * N)]
pop = [(v, min(max(BASE_BETA * (med / v), 0.1), 2.0), random.uniform(0.3, 0.7),
        0.15 if v <= q20 else (0.05 if v >= q80 else 0.08)) for v in vots]
groups = [[] for _ in range(5)]
for a in pop:
    groups[sum(a[0] >= c for c in cuts)].append(a)
band = [f"Q{i+1}\n${st.median([a[0] for a in groups[i]]):.0f}/h" for i in range(5)]


def p_enter(a, fee):
    v, beta, btr, ess = a
    p = min(max(btr * math.exp(-beta * fee / v), 0.05), 0.95)
    return ess * max(p, 0.8) + (1 - ess) * p


def q_gap(v, fee, benefit):
    r = benefit(v) - fee - VC * 3.0
    if fee > v:
        r -= (fee - v) * 1.5
    return r - (0.3 - 0.15 * (v / 10.0))


FEE_LABELS = ["no charge", r"\$2 off-peak", r"\$4 shoulder", r"\$6 peak"]
rows = []
for i, g in enumerate(groups):
    for fee, lab in zip([0, 2, 4, 6], FEE_LABELS):
        rows.append(dict(band=band[i], series=lab,
                         value=sum(p_enter(a, fee) for a in g) / len(g) * N_AGENTS / 5))
pay_df = pd.DataFrame(rows)
pay_df["series"] = pd.Categorical(pay_df["series"], FEE_LABELS)
pay_df["panel"] = "Pay — agents still entering (of 500 per quintile)"

drop = [dict(band=band[i], panel=pay_df["panel"][0],
             label=f"−{100 * (sum(p_enter(a, 0) for a in g) - sum(p_enter(a, 6) for a in g)) / sum(p_enter(a, 0) for a in g):.0f}%")
        for i, g in enumerate(groups)]
drop_df = pd.DataFrame(drop)
drop_df["value"] = 8.0

BENEFITS = [("as implemented (benefit = VoT/10)", lambda v: v / 10.0),
            ("benefit = half an hour of VoT", lambda v: v * 0.5)]
rows = []
for i, g in enumerate(groups):
    v = st.median([a[0] for a in g])
    for lab, fn in BENEFITS:
        rows.append(dict(band=band[i], series=lab, value=q_gap(v, 6, fn)))
learn_df = pd.DataFrame(rows)
learn_df["series"] = pd.Categorical(learn_df["series"], [b[0] for b in BENEFITS])
learn_df["panel"] = "Learn — value of entering at the peak fee (NZD)"

panels = [pay_df["panel"][0], learn_df["panel"][0]]
for d in (pay_df, drop_df, learn_df):
    d["panel"] = pd.Categorical(d["panel"], panels)

p = (ggplot(mapping=aes("band", "value"))
     + geom_col(pay_df, aes(fill="series"), position=position_dodge(width=0.85),
                width=0.8)
     + geom_text(drop_df, aes(label="label"), colour="#b03a2e", size=8,
                 fontweight="bold")
     + geom_hline(learn_df.iloc[[0]], yintercept=0, colour="black", size=0.5)
     + geom_line(learn_df, aes(colour="series", group="series"), size=1.1)
     + geom_point(learn_df, aes(colour="series"), size=2.5)
     + facet_wrap("panel", scales="free_y")
     + scale_fill_manual(values=["#b8b8b8", "#8fb2cf", "#d19a4e", "#c0504d"])
     + scale_colour_manual(values=["#c0504d", "#4878a8"])
     + labs(title="Who the charge removes from the road",
            subtitle="Value-of-time quintile, Q1 = lowest income. The price rule "
                     "deters the poorest ten times as strongly.\n"
                     "The learner deters every band alike, but only because its "
                     "reward values a commute at a tenth of an hour.",
            x="value-of-time quintile", y="",
            caption="Derived from the model's decision and reward functions "
                    "applied to the calibrated VoT distribution — not measured "
                    "in a run.")
     + BASE_THEME)
out = os.path.join(FIGS, "equity_by_income_gg.png")
p.save(out, dpi=200, verbose=False)
print("wrote", out)


# ------------------------------------------------------------- opt-in data --
def days(rule, fee, tag):
    path = os.path.join(TABLES, f"days_{rule}_{fee}{tag}.csv")
    return list(csv.DictReader(open(path))) if os.path.exists(path) else None


def optin(tag, off_label, on_label, title, subtitle, fname):
    order = [f"no charge, {off_label}", f"ToU, {off_label}",
             f"no charge, {on_label}", f"ToU, {on_label}"]
    rows = []
    for tg, fee, lab in [("", "No-Charge", order[0]), ("", "tou", order[1]),
                         (tag, "No-Charge", order[2]), (tag, "tou", order[3])]:
        for rule, short in RULES:
            d = days(rule, fee, tg)
            if not d:
                continue
            rows.append(dict(rule=short, series=lab, panel="daily peak inner-cordon V/C",
                             value=st.mean(float(r["vc_inner"]) for r in d)))
            rows.append(dict(rule=short, series=lab, panel="share of agents entering",
                             value=st.mean(float(r["attendance"]) for r in d)))
    df = pd.DataFrame(rows)
    df["series"] = pd.Categorical(df["series"], order)
    df["rule"] = pd.Categorical(df["rule"], [s for _, s in RULES])
    df["label"] = df.apply(lambda r: f'{r["value"]:.3f}'
                           if "V/C" in r["panel"] else f'{r["value"]:.2f}', axis=1)
    p = (ggplot(df, aes("rule", "value", fill="series"))
         + geom_col(position=position_dodge(width=0.85), width=0.8)
         # group= is required or the labels ignore the dodge and stack up
         + geom_text(aes(label="label", group="series"),
                     position=position_dodge(width=0.85),
                     va="bottom", size=7)
         + facet_wrap("panel", scales="free_y")
         + scale_fill_manual(values=["#c9c9c9", "#8a8a8a", "#8fb8dc", "#2f6fa8"])
         + scale_y_continuous(expand=(0.02, 0, 0.14, 0))
         + labs(title=title, subtitle=subtitle, x="", y="")
         + BASE_THEME)
    out = os.path.join(FIGS, fname)
    p.save(out, dpi=200, verbose=False)
    print("wrote", out)


optin("_rt", "fixed hour", "may retime",
      "Departure-time choice changes how many trips are made",
      "Pay's entry rate is unchanged because only 2.5 % of its entrants shift.\n"
      "Learn's jumps from 0.34 to 0.62: given somewhere to move, it stops "
      "forgoing the trip, and the measured congestion benefit falls with it.",
      "optin_retiming_gg.png")
optin("_rr", "fixed route", "may reroute",
      "Route choice changes where the trips go, not how many there are",
      "Entry rates are nearly identical in both arms.\n"
      "What moves is the no-charge baseline: inner V/C rises while the cordon "
      "boundary sheds two fifths of its load.",
      "optin_rerouting_gg.png")
