"""Cross-arm analysis and figures (PNG, 200 dpi, into runs/figures/). Owner: integrator.

    python -m cordonlite.analysis [--runs runs/] [--out runs/figures] [--include-netlogo]
                                  [--seed S] [--all] [--run-dirs DIR ...]
    python -m cordonlite.analysis --compare runs/R-clock_mock_py_s1 runs/R-clock_mock_netlogo_s1

By default only canonical runs are used: runs without a variant suffix (no --regime, --fee-start,
--peak-fee, --capacity-scale, --set, or non-default --n-agents/--days) of one seed (--seed, else the
seed with the most runs). --all includes every run, labelled with its differing settings; --run-dirs
takes an explicit list of run folders.

When the runs folder also holds runs at other peak charges (--peak-fee, folder suffix _peak<NZ$>; 0 =
no charge) of that seed, main() writes the fee-response outputs too: fee_response.csv / .md,
fee_response_by_group.csv and fee_response.png (how the willingness to travel into the city centre,
car use and congestion change with the charge level, days 21-30 against the no-charge run of the
same days). A run's peak is meta.fee_peak, else the maximum of its fees.csv (a run made before the
key existed); runs of the retired charge multiplier (fees.scale, suffix _fx<X>) are left out.

Commuters choose CAR, PT or WFH (SKIP was removed on 2026-10-09). A run made before then may hold
SKIP days: they still count in every share's denominator (all commuters), the tables just have no
SKIP column and the mode-share figure draws them as a separate layer.

Public API:
    discover_runs(runs_dir, include_netlogo=False, seed=None, include_all=False) -> dict[str, Path]
    load_run(run_dir: Path) -> dict[str, object]          # DataFrames for each run output + summary dict
    compare_runs(a: Path, b: Path) -> dict                 # byte and frame equality of two run folders
    summary_table(runs) -> pd.DataFrame                    # key numbers per run (day 10 vs day 30: mode shares,
                                                           # travel share car + PT; road delay, car
                                                           # door-to-door, LoS E/F share by V/C next to the
                                                           # mean V/C, LoS E/F by speed, AT congested share
                                                           # of motorways / other roads, days 6-10 vs 21-30)
    run_fee_peak(meta, run_dir) -> float                   # highest levied charge (meta, else fees.csv)
    run_charged(meta) -> bool                              # the run levies a charge (from fee_start_day)
    discover_fee_response_runs(runs_dir, seed=None, include_netlogo=False) -> dict[(arm, peak), Path]
    fee_response_table(runs, base=(6, 10), charged=(21, 30)) -> pd.DataFrame   # one row per arm x peak
                                                           # (days 21-30), changes against the peak-0 run
    fee_response_by_group(runs, archetype_labels=(), charged=(21, 30)) -> pd.DataFrame
                                                           # shares by archetype x company car, arm, peak
    fig_fee_response(table, out) -> Path                   # 2 x 3 panels against the peak charge
    road_delay_by_departure(run, days, bin_min=15) -> pd.DataFrame   # mean road delay by departure bin
    los_by_bin(run, days) -> pd.DataFrame                  # LoS E/F shares, AT congested, mean V/C by hour and group
    fig_mode_shares(runs, out) -> Path
    fig_crossings_hist(runs, out, days=(10, 30)) -> Path  # gate-exit (crossing) histograms, the runs' charge above
    fig_cordon_entries(runs, out) -> Path                  # entries per 15 min, the runs' fees.csv schedule(s) above
    fig_queue_delay(runs, out) -> Path                     # mean and peak queue delay by day
    fig_road_delay(runs, out) -> Path                      # mean road delay by departure time, days 6-10 vs 21-30
    fig_los(runs, out) -> Path                             # hourly % traffic at LoS E/F by V/C next to the mean
                                                           # V/C, LoS E/F by speed, AT congested, days 6-10 vs 21-30
    fig_calls_per_day(runs, out) -> Path
    table_who_adapts(run, base=(6, 10), end=(26, 30)) -> pd.DataFrame   # modal mode in two windows, twins excluded, Wilson CIs
    twin_summary(run) -> dict                              # twin divergence by day, conditional on the same day-10 option
    llm_diagnostics(run, rule_run=None) -> dict            # v3 7.5: cache hits, distinct prompts per A cell, entropy
    fig_who_adapts(runs, out) -> Path
    table_twins(run, day=11) -> pd.DataFrame
    fig_vickrey_check(run, cfg, out) -> Path
    main(argv=None) -> int

A single y-axis is used throughout; the ToU schedule is drawn in its own panel, not on a twin axis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import textwrap
from pathlib import Path
from typing import Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from cordonlite import fees as feesmod  # noqa: E402
from cordonlite import roads as roadsmod  # noqa: E402
from cordonlite.config import Config, load_config  # noqa: E402
from cordonlite.engine import FEES_FILE  # noqa: E402
from cordonlite.types import clock_str  # noqa: E402
from cordonlite.vickrey import equilibrium, queue_length  # noqa: E402

DPI = 200
# Categorical slots (validated reference palette, light mode), assigned in fixed order.
SLOTS = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
MODE_COLOURS = {"CAR": SLOTS[0], "PT": SLOTS[2], "WFH": SLOTS[3], "SKIP": SLOTS[1]}   # SKIP: runs before 2026-10-09
ARM_ORDER = ("R-daily", "R-clock", "L-clock", "L-daily")
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
MODES = ("CAR", "PT", "WFH")
OLD_MODE = "SKIP"          # removed on 2026-10-09; read from older runs only
# Shown wherever LoS E/F is reported (summary_table.md, fee_response.md, los.png, fee_response.png)
LOS_NOTE = ("LoS E/F by V/C and the mean V/C are shown together and are best read together. On other roads the "
            "V/C grade is E/F for about 99% of the traffic from 07:00, because their capacity is a BPR scale "
            "fitted to the TomTom congestion index (about 0.077 x the daily traffic count), not a lane capacity. "
            "On motorways about 76% of the vehicle-km is inside the fixed usual breakdown windows, which are "
            "graded F whatever the flow. LoS E/F by speed (at most 40% of free-flow speed) and the AT congested "
            "share (below 50%) grade the simulated speeds.")
OUTPUT_FILES = ("decisions.csv", "outcomes.csv", "profile.csv", "road_entries.csv", roadsmod.ROAD_LOS_FILE,
                roadsmod.LOS_SUMMARY_FILE, "personas.csv", "summary.json", "llm_calls.jsonl", "config_snapshot.toml")


# --------------------------------------------------------------------------- loading


def _label(run_dir: Path, summary: dict) -> str:
    m = summary["meta"]
    lab = m["arm"]
    if m["arm"].startswith("L-"):
        lab += " (mock)" if m.get("backend") == "mock" else " [API]"
    if m.get("traits") == "off":
        lab += " (traits off)"
    if m.get("engine") == "netlogo":
        lab += " [NetLogo]"
    if m.get("variant"):
        lab += f" {{{m['variant'].lstrip('_')}}}"
    return lab


def discover_runs(runs_dir: Path, include_netlogo: bool = False, seed: int | None = None,
                  include_all: bool = False) -> dict[str, Path]:
    """Run folders with a summary.json, labelled by arm; NetLogo duplicates skipped by default.

    Unless include_all, only canonical runs (meta.variant empty) of one seed are kept: ``seed``
    if given, else the seed with the most canonical runs. Labels that would repeat get the folder
    name appended."""
    found: list[tuple[tuple, str, Path, dict]] = []
    for d in sorted(Path(runs_dir).iterdir()):
        s = d / "summary.json"
        if not d.is_dir() or not s.exists():
            continue
        summ = json.loads(s.read_text())
        m = summ["meta"]
        if m.get("engine") == "netlogo" and not include_netlogo:
            continue
        arm_i = ARM_ORDER.index(m["arm"]) if m["arm"] in ARM_ORDER else 9
        key = (m.get("traits") == "off", m.get("engine") == "netlogo", arm_i, d.name)
        found.append((key, _label(d, summ), d, m))
    if not include_all:
        canon = [f for f in found if not f[3].get("variant")]
        if seed is None and canon:
            seeds = [f[3]["seed"] for f in canon]
            seed = max(sorted(set(seeds)), key=seeds.count)
        found = [f for f in canon if seed is None or f[3]["seed"] == seed]
    out: dict[str, Path] = {}
    for _k, lab, d, _m in sorted(found, key=lambda f: f[0]):
        if lab in out:
            lab = f"{lab} [{d.name}]"
        out[lab] = d
    return out


def load_run(run_dir: Path) -> dict[str, object]:
    """DataFrames for decisions, outcomes, profile, personas and los_summary (empty for a run made
    before the LoS outputs or with free-flow roads), plus summary and the config snapshot."""
    d = Path(run_dir)
    run: dict[str, object] = {"dir": d}
    for name in ("decisions", "outcomes", "profile", "personas"):
        run[name] = pd.read_csv(d / f"{name}.csv", keep_default_na=True)
    los = d / roadsmod.LOS_SUMMARY_FILE
    run["los_summary"] = (pd.read_csv(los) if los.exists()
                          else pd.DataFrame(columns=list(roadsmod.LOS_SUMMARY_COLUMNS)))
    run["summary"] = json.loads((d / "summary.json").read_text())
    run["days"] = pd.DataFrame(run["summary"]["days"])  # type: ignore[index]
    run["label"] = _label(d, run["summary"])  # type: ignore[arg-type]
    return run


def compare_runs(a: Path, b: Path) -> dict:
    """Equality of two run folders: sha256 of each output file plus frame equality of outcomes/profile.

    summary.json and config_snapshot.toml differ in the engine label only, so they are compared
    without it; the two folders must also hold the same set of files.
    """
    res: dict[str, object] = {"a": str(a), "b": str(b), "files": {}}
    ok = True
    names = [sorted(f.name for f in Path(x).iterdir()) for x in (a, b)]
    res["same_file_set"] = names[0] == names[1]
    ok &= bool(res["same_file_set"])
    for f in OUTPUT_FILES:
        pa, pb = Path(a) / f, Path(b) / f
        if f == "summary.json":
            sa, sb = json.loads(pa.read_text()), json.loads(pb.read_text())
            for s in (sa, sb):
                s["meta"].pop("engine", None)
            same = sa == sb
        elif f == "config_snapshot.toml":
            strip = [[ln for ln in x.read_text().splitlines() if not ln.startswith("engine = ")] for x in (pa, pb)]
            same = strip[0] == strip[1]
        else:
            if f == roadsmod.ROAD_ENTRIES_FILE:   # may be road_entries.csv.gz (run.compress_csv_over_mb)
                pa, pb = roadsmod.road_entries_path(Path(a)), roadsmod.road_entries_path(Path(b))
            same = (pa.name == pb.name and
                    hashlib.sha256(pa.read_bytes()).hexdigest() == hashlib.sha256(pb.read_bytes()).hexdigest())
        res["files"][f] = same  # type: ignore[index]
        ok &= same
    oa, ob = pd.read_csv(Path(a) / "outcomes.csv"), pd.read_csv(Path(b) / "outcomes.csv")
    res["outcomes_rows"] = len(oa)
    res["car_rows"] = int((oa["mode"] == "CAR").sum())
    res["outcomes_frame_equal"] = bool(oa.equals(ob))
    res["identical"] = bool(ok and res["outcomes_frame_equal"])
    return res


# --------------------------------------------------------------------------- tables


def _commuters(days: pd.DataFrame) -> pd.Series:
    """Commuters per summary.json day row: car + PT + WFH, plus SKIP in a run made before it was removed."""
    tot = days["cars"] + days["pt"] + days["wfh"]
    return tot + days["skip"] if "skip" in days else tot


def _share(days: pd.DataFrame, day: int, col: str) -> float:
    sub = days[days["day"] == day]
    return float(sub[col].iloc[0]) / float(_commuters(sub).iloc[0])


def _period_cars(run: dict, d0: int, d1: int) -> pd.DataFrame:
    """Car rows of days d0..d1 (served and unserved)."""
    o: pd.DataFrame = run["outcomes"]  # type: ignore[assignment]
    return o[(o["mode"] == "CAR") & (o["day"] >= d0) & (o["day"] <= d1)]


def _road_numbers(run: dict, d0: int, d1: int) -> dict[str, float]:
    """Mean road delay of car agents (served and unserved, as summary.json mean_road_delay) and mean
    door-to-door time of served cars over days d0..d1; road delay is nan for a run made before
    road congestion was modelled (no road_delay_min column)."""
    cars = _period_cars(run, d0, d1)
    served = cars[cars["gate_exit_min"] >= 0]
    rd = float(cars["road_delay_min"].mean()) if ("road_delay_min" in cars and len(cars)) else np.nan
    door = float((served["arrive_min"] - served["depart_min"]).mean()) if len(served) else np.nan
    return {"road": rd, "door": door}


LOS_POOLED = ("share_EF", "vc_mean", "share_EF_speed", "share_congested_AT")   # los_by_bin's pooled measures


def los_by_bin(run: dict, days: tuple[int, int], groups: Sequence[str] = ("motorway", "other")) -> pd.DataFrame:
    """Level of Service over days d0..d1 from los_summary.csv: per bin (roads.LOS_BINS) and group the
    share of traffic at LoS E/F (by V/C, share_EF; by speed, share_EF_speed), the share congested by
    Auckland Transport's definition (share_congested_AT) and the mean V/C, all pooled over the days by
    vehicle-km (each day's values are vehicle-km weighted, so this is the share of all the period's
    vehicle-km in that bin). Columns bin, group, share_EF, vc_mean, veh_km, share_EF_speed,
    share_congested_AT (nan for a run made before the speed-based columns); empty for a run without
    LoS outputs."""
    cols = ["bin", "group", "share_EF", "vc_mean", "veh_km", "share_EF_speed", "share_congested_AT"]
    ls = run.get("los_summary")
    if not isinstance(ls, pd.DataFrame) or len(ls) == 0:
        return pd.DataFrame(columns=cols)
    sub = ls[(ls["day"] >= days[0]) & (ls["day"] <= days[1]) & ls["group"].isin(list(groups))].copy()
    if len(sub) == 0:
        return pd.DataFrame(columns=cols)
    have = [c for c in LOS_POOLED if c in sub.columns]
    for c in have:
        sub[f"_{c}"] = sub[c] * sub["veh_km"]
    g = sub.groupby(["bin", "group"], sort=False)[[f"_{c}" for c in have] + ["veh_km"]].sum().reset_index()
    for c in LOS_POOLED:
        g[c] = g[f"_{c}"] / g["veh_km"] if c in have else np.nan
    order = {b[0]: i for i, b in enumerate(roadsmod.LOS_BINS)}
    gorder = {x: i for i, x in enumerate(groups)}
    g["_b"], g["_g"] = g["bin"].map(order), g["group"].map(gorder)
    g = g.sort_values(["_b", "_g"], kind="stable")
    return g[cols].reset_index(drop=True)


def summary_table(runs: Mapping[str, dict], days: tuple[int, int] = (10, 30),
                  periods: tuple[tuple[int, int], ...] = ((6, 10), (21, 30))) -> pd.DataFrame:
    """Key numbers per run: mode shares (car, PT, WFH; of all commuters, so a run made before SKIP was
    removed keeps its skippers in the denominator) and the travel share (car + PT: commuters going into
    the city centre) on two days, peak delay, revenue, decider calls; mean road delay before the gate,
    mean car door-to-door time and, over 07:00-09:00, the share of traffic at LoS E/F by V/C
    (los_ef_share) with the mean V/C (vc_mean) next to it, the share at LoS E/F by speed
    (los_ef_speed_share) and the share congested by Auckland Transport's definition
    (congested_at_share) of motorways and of other roads (los_by_bin: vehicle-km weighted; nan without
    LoS outputs) over each period (before / with the charge). main() writes LOS_NOTE under the table."""
    rows = []
    for lab, r in runs.items():
        dd: pd.DataFrame = r["days"]  # type: ignore[assignment]
        meta = r["summary"]["meta"]  # type: ignore[index]
        row: dict[str, object] = {"run": lab}
        for d in days:
            if d > dd["day"].max():
                continue
            rec = dd[dd["day"] == d].iloc[0]
            for c, n in (("cars", "car"), ("pt", "pt"), ("wfh", "wfh")):
                row[f"{n}_share_d{d}"] = round(_share(dd, d, c), 3)
            # willingness to travel: share of commuters going into the city centre (car or PT)
            row[f"travel_share_d{d}"] = round(_share(dd, d, "cars") + _share(dd, d, "pt"), 3)
            if "early_shift" in rec:   # share of all commuters working the early day (car or PT)
                row[f"early_shift_share_d{d}"] = round(_share(dd, d, "early_shift"), 3)
            row[f"peak_delay_d{d}"] = round(float(rec.get("peak_bin_delay_wmean", np.nan)), 1)
            row[f"peak_delay_worst_d{d}"] = round(float(rec["peak_bin_delay"]), 1)
            row[f"mean_delay_d{d}"] = round(float(rec["mean_queue_delay"]), 1)
            row[f"revenue_d{d}"] = round(float(rec["revenue"]), 2)
        for d0, d1 in periods:
            if d1 > dd["day"].max():
                continue
            num = _road_numbers(r, d0, d1)
            row[f"mean_road_delay_d{d0}_{d1}"] = round(num["road"], 2)
            row[f"car_door_to_door_d{d0}_{d1}"] = round(num["door"], 2)
            los = los_by_bin(r, (d0, d1))
            pk = los[los["bin"] == roadsmod.LOS_PEAK_BIN].set_index("group")
            for grp, tag in (("motorway", "mwy"), ("other", "other")):
                ok = grp in pk.index
                for key, col in (("los_ef_share", "share_EF"), ("vc_mean", "vc_mean"),
                                 ("los_ef_speed_share", "share_EF_speed"),
                                 ("congested_at_share", "share_congested_AT")):
                    row[f"{key}_{tag}_d{d0}_{d1}"] = round(float(pk.loc[grp, col]), 4) if ok else np.nan
        row["revenue_total"] = meta["revenue_total"]
        row["decider_calls_total"] = meta["decider_calls_total"]
        row["llm_decisions"] = meta["calls_total"]["llm"]
        row["llm_fallback_rule"] = meta["calls_total"]["llm-fallback-rule"]
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- fee response (charge levels)


# The peak charges (NZ$) of the comparison (2026-10-09): 0 (no charge, the counterfactual on the same days), 3 (AT's
# modelled NZ$3), 6 (the canonical runs: the SSC2026 schedule), 12, 18 and 30. Any _peak<NZ$> run is read.
FEE_RESPONSE_PEAKS: tuple[float, ...] = (0.0, 3.0, 6.0, 12.0, 18.0, 30.0)
FEE_RESPONSE_SHARES = (("cars", "car_share"), ("pt", "pt_share"), ("wfh", "wfh_share"))
_PEAK_VARIANT = re.compile(r"^_peak(\d+(?:\.\d+)?)$")    # run.py variant_suffix of a --peak-fee run
# fee_response.csv LoS columns over 07:00-09:00, side by side per road group: LoS E/F by speed, by V/C, mean V/C
FEE_RESPONSE_LOS = (("los_ef_speed_share", "share_EF_speed"), ("los_ef_share", "share_EF"), ("vc_mean", "vc_mean"))


def run_fee_peak(meta: Mapping, run_dir: Path) -> float:
    """Highest charge (NZ$) of a run's levied table: meta.fee_peak, else the maximum of its fees.csv
    (a run made before the key existed); nan when neither is there. A run of the retired charge
    multiplier also has meta.fee_scale, which is not needed (fee_peak already holds its peak)."""
    if meta.get("fee_peak") is not None:
        return float(meta["fee_peak"])
    p = Path(run_dir) / FEES_FILE
    return float(max(feesmod.read_fees_csv(p))) if p.exists() else float("nan")


def run_charged(meta: Mapping) -> bool:
    """True when a run levies a charge (from meta.fee_start_day): its regime is not "none" and its peak
    is above 0 (fees.peak_fee 0 levies nothing; a run without meta.fee_peak counts as charged)."""
    return (meta.get("fee_regime") != "none" and bool(meta.get("fee_start_day"))
            and (meta.get("fee_peak") is None or float(meta["fee_peak"]) > 0))


def discover_fee_response_runs(runs_dir: Path, seed: int | None = None,
                               include_netlogo: bool = False) -> dict[tuple[str, float], Path]:
    """Runs of the fee-response comparison, keyed (arm label, peak charge NZ$): per arm the canonical
    run (meta.variant empty; its peak from run_fee_peak, NZ$6) and the runs that differ from it in the
    peak charge only (variant "_peak<NZ$>", run.py --peak-fee, keyed by that value; 0 = the no-charge
    run). Every other variant is left out, the retired charge multiplier's "_fx<X>" runs too; so are
    traits-off runs, and NetLogo runs unless include_netlogo. One seed: ``seed`` if given, else the seed
    with the most canonical runs (as discover_runs). Ordered by arm (ARM_ORDER) and peak."""
    found: list[tuple[tuple, tuple[str, float], Path, int]] = []
    canon_seeds: list[int] = []
    for d in sorted(Path(runs_dir).iterdir()):
        s = d / "summary.json"
        if not d.is_dir() or not s.exists():
            continue
        m = json.loads(s.read_text())["meta"]
        if (m.get("engine") == "netlogo" and not include_netlogo) or m.get("traits") == "off":
            continue
        variant = m.get("variant") or ""
        if variant == "":
            peak = run_fee_peak(m, d)
            if np.isnan(peak):
                continue
            canon_seeds.append(int(m["seed"]))
        else:
            hit = _PEAK_VARIANT.match(variant)
            if hit is None:
                continue
            peak = float(hit.group(1))
        arm = _label(d, {"meta": {**m, "variant": ""}})
        arm_i = ARM_ORDER.index(m["arm"]) if m["arm"] in ARM_ORDER else 9
        found.append(((arm_i, arm, peak, d.name), (arm, round(float(peak), 4)), d, int(m["seed"])))
    if seed is None and canon_seeds:
        seed = max(sorted(set(canon_seeds)), key=canon_seeds.count)
    out: dict[tuple[str, float], Path] = {}
    for _k, key, d, s in sorted(found, key=lambda f: f[0]):
        if (seed is None or s == seed) and key not in out:
            out[key] = d
    return out


def _served_cars_by_day(run: dict) -> pd.Series:
    """Car cordon crossings (served cars, gate_exit_min >= 0) per day, every day of the run."""
    o: pd.DataFrame = run["outcomes"]  # type: ignore[assignment]
    dd: pd.DataFrame = run["days"]  # type: ignore[assignment]
    car = o[(o["mode"] == "CAR") & (o["gate_exit_min"].fillna(-1) >= 0)]
    return car.groupby("day").size().reindex(dd["day"].astype(int).tolist(), fill_value=0)


def _same_before_charge(run: dict, ref: dict) -> bool | None:
    """True when decisions.csv and outcomes.csv of the days before ``run``'s charge (days 1 to
    fee_start_day - 1) are the same in ``ref``: a run at another peak charge differs from the same arm's
    no-charge run only from the charge day on. None without a charge day."""
    meta = run["summary"]["meta"]  # type: ignore[index]
    fs = meta.get("fee_start_day")
    if meta.get("fee_regime") == "none" or not fs:
        return None
    for name in ("decisions", "outcomes"):
        a, b = (x[name] for x in (run, ref))
        a = a[a["day"] < fs].reset_index(drop=True)  # type: ignore[index]
        b = b[b["day"] < fs].reset_index(drop=True)  # type: ignore[index]
        # values, not dtypes: a column read from the whole file (e.g. triggers, empty in a no-charge run
        # and holding T2 in a charged one) can load as float in one run and as text in the other
        try:
            pd.testing.assert_frame_equal(a, b, check_dtype=False, check_exact=True)
        except AssertionError:
            return False
    return True


def _wtp_below(personas: pd.DataFrame, peak: float) -> float:
    """Share of commuters whose willingness to pay (personas.csv wtp_fee) is below ``peak``; nan for a
    run made before the willingness to pay (no wtp_fee column)."""
    if "wtp_fee" not in personas or len(personas) == 0:
        return float("nan")
    wtp = pd.to_numeric(personas["wtp_fee"], errors="coerce").astype(float)
    return round(float((wtp < float(peak)).mean()), 4)


def _window_numbers(run: dict, window: tuple[int, int], peak: float) -> dict[str, object] | None:
    """Fee-response numbers of one run over days window[0]..window[1] (None when the run is shorter):
    shares of all commuter-days, the willingness-to-travel diagnostics, crossings, delays, LoS and V/C
    (07:00-09:00) and revenue."""
    dd: pd.DataFrame = run["days"]  # type: ignore[assignment]
    d0, d1 = window
    if d1 > dd["day"].max():
        return None
    sub = dd[(dd["day"] >= d0) & (dd["day"] <= d1)]
    tot = float(_commuters(sub).sum())
    row: dict[str, object] = {"window": f"d{d0}-{d1}"}
    for c, name in FEE_RESPONSE_SHARES:
        row[name] = round(float(sub[c].sum()) / tot, 3)
    row["travel_share"] = round(float(sub["cars"].sum() + sub["pt"].sum()) / tot, 3)
    # willingness to travel: commuter-days with at least one / every car option removed (summary.json
    # wtt_limited, wtt_no_car), and commuters whose willingness to pay is below the peak charge
    for key, name in (("wtt_limited", "wtt_limited_share"), ("wtt_no_car", "wtt_no_car_share")):
        row[name] = round(float(sub[key].sum()) / tot, 4) if key in sub else np.nan
    row["wtp_below_peak_share"] = _wtp_below(run["personas"], peak)  # type: ignore[arg-type]
    row["car_crossings_per_day"] = round(float(_served_cars_by_day(run).loc[d0:d1].mean()), 1)
    row["mean_road_delay"] = round(_road_numbers(run, d0, d1)["road"], 2)
    pk_col = "peak_bin_delay_wmean" if "peak_bin_delay_wmean" in sub else "peak_bin_delay"
    row["peak_queue_delay"] = round(float(sub[pk_col].mean()), 2)
    row["peak_total_delay"] = (round(float(sub["peak_bin_total_delay_wmean"].mean()), 2)
                               if "peak_bin_total_delay_wmean" in sub else np.nan)
    los = los_by_bin(run, (d0, d1))
    pk = los[los["bin"] == roadsmod.LOS_PEAK_BIN].set_index("group")
    for grp, tag in (("motorway", "mwy"), ("other", "other")):
        for key, col in FEE_RESPONSE_LOS:
            row[f"{key}_{tag}"] = round(float(pk.loc[grp, col]), 4) if grp in pk.index else np.nan
    for grp, tag in (("motorway", "mwy"), ("other", "other")):
        row[f"congested_at_share_{tag}"] = (round(float(pk.loc[grp, "share_congested_AT"]), 4)
                                            if grp in pk.index else np.nan)
    row["revenue_per_day"] = round(float(sub["revenue"].mean()), 2)
    return row


def _fee_arms(runs: Mapping[tuple[str, float], dict]) -> dict[str, list[tuple[float, dict]]]:
    """Runs grouped by arm, each arm's runs sorted by peak charge."""
    arms: dict[str, list[tuple[float, dict]]] = {}
    for (arm, peak), r in runs.items():
        arms.setdefault(arm, []).append((float(peak), r))
    return {a: sorted(v, key=lambda x: x[0]) for a, v in arms.items()}


