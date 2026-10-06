"""Unit tests for prep/build_inputs.py pure functions (toy graphs, no real data needed)."""

from __future__ import annotations

import math

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import pytest
import shapely
from shapely.geometry import LineString, box

from cordonlite.config import load_config
from prep import build_inputs as bi

CORDON = box(0.0, 0.0, 100.0, 100.0)


def _edge(G: nx.Graph, u, v, minutes: float, seg: str, frc: int = 2) -> None:
    G.add_edge(u, v, minutes=minutes, segment_id=seg, frc=frc, speed_limit=50.0,
               street_name=f"st-{seg}", distance_m=minutes * 50000 / 60, row=0)


def _toy_graph() -> tuple[nx.Graph, tuple[float, float]]:
    """Cross-shaped toy network. Destination (50, 50) inside the box cordon.

    West arm: (-200,50) - (-50,50) - (20,50) - (50,50)          gate edge w2 enters at (20,50)
    South arm with a clip: (50,-200) - (50,-20) - (60,5) [inside] - (70,-10) [outside]
                           - (80,30) [inside] - (50,50)          first entry s2, last entry s4
    """
    G = nx.Graph()
    _edge(G, (-200.0, 50.0), (-50.0, 50.0), 3.0, "w1")
    _edge(G, (-50.0, 50.0), (20.0, 50.0), 1.0, "w2")
    _edge(G, (20.0, 50.0), (50.0, 50.0), 0.5, "w3")
    _edge(G, (50.0, -200.0), (50.0, -20.0), 3.0, "s1")
    _edge(G, (50.0, -20.0), (60.0, 5.0), 0.5, "s2")
    _edge(G, (60.0, 5.0), (70.0, -10.0), 0.3, "s3")
    _edge(G, (70.0, -10.0), (80.0, 30.0), 0.5, "s4")
    _edge(G, (80.0, 30.0), (50.0, 50.0), 0.6, "s5")
    return G, (50.0, 50.0)


# --------------------------------------------------------------------------- gates


def test_first_and_last_entry_on_path() -> None:
    inside = {"a": False, "b": False, "c": True, "d": False, "e": True, "f": True}
    path = ["a", "b", "c", "d", "e", "f"]
    assert bi.first_entry(path, inside) == 2
    assert bi.last_entry(path, inside) == 4
    assert bi.count_entries(path, inside) == 2
    assert bi.gate_index(path, inside, "first_entry") == 2
    assert bi.gate_index(path, inside, "last_entry") == 4
    with pytest.raises(ValueError):
        bi.gate_index(path, inside, "nope")


def test_entry_single_crossing_rules_agree() -> None:
    inside = {"a": False, "b": False, "c": True, "d": True}
    path = ["a", "b", "c", "d"]
    assert bi.first_entry(path, inside) == bi.last_entry(path, inside) == 2
    assert bi.count_entries(path, inside) == 1


def test_entry_errors() -> None:
    with pytest.raises(ValueError):
        bi.first_entry(["a", "b"], {"a": False, "b": False})
    with pytest.raises(ValueError):
        bi.last_entry(["a", "b"], {"a": True, "b": False})


def test_trace_paths_toy_graph_first_and_last() -> None:
    G, dest = _toy_graph()
    origins = pd.DataFrame({"origin_id": [0, 1], "node": [(-200.0, 50.0), (50.0, -200.0)],
                            "x_nztm": [-200.0, 50.0], "y_nztm": [50.0, -200.0], "weight": [1.0, 1.0]})
    first = bi.trace_paths(G, dest, origins, CORDON, "first_entry").set_index("origin_id")
    last = bi.trace_paths(G, dest, origins, CORDON, "last_entry").set_index("origin_id")
    # west: single crossing, both rules give w2; times split at (20, 50)
    assert first.loc[0, "segment_id"] == last.loc[0, "segment_id"] == "w2"
    assert first.loc[0, "fftt_to_gate_min"] == pytest.approx(4.0)
    assert first.loc[0, "fftt_gate_to_dest_min"] == pytest.approx(0.5)
    assert first.loc[0, "n_entries"] == 1
    # south: clips the cordon at (60, 5), leaves, re-enters at (80, 30)
    assert first.loc[1, "segment_id"] == "s2"
    assert last.loc[1, "segment_id"] == "s4"
    assert first.loc[1, "n_entries"] == 2
    assert first.loc[1, "fftt_to_gate_min"] == pytest.approx(3.5)
    assert first.loc[1, "fftt_gate_to_dest_min"] == pytest.approx(1.4)
    assert last.loc[1, "fftt_to_gate_min"] == pytest.approx(4.3)
    assert last.loc[1, "fftt_gate_to_dest_min"] == pytest.approx(0.6)
    for df in (first, last):
        tot = df["fftt_to_gate_min"] + df["fftt_gate_to_dest_min"]
        assert tot.loc[0] == pytest.approx(4.5) and tot.loc[1] == pytest.approx(4.9)


