"""Orchestrator tests: capacity, end-to-end tiny runs (byte-identical reproduction), estimate, calibrate."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cordonlite import roads as roadsmod
from cordonlite import run as R
from cordonlite.config import load_config
from cordonlite.options import departure_grid
from tests.conftest import write_tiny_road_data

OUTPUTS = ("decisions.csv", "outcomes.csv", "profile.csv", "road_entries.csv", "road_los.csv", "los_summary.csv",
           "personas.csv", "summary.json", "llm_calls.jsonl", "config_snapshot.toml")


@pytest.fixture
def data_dir(tmp_path: Path, tiny_origins: pd.DataFrame, tiny_corridors_prep: pd.DataFrame) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    tiny_origins.to_csv(d / "origins.csv", index=False)
    tiny_corridors_prep.to_csv(d / "corridors.csv", index=False)
    return d


def tiny(data_dir: Path, **ov: object) -> object:
    """Tiny run config; free-flow roads unless road.enabled is overridden (see tiny_roads)."""
    base = {"run.n_agents": 20, "run.n_days": 6, "fees.fee_start_day": 3, "persona.n_twins": 4,
            "events.pt_disruption_day": 5, "run.data_dir": str(data_dir), "run.seed": 3,
            "engine.use_calibration": False, "engine.capacity_scale": 0.5, "road.enabled": False}
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
    # empty corridor floored at engine.min_capacity_vph (950 veh/h) in agents/min: 1 agent = 19000 / 10 cars
    assert cfg.engine.min_capacity_vph == 950.0
    assert cap[2] == round(950.0 / 60 / (19000.0 / 10), 6)
    old = tiny(data_dir, **{"engine.min_capacity_vph": 0.0})   # 0: the floor in agents/min
    assert R.capacity_per_min(tiny_corridors_prep, ag, old, scale=5.0)[2] == old.engine.min_capacity_per_min
    cfg2 = tiny(data_dir, **{"engine.capacity_mode": "raw_scaled"})
    cap2 = R.capacity_per_min(tiny_corridors_prep, ag, cfg2, scale=1.0)
    exp = max(950.0 / 60 / (19000.0 / 10), 5000 / 60 * 10 / cfg2.engine.agents_represented)
    assert cap2[0] == pytest.approx(exp, abs=1e-6)


@pytest.mark.parametrize("n, floor", [(300, 0.25), (950, 0.791667), (1900, 1.583333)])
def test_capacity_floor_in_vehicles(data_dir: Path, tiny_corridors_prep: pd.DataFrame, n: int, floor: float) -> None:
    """The floor is 950 veh/h at any n: 0.25 agents/min at 300 agents (the earlier agents/min floor,
    exactly), 0.791667 at 950."""
    ag = pd.DataFrame({"agent_id": range(n), "corridor_id": [0] * n})
    cap = R.capacity_per_min(tiny_corridors_prep, ag, tiny(data_dir), scale=1.0)
    assert cap[1] == cap[2] == floor
    assert floor * (19000.0 / n) * 60 == pytest.approx(950.0, abs=0.01)


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
    assert set(out["mode"]) <= {"CAR", "PT", "WFH"}                 # no SKIP since 2026-10-09
    summ = json.loads((a / "summary.json").read_text())
    assert [d["day"] for d in summ["days"]] == list(range(1, 7))
    assert all(not d["fee_active"] for d in summ["days"][:2]) and all(d["fee_active"] for d in summ["days"][2:])
    assert all(d["revenue"] == 0 for d in summ["days"][:2])
    called = dec[dec["decider"].isin(["rule", "llm", "llm-fallback-rule"])]
    # forced: one option left, when the willingness to pay removed every car option of a commuter with
    # PT but no WFH (no decider is asked)
    forced = dec[dec["decider"] == "forced"]
    assert (forced["day"] >= 3).all() and forced["wtt_all_removed"].all() and (forced["mode"] == "PT").all()
    if arm.endswith("daily"):
        assert len(called) + len(forced) == 120
    else:
        # day 1 (T1) and the charge day (T2) wake everyone; other days only triggered agents
        assert set(called[called["day"] == 1]["agent_id"]) == set(range(20))
        assert set(pd.concat([called, forced]).query("day == 3")["agent_id"]) == set(range(20))
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


def test_calibrate_seeds_in_parallel_match_sequential(tmp_path: Path, data_dir: Path) -> None:
    """calibrate --seeds runs the seeds in parallel processes and writes the file that running them
    one after another (--jobs 1) writes."""
    args = ["--n-agents", "20", "--target", "3", "--seeds", "3", "4",
            "--set", f"run.data_dir={data_dir}", "--set", "persona.n_twins=4", "--set", "road.enabled=false",
            "--set", "events.pt_disruption_day=5", "--set", "engine.calib_max_iter=2",
            "--set", "engine.calib_days=[2, 3]"]
    assert R.main(["calibrate", *args, "--jobs", "1", "--output", str(tmp_path / "seq.json")]) == 0
    assert R.main(["calibrate", *args, "--jobs", "2", "--output", str(tmp_path / "par.json")]) == 0
    seq = (tmp_path / "seq.json").read_text()
    assert (tmp_path / "par.json").read_text() == seq
    assert set(json.loads(seq)["by_seed"]) == {"3", "4"}


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


def test_netlogo_home_env_var_is_not_recorded(tmp_path: Path, data_dir: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    """CORDONLITE_NETLOGO_HOME only says where NetLogo is on this machine: a run made with it set
    gets the same folder name (variant label), config_snapshot.toml and summary.json as one made
    without it, so a py run and a NetLogo run made this way differ only in the engine label."""
    from cordonlite.engine import NETLOGO_HOME_ENV

    args = ["--arm", "R-clock", "--backend", "mock", "--engine", "py", "--n-agents", "20", "--days", "6",
            "--fee-start", "3", "--seed", "3", "--capacity-scale", "0.5", "--quiet",
            "--set", f"run.data_dir={data_dir}", "--set", "persona.n_twins=4", "--set", "road.enabled=false"]
    monkeypatch.delenv(NETLOGO_HOME_ENV, raising=False)
    assert R.main([*args, "--out", str(tmp_path / "a")]) == 0
    monkeypatch.setenv(NETLOGO_HOME_ENV, str(tmp_path / "Elsewhere" / "NetLogo 7.0.4"))
    assert R.main([*args, "--out", str(tmp_path / "b")]) == 0
    (a,), (b,) = (list((tmp_path / x).iterdir()) for x in "ab")
    assert a.name == b.name
    assert _hashes(a) == _hashes(b)
    assert "Elsewhere" not in (b / "config_snapshot.toml").read_text() + (b / "summary.json").read_text()


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


def test_calib_value_total_delay_reads_queue_plus_road_peaks() -> None:
    days = [{"peak_bin_delay_by_corridor": {"0": 10.0, "1": 30.0},
             "peak_bin_total_delay_by_corridor": {"0": 18.0, "1": 36.0}, "cars_by_corridor": {"0": 30, "1": 10}}]
    assert R.calib_value(days, "worst", "total")[0] == pytest.approx(36.0)
    assert R.calib_value(days, "car_weighted_mean", "total")[0] == pytest.approx((18 * 30 + 36 * 10) / 40)
    assert R.calib_value(days, "worst")[0] == pytest.approx(30.0)   # default: queue only


def test_peak_bin_delay_with_road_adds_road_delay() -> None:
    out = pd.DataFrame({"mode": ["CAR", "CAR", "CAR", "PT"], "corridor_id": [0, 0, 0, 0],
                        "gate_arrive_min": [480, 481, 500, -1], "gate_exit_min": [484, 490, 500, -1],
                        "queue_delay_min": [4, 9, 0, None], "road_delay_min": [2, 3, 7, None]})
    assert R.peak_bin_delay(out, 0, 15) == pytest.approx(6.5)                  # bin 32: (4 + 9) / 2
    assert R.peak_bin_delay(out, 0, 15, with_road=True) == pytest.approx(9.0)  # (6 + 12) / 2 vs 7


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


# --------------------------------------------------------------------------- road congestion


@pytest.fixture
def road_data_dir(data_dir: Path, tiny_origins: pd.DataFrame) -> Path:
    write_tiny_road_data(data_dir, tiny_origins)
    return data_dir


def test_roads_off_outputs(tmp_path: Path, data_dir: Path) -> None:
    """Free-flow roads: header-only road_entries.csv, no road scenario files, road delay 0."""
    d = R.run_simulation(tiny(data_dir, **{"run.arm": "R-daily"}), tmp_path)
    assert (d / "road_entries.csv").read_bytes() == b"day,section_id,minute,entries\n"
    assert not any((d / f).exists() for f in roadsmod.ROAD_SCENARIO_FILES)
    out = pd.read_csv(d / "outcomes.csv")
    assert list(out.columns).index("road_delay_min") == list(out.columns).index("depart_min") + 1
    car = out[out["mode"] == "CAR"]
    assert (car["road_delay_min"] == 0).all() and out.loc[out["mode"] != "CAR", "road_delay_min"].isna().all()
    s = json.loads((d / "summary.json").read_text())
    assert all(x["mean_road_delay"] == 0.0 and x["max_road_delay"] == 0 for x in s["days"])
    assert s["meta"]["road"]["enabled"] is False and s["meta"]["road"]["k"] is None
    assert not list(d.glob("road_day*.csv"))
    # LoS outputs: header only, so the file set is that of a run with roads; day keys None
    assert (d / "road_los.csv").read_text() == ",".join(roadsmod.ROAD_LOS_COLUMNS) + "\n"
    assert (d / "los_summary.csv").read_text() == ",".join(roadsmod.LOS_SUMMARY_COLUMNS) + "\n"
    assert all(all(x[k] is None for k in roadsmod.LOS_DAY_KEYS) for x in s["days"])
    assert {"road_los.csv", "los_summary.csv"} <= set(R.RUN_OUTPUTS)


def test_two_pt_disruption_days(tmp_path: Path, data_dir: Path) -> None:
    """A list of disruption days disrupts the same corridor on each of them: its PT riders are marked
    pt_disrupted on those days only, with the PT time multiplied, and summary.json keeps the list."""
    cfg = tiny(data_dir, **{"run.arm": "R-daily", "events.pt_disruption_day": [2, 5]})
    d = R.run_simulation(cfg, tmp_path)
    out = pd.read_csv(d / "outcomes.csv")
    meta = json.loads((d / "summary.json").read_text())["meta"]
    assert meta["pt_disruption_day"] == [2, 5] and meta["pt_disruption_corridor"] is not None
    hit = out[out["pt_disrupted"]]
    assert set(hit["day"]) == {2, 5} and (hit["mode"] == "PT").all()
    assert set(hit["corridor_id"]) == {meta["pt_disruption_corridor"]}


def test_plans_of_every_day_are_one_file(tmp_path: Path, data_dir: Path) -> None:
    """The plans of all days are one file, plans.csv (day, agent_id, mode, depart_min), written once at the
    end of the run: one row per agent and day, equal to what the engine ran each day (the CAR rows match
    outcomes.csv), and no plans_dayNN.csv is left in the run folder."""
    cfg = tiny(data_dir, **{"run.arm": "R-daily"})
    d = R.run_simulation(cfg, tmp_path)
    plans = pd.read_csv(d / "plans.csv")
    out = pd.read_csv(d / "outcomes.csv")
    assert list(plans.columns) == ["day", "agent_id", "mode", "depart_min"]
    assert len(plans) == len(out) and plans.groupby("day").size().eq(cfg.run.n_agents).all()
    assert sorted(plans["day"].unique()) == list(range(1, cfg.run.n_days + 1))
    merged = plans.merge(out, on=["day", "agent_id"], suffixes=("_plan", "_out"))
    assert len(merged) == len(plans) and (merged["mode_plan"] == merged["mode_out"]).all()
    car = merged[merged["mode_plan"] == "CAR"]
    assert (car["depart_min_plan"] == car["depart_min_out"]).all()
    assert (plans.loc[plans["mode"] != "CAR", "depart_min"] == -1).all()
    assert not list(d.glob("plans_day*.csv")) and "plans.csv" in R.RUN_OUTPUTS


def test_roads_on_end_to_end(tmp_path: Path, road_data_dir: Path) -> None:
    cfg = tiny(road_data_dir, **{"run.arm": "R-daily", "road.enabled": True})
    a = R.run_simulation(cfg, tmp_path / "a")
    b = R.run_simulation(cfg, tmp_path / "b")
    assert _hashes(a) == _hashes(b)
    assert all((a / f).exists() for f in roadsmod.ROAD_SCENARIO_FILES)
    out = pd.read_csv(a / "outcomes.csv")
    car = out[out["mode"] == "CAR"]
    fg = pd.read_csv(a / "agents.csv").set_index("agent_id")["fftt_to_gate_min"]
    assert (car["gate_arrive_min"] == car["depart_min"] + car["agent_id"].map(fg) + car["road_delay_min"]).all()
    assert car["road_delay_min"].max() > 0 and (car["road_delay_min"] >= 0).all()
    assert out.loc[out["mode"] != "CAR", "road_delay_min"].isna().all()
    # every car enters each section of its route once
    ent = pd.read_csv(a / "road_entries.csv")
    road = roadsmod.read_road_scenario(a)
    n_route = car["agent_id"].map(lambda x: len(road.routes.get(int(x), ()))).groupby(car["day"]).sum()
    assert ent.groupby("day")["entries"].sum().to_dict() == n_route.to_dict()
    s = json.loads((a / "summary.json").read_text())
    assert s["meta"]["road"] == roadsmod.road_settings(cfg)   # roads on, with k of data/road_meta.json
    assert s["meta"]["road"]["enabled"] is True and s["meta"]["road"]["k"] == 0.1
    for day in s["days"]:
        c = car[car["day"] == day["day"]]
        served = c[c["gate_exit_min"] >= 0]
        assert day["mean_road_delay"] == round(float(c["road_delay_min"].mean()), 4)
        assert day["max_road_delay"] == int(c["road_delay_min"].max())
        assert day["mean_car_travel_min"] == round(float((served["arrive_min"] - served["depart_min"]).mean()), 4)
    # V/C and Level of Service (SPEC4 B): computed after the run from the scenario and road_entries.csv
    rl, ls = pd.read_csv(a / "road_los.csv"), pd.read_csv(a / "los_summary.csv")
    assert list(rl.columns) == list(roadsmod.ROAD_LOS_COLUMNS) and list(ls.columns) == list(roadsmod.LOS_SUMMARY_COLUMNS)
    assert set(rl["section_id"]) == set(road.section_ids) and set(rl["period"]) == {"d2-5"}   # 6 days: days 2-5 (since 2026-10-15)
    assert len(rl) == len(road.section_ids) * len(roadsmod.LOS_BINS)
    assert len(ls) == 6 * len(roadsmod.LOS_BINS) * len(set(ls["group"]))
    assert {"motorway", "other", "all"} <= set(ls["group"]) and any(g.startswith("corridor") for g in ls["group"])
    info = roadsmod.los_section_info(road, road_data_dir)
    want = roadsmod.los_outputs(road, ent, info, range(1, 7))
    pk = ls[(ls["bin"] == roadsmod.LOS_PEAK_BIN)].set_index(["day", "group"])
    for day in s["days"]:
        assert {k: day[k] for k in roadsmod.LOS_DAY_KEYS} == want.day_keys[day["day"]]
        assert day["los_ef_share_mwy"] is None and day["vc_mean_mwy"] is None   # the tiny data has no motorway
        assert day["los_ef_speed_share_mwy"] is None and day["congested_at_share_mwy"] is None
        assert day["los_ef_share_other"] == round(float(pk.loc[(day["day"], "other"), "share_EF"]), 4)
        assert day["los_ef_speed_share_other"] == round(float(pk.loc[(day["day"], "other"), "share_EF_speed"]), 4)
        assert day["congested_at_share_other"] == round(float(pk.loc[(day["day"], "other"), "share_congested_AT"]), 4)
        assert day["vc_mean_other"] == pytest.approx(pk.loc[(day["day"], "other"), "vc_mean"], abs=1e-4)
    # commuter vehicles: entries x vehicles_per_agent, mean per day of the period (days 2-5)
    e0 = ent[(ent["minute"] >= 420) & (ent["minute"] < 540) & ent["day"].between(2, 5)]
    tot = rl[rl["bin"] == roadsmod.LOS_PEAK_BIN]["commuter_veh"].sum()
    assert tot == pytest.approx(e0["entries"].sum() * road.vehicles_per_agent / 4, rel=1e-6)


def test_public_road_information(tmp_path: Path, road_data_dir: Path) -> None:
    """Day 1 usual traffic; later days yesterday's actual traffic, which reproduces each car's
    road delay of that day."""
    cfg = tiny(road_data_dir, **{"run.arm": "R-daily", "road.enabled": True})
    d = R.run_simulation(cfg, tmp_path)
    road = roadsmod.read_road_scenario(d)
    from cordonlite.persona import build_personas
    personas = build_personas(pd.read_csv(road_data_dir / "origins.csv"),
                              pd.read_csv(road_data_dir / "corridors.csv"), cfg)
    t = cfg.time
    usual = R.public_road(road, personas, cfg)
    assert set(usual) == {p.agent_id for p in personas}
    assert all(len(v) == t.depart_latest_min - t.sim_start_min + 1 for v in usual.values())
    assert max(np.nanmax(v) for v in usual.values()) > 0
    ent = pd.read_csv(d / "road_entries.csv")
    day1 = ent[ent["day"] == 1]
    table = roadsmod.speed_table(road, day1, range(t.sim_start_min, t.sim_end_cap_min + 301))
    exact = roadsmod.route_delays(road, table, road.routes, range(t.sim_start_min, t.depart_latest_min + 1))
    out = pd.read_csv(d / "outcomes.csv")
    car1 = out[(out["mode"] == "CAR") & (out["day"] == 1)]
    for _, r in car1.iterrows():
        x = exact[int(r["agent_id"])][int(r["depart_min"]) - t.sim_start_min]
        assert int(np.floor(x + 0.5)) == r["road_delay_min"]
    pub = R.public_road(road, personas, cfg, day1)
    aid = int(car1.iloc[0]["agent_id"])
    # unrounded, so rounded once like the engine; only the departure grid is computed (NaN elsewhere)
    grid = [m - t.sim_start_min for m in departure_grid(cfg)]
    assert [pub[aid][i] for i in grid] == [float(exact[aid][i]) for i in grid]
    off = [i for i in range(len(pub[aid])) if i not in set(grid)]
    assert off and all(math.isnan(pub[aid][i]) for i in off)
    for _, r in car1.iterrows():
        x = pub[int(r["agent_id"])][int(r["depart_min"]) - t.sim_start_min]
        assert int(np.floor(x + 0.5)) == r["road_delay_min"]


def test_public_road_is_rounded_once(tmp_path: Path, road_data_dir: Path, monkeypatch: pytest.MonkeyPatch,
                                     make_today) -> None:
    """An extra of 5.4996 min is a 5-min road delay in the engine (floor(extra + 0.5)); the published
    delay keeps it unrounded, so the expected gate arrival also adds 5 min (2 dp would give 5.5 -> 6)."""
    from cordonlite.options import build_options
    from cordonlite.persona import build_personas, trait_params
    from cordonlite.memory import new_memory

    cfg = tiny(road_data_dir, **{"road.enabled": True})
    personas = build_personas(pd.read_csv(road_data_dir / "origins.csv"),
                              pd.read_csv(road_data_dir / "corridors.csv"), cfg)
    R.write_scenario(tmp_path, pd.read_csv(road_data_dir / "corridors.csv"), personas, cfg)
    road = roadsmod.read_road_scenario(tmp_path)
    t = cfg.time
    monkeypatch.setattr(roadsmod, "route_delays",
                        lambda road_, table, routes, deps: {a: np.full(len(deps), 5.4996) for a in routes})
    pub = R.public_road(road, personas, cfg)
    p = personas[0]
    assert [pub[p.agent_id][m - t.sim_start_min] for m in departure_grid(cfg)] == [5.4996] * len(departure_grid(cfg))
    today = make_today(1, fee_active=False, public_road=pub)
    opts = build_options(p, new_memory(p.agent_id), today, trait_params(p, cfg), cfg, False)
    cars = [o for o in opts if o.mode == "CAR"]
    assert cars and all(o.expected_gate_arrive_min == o.depart_min + p.fftt_to_gate_min + 5 for o in cars)


def test_roads_on_without_prep_files_fails_clearly(tmp_path: Path, data_dir: Path) -> None:
    with pytest.raises(FileNotFoundError, match="prep.build_roads"):
        R.run_simulation(tiny(data_dir, **{"road.enabled": True}), tmp_path / "runs")


def test_calibration_road_settings(tmp_path: Path, road_data_dir: Path, capsys: pytest.CaptureFixture) -> None:
    """A free-flow calibration (no road record) is flagged for a congested run, and vice versa."""
    on = {"road.enabled": True}
    rec = R.calibrate(tiny(road_data_dir, **on, **{"engine.calib_max_iter": 1, "engine.calib_days": [2, 2],
                                                   "run.n_days": 2}), target=3.0, progress=False)
    assert rec["road"] == {"enabled": True, "bpr_alpha": 0.15, "bpr_beta": 4, "speed_floor": 0.18,
                           "flow_window_min": 15, "k": 0.1, "mwy_breakdown": True, "mwy_breakdown_vc": 1.0,
                           "mwy_recover_vc": 0.95, "mwy_capacity_drop": 0.1, "mwy_jam_speed": 0.45}
    f = tmp_path / "cal.json"
    f.write_text(json.dumps({"capacity_scale": 0.7, "seed": 3, "n_agents": 20}))
    use = {"engine.use_calibration": True, "engine.calibration_file": str(f)}
    scale, src = R.resolve_capacity_scale(tiny(road_data_dir, **use, **on))
    assert scale == 0.7 and "MISMATCH" in src and "road.enabled False" in src
    assert "WARNING" in capsys.readouterr().err
    assert "MISMATCH" not in R.resolve_capacity_scale(tiny(road_data_dir, **use))[1]
    assert rec["calib_delay"] == "total"
    f.write_text(json.dumps({"capacity_scale": 0.7, "seed": 3, "n_agents": 20, "road": rec["road"],
                             "by_seed": {"3": {"capacity_scale": 0.6, "n_agents": 20, "road": rec["road"],
                                               "calib_delay": "total"}}}))
    scale, src = R.resolve_capacity_scale(tiny(road_data_dir, **use, **on))
    assert scale == 0.6 and "MISMATCH" not in src
    scale, src = R.resolve_capacity_scale(tiny(road_data_dir, **use, **on, **{"engine.calib_delay": "queue"}))
    assert scale == 0.6 and "calib_delay total (this run queue)" in src
    scale, src = R.resolve_capacity_scale(tiny(road_data_dir, **use, **on, **{"road.bpr_alpha": 0.2}))
    assert scale == 0.6 and "MISMATCH" in src and "bpr_alpha 0.15" in src
    # the motorway breakdown rule: a record made without it (2026-10-07) or with other thresholds
    scale, src = R.resolve_capacity_scale(tiny(road_data_dir, **use, **on, **{"road.mwy_breakdown": False}))
    assert scale == 0.6 and "road mwy_breakdown True (this run False)" in src
    scale, src = R.resolve_capacity_scale(tiny(road_data_dir, **use, **on, **{"road.mwy_jam_speed": 0.5}))
    assert scale == 0.6 and "road mwy_jam_speed 0.45 (this run 0.5)" in src


def test_calibrate_behaviour_reports_the_calibrated_delay(road_data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """scripts/calibrate_behaviour.py: with calib_delay "total" the capacity is calibrated to queue + road
    delay, so each evaluation records that (and the road settings) and reports the total peak delay and
    the road delay next to the queue-only peak."""
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("calibrate_behaviour_t", root / "scripts" / "calibrate_behaviour.py")
    cb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cb)
    monkeypatch.setattr(cb, "N_AGENTS", 20)
    ov = {"run.n_agents": 20, "run.n_days": 30, "fees.fee_start_day": 11, "persona.n_twins": 4,
          "run.data_dir": str(road_data_dir), "engine.use_calibration": False, "road.enabled": True,
          "engine.calib_max_iter": 1, "engine.calib_days": [2, 2]}
    row = cb.evaluate({"label": "t", "overrides": ov, "seed": 3, "scale": "calibrate"})
    cfg = load_config(overrides={**ov, "run.arm": "R-daily", "run.seed": 3})
    assert cfg.engine.calib_delay == "total"
    assert row["calibration"]["calib_delay"] == "total"
    assert row["calibration"]["road"] == roadsmod.road_settings(cfg)
    res = R.simulate(cfg, road_data_dir.parent / "cb_run", row["capacity_scale"], engine_kind="py")
    m = cb.metrics(res, 20)
    days = res.days
    assert m["peak_total_delay_6_10"] == pytest.approx(np.mean([d["peak_bin_total_delay_wmean"] for d in days[5:10]]))
    assert m["peak_delay_6_10"] == pytest.approx(np.mean([d["peak_bin_delay_wmean"] for d in days[5:10]]))
    assert m["road_delay_6_10"] == pytest.approx(np.mean([d["mean_road_delay"] for d in days[5:10]]))
    assert m["road_delay_6_10"] > 0 and m["peak_total_delay_6_10"] > m["peak_delay_6_10"]
    assert {"peak_total_delay_6_10", "road_delay_21_30"} <= set(cb.summarise([m, m]))
    older = cb.SUMMARY_KEYS[:cb.SUMMARY_KEYS.index("peak_total_delay_6_10")]
    assert "peak_total_delay_6_10" not in cb.summarise([{k: 0.0 for k in older}] * 2)  # older logs
    assert cb.calib_delay_words({"calib_delay": "total"}) == "queue + road delay"
    assert cb.calib_delay_words({}) == "queue delay"


def test_calibrate_behaviour_n_agents_and_seed_tolerance() -> None:
    """scripts/calibrate_behaviour.py takes n from config.toml; the single-seed tolerances are the
    n = 300 values x sqrt(300 / n); a stage re-using a search logged at another n keeps that n
    (select, report) or stops (final, oos, gap: they would add runs)."""
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("calibrate_behaviour_n", root / "scripts" / "calibrate_behaviour.py")
    cb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cb)
    assert cb.N_AGENTS == load_config().run.n_agents == 950
    assert cb.seed_tolerance(300) == cb.SEED_TOL_300 == {"base_car": 0.05, "base_pt": 0.05, "base_wfh": 0.05,
                                                         "change_21_30": 0.04, "change_11_13": 0.04}
    assert cb.SEED_TOL == cb.seed_tolerance(950) == {"base_car": 0.028, "base_pt": 0.028, "base_wfh": 0.028,
                                                     "change_21_30": 0.022, "change_11_13": 0.022}
    assert cb.tolerance_words(cb.SEED_TOL) == "shares ±0.028, response ±2.2 pp"
    with pytest.raises(SystemExit, match="n_agents = 300"):
        cb.use_logged_n({"n_agents": 300}, "final")
    cb.use_logged_n({"n_agents": 300}, "report")
    assert cb.N_AGENTS == 300 and cb.SEED_TOL == cb.SEED_TOL_300


def test_calibrate_behaviour_three_scalar_search_helpers() -> None:
    """scripts/calibrate_behaviour.py (2026-10-09): SKIP is gone from the targets; beta0 is the third searched
    scalar with anchor 0.5; beta0 = 0 points are references the rule never picks; stage 2 widens the PAP set
    at the edge of stage 1; stage 3 adds the midpoints around the stage-2 choice."""
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("calibrate_behaviour_s", root / "scripts" / "calibrate_behaviour.py")
    cb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cb)
    assert "base_skip" not in cb.TARGETS and "base_skip" not in cb.SUMMARY_KEYS
    assert cb.ANCHORS["beta0"] == cb.V3_SCALARS["beta0"] == 0.5
    assert cb.point_overrides(22.0, 17.0, 9.0, 0.2)["wtt.beta0"] == 0.2
    assert cb.BEFORE["wtt.beta0"] == 0.0 and "costs.skip_cost" not in cb.BEFORE
    assert cb.anchor_distance({"pap": 8.0, "park": 17.0, "wfh": 8.0, "beta0": 0.25}) == pytest.approx(0.25)
    assert cb.anchor_distance({"pap": 8.0, "park": 17.0, "wfh": 8.0}) == 0.0          # archived point, no beta0
    good = {k: (t["centre"] if t["centre"] is not None else (t["lo"] + t["hi"]) / 2) for k, t in cb.TARGETS.items()}

    def point(pap, wfh, b0, **mean):
        sc = {"pap": pap, "park": 17.0, "wfh": wfh, "beta0": b0}
        rows = [{"seed": s, **good, **mean} for s in cb.SEEDS]
        return {"label": cb.point_label(sc), "scalars": sc, "reference": b0 == 0.0, "per_seed": rows,
                "mean": cb.summarise(rows), "feasible": cb.feasible(rows), "loss": cb.loss(rows, sc),
                "anchor_distance": cb.anchor_distance(sc)}

    pts = [point(22.0, 9.0, 0.0), point(22.0, 9.0, 0.1), point(22.0, 12.0, 0.3),
           point(21.0, 9.0, 0.2, base_pt=0.17), point(23.0, 9.0, 0.2, base_car=0.88)]
    assert all(p["feasible"] for p in pts[:3]) and not any(p["feasible"] for p in pts[3:])
    assert cb.select(pts)["label"] == "pap22_park17_wfh12_b0.3"     # nearest the anchors; the reference never
    assert cb.select([pts[0], pts[3]])["label"] == pts[3]["label"]   # no feasible candidate: lowest loss
    assert all(sc["beta0"] > 0 for sc in cb.ridge_alternatives(pts, "pap22_park17_wfh12_b0.3"))
    assert cb.stage2_paps(pts) == [22.0]
    assert cb.stage2_paps([point(21.0, 9.0, 0.1), point(22.0, 9.0, 0.1)]) == [20.0, 21.0, 22.0]
    assert cb.stage3_betas(0.2) == [0.15, 0.25]
    assert cb.stage3_betas(0.05) == [0.025, 0.075]
    assert cb.on_grid_edge({"pap": 22.0, "wfh": 9.0, "beta0": 0.05}) == {"pap": False, "wfh": False, "beta0": True}
    assert cb.on_grid_edge({"pap": 22.0, "wfh": 9.0, "beta0": 0.05}, [0.025, 0.05, 1.0])["beta0"] is False
