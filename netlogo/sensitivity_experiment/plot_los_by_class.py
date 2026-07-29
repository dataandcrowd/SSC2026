#!/usr/bin/env python3
"""Level of service on motorways against arterials.

Two views of the same question, because the model measures it two ways and they
disagree in an informative way:

  left   the mix of peak LoS grades A-F across links, by road class. Counts
         links, so a quiet lane weighs the same as a motorway carriageway.
  right  the flow-weighted share of traffic at LoS E or worse, by reporting
         group (MWY is the motorway corridors; CBD, East and West are
         arterials), as recorded each day by the model itself.

The class-specific HCM thresholds mean an arterial grades E from V/C 0.82 while
a motorway grades E from 0.90, so arterials are expected to sit worse; the
point of the figure is how much the charge moves each.

Reads  output/tables/links_<Rule>_<fee>.csv
       output/tables/paper-figs.csv
Writes output/figures/los_by_class_gg.png
"""
import collections, csv, os, statistics as st
import pandas as pd
from plotnine import (ggplot, aes, geom_col, geom_text, facet_grid, facet_wrap,
                      labs, theme_minimal, theme, element_text, element_blank,
                      element_rect, scale_fill_manual, scale_y_continuous,
                      position_dodge, coord_flip)

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

RULES = [("Exp-Decay", "Pay"), ("ElFarol", "Oscillate"), ("Q-Learning", "Learn")]
GRADES = ["A", "B", "C", "D", "E", "F"]
GRADE_COLOUR = dict(zip("ABCDEF",
                        ["#4a9a4a", "#a5c85a", "#f2d349",
                         "#e8973a", "#d64545", "#7d1f1f"]))
BASE_THEME = (theme_minimal()
              + theme(plot_title=element_text(size=12, weight="bold", ha="left"),
                      plot_subtitle=element_text(size=9, colour="#555555", ha="left"),
                      plot_caption=element_text(size=8, colour="#777777", ha="left"),
                      strip_text=element_text(size=9.5, weight="bold"),
                      strip_background=element_rect(fill="#eef3f8", colour="none"),
                      legend_position="top", legend_title=element_blank(),
                      panel_grid_minor=element_blank()))

# --- 1. grade mix across links, by class ----------------------------------
rows = []
for rule, short in RULES:
    for fee, flab in [("No-Charge", "no charge"), ("tou", "ToU")]:
        path = os.path.join(TABLES, f"links_{rule}_{fee}.csv")
        if not os.path.exists(path):
            continue
        links = list(csv.DictReader(open(path)))
        for cls, clab in [("motorway", "Motorway"), ("arterial", "Arterial")]:
            sel = [r for r in links if r["class"] == cls]
            n = len(sel)
            counts = collections.Counter(r["los_peak"] for r in sel)
            for g in GRADES:
                rows.append(dict(rule=short, fee=flab, cls=f"{clab} (n={n})",
                                 grade=g, share=100 * counts[g] / n))
mix = pd.DataFrame(rows)
mix["rule"] = pd.Categorical(mix["rule"], [s for _, s in RULES])
mix["fee"] = pd.Categorical(mix["fee"], ["no charge", "ToU"])
mix["grade"] = pd.Categorical(mix["grade"], GRADES[::-1])  # A ends up at the bottom of the stack
mix["cls"] = pd.Categorical(mix["cls"], sorted(mix["cls"].unique(), reverse=True))

p = (ggplot(mix, aes("fee", "share", fill="grade"))
     + geom_col(width=0.7)
     + facet_grid("cls ~ rule")
     # dict values, or plotnine matches colours to `breaks` order, not levels
     + scale_fill_manual(values=GRADE_COLOUR, breaks=GRADES)
     + labs(title="Peak level of service by road class",
            subtitle="Share of links at each grade, daily peak of the flow V/C, "
                     "days 1-14.\nArterials grade stricter (LoS E from V/C 0.82 "
                     "against 0.90 on a motorway) and start worse.",
            x="", y="% of links",
            caption="Counts links, so a side street weighs as much as a "
                    "motorway carriageway — see the flow-weighted panel.")
     + theme(figure_size=(11, 5.6)) + BASE_THEME)
out = os.path.join(FIGS, "los_by_class_gg.png")
p.save(out, dpi=200, verbose=False)
print("wrote", out)

# --- 2. flow-weighted E/F share by reporting group -------------------------
path = os.path.join(TABLES, "paper-figs.csv")
if not os.path.exists(path):
    print("(skip flow-weighted panel: paper-figs.csv missing)")
    raise SystemExit
raw = list(csv.reader(open(path)))
hi = [i for i, r in enumerate(raw) if r and r[0] == "[run number]"][0]
cols = raw[hi]
data = [dict(zip(cols, r)) for r in raw[hi + 1:] if len(r) == len(cols)]
agg = collections.defaultdict(list)
for d in data:
    if int(float(d["[step]"])) == 0:
        continue
    agg[(d["decision-rule"], d["fee-regime"])].append(d)

GROUPS = [("peak-ef-mwy", "MWY\n(motorway)"), ("peak-ef-cbd", "CBD\n(arterial)"),
          ("peak-ef-east", "East\n(arterial)"), ("peak-ef-west", "West\n(arterial)")]
NAME = {"Exp-Decay": "Pay", "El Farol": "Oscillate", "Q-Learning": "Learn"}
rows = []
for rule, short in NAME.items():
    for metric, glab in GROUPS:
        for fee, flab in [("No-Charge", "no charge"), ("tou", "ToU")]:
            if (rule, fee) not in agg:
                continue
            rows.append(dict(rule=short, group=glab, fee=flab,
                             value=st.mean(float(d[metric]) for d in agg[(rule, fee)])))
ef = pd.DataFrame(rows)
ef["rule"] = pd.Categorical(ef["rule"], [s for _, s in RULES])
ef["group"] = pd.Categorical(ef["group"], [g for _, g in GROUPS])
ef["fee"] = pd.Categorical(ef["fee"], ["no charge", "ToU"])
ef["label"] = ef["value"].map(lambda v: f"{v:.0f}")

p = (ggplot(ef, aes("group", "value", fill="fee"))
     + geom_col(position=position_dodge(width=0.8), width=0.72)
     + geom_text(aes(label="label", group="fee"),
                 position=position_dodge(width=0.8), va="bottom", size=7)
     + facet_wrap("rule")
     + scale_fill_manual(values=["#9e9e9e", "#2f6fa8"])
     + scale_y_continuous(limits=(0, 105), expand=(0, 0, 0.02, 0))
     + labs(title="Traffic at LoS E or worse, flow-weighted, by reporting group",
            subtitle="Daily peak, 14-day mean. MWY is the motorway corridors; "
                     "CBD, East and West are arterial groups.\nLevels are high "
                     "because of the temporal residual — read the charged "
                     "against the uncharged bar, not the height.",
            x="", y="% of traffic at LoS E/F")
     + theme(figure_size=(11, 4.0)) + BASE_THEME)
out = os.path.join(FIGS, "los_ef_by_group_gg.png")
p.save(out, dpi=200, verbose=False)
print("wrote", out)