def test_trace_paths_rejects_origin_inside() -> None:
    G, dest = _toy_graph()
    origins = pd.DataFrame({"origin_id": [0], "node": [(20.0, 50.0)], "x_nztm": [20.0],
                            "y_nztm": [50.0], "weight": [1.0]})
    with pytest.raises(ValueError):
        bi.trace_paths(G, dest, origins, CORDON)


def test_gate_point_on_boundary() -> None:
    line = LineString([(-10.0, 50.0), (20.0, 50.0)])
    p = bi.gate_point(line, CORDON, (20.0, 50.0))
    assert (p.x, p.y) == pytest.approx((0.0, 50.0))
    # segment stopping short of the boundary is snapped to the nearest boundary point
    p2 = bi.gate_point(LineString([(-10.0, 50.0), (-0.3, 50.0)]), CORDON, (0.2, 50.0))
    assert CORDON.boundary.distance(p2) == pytest.approx(0.0, abs=1e-9)


def test_destination_node_inside_nearest_centroid() -> None:
    G, _ = _toy_graph()
    assert bi.destination_node(G, CORDON) == (50.0, 50.0)


# --------------------------------------------------------------------------- bearings


def test_bearing_and_compass() -> None:
    assert bi.bearing_deg(0, 0, 0, 10) == pytest.approx(0.0)
    assert bi.bearing_deg(0, 0, 10, 0) == pytest.approx(90.0)
    assert bi.bearing_deg(0, 0, 0, -10) == pytest.approx(180.0)
    assert bi.bearing_deg(0, 0, -10, 0) == pytest.approx(270.0)
    assert bi.compass8(0.0) == "North"
    assert bi.compass8(350.0) == "North"
    assert bi.compass8(100.0) == "East"
    assert bi.compass8(225.0) == "South-west"
    assert bi.circular_mean_deg(np.array([350.0, 10.0])) % 360.0 == pytest.approx(0.0, abs=1e-9)
    assert bi.circular_mean_deg(np.array([80.0, 100.0]), np.array([1.0, 3.0])) == pytest.approx(95.0, abs=0.1)


def test_kmeans_groups_wraparound_and_orders_clockwise() -> None:
    b = np.array([355.0, 5.0, 2.0, 88.0, 92.0, 181.0, 179.0, 270.0])
    w = np.ones_like(b)
    lab = bi.weighted_bearing_kmeans(b, w, 4)
    # north cluster spans 0/360
    assert lab[0] == lab[1] == lab[2] == 0
    assert lab[3] == lab[4] == 1
    assert lab[5] == lab[6] == 2
    assert len(set(lab)) == 4
    # 270 joins a neighbour or is its own cluster; with k=4 the 4 groups are N, E, S, W
    assert lab[7] == 3


def test_kmeans_deterministic_and_k_capped() -> None:
    rng = np.random.default_rng(3)
    b = rng.uniform(0, 360, 40)
    w = rng.uniform(1, 10, 40)
    a1 = bi.weighted_bearing_kmeans(b, w, 5, rng=np.random.default_rng(7))
    a2 = bi.weighted_bearing_kmeans(b, w, 5, rng=np.random.default_rng(7))
    assert np.array_equal(a1, a2)
    assert set(a1) == set(range(5))
    two = bi.weighted_bearing_kmeans(np.array([10.0, 10.0, 200.0]), np.ones(3), 5)
    assert set(two) == {0, 1}
    assert np.array_equal(bi.weighted_bearing_kmeans(np.array([10.0]), np.ones(1), 5), [0])


def test_kmeans_weights_pull_centre() -> None:
    b = np.array([80.0, 100.0, 260.0, 280.0])
    lab = bi.weighted_bearing_kmeans(b, np.array([1.0, 1.0, 1.0, 1.0]), 2)
    assert lab[0] == lab[1] and lab[2] == lab[3] and lab[0] != lab[2]


def test_group_corridors_columns_and_capacity() -> None:
    cfg = load_config(overrides={"prep.n_corridors": 2})
    gates = pd.DataFrame({
        "gate_id": [0, 1, 2, 3], "segment_id": ["a", "b", "c", "d"],
        "streetName": ["Exit 4A Northern Motorway", "Fanshawe Street", "Queen Street", "Queen Street"],
        "frc": [0, 1, 3, 4], "speedLimit": [80, 50, 50, 30],
        "x_nztm": [50.0, 60.0, 50.0, 40.0], "y_nztm": [100.0, 100.0, 0.0, 0.0],
        "n_origins": [10, 5, 7, 1],
    })
    g, c = bi.group_corridors(gates, CORDON, cfg)
    assert list(c.columns) == list(bi.CORRIDORS_COLUMNS)
    assert list(c["corridor_id"]) == [0, 1]
    north = c.iloc[0]
    assert north["name"].startswith("North (Northern Motorway ramp")
    assert north["capacity_vph_raw"] == pytest.approx(4000.0 + 2500.0)
    assert c.iloc[1]["capacity_vph_raw"] == pytest.approx(900.0 + 600.0)
    assert c.iloc[1]["main_streets"] == "Queen Street"
    assert set(g["corridor_id"]) == {0, 1}