def _pct_change(now: float, ref: float) -> float:
    return round(100.0 * (now / ref - 1.0), 1) if ref and not np.isnan(ref) else np.nan


def fee_response_table(runs: Mapping[tuple[str, float], dict], base: tuple[int, int] = (6, 10),
                       charged: tuple[int, int] = (21, 30)) -> pd.DataFrame:
    """How behaviour and congestion respond to the peak charge: one row per arm and peak over the
    ``charged`` days (default 21-30).

    runs: loaded runs keyed (arm label, peak NZ$), as discover_fee_response_runs. Shares are of all
    commuter-days in the window (travel_share = car + PT: commuters going into the city centre).
    car_crossings_change_pct (the main measure) compares the mean car cordon crossings per day with
    the same arm's peak-0 run (no charge) on the same days, so only the charge differs;
    car_crossings_change_vs_own_d<b0>_<b1>_pct is the run's own change against its uncharged ``base``
    days (the before/after measure of the behaviour calibration). Willingness to travel:
    wtt_limited_share and wtt_no_car_share are the shares of commuter-days with at least one / every
    car option removed (its charge above the commuter's willingness to pay), wtp_below_peak_share the
    share of commuters whose willingness to pay is below the peak charge (company cars and commuters
    with neither PT nor WFH keep their car options all the same); nan for runs made before it.
    mean_road_delay is the mean road delay of car commuters (min); peak_queue_delay the mean over the
    days of the peak 15-min gate-queue delay (summary.json peak_bin_delay_wmean); peak_total_delay the
    same for gate queue + road delay (peak_bin_total_delay_wmean, the metric the capacity is
    calibrated to). The LoS columns are 07:00-09:00 shares of traffic, side by side for motorways (mwy)
    and other roads: at LoS E/F by speed (los_ef_speed_share), at LoS E/F by V/C (los_ef_share) with
    the mean V/C (vc_mean), and congested by AT's definition (nan without LoS outputs; see LOS_NOTE).
    revenue_per_day in NZ$. same_before_charge_as_peak0 says whether the days before the charge
    (decisions.csv and outcomes.csv) equal those of the arm's peak-0 run, as they must (same seed,
    no charge yet); None for the peak-0 run itself and for an arm without one."""
    rows = []
    own = f"car_crossings_change_vs_own_d{base[0]}_{base[1]}_pct"
    for arm, lst in _fee_arms(runs).items():
        ref = next((r for p, r in lst if p == 0.0), None)          # the arm's no-charge run
        ref_now = (float(_served_cars_by_day(ref).loc[charged[0]:charged[1]].mean())
                   if ref is not None and charged[1] <= ref["days"]["day"].max() else np.nan)  # type: ignore[index]
        for peak, r in lst:
            w = _window_numbers(r, charged, peak)
            if w is None:
                continue
            meta = r["summary"]["meta"]  # type: ignore[index]
            cross = _served_cars_by_day(r)
            now = float(cross.loc[charged[0]:charged[1]].mean())
            pre = float(cross.loc[base[0]:base[1]].mean())
            row: dict[str, object] = {"arm": arm, "seed": meta["seed"], "peak_fee": peak}
            row.update({k: w[k] for k in ("window", "car_share", "pt_share", "wfh_share", "travel_share",
                                          "wtt_limited_share", "wtt_no_car_share", "wtp_below_peak_share",
                                          "car_crossings_per_day")})
            row["car_crossings_change_pct"] = _pct_change(now, ref_now)
            row[own] = _pct_change(now, pre)
            row.update({k: v for k, v in w.items() if k not in row})
            row["same_before_charge_as_peak0"] = None if (ref is None or r is ref) else _same_before_charge(r, ref)
            row["run"] = Path(r["dir"]).name  # type: ignore[arg-type]
            rows.append(row)
    return pd.DataFrame(rows)


