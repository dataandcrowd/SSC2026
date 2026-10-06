"""Behaviour calibration of the rule decider against observed cordon responses.

    .venv/bin/python scripts/calibrate_behaviour.py [--workers 12] [--stage all|search|select|final|oos|report]

What it does (R-daily arm, rule decider, PyEngine, seeds 1-3, n = 300, 30 days; LLM arms are
never calibrated):

1. ``before``: the pre-recalibration specification (paid-fee reference, eta up to 3, PAP 0, WFH =
   wfh_cost x phi, kappa_H halved at T2, paid parking NZ$8, no fuel cost), with capacity recalibrated
   per seed.
2. ``structural``: the structural fixes alone, at the v3 scalars (PAP 8, k_WFH 8), with the two
   fixed inputs of the current model: paid parking NZ$17 (PARK_FIXED, an author decision) and the
   fuel cost (costs.fuel_cost_per_km from config.toml). Neither is searched.
3. ``search``: a full grid over TWO free scalars on top of the structural fixes:
   PAP (costs.pt_attitude_penalty) x k_WFH (costs.wfh_cost). Paid parking is fixed at PARK_FIXED
   (office archetypes; student 0.75 x) and is no longer a calibrated scalar (2026-10-03, DEVIATIONS.md
   "Parking and fuel fixed by the authors"). For every grid point and seed the corridor capacity
   is recalibrated first with the project's own ``cordonlite.run.calibrate`` (R-daily, no charge,
   days 6-10, car-weighted peak 15-min queue delay = 15 min, default bisection bracket), so
   behaviour and capacity are mutually consistent at every evaluated point (a nested solve rather
   than alternation). Every evaluated point is logged. Earlier searches are archived in
   data/behaviour_calibration_pre_fuel.json (no fuel, three scalars) and
   data/behaviour_calibration_fuel023_park11.json (fuel NZ$0.23/km, three scalars) and
   data/behaviour_calibration_skip25_noearly.json (SKIP cost NZ$25, no early-start option; two
   scalars); the selection history is carried forward. The SKIP cost (NZ$30) and the early-start
   option (costs.early_start_min, costs.early_shift_cost, persona.early_shift_prob) are fixed
   assumptions of the current model (2026-10-05) and are never searched.
4. ``select``: lexicographic (SELECTION_DOC): feasible points first (3-seed means in band at the
   targets' stated precision, every seed within the stated tolerance), then the point closest to
   the literature / design anchors, then the loss. ``--stage select`` re-applies it to the log.
5. ``final``: the chosen point on seeds 1-3 and held-out seeds 4-5, no-charge counterfactuals at
   the same capacity (retiming and churn baselines), who-adapts tables by trait level, and
   population trait manipulations (all agents at level 1, 3 or 5 of one trait, capacity fixed).
6. ``oos``: out-of-sample checks that played no part in the selection: the chosen point on unseen
   seeds 6-12 and the two ridge alternatives nearest the anchors (``ridge_alternatives``) on seeds
   4-12, each with per-seed capacity calibration; where the F response comes from (WFH, PT and
   retiming by F level, population manipulation at fixed capacity). The grid is wide enough that the
   chosen point is interior; ``chosen.on_grid_edge`` records this.
7. ``report``: data/behaviour_calibration.json and docs/calibration_report.md with figures in
   docs/figures/. ``--stage select`` appends the rule it replaces to ``search.selection_history``.

Everything runs in-process into temporary folders; runs/ and data/calibration.json are not
touched. Capacity calibration for the chosen values is written separately with
``python -m cordonlite.run calibrate --seeds 1 2 3`` once config.toml holds them.
"""

from __future__ import annotations

import argparse
import dataclasses
import itertools
import json
import math
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

OUT_JSON = ROOT / "data" / "behaviour_calibration.json"
PRE_FUEL_JSON = ROOT / "data" / "behaviour_calibration_pre_fuel.json"   # archived log of the calibration without fuel
PREV_JSON = ROOT / "data" / "behaviour_calibration_fuel023_park11.json"   # archived log: fuel 0.23/km, parking searched (chose 11)
LAST_JSON = ROOT / "data" / "behaviour_calibration_skip25_noearly.json"   # archived log: SKIP cost 25, no early start (chose PAP 20 / k_WFH 10)
OUT_MD = ROOT / "docs" / "calibration_report.md"
FIG_DIR = ROOT / "docs" / "figures"

SEEDS = (1, 2, 3)
HOLDOUT_SEEDS = (4, 5)
OOS_SEEDS = tuple(range(6, 13))   # unseen seeds, used only by --stage oos (never in the selection)
# Ridge alternatives checked out of sample: chosen from the search log by ridge_alternatives() (the
# non-feasible points that become feasible when the soft overshoot bound is relaxed, nearest the
# anchors first). Before the fuel addition these were PAP 8 / parking 15 and PAP 10 / parking 17.
N_RIDGE_ALTERNATIVES = 2
N_AGENTS, N_DAYS = 300, 30
PEAK_BAND = (480, 540)        # gate exits 08:00-09:00, the NZ$6 band of the ToU schedule
SHOULDER_BAND = (420, 480)    # 07:00-08:00 (NZ$4 to 07:30, ramp to NZ$6 at 08:00)

# ----------------------------------------------------------------------------- targets
# All targets are stated assumptions [A]; the response anchors are Stockholm (about -20%, after
# -28% then -23%) and Gothenburg (about -12%): Boerjesson et al. 2012, Transport Policy 20:1-12;
# Boerjesson and Kristoffersson 2015, TR-A 75:134-146 (v3 reference list).
TARGETS = {
    "base_car": {"lo": 0.75, "hi": 0.85, "centre": 0.80,
                 "what": "car share, mean of days 6-10 (pre-charge), R-daily"},
    "base_pt": {"lo": 0.08, "hi": 0.15, "centre": 0.115, "what": "PT share, days 6-10"},
    "base_wfh": {"lo": 0.0, "hi": 0.10, "centre": None, "what": "WFH share, days 6-10 (at most)"},
    "base_skip": {"lo": 0.0, "hi": 0.02, "centre": None, "what": "SKIP share, days 6-10 (at most)"},
    "change_21_30": {"lo": -0.22, "hi": -0.12, "centre": -0.20,
                     "what": "car cordon crossings, mean days 21-30 vs mean days 6-10"},
    "change_11_13": {"lo": -0.30, "hi": 0.0, "centre": None,
                     "what": "overshoot, mean days 11-13 vs days 6-10 (may reach about -30%)"},
}
# stated tolerance for single seeds (n = 300): shares +/- 0.05, response +/- 4 pp
SEED_TOL = {"base_car": 0.05, "base_pt": 0.05, "base_wfh": 0.05, "base_skip": 0.0,
            "change_21_30": 0.04, "change_11_13": 0.04}


def park(x: float) -> dict[str, Any]:
    """Paid parking for office archetypes 1-3; student 0.75 x (v3: 6 vs 8); trades/company 0."""
    return {"persona.park_cost_paid": [x, x, x, 0.0, round(0.75 * x, 4)]}


ETA_V3_CAPPED = [0.0, 0.25, 0.5, 0.75, 1.0]
BEFORE = {   # the specification state before this recalibration (explicit, independent of config.toml)
    "memory.ref_fee_update": "all_days",
    "traits.eta": [0.0, 0.5, 1.0, 2.0, 3.0],
    "costs.wfh_form": "spec",
    "clock.discontinuity_triggers": ["T1", "T2", "T4", "T6"],
    "costs.pt_attitude_penalty": 0.0,
    "costs.wfh_cost": 8.0,
    "costs.fuel_cost_per_km": 0.0,   # the specification had no fuel cost
    "costs.skip_cost": 25.0,         # the specification value (NZ$30 since 2026-10-05)
    "persona.early_shift_prob": [0.0, 0.0, 0.0, 0.0, 0.0],   # the specification had no early-start option
    **park(8.0),
}
STRUCTURAL = {   # structural fixes (values the v3 note justifies; see DEVIATIONS.md, Recalibration)
    "memory.ref_fee_update": "faced",
    "traits.eta": ETA_V3_CAPPED,
    "costs.wfh_form": "v3_relative",
    "clock.discontinuity_triggers": ["T1", "T4", "T6"],
}
V3_SCALARS = {"pap": 8.0, "park": 8.0, "wfh": 8.0}
# Literature / design anchors used to choose inside the feasible set: PAP and k_WFH at the v3 values.
# Paid parking is NOT searched any more: it is fixed at NZ$17/day [author decision, 2026-10-03], consistent
# with the all-day rate of Auckland Transport's Downtown, Civic and Victoria Street car parks from 1 Dec 2014
# (Greater Auckland, 18 Nov 2014, quoting AT). It stays in the scalars dict (constant) so that the loss and the
# anchor distance keep their earlier form; both terms are the same at every point.
PARK_FIXED = 17.0
ANCHORS = {"pap": 8.0, "park": 17.0, "wfh": 8.0}
# Two free scalars. The grid was fixed after a range-finding probe (PAP 12-40 in steps of 4 at k_WFH 8 and 12,
# seeds 1-3, logged under search.range_probe) and before the search: NZ$1 steps, wide enough that the chosen
# point is not on an edge (the earlier ranges were PAP 4-12 and k_WFH 2-8, with both chosen values on the edge).
GRID = {"pap": [float(x) for x in range(10, 37)],
        "wfh": [float(x) for x in range(2, 17)]}
RANGE_PROBE = [   # 3-seed means of the range-finding probe, parking 17, fuel 0.30 (run before the grid was fixed)
    {"pap": 12, "wfh": 8, "base_car": 0.663, "base_pt": 0.318, "base_skip": 0.009, "change_21_30": -0.220, "change_11_13": -0.330},
    {"pap": 12, "wfh": 12, "base_car": 0.671, "base_pt": 0.319, "base_skip": 0.010, "change_21_30": -0.156, "change_11_13": -0.251},
    {"pap": 16, "wfh": 8, "base_car": 0.736, "base_pt": 0.239, "base_skip": 0.014, "change_21_30": -0.213, "change_11_13": -0.320},
    {"pap": 16, "wfh": 12, "base_car": 0.750, "base_pt": 0.236, "base_skip": 0.013, "change_21_30": -0.160, "change_11_13": -0.250},
    {"pap": 20, "wfh": 8, "base_car": 0.828, "base_pt": 0.145, "base_skip": 0.020, "change_21_30": -0.223, "change_11_13": -0.340},
    {"pap": 20, "wfh": 12, "base_car": 0.833, "base_pt": 0.146, "base_skip": 0.019, "change_21_30": -0.163, "change_11_13": -0.257},
    {"pap": 24, "wfh": 8, "base_car": 0.851, "base_pt": 0.106, "base_skip": 0.034, "change_21_30": -0.201, "change_11_13": -0.307},
    {"pap": 24, "wfh": 12, "base_car": 0.861, "base_pt": 0.105, "base_skip": 0.032, "change_21_30": -0.140, "change_11_13": -0.231},
    {"pap": 28, "wfh": 8, "base_car": 0.872, "base_pt": 0.082, "base_skip": 0.038, "change_21_30": -0.186, "change_11_13": -0.305},
    {"pap": 28, "wfh": 12, "base_car": 0.881, "base_pt": 0.081, "base_skip": 0.036, "change_21_30": -0.127, "change_11_13": -0.217},
    {"pap": 32, "wfh": 8, "base_car": 0.908, "base_pt": 0.046, "base_skip": 0.038, "change_21_30": -0.204, "change_11_13": -0.315},
    {"pap": 32, "wfh": 12, "base_car": 0.903, "base_pt": 0.054, "base_skip": 0.040, "change_21_30": -0.126, "change_11_13": -0.210},
    {"pap": 40, "wfh": 8, "base_car": 0.928, "base_pt": 0.016, "base_skip": 0.047, "change_21_30": -0.194, "change_11_13": -0.307},
    {"pap": 40, "wfh": 12, "base_car": 0.940, "base_pt": 0.016, "base_skip": 0.042, "change_21_30": -0.134, "change_11_13": -0.232},
]


def on_grid_edge(sc: dict[str, float]) -> dict[str, bool]:
    return {k: sc[k] in (min(GRID[k]), max(GRID[k])) for k in GRID}


def point_overrides(pap: float, park_paid: float, wfh: float) -> dict[str, Any]:
    return {**STRUCTURAL, "costs.pt_attitude_penalty": pap, "costs.wfh_cost": wfh, **park(park_paid)}


# ----------------------------------------------------------------------------- one evaluation


def _modal(vals: list) -> Any:
    c = Counter(vals)
    return max(c.items(), key=lambda kv: (kv[1], str(kv[0])))[0]


