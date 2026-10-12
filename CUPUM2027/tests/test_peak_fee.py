"""Peak charge fees.peak_fee (NZ$, 2026-10-09; replaced the charge multiplier fees.scale): run folder suffix
_peak<NZ$>, summary meta, the scaled fees.csv and prompt, peak 0 = regime "none", and the fee-response outputs of
the analysis (one row per arm and peak over the charged days, against the no-charge run of the same days; the
willingness to travel; LoS by speed and by V/C next to the mean V/C)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cordonlite import analysis as A
from cordonlite import fees
from cordonlite import run as R
from cordonlite.config import load_config
from tests.conftest import write_tiny_road_data

COMPARED = ("decisions.csv", "outcomes.csv", "profile.csv", "personas.csv", "fees.csv", "scenario.csv",
            "llm_calls.jsonl", "road_entries.csv", "los_summary.csv", "road_los.csv")


@pytest.fixture
def data_dir(tmp_path: Path, tiny_origins: pd.DataFrame, tiny_corridors_prep: pd.DataFrame) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    tiny_origins.to_csv(d / "origins.csv", index=False)
    tiny_corridors_prep.to_csv(d / "corridors.csv", index=False)
    return d


def tiny(data_dir: Path, **ov: object) -> object:
    """Tiny run config (as tests/test_run.py): 20 agents, 6 days, charge from day 3, free-flow roads."""
    base = {"run.n_agents": 20, "run.n_days": 6, "fees.fee_start_day": 3, "persona.n_twins": 4,
            "events.pt_disruption_day": 5, "run.data_dir": str(data_dir), "run.seed": 3,
            "engine.use_calibration": False, "engine.capacity_scale": 0.5, "road.enabled": False}
    base.update(ov)
    return load_config(overrides=base)


def test_variant_suffix_and_folder_name(tmp_path: Path, data_dir: Path) -> None:
    base = tiny(data_dir)
    assert base.fees.peak_fee == 6.0 and R.variant_suffix(base, base) == ""
    twelve = tiny(data_dir, **{"fees.peak_fee": 12.0})
    assert R.variant_suffix(twelve, base) == "_peak12"
    assert R.variant_suffix(tiny(data_dir, **{"fees.peak_fee": 0}), base) == "_peak0"
    assert R.variant_suffix(tiny(data_dir, **{"fees.peak_fee": 2.5}), base) == "_peak2.5"
    assert R.variant_suffix(tiny(data_dir, **{"fees.peak_fee": 30.0, "fees.regime": "flat"}), base) == "_flat_peak30"
    d = R.run_simulation(twelve, tmp_path / "runs", variant=R.variant_suffix(twelve, base))
    assert d.name == "R-clock_mock_py_s3_peak12"


def test_cli_peak_fee_flag(tmp_path: Path, data_dir: Path, capsys: pytest.CaptureFixture) -> None:
    ns = argparse.Namespace(set=["fees.peak_fee=18"], peak_fee=12.0, days=None, seed=None, n_agents=None,
                            traits=None, arm=None, backend=None, engine=None, fee_start=None, regime=None)
    assert R._overrides(ns)["fees.peak_fee"] == 12.0
    assert "--peak-fee 12.0 overrides --set fees.peak_fee=18" in capsys.readouterr().err
    args = ["--arm", "R-daily", "--n-agents", "20", "--days", "4", "--fee-start", "3", "--seed", "3",
            "--capacity-scale", "0.5", "--peak-fee", "12", "--quiet", "--out", str(tmp_path / "runs"),
            "--set", f"run.data_dir={data_dir}", "--set", "persona.n_twins=4", "--set", "road.enabled=false"]
    assert R.main(args) == 0
    (d,) = list((tmp_path / "runs").iterdir())
    assert d.name.startswith("R-daily_mock_py_s3_n20_d4_fs3_peak12_cs0.5_set-")
    meta = json.loads((d / "summary.json").read_text())["meta"]
    assert meta["fee_peak"] == 12.0 and "fee_scale" not in meta and "_peak12" in meta["variant"]
    with pytest.raises(SystemExit, match="fees.peak_fee"):
        R.main([*args[:-6], "--peak-fee", "-1"])
    with pytest.raises(SystemExit):                       # the retired multiplier: no flag, no key
        R.main([*args[:12], "--fee-scale", "2"])
    with pytest.raises(SystemExit, match="fees.scale"):
        R.main([*args[:12], "--set", "fees.scale=2"])


def test_cli_estimate_file_names_the_variant(tmp_path: Path, data_dir: Path) -> None:
    """--estimate writes estimates/<arm>_n<N>_d<D>_s<seed><variant>.json, so an estimate at another
    charge does not overwrite the canonical one; n and d are not repeated in the suffix."""
    args = ["--arm", "L-clock", "--n-agents", "20", "--days", "4", "--fee-start", "3", "--seed", "3",
            "--capacity-scale", "0.5", "--peak-fee", "12", "--estimate", "--out", str(tmp_path / "runs"),
            "--set", f"run.data_dir={data_dir}", "--set", "persona.n_twins=4", "--set", "road.enabled=false"]
    assert R.main(args) == 0
    (f,) = list((tmp_path / "runs" / "estimates").iterdir())
    assert f.name.startswith("L-clock_n20_d4_s3_fs3_peak12_cs0.5_set-") and f.suffix == ".json"


def test_peak_fee_run_outputs(tmp_path: Path, data_dir: Path) -> None:
    """fees.csv, the engine's fee_paid, summary meta and the LLM prompt all use the schedule scaled to the
    peak; the days before the charge are the same as at the canonical peak (NZ$6)."""
    runs = {}
    for peak in (6.0, 12.0):
        cfg = tiny(data_dir, **{"run.arm": "L-clock", "fees.peak_fee": peak})
        runs[peak] = R.run_simulation(cfg, tmp_path / "runs", name=f"p{peak:g}")
    six, twelve = runs[6.0], runs[12.0]
    tbl = fees.read_fees_csv(twelve / "fees.csv")
    assert tbl == fees.fee_table("tou", peak_fee=12.0) and max(tbl) == 12.0 and min(tbl) == 4.0
    assert fees.read_fees_csv(six / "fees.csv") == fees.fee_table("tou")
    m6, m12 = (json.loads((d / "summary.json").read_text())["meta"] for d in (six, twelve))
    assert (m6["fee_peak"], m12["fee_peak"]) == (6.0, 12.0) and "fee_scale" not in m12
    out = pd.read_csv(twelve / "outcomes.csv")
    car = out[(out["mode"] == "CAR") & (out["gate_exit_min"] >= 0)]
    charged = car[car["day"] >= 3]
    assert len(charged) and (charged["fee_paid"] == charged["gate_exit_min"].map(lambda m: tbl[int(m)])).all()
    assert (car[car["day"] < 3]["fee_paid"] == 0).all()
    prompts = [json.loads(x) for x in (twelve / "llm_calls.jsonl").read_text().splitlines()]
    day3 = [p["user"] for p in prompts if p["day"] == 3]
    assert day3 and all("NZ$12.00" in u for u in day3) and not any("NZ$6.00" in u for u in day3)
    for name in ("decisions.csv", "outcomes.csv"):
        a, b = (pd.read_csv(d / name) for d in (six, twelve))
        assert a[a["day"] < 3].equals(b[b["day"] < 3])


@pytest.mark.parametrize("arm", ["R-clock", "L-daily"])
def test_peak_zero_is_the_same_run_as_regime_none(tmp_path: Path, data_dir: Path, arm: str) -> None:
    """--peak-fee 0 levies no charge at all: no charge day (fee_active false, scenario.csv charge_from_day 0),
    no trigger T2, no charge in the prompt, so decisions, outcomes, plans and every other run output equal a
    --regime none run's (roads on, so the road and LoS outputs are compared too)."""
    write_tiny_road_data(data_dir, pd.read_csv(data_dir / "origins.csv"))
    common = ["--arm", arm, "--n-agents", "20", "--days", "6", "--fee-start", "3", "--seed", "3",
              "--capacity-scale", "0.5", "--quiet", "--out", str(tmp_path / "runs"),
              "--set", f"run.data_dir={data_dir}", "--set", "persona.n_twins=4",
              "--set", "events.pt_disruption_day=5", "--set", "road.enabled=true"]
    assert R.main([*common, "--peak-fee", "0", "--name", "peak0"]) == 0
    assert R.main([*common, "--regime", "none", "--name", "none"]) == 0
    p0, none = tmp_path / "runs" / "peak0", tmp_path / "runs" / "none"
    for f in COMPARED + ("plans.csv",):
        assert (p0 / f).read_bytes() == (none / f).read_bytes(), f
    s0, sn = (json.loads((d / "summary.json").read_text()) for d in (p0, none))
    assert s0["days"] == sn["days"] and not any(d["fee_active"] for d in s0["days"])
    assert s0["meta"]["fee_peak"] == sn["meta"]["fee_peak"] == 0.0
    assert (s0["meta"]["fee_regime"], sn["meta"]["fee_regime"]) == ("tou", "none")
    assert not A.run_charged(s0["meta"]) and not A.run_charged(sn["meta"])
    assert pd.read_csv(p0 / "scenario.csv").set_index("key").loc["charge_from_day", "value"] == 0
    dec = pd.read_csv(p0 / "decisions.csv")
    assert not dec["triggers"].fillna("").str.contains("T2").any() and dec["wtt_removed"].eq(0).all()
    if arm.startswith("L-"):
        users = [json.loads(x)["user"] for x in (p0 / "llm_calls.jsonl").read_text().splitlines()]
        assert users and not any("congestion charge" in u.lower() for u in users)
    # a charged run of the same arm differs from the charge day on (the files are the same up to day 2)
    assert R.main([*common, "--name", "peak6"]) == 0
    p6 = tmp_path / "runs" / "peak6"
    for f in ("decisions.csv", "outcomes.csv"):
        a, b = ((d / f).read_text().splitlines() for d in (p0, p6))
        n = 1 + 2 * 20                                   # header and days 1-2 (sorted by day, agent)
        assert a[:n] == b[:n] and a[n:] != b[n:], f
    b = pd.read_csv(p6 / "decisions.csv")
    assert b.loc[b["day"] == 3, "triggers"].fillna("").str.contains("T2").any()
    assert A._same_before_charge(A.load_run(p6), A.load_run(p0)) is True


