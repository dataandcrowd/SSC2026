"""Compare PyEngine and NetLogoEngine on random and edge-case plan sets (own process).

Usage (from the cordon_lite folder):
    .venv/bin/python scripts/check_netlogo_equivalence.py [--scenario DIR] [--n-random 6] [--seed 7]
                                                           [--real-agents 300] [--timing-agents 300]
                                                           [--gui-smoke] [--netlogo-home PATH] [--json OUT]

Without --scenario a synthetic scenario (3 corridors, 20 agents, as in tests/conftest.py) is built.
Variants compared (outcomes, profile and road entries, exactly):
  base     the scenario as given (free-flow roads unless it holds road files);
  lowcap   every capacity below 1 car per minute;
  road     synthetic road files on the scenario's agents (write_road_files): congested enough that
           sections hit the speed floor, commuter entries in the flow window slow later cars, cars
           enter several sections within one minute (short and zero-length sections), some agents
           have no route (free flow), and many cars reach the gate in the same minute;
  road_mwy the road variant with motorway flow breakdown (add_motorways): the trunk and the shared
           sections are motorways, some with a usual-traffic breakdown window, others broken down
           only when their V/C reaches the threshold with today's traffic;
  road_nzta the road_mwy variant with NZTA-style per-section values (add_profiles): three time
           profiles in the long road_profile.csv (profile_id, minute, r) and a capacity drop per
           section (cap_drop, 0.04 to 0.3 on motorways);
  real     with --real-agents N: a scenario from run.write_scenario with N real personas and the
           real prep data (data/origins.csv, corridors.csv and the road files of prep.build_roads,
           with the config's road settings: motorway breakdown when road.mwy_breakdown).
The road variants also get road_plan_sets (everyone leaving at 07:45, departures on every minute,
a 07:30 peak); every check reports road coverage (floor hits, window entries, gate ties, entries
on motorways broken down by their window or by the V/C threshold, at the jam speed or not; entries
by time profile and broken-down entries on sections whose capacity drop differs from the global one).
--gui-smoke exercises the GUI headless on the road_nzta variant and checks that its car minutes (the
shared road-arrivals and point-queues) equal PyEngine's, which days charge-on plays and
the plots' pens (queues by corridor, entries, LoS E/F and mean V/C).
The script prints a JSON summary and ends with os._exit (exit code 0 if every comparison
matched), because the NetLogo JVM can start only once per process and may hang on exit.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from cordonlite import fees  # noqa: E402
from cordonlite import roads as roadsmod  # noqa: E402
from cordonlite.config import load_config  # noqa: E402
from cordonlite.engine import (  # noqa: E402
    AGENTS_COLUMNS, AGENTS_FILE, CORRIDORS_COLUMNS, CORRIDORS_FILE, FEES_FILE,
    NETLOGO_HOME_ENV, NetLogoEngine, PyEngine, hard_exit, shutdown_netlogo_link,
)

MODES = np.array(["CAR", "PT", "WFH", "SKIP"])


def config(**extra: object):
    return load_config(overrides=extra)


def write_scenario(d: Path, corridors: pd.DataFrame, agents: pd.DataFrame, regime: str = "tou") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    corridors[list(CORRIDORS_COLUMNS)].to_csv(d / CORRIDORS_FILE, index=False)
    agents[list(AGENTS_COLUMNS)].to_csv(d / AGENTS_FILE, index=False)
    fees.write_fees_csv(d / FEES_FILE, fees.fee_table(regime))
    return d


def tiny_scenario(d: Path) -> Path:
    """Same data as tests/conftest.py (3 corridors, 20 agents)."""
    cor = pd.DataFrame({
        "corridor_id": [0, 1, 2],
        "name": ["North (Harbour Bridge)", "West (Great North Rd)", "South (Khyber Pass Rd)"],
        "capacity_per_min": [0.5, 1.0, 1.5],
        "x": [1757000.0, 1755000.0, 1758500.0],
        "y": [5923000.0, 5920000.0, 5918000.0],
    })
    rows = []
    for i in range(20):
        rows.append({"agent_id": i, "corridor_id": i % 3, "fftt_to_gate_min": 10 + (i * 7) % 31,
                     "fftt_gate_to_dest_min": 2 + i % 5, "x": 1750000.0 + 500.0 * i,
                     "y": 5910000.0 + 300.0 * ((i * 3) % 20)})
    return write_scenario(d, cor, pd.DataFrame(rows))


def synthetic_scenario(d: Path, n_agents: int, n_corridors: int = 5, seed: int = 11) -> Path:
    """Random city-wide-like scenario; capacity so each corridor clears in about 60 minutes."""
    rng = np.random.default_rng(seed)
    corr = rng.integers(0, n_corridors, n_agents)
    counts = np.bincount(corr, minlength=n_corridors)
    ang = np.linspace(0, 2 * np.pi, n_corridors, endpoint=False) + 0.3
    cx, cy = 1757000.0, 5920000.0
    cor = pd.DataFrame({
        "corridor_id": np.arange(n_corridors),
        "name": [f"Corridor {k}" for k in range(n_corridors)],
        "capacity_per_min": np.maximum(0.25, counts / 60.0),
        "x": cx + 1500 * np.sin(ang), "y": cy + 1500 * np.cos(ang),
    })
    r = rng.uniform(3000, 25000, n_agents)
    ag = pd.DataFrame({
        "agent_id": np.arange(n_agents), "corridor_id": corr,
        "fftt_to_gate_min": rng.integers(5, 50, n_agents),
        "fftt_gate_to_dest_min": rng.integers(0, 6, n_agents),
        "x": cx + r * np.sin(ang[corr] + rng.normal(0, 0.3, n_agents)),
        "y": cy + r * np.cos(ang[corr] + rng.normal(0, 0.3, n_agents)),
    })
    return write_scenario(d, cor, ag)


def low_capacity_variant(src: Path, dst: Path) -> Path:
    """Copy of a scenario with every capacity below one car per minute."""
    shutil.copytree(src, dst)
    cor = pd.read_csv(dst / CORRIDORS_FILE)
    lows = [0.3, 0.7, 0.45, 0.9, 0.2, 0.55]
    cor["capacity_per_min"] = [lows[i % len(lows)] for i in range(len(cor))]
    cor.to_csv(dst / CORRIDORS_FILE, index=False)
    return dst


def write_road_files(d: Path, agents: pd.DataFrame, seed: int = 5) -> Path:
    """Synthetic road files (roads.ROAD_SCENARIO_FILES) for the agents of a scenario.

    Each routed agent drives 1-3 own sections (one of them zero-length, several shorter than a
    minute), then three sections shared by its corridor and, for even agent_id, a trunk shared by
    every corridor. Capacities are low against background plus 63-car agents, so the trunk and the
    shared sections reach the speed floor at the peak. Every seventh agent (agent_id % 7 == 3) has no
    route (free flow). Rows are written unsorted; floats with full precision."""
    rng = np.random.default_rng(seed)
    secs: list[dict] = []

    def sec(sid: int, ff: float, cap: float, bg_share: float, w: float) -> int:
        bg = round(cap * bg_share, 3)
        secs.append({"section_id": sid, "ff_min": ff, "cap_vph": round(cap, 3), "bg_peak_vph": bg,
                     "obs_peak_vph": round(bg * 1.15, 3), "w_factor": round(w, 6)})
        return sid

    trunk = sec(9000, 1.75, 700.0, 0.85, 1.0)
    shared: dict[int, list[int]] = {}
    for c in sorted(int(x) for x in agents["corridor_id"].unique()):
        shared[c] = [sec(5000 + 10 * c + j, float(rng.uniform(0.4, 2.5)), float(rng.uniform(500, 900)),
                         float(rng.uniform(0.6, 0.95)), 1.0 if j == 2 else float(rng.uniform(0.4, 1.0)))
                     for j in range(3)]
    routes: list[tuple[int, int, int]] = []
    for aid, c in zip(agents["agent_id"].astype(int), agents["corridor_id"].astype(int)):
        if aid % 7 == 3:
            continue
        own = []
        for j in range(1 + aid % 3):
            ff = 0.0 if (aid == 2 and j == 0) else float(rng.choice([rng.uniform(0.05, 0.6), rng.uniform(1.0, 6.0)]))
            own.append(sec(10000 + 10 * aid + j, ff, float(rng.uniform(400, 1200)), float(rng.uniform(0.1, 0.9)),
                           float(rng.uniform(0.2, 1.0))))
        rt = own + shared[c] + ([trunk] if aid % 2 == 0 else [])
        routes.extend((aid, k, s) for k, s in enumerate(rt))
    sec_df = pd.DataFrame(secs).sample(frac=1.0, random_state=seed)
    sec_df.to_csv(d / roadsmod.ROAD_SECTIONS_FILE, index=False, lineterminator="\n")
    rt_df = pd.DataFrame(routes, columns=list(roadsmod.AGENT_ROUTES_COLUMNS)).sample(frac=1.0, random_state=seed)
    rt_df.to_csv(d / roadsmod.AGENT_ROUTES_FILE, index=False, lineterminator="\n")
    m = np.arange(roadsmod.N_PROFILE_MINUTES)
    knots = ([0, 300, 420, 465, 495, 540, 660, 1439], [0.15, 0.15, 0.6, 1.0, 1.05, 0.8, 0.5, 0.4])
    pd.DataFrame({"minute": m, "r": np.interp(m, *knots).round(6)}).to_csv(
        d / roadsmod.ROAD_PROFILE_FILE, index=False, lineterminator="\n")
    params = (("bpr_alpha", "0.15"), ("bpr_beta", "4"), ("speed_floor", "0.18"), ("flow_window_min", "15"),
              ("vehicles_per_agent", repr(19000.0 / 300)))
    (d / roadsmod.ROAD_PARAMS_FILE).write_text("key,value\n" + "".join(f"{k},{v}\n" for k, v in params),
                                               encoding="utf-8", newline="\n")
    return d


def road_variant(src: Path, dst: Path, seed: int = 5) -> Path:
    """Copy of a scenario with synthetic road files (write_road_files)."""
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("plans_day*", "outcomes_day*", "profile_day*",
                                                            "road_day*"))
    return write_road_files(dst, pd.read_csv(dst / AGENTS_FILE), seed)


MWY_PARAMS = (("mwy_breakdown", "1"), ("mwy_breakdown_vc", "1.0"), ("mwy_recover_vc", "0.95"),
              ("mwy_capacity_drop", "0.1"), ("mwy_jam_speed", "0.45"))


def add_motorways(d: Path) -> Path:
    """Motorway flow breakdown on the road files of d (roads.MWY_COLUMNS, MWY_PARAMS): the trunk
    (9000) and the shared sections 5000 + 10 c + j are motorways. The trunk and j = 0 have the
    usual-traffic window 07:10-09:50; j = 1 a short window 07:40-08:00 (a breakdown before or after
    it needs V/C >= 1 with today's traffic); j = 2 none (only today's traffic breaks it down). The
    other sections keep mwy 0 (one own section gets a window that must be ignored). Rows keep the
    file's order."""
    sec = pd.read_csv(d / roadsmod.ROAD_SECTIONS_FILE, float_precision="round_trip")
    win = {0: (430, 590), 1: (460, 480), 2: (-1, -1)}
    rows = []
    for s in sec["section_id"].astype(int):
        if s == 9000:
            rows.append((1, 430, 590))
        elif 5000 <= s < 9000:
            rows.append((1, *win[s % 10]))
        elif s == 10040:
            rows.append((0, 430, 590))
        else:
            rows.append((0, -1, -1))
    for j, c in enumerate(roadsmod.MWY_COLUMNS):
        sec[c] = [r[j] for r in rows]
    sec.to_csv(d / roadsmod.ROAD_SECTIONS_FILE, index=False, lineterminator="\n")
    with open(d / roadsmod.ROAD_PARAMS_FILE, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(f"{k},{v}\n" for k, v in MWY_PARAMS))
    return d