def fee_response_by_group(runs: Mapping[tuple[str, float], dict], archetype_labels: Sequence[str] = (),
                          charged: tuple[int, int] = (21, 30)) -> pd.DataFrame:
    """Mode shares, the travel share (car + PT) and the willingness-to-travel shares by archetype
    (personas.csv code, label from ``archetype_labels``, config persona.archetype_labels) x company car
    (the employer pays the charge, so the willingness to pay never removes its car options), per arm
    and peak over the ``charged`` days. Shares are of the cell's commuter-days (wtt_limited_share /
    wtt_no_car_share: at least one / every car option removed, decisions.csv; nan for runs made before
    the willingness to pay), wtp_below_peak_share of its commuters; n_agents counts its commuters."""
    rows = []
    d0, d1 = charged
    for arm, lst in _fee_arms(runs).items():
        for peak, r in lst:
            dd: pd.DataFrame = r["days"]  # type: ignore[assignment]
            if d1 > dd["day"].max():
                continue
            meta = r["summary"]["meta"]  # type: ignore[index]
            dec: pd.DataFrame = r["decisions"]  # type: ignore[assignment]
            per: pd.DataFrame = r["personas"]  # type: ignore[assignment]
            wcols = [c for c in ("wtt_removed", "wtt_all_removed") if c in dec]
            pcols = ["agent_id", "archetype", "company_car"] + (["wtp_fee"] if "wtp_fee" in per else [])
            w = dec[(dec["day"] >= d0) & (dec["day"] <= d1)][["agent_id", "mode", *wcols]].merge(
                per[pcols], on="agent_id", how="left")
            for (arch, cc), sub in w.groupby(["archetype", "company_car"], sort=True):
                i = int(arch)
                n = len(sub)
                row: dict[str, object] = {
                    "arm": arm, "seed": meta["seed"], "peak_fee": peak, "window": f"d{d0}-{d1}",
                    "archetype": i,
                    "archetype_label": archetype_labels[i - 1] if 1 <= i <= len(archetype_labels) else str(i),
                    "company_car": bool(cc), "n_agents": int(sub["agent_id"].nunique())}
                for m, (_c, name) in zip(MODES, FEE_RESPONSE_SHARES):
                    row[name] = round(float((sub["mode"] == m).sum()) / n, 3)
                row["travel_share"] = round(float(sub["mode"].isin(["CAR", "PT"]).sum()) / n, 3)
                row["wtt_limited_share"] = (round(float((sub["wtt_removed"] > 0).sum()) / n, 4)
                                            if "wtt_removed" in sub else np.nan)
                row["wtt_no_car_share"] = (round(float(sub["wtt_all_removed"].astype(bool).sum()) / n, 4)
                                           if "wtt_all_removed" in sub else np.nan)
                agents = per[per["agent_id"].isin(sub["agent_id"].unique())]
                row["wtp_below_peak_share"] = _wtp_below(agents, peak)
                rows.append(row)
    return pd.DataFrame(rows)