# --------------------------------------------------------------------------- analysis: fee response


@pytest.fixture
def fee_runs(tmp_path: Path, data_dir: Path) -> Path:
    """A runs folder (congested tiny roads) with R-clock at peak 6 (canonical), 0 (_peak0) and 12 (_peak12),
    R-daily at peak 6 and 0, plus runs the comparison must leave out: a variant (_flat_peak12), a run of
    the retired charge multiplier (variant _fx2) and an R-clock run of another seed."""
    write_tiny_road_data(data_dir, pd.read_csv(data_dir / "origins.csv"))
    runs = tmp_path / "runs"
    base = tiny(data_dir, **{"road.enabled": True})
    for arm, peak in (("R-clock", 6.0), ("R-clock", 0.0), ("R-clock", 12.0), ("R-daily", 6.0), ("R-daily", 0.0)):
        cfg = tiny(data_dir, **{"run.arm": arm, "fees.peak_fee": peak, "road.enabled": True})
        R.run_simulation(cfg, runs, variant=R.variant_suffix(cfg, base))
    flat = tiny(data_dir, **{"run.arm": "R-daily", "fees.regime": "flat", "fees.peak_fee": 12.0, "road.enabled": True})
    R.run_simulation(flat, runs, variant=R.variant_suffix(flat, base))
    fx = R.run_simulation(tiny(data_dir, **{"run.arm": "R-daily", "fees.peak_fee": 12.0, "road.enabled": True}),
                          runs, name="R-daily_mock_py_s3_fx2")
    s = json.loads((fx / "summary.json").read_text())
    s["meta"].update(variant="_fx2", fee_scale=2.0)
    (fx / "summary.json").write_text(json.dumps(s))
    other = tiny(data_dir, **{"run.arm": "R-clock", "run.seed": 4, "fees.peak_fee": 12.0, "road.enabled": True})
    R.run_simulation(other, runs, variant=R.variant_suffix(other, base))
    return runs


