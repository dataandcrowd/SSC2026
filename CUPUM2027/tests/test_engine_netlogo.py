"""PyEngine == NetLogoEngine, run in a child process (the JVM starts once per process and may hang on exit).

Skipped unless pytest gets --run-netlogo or CORDONLITE_RUN_NETLOGO=1. The child is
scripts/check_netlogo_equivalence.py, which ends with os._exit. It compares both engines on the
conftest scenario and a low-capacity copy of it (every capacity below 1 car per minute), over random
plan sets plus all-SKIP, identical departures, identical gate arrivals (ties), a single used corridor
(the others empty), a single car, and shuffled rows with missing non-car departures; it also
exercises the GUI procedures headless and times run_day for 300 agents.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_netlogo_equivalence.py"


def _run(args: list[str], tmp_path: Path, timeout: int = 600) -> dict:
    out = tmp_path / "summary.json"
    proc = subprocess.run([sys.executable, str(SCRIPT), *args, "--json", str(out)], cwd=ROOT,
                          capture_output=True, text=True, timeout=timeout)
    assert out.exists(), f"no summary; rc={proc.returncode}\nstderr tail:\n{proc.stderr[-3000:]}"
    summary = json.loads(out.read_text())
    assert "exception" not in summary, summary["exception"]
    summary["_rc"] = proc.returncode
    return summary


@pytest.mark.netlogo
def test_pyengine_equals_netlogoengine(tiny_scenario_dir: Path, tmp_path: Path) -> None:
    s = _run(["--scenario", str(tiny_scenario_dir), "--n-random", "8", "--seed", "20270",
              "--gui-smoke", "--timing-agents", "300"], tmp_path)
    eq = s["equivalence"]
    bad = [c for c in eq["checks"] if not c["ok"]]
    assert not bad, json.dumps(bad, indent=1)[:4000]
    labels = {c["label"] for c in eq["checks"]}
    assert {"all_skip", "ties_same_arrival", "one_corridor_only", "single_car", "shuffled_nan"} <= labels
    assert {c["variant"] for c in eq["checks"]} == {"base", "lowcap"}
    assert eq["n_ok"] == eq["n_checks"] >= 2 * 14
    assert s["gui_smoke"]["ok"], s["gui_smoke"]
    assert s["timing"]["equal"]
    assert s["_rc"] == 0


@pytest.mark.netlogo
def test_netlogo_second_seed_builtin_scenario(tmp_path: Path) -> None:
    s = _run(["--n-random", "6", "--seed", "99"], tmp_path)
    assert s["equivalence"]["n_ok"] == s["equivalence"]["n_checks"]
    assert s["_rc"] == 0
