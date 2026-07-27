#!/usr/bin/env python3
"""Every number the paper's Results section quotes, from the calibrated runs.

Reads the per-day scenario records written by `save-records` in the
`paper-figs` experiment (days_<Rule>_<fee>.csv: entry rate, inner / boundary /
peripheral V/C per simulated day) plus the hourly and LoS-hour tables, and
prints one block per decision rule with the No-Charge -> ToU comparison.

Reads  output/tables/days_<Rule>_<fee>.csv
       output/tables/hourly_<Rule>_<fee>.csv
       output/tables/los_hours_<Rule>_<fee>.csv
Writes output/tables/paper_numbers.txt (and prints the same to stdout)
"""
import csv, os, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
RULES = [("Exp-Decay", "Pay (exponential decay)"),
         ("ElFarol", "Oscillate (El Farol)"),
         ("Q-Learning", "Learn (Q-learning)")]
FEES = ["No-Charge", "tou"]
GRADES = ["A", "B", "C", "D", "E", "F"]
BURN_IN = 7   # converged regime for the learning rules; matches the figures

out_lines = []


def say(s=""):
    print(s)
    out_lines.append(s)


def read(kind, rule, fee):
    path = os.path.join(TABLES, f"{kind}_{rule}_{fee}.csv")
    return list(csv.DictReader(open(path))) if os.path.exists(path) else None


def pct(a, b):
    """Reduction from a to b, in per cent of a."""
    return 100 * (a - b) / a if a else float("nan")


def ms(xs):
    return st.mean(xs), (st.stdev(xs) if len(xs) > 1 else 0.0)


for rule, title in RULES:
    days = {fee: read("days", rule, fee) for fee in FEES}
    if not all(days.values()):
        say(f"{title}: no days_{rule}_*.csv yet — run the paper-figs experiment")
        say()
        continue
    say(f"=== {title} ===")

    # --- daily peak V/C by cordon position, and the entry rate --------------
    for field, label in [("vc_inner", "peak V/C inner"),
                         ("vc_boundary", "peak V/C boundary"),
                         ("vc_peripheral", "peak V/C peripheral"),
                         ("attendance", "CBD entry rate")]:
        m, s = {}, {}
        for fee in FEES:
            xs = [float(r[field]) for r in days[fee]]
            m[fee], s[fee] = ms(xs)
        say(f"  {label:22s} {m['No-Charge']:.3f} ± {s['No-Charge']:.3f}"
            f"  ->  {m['tou']:.3f} ± {s['tou']:.3f}"
            f"   ({pct(m['No-Charge'], m['tou']):+5.1f} %)")
    n = len(days["No-Charge"])
    say(f"  (mean ± day-to-day SD over {n} simulated days)")

    # --- hour-of-day profile ------------------------------------------------
    hourly = {fee: read("hourly", rule, fee) for fee in FEES}
    if all(hourly.values()):
        for label, hrs in [("AM peak 07-09", {7, 8}), ("PM peak 16-18", {16, 17}),
                           ("all day", set(range(24)))]:
            v = {}
            for fee in FEES:
                xs = [float(r["vc_inner"]) for r in hourly[fee]
                      if int(float(r["day"])) > BURN_IN
                      and int(float(r["hour"])) in hrs]
                v[fee] = st.mean(xs)
            say(f"  mean inner V/C {label:14s} {v['No-Charge']:.4f} -> {v['tou']:.4f}"
                f"   ({pct(v['No-Charge'], v['tou']):+5.1f} %)")

    # --- network-wide LoS mix ----------------------------------------------
    los = {fee: read("los_hours", rule, fee) for fee in FEES}
    if all(los.values()):
        for label, hrs in [("all day", None), ("07-09", {7, 8})]:
            ef = {}
            for fee in FEES:
                tot = [0.0] * 6
                for r in los[fee]:
                    if int(float(r["day"])) <= BURN_IN:
                        continue
                    if hrs and int(float(r["hour"])) not in hrs:
                        continue
                    tot = [a + float(r["f" + g]) for a, g in zip(tot, GRADES)]
                s = sum(tot)
                ef[fee] = 100 * (tot[4] + tot[5]) / s if s else float("nan")
            say(f"  % traffic at LoS E/F {label:8s} {ef['No-Charge']:.1f} ->"
                f" {ef['tou']:.1f}   ({ef['No-Charge'] - ef['tou']:+.1f} pp)")
    say()

# --- cross-rule summary: what the paper compares ---------------------------
say("=== cross-rule summary (14-day mean of daily peak V/C) ===")
say(f"  {'rule':24s} {'inner NC':>9s} {'inner ToU':>10s} {'red %':>7s}"
    f" {'SD NC':>7s} {'SD ToU':>7s} {'entry NC':>9s} {'entry ToU':>10s}")
for rule, title in RULES:
    days = {fee: read("days", rule, fee) for fee in FEES}
    if not all(days.values()):
        continue
    mi, si = {}, {}
    ent = {}
    for fee in FEES:
        mi[fee], si[fee] = ms([float(r["vc_inner"]) for r in days[fee]])
        ent[fee] = st.mean([float(r["attendance"]) for r in days[fee]])
    say(f"  {title:24s} {mi['No-Charge']:9.3f} {mi['tou']:10.3f}"
        f" {pct(mi['No-Charge'], mi['tou']):7.1f}"
        f" {si['No-Charge']:7.3f} {si['tou']:7.3f}"
        f" {ent['No-Charge']:9.3f} {ent['tou']:10.3f}")

path = os.path.join(TABLES, "paper_numbers.txt")
with open(path, "w") as f:
    f.write("\n".join(out_lines) + "\n")
print("\nwrote", path)
