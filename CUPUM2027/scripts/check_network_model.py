"""Check the GUI of netlogo7/cordon_lite.nlogox against a finished run (own process).

Usage (from the cordon_lite folder):
    .venv/bin/python scripts/check_network_model.py [--run-dir runs/R-clock_mock_py_s1_d10_fs6] [--days 1 6]
                                                    [--views DIR] [--view-times 06:45 07:15 ...]
                                                    [--netlogo-home PATH] [--json OUT]

setup-run (setup on any folder) loads the run folder, builds the TomTom road network and places the
city-centre buildings.
The script checks the network (28,507 nodes and 30,835 roads, the giant component prep routes on;
1,106 nodes in the cordon), every commuter's gate (the prep gate of its origin, entered from
outside to inside), its workplace (a building inside the cordon, the same on a second draw) and
that its leg from the gate to its parking node runs outside the cordon polygon for at most
MAX_OUTSIDE_M metres (only from the Wellesley Street ramp and Hopetoun Street gates, whose inside
ends reach the rest of the cordon through a road just outside it); and for each day:
  - every car's depart, gate-arrive, gate-exit and arrive minute (and road delay, when the run has
    road files) equals the run's outcomes.csv;
  - PT riders are the run's PT riders (their minutes are read from that file: a consistency check);
  - with road files: each car's section times in the model (road-arrivals) equal those of a probe
    on cordonlite.roads.speed_table built from the day's road_entries.csv (the engine's day, so
    the same doubles), and its drive to the gate follows them: at a sampled clock a car before
    its gate stands where its free-flow progress puts it (the free-flow minutes of route covered at
    each section's congested pace, the times stretched so that it reaches the gate at gate-arr),
    within 1 m; without road files it moves at constant speed by metres;
  - every car's drive reaches its gate point exactly at its gate-arrive minute (drive-point);
  - with road files: the road colours are the speed grades of the sections at the last 5-minute
    mark: the speed factor of cordonlite.roads.speed_table built from the day's road_entries.csv
    (background flow of that minute plus the day's commuter entries in the flow window before it;
    the engine's speed / free-flow speed) in the bands of SPEED_BANDS (normal >= 0.80, slow, heavy,
    jammed < 0.40), and jammed for a motorway section in broken-down flow (the table's broken
    mask, the engine's breakdown rule) whatever its speed; every section not waiting to be redrawn
    is drawn in its grade; and the "traffic delay (min)" monitor is the mean road delay of the cars
    that have reached their gate;
  - with road files: the Level of Service the GUI shows (SPEC4 B; the "LoS E/F %", "mean V/C" and
    "LoS E/F by speed %" monitors at the last 5-minute mark) equals cordonlite.roads at that minute:
    every section's LoS grade by V/C and by speed (los_at_minute on traffic_table built from the day's
    road_entries.csv, with km and mwy of data/road_sections.csv) exactly, and the shares of motorway
    and other-road traffic at E/F (by V/C and by speed) and their mean V/C within LOS_TOL; at the end of the day the "% traffic at LoS E/F" plot (export-plot)
    holds one point per 5-minute mark of the day for each pen, equal to the same values (the marks
    finish-day skips included);
  - one go is one tick of 1/steps-per-minute minutes (15 s; the counter counts steps since
    sim_start_min);
  - the day is animated to 08:30; at 08:00 no car on the road is hidden, a queued car stands on its
    approach road (within 1 m of it) at most q-rank x queue-spacing-m (+1 m) from its gate point,
    and a driving car is on its route; in both views a queued car is red and drawn 80% of the queue
    spacing long (at least 1.5 patches, at most a moving car's size) and a moving car at its size;
  - the day ends 2 minutes after the last arrival (sim_end_cap_min if a car is never served), and
    then every commuter is in the state its engine minutes give: at its building (CAR, PT), at
    home (WFH, SKIP), still queued (a car never served).
It also reports the implied speeds to the gate (route km / (gate_arrive_min - depart_min)) of the
checked days, the time per go during 07:30-08:30 and how far each drawn route's free-flow minutes
are from the engine route's (the network path and prep's path).
--views DIR also exports the Auckland and City-centre views at 08:00 and at the end of each day,
and at each --view-times clock (HH:MM; the day is animated to the last of them, and the positions,
colours and monitor are checked there too; a clock after the day's end is skipped and listed in
marks_after_day_end, as a later go would start the next day); grades_HH:MM (and mwy_grades_HH:MM, motorway sections
only) count the sections by grade at each checked clock, and mwy_jammed_by_profile_HH:MM counts the
motorway sections drawn jammed and all of them by time profile (NZTA sites, SPEC3: the motorway
corridors break down at different times). With road files the summary also gives the time profiles
and the capacity drops of the run's sections (several of each with NZTA data); the model reads them
through the engine's reporters (road-volume, road-speed-factor), so the grade check covers them.
The script prints a JSON summary and ends with os._exit (exit code 0 if every check passed),
because the NetLogo JVM can start only once per process and may hang on exit.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402

from cordonlite.config import load_config  # noqa: E402
from cordonlite.engine import (  # noqa: E402
    NETLOGO_HOME_ENV, _nl_string, get_netlogo_link, hard_exit, shutdown_netlogo_link,
)
from cordonlite.roads import (LOS_REGIONS, ROAD_ENTRIES_FILE, TABLE_TAIL_MIN, RoadScenario, los_at_minute,  # noqa: E402
                              los_section_info, read_road_scenario, speed_table, traffic_table)

MODEL = ROOT / "netlogo7" / "cordon_lite.nlogox"
N_NODES, N_ROADS, N_IN_CORDON = 28507, 30835, 1106   # prep giant component (data/prep_report.md)
MAX_OUTSIDE_M = 200.0   # longest stretch outside the cordon on a gate-to-building leg (about 180 m, gate 20)
BY_AGENT = "sort-on [agent-id] commuters"
# clocks at which drawn positions and road colours are checked: off the 15-minute departure grid
# (a car that has just left stands at home whatever its speed), and 07:30, 08:00 and 08:30
SAMPLE_MIN = (427.5, 450, 457.5, 480, 487.5, 510)
# speed grades of the road colours: lower bounds of the speed factor of normal, slow and heavy traffic
# (jammed below the last), as grade-bands in the model
SPEED_BANDS = (0.80, 0.60, 0.40)
# car sizes (patches) as in the model: moving cars (car-size) and queued cars (queued-car-size), whose
# length (the car shape is CAR_SHAPE_LENGTH of its size long) is QUEUED_LENGTH_SHARE of the queue spacing
MOVING_SIZE = {"cc": 4.0, "auckland": 2.5}
CAR_SHAPE_LENGTH = 0.9
QUEUED_LENGTH_SHARE = 0.8
MIN_QUEUED_SIZE = 1.5
# Level of Service (SPEC4 B): GUI globals (fractions; -1 = no traffic in the group) and the keys of
# cordonlite.roads.los_at_minute; the GUI sums sections one by one, numpy pairwise, so the shares agree
# to rounding (LOS_TOL); the grades must be equal
LOS_VALUES = (("los-ef-mwy", "ef_share_mwy"), ("los-ef-other", "ef_share_other"),
              ("los-vc-mwy", "vc_mean_mwy"), ("los-vc-other", "vc_mean_other"),
              ("los-efs-mwy", "ef_speed_share_mwy"), ("los-efs-other", "ef_speed_share_other"))
# monitors: reporter (with the group "motorway" / "other") -> (los_at_minute key prefix, scale)
LOS_MONITORS = (("los-ef-pct", "ef_share", 100.0), ("los-vc", "vc_mean", 1.0),
                ("los-ef-speed-pct", "ef_speed_share", 100.0))
LOS_TOL = 1e-9
# the two LoS plots, one pen per region of LOS_REGIONS: plot -> (los_at_minute key of the region list, scale)
LOS_PLOTS = (("% traffic at LoS E/F", "region_ef_share", 100.0),
             ("Mean V/C (1 = at capacity)", "region_vc_mean", 1.0))


def per_agent(link, expr: str) -> list:
    """[expr] of every commuter in agent_id order (one type per call: pynetlogo cannot mix types)."""
    return list(link.report(f"map [ c -> [ {expr} ] of c ] {BY_AGENT}"))


def ragged(link, expr: str, agents: str = BY_AGENT) -> list[np.ndarray]:
    """A list-valued [expr] of each agent (lists of different lengths, which pynetlogo cannot return
    as one nested list): lengths and the flattened values, split again."""
    n = np.atleast_1d(np.array(link.report(f"map [ c -> [ length {expr} ] of c ] {agents}"), dtype=int))
    if n.sum() == 0:
        return [np.zeros(0) for _ in n]
    flat = np.atleast_1d(np.array(link.report(f"reduce sentence map [ c -> [ {expr} ] of c ] {agents}"), dtype=float))
    return np.split(flat, np.cumsum(n)[:-1])


def dist_to_polyline(p: np.ndarray, pts: np.ndarray) -> float:
    """Euclidean distance from point p to the polyline pts (metres)."""
    if len(pts) == 1:
        return float(np.hypot(*(p - pts[0])))
    a, b = pts[:-1], pts[1:]
    ab = b - a
    t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
    return float(np.hypot(*(a + t[:, None] * ab - p).T).min())


def along(pts: np.ndarray, cum: np.ndarray, x: float) -> np.ndarray:
    """Point at x along the polyline pts, where cum[j] is x at point j (non-decreasing)."""
    j = int(np.searchsorted(cum, x, side="right")) - 1
    j = min(max(j, 0), len(pts) - 2)
    span = cum[j + 1] - cum[j]
    f = min(1.0, max(0.0, (x - cum[j]) / span)) if span > 0 else 1.0
    return pts[j] + f * (pts[j + 1] - pts[j])


def check_setup(link, run_dir: Path, out: dict) -> tuple[list[str], dict]:
    errs: list[str] = []
    n = {k: int(link.report(r)) for k, r in [("nodes", "count nodes"), ("roads", "count roads"),
                                               ("in_cordon", "count nodes with [in-cordon?]"),
                                               ("buildings", "count buildings"),
                                               ("commuters", "count commuters"), ("gates", "count gates")]}
    out["counts"] = n
    if (n["nodes"], n["roads"], n["in_cordon"]) != (N_NODES, N_ROADS, N_IN_CORDON):
        errs.append(f"network {n['nodes']}/{n['roads']}/{n['in_cordon']} != {N_NODES}/{N_ROADS}/{N_IN_CORDON}")
    n_bld = len(pd.read_csv(ROOT / "netlogo7" / "gis" / "cbd_buildings.csv"))
    if n["buildings"] != n_bld:
        errs.append(f"{n['buildings']} buildings, cbd_buildings.csv has {n_bld}")
    agents = pd.read_csv(run_dir / "agents.csv")
    if n["commuters"] != len(agents):
        errs.append(f"{n['commuters']} commuters, agents.csv has {len(agents)}")
    if not link.report("all? commuters [ is-building? work-building and [in-cordon?] of [bnode] of work-building ]"):
        errs.append("a workplace is missing or its node is outside the cordon")
    if not link.report("all? gates [ inside-node = nobody or ((not [in-cordon?] of outside-node) and [in-cordon?] of inside-node) ]"):
        errs.append("a gate segment is not entered from outside to inside")
    personas = run_dir / "personas.csv"
    if personas.exists():
        origins = pd.read_csv(ROOT / "data" / "origins.csv").set_index("origin_id")
        want = pd.read_csv(personas).sort_values("agent_id").origin_id.map(origins.gate_id).to_numpy()
        got = np.array(per_agent(link, "[gate-id] of my-gate"), dtype=int)
        if not (got == want).all():
            errs.append(f"{int((got != want).sum())} commuters not at the prep gate of their origin")
        out["prep_gates"] = sorted(set(got.tolist()))
    cordon = gpd.read_file(ROOT / "netlogo7" / "gis" / "cordon.shp").geometry.iloc[0].buffer(1.0)
    legs = [leg.reshape(-1, 2) for leg in ragged(link, "reduce sentence route-in")]
    outside_m = np.array([shapely.LineString(leg).difference(cordon).length if len(leg) > 1 else 0.0
                          for leg in legs])
    if outside_m.max() > MAX_OUTSIDE_M:
        errs.append(f"a leg from the gate to the building runs {outside_m.max():.0f} m outside the cordon")
    out["legs_leaving_cordon"] = int((outside_m > 0).sum())
    out["max_outside_m"] = round(float(outside_m.max()), 1)
    # the drives to the gate: route-out points, their cumulative metres and free-flow minutes
    ids = np.array(per_agent(link, "agent-id"), dtype=int)
    pts = [p.reshape(-1, 2) for p in ragged(link, "reduce sentence route-out")]
    lens = ragged(link, "len-out")
    tts = ragged(link, "route-out-minutes")
    if any(len(t) != len(p) or len(p) < 2 for t, p in zip(tts, pts)):
        errs.append("route-out-minutes and route-out differ in length (or a route has fewer than 2 points)")
    if any(np.any(np.diff(t) < 0) for t in tts):
        errs.append("route-out-minutes is not non-decreasing")
    geo = {"pts": dict(zip(ids, pts)), "len": dict(zip(ids, lens)), "tt": dict(zip(ids, tts))}
    # implied constant speeds (km/h) at free flow; the drives of the checked days are in kmh_to_gate
    ag = agents.sort_values("agent_id")
    for leg, km, mins in (("to_gate_free_flow", np.array([v[-1] for v in lens]) / 1000, ag.fftt_to_gate_min),
                          ("gate_to_building", np.array(per_agent(link, "last len-in"), dtype=float) / 1000,
                           ag.fftt_gate_to_dest_min)):
        m = mins.to_numpy(dtype=float)
        out[f"kmh_{leg}"] = pctl(km[m > 0] / m[m > 0] * 60)
    ids_b = per_agent(link, "[building-id] of work-building")
    link.command("assign-workplaces")
    if per_agent(link, "[building-id] of work-building") != ids_b:
        errs.append("a second workplace draw differs (seed)")
    out["distinct_workplaces"] = len(set(ids_b))
    return errs, geo


def pctl(v: np.ndarray) -> dict:
    v = np.asarray(v, dtype=float)
    if len(v) == 0:
        return {}
    return {q: round(float(np.percentile(v, p)), 1) for q, p in
            (("min", 0), ("p5", 5), ("median", 50), ("p95", 95), ("max", 100))}


def hhmm(m: float) -> str:
    return f"{int(m) // 60:02d}:{int(m) % 60:02d}"


def state_at(m: float, mode: str, dep: int, ga: int, gx: int, arr: int) -> str:
    """The model's state-at, from the engine minutes (Python mirror)."""
    if mode == "CAR":
        if m < dep:
            return "home"
        if m < ga:
            return "driving"
        if gx == -1 or m < gx:
            return "queued"
        return "driving" if m < arr else "work"
    if mode == "PT":
        if m < dep:
            return "home"
        return "transit" if m < arr else "work"
    return "home"


