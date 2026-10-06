"""Compare PyEngine and NetLogoEngine on random and edge-case plan sets (own process).

Usage (from the cordon_lite folder):
    .venv/bin/python scripts/check_netlogo_equivalence.py [--scenario DIR] [--n-random 6] [--seed 7]
                                                           [--timing-agents 300] [--gui-smoke] [--json OUT]

Without --scenario a synthetic scenario (3 corridors, 20 agents, as in tests/conftest.py) is built.
Each scenario is also run with a low-capacity variant (all capacities < 1 car per minute).
The script prints a JSON summary and ends with os._exit (exit code 0 if every comparison
matched), because the NetLogo JVM can start only once per process and may hang on exit.
"""

from __future__ import annotations

import argparse
import json
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
from cordonlite.config import load_config  # noqa: E402
from cordonlite.engine import (  # noqa: E402
    AGENTS_COLUMNS, AGENTS_FILE, CORRIDORS_COLUMNS, CORRIDORS_FILE, FEES_FILE,
    NetLogoEngine, PyEngine, hard_exit, shutdown_netlogo_link,
)

MODES = np.array(["CAR", "PT", "WFH", "SKIP"])


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
    # identical gate arrival minute for everyone (maximal ties)
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


def compare(a, b) -> list[str]:
    errs = []
    for name in ("outcomes", "profile"):
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


def run_checks(scenario: Path, n_random: int, seed: int, work: Path) -> dict:
    cfg = load_config()
    results = []
    variants = [("base", scenario), ("lowcap", low_capacity_variant(scenario, work / (scenario.name + "_lowcap")))]
    nl = NetLogoEngine(cfg)
    for vname, vdir in variants:
        py = PyEngine(cfg)
        py.load(vdir)
        nl.load(vdir)
        agents = pd.read_csv(vdir / AGENTS_FILE)
        for day, (label, plans, fee_on) in enumerate(plan_sets(agents, n_random, seed), start=1):
            ra = py.run_day(day, plans, fee_on)
            rb = nl.run_day(day, plans, fee_on)
            errs = compare(ra, rb)
            results.append({"variant": vname, "label": label, "day": day, "cars": int(len(ra.outcomes)),
                            "profile_rows": int(len(ra.profile)), "ok": not errs, "errors": errs})
    nl.close()
    return {"scenario": str(scenario), "n_checks": len(results),
            "n_ok": sum(r["ok"] for r in results), "checks": results}


def timing(n_agents: int, work: Path, n_days: int = 5, seed: int = 3) -> dict:
    cfg = load_config()
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


def gui_smoke(scenario: Path, work: Path) -> dict:
    """Exercise the GUI headless: setup (map, network, routes), go, finish-day over two demo days, plots."""
    from cordonlite.engine import _nl_string, get_netlogo_link

    cfg = load_config()
    d = work / "gui_scenario"
    shutil.copytree(scenario, d, ignore=shutil.ignore_patterns("plans_day*", "outcomes_day*", "profile_day*"))
    link = get_netlogo_link(cfg)
    link.load_model(str(cfg.resolve_path(cfg.engine.model_path)))
    link.command(f"set scenario-dir {_nl_string(str(d))}")
    link.command("set fee-start-day 2")
    link.command("setup")
    out: dict = {"corridors": int(link.report("length corr-ids")), "commuters": int(link.report("count commuters")),
                 "gates": int(link.report("count gates")), "nodes": int(link.report("count nodes"))}
    link.command("go")              # starts day 1 and plays one tick
    out["day1_started"] = bool(link.report("day-running?")) and int(link.report("current-day")) == 1
    link.command("finish-day")      # rest of day 1
    link.command("finish-day")      # day 2 (charged from fee-start-day 2)
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
    out["queue_pens_ok"] = all(bool(link.report(f'plot-pen-exists? "{int(c)}: {n}"'))
                               for c, n in zip(names["corridor_id"], names["name"]))
    link.command('set-current-plot "Cordon entries per 15 min"')
    out["entries_pen_ok"] = bool(link.report('plot-pen-exists? "entries"'))
    out["ok"] = (out["day1_started"] and out["day"] == 2 and out["fee_active_day2"] and out["all_arrived"]
                 and out["ticks_ok"] and out["no_files_written"] and out["queue_pens_ok"]
                 and out["entries_pen_ok"] and out["nodes"] > 0 and 1 <= out["gates"] <= out["corridors"])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenario", type=Path, default=None)
    ap.add_argument("--n-random", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--timing-agents", type=int, default=0, help="also time run_day for this many agents")
    ap.add_argument("--gui-smoke", action="store_true", help="also exercise the GUI procedures headless")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    summary: dict = {}
    code = 1
    try:
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="cl_nl_") as tmp:
            work = Path(tmp)
            scen = args.scenario.resolve() if args.scenario else tiny_scenario(work / "tiny")
            summary["equivalence"] = run_checks(scen, args.n_random, args.seed, work)
            if args.gui_smoke:
                summary["gui_smoke"] = gui_smoke(scen, work)
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
