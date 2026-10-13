"""Analysis with road congestion: road delay and Level of Service (LoS E/F share by V/C and by speed,
AT congested share, mean V/C) in the summary table, the road-delay and LoS figures."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cordonlite import analysis as A
from cordonlite import roads as roadsmod
from cordonlite import run as R
from cordonlite.config import load_config
from tests.conftest import write_tiny_road_data


@pytest.fixture
def runs(tmp_path: Path, tiny_origins: pd.DataFrame, tiny_corridors_prep: pd.DataFrame) -> dict[str, dict]:
    """Tiny R-daily runs (20 agents, 6 days) with roads on and off."""
    data = tmp_path / "data"
    data.mkdir()
    tiny_origins.to_csv(data / "origins.csv", index=False)
    tiny_corridors_prep.to_csv(data / "corridors.csv", index=False)
    write_tiny_road_data(data, tiny_origins)
    out = {}
    for on in (True, False):
        cfg = load_config(overrides={
            "run.n_agents": 20, "run.n_days": 6, "fees.fee_start_day": 3, "persona.n_twins": 4,
            "events.pt_disruption_day": 5, "run.data_dir": str(data), "run.seed": 3,
            "engine.use_calibration": False, "engine.capacity_scale": 0.5, "run.arm": "R-daily",
            "road.enabled": on})
        d = R.run_simulation(cfg, tmp_path / "runs", name="on" if on else "off")
        out["on" if on else "off"] = A.load_run(d)
    return out


def test_summary_table_road_columns(runs: dict[str, dict]) -> None:
    st = A.summary_table(runs, days=(2, 6), periods=((1, 3), (4, 6))).set_index("run")
    for col in ("mean_road_delay_d1_3", "mean_road_delay_d4_6", "car_door_to_door_d1_3", "car_door_to_door_d4_6"):
        assert col in st.columns
    o = runs["on"]["outcomes"]
    for d0, d1 in ((1, 3), (4, 6)):
        car = o[(o["mode"] == "CAR") & (o["day"] >= d0) & (o["day"] <= d1)]
        served = car[car["gate_exit_min"] >= 0]
        assert st.loc["on", f"mean_road_delay_d{d0}_{d1}"] == round(float(car["road_delay_min"].mean()), 2) > 0
        assert st.loc["on", f"car_door_to_door_d{d0}_{d1}"] == round(
            float((served["arrive_min"] - served["depart_min"]).mean()), 2)
        assert st.loc["off", f"mean_road_delay_d{d0}_{d1}"] == 0.0
    # the summary.json day means agree (equal car counts per day are not needed: compare one day)
    day1 = runs["on"]["days"].set_index("day").loc[1]
    assert A.summary_table(runs, days=(2, 6), periods=((1, 1),)).set_index("run").loc[
        "on", "mean_road_delay_d1_1"] == round(float(day1["mean_road_delay"]), 2)
    # default periods (days 6-10, 21-30) are left out of a 6-day run
    assert not any(c.startswith("mean_road_delay") for c in A.summary_table(runs, days=(2, 6)).columns)


def test_road_delay_by_departure_and_figure(runs: dict[str, dict], tmp_path: Path) -> None:
    t = A.road_delay_by_departure(runs["on"], (1, 3))
    assert list(t.columns) == ["bin_start", "bin_mid", "cars", "mean_road_delay"]
    o = runs["on"]["outcomes"]
    car = o[(o["mode"] == "CAR") & (o["day"] <= 3)]
    assert int(t["cars"].sum()) == len(car)
    assert float(np.average(t["mean_road_delay"], weights=t["cars"])) == pytest.approx(car["road_delay_min"].mean())
    assert (t["bin_start"] % 15 == 0).all() and (t["bin_mid"] == t["bin_start"] + 7.5).all()
    assert (A.road_delay_by_departure(runs["off"], (1, 3))["mean_road_delay"] == 0).all()
    # a run made before road congestion was modelled has no road_delay_min column
    old = dict(runs["off"], outcomes=runs["off"]["outcomes"].drop(columns=["road_delay_min"]), label="old")
    assert len(A.road_delay_by_departure(old, (1, 3))) == 0
    assert np.isnan(A.summary_table({"old": old}, days=(2, 6), periods=((1, 3),))["mean_road_delay_d1_3"].iloc[0])
    p = A.fig_road_delay({**runs, "old": old}, tmp_path / "fig", pre=(1, 3), post=(4, 6))
    assert p.exists() and p.name == "road_delay.png" and p.stat().st_size > 0



def test_summary_table_los_columns_and_los_by_bin(runs: dict[str, dict]) -> None:
    """LoS E/F share (by V/C and by speed), AT congested share and mean V/C over 07:00-09:00 per period:
    los_summary.csv pooled over the days by vehicle-km; nan for motorways when there are none (the tiny
    data) and for a run without roads."""
    st = A.summary_table(runs, days=(2, 6), periods=((1, 3), (4, 6))).set_index("run")
    for d in ("d1_3", "d4_6"):
        for key in ("los_ef_share", "vc_mean", "los_ef_speed_share", "congested_at_share"):
            for tag in ("mwy", "other"):
                assert f"{key}_{tag}_{d}" in st.columns
                assert np.isnan(st.loc["off", f"{key}_{tag}_{d}"])
            assert np.isnan(st.loc["on", f"{key}_mwy_{d}"])
    ls = runs["on"]["los_summary"]
    sub = ls[(ls["day"] <= 3) & (ls["bin"] == "07:00-09:00") & (ls["group"] == "other")]
    vkm = sub["veh_km"].sum()
    for key, col in (("los_ef_share", "share_EF"), ("vc_mean", "vc_mean"), ("los_ef_speed_share", "share_EF_speed"),
                     ("congested_at_share", "share_congested_AT")):
        assert st.loc["on", f"{key}_other_d1_3"] == round(float((sub[col] * sub["veh_km"]).sum() / vkm), 4), key
    assert 0 < st.loc["on", "vc_mean_other_d1_3"]
    # one day: los_by_bin is that day's row (summary.json keys round it to 4 dp)
    t = A.los_by_bin(runs["on"], (2, 2))
    assert list(t.columns) == ["bin", "group", "share_EF", "vc_mean", "veh_km", "share_EF_speed",
                               "share_congested_AT"]
    assert t["bin"].tolist() == [b[0] for b in roadsmod.LOS_BINS for _g in ("motorway", "other")]
    assert t["group"].tolist() == ["motorway", "other"] * len(roadsmod.LOS_BINS)
    mw = t[t["group"] == "motorway"]                         # no motorway in the tiny data: no traffic
    assert (mw["veh_km"] == 0).all() and mw["share_EF"].isna().all()
    t = t[t["group"] == "other"]
    day2 = runs["on"]["days"].set_index("day").loc[2]
    pk = t[t["bin"] == "07:00-09:00"].iloc[0]
    assert round(float(pk["share_EF"]), 4) == day2["los_ef_share_other"]
    assert round(float(pk["vc_mean"]), 4) == day2["vc_mean_other"]
    assert round(float(pk["share_EF_speed"]), 4) == day2["los_ef_speed_share_other"]
    assert round(float(pk["share_congested_AT"]), 4) == day2["congested_at_share_other"]
    assert len(A.los_by_bin(runs["off"], (1, 3))) == 0
    # a los_summary.csv made before the speed-based columns: those are nan, the others as before
    old_ls = ls.drop(columns=["share_EF_speed", "share_congested_AT"])
    t_old = A.los_by_bin(dict(runs["on"], los_summary=old_ls), (1, 3))
    t_new = A.los_by_bin(runs["on"], (1, 3))
    assert t_old["share_EF_speed"].isna().all() and t_old["share_congested_AT"].isna().all()
    pd.testing.assert_frame_equal(t_old[["bin", "group", "share_EF", "vc_mean", "veh_km"]],
                                  t_new[["bin", "group", "share_EF", "vc_mean", "veh_km"]])
    # a run made before the LoS outputs (no los_summary.csv) loads with an empty frame
    old_dir = Path(runs["on"]["dir"])
    assert len(A.load_run(old_dir)["los_summary"]) == len(ls)


def test_los_by_bin_pools_every_share_by_vehicle_km() -> None:
    """los_by_bin on a hand-made los_summary: each share (by V/C, by speed, AT congested) and the mean
    V/C of a bin is the vehicle-km weighted mean of the days' values."""
    rows = []
    for day, vkm, ef, vc, efs, at in ((1, 100.0, 1.0, 1.4, 0.10, 0.20), (2, 300.0, 0.5, 1.0, 0.30, 0.60)):
        for b in roadsmod.LOS_BINS:
            rows.append((day, b[0], "other", ef, vc, 0.8, vkm, efs, at))
            rows.append((day, b[0], "motorway", ef, vc, 0.8, 0.0, np.nan, np.nan))
    ls = pd.DataFrame(rows, columns=list(roadsmod.LOS_SUMMARY_COLUMNS))
    t = A.los_by_bin({"los_summary": ls}, (1, 2)).set_index(["bin", "group"])
    pk = t.loc[(roadsmod.LOS_PEAK_BIN, "other")]
    assert pk["veh_km"] == 400.0
    assert pk["share_EF"] == pytest.approx((100 * 1.0 + 300 * 0.5) / 400)
    assert pk["vc_mean"] == pytest.approx((100 * 1.4 + 300 * 1.0) / 400)
    assert pk["share_EF_speed"] == pytest.approx((100 * 0.10 + 300 * 0.30) / 400)
    assert pk["share_congested_AT"] == pytest.approx((100 * 0.20 + 300 * 0.60) / 400)
    assert np.isnan(t.loc[(roadsmod.LOS_PEAK_BIN, "motorway"), "share_EF_speed"])


def test_fig_los(runs: dict[str, dict], tmp_path: Path) -> None:
    p = A.fig_los(runs, tmp_path / "fig", pre=(1, 3), post=(4, 6))
    assert p.exists() and p.name == "los.png" and p.stat().st_size > 0
    old = dict(runs["off"], los_summary=pd.DataFrame(columns=list(roadsmod.LOS_SUMMARY_COLUMNS)), label="old")
    assert A.fig_los({"old": old}, tmp_path / "fig2", pre=(1, 3), post=(4, 6)).exists()
    # a run made before the speed-based columns: those panels say so, the others are drawn
    pre_speed = dict(runs["on"], los_summary=runs["on"]["los_summary"].drop(columns=["share_EF_speed",
                                                                                     "share_congested_AT"]))
    assert A.fig_los({"on": runs["on"], "pre": pre_speed}, tmp_path / "fig3", pre=(1, 3), post=(4, 6)).exists()
    assert {"road_los.csv", "los_summary.csv"} <= set(A.OUTPUT_FILES)
