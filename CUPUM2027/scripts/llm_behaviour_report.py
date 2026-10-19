"""Agent-level comparison of H-clock (LLM at moments of change) with R-clock (rule) runs.

    python scripts/llm_behaviour_report.py --out runs/llm_behaviour \
        --pair NZ6=full_H-clock_s1,full_R-clock_s1 --pair NZ18=full_H-clock_s1_peak18,full_R-clock_s1_peak18

Each --pair is LABEL=H_RUN,R_RUN (folders in runs/, same seed and settings). Writes to --out:
    scenario_summary.csv         daily means before and with the charge for every run (cars, bus or train,
                                 home, delays, late trips, charge paid; LLM questions)
    agent_days.csv               one row per scenario, arm, commuter and day: what they did, who decided,
                                 the triggers, and the reason (the rule's template, or the LLM's own words)
    response_by_circumstance.csv how commuters who drove before the charge responded to it (kept their
                                 time, retimed, switched to bus or train, worked from home, mixed), by trait
                                 level and by circumstance, for both arms
    llm_reasons_by_trait.csv     the LLM's main reason on the charge day, by trait level
    examples.md                  side-by-side trajectories of selected commuters, with the LLM's words
Reads run folders only; makes no API call.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SYM = {"CAR": "C", "PT": "B", "WFH": "H"}
CHARGE_DAY_DEFAULT = 6


def load(run: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    d = pd.read_csv(run / "decisions.csv")
    p = pd.read_csv(run / "personas.csv").set_index("agent_id")
    p["fftt_total_min"] = p["fftt_to_gate_min"] + p["fftt_gate_to_dest_min"]
    plan: dict = {}
    if (run / "plan_log.jsonl").exists():
        for line in (run / "plan_log.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            plan[(r["agent_id"], r["day"])] = r
    words: dict = {}
    if (run / "llm_calls.jsonl").exists():
        for line in (run / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("valid") and r.get("parsed"):
                words[(r["agent_id"], r["day"])] = r["parsed"]
    return d, p, plan, words


def agent_days(label: str, arm: str, d: pd.DataFrame, plan: dict, words: dict) -> pd.DataFrame:
    out = d[["agent_id", "day", "mode", "option_id", "depart_min", "decider", "triggers", "reason"]].copy()
    out.insert(0, "arm", arm)
    out.insert(0, "scenario", label)
    out["question"] = [plan.get((a, t), {}).get("handler", "") if dec == "llm" else ""
                       for a, t, dec in zip(out["agent_id"], out["day"], out["decider"])]
    out["llm_main_reason"] = [words.get((a, t), {}).get("main_reason", "") if dec == "llm" else ""
                              for a, t, dec in zip(out["agent_id"], out["day"], out["decider"])]
    return out


def response(d: pd.DataFrame, charge_day: int) -> pd.Series:
    """Response of each commuter who drove on the day before the charge, over the charged days."""
    before = d[d["day"] == charge_day - 1].set_index("agent_id")
    after = d[d["day"] >= charge_day]
    res = {}
    for a, g in after.groupby("agent_id"):
        if before.loc[a, "mode"] != "CAR":
            continue
        modes = set(g["mode"])
        if len(modes) > 1:
            res[a] = "mixed week"
        elif modes == {"CAR"}:
            res[a] = "kept time" if set(g["option_id"]) == {before.loc[a, "option_id"]} else "retimed"
        else:
            res[a] = {"PT": "bus or train", "WFH": "work from home"}[modes.pop()]
    return pd.Series(res, name="response")


def circumstances(p: pd.DataFrame, d: pd.DataFrame, charge_day: int) -> pd.DataFrame:
    c = pd.DataFrame(index=p.index)
    for t, name in (("H", "routine (H)"), ("F", "flexibility (F)"), ("P", "attitude to bus/train (P)"),
                    ("S", "charge sensitivity (S)")):
        c[name] = p[t].astype(str)
    c["pays parking"] = (p["parking_cost"] > 0).map({True: "yes", False: "no"})
    c["employer pays charge"] = p["company_car"].map({True: "yes", False: "no"})
    c["can work from home"] = p["wfh_allowed"].map({True: "yes", False: "no"})
    extra = (p["pt_time_min"] - p["fftt_total_min"]).where(p["pt_allowed"])
    c["bus slower than free-flow drive"] = pd.cut(extra, [-1e9, 15, 30, 1e9],
                                                  labels=["up to 15 min", "15-30 min", "over 30 min"]).astype(str)
    c.loc[~p["pt_allowed"], "bus slower than free-flow drive"] = "no bus or train"
    c["late before the charge"] = "no"
    return c


def lateness(run: Path, charge_day: int) -> pd.Series:
    o = pd.read_csv(run / "outcomes.csv")
    o = o[(o["day"] >= 2) & (o["day"] < charge_day)]
    return (o.groupby("agent_id")["late_min"].apply(lambda s: int((s > 5).sum()) >= 2)
            .map({True: "yes", False: "no"}))


def trajectory(d: pd.DataFrame, a: int, charge_day: int) -> str:
    g = d[d["agent_id"] == a].sort_values("day")
    s = "".join(SYM.get(m, "?") for m in g["mode"])
    out = s[:charge_day - 1] + " | " + s[charge_day - 1:]
    cars = g[g["mode"] == "CAR"]
    before, after = cars[cars["day"] < charge_day], cars[cars["day"] >= charge_day]
    clock = lambda m: f"{int(m) // 60:02d}:{int(m) % 60:02d}"
    if len(before) and len(after):
        b, e = before["depart_min"].iloc[-1], after["depart_min"].iloc[-1]
        out += f"   (drives at {clock(b)}" + (f", then {clock(e)})" if b != e else " throughout)")
    return out


def scenario_summary(label: str, arm: str, run: Path, charge_day: int) -> dict:
    """Daily means before (days 2 to the day before the charge) and with the charge."""
    o = pd.read_csv(run / "outcomes.csv")
    row = {"scenario": label, "arm": arm, "run": run.name}
    for tag, sel in (("before", (o["day"] >= 2) & (o["day"] < charge_day)), ("charge", o["day"] >= charge_day)):
        x = o[sel]
        n = x["day"].nunique()
        cars = x[x["mode"] == "CAR"]
        row.update({f"cars_{tag}": len(cars) / n, f"pt_{tag}": (x["mode"] == "PT").sum() / n,
                    f"wfh_{tag}": (x["mode"] == "WFH").sum() / n,
                    f"road_delay_per_car_{tag}": cars["road_delay_min"].mean(),
                    f"queue_per_car_{tag}": cars["queue_delay_min"].mean(),
                    f"late_trips_{tag}": (x["late_min"] > 0.5).sum() / n,
                    f"charge_paid_{tag}": x["fee_paid"].sum() / n})
    row["cars_change_pct"] = 100 * (row["cars_charge"] / row["cars_before"] - 1)
    if (run / "llm_calls.jsonl").exists():
        c = [json.loads(x) for x in (run / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines()]
        row["llm_questions"] = len(c)
        row["llm_invalid"] = sum(not x.get("valid", True) for x in c)
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pair", action="append", required=True, help="LABEL=H_RUN,R_RUN")
    ap.add_argument("--out", default="runs/llm_behaviour")
    ap.add_argument("--charge-day", type=int, default=CHARGE_DAY_DEFAULT)
    ap.add_argument("--examples", type=int, default=8)
    args = ap.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    cd = args.charge_day
    summary: list[dict] = []
    days, resp_rows, reason_rows, md = [], [], [], ["# Agent-level trajectories: rule (R-clock) and LLM (H-clock)", "",
        "Mode by day: C car, B bus or train, H home; `|` marks the start of the charge. Same commuters, same seed and "
        "settings in both arms. Quotes are the LLM's replies, word for word.", ""]
    for spec in args.pair:
        label, runs = spec.split("=", 1)
        h_run, r_run = (ROOT / "runs" / x for x in runs.split(","))
        hd, p, hplan, hwords = load(h_run)
        rd, _, _, _ = load(r_run)
        summary += [scenario_summary(label, "H-clock", h_run, cd), scenario_summary(label, "R-clock", r_run, cd)]
        days += [agent_days(label, "H-clock", hd, hplan, hwords), agent_days(label, "R-clock", rd, {}, {})]
        circ = circumstances(p, hd, cd)
        circ["late before the charge"] = lateness(h_run, cd).reindex(circ.index).fillna("no")
        for arm, d in (("H-clock", hd), ("R-clock", rd)):
            r = response(d, cd)
            for col in circ.columns:
                t = pd.crosstab(circ.loc[r.index, col], r, normalize="index").mul(100).round(1)
                n = circ.loc[r.index, col].value_counts()
                for level, row in t.iterrows():
                    resp_rows.append({"scenario": label, "arm": arm, "circumstance": col, "level": level,
                                      "drivers": int(n[level]), **row.to_dict()})
        main = {a: w.get("main_reason") for (a, t), w in hwords.items() if t == cd and "what_i_do" in w}
        for trait in ("P", "H", "S", "F"):
            t = pd.crosstab(p.loc[list(main), trait], pd.Series(main), normalize="index").mul(100).round(1)
            for level, row in t.iterrows():
                reason_rows.append({"scenario": label, "trait": trait, "level": level, **row.to_dict()})
        # examples: one commuter for each pattern, picked from the data
        rh, rr = response(hd, cd), response(rd, cd)
        asked = {a for (a, t), x in hplan.items() if x["decider"] == "llm"}
        patterns = [
            ("LLM switched to bus or train, rule kept driving", rh.index[(rh == "bus or train") & rr.reindex(rh.index).isin(["kept time", "retimed"])]),
            ("LLM kept driving at the usual time, rule changed", rh.index[(rh == "kept time") & ~rr.reindex(rh.index).isin(["kept time"])]),
            ("LLM chose a mixed week", rh.index[rh == "mixed week"]),
            ("LLM tried something and reviewed it", [a for (a, t), x in hplan.items() if x["handler"] == "change:review" and t > cd]),
            ("Asked about lateness before the charge", [a for (a, t), x in hplan.items() if x["handler"] == "change:late" and t < cd]),
            ("Bus or train disrupted, one-day question", [a for (a, t), x in hplan.items() if x["handler"] == "today:disruption"]),
            ("Bus or train disrupted, own back-up used", [a for (a, t), x in hplan.items() if x["handler"] == "contingency"]),
        ]
        md += [f"## {label}", ""]
        for title, agents in patterns:
            agents = sorted(set(int(a) for a in agents))
            if not agents:
                continue
            a = agents[0]
            q = p.loc[a]
            md += [f"### {title} (commuter {a}; {len(agents)} such commuters)", "",
                   f"Traits H{q['H']} F{q['F']} P{q['P']} S{q['S']}; parking NZ${q['parking_cost']:.2f}; "
                   f"{'employer pays the charge' if q['company_car'] else 'pays the charge'}; "
                   f"{'can' if q['wfh_allowed'] else 'cannot'} work from home; "
                   f"{'bus or train ' + str(round(q['pt_time_min'])) + ' min' if q['pt_allowed'] else 'no bus or train'}, "
                   f"drive {q['fftt_total_min']} min with no traffic.", "",
                   f"- Rule:  `{trajectory(rd, a, cd)}`", f"- LLM:   `{trajectory(hd, a, cd)}`", ""]
            for (aa, t), x in sorted(hplan.items()):
                if aa == a and x["decider"] == "llm":
                    w = hwords.get((a, t), {})
                    choice = w.get("what_i_do", w.get("what_i_do_today", ""))
                    extra = ""
                    if w.get("second_choice") not in (None, "none") and w.get("days_a_week_on_second"):
                        extra = f" + {w['second_choice']} {w['days_a_week_on_second']} days a week"
                    if w.get("trying_it_out_for_days"):
                        extra += f", trial {w['trying_it_out_for_days']} days"
                    if w.get("if_bus_disrupted") not in (None, "not_applicable"):
                        extra += f", back-up if bus or train disrupted: {w['if_bus_disrupted']}"
                    md.append(f"- Day {t}, asked ({x['handler'].replace('change:', '').replace('today:', 'today: ')}): "
                              f"**{choice}**{extra}; main reason {w.get('main_reason')}. \"{w.get('in_my_words', '')}\"")
            for (aa, t), x in sorted(hplan.items()):
                if aa == a and x["handler"] == "contingency":
                    md.append(f"- Day {t}: bus or train disrupted; the commuter's own back-up applied "
                              f"({x['strategy']}), no LLM call.")
            rule_days = rd[(rd["agent_id"] == a) & (rd["decider"] == "rule") & (rd["day"] > 1)]
            for _, row in rule_days.iterrows():
                md.append(f"- Day {row['day']}, rule woken ({row['triggers']}): {row['reason']}")
            md.append("")
        _ = asked
    pd.DataFrame(summary).round(2).to_csv(out / "scenario_summary.csv", index=False, lineterminator="\n")
    pd.concat(days).to_csv(out / "agent_days.csv", index=False, lineterminator="\n")
    pd.DataFrame(resp_rows).fillna(0).to_csv(out / "response_by_circumstance.csv", index=False, lineterminator="\n")
    pd.DataFrame(reason_rows).fillna(0).to_csv(out / "llm_reasons_by_trait.csv", index=False, lineterminator="\n")
    (out / "examples.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