def road_mwy_variant(src: Path, dst: Path, seed: int = 5) -> Path:
    """Copy of a scenario with synthetic road files and motorway breakdown (add_motorways)."""
    return add_motorways(road_variant(src, dst, seed))


DROP_BY_J = {0: 0.263187, 1: 0.04, 2: 0.3}   # cap_drop of the shared motorway sections 5000 + 10 c + j


def add_profiles(d: Path) -> Path:
    """NZTA-style per-section values (SPEC3) on the road_mwy files of d: road_profile.csv in the long
    format with three profiles (0 = the file's profile; 1 = an early maximum at 06:22 falling to a
    plateau until 09:30, as SH1 north; 2 = a late peak at 08:07, as SH20), profile_id by section
    (trunk 1; shared j = 0 -> 1, j = 1 -> 2, j = 2 -> 0; own sections (s // 10) % 3) and cap_drop
    (trunk 0.15, shared sections DROP_BY_J, other sections the global 0.1). Rows are shuffled."""
    sec = pd.read_csv(d / roadsmod.ROAD_SECTIONS_FILE, float_precision="round_trip")
    prof0 = pd.read_csv(d / roadsmod.ROAD_PROFILE_FILE, float_precision="round_trip").sort_values("minute")
    m = np.arange(roadsmod.N_PROFILE_MINUTES)
    p1 = np.interp(m, [0, 300, 360, 382, 420, 570, 660, 1439], [0.2, 0.2, 0.95, 1.08, 0.82, 0.86, 0.7, 0.45]).round(6)
    p2 = np.interp(m, [0, 300, 420, 487, 520, 600, 1439], [0.12, 0.12, 0.6, 1.1, 0.95, 0.7, 0.4]).round(6)
    long = pd.concat([pd.DataFrame({"profile_id": k, "minute": m, "r": r})
                      for k, r in ((0, prof0["r"].to_numpy()), (1, p1), (2, p2))], ignore_index=True)
    long.sample(frac=1.0, random_state=3).to_csv(d / roadsmod.ROAD_PROFILE_FILE, index=False, lineterminator="\n")
    pid, drop = [], []
    for s in sec["section_id"].astype(int):
        if s == 9000:
            pid.append(1)
            drop.append(0.15)
        elif 5000 <= s < 9000:
            pid.append({0: 1, 1: 2, 2: 0}[s % 10])
            drop.append(DROP_BY_J[s % 10])
        else:
            pid.append((s // 10) % 3)
            drop.append(0.1)
    sec["profile_id"] = pid
    sec["cap_drop"] = drop
    sec.to_csv(d / roadsmod.ROAD_SECTIONS_FILE, index=False, lineterminator="\n")
    return d


def road_nzta_variant(src: Path, dst: Path, seed: int = 5) -> Path:
    """Copy of a scenario with synthetic road files, motorway breakdown and NZTA-style per-section
    profiles and capacity drops (add_profiles)."""
    return add_profiles(road_mwy_variant(src, dst, seed))


def real_scenario(d: Path, n_agents: int) -> Path:
    """run.write_scenario with n_agents real personas, the real prep data and roads on."""
    from cordonlite import run as R
    from cordonlite.persona import build_personas

    cfg = config(**{"run.n_agents": n_agents, "road.enabled": True})
    origins, corridors_prep = R.load_prep(cfg)
    personas = build_personas(origins, corridors_prep, cfg)
    scale, _src = R.resolve_capacity_scale(cfg, warn=False)
    R.write_scenario(d, corridors_prep, personas, cfg, scale)
    return d


def plan_sets(agents: pd.DataFrame, n_random: int, seed: int) -> list[tuple[str, pd.DataFrame, bool]]:
    """(label, plans, fee_active) covering random days, ties, empty corridors and an all-SKIP day."""
    rng = np.random.default_rng(seed)
    ids = agents["agent_id"].to_numpy()
    n = len(ids)
    grid = np.arange(360, 586, 15)
    out: list[tuple[str, pd.DataFrame, bool]] = []
    for r in range(n_random):
        modes = rng.choice(MODES, n, p=[0.7, 0.15, 0.1, 0.05])
        dep = rng.choice(grid, n)
        out.append((f"random{r}", pd.DataFrame({"agent_id": ids, "mode": modes, "depart_min": dep}), bool(r % 2)))
    out.append(("all_skip", pd.DataFrame({"agent_id": ids, "mode": "SKIP", "depart_min": 480}), True))
    out.append(("all_car_same_depart", pd.DataFrame({"agent_id": ids, "mode": "CAR", "depart_min": 450}), True))
    # identical free-flow gate arrival minute for everyone (maximal ties without road delay)
    same_a = 470 - agents["fftt_to_gate_min"].to_numpy()
    out.append(("ties_same_arrival", pd.DataFrame({"agent_id": ids, "mode": "CAR", "depart_min": same_a}), True))
    first = int(agents["corridor_id"].min())
    on_first = agents["corridor_id"].to_numpy() == first
    out.append(("one_corridor_only", pd.DataFrame({
        "agent_id": ids, "mode": np.where(on_first, "CAR", "PT"), "depart_min": rng.choice(grid, n)}), True))
    one = np.full(n, "WFH", dtype=object)
    one[0] = "CAR"
    out.append(("single_car", pd.DataFrame({"agent_id": ids, "mode": one, "depart_min": 585}), False))
    # shuffled row order and non-car depart_min missing
    shuf = out[0][1].sample(frac=1.0, random_state=seed).reset_index(drop=True).copy()
    shuf["depart_min"] = shuf["depart_min"].astype("float64")
    shuf.loc[shuf["mode"] != "CAR", "depart_min"] = np.nan
    out.append(("shuffled_nan", shuf, True))
    return out


def road_plan_sets(agents: pd.DataFrame, seed: int) -> list[tuple[str, pd.DataFrame, bool]]:
    """Extra plan sets for congested roads: everyone driving at 07:45, departures on every minute
    06:00-10:00, and a 07:30 peak (normal, sd 20 min) with some PT and WFH."""
    rng = np.random.default_rng(seed + 1)
    ids = agents["agent_id"].to_numpy()
    n = len(ids)
    peak = np.clip(np.round(rng.normal(450, 20, n)), 360, 600).astype(int)
    return [
        ("all_car_0745", pd.DataFrame({"agent_id": ids, "mode": "CAR", "depart_min": 465}), True),
        ("spread_every_minute", pd.DataFrame({"agent_id": ids, "mode": "CAR",
                                              "depart_min": rng.integers(360, 601, n)}), False),
        ("peak_0730", pd.DataFrame({"agent_id": ids, "mode": rng.choice(MODES[:3], n, p=[0.8, 0.12, 0.08]),
                                    "depart_min": peak}), True),
    ]


def compare(a, b) -> list[str]:
    errs = []
    for name in ("outcomes", "profile", "road"):
        x, y = getattr(a, name), getattr(b, name)
        if list(x.columns) != list(y.columns):
            errs.append(f"{name}: columns differ")
            continue
        if x.shape != y.shape:
            errs.append(f"{name}: shape {x.shape} vs {y.shape}")
            continue
        if list(x.dtypes) != list(y.dtypes):
            errs.append(f"{name}: dtypes {list(x.dtypes)} vs {list(y.dtypes)}")
        try:
            pd.testing.assert_frame_equal(x, y, check_exact=True)
        except AssertionError as e:  # pragma: no cover - reported
            errs.append(f"{name}: {str(e)[:400]}")
    return errs


def road_coverage(res, road: roadsmod.RoadScenario | None) -> dict:
    """What a day exercised on the roads (PyEngine result): entries, entries at the speed floor,
    entries with commuters already in the flow window, cars sharing their gate arrival minute with
    another car of the same corridor, road delays and unserved cars; on motorways (with the
    breakdown rule on): entries in broken-down flow inside the usual-traffic window (mwy_window),
    outside it at V/C >= the threshold (mwy_trigger; mwy_trigger_commuters when the background alone
    is below it), at the jam speed (mwy_jam_cap) and not broken down (mwy_plain)."""
    out = res.outcomes
    ties = int(out.duplicated(["corridor_id", "gate_arrive_min"], keep=False).sum()) if len(out) else 0
    cov = {"entries": int(res.road["entries"].sum()), "floor_hits": 0, "window_entries": 0, "gate_ties": ties,
           "cars_road_delayed": int((out["road_delay_min"] > 0).sum()),
           "max_road_delay": int(out["road_delay_min"].max()) if len(out) else 0,
           "unserved": int((out["gate_exit_min"] < 0).sum()),
           "mwy_window": 0, "mwy_trigger": 0, "mwy_trigger_commuters": 0, "mwy_jam_cap": 0, "mwy_plain": 0,
           "mwy_own_drop": 0, "mwy_own_drop_below_jam": 0}
    if road is None or not len(res.road):
        return cov
    pos, W = road.index, road.flow_window_min
    fpe = road.fpe
    by_sec: dict[int, dict[int, int]] = {}
    for s, m, n in zip(res.road["section_id"], res.road["minute"], res.road["entries"]):
        by_sec.setdefault(int(s), {})[int(m)] = int(n)
    for s, mm in by_sec.items():
        i = pos[s]
        pk = f"profile_{road.profile_id[i]}_entries"
        for m, n in mm.items():
            c = sum(mm.get(j, 0) for j in range(m - W, m))
            f = roadsmod.speed_factor(road, i, m, c)
            cov[pk] = cov.get(pk, 0) + n
            if f == road.speed_floor:
                cov["floor_hits"] += n
            if c > 0:
                cov["window_entries"] += n
            if road.mwy_breakdown and road.mwy[i] == 1:
                rr = road.sec_r[i]
                rm = rr[m] if m < roadsmod.N_PROFILE_MINUTES else rr[-1]
                x = (road.bg_peak_vph[i] * rm + c * fpe[i]) / road.cap_vph[i]
                if not roadsmod.broken_down(road, i, m, x):
                    cov["mwy_plain"] += n
                    continue
                if road.cap_drop[i] != road.mwy_capacity_drop:
                    cov["mwy_own_drop"] += n
                    cov["mwy_own_drop_below_jam"] += n * int(f < road.mwy_jam_speed)
                if road.bd_on[i] <= m < road.bd_off[i]:
                    cov["mwy_window"] += n
                else:
                    cov["mwy_trigger"] += n
                    if (road.bg_peak_vph[i] * rm) / road.cap_vph[i] < road.mwy_breakdown_vc:
                        cov["mwy_trigger_commuters"] += n   # the commuters' cars tipped it over
                cov["mwy_jam_cap"] += n * int(f == road.mwy_jam_speed)
    return cov


def run_checks(variants: list[tuple[str, Path]], n_random: int, seed: int) -> dict:
    cfg = config()
    results = []
    coverage: dict[str, dict] = {}
    nl = NetLogoEngine(cfg)
    for vname, vdir in variants:
        py = PyEngine(cfg)
        py.load(vdir)
        nl.load(vdir)
        road = py.scenario.road if py.scenario is not None else None
        agents = pd.read_csv(vdir / AGENTS_FILE)
        sets = plan_sets(agents, n_random, seed) + (road_plan_sets(agents, seed) if road is not None else [])
        tot: dict[str, int] = {}
        for day, (label, plans, fee_on) in enumerate(sets, start=1):
            t0 = time.perf_counter()
            ra = py.run_day(day, plans, fee_on)
            t1 = time.perf_counter()
            rb = nl.run_day(day, plans, fee_on)
            t2 = time.perf_counter()
            errs = compare(ra, rb)
            cov = road_coverage(ra, road)
            for k, v in cov.items():
                tot[k] = max(tot.get(k, 0), v) if k == "max_road_delay" else tot.get(k, 0) + v
            results.append({"variant": vname, "label": label, "day": day, "cars": int(len(ra.outcomes)),
                            "profile_rows": int(len(ra.profile)), "road_rows": int(len(ra.road)),
                            "coverage": cov, "py_s": round(t1 - t0, 4), "nl_s": round(t2 - t1, 4),
                            "ok": not errs, "errors": errs})
        coverage[vname] = {"road": road is not None, "n_sections": len(road.section_ids) if road else 0,
                           "n_routes": len(road.routes) if road else 0,
                           "mwy_breakdown": bool(road.mwy_breakdown) if road else False,
                           "n_mwy_sections": int(sum(road.mwy)) if road else 0,
                           "n_profiles": len(road.profiles) if road else 0,
                           "n_cap_drops": len(set(road.cap_drop)) if road else 0, **tot}
    nl.close()
    return {"variants": {v: str(d) for v, d in variants}, "n_checks": len(results),
            "n_ok": sum(r["ok"] for r in results), "coverage": coverage, "checks": results}


def timing(n_agents: int, work: Path, n_days: int = 5, seed: int = 3) -> dict:
    cfg = config()
    d = synthetic_scenario(work / f"timing_{n_agents}", n_agents)
    agents = pd.read_csv(d / AGENTS_FILE)
    rng = np.random.default_rng(seed)
    grid = np.arange(360, 586, 15)
    plans = [pd.DataFrame({"agent_id": agents["agent_id"], "mode": rng.choice(MODES, n_agents, p=[0.8, 0.1, 0.05, 0.05]),
                           "depart_min": rng.choice(grid, n_agents)}) for _ in range(n_days)]
    out: dict = {"n_agents": n_agents, "n_days": n_days}
    for kind, eng in (("py", PyEngine(cfg)), ("netlogo", NetLogoEngine(cfg))):
        t0 = time.perf_counter()
        eng.load(d)
        out[f"{kind}_load_s"] = round(time.perf_counter() - t0, 4)
        ts = []
        res = []
        for day, p in enumerate(plans, start=1):
            t0 = time.perf_counter()
            res.append(eng.run_day(day, p, True))
            ts.append(time.perf_counter() - t0)
        out[f"{kind}_run_day_s"] = [round(t, 4) for t in ts]
        out[f"{kind}_run_day_mean_s"] = round(float(np.mean(ts)), 4)
        out[f"{kind}_run_day_mean_after_first_s"] = round(float(np.mean(ts[1:])), 4) if len(ts) > 1 else None
        out[f"_{kind}_res"] = res
    out["equal"] = all(not compare(a, b) for a, b in zip(out.pop("_py_res"), out.pop("_netlogo_res")))
    return out


def _gui_minutes_match(link, scen_dir: Path, day: int) -> dict:
    """The GUI's minutes of today's cars (start-day -> simulate-queues) against PyEngine on the same
    plans: depart, gate arrival (with road delay), gate exit and arrival must be equal."""
    rows = link.report('map [ c -> [ (list agent-id dep gate-arr gate-exit arr) ] of c ] '
                       'sort-on [ agent-id ] commuters with [ mode-today = "CAR" ]')
    gui = pd.DataFrame(np.asarray(rows, dtype=float).reshape(-1, 5),
                       columns=["agent_id", "depart_min", "gate_arrive_min", "gate_exit_min", "arrive_min"]
                       ).astype("int64")
    py = PyEngine(config())
    py.load(scen_dir)
    res = py.run_day(day, pd.DataFrame({"agent_id": gui["agent_id"], "mode": "CAR",
                                        "depart_min": gui["depart_min"]}), False)
    ref = res.outcomes[list(gui.columns)].reset_index(drop=True)
    ok = len(gui) > 0 and gui.equals(ref)
    return {"cars": int(len(gui)), "ok": bool(ok),
            "cars_road_delayed": int((res.outcomes["road_delay_min"] > 0).sum()),
            "mismatches": int((gui != ref).any(axis=1).sum()) if gui.shape == ref.shape else -1}


def gui_smoke(scenario: Path, work: Path) -> dict:
    """Exercise the GUI headless: setup (map, network, routes), go, finish-day over two demo days (the
    folder has no plans files; its scenario.csv charges day 2 of 2), plots; the GUI's car minutes on both
    days must equal PyEngine's (the same road-arrivals and point-queues). Then the charge-on variable:
    "off: before the charge" plays day 1 again, "on: with the charge" day 2. Nothing here may reach a
    user-message (it waits for a click, headless too)."""
    from cordonlite.engine import _nl_string, get_netlogo_link
    from cordonlite.run import SCENARIO_FILE

    cfg = config()
    d = work / "gui_scenario"
    shutil.copytree(scenario, d, ignore=shutil.ignore_patterns("plans_day*", "outcomes_day*", "profile_day*",
                                                               "road_day*"))
    # scenario.csv as cordonlite/run.py writes it: charged from day 2, two days
    pd.DataFrame({"key": ["charge_from_day", "n_days"], "value": [2, 2]}).to_csv(
        d / SCENARIO_FILE, index=False, lineterminator="\n")
    road = roadsmod.read_road_scenario(d)
    link = get_netlogo_link(cfg)
    link.load_model(str(cfg.resolve_path(cfg.engine.model_path)))
    link.command(f"setup-run {_nl_string(str(d))}")   # the experiment chooser takes only its listed experiments
    out: dict = {"corridors": int(link.report("length corr-ids")), "commuters": int(link.report("count commuters")),
                 "gates": int(link.report("count gates")), "nodes": int(link.report("count nodes")),
                 "road_on": bool(link.report("road-on?"))}
    out["road_ok"] = (out["road_on"] == (road is not None)) and (
        road is None or float(link.report("vehicles-per-agent")) == road.vehicles_per_agent)
    link.command("go")              # starts day 1 and plays one tick
    out["day1_started"] = bool(link.report("day-running?")) and int(link.report("current-day")) == 1
    out["day1_minutes"] = _gui_minutes_match(link, d, 1)
    link.command("finish-day")      # rest of day 1
    link.command("finish-day")      # day 2 (charged from day 2: scenario.csv)
    out["day2_minutes"] = _gui_minutes_match(link, d, 2)
    spm = float(link.report("steps-per-minute"))
    out.update({
        "day": int(link.report("current-day")), "ticks": float(link.report("ticks")),
        "cars": int(link.report("n-cars")), "mean_delay": float(link.report("mean-delay")),
        "fee_active_day2": bool(link.report("fee-active-today?")),
        "all_arrived": bool(link.report('all? commuters [ member? (state-at clock) ["work" "home"] ]')),
        "ticks_ok": float(link.report("ticks")) == (float(link.report("day-end-min"))
                                                    - float(link.report("sim-start-min"))) * spm,
        "no_files_written": not any(d.glob("*_day*.csv")),
    })
    link.command('set-current-plot "Queue length by corridor"')
    names = pd.read_csv(d / CORRIDORS_FILE).sort_values("corridor_id")
    # the legend names a corridor by the first road in brackets (corridor-entry-name)
    out["queue_pens_ok"] = all(bool(link.report(f'plot-pen-exists? "{int(c)}: {_entry_name(n)}"'))
                               for c, n in zip(names["corridor_id"], names["name"]))
    link.command('set-current-plot "Cordon entries per 15 min"')
    out["entries_pen_ok"] = bool(link.report('plot-pen-exists? "entries"'))
    # LoS E/F and, under it, the mean V/C of the same 5-minute pass (plot-los); los-mark >= 0 once plotted
    out["los_vc_pens_ok"] = True
    for plot in ("% traffic at LoS E/F", "Mean V/C (1 = at capacity)"):
        link.command(f'set-current-plot "{plot}"')
        out["los_vc_pens_ok"] &= all(bool(link.report(f'plot-pen-exists? "{p}"')) for p in roadsmod.LOS_REGIONS)
    out["los_mark"] = int(link.report("los-mark"))
    out["charge_on"] = charge_on_smoke(link)
    out["ok"] = (out["day1_started"] and out["day"] == 2 and out["fee_active_day2"] and out["all_arrived"]
                 and out["ticks_ok"] and out["no_files_written"] and out["queue_pens_ok"]
                 and out["entries_pen_ok"] and out["los_vc_pens_ok"]
                 and out["nodes"] > 0 and 1 <= out["gates"] <= out["corridors"]
                 and out["road_ok"] and out["day1_minutes"]["ok"] and out["day2_minutes"]["ok"]
                 and out["charge_on"]["ok"])
    return out


def _entry_name(name: str) -> str:
    """corridor-entry-name: the first road in the brackets of a corridor name, else the whole name."""
    i = name.find(" (")
    return name if i < 0 else name[i + 2:-1].split(",")[0]


def charge_on_smoke(link) -> dict:
    """The charge-on variable after day 2 of a run charged from day 2 of 2 (gui_smoke): "all days" is over
    (next-day-to-show is the message, read without go, whose user-message would wait for a click);
    "off: before the charge" makes go start day 1 again, uncharged, and is over after it; "on: with the
    charge" makes finish-day play day 2, charged."""
    out: dict = {"all_days_over": bool(link.report("is-string? next-day-to-show"))}
    link.command('set charge-on "off: before the charge"')
    link.command("go")              # day 2 is not before the charge: day 1 starts, one tick plays
    out["off_day"] = int(link.report("current-day"))
    out["off_running"] = bool(link.report("day-running?"))
    out["off_charged"] = bool(link.report("fee-active-today?"))
    link.command("finish-day")      # rest of day 1
    out["off_over"] = bool(link.report("is-string? next-day-to-show"))
    link.command('set charge-on "on: with the charge"')
    link.command("finish-day")      # day 2, the only charged day
    out["on_day"] = int(link.report("current-day"))
    out["on_charged"] = bool(link.report("fee-active-today?"))
    out["on_finished"] = not bool(link.report("day-running?"))
    out["ok"] = (out["all_days_over"] and out["off_day"] == 1 and out["off_running"] and not out["off_charged"]
                 and out["off_over"] and out["on_day"] == 2 and out["on_charged"] and out["on_finished"])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", type=Path, default=None)
    ap.add_argument("--n-random", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--real-agents", type=int, default=0,
                    help="also compare a real-data scenario with this many agents and roads on (needs data/)")
    ap.add_argument("--timing-agents", type=int, default=0, help="also time run_day for this many agents")
    ap.add_argument("--gui-smoke", action="store_true", help="also exercise the GUI procedures headless")
    ap.add_argument("--netlogo-home", default=None,
                    help="NetLogo folder (sets CORDONLITE_NETLOGO_HOME, which overrides [engine] netlogo_home)")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    if args.netlogo_home:
        os.environ[NETLOGO_HOME_ENV] = args.netlogo_home
    summary: dict = {}
    code = 1
    try:
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="cl_nl_") as tmp:
            work = Path(tmp)
            scen = args.scenario.resolve() if args.scenario else tiny_scenario(work / "tiny")
            variants = [("base", scen),
                        ("lowcap", low_capacity_variant(scen, work / (scen.name + "_lowcap"))),
                        ("road", road_variant(scen, work / (scen.name + "_road"))),
                        ("road_mwy", road_mwy_variant(scen, work / (scen.name + "_road_mwy"))),
                        ("road_nzta", road_nzta_variant(scen, work / (scen.name + "_road_nzta")))]
            if args.real_agents > 0:
                variants.append(("real", real_scenario(work / f"real_{args.real_agents}", args.real_agents)))
            summary["equivalence"] = run_checks(variants, args.n_random, args.seed)
            if args.gui_smoke:
                summary["gui_smoke"] = gui_smoke(dict(variants)["road_nzta"], work)
            if args.timing_agents > 0:
                summary["timing"] = timing(args.timing_agents, work)
        summary["wall_s"] = round(time.perf_counter() - t0, 3)
        eq = summary["equivalence"]
        ok = (eq["n_ok"] == eq["n_checks"] and summary.get("timing", {}).get("equal", True)
              and summary.get("gui_smoke", {}).get("ok", True))
        code = 0 if ok else 1
    except Exception:  # noqa: BLE001 - report and exit non-zero
        summary["exception"] = traceback.format_exc()
        code = 2
    summary["exit_code"] = code
    text = json.dumps(summary, indent=1)
    if args.json:
        args.json.write_text(text)
    print(text)
    shutdown_netlogo_link(timeout_s=5.0)
    return code


if __name__ == "__main__":
    hard_exit(main())