def test_clean_street_name() -> None:
    assert bi.clean_street_name("Exit 429B Wellesley Street") == "Wellesley Street ramp"
    assert bi.clean_street_name("Entry 424 Fanshawe Street") == "Fanshawe Street ramp"
    assert bi.clean_street_name("Alten Road") == "Alten Road"


# --------------------------------------------------------------------------- graph and origins


def test_edge_minutes() -> None:
    assert bi.edge_minutes(1000.0, 60.0) == pytest.approx(1.0)
    assert bi.edge_minutes(500.0, 50.0, 1.2) == pytest.approx(0.72)


def test_build_graph_rounds_collapses_parallel_and_keeps_giant() -> None:
    cfg = load_config()
    roads = gpd.GeoDataFrame({
        "newSegmentId": ["a", "a-rev", "b", "far"],
        "speedLimit": [50, 100, 50, 50],
        "frc": [2, 2, 3, 4],
        "streetName": ["A", "A", "B", None],
        "distance": [1000.0, 1000.0, 500.0, 100.0],
    }, geometry=[LineString([(0.2, 0.1), (1000.0, 0.0)]),
                 LineString([(1000.3, 0.2), (0.0, 0.0)]),        # reverse digitisation, faster
                 LineString([(1000.0, 0.0), (1000.0, 500.0)]),
                 LineString([(9000.0, 0.0), (9100.0, 0.0)])], crs="EPSG:2193")
    roads["streetName"] = roads["streetName"].fillna("")
    G = bi.build_graph(roads, cfg)
    assert G.number_of_nodes() == 3 and G.number_of_edges() == 2
    e = G.edges[(0.0, 0.0), (1000.0, 0.0)]
    assert e["segment_id"] == "a-rev" and e["minutes"] == pytest.approx(0.6)


def test_local_road_length_radius() -> None:
    roads = gpd.GeoDataFrame({"frc": [4, 3, 1], "distance": [100.0, 50.0, 1000.0]},
                             geometry=[LineString([(0, 0), (100, 0)]), LineString([(0, 600), (50, 600)]),
                                       LineString([(0, 10), (1000, 10)])], crs="EPSG:2193")
    w = bi.local_road_length(np.array([[50.0, 0.0], [25.0, 600.0], [5000.0, 5000.0]]), roads, [3, 4], 500.0)
    assert w.tolist() == [100.0, 50.0, 0.0]


def test_sample_origins_deterministic_and_weighted() -> None:
    cfg = load_config(overrides={"prep.n_origin_points": 50})
    cand = pd.DataFrame({"node": [(float(i), 0.0) for i in range(200)], "x_nztm": np.arange(200.0),
                         "y_nztm": np.zeros(200), "weight": np.r_[np.full(100, 100.0), np.full(100, 1.0)]})
    a = bi.sample_origins(cand, cfg)
    b = bi.sample_origins(cand, cfg)
    pd.testing.assert_frame_equal(a, b)
    assert list(a["origin_id"]) == list(range(50))
    assert a["node"].nunique() == 50                  # without replacement
    assert (a["weight"] == 100.0).mean() > 0.8
    small = bi.sample_origins(cand.head(10), cfg)     # fewer candidates than requested -> replacement
    assert len(small) == 50


def test_inside_mask() -> None:
    m = bi.inside_mask(CORDON, np.array([[50.0, 50.0], [150.0, 50.0], [0.0, 50.0]]))
    assert m.tolist() == [True, False, True]


def test_real_outputs_consistent_if_present() -> None:
    """Sanity checks on data/ produced by the real prep run (skipped if not built)."""
    cfg = load_config()
    d = cfg.resolve_path(cfg.run.data_dir)
    if not (d / "origins.csv").exists():
        pytest.skip("data/ not built")
    o = pd.read_csv(d / "origins.csv")
    g = pd.read_csv(d / "gates.csv")
    c = pd.read_csv(d / "corridors.csv")
    assert list(o.columns) == list(bi.ORIGINS_COLUMNS)
    assert list(g.columns) == list(bi.GATES_COLUMNS)
    assert list(c.columns) == list(bi.CORRIDORS_COLUMNS)
    assert len(o) == cfg.prep.n_origin_points
    assert list(c["corridor_id"]) == list(range(len(c)))
    assert set(o["corridor_id"]) <= set(c["corridor_id"])
    assert set(o["gate_id"]) == set(g["gate_id"])
    assert (g.groupby("corridor_id").size() == c.set_index("corridor_id")["n_gates"]).all()
    assert g["n_origins"].sum() == len(o)
    gate_corr = dict(zip(g["gate_id"], g["corridor_id"]))
    assert (o["gate_id"].map(gate_corr) == o["corridor_id"]).all()
    cordon = gpd.read_file(d / "cordon.geojson").geometry.iloc[0]
    assert not bi.inside_mask(cordon, o[["x_nztm", "y_nztm"]].to_numpy()).any()
    bnd = cordon.boundary
    assert shapely.distance(bnd, shapely.points(g[["x_nztm", "y_nztm"]].to_numpy())).max() < 0.1
    assert (o["fftt_to_gate_min"] >= 0).all() and (o["fftt_gate_to_dest_min"] >= 0).all()
    assert not math.isnan(o["path_km"].sum())
