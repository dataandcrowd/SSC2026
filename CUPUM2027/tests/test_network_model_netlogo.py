"""The GUI of netlogo7/cordon_lite.nlogox against a finished run, in a child process (the JVM starts once
per process and may hang on exit).

Skipped unless pytest gets --run-netlogo or CORDONLITE_RUN_NETLOGO=1. Each case first writes an
11-day R-clock mock run (PyEngine) into tmp_path, with congested roads (road.enabled = true, the
config) and with free-flow roads (road.enabled = false), then runs scripts/check_network_model.py
on it, which ends with os._exit. The script builds the TomTom network and checks gates,
workplaces, the engine minutes of every car against outcomes.csv, that each car's drive to its gate
follows its section times (constant speed on free-flow roads) and reaches the gate point at its
gate-arrive minute, the road colours (speed grades of the sections: the engine's speed factor, as
cordonlite.roads computes it; motorway sections in broken-down flow jammed), the traffic delay
monitor, the Level of Service monitors (E/F by V/C and by speed, mean V/C), grades and plot (SPEC4 B:
equal to cordonlite.roads los_at_minute at the same 5-minute marks), where queued and driving cars stand
while a day is animated, and that at the end of the day CAR and PT commuters are at their
building. Needs the map layers (python -m prep.build_netlogo_layers) and the road data (python -m
prep.build_roads). CORDONLITE_NETLOGO_HOME, when set, overrides [engine] netlogo_home for this check
(e.g. NetLogo installed outside /Applications).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_network_model.py"


@pytest.mark.netlogo
@pytest.mark.parametrize("roads", [True, False], ids=["congested_roads", "free_flow_roads"])
def test_network_model_matches_the_run(tmp_path: Path, roads: bool) -> None:
    run = [sys.executable, "-m", "cordonlite.run", "--arm", "R-clock", "--backend", "mock", "--engine", "py",
           "--days", "11", "--seed", "1", "--out", str(tmp_path), "--name", "run", "--quiet",
           "--set", f"road.enabled={'true' if roads else 'false'}"]
    proc = subprocess.run(run, cwd=ROOT, capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, proc.stderr[-3000:]
    run_dir = tmp_path / "run"
    assert (run_dir / "road_sections.csv").exists() == roads
    out = tmp_path / "summary.json"
    args = [sys.executable, str(SCRIPT), "--run-dir", str(run_dir), "--days", "1", "11", "--json", str(out)]
    if os.environ.get("CORDONLITE_NETLOGO_HOME"):
        args += ["--netlogo-home", os.environ["CORDONLITE_NETLOGO_HOME"]]
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=1800)
    assert out.exists(), f"no summary; rc={proc.returncode}\nstderr tail:\n{proc.stderr[-3000:]}"
    s = json.loads(out.read_text())
    assert "exception" not in s, s["exception"]
    assert not s["errors"], s["errors"]
    assert s["roads"] is roads
    assert s["counts"]["nodes"] == 28507 and s["counts"]["roads"] == 30835
    assert s["max_outside_m"] <= 300
    for d in ("day1", "day11"):
        assert s[d]["cars"] > 0 and s[d]["drives_checked"] > 0
    assert 5 < s["kmh_to_gate"]["median"] < 120
    if roads:
        assert s["sections_drawn"] == s["sections"] > 0
        assert s["day1"]["section_times_max_abs_diff_min"] <= 1e-9
        assert any(k.startswith("grades_") for k in s["day1"])   # the speed grades were checked
        # Level of Service (SPEC4 B): checked at the marks and on the day's plot (one point per 5 min)
        for d in ("day1", "day11"):
            marks = [k for k in s[d] if k.startswith("los_") and k[4:6].isdigit()]
            assert marks, sorted(s[d])
            # the speed-based LoS (grades, E/F shares, monitors) was checked at the same marks
            assert all("ef_speed_pct_mwy" in s[d][k] and len(s[d][k]["speed_grades_A_F"]) == 6 for k in marks)
            assert s[d]["los_max_abs_diff"] <= 1e-9 and s[d]["los_plot_max_abs_diff_pct"] <= 1e-7
            n_marks = s[d]["los_plot_points"]
            # every region with traffic has the same number of points: one per 5-minute mark
            assert n_marks["Other roads"] > 12 and n_marks["SH1"] == n_marks["Other roads"], n_marks
            assert set(n_marks) == {"SH1", "SH16", "SH20", "North Shore", "New Lynn", "Green Lane", "Other roads"}
        # motorway breakdown (the config default): every motorway section whose usual-traffic window
        # holds 08:00 is broken down and drawn jammed (purple). With the NZTA counts (SPEC3) the
        # windows differ by site and some motorways (SH20) have none, so not every motorway is purple
        rs = pd.read_csv(run_dir / "road_sections.csv")
        in_win = int(((rs["mwy"] == 1) & (rs["bd_on"] <= 480) & (480 < rs["bd_off"])).sum())
        assert in_win > 0
        for d in ("day1", "day11"):
            g = s[d]["mwy_grades_08:00"]
            assert sum(g) == int((rs["mwy"] == 1).sum()) and in_win <= g[3], (g, in_win)
            byp = s[d]["mwy_jammed_by_profile_08:00"]
            assert sum(v[0] for v in byp.values()) == g[3] and sum(v[1] for v in byp.values()) == sum(g)
        if "profile_id" in rs.columns:   # data with NZTA sites: several profiles and capacity drops read
            assert len(s["profiles"]) > 1 and len(s["cap_drops"]) > 1, (s["profiles"], s["cap_drops"])
    assert proc.returncode == 0
