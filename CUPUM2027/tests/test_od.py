"""Unit tests for the Census OD step (prep/build_od.py) and its use in prep/build_inputs.py (toy data)."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, box

from cordonlite.config import load_config
from prep import build_inputs as bi
from prep import build_od as bo

DRV, CO, BUS, TRAIN = ("2023_Drive_a_private_car_truck_or_van", "2023_Drive_a_company_car_truck_or_van",
                       "2023_Public_bus", "2023_Train")
MODES = [DRV, CO, BUS, TRAIN]


def test_allocate_caps_cells_and_passes_the_rest_on() -> None:
    out = bo._allocate(11.0, np.array([0.4, 0.1]), 5.0)
    assert out.tolist() == pytest.approx([5.0, 5.0])        # 8.8 + 2.2, bus capped, train takes the rest
    out = bo._allocate(4.0, np.array([0.5, 0.0, 0.5]), 5.0)
    assert out.tolist() == pytest.approx([2.0, 0.0, 2.0])   # a mode with no share gets nothing
    assert bo._allocate(0.0, np.array([1.0]), 5.0).tolist() == [0.0]


def test_impute_pairs_residual_and_suppressed_total() -> None:
    pairs = pd.DataFrame({DRV: [9, -999, 30], CO: [-999, -999, 0], BUS: [-999, -999, 6], TRAIN: [6, -999, 0],
                          bo.TOTAL_COL: [18, -999, 36]})
    shares = pd.Series({DRV: 0.5, CO: 0.0, BUS: 0.5, TRAIN: 0.0})
    f = bo.impute_pairs(pairs, MODES, shares, 5.0, 3.0)
    # pair 0: residual 18 - 15 = 3, all of it to the bus (the company car has no share)
    assert f.loc[0].tolist() == pytest.approx([9.0, 0.0, 3.0, 6.0])
    # pair 1: total suppressed -> 3 commuters, split by the shares
    assert f.loc[1].tolist() == pytest.approx([1.5, 0.0, 1.5, 0.0])
    # pair 2: nothing suppressed, the shown cells stay (the total is not forced)
    assert f.loc[2].tolist() == [30.0, 0.0, 6.0, 0.0]


def _toy_files(tmp) -> dict:
    """Cordon = SA2 'C' (0..100 square); home SA2s 'A' (100..200) and 'B' (200..300) and 'Z' with no polygon."""
    sa3 = gpd.GeoDataFrame({"SA32025_V1_00_NAME": ["Auckland City Centre", "Elsewhere"]},
                           geometry=[box(0, 0, 100, 100), box(100, 0, 400, 100)], crs="EPSG:2193")
    sa3_path = tmp / "sa3.gpkg"
    sa3.to_file(sa3_path, driver="GPKG")
    sa2 = gpd.GeoDataFrame({"SA22026_V1_00": ["100", "200", "300"], "SA22026_V1_00_NAME_ASCII": ["C", "A", "B"]},
                           geometry=[box(0, 0, 100, 100), box(100, 0, 200, 100), box(200, 0, 300, 100)],
                           crs="EPSG:2193")
    sa2_path = tmp / "sa2.gpkg"
    sa2.to_file(sa2_path, driver="GPKG")
    cols = ["SA22023_V1_00_usual_residence_address", "SA22023_V1_00_NAME_ASCII_usual_residence_address",
            "SA22023_V1_00_workplace_address", "SA22023_V1_00_NAME_ASCII_workplace_address", "2023_Work_at_home",
            *MODES, bo.TOTAL_COL]
    rows = [["200", "A", "100", "C", -999, -999, -999, 6, -999, 9],   # A -> cordon: residual 3
            ["300", "B", "100", "C", -999, -999, -999, -999, -999, -999],   # B -> cordon: total suppressed
            ["100", "C", "100", "C", 30, 6, -999, -999, -999, 39],    # lives in the cordon: left out
            ["200", "A", "300", "B", -999, 60, -999, -999, -999, 60],  # works outside the cordon: left out
            ["900", "Z", "100", "C", -999, 6, -999, -999, -999, 6]]   # no polygon: dropped
    od_path = tmp / "od.csv"
    pd.DataFrame(rows, columns=cols).to_csv(od_path, index=False)
    return {"prep.census_od_csv": str(od_path), "prep.sa2_gpkg": str(sa2_path), "prep.cordon_gpkg": str(sa3_path)}


def test_build_od_toy(tmp_path) -> None:
    cfg = load_config(overrides=_toy_files(tmp_path))
    by, st = bo.build_od(cfg)
    assert list(by.columns) == list(bo.OD_COLUMNS)
    assert by["sa2_code"].tolist() == ["200", "300"]
    # shares of the shown outside-to-cordon cells (Z's 6 drivers count here): driving 6 of 12, bus 6 of 12
    a, b = by.set_index("sa2_code").loc["200"], by.set_index("sa2_code").loc["300"]
    assert a["drivers_shown"] == 0 and a["drivers_to_cordon"] == pytest.approx(3.0)   # A's residual 9 - 6, all driving
    assert b["drivers_shown"] == 0 and b["drivers_to_cordon"] == pytest.approx(1.5)   # 3 commuters, half driving
    assert 100 < a["x_nztm"] < 200 and 0 < a["y_nztm"] < 100
    assert len(st["unmatched"]) == 1 and st["n_cbd_sa2"] == 1 and st["drivers_shown"] == 6
    assert "Drivers, shown cells only" in bo.render_report(cfg, by, st)


def test_od_weights_split_within_sa2_and_snap(tmp_path) -> None:
    files = _toy_files(tmp_path)
    cfg = load_config(overrides={**files, "prep.density_radius_m": 20.0})
    # candidate nodes: two in A (local road 100 m and 300 m near them), one in neither (x = 350)
    xy = np.array([[120.0, 50.0], [180.0, 50.0], [350.0, 50.0]])
    roads = gpd.GeoDataFrame({"frc": [4, 4], "distance": [100.0, 300.0]},
                             geometry=[LineString([(115, 50), (125, 50)]), LineString([(175, 50), (185, 50)])],
                             crs="EPSG:2193")
    od = pd.DataFrame({"sa2_code": ["200", "300"], "sa2_name": ["A", "B"], "x_nztm": [140.0, 280.0],
                       "y_nztm": [50.0, 50.0], "drivers_to_cordon": [40.0, 10.0]})
    w, info = bi.od_weights(xy, roads, od, cfg)
    assert w.tolist() == pytest.approx([10.0, 30.0, 10.0])   # A by the proxy; B has no node -> nearest (x = 350)
    assert info["n_snapped"] == 1 and info["drivers_snapped"] == 10.0
    w, _ = bi.od_weights(xy, roads, od, load_config(overrides={**files, "prep.od_within_sa2": "snap"}))
    assert w.tolist() == pytest.approx([40.0, 0.0, 10.0])    # A at the node nearest (140, 50): x = 120
