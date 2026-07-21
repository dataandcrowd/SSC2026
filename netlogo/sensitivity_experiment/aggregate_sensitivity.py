#!/usr/bin/env python3
"""Aggregate the BehaviorSpace sensitivity-analysis tables into a tidy summary.

For each scenario it computes, from the daily series of peak-vc-inner:
  mean over days, and day-to-day standard deviation (volatility).
Then it pairs No-Charge against ToU at each parameter value and reports the
percentage reduction in inner-cordon peak V/C.

Reads netlogo/output/tables/sensitivity-*.csv (BehaviorSpace "table" format).
"""
import csv, os, statistics as st
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.path.join(HERE, "..", "..", "output", "tables")

PARAM = {  # which varied variable identifies each experiment
    "sensitivity-pay": "base-beta",
    "sensitivity-elfarol": "el-farol-threshold",
    "sensitivity-ql-alpha": "ql-alpha",
    "sensitivity-ql-epsilon": "ql-epsilon-init",
}

def load(path):
    with open(path) as f:
        rows = list(csv.reader(f))
    hdr_i = next(i for i, r in enumerate(rows) if r and r[0] == "[run number]")
    return rows[hdr_i], [r for r in rows[hdr_i + 1:] if r]

for exp, pvar in PARAM.items():
    path = os.path.join(TABLES, f"{exp}.csv")
    if not os.path.exists(path):
        print(f"(skip {exp}: {path} not found)"); continue
    hdr, data = load(path)
    cm, cf, cp, cr = (hdr.index("peak-vc-inner"), hdr.index("fee-regime"),
                      hdr.index(pvar), hdr.index("[run number]"))
    cd = hdr.index("current-sim-day")
    series = defaultdict(list); meta = {}
    for r in data:
        if int(float(r[cd])) < 1:   # skip the step-0 row recorded before day 1
            continue
        series[r[cr]].append(float(r[cm]))
        meta[r[cr]] = (r[cp].strip('"'), r[cf].strip('"'))
    agg = {}
    for run, vals in series.items():
        p, fee = meta[run]
        agg[(p, fee)] = (st.mean(vals), st.pstdev(vals) if len(vals) > 1 else 0.0)
    print(f"\n=== {exp}  (varying {pvar}) ===")
    print(f"{pvar:>16}{'none':>9}{'tou':>9}{'red%':>8}{'SD(tou)':>9}")
    for p in sorted({p for p, _ in agg}, key=float):
        none, tou = agg.get((p, "No-Charge")), agg.get((p, "tou"))
        if not (none and tou):
            continue
        red = 100 * (none[0] - tou[0]) / none[0] if none[0] else 0
        print(f"{p:>16}{none[0]:>9.3f}{tou[0]:>9.3f}{red:>7.1f}%{tou[1]:>9.3f}")

# --- k-factor sweep: LoS robustness -----------------------------------------
# k-factor only rescales the assumed hourly capacity (measurement layer), so
# traffic dynamics are identical across values. We summarise the mean daily
# peak % of traffic at LoS E/F per reporting group, for each k and fee regime.
GROUPS = ["peak-ef-mwy", "peak-ef-cbd", "peak-ef-east", "peak-ef-west"]
path = os.path.join(TABLES, "sensitivity-kfactor.csv")
if os.path.exists(path):
    hdr, data = load(path)
    cf, cp, cr = hdr.index("fee-regime"), hdr.index("k-factor"), hdr.index("[run number]")
    cd = hdr.index("current-sim-day")
    cg = [hdr.index(g) for g in GROUPS]
    series = defaultdict(lambda: [[] for _ in GROUPS]); meta = {}
    for r in data:
        if int(float(r[cd])) < 1:   # skip the step-0 row recorded before day 1
            continue
        for j, c in enumerate(cg):
            series[r[cr]][j].append(float(r[c]))
        meta[r[cr]] = (r[cp].strip('"'), r[cf].strip('"'))
    agg = {}
    for run, cols in series.items():
        agg[meta[run]] = ([st.mean(v) for v in cols],
                          [st.pstdev(v) if len(v) > 1 else 0.0 for v in cols])
    print("\n=== sensitivity-kfactor  (daily-peak % traffic at LoS E/F, mean ± SD over days) ===")
    print(f"{'k-factor':>10}{'fee':>11}{'MWY':>13}{'CBD':>13}{'East':>13}{'West':>13}")
    for (p, fee) in sorted(agg, key=lambda t: (float(t[0]), t[1])):
        m, s = agg[(p, fee)]
        cells = "".join(f"{m[i]:>7.1f}±{s[i]:<5.1f}" for i in range(4))
        print(f"{p:>10}{fee:>11}{cells}")
else:
    print(f"(skip sensitivity-kfactor: {path} not found)")
