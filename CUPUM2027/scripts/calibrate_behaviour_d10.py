"""Behaviour calibration of the rule decider for the 10-day design (2026-10-15).

    .venv/bin/python scripts/calibrate_behaviour_d10.py [--workers 14] [--stage all|search|final|report]

The 10-day design [author decision 2026-10-15]: days 1-5 uncharged, the charge from day 6 (fees.fee_start_day),
no PT disruption (events.pt_disruption_day = 0), base shares and the capacity calibration on days 2-5
(engine.calib_days; day 1 is left out because commuters have no experience yet), and the response on the mean of
the charged days 6-10 against days 2-5, with a wider band than the 30-day design (-15% to -30%, centre -20%) and no
separate overshoot target, since a 5-day charged period holds the short-run response. The 30-day calibration is
archived in data/behaviour_calibration_d30.json and data/calibration_d30.json (scripts/calibrate_behaviour.py).

Everything else is as in scripts/calibrate_behaviour.py, whose building blocks it reuses: R-daily arm, rule decider,
PyEngine, 950 agents, seeds 1-3, the structural fixes, paid parking NZ$17 and fuel fixed, three searched scalars
(PAP = costs.pt_attitude_penalty, k_WFH = costs.wfh_cost, beta0 = wtt.beta0), capacity recalibrated per (PAP,
k_WFH, seed) with cordonlite.run.calibrate (no charge, so the scale is shared by every beta0 of the pair), the same
single-seed tolerances and the same selection rule (feasible first, then nearest the anchors PAP 8 / k_WFH 8 /
beta0 0.5, then the loss).

Stages:
    search  stage 1: PAP 20-24 x k_WFH {4, 6, 8, 10, 12, 14, 16} x beta0 {0.05, 0.1, 0.15, 0.2, 0.3, 0.5}, plus beta0 = 0
            as a reference (never selected); stage 2: the full NZ$1 k_WFH range 2-16 x beta0 {0.05, 0.1, 0.15, 0.2,
            0.25, 0.3, 0.4, 0.5, 0.75, 1.0} on the PAP values where stage 1 meets the base-share targets
    final   the chosen point on unseen seeds 4-12 (own capacity calibration per seed) and the sensitivities to the
            fixed assumptions of the 30-day report (willingness to pay off / SSC2026 beta0 / sample-median VoT_ref,
            early start off / cheaper / dearer / everyone allowed), seeds 1-3, capacity recalibrated
    report  data/behaviour_calibration.json and docs/calibration_report.md

Runs go to temporary folders; runs/, config.toml and data/calibration.json are not touched. Put the chosen values in
config.toml by hand, then `python -m cordonlite.run calibrate --seeds 1 2 3`.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import calibrate_behaviour as cb  # noqa: E402
from cordonlite.config import load_config  # noqa: E402

OUT_JSON = ROOT / "data" / "behaviour_calibration.json"
OUT_MD = ROOT / "docs" / "calibration_report.md"
CKPT = Path(tempfile.gettempdir()) / "cordonlite_behaviour_d10_checkpoint.jsonl"

CFG0 = load_config()
N_AGENTS, N_DAYS = int(CFG0.run.n_agents), 10
BASE_DAYS = (2, 5)            # uncharged days of the base shares and of the capacity calibration
RESP_DAYS = (6, 10)           # charged days of the response
assert int(CFG0.fees.fee_start_day) == RESP_DAYS[0] and tuple(CFG0.engine.calib_days) == BASE_DAYS, \
    "config.toml must hold fees.fee_start_day = 6 and engine.calib_days = [2, 5]"

SEEDS = (1, 2, 3)
OOS_SEEDS = tuple(range(4, 13))
TARGETS = {
    "base_car": {"lo": 0.75, "hi": 0.85, "centre": 0.80, "what": "car share, mean of days 2-5 (uncharged)"},
    "base_pt": {"lo": 0.08, "hi": 0.15, "centre": 0.115, "what": "PT share, days 2-5"},
    "base_wfh": {"lo": 0.0, "hi": 0.10, "centre": None, "what": "WFH share, days 2-5 (at most)"},
    "change_6_10": {"lo": -0.30, "hi": -0.15, "centre": -0.20,
                    "what": "car cordon crossings, mean days 6-10 (charged) vs mean days 2-5"},
}
BASE_KEYS = ("base_car", "base_pt", "base_wfh")
_tol = cb.seed_tolerance(N_AGENTS)
SEED_TOL = {"base_car": _tol["base_car"], "base_pt": _tol["base_pt"], "base_wfh": _tol["base_wfh"],
            "change_6_10": _tol["change_21_30"]}
LOSS_SCALE = {"base_car": 0.05, "base_pt": 0.035, "change_6_10": 0.04}

STAGE1 = {"pap": [20.0, 21.0, 22.0, 23.0, 24.0], "wfh": [4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0],
          "beta0": [0.05, 0.1, 0.15, 0.2, 0.3, 0.5]}
STAGE2 = {"wfh": [float(x) for x in range(2, 17)], "beta0": [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0]}
# Stage 3 (only when stages 1-2 have no feasible point): PAP in NZ$0.25 steps on both sides of the chosen PAP. With
# WFH near 0, car + PT is about 1, so base car <= 0.85 and base PT <= 0.15 hold together only near 0.85 / 0.15, which
# can fall between two NZ$1 PAP steps (2026-10-15: PAP 21 gives PT 0.15-0.16, PAP 22 car 0.858 on days 2-5).
STAGE3 = {"pap_offsets": [-0.75, -0.5, -0.25, 0.25, 0.5, 0.75], "wfh": [float(x) for x in range(6, 17)],
          "beta0": STAGE2["beta0"]}
BETA0_REFERENCE = 0.0
BETA0_MIN_SELECT = 0.15   # [author decision 2026-10-16] keep a working willingness-to-pay limit (the 30-day choice was 0.15)
SELECTION_DOC = ("lexicographic [author decision 2026-10-16]: (1) feasible = every 3-seed mean in its target band at "
                 "the targets' stated precision (shares to 2 decimals, changes to whole percent) and every seed within "
                 "the stated single-seed tolerance; (2) beta0 >= 0.15, so that the willingness-to-pay limit stays in "
                 "force (beta0 0.05-0.1 lie at the bottom of the searched range, where the limit almost vanishes); "
                 "(3) the 3-seed mean response of days 6-10 nearest the -20% centre (Stockholm), at the stated "
                 "precision (whole percent); (4) loss as tie-break. If no point is feasible, the lowest loss. beta0 = 0 references are never selected. "
                 "This replaces the anchor rule of the 30-day calibration (nearest PAP 8 / k_WFH 8 / beta0 0.5), "
                 "which with the wider 10-day band picked a point at its edge (PAP 21.25 / k_WFH 11 / beta0 0.25, "
                 "-29.1%).")

SENSITIVITIES = [   # (label, what, overrides on top of the chosen point); as gap_sensitivity of the 30-day log
    ("nowtt", "no willingness-to-pay limit (wtt.beta0 = 0)", {"wtt.beta0": 0.0}),
    ("ssc", "SSC2026's price sensitivity (wtt.beta0 = 0.5)", {"wtt.beta0": 0.5}),
    ("samplemedian", "VoT_ref = median VoT of the simulated commuters (wtt.vot_ref = sample_median)",
     {"wtt.vot_ref": "sample_median"}),
    ("noearly", "no early-start option (persona.early_shift_prob all 0)",
     {"persona.early_shift_prob": [0.0, 0.0, 0.0, 0.0, 0.0]}),
    ("early1.5", "early day costs NZ$1.5 x phi(F) (costs.early_shift_cost 3 -> 1.5)", {"costs.early_shift_cost": 1.5}),
    ("early6", "early day costs NZ$6 x phi(F) (costs.early_shift_cost 3 -> 6)", {"costs.early_shift_cost": 6.0}),
    ("earlyall", "every employer of archetypes 1, 2 and 4 allows the early day",
     {"persona.early_shift_prob": [1.0, 1.0, 0.0, 1.0, 0.0]}),
]


# ----------------------------------------------------------------------------- one evaluation

def metrics(res, n: int) -> dict[str, Any]:
    """Target metrics and day series of one 10-day run."""
    days = res.days
    out = pd.DataFrame(res.outcomes)
    car = out[(out["mode"] == "CAR") & (out["gate_exit_min"].astype(float) >= 0)]
    cr = car.groupby("day").size().reindex(range(1, len(days) + 1), fill_value=0).to_numpy(dtype=float)
    b0, b1 = BASE_DAYS
    r0, r1 = RESP_DAYS
    pre = cr[b0 - 1:b1].mean()

    def chg(a, b):
        return float(cr[a - 1:b].mean() / pre - 1.0) if pre else float("nan")

    def mean_of(key, a, b, div=1.0):
        return float(np.mean([d.get(key, 0) / div for d in days[a - 1:b]]))

    def band_cross(a, b, band):
        g = car[(car["day"] >= a) & (car["day"] <= b)]["gate_exit_min"].astype(int)
        return float(((g >= band[0]) & (g < band[1])).sum()) / (b - a + 1)

    pk0, pk1 = band_cross(b0, b1, cb.PEAK_BAND), band_cross(r0, r1, cb.PEAK_BAND)
    return {
        "base_car": mean_of("cars", b0, b1, n), "base_pt": mean_of("pt", b0, b1, n), "base_wfh": mean_of("wfh", b0, b1, n),
        "change_6_10": chg(r0, r1), "change_6": chg(6, 6), "change_8_10": chg(8, 10),
        "change_by_day": [float(x / pre - 1.0) for x in cr], "crossings_by_day": [int(x) for x in cr],
        "share_by_day": {k: [round(d[k] / n, 4) for d in days] for k in ("cars", "pt", "wfh")},
        "end_car": mean_of("cars", r0, r1, n), "end_pt": mean_of("pt", r0, r1, n), "end_wfh": mean_of("wfh", r0, r1, n),
        "end_wtt_no_car": mean_of("wtt_no_car", r0, r1, n), "end_wtt_limited": mean_of("wtt_limited", r0, r1, n),
        "base_early": mean_of("early_shift", b0, b1, n), "end_early": mean_of("early_shift", r0, r1, n),
        "peak_cross_change": float(pk1 / pk0 - 1.0) if pk0 else float("nan"),
        "peak_total_delay_base": mean_of("peak_bin_total_delay_wmean", b0, b1),
        "peak_total_delay_end": mean_of("peak_bin_total_delay_wmean", r0, r1),
        "peak_delay_base": mean_of("peak_bin_delay_wmean", b0, b1),
        "peak_delay_end": mean_of("peak_bin_delay_wmean", r0, r1),
        "road_delay_base": mean_of("mean_road_delay", b0, b1), "road_delay_end": mean_of("mean_road_delay", r0, r1),
        "revenue": float(sum(d["revenue"] for d in days)),
    }


def run_overrides(seed: int, overrides: dict) -> dict:
    return {"run.arm": "R-daily", "run.seed": int(seed), "run.n_agents": N_AGENTS, "run.n_days": N_DAYS, **overrides}


def capacity_job(job: dict) -> dict:
    from cordonlite.run import calibrate

    t0 = time.perf_counter()
    rec = calibrate(load_config(overrides=run_overrides(job["seed"], job["overrides"])), progress=False)
    return {"kind": "capacity", "key": job["key"], "seed": int(job["seed"]),
            "calibration": cb._calib_record(rec), "seconds": round(time.perf_counter() - t0, 1)}


def run_job(job: dict) -> dict:
    from cordonlite.run import simulate

    t0 = time.perf_counter()
    cfg = load_config(overrides=run_overrides(job["seed"], job["overrides"]))
    with tempfile.TemporaryDirectory(prefix="cl_bcal10_") as tmp:
        res = simulate(cfg, Path(tmp), float(job["scale"]), engine_kind="py")
    peak = float(cfg.fees.peak_fee)
    row = {"kind": "run", "label": job["label"], "seed": int(job["seed"]), "capacity_scale": float(job["scale"]),
           **metrics(res, N_AGENTS),
           "wtp_below_peak_share": float(np.mean([p.wtp_fee < peak for p in res.personas])),
           "seconds": round(time.perf_counter() - t0, 1)}
    return row


def task(job: dict) -> dict:
    return capacity_job(job) if job["kind"] == "capacity" else run_job(job)


# ----------------------------------------------------------------------------- bookkeeping

class Store:
    """Capacity records and runs so far, appended to a JSONL checkpoint so that an interrupted search resumes."""

    def __init__(self) -> None:
        self.cap: dict[str, dict] = {}
        self.rows: dict[str, dict] = {}
        if CKPT.exists():
            for line in CKPT.read_text().splitlines():
                self._add(json.loads(line))
            print(f"resuming from {CKPT}: {len(self.cap)} calibrations, {len(self.rows)} runs", flush=True)

    def _add(self, r: dict) -> None:
        if r["kind"] == "capacity":
            self.cap[f"{r['key']}|{r['seed']}"] = r
        else:
            self.rows[f"{r['label']}|{r['seed']}"] = r

    def add(self, r: dict) -> None:
        self._add(r)
        with CKPT.open("a") as f:
            f.write(json.dumps(r) + "\n")


def label_of(sc: dict) -> str:
    return cb.point_label({"park": cb.PARK_FIXED, **sc})


def overrides_of(sc: dict) -> dict:
    return cb.point_overrides(sc["pap"], cb.PARK_FIXED, sc["wfh"], sc["beta0"])


def evaluate_points(store: Store, points: list[dict], seeds, workers: int, desc: str,
                    cap_key=lambda sc: f"pap{sc['pap']:g}_wfh{sc['wfh']:g}", extra=None) -> None:
    """Capacity per (cap_key, seed) first, then the charged runs. extra(sc) adds overrides (sensitivities)."""
    extra = extra or (lambda sc: {})
    cap_jobs, seen = [], set()
    for sc in points:
        for s in seeds:
            k = f"{cap_key(sc)}|{s}"
            if k not in store.cap and k not in seen:
                seen.add(k)
                cap_jobs.append({"kind": "capacity", "key": cap_key(sc), "seed": s,
                                 "overrides": {**overrides_of(sc), **extra(sc)}})
    if cap_jobs:
        cb.run_jobs(cap_jobs, workers, f"{desc} capacity", fn=task, on_result=store.add)
    run_jobs = []
    for sc in points:
        for s in seeds:
            if f"{sc['label']}|{s}" not in store.rows:
                run_jobs.append({"kind": "run", "label": sc["label"], "seed": s,
                                 "overrides": {**overrides_of(sc), **extra(sc)},
                                 "scale": store.cap[f"{cap_key(sc)}|{s}"]["calibration"]["capacity_scale"]})
    if run_jobs:
        cb.run_jobs(run_jobs, workers, f"{desc} runs", fn=task, on_result=store.add)


# ----------------------------------------------------------------------------- selection

def band_excess(key: str, v: float, tol: float = 0.0) -> float:
    t = TARGETS[key]
    return max(0.0, t["lo"] - tol - v, v - t["hi"] - tol)


def mean_of_rows(rows: list[dict]) -> dict[str, float]:
    keys = [k for k, v in rows[0].items() if isinstance(v, float)]
    return {k: float(np.mean([r[k] for r in rows])) for k in keys}


def feasible(rows: list[dict], m: dict) -> bool:
    return (all(band_excess(k, round(m[k], 2)) == 0.0 for k in TARGETS)
            and all(band_excess(k, r[k], SEED_TOL[k]) == 0.0 for r in rows for k in TARGETS))


def loss(rows: list[dict], m: dict, sc: dict) -> dict[str, float]:
    centre = sum(((m[k] - TARGETS[k]["centre"]) / s) ** 2 for k, s in LOSS_SCALE.items())
    band = sum((band_excess(k, m[k]) / 0.02) ** 2 for k in TARGETS)
    band += sum((band_excess(k, r[k], SEED_TOL[k]) / 0.02) ** 2 for r in rows for k in TARGETS)
    full = {"park": cb.PARK_FIXED, **sc}
    prior = 0.02 * sum(((full[k] - cb.V3_SCALARS[k]) / cb.V3_SCALARS[k]) ** 2 for k in cb.V3_SCALARS)
    return {"total": centre + band + prior, "centre": centre, "band": band, "prior": prior}


def point_record(store: Store, sc: dict, seeds=SEEDS) -> dict:
    rows = [store.rows[f"{sc['label']}|{s}"] for s in seeds]
    m = mean_of_rows(rows)
    return {"label": sc["label"], "scalars": {k: sc[k] for k in ("pap", "wfh", "beta0")},
            "reference": sc["beta0"] == BETA0_REFERENCE, "mean": m, "feasible": feasible(rows, m),
            "loss": loss(rows, m, {k: sc[k] for k in ("pap", "wfh", "beta0")}),
            "per_seed": [{k: r[k] for k in (*TARGETS, "capacity_scale", "change_6", "change_8_10")} | {"seed": r["seed"]}
                         for r in rows]}


def select(points: list[dict]) -> dict:
    cand = [p for p in points if not p["reference"]]
    feas = [p for p in cand if p["feasible"]]
    if feas:
        feas = [p for p in feas if p["scalars"]["beta0"] >= BETA0_MIN_SELECT] or feas
        centre = TARGETS["change_6_10"]["centre"]
        return min(feas, key=lambda p: (round(abs(round(p["mean"]["change_6_10"], 2) - centre), 6), p["loss"]["total"]))
    return min(cand, key=lambda p: p["loss"]["total"])


def grid(paps, wfhs, betas) -> list[dict]:
    out = []
    for pap in paps:
        for wfh in wfhs:
            for b in betas:
                sc = {"pap": pap, "wfh": wfh, "beta0": b}
                out.append({**sc, "label": label_of(sc)})
    return out


def base_ok(p: dict) -> bool:
    return (all(band_excess(k, round(p["mean"][k], 2)) == 0.0 for k in BASE_KEYS)
            and all(band_excess(k, r[k], SEED_TOL[k]) == 0.0 for r in p["per_seed"] for k in BASE_KEYS))


# ----------------------------------------------------------------------------- stages

def stage_search(store: Store, workers: int) -> dict:
    t0 = time.perf_counter()
    s1 = grid(STAGE1["pap"], STAGE1["wfh"], STAGE1["beta0"] + [BETA0_REFERENCE])
    evaluate_points(store, s1, SEEDS, workers, "stage 1")
    rec1 = [point_record(store, sc) for sc in s1]
    paps = sorted({p["scalars"]["pap"] for p in rec1 if base_ok(p)})
    if paps and min(paps) == min(STAGE1["pap"]):
        paps.insert(0, min(paps) - 1.0)
    if paps and max(paps) == max(STAGE1["pap"]):
        paps.append(max(paps) + 1.0)
    if not paps:
        best = min(rec1, key=lambda p: sum(band_excess(k, p["mean"][k]) for k in BASE_KEYS))["scalars"]["pap"]
        paps = [best - 1.0, best, best + 1.0]
    print(f"stage 2 on PAP {paps}", flush=True)
    s2 = [sc for sc in grid(paps, STAGE2["wfh"], STAGE2["beta0"]) if sc["label"] not in {x["label"] for x in s1}]
    evaluate_points(store, s2, SEEDS, workers, "stage 2")
    points = [point_record(store, sc) for sc in s1 + s2]
    chosen = select(points)
    s3_paps: list[float] = []
    if not chosen["feasible"]:
        c = chosen["scalars"]["pap"]
        s3_paps = [c + o for o in STAGE3["pap_offsets"]]
        print(f"no feasible point: stage 3 on PAP {s3_paps}", flush=True)
        done = {x["label"] for x in s1 + s2}
        s3 = [sc for sc in grid(s3_paps, STAGE3["wfh"], STAGE3["beta0"]) if sc["label"] not in done]
        evaluate_points(store, s3, SEEDS, workers, "stage 3")
        points += [point_record(store, sc) for sc in s3]
        chosen = select(points)
    print(f"chosen {chosen['label']}: feasible {chosen['feasible']}, "
          + ", ".join(f"{k} {chosen['mean'][k]:.3f}" for k in TARGETS), flush=True)
    return {"stage2_paps": paps, "stage3_paps": s3_paps, "points": points, "chosen": chosen,
            "n_points": len(points), "n_feasible": sum(p["feasible"] for p in points if not p["reference"]),
            "wall_seconds": round(time.perf_counter() - t0)}


def stage_final(store: Store, chosen: dict, workers: int) -> dict:
    sc = {**chosen["scalars"], "label": chosen["label"]}
    evaluate_points(store, [sc], OOS_SEEDS, workers, "out of sample")
    oos = point_record(store, sc, OOS_SEEDS)
    sens = []
    variants = [{**sc, "label": f"{sc['label']}__{lab}", "_extra": ov, "_lab": lab, "_what": what}
                for lab, what, ov in SENSITIVITIES]
    evaluate_points(store, variants, SEEDS, workers, "sensitivities",
                    cap_key=lambda v: f"sens_{v['_lab']}", extra=lambda v: v["_extra"])
    for v in variants:
        rows = [store.rows[f"{v['label']}|{s}"] for s in SEEDS]
        m = mean_of_rows(rows)
        sens.append({"label": v["_lab"], "what": v["_what"], "overrides": v["_extra"],
                     "mean": {k: m[k] for k in (*TARGETS, "change_6", "change_8_10", "end_car", "end_pt", "end_wfh")},
                     "feasible": feasible(rows, m)})
    return {"out_of_sample": {"seeds": list(OOS_SEEDS), "mean": oos["mean"], "per_seed": oos["per_seed"],
                              "feasible": oos["feasible"]},
            "sensitivity": sens}


# ----------------------------------------------------------------------------- report

def pct(x: float) -> str:
    return f"{100 * x:+.1f}%"


def write_report(log: dict) -> None:
    ch, s = log["chosen"], log["search"]
    m = ch["mean"]
    L = ["# Behaviour calibration, 10-day design", "",
         f"Written by `scripts/calibrate_behaviour_d10.py` on {log['date']}. Log: `data/behaviour_calibration.json`. "
         "The 30-day calibration is archived in `data/behaviour_calibration_d30.json`.", "",
         "## Design", "",
         f"R-daily, rule decider, {N_AGENTS} agents, {N_DAYS} days, seeds 1-3. Days 1-5 uncharged, NZ$6 peak ToU "
         "charge from day 6, no PT disruption. Base shares and the capacity calibration on days 2-5; response = mean "
         "car cordon crossings of days 6-10 against days 2-5.", "",
         "| Target | Band | Centre | Single-seed tolerance |", "|---|---|---|---|"]
    for k, t in TARGETS.items():
        L.append(f"| {t['what']} | {t['lo']:g} to {t['hi']:g} | {t['centre'] if t['centre'] is not None else '-'} "
                 f"| ±{SEED_TOL[k]:g} |")
    L += ["", f"Selection: {SELECTION_DOC}", "",
          "## Search", "",
          f"Stage 1: PAP {STAGE1['pap']}, k_WFH {STAGE1['wfh']}, beta0 {STAGE1['beta0']} (+ beta0 0 reference). "
          f"Stage 2: k_WFH 2-16 x beta0 {STAGE2['beta0']} on PAP {s['stage2_paps']}. "
          + (f"Stage 3 (no feasible point after stage 2): k_WFH 6-16 x the same beta0 on PAP {s['stage3_paps']}. "
             if s.get("stage3_paps") else "")
          + 
          f"{s['n_points']} points, {s['n_feasible']} feasible, {s['wall_seconds'] / 60:.0f} min.", "",
          "## Chosen point", "",
          f"PAP {ch['scalars']['pap']:g}, k_WFH {ch['scalars']['wfh']:g}, beta0 {ch['scalars']['beta0']:g} "
          f"(feasible: {ch['feasible']}).", "",
          "| Seed | Base car | Base PT | Base WFH | Days 6-10 | Day 6 | Days 8-10 | Capacity scale |",
          "|---|---|---|---|---|---|---|---|"]
    for r in ch["per_seed"]:
        L.append(f"| {r['seed']} | {r['base_car']:.3f} | {r['base_pt']:.3f} | {r['base_wfh']:.3f} | "
                 f"{pct(r['change_6_10'])} | {pct(r['change_6'])} | {pct(r['change_8_10'])} | {r['capacity_scale']:.4f} |")
    L.append(f"| mean | {m['base_car']:.3f} | {m['base_pt']:.3f} | {m['base_wfh']:.3f} | {pct(m['change_6_10'])} | "
             f"{pct(m['change_6'])} | {pct(m['change_8_10'])} | {m['capacity_scale']:.4f} |")
    L += ["", f"Days 6-10: car {m['end_car']:.3f}, PT {m['end_pt']:.3f}, WFH {m['end_wfh']:.3f}; "
          f"{100 * m['wtp_below_peak_share']:.1f}% of commuters have a WTP below the NZ$6 peak, "
          f"{100 * m['end_wtt_no_car']:.1f}% no car option on charged days. Peak 15-min road + queue delay "
          f"{m['peak_total_delay_base']:.1f} -> {m['peak_total_delay_end']:.1f} min; mean road delay "
          f"{m['road_delay_base']:.2f} -> {m['road_delay_end']:.2f} min.", ""]
    feas = sorted([p for p in s["points"] if p["feasible"] and not p["reference"]],
                  key=lambda p: (p["scalars"]["pap"], p["scalars"]["wfh"], p["scalars"]["beta0"]))
    if feas:
        L += ["Feasible points:", "", "| PAP | k_WFH | beta0 | Base car | Base PT | Days 6-10 | Loss |", "|---|---|---|---|---|---|---|"]
        for p in feas:
            q = p["mean"]
            L.append(f"| {p['scalars']['pap']:g} | {p['scalars']['wfh']:g} | {p['scalars']['beta0']:g} | "
                     f"{q['base_car']:.3f} | {q['base_pt']:.3f} | {pct(q['change_6_10'])} | {p['loss']['total']:.3f} |")
        L.append("")
    if "out_of_sample" in log:
        o = log["out_of_sample"]
        q = o["mean"]
        L += ["## Out of sample (seeds 4-12, own capacity calibration)", "",
              f"Mean: base car {q['base_car']:.3f}, PT {q['base_pt']:.3f}, WFH {q['base_wfh']:.3f}, days 6-10 "
              f"{pct(q['change_6_10'])} (single seeds {pct(min(r['change_6_10'] for r in o['per_seed']))} to "
              f"{pct(max(r['change_6_10'] for r in o['per_seed']))}); in band at the stated precision: {o['feasible']}.", ""]
    if "sensitivity" in log:
        L += ["## Sensitivity to fixed assumptions (seeds 1-3, capacity recalibrated, never adopted)", "",
              "| Variant | Base car | Days 6-10 | Day 6 | Days 8-10 |", "|---|---|---|---|---|",
              f"| chosen | {m['base_car']:.3f} | {pct(m['change_6_10'])} | {pct(m['change_6'])} | {pct(m['change_8_10'])} |"]
        for v in log["sensitivity"]:
            q = v["mean"]
            L.append(f"| {v['what']} | {q['base_car']:.3f} | {pct(q['change_6_10'])} | {pct(q['change_6'])} | "
                     f"{pct(q['change_8_10'])} |")
        L.append("")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"-> {OUT_MD}", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--stage", default="all", choices=["all", "search", "final", "report"])
    a = ap.parse_args(argv)
    store = Store()
    log: dict[str, Any] = json.loads(OUT_JSON.read_text()) if a.stage in ("final", "report") else {}
    if a.stage in ("all", "search"):
        s = stage_search(store, a.workers)
        log = {"design": "10-day (2026-10-15)", "date": time.strftime("%Y-%m-%d"), "n_agents": N_AGENTS,
               "n_days": N_DAYS, "arm": "R-daily", "seeds": list(SEEDS), "base_days": list(BASE_DAYS),
               "resp_days": list(RESP_DAYS), "fee_start_day": RESP_DAYS[0], "pt_disruption": "none",
               "targets": TARGETS, "seed_tolerance": SEED_TOL, "structural": cb.STRUCTURAL,
               "park_fixed": cb.PARK_FIXED, "fuel_cost_per_km": float(CFG0.costs.fuel_cost_per_km),
               "anchors": cb.ANCHORS, "selection": SELECTION_DOC,
               "search": {k: v for k, v in s.items() if k != "chosen"}, "chosen": s["chosen"]}
        OUT_JSON.write_text(json.dumps(log, indent=1) + "\n")
    if a.stage in ("all", "final"):
        log.update(stage_final(store, log["chosen"], a.workers))
        OUT_JSON.write_text(json.dumps(log, indent=1) + "\n")
    write_report(log)
    print(f"-> {OUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
