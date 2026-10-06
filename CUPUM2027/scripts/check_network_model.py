"""Check the GUI of netlogo7/cordon_lite.nlogox against a finished run (own process).

Usage (from the cordon_lite folder):
    .venv/bin/python scripts/check_network_model.py [--run-dir runs/R-clock_mock_py_s1] [--days 1 11]
                                                    [--views DIR] [--netlogo-home PATH] [--json OUT]

setup loads the run folder, builds the TomTom road network and places the city-centre buildings.
The script checks the network (28,507 nodes and 30,835 roads, the giant component prep routes on;
1,106 nodes in the cordon), every commuter's gate (the prep gate of its origin, entered from
outside to inside), its workplace (a building inside the cordon, the same on a second draw) and
that its leg from the gate to its parking node runs outside the cordon polygon for at most
MAX_OUTSIDE_M metres (only from the Wellesley Street ramp and Hopetoun Street gates, whose inside
ends reach the rest of the cordon through a road just outside it); and for each day:
  - every car's depart, gate-arrive, gate-exit and arrive minute equals the run's outcomes.csv;
  - PT riders are the run's PT riders (their minutes are read from that file: a consistency check);
  - one go is one tick of 1/steps-per-minute minutes (15 s; the counter counts steps since
    sim_start_min);
  - while the day is animated (to 08:00), no car on the road is hidden, a queued car stands on its
    approach road (within 1 m of it) at most q-rank x queue-spacing-m (+1 m) from its gate point,
    and a driving car is on its route;
  - the day ends 2 minutes after the last arrival (sim_end_cap_min if a car is never served), and
    then every commuter is in the state its engine minutes give: at its building (CAR, PT), at
    home (WFH, SKIP), still queued (a car never served).
--views DIR also exports the Auckland and City-centre views at 08:00 and at the end of each day.
The script prints a JSON summary and ends with os._exit (exit code 0 if every check passed),
because the NetLogo JVM can start only once per process and may hang on exit.
"""

from __future__ import annotations

import argparse
import json
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
from cordonlite.engine import _nl_string, get_netlogo_link, hard_exit, shutdown_netlogo_link  # noqa: E402

MODEL = ROOT / "netlogo7" / "cordon_lite.nlogox"
N_NODES, N_ROADS, N_IN_CORDON = 28507, 30835, 1106   # prep giant component (data/prep_report.md)
MAX_OUTSIDE_M = 200.0   # longest stretch outside the cordon on a gate-to-building leg (about 180 m, gate 20)
BY_AGENT = "sort-on [agent-id] commuters"


def per_agent(link, expr: str) -> list:
    """[expr] of every commuter in agent_id order (one type per call: pynetlogo cannot mix types)."""
    return list(link.report(f"map [ c -> [ {expr} ] of c ] {BY_AGENT}"))


def dist_to_polyline(p: np.ndarray, pts: np.ndarray) -> float:
    """Euclidean distance from point p to the polyline pts (metres)."""
    if len(pts) == 1:
        return float(np.hypot(*(p - pts[0])))
    a, b = pts[:-1], pts[1:]
    ab = b - a
    t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
    return float(np.hypot(*(a + t[:, None] * ab - p).T).min())


def check_setup(link, run_dir: Path, out: dict) -> list[str]:
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
    if not link.report("all? gates [ v-node = nobody or ((not [in-cordon?] of u-node) and [in-cordon?] of v-node) ]"):
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
    # route-in lists have different lengths, which pynetlogo cannot return as one nested list
    n_pts = np.array(per_agent(link, "length route-in"), dtype=int)
    flat = np.array(link.report(f"reduce sentence map [ c -> [ route-in ] of c ] {BY_AGENT}"))
    legs = np.split(flat, np.cumsum(n_pts)[:-1])
    outside_m = np.array([shapely.LineString(leg).difference(cordon).length if len(leg) > 1 else 0.0
                          for leg in legs])
    if outside_m.max() > MAX_OUTSIDE_M:
        errs.append(f"a leg from the gate to the building runs {outside_m.max():.0f} m outside the cordon")
    out["legs_leaving_cordon"] = int((outside_m > 0).sum())
    out["max_outside_m"] = round(float(outside_m.max()), 1)
    # implied constant speeds (km/h): each leg is covered in the engine's free-flow minutes
    ag = agents.sort_values("agent_id")
    for leg, var, mins in (("to_gate", "last len-out", ag.fftt_to_gate_min), ("gate_to_building", "last len-in",
                                                                               ag.fftt_gate_to_dest_min)):
        km = np.array(per_agent(link, var), dtype=float) / 1000
        kmh = km / np.maximum(mins.to_numpy(), 1e-9) * 60
        kmh = kmh[mins.to_numpy() > 0]
        out[f"kmh_{leg}"] = {q: round(float(np.percentile(kmh, v)), 1) for q, v in
                             (("min", 0), ("p5", 5), ("median", 50), ("p95", 95), ("max", 100))}
    ids = per_agent(link, "[building-id] of work-building")
    link.command("assign-workplaces")
    if per_agent(link, "[building-id] of work-building") != ids:
        errs.append("a second workplace draw differs (seed)")
    out["distinct_workplaces"] = len(set(ids))
    return errs


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


