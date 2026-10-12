"""PyEngine == NetLogoEngine, run in a child process (the JVM starts once per process and may hang on exit).

Skipped unless pytest gets --run-netlogo or CORDONLITE_RUN_NETLOGO=1. The child is
scripts/check_netlogo_equivalence.py, which ends with os._exit. It compares both engines (outcomes,
queue profile and road entries, exactly) on the conftest scenario, a low-capacity copy of it (every
capacity below 1 car per minute), a copy with synthetic congested road files (sections at the speed
floor, commuter entries in the flow window, cars sharing a gate arrival minute, agents without a
route), the same with motorway flow breakdown (motorway sections broken down inside their
usual-traffic window, outside it when today's commuters lift V/C to the threshold, at the jam
speed, and not broken down), the same with NZTA-style per-section values (three time profiles in
the long road_profile.csv, a capacity drop per section) and, when the prep data is present, a
scenario of 300 real personas with the real road files (motorway breakdown on, the config default;
the NZTA site profiles and capacity drops).
Plan sets: random days plus all-SKIP, identical departures, identical free-flow gate arrivals, a
single used corridor (the others empty), a single car, shuffled rows with missing non-car departures
and, with roads, everyone leaving at 07:45, departures on every minute and a 07:30 peak. It also
exercises the GUI procedures headless on the NZTA-style copy (its car minutes must equal PyEngine's)
and times run_day for 300 agents. CORDONLITE_NETLOGO_HOME, when set, overrides [engine] netlogo_home.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_netlogo_equivalence.py"
REAL_DATA = ("origins.csv", "corridors.csv", "road_sections.csv", "origin_sections.csv", "road_profile.csv")


def _run(args: list[str], tmp_path: Path, timeout: int = 900) -> dict:
    out = tmp_path / "summary.json"
    cmd = [sys.executable, str(SCRIPT), *args, "--json", str(out)]
    if os.environ.get("CORDONLITE_NETLOGO_HOME"):
        cmd += ["--netlogo-home", os.environ["CORDONLITE_NETLOGO_HOME"]]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    assert out.exists(), f"no summary; rc={proc.returncode}\nstderr tail:\n{proc.stderr[-3000:]}"
    summary = json.loads(out.read_text())
    assert "exception" not in summary, summary["exception"]
    summary["_rc"] = proc.returncode
    return summary


def _road_exercised(cov: dict) -> None:
    assert cov["road"] and cov["entries"] > 0, cov
    assert cov["floor_hits"] > 0 and cov["window_entries"] > 0, cov
    assert cov["gate_ties"] > 0 and cov["cars_road_delayed"] > 0, cov


def _motorways_exercised(cov: dict, commuter_trigger: bool = True) -> None:
    """Motorway sections broken down by their window, by the V/C threshold (today's commuters lifting
    it, commuter_trigger), at the jam speed, and motorway entries in plain flow."""
    assert cov["mwy_breakdown"] and cov["n_mwy_sections"] > 0, cov
    assert cov["mwy_window"] > 0 and cov["mwy_jam_cap"] > 0 and cov["mwy_plain"] > 0, cov
    assert cov["mwy_trigger"] > 0 and (cov["mwy_trigger_commuters"] > 0 or not commuter_trigger), cov


def _profiles_exercised(cov: dict, n_profiles: int = 3) -> None:
    """Several time profiles (entries on each) and per-section capacity drops: broken-down entries on
    sections whose drop is not the global one, some of them below the jam speed (the drop matters)."""
    assert cov["n_profiles"] >= n_profiles and cov["n_cap_drops"] >= 2, cov
    assert sum(1 for k, v in cov.items() if k.startswith("profile_") and v > 0) >= n_profiles, cov
    assert cov["mwy_own_drop"] > 0, cov


@pytest.mark.netlogo
def test_pyengine_equals_netlogoengine(tiny_scenario_dir: Path, tmp_path: Path) -> None:
    real = all((ROOT / "data" / f).exists() for f in REAL_DATA)
    s = _run(["--scenario", str(tiny_scenario_dir), "--n-random", "8", "--seed", "20270",
              "--gui-smoke", "--timing-agents", "300"] + (["--real-agents", "300"] if real else []), tmp_path)
    eq = s["equivalence"]
    bad = [c for c in eq["checks"] if not c["ok"]]
    assert not bad, json.dumps(bad, indent=1)[:4000]
    labels = {c["label"] for c in eq["checks"]}
    assert {"all_skip", "ties_same_arrival", "one_corridor_only", "single_car", "shuffled_nan",
            "all_car_0745", "spread_every_minute", "peak_0730"} <= labels
    variants = {"base", "lowcap", "road", "road_mwy", "road_nzta"} | ({"real"} if real else set())
    assert {c["variant"] for c in eq["checks"]} == variants
    # 14 plan sets per variant (8 random + 6), 3 more on each road variant
    assert eq["n_ok"] == eq["n_checks"] == 14 * len(variants) + 3 * (len(variants) - 2)
    assert not eq["coverage"]["base"]["road"] and eq["coverage"]["base"]["entries"] == 0
    _road_exercised(eq["coverage"]["road"])
    assert not eq["coverage"]["road"]["mwy_breakdown"] and eq["coverage"]["road"]["mwy_window"] == 0
    _road_exercised(eq["coverage"]["road_mwy"])
    _motorways_exercised(eq["coverage"]["road_mwy"])
    assert eq["coverage"]["road_mwy"]["n_profiles"] == 1 and eq["coverage"]["road_mwy"]["mwy_own_drop"] == 0
    _road_exercised(eq["coverage"]["road_nzta"])
    _motorways_exercised(eq["coverage"]["road_nzta"])
    _profiles_exercised(eq["coverage"]["road_nzta"])
    assert eq["coverage"]["road_nzta"]["mwy_own_drop_below_jam"] > 0
    if real:
        _road_exercised(eq["coverage"]["real"])
        _motorways_exercised(eq["coverage"]["real"], commuter_trigger=False)
        assert eq["coverage"]["real"]["n_routes"] == 300
        if eq["coverage"]["real"]["n_profiles"] > 1:      # data with NZTA sites (SPEC3)
            _profiles_exercised(eq["coverage"]["real"], n_profiles=2)
    g = s["gui_smoke"]
    assert g["ok"], g
    assert g["road_on"] and g["day1_minutes"]["cars_road_delayed"] > 0
    assert s["timing"]["equal"]
    assert s["_rc"] == 0


@pytest.mark.netlogo
def test_netlogo_second_seed_builtin_scenario(tmp_path: Path) -> None:
    s = _run(["--n-random", "6", "--seed", "99"], tmp_path)
    eq = s["equivalence"]
    assert eq["n_ok"] == eq["n_checks"] == 5 * 12 + 3 * 3
    assert {c["variant"] for c in eq["checks"]} == {"base", "lowcap", "road", "road_mwy", "road_nzta"}
    _road_exercised(eq["coverage"]["road"])
    _motorways_exercised(eq["coverage"]["road_mwy"])
    _profiles_exercised(eq["coverage"]["road_nzta"])
    assert s["_rc"] == 0