def metrics(res, n: int) -> dict[str, Any]:
    """Target metrics and day series of one run."""
    days = res.days
    out = pd.DataFrame(res.outcomes)
    car = out[(out["mode"] == "CAR") & (out["gate_exit_min"].astype(float) >= 0)]
    cross = car.groupby("day").size().reindex(range(1, len(days) + 1), fill_value=0)
    cr = cross.to_numpy(dtype=float)
    pre = cr[5:10].mean()

    def chg(a, b):
        return float(cr[a - 1:b].mean() / pre - 1.0) if pre else float("nan")

    def band_share(d0, d1, band):
        g = car[(car["day"] >= d0) & (car["day"] <= d1)]["gate_exit_min"].astype(int)
        return float(((g >= band[0]) & (g < band[1])).mean()) if len(g) else float("nan")

    def hist(d0, d1):
        g = car[(car["day"] >= d0) & (car["day"] <= d1)]["gate_exit_min"].astype(int)
        b = (g // 15) * 15
        h = b.value_counts().sort_index() / (d1 - d0 + 1)
        return {int(k): float(v) for k, v in h.items()}

    def band_cross(d0, d1, band):   # crossings per day with a gate exit inside the band
        g = car[(car["day"] >= d0) & (car["day"] <= d1)]["gate_exit_min"].astype(int)
        return float(((g >= band[0]) & (g < band[1])).sum()) / (d1 - d0 + 1)

    def band_chg(band):
        b0 = band_cross(6, 10, band)
        return float(band_cross(21, 30, band) / b0 - 1.0) if b0 else float("nan")

    share = {k: [d[k] / n for d in days] for k in ("cars", "pt", "wfh", "skip")}
    early = [d.get("early_shift", 0) / n for d in days]            # commuters working the early day (car or PT)
    early_car = [d.get("early_shift_cars", 0) / max(d["cars"], 1) for d in days]   # share of that day's car users
    m = {
        "base_car": float(np.mean(share["cars"][5:10])),
        "base_pt": float(np.mean(share["pt"][5:10])),
        "base_wfh": float(np.mean(share["wfh"][5:10])),
        "base_skip": float(np.mean(share["skip"][5:10])),
        "change_21_30": chg(21, 30),
        "change_11_13": chg(11, 13),
        "change_by_day": [float(x / pre - 1.0) for x in cr],
        "crossings_by_day": [int(x) for x in cr],
        "share_by_day": {k: [round(x, 4) for x in v] for k, v in share.items()},
        "end_car": float(np.mean(share["cars"][20:30])),
        "end_pt": float(np.mean(share["pt"][20:30])),
        "end_wfh": float(np.mean(share["wfh"][20:30])),
        "end_skip": float(np.mean(share["skip"][20:30])),
        "base_early": float(np.mean(early[5:10])),
        "end_early": float(np.mean(early[20:30])),
        "early_11_13": float(np.mean(early[10:13])),
        "base_early_of_cars": float(np.mean(early_car[5:10])),
        "end_early_of_cars": float(np.mean(early_car[20:30])),
        "early_by_day": [round(x, 4) for x in early],
        "peak_cross_6_10": band_cross(6, 10, PEAK_BAND),
        "peak_cross_21_30": band_cross(21, 30, PEAK_BAND),
        "peak_cross_change": band_chg(PEAK_BAND),                       # 08:00-09:00 crossings, d21-30 vs d6-10
        "pre0730_cross_change": band_chg((0, 450)),                     # crossings before 07:30 (NZ$4 or less)
        "peak_band_share_6_10": band_share(6, 10, PEAK_BAND),
        "peak_band_share_21_30": band_share(21, 30, PEAK_BAND),
        "shoulder_share_6_10": band_share(6, 10, SHOULDER_BAND),
        "shoulder_share_21_30": band_share(21, 30, SHOULDER_BAND),
        "exit_hist_6_10": hist(6, 10),
        "exit_hist_21_30": hist(21, 30),
        "peak_delay_6_10": float(np.mean([d["peak_bin_delay_wmean"] for d in days[5:10]])),
        "peak_delay_21_30": float(np.mean([d["peak_bin_delay_wmean"] for d in days[20:30]])),
        "revenue": float(sum(d["revenue"] for d in days)),
    }
    return m


def agent_frame(res, n_twins: int, cfg_early_start: int = 420) -> list[dict]:
    """Per-agent behaviour summary for who-adapts tables (twins flagged)."""
    out = pd.DataFrame(res.outcomes)
    out["key"] = np.where(out["mode"] == "CAR", "CAR_" + out["depart_min"].astype("Int64").astype(str),
                          out["mode"])
    n = len(res.personas)
    k = min(n_twins, n // 2)
    rows = []
    by_agent = {a: g.sort_values("day") for a, g in out.groupby("agent_id")}
    for p in res.personas:
        g = by_agent[p.agent_id]
        keys = g["key"].tolist()
        modes = g["mode"].tolist()
        es = [bool(x) for x in g["early_shift"].tolist()]
        rows.append({
            "agent_id": p.agent_id, "twin": p.agent_id >= n - k, "H": p.H, "F": p.F, "P": p.P, "S": p.S,
            "archetype": p.archetype, "pt_allowed": bool(p.pt_allowed), "company_car": bool(p.company_car),
            "parking_cost": float(p.parking_cost), "vot": float(p.vot),
            "mode_d10": modes[9], "key_d10": keys[9], "mode_d11": modes[10],
            "modal_6_10": _modal(keys[5:10]), "modal_26_30": _modal(keys[25:30]),
            "modal_11_13_mode": _modal(modes[10:13]),
            "early_ok": bool(p.early_shift_ok and p.tstar_min > cfg_early_start),
            "early_days_6_10": int(sum(es[5:10])), "early_days_26_30": int(sum(es[25:30])),
        })
    return rows


def evaluate(job: dict) -> dict:
    """One (overrides, seed) evaluation. job: label, overrides, seed, scale ('calibrate' or float),
    nofee (also run a no-charge counterfactual at the same capacity), agents (return agent rows)."""
    from cordonlite.config import load_config
    from cordonlite.run import calibrate, simulate

    t0 = time.perf_counter()
    ov = {"run.arm": "R-daily", "run.seed": int(job["seed"]), "run.n_agents": N_AGENTS,
          "run.n_days": N_DAYS, **job["overrides"]}
    cfg = load_config(overrides=ov)
    calib = None
    scale = job["scale"]
    if scale == "calibrate":
        rec = calibrate(cfg, progress=False)
        scale = float(rec["capacity_scale"])
        calib = {"capacity_scale": scale, "achieved_peak_delay_min": rec["achieved_peak_delay_min"],
                 "status": rec["status"], "n_probes": len(rec["history"])}
    with tempfile.TemporaryDirectory(prefix="cl_bcal_") as tmp:
        res = simulate(cfg, Path(tmp), float(scale), engine_kind="py", write_plans=False)
    row = {"label": job["label"], "seed": int(job["seed"]), "capacity_scale": float(scale),
           "calibration": calib, **job.get("meta", {}), **metrics(res, N_AGENTS)}
    paying = [float(p.fuel_cost) for p in res.personas if not p.company_car]
    row["fuel_mean_paying"] = float(np.mean(paying)) if paying else 0.0
    row["fuel_p10_p90_paying"] = [float(np.percentile(paying, 10)), float(np.percentile(paying, 90))] if paying else [0.0, 0.0]
    if job.get("agents"):
        row["agents"] = agent_frame(res, cfg.persona.n_twins, int(cfg.costs.early_start_min))
    row["early_ok_share"] = float(np.mean([bool(p.early_shift_ok and p.tstar_min > cfg.costs.early_start_min)
                                           for p in res.personas]))
    if job.get("nofee"):
        cfg0 = dataclasses.replace(cfg, fees=dataclasses.replace(cfg.fees, regime="none"))
        with tempfile.TemporaryDirectory(prefix="cl_bcal0_") as tmp:
            res0 = simulate(cfg0, Path(tmp), float(scale), engine_kind="py", write_plans=False)
        m0 = metrics(res0, N_AGENTS)
        row["nofee"] = {k: m0[k] for k in ("crossings_by_day", "peak_band_share_21_30", "shoulder_share_21_30",
                                           "exit_hist_21_30", "end_car", "base_car", "end_pt", "base_pt",
                                           "end_wfh", "base_wfh", "change_by_day", "change_21_30", "base_skip",
                                           "end_skip", "base_early", "end_early", "base_early_of_cars",
                                           "end_early_of_cars", "early_by_day", "peak_cross_change",
                                           "pre0730_cross_change", "peak_cross_6_10", "peak_cross_21_30")}
        if job.get("agents"):
            row["nofee"]["agents"] = agent_frame(res0, cfg.persona.n_twins, int(cfg.costs.early_start_min))
    row["seconds"] = round(time.perf_counter() - t0, 1)
    return row


def run_jobs(jobs: list[dict], workers: int, desc: str) -> list[dict]:
    t0 = time.perf_counter()
    out: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, r in enumerate(ex.map(evaluate, jobs), 1):
            out.append(r)
            if i % max(1, len(jobs) // 10) == 0 or i == len(jobs):
                print(f"  {desc}: {i}/{len(jobs)} [{time.perf_counter() - t0:.0f}s]", flush=True)
    return out


# ----------------------------------------------------------------------------- selection

SUMMARY_KEYS = ("base_car", "base_pt", "base_wfh", "base_skip", "change_21_30", "change_11_13",
                "peak_band_share_6_10", "peak_band_share_21_30", "end_car", "end_pt", "end_wfh",
                "capacity_scale", "peak_delay_6_10", "peak_delay_21_30",
                "end_skip", "base_early", "end_early", "base_early_of_cars", "end_early_of_cars",
                "peak_cross_change", "pre0730_cross_change")
LOSS_SCALE = {"base_car": 0.05, "base_pt": 0.035, "change_21_30": 0.04}


def summarise(rows: list[dict]) -> dict[str, float]:
    return {k: float(np.mean([r[k] for r in rows])) for k in SUMMARY_KEYS}


def summarise_keys(rows: list[dict], keys) -> dict[str, float]:
    return {k: float(np.mean([r[k] for r in rows])) for k in keys}


def band_excess(key: str, v: float, tol: float = 0.0) -> float:
    t = TARGETS[key]
    return max(0.0, t["lo"] - tol - v, v - t["hi"] - tol)


def loss(rows: list[dict], scalars: dict[str, float]) -> dict[str, float]:
    """Loss of one grid point over its seeds.

    centre: sum of squared (3-seed mean - centre) / scale for base car, base PT and the d21-30
            response (scales 0.05, 0.035, 0.04);
    band:   squared band excess of the 3-seed means for every target (scale 0.02), plus squared
            excess beyond the stated single-seed tolerance for each seed;
    prior:  0.02 x sum of squared relative distances of the scalars from the v3 values (8, 8, 8),
            a weak tie-break toward the design-note values.
    """
    m = summarise(rows)
    centre = sum(((m[k] - TARGETS[k]["centre"]) / s) ** 2 for k, s in LOSS_SCALE.items())
    band = sum((band_excess(k, m[k]) / 0.02) ** 2 for k in TARGETS)
    band += sum((band_excess(k, r[k], SEED_TOL[k]) / 0.02) ** 2 for r in rows for k in TARGETS)
    prior = 0.02 * sum(((scalars[k] - V3_SCALARS[k]) / V3_SCALARS[k]) ** 2 for k in V3_SCALARS)
    return {"total": centre + band + prior, "centre": centre, "band": band, "prior": prior}


def feasible(rows: list[dict], mean: dict[str, float] | None = None) -> bool:
    """Every 3-seed mean inside its target band at the precision the targets are stated in (shares to
    2 decimals, changes to whole percent), and every seed within the stated single-seed tolerance."""
    m = mean or {k: float(np.mean([r[k] for r in rows])) for k in TARGETS}
    return (all(band_excess(k, round(m[k], 2)) == 0.0 for k in TARGETS)
            and all(band_excess(k, r[k], SEED_TOL[k]) == 0.0 for r in rows for k in TARGETS))


def anchor_distance(sc: dict[str, float]) -> float:
    return float(sum(((sc[k] - ANCHORS[k]) / ANCHORS[k]) ** 2 for k in ANCHORS))


SELECTION_DOC = ("lexicographic: (1) feasible = every 3-seed mean in its target band at the targets' stated "
                 "precision (shares to 2 decimals, changes to whole percent) and every seed within the stated "
                 "single-seed tolerance; (2) among feasible points, the smallest squared relative distance "
                 "to the anchors (PAP 8 [v3], paid parking 17 [AT car-park all-day rate 2014], k_WFH 8 [v3]); "
                 "(3) loss as tie-break. If no point is feasible, the lowest loss.")


def select(points: list[dict]) -> dict:
    feas = [p for p in points if p["feasible"]]
    if feas:
        return min(feas, key=lambda p: (round(anchor_distance(p["scalars"]), 9), p["loss"]["total"]))
    return min(points, key=lambda p: p["loss"]["total"])


def ridge_alternatives(points: list[dict], chosen_label: str, n: int = N_RIDGE_ALTERNATIVES) -> list[tuple]:
    """Alternatives checked out of sample: non-feasible points nearest the anchors that become feasible
    when the soft overshoot bound is relaxed to -33% (the rule used since the search without fuel);
    filled up from the ten lowest-loss other points (nearest the anchors first) when fewer than n qualify."""
    lo0 = TARGETS["change_11_13"]["lo"]
    try:
        TARGETS["change_11_13"]["lo"] = -0.33
        relaxed = [p for p in points if not p["feasible"] and p["label"] != chosen_label
                   and feasible(p["per_seed"], p["mean"])]
    finally:
        TARGETS["change_11_13"]["lo"] = lo0
    relaxed.sort(key=lambda p: (round(anchor_distance(p["scalars"]), 9), p["loss"]["total"]))
    out = relaxed[:n]
    if len(out) < n:
        rest = sorted((p for p in points if p["label"] != chosen_label and p not in out),
                      key=lambda q: q["loss"]["total"])[:10]
        rest.sort(key=lambda p: (round(anchor_distance(p["scalars"]), 9), p["loss"]["total"]))
        out += rest[:n - len(out)]
    return [(p["scalars"]["pap"], p["scalars"]["park"], p["scalars"]["wfh"]) for p in out]


def selection_sensitivity(points: list[dict]) -> dict[str, Any]:
    """How the selection depends on rounding and on the soft overshoot bound (no new runs)."""
    def strict(p):
        m = p["mean"]
        return (all(band_excess(k, m[k]) == 0.0 for k in TARGETS)
                and all(band_excess(k, r[k], SEED_TOL[k]) == 0.0 for r in p["per_seed"] for k in TARGETS))

    out: dict[str, Any] = {
        "feasible_rounded": [p["label"] for p in points if feasible(p["per_seed"], p["mean"])],
        "feasible_strict": [p["label"] for p in points if strict(p)],
        "lowest_loss": min(points, key=lambda p: p["loss"]["total"])["label"],
        "overshoot_bound": [],
    }
    lo0 = TARGETS["change_11_13"]["lo"]
    try:
        for lo in (-0.30, -0.31, -0.32, -0.33):
            TARGETS["change_11_13"]["lo"] = lo
            feas = [p for p in points if feasible(p["per_seed"], p["mean"])]
            pick = (min(feas, key=lambda p: (round(anchor_distance(p["scalars"]), 9), p["loss"]["total"]))
                    if feas else min(points, key=lambda p: p["loss"]["total"]))
            out["overshoot_bound"].append({"lo": lo, "feasible": [p["label"] for p in feas], "chosen": pick["label"]})
    finally:
        TARGETS["change_11_13"]["lo"] = lo0
    return out


def target_status(rows: list[dict]) -> dict[str, Any]:
    m = summarise(rows)
    st = {}
    for k, t in TARGETS.items():
        st[k] = {"mean": m[k], "per_seed": [r[k] for r in rows], "lo": t["lo"], "hi": t["hi"],
                 "mean_in_band": band_excess(k, m[k]) == 0.0,
                 "seeds_in_band": [band_excess(k, r[k]) == 0.0 for r in rows],
                 "seeds_within_tolerance": [band_excess(k, r[k], SEED_TOL[k]) == 0.0 for r in rows]}
    return st


# ----------------------------------------------------------------------------- who adapts


def wilson(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def who_adapts(agent_rows: list[dict], nofee_rows: list[dict] | None = None) -> pd.DataFrame:
    """Day-10 drivers (non-twins, not company cars) pooled over seeds; outcome shares by trait level.

    keep_d11: drives on day 11 (the charge wake); keep_end: modal option days 26-30 is a car
    option; to_pt_end: modal option days 26-30 is PT (PT-feasible drivers only); retime_end: still
    a car user at days 26-30 with a different modal departure than days 6-10 (among keepers).
    With ``nofee_rows`` the same shares from the no-charge counterfactual are added (``*_nofee``),
    which removes the day-to-day churn and selection that a charge-free run also shows."""
    def prep(rows):
        df = pd.DataFrame(rows)
        df = df[(~df["twin"]) & (~df["company_car"]) & (df["mode_d10"] == "CAR")
                & df["modal_6_10"].str.startswith("CAR")].copy()
        df["keep_d11"] = df["mode_d11"] == "CAR"
        df["keep_end"] = df["modal_26_30"].str.startswith("CAR")
        df["to_pt_end"] = df["modal_26_30"] == "PT"
        df["retime_end"] = df["keep_end"] & (df["modal_26_30"] != df["modal_6_10"])
        return df

    def prep_all(rows):   # every PT-feasible non-twin agent, whatever its day-10 mode
        df = pd.DataFrame(rows)
        df = df[(~df["twin"]) & df["pt_allowed"]].copy()
        df["pt_end_all"] = df["modal_26_30"] == "PT"
        return df

    df = prep(agent_rows)
    d0 = prep(nofee_rows) if nofee_rows else None
    da = prep_all(agent_rows)
    da0 = prep_all(nofee_rows) if nofee_rows else None
    out = []
    for lv in range(1, 6):
        g = da[da["P"] == lv]
        k, n = int(g["pt_end_all"].sum()), len(g)
        lo, hi = wilson(k, n)
        r = {"trait": "P", "level": lv, "metric": "pt_end_all", "n": n, "share": k / n if n else float("nan"),
             "ci_lo": lo, "ci_hi": hi}
        if da0 is not None:
            g0 = da0[da0["P"] == lv]
            r["n_nofee"] = len(g0)
            r["share_nofee"] = float(g0["pt_end_all"].mean()) if len(g0) else float("nan")
        out.append(r)
    for trait in ("H", "P", "F", "S"):
        for lv in range(1, 6):
            for metric, sub in (("keep_d11", None), ("keep_end", None), ("to_pt_end", "pt_allowed"),
                                ("retime_end", "keep_end")):
                g = df[df[trait] == lv]
                if sub:
                    g = g[g[sub]]
                k, n = int(g[metric].sum()), len(g)
                lo, hi = wilson(k, n)
                r = {"trait": trait, "level": lv, "metric": metric, "n": n, "share": k / n if n else float("nan"),
                     "ci_lo": lo, "ci_hi": hi}
                if d0 is not None:
                    g0 = d0[d0[trait] == lv]
                    if sub:
                        g0 = g0[g0[sub]]
                    r["n_nofee"] = len(g0)
                    r["share_nofee"] = float(g0[metric].mean()) if len(g0) else float("nan")
                out.append(r)
    return pd.DataFrame(out)


def paired_retiming(agents: list[dict], agents0: list[dict], by: str | None = None) -> dict | list[dict]:
    """Paired (common random numbers) retiming: agents who are car users at days 26-30 in BOTH the
    charged run and the no-charge run at the same capacity and seed; share whose modal departure
    differs, mean signed shift (min) and share moved earlier / later. Rule noise is drawn per
    (seed, agent, day, option), so the two runs differ only through the charge and its feedback.
    Rows must carry a 'seed' key."""
    a = pd.DataFrame(agents)
    b = pd.DataFrame(agents0)[["seed", "agent_id", "modal_26_30"]].rename(columns={"modal_26_30": "nofee"})
    d = a.merge(b, on=["seed", "agent_id"])
    d = d[(~d["twin"]) & d["modal_26_30"].str.startswith("CAR") & d["nofee"].str.startswith("CAR")].copy()
    d["shift"] = d["modal_26_30"].str[4:].astype(int) - d["nofee"].str[4:].astype(int)

    def summ(g):
        n = len(g)
        k = int((g["shift"] != 0).sum())
        lo, hi = wilson(k, n)
        return {"n": n, "retimed": k / n if n else float("nan"), "ci_lo": lo, "ci_hi": hi,
                "mean_shift_min": float(g["shift"].mean()) if n else float("nan"),
                "earlier": float((g["shift"] < 0).mean()) if n else float("nan"),
                "later": float((g["shift"] > 0).mean()) if n else float("nan")}

    if by is None:
        return summ(d)
    return [{"level": int(lv), **summ(g)} for lv, g in d.groupby(by)]


def spearman_sign(levels: list[int], vals: list[float]) -> str:
    v = [x for x in vals if not math.isnan(x)]
    if len(v) < 2:
        return "n/a"
    d = np.diff([x for x in vals if not math.isnan(x)])
    if np.all(d >= -1e-9):
        return "monotone up"
    if np.all(d <= 1e-9):
        return "monotone down"
    return "not monotone"


# ----------------------------------------------------------------------------- figures


def figures(before: list[dict], after: list[dict], after_nofee: list[dict], grid_rows: list[dict],
            chosen: dict) -> dict[str, str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from cordonlite.analysis import INK, INK2, GRID as GRIDC, MODE_COLOURS, SLOTS
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "axes.labelcolor": INK,
                         "xtick.color": INK2, "ytick.color": INK2, "axes.titlesize": 10})
    days = np.arange(1, N_DAYS + 1)
    paths = {}

    def style(ax):
        ax.grid(True, color=GRIDC, lw=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.axvline(10.5, color=INK2, lw=0.8, ls=":")
        ax.axvline(20, color=INK2, lw=0.8, ls=":")

    # 1. mode shares by day, before vs after (3-seed mean, seed range shaded)
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.8), sharey=True)
    for ax, rows, title in ((axes[0], before, "Before (specification GC)"),
                            (axes[1], after, "After (structural fixes + calibration)")):
        for key, mode in (("cars", "CAR"), ("pt", "PT"), ("wfh", "WFH"), ("skip", "SKIP")):
            arr = np.array([r["share_by_day"][key] for r in rows])
            ax.fill_between(days, arr.min(0), arr.max(0), color=MODE_COLOURS[mode], alpha=0.18, lw=0)
            ax.plot(days, arr.mean(0), color=MODE_COLOURS[mode], lw=2, label=mode)
            ax.annotate(mode, (days[-1], arr.mean(0)[-1]), xytext=(4, 0), textcoords="offset points",
                        color=INK2, va="center", fontsize=8)
        style(ax)
        ax.set_title(title, color=INK)
        ax.set_xlabel("day (charge from day 11; PT disruption day 20)")
        ax.set_xlim(1, N_DAYS + 2.5)
    axes[0].set_ylabel("share of commuters (R-daily, seeds 1-3)")
    axes[0].set_ylim(0, 1)
    h, lab = axes[1].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=4, frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    p = FIG_DIR / "calib_mode_shares.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    paths["mode_shares"] = str(p.relative_to(ROOT))

    # 2. crossing change by day with Stockholm / Gothenburg references
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.axhspan(-0.22, -0.12, color="#d9d8d2", alpha=0.6, lw=0)
    ax.text(16, -0.105, "target band -12% to -22% (shaded)", color=INK2, fontsize=7.5)
    for y, lab in ((-0.20, "Stockholm about -20%"), (-0.12, "Gothenburg about -12%")):
        ax.axhline(y, color=INK2, lw=0.9, ls="--")
        ax.text(1.2, y + 0.012, lab, color=INK2, fontsize=7.5)
    ax.plot([11, 12.5], [-0.28, -0.23], ls="none", marker="D", ms=5, color=INK2)
    ax.text(13.2, -0.375, "Stockholm initial -28%, then -23% (diamonds)", color=INK2, fontsize=7.5, va="center")
    for rows, col, lab in ((before, SLOTS[1], "before"), (after, SLOTS[0], "after")):
        arr = np.array([r["change_by_day"] for r in rows])
        ax.fill_between(days, arr.min(0), arr.max(0), color=col, alpha=0.18, lw=0)
        ax.plot(days, arr.mean(0), color=col, lw=2, label=lab)
        ax.annotate(lab, (days[-1], arr.mean(0)[-1]), xytext=(4, 0), textcoords="offset points",
                    color=INK2, va="center", fontsize=8)
    style(ax)
    ax.set_xlim(1, 33)
    ax.set_ylim(-0.75, 0.1)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_xlabel("day (charge from day 11; PT disruption day 20)")
    ax.set_ylabel("car cordon crossings vs days 6-10")
    ax.legend(loc="lower left", frameon=False, fontsize=8)
    ax.set_title("Car cordon crossings relative to days 6-10 (R-daily, mean of seeds 1-3, range shaded)",
                 color=INK)
    fig.tight_layout()
    p = FIG_DIR / "calib_crossing_change.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    paths["crossing_change"] = str(p.relative_to(ROOT))

    # 3. crossing-time distribution, days 21-30, charged vs no-charge counterfactual (after)
    bins = np.arange(330, 660, 15)

    def mean_hist(dicts):
        return np.array([[d.get(int(b), 0.0) for b in bins] for d in dicts]).mean(0)

    h1 = mean_hist([r["exit_hist_21_30"] for r in after])
    h0 = mean_hist([r["exit_hist_21_30"] for r in after_nofee])
    fig, (ax0, ax) = plt.subplots(2, 1, figsize=(8, 4.4), sharex=True, gridspec_kw={"height_ratios": [1, 3]})
    from cordonlite import fees as feesmod
    from cordonlite.config import load_config
    tbl = feesmod.fee_table_from_config(load_config())
    mins = np.arange(330, 660)
    ax0.plot(mins, [tbl[m] for m in mins], color=INK2, lw=1.5)
    ax0.set_ylabel("NZ$")
    ax0.set_title("ToU charge (from day 11) and car crossings per 15 min, days 21-30", color=INK)
    for s in ("top", "right"):
        ax0.spines[s].set_visible(False)
    w = 6.5
    ax.bar(bins + 7.5 - w / 2 - 0.5, h0, width=w, color=SLOTS[1], label="no charge (same capacity)")
    ax.bar(bins + 7.5 + w / 2 + 0.5, h1, width=w, color=SLOTS[0], label="charge")
    ax.set_ylabel("crossings per day (mean of seeds 1-3)")
    ax.set_xticks(np.arange(360, 661, 60))
    ax.set_xticklabels([f"{m // 60:02d}:{m % 60:02d}" for m in np.arange(360, 661, 60)])
    ax.set_xlabel("gate exit time")
    ax.grid(True, axis="y", color=GRIDC, lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    p = FIG_DIR / "calib_crossing_times.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    paths["crossing_times"] = str(p.relative_to(ROOT))

    # 4. search surface over the two free scalars: d21-30 response and base PT
    df = pd.DataFrame([{**g["scalars"], **g["mean"]} for g in grid_rows])
    fig, axes = plt.subplots(2, 1, figsize=(13, 10.5))
    for ax, key, title, fmt in ((axes[0], "change_21_30", "crossings change d21-30 vs d6-10 (%)", "{:+.0f}"),
                                (axes[1], "base_pt", "pre-charge PT share (days 6-10, %)", "{:.0f}")):
        piv = df.pivot(index="wfh", columns="pap", values=key).sort_index(ascending=False)
        ax.imshow(np.abs(piv.to_numpy() - (TARGETS[key]["centre"])), cmap="Greys_r", aspect="auto",
                  vmin=0, vmax=0.25 if key == "change_21_30" else 0.15)
        for i, wf in enumerate(piv.index):
            for j, pap in enumerate(piv.columns):
                v = piv.loc[wf, pap]
                if pd.isna(v):
                    continue
                mark = "*" if (pap == chosen["pap"] and wf == chosen["wfh"]) else ""
                ax.text(j, i, fmt.format(v * 100) + mark, ha="center", va="center", fontsize=7.5,
                        color="#ffffff" if abs(v - TARGETS[key]["centre"]) < 0.06 else INK)
        ax.set_xticks(range(len(piv.columns)), [f"{c:g}" for c in piv.columns])
        ax.set_yticks(range(len(piv.index)), [f"{c:g}" for c in piv.index])
        ax.set_xlabel("PAP NZ$ (x omega(P))")
        ax.set_ylabel("k_WFH NZ$ (x phi(F))")
        ax.set_title(f"{title} (paid parking fixed at NZ${PARK_FIXED:g}; darker = closer to target centre; * chosen)",
                     color=INK, fontsize=9)
    fig.tight_layout()
    p = FIG_DIR / "calib_search.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    paths["search"] = str(p.relative_to(ROOT))
    return paths


# ----------------------------------------------------------------------------- report


def pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def write_report(res: dict) -> None:
    ch = res["chosen"]["scalars"]
    tst = res["chosen"]["targets"]
    pf = res.get("pre_fuel") or {}
    lines = []
    A = lines.append
    A("# Behaviour calibration report")
    A("")
    A("Generated by `scripts/calibrate_behaviour.py` (data: `data/behaviour_calibration.json`). R-daily arm, "
      "rule decider, PyEngine, n = 300, 30 days, seeds 1-3 (held-out seeds 4-5 and, after the selection, "
      "unseen seeds 6-12 for checking only). "
      "The LLM arms are never calibrated. Capacity is recalibrated per seed and per evaluated point "
      "with `cordonlite.run.calibrate` (car-weighted peak 15-min queue delay of 15 min, days 6-10, no charge).")
    A("")
    A("## Targets (all stated assumptions)")
    A("")
    A("| Target | Band | Centre | Meaning |")
    A("|---|---|---|---|")
    for k, t in TARGETS.items():
        A(f"| `{k}` | {t['lo']:g} to {t['hi']:g} | {t['centre'] if t['centre'] is not None else '-'} | {t['what']} |")
    A("")
    A("Response anchors: Stockholm about -20% (an initial -28%, then -23%, settling at 20-22%), Gothenburg "
      "about -12% (Börjesson et al. 2012, Transport Policy 20:1-12; Börjesson and Kristoffersson 2015, "
      "TR-A 75:134-146). Single-seed tolerance: shares ±0.05, response ±4 pp.")
    A("")
    A("**Comparability of the anchors.** The Stockholm and Gothenburg figures are reductions of total cordon-crossing "
      "traffic in charged hours (all vehicles and purposes), observed over months to years. v3 section 10.5 lists "
      "them as soft checks, notes that private-car elasticities (-0.85 to -1.9) are about twice the total-traffic "
      "ones (-0.4 to -0.9), and asks for the comparison to be reported as qualitative only. The target here is a "
      "hard band on AM car-commuter crossings over days 21-30, and days 11-13 stand in for Stockholm's early "
      "-28% then -23%. A private-car commuter response is likely larger than the total-traffic one, and the "
      "observed trajectory unfolded over months, not days. The band is therefore a stated assumption that puts "
      "the rule arm in a plausible range, not a validation. Auckland-specific support is indicative only: AT option "
      "1a (v3 10.5) implies AM-peak vehicle trips of about -3,600 against about 19,000 charged vehicles (about 19%).")
    A("")
    A("## Structural fixes (applied before the search)")
    A("")
    for s in res["structural_fixes"]:
        A(f"- **{s['param']}**: {s['from']} -> {s['to']}. {s['why']}")
    A("")
    fu = res["fuel"]
    pk = res["parking"]
    prv = res.get("previous") or {}
    cm_ = res["chosen"].get("mean") or next(p for p in res["search"]["points"] if p["label"] == res["chosen"]["label"])["mean"]
    fm = [r.get("fuel_mean_paying") for r in res["chosen"].get("per_seed", []) if r.get("fuel_mean_paying") is not None]
    fuel_txt = (f"mean NZ${np.mean(fm):.1f} a day for a driver who pays it (seeds 1-3: "
                + ", ".join(f"{x:.1f}" for x in fm) + ")") if fm else "see config.toml"
    lst = res.get("last") or {}
    es = res.get("early_start_summary")
    ea, sk = res.get("early_start", {}), res.get("skip", {})
    A("## Early start and SKIP cost (author decisions, 2026-10-05)")
    A("")
    A(f"Two assumptions changed before this search, and neither is searched. **Cost of postponing**: "
      f"`costs.skip_cost` = NZ${sk.get('skip_cost', 30):g} plus {sk.get('skip_vot_hours', 1):g} hour of VoT [A, author "
      "decision 2026-10-05; raised with the driving cost] (NZ$25 before). **Early start**: a commuter whose employer "
      "allows it (Layer A constraint `early_shift_ok`, probability by archetype "
      f"{ea.get('early_shift_prob')} for hybrid office, on-site office, shift/service, trades/work vehicle and "
      f"tertiary student [A]) may start work at {ea.get('early_start_min', 420) // 60:02d}:{ea.get('early_start_min', 420) % 60:02d} "
      "instead of the usual start t* (07:00 to 15:00 [A, author: employers encourage it]). Every car and PT option of "
      "such a commuter is measured against the cheaper of the two starts: schedule delay against t*, or schedule delay "
      f"against the early start plus NZ${ea.get('early_shift_cost', 3):g} x phi(F) a day [A]. The car departures around "
      f"the reference departure of each start (+/- {max(ea.get('anchor_offsets_min', [0, 15]))} min) are added to the "
      "standing +/- 60 min set. Early and late minutes, lateness for T3 and the stored outcome use the start the "
      "chosen option implies. The LLM prompt states the permission and shows the start time of every option. "
      "Targets, seeds (1-3 search, 4-5 held out, 6-12 out of sample), loss, selection rule, grid and the two "
      "searched scalars (PAP, k_WFH) are unchanged. The earlier state is archived in "
      "`data/behaviour_calibration_skip25_noearly.json` with `docs/calibration_report_skip25_noearly.md`.")
    A("")
    if es:
        A("Early start, retiming, postponing and peak spreading at the chosen point (R-daily; 'no charge' is the run "
          "without the charge at the same capacity and seed, which has the same day-to-day churn):")
        A("")
        A("| Seed | may start early | early start d6-10 | d11-13 | d21-30 | d21-30, no charge | SKIP d6-10 | SKIP d21-30 | "
          "retimed (of all commuters) | same, no charge | crossings d21-30 vs d6-10, all morning | 08:00-09:00 | "
          "before 07:30 | 08:00-09:00, no charge |")
        A("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        def es_row(lab, x):
            rt_, rt0 = x.get("retiming"), x.get("nofee_retiming")
            A(f"| {lab} | {x['early_ok_share']:.3f} | {x['base_early']:.3f} | {x['early_11_13']:.3f} | {x['end_early']:.3f} | "
              f"{x['nofee_end_early']:.3f} | {x['base_skip']:.3f} | {x['end_skip']:.3f} | "
              + (f"{rt_['retimed_of_all']:.3f} | {rt0['retimed_of_all']:.3f}" if rt_ else "- | -")
              + f" | {pct(x['change_21_30'])} | {pct(x['peak_cross_change'])} | {pct(x['pre0730_cross_change'])} | "
              f"{pct(x['nofee_peak_cross_change'])} |")
        for x in es["per_seed"]:
            es_row(f"{x['seed']}" + (" (held out)" if x["seed"] in HOLDOUT_SEEDS else ""), x)
        es_row("mean 1-3", es["mean_1_3"])
        A("")
        m_ = es["mean_1_3"]
        A("'Early start' is the share of all commuters whose day is measured against the early start (car or PT), "
          "mean over the days. 'Retimed' counts commuters whose modal option is a car departure on days 6-10 and on "
          "days 26-30 with a different modal departure (an early-start departure counts). "
          f"Mean of seeds 1-3: {m_['early_ok_share']:.1%} of commuters may start early; {m_['base_early']:.1%} do so "
          f"before the charge and {m_['end_early']:.1%} on days 21-30 ({m_['nofee_end_early']:.1%} in the no-charge "
          f"run); as a share of car users {m_['base_early_of_cars']:.1%} and {m_['end_early_of_cars']:.1%}. "
          f"{m_['retiming']['retimed_of_all']:.1%} of commuters retime their drive "
          f"({m_['retiming']['retimed_earlier_of_all']:.1%} earlier, {m_['retiming']['retimed_later_of_all']:.1%} later), "
          f"against {m_['nofee_retiming']['retimed_of_all']:.1%} without the charge. SKIP is {m_['base_skip']:.3f} before "
          f"and {m_["end_skip"]:.3f} after. Car crossings change by {pct(m_["change_21_30"])} over the whole morning and by "
          f"{pct(m_['peak_cross_change'])} in the 08:00 to 09:00 peak (NZ$6), against {pct(m_['pre0730_cross_change'])} "
          f"before 07:30 (NZ$4); without the charge the peak changes by {pct(m_['nofee_peak_cross_change'])} over the "
          "same days.")
        A("")
    A("## Parking and fuel fixed by the authors")
    A("")
    A(f"Two inputs are fixed from real-world knowledge and are not calibrated (2026-10-03). **Paid parking** is "
      f"NZ${pk['park_cost_paid_office']:g} a day for office archetypes (student NZ${pk['student']:g}; trades and "
      "company vehicles 0) [author decision; consistent with the AT 2014 Victoria St daily rate already noted in "
      "config comments]. It was a searched scalar before (NZ$17 without a fuel cost, NZ$11 with fuel at "
      f"NZ$0.23/km). **Fuel** is 2 x path_km x NZ${fu['fuel_cost_per_km']:.2f}/km (round trip, to the cent; 0 for "
      "company cars and work vehicles): petrol NZ$3.30/L [author-supplied, Oct 2026] x 9.0 L/100 km (Metcalfe and "
      f"Sridhar 2016 for the Ministry of Transport) = 0.297, rounded to 0.30; {fuel_txt}. The petrol price was "
      "supplied by the authors and has not been verified against a published series here (the MBIE weekly series "
      "gave NZ$2.53/L for September 2025 and NZ$2.97/L for September 2026). Under `wfh_form = \"v3_relative\"` WFH "
      "carries parking and fuel, so WFH earns no credit for the avoided drive. The prompt of the LLM arms states "
      "both daily costs.")
    A("")
    A("The search runs over two scalars only, PAP and k_WFH, with the same targets, seeds, loss and selection "
      "rule. Earlier searches are archived: `data/behaviour_calibration_pre_fuel.json` with "
      "`docs/calibration_report_pre_fuel.md` (no fuel, three scalars), "
      "`data/behaviour_calibration_fuel023_park11.json` with `docs/calibration_report_fuel023_park11.md` (fuel "
      "NZ$0.23/km, three scalars) and `data/behaviour_calibration_skip25_noearly.json` with "
      "`docs/calibration_report_skip25_noearly.md` (SKIP cost NZ$25, no early start, two scalars).")
    A("")
    if pf and prv and lst:
        c0, m0 = pf["chosen"], pf["chosen_mean"]
        c1, m1 = prv["chosen"], prv["chosen_mean"]
        c2, m2 = lst["chosen"], lst["chosen_mean"]
        A("| | Without fuel (archived) | Fuel NZ$0.23/km, parking searched (archived) | Fuel NZ$0.30/km, parking fixed, "
          "SKIP NZ$25, no early start (archived) | SKIP NZ$30 and early start (this report) |")
        A("|---|---|---|---|---|")
        A(f"| Fuel cost | none | NZ$0.23/km, fixed | NZ$0.30/km, fixed | NZ${fu['fuel_cost_per_km']:.2f}/km, fixed |")
        A(f"| Paid parking, office (student) | NZ${c0['park']:g} (NZ${0.75 * c0['park']:g}), searched | "
          f"NZ${c1['park']:g} (NZ${0.75 * c1['park']:g}), searched | NZ${c2['park']:g} (NZ${0.75 * c2['park']:g}), fixed | "
          f"NZ${ch['park']:g} (NZ${0.75 * ch['park']:g}), fixed |")
        A(f"| SKIP cost (plus 1 h of VoT) | NZ$25 | NZ$25 | NZ$25 | NZ${sk.get('skip_cost', 30):g} |")
        A("| Early-start option | no | no | no | yes |")
        A("| Searched scalars | PAP, parking, k_WFH | PAP, parking, k_WFH | PAP, k_WFH | PAP, k_WFH |")
        e_ = on_grid_edge(ch)
        A(f"| PAP (x omega(P)) | NZ${c0['pap']:g} | NZ${c1['pap']:g} (grid edge) | NZ${c2['pap']:g} (interior) | "
          f"NZ${ch['pap']:g} ({'grid edge' if e_['pap'] else 'interior'}) |")
        A(f"| k_WFH (x phi(F)) | NZ${c0['wfh']:g} (grid edge) | NZ${c1['wfh']:g} (grid edge) | NZ${c2['wfh']:g} (interior) | "
          f"NZ${ch['wfh']:g} ({'grid edge' if e_['wfh'] else 'interior'}) |")
        A(f"| Feasible points | {pf['n_feasible']} of {pf['n_points']} (after rounding) | {prv['n_feasible']} of "
          f"{prv['n_points']} | {lst['n_feasible']} of {lst['n_points']} | "
          f"{sum(p['feasible'] for p in res['search']['points'])} of {len(res['search']['points'])} |")
        for k, lab in (("base_car", "Car share d6-10 (0.75-0.85)"), ("base_pt", "PT share d6-10 (0.08-0.15)"),
                       ("base_wfh", "WFH share d6-10 (at most 0.10)"), ("base_skip", "SKIP share d6-10 (at most 0.02)")):
            A(f"| {lab} | {m0[k]:.3f} | {m1[k]:.3f} | {m2[k]:.3f} | {cm_[k]:.3f} |")
        for k, lab in (("change_11_13", "Crossings d11-13 vs d6-10 (to about -30%)"),
                       ("change_21_30", "Crossings d21-30 vs d6-10 (-12% to -22%)")):
            A(f"| {lab} | {pct(m0[k])} | {pct(m1[k])} | {pct(m2[k])} | {pct(cm_[k])} |")
        A(f"| Capacity scale (mean of seeds 1-3) | {m0['capacity_scale']:.3f} | {m1['capacity_scale']:.3f} | "
          f"{m2['capacity_scale']:.3f} | {cm_['capacity_scale']:.3f} |")
        A("")
        A("With parking at NZ$17 and fuel at NZ$0.30/km a paying driver's money cost is about NZ$"
          f"{ch['park'] + (np.mean(fm) if fm else 8.6):.0f} a day before any charge (parking plus fuel), against about "
          "NZ$18 in the two earliest states, so PAP is far higher than in those states: it is the one scalar that "
          "holds the assumed pre-charge shares. In the third state postponing (NZ$25 plus one hour of VoT) was close "
          f"to the cost of a day's driving and the SKIP share was {m2['base_skip']:.3f} before the charge; with the "
          f"SKIP cost at NZ$30 and the early-start option it is {cm_['base_skip']:.3f}.")
        A("")
    A("## Search")
    A("")
    g = res["search"]
    A(f"{len(g['points'])} grid points x {len(SEEDS)} seeds = {len(g['points']) * len(SEEDS)} evaluations, each "
      f"with its own capacity calibration. Full grid in NZ$1 steps: PAP {GRID['pap'][0]:g} to {GRID['pap'][-1]:g}, "
      f"k_WFH {GRID['wfh'][0]:g} to {GRID['wfh'][-1]:g}, paid parking fixed at NZ${PARK_FIXED:g}. The ranges were set "
      "after a range-finding probe (PAP 12 to 40 in steps of 4 at k_WFH 8 and 12, seeds 1-3; logged as "
      "`search.range_probe`) and before the search. "
      f"Selection: {g['selection']} Loss: {g['loss_doc']} Paid parking is constant, so its terms in the anchor "
      "distance (0) and in the prior (a constant) do not affect the ranking.")
    A("")
    nf = sum(p["feasible"] for p in g["points"])
    ss = res["selection_sensitivity"]
    cpt = next(p for p in g["points"] if p["label"] == res["chosen"]["label"])
    cmean = res["chosen"].get("mean") or cpt["mean"]
    crow = res["chosen"].get("per_seed") or cpt["per_seed"]
    missed = [k for k in TARGETS if band_excess(k, round(cmean[k], 2)) > 0]
    fv = lambda k, v: pct(v) if k.startswith("change") else format(v, ".3f")
    seed_miss = [(r["seed"], k, r[k], band_excess(k, r[k], SEED_TOL[k])) for r in crow for k in TARGETS
                 if band_excess(k, r[k], SEED_TOL[k]) > 0]
    edge = on_grid_edge(res["chosen"]["scalars"])
    txt = (f"{nf} of {len(g['points'])} points are feasible at the stated precision (shares to 2 decimals, changes "
           f"to whole percent); strictly (unrounded 3-seed means) {len(ss['feasible_strict'])} are. ")
    if nf == 0:
        txt += (f"With no feasible point the rule falls back to the lowest loss, which gives {ss['lowest_loss']}. "
                + ("At the stated precision the 3-seed means of the chosen point miss "
                   + ", ".join(f"`{k}` ({fv(k, cmean[k])})" for k in missed) + ". " if missed else
                   "Every 3-seed mean of the chosen point is inside its band. ")
                + ("The point is not feasible because of the single-seed rule: "
                   + "; ".join(f"seed {sd} `{k}` {fv(k, v)} (beyond the band plus tolerance by "
                               + (f"{ex * 100:.1f} pp" if k.startswith("change") else f"{ex:.3f}") + ")"
                               for sd, k, v, ex in seed_miss)
                   + ". " + ("The single-seed tolerance for the SKIP share is 0, so a seed with a SKIP share above "
                             "0.02 fails. " if any(k == "base_skip" for _, k, _, _ in seed_miss) else "")
                   if seed_miss else ""))
    else:
        txt += f"The chosen point is {res['chosen']['label']}; the lowest-loss point is {ss['lowest_loss']}. "
    txt += ("Neither chosen value is on an edge of its searched range." if not any(edge.values()) else
            "On a grid edge: " + ", ".join(k for k, v in edge.items() if v) + ".")
    A(txt)
    A("")
    A("Sensitivity to the soft overshoot bound ('may reach about -30%', treated as a hard bound): "
      + "; ".join(f"bound {pct(x['lo'])}: {len(x['feasible'])} feasible, chosen {x['chosen']}" for x in ss["overshoot_bound"])
      + ". The anchors (PAP 8, k_WFH 8) act only inside a feasible set.")
    A("")
    hist = g.get("selection_history", [])
    if hist:
        A("Selection history (append-only from this version; `search.selection_history`): "
          + " ".join(h.get("note") or f"{h['replaced_at']}: replaced rule choosing {h['chosen']}." for h in hist))
        A("")
    A("Feasible points and the ten lowest-loss points (3-seed means):")
    A("")
    A("| PAP | k_WFH | feasible | anchor dist. | loss | base car | base PT | base WFH | base SKIP | d11-13 | d21-30 |")
    A("|---|---|---|---|---|---|---|---|---|---|---|")
    show = [p for p in g["points"] if p["feasible"]]
    show += [p for p in sorted(g["points"], key=lambda q: q["loss"]["total"])[:10] if not p["feasible"]]
    for p in sorted(show, key=lambda q: (not q["feasible"], q["anchor_distance"], q["loss"]["total"])):
        s, m = p["scalars"], p["mean"]
        A(f"| {s['pap']:g} | {s['wfh']:g} | {'yes' if p['feasible'] else 'no'} | "
          f"{p['anchor_distance']:.3f} | {p['loss']['total']:.2f} | {m['base_car']:.3f} | "
          f"{m['base_pt']:.3f} | {m['base_wfh']:.3f} | {m['base_skip']:.3f} | {pct(m['change_11_13'])} | {pct(m['change_21_30'])} |")
    A("")
    A(f"Chosen: **PAP NZ${ch['pap']:g} x omega(P), k_WFH NZ${ch['wfh']:g} x phi(F)**, with paid parking fixed at "
      f"NZ${ch['park']:g}/day (student NZ${0.75 * ch['park']:g}) and fuel fixed at NZ${fu['fuel_cost_per_km']:.2f}/km.")
    A("")
    A("How to read the chosen values. PAP enters in the specification form omega(P) x (VoT/60 x T_pt + PAP) + fare: "
      "omega also scales PT time, and v3's HTA/2 factor is absent. v3 6.2 uses omega(P) x PAP x HTA/2 (HTA 1 local, "
      f"2 boundary) with PAP 8 swept {{4, 8, 12}}, so Cordon-Lite's {ch['pap']:g} x omega equals v3 PAP {ch['pap']:g} "
      f"(boundary homes) to {2 * ch['pap']:g} (local homes), far above v3's range; P = 1-2 agents also face doubled "
      "or 1.5 x PT time and practically never ride PT. PAP is the one scalar left to hold the assumed baseline "
      "split, so it absorbs the whole rise in the money cost of driving: it is a fitted residual, not an estimate "
      f"of a PT attitude. k_WFH {ch['wfh']:g} is above v3's NZ$8; it is identified here by the response and overshoot "
      "targets (a higher value weakens both), not by the WFH share, which stays near zero. Parking and fuel are no "
      "longer fitted, so the earlier caveat that parking was in effect a fitted value no longer applies.")
    A("")
    A(f"![search]({Path(res['figures']['search']).relative_to('docs')})")
    A("")
    A("## Before vs after (3-seed means)")
    A("")
    b, s_, a = res["before"]["mean"], res["structural_only"]["mean"], res["chosen"]["mean"]
    A("| Metric | Target | Before | Structural fixes only (v3 values) | After (chosen) |")
    A("|---|---|---|---|---|")
    for k, lab in (("base_car", "car share d6-10"), ("base_pt", "PT share d6-10"), ("base_wfh", "WFH share d6-10"),
                   ("base_skip", "SKIP share d6-10"), ("change_11_13", "crossings d11-13 vs d6-10"),
                   ("change_21_30", "crossings d21-30 vs d6-10")):
        t = TARGETS[k]
        f = pct if k.startswith("change") else (lambda v: f"{v:.3f}")
        band = f"{pct(t['lo'])} to {pct(t['hi'])}" if k.startswith("change") else f"{t['lo']:g}-{t['hi']:g}"
        A(f"| {lab} | {band} | {f(b[k])} | {f(s_[k])} | {f(a[k])} |")
    for k, lab in (("end_car", "car share d21-30"), ("end_pt", "PT share d21-30"), ("end_wfh", "WFH share d21-30"),
                   ("peak_band_share_21_30", "08:00-09:00 crossing share d21-30"),
                   ("peak_delay_6_10", "peak delay d6-10 (min)"), ("peak_delay_21_30", "peak delay d21-30 (min)"),
                   ("capacity_scale", "capacity scale")):
        A(f"| {lab} | - | {b[k]:.3f} | {s_[k]:.3f} | {a[k]:.3f} |")
    A("")
    A("'Before' is the pre-recalibration specification, which has no fuel cost and paid parking NZ$8. 'Structural "
      f"fixes only' is the current model, with the fixed parking (NZ${PARK_FIXED:g}) and fuel "
      f"(NZ${fu['fuel_cost_per_km']:.2f}/km), at the v3 scalars (PAP 8, k_WFH 8). It has base car {s_['base_car']:.3f} "
      f"and PT {s_['base_pt']:.3f}, far outside the baseline bands, and responds by {pct(s_['change_21_30'])} on days "
      f"21-30 and {pct(s_['change_11_13'])} on days 11-13 (per seed "
      + ", ".join(pct(r["change_21_30"]) for r in res["structural_only"]["per_seed"]) + "). "
      + (f"Without fuel and with v3's NZ$8 parking the v3-valued model gave car {pf['structural_mean']['base_car']:.3f}, "
         f"PT {pf['structural_mean']['base_pt']:.3f} and a response of {pct(pf['structural_mean']['change_21_30'])} "
         f"(overshoot {pct(pf['structural_mean']['change_11_13'])}), the like-for-like v3 sensitivity. " if pf else "")
      + f"In the search PAP moved to restore the assumed baseline shares (to {ch['pap']:g}) and k_WFH to "
      f"{ch['wfh']:g}, and the response is {pct(a['change_21_30'])}. The closeness to Stockholm's -20% is partly a "
      "by-product of fitting the baseline.")
    A("")
    A("## Per-seed metrics against each target (chosen values)")
    A("")
    rows = res["chosen"]["per_seed"] + res["chosen"]["holdout"]
    A("| Seed | capacity scale | base car | base PT | base WFH | base SKIP | d11-13 | d21-30 | within band / tolerance |")
    A("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        flags = []
        for k in TARGETS:
            if band_excess(k, r[k]) == 0:
                continue
            flags.append(f"{k} {'within tol.' if band_excess(k, r[k], SEED_TOL[k]) == 0 else 'OUT'}")
        tag = " (held out)" if r["seed"] in HOLDOUT_SEEDS else ""
        A(f"| {r['seed']}{tag} | {r['capacity_scale']:.4f} | {r['base_car']:.3f} | {r['base_pt']:.3f} | "
          f"{r['base_wfh']:.3f} | {r['base_skip']:.3f} | {pct(r['change_11_13'])} | {pct(r['change_21_30'])} | "
          f"{'all in band' if not flags else '; '.join(flags)} |")
    A("")
    A("Target status on the calibration seeds 1-3:")
    A("")
    for k, t in tst.items():
        rounded_ok = band_excess(k, round(t["mean"], 2)) == 0.0
        state = ("in band" if t["mean_in_band"] else
                 "in band at the stated precision, above the bound unrounded" if rounded_ok else "OUT of band")
        A(f"- `{k}`: mean {t['mean']:.3f} ({state}); seeds in band "
          f"{sum(t['seeds_in_band'])}/3, within tolerance {sum(t['seeds_within_tolerance'])}/3.")
    A("")
    oos = res.get("out_of_sample")
    if oos:
        A("## Out-of-sample seeds and the ridge alternatives")
        A("")
        A(oos["note"] + " Seeds 4-5 come from the final stage; seeds 6-12 were never run before the selection.")
        A("")
        A("| Seed | capacity scale | base car | base PT | base WFH | base SKIP | d11-13 | d21-30 | outside band / tolerance |")
        A("|---|---|---|---|---|---|---|---|---|")
        for r in oos["chosen"]["per_seed"]:
            flags = []
            for k in TARGETS:
                if band_excess(k, r[k]) == 0:
                    continue
                flags.append(f"{k} {'within tol.' if band_excess(k, r[k], SEED_TOL[k]) == 0 else 'OUT of tol.'}")
            A(f"| {r['seed']} | {r['capacity_scale']:.4f} | {r['base_car']:.3f} | {r['base_pt']:.3f} | "
              f"{r['base_wfh']:.3f} | {r['base_skip']:.3f} | {pct(r['change_11_13'])} | {pct(r['change_21_30'])} | "
              f"{'all in band' if not flags else '; '.join(flags)} |")
        A("")
        A("| Point | seeds | base car | base PT | base SKIP | d11-13 | d21-30 |")
        A("|---|---|---|---|---|---|---|")
        cm = res["chosen"]["mean"]
        A(f"| chosen PAP {ch['pap']:g} / k_WFH {ch['wfh']:g} | 1-3 (calibration) | {cm['base_car']:.3f} | "
          f"{cm['base_pt']:.3f} | {cm['base_skip']:.3f} | {pct(cm['change_11_13'])} | {pct(cm['change_21_30'])} |")
        for lab, key in (("4-12", "mean_4_12"), ("6-12 (unseen)", "mean_6_12"), ("1-12", "mean_1_12")):
            m = oos["chosen"][key]
            A(f"| chosen PAP {ch['pap']:g} / k_WFH {ch['wfh']:g} | {lab} | {m['base_car']:.3f} | {m['base_pt']:.3f} | "
              f"{m['base_skip']:.3f} | {pct(m['change_11_13'])} | {pct(m['change_21_30'])} |")
        for alt in oos["alternatives"]:
            sc = alt["scalars"]
            for lab, m in (("1-3 (calibration)", alt["mean_1_3"]), ("4-12", alt["mean_4_12"])):
                A(f"| PAP {sc['pap']:g} / k_WFH {sc['wfh']:g} | {lab} | {m['base_car']:.3f} | {m['base_pt']:.3f} | "
                  f"{m['base_skip']:.3f} | {pct(m['change_11_13'])} | {pct(m['change_21_30'])} |")
        A("")
        m6, m12 = oos["chosen"]["mean_6_12"], oos["chosen"]["mean_1_12"]
        m4 = oos["chosen"]["mean_4_12"]
        out_tol = [f"seed {r['seed']} `{k}` "
                   + (pct(r[k]) if k.startswith("change") else f"{r[k]:.3f}")
                   for r in oos["chosen"]["per_seed"] for k in TARGETS if band_excess(k, r[k], SEED_TOL[k]) > 0]
        inb = lambda k, v: "in band" if band_excess(k, round(v, 2)) == 0 else "OUT of band"
        A(f"Out of sample the response is {pct(m6['change_21_30'])} on unseen seeds 6-12 "
          f"({inb('change_21_30', m6['change_21_30'])}; {pct(m12['change_21_30'])} over seeds 1-12), with an overshoot "
          f"of {pct(m6['change_11_13'])} ({inb('change_11_13', m6['change_11_13'])}; {pct(m12['change_11_13'])} over "
          f"seeds 1-12). Over seeds 1-12 base car is {m12['base_car']:.3f} ({inb('base_car', m12['base_car'])}), base "
          f"PT {m12['base_pt']:.3f} ({inb('base_pt', m12['base_pt'])}) and base SKIP {m12['base_skip']:.3f} "
          f"({inb('base_skip', m12['base_skip'])}), all at the stated precision. On the unseen seeds 6-12 alone base "
          f"car is {m6['base_car']:.3f} ({inb('base_car', m6['base_car'])}), base PT {m6['base_pt']:.3f} "
          f"({inb('base_pt', m6['base_pt'])}) and base SKIP {m6['base_skip']:.3f} ({inb('base_skip', m6['base_skip'])}). "
          "Single seeds outside the stated tolerance: "
          + ("; ".join(out_tol) if out_tol else "none outside tolerance") + ". "
          + "The ridge alternatives ("
          + ", ".join(f"PAP {x['scalars']['pap']:g} / k_WFH {x['scalars']['wfh']:g}" for x in oos["alternatives"])
          + ") give on seeds 4-12 ("
          + ", ".join(f"{pct(x['mean_4_12']['change_21_30'])}, overshoot {pct(x['mean_4_12']['change_11_13'])}"
                      for x in oos["alternatives"])
          + f") against the chosen point ({pct(m4['change_21_30'])}, {pct(m4['change_11_13'])}). "
          "The choice was not changed after seeing these seeds.")
        A("")
    gs = res.get("gap_sensitivity")
    if gs:
        A("## Sensitivity to the fixed assumptions (not adopted)")
        A("")
        A(gs["note"])
        A("")
        A("| Variant (at the chosen PAP and k_WFH) | feasible | base car | base PT | base WFH | base SKIP (per seed) | "
          "SKIP d21-30 | early start d6-10 | early start d21-30 | d11-13 | d21-30 | 08:00-09:00 crossings |")
        A("|---|---|---|---|---|---|---|---|---|---|---|---|")
        cm0 = res["chosen"]["mean"]
        A(f"| chosen point, no change | {'yes' if res['chosen'].get('feasible') else 'no'} | {cm0['base_car']:.3f} | "
          f"{cm0['base_pt']:.3f} | {cm0['base_wfh']:.3f} | {cm0['base_skip']:.3f} "
          f"({', '.join(format(r['base_skip'], '.3f') for r in res['chosen']['per_seed'])}) | {cm0['end_skip']:.3f} | "
          f"{cm0['base_early']:.3f} | {cm0['end_early']:.3f} | {pct(cm0['change_11_13'])} | {pct(cm0['change_21_30'])} | "
          f"{pct(cm0['peak_cross_change'])} |")
        for v in gs["variants"]:
            m = v["mean"]
            A(f"| {v['what']} | {'yes' if v['feasible'] else 'no'} | {m['base_car']:.3f} | {m['base_pt']:.3f} | "
              f"{m['base_wfh']:.3f} | {m['base_skip']:.3f} ({', '.join(format(r['base_skip'], '.3f') for r in v['per_seed'])}) | "
              f"{m['end_skip']:.3f} | {m['base_early']:.3f} | {m['end_early']:.3f} | "
              f"{pct(m['change_11_13'])} | {pct(m['change_21_30'])} | {pct(m['peak_cross_change'])} |")
        A("")
        if gs.get("research"):
            A("Local re-search under each changed assumption (PAP 17 to 24, k_WFH 7 to 11, seeds 1-3, same rule; optional stage `gap`; "
              "logged as `gap_sensitivity.research`, never adopted):")
            A("")
            A("| Changed assumption | feasible points | the rule would choose | base car | base PT | base SKIP (per seed) | d11-13 | d21-30 |")
            A("|---|---|---|---|---|---|---|---|")
            for v in gs["research"]:
                w = v["would_choose"]
                m = w["mean"]
                A(f"| {v['what']} | {v['n_feasible']} of {v['n_points']} | PAP {w['scalars']['pap']:g} / k_WFH "
                  f"{w['scalars']['wfh']:g} ({'feasible' if w['feasible'] else 'not feasible, lowest loss'}) | "
                  f"{m['base_car']:.3f} | {m['base_pt']:.3f} | {m['base_skip']:.3f} "
                  f"({', '.join(format(r['base_skip'], '.3f') for r in w['per_seed'])}) | {pct(m['change_11_13'])} | "
                  f"{pct(m['change_21_30'])} |")
            A("")
        A(gs["reading"])
        A("")
    A(f"![mode shares]({Path(res['figures']['mode_shares']).relative_to('docs')})")
    A("")
    A(f"![crossing change]({Path(res['figures']['crossing_change']).relative_to('docs')})")
    A("")
    A("## Retiming")
    A("")
    rt = res["retiming"]
    A("Measured against a no-charge run at the same capacity and seed (days 21-30), because the no-charge "
      "run has the same day-to-day churn and congestion feedback.")
    A("")
    A("| Seed | 08:00-09:00 share, charge | same, no charge | 07:00-08:00 share, charge | same, no charge |")
    A("|---|---|---|---|---|")
    for r in rt["per_seed"]:
        A(f"| {r['seed']} | {r['peak']:.3f} | {r['peak_nofee']:.3f} | {r['shoulder']:.3f} | {r['shoulder_nofee']:.3f} |")
    A("")
    A(rt["verdict"])
    A("")
    A("Crossings per day before 07:30 (NZ$4 or less): " + ", ".join(
        f"seed {x['seed']}: {x['early_crossings']:.1f} with the charge vs {x['early_crossings_nofee']:.1f} without"
        for x in rt["per_seed"]) + ".")
    A("")
    def band_sum(h, lo, hi):
        return sum(v for k, v in h.items() if lo <= int(k) < hi)

    after_rows = res["chosen"]["per_seed"]
    for lab, lo_, hi_ in (("06:00-07:30 (NZ$4 or less)", 360, 450), ("08:00-09:00 (NZ$6)", 480, 540),
                          ("09:30-10:15 (back to NZ$4)", 570, 615)):
        c1 = np.mean([band_sum(r["exit_hist_21_30"], lo_, hi_) for r in after_rows])
        c0 = np.mean([band_sum(r["nofee"]["exit_hist_21_30"], lo_, hi_) for r in after_rows])
        A(f"- Crossings per day {lab}, days 21-30, mean of seeds 1-3: {c1:.1f} with the charge, {c0:.1f} without "
          f"({c1 / c0 - 1:+.0%}).")
    A("")
    pr = res["retiming_paired"]
    al = pr["all"]
    A("Paired check (common random numbers: the charged and no-charge runs share every rule noise draw): among "
      f"agents who drive at days 26-30 in both runs (n = {al['n']}, seeds 1-3), {al['retimed']:.1%} "
      f"[{al['ci_lo']:.1%}, {al['ci_hi']:.1%}] have a different modal departure with the charge "
      f"({al['earlier']:.1%} earlier, {al['later']:.1%} later; mean shift {al['mean_shift_min']:+.1f} min). By F level: "
      + "; ".join(f"F{r['level']} {r['retimed']:.2f} [{r['ci_lo']:.2f}, {r['ci_hi']:.2f}] n={r['n']}" for r in pr["by_F"])
      + ".")
    A("")
    A(f"![crossing times]({Path(res['figures']['crossing_times']).relative_to('docs')})")
    A("")
    A("## Trait monotonicity")
    A("")
    A("### Who adapts on the calibrated runs")
    A("")
    A("Day-10 drivers (modal option days 6-10 a car option, twins and company cars excluded), pooled over seeds "
      "1-3, share with 95% Wilson interval; in brackets the same share in the no-charge counterfactual (churn "
      "and selection baseline).")
    A("")
    wa = pd.DataFrame(res["who_adapts"])
    labels = {"keep_d11": "drives on day 11", "keep_end": "car user d26-30",
              "to_pt_end": "PT user d26-30 (PT-feasible day-10 drivers)", "retime_end": "retimed d26-30 (car keepers)",
              "pt_end_all": "PT user d26-30 (all PT-feasible agents)"}
    for trait, metrics_ in (("H", ("keep_d11", "keep_end")), ("P", ("to_pt_end", "pt_end_all")), ("F", ("retime_end",)),
                            ("S", ("keep_d11", "keep_end"))):
        for mt in metrics_:
            sub = wa[(wa["trait"] == trait) & (wa["metric"] == mt)].sort_values("level")
            cells = []
            for _, r in sub.iterrows():
                if r["n"] == 0:
                    cells.append("n=0")
                    continue
                cells.append(f"{r['share']:.2f} [{r['ci_lo']:.2f}, {r['ci_hi']:.2f}] n={int(r['n'])} "
                             f"({r['share_nofee']:.2f})")
            A(f"- **{trait} -> {labels[mt]}** ({spearman_sign(list(range(1, 6)), sub['share'].tolist())}): "
              + " | ".join(f"L{i + 1} {c}" for i, c in enumerate(cells)))
    A("")
    A("### Population trait manipulation (unbiased check)")
    A("")
    A("Every agent set to one level (1-5) of one trait (others drawn as usual), capacity fixed at the chosen "
      "point's per-seed scale, mean of seeds 1-3. Retiming and peak-band shares are differences from the "
      "no-charge run at the same setting.")
    A("")
    A("| Trait | Level | d11-13 | d21-30 | PT share d6-10 | PT share d21-30 minus no-charge | day-10 drivers to PT | "
      "08-09 share minus no-charge | retimed keepers minus no-charge |")
    A("|---|---|---|---|---|---|---|---|---|")
    for r in res["manipulation"]:
        A(f"| {r['trait']} | {r['level']} | {pct(r['change_11_13'])} | {pct(r['change_21_30'])} | {r['base_pt']:.3f} | "
          f"{r['end_pt_minus_nofee']:+.3f} | {r['to_pt']:.3f} | "
          f"{r['peak_minus_nofee']:+.3f} | {r['retime_minus_nofee']:+.3f} |")
    A("")
    for line in res["monotonicity_verdict"]:
        A(f"- {line}")
    A("")
    if oos and oos.get("F_decomposition"):
        A("### Where the F gradient comes from")
        A("")
        A("Same population manipulation (every agent at one F level, capacity fixed, seeds 1-3), split by margin. "
          "Differences are charge minus no-charge run at the same setting, days 21-30.")
        A("")
        A("| F | d21-30 | car share | PT share | WFH share | WFH share with charge (seeds 1-3) | retimed keepers, charge | same, no charge |")
        A("|---|---|---|---|---|---|---|---|")
        for f in oos["F_decomposition"]:
            A(f"| {f['level']} | {pct(f['change_21_30'])} | {f['end_car_minus_nofee']:+.3f} | {f['end_pt_minus_nofee']:+.3f} | "
              f"{f['end_wfh_minus_nofee']:+.3f} | {', '.join(f'{x:.3f}' for x in f['end_wfh_per_seed'])} | "
              f"{f['retimed_keepers']:.3f} | {f['retimed_keepers_nofee']:.3f} |")
        A("")
        A("The F response gradient comes mainly from F = 4-5 hybrid workers switching to daily WFH, which is "
          "unbounded without v3's WFH quota; PT gains barely vary with F. Retiming of car keepers against the "
          "no-charge run is flat across F (the paired departure change rises with F, "
          f"{res['retiming_paired']['by_F'][0]['retimed']:.2f} to {res['retiming_paired']['by_F'][-1]['retimed']:.2f}, "
          "but retiming in the no-charge run rises with F too). The F response gradient is therefore not evidence for the 'high F retimes more' target.")
        A("")
    A("## Limits")
    A("")
    for line in res["limits"]:
        A(f"- {line}")
    A("")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------- main


LIMITS = [
    "The targets are stated assumptions, and the response anchors are not like-for-like: Stockholm and Gothenburg "
    "measured total cordon traffic in charged hours over months to years, while the band here applies to AM car "
    "commuters over days 21-30. v3 10.5 asks for a qualitative comparison only; the private-car commuter response "
    "is likely larger than the total-traffic one.",
    "Six of 405 grid points are feasible, and the rule picks PAP 20 / k_WFH 10, the feasible point nearest the "
    "anchors, the same values as before the SKIP cost and the early start changed. Feasibility is judged at the "
    "precision the targets are stated in. Unrounded, the 3-seed mean PT share is 0.154 (0.0036 above the 0.15 "
    "bound; 0.15 at two decimals), and no grid point is feasible on unrounded means. Three single-seed values lie "
    "outside their band but inside the stated tolerance: base car 0.866 on seed 1 (0.016 above 0.85) and base PT "
    "0.155 and 0.175 on seeds 2 and 3 (0.005 and 0.025 above 0.15). Every other value is in band (days 21-30: "
    "-15.2%, -17.8%, -15.0%; days 11-13: -23.8%, -28.0%, -23.8%; SKIP 0.001, 0.001, 0.006). The targets were not "
    "relaxed.",
    "The response sits in the weaker half of the band: -16.0% on seeds 1-3 against a centre of -20%, and -15.0% on "
    "unseen seeds 6-12 (single seeds -12.0% to -18.3%; seed 6 is at the edge of the band). The lowest-loss point "
    "(PAP 21 / k_WFH 8: -19.2%, overshoot -27.8%) is also feasible, but the rule ranks distance to the anchors "
    "before the loss. Out of sample nothing is outside the stated tolerance. Base PT is above 0.15 on held-out "
    "seed 5 and unseen seeds 7, 8 and 11 (0.165 to 0.195) and base car above 0.85 on seeds 6 and 10 (0.883, 0.853), "
    "all within tolerance; over seeds 1-12 base PT is 0.155 (0.15 at the stated precision).",
    "Postponing is rare again. With the SKIP cost at NZ$30 plus one hour of VoT the SKIP share is 0.003 before the "
    "charge and 0.010 on days 21-30 (seeds 1-3: 0.002, 0.007, 0.020; unseen seeds 6-12: 0.014). The sensitivity "
    "runs show that this comes from the SKIP cost and not from the early start: without the early-start option "
    "the SKIP share is the same (0.004 and 0.010), and with the SKIP cost back at NZ$25 it is 0.022 before the "
    "charge and 0.047 after, even with the early start available.",
    "The early start is used mainly to avoid the queue, not the charge. About 47% of commuters may start early. "
    "6.1% of all commuters do so on days 6-10 (7.3% of car users), when the peak queue delay is about 15 minutes. "
    "Under the charge the share is 6.4% on days 11-13 and falls to 4.2% on days 21-30 (6.1% in the no-charge run), "
    "because the queues almost disappear (peak delay about 3 minutes) and the remaining saving of about NZ$2 in "
    "charge (NZ$4 before 07:30 against NZ$6 from 08:00 to 09:00, plus the loss term) is smaller than the assumed "
    "inconvenience of NZ$3 x phi(F). Only seed 3 shows a small rise (0.049 to 0.054). The result depends on that "
    "assumed cost: at NZ$1.5 x phi(F) the share rises under the charge (0.100 to 0.115) and the 08:00 to 09:00 "
    "crossings fall by 33%; at NZ$6 x phi(F) almost nobody starts early (0.016, then 0.006). The cost and the "
    "permission probabilities are assumptions with no empirical source.",
    "Peak spreading is present but uneven across seeds. Car crossings in the 08:00 to 09:00 peak (NZ$6) fall by "
    "18.6% from days 6-10 to days 21-30 against 16.0% over the whole morning (seeds 1-3: 13.7%, 16.8%, 25.4% "
    "against 15.2%, 17.8%, 15.0%), and by 24.8% against 15.0% on unseen seeds 6-12 (23.9% against 15.6% over "
    "seeds 1-12). Crossings before 07:30 fall by 11.2% on seeds 1-3 and by 2.2% over seeds 1-12, and those after "
    "09:30 rise by about a quarter. Against the no-charge run the 08:00 to 09:00 share of crossings falls only in "
    "seed 3 (-0.069; +0.007 and +0.013 in seeds 1 and 2). In the paired check 43.8% of commuters who drive in both "
    "runs have a different modal departure with the charge, 15.1% earlier and 28.7% later (mean shift +4 minutes): "
    "most of the change is later departures enabled by the congestion relief, not earlier ones.",
    "Day-to-day churn in the daily rule arm is large: 32% of commuters have a different modal car departure on "
    "days 26-30 than on days 6-10 with the charge, and 37% without it. A before-and-after count of retimers "
    "therefore says little, and retiming is reported against the no-charge run.",
    "PAP is a fitted residual. With parking and fuel fixed, PAP is the only scalar that can hold the assumed "
    "pre-charge split, and it stays at 20 (v3 PAP 20-40 in v3's form, against v3's NZ$8 swept 4-12). At PAP 20 "
    "commuters with P = 1-2 never ride PT (PT share 0.000 in the population manipulation), so PT use is confined "
    "to P = 3-5. The baseline shares react sharply to PAP (base PT 0.170 at PAP 19, 0.154 at 20, 0.146 at 21, "
    "k_WFH 10), while the response depends on it less (-16.8% to -14.0% for PAP 19-22).",
    "k_WFH is identified by the response and overshoot, not by the WFH share: at PAP 20 the days 21-30 response is "
    "-19.7% at k_WFH 8, -16.0% at 10 and -12.7% at 12, and the overshoot -30.4%, -25.2% and -22.0%, while base WFH "
    "stays at 0.00. A realistic hybrid-work baseline is not reproduced: k_WFH 4 gives about 4% WFH before the "
    "charge but a response of -32.4%. v3's WFH quota (1-3 days per 5-day block) would bound this margin; it is not "
    "implemented.",
    "The fixed inputs carry their own uncertainty. The petrol price (NZ$3.30/L) is author-supplied for October 2026 "
    "and was not verified here; the last published figure we read was NZ$2.97/L for September 2026. Consumption is "
    "9.0 L/100 km for every paying driver; electric vehicles, fuel cards and other running costs are not "
    "represented. Paid parking NZ$17 is a 2014 casual all-day rate, applied to half of office commuters (the other "
    "half park free). The SKIP cost (NZ$30), the early start time (07:00), its cost (NZ$3 x phi(F)) and the "
    "permission probabilities (0.8, 0.5, 0, 0.5, 0) are author assumptions. Base years are mixed (2026 fuel, 2025 "
    "fare and charge, 2014 parking).",
    "The v3-valued model (PAP 8, k_WFH 8) with the fixed parking and fuel has base car 0.575 and PT 0.421, far "
    "outside the baseline bands, and responds by -25.5% (overshoot -38.4%). Without fuel and with v3's NZ$8 parking "
    "it gave -15.4% (overshoot -25.0%). The scalars were moved to meet the assumed baseline.",
    "The choice does not depend on the soft overshoot bound (the same point is chosen for bounds of -30% to -33%). "
    "It does depend on the anchors: the neighbours PAP 20 / k_WFH 8 and 9, which miss feasibility on the rounded PT "
    "share (0.157) and, for k_WFH 8, on the seed-2 overshoot (-34.0%), give -19.9% and -17.0% on seeds 4-12, "
    "against -15.4% for the chosen point.",
    "Capacity is a further calibrated quantity, recalibrated per point and seed; its discrete jumps add noise of a "
    "few points to the base shares (seeds 2 to 4 share the scale 0.3961).",
    "Single-agent example (tests/test_rules.py): for the shared Layer A with paid parking NZ$17 and the fuel cost "
    "of a 20 km path, 250 of the 625 trait combinations ride PT before the charge. Of the other 375, without the "
    "early-start permission 276 keep the car at the usual time on the charge morning, 93 switch to PT, 4 retime "
    "by 15 minutes (H = 1) and 2 postpone. With the permission 260 keep, 93 switch to PT, 20 leave at 06:30 for "
    "the 07:00 start and 2 postpone. The v3 worked example (identical A: pay / PT / retime) still separates only "
    "with the v3 settings or with free parking.",
    "H damps the charge wake only at level 5 (days 11-13: -26.4%, -27.4%, -28.8%, -25.6% at H = 1-4, -19.3% at "
    "H = 5), and not in the long run (-14.7% to -16.5%): habit re-forms on the new mode immediately.",
    "The charge-induced switch to PT is largest at P = 3 (+0.139 against the no-charge run; +0.101 and +0.099 at "
    "P = 4-5, 0 at P = 1-2): at P = 4-5 most agents for whom PT is viable already ride PT before the charge "
    "(ceiling). The PT share after the charge rises with P (0.00, 0.00, 0.25, 0.46, 0.55).",
    "The F response gradient (-11.2% at F = 1 to -33.7% at F = 5) still comes mainly from daily WFH of F = 4-5 "
    "hybrid workers (no quota; WFH share about 0.20 at F = 5). With the early start the 08:00 to 09:00 share of "
    "crossings now falls with F against the no-charge run (+0.050 at F = 1 to -0.148 at F = 5), partly because "
    "phi(F) scales the cost of the early day, but retiming of car keepers against the no-charge run stays small "
    "(-0.05 to +0.05).",
    "Who-adapts tables conditional on being a day-10 driver are biased by selection; the population manipulation "
    "is the unbiased check.",
    "The reference fee follows the fee faced, but on car days it uses the fee actually paid (after retiming; v3 uses "
    "the fee at h0 before retiming) and alpha 0.3 (SPEC; v3 0.2), so a retimer keeps a loss term on returning to "
    "the peak.",
    "The start an option is measured against is chosen from the expected arrival on the morning of the decision "
    "and is kept for the outcome: a commuter who planned the 07:00 start and is held up counts as late for 07:00 "
    "(and can be woken by T3), not as early for the usual start. For an agent on a standing plan the start is "
    "re-read from that morning's expected arrival.",
    "Clock arms keep more of the day-11 response than R-daily (R-clock -19.5%, -22.5%, -20.8% against -15.2%, "
    "-17.8%, -15.0%, seeds 1-3). With few postponed trips the event-only clock makes only 12 to 123 decisions "
    "after day 12 outside the disruption days. The LLM deciders are not calibrated, but the shared Layer A inputs "
    "(parking, fuel and the early-start permission) reach the LLM prompt. The rule's WFH earns no parking, fuel or "
    "commute credit while the prompt states both daily costs, so live-LLM WFH shares are not comparable with the "
    "rule arm on this margin, and a live LLM is not told the rule's NZ$3 x phi(F) cost of the early day (it reads "
    "the flexibility sentence instead). MockLLM re-weights the same GC parts and responds more strongly.",
]


GAP_READING = (
    "The two decisions of 2026-10-05 do different jobs. The SKIP cost removes the postponed trips: with NZ$25 the "
    "SKIP share is back at 0.022 before the charge (0.025 on seeds 2 and 3, above the bound) and 0.047 after it, "
    "although the early start is available. The early start does not replace postponing in the rule; without it "
    "the SKIP share is unchanged, base PT is 0.161 (above the band at the stated precision) and the 08:00 to 09:00 "
    "crossings fall by 14.4%, slightly less than the whole morning (14.5%), against 18.6% with it. How much the "
    "early start is used depends on its assumed cost: at NZ$1.5 x phi(F) one commuter in ten starts early before "
    "the charge and more do so after it (0.100 to 0.115), and the peak crossings fall by a third; at NZ$6 x phi(F) "
    "the option is almost unused. Giving the permission to every employee of the three eligible groups raises the "
    "share to 0.084 before and 0.065 after the charge and stays feasible. None of the variants was searched or "
    "adopted; 'feasible' is judged at the chosen PAP and k_WFH only.")


STRUCTURAL_FIXES_DOC = [
    {"param": "memory.ref_fee_update", "from": "all_days (EMA of the fee PAID, 0 on non-car days)",
     "to": "faced (EMA, alpha = memory.ema_alpha, of the fee FACED at the car reference departure on every day)",
     "why": "[v3 5.2 fee-ref, with two differences [A]: on car days the fee actually paid (after retiming) rather "
            "than the fee at h0, and alpha 0.3 (SPEC) rather than 0.2]. With the paid fee, agents who left the car "
            "kept a reference of 0 and a loss term on the full fee for ever, so the day-11 response could not fade."},
    {"param": "traits.eta", "from": "[0, 0.5, 1, 2, 3]", "to": "[0, 0.25, 0.5, 0.75, 1]",
     "why": "[v3 4.4 capped variant; De Borger and Fosgerau 2008: a total weight of 4 is generous]. The loss "
            "term was larger than the fee itself for day-11 leavers."},
    {"param": "costs.wfh_form", "from": "spec (WFH = k_WFH x phi; saves car time and parking)",
     "to": "v3_relative (WFH = k_WFH x phi + VoT/60 x free-flow time + parking + fuel)",
     "why": "[v3 6.2: WFH has no PARK term; zero-fee property]. WFH no longer earns the commute, parking and "
            "fuel as savings; it still avoids congestion delay, schedule delay and the charge."},
    {"param": "costs.fuel_cost_per_km", "from": "0 (no fuel cost; v3 folded fuel into its parking value)",
     "to": "0.30 NZ$/km, fixed input (petrol NZ$3.30/L [author-supplied, Oct 2026] x 9.0 L/100 km); car fuel = "
           "2 x path_km x 0.30, 0 for company cars",
     "why": "Driving cost only time, schedule delay, charge and parking, so a calibrated parking value also "
            "stood for fuel. Fuel is explicit and is not a calibration scalar."},
    {"param": "persona.park_cost_paid", "from": "[8, 8, 8, 0, 6] [v3], then searched (17 without fuel, 11 with fuel 0.23)",
     "to": "[17, 17, 17, 0, 12.75], fixed input [author decision; consistent with the AT 2014 Victoria St daily rate]",
     "why": "Paid parking is set from real-world knowledge and is no longer a calibration scalar."},
    {"param": "clock.discontinuity_triggers", "from": "[T1, T2, T4, T6]", "to": "[T1, T4, T6]",
     "why": "[A, Verplanken et al. 2008]: habit discontinuity is a change of the performance context; a price "
            "change leaves route, time and cues intact, so kappa_H is no longer halved at the charge wake."},
    {"param": "costs.pt_attitude_penalty", "from": "0", "to": "PAP x omega(P), searched in 10-36",
     "why": "[v3 6.2 PAP NZ$8, swept {4, 8, 12}, in v3's form omega(P) x PAP x HTA/2]; free scalar 1 of 2 (the other is k_WFH, searched in 2-16), entered in the "
            "specification form omega(P) x (VoT/60 x T_pt + PAP), so the value is not comparable with v3's."},
    {"param": "engine capacity", "from": "seed-1 scale used for every seed",
     "to": "recalibrated per seed and per evaluated point; data/calibration.json holds by_seed records",
     "why": "Pre-charge congestion feeds back on the response."},
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--stage", choices=("all", "search", "select", "final", "oos", "gap", "report"), default="all",
                    help="search: before/structural/grid only (writes the JSON log); final: re-use the logged "
                         "search, run the chosen point's checks; report: rebuild report and figures from the JSON")
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    res: dict[str, Any] = json.loads(OUT_JSON.read_text()) if (args.stage in ("select", "final", "oos", "gap", "report")
                                                               and OUT_JSON.exists()) else {}

    if args.stage in ("all", "search"):
        # append-only selection history: carry the archived history forward and record the selection
        # that this search replaces
        prev = json.loads(LAST_JSON.read_text()) if LAST_JSON.exists() else {}
        history = list(prev.get("search", {}).get("selection_history", []))
        if prev:
            history.append({
                "replaced_at": time.strftime("%Y-%m-%d %H:%M:%S"), "selection": prev["search"].get("selection"),
                "anchors": prev["search"].get("anchors"), "chosen": prev.get("chosen", {}).get("label"),
                "note": (f"{time.strftime('%Y-%m-%d')}: the authors raised the cost of postponing (costs.skip_cost) "
                         "from NZ$25 to NZ$30 and added the early-start option (employer permission by archetype, "
                         "07:00 start, NZ$3 x phi(F) a day); both are fixed assumptions and are not searched. The "
                         "search was rerun over PAP and k_WFH on the same grid with the same targets, seeds, loss "
                         f"and rule. This replaces the search with SKIP cost NZ$25 and no early start, which chose "
                         f"{prev.get('chosen', {}).get('label')} (no feasible point, lowest loss); its full log is "
                         "kept in data/behaviour_calibration_skip25_noearly.json and its report in "
                         "docs/calibration_report_skip25_noearly.md.")})
        from cordonlite.config import load_config as _lc
        fuel_km = float(_lc().costs.fuel_cost_per_km)
        _c = _lc()
        res = {"early_start": {"early_start_min": int(_c.costs.early_start_min),
                               "early_shift_cost": float(_c.costs.early_shift_cost),
                               "early_shift_prob": list(_c.persona.early_shift_prob),
                               "anchor_offsets_min": list(_c.time.anchor_offsets_min),
                               "status": "fixed assumptions [A, author decision 2026-10-05]; not searched"},
               "skip": {"skip_cost": float(_c.costs.skip_cost), "skip_vot_hours": float(_c.costs.skip_vot_hours),
                        "status": "fixed assumption [A, author decision 2026-10-05; raised with the driving cost]; not searched"},
               "fuel": {"fuel_cost_per_km": fuel_km, "status": "fixed input (config.toml: author-supplied petrol price, Oct 2026, x 9.0 L/100 km); not searched",
                        "form": "car fuel = round(2 x path_km x fuel_cost_per_km, 2); 0 for company cars; "
                                "v3_relative WFH carries it like parking",
                        "before_state_has_fuel": False},
               "parking": {"park_cost_paid_office": PARK_FIXED, "student": 0.75 * PARK_FIXED,
                           "status": "fixed input [author decision, 2026-10-03]; not searched"},
               "targets": TARGETS, "seed_tolerance": SEED_TOL, "seeds": list(SEEDS),
               "holdout_seeds": list(HOLDOUT_SEEDS), "n_agents": N_AGENTS, "n_days": N_DAYS,
               "arm": "R-daily", "decider": "rule", "engine": "py",
               "before_overrides": BEFORE, "structural_overrides": STRUCTURAL,
               "structural_fixes": STRUCTURAL_FIXES_DOC, "grid": GRID, "v3_scalars": V3_SCALARS,
               "capacity_procedure": ("nested: for every evaluated point and seed, cordonlite.run.calibrate "
                                      "(default bracket and tolerance) is run with that point's behaviour "
                                      "parameters, then the 30-day charged run uses the resulting scale")}
        jobs = [{"label": "before", "overrides": BEFORE, "seed": s, "scale": "calibrate", "nofee": True}
                for s in SEEDS]
        jobs += [{"label": "structural", "overrides": point_overrides(**{"pap": 8.0, "park_paid": PARK_FIXED, "wfh": 8.0}),
                  "seed": s, "scale": "calibrate"} for s in SEEDS]
        pts = list(itertools.product(GRID["pap"], [PARK_FIXED], GRID["wfh"]))
        jobs += [{"label": f"pap{p:g}_park{k:g}_wfh{w:g}", "overrides": point_overrides(p, k, w), "seed": s,
                  "scale": "calibrate", "meta": {"scalars": {"pap": p, "park": k, "wfh": w}}}
                 for (p, k, w) in pts for s in SEEDS]
        print(f"search: {len(jobs)} evaluations on {args.workers} workers", flush=True)
        rows = run_jobs(jobs, args.workers, "search")
        res["before"] = {"per_seed": [r for r in rows if r["label"] == "before"]}
        res["before"]["mean"] = summarise(res["before"]["per_seed"])
        res["structural_only"] = {"per_seed": [r for r in rows if r["label"] == "structural"]}
        res["structural_only"]["mean"] = summarise(res["structural_only"]["per_seed"])
        points = []
        for (p, k, w) in pts:
            label = f"pap{p:g}_park{k:g}_wfh{w:g}"
            pr = [r for r in rows if r["label"] == label]
            sc = {"pap": p, "park": k, "wfh": w}
            points.append({"label": label, "scalars": sc, "loss": loss(pr, sc), "mean": summarise(pr),
                           "feasible": feasible(pr), "anchor_distance": anchor_distance(sc),
                           "per_seed": [{kk: r[kk] for kk in ("seed", "capacity_scale", "calibration", *TARGETS,
                                                              "end_car", "end_pt", "end_wfh", "end_skip",
                                                              "base_early", "end_early", "peak_cross_change",
                                                              "peak_band_share_21_30")} for r in pr]})
        res["search"] = {"method": ("full factorial grid over PAP and k_WFH in NZ$1 steps, paid parking fixed at "
                                    "NZ$17; nested capacity calibration at every point and seed"),
                         "free_scalars": ["pap", "wfh"], "range_probe": RANGE_PROBE,
                         "anchors": ANCHORS, "selection": SELECTION_DOC,
                         "points": points, "loss_doc": " ".join(loss.__doc__.split()),
                         "selection_history": history}
        best = select(points)
        res["chosen"] = {"scalars": best["scalars"], "label": best["label"], "loss": best["loss"],
                         "on_grid_edge": on_grid_edge(best["scalars"])}
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
        print(f"chosen {best['label']} loss {best['loss']['total']:.3f} mean {best['mean']}", flush=True)

    if args.stage == "select":   # re-apply the selection rule to the logged search (no new runs)
        # append-only history: keep the rule, anchors and choice being replaced
        res["search"].setdefault("selection_history", []).append(
            {"replaced_at": time.strftime("%Y-%m-%d %H:%M:%S"), "selection": res["search"].get("selection"),
             "anchors": res["search"].get("anchors"), "chosen": res.get("chosen", {}).get("label")})
        for p in res["search"]["points"]:
            p["feasible"] = feasible(p["per_seed"], p["mean"])
            p["anchor_distance"] = anchor_distance(p["scalars"])
        res["search"]["selection"] = SELECTION_DOC
        res["search"]["anchors"] = ANCHORS
        best = select(res["search"]["points"])
        res["chosen"] = {"scalars": best["scalars"], "label": best["label"], "loss": best["loss"],
                         "on_grid_edge": on_grid_edge(best["scalars"])}
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
        print(f"chosen {best['label']} feasible {best['feasible']} mean {best['mean']}", flush=True)

    if args.stage in ("all", "final"):
        ch = res["chosen"]["scalars"]
        ov = point_overrides(ch["pap"], ch["park"], ch["wfh"])
        rows = run_jobs([{"label": "chosen", "overrides": ov, "seed": s, "scale": "calibrate", "nofee": True,
                          "agents": True} for s in SEEDS + HOLDOUT_SEEDS], args.workers, "final")
        main_rows = [r for r in rows if r["seed"] in SEEDS]
        hold = [r for r in rows if r["seed"] in HOLDOUT_SEEDS]
        scale_by_seed = {r["seed"]: r["capacity_scale"] for r in main_rows}
        agents = [{**a, "seed": r["seed"]} for r in main_rows for a in r.pop("agents")]
        agents0 = [{**a, "seed": r["seed"]} for r in main_rows for a in r["nofee"].pop("agents")]
        for r in hold:
            r.pop("agents", None)
            r["nofee"].pop("agents", None)
        res["chosen"].update(per_seed=main_rows, holdout=hold, mean=summarise(main_rows), feasible=feasible(main_rows),
                             targets=target_status(main_rows), loss=loss(main_rows, ch))
        res["who_adapts"] = who_adapts(agents, agents0).to_dict("records")
        # retiming against the same-capacity no-charge run
        rt = [{"seed": r["seed"], "peak": r["peak_band_share_21_30"], "peak_nofee": r["nofee"]["peak_band_share_21_30"],
               "shoulder": r["shoulder_share_21_30"], "shoulder_nofee": r["nofee"]["shoulder_share_21_30"]}
              for r in main_rows]
        d_peak = [x["peak"] - x["peak_nofee"] for x in rt]
        d_sh = [x["shoulder"] - x["shoulder_nofee"] for x in rt]
        early0 = [sum(v for k, v in r["nofee"]["exit_hist_21_30"].items() if int(k) < 450) for r in main_rows]
        early1 = [sum(v for k, v in r["exit_hist_21_30"].items() if int(k) < 450) for r in main_rows]
        for x, e0, e1 in zip(rt, early0, early1):
            x.update(early_crossings=e1, early_crossings_nofee=e0)
        res["retiming_paired"] = {"all": paired_retiming(agents, agents0),
                                  "by_F": paired_retiming(agents, agents0, "F")}
        res["retiming"] = {"per_seed": rt, "peak_minus_nofee": d_peak, "shoulder_minus_nofee": d_sh,
                           "verdict": (f"08:00-09:00 crossing share under the charge minus no charge: "
                                       + ", ".join(f"{x:+.3f}" for x in d_peak) + " (seeds 1-3); 07:00-08:00: "
                                       + ", ".join(f"{x:+.3f}" for x in d_sh) + ". "
                                       + ("Peak spreading is visible in every seed."
                                          if all(x < 0 for x in d_peak) else
                                          "Peak spreading is NOT visible in every seed."))}
        # early start, retiming, postponing and peak spreading, per seed (charged run and no-charge run)
        def _keepers(rows_, seed):
            d = pd.DataFrame([a for a in rows_ if a["seed"] == seed])
            k = d[d["modal_6_10"].str.startswith("CAR") & d["modal_26_30"].str.startswith("CAR")]
            ret = k[k["modal_26_30"] != k["modal_6_10"]]
            shift = ret["modal_26_30"].str[4:].astype(int) - ret["modal_6_10"].str[4:].astype(int)
            return {"n_all": int(len(d)), "n_keepers": int(len(k)), "n_retimed": int(len(ret)),
                    "retimed_of_keepers": float(len(ret) / len(k)) if len(k) else float("nan"),
                    "retimed_of_all": float(len(ret) / len(d)) if len(d) else float("nan"),
                    "retimed_earlier_of_all": float((shift < 0).sum() / len(d)) if len(d) else float("nan"),
                    "retimed_later_of_all": float((shift > 0).sum() / len(d)) if len(d) else float("nan")}

        es_rows = []
        for r in main_rows + hold:
            row = {"seed": r["seed"], "early_ok_share": r["early_ok_share"]}
            for k in ("base_early", "end_early", "early_11_13", "base_early_of_cars", "end_early_of_cars", "base_skip",
                      "end_skip", "change_21_30", "peak_cross_change", "pre0730_cross_change", "peak_cross_6_10",
                      "peak_cross_21_30"):
                row[k] = r[k]
            for k in ("base_early", "end_early", "end_skip", "change_21_30", "peak_cross_change", "pre0730_cross_change"):
                row[f"nofee_{k}"] = r["nofee"][k]
            if r["seed"] in SEEDS:
                row["retiming"] = _keepers(agents, r["seed"])
                row["nofee_retiming"] = _keepers(agents0, r["seed"])
            es_rows.append(row)
        es_main = [x for x in es_rows if x["seed"] in SEEDS]
        es_mean = {k: float(np.mean([x[k] for x in es_main])) for k in es_main[0] if k not in ("seed", "retiming", "nofee_retiming")}
        for kk in ("retiming", "nofee_retiming"):
            es_mean[kk] = {k: float(np.mean([x[kk][k] for x in es_main])) for k in es_main[0][kk]}
        res["early_start_summary"] = {
            "definitions": {
                "early": "share of all commuters whose day is measured against the early start (car or PT), mean over the days",
                "early_of_cars": "the same as a share of that day's car users",
                "retimed": ("commuters whose modal option is a car departure on days 6-10 and on days 26-30 and whose "
                            "modal departure differs; an early-start departure counts as a retimed departure"),
                "peak_cross_change": "car crossings with a gate exit 08:00-09:00, mean per day days 21-30 vs days 6-10",
                "nofee_*": "the same quantity in the no-charge run at the same capacity and seed (churn baseline)"},
            "per_seed": es_rows, "mean_1_3": es_mean}
        # population trait manipulation at fixed capacity
        mjobs = []
        for trait in "HFPS":
            for lv in (1, 2, 3, 4, 5):
                one = [1.0 if i == lv else 0.0 for i in range(1, 6)]
                for s in SEEDS:
                    mjobs.append({"label": f"{trait}{lv}", "overrides": {**ov, f"traits.shares_{trait}": one},
                                  "seed": s, "scale": scale_by_seed[s], "nofee": True, "agents": True,
                                  "meta": {"trait": trait, "level": lv}})
        mrows = run_jobs(mjobs, args.workers, "manipulation")
        man = []
        for trait in "HFPS":
            for lv in (1, 2, 3, 4, 5):
                rr = [r for r in mrows if r["trait"] == trait and r["level"] == lv]
                to_pt, ret, ret0 = [], [], []
                for r in rr:
                    df = pd.DataFrame(r["agents"])
                    d = df[(~df["twin"]) & df["modal_6_10"].str.startswith("CAR")]
                    to_pt.append(float((d["modal_26_30"] == "PT").mean()))
                    keep = d[d["modal_26_30"].str.startswith("CAR")]
                    ret.append(float((keep["modal_26_30"] != keep["modal_6_10"]).mean()))
                    d0 = pd.DataFrame(r["nofee"]["agents"])
                    d0 = d0[(~d0["twin"]) & d0["modal_6_10"].str.startswith("CAR")]
                    k0 = d0[d0["modal_26_30"].str.startswith("CAR")]
                    ret0.append(float((k0["modal_26_30"] != k0["modal_6_10"]).mean()))
                man.append({"trait": trait, "level": lv,
                            "change_11_13": float(np.mean([r["change_11_13"] for r in rr])),
                            "change_21_30": float(np.mean([r["change_21_30"] for r in rr])),
                            "to_pt": float(np.mean(to_pt)),
                            "pt_gain": float(np.mean([r["end_pt"] - r["base_pt"] for r in rr])),
                            "end_pt": float(np.mean([r["end_pt"] for r in rr])),
                            "base_pt": float(np.mean([r["base_pt"] for r in rr])),
                            "end_pt_minus_nofee": float(np.mean([r["end_pt"] - r["nofee"]["end_pt"] for r in rr])),
                            "peak_minus_nofee": float(np.mean([r["peak_band_share_21_30"]
                                                               - r["nofee"]["peak_band_share_21_30"] for r in rr])),
                            "retime_minus_nofee": float(np.mean(ret) - np.mean(ret0)),
                            "per_seed_change_21_30": [r["change_21_30"] for r in rr]})
        res["manipulation"] = man

        def series(trait, key):
            return [m[key] for m in man if m["trait"] == trait]

        verdict = []
        def mono(v, up=True):
            d = np.diff(v)
            return bool(np.all(d >= 0)) if up else bool(np.all(d <= 0))

        def trend(v):
            return float(np.polyfit(np.arange(1, len(v) + 1), v, 1)[0])

        h11 = series("H", "change_11_13")
        verdict.append(f"H, day 11-13 response (levels 1-5): {', '.join(pct(x) for x in h11)}; linear trend "
                       f"{trend(h11) * 100:+.2f} pp per level: "
                       + ("smaller with higher H (monotone)" if mono(h11) else "NOT strictly monotone"))
        h30 = series("H", "change_21_30")
        verdict.append(f"H, day 21-30 response: {', '.join(pct(x) for x in h30)}; trend {trend(h30) * 100:+.2f} pp "
                       "per level: " + ("smaller with higher H (monotone)" if mono(h30) else
                                        "NOT monotone (habit re-forms on the new mode at once, so high H also "
                                        "keeps leavers on PT)"))
        p_ = series("P", "end_pt_minus_nofee")
        verdict.append(f"P, PT share at days 21-30 caused by the charge (charge minus no-charge run): "
                       f"{', '.join(f'{x:+.3f}' for x in p_)}: "
                       + ("rises with P (monotone)" if mono(p_) else "NOT monotone"))
        p3 = series("P", "end_pt")
        verdict.append(f"P, PT share at days 21-30 with the charge: "
                       f"{', '.join(f'{x:.3f}' for x in p3)}: " + ("rises with P (monotone)" if mono(p3) else "NOT monotone"))
        p2 = series("P", "to_pt")
        verdict.append(f"P, share of day-10 drivers on PT at days 26-30: {', '.join(f'{x:.3f}' for x in p2)} "
                       "(selection: at P = 5 most PT-feasible agents already ride PT before the charge, so the "
                       "remaining drivers are those for whom PT is poor)")
        f_ = series("F", "peak_minus_nofee")
        verdict.append(f"F, 08:00-09:00 share minus no-charge: {', '.join(f'{x:+.3f}' for x in f_)}: "
                       + ("more peak spreading with higher F (monotone)" if mono(f_, up=False) else
                          f"NOT strictly monotone (trend {trend(f_):+.3f} per level)"))
        fr = series("F", "retime_minus_nofee")
        verdict.append(f"F, retimed keepers minus no-charge: {', '.join(f'{x:+.3f}' for x in fr)}: "
                       + ("rises with F (monotone)" if mono(fr) else f"NOT strictly monotone (trend {trend(fr):+.3f} per level)"))
        s_ = series("S", "change_21_30")
        verdict.append(f"S, day 21-30 response: {', '.join(pct(x) for x in s_)}: "
                       + ("stronger with higher S (monotone)" if mono(s_, up=False) else
                          f"NOT strictly monotone (trend {trend(s_) * 100:+.2f} pp per level)"))
        s11 = series("S", "change_11_13")
        verdict.append(f"S, day 11-13 response: {', '.join(pct(x) for x in s11)}: "
                       + ("stronger with higher S (monotone)" if mono(s11, up=False) else "NOT strictly monotone"))
        res["monotonicity_verdict"] = verdict
        res["nofee_chosen"] = [r["nofee"] for r in main_rows]
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")

    if args.stage in ("all", "oos"):   # out-of-sample checks; never used in the selection
        ch = res["chosen"]["scalars"]
        ov = point_overrides(ch["pap"], ch["park"], ch["wfh"])
        jobs = [{"label": "chosen", "overrides": ov, "seed": s, "scale": "calibrate",
                 "meta": {"scalars": dict(ch)}} for s in OOS_SEEDS]
        ridge = ridge_alternatives(res["search"]["points"], res["chosen"]["label"])
        for (p_, k_, w_) in ridge:
            jobs += [{"label": f"pap{p_:g}_park{k_:g}_wfh{w_:g}", "overrides": point_overrides(p_, k_, w_), "seed": s,
                      "scale": "calibrate", "meta": {"scalars": {"pap": p_, "park": k_, "wfh": w_}}}
                     for s in HOLDOUT_SEEDS + OOS_SEEDS]
        scale_by_seed = {r["seed"]: r["capacity_scale"] for r in res["chosen"]["per_seed"]}
        for lv in (1, 2, 3, 4, 5):
            one = [1.0 if i == lv else 0.0 for i in range(1, 6)]
            jobs += [{"label": f"F{lv}", "overrides": {**ov, "traits.shares_F": one}, "seed": s,
                      "scale": scale_by_seed[s], "nofee": True, "agents": True, "meta": {"level": lv}}
                     for s in SEEDS]
        # sensitivities to the fixed assumptions at the chosen point (never adopted, no new search)
        GAP = [("skip25", "postponing costs NZ$25 + 1 h of VoT (costs.skip_cost 30 -> 25, the value until 2026-10-05)",
                {"costs.skip_cost": 25.0}),
               ("noearly", "no early-start option (persona.early_shift_prob all 0)",
                {"persona.early_shift_prob": [0.0, 0.0, 0.0, 0.0, 0.0]}),
               ("early1.5", "early day costs NZ$1.5 x phi(F) (costs.early_shift_cost 3 -> 1.5)",
                {"costs.early_shift_cost": 1.5}),
               ("early6", "early day costs NZ$6 x phi(F) (costs.early_shift_cost 3 -> 6)",
                {"costs.early_shift_cost": 6.0}),
               ("earlyall", "every employer of archetypes 1, 2 and 4 allows the early day (probabilities 1, 1, 0, 1, 0)",
                {"persona.early_shift_prob": [1.0, 1.0, 0.0, 1.0, 0.0]})]
        jobs += [{"label": f"gap_{g_}", "overrides": {**ov, **o_}, "seed": s, "scale": "calibrate"}
                 for (g_, _, o_) in GAP for s in SEEDS]
        rows = run_jobs(jobs, args.workers, "oos")
        gap = []
        for (g_, what, o_) in GAP:
            pr = [r for r in rows if r["label"] == f"gap_{g_}"]
            gap.append({"label": g_, "what": what, "overrides": o_, "mean": summarise(pr), "feasible": feasible(pr),
                        "per_seed": [{kk: r[kk] for kk in ("seed", "capacity_scale", *TARGETS, "end_skip", "base_early",
                                                           "end_early", "peak_cross_change")} for r in pr]})
        res["gap_sensitivity"] = {
            "note": ("Run after the selection and not adopted. Each variant changes one of the fixed assumptions "
                     "(cost of postponing, early-start option) at the chosen PAP and k_WFH (no new search), on seeds "
                     "1-3 with nested capacity calibration, to show how much the result depends on it."),
            "variants": gap, "reading": ""}
        keep = ("seed", "capacity_scale", *TARGETS, "end_car", "end_pt", "end_wfh", "end_skip", "base_early",
                "end_early", "peak_cross_change", "pre0730_cross_change")
        held = [{k: r[k] for k in keep} for r in res["chosen"]["holdout"]]
        unseen = [{k: r[k] for k in keep} for r in rows if r["label"] == "chosen"]
        oos: dict[str, Any] = {
            "note": ("Out-of-sample checks run after the selection; they did not influence it. Capacity is "
                     "recalibrated per seed as in the search."),
            "chosen": {"scalars": dict(ch), "per_seed": held + unseen,
                       "mean_4_12": summarise_keys(held + unseen, keep[2:]),
                       "mean_6_12": summarise_keys(unseen, keep[2:]),
                       "mean_1_12": summarise_keys([{k: r[k] for k in keep} for r in res["chosen"]["per_seed"]]
                                                   + held + unseen, keep[2:])},
            "alternatives": [],
        }
        for (p_, k_, w_) in ridge:
            lab = f"pap{p_:g}_park{k_:g}_wfh{w_:g}"
            rr = [{k: r[k] for k in keep} for r in rows if r["label"] == lab]
            calib = next(p for p in res["search"]["points"] if p["label"] == lab)
            oos["alternatives"].append({"label": lab, "scalars": {"pap": p_, "park": k_, "wfh": w_}, "per_seed": rr,
                                        "mean_4_12": summarise_keys(rr, keep[2:]),
                                        "mean_1_3": {k: calib["mean"][k] for k in keep[2:]}})
        fdec = []
        for lv in (1, 2, 3, 4, 5):
            rr = [r for r in rows if r["label"] == f"F{lv}"]
            ret, ret0 = [], []
            for r in rr:
                df = pd.DataFrame(r["agents"])
                d0 = pd.DataFrame(r["nofee"]["agents"])
                for frame, acc in ((df, ret), (d0, ret0)):
                    d = frame[(~frame["twin"]) & frame["modal_6_10"].str.startswith("CAR")]
                    k = d[d["modal_26_30"].str.startswith("CAR")]
                    acc.append(float((k["modal_26_30"] != k["modal_6_10"]).mean()))
            fdec.append({"level": lv,
                         "change_21_30": float(np.mean([r["change_21_30"] for r in rr])),
                         "end_car_minus_nofee": float(np.mean([r["end_car"] - r["nofee"]["end_car"] for r in rr])),
                         "end_pt_minus_nofee": float(np.mean([r["end_pt"] - r["nofee"]["end_pt"] for r in rr])),
                         "end_wfh_minus_nofee": float(np.mean([r["end_wfh"] - r["nofee"]["end_wfh"] for r in rr])),
                         "end_wfh": float(np.mean([r["end_wfh"] for r in rr])),
                         "end_wfh_per_seed": [r["end_wfh"] for r in rr],
                         "nofee_end_wfh": float(np.mean([r["nofee"]["end_wfh"] for r in rr])),
                         "retimed_keepers": float(np.mean(ret)), "retimed_keepers_nofee": float(np.mean(ret0))})
        oos["F_decomposition"] = fdec
        res["out_of_sample"] = oos
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")

    if args.stage == "gap":   # optional local re-search under one changed assumption; logged, never adopted; not part of "all"
        GAP_GRID = {"pap": [float(x) for x in range(17, 25)], "wfh": [7.0, 8.0, 9.0, 10.0, 11.0]}
        research = []
        jobs = []
        for v in res["gap_sensitivity"]["variants"]:
            for p_ in GAP_GRID["pap"]:
                for w_ in GAP_GRID["wfh"]:
                    jobs += [{"label": f"{v['label']}|{p_:g}|{w_:g}",
                              "overrides": {**point_overrides(p_, PARK_FIXED, w_), **v["overrides"]},
                              "seed": s, "scale": "calibrate"} for s in SEEDS]
        rows = run_jobs(jobs, args.workers, "gap")
        for v in res["gap_sensitivity"]["variants"]:
            pts_ = []
            for p_ in GAP_GRID["pap"]:
                for w_ in GAP_GRID["wfh"]:
                    pr = [r for r in rows if r["label"] == f"{v['label']}|{p_:g}|{w_:g}"]
                    sc = {"pap": p_, "park": PARK_FIXED, "wfh": w_}
                    pts_.append({"label": f"pap{p_:g}_park{PARK_FIXED:g}_wfh{w_:g}", "scalars": sc,
                                 "loss": loss(pr, sc), "mean": summarise(pr), "feasible": feasible(pr),
                                 "anchor_distance": anchor_distance(sc),
                                 "per_seed": [{kk: r[kk] for kk in ("seed", "capacity_scale", *TARGETS)} for r in pr]})
            best = select(pts_)
            research.append({"label": v["label"], "what": v["what"], "overrides": v["overrides"], "grid": GAP_GRID,
                             "n_points": len(pts_), "n_feasible": sum(p["feasible"] for p in pts_),
                             "feasible": [p["label"] for p in pts_ if p["feasible"]],
                             "would_choose": {k: best[k] for k in ("label", "scalars", "mean", "feasible", "per_seed", "loss")},
                             "points": pts_})
        res["gap_sensitivity"]["research"] = research
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")

    if args.stage in ("all", "final", "oos", "gap", "report"):
        ch = res["chosen"]["scalars"]
        before_rows = res["before"]["per_seed"]
        after_rows = res["chosen"]["per_seed"]
        res["figures"] = figures(before_rows, after_rows, [r["nofee"] for r in after_rows],
                                 res["search"]["points"], ch)
        res["limits"] = LIMITS
        res["structural_fixes"] = STRUCTURAL_FIXES_DOC
        if PRE_FUEL_JSON.exists():   # summary of the archived calibration without fuel (before/after table)
            old = json.loads(PRE_FUEL_JSON.read_text())
            res["pre_fuel"] = {
                "source": str(PRE_FUEL_JSON.relative_to(ROOT)), "chosen": old["chosen"]["scalars"],
                "chosen_mean": old["chosen"]["mean"], "structural_mean": old["structural_only"]["mean"],
                "grid": old["grid"], "grid_fine": old["search"]["grid_fine"],
                "n_points": len(old["search"]["points"]),
                "n_feasible": sum(bool(p["feasible"]) for p in old["search"]["points"]),
                "oos_mean_6_12": old.get("out_of_sample", {}).get("chosen", {}).get("mean_6_12")}
        if LAST_JSON.exists():   # summary of the archived two-scalar calibration with SKIP 25 and no early start
            old = json.loads(LAST_JSON.read_text())
            res["last"] = {
                "source": str(LAST_JSON.relative_to(ROOT)), "chosen": old["chosen"]["scalars"],
                "chosen_mean": old["chosen"]["mean"], "n_points": len(old["search"]["points"]),
                "n_feasible": sum(bool(p["feasible"]) for p in old["search"]["points"]),
                "oos_mean_6_12": old.get("out_of_sample", {}).get("chosen", {}).get("mean_6_12")}
        if PREV_JSON.exists():   # summary of the archived three-scalar calibration with fuel NZ$0.23/km
            old = json.loads(PREV_JSON.read_text())
            res["previous"] = {
                "source": str(PREV_JSON.relative_to(ROOT)), "chosen": old["chosen"]["scalars"],
                "chosen_mean": old["chosen"]["mean"], "n_points": len(old["search"]["points"]),
                "n_feasible": sum(bool(p["feasible"]) for p in old["search"]["points"]),
                "oos_mean_6_12": old.get("out_of_sample", {}).get("chosen", {}).get("mean_6_12")}
        res["chosen"]["on_grid_edge"] = on_grid_edge(ch)
        if res.get("gap_sensitivity"):
            res["gap_sensitivity"]["reading"] = GAP_READING
        res["selection_sensitivity"] = selection_sensitivity(res["search"]["points"])
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
        write_report(res)
    print(f"done in {time.perf_counter() - t0:.0f}s -> {OUT_JSON.relative_to(ROOT)}, {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