ARCHETYPE_SHORT = {1: "hybrid\noffice", 2: "on-site\noffice", 3: "shift/\nservice",
                   4: "trades\n(car only)", 5: "student"}


def wilson(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial share k/n (nan for n = 0)."""
    if n <= 0:
        return (np.nan, np.nan)
    ph = k / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * np.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def _twin_ids(per: pd.DataFrame) -> set[int]:
    from cordonlite.persona import TRAIT_NAMES

    a_cols = [c for c in per.columns if c not in ("agent_id", *TRAIT_NAMES)]
    groups = per.groupby(a_cols, dropna=False)["agent_id"].apply(lambda x: sorted(int(v) for v in x))
    return {i for ids in groups for i in ids[1:]}


def _modal_mode(dec: pd.DataFrame, d0: int, d1: int) -> pd.Series:
    """Most frequent mode per agent over days d0..d1 (ties: CAR, PT, WFH order; SKIP last in a run made
    before it was removed)."""
    w = dec[(dec["day"] >= d0) & (dec["day"] <= d1)]
    modes = list(MODES) + ([OLD_MODE] if (w["mode"] == OLD_MODE).any() else [])
    cnt = w.groupby(["agent_id", "mode"]).size().unstack(fill_value=0).reindex(columns=modes, fill_value=0)
    return cnt.idxmax(axis=1)


def table_who_adapts(run: dict, base: tuple[int, int] = (6, 10),
                     end: tuple[int, int] | None = None) -> pd.DataFrame:
    """Share of drivers (modal mode CAR over the ``base`` days) whose modal mode over the ``end``
    days (default: the last 5 days) is not CAR, by archetype, VoT quintile and each trait level.

    Twins (agents that copy another agent's Layer A) are excluded so no Layer A profile counts
    twice. Shares carry 95% Wilson intervals. Archetype 4 (car only: no PT, no WFH, so the willingness
    to pay never removes its car options) cannot leave the car: a structural zero, flagged in
    ``structural_zero`` (in a run made before SKIP was removed it could leave only by skipping)."""
    dec: pd.DataFrame = run["decisions"]  # type: ignore[assignment]
    per: pd.DataFrame = run["personas"]  # type: ignore[assignment]
    last = int(dec["day"].max())
    end = (max(1, last - 4), last) if end is None else end
    twins = _twin_ids(per)
    a = _modal_mode(dec, *base)
    b = _modal_mode(dec, *end)
    df = per[~per["agent_id"].isin(twins)].set_index("agent_id")[
        ["archetype", "vot_quintile", "H", "F", "P", "S", "must_drive"]].copy()
    df["car_base"] = (a.reindex(df.index) == "CAR")
    df["left_car"] = df["car_base"] & (b.reindex(df.index) != "CAR")
    rows = []
    for g in ("archetype", "vot_quintile", "H", "F", "P", "S"):
        for lv, sub in df.groupby(g):
            cars = sub[sub["car_base"]]
            n, k = len(cars), int(cars["left_car"].sum())
            lo, hi = wilson(k, n)
            rows.append({"group": g, "level": int(lv), "n": len(sub), "n_car_base": n,
                         "left_car_share": round(k / n, 3) if n else np.nan,
                         "ci_low": round(lo, 3), "ci_high": round(hi, 3),
                         "structural_zero": bool(g == "archetype" and len(sub) and sub["must_drive"].all()),
                         "base_days": f"{base[0]}-{base[1]}", "end_days": f"{end[0]}-{end[1]}"})
    return pd.DataFrame(rows)


def twin_summary(run: dict, days: Sequence[int] = (1, 10, 11, 12, 20, 30)) -> dict:
    """Twin pairs (identical Layer A): how many choose different options on each day, and on day
    11 how many differ among the pairs that held the same option on day 10 (same starting state)."""
    per: pd.DataFrame = run["personas"]  # type: ignore[assignment]
    dec: pd.DataFrame = run["decisions"]  # type: ignore[assignment]
    from cordonlite.persona import TRAIT_NAMES

    a_cols = [c for c in per.columns if c not in ("agent_id", *TRAIT_NAMES)]
    groups = per.groupby(a_cols, dropna=False)["agent_id"].apply(lambda x: sorted(int(v) for v in x))
    pairs = [(ids[0], j) for ids in groups if len(ids) > 1 for j in ids[1:]]
    opt = dec.set_index(["day", "agent_id"])["option_id"]
    last = int(dec["day"].max())
    out: dict[str, object] = {"run": run["label"], "n_pairs": len(pairs)}
    for d in days:
        if d <= last:
            out[f"differ_d{d}"] = int(sum(opt[(d, i)] != opt[(d, j)] for i, j in pairs))
    if 11 <= last:
        same10 = [(i, j) for i, j in pairs if opt[(10, i)] == opt[(10, j)]]
        out["same_d10"] = len(same10)
        out["differ_d11_given_same_d10"] = int(sum(opt[(11, i)] != opt[(11, j)] for i, j in same10))
    return out


def llm_diagnostics(run: dict, rule_run: dict | None = None) -> dict:
    """v3 section 7.5 heterogeneity diagnostics for an LLM arm (empty dict for a rule arm).

    cache hit rate and shared answers; distinct prompts / LLM-decided agents, overall and per Layer A
    cell (archetype x VoT quintile) on the first charged day; within-cell mode entropy on that
    day, and its ratio to the rule arm ``rule_run`` (flattening check, v3 10.4)."""
    meta = run["summary"]["meta"]  # type: ignore[index]
    if not meta["arm"].startswith("L-"):
        return {}
    log = Path(run["dir"]) / "llm_calls.jsonl"  # type: ignore[arg-type]
    recs = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
    final = {}
    for r in recs:  # last attempt per agent-day
        final[(r["day"], r["agent_id"])] = r
    per = run["personas"].set_index("agent_id")  # type: ignore[union-attr]
    fs = int(meta.get("fee_start_day") or 0)
    out: dict[str, object] = {
        "run": run["label"], "records": len(recs), "agent_days": len(final),
        "cache_hit_rate": round(float(np.mean([r["cache_hit"] for r in final.values()])), 4) if final else None,
        "shared_answers": int(sum(r.get("shared", False) for r in final.values())),
        "distinct_prompts_per_agent": round(len({r["cache_key"] for r in final.values()}) / len(final), 4) if final else None,
    }
    day_recs = [r for (d, _a), r in final.items() if d == fs]
    if day_recs:
        cells: dict[tuple, set] = {}
        n_cell: dict[tuple, int] = {}
        for r in day_recs:
            p = per.loc[r["agent_id"]]
            c = (int(p["archetype"]), int(p["vot_quintile"]))
            cells.setdefault(c, set()).add(r["cache_key"])
            n_cell[c] = n_cell.get(c, 0) + 1
        out[f"distinct_prompts_per_agent_in_cell_d{fs}"] = round(
            float(np.mean([len(cells[c]) / n_cell[c] for c in cells])), 4)

    def entropy(r: dict, day: int) -> float:
        dec = r["decisions"]
        pp = r["personas"].set_index("agent_id")
        sub = dec[dec["day"] == day].join(pp[["archetype", "vot_quintile"]], on="agent_id")
        hs, ws = [], []
        for _c, g in sub.groupby(["archetype", "vot_quintile"]):
            q = g["mode"].value_counts(normalize=True).to_numpy()
            hs.append(float(-(q * np.log2(q)).sum()))
            ws.append(len(g))
        return float(np.average(hs, weights=ws)) if ws else float("nan")
    if fs:
        h_llm = entropy(run, fs)
        out[f"within_cell_mode_entropy_d{fs}"] = round(h_llm, 4)
        if rule_run is not None:
            h_rule = entropy(rule_run, fs)
            out[f"within_cell_mode_entropy_d{fs}_rule"] = round(h_rule, 4)
            out["entropy_ratio_llm_over_rule"] = round(h_llm / h_rule, 4) if h_rule > 0 else None
    return out


def table_twins(run: dict, day: int = 11) -> pd.DataFrame:
    """Twin pairs (identical Layer A, own Layer B): traits, day-10 and day-`day` choices and reasons
    (empty for a run shorter than ``day`` days)."""
    from cordonlite.persona import TRAIT_NAMES

    per: pd.DataFrame = run["personas"]  # type: ignore[assignment]
    dec: pd.DataFrame = run["decisions"]  # type: ignore[assignment]
    if day > int(dec["day"].max()):
        return pd.DataFrame()
    a_cols = [c for c in per.columns if c not in ("agent_id", *TRAIT_NAMES)]
    groups = per.groupby(a_cols, dropna=False)["agent_id"].apply(lambda s: sorted(int(x) for x in s))
    d0 = dec[dec["day"] == day - 1].set_index("agent_id")
    d1 = dec[dec["day"] == day].set_index("agent_id")
    pt = per.set_index("agent_id")
    rows = []
    for ids in groups:
        if len(ids) < 2:
            continue
        orig = ids[0]
        for twin in ids[1:]:
            for role, aid in (("original", orig), ("twin", twin)):
                p = pt.loc[aid]
                rows.append({
                    "pair": f"{orig}-{twin}", "role": role, "agent_id": aid,
                    "archetype": int(p["archetype"]), "vot": round(float(p["vot"]), 2),
                    "tstar": clock_str(int(p["tstar_min"])),
                    "HFPS": "".join(str(int(p[t])) for t in TRAIT_NAMES),
                    f"option_d{day - 1}": d0.loc[aid, "option_id"],
                    f"option_d{day}": d1.loc[aid, "option_id"],
                    "decider": d1.loc[aid, "decider"],
                    "reason": d1.loc[aid, "reason"] if isinstance(d1.loc[aid, "reason"], str) else "",
                })
    out = pd.DataFrame(rows)
    if len(out):
        diff = out.groupby("pair")[f"option_d{day}"].nunique() > 1
        out["pair_differs"] = out["pair"].map(diff)
    return out


# --------------------------------------------------------------------------- figure helpers


def _style(ax: plt.Axes) -> None:
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=7)
    ax.title.set_color(INK)
    ax.xaxis.label.set_color(INK2)
    ax.yaxis.label.set_color(INK2)


def _events(ax: plt.Axes, meta: dict) -> None:
    if run_charged(meta):     # no line for regime "none" or peak charge 0
        ax.axvline(meta["fee_start_day"] - 0.5, color=INK2, linewidth=0.8, linestyle="--")
    dd = meta.get("pt_disruption_day")       # one day, or a list of days (2026-10-13)
    for d in (dd if isinstance(dd, list) else [dd]):
        if d and d <= meta.get("n_days", 0):
            ax.axvline(d, color=INK2, linewidth=0.8, linestyle=":")


def _grid(n: int, w: float = 3.4, h: float = 2.6) -> tuple[plt.Figure, np.ndarray]:
    ncol = min(n, 3) if n != 4 else 2
    nrow = int(np.ceil(n / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(w * ncol, h * nrow), squeeze=False)
    for ax in axes.flat[n:]:
        ax.set_visible(False)
    return fig, axes


def _save(fig: plt.Figure, out: Path, name: str) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    p = out / name
    fig.savefig(p, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return p


def _footnote(fig: plt.Figure, text: str, width: int = 160) -> None:
    """A note in small grey type along the bottom edge of the figure (leave room with tight_layout's rect)."""
    fig.text(0.01, 0.005, "\n".join(textwrap.wrap(text, width)), fontsize=6.5, color=INK2, ha="left", va="bottom")


def _arm_ls(lab: str) -> str:
    """Dashed for L-daily so it stays visible where it overlaps R-daily."""
    return "--" if lab.startswith("L-daily") else "-"


def _arm_colour(lab: str, i: int) -> str:
    base = lab.split(" ")[0]
    if base in ARM_ORDER and "traits off" not in lab:
        return SLOTS[ARM_ORDER.index(base)]
    return SLOTS[4 + (i % 4)]


# --------------------------------------------------------------------------- figures


def fig_mode_shares(runs: Mapping[str, dict], out: Path) -> Path:
    """Daily mode shares (car, PT, WFH), one stacked-area panel per run (dashed: charge starts; dotted:
    PT disruption). A run made before SKIP was removed draws its SKIP days as a fourth layer."""
    fig, axes = _grid(len(runs))
    for ax, (lab, r) in zip(axes.flat, runs.items()):
        dd: pd.DataFrame = r["days"]  # type: ignore[assignment]
        tot = _commuters(dd)
        cols = [("cars", "CAR"), ("pt", "PT"), ("wfh", "WFH")]
        if "skip" in dd and dd["skip"].sum() > 0:
            cols.append(("skip", OLD_MODE))
        ax.stackplot(dd["day"], *[dd[c] / tot for c, _m in cols], colors=[MODE_COLOURS[m] for _c, m in cols],
                     labels=[m if m != OLD_MODE else "SKIP (runs before 2026-10-09)" for _c, m in cols],
                     edgecolor="white", linewidth=0.6)
        _events(ax, r["summary"]["meta"])  # type: ignore[index]
        ax.set_ylim(0, 1)
        ax.set_xlim(dd["day"].min(), dd["day"].max())
        ax.set_title(lab, fontsize=9)
        ax.set_xlabel("day", fontsize=8)
        ax.set_ylabel("share of commuters", fontsize=8)
        _style(ax)
    legend: dict[str, object] = {}
    for ax in axes.flat:
        for h, l_ in zip(*ax.get_legend_handles_labels()):
            legend.setdefault(l_, h)
    fig.legend(list(legend.values()), list(legend), loc="lower center", ncol=4, frameon=False, fontsize=8,
               bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Daily mode shares by arm", fontsize=10, color=INK)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    return _save(fig, out, "mode_shares.png")


def _fee_tables(runs: Mapping[str, dict], cfg: Config) -> list[list[float]]:
    """The charge schedules to draw above the runs: each different non-zero fees.csv of the runs,
    highest peak first (with --all the _peak runs add theirs); the ToU schedule of ``cfg`` when no run
    has one (uncharged or older runs), at the SSC2026 peak when cfg charges nothing."""
    tables: list[list[float]] = []
    for r in runs.values():
        p = Path(r["dir"]) / FEES_FILE if r.get("dir") is not None else None
        tbl = feesmod.read_fees_csv(p) if p is not None and p.exists() else []
        if tbl and max(tbl) > 0 and tbl not in tables:
            tables.append(tbl)
    if tables:
        return sorted(tables, key=max, reverse=True)
    own = feesmod.fee_table_from_config(cfg, "tou")
    return [own if max(own) > 0 else feesmod.fee_table("tou", points=cfg.fees.tou_points)]


def _fee_panel(ax: plt.Axes, tables: Sequence[Sequence[float]], lo: int, hi: int) -> None:
    m = np.arange(lo, hi + 1)
    for tbl in tables:
        ax.plot(m, [tbl[i] for i in m], color=INK2, linewidth=1.5)
        if len(tables) > 1:   # several schedules: name each by its peak
            i = int(np.argmax([tbl[j] for j in m]))
            ax.text(m[i], tbl[m[i]], f"NZ${max(tbl):g}", fontsize=6, color=INK2, ha="center", va="bottom")
    ax.set_ylabel("charge NZ$", fontsize=7)
    ax.set_ylim(0, max(max(t) for t in tables) * 1.25)
    _style(ax)


def _clock_ticks(ax: plt.Axes, lo: int, hi: int, step: int = 60) -> None:
    t = list(range(lo - lo % step + (step if lo % step else 0), hi + 1, step))
    ax.set_xticks(t)
    ax.set_xticklabels([clock_str(x) for x in t])


X_LO, X_HI = 360, 615   # 06:00 to 10:15: no crossings happen after 10:00 in practice


def fig_crossings_hist(runs: Mapping[str, dict], out: Path, days: tuple[int, int] = (10, 30),
                       cfg: Config | None = None) -> Path:
    """Gate-exit (cordon-crossing) histograms, 15-min bins, day 10 vs day 30, one panel per run."""
    cfg = cfg or load_config()
    lo, hi = X_LO, X_HI
    bins = np.arange(lo, hi + 15, 15)
    n = len(runs)
    ncol = 2 if n == 4 else min(n, 3)
    nrow = int(np.ceil(n / ncol))
    fig = plt.figure(figsize=(3.6 * ncol, 3.0 * nrow + 0.9))
    gs = fig.add_gridspec(nrow + 1, ncol, height_ratios=[0.35] + [1.0] * nrow)
    tables = _fee_tables(runs, cfg)
    for c in range(ncol):
        _fee_panel(fig.add_subplot(gs[0, c]), tables, lo, hi)
        fig.axes[-1].set_xlim(lo, hi)
        _clock_ticks(fig.axes[-1], lo, hi)
        fig.axes[-1].set_title("ToU charge at crossing time", fontsize=8)
    cols = (SLOTS[0], SLOTS[1])
    for i, (lab, r) in enumerate(runs.items()):
        ax = fig.add_subplot(gs[1 + i // ncol, i % ncol])
        o: pd.DataFrame = r["outcomes"]  # type: ignore[assignment]
        for d, col in zip(days, cols):
            x = o[(o["day"] == d) & (o["mode"] == "CAR") & (o["gate_exit_min"] >= 0)]["gate_exit_min"]
            ax.hist(x, bins=bins, histtype="step", linewidth=2, color=col, label=f"day {d} ({len(x)} cars)")
        ax.set_xlim(lo, hi)
        _clock_ticks(ax, lo, hi)
        ax.set_title(lab, fontsize=9)
        ax.set_ylabel("cars crossing per 15 min", fontsize=8)
        ax.legend(fontsize=7, frameon=False)
        _style(ax)
    fig.suptitle("Cordon crossings (gate exits) before and after the charge", fontsize=10, color=INK)
    fig.tight_layout()
    return _save(fig, out, "crossings_hist.png")


def fig_cordon_entries(runs: Mapping[str, dict], out: Path, cfg: Config | None = None,
                       pre: tuple[int, int] = (6, 10), post: tuple[int, int] = (21, 30)) -> Path:
    """Cordon entries per 15 min (mean over pre-charge and post-charge days), one line per run,
    with the ToU schedule in a panel above (no twin axis)."""
    cfg = cfg or load_config()
    lo, hi = X_LO, X_HI
    fig, (axf, ax1, ax2) = plt.subplots(3, 1, figsize=(7.0, 7.0), sharex=True,
                                        gridspec_kw={"height_ratios": [0.4, 1, 1]})
    _fee_panel(axf, _fee_tables(runs, cfg), lo, hi)
    axf.set_title("ToU charge (from day %d)" % cfg.fees.fee_start_day, fontsize=9)
    for ax, (d0, d1), ttl in ((ax1, pre, "before the charge"), (ax2, post, "with the charge")):
        for i, (lab, r) in enumerate(runs.items()):
            dd: pd.DataFrame = r["days"]  # type: ignore[assignment]
            sub = dd[(dd["day"] >= d0) & (dd["day"] <= d1)]
            if len(sub) == 0:
                continue
            ent = pd.DataFrame(list(sub["entries_per_15min"])).mean()
            mins = [int(k[:2]) * 60 + int(k[3:]) for k in ent.index]
            ax.plot(np.array(mins) + 7.5, ent.to_numpy(), color=_arm_colour(lab, i), linewidth=2,
                    marker="o", markersize=3, label=lab)
        ax.set_title(f"Cordon entries per 15 min, mean of days {d0}-{d1} ({ttl})", fontsize=9)
        ax.set_ylabel("cars per 15 min", fontsize=8)
        if ax.lines:          # a run shorter than the period draws nothing
            ax.legend(fontsize=7, frameon=False, ncol=2)
        _style(ax)
    ax2.set_xlim(lo, hi)
    _clock_ticks(ax2, lo, hi)
    fig.tight_layout()
    return _save(fig, out, "cordon_entries.png")


def fig_queue_delay(runs: Mapping[str, dict], out: Path) -> Path:
    """Mean queue delay of cars, and the peak 15-min-bin mean delay by day: car-weighted mean over
    corridors (the calibrated metric, solid) and the worst corridor (thin dotted)."""
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.4))
    meta0 = None
    for i, (lab, r) in enumerate(runs.items()):
        dd: pd.DataFrame = r["days"]  # type: ignore[assignment]
        meta0 = r["summary"]["meta"]  # type: ignore[index]
        col = _arm_colour(lab, i)
        axes[0].plot(dd["day"], dd["mean_queue_delay"], color=col, linewidth=2, linestyle=_arm_ls(lab), label=lab)
        if "peak_bin_delay_wmean" in dd:
            axes[1].plot(dd["day"], dd["peak_bin_delay_wmean"], color=col, linewidth=2,
                         linestyle=_arm_ls(lab), label=lab)
        axes[1].plot(dd["day"], dd["peak_bin_delay"], color=col, linewidth=0.8, linestyle=":")
    for ax, t in zip(axes, ("Mean queue delay per car (min)",
                            "Peak 15-min mean delay (min): car-weighted mean of\ncorridors (solid, "
                            "calibrated metric); worst corridor (dotted)")):
        if meta0:
            _events(ax, meta0)
        ax.set_title(t, fontsize=9)
        ax.set_xlabel("day", fontsize=8)
        _style(ax)
    axes[0].legend(fontsize=7, frameon=False)
    fig.tight_layout()
    return _save(fig, out, "queue_delay.png")


def road_delay_by_departure(run: dict, days: tuple[int, int], bin_min: int = 15) -> pd.DataFrame:
    """Mean road delay (min, before the gate) of cars by departure-time bin over days d0..d1:
    columns bin_start, bin_mid, cars (car-days), mean_road_delay. Empty for a run without a
    road_delay_min column (made before road congestion was modelled)."""
    cars = _period_cars(run, *days)
    if "road_delay_min" not in cars or len(cars) == 0:
        return pd.DataFrame(columns=["bin_start", "bin_mid", "cars", "mean_road_delay"])
    b = (cars["depart_min"].astype(int) // bin_min) * bin_min
    g = cars.groupby(b)["road_delay_min"].agg(["size", "mean"]).reset_index()
    g.columns = ["bin_start", "cars", "mean_road_delay"]
    g["bin_mid"] = g["bin_start"] + bin_min / 2.0
    return g[["bin_start", "bin_mid", "cars", "mean_road_delay"]]


def fig_road_delay(runs: Mapping[str, dict], out: Path, pre: tuple[int, int] = (6, 10),
                   post: tuple[int, int] = (21, 30), bin_min: int = 15) -> Path:
    """Mean road delay before the gate by departure time (15-min bins, all corridors), mean over the
    pre-charge and the charged days, one panel per run. A run with free-flow roads shows 0; a run
    made before road congestion was modelled has no road delay and is marked so."""
    fig, axes = _grid(len(runs), w=3.6, h=2.8)
    cols = (SLOTS[0], SLOTS[1])
    lo, hi = X_LO, X_HI
    tables: dict[str, list[tuple[tuple[int, int], str, pd.DataFrame]]] = {}
    for lab, r in runs.items():
        last = int(r["days"]["day"].max())  # type: ignore[index]
        tables[lab] = [((d0, d1), col, road_delay_by_departure(r, (d0, d1), bin_min))
                       for (d0, d1), col in zip((pre, post), cols) if d1 <= last]
    ymax = max([1.0] + [float(t["mean_road_delay"].max()) for v in tables.values() for _p, _c, t in v if len(t)])
    for ax, (lab, r) in zip(axes.flat, runs.items()):
        drawn = False
        for (d0, d1), col, t in tables[lab]:
            if len(t) == 0:
                continue
            mean = float(_road_numbers(r, d0, d1)["road"])
            ax.plot(t["bin_mid"], t["mean_road_delay"], color=col, linewidth=2, marker="o", markersize=3,
                    label=f"days {d0}-{d1} (mean {mean:.1f} min)")
            drawn = True
        if not drawn:
            ax.text(0.5, 0.5, "no road delay recorded", transform=ax.transAxes, ha="center",
                    va="center", fontsize=8, color=INK2)
        ax.set_xlim(lo, hi)
        ax.set_ylim(0, ymax * 1.15)      # one scale for every panel
        _clock_ticks(ax, lo, hi)
        ax.set_title(lab, fontsize=9)
        ax.set_xlabel("leaving home", fontsize=8)
        ax.set_ylabel("mean road delay (min)", fontsize=8)
        if drawn:
            ax.legend(fontsize=7, frameon=False, loc="upper left")
        _style(ax)
    fig.suptitle("Road delay before the cordon gate by departure time (all corridors; "
                 f"{bin_min}-min bins)", fontsize=10, color=INK)
    fig.tight_layout()
    return _save(fig, out, "road_delay.png")


LOS_GROUP_STYLE = {"motorway": ("motorways", SLOTS[0]), "other": ("other roads", SLOTS[1])}


def fig_los(runs: Mapping[str, dict], out: Path, pre: tuple[int, int] = (6, 10),
            post: tuple[int, int] = (21, 30)) -> Path:
    """Level of Service of the road sections on the commuters' routes by hour (06-07 .. 09-10;
    los_by_bin), one row per run, four panels: the % of traffic (vehicle-km) at LoS E/F by V/C (HCM 1994
    bands as SSC2026) next to the vehicle-km weighted mean V/C it grades, then at LoS E/F by speed (HCM
    2010 urban street bands on the speed factor) and congested by Auckland Transport's definition
    (below 50% of free-flow speed); motorways and other roads, days pre (solid) and post (dashed).
    LOS_NOTE is printed under the panels. A run without LoS outputs (free-flow roads, or made before
    them; or before the speed-based columns) is marked so."""
    hours = [b for b in roadsmod.LOS_BINS if b[0] != roadsmod.LOS_PEAK_BIN]
    xs = [(a + b) / 2 / 60 for _l, a, b in hours]
    n = max(1, len(runs))
    panels = (("share_EF", "LoS E/F by V/C (HCM 1994, as SSC2026)"),
              ("vc_mean", "mean V/C (dotted line: V/C = 1)"),
              ("share_EF_speed", "LoS E/F by speed (at most 40% of free flow)"),
              ("share_congested_AT", "congested (AT: below 50% of free flow)"))
    fig, axes = plt.subplots(n, len(panels), figsize=(15.0, 2.8 * n + 1.1), squeeze=False)
    vmax = 1.0
    tabs = {}
    for lab, r in runs.items():
        last = int(r["days"]["day"].max())  # type: ignore[index]
        tabs[lab] = [((d0, d1), ls, los_by_bin(r, (d0, d1))) for (d0, d1), ls in ((pre, "-"), (post, "--"))
                     if d1 <= last]
        for _p, _ls, t in tabs[lab]:
            if len(t):
                vmax = max(vmax, float(t["vc_mean"].max()))
    for row, (lab, _r) in zip(axes, runs.items()):
        drawn = [False] * len(panels)
        for (d0, d1), ls, t in tabs[lab]:
            for grp, (name, col) in LOS_GROUP_STYLE.items():
                sub = t[t["group"] == grp].set_index("bin").reindex([h[0] for h in hours])
                kw = dict(color=col, linestyle=ls, linewidth=2, marker="o", markersize=4,
                          label=f"{name}, days {d0}-{d1}")
                for k, (col_name, _ttl) in enumerate(panels):
                    y = sub[col_name].to_numpy(dtype=float)
                    if np.isnan(y).all():
                        continue
                    row[k].plot(xs, y if col_name == "vc_mean" else 100 * y, **kw)
                    drawn[k] = True
        for k, ax in enumerate(row):
            if not drawn[k]:
                ax.text(0.5, 0.5, "not recorded in this run", transform=ax.transAxes, ha="center",
                        va="center", fontsize=8, color=INK2)
            if panels[k][0] == "vc_mean":
                ax.set_ylim(0, vmax * 1.1)
                ax.axhline(1.0, color=INK2, linewidth=0.8, linestyle=":")
                ax.set_ylabel("mean V/C", fontsize=8)
            else:
                ax.set_ylim(0, 105)
                ax.set_ylabel(f"{lab}: % of traffic" if k == 0 else "% of traffic", fontsize=8)
            ax.set_xticks(xs)
            ax.set_xticklabels([h[0] for h in hours], fontsize=7)
            ax.set_xlim(xs[0] - 0.4, xs[-1] + 0.4)
            ax.set_title(panels[k][1], fontsize=9)
            _style(ax)
        if drawn[0]:
            row[0].legend(fontsize=7, frameon=False, loc="lower center")
    fig.suptitle("Level of Service on the commuters' routes by hour (vehicle-km weighted)", fontsize=10, color=INK)
    _footnote(fig, LOS_NOTE, width=200)
    fig.tight_layout(rect=(0, 0.35 / (2.8 * n + 1.1), 1, 1))
    return _save(fig, out, "los.png")


# One panel each: title, the series (column, line style, marker, legend text), y label, multiplier, top of the
# y-axis (None: from the data). The arms differ in colour, the series of a panel in line style and marker.
FEE_RESPONSE_PANELS = (
    ("(a) mode shares", (("car_share", "-", "o", "car"), ("pt_share", "--", "s", "PT"),
                         ("wfh_share", ":", "^", "WFH")), "share of commuters", 1.0, 1.05),
    ("(b) travel share and willingness to pay", (
        ("travel_share", "-", "o", "travel share: car + PT"),
        ("wtp_below_peak_share", "--", "s", "willingness to pay below the peak charge")),
     "share of commuters", 1.0, 1.05),
    ("(c) delay of cars", (("mean_road_delay", "-", "o", "mean road delay"),
                           ("peak_queue_delay", "--", "s", "peak 15-min gate-queue delay")), "minutes", 1.0, None),
    ("(d) traffic at LoS E/F, 07:00-09:00", (
        ("los_ef_speed_share_mwy", "-", "o", "by speed, motorways"),
        ("los_ef_speed_share_other", "--", "o", "by speed, other roads"),
        ("los_ef_share_mwy", "-.", "s", "by V/C, motorways"),
        ("los_ef_share_other", ":", "s", "by V/C, other roads")), "% of traffic (vehicle-km)", 100.0, 105.0),
    ("(e) mean V/C, 07:00-09:00", (("vc_mean_mwy", "-", "o", "motorways"), ("vc_mean_other", "--", "s", "other roads")),
     "mean V/C (vehicle-km weighted)", 1.0, None),
    ("(f) charge revenue", (("revenue_per_day", "-", "o", "revenue per day"),), "NZ$ per day", 1.0, None),
)


def fig_fee_response(table: pd.DataFrame, out: Path) -> Path:
    """Response to the peak charge (fee_response_table) over the charged days (21-30), one line per arm
    against the peak charge (0 = the no-charge run of the same days): (a) car, PT and WFH shares, (b)
    travel share (car + PT) and the share of commuters whose willingness to pay is below the peak
    charge, (c) mean road delay and peak 15-min gate-queue delay, (d) traffic at LoS E/F by speed and by
    V/C on motorways and other roads, (e) mean V/C on motorways and other roads, (f) revenue per day.
    One y-axis per panel: a panel's series share its unit and differ in line style (legend in the
    panel), the arms in colour (legend below). LOS_NOTE is printed under the panels."""
    fig, axes = plt.subplots(2, 3, figsize=(14.0, 8.4))
    arms = list(dict.fromkeys(table["arm"])) if len(table) else []
    arms.sort(key=lambda a: ARM_ORDER.index(a.split(" ")[0]) if a.split(" ")[0] in ARM_ORDER else 9)
    xs = sorted({float(x) for x in table["peak_fee"]}) if len(table) else [0.0]
    w = table["window"] if len(table) else pd.Series(dtype=object)
    days = "days " + str(w.iloc[0]).lstrip("d") if len(w) else "days 21-30"
    for ax, (title, series, ylab, mult, top) in zip(axes.flat, FEE_RESPONSE_PANELS):
        ymax = 0.0
        styles = []
        for i, arm in enumerate(arms):
            sub = table[table["arm"] == arm].sort_values("peak_fee", kind="stable")
            for col, ls, mk, _txt in series:
                if col not in sub:
                    continue
                y = mult * sub[col].to_numpy(dtype=float)
                if np.isnan(y).all():
                    continue
                ax.plot(sub["peak_fee"], y, color=_arm_colour(arm, i), linestyle=ls, linewidth=2, marker=mk,
                        markersize=4.5, label=arm)
                ymax = max(ymax, float(np.nanmax(y)))
                if (col, ls, mk, _txt) not in styles:
                    styles.append((col, ls, mk, _txt))
        if not ax.lines:
            ax.text(0.5, 0.5, "not recorded in these runs", transform=ax.transAxes, ha="center",
                    va="center", fontsize=8, color=INK2)
        elif len(series) > 1:   # which line style is which measure (long handles: a short one hides the dashes)
            proxies = [plt.Line2D([], [], color=INK2, linestyle=ls, marker=mk, markersize=4, linewidth=1.5)
                       for _c, ls, mk, _t in styles]
            ax.legend(proxies, [t for _c, _l, _m, t in styles], fontsize=6.5, frameon=False, loc="best",
                      handlelength=5.0)
        if title.startswith("(e)"):
            ax.axhline(1.0, color=INK2, linewidth=0.8, linestyle=":")
            ymax = max(ymax, 1.0)
        ax.set_ylim(0, top if top is not None else (ymax * 1.15 if ymax > 0 else 1.0))
        ax.set_xticks(xs)
        ax.set_xticklabels([f"{x:g}" for x in xs], fontsize=7)
        ax.set_xlabel(f"peak charge, NZ$ ({days}; 0 = no charge)", fontsize=8)
        ax.set_ylabel(ylab, fontsize=8)
        ax.set_title(title, fontsize=9)
        _style(ax)
    legend: dict[str, object] = {}
    for i, arm in enumerate(arms):
        legend[arm] = plt.Line2D([], [], color=_arm_colour(arm, i), linewidth=3)
    if legend:
        fig.legend(list(legend.values()), list(legend), loc="lower center", ncol=min(len(legend), 4),
                   frameon=False, fontsize=8, bbox_to_anchor=(0.5, 0.05))
    fig.suptitle(f"Response to the peak charge, {days} (the ToU schedule scaled to each "
                 "peak; 0 = the no-charge run of the same days)\nBehaviour is calibrated at the NZ$6 schedule, "
                 "other peaks extrapolate; the L arms use MockLLM, a pipeline check, not an LLM",
                 fontsize=10, color=INK)
    _footnote(fig, LOS_NOTE, width=190)
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    return _save(fig, out, "fee_response.png")


def fig_calls_per_day(runs: Mapping[str, dict], out: Path) -> Path:
    """Decider calls per day (rule, LLM and fallback; standing days excluded), log scale."""
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    meta0 = None
    for i, (lab, r) in enumerate(runs.items()):
        dd: pd.DataFrame = r["days"]  # type: ignore[assignment]
        meta0 = r["summary"]["meta"]  # type: ignore[index]
        calls = [c["rule"] + c["llm"] + c["llm-fallback-rule"] for c in dd["calls"]]
        tot = sum(calls)
        ax.plot(dd["day"], np.maximum(calls, 0.8), color=_arm_colour(lab, i), linewidth=2,
                linestyle=_arm_ls(lab), marker="o", markersize=3, label=f"{lab} (total {tot})")
    if meta0:
        _events(ax, meta0)
    ax.set_yscale("log")
    ax.set_ylabel("decider calls per day (log)", fontsize=8)
    ax.set_xlabel("day", fontsize=8)
    ax.set_title("Decider calls per day: daily arms vs cognitive clock (0 drawn at 0.8)", fontsize=9)
    ax.legend(fontsize=7, frameon=False)
    _style(ax)
    fig.tight_layout()
    return _save(fig, out, "calls_per_day.png")


def fig_who_adapts(runs: Mapping[str, dict], out: Path) -> Path:
    """Share of drivers (modal mode CAR on days 6-10) not driving (modal mode, last 5 days), by
    group and level, per run, with 95% Wilson intervals; groups with n < 10 drivers are greyed
    out and annotated, structural zeros (car only) marked."""
    groups = ("archetype", "vot_quintile", "H", "F", "P", "S")
    titles = {"archetype": "archetype", "vot_quintile": "VoT quintile", "H": "habit H",
              "F": "flexibility F", "P": "PT openness P", "S": "cost salience S"}
    tabs = {lab: table_who_adapts(r) for lab, r in runs.items()}
    fig, axes = plt.subplots(2, 3, figsize=(11.5, 6.2))
    k = len(runs)
    w = 0.8 / max(k, 1)
    for ax, g in zip(axes.flat, groups):
        for i, (lab, t) in enumerate(tabs.items()):
            sub = t[t["group"] == g]
            x = sub["level"].to_numpy() + (i - (k - 1) / 2) * w
            y = sub["left_car_share"].to_numpy(dtype=float)
            small = sub["n_car_base"].to_numpy() < 10
            col = _arm_colour(lab, i)
            ax.bar(x[~small], np.nan_to_num(y[~small]), width=w * 0.9, color=col, label=lab,
                   edgecolor="white", linewidth=0.5)
            ax.bar(x[small], np.nan_to_num(y[small]), width=w * 0.9, color=col, alpha=0.25,
                   edgecolor="white", linewidth=0.5)
            err = np.vstack([y - sub["ci_low"].to_numpy(dtype=float), sub["ci_high"].to_numpy(dtype=float) - y])
            ax.errorbar(x, y, yerr=np.nan_to_num(err), fmt="none", ecolor=INK2, elinewidth=0.6, capsize=1.5)
            if i == 0:
                for lv, n, sz in zip(sub["level"], sub["n_car_base"], sub["structural_zero"]):
                    txt = "car only" if sz else f"n={n}"
                    ax.text(lv, 1.02, txt, ha="center", va="bottom", fontsize=5.5, color=INK2)
        ax.set_title(titles[g], fontsize=9, pad=12)
        ax.set_ylim(0, 1.1)
        ax.set_xticks([1, 2, 3, 4, 5])
        if g == "archetype":
            ax.set_xticklabels([ARCHETYPE_SHORT[i] for i in range(1, 6)], fontsize=6)
        _style(ax)
    for a in (axes.flat[0], axes.flat[3]):
        a.set_ylabel("share of drivers (days 6-10)\nnot driving (last 5 days)", fontsize=8)
    h, l_ = axes.flat[0].get_legend_handles_labels()
    fig.legend(h, l_, loc="lower center", ncol=min(k, 6), frameon=False, fontsize=8, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Who adapts: leaving the car by persona group (twins excluded; 95% Wilson intervals; "
                 "pale bars: fewer than 10 drivers; n = drivers of the first run)", fontsize=9, color=INK)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return _save(fig, out, "who_adapts.png")


def fig_vickrey_check(run: dict, cfg: Config, out: Path, days: tuple[int, int] = (6, 10)) -> Path:
    """Simulated queue length at the busiest corridor (pre-charge days) against the analytical
    Vickrey no-toll equilibrium for the same N and capacity (homogeneous commuters, mean VoT,
    Small 1982 ratios, t* at the gate = median of the drivers' t* minus gate-to-destination time)."""
    prof: pd.DataFrame = run["profile"]  # type: ignore[assignment]
    o: pd.DataFrame = run["outcomes"]  # type: ignore[assignment]
    per: pd.DataFrame = run["personas"]  # type: ignore[assignment]
    meta = run["summary"]["meta"]  # type: ignore[index]
    d0, d1 = days
    cars = o[(o["mode"] == "CAR") & (o["day"] >= d0) & (o["day"] <= d1)]
    busiest = int(cars["corridor_id"].value_counts().idxmax())
    s = float(meta["capacity_per_min"][str(busiest)])
    N = float((cars["corridor_id"] == busiest).sum()) / (d1 - d0 + 1)
    ids = cars[cars["corridor_id"] == busiest]["agent_id"].unique()
    pp = per[per["agent_id"].isin(ids)]
    tstar_gate = float(np.median(pp["tstar_min"] - pp["fftt_gate_to_dest_min"]))
    alpha = float(pp["vot"].mean()) / 60.0
    res = equilibrium(N, s, alpha, cfg.costs.beta_ratio * alpha, cfg.costs.gamma_ratio * alpha, tstar_gate)
    fig, ax = plt.subplots(figsize=(6.8, 3.6))
    p = prof[(prof["corridor_id"] == busiest) & (prof["day"] >= d0) & (prof["day"] <= d1)]
    for d, sub in p.groupby("day"):
        ax.plot(sub["minute"], sub["queue_len"], color=SLOTS[0], linewidth=1, alpha=0.45,
                label="simulated, days %d-%d" % (d0, d1) if d == d0 else None)
    t = np.linspace(res.t_first - 10, res.t_last + 10, 400)
    ax.plot(t, queue_length(res, t), color=SLOTS[1], linewidth=2,
            label=f"Vickrey equilibrium, one t* (N={N:.0f}, s={s:.2f}/min)")
    ax.set_xlim(360, 690)
    _clock_ticks(ax, 360, 690)
    ax.set_ylabel("queue length (cars)", fontsize=8)
    name = meta["corridor_names"][str(busiest)]
    ax.set_title(f"{run['label']}: corridor {busiest} {name}\nrush length N/s = {res.rush_len:.0f} min, "
                 f"equilibrium cost delta*N/s = NZ${res.cost_per_commuter:.2f}", fontsize=8)
    ax.legend(fontsize=7, frameon=False)
    _style(ax)
    fig.tight_layout()
    return _save(fig, out, "vickrey_check.png")


# --------------------------------------------------------------------------- CLI


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines) + "\n"


FEE_RESPONSE_FILES = ("fee_response.csv", "fee_response.md", "fee_response_by_group.csv", "fee_response.png")


def _write_fee_response(runs_dir: Path, out: Path, cfg: Config, seed: int | None, include_netlogo: bool,
                        loaded: Mapping[str, dict] | None = None, base: tuple[int, int] = (6, 10),
                        charged: tuple[int, int] = (21, 30)) -> list[Path]:
    """fee_response.csv / .md, fee_response_by_group.csv and fee_response.png when the runs folder
    holds runs at other peak charges (_peak<NZ$>, discover_fee_response_runs) that reach the last
    ``charged`` day; otherwise the files of an earlier analysis are removed and nothing is written.
    Runs already in ``loaded`` are reused."""
    found = discover_fee_response_runs(runs_dir, seed, include_netlogo)
    have = {Path(r["dir"]).resolve(): r for r in (loaded or {}).values()}  # type: ignore[arg-type]
    fr_runs = {k: have.get(d.resolve()) or load_run(d) for k, d in found.items()}
    fr = (fee_response_table(fr_runs, base, charged)
          if any(r["summary"]["meta"].get("variant") for r in fr_runs.values()) else pd.DataFrame())  # type: ignore[index]
    if len(fr) == 0:   # no run at another peak, or none reaching the last charged day
        for f in FEE_RESPONSE_FILES:
            (out / f).unlink(missing_ok=True)
        return []
    out.mkdir(parents=True, exist_ok=True)
    fr.to_csv(out / "fee_response.csv", index=False)
    if (fr["same_before_charge_as_peak0"] == False).any():  # noqa: E712 (None for the peak-0 rows)
        print("WARNING: a run at another peak charge differs from the same arm's peak-0 run before the charge "
              "(fee_response.csv, same_before_charge_as_peak0)", file=sys.stderr)
    own = f"car_crossings_change_vs_own_d{base[0]}_{base[1]}_pct"
    (out / "fee_response.md").write_text(
        _md_table(fr) + "\n"
        f"One row per arm and peak charge (peak_fee, NZ$: the ToU schedule scaled to that peak, charged from the "
        f"charge day) over days {charged[0]}-{charged[1]}. Peak 0 is the no-charge run of the same arm and seed "
        "(run.py --peak-fee 0). car_crossings_change_pct, the main measure, compares the car cordon crossings per "
        f"day with that run on the same days, so only the charge differs; {own} is the run's own change against "
        f"its uncharged days {base[0]}-{base[1]} (the before/after measure the behaviour calibration targets), "
        "which also holds what changes over the days without a charge. same_before_charge_as_peak0 checks that "
        "decisions.csv and outcomes.csv of the days before the charge equal the peak-0 run's, as they must (same "
        "seed, no charge yet). travel_share = car + PT, the share of commuters going into the city centre.\n\n"
        "Willingness to travel: wtt_limited_share and wtt_no_car_share are the shares of commuter-days with at "
        "least one and with every car option removed because its charge was above the commuter's willingness to "
        "pay; wtp_below_peak_share is the share of commuters whose willingness to pay is below the peak charge "
        "(company cars and commuters with neither PT nor WFH keep their car options all the same). Delays in "
        "minutes: mean_road_delay of car commuters; peak_queue_delay the peak 15-min gate-queue delay; "
        "peak_total_delay the peak 15-min gate-queue + road delay, the metric the capacity is calibrated to "
        "(15 min without a charge). LoS over 07:00-09:00, mwy = motorways, other = other roads: "
        "los_ef_speed_share = share of traffic at LoS E/F by speed, los_ef_share = at LoS E/F by V/C, vc_mean = "
        "the mean V/C, congested_at_share = congested by AT's definition. " + LOS_NOTE + "\n\n"
        "Behaviour is calibrated at the NZ$6 schedule; other peaks extrapolate. The L arms use MockLLM (mock), "
        "a pipeline check, not an LLM.\n")
    fee_response_by_group(fr_runs, cfg.persona.archetype_labels, charged).to_csv(
        out / "fee_response_by_group.csv", index=False)
    return [out / "fee_response.csv", out / "fee_response_by_group.csv", fig_fee_response(fr, out)]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m cordonlite.analysis")
    ap.add_argument("--runs", default=None, help="runs folder (default run.runs_dir)")
    ap.add_argument("--out", default=None, help="figures folder (default <runs>/figures)")
    ap.add_argument("--include-netlogo", action="store_true")
    ap.add_argument("--seed", type=int, default=None, help="seed of the canonical runs (default: most runs)")
    ap.add_argument("--all", action="store_true", help="include variant runs (labelled by their settings)")
    ap.add_argument("--run-dirs", nargs="+", default=None, help="explicit run folders instead of discovery")
    ap.add_argument("--compare", nargs=2, metavar=("RUN_A", "RUN_B"), default=None)
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.compare:
        res = compare_runs(Path(args.compare[0]), Path(args.compare[1]))
        print(json.dumps(res, indent=1))
        return 0 if res["identical"] else 1
    runs_dir = Path(args.runs) if args.runs else cfg.resolve_path(cfg.run.runs_dir)
    out = Path(args.out) if args.out else runs_dir / "figures"
    if args.run_dirs:
        found = {}
        for d in args.run_dirs:
            lab = _label(Path(d), json.loads((Path(d) / "summary.json").read_text()))
            found[lab if lab not in found else f"{lab} [{Path(d).name}]"] = Path(d)
    else:
        found = discover_runs(runs_dir, args.include_netlogo, args.seed, args.all)
    if not found:
        print(f"no runs with summary.json under {runs_dir}", file=sys.stderr)
        return 1
    runs = {lab: load_run(d) for lab, d in found.items()}
    main_runs = {k: v for k, v in runs.items() if "traits off" not in k} or runs
    out.mkdir(parents=True, exist_ok=True)
    written = [
        fig_mode_shares(runs, out),
        fig_crossings_hist(main_runs, out, cfg=cfg),
        fig_cordon_entries(main_runs, out, cfg=cfg),
        fig_queue_delay(runs, out),
        fig_road_delay(main_runs, out),
        fig_los(main_runs, out),
        fig_calls_per_day(runs, out),
        fig_who_adapts(runs, out),
    ]
    ref = next((v for k, v in runs.items() if k.startswith("R-daily")), next(iter(runs.values())))
    written.append(fig_vickrey_check(ref, cfg, out))
    st = summary_table(runs)
    st.to_csv(out / "summary_table.csv", index=False)
    (out / "summary_table.md").write_text(
        _md_table(st) + "\nShares are of all commuters. LoS over 07:00-09:00, mwy = motorways, other = other roads: "
        "los_ef_share = share of traffic at LoS E/F by V/C, vc_mean = the mean V/C next to it, los_ef_speed_share "
        "= at LoS E/F by speed, congested_at_share = congested by AT's definition. " + LOS_NOTE + "\n")
    # runs at other peak charges (--peak-fee, _peak<NZ$>) of the canonical runs' seed
    fr_seed = args.seed
    if fr_seed is None and not (args.all or args.run_dirs):
        fr_seed = int(next(iter(runs.values()))["summary"]["meta"]["seed"])  # type: ignore[index]
    written += _write_fee_response(runs_dir, out, cfg, fr_seed, args.include_netlogo, runs)
    for stale in ("departure_hist.png",):  # renamed outputs of earlier versions
        (out / stale).unlink(missing_ok=True)
    for f in list(out.glob("who_adapts_*.csv")) + list(out.glob("twins_day11_*.csv")):
        f.unlink()
    rule_refs = {False: runs.get("R-clock"), True: runs.get("R-clock (traits off)")}  # matched information
    twins, diags = [], []
    for lab, r in runs.items():
        slug = (lab.replace(" ", "_").replace("(", "").replace(")", "").replace("[", "")
                .replace("]", "").replace("{", "").replace("}", ""))
        table_who_adapts(r).to_csv(out / f"who_adapts_{slug}.csv", index=False)
        tw = table_twins(r)
        tw.to_csv(out / f"twins_day11_{slug}.csv", index=False)
        twins.append(twin_summary(r))
        dg = llm_diagnostics(r, rule_refs["traits off" in lab])
        if dg:
            diags.append(dg)
    tws = pd.DataFrame(twins)
    tws.to_csv(out / "twins_summary.csv", index=False)
    (out / "twins_summary.md").write_text(
        _md_table(tws) + "\nTwins share Layer A. Rule noise uses common random numbers for twins and MockLLM "
        "is seeded by the prompt, so with traits off (identical A and B) a difference comes from "
        "history only. MockLLM is a pipeline check, not an LLM.\n")
    if diags:
        dgf = pd.DataFrame(diags)
        dgf.to_csv(out / "llm_diagnostics.csv", index=False)
        (out / "llm_diagnostics.md").write_text(_md_table(dgf))
    for p in written:
        print(p)
    print(out / "summary_table.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
