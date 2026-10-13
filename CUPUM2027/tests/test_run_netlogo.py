"""End-to-end run with NetLogoEngine == PyEngine (subprocess: the JVM starts once per process).

CORDONLITE_NETLOGO_HOME, when set, overrides [engine] netlogo_home: the subprocesses inherit it and
engine.get_netlogo_link reads it, so it is not a --set override and both runs keep the same folder
name and config snapshot.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests.conftest import write_tiny_road_data

ROOT = Path(__file__).resolve().parents[1]


def _run_both(tmp_path: Path, data: Path, extra: list[str]) -> tuple[Path, Path]:
    common = ["--arm", "R-clock", "--backend", "mock", "--n-agents", "20", "--days", "6",
              "--fee-start", "3", "--seed", "3", "--capacity-scale", "0.4", "--quiet",
              "--out", str(tmp_path / "runs"), "--set", f"run.data_dir={data}",
              "--set", "persona.n_twins=4", "--set", "events.pt_disruption_day=5", *extra]
    for eng in ("py", "netlogo"):
        p = subprocess.run([sys.executable, "-m", "cordonlite.run", *common, "--engine", eng,
                            "--name", f"R-clock_mock_{eng}_s3"],
                           cwd=ROOT, capture_output=True, text=True, timeout=300)
        assert p.returncode == 0, p.stderr[-3000:]
    return tmp_path / "runs" / "R-clock_mock_py_s3", tmp_path / "runs" / "R-clock_mock_netlogo_s3"


def _data(tmp_path: Path, origins: pd.DataFrame, corridors_prep: pd.DataFrame) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    origins.to_csv(data / "origins.csv", index=False)
    corridors_prep.to_csv(data / "corridors.csv", index=False)
    return data


@pytest.mark.netlogo
def test_run_netlogo_equals_py(tmp_path: Path, tiny_origins: pd.DataFrame,
                               tiny_corridors_prep: pd.DataFrame) -> None:
    """Free-flow roads (road.enabled = false)."""
    from cordonlite.analysis import compare_runs

    data = _data(tmp_path, tiny_origins, tiny_corridors_prep)
    py, nl = _run_both(tmp_path, data, ["--set", "road.enabled=false"])
    res = compare_runs(py, nl)
    assert res["identical"], res
    # same file set in both folders (NetLogo's per-day exchange files are removed after the run)
    names = [sorted(f.name for f in d.iterdir()) for d in (py, nl)]
    assert names[0] == names[1]
    assert (py / "road_entries.csv").read_bytes() == b"day,section_id,minute,entries\n"


@pytest.mark.netlogo
def test_run_netlogo_equals_py_with_roads(tmp_path: Path, tiny_origins: pd.DataFrame,
                                          tiny_corridors_prep: pd.DataFrame) -> None:
    """Congested roads (road.enabled = true, the tiny prep road files of conftest)."""
    from cordonlite.analysis import compare_runs

    data = _data(tmp_path, tiny_origins, tiny_corridors_prep)
    write_tiny_road_data(data, tiny_origins)
    py, nl = _run_both(tmp_path, data, ["--set", "road.enabled=true"])
    res = compare_runs(py, nl)
    assert res["identical"], res
    names = [sorted(f.name for f in d.iterdir()) for d in (py, nl)]
    assert names[0] == names[1] and "road_sections.csv" in names[0]
    assert not [n for n in names[1] if n.startswith(("road_day", "outcomes_day", "profile_day"))]
    out = pd.read_csv(nl / "outcomes.csv")
    assert out.loc[out["mode"] == "CAR", "road_delay_min"].max() > 0
    assert len(pd.read_csv(nl / "road_entries.csv")) > 0


@pytest.mark.netlogo
def test_run_netlogo_equals_py_with_motorway_breakdown(tmp_path: Path, tiny_origins: pd.DataFrame,
                                                       tiny_corridors_prep: pd.DataFrame) -> None:
    """Motorway flow breakdown: the corridors' shared sections of the tiny road data are motorways
    (frc 0, mwy 1). With the thresholds 0.8 / 0.7 they have a usual-traffic window (07:50 to 08:32,
    V/C 0.85 at the 08:00 peak) and today's commuters break them down outside it."""
    from cordonlite.analysis import compare_runs

    data = _data(tmp_path, tiny_origins, tiny_corridors_prep)
    write_tiny_road_data(data, tiny_origins)
    sec = pd.read_csv(data / "road_sections.csv")
    shared = sec["section_id"] >= 1000
    sec["frc"] = np.where(shared, 0, 2)
    sec["mwy"], sec["bd_on"], sec["bd_off"] = shared.astype(int), -1, -1
    sec.to_csv(data / "road_sections.csv", index=False)
    py, nl = _run_both(tmp_path, data, ["--set", "road.enabled=true", "--set", "road.mwy_breakdown=true",
                                        "--set", "road.mwy_breakdown_vc=0.8", "--set", "road.mwy_recover_vc=0.7"])
    res = compare_runs(py, nl)
    assert res["identical"], res
    rs = pd.read_csv(nl / "road_sections.csv")
    assert set(rs.loc[rs["mwy"] == 1, "bd_on"]) == {470} and set(rs.loc[rs["mwy"] == 1, "bd_off"]) == {512}
    params = pd.read_csv(nl / "road_params.csv", dtype=str).set_index("key")["value"]
    assert params["mwy_breakdown"] == "1" and params["mwy_breakdown_vc"] == "0.8"
    out = pd.read_csv(nl / "outcomes.csv")
    assert out.loc[out["mode"] == "CAR", "road_delay_min"].max() > 0


