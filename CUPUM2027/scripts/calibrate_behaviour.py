"""Behaviour calibration of the rule decider against observed cordon responses.

    .venv/bin/python scripts/calibrate_behaviour.py [--workers 12] [--stage all|search|select|final|oos|report]

What it does (R-daily arm, rule decider, PyEngine, seeds 1-3, n = run.n_agents of config.toml (950;
300 before 2026-10-08), 30 days; LLM arms are never calibrated). The single-seed tolerances scale with
n (seed_tolerance: the n = 300 values x sqrt(300 / n)):

1. ``before``: the pre-recalibration specification (paid-fee reference, eta up to 3, PAP 0, WFH =
   wfh_cost x phi, kappa_H halved at T2, paid parking NZ$8, no fuel cost, no early start, no limit on
   the willingness to pay), with capacity recalibrated per seed. SKIP (postpone the day) was removed
   from the model on 2026-10-09, so this state no longer has it either.
2. ``structural``: the structural fixes alone, at the design values (PAP 8, k_WFH 8 [v3]; wtt.beta0
   0.5 [SSC2026 base_beta]), with the two fixed inputs of the current model: paid parking NZ$17
   (PARK_FIXED, an author decision) and the fuel cost (costs.fuel_cost_per_km from config.toml).
   Neither is searched.
3. ``search``: a staged grid over THREE free scalars on top of the structural fixes (2026-10-09):
   PAP (costs.pt_attitude_penalty) x k_WFH (costs.wfh_cost) x beta0 (wtt.beta0, the price
   sensitivity of the willingness to travel: P(WTP >= F) = exp(-beta F / VoT)). Paid parking is fixed
   at PARK_FIXED (office archetypes; student 0.75 x) and is no longer a calibrated scalar (2026-10-03,
   DEVIATIONS.md "Parking and fuel fixed by the authors"). For every (PAP, k_WFH) pair and seed the
   corridor capacity is recalibrated first with the project's own ``cordonlite.run.calibrate``
   (R-daily, no charge, days 6-10, car-weighted peak 15-min delay = engine.calib_target_peak_delay_min
   (15 min), where the delay is queue + road delay with engine.calib_delay = "total" (config.toml,
   2026-10-07) and the gate queue alone with "queue"; default bisection bracket), so behaviour and
   capacity are mutually consistent at every evaluated point (a nested solve rather than
   alternation). The calibration runs without the charge, where the willingness to pay removes no
   option (every fee is 0), so its scale does not depend on beta0: it is solved once per (PAP, k_WFH,
   seed) and shared by every beta0 of that pair (the days 1-10 of the charged runs, and with them the
   base shares, are the same for every beta0 too). Even so, the full 27 x 15 x 7 grid (1,215
   calibrations and 8,505 charged runs) would take about 11 hours on 14 workers (under 14-way load a
   calibration takes about 140 s and a 30-day run about 44 s of a worker's time; alone about 200 s and
   70 s), so the search is staged (SEARCH_DESIGN):
     stage 1: beta0 in BETA0_STAGE1 (0.05 to 1.0) on PAP 21-23 x k_WFH {4, 6, 8, 9, 10, 12, 14, 16}
              around the earlier optimum (PAP 22, k_WFH 9) and on the four corners of the NZ$1 grid;
     stage 2: the full NZ$1 k_WFH range 2-16 at every beta0 of stage 1, on the PAP values where stage 1
              meets the three base-share targets (base shares do not depend on beta0), widened by
              one step when such a PAP is at the edge of the stage-1 range;
     stage 3: one finer beta0 step, the midpoints between the stage-2 choice and its neighbours in
              BETA0_STAGE1, on the same (PAP, k_WFH) pairs.
   beta0 = 0 (no limit: the model without the willingness to travel) is run on every stage 1-2 pair
   as a reference and is never selected. Every evaluated point is logged. Earlier searches are
   archived in data/behaviour_calibration_pre_fuel.json (no fuel, three scalars),
   data/behaviour_calibration_fuel023_park11.json (fuel NZ$0.23/km, three scalars),
   data/behaviour_calibration_skip25_noearly.json (SKIP cost NZ$25, no early-start option; two
   scalars), data/behaviour_calibration_freeflow300.json (SKIP cost NZ$30 and early start, 300
   agents, free-flow roads, capacity calibrated to the gate queue alone; two scalars) and
   data/behaviour_calibration_skip30_nowtt.json (950 agents, congested roads, SKIP cost NZ$30, no
   willingness to travel; two scalars), each with data/calibration_<tag>.json,
   docs/calibration_report_<tag>.md and docs/figures/<tag>/ (with the example prompt of that state);
   the selection history is carried forward from the latest archive (LAST_JSON). The early-start
   option (costs.early_start_min, costs.early_shift_cost, persona.early_shift_prob) is a fixed
   assumption of the current model (2026-10-05) and is never searched; so are run.n_agents, the
   [road] settings, engine.calib_delay, wtt.beta_clip and wtt.vot_ref.
4. ``select``: lexicographic (SELECTION_DOC): feasible points first (3-seed means in band at the
   targets' stated precision, every seed within the stated tolerance), then the point closest to
   the literature / design anchors (PAP 8, k_WFH 8, beta0 0.5), then the loss. ``--stage select``
   re-applies it to the log.
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

Behaviour is calibrated at the NZ$6 peak (fees.peak_fee of config.toml); runs at other peaks
extrapolate. Everything runs in-process into temporary folders; runs/ and data/calibration.json are
not touched. Capacity calibration for the chosen values is written separately with
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

from cordonlite.config import load_config  # noqa: E402

OUT_JSON = ROOT / "data" / "behaviour_calibration.json"
PRE_FUEL_JSON = ROOT / "data" / "behaviour_calibration_pre_fuel.json"   # archived log of the calibration without fuel
PREV_JSON = ROOT / "data" / "behaviour_calibration_fuel023_park11.json"   # archived log: fuel 0.23/km, parking searched (chose 11)
SKIP25_JSON = ROOT / "data" / "behaviour_calibration_skip25_noearly.json"   # archived log: SKIP cost 25, no early start (chose PAP 20 / k_WFH 10)
# archived log: SKIP cost 30 and early start with 300 agents and free-flow roads, capacity calibrated to the gate
# queue (chose PAP 20 / k_WFH 10)
FREEFLOW_JSON = ROOT / "data" / "behaviour_calibration_freeflow300.json"
# the latest archived log, whose selection history the next search carries forward: 950 agents, congested roads,
# SKIP cost 30, no willingness to travel, two scalars (chose PAP 22 / k_WFH 9; archived 2026-10-09)
LAST_JSON = ROOT / "data" / "behaviour_calibration_skip30_nowtt.json"
OUT_MD = ROOT / "docs" / "calibration_report.md"
FIG_DIR = ROOT / "docs" / "figures"


def archive_paths(log: Path) -> dict[str, str]:
    """Repository paths of an archived state data/behaviour_calibration_<tag>.json: the log, the capacity
    calibration data/calibration_<tag>.json, the report docs/calibration_report_<tag>.md and the figures
    docs/figures/<tag>/."""
    tag = log.stem.removeprefix("behaviour_calibration_")
    return {"tag": tag, "log": f"data/{log.name}", "capacity": f"data/calibration_{tag}.json",
            "report": f"docs/calibration_report_{tag}.md", "figures": f"docs/figures/{tag}/"}


def archive_summary(log: Path) -> dict[str, Any]:
    """What the report's history table reads from an archived two-scalar log (freeflow300 and later)."""
    old = json.loads(log.read_text())
    arc = archive_paths(log)
    return {"source": arc["log"], "report": arc["report"], "capacity": arc["capacity"],
            "chosen": old["chosen"]["scalars"], "chosen_mean": old["chosen"]["mean"],
            "n_points": len(old["search"]["points"]),
            "n_feasible": sum(bool(p["feasible"]) for p in old["search"]["points"]),
            "on_grid_edge": old["chosen"].get("on_grid_edge"),
            "n_agents": int(old.get("n_agents", 300)), "road": old.get("road"),
            "calib_delay": old.get("calib_delay") or "queue",
            "skip_cost": float(old.get("skip", {}).get("skip_cost", 30.0)),
            "fuel_cost_per_km": float(old.get("fuel", {}).get("fuel_cost_per_km", 0.30)),
            "oos_mean_6_12": old.get("out_of_sample", {}).get("chosen", {}).get("mean_6_12")}


SEEDS = (1, 2, 3)
HOLDOUT_SEEDS = (4, 5)
OOS_SEEDS = tuple(range(6, 13))   # unseen seeds, used only by --stage oos (never in the selection)
# Ridge alternatives checked out of sample: chosen from the search log by ridge_alternatives() (the
# non-feasible points that become feasible when the soft overshoot bound is relaxed, nearest the
# anchors first). Before the fuel addition these were PAP 8 / parking 15 and PAP 10 / parking 17. In the two-scalar
# search of 2026-10-09 (archived as skip30_nowtt) no point became feasible with the relaxed bound, so both came from
# the fallback (the points nearest the anchors among the ten lowest-loss other points): PAP 21 / k_WFH 9 and 10. The
# same holds in the three-scalar search of the same day, which gives PAP 22 / k_WFH 11 / beta0 0.1 and PAP 22 / k_WFH
# 10 / beta0 0.05.
N_RIDGE_ALTERNATIVES = 2
# agents per run: run.n_agents of config.toml (950 since 2026-10-08; the archived logs and the search
# before that date used 300); 30 days
N_AGENTS, N_DAYS = int(load_config().run.n_agents), 30
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
    "change_21_30": {"lo": -0.22, "hi": -0.12, "centre": -0.20,
                     "what": "car cordon crossings, mean days 21-30 vs mean days 6-10"},
    "change_11_13": {"lo": -0.30, "hi": 0.0, "centre": None,
                     "what": "overshoot, mean days 11-13 vs days 6-10 (may reach about -30%)"},
}
# The SKIP share target (at most 0.02 on days 6-10, single-seed tolerance 0) was dropped on 2026-10-09 with SKIP.
# stated tolerance for single seeds at n = 300: shares +/- 0.05, response +/- 4 pp
SEED_TOL_300 = {"base_car": 0.05, "base_pt": 0.05, "base_wfh": 0.05,
                "change_21_30": 0.04, "change_11_13": 0.04}
BASE_KEYS = ("base_car", "base_pt", "base_wfh")   # targets of days 6-10 (uncharged): they do not depend on beta0


def seed_tolerance(n_agents: int) -> dict[str, float]:
    """Single-seed tolerance at n agents: the n = 300 values x sqrt(300 / n), to 3 decimals (the
    seed-to-seed spread of a share or a change falls with 1 / sqrt(n); seeds 1-5, R-daily, at
    300 -> 950 the SD of the d21-30 response fell 1.9 -> 1.1 pp, x 0.58 against sqrt(300 / 950) =
    0.56). At 950: shares +/- 0.028, response +/- 2.2 pp."""
    f = math.sqrt(300.0 / int(n_agents))
    return {k: round(v * f, 3) for k, v in SEED_TOL_300.items()}


SEED_TOL = seed_tolerance(N_AGENTS)


def tolerance_words(tol: dict[str, float]) -> str:
    """'shares +/-0.028, response +/-2.2 pp' for the report."""
    return f"shares ±{tol['base_car']:g}, response ±{100 * tol['change_21_30']:g} pp"


def use_logged_n(res: dict[str, Any], stage: str) -> None:
    """A stage that re-uses the logged search keeps the search's n_agents (logs before 2026-10-08 have
    300): select and report use it for the tolerance and the text; final, oos and gap would add runs,
    so they stop when config.toml has another run.n_agents."""
    global N_AGENTS, SEED_TOL
    n = int(res.get("n_agents", 300))
    if not res or n == N_AGENTS:
        return
    if stage in ("final", "oos", "gap"):
        raise SystemExit(f"the logged search ({OUT_JSON.name}) used n_agents = {n}, config.toml has "
                         f"run.n_agents = {N_AGENTS}: rerun --stage search (or all) at {N_AGENTS} agents")
    print(f"note: the logged search used n_agents = {n} (config.toml {N_AGENTS}); {stage} uses {n}", flush=True)
    N_AGENTS, SEED_TOL = n, seed_tolerance(n)


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
    # the specification's SKIP option (cost NZ$25) no longer exists (removed 2026-10-09), so it cannot be restored here
    "persona.early_shift_prob": [0.0, 0.0, 0.0, 0.0, 0.0],   # the specification had no early-start option
    "wtt.beta0": 0.0,                # the specification had no limit on the willingness to pay
    **park(8.0),
}
STRUCTURAL = {   # structural fixes (values the v3 note justifies; see DEVIATIONS.md, Recalibration)
    "memory.ref_fee_update": "faced",
    "traits.eta": ETA_V3_CAPPED,
    "costs.wfh_form": "v3_relative",
    "clock.discontinuity_triggers": ["T1", "T4", "T6"],
}
# design values of the scalars: PAP, parking and k_WFH from v3; beta0 = SSC2026's base_beta 0.5 [SSC] (2026-10-09)
V3_SCALARS = {"pap": 8.0, "park": 8.0, "wfh": 8.0, "beta0": 0.5}
# Literature / design anchors used to choose inside the feasible set: PAP and k_WFH at the v3 values, beta0 at
# SSC2026's base_beta 0.5 (akl_pricing.nls; 2026-10-09).
# Paid parking is NOT searched any more: it is fixed at NZ$17/day [author decision, 2026-10-03], consistent
# with the all-day rate of Auckland Transport's Downtown, Civic and Victoria Street car parks from 1 Dec 2014
# (Greater Auckland, 18 Nov 2014, quoting AT). It stays in the scalars dict (constant) so that the loss and the
# anchor distance keep their earlier form; both terms are the same at every point.
PARK_FIXED = 17.0
ANCHORS = {"pap": 8.0, "park": 17.0, "wfh": 8.0, "beta0": 0.5}
# The NZ$1 ranges of PAP and k_WFH. They were fixed after a range-finding probe (PAP 12-40 in steps of 4 at k_WFH
# 8 and 12, seeds 1-3, logged under search.range_probe) and before the first two-scalar search, wide enough that
# the chosen point is not on an edge (the earlier ranges were PAP 4-12 and k_WFH 2-8, with both chosen values on
# the edge). Searched in full up to 2026-10-09; the three-scalar search covers them in stages (SEARCH_DESIGN).
GRID = {"pap": [float(x) for x in range(10, 37)],
        "wfh": [float(x) for x in range(2, 17)]}
