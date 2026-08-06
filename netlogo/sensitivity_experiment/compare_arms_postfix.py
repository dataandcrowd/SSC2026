"""Post-fix four-arm comparison, with pre-fix values alongside.

Run after the 2026-08-06 extension-arm re-run (retiming / rerouting /
retiming-rerouting) finishes. Reads the fresh days_* tables in output/tables
and the pre-fix set preserved in output/tables_prefix_backup_20260805, and
prints, for every rule x arm: No-Charge -> ToU mean peak V/C by zone, the
percentage reduction, the entry change, and the same cell from the pre-fix
run, so the unified table for behavioural_extensions.md and the arms slide
can be filled in directly.

Usage:  python compare_arms_postfix.py
"""
import csv
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
NEW = os.path.join(HERE, "..", "..", "output", "tables")
OLD = os.path.join(HERE, "..", "..", "output", "tables_prefix_backup_20260805")

RULES = [("Pay", "Exp-Decay"), ("Oscillate", "ElFarol"), ("Learn", "Q-Learning")]
ARMS = [("base", ""), ("retime", "_rt"), ("reroute", "_rr"), ("both", "_rt_rr")]
ZONES = [("inner", "vc_inner"), ("boundary", "vc_boundary"),
         ("peripheral", "vc_peripheral"), ("entries", "attendance")]


def rows(base, rule, regime, tag):
    path = os.path.join(base, f"days_{rule}_{regime}{tag}.csv")
    if not os.path.exists(path):
        return None
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def cell(base, rule, tag, col):
    nc = rows(base, rule, "No-Charge", tag)
    tou = rows(base, rule, "tou", tag)
    if not nc or not tou:
        return None
    a = st.mean(float(r[col]) for r in nc)
    b = st.mean(float(r[col]) for r in tou)
    red = 100 * (b - a) / a if a else 0.0
    return a, b, red


def main():
    for label, rule in RULES:
        print(f"=== {label} ({rule}) ===")
        for arm, tag in ARMS:
            parts = []
            stale = ""
            for zlabel, col in ZONES:
                new = cell(NEW, rule, tag, col)
                old = cell(OLD, rule, tag, col)
                if new is None:
                    parts.append(f"{zlabel}: MISSING")
                    continue
                a, b, red = new
                s = f"{zlabel} {a:.3f}->{b:.3f} ({red:+.1f}%)"
                if old:
                    s += f" [pre-fix {old[2]:+.1f}%]"
                parts.append(s)
            # same-bytes check: if the "new" file equals the backup, the re-run
            # has not actually replaced this arm yet
            p_new = os.path.join(NEW, f"days_{rule}_tou{tag}.csv")
            p_old = os.path.join(OLD, f"days_{rule}_tou{tag}.csv")
            if os.path.exists(p_new) and os.path.exists(p_old):
                with open(p_new, "rb") as f1, open(p_old, "rb") as f2:
                    if f1.read() == f2.read():
                        stale = "  ** IDENTICAL TO PRE-FIX BACKUP - NOT RE-RUN **"
            print(f"  {arm:8s}{stale}")
            for p in parts:
                print(f"    {p}")
        print()


if __name__ == "__main__":
    main()