# --------------------------------------------------------------------------- roads (Python side)


def road_context(run_dir: Path) -> dict | None:
    """The run's road scenario, its road entries (road_entries.csv, all days) and the sections' LoS
    weights and bands (km, mwy of data/road_sections.csv: the file the GUI reads, ../data from the model)."""
    road = read_road_scenario(run_dir)
    if road is None:
        return None
    return {"road": road, "entries": pd.read_csv(run_dir / ROAD_ENTRIES_FILE),
            "los_info": los_section_info(road, ROOT / "data")}


def los_want(lw: dict, key: str) -> float:
    """A los_at_minute value as the GUI holds it (-1 for a group without traffic)."""
    v = float(lw[key])
    return v if math.isfinite(v) else -1.0


def read_plot_export(path: Path) -> dict[str, list[tuple[float, float]]]:
    """Points (x, y) of each pen of a NetLogo export-plot CSV file."""
    import csv

    rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines()))
    out: dict[str, list[tuple[float, float]]] = {}
    for j, row in enumerate(rows):
        if row and row[0] == "x" and len(row) >= 2 and row[1] == "y" and j > 0:
            names = [n.strip('"') for n in rows[j - 1]]          # pen names are written in quotes
            starts = [k for k in range(0, len(row), 4) if k < len(names) and names[k]]
            for k in starts:
                out[names[k]] = []
            for data in rows[j + 1:]:
                if not data or not any(c.strip() for c in data):
                    break
                for k in starts:
                    if k + 1 < len(data) and data[k].strip() and data[k + 1].strip():
                        out[names[k]].append((float(data[k]), float(data[k + 1])))
            break
    return out