@pytest.mark.netlogo
def test_run_netlogo_equals_py_with_nzta_profiles(tmp_path: Path, tiny_origins: pd.DataFrame,
                                                  tiny_corridors_prep: pd.DataFrame) -> None:
    """NZTA motorway counts (SPEC3): the corridors' shared sections are motorways; the first of each
    pair comes from a 'site' with its own time profile (an early maximum, then a plateau), window
    06:30-09:30 and capacity drop; road_profile.csv is in the long format. Both engines read the
    per-section profiles and divisors and give the same run."""
    from cordonlite.analysis import compare_runs

    data = _data(tmp_path, tiny_origins, tiny_corridors_prep)
    write_tiny_road_data(data, tiny_origins)
    sec = pd.read_csv(data / "road_sections.csv")
    shared = sec["section_id"] >= 1000
    site = shared & (sec["section_id"] % 2 == 0)
    sec["frc"] = np.where(shared, 0, 2)
    sec["mwy"] = shared.astype(int)
    sec["adt_source"] = np.where(site, "nzta", "count")
    sec["bd_on"], sec["bd_off"] = np.where(site, 390, -1), np.where(site, 570, -1)
    sec["profile_id"] = np.where(site, 1 + (sec["section_id"] // 2) % 2, 0)
    sec["cap_drop"] = np.where(site, np.where(sec["section_id"] % 4 == 0, 0.263187, 0.18), 0.1)
    sec.to_csv(data / "road_sections.csv", index=False)
    prof = pd.read_csv(data / "road_profile.csv")
    m = np.arange(1440)
    p1 = np.interp(m, [0, 300, 360, 382, 420, 570, 660, 1439], [0.2, 0.2, 0.95, 1.08, 0.8, 0.86, 0.7, 0.45]).round(6)
    p2 = np.interp(m, [0, 300, 420, 487, 520, 600, 1439], [0.12, 0.12, 0.6, 1.1, 0.95, 0.7, 0.4]).round(6)
    pd.concat([prof.assign(profile_id=0), pd.DataFrame({"minute": m, "r": p1, "profile_id": 1}),
               pd.DataFrame({"minute": m, "r": p2, "profile_id": 2})])[["profile_id", "minute", "r"]].to_csv(
        data / "road_profile.csv", index=False)
    py, nl = _run_both(tmp_path, data, ["--set", "road.enabled=true", "--set", "road.mwy_breakdown=true"])
    res = compare_runs(py, nl)
    assert res["identical"], res
    rs = pd.read_csv(nl / "road_sections.csv")
    assert list(rs.columns)[-2:] == ["profile_id", "cap_drop"] and set(rs["profile_id"]) == {0, 1, 2}
    site = rs["profile_id"] > 0
    assert set(rs.loc[site, "bd_on"]) == {390} and set(rs.loc[site, "cap_drop"]) == {0.263187, 0.18}
    assert set(pd.read_csv(nl / "road_profile.csv")["profile_id"]) == {0, 1, 2}
    out = pd.read_csv(nl / "outcomes.csv")
    assert out.loc[out["mode"] == "CAR", "road_delay_min"].max() > 0


@pytest.mark.netlogo
def test_run_netlogo_equals_py_with_peak_fee(tmp_path: Path, tiny_origins: pd.DataFrame,
                                             tiny_corridors_prep: pd.DataFrame) -> None:
    """Peak charge NZ$30 (--peak-fee 30; free-flow roads): the run folder's fees.csv holds the schedule
    scaled to that peak and NetLogoEngine charges from it as PyEngine does."""
    from cordonlite import fees
    from cordonlite.analysis import compare_runs

    data = _data(tmp_path, tiny_origins, tiny_corridors_prep)
    py, nl = _run_both(tmp_path, data, ["--set", "road.enabled=false", "--peak-fee", "30"])
    res = compare_runs(py, nl)
    assert res["identical"], res
    assert fees.read_fees_csv(nl / "fees.csv") == fees.fee_table("tou", peak_fee=30.0)
    out = pd.read_csv(nl / "outcomes.csv")
    paid = out.loc[(out["mode"] == "CAR") & (out["day"] >= 3) & (out["gate_exit_min"] >= 0), "fee_paid"]
    assert len(paid) and paid.min() >= 10.0                      # the lowest charge is NZ$2 x 30 / 6


@pytest.mark.netlogo
def test_run_netlogo_equals_py_with_peak_fee_zero(tmp_path: Path, tiny_origins: pd.DataFrame,
                                                  tiny_corridors_prep: pd.DataFrame) -> None:
    """Peak charge 0 (--peak-fee 0): no charge day (scenario.csv charge_from_day 0, fees.csv all zero), and
    NetLogoEngine gives the same run as PyEngine."""
    from cordonlite.analysis import compare_runs

    data = _data(tmp_path, tiny_origins, tiny_corridors_prep)
    py, nl = _run_both(tmp_path, data, ["--set", "road.enabled=false", "--peak-fee", "0"])
    res = compare_runs(py, nl)
    assert res["identical"], res
    assert pd.read_csv(nl / "scenario.csv").set_index("key").loc["charge_from_day", "value"] == 0
    assert (pd.read_csv(nl / "outcomes.csv")["fee_paid"].fillna(0) == 0).all()
