"""Orchestrator tests: capacity, end-to-end tiny runs (byte-identical reproduction), estimate, calibrate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from cordonlite import run as R
from cordonlite.config import load_config

OUTPUTS = ("decisions.csv", "outcomes.csv", "profile.csv", "personas.csv", "summary.json",
           "llm_calls.jsonl", "config_snapshot.toml")


@pytest.fixture
def data_dir(tmp_path: Path, tiny_origins: pd.DataFrame, tiny_corridors_prep: pd.DataFrame) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    tiny_origins.to_csv(d / "origins.csv", index=False)
    tiny_corridors_prep.to_csv(d / "corridors.csv", index=False)
    return d


def tiny(data_dir: Path, **ov: object) -> object:
    base = {"run.n_agents": 20, "run.n_days": 6, "fees.fee_start_day": 3, "persona.n_twins": 4,
            "events.pt_disruption_day": 5, "run.data_dir": str(data_dir), "run.seed": 3,
            "engine.use_calibration": False, "engine.capacity_scale": 0.5}
    base.update(ov)
    return load_config(overrides=base)


def _hashes(d: Path) -> dict[str, str]:
    return {f: hashlib.sha256((d / f).read_bytes()).hexdigest() for f in OUTPUTS}


def test_run_dir_name() -> None:
    assert R.run_dir_name("R-clock", "mock", "py", 1) == "R-clock_mock_py_s1"
    assert R.run_dir_name("L-clock", "mock", "py", 1, "off") == "L-clock_mock_py_s1_traitsoff"


def test_capacity_modes(data_dir: Path, tiny_corridors_prep: pd.DataFrame) -> None:
    ag = pd.DataFrame({"agent_id": range(10), "corridor_id": [0] * 6 + [1] * 4})
    cfg = tiny(data_dir)
    cap = R.capacity_per_min(tiny_corridors_prep, ag, cfg, scale=5.0)
    assert cap[0] == pytest.approx(6 / 60 * 5.0) and cap[1] == pytest.approx(4 / 60 * 5.0)
    assert cap[2] == cfg.engine.min_capacity_per_min  # empty corridor floored
    cfg2 = tiny(data_dir, **{"engine.capacity_mode": "raw_scaled"})
    cap2 = R.capacity_per_min(tiny_corridors_prep, ag, cfg2, scale=1.0)
    exp = max(0.25, 5000 / 60 * 10 / cfg2.engine.agents_represented)
    assert cap2[0] == pytest.approx(exp, abs=1e-6)


def test_resolve_capacity_scale(tmp_path: Path, data_dir: Path) -> None:
    cfg = tiny(data_dir)
    assert R.resolve_capacity_scale(cfg) == (0.5, "config")
    assert R.resolve_capacity_scale(cfg, 2.0) == (2.0, "cli")
    f = tmp_path / "cal.json"
    f.write_text(json.dumps({"capacity_scale": 0.7}))
    cfg2 = tiny(data_dir, **{"engine.use_calibration": True, "engine.calibration_file": str(f)})
    assert R.resolve_capacity_scale(cfg2)[0] == 0.7


@pytest.mark.parametrize("arm", ["R-clock", "L-clock", "R-daily", "L-daily"])
def test_end_to_end_byte_identical(tmp_path: Path, data_dir: Path, arm: str) -> None:
    cfg = tiny(data_dir, **{"run.arm": arm})
    a = R.run_simulation(cfg, tmp_path / "a")
    b = R.run_simulation(cfg, tmp_path / "b")
    assert _hashes(a) == _hashes(b)
    dec = pd.read_csv(a / "decisions.csv")
    out = pd.read_csv(a / "outcomes.csv")
    assert len(dec) == len(out) == 20 * 6
    assert set(out["mode"]) <= {"CAR", "PT", "WFH", "SKIP"}
    summ = json.loads((a / "summary.json").read_text())
    assert [d["day"] for d in summ["days"]] == list(range(1, 7))
    assert all(not d["fee_active"] for d in summ["days"][:2]) and all(d["fee_active"] for d in summ["days"][2:])
    assert all(d["revenue"] == 0 for d in summ["days"][:2])
    called = dec[dec["decider"].isin(["rule", "llm", "llm-fallback-rule"])]
    if arm.endswith("daily"):
        assert len(called) == 120
    else:
        # day 1 (T1) and the charge day (T2) wake everyone; other days only triggered agents
        assert set(called[called["day"] == 1]["agent_id"]) == set(range(20))
        assert set(called[called["day"] == 3]["agent_id"]) == set(range(20))
        assert (called["triggers"].fillna("") != "").all()
        assert len(called) < 120
    assert (dec[dec["day"] == 1]["decider"] != "standing").all()
    lines = (a / "llm_calls.jsonl").read_text().splitlines()
    n_llm = int(dec["decider"].isin(["llm", "llm-fallback-rule"]).sum())
    assert len(lines) >= n_llm and (n_llm > 0) == arm.startswith("L-")
    # car fees are paid at the gate-exit minute
    car = out[(out["mode"] == "CAR") & (out["gate_exit_min"] >= 0)]
    assert (car[car["day"] < 3]["fee_paid"] == 0).all()


def test_standing_executes_previous_choice(tmp_path: Path, data_dir: Path) -> None:
    cfg = tiny(data_dir, **{"run.arm": "R-clock"})
    d = R.run_simulation(cfg, tmp_path)
    dec = pd.read_csv(d / "decisions.csv").sort_values(["agent_id", "day"])
    for _aid, g in dec.groupby("agent_id"):
        g = g.reset_index(drop=True)
        for i in range(1, len(g)):
            if g.loc[i, "decider"] == "standing":
                assert g.loc[i, "option_id"] == g.loc[i - 1, "option_id"]
                assert g.loc[i - 1, "option_id"] != "SKIP"  # a SKIP never stands


def test_estimate_matches_llm_run(tmp_path: Path, data_dir: Path) -> None:
    cfg = tiny(data_dir, **{"run.arm": "L-clock"})
    est = R.estimate(cfg)
    d = R.run_simulation(cfg, tmp_path)
    n = len((d / "llm_calls.jsonl").read_text().splitlines())
    assert est["n_llm_calls"] == n
    assert est["approx_input_tokens"] > 0 and "APPROXIMATE" in est["note"]
    with pytest.raises(ValueError):
        R.estimate(tiny(data_dir, **{"run.arm": "R-clock"}))


def test_calibrate_small(data_dir: Path) -> None:
    cfg = tiny(data_dir, **{"engine.calib_max_iter": 4, "engine.calib_days": [2, 3]})
    rec = R.calibrate(cfg, target=3.0, progress=False)
    lo, hi = cfg.engine.calib_scale_bounds
    assert lo <= rec["capacity_scale"] <= hi
    assert rec["history"] and rec["target_peak_delay_min"] == 3.0


def test_analysis_outputs(tmp_path: Path, data_dir: Path) -> None:
    from cordonlite import analysis as A

    runs = tmp_path / "runs"
    for arm in ("R-clock", "L-clock"):
        R.run_simulation(tiny(data_dir, **{"run.arm": arm}), runs)
    R.run_simulation(tiny(data_dir, **{"run.arm": "R-clock"}), runs, name="R-clock_copy")
    cmp = A.compare_runs(runs / "R-clock_mock_py_s3", runs / "R-clock_copy")
    assert cmp["identical"]
    found = A.discover_runs(runs)
    loaded = {k: A.load_run(v) for k, v in found.items()}
    first = next(iter(loaded.values()))
    who = A.table_who_adapts(first, base=(1, 2), end=(5, 6))
    assert set(who["group"]) == {"archetype", "vot_quintile", "H", "F", "P", "S"}
    assert who["n"][who["group"] == "H"].sum() == 20 - 4          # twins excluded
    assert ((who["ci_low"] <= who["left_car_share"]) | who["left_car_share"].isna()).all()
    tw = A.table_twins(first, day=3)
    assert len(tw) == 2 * 4
    ts = A.twin_summary(first, days=(1, 3, 6))
    assert ts["n_pairs"] == 4 and set(ts) >= {"differ_d1", "differ_d3", "differ_d6"}
    lc = next(v for k, v in loaded.items() if k.startswith("L-clock"))
    dg = A.llm_diagnostics(lc, first)
    assert dg["agent_days"] > 0 and dg["cache_hit_rate"] == 0.0 and "entropy_ratio_llm_over_rule" in dg
    assert A.llm_diagnostics(first) == {}
    out = tmp_path / "fig"
    for f in (A.fig_mode_shares, A.fig_queue_delay, A.fig_calls_per_day, A.fig_who_adapts):
        assert f(loaded, out).exists()
    # a variant run is left out unless asked for
    R.run_simulation(tiny(data_dir, **{"run.arm": "R-daily", "fees.regime": "flat"}), runs, variant="_flat")
    assert not any(k.startswith("R-daily") for k in A.discover_runs(runs))
    assert any("{flat}" in k for k in A.discover_runs(runs, include_all=True))


def test_variant_suffix_and_no_overwrite_on_failure(tmp_path: Path, data_dir: Path,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-default settings get their own folder; a failing run leaves a finished run intact."""
    base = tiny(data_dir)
    assert R.variant_suffix(base, base) == ""
    v = tiny(data_dir, **{"fees.regime": "flat", "fees.fee_start_day": 4, "run.n_days": 5})
    sfx = R.variant_suffix(v, base, 1.0, {"costs.pt_attitude_penalty": 8})
    assert sfx.startswith("_d5_flat_fs4_cs1_set-") and len(sfx.split("_set-")[1]) == 8
    good = R.run_simulation(base, tmp_path / "runs")
    h = _hashes(good)

    def boom(*a: object, **k: object) -> None:
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(R, "write_outputs", boom)
    with pytest.raises(RuntimeError):
        R.run_simulation(base, tmp_path / "runs")
    assert _hashes(good) == h
    assert (tmp_path / "runs" / (good.name + ".failed")).is_dir()
    assert not list((tmp_path / "runs").glob(".tmp_*"))