# Third free scalar (2026-10-09): wtt.beta0. Stage 1 runs these values; 0.5 is the anchor (SSC2026 base_beta).
# beta = clip(beta0 x VoT_ref / VoT, 0.1, 2.0), so below beta0 = 0.1 the lower clip holds beta at 0.1 for every
# commuter with VoT above VoT_ref x beta0 / 0.1: the limit cannot be made weaker than that floor except by
# beta0 = 0, which switches it off.
BETA0_STAGE1 = [0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0]
BETA0_REFERENCE = 0.0   # no limit (the model without the willingness to travel): run as a reference, never selected
STAGE1 = {"pap": [21.0, 22.0, 23.0], "wfh": [4.0, 6.0, 8.0, 9.0, 10.0, 12.0, 14.0, 16.0]}
STAGE1_CORNERS = [(10.0, 2.0), (10.0, 16.0), (36.0, 2.0), (36.0, 16.0)]
SEARCH_DESIGN = (
    "staged grid over PAP x k_WFH x beta0 (paid parking fixed at NZ$17); capacity calibrated once per (PAP, k_WFH, "
    "seed) and shared by every beta0 of that pair (the calibration has no charge, so the willingness to pay removes "
    "nothing and the scale does not depend on beta0). Stage 1: beta0 in {0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0} on "
    "PAP 21-23 x k_WFH {4, 6, 8, 9, 10, 12, 14, 16} around the two-scalar optimum (PAP 22, k_WFH 9) and on the four "
    "corners of the NZ$1 grid (PAP 10 and 36 x k_WFH 2 and 16). Stage 2: the full NZ$1 k_WFH range 2-16 at every "
    "stage-1 beta0, on each PAP of stage 1 at which some k_WFH meets the three base-share targets (the base shares "
    "do not depend on beta0), plus the next PAP outwards when such a PAP is at the edge of 21-23. Stage 3: one finer "
    "beta0 step, the midpoints between the beta0 the rule chooses after stage 2 and its neighbours in the stage-1 "
    "list, on the stage-2 pairs. beta0 = 0 (no limit) is run on every stage 1-2 pair as a reference and never "
    "selected. Seeds 1-3; selection over every non-reference point of the three stages.")


def stage2_paps(points: list[dict]) -> list[float]:
    """PAP values for stage 2: those of stage 1 at which some k_WFH meets the three base-share targets
    (3-seed means in band at the stated precision and every seed within tolerance), plus the next PAP
    outwards when such a value is at the edge of STAGE1["pap"]. Without any, the PAP of the point with
    the smallest base-share excess and its two neighbours."""
    def base_excess(p):
        return (sum(band_excess(k, round(p["mean"][k], 2)) for k in BASE_KEYS)
                + sum(band_excess(k, r[k], SEED_TOL[k]) for r in p["per_seed"] for k in BASE_KEYS))

    cand = [p for p in points if p["scalars"]["pap"] in STAGE1["pap"]]
    ok = sorted({p["scalars"]["pap"] for p in cand if base_excess(p) == 0.0})
    if not ok:
        best = min(cand, key=base_excess)["scalars"]["pap"]
        return [best - 1.0, best, best + 1.0]
    out = set(ok)
    if min(ok) == min(STAGE1["pap"]):
        out.add(min(ok) - 1.0)
    if max(ok) == max(STAGE1["pap"]):
        out.add(max(ok) + 1.0)
    return sorted(out)


def stage3_betas(chosen_b0: float) -> list[float]:
    """The midpoints between the stage-2 choice of beta0 and its neighbours in BETA0_STAGE1 (half of it
    below the lowest value, 1.25 above the highest)."""
    b = sorted(BETA0_STAGE1)
    i = b.index(chosen_b0) if chosen_b0 in b else min(range(len(b)), key=lambda j: abs(b[j] - chosen_b0))
    lo = b[i - 1] if i > 0 else 0.0
    hi = b[i + 1] if i + 1 < len(b) else 1.5 * b[i]
    return sorted({round((lo + b[i]) / 2, 4), round((b[i] + hi) / 2, 4)} - set(b))