def check_day(link, day: int, outcomes: pd.DataFrame, views: Path | None, out: dict) -> list[str]:
    errs: list[str] = []
    link.command(f"start-day {day}")
    if not link.report("day-running?"):
        return [f"day {day} did not start"]
    mins = np.array(link.report(f"map [ c -> [ (list agent-id dep gate-arr gate-exit arr) ] of c ] {BY_AGENT}"))
    df = pd.DataFrame(mins, columns=["agent_id", "dep", "ga", "gx", "arr"]).astype(int)
    df["mode"] = [str(m) for m in per_agent(link, "mode-today")]
    o = outcomes[outcomes.day == day].set_index("agent_id")
    car = df[df["mode"] == "CAR"].set_index("agent_id")
    oc = o[o["mode"] == "CAR"]
    cols = [("dep", "depart_min"), ("ga", "gate_arrive_min"), ("gx", "gate_exit_min"), ("arr", "arrive_min")]
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
    # animate to 08:00 (one go = one minute = one tick) and check where the cars on the road are
    t0 = time.perf_counter()
    steps = 0
    while float(link.report("clock")) < 480 and link.report("day-running?"):
        link.command("go")
        steps += 1
    rec["ticks_to_0800"] = steps
    rec["s_per_tick"] = round((time.perf_counter() - t0) / max(1, steps), 4)
    if float(link.report("clock")) != 480 or float(link.report("ticks")) != (480 - sim_start) * spm:
        errs.append(f"day {day}: clock {link.report('clock')} / ticks {link.report('ticks')} at 08:00, "
                    f"expected 480 / {(480 - sim_start) * spm:g}")
    states = [str(s) for s in per_agent(link, "state-at clock")]   # java.lang.String -> str
    rec["states_0800"] = {s: states.count(s) for s in sorted(set(states))}
    xy = np.array(link.report(f"map [ c -> [ nztm-of (list xcor ycor) ] of c ] {BY_AGENT}"))
    hidden = per_agent(link, "hidden?")
    ranks = np.array(per_agent(link, "q-rank"))
    gates = np.array(link.report(f"map [ c -> [ (list [gx] of my-gate [gy] of my-gate) ] of c ] {BY_AGENT}"))
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
    if bad_q or bad_d or bad_h:
        errs.append(f"day {day} 08:00: {bad_q} queued cars too far from their gate, {bad_d} cars off their "
                    f"route, {bad_h} cars on the road hidden")
    if views:
        export_views(link, views, f"day{day:02d}_0800")
    link.command("finish-day")
    if float(link.report("clock")) != day_end or float(link.report("ticks")) != (day_end - sim_start) * spm:
        errs.append(f"day {day}: finish-day stopped at minute {link.report('clock')} (ticks {link.report('ticks')})")
    end = [str(s) for s in per_agent(link, "state-at clock")]
    want_state = [state_at(day_end, r.mode, r.dep, r.ga, r.gx, r.arr) for r in df.itertuples()]
    if end != want_state:
        errs.append(f"day {day} end: {sum(a != b for a, b in zip(end, want_state))} commuters in the wrong state")
    rec["day_end"] = hhmm(day_end)
    rec["states_end"] = {s: want_state.count(s) for s in sorted(set(want_state))}
    pos = np.array(link.report(f"map [ c -> [ (list xcor ycor) ] of c ] {BY_AGENT}"))
    want_work = link.report(f"map [ c -> [ map-xy [bx] of work-building [by] of work-building ] of c ] {BY_AGENT}")
    want_home = link.report(f"map [ c -> [ map-xy home-x home-y ] of c ] {BY_AGENT}")
    hidden = per_agent(link, "hidden?")
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


def export_views(link, folder: Path, stem: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for view, tag in (("City centre", "cc"), ("Auckland", "auckland")):
        link.command(f'set-map-view "{view}"')
        link.command(f"export-view {_nl_string(str((folder / f'{stem}_{tag}.png').resolve()))}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", type=Path, default=ROOT / "runs" / "R-clock_mock_py_s1")
    ap.add_argument("--days", type=int, nargs="+", default=[1, 11])
    ap.add_argument("--views", type=Path, default=None, help="export views as PNG into this folder")
    ap.add_argument("--netlogo-home", default=None, help="override [engine] netlogo_home")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    summary: dict = {}
    errs: list[str] = []
    code = 1
    try:
        cfg = load_config(overrides={"engine.netlogo_home": args.netlogo_home} if args.netlogo_home else None)
        run_dir = args.run_dir.resolve()
        link = get_netlogo_link(cfg)
        link.load_model(str(MODEL))
        link.command(f"set scenario-dir {_nl_string(str(run_dir))}")
        t0 = time.perf_counter()
        link.command("setup")
        summary["setup_s"] = round(time.perf_counter() - t0, 1)
        errs += check_setup(link, run_dir, summary)
        outcomes = pd.read_csv(run_dir / "outcomes.csv")
        for d in sorted(args.days):
            # start-day only moves forward: days in between are finished without animation
            while int(link.report("current-day")) < d - 1:
                link.command("finish-day")
            errs += check_day(link, d, outcomes, args.views, summary)
        code = 0 if not errs else 1
    except Exception:  # noqa: BLE001 - report and exit non-zero
        summary["exception"] = traceback.format_exc()
        code = 2
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