def test_calibration_mismatch_is_reported(tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture) -> None:
    f = tmp_path / "cal.json"
    f.write_text(json.dumps({"capacity_scale": 0.7, "seed": 1, "n_agents": 300, "traits": "on"}))
    cfg = tiny(data_dir, **{"engine.use_calibration": True, "engine.calibration_file": str(f)})
    scale, src = R.resolve_capacity_scale(cfg)
    assert scale == 0.7 and "MISMATCH" in src and "seed 1 (this run 3)" in src
    assert "WARNING" in capsys.readouterr().err


def test_calib_value_metrics() -> None:
    days = [{"peak_bin_delay_by_corridor": {"0": 10.0, "1": 30.0}, "cars_by_corridor": {"0": 30, "1": 10}},
            {"peak_bin_delay_by_corridor": {"0": 20.0, "1": 40.0}, "cars_by_corridor": {"0": 30, "1": 10}}]
    assert R.calib_value(days, "worst")[0] == pytest.approx(35.0)
    assert R.calib_value(days, "busiest")[:2] == (pytest.approx(15.0), 0)
    assert R.calib_value(days, "car_weighted_mean")[0] == pytest.approx((15.0 + 25.0) / 2)


def test_cli_set_is_type_checked_and_flags_win(capsys: pytest.CaptureFixture) -> None:
    import argparse

    from cordonlite.config import ConfigError
    with pytest.raises(ConfigError):
        load_config(overrides={"costs.pt_attitude_penalty": "abc"})
    with pytest.raises(ConfigError):
        load_config(overrides={"run.n_days": 2.5})
    ns = argparse.Namespace(set=["run.n_days=5"], days=12, seed=None, n_agents=None, traits=None,
                            arm=None, backend=None, engine=None, fee_start=None, regime=None, config=None)
    assert R._overrides(ns)["run.n_days"] == 12
    assert "overrides --set run.n_days=5" in capsys.readouterr().err