def test_discover_and_fee_response_table(fee_runs: Path) -> None:
    found = A.discover_fee_response_runs(fee_runs)
    assert list(found) == [("R-daily", 0.0), ("R-daily", 6.0), ("R-clock", 0.0), ("R-clock", 6.0),
                           ("R-clock", 12.0)]
    assert found[("R-clock", 12.0)].name == "R-clock_mock_py_s3_peak12"
    assert found[("R-clock", 0.0)].name == "R-clock_mock_py_s3_peak0"
    assert A.discover_fee_response_runs(fee_runs, seed=1) == {}
    assert list(A.discover_fee_response_runs(fee_runs, seed=4)) == [("R-clock", 12.0)]
    assert set(A.discover_runs(fee_runs)) == {"R-daily", "R-clock"}               # canonical runs only
    loaded = {k: A.load_run(d) for k, d in found.items()}
    t = A.fee_response_table(loaded, base=(1, 2), charged=(4, 6))
    own = "car_crossings_change_vs_own_d1_2_pct"
    cols = list(t.columns)
    assert cols[:4] == ["arm", "seed", "peak_fee", "window"] and cols[-2:] == ["same_before_charge_as_peak0", "run"]
    for c in ("car_share", "pt_share", "wfh_share", "travel_share", "wtt_limited_share", "wtt_no_car_share",
              "wtp_below_peak_share", "car_crossings_per_day", "car_crossings_change_pct", own,
              "mean_road_delay", "peak_queue_delay", "peak_total_delay", "revenue_per_day"):
        assert c in cols, c
    assert not any("skip" in c for c in cols)
    for tag in ("mwy", "other"):      # side by side: LoS E/F by speed, by V/C, mean V/C
        i = cols.index(f"los_ef_speed_share_{tag}")
        assert cols[i:i + 3] == [f"los_ef_speed_share_{tag}", f"los_ef_share_{tag}", f"vc_mean_{tag}"]
        assert f"congested_at_share_{tag}" in cols
    rc = t[t["arm"] == "R-clock"].reset_index(drop=True)
    assert list(rc["peak_fee"]) == [0.0, 6.0, 12.0] and set(rc["window"]) == {"d4-6"}
    assert rc.loc[0, "car_crossings_change_pct"] == 0.0 and rc.loc[0, "revenue_per_day"] == 0.0
    assert rc.loc[0, "same_before_charge_as_peak0"] is None
    assert (rc.loc[1:, "same_before_charge_as_peak0"] == True).all()  # noqa: E712
    assert ((rc[["car_share", "pt_share", "wfh_share"]].sum(axis=1) - 1.0).abs() <= 0.002).all()
    assert ((rc["travel_share"] - rc["car_share"] - rc["pt_share"]).abs() <= 0.0011).all()
    # the numbers against the run outputs
    r0, r12 = loaded[("R-clock", 0.0)], loaded[("R-clock", 12.0)]
    dd = r12["days"]
    sub = dd[(dd["day"] >= 4) & (dd["day"] <= 6)]
    n = float(sub[["cars", "pt", "wfh"]].to_numpy().sum())
    assert rc.loc[2, "travel_share"] == round(float(sub["cars"].sum() + sub["pt"].sum()) / n, 3)
    assert rc.loc[2, "revenue_per_day"] == round(float(sub["revenue"].mean()), 2) > 0
    assert rc.loc[2, "peak_queue_delay"] == round(float(sub["peak_bin_delay_wmean"].mean()), 2)
    assert rc.loc[2, "peak_total_delay"] == round(float(sub["peak_bin_total_delay_wmean"].mean()), 2)
    assert rc.loc[2, "wtt_limited_share"] == round(float(sub["wtt_limited"].sum()) / n, 4)
    assert rc.loc[2, "wtt_no_car_share"] == round(float(sub["wtt_no_car"].sum()) / n, 4)
    dec = r12["decisions"]
    w = dec[(dec["day"] >= 4) & (dec["day"] <= 6)]
    assert rc.loc[2, "wtt_limited_share"] == round(float((w["wtt_removed"] > 0).mean()), 4)
    per = r12["personas"]
    assert rc.loc[2, "wtp_below_peak_share"] == round(float((per["wtp_fee"].astype(float) < 12.0).mean()), 4)
    assert rc.loc[0, "wtp_below_peak_share"] == 0.0 and rc.loc[0, "wtt_limited_share"] == 0.0

    def cross(r: dict, d0: int, d1: int) -> float:
        o = r["outcomes"]
        c = o[(o["mode"] == "CAR") & (o["gate_exit_min"] >= 0) & (o["day"] >= d0) & (o["day"] <= d1)]
        return len(c) / (d1 - d0 + 1)
    assert rc.loc[2, "car_crossings_per_day"] == round(cross(r12, 4, 6), 1)
    assert rc.loc[2, "car_crossings_change_pct"] == round(100.0 * (cross(r12, 4, 6) / cross(r0, 4, 6) - 1.0), 1)
    assert rc.loc[2, own] == round(100.0 * (cross(r12, 4, 6) / cross(r12, 1, 2) - 1.0), 1)
    # LoS of the tiny roads: other roads only (no motorway), from los_summary.csv over 07:00-09:00
    pk = A.los_by_bin(r12, (4, 6)).set_index(["bin", "group"]).loc[("07:00-09:00", "other")]
    assert rc.loc[2, "los_ef_share_other"] == round(float(pk["share_EF"]), 4)
    assert rc.loc[2, "vc_mean_other"] == round(float(pk["vc_mean"]), 4) > 0
    assert rc.loc[2, "los_ef_speed_share_other"] == round(float(pk["share_EF_speed"]), 4)
    assert rc[["los_ef_share_mwy", "vc_mean_mwy", "los_ef_speed_share_mwy"]].isna().all().all()
    # an arm without a peak-0 run has no change against it, and no check
    t2 = A.fee_response_table({k: v for k, v in loaded.items() if k != ("R-clock", 0.0)}, base=(1, 2),
                              charged=(4, 6))
    rc2 = t2[t2["arm"] == "R-clock"]
    assert rc2["car_crossings_change_pct"].isna().all() and rc2["same_before_charge_as_peak0"].isna().all()
    assert rc2[own].notna().all()