def check_los_plot(link, day: int, ttab, info: pd.DataFrame, day_start: float, day_end: float,
                   rec: dict) -> list[str]:
    """The finished day's "% traffic at LoS E/F" and "Mean V/C" plots: one pen per region of LOS_REGIONS
    with one point per 5-minute mark from day-start to day-end, at 100 x the share (V/C: the value)
    los_at_minute gives (no point for a region without traffic)."""
    import tempfile

    marks = list(range(5 * int(day_start // 5), 5 * int(day_end // 5) + 1, 5))
    want = {m: los_at_minute(ttab, info, m) for m in marks}
    errs: list[str] = []
    worst = 0.0
    for plot, key, scale in LOS_PLOTS:
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "los_plot.csv"
            link.command(f"export-plot {_nl_string(plot)} {_nl_string(str(f.resolve()))}")
            pts = read_plot_export(f)
        for k, pen in enumerate(LOS_REGIONS):
            exp = [(m / 60, scale * want[m][key][k]) for m in marks if math.isfinite(want[m][key][k])]
            got = pts.get(pen, [])
            if len(got) != len(exp):
                errs.append(f"day {day}: the pen {pen!r} of the plot {plot!r} has {len(got)} points, expected "
                            f"{len(exp)} (one per 5-minute mark)")
                continue
            for (gx, gy), (ex, ey) in zip(got, exp):
                worst = max(worst, abs(gy - ey) / scale * 100)
                if abs(gx - ex) > 1e-9 or abs(gy - ey) > scale * LOS_TOL:
                    errs.append(f"day {day}: the pen {pen!r} of the plot {plot!r} has ({gx:.4f}, {gy:.6f}), "
                                f"expected ({ex:.4f}, {ey:.6f})")
                    break
            if plot == LOS_PLOTS[0][0]:
                rec.setdefault("los_plot_points", {})[pen] = len(got)
    rec["los_plot_max_abs_diff_pct"] = worst
    return errs


def section_times(road: RoadScenario, table, aid: int, dep: int) -> list[float]:
    """Elapsed minutes at the entry of each section of the car's route and at the gate: a probe on the
    day's speed table entering each section at minute dep + floor(el) (the engine's rule)."""
    pos = road.index
    el, out = 0.0, [0.0]
    for s in road.routes.get(aid, ()):
        i = pos[s]
        f = float(table.f[i, dep + math.floor(el) - table.start_min])
        el = el + road.ff_min[i] / f
        out.append(el)
    return out


def drive_xy(c: float, car: dict, geo_pts: np.ndarray, geo_len: np.ndarray, geo_tt: np.ndarray) -> np.ndarray:
    """Where a car driving to its gate should stand at clock c (dep <= c < gate-arr): with section
    times, at its free-flow progress (route minutes covered, each section's free-flow minutes over its
    congested minutes, times stretched to reach the gate at gate-arr) laid on route-out by route-out-minutes;
    without, at constant speed by metres."""
    dep, ga, tms, ffs = car["dep"], car["ga"], car["tms"], car["ffs"]
    if tms is None or len(tms) < 2 or tms[-1] <= 0 or geo_tt[-1] <= 0:
        return along(geo_pts, geo_len, geo_len[-1] * (c - dep) / (ga - dep))
    e = (c - dep) * tms[-1] / (ga - dep)               # engine minutes since departure
    k = min(int(np.searchsorted(tms, e, side="right")) - 1, len(ffs) - 1)
    span = tms[k + 1] - tms[k]
    covered = sum(ffs[:k]) + ffs[k] * (min(1.0, max(0.0, (e - tms[k]) / span)) if span > 0 else 1.0)
    return along(geo_pts, geo_tt, covered / sum(ffs) * geo_tt[-1])


def speed_grades(table, m: int) -> list[int]:
    """Speed grade of every section at minute m (0 = normal, 1 = slow, 2 = heavy, 3 = jammed) from the
    day's speed table (cordonlite.roads.speed_table on the day's road entries: the engine's speed
    factors, entries at minutes m - W .. m - 1); a motorway section in broken-down flow (the table's
    broken mask) is jammed whatever its speed."""
    col = m - table.start_min
    broken = table.broken[:, col] if table.broken is not None else np.zeros(table.f.shape[0], dtype=bool)
    out = []
    for f, b in zip(table.f[:, col], broken):
        g = 0
        while g < len(SPEED_BANDS) and f < SPEED_BANDS[g]:
            g += 1
        out.append(len(SPEED_BANDS) if b else g)
    return out


def check_day(link, day: int, outcomes: pd.DataFrame, geo: dict, ctx: dict | None, views: Path | None,
              out: dict, view_min: tuple[float, ...] = ()) -> list[str]:
    errs: list[str] = []
    link.command(f"start-day {day}")
    if not link.report("day-running?"):
        return [f"day {day} did not start"]
    mins = np.array(link.report(
        f"map [ c -> [ (list agent-id dep gate-arr gate-exit arr road-delay) ] of c ] {BY_AGENT}"))
    df = pd.DataFrame(mins, columns=["agent_id", "dep", "ga", "gx", "arr", "rd"]).astype(int)
    df["mode"] = [str(m) for m in per_agent(link, "mode-today")]
    o = outcomes[outcomes.day == day].set_index("agent_id")
    car = df[df["mode"] == "CAR"].set_index("agent_id")
    oc = o[o["mode"] == "CAR"]
    cols = [("dep", "depart_min"), ("ga", "gate_arrive_min"), ("gx", "gate_exit_min"), ("arr", "arrive_min")]
    if "road_delay_min" in oc.columns:
        cols.append(("rd", "road_delay_min"))
    if len(car) != len(oc) or set(car.index) != set(oc.index):
        errs.append(f"day {day}: {len(car)} cars, outcomes.csv has {len(oc)}")
    else:
        for mine, theirs in cols:
            want = oc.loc[car.index, theirs].fillna(-1).astype(int).to_numpy()
            if not (car[mine].to_numpy() == want).all():
                errs.append(f"day {day}: car {theirs} differs for {int((car[mine].to_numpy() != want).sum())} cars")
    pt = df[df["mode"] == "PT"].set_index("agent_id")
    op = o[o["mode"] == "PT"]
    if set(pt.index) != set(op.index):
        errs.append(f"day {day}: {len(pt)} PT riders, outcomes.csv has {len(op)} (or other agents)")
    elif not ((pt["dep"].to_numpy() == op.loc[pt.index, "depart_min"].to_numpy()).all()
              and (pt["arr"].to_numpy() == op.loc[pt.index, "arrive_min"].to_numpy()).all()):
        errs.append(f"day {day}: PT minutes differ from outcomes.csv")
    rec: dict = {"cars": len(car), "pt": len(pt)}
    sim_start = float(link.report("sim-start-min"))
    spm = float(link.report("steps-per-minute"))
    if float(link.report("ticks")) != (float(link.report("day-start")) - sim_start) * spm:
        errs.append(f"day {day}: ticks {link.report('ticks')} at the start of the day, not steps since sim start")
    day_end = float(link.report("day-end-min"))
    last = max([int(v) for v in df.arr if v >= 0] or [0])
    want_end = (float(link.report("sim-end-cap-min")) if ((df["mode"] == "CAR") & (df.gx < 0)).any()
                else max(last, float(link.report("day-start")) + 1)) + 2
    if day_end != want_end:
        errs.append(f"day {day}: the day ends at minute {day_end:g}, expected {want_end:g} (last arrival + 2)")

    # today's drives to the gate: section times (model vs a probe on the day's speed table) and t-out
    car_ids = [int(a) for a in car.index]
    cars_nl = 'sort-on [agent-id] commuters with [ mode-today = "CAR" ]'
    t_out = dict(zip(car_ids, ragged(link, "t-out", cars_nl)))
    drives: dict[int, dict] = {}
    table = None
    if ctx is not None:
        road: RoadScenario = ctx["road"]
        day_entries = ctx["entries"][ctx["entries"].day == day]
        last_min = int(link.report("sim-end-cap-min")) + TABLE_TAIL_MIN
        table = speed_table(road, day_entries, range(int(sim_start), last_min))
        ttab = traffic_table(road, day_entries, range(int(sim_start), last_min))   # V/C and LoS
        nl_times = dict(zip(car_ids, ragged(link, "table:get-or-default (item 2 today-road) agent-id []", cars_nl)))
        bad_t = bad_rd = 0
        diff_t = 0.0
        for aid in car_ids:
            dep = int(car.loc[aid, "dep"])
            rt = road.routes.get(aid, ())
            tms = section_times(road, table, aid, dep) if rt else None
            if rt:
                diff = np.abs(np.array(tms) - nl_times[aid]).max() if len(nl_times[aid]) == len(tms) else np.inf
                diff_t = max(diff_t, float(diff))
                bad_t += int(diff > 1e-9)
                ffsum = 0.0
                for s in rt:
                    ffsum = ffsum + road.ff_min[road.index[s]]
                bad_rd += int(max(0, math.floor(tms[-1] - ffsum + 0.5)) != int(car.loc[aid, "rd"]))
            drives[aid] = {"dep": dep, "ga": int(car.loc[aid, "ga"]), "tms": None if tms is None else np.array(tms),
                           "ffs": [road.ff_min[road.index[s]] for s in rt]}
        rec["section_times_max_abs_diff_min"] = diff_t
        if bad_t or bad_rd:
            errs.append(f"day {day}: {bad_t} cars' section times differ from the probe on road_entries.csv, "
                        f"{bad_rd} road delays differ from them")
        # the drawn route against the engine route: free-flow minutes to the gate segment's inside end
        gap = [abs(geo["tt"][a][-1] - sum(d["ffs"])) for a, d in drives.items() if d["ffs"]]
        rec["route_tt_gap_min"] = pctl(gap) if gap else {}
        rec["routes_tt_gap_over_0.01_min"] = int(sum(g > 0.01 for g in gap))
    else:
        for aid in car_ids:
            drives[aid] = {"dep": int(car.loc[aid, "dep"]), "ga": int(car.loc[aid, "ga"]), "tms": None, "ffs": []}
    # implied speed of each drive to the gate (route km over gate_arrive - depart)
    kmh = [geo["len"][a][-1] / 1000 / (d["ga"] - d["dep"]) * 60 for a, d in drives.items() if d["ga"] > d["dep"]]
    out.setdefault("_kmh_to_gate", []).extend(kmh)
    # the drive reaches the gate point exactly at gate-arr, and starts at home at dep
    at_gate = ragged(link, "drive-point gate-arr", cars_nl)
    at_home = ragged(link, "drive-point dep", cars_nl)
    bad_g = sum(float(np.hypot(*(g[:2] - geo["pts"][a][-1]))) > 1e-6 for a, g in zip(car_ids, at_gate))
    bad_h = sum(float(np.hypot(*(h[:2] - geo["pts"][a][0]))) > 1e-6 for a, h in zip(car_ids, at_home)
                if drives[a]["ga"] > drives[a]["dep"])
    bad_m = sum(len(t_out[a]) != len(geo["pts"][a]) or np.any(np.diff(t_out[a]) < -1e-12)
                or t_out[a][0] != drives[a]["dep"] or t_out[a][-1] != drives[a]["ga"] for a in car_ids)
    if bad_g or bad_h or bad_m:
        errs.append(f"day {day}: {bad_g} drives not at the gate point at gate-arr, {bad_h} not at home at "
                    f"departure, {bad_m} with t-out not running from depart to gate-arr")

    # animate to 08:30 (one go = one tick = 15 s); check drawn positions and road colours on the way
    worst = 0.0
    off_even: list[float] = []
    n_checked = bad_pos = bad_grade = bad_shown = bad_mon = bad_los = 0
    los_diff = 0.0
    for mark in sorted(set(SAMPLE_MIN) | set(view_min)):
        if mark > day_end:      # the day is over by then (a later go would start the next day)
            rec.setdefault("marks_after_day_end", []).append(hhmm(mark))
            continue
        n_go = int(round((mark - float(link.report("clock"))) * spm))
        if n_go <= 0 or not link.report("day-running?"):
            continue
        link.command(f"reset-timer repeat {n_go} [ go ]")
        if 450 < mark <= 510:   # the go loops from 07:30 to 08:30
            rec.setdefault("go_ms_per_tick_0730_0830", []).append(round(float(link.report("timer")) * 1000 / n_go, 1))
        clock = float(link.report("clock"))
        if clock != mark or float(link.report("ticks")) != (mark - sim_start) * spm:
            errs.append(f"day {day}: clock {clock} / ticks {link.report('ticks')} after going to {hhmm(mark)}, "
                        f"expected {mark} / {(mark - sim_start) * spm:g}")
            break
        xy = np.array(link.report(f"map [ c -> [ nztm-of (list xcor ycor) ] of c ] {BY_AGENT}"))
        for i, aid in enumerate(df.agent_id):
            d = drives.get(int(aid))
            if d is None or not (d["dep"] <= clock < d["ga"]):
                continue
            want = drive_xy(clock, d, geo["pts"][aid], geo["len"][aid], geo["tt"][aid])
            dist = float(np.hypot(*(xy[i] - want)))
            worst = max(worst, dist)
            if d["tms"] is not None:   # how far a constant-speed drive would be (the check can tell them apart)
                cum = geo["len"][aid]
                even = along(geo["pts"][aid], cum, cum[-1] * (clock - d["dep"]) / (d["ga"] - d["dep"]))
                off_even.append(float(np.hypot(*(even - want))))
            n_checked += 1
            bad_pos += int(dist > 1.0)
        mon = float(link.report("traffic-delay-now"))
        done = car[(car.ga >= 0) & (car.ga <= clock)]
        want_mon = float(done.rd.mean()) if len(done) else 0.0
        bad_mon += int(abs(mon - want_mon) > 1e-9)
        if table is not None and link.report("not empty? sec-links"):
            got = [int(g) for g in np.atleast_1d(link.report("speed-grade"))]
            want_g = speed_grades(table, 5 * int(clock // 5))
            bad_grade += sum(a != b for a, b in zip(got, want_g)) + abs(len(got) - len(want_g))
            bad_shown += int(link.report("length filter [ i -> (item i grade-shown != item i speed-grade) and "
                                         "not member? i grade-pending ] range length sec-ids"))
            rec[f"grades_{hhmm(clock)}"] = [want_g.count(g) for g in range(len(SPEED_BANDS) + 1)]
            mw = [g for g, m_ in zip(want_g, ctx["road"].mwy) if m_ == 1]
            if mw:
                rec[f"mwy_grades_{hhmm(clock)}"] = [mw.count(g) for g in range(len(SPEED_BANDS) + 1)]
                byp: dict[str, list[int]] = {}
                for g, m_, p_ in zip(want_g, ctx["road"].mwy, ctx["road"].profile_id):
                    if m_ == 1:
                        a = byp.setdefault(str(p_), [0, 0])
                        a[0] += int(g == len(SPEED_BANDS))
                        a[1] += 1
                rec[f"mwy_jammed_by_profile_{hhmm(clock)}"] = dict(sorted(byp.items(), key=lambda kv: int(kv[0])))
            # Level of Service at the same 5-minute mark (SPEC4 B): grades, shares, mean V/C, monitors
            lw = los_at_minute(ttab, ctx["los_info"], 5 * int(clock // 5))
            for nl_list, key in (("los-grade", "grades"), ("los-speed-grade", "speed_grades")):
                got_lg = [int(g) for g in np.atleast_1d(link.report(nl_list))]
                bad_los += sum(a != b for a, b in zip(got_lg, lw[key])) + abs(len(got_lg) - len(lw[key]))
            for nl_name, key in LOS_VALUES:
                d_ = abs(float(link.report(nl_name)) - los_want(lw, key))
                los_diff = max(los_diff, d_)
                bad_los += int(d_ > LOS_TOL)
            for nl_name, key in (("los-region-ef", "region_ef_share"), ("los-region-vc", "region_vc_mean")):
                got_r = [float(v_) for v_ in np.atleast_1d(link.report(nl_name))]
                want_r = [v_ if math.isfinite(v_) else -1.0 for v_ in lw[key]]
                d_ = max([abs(a_ - b_) for a_, b_ in zip(got_r, want_r)] + [float(abs(len(got_r) - len(want_r)))])
                los_diff = max(los_diff, d_)
                bad_los += int(d_ > LOS_TOL)
            for rep_, pre, scale in LOS_MONITORS:
                for grp, tag in (("motorway", "mwy"), ("other", "other")):
                    want = lw[f"{pre}_{tag}"]
                    shown = link.report(f'{rep_} "{grp}"')
                    ok = (abs(float(shown) - scale * want) <= scale * LOS_TOL if math.isfinite(want)
                          else str(shown) == "-")
                    bad_los += int(not ok)
            rec[f"los_{hhmm(clock)}"] = {
                "ef_pct_mwy": round(100 * lw["ef_share_mwy"], 2), "ef_pct_other": round(100 * lw["ef_share_other"], 2),
                "vc_mwy": round(lw["vc_mean_mwy"], 4), "vc_other": round(lw["vc_mean_other"], 4),
                "ef_speed_pct_mwy": round(100 * lw["ef_speed_share_mwy"], 2),
                "ef_speed_pct_other": round(100 * lw["ef_speed_share_other"], 2),
                "congested_at_pct_mwy": round(100 * lw["congested_at_share_mwy"], 2),
                "congested_at_pct_other": round(100 * lw["congested_at_share_other"], 2),
                "grades_A_F": [lw["grades"].count(g) for g in range(6)],
                "speed_grades_A_F": [lw["speed_grades"].count(g) for g in range(6)]}
        if mark == 480:
            errs += check_0800(link, day, df, rec, views)
        elif views and mark in view_min:
            export_views(link, views, f"day{day:02d}_{hhmm(clock).replace(':', '')}")
    rec["drives_checked"] = n_checked
    rec["drive_max_offset_m"] = round(worst, 6)
    if off_even:
        rec["constant_speed_offset_m"] = pctl(off_even)
    if table is not None:
        rec["los_max_abs_diff"] = los_diff
    if bad_pos or bad_grade or bad_shown or bad_mon or bad_los:
        errs.append(f"day {day}: {bad_pos} drawn cars more than 1 m from their section-time position, "
                    f"{bad_grade} section speed grades differ, {bad_shown} sections drawn in another grade "
                    f"without waiting to be redrawn, traffic delay monitor wrong at {bad_mon} marks, "
                    f"{bad_los} Level of Service grades, shares or monitors differ from cordonlite.roads")
    day_start = float(link.report("day-start"))

    link.command("finish-day")
    if float(link.report("clock")) != day_end or float(link.report("ticks")) != (day_end - sim_start) * spm:
        errs.append(f"day {day}: finish-day stopped at minute {link.report('clock')} (ticks {link.report('ticks')})")
    if table is not None and link.report("not empty? sec-links"):
        errs += check_los_plot(link, day, ttab, ctx["los_info"], day_start, day_end, rec)
    end = [str(s) for s in per_agent(link, "state-at clock")]
    want_state = [state_at(day_end, r.mode, r.dep, r.ga, r.gx, r.arr) for r in df.itertuples()]
    if end != want_state:
        errs.append(f"day {day} end: {sum(a != b for a, b in zip(end, want_state))} commuters in the wrong state")
    rec["day_end"] = hhmm(day_end)
    rec["states_end"] = {s: want_state.count(s) for s in sorted(set(want_state))}
    # where each commuter is drawn: by its bus on a public transport day (bus-riders), else by itself
    pos = np.array(link.report(f"map [ c -> [ [ (list xcor ycor) ] of drawn-agent ] of c ] {BY_AGENT}"))
    want_work = link.report(f"map [ c -> [ map-xy [building-x] of work-building [building-y] of work-building ] of c ] {BY_AGENT}")
    want_home = link.report(f"map [ c -> [ map-xy home-x home-y ] of c ] {BY_AGENT}")
    hidden = per_agent(link, "[hidden?] of drawn-agent")
    n_pt = int(link.report('count commuters with [ mode-today = "PT" ]'))
    if int(link.report("count bus-riders")) != n_pt or not link.report(
            'all? commuters with [ mode-today = "PT" ] [ hidden? and count bus-riders with [ rider = myself ] = 1 ]'):
        errs.append(f"day {day} end: the public transport riders are not each drawn by exactly one bus")
    off = 0
    for p, ws, ww, wh, h in zip(pos, want_state, want_work, want_home, hidden):
        w = ww if ws == "work" else wh if ws == "home" else None
        if w is None:
            off += int(bool(h) != (ws == "transit"))      # on the road: shown; PT in transit: hidden
        elif len(w) == 0:
            off += int(not h)
        else:
            off += int(bool(h) or np.hypot(*(p - np.array(w))) > 1e-9)
    if off:
        errs.append(f"day {day} end: {off} commuters drawn in the wrong place")
    if views:
        export_views(link, views, f"day{day:02d}_end")
    out[f"day{day}"] = rec
    return errs


def check_0800(link, day: int, df: pd.DataFrame, rec: dict, views: Path | None) -> list[str]:
    """Cars on the road at 08:00: shown, queued cars on their approach road near the gate, driving
    cars on their route."""
    states = [str(s) for s in per_agent(link, "state-at clock")]   # java.lang.String -> str
    rec["states_0800"] = {s: states.count(s) for s in sorted(set(states))}
    xy = np.array(link.report(f"map [ c -> [ nztm-of (list xcor ycor) ] of c ] {BY_AGENT}"))
    hidden = per_agent(link, "hidden?")
    ranks = np.array(per_agent(link, "q-rank"))
    gates = np.array(link.report(f"map [ c -> [ (list [gate-x] of my-gate [gate-y] of my-gate) ] of c ] {BY_AGENT}"))
    spacing = float(link.report("queue-spacing-m"))
    bad_q = bad_d = bad_h = 0
    clock = float(link.report("clock"))
    for i, s in enumerate(states):
        if s not in ("queued", "driving"):
            continue
        if hidden[i]:            # the Auckland view holds every route, so no car on the road is hidden
            bad_h += 1
            continue
        aid = int(df.agent_id.iloc[i])
        route = "route-out" if (s == "queued" or clock < df.ga.iloc[i]) else "route-in"
        pts = np.array(link.report(f"[ {route} ] of table:get commuter-of {aid}"))
        if dist_to_polyline(xy[i], pts) > 1:
            bad_d += 1
        elif s == "queued" and np.hypot(*(xy[i] - gates[i])) > ranks[i] * spacing + 1:
            bad_q += 1
    errs = check_car_sizes(link, day, spacing, rec)
    if views:
        export_views(link, views, f"day{day:02d}_0800")
    if bad_q or bad_d or bad_h:
        errs.append(f"day {day} 08:00: {bad_q} queued cars too far from their gate, {bad_d} cars off their "
                    f"route, {bad_h} cars on the road hidden")
    return errs


def check_car_sizes(link, day: int, spacing: float, rec: dict) -> list[str]:
    """In each view, queued cars are red and drawn at QUEUED_LENGTH_SHARE of their queue spacing
    (the car shape is CAR_SHAPE_LENGTH of its size long), at least MIN_QUEUED_SIZE patches and at
    most a moving car's size; moving cars keep MOVING_SIZE. The view is put back afterwards."""
    view0 = str(link.report("map-view"))
    bad = 0
    for view, tag in (("City centre", "cc"), ("Auckland", "auckland")):
        link.command(f'set-map-view "{view}"')
        env = [float(v) for v in link.report("map-env")]
        mpp = (env[1] - env[0]) / float(link.report("world-width"))
        moving = MOVING_SIZE[tag]
        want = max(MIN_QUEUED_SIZE, min(moving, QUEUED_LENGTH_SHARE * spacing / mpp / CAR_SHAPE_LENGTH))
        # (pynetlogo cannot return an empty list: no queued car at 08:00 on a calm day)
        q = (np.atleast_1d(np.asarray(link.report('[ (list size color) ] of commuters with [ state-at clock = "queued" ]'),
                                      dtype=float)).reshape(-1, 2)
             if link.report('any? commuters with [ state-at clock = "queued" ]') else np.zeros((0, 2)))
        d = (np.atleast_1d(np.asarray(link.report('[ size ] of commuters with [ state-at clock = "driving" ]'),
                                      dtype=float))
             if link.report('any? commuters with [ state-at clock = "driving" ]') else np.zeros(0))
        bad += int((np.abs(q[:, 0] - want) > 1e-9).sum() + (q[:, 1] != 15).sum() + (np.abs(d - moving) > 1e-9).sum())
        rec[f"queued_car_size_{tag}"] = round(want, 4)
        rec[f"queued_car_length_m_{tag}"] = round(CAR_SHAPE_LENGTH * want * mpp, 1)
    rec["queue_spacing_m"] = spacing
    link.command(f'set-map-view "{view0}"')
    return [f"day {day} 08:00: {bad} cars drawn at the wrong size or colour"] if bad else []


def export_views(link, folder: Path, stem: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for view, tag in (("City centre", "cc"), ("Auckland", "auckland")):
        link.command(f'set-map-view "{view}"')
        link.command(f"export-view {_nl_string(str((folder / f'{stem}_{tag}.png').resolve()))}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", type=Path, default=ROOT / "runs" / "R-clock_mock_py_s1_d10_fs6")
    ap.add_argument("--days", type=int, nargs="+", default=[1, 6])
    ap.add_argument("--views", type=Path, default=None, help="export views as PNG into this folder")
    ap.add_argument("--view-times", nargs="*", default=[],
                    help="with --views, also export the views at these clocks (HH:MM) of each day")
    ap.add_argument("--netlogo-home", default=None,
                    help="NetLogo folder (sets CORDONLITE_NETLOGO_HOME, which overrides [engine] netlogo_home)")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    summary: dict = {}
    errs: list[str] = []
    code = 1
    try:
        if args.netlogo_home:
            os.environ[NETLOGO_HOME_ENV] = args.netlogo_home
        cfg = load_config()
        view_min = tuple(float(int(h) * 60 + int(m)) for h, m in (v.split(":") for v in args.view_times))
        run_dir = args.run_dir.resolve()
        ctx = road_context(run_dir)
        summary["roads"] = ctx is not None
        link = get_netlogo_link(cfg)
        link.load_model(str(MODEL))
        t0 = time.perf_counter()
        link.command(f"setup-run {_nl_string(str(run_dir))}")   # the experiment chooser takes only its listed experiments
        summary["setup_s"] = round(time.perf_counter() - t0, 1)
        if bool(link.report("road-on?")) != (ctx is not None):
            errs.append(f"road-on? is {link.report('road-on?')} for a run folder "
                        f"with{'' if ctx else 'out'} road files")
        if ctx is not None:
            rd = ctx["road"]
            summary["sections"] = len(rd.section_ids)
            summary["sections_drawn"] = int(link.report("length filter [ fs -> not empty? fs ] sec-links"))
            summary["profiles"] = {str(k): int(sum(p_ == k for p_ in rd.profile_id)) for k in sorted(rd.profiles)}
            summary["cap_drops"] = {repr(d): int(sum(x == d for x in rd.cap_drop)) for d in sorted(set(rd.cap_drop))}
            if int(link.report("table:length road-profiles")) != len(rd.profiles):
                errs.append(f"the model read {link.report('table:length road-profiles')} time profiles, "
                            f"the run has {len(rd.profiles)}")
            keep_nl = [float(x) for x in np.atleast_1d(link.report("sec-keep"))]
            if keep_nl != list(rd.sec_keep):
                errs.append("the model's per-section capacity-drop divisors (sec-keep) differ from the run's")
            # the regions of the LoS plots: the model's rules (region-of) give the same region as Python's
            region_nl = [int(x) for x in np.atleast_1d(link.report("sec-region"))]
            region_py = [int(x) for x in ctx["los_info"]["region"]]
            if region_nl != region_py:
                errs.append(f"{sum(a != b for a, b in zip(region_nl, region_py))} of {len(region_py)} sections have "
                            "another LoS region in the model than in cordonlite.roads.los_region_of")
            summary["los_region_sections"] = {n: region_py.count(k) for k, n in enumerate(LOS_REGIONS)}
        e, geo = check_setup(link, run_dir, summary)
        errs += e
        outcomes = pd.read_csv(run_dir / "outcomes.csv")
        for d in sorted(args.days):
            # start-day only moves forward: days in between are finished without animation
            while int(link.report("current-day")) < d - 1:
                link.command("finish-day")
            errs += check_day(link, d, outcomes, geo, ctx, args.views, summary, view_min)
        summary["kmh_to_gate"] = pctl(summary.pop("_kmh_to_gate", []))
        code = 0 if not errs else 1
    except Exception:  # noqa: BLE001 - report and exit non-zero
        summary["exception"] = traceback.format_exc()
        code = 2
    summary.pop("_kmh_to_gate", None)
    summary["errors"] = errs
    summary["exit_code"] = code
    try:
        text = json.dumps(summary, indent=1, default=str)
    except (TypeError, ValueError) as ex:       # never hang on a summary that cannot be written
        text = json.dumps({"exception": f"summary not serialisable: {ex}", "errors": errs, "exit_code": 2})
        code = 2
    if args.json:
        args.json.write_text(text)
    print(text)
    shutdown_netlogo_link(timeout_s=5.0)
    return code


if __name__ == "__main__":
    hard_exit(main())
