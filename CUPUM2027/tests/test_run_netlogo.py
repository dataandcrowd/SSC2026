"""End-to-end run with NetLogoEngine == PyEngine (subprocess: the JVM starts once per process)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.netlogo
def test_run_netlogo_equals_py(tmp_path: Path, tiny_origins: pd.DataFrame,
                               tiny_corridors_prep: pd.DataFrame) -> None:
    from cordonlite.analysis import compare_runs

    data = tmp_path / "data"
    data.mkdir()
    tiny_origins.to_csv(data / "origins.csv", index=False)
    tiny_corridors_prep.to_csv(data / "corridors.csv", index=False)
    common = ["--arm", "R-clock", "--backend", "mock", "--n-agents", "20", "--days", "6",
              "--fee-start", "3", "--seed", "3", "--capacity-scale", "0.4", "--quiet",
              "--out", str(tmp_path / "runs"), "--set", f"run.data_dir={data}",
              "--set", "persona.n_twins=4", "--set", "events.pt_disruption_day=5"]
    for eng in ("py", "netlogo"):
        p = subprocess.run([sys.executable, "-m", "cordonlite.run", *common, "--engine", eng,
                            "--name", f"R-clock_mock_{eng}_s3"],
                           cwd=ROOT, capture_output=True, text=True, timeout=300)
        assert p.returncode == 0, p.stderr[-3000:]
    res = compare_runs(tmp_path / "runs" / "R-clock_mock_py_s3", tmp_path / "runs" / "R-clock_mock_netlogo_s3")
    assert res["identical"], res
    # same file set in both folders (NetLogo's per-day exchange files are removed after the run)
    names = [sorted(f.name for f in (tmp_path / "runs" / f"R-clock_mock_{e}_s3").iterdir()) for e in ("py", "netlogo")]
    assert names[0] == names[1]
