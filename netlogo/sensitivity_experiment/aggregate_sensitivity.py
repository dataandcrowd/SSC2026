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
    series = defaultdict(list); meta = {}
    for r in data:
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
