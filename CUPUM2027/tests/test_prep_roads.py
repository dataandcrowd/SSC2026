"""Unit tests for prep/build_roads.py (toy networks and toy count files, no real data, no NetLogo)."""

from __future__ import annotations

import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, box

from cordonlite.config import load_config
from prep import build_inputs as bi
from prep import build_roads as br


def _edges(spec: list[tuple]) -> pd.DataFrame:
    """Toy edge table from (u, v, street_name, frc, two_way) tuples; geometry u -> v, 50 km/h."""
    rows = []
    for i, (u, v, name, frc, two_way) in enumerate(spec):
        g = LineString([u, v])
        rows.append({"u": u, "v": v, "row": i, "segment_id": f"s{i}", "minutes": g.length / (50000 / 60),
                     "distance_m": g.length, "frc": frc, "speed_limit": 50, "street_name": name,
                     "core": br.norm_name(name), "ramp": br.is_ramp_name(name),
                     "bearing": float(bi.bearing_deg(u[0], u[1], v[0], v[1])), "two_way": two_way,
                     "geometry": g})
    return pd.DataFrame(rows)


def _counts(rows: list[dict]) -> pd.DataFrame:
    """Toy count table in the load_counts format."""
    out = []
    for i, r in enumerate(rows):
        kind, route = br.count_kind(r["road_name"])
        out.append({"count_id": r.get("count_id", i + 1), "road_name": r["road_name"], "kind": kind,
                    "route": route, "core": br.norm_name(r["road_name"]) if kind == "local" else "",
                    "adt": float(r["adt"]), "peaktraffic": float(r.get("peaktraffic", math.nan)),
                    "peak_min": br.parse_peak_hour(r.get("peak_hour")), "count_date": r.get("count_date", "2020-01-01"),
                    "x": float(r["x"]), "y": float(r["y"])})
    return pd.DataFrame(out)


# --------------------------------------------------------------------------- names and counts


@pytest.mark.parametrize("raw, expected", [
    ("Exit 429B Wellesley Street", "WELLESLEY"),
    ("WELLESLEY ST", "WELLESLEY"),
    ("MT EDEN RD (NORTH)", "MT EDEN"),
    ("Mount Eden Road", "MT EDEN"),
    ("GREAT SOUTH RD", "GREAT SOUTH"),
    ("Great South Road", "GREAT SOUTH"),
    ("Saint Luke's Road", "ST LUKES"),
    ("ST LUKES RD", "ST LUKES"),
    ("WAIRAU RD (TAKA/GLENFIELD/E.C", "WAIRAU"),
    ("QUEEN ST N", "QUEEN"),
    ("Terrace Atatu Road", "TE ATATU"),
    ("TE ATATU RD", "TE ATATU"),
    ("Southern Motorway", "SOUTHERN"),
    ("Upper Harbour Highway", "UPPER HARBOUR"),
    ("Entry And Exit 444 East Tamaki Road", "EAST TAMAKI"),
    ("Entry 424 Fanshawe Street", "FANSHAWE"),
    ("WEST COAST RD", "WEST COAST"),
    ("The Strand", "THE STRAND"),
    ("Road", "ROAD"),
    ("", ""),
    (None, ""),
    (float("nan"), ""),
])
def test_norm_name(raw, expected) -> None:
    assert br.norm_name(raw) == expected


def test_ramp_names() -> None:
    assert br.is_ramp_name("Exit 4A Northern Motorway")
    assert br.is_ramp_name("Northern Motorway Entry")
    assert br.is_ramp_name("Entry 19 Maioro Street")
    assert not br.is_ramp_name("Southern Motorway")
    assert not br.is_ramp_name("Exeter Road")


def test_motorway_mainline() -> None:
    assert br.is_motorway(0, 100, "Southern Motorway") and br.is_motorway(0, 80, "Upper Harbour Motorway")
    assert br.is_motorway(0, 100, "20") and br.is_motorway(0, 100, "Airport Motorway")
    # motorway by name at a lower frc: the Auckland Harbour Bridge stretch of the Northern Motorway
    assert br.is_motorway(2, 80, "Northern Motorway") and br.is_motorway(1, 80, "Northern Motorway")
    assert br.is_motorway(3, 100, "Southwestern Motorway")
    for frc, spd, name in ((0, 100, "Exit 4A Northern Motorway"), (0, 100, "Entry 449 Southwestern Motorway"),
                           (0, 80, "Exit 424D Helensville"), (0, 100, "Entry And Exit 7 Northern Motorway"),
                           (0, 100, "Northern Motorway On-Ramp"), (0, 100, "Southern Motorway Off-Ramp"),
                           (0, 50, "Stanley Street"), (0, 60, "George Bolt Memorial Drive"),
                           (2, 80, "Exit 2 Southern Motorway"), (3, 100, "Entry 448 Southwestern Motorway"),
                           (1, 50, "Northern Motorway"), (1, 80, "State Highway 16"), (1, 100, "Upper Harbour Highway"),
                           (2, 80, "South Eastern Highway"), (2, 80, "Albany Expressway"), (1, 50, "19")):
        assert not br.is_motorway(frc, spd, name), name


def test_motorway_names() -> None:
    for name in ("Northern Motorway", "Southern Motorway", "Northwestern Motorway", "Southwestern Motorway",
                 "Upper Harbour Motorway", "Airport Motorway", "Exit 2 Southern Motorway"):
        assert br.is_motorway_name(name), name
    for name in ("Upper Harbour Highway", "State Highway 16", "20", "", "Great North Road", None, float("nan")):
        assert not br.is_motorway_name(name), name


def test_parse_peak_hour_formats() -> None:
    assert br.parse_peak_hour("800") == 480
    assert br.parse_peak_hour("0800") == 480
    assert br.parse_peak_hour("08:00") == 480
    assert br.parse_peak_hour("8:15") == 495
    assert br.parse_peak_hour("16:") == 960
    assert math.isnan(br.parse_peak_hour("abc"))
    assert math.isnan(br.parse_peak_hour(None))
    assert math.isnan(br.parse_peak_hour(float("nan")))


def test_count_kind() -> None:
    assert br.count_kind("SH 01N-0431-I") == ("sh_cway", "01N")
    assert br.count_kind("SH 01N-0448/05.06-D") == ("sh_cway", "01N")
    assert br.count_kind("SH 016-0019-R1") == ("sh_ramp", "016")
    assert br.count_kind("SH 20A-0000-R12") == ("sh_ramp", "20A")
    assert br.count_kind("SH 01N-0414/09.02") == ("sh_other", "01N")
    assert br.count_kind("GREAT SOUTH RD") == ("local", "")
    assert br.count_kind(None) == ("local", "")


def test_speed_band() -> None:
    assert [br.speed_band(s) for s in (30, 35, 40, 50, 60, 70, 80, 90, 100)] == [35, 35, 40, 50, 60, 70, 80, 80, 100]


# --------------------------------------------------------------------------- matching


def test_match_is_name_checked_within_distance_and_keeps_latest() -> None:
    E = _edges([
        ((0.0, 0.0), (100.0, 0.0), "Great South Road", 2, True),     # e0
        ((0.0, 0.0), (0.0, 100.0), "Merino Avenue", 4, True),        # e1 cross street
        ((500.0, 0.0), (500.0, 300.0), "Southern Motorway", 0, False),  # e2
        ((520.0, 300.0), (520.0, 0.0), "Northwestern Motorway", 0, False),  # e3 other route
        ((700.0, 0.0), (700.0, 200.0), "Exit 4A Northern Motorway", 1, False),  # e4 ramp
    ])
    C = _counts([
        {"road_name": "GREAT SOUTH RD", "adt": 1000, "x": 0.5, "y": 5.0, "count_date": "2015-03-01"},  # nearer e1, name -> e0
        {"road_name": "GREAT SOUTH RD", "adt": 2000, "x": 60.0, "y": 3.0, "count_date": "2021-03-01"},  # e0, more recent
        {"road_name": "MERINO AVE", "adt": 300, "x": 50.0, "y": 40.0},                                 # 40+ m from both
        {"road_name": "SH 01N-0427-I", "adt": 50000, "x": 505.0, "y": 100.0},                           # e2
        {"road_name": "SH 01N-0427-D", "adt": 50000, "x": 545.0, "y": 100.0},                           # e3 is not route 01N
        {"road_name": "SH 01N-0427-R2", "adt": 9000, "x": 705.0, "y": 50.0},                            # ramp e4
        {"road_name": "SH 01N-0427-R3", "adt": 9000, "x": 505.0, "y": 250.0},                           # ramp record near carriageway
    ])
    pm, em = br.match_counts(E, C, 30.0)
    got = dict(zip(pm["ci"], pm["edge"]))
    assert got == {0: 0, 1: 0, 3: 2, 5: 4}
    assert dict(zip(em["edge"], em["ci"])) == {0: 1, 2: 3, 4: 5}


