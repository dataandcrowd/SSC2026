"""The GUI of netlogo7/cordon_lite.nlogox against a finished run, in a child process (the JVM starts once
per process and may hang on exit).

Skipped unless pytest gets --run-netlogo or CORDONLITE_RUN_NETLOGO=1. The child is
scripts/check_network_model.py, which ends with os._exit. It loads the canonical R-clock run, builds
the TomTom network and checks gates, workplaces, the engine minutes of every car against
outcomes.csv, where queued and driving cars stand while a day is animated, and that at the end of
the day CAR and PT commuters are at their building. Needs the map layers (python -m
prep.build_netlogo_layers) and the run folder runs/R-clock_mock_py_s1. CORDONLITE_NETLOGO_HOME, when
set, overrides [engine] netlogo_home for this check (e.g. NetLogo installed outside /Applications).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_network_model.py"


@pytest.mark.netlogo
def test_network_model_matches_the_run(tmp_path: Path) -> None:
    out = tmp_path / "summary.json"
    args = [sys.executable, str(SCRIPT), "--days", "1", "11", "--json", str(out)]
    if os.environ.get("CORDONLITE_NETLOGO_HOME"):
        args += ["--netlogo-home", os.environ["CORDONLITE_NETLOGO_HOME"]]
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=1800)
    assert out.exists(), f"no summary; rc={proc.returncode}\nstderr tail:\n{proc.stderr[-3000:]}"
    s = json.loads(out.read_text())
    assert "exception" not in s, s["exception"]
    assert not s["errors"], s["errors"]
    assert s["counts"]["nodes"] == 28507 and s["counts"]["roads"] == 30835
    assert s["max_outside_m"] <= 300
    assert s["day1"]["cars"] > 0 and s["day11"]["cars"] > 0
    assert proc.returncode == 0