# 3-seed means of the range-finding probe, parking 17, fuel 0.30, run once before the grid was fixed, in the model
# of the first two-scalar search: 300 agents, free-flow roads, capacity calibrated to the gate queue, SKIP cost
# NZ$25, no early start (the same list is in data/behaviour_calibration_skip25_noearly.json). It has not been rerun
# since; the grid it set has been kept for every later search (2026-10-05; 2026-10-09 with 950 agents and congested
# roads, where the chosen PAP 22 / k_WFH 9 is again interior). These values do not describe the current model.
RANGE_PROBE = [
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


def on_grid_edge(sc: dict[str, float], beta0_values: list[float] | None = None) -> dict[str, bool]:
    """Whether each chosen scalar is at an end of its searched range: PAP and k_WFH against the NZ$1 ranges,
    beta0 (when present) against the searched positive values (default BETA0_STAGE1)."""
    out = {k: sc[k] in (min(GRID[k]), max(GRID[k])) for k in GRID}
    if "beta0" in sc:
        b = [x for x in (beta0_values or BETA0_STAGE1) if x > 0]
        out["beta0"] = sc["beta0"] in (min(b), max(b))
    return out


def point_overrides(pap: float, park_paid: float, wfh: float, beta0: float) -> dict[str, Any]:
    return {**STRUCTURAL, "costs.pt_attitude_penalty": pap, "costs.wfh_cost": wfh, "wtt.beta0": beta0,
            **park(park_paid)}


def point_label(sc: dict[str, float]) -> str:
    return f"pap{sc['pap']:g}_park{sc['park']:g}_wfh{sc['wfh']:g}_b{sc['beta0']:g}"


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

    share = {k: [d[k] / n for d in days] for k in ("cars", "pt", "wfh")}
    # willingness to travel (2026-10-09): commuters with every car option removed / with some removed, and the
    # decisions forced onto the one option left (PT only)
    share["no_car"] = [d.get("wtt_no_car", 0) / n for d in days]
    share["limited"] = [d.get("wtt_limited", 0) / n for d in days]
    forced = [d.get("calls", {}).get("forced", 0) / n for d in days]
    early = [d.get("early_shift", 0) / n for d in days]            # commuters working the early day (car or PT)
    early_car = [d.get("early_shift_cars", 0) / max(d["cars"], 1) for d in days]   # share of that day's car users
    m = {
        "base_car": float(np.mean(share["cars"][5:10])),
        "base_pt": float(np.mean(share["pt"][5:10])),
        "base_wfh": float(np.mean(share["wfh"][5:10])),
        "change_21_30": chg(21, 30),
        "change_11_13": chg(11, 13),
        "change_by_day": [float(x / pre - 1.0) for x in cr],
        "crossings_by_day": [int(x) for x in cr],
        "share_by_day": {k: [round(x, 4) for x in v] for k, v in share.items()},
        "end_car": float(np.mean(share["cars"][20:30])),
        "end_pt": float(np.mean(share["pt"][20:30])),
        "end_wfh": float(np.mean(share["wfh"][20:30])),
        "wtt_no_car_11_13": float(np.mean(share["no_car"][10:13])),
        "end_wtt_no_car": float(np.mean(share["no_car"][20:30])),
        "end_wtt_limited": float(np.mean(share["limited"][20:30])),
        "end_forced": float(np.mean(forced[20:30])),
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
        # peak 15-min delay, car-weighted over corridors: the gate queue only, and queue + road delay
        # (the capacity calibration target with engine.calib_delay = "total"); mean road delay of cars
        "peak_delay_6_10": float(np.mean([d["peak_bin_delay_wmean"] for d in days[5:10]])),
        "peak_delay_21_30": float(np.mean([d["peak_bin_delay_wmean"] for d in days[20:30]])),
        "peak_total_delay_6_10": float(np.mean([d["peak_bin_total_delay_wmean"] for d in days[5:10]])),
        "peak_total_delay_21_30": float(np.mean([d["peak_bin_total_delay_wmean"] for d in days[20:30]])),
        "road_delay_6_10": float(np.mean([d["mean_road_delay"] for d in days[5:10]])),
        "road_delay_21_30": float(np.mean([d["mean_road_delay"] for d in days[20:30]])),
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


def _calib_record(rec: dict) -> dict:
    """The part of a cordonlite.run.calibrate record that the log keeps per evaluation."""
    return {"capacity_scale": float(rec["capacity_scale"]), "achieved_peak_delay_min": rec["achieved_peak_delay_min"],
            "calib_delay": rec["calib_delay"], "road": rec["road"],
            "status": rec["status"], "n_probes": len(rec["history"])}


def _run_overrides(job: dict) -> dict[str, Any]:
    return {"run.arm": "R-daily", "run.seed": int(job["seed"]), "run.n_agents": N_AGENTS,
            "run.n_days": N_DAYS, **job["overrides"]}


def capacity(job: dict) -> dict:
    """Nested capacity calibration of one (PAP, k_WFH, seed) of the search (job: key, overrides, seed). The
    calibration runs without the charge, where the willingness to pay removes no option, so the record holds
    for every beta0 of the pair (evaluate takes it as job["calibration"] with job["scale"] = its scale)."""
    from cordonlite.config import load_config
    from cordonlite.run import calibrate

    t0 = time.perf_counter()
    rec = calibrate(load_config(overrides=_run_overrides(job)), progress=False)
    return {"key": job["key"], "seed": int(job["seed"]), "calibration": _calib_record(rec),
            "seconds": round(time.perf_counter() - t0, 1)}


def evaluate(job: dict) -> dict:
    """One (overrides, seed) evaluation. job: label, overrides, seed, scale ('calibrate' or float; with a
    float, an optional calibration record of a shared calibration, see capacity), nofee (also run a
    no-charge counterfactual at the same capacity), agents (return agent rows)."""
    from cordonlite.config import load_config
    from cordonlite.run import calibrate, simulate

    t0 = time.perf_counter()
    cfg = load_config(overrides=_run_overrides(job))
    calib = job.get("calibration")
    scale = job["scale"]
    if scale == "calibrate":
        calib = _calib_record(calibrate(cfg, progress=False))
        scale = calib["capacity_scale"]
    with tempfile.TemporaryDirectory(prefix="cl_bcal_") as tmp:
        res = simulate(cfg, Path(tmp), float(scale), engine_kind="py")
    row = {"label": job["label"], "seed": int(job["seed"]), "capacity_scale": float(scale),
           "calibration": calib, **job.get("meta", {}), **metrics(res, N_AGENTS)}
    paying = [float(p.fuel_cost) for p in res.personas if not p.company_car]
    row["fuel_mean_paying"] = float(np.mean(paying)) if paying else 0.0
    row["fuel_p10_p90_paying"] = [float(np.percentile(paying, 10)), float(np.percentile(paying, 90))] if paying else [0.0, 0.0]
    if job.get("agents"):
        row["agents"] = agent_frame(res, cfg.persona.n_twins, int(cfg.costs.early_start_min))
    row["early_ok_share"] = float(np.mean([bool(p.early_shift_ok and p.tstar_min > cfg.costs.early_start_min)
                                           for p in res.personas]))
    # willingness to pay: commuters it can limit (no company car, PT or WFH available) and those among all
    # commuters whose WTP is below the NZ$ peak charge
    peak = float(cfg.fees.peak_fee)
    limitable = [p for p in res.personas if not p.company_car and (p.pt_allowed or p.wfh_allowed)]
    row["wtt_limitable_share"] = len(limitable) / len(res.personas)
    row["wtp_below_peak_share"] = float(np.mean([p.wtp_fee < peak for p in res.personas]))
    row["wtp_below_peak_limitable_share"] = float(np.mean([p.wtp_fee < peak for p in limitable])) if limitable else 0.0
    if job.get("nofee"):
        cfg0 = dataclasses.replace(cfg, fees=dataclasses.replace(cfg.fees, regime="none"))
        with tempfile.TemporaryDirectory(prefix="cl_bcal0_") as tmp:
            res0 = simulate(cfg0, Path(tmp), float(scale), engine_kind="py")
        m0 = metrics(res0, N_AGENTS)
        row["nofee"] = {k: m0[k] for k in ("crossings_by_day", "peak_band_share_21_30", "shoulder_share_21_30",
                                           "exit_hist_21_30", "end_car", "base_car", "end_pt", "base_pt",
                                           "end_wfh", "base_wfh", "change_by_day", "change_21_30",
                                           "end_wtt_no_car", "base_early", "end_early", "base_early_of_cars",
                                           "end_early_of_cars", "early_by_day", "peak_cross_change",
                                           "pre0730_cross_change", "peak_cross_6_10", "peak_cross_21_30")}
        if job.get("agents"):
            row["nofee"]["agents"] = agent_frame(res0, cfg.persona.n_twins, int(cfg.costs.early_start_min))
    row["seconds"] = round(time.perf_counter() - t0, 1)
    return row


def task(job: dict) -> dict:
    """Process-pool entry of the search: a shared capacity calibration (job["kind"] == "capacity") or an
    evaluation."""
    return capacity(job) if job.get("kind") == "capacity" else evaluate(job)


def cal_key(pap: float, wfh: float, seed: int) -> str:
    return f"pap{pap:g}_wfh{wfh:g}_s{int(seed)}"


class Checkpoint:
    """Calibrations and runs of the search so far, in the system temp folder, so that an interrupted
    --stage search (or all) resumes where it stopped. It is used only while the model (config.toml apart
    from the three searched scalars), n, the seeds and the search design are unchanged, and is deleted
    once the search log is written."""

    PATH = Path(tempfile.gettempdir()) / "cordonlite_behaviour_search_checkpoint.json"

    def __init__(self) -> None:
        import hashlib

        base = load_config(overrides={"costs.pt_attitude_penalty": 0.0, "costs.wfh_cost": 0.0, "wtt.beta0": 0.0})
        sig = repr((base, N_AGENTS, N_DAYS, SEEDS, STRUCTURAL, PARK_FIXED, SEARCH_DESIGN, BETA0_STAGE1, STAGE1,
                    STAGE1_CORNERS, BEFORE, V3_SCALARS))
        self.signature = hashlib.sha256(sig.encode("utf-8")).hexdigest()
        self.cal: dict[str, dict] = {}
        self.rows: dict[str, dict] = {}
        if self.PATH.exists():
            old = json.loads(self.PATH.read_text(encoding="utf-8"))
            if old.get("signature") == self.signature:
                self.cal, self.rows = old["cal"], old["rows"]
                print(f"resuming from {self.PATH}: {len(self.cal)} calibrations, {len(self.rows)} runs", flush=True)

    def row(self, label: str, seed: int) -> dict | None:
        return self.rows.get(f"{label}|{int(seed)}")

    def add_row(self, r: dict) -> None:
        self.rows[f"{r['label']}|{int(r['seed'])}"] = r

    def rows_labelled(self, label: str) -> list[dict]:
        return [r for r in self.rows.values() if r["label"] == label]

    def save(self) -> None:
        tmp = self.PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps({"signature": self.signature, "cal": self.cal, "rows": self.rows}), encoding="utf-8")
        tmp.replace(self.PATH)

    def clear(self) -> None:
        self.PATH.unlink(missing_ok=True)


def run_jobs(jobs: list[dict], workers: int, desc: str, fn=evaluate, on_result=None) -> list[dict]:
    """fn over jobs in a process pool, results in job order; on_result(row) is called as each arrives."""
    t0 = time.perf_counter()
    out: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, r in enumerate(ex.map(fn, jobs), 1):
            out.append(r)
            if on_result is not None:
                on_result(r)
            if i % max(1, len(jobs) // 10) == 0 or i == len(jobs):
                print(f"  {desc}: {i}/{len(jobs)} [{time.perf_counter() - t0:.0f}s]", flush=True)
    return out


# ----------------------------------------------------------------------------- selection

# base_skip and end_skip were dropped with SKIP (2026-10-09); the archived logs still hold them
SUMMARY_KEYS = ("base_car", "base_pt", "base_wfh", "change_21_30", "change_11_13",
                "peak_band_share_6_10", "peak_band_share_21_30", "end_car", "end_pt", "end_wfh",
                "capacity_scale", "peak_delay_6_10", "peak_delay_21_30",
                "peak_total_delay_6_10", "peak_total_delay_21_30", "road_delay_6_10", "road_delay_21_30",
                "base_early", "end_early", "base_early_of_cars", "end_early_of_cars",
                "peak_cross_change", "pre0730_cross_change",
                "wtt_no_car_11_13", "end_wtt_no_car", "end_wtt_limited", "end_forced", "wtp_below_peak_share")
LOSS_SCALE = {"base_car": 0.05, "base_pt": 0.035, "change_21_30": 0.04}


def summarise(rows: list[dict]) -> dict[str, float]:
    """3-seed means of SUMMARY_KEYS (a key missing from older logged rows, e.g. the road delays, is left out)."""
    return {k: float(np.mean([r[k] for r in rows])) for k in SUMMARY_KEYS if all(k in r for r in rows)}


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
    prior:  0.02 x sum of squared relative distances of the scalars from the design values (PAP,
            parking and k_WFH 8 [v3]; beta0 0.5 [SSC2026 base_beta]), a weak tie-break toward them.
    """
    m = summarise(rows)
    centre = sum(((m[k] - TARGETS[k]["centre"]) / s) ** 2 for k, s in LOSS_SCALE.items())
    band = sum((band_excess(k, m[k]) / 0.02) ** 2 for k in TARGETS)
    band += sum((band_excess(k, r[k], SEED_TOL[k]) / 0.02) ** 2 for r in rows for k in TARGETS)
    prior = 0.02 * sum(((scalars[k] - V3_SCALARS[k]) / V3_SCALARS[k]) ** 2 for k in V3_SCALARS if k in scalars)
    return {"total": centre + band + prior, "centre": centre, "band": band, "prior": prior}


def feasible(rows: list[dict], mean: dict[str, float] | None = None) -> bool:
    """Every 3-seed mean inside its target band at the precision the targets are stated in (shares to
    2 decimals, changes to whole percent), and every seed within the stated single-seed tolerance."""
    m = mean or {k: float(np.mean([r[k] for r in rows])) for k in TARGETS}
    return (all(band_excess(k, round(m[k], 2)) == 0.0 for k in TARGETS)
            and all(band_excess(k, r[k], SEED_TOL[k]) == 0.0 for r in rows for k in TARGETS))


def anchor_distance(sc: dict[str, float]) -> float:
    """Squared relative distance to the anchors (a scalar missing from an archived point is left out)."""
    return float(sum(((sc[k] - ANCHORS[k]) / ANCHORS[k]) ** 2 for k in ANCHORS if k in sc))


SELECTION_DOC = ("lexicographic: (1) feasible = every 3-seed mean in its target band at the targets' stated "
                 "precision (shares to 2 decimals, changes to whole percent) and every seed within the stated "
                 "single-seed tolerance; (2) among feasible points, the smallest squared relative distance "
                 "to the anchors (PAP 8 [v3], paid parking 17 [AT car-park all-day rate 2014], k_WFH 8 [v3], "
                 "beta0 0.5 [SSC2026 base_beta]); (3) loss as tie-break. If no point is feasible, the lowest "
                 "loss. Points with beta0 = 0 (no willingness-to-pay limit) are references and are never "
                 "selected.")


def candidates(points: list[dict]) -> list[dict]:
    """The points the rule may choose: every point except the beta0 = 0 references."""
    return [p for p in points if not p.get("reference")]


def select(points: list[dict]) -> dict:
    cand = candidates(points)
    feas = [p for p in cand if p["feasible"]]
    if feas:
        return min(feas, key=lambda p: (round(anchor_distance(p["scalars"]), 9), p["loss"]["total"]))
    return min(cand, key=lambda p: p["loss"]["total"])


def ridge_alternatives(points: list[dict], chosen_label: str, n: int = N_RIDGE_ALTERNATIVES) -> list[dict]:
    """Alternatives checked out of sample (their scalars): non-feasible points nearest the anchors that
    become feasible when the soft overshoot bound is relaxed to -33% (the rule used since the search
    without fuel); filled up from the ten lowest-loss other points (nearest the anchors first) when fewer
    than n qualify. beta0 = 0 references are never alternatives."""
    points = candidates(points)
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
    return [dict(p["scalars"]) for p in out]


def selection_sensitivity(points: list[dict]) -> dict[str, Any]:
    """How the selection depends on rounding and on the soft overshoot bound (no new runs; beta0 = 0
    references left out)."""
    points = candidates(points)

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
        for key, mode in (("cars", "CAR"), ("pt", "PT"), ("wfh", "WFH")):
            arr = np.array([r["share_by_day"][key] for r in rows])
            ax.fill_between(days, arr.min(0), arr.max(0), color=MODE_COLOURS[mode], alpha=0.18, lw=0)
            ax.plot(days, arr.mean(0), color=MODE_COLOURS[mode], lw=2, label=mode)
            ax.annotate(mode, (days[-1], arr.mean(0)[-1]), xytext=(4, 0), textcoords="offset points",
                        color=INK2, va="center", fontsize=8)
        # commuters left without a car option by the willingness to pay (a subset of PT and WFH)
        arr = np.array([r["share_by_day"].get("no_car", [0.0] * N_DAYS) for r in rows])
        if arr.max() > 0:
            ax.plot(days, arr.mean(0), color=INK2, lw=1.2, ls="--", label="no car option (WTP below every charge)")
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
    paths["mode_shares"] = p.relative_to(ROOT).as_posix()

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
    paths["crossing_change"] = p.relative_to(ROOT).as_posix()

    # 3. crossing-time distribution, days 21-30, charged vs no-charge counterfactual (after)
    bins = np.arange(330, 660, 15)

    def mean_hist(dicts):   # keys are ints in memory and strings once read back from the JSON log (--stage report)
        return np.array([[float({int(k): v for k, v in d.items()}.get(int(b), 0.0)) for b in bins]
                         for d in dicts]).mean(0)

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
    paths["crossing_times"] = p.relative_to(ROOT).as_posix()

    # 4. search surface over the three free scalars: the responses over k_WFH x beta0 at the chosen PAP, and the
    # base shares (which do not depend on beta0) over k_WFH x PAP
    df = pd.DataFrame([{**g["scalars"], **g["mean"], "feasible": bool(g["feasible"])} for g in grid_rows])
    fig, axes = plt.subplots(2, 2, figsize=(14, 10.5), gridspec_kw={"width_ratios": [1.25, 1]})
    from matplotlib.patches import Rectangle

    def dist(key, v):   # distance shaded: to the centre where the target has one, else the band excess
        return abs(v - TARGETS[key]["centre"]) if TARGETS[key]["centre"] is not None else band_excess(key, v)

    at_pap = df[df["pap"] == chosen["pap"]]
    base = df.drop_duplicates(subset=["pap", "wfh"])   # the base shares are the same for every beta0 of a pair
    panels = ((axes[0, 0], at_pap, "beta0", "change_21_30", "crossings change d21-30 vs d6-10 (%)", "{:+.0f}", 0.25),
              (axes[0, 1], at_pap, "beta0", "change_11_13", "crossings change d11-13 vs d6-10 (%)", "{:+.0f}", 0.15),
              (axes[1, 0], base, "pap", "base_pt", "pre-charge PT share (days 6-10, %)", "{:.0f}", 0.15),
              (axes[1, 1], base, "pap", "base_car", "pre-charge car share (days 6-10, %)", "{:.0f}", 0.15))
    for ax, d, col, key, title, fmt, vmax in panels:
        piv = d.pivot(index="wfh", columns=col, values=key).sort_index(ascending=False)
        feas = d.pivot(index="wfh", columns=col, values="feasible").reindex_like(piv)
        ax.imshow(np.vectorize(lambda v: np.nan if pd.isna(v) else dist(key, v))(piv.to_numpy(dtype=float)),
                  cmap="Greys_r", aspect="auto", vmin=0, vmax=vmax)
        for i, wf in enumerate(piv.index):
            for j, c in enumerate(piv.columns):
                v = piv.loc[wf, c]
                if pd.isna(v):
                    continue
                here = wf == chosen["wfh"] and (c == chosen[col])
                ax.text(j, i, fmt.format(v * 100) + ("*" if here else ""), ha="center", va="center", fontsize=7,
                        color="#ffffff" if dist(key, v) < 0.4 * vmax else INK)
                fv = feas.loc[wf, c]
                if col == "beta0" and not pd.isna(fv) and bool(fv):   # dashed: a beta0 = 0 reference, never selected
                    ref = c == BETA0_REFERENCE
                    ax.add_patch(Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False, ec=INK2 if ref else SLOTS[0],
                                           lw=1.2 if ref else 1.6, ls="--" if ref else "-"))
        ax.set_xticks(range(len(piv.columns)), [f"{c:g}" for c in piv.columns])
        ax.set_yticks(range(len(piv.index)), [f"{c:g}" for c in piv.index])
        ax.set_xlabel("beta0 (wtt.beta0; 0 = no limit, reference)" if col == "beta0" else "PAP NZ$ (x omega(P))")
        ax.set_ylabel("k_WFH NZ$ (x phi(F))")
        ax.set_title(title + (f" at PAP {chosen['pap']:g}; outlined = feasible (dashed: reference)" if col == "beta0"
                              else "; the same for every beta0"), color=INK, fontsize=9)
    fig.suptitle(f"Search over PAP, k_WFH and beta0 (paid parking fixed at NZ${PARK_FIXED:g}; darker = closer to the "
                 "target centre or inside the band; * chosen; blank = not run)", color=INK, fontsize=10)
    fig.tight_layout()
    p = FIG_DIR / "calib_search.png"
    fig.savefig(p, dpi=200)
    plt.close(fig)
    paths["search"] = p.relative_to(ROOT).as_posix()
    return paths


# ----------------------------------------------------------------------------- report


def pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def calib_delay_words(res: dict) -> str:
    """What the capacity calibration measured (a log without calib_delay predates road congestion: queue)."""
    return "queue + road delay" if res.get("calib_delay", "queue") == "total" else "queue delay"


def road_words(res: dict) -> str:
    """The roads of a logged search (a log without "road" predates road congestion: free-flow roads)."""
    rd = res.get("road") or {}
    if not rd.get("enabled"):
        return "free-flow roads"
    return "congested roads" + (" with the motorway breakdown rule" if rd.get("mwy_breakdown") else "")


def state_words(res: dict) -> str:
    """'300 agents, free-flow roads' / '950 agents, congested roads with the motorway breakdown rule'."""
    return f"{int(res.get('n_agents', 300))} agents, {road_words(res)}"


def write_report(res: dict) -> None:
    ch = res["chosen"]["scalars"]
    tst = res["chosen"]["targets"]
    pf = res.get("pre_fuel") or {}
    wt = res.get("wtt") or {}
    lines = []
    A = lines.append
    A("# Behaviour calibration report")
    A("")
    A("Generated by `scripts/calibrate_behaviour.py` (data: `data/behaviour_calibration.json`). R-daily arm, "
      f"rule decider, PyEngine, n = {N_AGENTS}, 30 days, seeds 1-3 (held-out seeds 4-5 and, after the selection, "
      "unseen seeds 6-12 for checking only). "
      "The LLM arms are never calibrated. Capacity is recalibrated per seed and per evaluated (PAP, k_WFH) pair "
      f"with `cordonlite.run.calibrate` (car-weighted peak 15-min {calib_delay_words(res)} of "
      f"{res.get('calib_target_peak_delay_min', 15.0):g} min, days 6-10, no charge). Roads: "
      + ("free flow (no road congestion)." if not (res.get("road") or {}).get("enabled") else
         f"{road_words(res)} (`[road]` of config.toml, capacity k = {res['road'].get('k')} x directional ADT "
         "from data/road_meta.json; fixed inputs, not searched).")
      + f" Behaviour is calibrated at the NZ${wt.get('peak_fee', 6.0):g} peak of the ToU schedule (`fees.peak_fee`); "
        "runs at other peaks (`--peak-fee`) extrapolate from it.")
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
      f"TR-A 75:134-146). Single-seed tolerance at n = {N_AGENTS}: {tolerance_words(SEED_TOL)} "
      "(±0.05 and ±4 pp at n = 300, x sqrt(300 / n)). The SKIP-share target (at most 0.02) went with SKIP on "
      "2026-10-09; every other target is unchanged.")
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
    lst = res.get("last") or {}          # the latest archived state (LAST_JSON: SKIP, no willingness to travel)
    ff = res.get("freeflow300") or {}    # the state with 300 agents and free-flow roads (FREEFLOW_JSON)
    sk25 = res.get("skip25") or {}       # the state with SKIP cost NZ$25 and no early start (SKIP25_JSON)
    es = res.get("early_start_summary")
    ea = res.get("early_start", {})
    vref = wt.get("vot_ref_value", 9.97)
    peak = wt.get("peak_fee", 6.0)
    A("## SKIP removed and the willingness to travel (2026-10-09)")
    A("")
    A("Two author decisions of 2026-10-09 change the choice set. **SKIP is removed.** Postponing the day had become a "
      "permanent choice rather than a one-day postponement: at a NZ$30 peak, 97 of R-clock's 102 skippers skipped "
      "every one of days 21-30, and at NZ$6, 8 commuters skipped every day; in the rule arms every skipper could have "
      "taken PT. Every commuter now chooses among CAR (a departure time), PT and WFH where allowed, and the SKIP-share "
      "target is dropped. **The willingness to travel follows an exponential decay**, after the SSC2026 model "
      "(akl_pricing.nls: p_enter = clip(base_trip_rate x exp(-beta x fee / VoT), 0.05, 0.95), beta = clip(base_beta x "
      "median VoT / VoT, 0.1, 2.0), base_beta 0.5). Each commuter draws u ~ U(0, 1) once (Layer A, after every other "
      "draw; twins copy it) and has a fixed most it would pay a day to drive into the city centre, WTP = -ln(u) x VoT / "
      f"beta, with beta = clip(beta0 x VoT_ref / VoT, {wt.get('beta_clip', [0.1, 2.0])[0]:g}, "
      f"{wt.get('beta_clip', [0.1, 2.0])[1]:g}) and VoT_ref = exp(vot_mu) = NZ${vref:.2f}/h (`wtt.vot_ref = "
      f"\"{wt.get('vot_ref', 'distribution_median')}\"`, the median of the VoT distribution; SSC2026 used the sample "
      "median). The share willing to pay a charge F is then exp(-beta F / VoT). On a charged day a car option whose "
      "charge (the fee at its expected crossing) is above WTP is not offered, so cheaper shoulder departures stay "
      "(retiming) and a commuter unwilling to pay any of them takes PT or works from home; one left with PT only is "
      "'forced' (no decision is asked). Company cars (the employer pays) and commuters with neither PT nor WFH (an "
      "essential trip) are exempt. It applies in every arm as a choice-set constraint, and not on uncharged days, so "
      "days 1-10, the base shares and the capacity calibration do not depend on beta0. beta0 is searched next to PAP "
      "and k_WFH, with SSC2026's 0.5 as its anchor; beta0 = 0 switches the limit off and is run only as a reference. "
      f"Because of the lower clip, beta is at least {wt.get('beta_clip', [0.1, 2.0])[0]:g} for every commuter, so "
      "any positive beta0 removes some car options: below beta0 = 0.1 only commuters with a VoT under "
      "VoT_ref x beta0 / 0.1 have a beta above the floor.")
    A("")
    if es:
        A("Willingness to pay at the chosen point (R-daily; shares of all commuters; 'limitable' excludes company cars "
          "and commuters with neither PT nor WFH):")
        A("")
        A(f"| Seed | limitable | WTP below NZ${peak:g} (all) | same, limitable | no car option d11-13 | no car option "
          "d21-30 | some car options removed d21-30 | forced onto PT d21-30 |")
        A("|---|---|---|---|---|---|---|---|")

        def wtt_row(lab, x):
            A(f"| {lab} | {x['wtt_limitable_share']:.3f} | {x['wtp_below_peak_share']:.3f} | "
              f"{x['wtp_below_peak_limitable_share']:.3f} | {x['wtt_no_car_11_13']:.3f} | {x['end_wtt_no_car']:.3f} | "
              f"{x['end_wtt_limited']:.3f} | {x['end_forced']:.3f} |")
        for x in es["per_seed"]:
            wtt_row(f"{x['seed']}" + (" (held out)" if x["seed"] in HOLDOUT_SEEDS else ""), x)
        wtt_row("mean 1-3", es["mean_1_3"])
        A("")
        m_ = es["mean_1_3"]
        b0 = ch["beta0"]
        lo_, hi_ = wt.get("beta_clip", [0.1, 2.0])
        bm = min(max(b0, lo_), hi_)   # beta of a commuter with VoT = VoT_ref
        A(f"At beta0 = {b0:g} a commuter with the median VoT (NZ${vref:.2f}/h) would pay the NZ${peak:g} peak with "
          f"probability exp(-{bm:g} x {peak:g} / {vref:.2f}) = {math.exp(-bm * peak / vref):.2f} "
          f"and the NZ$4 shoulder with probability {math.exp(-bm * 4 / vref):.2f}. On days 21-30 "
          f"{m_['end_wtt_no_car']:.1%} of all commuters have no car option left and {m_['end_wtt_limited']:.1%} have at "
          f"least one removed (seeds 1-3); {m_['wtp_below_peak_share']:.1%} have a WTP below the peak charge, exempt "
          "ones included.")
        A("")
    A("## Early start (2026-10-05)")
    A("")
    A("A commuter whose employer allows it (Layer A constraint `early_shift_ok`, probability by archetype "
      f"{ea.get('early_shift_prob')} for hybrid office, on-site office, shift/service, trades/work vehicle and "
      f"tertiary student [A]) may start work at {ea.get('early_start_min', 420) // 60:02d}:{ea.get('early_start_min', 420) % 60:02d} "
      "instead of the usual start t* (07:00 to 15:00 [A, author: employers encourage it]). Every car and PT option of "
      "such a commuter is measured against the cheaper of the two starts: schedule delay against t*, or schedule delay "
      f"against the early start plus NZ${ea.get('early_shift_cost', 3):g} x phi(F) a day [A]. The car departures around "
      f"the reference departure of each start (+/- {max(ea.get('anchor_offsets_min', [0, 15]))} min) are added to the "
      "standing +/- 60 min set. Early and late minutes, lateness for T3 and the stored outcome use the start the "
      "chosen option implies. The LLM prompt states the permission and shows the start time of every option. It is a "
      "fixed assumption and is not searched.")
    A("")
    if es:
        A("Early start, retiming and peak spreading at the chosen point (R-daily; 'no charge' is the run without the "
          "charge at the same capacity and seed, which has the same day-to-day churn):")
        A("")
        A("| Seed | may start early | early start d6-10 | d11-13 | d21-30 | d21-30, no charge | "
          "retimed (of all commuters) | same, no charge | crossings d21-30 vs d6-10, all morning | 08:00-09:00 | "
          "before 07:30 | 08:00-09:00, no charge |")
        A("|---|---|---|---|---|---|---|---|---|---|---|---|")

        def es_row(lab, x):
            rt_, rt0 = x.get("retiming"), x.get("nofee_retiming")
            A(f"| {lab} | {x['early_ok_share']:.3f} | {x['base_early']:.3f} | {x['early_11_13']:.3f} | {x['end_early']:.3f} | "
              f"{x['nofee_end_early']:.3f} | "
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
          f"against {m_['nofee_retiming']['retimed_of_all']:.1%} without the charge. Car crossings change by "
          f"{pct(m_['change_21_30'])} over the whole morning and by {pct(m_['peak_cross_change'])} in the 08:00 to 09:00 "
          f"peak (NZ$6), against {pct(m_['pre0730_cross_change'])} before 07:30 (NZ$4); without the charge the peak "
          f"changes by {pct(m_['nofee_peak_cross_change'])} over the same days.")
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
    A("The search runs over three scalars, PAP, k_WFH and beta0, with the same targets (less the SKIP share), "
      "seeds, loss and selection rule; the anchors and the prior gain beta0 0.5. Earlier searches are archived: "
      "`data/behaviour_calibration_pre_fuel.json` with `docs/calibration_report_pre_fuel.md` (no fuel, three "
      "scalars), `data/behaviour_calibration_fuel023_park11.json` with `docs/calibration_report_fuel023_park11.md` "
      "(fuel NZ$0.23/km, three scalars), `data/behaviour_calibration_skip25_noearly.json` with "
      "`docs/calibration_report_skip25_noearly.md` (SKIP cost NZ$25, no early start, two scalars)"
      + (f", `{ff['source']}` with `{ff['report']}` (SKIP cost NZ${ff['skip_cost']:g} and early start, "
         f"{state_words(ff)}, capacity calibrated to the {calib_delay_words(ff)}, two scalars)" if ff else "")
      + (f" and `{lst['source']}` with `{lst['report']}` (SKIP cost NZ${lst['skip_cost']:g}, no willingness to travel, "
         f"{state_words(lst)}, capacity calibrated to the {calib_delay_words(lst)}, two scalars), each with its "
         "capacity calibration, figures and example prompt." if lst else "."))
    A("")
    if pf and prv and sk25 and ff and lst:
        c0, m0 = pf["chosen"], pf["chosen_mean"]
        c1, m1 = prv["chosen"], prv["chosen_mean"]
        c2, m2 = sk25["chosen"], sk25["chosen_mean"]
        c3, m3 = ff["chosen"], ff["chosen_mean"]
        c4, m4 = lst["chosen"], lst["chosen_mean"]
        e3 = ff.get("on_grid_edge") or on_grid_edge(c3)
        e4 = lst.get("on_grid_edge") or on_grid_edge(c4)
        old = (pf, prv, sk25, ff, lst)   # the archived logs before road congestion record n_agents but no road / calib_delay
        A("| | Without fuel (archived) | Fuel NZ$0.23/km, parking searched (archived) | Fuel NZ$0.30/km, parking fixed, "
          f"SKIP NZ$25, no early start (archived) | SKIP NZ${ff['skip_cost']:g} and early start, {state_words(ff)} "
          f"(archived) | SKIP NZ${lst['skip_cost']:g}, {state_words(lst)} (archived) | no SKIP, willingness to travel, "
          f"{state_words(res)} (this report) |")
        A("|---|---|---|---|---|---|---|")
        A("| Agents (n) | " + " | ".join(f"{int(x.get('n_agents', 300))}" for x in old) + f" | {N_AGENTS} |")
        A("| Roads | " + " | ".join(road_words(x) for x in old) + f" | {road_words(res)} |")
        A("| Capacity calibrated to (car-weighted peak 15-min delay) | " + " | ".join(calib_delay_words(x) for x in old)
          + f" | {calib_delay_words(res)} |")
        A(f"| Fuel cost | none | NZ$0.23/km, fixed | NZ$0.30/km, fixed | NZ${ff['fuel_cost_per_km']:.2f}/km, fixed | "
          f"NZ${lst['fuel_cost_per_km']:.2f}/km, fixed | NZ${fu['fuel_cost_per_km']:.2f}/km, fixed |")
        A(f"| Paid parking, office (student) | NZ${c0['park']:g} (NZ${0.75 * c0['park']:g}), searched | "
          f"NZ${c1['park']:g} (NZ${0.75 * c1['park']:g}), searched | NZ${c2['park']:g} (NZ${0.75 * c2['park']:g}), fixed | "
          f"NZ${c3['park']:g} (NZ${0.75 * c3['park']:g}), fixed | NZ${c4['park']:g} (NZ${0.75 * c4['park']:g}), fixed | "
          f"NZ${ch['park']:g} (NZ${0.75 * ch['park']:g}), fixed |")
        A(f"| SKIP option (cost plus 1 h of VoT) | NZ$25 | NZ$25 | NZ$25 | NZ${ff['skip_cost']:g} | NZ${lst['skip_cost']:g} | "
          "removed |")
        A("| Early-start option | no | no | no | yes | yes | yes |")
        A(f"| Willingness to travel (beta0) | no | no | no | no | no | {ch['beta0']:g}, searched |")
        A("| Searched scalars | PAP, parking, k_WFH | PAP, parking, k_WFH | PAP, k_WFH | PAP, k_WFH | PAP, k_WFH | "
          "PAP, k_WFH, beta0 |")
        e_ = on_grid_edge(ch, res["search"].get("beta0_values"))
        A(f"| PAP (x omega(P)) | NZ${c0['pap']:g} | NZ${c1['pap']:g} (grid edge) | NZ${c2['pap']:g} (interior) | "
          f"NZ${c3['pap']:g} ({'grid edge' if e3['pap'] else 'interior'}) | "
          f"NZ${c4['pap']:g} ({'grid edge' if e4['pap'] else 'interior'}) | "
          f"NZ${ch['pap']:g} ({'grid edge' if e_['pap'] else 'interior'}) |")
        A(f"| k_WFH (x phi(F)) | NZ${c0['wfh']:g} (grid edge) | NZ${c1['wfh']:g} (grid edge) | NZ${c2['wfh']:g} (interior) | "
          f"NZ${c3['wfh']:g} ({'grid edge' if e3['wfh'] else 'interior'}) | "
          f"NZ${c4['wfh']:g} ({'grid edge' if e4['wfh'] else 'interior'}) | "
          f"NZ${ch['wfh']:g} ({'grid edge' if e_['wfh'] else 'interior'}) |")
        cand_ = candidates(res["search"]["points"])
        A(f"| Feasible points | {pf['n_feasible']} of {pf['n_points']} (after rounding) | {prv['n_feasible']} of "
          f"{prv['n_points']} | {sk25['n_feasible']} of {sk25['n_points']} | {ff['n_feasible']} of {ff['n_points']} | "
          f"{lst['n_feasible']} of {lst['n_points']} | {sum(p['feasible'] for p in cand_)} of {len(cand_)} |")
        for k, lab in (("base_car", "Car share d6-10 (0.75-0.85)"), ("base_pt", "PT share d6-10 (0.08-0.15)"),
                       ("base_wfh", "WFH share d6-10 (at most 0.10)")):
            A(f"| {lab} | {m0[k]:.3f} | {m1[k]:.3f} | {m2[k]:.3f} | {m3[k]:.3f} | {m4[k]:.3f} | {cm_[k]:.3f} |")
        A(f"| SKIP share d6-10 (at most 0.02 while SKIP existed) | {m0['base_skip']:.3f} | {m1['base_skip']:.3f} | "
          f"{m2['base_skip']:.3f} | {m3['base_skip']:.3f} | {m4['base_skip']:.3f} | - |")
        for k, lab in (("change_11_13", "Crossings d11-13 vs d6-10 (to about -30%)"),
                       ("change_21_30", "Crossings d21-30 vs d6-10 (-12% to -22%)")):
            A(f"| {lab} | {pct(m0[k])} | {pct(m1[k])} | {pct(m2[k])} | {pct(m3[k])} | {pct(m4[k])} | {pct(cm_[k])} |")
        A(f"| Capacity scale (mean of seeds 1-3) | {m0['capacity_scale']:.3f} | {m1['capacity_scale']:.3f} | "
          f"{m2['capacity_scale']:.3f} | {m3['capacity_scale']:.3f} | {m4['capacity_scale']:.3f} | "
          f"{cm_['capacity_scale']:.3f} |")
        A("")
        A("With parking at NZ$17 and fuel at NZ$0.30/km a paying driver's money cost is about NZ$"
          f"{ch['park'] + (np.mean(fm) if fm else 8.6):.0f} a day before any charge (parking plus fuel), against about "
          "NZ$18 in the two earliest states, so PAP is far higher than in those states: it is the one scalar that "
          "holds the assumed pre-charge shares. The last archived state and this report share the rule, the fixed "
          "inputs, the number of agents, the roads, the capacity target, the grid of PAP and k_WFH, the seeds, the "
          "loss and the selection rule; they differ in the choice set (SKIP at NZ$"
          f"{lst['skip_cost']:g} there, removed here) and in the willingness to travel (none there, beta0 searched "
          f"here). The SKIP share was {m4['base_skip']:.3f} before the charge in the last archived state, so the base "
          "shares hardly move without it.")
        A("")
    A("## Search")
    A("")
    g = res["search"]
    cand = candidates(g["points"])
    refs = [p for p in g["points"] if p.get("reference")]
    stg = g.get("stages", {})
    A(f"{len(cand)} points (PAP x k_WFH x beta0) and {len(refs)} beta0 = 0 references, seeds 1-3: "
      f"{g.get('n_calibrations', 0):,} capacity calibrations and {g.get('n_runs', 0):,} charged 30-day runs, in "
      f"{g.get('wall_seconds', 0) / 3600:.1f} hours on {g.get('workers', '?')} workers. "
      + g["method"][:1].upper() + g["method"][1:])
    A("")
    if stg:
        A("| Stage | PAP | k_WFH | beta0 | (PAP, k_WFH) pairs | capacity calibrations | charged runs | hours |")
        A("|---|---|---|---|---|---|---|---|")
        for name, s_ in stg.items():
            prs = s_["pairs"]
            paps_ = sorted({p for p, _ in prs})
            wfhs_ = sorted({w for _, w in prs})
            A(f"| {name} | {', '.join(f'{x:g}' for x in paps_)} | "
              + (f"{wfhs_[0]:g}-{wfhs_[-1]:g}" if len(wfhs_) == 15 else ", ".join(f"{x:g}" for x in wfhs_))
              + f" | {', '.join(f'{x:g}' for x in s_['beta0'])} | {len(prs)} | {s_['n_calibrations']} | {s_['n_runs']} | "
              f"{s_['seconds'] / 3600:.2f} |")
        A("")
        A("Stage 1 includes the four corners of the NZ$1 grid (PAP 10 and 36 x k_WFH 2 and 16). "
          + (f"Stage 2 ran at PAP {', '.join(f'{x:g}' for x in stg['stage2'].get('paps', []))}. " if "stage2" in stg else "")
          + (f"After stage 2 the rule chose {stg['stage3'].get('chosen_after_stage2')}; stage 3 added beta0 "
             f"{', '.join(f'{x:g}' for x in stg['stage3']['beta0'])}." if "stage3" in stg else ""))
        A("")
    A(f"Selection: {g['selection']} Loss: {g['loss_doc']} Paid parking is constant, so its terms in the anchor "
      "distance (0) and in the prior (a constant) do not affect the ranking. The PAP and k_WFH ranges are those of the "
      "earlier searches (set after a range-finding probe with PAP 12 to 40 in steps of 4 at k_WFH 8 and 12; 300 "
      "agents, free-flow roads, SKIP cost NZ$25, no early start; logged as `search.range_probe` and not rerun).")
    A("")
    nf = sum(p["feasible"] for p in cand)
    ss = res["selection_sensitivity"]
    cpt = next(p for p in g["points"] if p["label"] == res["chosen"]["label"])
    cmean = res["chosen"].get("mean") or cpt["mean"]
    crow = res["chosen"].get("per_seed") or cpt["per_seed"]
    missed = [k for k in TARGETS if band_excess(k, round(cmean[k], 2)) > 0]
    fv = lambda k, v: pct(v) if k.startswith("change") else format(v, ".3f")
    seed_miss = [(r["seed"], k, r[k], band_excess(k, r[k], SEED_TOL[k])) for r in crow for k in TARGETS
                 if band_excess(k, r[k], SEED_TOL[k]) > 0]
    edge = on_grid_edge(res["chosen"]["scalars"], g.get("beta0_values"))
    txt = (f"{nf} of {len(cand)} points are feasible at the stated precision (shares to 2 decimals, changes "
           f"to whole percent); strictly (unrounded 3-seed means) {len(ss['feasible_strict'])} are. ")
    if nf == 0:
        txt += (f"NO POINT IS FEASIBLE. With no feasible point the rule falls back to the lowest loss, which gives "
                f"{ss['lowest_loss']}. "
                + ("At the stated precision the 3-seed means of the chosen point miss "
                   + ", ".join(f"`{k}` ({fv(k, cmean[k])})" for k in missed) + ". " if missed else
                   "Every 3-seed mean of the chosen point is inside its band. ")
                + ("The point is not feasible because of the single-seed rule: "
                   + "; ".join(f"seed {sd} `{k}` {fv(k, v)} (beyond the band plus tolerance by "
                               + (f"{ex * 100:.1f} pp" if k.startswith("change") else f"{ex:.3f}") + ")"
                               for sd, k, v, ex in seed_miss) + ". " if seed_miss else ""))
    else:
        txt += f"The chosen point is {res['chosen']['label']}; the lowest-loss point is {ss['lowest_loss']}. "
    txt += ("No chosen value is on an edge of its searched range." if not any(edge.values()) else
            "On an edge of the searched range: " + ", ".join(k for k, v in edge.items() if v) + ".")
    A(txt)
    A("")
    A("Sensitivity to the soft overshoot bound ('may reach about -30%', treated as a hard bound): "
      + "; ".join(f"bound {pct(x['lo'])}: {len(x['feasible'])} feasible, chosen {x['chosen']}" for x in ss["overshoot_bound"])
      + ". The anchors (PAP 8, k_WFH 8, beta0 0.5) act only inside a feasible set.")
    A("")
    hist = g.get("selection_history", [])
    if hist:
        A("Selection history (append-only from this version; `search.selection_history`): "
          + " ".join(h.get("note") or f"{h['replaced_at']}: replaced rule choosing {h['chosen']}." for h in hist))
        A("")
    A("Feasible points and the ten lowest-loss other points (3-seed means; 'no car' is the share of commuters with every "
      "car option removed by the willingness to pay, days 21-30):")
    A("")
    A("| PAP | k_WFH | beta0 | stage | feasible | anchor dist. | loss | base car | base PT | base WFH | no car d21-30 | "
      "d11-13 | d21-30 |")
    A("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    show = [p for p in cand if p["feasible"]]
    show += [p for p in sorted(cand, key=lambda q: q["loss"]["total"])[:10] if not p["feasible"]]

    def point_row(p):
        s, m = p["scalars"], p["mean"]
        return (f"| {s['pap']:g} | {s['wfh']:g} | {s['beta0']:g} | {str(p.get('stage', '-')).removeprefix('stage')} | "
                f"{'yes' if p['feasible'] else 'no'} | {p['anchor_distance']:.3f} | {p['loss']['total']:.2f} | "
                f"{m['base_car']:.3f} | {m['base_pt']:.3f} | {m['base_wfh']:.3f} | {m.get('end_wtt_no_car', 0.0):.3f} | "
                f"{pct(m['change_11_13'])} | {pct(m['change_21_30'])} |")
    for p in sorted(show, key=lambda q: (not q["feasible"], q["anchor_distance"], q["loss"]["total"])):
        A(point_row(p))
    A("")
    ref_here = sorted((p for p in refs if p["scalars"]["pap"] == ch["pap"]), key=lambda q: q["scalars"]["wfh"])
    if ref_here:
        A(f"References (beta0 = 0, no limit: SKIP removed and nothing else) at PAP {ch['pap']:g}, d21-30 response by "
          "k_WFH: " + ", ".join(f"{p['scalars']['wfh']:g}: {pct(p['mean']['change_21_30'])} "
                                 f"({pct(p['mean']['change_11_13'])} on d11-13)" for p in ref_here) + ".")
        A("")
    A(f"Chosen: **PAP NZ${ch['pap']:g} x omega(P), k_WFH NZ${ch['wfh']:g} x phi(F), beta0 {ch['beta0']:g}**, with paid "
      f"parking fixed at NZ${ch['park']:g}/day (student NZ${0.75 * ch['park']:g}) and fuel fixed at "
      f"NZ${fu['fuel_cost_per_km']:.2f}/km." + ("" if res["chosen"].get("feasible", cpt["feasible"]) else
                                                 " **This point is not feasible** (see above)."))
    A("")
    A("How to read the chosen values. PAP enters in the specification form omega(P) x (VoT/60 x T_pt + PAP) + fare: "
      "omega also scales PT time, and v3's HTA/2 factor is absent. v3 6.2 uses omega(P) x PAP x HTA/2 (HTA 1 local, "
      f"2 boundary) with PAP 8 swept {{4, 8, 12}}, so Cordon-Lite's {ch['pap']:g} x omega equals v3 PAP {ch['pap']:g} "
      f"(boundary homes) to {2 * ch['pap']:g} (local homes), far above v3's range; P = 1-2 agents also face doubled "
      "or 1.5 x PT time and practically never ride PT. PAP is the one scalar left to hold the assumed baseline "
      "split, so it absorbs the whole rise in the money cost of driving: it is a fitted residual, not an estimate "
      f"of a PT attitude. k_WFH {ch['wfh']:g} is "
      + ("above" if ch["wfh"] > V3_SCALARS["wfh"] else "equal to" if ch["wfh"] == V3_SCALARS["wfh"] else "below")
      + f" v3's NZ${V3_SCALARS['wfh']:g}; it is identified here by the response and overshoot "
      "targets (a higher value weakens both), not by the WFH share, which stays near zero. beta0 "
      f"{ch['beta0']:g} is " + ("below" if ch["beta0"] < 0.5 else "equal to" if ch["beta0"] == 0.5 else "above")
      + " SSC2026's base_beta 0.5. It does not move the base shares and is identified, together with k_WFH, by the "
      "response and overshoot: both strengthen the response, so the targets fix a ridge in (k_WFH, beta0) and the "
      "anchors pick the point on it. Parking and fuel are no longer fitted.")
    A("")
    A(f"![search]({Path(res['figures']['search']).relative_to('docs').as_posix()})")
    A("")
    A("## Before vs after (3-seed means)")
    A("")
    b, s_, a = res["before"]["mean"], res["structural_only"]["mean"], res["chosen"]["mean"]
    A("| Metric | Target | Before | Structural fixes only (design values) | After (chosen) |")
    A("|---|---|---|---|---|")
    for k, lab in (("base_car", "car share d6-10"), ("base_pt", "PT share d6-10"), ("base_wfh", "WFH share d6-10"),
                   ("change_11_13", "crossings d11-13 vs d6-10"), ("change_21_30", "crossings d21-30 vs d6-10")):
        t = TARGETS[k]
        f = pct if k.startswith("change") else (lambda v: f"{v:.3f}")
        band = f"{pct(t['lo'])} to {pct(t['hi'])}" if k.startswith("change") else f"{t['lo']:g}-{t['hi']:g}"
        A(f"| {lab} | {band} | {f(b[k])} | {f(s_[k])} | {f(a[k])} |")
    for k, lab in (("end_car", "car share d21-30"), ("end_pt", "PT share d21-30"), ("end_wfh", "WFH share d21-30"),
                   ("end_wtt_no_car", "no car option d21-30 (willingness to pay)"),
                   ("peak_band_share_21_30", "08:00-09:00 crossing share d21-30"),
                   ("peak_delay_6_10", "peak queue delay d6-10 (min)"),
                   ("peak_delay_21_30", "peak queue delay d21-30 (min)"),
                   ("peak_total_delay_6_10", "peak queue + road delay d6-10 (min)"),
                   ("peak_total_delay_21_30", "peak queue + road delay d21-30 (min)"),
                   ("road_delay_6_10", "mean road delay of cars d6-10 (min)"),
                   ("road_delay_21_30", "mean road delay of cars d21-30 (min)"),
                   ("capacity_scale", "capacity scale")):
        if k not in b or k not in s_ or k not in a:   # older logs have no road delays
            continue
        A(f"| {lab} | - | {b[k]:.3f} | {s_[k]:.3f} | {a[k]:.3f} |")
    A("")
    A(f"Capacity is calibrated to the {calib_delay_words(res)} (the 'peak queue + road delay' row when roads "
      "are congested; the 'peak queue delay' row with free-flow roads).")
    A("")
    A("'Before' is the pre-recalibration specification, which has no fuel cost, paid parking NZ$8, no early start and "
      "no willingness-to-pay limit (its SKIP option no longer exists in the model). 'Structural fixes only' is the "
      f"current model, with the fixed parking (NZ${PARK_FIXED:g}) and fuel (NZ${fu['fuel_cost_per_km']:.2f}/km), at "
      f"the design values (PAP 8, k_WFH 8, beta0 0.5). It has base car {s_['base_car']:.3f} "
      f"and PT {s_['base_pt']:.3f}, far outside the baseline bands, and responds by {pct(s_['change_21_30'])} on days "
      f"21-30 and {pct(s_['change_11_13'])} on days 11-13 (per seed "
      + ", ".join(pct(r["change_21_30"]) for r in res["structural_only"]["per_seed"]) + "). "
      + (f"Without fuel and with v3's NZ$8 parking the v3-valued model gave car {pf['structural_mean']['base_car']:.3f}, "
         f"PT {pf['structural_mean']['base_pt']:.3f} and a response of {pct(pf['structural_mean']['change_21_30'])} "
         f"(overshoot {pct(pf['structural_mean']['change_11_13'])}), the like-for-like v3 sensitivity. " if pf else "")
      + f"In the search PAP moved to restore the assumed baseline shares (to {ch['pap']:g}), k_WFH to {ch['wfh']:g} "
      f"and beta0 to {ch['beta0']:g}, and the response is {pct(a['change_21_30'])}. The closeness to Stockholm's -20% "
      "is partly a by-product of fitting the baseline.")
    A("")
    A("## Per-seed metrics against each target (chosen values)")
    A("")
    rows = res["chosen"]["per_seed"] + res["chosen"]["holdout"]
    A("| Seed | capacity scale | base car | base PT | base WFH | d11-13 | d21-30 | no car d21-30 | within band / tolerance |")
    A("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        flags = []
        for k in TARGETS:
            if band_excess(k, r[k]) == 0:
                continue
            flags.append(f"{k} {'within tol.' if band_excess(k, r[k], SEED_TOL[k]) == 0 else 'OUT'}")
        tag = " (held out)" if r["seed"] in HOLDOUT_SEEDS else ""
        A(f"| {r['seed']}{tag} | {r['capacity_scale']:.4f} | {r['base_car']:.3f} | {r['base_pt']:.3f} | "
          f"{r['base_wfh']:.3f} | {pct(r['change_11_13'])} | {pct(r['change_21_30'])} | {r['end_wtt_no_car']:.3f} | "
          f"{'all in band' if not flags else '; '.join(flags)} |")
    A("")
    A("Target status on the calibration seeds 1-3:")
    A("")
    for k, t in tst.items():
        rounded_ok = band_excess(k, round(t["mean"], 2)) == 0.0
        state = ("in band" if t["mean_in_band"] else
                 "in band at the stated precision, outside the bound unrounded" if rounded_ok else "OUT of band")
        A(f"- `{k}`: mean {t['mean']:.3f} ({state}); seeds in band "
          f"{sum(t['seeds_in_band'])}/3, within tolerance {sum(t['seeds_within_tolerance'])}/3.")
    A("")
    oos = res.get("out_of_sample")
    if oos:
        A("## Out-of-sample seeds and the ridge alternatives")
        A("")
        A(oos["note"] + " Seeds 4-5 come from the final stage; seeds 6-12 were never run before the selection.")
        A("")
        A("| Seed | capacity scale | base car | base PT | base WFH | d11-13 | d21-30 | no car d21-30 | outside band / tolerance |")
        A("|---|---|---|---|---|---|---|---|---|")
        for r in oos["chosen"]["per_seed"]:
            flags = []
            for k in TARGETS:
                if band_excess(k, r[k]) == 0:
                    continue
                flags.append(f"{k} {'within tol.' if band_excess(k, r[k], SEED_TOL[k]) == 0 else 'OUT of tol.'}")
            A(f"| {r['seed']} | {r['capacity_scale']:.4f} | {r['base_car']:.3f} | {r['base_pt']:.3f} | "
              f"{r['base_wfh']:.3f} | {pct(r['change_11_13'])} | {pct(r['change_21_30'])} | {r['end_wtt_no_car']:.3f} | "
              f"{'all in band' if not flags else '; '.join(flags)} |")
        A("")
        A("| Point | seeds | base car | base PT | base WFH | d11-13 | d21-30 |")
        A("|---|---|---|---|---|---|---|")
        cm = res["chosen"]["mean"]
        nm = f"PAP {ch['pap']:g} / k_WFH {ch['wfh']:g} / beta0 {ch['beta0']:g}"
        A(f"| chosen {nm} | 1-3 (calibration) | {cm['base_car']:.3f} | {cm['base_pt']:.3f} | {cm['base_wfh']:.3f} | "
          f"{pct(cm['change_11_13'])} | {pct(cm['change_21_30'])} |")
        for lab, key in (("4-12", "mean_4_12"), ("6-12 (unseen)", "mean_6_12"), ("1-12", "mean_1_12")):
            m = oos["chosen"][key]
            A(f"| chosen {nm} | {lab} | {m['base_car']:.3f} | {m['base_pt']:.3f} | {m['base_wfh']:.3f} | "
              f"{pct(m['change_11_13'])} | {pct(m['change_21_30'])} |")
        for alt in oos["alternatives"]:
            sc = alt["scalars"]
            for lab, m in (("1-3 (calibration)", alt["mean_1_3"]), ("4-12", alt["mean_4_12"])):
                A(f"| PAP {sc['pap']:g} / k_WFH {sc['wfh']:g} / beta0 {sc['beta0']:g} | {lab} | {m['base_car']:.3f} | "
                  f"{m['base_pt']:.3f} | {m['base_wfh']:.3f} | {pct(m['change_11_13'])} | {pct(m['change_21_30'])} |")
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
          f"seeds 1-12). Over seeds 1-12 base car is {m12['base_car']:.3f} ({inb('base_car', m12['base_car'])}) and base "
          f"PT {m12['base_pt']:.3f} ({inb('base_pt', m12['base_pt'])}), at the stated precision. On the unseen seeds "
          f"6-12 alone base car is {m6['base_car']:.3f} ({inb('base_car', m6['base_car'])}) and base PT "
          f"{m6['base_pt']:.3f} ({inb('base_pt', m6['base_pt'])}). "
          "Single seeds outside the stated tolerance: "
          + ("; ".join(out_tol) if out_tol else "none outside tolerance") + ". "
          + "The ridge alternatives ("
          + ", ".join(f"PAP {x['scalars']['pap']:g} / k_WFH {x['scalars']['wfh']:g} / beta0 {x['scalars']['beta0']:g}"
                      for x in oos["alternatives"])
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
        A("| Variant (at the chosen PAP, k_WFH and beta0) | feasible | base car | base PT | base WFH | no car d21-30 | "
          "early start d6-10 | early start d21-30 | d11-13 | d21-30 | 08:00-09:00 crossings |")
        A("|---|---|---|---|---|---|---|---|---|---|---|")
        cm0 = res["chosen"]["mean"]
        A(f"| chosen point, no change | {'yes' if res['chosen'].get('feasible') else 'no'} | {cm0['base_car']:.3f} | "
          f"{cm0['base_pt']:.3f} | {cm0['base_wfh']:.3f} | {cm0['end_wtt_no_car']:.3f} | "
          f"{cm0['base_early']:.3f} | {cm0['end_early']:.3f} | {pct(cm0['change_11_13'])} | {pct(cm0['change_21_30'])} | "
          f"{pct(cm0['peak_cross_change'])} |")
        for v in gs["variants"]:
            m = v["mean"]
            A(f"| {v['what']} | {'yes' if v['feasible'] else 'no'} | {m['base_car']:.3f} | {m['base_pt']:.3f} | "
              f"{m['base_wfh']:.3f} | {m['end_wtt_no_car']:.3f} | {m['base_early']:.3f} | {m['end_early']:.3f} | "
              f"{pct(m['change_11_13'])} | {pct(m['change_21_30'])} | {pct(m['peak_cross_change'])} |")
        A("")
        if gs.get("research"):
            gg = gs["research"][0]["grid"]
            A(f"Local re-search under each changed assumption (PAP {gg['pap'][0]:g} to {gg['pap'][-1]:g}, k_WFH "
              f"{gg['wfh'][0]:g} to {gg['wfh'][-1]:g}, beta0 as in the variant or the chosen value, seeds 1-3, same "
              "rule; optional stage `gap`; logged as `gap_sensitivity.research`, never adopted):")
            A("")
            A("| Changed assumption | feasible points | the rule would choose | base car | base PT | d11-13 | d21-30 |")
            A("|---|---|---|---|---|---|---|")
            for v in gs["research"]:
                w = v["would_choose"]
                m = w["mean"]
                A(f"| {v['what']} | {v['n_feasible']} of {v['n_points']} | PAP {w['scalars']['pap']:g} / k_WFH "
                  f"{w['scalars']['wfh']:g} ({'feasible' if w['feasible'] else 'not feasible, lowest loss'}) | "
                  f"{m['base_car']:.3f} | {m['base_pt']:.3f} | {pct(m['change_11_13'])} | {pct(m['change_21_30'])} |")
            A("")
        A(gs["reading"])
        A("")
    A(f"![mode shares]({Path(res['figures']['mode_shares']).relative_to('docs').as_posix()})")
    A("")
    A(f"![crossing change]({Path(res['figures']['crossing_change']).relative_to('docs').as_posix()})")
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
    A(f"![crossing times]({Path(res['figures']['crossing_times']).relative_to('docs').as_posix()})")
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
        fd = oos["F_decomposition"]
        rk = [f["retimed_keepers"] - f["retimed_keepers_nofee"] for f in fd]
        rk_words = ("flat across F" if max(rk) - min(rk) < 0.05 else
                    "larger at higher F" + ("" if bool(np.all(np.diff(rk) >= 0)) else ", though not monotone"))
        pb = res["retiming_paired"]["by_F"]
        A(f"Between F = 1 and F = 5 the charge's effect on the car share (charge minus no-charge run) goes from "
          f"{fd[0]['end_car_minus_nofee']:+.3f} to {fd[-1]['end_car_minus_nofee']:+.3f} and on the WFH share from "
          f"{fd[0]['end_wfh_minus_nofee']:+.3f} to {fd[-1]['end_wfh_minus_nofee']:+.3f}, while the PT gain stays between "
          f"{min(f['end_pt_minus_nofee'] for f in fd):+.3f} and {max(f['end_pt_minus_nofee'] for f in fd):+.3f}: the F "
          "response gradient comes mainly from F = 4-5 hybrid workers switching to daily WFH, which is unbounded "
          "without v3's WFH quota. It is a mode effect and is no evidence on retiming, which moves a crossing in time "
          "rather than removing it. Retiming is checked separately: against the no-charge run, retiming of car keepers "
          "changes by " + ", ".join(f"{x:+.3f}" for x in rk) + f" at F = 1-5 ({rk_words}); the paired departure "
          f"change goes from {pb[0]['retimed']:.2f} at F = 1 to {pb[-1]['retimed']:.2f} at F = 5, and retiming in the "
          "no-charge run itself is " + ", ".join(f"{f['retimed_keepers_nofee']:.3f}" for f in fd) + ".")
        A("")
    A("## Limits")
    A("")
    for line in res["limits"]:
        A(f"- {line}")
    A("")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------- main


# Hand-written prose: every number below is taken from data/behaviour_calibration.json of the three-scalar search of
# 2026-10-09 (SKIP removed, willingness to travel added, 950 agents, congested roads with the motorway breakdown rule,
# capacity calibrated to the peak queue + road delay), except the single-agent counts, which come from
# tests/test_rules.py. Rewrite it after every new search.
LIMITS = [
    "The targets are stated assumptions, and the response anchors are not like-for-like: Stockholm and Gothenburg "
    "measured total cordon traffic in charged hours over months to years, while the band here applies to AM car "
    "commuters over days 21-30. v3 10.5 asks for a qualitative comparison only; the private-car commuter response "
    "is likely larger than the total-traffic one.",
    "Behaviour is calibrated at the NZ$6 peak of the SSC2026 schedule only. Runs at other peaks (fees.peak_fee 0, 3, "
    "12, 18, 30) extrapolate the fitted model, and the willingness to travel makes the extrapolation steep by "
    "construction: the share willing to pay falls as exp(-beta F / VoT), so a higher peak removes the car for more "
    "commuters whatever the rest of the cost model says.",
    "15 of 489 points are feasible, all at PAP 22, on a ridge in k_WFH and beta0: k_WFH 10 with beta0 0.05, 11 with "
    "0.05-0.1, 12 with 0.05-0.15, 13 with 0.05-0.2 and 14 with 0.05-0.25. At the stated precision base PT is 0.16 at "
    "PAP 21 for every k_WFH; base car is 0.86 or more at PAP 22 from k_WFH 15, at PAP 23 from k_WFH 7 and at PAP 24 "
    "from k_WFH 6, and the lower k_WFH that keep the base shares in band at PAP 23-24 respond by -27.7% or more on "
    "days 21-30 even without the willingness to travel. The rule picks PAP 22 / k_WFH 12 / beta0 0.15, the feasible point nearest "
    "the anchors. The next ones are k_WFH 13 / beta0 0.2 (anchor distance 3.813 against 3.802), k_WFH 11 / beta0 0.1 "
    "(3.843) and k_WFH 14 / beta0 0.25 (3.875): the targets fix the ridge and the anchors choose the point on it. The "
    "lowest-loss point is k_WFH 10 / beta0 0.05 (loss 2.03 against 2.18). On unrounded 3-seed means no point is "
    "feasible, because base car is 0.853-0.855 at every feasible point. On the calibration seeds base car is above 0.85 "
    "on seeds 1 and 2 (0.853, 0.859) and the days 21-30 response is beyond -22% on seed 2 (-23.1%), all within the "
    "stated tolerance. The targets were not relaxed.",
    "The response is close to the centre of the band: -21.4% on seeds 1-3 (-20.9%, -23.1%, -20.4%), -21.1% on unseen "
    "seeds 6-12 (single seeds -19.2% to -23.1%) and -21.3% over seeds 1-12, with an overshoot of -25.2%, -25.4% and "
    "-25.3%. Base car runs high out of sample: 0.863 on the unseen seeds 6-12 and 0.859 over seeds 1-12, both above "
    "the band at the stated precision. It is above 0.85 on held-out seed 4 and on every unseen seed except 11 (0.859 "
    "to 0.875), all within the tolerance; base PT is 0.136 and 0.140, above 0.15 only on seeds 5 and 11 (0.153, "
    "0.151). The chosen point sits at the top of the base car band because base car rises as k_WFH removes the last "
    "WFH days (0.849 at k_WFH 9, 0.854 at 12), and the 0.2% who skipped before the charge now choose among car, PT "
    "and WFH.",
    "The willingness to travel does much of the work. At the chosen point 14.2% of commuters have a WTP below the NZ$6 "
    "peak (exempt company cars and trades included); on charged days 8.3% have no car option left, the same share on "
    "days 11-13 and 21-30 because the threshold is fixed, 11.6% have at least one car option removed, and 5.6% of "
    "all commuters are left with PT only (decider 'forced'). Without it (beta0 = 0, same PAP and k_WFH) the days "
    "21-30 response is -14.5% and the overshoot -18.7%; with SSC2026's beta0 0.5 they are -32.3% and -35.5%, and "
    "21.9% of commuters have no car option. Because beta is clipped below at 0.1, any positive beta0 removes some "
    "car options: beta0 0.05 already leaves 4.3% of commuters without a car and strengthens the response by 3.7 pp "
    "(-14.5% to -18.2% at k_WFH 12). The limit cannot be made weaker than that floor except by switching it off. "
    "VoT_ref from the simulated commuters' median VoT instead of exp(vot_mu) leaves the response practically "
    "unchanged (-21.4%).",
    "With the charge more commuters start early. About 48% may start early; 7.6% of all commuters do so on days 6-10 "
    "(8.8% of car users), 9.4% on days 11-13 and 9.5% on days 21-30, against 6.9% in the no-charge run; as a share of "
    "the fewer remaining car users it is 14.1%. The money saved by crossing early (NZ$4 before 07:30 against NZ$6 "
    "from 08:00 to 09:00, plus the loss term, and for some commuters the only charge they are willing to pay) is "
    "weighed against the assumed inconvenience of NZ$3 x phi(F), and the result depends on that assumed cost: at "
    "NZ$1.5 x phi(F) the share is 14.0% before and 17.0% after the charge and the 08:00 to 09:00 crossings fall by "
    "46.3%; at NZ$6 x phi(F) almost nobody starts early (0.018, then 0.014). Without the early start the days 21-30 "
    "response is -22.8% and seed 2 reaches -24.3%, beyond the tolerance. The cost and the permission probabilities "
    "are assumptions with no empirical source.",
    "Peak spreading is clear in every seed. Car crossings in the 08:00 to 09:00 peak (NZ$6) fall by 42.2% from days "
    "6-10 to days 21-30 against 21.4% over the whole morning (seeds 1-3: 44.1%, 39.9%, 42.5% against 20.9%, 23.1%, "
    "20.4%), and by 43.4% on unseen seeds 6-12 (43.0% over seeds 1-12). Crossings before 07:30 rise by 14.0% on "
    "seeds 1-3 (+18.4%, +5.2%, +18.3%) and by 13.5% over seeds 1-12. Against the no-charge run the 08:00 to 09:00 "
    "share of crossings falls in every seed (-0.129, -0.098, -0.132) and the 07:00 to 08:00 share rises (+0.065, "
    "+0.051, +0.081). In the paired check 32.8% of commuters who drive in both runs have a different modal departure "
    "with the charge, 20.9% earlier and 11.8% later (mean shift -9.8 minutes).",
    "Day-to-day churn in the daily rule arm is large: 25% of commuters have a different modal car departure on "
    "days 26-30 than on days 6-10 with the charge, and 23% without it. A before-and-after count of retimers "
    "therefore says little, and retiming is reported against the no-charge run.",
    "PAP is a fitted residual. With parking and fuel fixed, PAP is the only scalar that can hold the assumed "
    "pre-charge split, and the willingness to travel does not move that split; it is 22 again (v3 PAP 22-44 in v3's "
    "form, against v3's NZ$8 swept 4-12). At PAP 22 commuters with P = 1-2 practically never ride PT before the charge "
    "(PT share 0.002 and 0.003 in the population manipulation); after it 5.6% and 5.8% do (+0.055 and +0.058 "
    "against the no-charge run; 0.000 in the two-scalar search without the willingness to travel). "
    "The baseline shares react sharply to PAP (at k_WFH 12: base PT 0.160, 0.145, 0.128 and 0.116 at PAP 21-24), the "
    "response much less (-21.4%, -20.9% and -20.0% at PAP 22-24 with beta0 0.15).",
    "k_WFH and beta0 are identified together, by the response and the overshoot, not by the WFH share (base WFH 0.001 "
    "at k_WFH 12). At PAP 22 and beta0 0.15 the days 21-30 response is -24.3%, -22.4%, -21.4%, -20.0% and -19.4% at "
    "k_WFH 10-14 (overshoot -28.5% to -23.1%); at k_WFH 12 it is -14.5%, -18.2%, -19.5%, -21.4%, -22.9%, -24.2%, "
    "-26.4% and -32.3% at beta0 0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3 and 0.5. Along the ridge one NZ$ of k_WFH offsets "
    "about 0.05 of beta0. A realistic hybrid-work baseline is not reproduced: k_WFH 4 gives 7.4% WFH before the "
    "charge but a response of -36.5% at beta0 0.15. With k_WFH 12 WFH is a small margin (0.1% before the charge, 4.2% "
    "on days 21-30). v3's WFH quota (1-3 days per 5-day block) would bound it; it is not implemented.",
    "The fixed inputs carry their own uncertainty. The petrol price (NZ$3.30/L) is author-supplied for October 2026 "
    "and was not verified here; the last published figure we read was NZ$2.97/L for September 2026. Consumption is "
    "9.0 L/100 km for every paying driver; electric vehicles, fuel cards and other running costs are not "
    "represented. Paid parking NZ$17 is a 2014 casual all-day rate, applied to half of office commuters (the other "
    "half park free). The early start time (07:00), its cost (NZ$3 x phi(F)) and the permission probabilities (0.8, "
    "0.5, 0, 0.5, 0) are author assumptions, and so is the form of the willingness to travel: a threshold fixed per "
    "commuter (SSC2026 draws entry every day), beta clipped to 0.1-2.0, VoT_ref the median of the VoT distribution, "
    "no base trip rate and no 0.05-0.95 clip. Base years are mixed (2026 fuel, 2025 fare and charge, 2014 parking). "
    "The road layer is fixed as well and is not searched: section capacity k = 0.076999 x directional ADT, BPR alpha "
    "0.15 and beta 4 with a speed floor of 0.18, and the motorway breakdown rule (breakdown at V/C 1.0, recovery below "
    "0.95, discharge capacity 10% lower, speed at most 0.45 of free flow).",
    "The design-valued model (PAP 8, k_WFH 8, beta0 0.5) with the fixed parking and fuel has base car 0.556 and PT "
    "0.441, far outside the baseline bands, and responds by -40.0% (overshoot -45.2%). Without fuel, with v3's NZ$8 "
    "parking and without the willingness to travel (300 agents, free-flow roads) the v3-valued model gave -15.4% "
    "(overshoot -25.0%). The scalars were moved to meet the assumed baseline.",
    "The choice does not depend on the soft overshoot bound (the same 15 points are feasible, and the same point is "
    "chosen, for bounds of -30% to -33%), but where it lies on the ridge depends on the anchors (see above). No "
    "other point becomes feasible with the relaxed bound, so the two ridge alternatives checked out of sample are "
    "the points nearest the anchors among the ten lowest-loss other points, PAP 22 / k_WFH 11 / beta0 0.1 and PAP "
    "22 / k_WFH 10 / beta0 0.05. On seeds 4-12 they give -20.7% and -21.0% (base car 0.860 and 0.858), against "
    "-21.2% (base car 0.861) for the chosen point: out of sample the ridge points are hard to tell apart.",
    "Capacity is a further calibrated quantity, recalibrated per (PAP, k_WFH) pair and seed against the peak queue + "
    "road delay; it does not depend on beta0. Its discrete steps add noise to the base shares: at the chosen point "
    "the scale is 0.4303 on seed 1 and 0.3961 on seeds 2-3 (0.3961 on all three at k_WFH 9), and 0.3646 to 0.4303 on "
    "seeds 4-12. The gate queue is the smaller part of the 15-minute target: at the chosen point (seeds 1-3, days "
    "6-10) the car-weighted peak 15-min queue + road delay is 14.9 minutes, the peak of the queue delay alone 4.6 "
    "minutes and the mean road delay of a car 7.3 minutes. On days 21-30 the charge brings the peak queue delay down "
    "to 1.2 minutes, the peak queue + road delay to 9.8 minutes and the mean road delay to 5.9 minutes.",
    "Single-agent example (tests/test_rules.py; no willingness-to-pay limit in the example): for the shared Layer A "
    "with paid parking NZ$17 and the fuel cost of a 20 km path, 250 of the 625 trait combinations ride PT before the "
    "charge. Of the other 375, without the early-start permission 317 keep the car at the usual time on the charge "
    "morning, 54 switch to PT and 4 retime by 15 minutes (H = 1); the two that postponed the day until SKIP was "
    "removed now keep driving. With the permission 300 keep, 53 switch to PT and 22 leave at 06:30 for the 07:00 "
    "start. The v3 worked example (identical A: pay / PT / retime) still separates only with the v3 settings or with "
    "free parking.",
    "H damps the charge wake only at levels 4-5 (days 11-13: -26.5%, -27.4%, -27.0% at H = 1-3, -25.2% and -23.0% "
    "at H = 4-5), and not in the long run (-20.0% to -21.6%): habit re-forms on the new mode immediately.",
    "The charge-induced switch to PT is largest at P = 3 (+0.197 against the no-charge run; +0.156 and +0.142 at "
    "P = 4-5, +0.055 and +0.058 at P = 1-2): at P = 4-5 many PT-feasible agents already ride PT without the charge "
    "(0.40 and 0.58 of them at days 26-30 in the no-charge run, who-adapts tables). The PT share after the charge rises "
    "with P (0.06, 0.06, 0.27, 0.50, 0.60).",
    "The F response gradient (-17.8% at F = 1 to -33.9% at F = 5) still comes mainly from daily WFH of F = 4-5 hybrid "
    "workers (no quota; WFH share 0.17 at F = 5 on days 21-30 with the charge). The 08:00 to 09:00 share of crossings "
    "falls with F against the no-charge run (+0.010 at F = 1 to -0.218 at F = 5), partly because phi(F) scales the "
    "cost of the early day, and retiming of car keepers against the no-charge run is larger at F = 3-5 (+0.120, "
    "+0.158, +0.133) than at F = 1-2 (-0.010, +0.066).",
    "Who-adapts tables conditional on being a day-10 driver are biased by selection; the population manipulation "
    "is the unbiased check.",
    "The reference fee follows the fee faced, but on car days it uses the fee actually paid (after retiming; v3 uses "
    "the fee at h0 before retiming) and alpha 0.3 (SPEC; v3 0.2), so a retimer keeps a loss term on returning to "
    "the peak.",
    "The start an option is measured against is chosen from the expected arrival on the morning of the decision "
    "and is kept for the outcome: a commuter who planned the 07:00 start and is held up counts as late for 07:00 "
    "(and can be woken by T3), not as early for the usual start. For an agent on a standing plan the start is "
    "re-read from that morning's expected arrival.",
    "Only the R-daily arm is calibrated, and the clock arms are not run for this report. The LLM deciders are not "
    "calibrated, but the shared Layer A inputs (parking, fuel, the early-start permission and the willingness to pay, "
    "which removes the same car options in every arm) reach the LLM arms. The rule's WFH earns no parking, fuel or "
    "commute credit while the prompt states both daily costs, so live-LLM WFH shares are not comparable with the "
    "rule arm on this margin, and a live LLM is not told the rule's NZ$3 x phi(F) cost of the early day (it reads "
    "the flexibility sentence instead). MockLLM re-weights the same GC parts; its response at the chosen values is "
    "not measured here.",
]


GAP_READING = (
    "The willingness to travel and the early start do different jobs. Without the willingness to travel (beta0 = 0) "
    "the chosen PAP and k_WFH give -14.5% on days 21-30 (overshoot -18.7%), inside the band but well short of its "
    "centre, and no commuter loses the car; with SSC2026's beta0 0.5 the response is -32.3% (overshoot -35.5%) and "
    "21.9% of commuters have no car option, beyond the band on every seed. Taking VoT_ref from the simulated "
    "commuters' median VoT instead of exp(vot_mu) leaves the response practically unchanged (-21.4%). The early start keeps the chosen "
    "point feasible: without it the response is -22.8% and seed 2 reaches -24.3%, beyond the tolerance, and the "
    "08:00 to 09:00 crossings fall by 38.7% against 42.2% with it. How much the early start is used depends on its "
    "assumed cost: at NZ$1.5 x phi(F) 14.0% of commuters start early before the charge and 17.0% after it, and the "
    "peak crossings fall by 46.3%; at NZ$6 x phi(F) the option is almost unused (0.018, then 0.014). Giving the "
    "permission to every employee of the three eligible groups raises the share to 0.102 before and 0.124 after the "
    "charge. These three variants raise base car to 0.856-0.858, above the band at the stated precision (and at "
    "NZ$6 x phi(F) seed 2 responds by -24.6%, beyond the tolerance). None of the variants was searched or adopted; 'feasible' is judged at "
    "the chosen PAP, k_WFH and beta0 only.")


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
     "why": "[v3 6.2 PAP NZ$8, swept {4, 8, 12}, in v3's form omega(P) x PAP x HTA/2]; free scalar 1 of 3 (the others are "
            "k_WFH, searched in 2-16, and wtt.beta0), entered in the "
            "specification form omega(P) x (VoT/60 x T_pt + PAP), so the value is not comparable with v3's."},
    {"param": "SKIP option", "from": "SKIP (postpone or cancel the day) at NZ$25, later NZ$30, plus one hour of VoT",
     "to": "removed: every commuter chooses among CAR (a departure time), PT and WFH where allowed",
     "why": "[author decision 2026-10-09] SKIP had become a permanent choice rather than a one-day postponement (at a "
            "NZ$30 peak 97 of R-clock's 102 skippers skipped all of days 21-30; at NZ$6, 8 commuters skipped every "
            "day), and in the rule arms every skipper could have taken PT. The SKIP-share target goes with it."},
    {"param": "wtt.beta0 (willingness to travel)", "from": "none (any charge could be paid)",
     "to": "WTP = -ln(u) x VoT / beta, beta = clip(beta0 x VoT_ref / VoT, 0.1, 2.0), u ~ U(0,1) fixed per commuter; "
           "a CAR option charged above WTP is not offered; beta0 searched (free scalar 3 of 3)",
     "why": "[author decision 2026-10-09; SSC2026 akl_pricing.nls exponential decay, base_beta 0.5] The share willing "
            "to pay a charge F falls as exp(-beta F / VoT). Company cars and commuters with neither PT nor WFH are "
            "exempt. It applies in every arm as a choice-set constraint, and not on uncharged days."},
    {"param": "engine capacity", "from": "seed-1 scale used for every seed",
     "to": "recalibrated per seed and per evaluated (PAP, k_WFH) pair; data/calibration.json holds by_seed records",
     "why": "Pre-charge congestion feeds back on the response. The calibration has no charge, so it does not depend "
            "on beta0."},
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
    use_logged_n(res, args.stage)

    if args.stage in ("all", "search"):
        # append-only selection history: carry the archived history forward and record the selection
        # that this search replaces. The note below describes the change of the search of 2026-10-09 (SKIP
        # removed, willingness to travel added, beta0 searched as a third scalar); before the next search,
        # archive the current log as LAST_JSON and rewrite the note for that search's change.
        prev = json.loads(LAST_JSON.read_text()) if LAST_JSON.exists() else {}
        history = list(prev.get("search", {}).get("selection_history", []))
        from cordonlite.config import load_config as _lc
        from cordonlite.roads import road_settings
        fuel_km = float(_lc().costs.fuel_cost_per_km)
        _c = _lc()
        if prev:
            pch = prev.get("chosen", {})
            p_how = ("the feasible point nearest the anchors" if pch.get("feasible")
                     else "no feasible point, lowest loss")
            arc = archive_paths(LAST_JSON)
            history.append({
                "replaced_at": time.strftime("%Y-%m-%d %H:%M:%S"), "selection": prev["search"].get("selection"),
                "anchors": prev["search"].get("anchors"), "chosen": pch.get("label"),
                "note": (f"{time.strftime('%Y-%m-%d')}: SKIP (postpone the day, NZ$"
                         f"{float(prev.get('skip', {}).get('skip_cost', 30.0)):g} plus one hour of VoT) was removed "
                         "from the model and the willingness to travel was added (config.toml [wtt]: a fixed most "
                         "each commuter would pay to drive in, WTP = -ln(u) x VoT / beta, beta = clip(beta0 x VoT_ref "
                         "/ VoT, 0.1, 2.0), after SSC2026's exponential decay; a car option charged above it is not "
                         "offered) [author decisions 2026-10-09]. beta0 is searched as a third scalar next to PAP and "
                         "k_WFH in a staged grid with the same targets (less the SKIP share), seeds, loss and rule; the "
                         "anchors gain beta0 0.5 (SSC2026 base_beta). This replaces the two-scalar search with "
                         f"{state_words(prev)} and SKIP, which chose {pch.get('label')} ({p_how}); its full log is kept "
                         f"in {arc['log']}, its capacity calibration in {arc['capacity']} and its report in "
                         f"{arc['report']}.")})
        res = {"early_start": {"early_start_min": int(_c.costs.early_start_min),
                               "early_shift_cost": float(_c.costs.early_shift_cost),
                               "early_shift_prob": list(_c.persona.early_shift_prob),
                               "anchor_offsets_min": list(_c.time.anchor_offsets_min),
                               "status": "fixed assumptions [A, author decision 2026-10-05]; not searched"},
               "skip_removed": {"date": "2026-10-09",
                                "status": ("SKIP removed from the model [author decision 2026-10-09]; the archived "
                                           "logs hold base_skip and end_skip"),
                                "last_skip_cost": float(prev.get("skip", {}).get("skip_cost", 30.0)) if prev else None},
               "wtt": {"beta_clip": [float(x) for x in _c.wtt.beta_clip], "vot_ref": _c.wtt.vot_ref,
                       "vot_ref_value": round(math.exp(float(_c.persona.vot_mu)), 4),
                       "peak_fee": float(_c.fees.peak_fee),
                       "form": ("WTP = -ln(u) x VoT / beta, beta = clip(beta0 x VoT_ref / VoT, beta_clip), u ~ U(0,1) "
                                "once per commuter (Layer A); a CAR option whose charge is above WTP is not offered; "
                                "company cars and commuters with neither PT nor WFH are exempt"),
                       "status": "beta0 searched; beta_clip [SSC] and vot_ref [A] fixed, not searched"},
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
               "capacity_procedure": ("nested: for every (PAP, k_WFH) pair and seed, cordonlite.run.calibrate "
                                      "(default bracket and tolerance) is run with that pair's behaviour "
                                      "parameters, then the 30-day charged runs of every beta0 of the pair use the "
                                      "resulting scale (the calibration has no charge, so the willingness to pay "
                                      "removes nothing and the scale does not depend on beta0); it "
                                      f"targets the car-weighted peak 15-min "
                                      f"{'queue + road' if _c.engine.calib_delay == 'total' else 'queue'} delay "
                                      f"(engine.calib_delay = {_c.engine.calib_delay!r}) of "
                                      f"{_c.engine.calib_target_peak_delay_min:g} min"),
               "calib_delay": _c.engine.calib_delay,
               "calib_target_peak_delay_min": float(_c.engine.calib_target_peak_delay_min),
               "road": {**road_settings(_c),
                        "status": "fixed inputs (config.toml [road], k from data/road_meta.json); not searched"}}
        ck = Checkpoint()
        stages: dict[str, Any] = {}

        def run_stage(name: str, pairs: list[tuple[float, float]], betas: list[float], extra: list[dict] = ()) -> None:
            """Calibrate the (PAP, k_WFH, seed) not yet calibrated (with the extra evaluations in the same pool),
            then run every (pair, beta0, seed) not yet run."""
            t_ = time.perf_counter()
            todo = [(p, w, s) for (p, w) in pairs for s in SEEDS if cal_key(p, w, s) not in ck.cal]
            jobs = [{"kind": "capacity", "key": cal_key(p, w, s), "overrides": point_overrides(p, PARK_FIXED, w, 0.0),
                     "seed": s} for (p, w, s) in todo]
            jobs = [j for j in extra if ck.row(j["label"], j["seed"]) is None] + jobs
            print(f"{name}: {len(todo)} capacity calibrations (+{len(jobs) - len(todo)} other evaluations) on "
                  f"{args.workers} workers", flush=True)
            done = [0]

            def keep(r: dict) -> None:   # into the checkpoint as results arrive; saved every 25
                if "key" in r:
                    ck.cal[r["key"]] = r["calibration"]
                else:
                    ck.add_row(r)
                done[0] += 1
                if done[0] % 25 == 0:
                    ck.save()

            if jobs:
                run_jobs(jobs, args.workers, f"{name} capacity", fn=task, on_result=keep)
            ck.save()
            jobs = []
            for (p, w) in pairs:
                for b in betas:
                    sc = {"pap": p, "park": PARK_FIXED, "wfh": w, "beta0": b}
                    for s in SEEDS:
                        if ck.row(point_label(sc), s) is None:
                            c_ = ck.cal[cal_key(p, w, s)]
                            jobs.append({"label": point_label(sc), "overrides": point_overrides(p, PARK_FIXED, w, b),
                                         "seed": s, "scale": c_["capacity_scale"], "calibration": c_,
                                         "meta": {"scalars": sc, "stage": name}})
            print(f"{name}: {len(jobs)} charged runs ({len(pairs)} pairs x {len(betas)} beta0 x {len(SEEDS)} seeds, "
                  "less those already run)", flush=True)
            if jobs:
                run_jobs(jobs, args.workers, f"{name} runs", on_result=keep)
            ck.save()
            stages[name] = {"pairs": [list(x) for x in pairs], "beta0": list(betas),
                            "n_calibrations": len(todo), "n_runs": len(jobs),
                            "seconds": round(time.perf_counter() - t_, 1)}

        def build_points() -> list[dict]:
            by_label: dict[str, list[dict]] = {}
            for r in ck.rows.values():
                if "scalars" in r:
                    by_label.setdefault(r["label"], []).append(r)
            pts_ = []
            for label, pr in by_label.items():
                pr = sorted(pr, key=lambda r: r["seed"])
                if [r["seed"] for r in pr] != list(SEEDS):
                    continue
                sc = dict(pr[0]["scalars"])
                pts_.append({"label": label, "scalars": sc, "reference": sc["beta0"] == BETA0_REFERENCE,
                             "stage": pr[0].get("stage"), "loss": loss(pr, sc), "mean": summarise(pr),
                             "feasible": feasible(pr), "anchor_distance": anchor_distance(sc),
                             "per_seed": [{kk: r[kk] for kk in ("seed", "capacity_scale", "calibration", *TARGETS,
                                                                "end_car", "end_pt", "end_wfh", "wtt_no_car_11_13",
                                                                "end_wtt_no_car", "end_wtt_limited", "end_forced",
                                                                "wtp_below_peak_share", "base_early", "end_early",
                                                                "peak_cross_change", "peak_band_share_21_30")}
                                          for r in pr]})
            return sorted(pts_, key=lambda q: (q["scalars"]["pap"], q["scalars"]["wfh"], q["scalars"]["beta0"]))

        t_search = time.perf_counter()
        extra = [{"label": "before", "overrides": BEFORE, "seed": s, "scale": "calibrate", "nofee": True}
                 for s in SEEDS]
        extra += [{"label": "structural", "overrides": point_overrides(V3_SCALARS["pap"], PARK_FIXED,
                                                                       V3_SCALARS["wfh"], V3_SCALARS["beta0"]),
                   "seed": s, "scale": "calibrate"} for s in SEEDS]
        pairs1 = list(itertools.product(STAGE1["pap"], STAGE1["wfh"])) + STAGE1_CORNERS
        run_stage("stage1", pairs1, [BETA0_REFERENCE] + BETA0_STAGE1, extra)
        paps2 = stage2_paps(candidates(build_points()))
        pairs2 = list(itertools.product(paps2, GRID["wfh"]))
        run_stage("stage2", pairs2, [BETA0_REFERENCE] + BETA0_STAGE1)
        stages["stage2"]["paps"] = paps2
        best2 = select(build_points())
        betas3 = stage3_betas(best2["scalars"]["beta0"])
        run_stage("stage3", pairs2, betas3)
        stages["stage3"]["chosen_after_stage2"] = best2["label"]
        points = build_points()
        beta0_values = sorted({p["scalars"]["beta0"] for p in candidates(points)})
        res["before"] = {"per_seed": sorted(ck.rows_labelled("before"), key=lambda r: r["seed"])}
        res["before"]["mean"] = summarise(res["before"]["per_seed"])
        res["structural_only"] = {"per_seed": sorted(ck.rows_labelled("structural"), key=lambda r: r["seed"]),
                                  "scalars": {"pap": V3_SCALARS["pap"], "park": PARK_FIXED, "wfh": V3_SCALARS["wfh"],
                                              "beta0": V3_SCALARS["beta0"]}}
        res["structural_only"]["mean"] = summarise(res["structural_only"]["per_seed"])
        res["search"] = {"method": SEARCH_DESIGN, "free_scalars": ["pap", "wfh", "beta0"],
                         "range_probe": RANGE_PROBE, "stages": stages, "beta0_values": beta0_values,
                         "beta0_reference": BETA0_REFERENCE,
                         "n_calibrations": sum(s_["n_calibrations"] for s_ in stages.values()),
                         "n_runs": sum(s_["n_runs"] for s_ in stages.values()),
                         "wall_seconds": round(time.perf_counter() - t_search, 1), "workers": args.workers,
                         "anchors": ANCHORS, "selection": SELECTION_DOC,
                         "points": points, "loss_doc": " ".join(loss.__doc__.split()),
                         "selection_history": history}
        best = select(points)
        res["chosen"] = {"scalars": best["scalars"], "label": best["label"], "loss": best["loss"],
                         "on_grid_edge": on_grid_edge(best["scalars"], beta0_values)}
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
        ck.clear()
        print(f"chosen {best['label']} feasible {best['feasible']} loss {best['loss']['total']:.3f} "
              f"mean {best['mean']}", flush=True)

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
                         "on_grid_edge": on_grid_edge(best["scalars"], res["search"].get("beta0_values"))}
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
        print(f"chosen {best['label']} feasible {best['feasible']} mean {best['mean']}", flush=True)

    if args.stage in ("all", "final"):
        ch = res["chosen"]["scalars"]
        ov = point_overrides(ch["pap"], ch["park"], ch["wfh"], ch["beta0"])
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
        # early start, retiming, the willingness to pay and peak spreading, per seed (charged run and no-charge run)
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
            for k in ("base_early", "end_early", "early_11_13", "base_early_of_cars", "end_early_of_cars",
                      "wtt_no_car_11_13", "end_wtt_no_car", "end_wtt_limited", "end_forced", "wtp_below_peak_share",
                      "wtt_limitable_share", "wtp_below_peak_limitable_share", "change_21_30", "peak_cross_change",
                      "pre0730_cross_change", "peak_cross_6_10", "peak_cross_21_30"):
                row[k] = r[k]
            for k in ("base_early", "end_early", "change_21_30", "peak_cross_change", "pre0730_cross_change"):
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
                "end_wtt_no_car": ("share of all commuters with every car option removed by the willingness to pay, "
                                   "mean of days 21-30 (wtt_no_car_11_13: days 11-13)"),
                "end_wtt_limited": "share of all commuters with at least one car option removed, days 21-30",
                "end_forced": "share of all commuters whose decision was forced (PT the only option left), days 21-30",
                "wtp_below_peak_share": "share of all commuters whose WTP is below the peak charge (exempt ones included)",
                "wtt_limitable_share": "share of commuters the limit can apply to (no company car; PT or WFH allowed)",
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
        ov = point_overrides(ch["pap"], ch["park"], ch["wfh"], ch["beta0"])
        jobs = [{"label": "chosen", "overrides": ov, "seed": s, "scale": "calibrate",
                 "meta": {"scalars": dict(ch)}} for s in OOS_SEEDS]
        ridge = ridge_alternatives(res["search"]["points"], res["chosen"]["label"])
        for sc in ridge:
            jobs += [{"label": point_label(sc), "overrides": point_overrides(sc["pap"], sc["park"], sc["wfh"], sc["beta0"]),
                      "seed": s, "scale": "calibrate", "meta": {"scalars": dict(sc)}}
                     for s in HOLDOUT_SEEDS + OOS_SEEDS]
        scale_by_seed = {r["seed"]: r["capacity_scale"] for r in res["chosen"]["per_seed"]}
        for lv in (1, 2, 3, 4, 5):
            one = [1.0 if i == lv else 0.0 for i in range(1, 6)]
            jobs += [{"label": f"F{lv}", "overrides": {**ov, "traits.shares_F": one}, "seed": s,
                      "scale": scale_by_seed[s], "nofee": True, "agents": True, "meta": {"level": lv}}
                     for s in SEEDS]
        # sensitivities to the fixed assumptions at the chosen point (never adopted, no new search). The SKIP cost
        # variant (NZ$25) went with SKIP on 2026-10-09; the willingness-to-pay variants took its place.
        GAP = [("nowtt", "no willingness-to-pay limit (wtt.beta0 = 0; SKIP stays removed)", {"wtt.beta0": 0.0}),
               ("ssc", "SSC2026's price sensitivity (wtt.beta0 = 0.5, the anchor)", {"wtt.beta0": 0.5}),
               ("samplemedian", "VoT_ref = median VoT of the simulated commuters, as SSC2026 (wtt.vot_ref = "
                                "\"sample_median\")", {"wtt.vot_ref": "sample_median"}),
               ("noearly", "no early-start option (persona.early_shift_prob all 0)",
                {"persona.early_shift_prob": [0.0, 0.0, 0.0, 0.0, 0.0]}),
               ("early1.5", "early day costs NZ$1.5 x phi(F) (costs.early_shift_cost 3 -> 1.5)",
                {"costs.early_shift_cost": 1.5}),
               ("early6", "early day costs NZ$6 x phi(F) (costs.early_shift_cost 3 -> 6)",
                {"costs.early_shift_cost": 6.0}),
               ("earlyall", "every employer of archetypes 1, 2 and 4 allows the early day (probabilities 1, 1, 0, 1, 0)",
                {"persona.early_shift_prob": [1.0, 1.0, 0.0, 1.0, 0.0]})]
        GAP = [g for g in GAP if not (g[0] == "ssc" and ch["beta0"] == 0.5)]   # no variant equal to the chosen point
        jobs += [{"label": f"gap_{g_}", "overrides": {**ov, **o_}, "seed": s, "scale": "calibrate"}
                 for (g_, _, o_) in GAP for s in SEEDS]
        rows = run_jobs(jobs, args.workers, "oos")
        gap = []
        for (g_, what, o_) in GAP:
            pr = [r for r in rows if r["label"] == f"gap_{g_}"]
            gap.append({"label": g_, "what": what, "overrides": o_, "mean": summarise(pr), "feasible": feasible(pr),
                        "per_seed": [{kk: r[kk] for kk in ("seed", "capacity_scale", *TARGETS, "end_wtt_no_car",
                                                           "end_wtt_limited", "base_early", "end_early",
                                                           "peak_cross_change")} for r in pr]})
        res["gap_sensitivity"] = {
            "note": ("Run after the selection and not adopted. Each variant changes one of the fixed assumptions "
                     "(the willingness-to-pay form, early-start option) or sets beta0 to 0 or 0.5 at the chosen PAP, "
                     "k_WFH and (otherwise) beta0 (no new search), on seeds 1-3 with nested capacity calibration, to "
                     "show how much the result depends on it."),
            "variants": gap, "reading": ""}
        keep = ("seed", "capacity_scale", *TARGETS, "end_car", "end_pt", "end_wfh", "end_wtt_no_car", "base_early",
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
        for sc in ridge:
            lab = point_label(sc)
            rr = [{k: r[k] for k in keep} for r in rows if r["label"] == lab]
            calib = next(p for p in res["search"]["points"] if p["label"] == lab)
            oos["alternatives"].append({"label": lab, "scalars": dict(sc), "per_seed": rr,
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
                         "end_wtt_no_car": float(np.mean([r["end_wtt_no_car"] for r in rr])),
                         "retimed_keepers": float(np.mean(ret)), "retimed_keepers_nofee": float(np.mean(ret0))})
        oos["F_decomposition"] = fdec
        res["out_of_sample"] = oos
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")

    if args.stage == "gap":   # optional local re-search under one changed assumption; logged, never adopted; not part of "all"
        # PAP and k_WFH around the chosen point, beta0 held at the chosen value (a variant may set it)
        ch = res["chosen"]["scalars"]
        GAP_GRID = {"pap": [float(x) for x in range(int(ch["pap"]) - 5, int(ch["pap"]) + 3)],
                    "wfh": [float(x) for x in range(int(ch["wfh"]) - 2, int(ch["wfh"]) + 3)]}
        research = []
        jobs = []
        for v in res["gap_sensitivity"]["variants"]:
            for p_ in GAP_GRID["pap"]:
                for w_ in GAP_GRID["wfh"]:
                    jobs += [{"label": f"{v['label']}|{p_:g}|{w_:g}",
                              "overrides": {**point_overrides(p_, PARK_FIXED, w_, ch["beta0"]), **v["overrides"]},
                              "seed": s, "scale": "calibrate"} for s in SEEDS]
        rows = run_jobs(jobs, args.workers, "gap")
        for v in res["gap_sensitivity"]["variants"]:
            pts_ = []
            for p_ in GAP_GRID["pap"]:
                for w_ in GAP_GRID["wfh"]:
                    pr = [r for r in rows if r["label"] == f"{v['label']}|{p_:g}|{w_:g}"]
                    sc = {"pap": p_, "park": PARK_FIXED, "wfh": w_,
                          "beta0": float(v["overrides"].get("wtt.beta0", ch["beta0"]))}
                    pts_.append({"label": point_label(sc), "scalars": sc,
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
                "source": PRE_FUEL_JSON.relative_to(ROOT).as_posix(), "chosen": old["chosen"]["scalars"],
                "chosen_mean": old["chosen"]["mean"], "structural_mean": old["structural_only"]["mean"],
                "grid": old["grid"], "grid_fine": old["search"]["grid_fine"],
                "n_points": len(old["search"]["points"]),
                "n_feasible": sum(bool(p["feasible"]) for p in old["search"]["points"]),
                "n_agents": int(old.get("n_agents", 300)),
                "oos_mean_6_12": old.get("out_of_sample", {}).get("chosen", {}).get("mean_6_12")}
        if SKIP25_JSON.exists():   # summary of the archived two-scalar calibration with SKIP 25 and no early start
            old = json.loads(SKIP25_JSON.read_text())
            res["skip25"] = {
                "source": SKIP25_JSON.relative_to(ROOT).as_posix(), "chosen": old["chosen"]["scalars"],
                "chosen_mean": old["chosen"]["mean"], "n_points": len(old["search"]["points"]),
                "n_feasible": sum(bool(p["feasible"]) for p in old["search"]["points"]),
                "n_agents": int(old.get("n_agents", 300)),
                "oos_mean_6_12": old.get("out_of_sample", {}).get("chosen", {}).get("mean_6_12")}
        res.pop("freeflow300", None)
        if FREEFLOW_JSON.exists():   # the archived state with 300 agents and free-flow roads
            res["freeflow300"] = archive_summary(FREEFLOW_JSON)
        if LAST_JSON.exists():   # the latest archived state (950 agents, congested roads, SKIP, no WTT)
            res["last"] = archive_summary(LAST_JSON)
        if PREV_JSON.exists():   # summary of the archived three-scalar calibration with fuel NZ$0.23/km
            old = json.loads(PREV_JSON.read_text())
            res["previous"] = {
                "source": PREV_JSON.relative_to(ROOT).as_posix(), "chosen": old["chosen"]["scalars"],
                "chosen_mean": old["chosen"]["mean"], "n_points": len(old["search"]["points"]),
                "n_feasible": sum(bool(p["feasible"]) for p in old["search"]["points"]),
                "n_agents": int(old.get("n_agents", 300)),
                "oos_mean_6_12": old.get("out_of_sample", {}).get("chosen", {}).get("mean_6_12")}
        res["chosen"]["on_grid_edge"] = on_grid_edge(ch, res["search"].get("beta0_values"))
        if res.get("gap_sensitivity"):
            res["gap_sensitivity"]["reading"] = GAP_READING
        res["selection_sensitivity"] = selection_sensitivity(res["search"]["points"])
        OUT_JSON.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
        write_report(res)
    print(f"done in {time.perf_counter() - t0:.0f}s -> {OUT_JSON.relative_to(ROOT)}, {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