def test_directional_convention_and_peak_ratio() -> None:
    cfg = load_config()
    E = _edges([
        ((0.0, 0.0), (100.0, 0.0), "A Road", 2, True),
        ((0.0, 10.0), (100.0, 10.0), "B Road", 2, False),
        ((0.0, 20.0), (100.0, 20.0), "Southern Motorway", 0, False),
        ((0.0, 30.0), (100.0, 30.0), "Exit 1 Southern Motorway", 0, False),
        ((0.0, 40.0), (100.0, 40.0), "C Road", 3, True),
        ((0.0, 50.0), (100.0, 50.0), "D Road", 3, True),
        ((0.0, 60.0), (100.0, 60.0), "E Road", 3, True),
        ((0.0, 70.0), (100.0, 70.0), "Ti Rakau Drive", 2, True),
        ((0.0, 80.0), (100.0, 80.0), "Pakuranga Road", 2, False),
        ((0.0, 90.0), (100.0, 90.0), "Boundary Road", 3, True),
    ])
    C = _counts([
        {"road_name": "A RD", "adt": 1000, "peaktraffic": 120, "peak_hour": "08:00", "x": 0, "y": 0},
        {"road_name": "B RD", "adt": 1000, "peaktraffic": 120, "peak_hour": "1700", "x": 0, "y": 0},
        {"road_name": "SH 01N-0427-I", "adt": 30000, "x": 0, "y": 0},
        {"road_name": "SH 01N-0427-R1", "adt": 5000, "x": 0, "y": 0},
        {"road_name": "C RD", "adt": 1000, "peaktraffic": 300, "peak_hour": "945", "x": 0, "y": 0},
        {"road_name": "D RD", "adt": 1000, "peaktraffic": 10, "peak_hour": "07:30", "x": 0, "y": 0},
        {"road_name": "E RD", "adt": 1000, "peaktraffic": 120, "peak_hour": "10:00", "x": 0, "y": 0},
        {"road_name": "TI RAKAU DR (EASTBOUND)", "adt": 1000, "x": 0, "y": 0},
        {"road_name": "PAKURANGA RD (EAST BOUND)", "adt": 1000, "x": 0, "y": 0},
        {"road_name": "BOUNDARY RD", "adt": 1000, "x": 0, "y": 0},
    ])
    em = pd.DataFrame({"edge": range(10), "ci": range(10), "dist_m": 0.0})
    d = br.direct_values(E, C, em, cfg)
    # AT count: a two-way total, also on an edge without a reversed twin (B Road: in the real network
    # mostly a carriageway of a divided road); directional only when its name names a direction.
    # SH carriageway and ramp counts are directional.
    assert d.loc[0, ["adt_twoway", "adt_dir"]].tolist() == [1000.0, 500.0]
    assert d.loc[1, ["adt_twoway", "adt_dir"]].tolist() == [1000.0, 500.0]
    assert d.loc[2, ["adt_twoway", "adt_dir"]].tolist() == [60000.0, 30000.0]
    assert d.loc[3, ["adt_twoway", "adt_dir"]].tolist() == [10000.0, 5000.0]
    assert d.loc[7, ["adt_twoway", "adt_dir"]].tolist() == [2000.0, 1000.0]   # labelled, twin edge
    assert d.loc[8, ["adt_twoway", "adt_dir"]].tolist() == [2000.0, 1000.0]   # 'EAST BOUND' spelling
    assert d.loc[9, ["adt_twoway", "adt_dir"]].tolist() == [1000.0, 500.0]    # BOUNDARY is not a label
    # so obs_peak / (k adt_dir) = 2 share ratio / k everywhere
    assert (d["adt_twoway"] == 2 * d["adt_dir"]).all()
    assert d.at[0, "peak_ratio"] == pytest.approx(0.12)
    assert d.at[1, "peak_ratio"] == cfg.prep.road_peak_ratio_default     # PM peak
    assert d.at[2, "peak_ratio"] == cfg.prep.road_peak_ratio_default     # SH: no peak data
    assert d.at[4, "peak_ratio"] == 0.2                                    # 09:45 counts as AM, clipped
    assert d.at[5, "peak_ratio"] == 0.05                                   # clipped up
    assert d.at[6, "peak_ratio"] == cfg.prep.road_peak_ratio_default     # 10:00 is not AM
    assert d["count_peak"].tolist() == [True, False, False, False, True, True, False, False, False, False]


def test_direction_label() -> None:
    for name in ("TI RAKAU DR (EASTBOUND)", "PAKURANGA RD (EAST BOUND)", "ORMISTON RD (EASTBOUND/FLAT BUSH) (SE)",
                 "Great South Rd (Manukau) (Northbound)", "CAVENDISH DR (WESTBOUND)", "X RD (SOUTH BOUND)"):
        assert br.has_direction_label(name), name
    for name in ("BOUNDARY RD", "HOMEWARD BOUND", "LINCOLN RD", "", None, math.nan, "EAST COAST RD"):
        assert not br.has_direction_label(name), name


def test_stale_counts_are_not_used() -> None:
    """An AT count below a quarter of a more recent count of the same street within stale_m is dropped;
    a newer small count, a similar older count, a far one and another street are kept."""
    E = _edges([
        ((0.0, 0.0), (100.0, 0.0), "Wairau Road", 2, True),      # e0: 1999 count of 64
        ((100.0, 0.0), (200.0, 0.0), "Wairau Road", 2, True),    # e1: 2024 count of 19,798
        ((200.0, 0.0), (300.0, 0.0), "Wairau Road", 2, True),    # e2: 2010 count of 6,000 (above a quarter)
        ((0.0, 50.0), (100.0, 50.0), "Target Road", 3, True),    # e3: other street, small, old
        ((0.0, 3000.0), (100.0, 3000.0), "Wairau Road", 2, True),  # e4: far away, old, small
        ((0.0, 100.0), (100.0, 100.0), "Kay Road", 3, True),     # e5: newer small count, older big one (e6)
        ((100.0, 100.0), (200.0, 100.0), "Kay Road", 3, True),
        ((0.0, 150.0), (100.0, 150.0), "Ti Rakau Drive", 2, True),   # e7: labelled 3,000 (6,000 two-way)
        ((100.0, 150.0), (200.0, 150.0), "Ti Rakau Drive", 2, True),  # e8: 20,000 two-way, newer
    ])
    C = _counts([
        {"road_name": "WAIRAU RD (WEST)", "adt": 64, "x": 50.0, "y": 2.0, "count_date": "1999-08-08"},
        {"road_name": "WAIRAU RD", "adt": 19798, "x": 150.0, "y": 2.0, "count_date": "2024-03-01"},
        {"road_name": "WAIRAU RD", "adt": 6000, "x": 250.0, "y": 2.0, "count_date": "2010-01-01"},
        {"road_name": "TARGET RD", "adt": 500, "x": 50.0, "y": 52.0, "count_date": "1990-01-01"},
        {"road_name": "WAIRAU RD", "adt": 100, "x": 50.0, "y": 3002.0, "count_date": "1995-01-01"},
        {"road_name": "KAY RD", "adt": 400, "x": 50.0, "y": 102.0, "count_date": "2025-01-01"},
        {"road_name": "KAY RD", "adt": 9000, "x": 150.0, "y": 102.0, "count_date": "2001-01-01"},
        {"road_name": "TI RAKAU DR (EASTBOUND)", "adt": 3000, "x": 50.0, "y": 152.0, "count_date": "2000-01-01"},
        {"road_name": "TI RAKAU DR", "adt": 20000, "x": 150.0, "y": 152.0, "count_date": "2020-01-01"},
    ])
    pm, em = br.match_counts(E, C, 30.0, stale_m=1000.0)
    assert dict(zip(pm["ci"], pm["edge"])) == {i: i for i in range(9)}
    assert pm.loc[pm["stale"], "ci"].tolist() == [0]
    assert sorted(em["edge"]) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert br.stale_counts(C, pm, 1000.0).tolist() == pm["stale"].tolist()
    pm0, em0 = br.match_counts(E, C, 30.0)                  # no stale check
    assert not pm0["stale"].any() and sorted(em0["edge"]) == list(range(9))


def test_load_counts_skips_bus_ramps(tmp_path: Path) -> None:
    """State-highway ramp records of bus-only ramps or busways (named so, or under half cars) are not
    used; a general ramp and an AT record naming a bus stop are."""
    pts = gpd.GeoDataFrame({
        "OBJECTID": [1, 2, 3, 4, 5, 6],
        "road_name": ["SH 01N-0414-R5", "SH 01N-0414-R2", "SH 01N-0422-R1", "THE AVENUE (LYNFIELD)", "SH 01N-0410-R6",
                      "SH 01N-0414-R5"],
        "start_name": ["START OF BUS RAMP", "CONSTELLATION DR", "START OF ISLAND NOSE", "BUS LAYOVER",
                       "ISLAND NOSE/BUSES ONLY (MOTORWAY)", "CONSTELLATION STATION NTH SEAL JOIN"],
        "end_name": ["CONSTELLATION STATION", "MOTORWAY", "ONEWA SOUTHBOUND BUSWAY BRIDGE NTH ABUT", "ORIANA AVE",
                     "ISLAND NOSE", "START ISLAND NOSE"],
        "adt": [311.0, 15400.0, 578.0, 5774.0, 63.0, 225.0], "peaktraffic": [np.nan] * 6, "peak_hour": [None] * 6,
        "count_date": ["2016-12-28"] * 6, "pccar": [12.0, 97.0, 5.0, 30.0, 13.0, 11.0],
    }, geometry=gpd.points_from_xy([X0] * 6, [Y0] * 6), crs="EPSG:2193").to_crs(4326)
    path = tmp_path / "adt.geojson"
    pts.to_file(path, driver="GeoJSON")
    counts, stats = br.load_counts(load_config(overrides={"prep.adt_geojson": str(path)}))
    assert counts["count_id"].tolist() == [2, 4]
    assert stats["n_sh_ramp_bus"] == 4 and stats["n_sh_ramp"] == 1 and stats["n_local"] == 1
    # without composition data the names alone decide
    pts.drop(columns="pccar").to_file(path, driver="GeoJSON")
    counts, stats = br.load_counts(load_config(overrides={"prep.adt_geojson": str(path)}))
    assert counts["count_id"].tolist() == [2, 4, 6] and stats["n_sh_ramp_bus"] == 3


# --------------------------------------------------------------------------- propagation