def test_fee_response_by_group_and_outputs(fee_runs: Path, tmp_path: Path) -> None:
    labels = load_config().persona.archetype_labels
    found = A.discover_fee_response_runs(fee_runs)
    loaded = {k: A.load_run(d) for k, d in found.items()}
    g = A.fee_response_by_group(loaded, labels, charged=(4, 6))
    assert list(g.columns) == ["arm", "seed", "peak_fee", "window", "archetype", "archetype_label", "company_car",
                               "n_agents", "car_share", "pt_share", "wfh_share", "travel_share",
                               "wtt_limited_share", "wtt_no_car_share", "wtp_below_peak_share"]
    for _k, sub in g.groupby(["arm", "peak_fee"]):
        assert sub["n_agents"].sum() == 20
        assert not sub.duplicated(["archetype", "company_car"]).any()
    assert set(g["archetype_label"]) <= set(labels)
    trades = g[g["archetype"] == 4]                       # car only: no PT, no WFH, the car always kept
    assert (trades["car_share"] == 1).all() and (trades["wtt_limited_share"] == 0).all()
    assert (g.loc[g["company_car"], "wtt_limited_share"] == 0).all()   # the employer pays
    assert (g.loc[g["peak_fee"] == 0, "wtp_below_peak_share"] == 0).all()
    out = tmp_path / "fig"
    written = A._write_fee_response(fee_runs, out, load_config(), None, False, base=(1, 2), charged=(4, 6))
    assert {p.name for p in written} == {"fee_response.csv", "fee_response_by_group.csv", "fee_response.png"}
    assert all((out / f).exists() for f in A.FEE_RESPONSE_FILES)
    md = (out / "fee_response.md").read_text()
    assert "extrapolate" in md and "MockLLM" in md and A.LOS_NOTE in md and "car_crossings_change_vs_own_d1_2_pct" in md
    assert len(pd.read_csv(out / "fee_response.csv")) == 5
    # no run at another peak charge: nothing written and earlier fee-response files removed
    for d in fee_runs.glob("*_peak*"):
        (d / "summary.json").unlink()
    assert A._write_fee_response(fee_runs, out, load_config(), None, False) == []
    assert not any((out / f).exists() for f in A.FEE_RESPONSE_FILES)