def test_missing_credentials_fail_before_day1(tmp_path: Path, data_dir: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    import anthropic
    monkeypatch.setattr(anthropic, "AsyncAnthropic",
                        lambda *a, **k: types.SimpleNamespace(api_key=None, auth_token=None, credentials=None))
    cfg = tiny(data_dir, **{"run.arm": "L-clock", "run.backend": "anthropic"})
    with pytest.raises(RuntimeError, match="No Anthropic credentials"):
        R.run_simulation(cfg, tmp_path / "runs")
    assert not (tmp_path / "runs").exists() or not any((tmp_path / "runs").iterdir())


def test_calibration_by_seed(tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture) -> None:
    """A per-seed record (calibrate --seeds) is used for its own seed without a mismatch warning."""
    f = tmp_path / "cal.json"
    f.write_text(json.dumps({"capacity_scale": 0.7, "seed": 1, "n_agents": 300,
                             "by_seed": {"1": {"capacity_scale": 0.7, "n_agents": 300},
                                         "3": {"capacity_scale": 0.55, "n_agents": 300},
                                         "4": {"capacity_scale": 0.9, "n_agents": 999}}}))
    base = {"engine.use_calibration": True, "engine.calibration_file": str(f), "run.n_agents": 300}
    scale, src = R.resolve_capacity_scale(tiny(data_dir, **base, **{"run.seed": 3}))
    assert scale == 0.55 and "seed 3" in src and "MISMATCH" not in src
    assert "WARNING" not in capsys.readouterr().err
    scale, src = R.resolve_capacity_scale(tiny(data_dir, **base, **{"run.seed": 4}))   # n_agents differs
    assert scale == 0.7 and "MISMATCH" in src


def test_early_shift_counted_and_deterministic(tmp_path: Path, data_dir: Path) -> None:
    """Early-start days appear in decisions, outcomes and summary.json; reruns are byte-identical;
    with no permission in the population there are none and nobody else is affected."""
    ov = {"run.arm": "R-daily", "run.n_agents": 40, "run.n_days": 8,
          "persona.early_shift_prob": [1.0, 1.0, 0.0, 1.0, 0.0], "costs.early_shift_cost": 0.0}
    cfg = tiny(data_dir, **ov)
    a = R.run_simulation(cfg, tmp_path / "a")
    b = R.run_simulation(cfg, tmp_path / "b")
    assert _hashes(a) == _hashes(b)
    out = pd.read_csv(a / "outcomes.csv")
    dec = pd.read_csv(a / "decisions.csv")
    per = pd.read_csv(a / "personas.csv")
    s = json.loads((a / "summary.json").read_text())
    assert {"start_used_min", "early_shift"} <= set(out.columns) and {"start_used_min", "early_shift"} <= set(dec.columns)
    n_early = int(out["early_shift"].sum())
    assert n_early > 0                                              # free early day: some commuters use it
    assert s["meta"]["early_shift_days_total"] == n_early == int(dec["early_shift"].sum())
    assert [d["early_shift"] for d in s["days"]] == out.groupby("day")["early_shift"].sum().astype(int).tolist()
    assert s["meta"]["early_shift_ok_agents"] == int(per["early_shift_ok"].sum())
    ok = set(per.loc[per["early_shift_ok"], "agent_id"])
    e = out[out["early_shift"]]
    assert set(e["agent_id"]) <= ok and (e["start_used_min"] == 420).all() and e["mode"].isin(["CAR", "PT"]).all()
    tstar = per.set_index("agent_id")["tstar_min"]
    trips = out[out["mode"].isin(["CAR", "PT"]) & ~out["early_shift"]]
    assert (trips["start_used_min"] == trips["agent_id"].map(tstar)).all()
    served = e[(e["mode"] == "CAR") & (e["gate_exit_min"] >= 0)]
    assert (served["late_min"] == (served["arrive_min"] - 420).clip(lower=0)).all()
    # no permission anywhere: no early-start days
    c = R.run_simulation(tiny(data_dir, **{**ov, "persona.early_shift_prob": [0.0] * 5}), tmp_path / "c")
    s0 = json.loads((c / "summary.json").read_text())
    assert s0["meta"]["early_shift_days_total"] == 0 and s0["meta"]["early_shift_ok_agents"] == 0