def _direct(E: pd.DataFrame, rows: dict[int, tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame({"count_id": list(range(1, len(rows) + 1)), "kind": [k for k, _ in rows.values()],
                         "adt_twoway": [a for _, a in rows.values()], "adt_dir": [a / 2 for _, a in rows.values()],
                         "peak_ratio": 0.096, "count_peak": False}, index=pd.Index(list(rows), name="edge"))


def test_propagation_same_street_within_distance_nearest_wins() -> None:
    E = _edges([
        ((0.0, 0.0), (400.0, 0.0), "Main Street", 3, True),        # e0 count
        ((400.0, 0.0), (800.0, 0.0), "Main Street", 3, True),      # e1 400 m from e0
        ((800.0, 0.0), (1200.0, 0.0), "Main Street", 3, True),     # e2 800 m from e0, 400 m from e4
        ((1200.0, 0.0), (1600.0, 0.0), "Main Street", 3, True),    # e3 1200 m from e0, 400 m from e4
        ((1600.0, 0.0), (2000.0, 0.0), "Main St", 3, True),        # e4 count (same normalised name)
        ((400.0, 0.0), (400.0, 400.0), "Other Road", 3, True),     # e5 other street
        ((2000.0, 0.0), (3600.0, 0.0), "Main Street", 3, True),    # e6 far: midpoint 1000 m from e4's
    ])
    prop = br.propagate(E, _direct(E, {0: ("local", 1000.0), 4: ("local", 5000.0)}), 1000.0)
    src = prop["src_edge"].to_dict()
    assert src[1] == 0 and prop.at[1, "dist_m"] == pytest.approx(400.0)
    assert src[2] == 0          # tie 800 vs 800: lower source edge wins
    assert src[3] == 4          # 400 m from e4, 1200 m from e0
    assert src[6] == 4 and prop.at[6, "dist_m"] == pytest.approx(1000.0)
    assert 5 not in src         # different street
    prop500 = br.propagate(E, _direct(E, {0: ("local", 1000.0)}), 500.0)
    assert set(prop500.index) == {1}


def test_propagation_motorway_name_and_sh_bearing_rules() -> None:
    E = _edges([
        ((0.0, 0.0), (0.0, 500.0), "Southern Motorway", 0, False),     # e0 northbound, SH count
        ((0.0, 500.0), (0.0, 1000.0), "Southern Motorway", 0, False),  # e1 northbound
        ((0.0, 1000.0), (20.0, 800.0), "Southern Motorway", 0, False), # e2 southbound (opposite bearing)
        ((0.0, 0.0), (0.0, -400.0), "Southern Motorway Extension", 0, False),  # e3 same core, other name
        ((100.0, 0.0), (500.0, 0.0), "Great North Road", 2, True),     # e4 count
        ((500.0, 0.0), (900.0, 0.0), "Great North Rd", 2, True),       # e5 frc 2: same core is enough
        ((900.0, 0.0), (1300.0, 0.0), "Great North Rd", 1, True),      # e6 frc 1: needs the same streetName
    ])
    prop = br.propagate(E, _direct(E, {0: ("sh_cway", 60000.0), 4: ("local", 20000.0)}), 1000.0)
    src = prop["src_edge"].to_dict()
    assert src.get(1) == 0
    assert 2 not in src          # opposite carriageway
    assert 3 not in src          # frc 0 with another streetName
    assert src.get(5) == 4
    assert 6 not in src
    # a local (non-SH) count on the same carriageways has no bearing rule
    prop2 = br.propagate(E, _direct(E, {0: ("local", 60000.0)}), 1000.0)
    assert prop2["src_edge"].to_dict().get(2) == 0


def test_edge_values_sources_and_defaults() -> None:
    cfg = load_config()
    spec = [((i * 100.0, 0.0), ((i + 1) * 100.0, 0.0), "Main Street", 3, True) for i in range(6)]
    spec += [((0.0, 5000.0 + i * 100.0), (0.0, 5100.0 + i * 100.0), f"Road {i}", 3, True) for i in range(6)]
    spec += [((9000.0, 0.0), (9000.0, 100.0), "Lonely Lane", 4, True)]
    E = _edges(spec)
    C = _counts([{"road_name": f"ROAD {i} RD", "adt": 1000.0 * (i + 1), "x": 0.0, "y": 5050.0 + i * 100.0}
                 for i in range(6)] + [{"road_name": "MAIN ST", "adt": 7000.0, "x": 50.0, "y": 0.0}])
    _, em = br.match_counts(E, C, 30.0)
    vals, info = br.edge_values(E, C, em, cfg)
    assert vals.loc[0, "adt_source"] == "count" and vals.loc[0, "adt_twoway"] == 7000.0
    assert (vals.loc[1:5, "adt_source"] == "propagated").all() and (vals.loc[1:5, "adt_twoway"] == 7000.0).all()
    # frc 4 has no count edges -> overall median of the 7 count edges (1000..6000 and 7000) = 4000
    assert vals.loc[12, "adt_source"] == "default"
    assert vals.loc[12, "adt_twoway"] == 4000.0 and vals.loc[12, "adt_dir"] == 2000.0
    assert vals.loc[12, "peak_ratio"] == cfg.prep.road_peak_ratio_default
    assert info["defaults_by_band"] == {"3/50": 4000.0}


# --------------------------------------------------------------------------- sections


def test_sections_chain_by_origin_set_and_key() -> None:
    # tree: 0 -> 1 -> 2 -> 3 (origin 0), 4 -> 2 (origin 1), 5 -> 3 (origin 2)
    routes = {0: [0, 1, 2, 3], 1: [4, 2, 3], 2: [5, 3]}
    key = ["k"] * 6
    sections, osec = br.build_sections(routes, key)
    assert sections == [[0, 1], [2], [3], [4], [5]]
    assert osec == {0: [0, 1, 2], 1: [3, 1, 2], 2: [4, 2]}
    # a different count value on edge 1 splits the first chain
    key2 = ["k", "other", "k", "k", "k", "k"]
    sections2, osec2 = br.build_sections(routes, key2)
    assert sections2 == [[0], [1], [2], [3], [4], [5]]
    assert osec2[0] == [0, 1, 2, 3]
    # numbering follows origin_id order, not dict order
    s3, o3 = br.build_sections({2: [5, 3], 0: [0, 1, 2, 3], 1: [4, 2, 3]}, key)
    assert s3 == sections and o3 == osec


def test_sections_merge_long_shared_chain() -> None:
    # two origins join at node and share a three-edge chain to the gate
    routes = {0: [10, 11, 1, 2, 3], 1: [20, 1, 2, 3]}
    sections, osec = br.build_sections(routes, {e: 0 for e in (10, 11, 20, 1, 2, 3)})
    assert sections == [[10, 11], [1, 2, 3], [20]]
    assert osec == {0: [0, 1], 1: [2, 1]}


def test_chain_midpoint_respects_travel_direction() -> None:
    a = LineString([(0.0, 0.0), (100.0, 0.0)])
    b = LineString([(300.0, 0.0), (100.0, 0.0)])     # digitised against travel
    x, y = br.chain_midpoint([a, b], [(0.0, 0.0), (100.0, 0.0)])
    assert (x, y) == pytest.approx((150.0, 0.0))


# --------------------------------------------------------------------------- profile and speeds


def test_profile_interpolation() -> None:
    r = br.road_profile([1.0, 2.0], 360)
    assert len(r) == 1440
    assert r[0] == 0.15 and r[299] == 0.15 and r[300] == 0.15
    assert r[367] == pytest.approx(round(0.15 + 0.85 * 67 / 67.5, 6))
    assert r[368] == pytest.approx(round(1.0 + 0.5 / 15, 6))
    assert r[375] == 1.5
    assert r[383] == 2.0 and r[1439] == 2.0
    assert all(float(f"{x:.6f}") == x for x in r)
    rc = br.road_profile(load_config().prep.road_profile, 360)
    assert rc[480] == pytest.approx(0.93 + (1.01 - 0.93) * 0.5)   # between the 07:45 and 08:00 centres


def test_speed_factor_formula() -> None:
    assert float(br.speed_factor(100.0, 100.0, 0.15, 0.18)) == 1.0 / 1.15
    assert float(br.speed_factor(0.0, 100.0, 0.15, 0.18)) == 1.0
    assert float(br.speed_factor(1000.0, 100.0, 0.15, 0.18)) == 0.18
    x = 1.3
    assert float(br.speed_factor(130.0, 100.0, 0.15, 0.18)) == 1.0 / (1.0 + 0.15 * ((x * x) * (x * x)))


def test_speed_factor_breakdown_rule() -> None:
    # the engines' rule (cordonlite.roads.speed_factor): y = x / 0.9, at most the jam speed, at least the floor
    v = np.array([100.0, 100.0, 130.0, 300.0])
    broken = np.array([False, True, True, True])
    f = br.speed_factor(v, 100.0, 0.15, 0.18, broken, 1 - 0.1, 0.45)
    assert f.tolist() == [1.0 / 1.15, 0.45, 0.45, 0.18]
    y = 1.3 / (1 - 0.1)
    f = br.speed_factor(v, 100.0, 0.15, 0.18, broken, 1 - 0.1, 1.0)
    assert f[2] == 1.0 / (1.0 + 0.15 * ((y * y) * (y * y)))
    none = np.zeros(4, dtype=bool)
    assert br.speed_factor(v, 100.0, 0.15, 0.18).tolist() == br.speed_factor(v, 100.0, 0.15, 0.18, none, 0.9,
                                                                              0.45).tolist()


def test_usual_breakdown_windows_and_state() -> None:
    rule = br.MwyRule(True, 1.0, 0.95, 0.1, 0.45)
    r = np.zeros(1440)
    r[400:500] = np.linspace(0.5, 1.2, 100).round(6)
    r[500:] = 0.96
    r[600:] = 0.5
    obs, cap = np.array([1000.0, 1000.0, 400.0]), np.array([1000.0, 1000.0, 1000.0])
    mwy = np.array([1, 0, 1])
    broken, on, off = br.usual_breakdown(obs, cap, r, mwy, rule)
    first = int(np.flatnonzero(r >= 1.0)[0])
    assert on.tolist() == [first, -1, -1] and off.tolist() == [600, -1, -1]   # 0.96 holds it until 10:00
    assert broken[0].sum() == 600 - first and not broken[1:].any()
    b2, on2, off2 = br.usual_breakdown(obs, cap, r, mwy, br.MwyRule(False, 1.0, 0.95, 0.1, 0.45))
    assert not b2.any() and on2.tolist() == on.tolist() and off2.tolist() == off.tolist()
    F = br.usual_speed_table(obs, cap, r, 0.15, 0.18, broken, rule)
    assert F[0, first] == 0.45 and F[0, 599] == 0.45 and F[0, 600] == 1.0 / (1.0 + 0.15 * (0.25 * 0.25))
    assert np.array_equal(F[1:], br.usual_speed_table(obs, cap, r, 0.15, 0.18)[1:])


def test_class_tti_and_masked_probe() -> None:
    F = np.ones((2, 1440))
    F[1, :] = 0.5
    rm = np.array([[0, 1], [0, -1], [1, -1]])
    ff = np.array([1.0, 2.0])
    mask = np.array([False, True])
    el, el_m = br.probe_elapsed(rm, ff, F, [480, 481], mask)
    assert el.tolist() == [[5.0, 5.0], [1.0, 1.0], [4.0, 4.0]]
    assert el_m.tolist() == [[4.0, 4.0], [0.0, 0.0], [4.0, 4.0]]
    assert np.array_equal(el, br.probe_elapsed(rm, ff, F, [480, 481]))
    ff_all = br.route_ffsum(rm, ff)
    ff_m = br.route_ffsum(rm, np.where(mask, ff, 0.0))
    t = br.class_tti(el, el_m, ff_all, ff_m, np.array([1.0, 1.0, 2.0]))
    assert t["motorway"] == 2.0 and t["non_motorway"] == 1.0          # routes without the part are left out
    assert t["all"] == pytest.approx((5 / 3 + 1 + 2 * 2) / 4)


def test_probe_uses_the_entry_minute() -> None:
    F = np.ones((2, 1440))
    F[1, 482:] = 0.5
    rm = np.array([[0, 1], [1, -1]])
    ff = np.array([1.5, 2.0])
    el = br.probe_elapsed(rm, ff, F, [480, 481])
    assert el[0].tolist() == [3.5, 5.5]          # second section entered at 481 vs 482
    assert el[1].tolist() == [2.0, 2.0]
    assert br.route_ffsum(rm, ff).tolist() == [3.5, 2.0]


def test_k_bisection_hits_target_on_toy_network() -> None:
    cfg = load_config()
    r = br.road_profile(cfg.prep.road_profile, cfg.prep.road_profile_start_min)
    rm = np.array([[0, 1, 2], [3, 1, 2], [4, 2, -1]])
    ff = np.array([1.0, 0.5, 2.0, 1.5, 0.7])
    adt_dir = np.array([5000.0, 20000.0, 30000.0, 4000.0, 8000.0])
    obs = np.round(0.6 * np.array([0.096, 0.1, 0.09, 0.12, 0.096]) * 2 * adt_dir, 3)
    w = np.array([1.0, 2.0, 0.5])
    k, tti, hist = br.calibrate_k(rm, ff, w, obs, adt_dir, r, 0.15, 0.18, 1.5, (480, 540), (0.02, 0.3))
    assert 0.02 < k < 0.3
    assert tti == pytest.approx(1.5, abs=1e-4)
    # tti is the probe result at the rounded k
    cap = np.round(k * adt_dir, 3)
    el = br.probe_elapsed(rm, ff, br.usual_speed_table(obs, cap, r, 0.15, 0.18), range(480, 540))
    assert br.weighted_tti(el, br.route_ffsum(rm, ff), w) == tti
    assert len(hist) == br.K_ITERATIONS + 3
    with pytest.raises(ValueError, match="outside the bracket"):
        br.calibrate_k(rm, ff, w, obs, adt_dir, r, 0.15, 0.18, 9.0, (480, 540), (0.02, 0.3))
    # motorway breakdown on section 2; k matched on the non-motorway part of the trips
    mwy = np.array([0, 0, 1, 0, 0])
    rule = br.MwyRule(True, 1.0, 0.95, 0.1, 0.45)
    k2, tti2, _ = br.calibrate_k(rm, ff, w, obs, adt_dir, r, 0.15, 0.18, 1.5, (480, 540), (0.02, 0.3),
                                 mwy=mwy, rule=rule, exclude_mwy=True)
    cap = np.round(k2 * adt_dir, 3)
    broken = br.usual_breakdown(obs, cap, r, mwy, rule)[0]
    assert broken[2].any() and not broken[[0, 1, 3, 4]].any()
    el, el_m = br.probe_elapsed(rm, ff, br.usual_speed_table(obs, cap, r, 0.15, 0.18, broken, rule),
                                range(480, 540), mwy == 1)
    ffs, ffm = br.route_ffsum(rm, ff), br.route_ffsum(rm, np.where(mwy == 1, ff, 0.0))
    tt = br.class_tti(el, el_m, ffs, ffm, w)
    assert tt["non_motorway"] == tti2 == pytest.approx(1.5, abs=1e-4)
    assert tt["motorway"] > tt["non_motorway"] and k2 != k
    # the rule off and whole trips matched: the calibration of 2026-10-07
    k3, tti3, _ = br.calibrate_k(rm, ff, w, obs, adt_dir, r, 0.15, 0.18, 1.5, (480, 540), (0.02, 0.3),
                                 mwy=mwy, rule=br.MwyRule(False, 1.0, 0.95, 0.1, 0.45), exclude_mwy=False)
    assert (k3, tti3) == (k, tti)
    # SPEC4 A3: the capacity floor inside the calibration (sections 0 and 3 raised): k moves so the
    # target still holds with cap = round(k x max(adt_dir, floor), 3); the flows (obs) are unchanged
    adt_cap = br.capacity_adt([2, 2, 2, 2, 2], adt_dir, {2: 7000.0})
    assert adt_cap.tolist() == [7000.0, 20000.0, 30000.0, 7000.0, 8000.0]
    k4, tti4, _ = br.calibrate_k(rm, ff, w, obs, adt_cap, r, 0.15, 0.18, 1.5, (480, 540), (0.02, 0.3))
    assert k4 < k and tti4 == pytest.approx(1.5, abs=1e-4)
    el = br.probe_elapsed(rm, ff, br.usual_speed_table(obs, np.round(k4 * adt_cap, 3), r, 0.15, 0.18), range(480, 540))
    assert br.weighted_tti(el, br.route_ffsum(rm, ff), w) == tti4
    # the floor applied after a calibration without it would miss the target
    el = br.probe_elapsed(rm, ff, br.usual_speed_table(obs, np.round(k * adt_cap, 3), r, 0.15, 0.18), range(480, 540))
    assert br.weighted_tti(el, br.route_ffsum(rm, ff), w) < 1.5 - 1e-3


def test_adt_floors_by_road_class() -> None:
    """SPEC4 A3: adt_floor[frc] = the 5th percentile of adt_dir over the sections of that frc (unweighted,
    numpy's linear interpolation); capacity uses max(adt_dir, floor); pct 0 = no floor."""
    frc = [0, 0, 0, 0, 0, 3, 3, 3, 4, 3]
    adt = [100.0, 200.0, 300.0, 400.0, 500.0, 10.0, 1000.0, 1000.0, 50.0, 1000.0]
    fl = br.adt_floors(frc, adt, 5.0)
    # frc 0: position 0.05 x 4 = 0.2 -> 100 + 0.2 x 100; frc 3 (10, 1000, 1000, 1000): 0.15 -> 10 + 0.15 x 990
    assert fl == {0: 120.0, 3: 158.5, 4: 50.0}
    assert fl[3] == round(float(np.percentile([10.0, 1000.0, 1000.0, 1000.0], 5)), 3)
    assert br.capacity_adt(frc, adt, fl).tolist() == [120.0, 200.0, 300.0, 400.0, 500.0, 158.5, 1000.0, 1000.0,
                                                      50.0, 1000.0]
    assert br.adt_floors(frc, adt, 50.0)[0] == 300.0                    # the median
    assert br.adt_floors(frc, adt, 0.0) == {} and br.adt_floors(frc, adt, -1.0) == {}
    assert br.capacity_adt(frc, adt, {}).tolist() == adt
    assert br.capacity_adt(frc, adt, {0: 120.0}).tolist()[5] == 10.0    # a class without a floor
    with pytest.raises(ValueError, match="at most 100"):
        br.adt_floors(frc, adt, 101.0)
    assert load_config().prep.road_adt_floor_pct == 5.0


def test_no_site_motorway_text_lists_the_floor_raised_windows() -> None:
    """road_report.md Assumptions on the motorways without an NZTA site: capacity k x max(ADT, floor); those at
    k x ADT 'break down together' only when they share one window, and the sections whose capacity the
    road-class floor raised (SPEC4 A3: lower usual V/C) are counted with their own windows. Before, the
    report said that every motorway without a site keeps k x ADT and breaks down together."""
    cf = {"by_frc": {"0": {"adt_floor": 15000.0}, "2": {"adt_floor": 4000.0}}}
    sec = pd.DataFrame({"mwy": [1, 1, 1, 1, 1, 0, 1],
                        "adt_source": ["count", "default", "propagated", "count", "count", "count", "nzta"],
                        "frc": [0, 0, 0, 0, 2, 3, 0],
                        "adt_dir": [20000.0, 18000.0, 14000.0, 13000.0, 5000.0, 100.0, 9000.0],
                        "peak_ratio": [0.096] * 7,
                        "bd_on": [428, 428, 436, 443, 428, -1, 405], "bd_off": [601, 601, 580, 562, 601, -1, 660]})
    t = br.no_site_motorway_text(sec, cf, 0.096)
    assert t.startswith("; the others (motorways without a site, 5 sections) keep the default peak ratio 0.096 and "
                        "capacity k x max(ADT, the road-class floor): "), t
    assert "the 3 at k x ADT break down together (07:08-10:01)" in t
    assert ("the 2 whose capacity the floor raised have a lower V/C and their own, shorter windows: "
            "07:16-09:40 (1), 07:23-09:22 (1)") in t
    # none raised: no floor clause
    t2 = br.no_site_motorway_text(sec.iloc[[0, 1, 4]], cf, 0.096)
    assert "floor raised" not in t2 and "the 3 at k x ADT break down together (07:08-10:01)" in t2
    # different windows at k x ADT are listed, not 'together'; a count's own peak ratio is named
    s3 = sec.iloc[[0, 1]].assign(bd_on=[428, 430], bd_off=[601, 600], peak_ratio=[0.096, 0.12])
    t3 = br.no_site_motorway_text(s3, cf, 0.096)
    assert "together" not in t3 and "the 2 at k x ADT have the windows 07:08-10:01 (1), 07:10-10:00 (1)" in t3
    assert "keep their count's peak ratio or the default 0.096" in t3
    # a raised section that is not shorter than all those at k x ADT: no 'shorter'
    s4 = sec.iloc[[0, 2]].assign(bd_on=[440, 436], bd_off=[560, 580])
    assert "their own windows: 07:16-09:40 (1)" in br.no_site_motorway_text(s4, cf, 0.096)
    assert br.no_site_motorway_text(sec[sec["adt_source"] == "nzta"], cf, 0.096) == ""


# --------------------------------------------------------------------------- NZTA motorway counts (SPEC3)

QH = [300 + 15 * i for i in range(24)]          # quarter hours 05:00 .. 10:45
# relative flow by quarter hour of three toy sites (SPEC3 1):
#   breakdown: maximum 06:15, a plateau about 0.78 until 09:30 with a dip at 07:30-07:45, recovery 09:45
#   saturated: within 5% of the maximum (08:00) from 06:15 to 09:15, the bottleneck itself (delta < 0.05)
#   late: a demand peak at 08:00 and no plateau (SH20)
REL = {
    "breakdown": [0.25, 0.40, 0.65, 0.90, 0.98, 1.00, 0.92, 0.80, 0.78, 0.77, 0.70, 0.70, 0.78, 0.79, 0.80,
                  0.80, 0.79, 0.81, 0.82, 0.72, 0.65, 0.62, 0.60, 0.58],
    "saturated": [0.20, 0.32, 0.50, 0.70, 0.86, 0.97, 0.98, 0.98, 0.97, 0.99, 0.98, 0.99, 1.00, 0.99, 0.99,
                  0.98, 0.97, 0.96, 0.93, 0.88, 0.82, 0.80, 0.79, 0.78],
    "late": [0.20, 0.27, 0.38, 0.47, 0.58, 0.70, 0.81, 0.81, 0.85, 0.91, 0.96, 0.97, 1.00, 0.99, 0.97, 0.90,
             0.84, 0.81, 0.80, 0.80, 0.77, 0.77, 0.77, 0.77],
}


def _weekdays(first: str, last: str) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(first, last)]


DAYS_2024 = _weekdays("2024-05-01", "2024-05-31") + _weekdays("2024-08-01", "2024-08-31") + \
    _weekdays("2024-11-01", "2024-11-30")
DAYS_2526 = _weekdays("2025-10-01", "2025-12-17")


def _toy_nzta(data_dir: Path, sites: list[dict]) -> None:
    """data_dir/nzta in the prep/fetch_nzta.py format. Each site dict: site_ref, corridor, x, y, rel
    (24 relative flows), peak (veh/h at rel 1) and optionally kind, cbd_role, n_days (2024 days kept),
    doubled (2024 months whose counts are doubled), outage (2024 dates without lane 2), growth (2025-26
    daily volume / 2024). Two lanes, light and heavy; a full day is 3 x the 05:00-11:00 counts."""
    d = data_dir / "nzta"
    d.mkdir(parents=True, exist_ok=True)
    srows, am, qd, dl = [], [], [], []
    for s in sites:
        ref, fd = s["site_ref"], 2
        srows.append({"site_ref": ref, "description": f"toy {ref}", "corridor": s["corridor"], "direction": "NB",
                      "flow_direction": fd, "kind": s.get("kind", "mainline"), "cbd_bound": 1,
                      "cbd_role": s.get("cbd_role", "CBD-bound"), "lanes": 2, "lat": -36.9, "lon": 174.8,
                      "x_nztm": s["x"], "y_nztm": s["y"], "note": ""})
        per_qh = [int(round(s["peak"] / 4.0 * r)) for r in s["rel"]]
        cells = []                                   # (time, lane, class, count) of one normal day
        for t, tot in zip(QH, per_qh):
            for lane, n in ((1, tot // 2), (2, tot - tot // 2)):
                heavy = n // 10
                hm = f"{t // 60:02d}:{t % 60:02d}"
                cells += [(hm, lane, "heavy", heavy), (hm, lane, "light", n - heavy)]
        day_sum = {}
        for _t, lane, cl, n in cells:
            day_sum[(lane, cl)] = day_sum.get((lane, cl), 0) + n
        for date in DAYS_2024[:s.get("n_days", len(DAYS_2024))]:
            mult = 2 if date[:7] in s.get("doubled", ()) else 1
            lanes = (1,) if date in s.get("outage", ()) else (1, 2)
            am += [(ref, date, t, fd, lane, cl, mult * n) for t, lane, cl, n in cells if lane in lanes]
            qd += [(ref, date, fd, lane, cl, mult * 3 * n, 96) for (lane, cl), n in sorted(day_sum.items())
                   if lane in lanes]
        for date in DAYS_2526:
            dl += [(ref, date, fd, lane, cl, float(round(s.get("growth", 1.02) * 3 * n)))
                   for (lane, cl), n in sorted(day_sum.items())]
    pd.DataFrame(srows).to_csv(d / br.NZTA_SITES_FILE, index=False)
    pd.DataFrame(am, columns=["site_ref", "local_date", "time", "flow_direction", "lane", "class", "count"]).to_csv(
        d / br.NZTA_AM_FILE, index=False)
    pd.DataFrame(qd, columns=["site_ref", "local_date", "flow_direction", "lane", "class", "count", "n_qh"]).to_csv(
        d / br.NZTA_QH_DAILY_FILE, index=False)
    pd.DataFrame(dl, columns=["site_ref", "local_date", "flow_direction", "lane", "class", "count"]).to_csv(
        d / br.NZTA_DAILY_FILE, index=False)


def test_site_breakdown_rule_cases() -> None:
    q = {k: [4000.0 * r for r in v] for k, v in REL.items()}
    # breakdown: delta = 1 - median(06:45..09:15) / q_max; onset at the first bin <= q_max (1 - delta / 2)
    b = br.site_breakdown(q["breakdown"], 0.10)
    pl = np.median([q["breakdown"][i] for i in range(24) if 405 <= QH[i] < 570])
    assert b["t_max"] == 375 and b["q_plateau"] == round(float(pl), 3)
    assert b["delta"] == round(1 - pl / 4000.0, 6) and b["delta"] >= 0.05 and not b["saturated"]
    assert b["breakdown"] and b["bd_on"] == 405 and b["cap_drop"] == b["delta"]
    # recovery from 09:30 on: two quarter hours below 0.95 x plateau from 09:45
    assert b["bd_off"] == 585 and b["recovered"] and b["recovery_by"] == "fall"
    lit = br.site_breakdown(q["breakdown"], 0.10, None, None, None)   # literal rule: the dip at 07:30 ends it
    assert lit["breakdown"] and (lit["bd_on"], lit["bd_off"]) == (405, 450)
    # saturated: the drop cannot be measured at the bottleneck, so cap_drop = the global drop
    s = br.site_breakdown(q["saturated"], 0.10)
    assert s["saturated"] and s["sat_start"] == 375 and s["sat_min"] == 195 and s["delta"] < 0.05
    assert s["breakdown"] and s["bd_on"] == 375 and s["cap_drop"] == 0.10
    assert br.site_breakdown(q["saturated"], 0.02)["cap_drop"] == s["delta"]   # max(delta, global)
    assert s["bd_off"] == 585          # q_pl = median(08:30..09:15); first two bins below 0.95 of it
    # late demand peak: no breakdown (no plateau of two hours before 09:30); the literal rule calls the
    # end of the peak a breakdown
    n = br.site_breakdown(q["late"], 0.10)
    assert not n["breakdown"] and (n["bd_on"], n["bd_off"]) == (-1, -1) and n["cap_drop"] == 0.10
    assert n["t_max"] == 480 and n["delta"] >= 0.05 and n["recovery_by"] is None
    assert br.site_breakdown(q["late"], 0.10, None, None, None)["breakdown"]
    # never back below the plateau within the data: bd_off = 11:00, not recovered
    flat = q["breakdown"][:19] + [q["breakdown"][18]] * 5
    f = br.site_breakdown(flat, 0.10)
    assert f["breakdown"] and f["bd_off"] == 660 and f["recovered"] is False and f["recovery_by"] is None


def test_site_breakdown_recovery_when_flow_rises_back() -> None:
    """SPEC4 A1: a jam also ends when the downstream bottleneck clears and throughput rises back towards
    the pre-breakdown maximum: from 09:30, two consecutive quarter hours each below 0.95 x plateau or
    above plateau + (q_max - plateau) / 2 (Tristram, 01N10417)."""
    base = [4000.0 * r for r in REL["breakdown"]]           # q_max 4000 at 06:15, plateau 0.79 x 4000
    b0 = br.site_breakdown(base, 0.10)
    q_pl = b0["q_plateau"]
    hi = q_pl + 0.5 * (4000.0 - q_pl)
    assert q_pl == 3160.0 and hi == 3580.0 and b0["rise_level"] == 3580.0

    def with_tail(tail: list[float]) -> list[float]:      # flows from 09:30 (bin 18) to 10:45
        return base[:18] + tail

    plateau = [q_pl] * 6
    # flow back up from 09:30: recovery at 09:30 by the rise; the fall rule alone never ends it
    up = with_tail([3700.0, 3720.0, 3800.0, 3760.0, 3720.0, 3700.0])
    r = br.site_breakdown(up, 0.10)
    assert (r["bd_on"], r["bd_off"], r["recovered"], r["recovery_by"]) == (405, 570, True, "rise")
    f = br.site_breakdown(up, 0.10, recover_rise=None)
    assert f["bd_off"] == 660 and f["recovered"] is False
    assert {k: v for k, v in f.items() if k not in ("bd_off", "recovered", "recovery_by", "rise_level")} == \
        {k: v for k, v in r.items() if k not in ("bd_off", "recovered", "recovery_by", "rise_level")}
    # the rise starts at 10:00: recovery at 10:00
    assert br.site_breakdown(with_tail([q_pl, q_pl, 3700.0, 3700.0, 3700.0, 3700.0]), 0.10)["bd_off"] == 600
    # one bin above, then back on the plateau: not two consecutive bins, no recovery
    one = br.site_breakdown(with_tail([3700.0, q_pl, 3700.0, q_pl, 3700.0, q_pl]), 0.10)
    assert one["bd_off"] == 660 and one["recovered"] is False
    # strictly above the level: at the level is still the jam
    assert br.site_breakdown(with_tail([hi] * 6), 0.10)["bd_off"] == 660
    assert br.site_breakdown(with_tail([hi + 0.001] * 6), 0.10)["bd_off"] == 570
    # one bin above and the next below 0.95 x plateau: also two bins outside the jam band
    mixed = br.site_breakdown(with_tail([3700.0, 2900.0] + plateau[:4]), 0.10)
    assert (mixed["bd_off"], mixed["recovery_by"]) == (570, "mixed")
    # a rise inside the plateau (before 09:30) does not end the window
    early = base[:14] + [3700.0, 3700.0] + base[16:18] + plateau
    e = br.site_breakdown(early, 0.10)
    assert e["q_plateau"] == q_pl and e["bd_off"] == 660
    # the literal SPEC3 rule (no amendments) does not use the rise either
    assert br.site_breakdown(up, 0.10, None, None, None)["bd_off"] == 450
    # a site without breakdown has no recovery
    assert br.site_breakdown([4000.0 * x for x in REL["late"]], 0.10)["rise_level"] is None


def test_site_profile_centres_and_shoulders() -> None:
    cfg = load_config()
    vals, start = cfg.prep.road_profile, cfg.prep.road_profile_start_min
    rb = [0.3 + 0.03 * i for i in range(24)]
    r = br.site_profile(rb, vals, start)
    assert len(r) == 1440 and all(float(f"{x:.6f}") == x for x in r)
    # linear between the bin centres 05:07.5, 05:22.5, ...: minute 315 is a third of the way
    assert r[315] == round(rb[0] + (rb[1] - rb[0]) * 7.5 / 15, 6)
    assert r[652] == round(rb[22] + (rb[23] - rb[22]) * 14.5 / 15, 6)
    # outside: the default profile scaled to match at the ends (default is 0.6 after 10:22.5)
    assert r[653] == r[1439] == round(rb[23], 6)
    r0 = br.road_profile(vals, start)
    a_lo = rb[0] / br._default_profile_at(vals, start, 307.5)
    assert r[100] == round(a_lo * r0[100], 6) and r[306] == round(a_lo * br._default_profile_at(vals, start, 306), 6)


def test_nzta_lane_days_flags_outages() -> None:
    rows = []
    for k, date in enumerate(_weekdays("2024-08-01", "2024-08-20")):
        for lane, n in ((1, 1000), (2, 900), (3, 50)):            # lane 3 only on two days: not a core lane
            if lane == 3 and k > 1:
                continue
            if lane == 2 and k == 4:
                n = 100                                            # below 0.3 x its median
            if not (lane == 1 and k == 6):                         # lane 1 missing on day 6
                rows.append(("S", date, 2, lane, "light", float(n)))
    df = pd.DataFrame(rows, columns=["site_ref", "local_date", "flow_direction", "lane", "class", "count"])
    out = br.nzta_lane_days(df)
    assert len(out) == 14 and out["low_lane"].tolist() == [k in (4, 6) for k in range(14)]
    assert out["total"].iloc[0] == 1950.0 and out["total"].iloc[2] == 1900.0


def _site(ref: str, corridor: str, kind_rel: str, x: float, y: float, **kw: object) -> dict:
    return {"site_ref": ref, "corridor": corridor, "rel": REL[kind_rel], "peak": 4000.0, "x": x, "y": y, **kw}


def test_toy_nzta_site_table(toy_nzta: dict) -> None:
    sites = toy_nzta["res1"]["sites"].set_index("site_ref")
    assert sites["valid"].tolist() == [True, True, True, False]
    assert sites.loc["T4", "reason"].startswith("10 valid 2024 weekdays")
    # the doubled May of T1 is flagged and left out; one outage day of T2 is not used
    assert sites.loc["T1", "level_flagged"].startswith("2024-05 (x1.9") and sites.loc["T1", "valid_2024"] == 43
    assert sites.loc["T2", "valid_2024"] == 65 and sites.loc["T3", "valid_2024"] == 66
    q = toy_nzta["res1"]["site_q"]
    cfg = toy_nzta["cfg"]
    for ref, rel in (("T1", "breakdown"), ("T2", "saturated"), ("T3", "late")):
        exp = [4 * int(round(1000.0 * r)) for r in REL[rel]]
        assert q[ref].tolist() == exp
        b = br.site_breakdown(exp, cfg.road.mwy_capacity_drop)
        t = sites.loc[ref]
        assert (bool(t["breakdown"]), int(t["bd_on"]), int(t["bd_off"]), float(t["cap_drop"])) == (
            b["breakdown"], b["bd_on"], b["bd_off"], b["cap_drop"])
        assert t["cap_vph"] == round(max(exp) * t["scale"], 3)
        assert t["scale"] == pytest.approx(1.02, abs=2e-3) and t["scale_source"] == "site"
    assert sites.loc["T1", "breakdown"] and sites.loc["T2", "saturated"] and not sites.loc["T3", "breakdown"]
    assert sites["profile_id"].tolist() == [1, 2, 3, -1]


def test_toy_nzta_sections(toy_nzta: dict) -> None:
    res, cfg = toy_nzta["res1"], toy_nzta["cfg"]
    sec = pd.read_csv(toy_nzta["out1"] / "road_sections.csv", float_precision="round_trip")
    assert tuple(sec.columns) == br.SECTIONS_COLUMNS
    sites = res["sites"].set_index("site_ref")
    m = sec[sec["mwy"] == 1]
    nz = sec[sec["adt_source"] == "nzta"]
    assert set(nz["section_id"]) == set(m["section_id"]) and len(nz) > 0
    # each motorway section takes the nearest used site (T4 is not used)
    for t in nz.itertuples():
        d = {ref: math.hypot(sites.loc[ref, "x_nztm"] - t.x_mid, sites.loc[ref, "y_nztm"] - t.y_mid)
             for ref in ("T1", "T2", "T3")}
        s = sites.loc[min(d, key=d.get)]
        assert (t.profile_id, t.cap_vph, t.obs_peak_vph, t.bd_on, t.bd_off, t.cap_drop) == (
            s["profile_id"], s["cap_vph"], s["obs_peak_vph"], s["bd_on"], s["bd_off"], s["cap_drop"])
        r = res["profiles"][int(t.profile_id)]
        am = round(t.obs_peak_vph * sum(float(r[k]) for k in range(360, 600)) / 60.0, 3)
        assert t.am_volume_veh == am and t.bg_peak_vph == pytest.approx(t.obs_peak_vph * (1 - t.phi), abs=2e-3)
        assert t.phi == round(min(1.0, t.expected_commuter_veh / am), 6)
    assert set(nz["profile_id"]) == {1, 2, 3}
    assert set(zip(nz.loc[nz["profile_id"] == 3, "bd_on"], nz.loc[nz["profile_id"] == 3, "bd_off"])) == {(-1, -1)}
    # other sections: profile 0, the global drop, k x ADT
    other = sec[sec["adt_source"] != "nzta"]
    assert (other["profile_id"] == 0).all() and (other["cap_drop"] == cfg.road.mwy_capacity_drop).all()
    adt_cap = br.capacity_adt(sec["frc"], sec["adt_dir"], res["floors"])[(sec["adt_source"] != "nzta").to_numpy()]
    assert np.allclose(other["cap_vph"], np.round(res["meta"]["k"] * adt_cap, 3))
    # sites' windows: the rule with the rise [SPEC4]; meta records the window by a fall alone
    for d in res["meta"]["nzta"]["sites"]:
        if d["valid"]:
            assert "window_fall_only" in d and "recovery_by" in d and "rise_level" in d
    md = res["meta"]["nzta"]["mapping_dist_m"]
    assert md["all"]["n"] == len(nz) and md["SH1_south"]["n"] == len(nz)
    assert md["all"]["max"] == max(res["meta"]["nzta"]["dist_m_by_section"].values())
    assert sorted(int(s) for s in res["meta"]["nzta"]["dist_m_by_section"]) == sorted(nz["section_id"])
    far = res["meta"]["nzta"]["farthest_sections"]
    assert [d["dist_m"] for d in far] == sorted((d["dist_m"] for d in far), reverse=True)
    assert len(far) == min(br.NZTA_FARTHEST_N, len(nz))
    # long road_profile.csv: profile 0 (the default) and one per used site
    prof = pd.read_csv(toy_nzta["out1"] / "road_profile.csv", float_precision="round_trip")
    assert list(prof.columns) == list(br.PROFILE_COLUMNS) and sorted(set(prof["profile_id"])) == [0, 1, 2, 3]
    assert np.array_equal(prof.loc[prof["profile_id"] == 0, "r"].to_numpy(),
                          br.road_profile(cfg.prep.road_profile, cfg.prep.road_profile_start_min))
    meta = res["meta"]["nzta"]
    assert meta["n_valid"] == 3 and meta["n_breakdown"] == 2 and meta["n_sections_nzta"] == len(nz)
    assert meta["mapping"]["Southern Motorway"]["mapped"] == len(nz)
    report = (toy_nzta["out1"] / "road_report.md").read_text()
    assert "## NZTA motorway counts" in report and "CC BY 4.0" in report
    # the run's scenario reads it: several profiles, per-section drops
    from cordonlite import roads as R
    assert R.read_profiles(prof).keys() == {0, 1, 2, 3}
    # rerun byte-identical
    for f in br.OUTPUT_FILES:
        assert (toy_nzta["out1"] / f).read_bytes() == (toy_nzta["out2"] / f).read_bytes(), f


def test_map_sections_needs_every_motorway_name() -> None:
    sec = pd.DataFrame({"mwy": [1, 1, 0], "street_name": ["Southern Motorway", "Mystery Motorway", "Queen Street"],
                        "x_mid": [0.0, 0.0, 0.0], "y_mid": [0.0, 0.0, 0.0]})
    sites = pd.DataFrame({"site_ref": ["A"], "corridor": ["SH1_south"], "valid": [True], "x_nztm": [100.0],
                          "y_nztm": [0.0]})
    with pytest.raises(ValueError, match="Mystery Motorway"):
        br.map_sections_to_sites(sec, sites)
    sec.loc[1, "street_name"] = "Upper Harbour Motorway"                 # mapped to no corridor
    mp = br.map_sections_to_sites(sec, sites)
    assert mp["site_ref"].tolist() == ["A", "", ""] and mp["corridor"].tolist() == ["SH1_south", "", ""]
    assert mp["dist_m"].iloc[0] == 100.0
    # SPEC4: at any distance by default; the SPEC3 limit (max_m) still works
    assert br.NZTA_MAP_M is None
    far = br.map_sections_to_sites(sec.assign(x_mid=7000.0), sites)
    assert far["site_ref"].tolist() == ["A", "", ""] and far["dist_m"].iloc[0] == 6900.0
    far6 = br.map_sections_to_sites(sec.assign(x_mid=7000.0), sites, max_m=6000.0)
    assert far6["site_ref"].tolist() == ["", "", ""] and far6["corridor"].iloc[0] == "SH1_south"


def test_map_sections_any_distance_same_corridor_only() -> None:
    """SPEC4 A2: every motorway mainline section of a corridor with valid sites takes the nearest valid
    site of the SAME corridor at any distance; corridors without valid sites, motorways without a
    corridor and non-motorway sections take none."""
    sec = pd.DataFrame({
        "mwy": [1, 1, 1, 1, 1, 0, 1],
        "street_name": ["Southern Motorway", "Southern Motorway", "Northern Motorway", "Southwestern Motorway",
                        "Upper Harbour Motorway", "Southern Motorway", "Southern Motorway"],
        "x_mid": [7000.0, 20000.0, 0.0, 49000.0, 100.0, 0.0, 9550.0],
        "y_mid": [0.0] * 7})
    sites = pd.DataFrame({
        "site_ref": ["A", "B", "C", "D", "E"],
        "corridor": ["SH1_south", "SH1_north", "SH1_south", "SH20", "SH1_south"],
        "valid": [True, True, True, False, False],          # D: the only SH20 site, not used; E: not used
        "x_nztm": [100.0, 30000.0, 19000.0, 50000.0, 7000.0], "y_nztm": [0.0] * 5})
    mp = br.map_sections_to_sites(sec, sites)
    # section 0: E (0 m) is not used, so A (6.9 km) although beyond the SPEC3 limit; section 2: B of its
    # own corridor at 30 km although A is 100 m away; section 6: tie A / C at 9450 m -> the first (A)
    assert mp["site_ref"].tolist() == ["A", "C", "B", "", "", "", "A"]
    assert mp["dist_m"].tolist()[:3] == [6900.0, 1000.0, 30000.0] and mp["dist_m"].iloc[6] == 9450.0
    assert mp["dist_m"].iloc[3:6].isna().all()
    assert mp["corridor"].tolist() == ["SH1_south", "SH1_south", "SH1_north", "SH20", "", "", "SH1_south"]
    lim = br.map_sections_to_sites(sec, sites, max_m=6000.0)       # SPEC3: within 6 km only
    assert lim["site_ref"].tolist() == ["", "C", "", "", "", "", ""]


# --------------------------------------------------------------------------- end to end on a toy network


X0, Y0 = 1757000.0, 5920000.0     # toy network in NZTM near Auckland so the count file can be WGS84


def _toy_inputs(tmp: Path, nzta_sites: list[dict] | None = None, extra_counts: list[dict] | None = None) -> dict:
    """Toy roads shapefile, cordon gpkg, count geojson, NZTA count files and config overrides;
    origins.csv built by the prep. Without nzta_sites the NZTA sites count SH20, which has no toy
    motorway, so every section keeps the k x ADT rule. extra_counts: more count points (road_name,
    adt, x, y in NZTM, optional peaktraffic, peak_hour, count_date)."""
    cordon = box(X0, Y0, X0 + 1000.0, Y0 + 1000.0)
    rows: list[tuple] = []

    def add(pts, name, frc, spd, both=True):
        for a, b in zip(pts[:-1], pts[1:]):
            for u, v in ((a, b), (b, a)) if both else ((a, b),):
                g = LineString([u, v])
                rows.append((f"{'-' if (u, v) != (a, b) else ''}{name[:3]}{len(rows)}", spd, frc, name, g.length, g))

    cx, cy = X0 + 500.0, Y0 + 500.0
    add([(X0 - 4000.0 + 500.0 * i, cy) for i in range(10)], "Great North Road", 2, 50)        # west arterial
    # one-way motorway; TomTom gives its "bridge" (y -1500 .. -1000) frc 2 and 80 km/h: a motorway by name
    mwy_pts = [(cx, Y0 - 4000.0 + 500.0 * i) for i in range(10)]
    add(mwy_pts[:6], "Southern Motorway", 0, 100, both=False)
    add(mwy_pts[5:7], "Southern Motorway", 2, 80, both=False)
    add(mwy_pts[6:], "Southern Motorway", 0, 100, both=False)
    for i in range(1, 8):                                                                       # local streets
        add([(X0 - 4000.0 + 500.0 * i, cy), (X0 - 4000.0 + 500.0 * i, cy + 400.0)], f"Side Street {i}", 4, 50)
        add([(cx, Y0 - 4000.0 + 500.0 * i), (cx + 400.0, Y0 - 4000.0 + 500.0 * i)], f"Lane {i}", 3, 50)
    roads = gpd.GeoDataFrame({"segment_id": [r[0] for r in rows], "speedLimit": [r[1] for r in rows],
                              "frc": [r[2] for r in rows], "streetName": [r[3] for r in rows],
                              "distance": [r[4] for r in rows]}, geometry=[r[5] for r in rows], crs="EPSG:2193")
    roads_path = tmp / "roads.shp"
    roads.to_file(roads_path)
    cordon_path = tmp / "sa3.gpkg"
    gpd.GeoDataFrame({"SA32025_V1_00_NAME": ["Auckland City Centre"]}, geometry=[cordon],
                     crs="EPSG:2193").to_file(cordon_path, driver="GPKG")
    ex = extra_counts or []
    pts = gpd.GeoDataFrame({
        "OBJECTID": list(range(1, 5 + len(ex))),
        "road_name": ["GREAT NORTH RD", "SH 01N-0427-I", "SIDE STREET 3", "GREAT NORTH RD"] + [c["road_name"] for c in ex],
        "adt": [20000.0, 50000.0, 800.0, 0.0] + [float(c["adt"]) for c in ex],
        "peaktraffic": [2000.0, np.nan, 90.0, 10.0] + [c.get("peaktraffic", np.nan) for c in ex],
        "peak_hour": ["08:00", None, "1700", "800"] + [c.get("peak_hour") for c in ex],
        "count_date": ["2022-05-01", "2016-12-28", "2019-03-01", "2023-01-01"] + [c.get("count_date", "2024-01-01")
                                                                               for c in ex],
    }, geometry=gpd.points_from_xy([X0 - 2250.0, cx + 3.0, X0 - 2500.0 + 3.0, X0 - 1250.0] + [c["x"] for c in ex],
                                   [cy + 4.0, Y0 - 2250.0, cy + 200.0, cy] + [c["y"] for c in ex]),
       crs="EPSG:2193").to_crs(4326)
    adt_path = tmp / "adt.geojson"
    pts.to_file(adt_path, driver="GeoJSON")
    data = tmp / "data"
    data.mkdir()
    if nzta_sites is None:
        nzta_sites = [_site("Z1", "SH20", "late", cx + 30.0, Y0 - 2000.0),
                      _site("Z2", "SH20", "breakdown", cx + 30.0, Y0 - 500.0)]
    _toy_nzta(data, nzta_sites)
    overrides = {"prep.roads_shp": str(roads_path), "prep.cordon_gpkg": str(cordon_path),
                 "prep.adt_geojson": str(adt_path), "run.data_dir": str(data),
                 "prep.n_origin_points": 6, "prep.n_corridors": 2, "prep.density_radius_m": 600.0,
                 "prep.od_csv": "", "prep.origin_draw": "unique"}   # the toy network has no SA2s: proxy weights
    cfg = load_config(overrides=overrides)
    roads_l = br.load_roads_shp(cfg)
    cordon_g, _ = br.load_cordon_any(cfg)
    br.reproduce_prep(cfg, roads_l, cordon_g)["origins_frame"].to_csv(data / "origins.csv", index=False)
    return {"cfg": cfg, "data": data}


@pytest.fixture(scope="module")
def toy(tmp_path_factory: pytest.TempPathFactory) -> dict:
    tmp = tmp_path_factory.mktemp("roads")
    t = _toy_inputs(tmp)
    t["res1"] = br.run_build_roads(t["cfg"], tmp / "out1")
    t["res2"] = br.run_build_roads(t["cfg"], tmp / "out2")
    t["out1"], t["out2"] = tmp / "out1", tmp / "out2"
    return t


@pytest.fixture(scope="module")
def toy_nzta(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """The toy network with four SH1_south NZTA sites along its Southern Motorway: T1 breakdown (its
    May counts doubled), T2 saturated (one lane outage day), T3 a late peak without breakdown, T4 with
    only 10 days (not used)."""
    tmp = tmp_path_factory.mktemp("roads_nzta")
    cx = X0 + 500.0
    t = _toy_inputs(tmp, [
        _site("T1", "SH1_south", "breakdown", cx + 30.0, Y0 - 2300.0, doubled=("2024-05",)),
        _site("T2", "SH1_south", "saturated", cx + 30.0, Y0 - 300.0, outage=("2024-08-07",)),
        _site("T3", "SH1_south", "late", cx + 30.0, Y0 - 1700.0),
        _site("T4", "SH1_south", "breakdown", cx + 30.0, Y0 - 1000.0, n_days=10),
    ])
    t["res1"] = br.run_build_roads(t["cfg"], tmp / "out1")
    t["res2"] = br.run_build_roads(t["cfg"], tmp / "out2")
    t["out1"], t["out2"] = tmp / "out1", tmp / "out2"
    return t


@pytest.fixture(scope="module")
def toy_floor(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """The toy_nzta network with one more, tiny count on Great North Road near the cordon (ADT 60, so
    adt_dir 30: a section far below the others of frc 2) and a small site T2 (800 veh/h, so its measured
    capacity is below k x the frc-0 floor), built with the default capacity floor (5th percentile) into
    out1 and out2 and without it (prep.road_adt_floor_pct = 0) into out0."""
    tmp = tmp_path_factory.mktemp("roads_floor")
    cx, cy = X0 + 500.0, Y0 + 500.0
    t = _toy_inputs(tmp, [
        _site("T1", "SH1_south", "breakdown", cx + 30.0, Y0 - 2300.0, doubled=("2024-05",)),
        {**_site("T2", "SH1_south", "saturated", cx + 30.0, Y0 - 300.0, outage=("2024-08-07",)), "peak": 800.0},
        _site("T3", "SH1_south", "late", cx + 30.0, Y0 - 1700.0),
        _site("T4", "SH1_south", "breakdown", cx + 30.0, Y0 - 1000.0, n_days=10),
    ], extra_counts=[{"road_name": "GREAT NORTH RD", "adt": 60.0, "x": X0 - 250.0, "y": cy + 3.0}])
    t["res1"] = br.run_build_roads(t["cfg"], tmp / "out1")
    t["res2"] = br.run_build_roads(t["cfg"], tmp / "out2")
    cfg0 = load_config(overrides={**_overrides_of(t["cfg"]), "run.data_dir": str(t["data"]),
                                  "prep.road_adt_floor_pct": 0.0})
    t["res0"] = br.run_build_roads(cfg0, tmp / "out0")
    t["out0"], t["out1"], t["out2"] = tmp / "out0", tmp / "out1", tmp / "out2"
    return t


def test_toy_capacity_floor(toy_floor: dict) -> None:
    """SPEC4 A3 end to end: cap_vph = round(k x max(adt_dir, floor[frc]), 3) on the k x ADT sections with
    floor = the 5th percentile of adt_dir of the frc over all sections; NZTA sections keep their measured
    capacity; the flows stay from the counts; k is calibrated with the floor; meta and report record it."""
    t = toy_floor
    sec = pd.read_csv(t["out1"] / "road_sections.csv", float_precision="round_trip")
    sec0 = pd.read_csv(t["out0"] / "road_sections.csv", float_precision="round_trip")
    m, m0 = t["res1"]["meta"], t["res0"]["meta"]
    fl = br.adt_floors(sec["frc"], sec["adt_dir"], 5.0)
    assert fl == t["res1"]["floors"] and fl == {int(c): v["adt_floor"] for c, v in m["capacity_floor"]["by_frc"].items()}
    assert m["road_adt_floor_pct"] == 5.0 and m["capacity_floor"]["pct"] == 5.0
    site = (sec["adt_source"] == "nzta").to_numpy()
    adt_cap = br.capacity_adt(sec["frc"], sec["adt_dir"], fl)
    assert (sec.loc[~site, "cap_vph"].to_numpy() == np.round(m["k"] * adt_cap[~site], 3)).all()
    raised = (adt_cap > sec["adt_dir"].to_numpy()) & ~site
    assert raised.sum() >= 1 and m["capacity_floor"]["n_raised"] == int(raised.sum())
    low = sec.loc[raised]
    assert set(low["street_name"]) == {"Great North Road"} and (low["adt_dir"] == 30.0).all()
    assert (low["cap_vph"] == round(m["k"] * fl[2], 3)).all() and fl[2] > 30.0
    assert m["capacity_floor"]["by_frc"]["2"]["n_raised"] == int(raised.sum())
    assert m["capacity_floor"]["by_frc"]["2"]["cap_floor_vph"] == round(m["k"] * fl[2], 3)
    assert 0 < m["capacity_floor"]["minutes_share_raised"] < 1
    # NZTA sections: the measured capacity, with or without the floor, also below k x the floor
    assert site.any() and (sec.loc[site, "cap_vph"].to_numpy() == sec0.loc[site, "cap_vph"].to_numpy()).all()
    sites = t["res1"]["sites"].set_index("site_ref")
    small = sec[site & (sec["profile_id"] == int(sites.loc["T2", "profile_id"]))]
    assert len(small) > 0 and (small["cap_vph"] == sites.loc["T2", "cap_vph"]).all()
    assert (small["cap_vph"] < m["k"] * small["frc"].map(fl)).all()
    # the floor sets capacity only: flows and commuter weights are those of the run without it
    for c in ("adt_twoway", "adt_dir", "obs_peak_vph", "am_volume_veh", "expected_commuter_veh", "phi", "bg_peak_vph",
              "w_factor", "profile_id", "cap_drop"):
        assert sec[c].tolist() == sec0[c].tolist(), c
    # without the floor: cap = k x adt_dir, no section raised, another k; both meet the TTI target
    assert m0["capacity_floor"]["by_frc"] == {} and m0["capacity_floor"]["n_raised"] == 0
    assert (sec0.loc[~site, "cap_vph"].to_numpy() == np.round(m0["k"] * sec0.loc[~site, "adt_dir"].to_numpy(), 3)).all()
    assert m["k"] < m0["k"]
    for mm in (m, m0):
        assert mm["tti_achieved"] == pytest.approx(t["cfg"].prep.road_tti_target, abs=1e-4)
        # TTI from the written capacities (after k), so the floor is inside the calibration
        assert mm["motorway"]["tti"]["non_motorway"]["08-09"] == pytest.approx(mm["tti_achieved"], abs=1e-6)
    report = (t["out1"] / "road_report.md").read_text()
    assert "## Capacity floor by road class" in report and "5th percentile" in report
    for f in br.OUTPUT_FILES:                         # deterministic
        assert (t["out1"] / f).read_bytes() == (t["out2"] / f).read_bytes(), f


def test_toy_outputs_columns_and_checks(toy: dict) -> None:
    out = toy["out1"]
    for f in br.OUTPUT_FILES:
        assert (out / f).exists(), f
    sec = pd.read_csv(out / "road_sections.csv", float_precision="round_trip")
    assert tuple(sec.columns) == br.SECTIONS_COLUMNS
    assert sec["section_id"].tolist() == list(range(len(sec)))
    os_ = pd.read_csv(out / "origin_sections.csv")
    assert tuple(os_.columns) == br.ORIGIN_SECTIONS_COLUMNS
    orig = pd.read_csv(toy["data"] / "origins.csv")
    assert set(os_["origin_id"]) == set(orig["origin_id"])
    # sections add up to the free-flow time to the gate, seq runs 0.. from the origin
    ffs = os_.merge(sec[["section_id", "ff_min"]], on="section_id").sort_values(["origin_id", "seq"])
    tot = ffs.groupby("origin_id")["ff_min"].sum()
    assert np.allclose(tot.loc[orig["origin_id"]].to_numpy(), orig["fftt_to_gate_min"].to_numpy(), atol=1e-3)
    assert (os_.groupby("origin_id")["seq"].apply(lambda s: s.tolist() == list(range(len(s))))).all()
    seg = pd.read_csv(out / "section_segments.csv")
    assert tuple(seg.columns) == br.SECTION_SEGMENTS_COLUMNS
    assert seg.groupby("section_id").size().tolist() == sec["n_seg"].tolist()
    prof = pd.read_csv(out / "road_profile.csv")
    assert list(prof.columns) == list(br.PROFILE_COLUMNS)
    assert prof.loc[prof["profile_id"] == 0, "minute"].tolist() == list(range(1440))
    assert (sec["profile_id"] == 0).all() and (sec["cap_drop"] == toy["cfg"].road.mwy_capacity_drop).all()
    assert toy["res1"]["meta"]["nzta"]["n_valid"] == 2 and toy["res1"]["meta"]["nzta"]["n_sections_nzta"] == 0
    # derived columns follow the formulas
    p = toy["cfg"].prep
    assert np.allclose(sec["obs_peak_vph"], np.round(p.road_inbound_share * sec["peak_ratio"] * sec["adt_twoway"], 3))
    fl = br.adt_floors(sec["frc"], sec["adt_dir"], p.road_adt_floor_pct)       # capacity floor by frc [SPEC4]
    assert np.allclose(sec["cap_vph"], np.round(toy["res1"]["meta"]["k"] * br.capacity_adt(sec["frc"], sec["adt_dir"],
                                                                                         fl), 3))
    assert np.allclose(sec["bg_peak_vph"], np.round(sec["obs_peak_vph"] * (1 - sec["phi"]), 3))
    assert ((sec["phi"] <= 1) & (sec["w_factor"] <= 1) & ((sec["phi"] == 1) | (sec["w_factor"] == 1))).all()
    assert set(sec["adt_source"]) <= set(br.ADT_SOURCES)
    assert "count" in set(sec["adt_source"])


def test_toy_k_hits_tti_target(toy: dict) -> None:
    m = toy["res1"]["meta"]
    assert m["tti_match"] == "non_motorway"          # prep.road_tti_exclude_mwy (config default)
    assert m["tti_achieved"] == pytest.approx(toy["cfg"].prep.road_tti_target, abs=1e-4)
    tt = m["motorway"]["tti"]
    assert tt["non_motorway"]["08-09"] == pytest.approx(m["tti_achieved"], abs=1e-6)
    assert tt["all"]["08-09"] == m["tti_by_hour"]["08-09"] and tt["all"]["07:30"] == m["tti_0730"]
    assert m["tti_by_hour"]["06-07"] < m["tti_by_hour"]["08-09"]


def test_toy_motorway_sections_and_windows(toy: dict) -> None:
    sec = pd.read_csv(toy["out1"] / "road_sections.csv", float_precision="round_trip")
    assert sec["mwy"].tolist() == [int(br.is_motorway(f, s, n)) for f, s, n in
                                   zip(sec["frc"], sec["speed_limit"], sec["street_name"])]
    m = sec[sec["mwy"] == 1]
    assert len(m) > 0 and set(m["street_name"]) == {"Southern Motorway"}
    assert (sec.loc[sec["mwy"] == 0, ["bd_on", "bd_off"]] == -1).all().all()
    # the windows follow cordonlite.roads.breakdown_windows on usual traffic with the written values
    from cordonlite.roads import breakdown_windows
    prof = pd.read_csv(toy["out1"] / "road_profile.csv", float_precision="round_trip")
    r = prof.loc[prof["profile_id"] == 0, "r"].to_numpy()
    rd = toy["cfg"].road
    x = (m["obs_peak_vph"].to_numpy()[:, None] * r[None, :]) / m["cap_vph"].to_numpy()[:, None]
    on, off = breakdown_windows(x, rd.mwy_breakdown_vc, rd.mwy_recover_vc)
    assert m["bd_on"].tolist() == on.tolist() and m["bd_off"].tolist() == off.tolist()
    assert (m["bd_on"] >= 0).all()
    mw = toy["res1"]["meta"]["motorway"]
    assert mw["n_sections"] == len(m) and mw["rule"]["mwy_breakdown"] is True
    assert mw["tti"]["motorway"]["08-09"] > mw["tti_without_breakdown"]["motorway"]["08-09"]
    assert set(mw["broken_share"]) == {"07:00", "07:30", "08:00", "08:30", "09:00", "09:30", "10:00"}
    report = (toy["out1"] / "road_report.md").read_text()
    assert "## Motorway flow breakdown" in report
    # the Assumptions sentence on motorways without a site is built from the written windows
    no_site = br.no_site_motorway_text(sec, toy["res1"]["meta"]["capacity_floor"],
                                       toy["cfg"].prep.road_peak_ratio_default)
    assert no_site and no_site + ". " in report and "keep k x ADT" not in report


def test_toy_motorway_by_name_at_lower_frc(toy: dict) -> None:
    """The toy motorway's frc-2 'bridge' is its own section (frc is part of the section key), flagged
    mwy = 1 by its name, with the same breakdown window as the frc-0 mainline; meta and report list it."""
    sec = pd.read_csv(toy["out1"] / "road_sections.csv", float_precision="round_trip")
    br_sec = sec[(sec["street_name"] == "Southern Motorway") & (sec["frc"] == 2)]
    assert len(br_sec) >= 1 and (br_sec["speed_limit"] == 80).all()
    assert (br_sec["mwy"] == 1).all() and (br_sec["bd_on"] >= 0).all()
    main = sec[(sec["street_name"] == "Southern Motorway") & (sec["frc"] == 0)]
    assert (main["mwy"] == 1).all()
    # same counts and peak ratio, so the same usual V/C and window as the mainline
    assert set(zip(br_sec["bd_on"], br_sec["bd_off"])) == set(zip(main["bd_on"], main["bd_off"]))
    # the old frc-0-only rule would have left it out: exactly these sections changed flag
    old = [int(f == 0 and not br.is_ramp_name(n) and s >= br.MWY_MIN_SPEED_KMH)
           for f, s, n in zip(sec["frc"], sec["speed_limit"], sec["street_name"])]
    changed = sec.loc[sec["mwy"].to_numpy() != np.array(old), "section_id"].tolist()
    assert changed == br_sec["section_id"].tolist()
    mw = toy["res1"]["meta"]["motorway"]
    assert [d["section_id"] for d in mw["by_name_not_frc0"]] == changed
    assert all(d["frc"] == 2 and d["window"] != "none" for d in mw["by_name_not_frc0"])
    report = (toy["out1"] / "road_report.md").read_text()
    for sid in changed:
        assert f"section {sid} 'Southern Motorway' frc 2, 80 km/h" in report


def test_toy_without_motorway_rule_is_the_old_calibration(toy: dict, tmp_path: Path) -> None:
    """road.mwy_breakdown = false, prep.road_tti_exclude_mwy = false and no capacity floor
    (prep.road_adt_floor_pct = 0): k and cap_vph as before 2026-10-08."""
    cfg = load_config(overrides={**_overrides_of(toy["cfg"]), "run.data_dir": str(toy["data"]),
                                 "road.mwy_breakdown": False, "prep.road_tti_exclude_mwy": False,
                                 "prep.road_adt_floor_pct": 0.0})
    res = br.run_build_roads(cfg, tmp_path / "out")
    sec, osec = res["sections"], res["osec"]
    oids = sorted(osec)
    orig = pd.read_csv(toy["data"] / "origins.csv").set_index("origin_id")
    p = cfg.prep
    k, _tti, _ = br.calibrate_k(br.route_matrix(osec, oids), sec["ff_min"].to_numpy(),
                                orig.loc[oids, "weight"].to_numpy(), sec["obs_peak_vph"].to_numpy(),
                                sec["adt_dir"].to_numpy(), res["profile"], cfg.road.bpr_alpha, cfg.road.speed_floor,
                                p.road_tti_target, tuple(p.road_tti_window), tuple(p.road_cap_k_bounds))
    assert res["meta"]["k"] == k and res["meta"]["tti_match"] == "all"
    assert res["meta"]["tti_by_hour"]["08-09"] == pytest.approx(res["meta"]["tti_achieved"], abs=1e-6)
    assert res["meta"]["motorway"]["broken_share"]["08:00"]["network"] == 0.0


def test_toy_rerun_is_byte_identical(toy: dict) -> None:
    for f in br.OUTPUT_FILES:
        a, b = (toy["out1"] / f).read_bytes(), (toy["out2"] / f).read_bytes()
        assert a == b, f
        assert b"\r\n" not in a


def test_toy_wrong_origins_fail_loudly(toy: dict, tmp_path: Path) -> None:
    orig = pd.read_csv(toy["data"] / "origins.csv")
    bad = orig.copy()
    bad.loc[0, "gate_id"] = bad.loc[0, "gate_id"] + 1
    data = tmp_path / "data"
    data.mkdir()
    bad.to_csv(data / "origins.csv", index=False)
    cfg = load_config(overrides={**{k: v for k, v in _overrides_of(toy["cfg"]).items()}, "run.data_dir": str(data)})
    with pytest.raises(ValueError, match="does not reproduce data/origins.csv"):
        br.run_build_roads(cfg, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def _overrides_of(cfg) -> dict:
    p = cfg.prep
    return {"prep.roads_shp": p.roads_shp, "prep.cordon_gpkg": p.cordon_gpkg, "prep.adt_geojson": p.adt_geojson,
            "prep.n_origin_points": p.n_origin_points, "prep.n_corridors": p.n_corridors,
            "prep.density_radius_m": p.density_radius_m, "prep.od_csv": p.od_csv, "prep.origin_draw": p.origin_draw}