def test_main_writes_the_tables_with_the_los_note(fee_runs: Path, tmp_path: Path) -> None:
    """main() on the tiny runs: the summary table carries the LoS note and no SKIP column; the 6-day runs
    do not reach the default charged days (21-30), so no fee-response files are written (and stale ones
    are removed)."""
    out = tmp_path / "fig"
    out.mkdir()
    (out / "fee_response.csv").write_text("stale\n")
    assert A.main(["--runs", str(fee_runs), "--out", str(out), "--seed", "3"]) == 0
    st = pd.read_csv(out / "summary_table.csv")
    assert set(st["run"]) == {"R-daily", "R-clock"} and not any("skip" in c for c in st.columns)
    assert A.LOS_NOTE in (out / "summary_table.md").read_text()
    assert (out / "los.png").exists() and (out / "mode_shares.png").exists()
    assert not any((out / f).exists() for f in A.FEE_RESPONSE_FILES)


def test_old_runs_are_still_read(fee_runs: Path, tmp_path: Path) -> None:
    """Runs made before 2026-10-09: no meta.fee_peak (peak from fees.csv), a "skip" day key and SKIP rows,
    no willingness to pay (no wtp_fee, no wtt columns or day keys). They load, keep their skippers in
    every share's denominator, and their willingness-to-travel numbers are nan."""
    d = fee_runs / "R-clock_mock_py_s3"
    s = json.loads((d / "summary.json").read_text())
    del s["meta"]["fee_peak"]
    for day in s["days"]:
        day["skip"] = 1 if day["day"] == 5 else 0
        day["pt"] -= day["skip"]
        for k in ("wtt_limited", "wtt_no_car"):
            del day[k]
    (d / "summary.json").write_text(json.dumps(s))
    dec = pd.read_csv(d / "decisions.csv").drop(columns=["wtt_removed", "wtt_all_removed"])
    i = dec.index[(dec["day"] == 5) & (dec["mode"] == "PT")][0]
    dec.loc[i, "mode"] = "SKIP"
    dec.to_csv(d / "decisions.csv", index=False)
    pd.read_csv(d / "personas.csv").drop(columns=["wtt_u", "wtt_beta", "wtp_fee"]).to_csv(d / "personas.csv",
                                                                                       index=False)
    m = s["meta"]
    assert A.run_fee_peak(m, d) == 6.0 and A.run_charged(m)
    assert A.discover_fee_response_runs(fee_runs)[("R-clock", 6.0)] == d
    old = A.load_run(d)
    st = A.summary_table({"old": old}, days=(5, 6)).iloc[0]
    d5 = old["days"].set_index("day").loc[5]
    assert st["pt_share_d5"] == round(d5["pt"] / (d5["cars"] + d5["pt"] + d5["wfh"] + 1), 3)
    assert not any("skip" in c for c in st.index)
    row = A.fee_response_table({("R-clock", 6.0): old}, base=(1, 2), charged=(4, 6)).iloc[0]
    assert np.isnan(row["wtt_limited_share"]) and np.isnan(row["wtp_below_peak_share"])
    assert row["car_share"] + row["pt_share"] + row["wfh_share"] < 1.0           # one skipper in the window
    g = A.fee_response_by_group({("R-clock", 6.0): old}, charged=(4, 6))
    assert g["wtt_limited_share"].isna().all() and g["wtp_below_peak_share"].isna().all()
    assert A._modal_mode(old["decisions"], 5, 5).isin(["CAR", "PT", "WFH", "SKIP"]).all()
    assert A.fig_mode_shares({"old": old}, tmp_path / "fig").exists()
