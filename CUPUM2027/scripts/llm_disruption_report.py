"""How commuters handled the bus or train disruption: H-clock (LLM) against R-clock (rule).

    python scripts/llm_disruption_report.py --out runs/llm_behaviour \
        --set NZ6=full_H-clock_s1_pt3_pt8,full_H-clock_s1,full_R-clock_s1_pt3_pt8,full_R-clock_s1

Each --set is LABEL=H_DISRUPTED,H_UNDISRUPTED,R_DISRUPTED,R_UNDISRUPTED (folders in runs/). The affected
commuters on a disruption day are those on the disrupted corridor who took the bus or train that day in
the undisrupted run of the same arm (the definition used for the rule-based results). Writes
disruption_response.csv: for each scenario, arm and disruption day, how many stayed on the bus or train,
drove or worked from home, their mean extra door-to-door time, and how many were back on the bus or
train the next day; for H-clock also how the LLM part handled it (one-day question or the commuter's own
back-up). Reads run folders only; makes no API call.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def handlers(run: Path) -> dict:
    p = run / "plan_log.jsonl"
    if not p.exists():
        return {}
    return {(r["agent_id"], r["day"]): r["handler"]
            for r in map(json.loads, p.read_text(encoding="utf-8").splitlines())}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--set", action="append", required=True)
    ap.add_argument("--out", default="runs/llm_behaviour")
    args = ap.parse_args()
    rows = []
    for spec in args.set:
        label, runs = spec.split("=", 1)
        h_dis, h_base, r_dis, r_base = (ROOT / "runs" / x for x in runs.split(","))
        for arm, dis, base in (("H-clock", h_dis, h_base), ("R-clock", r_dis, r_base)):
            od, ob = pd.read_csv(dis / "outcomes.csv"), pd.read_csv(base / "outcomes.csv")
            hit = od[od["pt_disrupted"].astype(bool)]
            hl = handlers(dis)
            for day in sorted(hit["day"].unique()):
                corridor = int(hit[hit["day"] == day]["corridor_id"].mode()[0])
                b = ob[(ob["day"] == day) & (ob["corridor_id"] == corridor) & (ob["mode"] == "PT")].set_index("agent_id")
                d = od[(od["day"] == day) & od["agent_id"].isin(b.index)].set_index("agent_id")
                nxt = od[(od["day"] == day + 1) & od["agent_id"].isin(b.index)].set_index("agent_id")
                n = len(b)
                extra = (d["travel_min"] - b.loc[d.index, "travel_min"]).where(d["mode"] != "WFH")
                row = {"scenario": label, "arm": arm, "day": int(day), "corridor": corridor, "affected": n,
                       "stayed_on_bus_or_train_pct": round(100 * (d["mode"] == "PT").mean(), 1),
                       "drove_pct": round(100 * (d["mode"] == "CAR").mean(), 1),
                       "worked_from_home_pct": round(100 * (d["mode"] == "WFH").mean(), 1),
                       "extra_minutes_mean": round(float(extra.mean()), 1),
                       "back_on_bus_or_train_next_day_pct": round(100 * (nxt["mode"] == "PT").mean(), 1) if len(nxt) else None}
                if arm == "H-clock":
                    hs = [hl.get((a, int(day)), "") for a in b.index]
                    row["llm_one_day_question"] = sum(h.startswith("today") for h in hs)
                    row["own_back_up_used"] = sum(h == "contingency" for h in hs)
                    row["routine_applied_no_call"] = n - row["llm_one_day_question"] - row["own_back_up_used"]
                rows.append(row)
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out / "disruption_response.csv", index=False, lineterminator="\n")
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
