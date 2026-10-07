"""Road congestion inputs (run once, after build_inputs): road sections, counts and capacity k.

Owner: prep builder. See INTERFACES.md and the road congestion design (2026-10-07). Outputs into
cordon_lite/data/.

    python -m prep.build_roads [--config config.toml] [--out-dir data]

The prep shortest paths are rebuilt with the build_inputs functions from the TomTom shapefile
(``prep.roads_shp``, field ``segment_id`` = TomTom ``newSegmentId``) and the cordon, and must
reproduce data/origins.csv exactly (coordinates, weight, gate_id, corridor_id, free-flow minutes,
path_km at the stored precision); otherwise the script stops. The pre-gate part of every origin's
path (origin node -> inside end of its gate segment, the edges whose minutes add up to
fftt_to_gate_min) is cut into road SECTIONS: maximal chains of consecutive graph edges used by the
same set of origins with the same frc, speed limit, normalised street name and count values.

Counts: every AT/NZTA count point (``prep.adt_geojson``) is matched to the nearest graph edge with
the same normalised street name within ``prep.adt_match_m`` (state-highway records by route to
the motorway names; bus-only ramp records are not used). An AT count is not used when a more
recent count of the same street within ``prep.adt_propagate_m`` is more than four times larger
(stale or misplaced counts, ``stale_counts``). A count holds along the same street up to
``prep.adt_propagate_m`` through the network (nearest source wins); other edges take the median
two-way ADT of matched edges of their frc and speed band. An AT count is a two-way total unless
its road_name names a direction (EASTBOUND, NORTH BOUND, ...); state-highway records count one
carriageway or one ramp. Per section: observed inbound peak-hour flow
``obs_peak_vph = road_inbound_share x peak_ratio x adt_twoway``, capacity ``cap_vph = k x adt_dir``,
the commuters' share ``phi`` of the counted 06:00-10:00 volume, background ``bg_peak_vph`` and the
commuter weight ``w_factor``. k is bisected so that the origin-weighted travel time index of
departures in ``prep.road_tti_window`` under usual traffic equals ``prep.road_tti_target`` (TomTom
Traffic Index, Auckland 2025), with the engines' speed factor (``speed_factor``).

Outputs (LF line endings; a rerun on the same inputs writes byte-identical files):
    road_sections.csv     one row per section (SECTIONS_COLUMNS), sorted by section_id
    origin_sections.csv   origin_id, seq, section_id (seq 0 at the origin)
    section_segments.csv  section_id, seq, segment_id (TomTom ids in travel order, for drawing)
    road_profile.csv      minute, r (1440 rows, r with 6 decimals)
    road_meta.json        parameters, k, TTI, matching counts, input files
    road_report.md        human-readable summary

Public API:
    norm_name(name) -> str
    parse_peak_hour(value) -> float                     # minutes after midnight or nan
    count_kind(road_name) -> tuple[str, str]            # (kind, SH route)
    has_direction_label(road_name) -> bool              # AT count of one direction ('... (EASTBOUND)')
    speed_band(speed_kmh) -> int
    load_roads_shp(cfg) -> gpd.GeoDataFrame
    load_cordon_any(cfg) -> tuple[BaseGeometry, Path]
    reproduce_prep(cfg, roads, cordon) -> dict
    check_origins(origins, ref) -> None
    edge_table(G, roads, cfg) -> pd.DataFrame
    pregate_routes(G, dest, origins, cordon, rule, eid) -> dict[int, list[tuple[int, Node]]]
    load_counts(cfg) -> tuple[pd.DataFrame, dict]
    stale_counts(counts, point_match, max_m) -> np.ndarray   # bool per point_match row
    match_counts(edges, counts, match_m, stale_m=None) -> tuple[pd.DataFrame, pd.DataFrame]
    direct_values(edges, counts, edge_match, cfg) -> pd.DataFrame
    propagate(edges, direct, max_m) -> pd.DataFrame
    edge_values(edges, counts, edge_match, cfg) -> pd.DataFrame
    build_sections(routes, key) -> tuple[list[list[int]], dict[int, list[int]]]
    road_profile(values, start_min) -> np.ndarray
    speed_factor(v, cap, alpha, floor) -> np.ndarray
    probe_elapsed(route_mat, ff, F, departures) -> np.ndarray
    weighted_tti(el, ffsum, weights) -> float
    calibrate_k(...) -> tuple[float, float, list]
    run_build_roads(cfg, out_dir=None) -> dict
    main(argv=None) -> int
"""

from __future__ import annotations

import argparse
import dataclasses
import heapq
import json
import math
import os
import re
from collections.abc import Hashable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from shapely.geometry.base import BaseGeometry

from cordonlite.config import ROOT, Config, load_config
from prep import build_inputs as bi

Node = tuple[float, float]

SECTIONS_COLUMNS: tuple[str, ...] = (
    "section_id", "n_seg", "ff_min", "km", "frc", "speed_limit", "street_name", "adt_twoway",
    "adt_dir", "adt_source", "peak_ratio", "cap_vph", "obs_peak_vph", "am_volume_veh",
    "expected_commuter_veh", "phi", "bg_peak_vph", "w_factor", "n_origins", "x_mid", "y_mid",
)
ORIGIN_SECTIONS_COLUMNS: tuple[str, ...] = ("origin_id", "seq", "section_id")
SECTION_SEGMENTS_COLUMNS: tuple[str, ...] = ("section_id", "seq", "segment_id")
PROFILE_COLUMNS: tuple[str, ...] = ("minute", "r")
OUTPUT_FILES: tuple[str, ...] = ("road_sections.csv", "origin_sections.csv", "section_segments.csv",
                                 "road_profile.csv", "road_meta.json", "road_report.md")
ADT_SOURCES: tuple[str, ...] = ("count", "propagated", "default")

# SA3 polygons in the SSC2026 repository, used when prep.cordon_gpkg does not exist (relative to
# the cordon_lite folder); data/cordon.geojson is the last fallback.
SA3_FALLBACK = "../../SSC2026/netlogo/Data/roads/akl_CBD_SA3.gpkg"

PEAK_RATIO_CLIP: tuple[float, float] = (0.05, 0.20)   # peak-hour volume / ADT is clipped to this [A]
AM_PEAK_START: tuple[int, int] = (360, 585)           # a count's peak_hour start in 06:00-09:45 is an AM peak
AM_VOLUME_WINDOW: tuple[int, int] = (360, 600)        # observed morning volume, minutes [360, 600)
PROFILE_RAMP_FROM_MIN = 300                           # profile ramps from 0.15 x first value at 05:00
PROFILE_LOW = 0.15
N_MINUTES = 1440
DEFAULT_MIN_EDGES = 5          # a (frc, speed band) median needs at least this many matched edges [A]
SH_BEARING_MAX_DEG = 60.0      # SH carriageway counts hold only on edges within this bearing [SPEC]
K_ITERATIONS = 30              # bisection steps for k (fixed, so reruns are identical; bracket / 2^30 << 1e-6)
TTI_HOURS: tuple[tuple[str, int, int], ...] = (
    ("06-07", 360, 420), ("07-08", 420, 480), ("08-09", 480, 540), ("09-10", 540, 600))
TTI_PROBE_MIN = 450            # 07:30
VC_PROBE_MIN: tuple[int, ...] = (450, 495)   # 07:30 and 08:15
LOW_CAP_VPH = 50.0             # report flag: sections with a capacity this small come from very small counts

# State-highway route -> normalised TomTom street names of its carriageways [SPEC 1.2]; the
# literal TomTom names of numbered state-highway links ("State Highway 16", "20") are added.
SH_ROUTE_NAMES: dict[str, frozenset[str]] = {
    "01N": frozenset({"NORTHERN", "SOUTHERN"}),
    "016": frozenset({"NORTHWESTERN", "STANLEY", "THE STRAND", "STATE HIGHWAY 16"}),
    "018": frozenset({"UPPER HARBOUR"}),
    "020": frozenset({"SOUTHWESTERN", "STATE HIGHWAY 20", "20"}),
    "20A": frozenset({"GEORGE BOLT MEMORIAL"}),
}
NAME_SUFFIXES: frozenset[str] = frozenset({
    "ROAD", "RD", "STREET", "ST", "AVENUE", "AVE", "AV", "DRIVE", "DR", "PLACE", "PL", "CRESCENT",
    "CRES", "TERRACE", "TCE", "PARADE", "PDE", "HIGHWAY", "HWY", "LANE", "LN", "WAY", "RISE", "MALL",
    "EXTENSION", "EXT", "XTN", "BOULEVARD", "BLVD", "GROVE", "GR", "CLOSE", "CL", "COURT", "CT",
    "SQUARE", "SQ", "QUAY", "ESPLANADE", "ESP", "MOTORWAY", "MWY", "BYPASS", "HILL", "EXPRESSWAY",
    "QUADRANT", "MILE", "CIRCLE", "LOOP", "RAMP",
})
DIRECTION_TOKENS: frozenset[str] = frozenset({"N", "S", "E", "W", "NORTH", "SOUTH", "EAST", "WEST"})
SPEED_BANDS: tuple[tuple[float, int], ...] = (
    (35.0, 35), (45.0, 40), (55.0, 50), (65.0, 60), (75.0, 70), (90.0, 80), (math.inf, 100))
_RAMP_RE = re.compile(r"^(ENTRY|EXIT)\b|\b(ENTRY|EXIT|RAMP)\b")
_PREFIX_RE = re.compile(r"^(ENTRY|EXIT)(\s+AND\s+(ENTRY|EXIT))?\s+\S+\s+")
# AT direction label in a count's road_name ('TI RAKAU DR (EASTBOUND)', 'PAKURANGA RD (EAST BOUND)',
# 'ORMISTON RD (EASTBOUND/FLAT BUSH)'; not BOUNDARY RD): the count covers one direction [A]. Whether
# the TomTom edge has a reversed twin says little about this: the carriageways of divided roads
# never twin, and AT counts there are still two-way totals.
_DIR_LABEL_RE = re.compile(r"\b(NORTH|SOUTH|EAST|WEST) ?BOUND\b")
# State-highway ramp records of bus-only ramps and busways count buses, not general traffic, and are
# not used [A]: start_name or end_name names a bus ramp, buses or a busway ('START OF BUS RAMP',
# 'ISLAND NOSE/BUSES ONLY', 'ONEWA SOUTHBOUND BUSWAY BRIDGE'), or cars are under BUS_RAMP_MAX_CAR_PCT
# of the record's traffic (pccar; the Northern Busway station ramps have 1-15%, other ramps 76-100%).
_BUS_RAMP_RE = re.compile(r"\bBUS(ES|WAY)?\b")
BUS_RAMP_MAX_CAR_PCT = 50.0
STALE_ADT_RATIO = 0.25   # an AT count below this share of a more recent same-street count nearby is not used [A]


# --------------------------------------------------------------------------- names and counts


def norm_name(name: Any) -> str:
    """Normalised street name for matching counts to TomTom segments.

    Upper case; ``(...)`` qualifiers dropped (also unclosed ones); TomTom ``Entry/Exit NNN``
    prefixes dropped; MOUNT -> MT, SAINT -> ST; punctuation removed; trailing direction tokens
    (N/S/E/W, NORTH, ...) and then street-type suffixes (RD/ROAD, ST/STREET, ...) dropped, always
    keeping the first word. 'Exit 429B Wellesley Street' -> 'WELLESLEY', 'MT EDEN RD (NORTH)' ->
    'MT EDEN'. TomTom's 'Terrace Atatu Road' is read as 'TE ATATU'.
    """
    if name is None or (isinstance(name, float) and math.isnan(name)):
        return ""
    s = str(name).upper().strip()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\(.*$", " ", s).strip()
    s = _PREFIX_RE.sub("", s)
    s = re.sub(r"^TERRACE ATATU\b", "TE ATATU", s)
    s = re.sub(r"[^A-Z0-9 ]", "", s.replace("-", " ").replace("/", " "))
    s = re.sub(r"\bMOUNT\b", "MT", s)
    s = re.sub(r"\bSAINT\b", "ST", s)
    t = s.split()
    while len(t) > 1 and t[-1] in DIRECTION_TOKENS:
        t.pop()
    while len(t) > 1 and t[-1] in NAME_SUFFIXES:
        t.pop()
    return " ".join(t)


def is_ramp_name(street_name: str) -> bool:
    """True for TomTom ramp names ('Exit 4A Northern Motorway', 'Northern Motorway Entry')."""
    return bool(_RAMP_RE.search(str(street_name).upper()))


def parse_peak_hour(value: Any) -> float:
    """Start of the count's peak hour in minutes after midnight ('800', '08:00', '16:'), else nan."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return math.nan
    s = str(value).strip()
    if ":" in s:
        h, _, mm = s.partition(":")
        h, mm = h.strip(), mm.strip() or "0"
        if not (h.isdigit() and mm.isdigit()):
            return math.nan
        return float(int(h) * 60 + int(mm))
    if not s.isdigit():
        return math.nan
    v = int(s)
    return float((v // 100) * 60 + v % 100)


def count_kind(road_name: Any) -> tuple[str, str]:
    """(kind, route) of a count record.

    kind: 'local' (AT count, two-way unless has_direction_label), 'sh_cway' (state-highway
    carriageway, road_name ending -I or -D), 'sh_ramp' (-R1, -R2, ...) or 'sh_other' (state-highway
    record without a direction suffix; not used). route: '01N', '016', ... for state highways.
    """
    s = "" if road_name is None or (isinstance(road_name, float) and math.isnan(road_name)) else str(road_name)
    m = re.match(r"^SH\s*(\w+)-", s)
    if not m:
        return "local", ""
    route = m.group(1)
    if re.search(r"-[ID]$", s):
        return "sh_cway", route
    if re.search(r"-R\d+$", s):
        return "sh_ramp", route
    return "sh_other", route


def has_direction_label(road_name: Any) -> bool:
    """True when an AT count's road_name names one direction ('TI RAKAU DR (EASTBOUND)', 'PAKURANGA
    RD (EAST BOUND)'): the count is directional. Other AT counts are two-way totals."""
    if road_name is None or (isinstance(road_name, float) and math.isnan(road_name)):
        return False
    return bool(_DIR_LABEL_RE.search(str(road_name).upper()))


def speed_band(speed_kmh: float) -> int:
    """Speed-limit band label used for default ADT medians (35, 40, 50, 60, 70, 80, 100)."""
    for upper, label in SPEED_BANDS:
        if float(speed_kmh) <= upper:
            return label
    return SPEED_BANDS[-1][1]


def clip_peak_ratio(x: float) -> float:
    lo, hi = PEAK_RATIO_CLIP
    return min(hi, max(lo, float(x)))


# --------------------------------------------------------------------------- loading


def load_roads_shp(cfg: Config) -> gpd.GeoDataFrame:
    """TomTom roads from ``prep.roads_shp`` through build_inputs.load_roads (field segment_id -> newSegmentId)."""
    shp = cfg.resolve_path(cfg.prep.roads_shp)
    if not shp.exists():
        raise FileNotFoundError(f"prep.roads_shp not found: {shp}")
    c2 = dataclasses.replace(cfg, prep=dataclasses.replace(cfg.prep, roads_gpkg=str(shp), roads_layer=shp.stem))
    roads = bi.load_roads(c2)
    if "newSegmentId" not in roads.columns:
        roads = roads.rename(columns={"segment_id": "newSegmentId"})
    return roads


def load_cordon_any(cfg: Config) -> tuple[BaseGeometry, Path]:
    """Cordon polygon: prep.cordon_gpkg if it exists, else the SSC2026 SA3 gpkg, else data/cordon.geojson."""
    for p in (cfg.prep.cordon_gpkg, SA3_FALLBACK):
        path = cfg.resolve_path(p)
        if path.exists():
            c2 = dataclasses.replace(cfg, prep=dataclasses.replace(cfg.prep, cordon_gpkg=str(path)))
            return bi.load_cordon(c2), path
    path = cfg.resolve_path(cfg.run.data_dir) / "cordon.geojson"
    gdf = gpd.read_file(path)
    if gdf.crs is not None and gdf.crs.to_epsg() != cfg.prep.crs_epsg:
        gdf = gdf.to_crs(epsg=cfg.prep.crs_epsg)
    return shapely.unary_union([shapely.make_valid(g) for g in gdf.geometry]).buffer(0), path


def load_counts(cfg: Config) -> tuple[pd.DataFrame, dict[str, int]]:
    """Count points with adt > 0 in the prep CRS, without the state-highway ramp records of bus-only
    ramps and busways (start_name or end_name names a bus ramp, buses or a busway, or pccar <
    BUS_RAMP_MAX_CAR_PCT; stats n_sh_ramp_bus).

    Columns: count_id (OBJECTID), road_name, kind, route, core (normalised road_name, local only),
    adt, peaktraffic, peak_min, count_date ('YYYY-MM-DD'), x, y.
    """
    path = cfg.resolve_path(cfg.prep.adt_geojson)
    g = gpd.read_file(path)
    if g.crs is None or g.crs.to_epsg() != cfg.prep.crs_epsg:
        g = g.set_crs(epsg=4326, allow_override=False) if g.crs is None else g
        g = g.to_crs(epsg=cfg.prep.crs_epsg)
    n_all = len(g)
    adt = pd.to_numeric(g["adt"], errors="coerce")
    g = g[(adt > 0) & g.geometry.notna() & ~g.geometry.is_empty].reset_index(drop=True)
    kinds = [count_kind(n) for n in g["road_name"]]
    xy = shapely.get_coordinates(g.geometry.values)
    dates = pd.to_datetime(g["count_date"], errors="coerce", utc=True)
    out = pd.DataFrame({
        "count_id": g["OBJECTID"].astype(int).to_numpy(),
        "road_name": g["road_name"].fillna("").astype(str).to_numpy(),
        "kind": [k for k, _ in kinds],
        "route": [r for _, r in kinds],
        "core": [norm_name(n) if k == "local" else "" for n, (k, _) in zip(g["road_name"], kinds)],
        "adt": pd.to_numeric(g["adt"], errors="coerce").to_numpy(dtype=float),
        "peaktraffic": pd.to_numeric(g["peaktraffic"], errors="coerce").to_numpy(dtype=float),
        "peak_min": [parse_peak_hour(v) for v in g["peak_hour"]],
        "count_date": dates.dt.strftime("%Y-%m-%d").fillna("").to_numpy(),
        "x": xy[:, 0], "y": xy[:, 1],
    })
    ends = [f"{a} {b}".upper() for a, b in zip(_text_col(g, "start_name"), _text_col(g, "end_name"))]
    pccar = (pd.to_numeric(g["pccar"], errors="coerce").to_numpy(dtype=float) if "pccar" in g.columns
             else np.full(len(g), np.nan))
    bus = (out["kind"] == "sh_ramp").to_numpy() & (
        np.array([bool(_BUS_RAMP_RE.search(e)) for e in ends], dtype=bool) | (pccar < BUS_RAMP_MAX_CAR_PCT))
    stats = {"n_points": int(n_all), "n_adt_positive": int(len(out)), "n_sh_ramp_bus": int(bus.sum())}
    out = out[~bus].reset_index(drop=True)
    for k in ("local", "sh_cway", "sh_ramp", "sh_other"):
        stats[f"n_{k}"] = int((out["kind"] == k).sum())
    return out, stats


def _text_col(g: pd.DataFrame, col: str) -> list[str]:
    """A text column as strings ('' for missing values or a missing column)."""
    if col not in g.columns:
        return [""] * len(g)
    return g[col].fillna("").astype(str).tolist()


# --------------------------------------------------------------------------- prep paths


def origins_frame(paths: pd.DataFrame, gates: pd.DataFrame) -> pd.DataFrame:
    """The origins.csv frame exactly as build_inputs.write_outputs builds it."""
    seg2gate = dict(zip(gates["segment_id"], gates["gate_id"]))
    seg2corr = dict(zip(gates["segment_id"], gates["corridor_id"]))
    return pd.DataFrame({
        "origin_id": paths["origin_id"].astype(int),
        "x_nztm": paths["x_nztm"].round(1),
        "y_nztm": paths["y_nztm"].round(1),
        "weight": paths["weight"].round(3),
        "corridor_id": paths["segment_id"].map(seg2corr).astype(int),
        "gate_id": paths["segment_id"].map(seg2gate).astype(int),
        "fftt_to_gate_min": paths["fftt_to_gate_min"].round(3),
        "fftt_gate_to_dest_min": paths["fftt_gate_to_dest_min"].round(3),
        "path_km": paths["path_km"].round(3),
    })[list(bi.ORIGINS_COLUMNS)]


def check_origins(origins: pd.DataFrame, ref: pd.DataFrame, atol: float = 5e-7) -> None:
    """Raise ValueError unless the rebuilt origins equal data/origins.csv column by column."""
    if len(origins) != len(ref):
        raise ValueError(f"rebuilt prep has {len(origins)} origins, data/origins.csv has {len(ref)}")
    bad = []
    for c in bi.ORIGINS_COLUMNS:
        if c not in ref.columns:
            bad.append(f"{c}: missing in data/origins.csv")
            continue
        a = origins[c].to_numpy(dtype=float)
        b = ref[c].to_numpy(dtype=float)
        n = int((~np.isclose(a, b, rtol=0.0, atol=atol)).sum())
        if n:
            bad.append(f"{c}: {n} rows differ (max abs diff {np.abs(a - b).max():.6g})")
    if bad:
        raise ValueError("the rebuilt prep does not reproduce data/origins.csv; road sections would not "
                         "match the run's origins:\n  " + "\n  ".join(bad))


def reproduce_prep(cfg: Config, roads: gpd.GeoDataFrame, cordon: BaseGeometry) -> dict[str, Any]:
    """Rebuild graph, destination, sampled origins, paths, gates and corridors as build_inputs does."""
    G = bi.build_graph(roads, cfg)
    dest = bi.destination_node(G, cordon)
    candidates = bi.candidate_origins(G, roads, cordon, cfg)
    origins = bi.sample_origins(candidates, cfg)
    paths = bi.trace_paths(G, dest, origins, cordon, cfg.prep.gate_rule)
    gates = bi.gate_table(paths, roads, cordon)
    gates, corridors = bi.group_corridors(gates, cordon, cfg)
    return {"G": G, "dest": dest, "origins": origins, "paths": paths, "gates": gates,
            "corridors": corridors, "origins_frame": origins_frame(paths, gates)}


def edge_table(G: nx.Graph, roads: gpd.GeoDataFrame, cfg: Config) -> pd.DataFrame:
    """One row per graph edge, ordered by its roads row (edge index = position).

    Columns: u, v (graph nodes), row, segment_id, minutes, distance_m, frc, speed_limit,
    street_name, core (norm_name), ramp, bearing (deg, from the segment's first to last vertex =
    travel direction), two_way (a segment in the reverse direction between the same rounded end
    points exists; otherwise a one-way carriageway or street), geometry.
    """
    r = cfg.prep.node_round_m
    geoms = roads.geometry.values
    p0 = shapely.get_coordinates(shapely.get_point(geoms, 0))
    p1 = shapely.get_coordinates(shapely.get_point(geoms, -1))
    x0, y0 = bi.round_xy(p0[:, 0], p0[:, 1], r)
    x1, y1 = bi.round_xy(p1[:, 0], p1[:, 1], r)
    directed = set(zip(zip(x0.tolist(), y0.tolist()), zip(x1.tolist(), y1.tolist())))
    edges = sorted(G.edges(data=True), key=lambda t: t[2]["row"])
    rows = []
    for u, v, d in edges:
        i = int(d["row"])
        a, b = (float(x0[i]), float(y0[i])), (float(x1[i]), float(y1[i]))
        rows.append({
            "u": u, "v": v, "row": i, "segment_id": d["segment_id"], "minutes": float(d["minutes"]),
            "distance_m": float(d["distance_m"]), "frc": int(d["frc"]),
            "speed_limit": int(round(d["speed_limit"])), "street_name": str(d["street_name"]),
            "core": norm_name(d["street_name"]), "ramp": is_ramp_name(d["street_name"]),
            "bearing": float(bi.bearing_deg(p0[i, 0], p0[i, 1], p1[i, 0], p1[i, 1])),
            "two_way": (b, a) in directed, "geometry": geoms[i],
        })
    return pd.DataFrame(rows)


def edge_index(edges: pd.DataFrame) -> dict[tuple[Node, Node], int]:
    """(u, v) and (v, u) -> edge index."""
    eid: dict[tuple[Node, Node], int] = {}
    for i, (u, v) in enumerate(zip(edges["u"], edges["v"])):
        eid[(u, v)] = i
        eid[(v, u)] = i
    return eid


def pregate_routes(G: nx.Graph, dest: Node, origins: pd.DataFrame, cordon: BaseGeometry, rule: str,
                   eid: dict[tuple[Node, Node], int]) -> dict[int, list[tuple[int, Node]]]:
    """origin_id -> [(edge index, node the edge is entered from)] from the origin to the gate's inside end.

    Same Dijkstra tree and gate rule as build_inputs.trace_paths; the gate edge is included.
    """
    _, paths = nx.single_source_dijkstra(G, dest, weight="minutes")
    nodes, xy = bi.node_array(G)
    ins = dict(zip(nodes, bi.inside_mask(cordon, xy).tolist()))
    out: dict[int, list[tuple[int, Node]]] = {}
    for o in origins.itertuples(index=False):
        path = list(reversed(paths[o.node]))
        i = bi.gate_index(path, ins, rule)
        out[int(o.origin_id)] = [(eid[(path[j], path[j + 1])], path[j]) for j in range(i)]
    return out


# --------------------------------------------------------------------------- count matching


def _name_ok(kind: str, route: str, core: str, e_core: str, e_ramp: bool, e_street: str) -> bool:
    if kind == "local":
        return core != "" and core == e_core
    if kind == "sh_cway":
        return e_core in SH_ROUTE_NAMES.get(route, frozenset())
    if kind == "sh_ramp":
        return e_ramp or e_street == ""
    return False


def stale_counts(counts: pd.DataFrame, point_match: pd.DataFrame, max_m: float) -> np.ndarray:
    """Stale AT counts among the matched points (bool per point_match row).

    A matched AT count is stale when a matched AT count of the same street (normalised name) whose
    point lies within max_m is more recent (later count_date) and its two-way ADT (2 x adt with a
    direction label) is below STALE_ADT_RATIO of that count's: an old count that newer counts of
    the street contradict, or a count placed on the wrong link (Wairau Rd: 64 vehicles a day in
    1999, 28 m from 19,798 in 2024; Queenstown Rd: 2,362 in 1990 next to 21,297 in 2025). The
    'most recent count_date' rule for counts on one edge, applied to the street's neighbourhood
    where the values disagree that much.
    """
    out = np.zeros(len(point_match), dtype=bool)
    if len(point_match) == 0:
        return out
    ci = point_match["ci"].to_numpy(dtype=int)
    loc = counts["kind"].to_numpy()[ci] == "local"
    core = counts["core"].to_numpy()[ci]
    date = counts["count_date"].to_numpy()[ci]
    x, y = counts["x"].to_numpy(dtype=float)[ci], counts["y"].to_numpy(dtype=float)[ci]
    twoway = np.array([float(a) * (2.0 if has_direction_label(n) else 1.0) for a, n in
                       zip(counts["adt"].to_numpy()[ci], counts["road_name"].to_numpy()[ci])])
    by_core: dict[str, list[int]] = {}
    for i in np.flatnonzero(loc & (core != "")):
        by_core.setdefault(str(core[i]), []).append(int(i))
    for rows in by_core.values():
        for i in rows:
            for j in rows:
                if (j != i and date[j] > date[i] and twoway[i] < STALE_ADT_RATIO * twoway[j]
                        and math.hypot(x[j] - x[i], y[j] - y[i]) <= max_m):
                    out[i] = True
                    break
    return out


def match_counts(edges: pd.DataFrame, counts: pd.DataFrame, match_m: float,
                 stale_m: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Name-checked nearest-edge match of every count point within match_m.

    Returns (point_match, edge_match). point_match: one row per matched count (ci = row in
    ``counts``, edge, dist_m, stale), nearest edge with an accepted name (ties: lower edge index);
    stale marks the AT counts that ``stale_counts`` drops with max_m = stale_m (none when stale_m
    is None). edge_match: one row per edge holding a count that is not stale; several counts on
    one edge keep the most recent count_date (ties: nearer, then lower count_id).
    """
    cols = ["ci", "edge", "dist_m"]
    if len(counts) == 0 or len(edges) == 0:
        return pd.DataFrame(columns=cols + ["stale"]), pd.DataFrame(columns=cols)
    geoms = np.asarray(edges["geometry"].to_list(), dtype=object)
    tree = shapely.STRtree(geoms)
    pts = shapely.points(counts["x"].to_numpy(dtype=float), counts["y"].to_numpy(dtype=float))
    pi, ei = tree.query(pts, predicate="dwithin", distance=float(match_m))
    if len(pi) == 0:
        return pd.DataFrame(columns=cols + ["stale"]), pd.DataFrame(columns=cols)
    d = shapely.distance(pts[pi], geoms[ei])
    kind, route, core = counts["kind"].to_numpy(), counts["route"].to_numpy(), counts["core"].to_numpy()
    e_core, e_ramp, e_st = edges["core"].to_numpy(), edges["ramp"].to_numpy(), edges["street_name"].to_numpy()
    ok = np.array([_name_ok(kind[p], route[p], core[p], e_core[e], bool(e_ramp[e]), e_st[e])
                   for p, e in zip(pi, ei)], dtype=bool)
    cand = pd.DataFrame({"ci": pi[ok].astype(int), "edge": ei[ok].astype(int), "dist_m": d[ok]})
    pm = (cand.sort_values(["ci", "dist_m", "edge"], kind="mergesort")
          .drop_duplicates("ci", keep="first").reset_index(drop=True))
    pm["stale"] = (stale_counts(counts, pm, float(stale_m)) if stale_m is not None
                   else np.zeros(len(pm), dtype=bool))
    pm2 = pm[~pm["stale"]]
    pm2 = pm2.assign(date=counts["count_date"].to_numpy()[pm2["ci"]],
                     cid=counts["count_id"].to_numpy()[pm2["ci"]])
    em = (pm2.sort_values(["edge", "date", "dist_m", "cid"], ascending=[True, False, True, True], kind="mergesort")
          .drop_duplicates("edge", keep="first")[cols].reset_index(drop=True))
    return pm[cols + ["stale"]], em


def direct_values(edges: pd.DataFrame, counts: pd.DataFrame, edge_match: pd.DataFrame,
                  cfg: Config) -> pd.DataFrame:
    """Values of the edges that hold a count (index = edge index).

    Directional convention [SPEC 1.3, direction from the count record]: a count of one carriageway
    or direction (SH -I/-D, SH ramp, or an AT count whose road_name names a direction,
    has_direction_label) is directional: adt_dir = adt, adt_twoway = 2 x adt; any other AT count
    is a two-way total: adt_twoway = adt, adt_dir = adt / 2. (An AT count on a TomTom edge without
    a reversed twin is not taken as directional: those edges are mostly carriageways of divided
    roads, and their AT counts are two-way totals like those of the same street elsewhere.)
    peak_ratio = peaktraffic / adt when the count's peak hour starts in 06:00-09:45, else
    prep.road_peak_ratio_default; clipped.
    """
    p = cfg.prep
    rows = []
    for e, ci in zip(edge_match["edge"].astype(int), edge_match["ci"].astype(int)):
        c = counts.iloc[ci]
        adt = float(c["adt"])
        directional = c["kind"] != "local" or has_direction_label(c["road_name"])
        twoway = 2.0 * adt if directional else adt
        pk, ptr = float(c["peak_min"]), float(c["peaktraffic"])
        am = (not math.isnan(pk)) and AM_PEAK_START[0] <= pk <= AM_PEAK_START[1] and ptr > 0
        ratio = clip_peak_ratio(ptr / adt if am else p.road_peak_ratio_default)
        rows.append({"edge": e, "count_id": int(c["count_id"]), "kind": c["kind"],
                     "adt_twoway": round(twoway, 3), "adt_dir": round(twoway / 2.0, 3),
                     "peak_ratio": round(ratio, 6), "count_peak": bool(am)})
    cols = ["edge", "count_id", "kind", "adt_twoway", "adt_dir", "peak_ratio", "count_peak"]
    return pd.DataFrame(rows, columns=cols).set_index("edge")


def _bearing_ok(b_src: float, b_tgt: float, axial: bool) -> bool:
    d = abs(((b_tgt - b_src) + 180.0) % 360.0 - 180.0)
    if axial:
        d = min(d, 180.0 - d)
    return d <= SH_BEARING_MAX_DEG


def propagate(edges: pd.DataFrame, direct: pd.DataFrame, max_m: float) -> pd.DataFrame:
    """Nearest count source along the same street for every edge without a count.

    The search runs through the edges with the same normalised name (midpoint to midpoint network
    distance, segment lengths ``distance_m``) up to ``max_m``. A source is accepted for a target
    edge when: both are not frc <= 1 / ramp edges, or their TomTom streetName is identical; and,
    for a state-highway carriageway count, the target's bearing is within 60 deg of the source
    edge's (compared as axes when either edge is two-way). Nearest accepted source wins (ties:
    lower source edge index). Returns a frame (index = edge index) with src_edge and dist_m.
    """
    n = len(edges)
    core = edges["core"].to_numpy()
    u, v = edges["u"].to_numpy(), edges["v"].to_numpy()
    length = edges["distance_m"].to_numpy(dtype=float)
    frc, ramp, street = edges["frc"].to_numpy(), edges["ramp"].to_numpy(), edges["street_name"].to_numpy()
    bearing, two_way = edges["bearing"].to_numpy(dtype=float), edges["two_way"].to_numpy()
    adj: dict[str, dict[Node, list[tuple[Node, float]]]] = {}
    node_edges: dict[str, dict[Node, list[int]]] = {}
    for i in range(n):
        if core[i] == "":
            continue
        a = adj.setdefault(core[i], {})
        a.setdefault(u[i], []).append((v[i], length[i]))
        a.setdefault(v[i], []).append((u[i], length[i]))
        ne = node_edges.setdefault(core[i], {})
        ne.setdefault(u[i], []).append(i)
        ne.setdefault(v[i], []).append(i)
    is_direct = np.zeros(n, dtype=bool)
    is_direct[direct.index.to_numpy(dtype=int)] = True
    best: dict[int, tuple[float, int]] = {}
    for s in sorted(int(x) for x in direct.index):
        c = core[s]
        if c == "":
            continue
        sh = direct.at[s, "kind"] == "sh_cway"
        strict_s = frc[s] <= 1 or bool(ramp[s])
        dist: dict[Node, float] = {}
        h0 = 0.5 * length[s]
        heap: list[tuple[float, int, Node]] = [(h0, 0, u[s]), (h0, 1, v[s])]
        tie = 2
        while heap:
            d0, _, x = heapq.heappop(heap)
            if x in dist:
                continue
            dist[x] = d0
            for y, w in adj[c].get(x, ()):
                nd = d0 + w
                if nd <= max_m and y not in dist:
                    heapq.heappush(heap, (nd, tie, y))
                    tie += 1
        for x, d0 in dist.items():
            for t in node_edges[c].get(x, ()):
                if is_direct[t]:
                    continue
                dt = d0 + 0.5 * length[t]
                if dt > max_m:
                    continue
                if (strict_s or frc[t] <= 1 or bool(ramp[t])) and street[s] != street[t]:
                    continue
                if sh and not _bearing_ok(bearing[s], bearing[t], bool(two_way[s] or two_way[t])):
                    continue
                cur = best.get(t)
                if cur is None or (dt, s) < cur:
                    best[t] = (dt, s)
    idx = sorted(best)
    return pd.DataFrame({"src_edge": [best[t][1] for t in idx], "dist_m": [best[t][0] for t in idx]},
                        index=pd.Index(idx, name="edge"))


def default_adt(edges: pd.DataFrame,
                direct: pd.DataFrame) -> tuple[dict[tuple[int, int], float], dict[int, float], float]:
    """Median two-way ADT of count edges by (frc, speed band) with >= DEFAULT_MIN_EDGES edges, by frc, overall."""
    d = edges.loc[direct.index, ["frc", "speed_limit"]].copy()
    d["band"] = [speed_band(s) for s in d["speed_limit"]]
    d["adt_twoway"] = direct["adt_twoway"].to_numpy(dtype=float)
    by_band = {(int(f), int(b)): float(g.median()) for (f, b), g in d.groupby(["frc", "band"])["adt_twoway"]
               if len(g) >= DEFAULT_MIN_EDGES}
    by_frc = {int(f): float(g.median()) for f, g in d.groupby("frc")["adt_twoway"]}
    overall = float(d["adt_twoway"].median()) if len(d) else math.nan
    return by_band, by_frc, overall


def edge_values(edges: pd.DataFrame, counts: pd.DataFrame, edge_match: pd.DataFrame,
                cfg: Config) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Per-edge adt_source, count_id, adt_twoway, adt_dir, peak_ratio (counts, propagation, defaults)."""
    p = cfg.prep
    direct = direct_values(edges, counts, edge_match, cfg)
    prop = propagate(edges, direct, float(p.adt_propagate_m))
    by_band, by_frc, overall = default_adt(edges, direct)
    n = len(edges)
    src = np.full(n, "default", dtype=object)
    cid = np.full(n, -1, dtype=int)
    twoway = np.full(n, np.nan)
    ratio = np.full(n, round(clip_peak_ratio(p.road_peak_ratio_default), 6))
    count_peak = np.zeros(n, dtype=bool)
    di = direct.index.to_numpy(dtype=int)
    src[di] = "count"
    cid[di] = direct["count_id"].to_numpy(dtype=int)
    twoway[di] = direct["adt_twoway"].to_numpy(dtype=float)
    ratio[di] = direct["peak_ratio"].to_numpy(dtype=float)
    count_peak[di] = direct["count_peak"].to_numpy(dtype=bool)
    if len(prop):
        pi = prop.index.to_numpy(dtype=int)
        se = prop["src_edge"].to_numpy(dtype=int)
        src[pi] = "propagated"
        cid[pi] = cid[se]
        twoway[pi] = twoway[se]
        ratio[pi] = ratio[se]
        count_peak[pi] = count_peak[se]
    frc, spd = edges["frc"].to_numpy(dtype=int), edges["speed_limit"].to_numpy(dtype=int)
    for i in np.flatnonzero(src == "default"):
        val = by_band.get((int(frc[i]), speed_band(spd[i])), by_frc.get(int(frc[i]), overall))
        if not np.isfinite(val):
            raise ValueError("no matched count to derive a default ADT from")
        twoway[i] = round(val, 3)
    out = pd.DataFrame({"adt_source": src, "count_id": cid, "adt_twoway": twoway,
                        "adt_dir": np.round(twoway / 2.0, 3), "peak_ratio": ratio, "count_peak": count_peak})
    info = {"defaults_by_band": {f"{f}/{b}": round(x, 1) for (f, b), x in sorted(by_band.items())},
            "defaults_by_frc": {str(f): round(x, 1) for f, x in sorted(by_frc.items())},
            "default_overall": round(overall, 1)}
    return out, info


# --------------------------------------------------------------------------- sections


def build_sections(routes: dict[int, Sequence[int]],
                   key: Sequence[Hashable]) -> tuple[list[list[int]], dict[int, list[int]]]:
    """Cut the routes into sections.

    ``routes``: origin_id -> edge indices in travel order (origin first); ``key[e]``: the edge's
    attributes that must agree within a section (frc, speed limit, name, count values). A section
    is a maximal run of consecutive edges with the same key and the same set of origins using
    them. Sections are numbered by first appearance walking origins in origin_id order, then seq.
    Returns (section edge lists in travel order, origin_id -> section ids in travel order).
    Raises ValueError if the result is not a consistent partition of every route.
    """
    users: dict[int, list[int]] = {}
    for oid in sorted(routes):
        for e in routes[oid]:
            users.setdefault(e, []).append(oid)
    set_ids: dict[tuple[int, ...], int] = {}
    eset = {e: set_ids.setdefault(tuple(o), len(set_ids)) for e, o in users.items()}
    sec_of: dict[int, int] = {}
    sections: list[list[int]] = []
    osec: dict[int, list[int]] = {}
    for oid in sorted(routes):
        seq: list[int] = []
        prev_key: Any = None
        prev_sec = -1
        for e in routes[oid]:
            k = (eset[e], key[e])
            if e in sec_of:
                s = sec_of[e]
            elif prev_sec >= 0 and k == prev_key:
                s = prev_sec
                sections[s].append(e)
            else:
                s = len(sections)
                sections.append([e])
            sec_of[e] = s
            if not seq or seq[-1] != s:
                seq.append(s)
            prev_key, prev_sec = k, s
        osec[oid] = seq
    for oid, seq in osec.items():
        flat = [e for s in seq for e in sections[s]]
        if flat != list(routes[oid]) or len(set(seq)) != len(seq):
            raise ValueError(f"sections are not a consistent partition of the route of origin {oid}")
    return sections, osec


def chain_midpoint(geoms: Sequence[BaseGeometry], starts: Sequence[Node]) -> tuple[float, float]:
    """Point at half the length of a chain of segments, each entered from ``starts[i]``."""
    lens = [float(g.length) for g in geoms]
    half = 0.5 * sum(lens)
    acc = 0.0
    for g, st, L in zip(geoms, starts, lens):
        if acc + L >= half or g is geoms[-1]:
            c = shapely.get_coordinates(g)
            fwd = math.hypot(c[0, 0] - st[0], c[0, 1] - st[1]) <= math.hypot(c[-1, 0] - st[0], c[-1, 1] - st[1])
            off = min(max(half - acc, 0.0), L)
            p = g.interpolate(off if fwd else L - off)
            return float(p.x), float(p.y)
        acc += L
    raise ValueError("empty chain")


# --------------------------------------------------------------------------- profile and speeds


def road_profile(values: Sequence[float], start_min: int, n: int = N_MINUTES) -> np.ndarray:
    """r(m) for every minute 0..n-1 (6 decimals) from 15-min bins starting at ``start_min``.

    Value at each bin centre (start + 7.5 + 15 i), linear between centres, constant after the last
    centre, a linear ramp from 0.15 x the first value at minute 300 (05:00) up to the first centre,
    and 0.15 x the first value before minute 300.
    """
    v = [float(x) for x in values]
    c0 = start_min + 7.5
    c_last = c0 + 15.0 * (len(v) - 1)
    low = PROFILE_LOW * v[0]
    out = np.empty(n)
    for m in range(n):
        if m >= c_last:
            r = v[-1]
        elif m >= c0:
            j = int((m - c0) // 15.0)
            t = (m - (c0 + 15.0 * j)) / 15.0
            r = v[j] + (v[j + 1] - v[j]) * t
        elif m >= PROFILE_RAMP_FROM_MIN:
            r = low + (v[0] - low) * (m - PROFILE_RAMP_FROM_MIN) / (c0 - PROFILE_RAMP_FROM_MIN)
        else:
            r = low
        out[m] = float(f"{r:.6f}")
    return out


def speed_factor(v: Any, cap: Any, alpha: float, floor: float) -> np.ndarray:
    """Engine speed factor (SPEC 1.4): x = v / cap, f = 1 / (1 + alpha (x x)(x x)), at least floor."""
    x = np.asarray(v, dtype=float) / np.asarray(cap, dtype=float)
    x4 = (x * x) * (x * x)
    f = 1.0 / (1.0 + alpha * x4)
    return np.where(f < floor, floor, f)


def usual_speed_table(obs_peak: np.ndarray, cap: np.ndarray, r: np.ndarray, alpha: float,
                      floor: float) -> np.ndarray:
    """f[s, m] under usual traffic (v = obs_peak_vph x r[m]) for every section and minute."""
    return speed_factor(np.asarray(obs_peak, dtype=float)[:, None] * np.asarray(r, dtype=float)[None, :],
                        np.asarray(cap, dtype=float)[:, None], alpha, floor)


def route_matrix(osec: dict[int, list[int]], origin_ids: Sequence[int]) -> np.ndarray:
    """Routes as an (n_origins, max_len) int array of section ids, padded with -1."""
    L = max((len(osec[o]) for o in origin_ids), default=0)
    mat = np.full((len(origin_ids), L), -1, dtype=np.int64)
    for i, o in enumerate(origin_ids):
        mat[i, :len(osec[o])] = osec[o]
    return mat


def route_ffsum(route_mat: np.ndarray, ff: np.ndarray) -> np.ndarray:
    """Sum of ff_min over each route, added left to right in seq order (as the engines do)."""
    s = np.zeros(route_mat.shape[0])
    for k in range(route_mat.shape[1]):
        sec = route_mat[:, k]
        act = sec >= 0
        s[act] = s[act] + ff[sec[act]]
    return s


def probe_elapsed(route_mat: np.ndarray, ff: np.ndarray, F: np.ndarray, departures: Sequence[int]) -> np.ndarray:
    """Elapsed minutes to the gate of a probe car (adds no load) per (route, departure).

    Same traversal rule as the engines: entering section s at minute d + floor(el) uses the speed
    factor of that minute; el = el + ff_min_s / f. Minutes past the end of ``F`` use its last column.
    """
    dep = np.asarray(departures, dtype=np.int64)[None, :]
    el = np.zeros((route_mat.shape[0], dep.shape[1]))
    last = F.shape[1] - 1
    for k in range(route_mat.shape[1]):
        sec = route_mat[:, k]
        act = sec >= 0
        if not act.any():
            break
        s = sec[act]
        e = el[act]
        m = np.minimum(dep + np.floor(e).astype(np.int64), last)
        f = F[s[:, None], m]
        el[act] = e + ff[s][:, None] / f
    return el


def weighted_tti(el: np.ndarray, ffsum: np.ndarray, weights: np.ndarray) -> float:
    """Origin-weighted mean over (origin, departure) of el / ffsum."""
    w = np.asarray(weights, dtype=float)
    tti = el / ffsum[:, None]
    return float((w[:, None] * tti).sum() / (w.sum() * el.shape[1]))


def calibrate_k(route_mat: np.ndarray, ff: np.ndarray, weights: np.ndarray, obs_peak: np.ndarray,
                adt_dir: np.ndarray, r: np.ndarray, alpha: float, floor: float, target: float,
                window: tuple[int, int], bounds: tuple[float, float],
                n_iter: int = K_ITERATIONS) -> tuple[float, float, list[tuple[float, float]]]:
    """Bisect k (cap_vph = round(k x adt_dir, 3)) so the weighted TTI over departures in window equals target.

    Returns (k rounded to 6 decimals, TTI at that k, [(k, TTI) probes]). Raises ValueError when
    the target is outside the TTI range of the bracket.
    """
    ffsum = route_ffsum(route_mat, ff)
    deps = list(range(int(window[0]), int(window[1])))
    hist: list[tuple[float, float]] = []

    def tti(k: float) -> float:
        cap = np.round(k * adt_dir, 3)
        F = usual_speed_table(obs_peak, cap, r, alpha, floor)
        val = weighted_tti(probe_elapsed(route_mat, ff, F, deps), ffsum, weights)
        hist.append((k, val))
        return val

    lo, hi = float(bounds[0]), float(bounds[1])
    t_lo, t_hi = tti(lo), tti(hi)
    if not (t_hi <= target <= t_lo):
        raise ValueError(f"TTI target {target} outside the bracket: k={lo} gives {t_lo:.4f}, "
                         f"k={hi} gives {t_hi:.4f} (prep.road_cap_k_bounds)")
    for _ in range(n_iter):
        mid = 0.5 * (lo + hi)
        if tti(mid) > target:
            lo = mid
        else:
            hi = mid
    k = round(0.5 * (lo + hi), 6)
    return k, tti(k), hist


# --------------------------------------------------------------------------- tables


def section_table(edges: pd.DataFrame, vals: pd.DataFrame, sections: list[list[int]],
                  starts: list[list[Node]], osec: dict[int, list[int]], weights: dict[int, float],
                  r: np.ndarray, cfg: Config) -> pd.DataFrame:
    """road_sections rows without cap_vph (set once k is known)."""
    p = cfg.prep
    users: dict[int, list[int]] = {}
    for oid in sorted(osec):
        for s in osec[oid]:
            users.setdefault(s, []).append(oid)
    w_total = sum(weights[o] for o in sorted(weights))
    r_am = 0.0
    for m in range(*AM_VOLUME_WINDOW):
        r_am += float(r[m])
    agents_cars = float(cfg.engine.agents_represented) * float(p.road_commuter_car_share)
    mins = edges["minutes"].to_numpy(dtype=float)
    dist = edges["distance_m"].to_numpy(dtype=float)
    geoms = edges["geometry"].to_numpy()
    src = vals["adt_source"].to_numpy()
    rows = []
    for sid, es in enumerate(sections):
        e0 = es[0]
        ff = 0.0
        km = 0.0
        for e in es:
            ff += mins[e]
            km += dist[e]
        srcs = {src[e] for e in es}
        source = "count" if "count" in srcs else ("propagated" if "propagated" in srcs else "default")
        twoway = float(vals["adt_twoway"].iat[e0])
        ratio = float(vals["peak_ratio"].iat[e0])
        obs = round(p.road_inbound_share * ratio * twoway, 3)
        am_vol = round(obs * r_am / 60.0, 3)
        w_s = sum(weights[o] for o in users[sid])
        exp_c = round(agents_cars * w_s / w_total, 3)
        phi = min(1.0, exp_c / am_vol) if am_vol > 0 else 1.0
        wf = min(1.0, am_vol / exp_c) if exp_c > 0 else 1.0
        xm, ym = chain_midpoint([geoms[e] for e in es], starts[sid])
        rows.append({
            "section_id": sid, "n_seg": len(es), "ff_min": ff, "km": round(km / 1000.0, 4),
            "frc": int(edges["frc"].iat[e0]), "speed_limit": int(edges["speed_limit"].iat[e0]),
            "street_name": str(edges["street_name"].iat[e0]), "adt_twoway": twoway,
            "adt_dir": float(vals["adt_dir"].iat[e0]), "adt_source": source, "peak_ratio": ratio,
            "cap_vph": math.nan, "obs_peak_vph": obs, "am_volume_veh": am_vol,
            "expected_commuter_veh": exp_c, "phi": round(phi, 6), "bg_peak_vph": round(obs * (1.0 - phi), 3),
            "w_factor": round(wf, 6), "n_origins": len(users[sid]),
            "x_mid": round(xm, 1), "y_mid": round(ym, 1),
        })
    return pd.DataFrame(rows, columns=list(SECTIONS_COLUMNS))


def section_keys(edges: pd.DataFrame, vals: pd.DataFrame) -> list[Hashable]:
    """Per-edge section key: frc, speed limit, normalised name, count values, observed/default."""
    return [(int(f), int(s), c, float(a), float(d), float(pr), src == "default")
            for f, s, c, a, d, pr, src in zip(edges["frc"], edges["speed_limit"], edges["core"],
                                               vals["adt_twoway"], vals["adt_dir"], vals["peak_ratio"],
                                               vals["adt_source"])]


# --------------------------------------------------------------------------- outputs


def _write_text(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, lineterminator="\n")


def _file_info(path: Path) -> dict[str, Any]:
    st = path.stat()
    try:
        rel = Path(os.path.relpath(path, ROOT)).as_posix()
    except ValueError:
        rel = path.as_posix()
    return {"path": rel, "bytes": int(st.st_size),
            "modified_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def _q(s: pd.Series | np.ndarray, qs: Sequence[float] = (0.0, 0.1, 0.5, 0.9, 1.0), fmt: str = "{:.3f}") -> str:
    a = np.asarray(s, dtype=float)
    return " | ".join(fmt.format(float(np.quantile(a, q))) for q in qs) if len(a) else " | ".join("-" for _ in qs)


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def render_report(cfg: Config, sec: pd.DataFrame, osec: dict[int, list[int]], origins: pd.DataFrame,
                  meta: dict[str, Any], r: np.ndarray, tti_corr: dict[int, float],
                  corridors: pd.DataFrame) -> str:
    """Markdown road report: coverage, k, TTI, V/C, commuter shares, busiest sections, assumptions."""
    p, rd = cfg.prep, cfg.road
    w = dict(zip(origins["origin_id"].astype(int), origins["weight"].astype(float)))
    w_total = sum(w.values())
    # traversal minutes: section ff_min x origin weight of its users
    trav = np.zeros(len(sec))
    for oid, seq in osec.items():
        for s in seq:
            trav[s] += w[oid]
    trav_min = trav * sec["ff_min"].to_numpy(dtype=float)
    sec = sec.assign(trav_min=trav_min)
    L: list[str] = ["# Cordon-Lite road congestion inputs (prep.build_roads)", ""]
    m = meta
    L += ["## Summary", "",
          f"- Sections: {len(sec)} on the pre-gate parts of {len(osec)} origin paths "
          f"({int(sec['n_seg'].sum())} graph edges, {sec['km'].sum():.1f} km, "
          f"{sec['ff_min'].sum():.1f} free-flow minutes); {m['n_origin_section_rows']} origin-section rows, "
          f"{np.mean([len(s) for s in osec.values()]):.1f} sections per origin on average "
          f"(max {max(len(s) for s in osec.values())}).",
          f"- The rebuilt prep paths reproduce `data/origins.csv` exactly (gate_id, corridor_id, "
          f"free-flow minutes); per-origin sum of section ff_min minus fftt_to_gate_min: max abs "
          f"{m['checks']['max_abs_ffsum_minus_fftt_to_gate']:.2e} min.",
          f"- Capacity factor k = {m['k']:.6f} (cap_vph = k x adt_dir), bisected in "
          f"{list(p.road_cap_k_bounds)} so that the origin-weighted travel time index of departures "
          f"{_hhmm(p.road_tti_window[0])}-{_hhmm(p.road_tti_window[1] - 1)} under usual traffic is "
          f"{p.road_tti_target} (achieved {m['tti_achieved']:.4f}).",
          f"- Usual-traffic V/C is 2 x {p.road_inbound_share} x peak_ratio x r(m) / k on every section; "
          f"with the default peak ratio {p.road_peak_ratio_default} that is "
          f"{2 * p.road_inbound_share * p.road_peak_ratio_default / m['k']:.2f} x r(m).",
          ""]
    L += ["## Travel time index under usual traffic", "",
          "Probe car on each origin's pre-gate route (adds no load), one departure per minute, "
          "origin-weighted mean of (time to the gate) / (free-flow time to the gate).", "",
          "| departures | TTI |", "|---|---|"]
    for lab, a, b in TTI_HOURS:
        L.append(f"| {_hhmm(a)}-{_hhmm(b - 1)} | {m['tti_by_hour'][lab]:.3f} |")
    L.append(f"| {_hhmm(TTI_PROBE_MIN)} only | {m['tti_0730']:.3f} |")
    L += ["", "By corridor (departures in the calibration window):", "",
          "| corridor | name | origins | TTI |", "|---|---|---|---|"]
    for c in corridors.itertuples():
        n = int((origins["corridor_id"] == c.corridor_id).sum())
        L.append(f"| {c.corridor_id} | {c.name} | {n} | {tti_corr.get(int(c.corridor_id), math.nan):.3f} |")
    L += ["", "## Count matching", "",
          f"- Count points: {m['counts']['n_points']} in `{p.adt_geojson}`, {m['counts']['n_adt_positive']} "
          f"with adt > 0 (local {m['counts']['n_local']}, SH carriageway {m['counts']['n_sh_cway']}, "
          f"SH ramp {m['counts']['n_sh_ramp']}, SH without direction {m['counts']['n_sh_other']}, not used; "
          f"{m['counts']['n_sh_ramp_bus']} SH ramp records of bus-only ramps or busways (named so, or under "
          f"{BUS_RAMP_MAX_CAR_PCT:g}% cars) are not used).",
          f"- Matched to a same-name graph edge within {p.adt_match_m:g} m and used: {m['counts']['n_matched']} "
          f"(local {m['counts']['matched_local']}, SH carriageway {m['counts']['matched_sh_cway']}, "
          f"SH ramp {m['counts']['matched_sh_ramp']}). Not used: {m['counts']['n_stale']} matched AT counts "
          f"below {STALE_ADT_RATIO:g} of a more recent count of the same street within {p.adt_propagate_m:g} m "
          "(stale or misplaced counts). Graph edges holding a count: "
          f"{m['edges']['count']}; propagated within {p.adt_propagate_m:g} m: {m['edges']['propagated']}; "
          f"default: {m['edges']['default']} (of {m['edges']['total']} graph edges).",
          "- Sections take adt_source 'count' when one of their edges holds a count, 'propagated' "
          "when their values come from a count on the same street, else 'default' (median two-way "
          "ADT of count edges with the same frc and speed band, else frc).", ""]
    L += ["Coverage by frc (share of sections | share of origin-weighted pre-gate free-flow minutes):", "",
          "| frc | sections | count | propagated | default | minutes share of all | count | propagated | default |",
          "|---|---|---|---|---|---|---|---|---|"]
    tm_all = sec["trav_min"].sum()
    for f, g in sec.groupby("frc"):
        tm = g["trav_min"].sum()
        sh = [(g["adt_source"] == s).mean() for s in ADT_SOURCES]
        shm = [g.loc[g["adt_source"] == s, "trav_min"].sum() / tm for s in ADT_SOURCES]
        L.append(f"| {f} | {len(g)} | " + " | ".join(f"{x:.1%}" for x in sh) +
                 f" | {tm / tm_all:.1%} | " + " | ".join(f"{x:.1%}" for x in shm) + " |")
    sh = [(sec["adt_source"] == s).mean() for s in ADT_SOURCES]
    shm = [sec.loc[sec["adt_source"] == s, "trav_min"].sum() / tm_all for s in ADT_SOURCES]
    L.append(f"| all | {len(sec)} | " + " | ".join(f"{x:.1%}" for x in sh) + " | 100.0% | " +
             " | ".join(f"{x:.1%}" for x in shm) + " |")
    pk = m["peak_ratio"]
    L += ["", f"- AM peak ratio from a count with an AM peak hour (06:00-09:45): {pk['sections_from_count']} "
          f"sections ({pk['minutes_share_from_count']:.1%} of origin-weighted pre-gate minutes); the others "
          f"use {p.road_peak_ratio_default}. Peak ratio over sections (min | p10 | median | p90 | max): "
          f"{_q(sec['peak_ratio'])}.", ""]
    L += ["## V/C under usual traffic", "",
          "V/C = obs_peak_vph x r(m) / cap_vph (background plus usual commuters, what the counts say). "
          "Median over sections and origin-weighted mean over traversal minutes.", "",
          "| frc | sections | median 07:30 | median 08:15 | weighted 07:30 | weighted 08:15 |",
          "|---|---|---|---|---|---|"]
    for f, g in sec.groupby("frc"):
        vc = {mm: g["obs_peak_vph"] * r[mm] / g["cap_vph"] for mm in VC_PROBE_MIN}
        wt = g["trav_min"]
        L.append(f"| {f} | {len(g)} | " + " | ".join(f"{vc[mm].median():.2f}" for mm in VC_PROBE_MIN) + " | " +
                 " | ".join(f"{(vc[mm] * wt).sum() / wt.sum():.2f}" for mm in VC_PROBE_MIN) + " |")
    L += ["", f"Speed factor f = 1 / (1 + {rd.bpr_alpha:g} (V/C)^{rd.bpr_beta}), at least {rd.speed_floor:g}; "
          f"time on a section = ff_min / f.", ""]
    low = sec["cap_vph"] < LOW_CAP_VPH
    low_names = ", ".join(sorted(set(sec.loc[low, "street_name"].astype(str)))[:5])
    L += ["## Commuter share of the counted volume", "",
          f"expected_commuter_veh = {cfg.engine.agents_represented:g} x {p.road_commuter_car_share:g} x "
          "(origin weight using the section) / (all origin weight); phi = min(1, expected / observed "
          "06:00-10:00 volume); bg_peak_vph = obs_peak_vph x (1 - phi); w_factor = min(1, observed / "
          "expected).", "",
          "| quantity | min | p10 | median | p90 | max |", "|---|---|---|---|---|---|",
          f"| phi | {_q(sec['phi'])} |", f"| w_factor | {_q(sec['w_factor'])} |",
          f"| expected_commuter_veh | {_q(sec['expected_commuter_veh'], fmt='{:.0f}')} |",
          f"| am_volume_veh | {_q(sec['am_volume_veh'], fmt='{:.0f}')} |", "",
          f"- Sections where the commuters reach the whole counted volume (phi = 1, w_factor < 1): "
          f"{int((sec['phi'] >= 1).sum())} ({(sec['phi'] >= 1).mean():.1%} of sections, "
          f"{sec.loc[sec['phi'] >= 1, 'trav_min'].sum() / tm_all:.1%} of origin-weighted pre-gate minutes).",
          f"- Origin-weighted mean phi over pre-gate minutes: {(sec['phi'] * sec['trav_min']).sum() / tm_all:.3f}.",
          f"- Data check: {int(low.sum())} sections have cap_vph below {LOW_CAP_VPH:g} veh/h (very small "
          f"counts, e.g. {low_names or 'none'}); {sec.loc[low, 'trav_min'].sum() / tm_all:.2%} of "
          "origin-weighted pre-gate minutes.", ""]
    L += ["## Sections used by the most origins", "",
          "| section | street | frc | speed | ff_min | origins | adt_twoway | source | peak_ratio | phi | w_factor | V/C 08:15 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    top = sec.sort_values(["n_origins", "section_id"], ascending=[False, True], kind="mergesort").head(10)
    for t in top.itertuples():
        vc = t.obs_peak_vph * r[VC_PROBE_MIN[1]] / t.cap_vph
        L.append(f"| {t.section_id} | {t.street_name or '(unnamed)'} | {t.frc} | {t.speed_limit} | {t.ff_min:.2f} | "
                 f"{t.n_origins} | {t.adt_twoway:.0f} | {t.adt_source} | {t.peak_ratio:.3f} | {t.phi:.3f} | "
                 f"{t.w_factor:.3f} | {vc:.2f} |")
    L += ["", "## Assumptions", "",
          "- [SPEC] Routes are the prep shortest free-flow paths on the undirected graph (no rerouting); "
          "only the pre-gate part is congested; the gate-to-destination leg stays free flow.",
          f"- [DATA] Two-way ADT from the AT/NZTA count points (`{p.adt_geojson}`): 7-day averages of mixed "
          "vintage (motorway counts mostly 2016); AT counts are two-way totals unless the record's name "
          "carries a direction (EASTBOUND, EAST BOUND, ...); state-highway records count one carriageway or ramp.",
          f"- [A] A count matches the nearest graph edge with the same normalised street name within "
          f"{p.adt_match_m:g} m (state-highway carriageway records by route to the motorway names, ramp records "
          "to ramp or unnamed edges); several counts on one edge keep the most recent; SH records without a "
          "direction suffix and SH ramp records of bus-only ramps or busways (named so, or under "
          f"{BUS_RAMP_MAX_CAR_PCT:g}% cars) are not used; an AT count below "
          f"{STALE_ADT_RATIO:g} of a more recent count of the same street within {p.adt_propagate_m:g} m "
          "(straight line) is not used.",
          f"- [A] A count holds along the same street up to {p.adt_propagate_m:g} m through the network "
          "(motorway, frc 1 and ramp edges need the identical TomTom name; SH carriageway counts only on edges "
          f"within {SH_BEARING_MAX_DEG:g} deg of their bearing); nearest source wins. Other edges take the "
          f"median two-way ADT of count edges with the same frc and speed band (at least {DEFAULT_MIN_EDGES} "
          "edges), else frc.",
          "- [SPEC, A] Direction: a count of one carriageway or direction (SH -I/-D, SH ramp, AT count whose "
          "name carries a direction) is directional (adt_dir = adt, two-way equivalent 2 x adt); any other AT "
          "count is a two-way total (adt_dir = adt / 2), also on TomTom edges without a reversed twin, which "
          "are mostly carriageways of divided roads rather than one-way streets.",
          f"- [A] Inbound share of the two-way AM peak-hour flow {p.road_inbound_share}; AM peak ratio "
          f"peaktraffic / adt where the count's peak hour starts 06:00-09:45, else {p.road_peak_ratio_default} "
          f"[DATA]; clipped to {list(PEAK_RATIO_CLIP)}.",
          f"- [A] Time profile r(m): 15-min bins from {_hhmm(p.road_profile_start_min)} {list(p.road_profile)} "
          "(peak timing from the counts [DATA], shape assumed), linear between bin centres, ramp to "
          f"{PROFILE_LOW} x the first value at 05:00.",
          f"- [A] Capacity = k x directional ADT (SSC2026 rule) with k calibrated to the TomTom Traffic Index "
          f"[DATA]: Auckland 2025 morning rush-hour congestion level 71.4% => TTI {p.road_tti_target} "
          "(https://www.tomtom.com/traffic-index/auckland-traffic/).",
          f"- [A] BPR alpha {rd.bpr_alpha:g}, beta {rd.bpr_beta}, speed floor {rd.speed_floor:g} (SSC2026); "
          f"commuter flow counts the cars that entered in the last {rd.flow_window_min} min.",
          f"- [A] Commuters are netted out of the counts with car share {p.road_commuter_car_share:g} of "
          f"{cfg.engine.agents_represented:g} represented vehicles; where all-or-nothing routing puts more "
          "commuter cars on a section than counted, their weight w_factor is reduced instead.",
          "- [A] Routing is undirected: many motorway traversals follow the opposite carriageway's geometry; "
          "congestion uses the inbound flow at the location, so the values do not depend on which "
          "carriageway is drawn.", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------- main


def run_build_roads(cfg: Config, out_dir: Path | None = None) -> dict[str, Any]:
    """Run the road prep and write the six outputs; returns tables and summary numbers."""
    p, rd = cfg.prep, cfg.road
    data_dir = cfg.resolve_path(cfg.run.data_dir)
    out_dir = Path(out_dir) if out_dir is not None else data_dir
    ref_path = data_dir / "origins.csv"
    ref = pd.read_csv(ref_path)
    roads = load_roads_shp(cfg)
    cordon, cordon_path = load_cordon_any(cfg)
    prep = reproduce_prep(cfg, roads, cordon)
    check_origins(prep["origins_frame"], ref)
    G, dest, origins, paths = prep["G"], prep["dest"], prep["origins"], prep["paths"]

    edges = edge_table(G, roads, cfg)
    eid = edge_index(edges)
    routes_n = pregate_routes(G, dest, origins, cordon, p.gate_rule, eid)
    routes = {o: [e for e, _ in rt] for o, rt in routes_n.items()}
    counts, cstats = load_counts(cfg)
    point_match, edge_match = match_counts(edges, counts, p.adt_match_m, stale_m=p.adt_propagate_m)
    vals, dinfo = edge_values(edges, counts, edge_match, cfg)

    sections, osec = build_sections(routes, section_keys(edges, vals))
    start_of = {e: n for rt in routes_n.values() for e, n in rt}
    starts = [[start_of[e] for e in es] for es in sections]
    weights = dict(zip(ref["origin_id"].astype(int), ref["weight"].astype(float)))
    r = road_profile(p.road_profile, p.road_profile_start_min)
    sec = section_table(edges, vals, sections, starts, osec, weights, r, cfg)

    # check: per origin, sections add up to the unrounded free-flow time to the gate
    ff = sec["ff_min"].to_numpy(dtype=float)
    oids = sorted(osec)
    rmat = route_matrix(osec, oids)
    ffsum = route_ffsum(rmat, ff)
    fftt = paths.set_index("origin_id").loc[oids, "fftt_to_gate_min"].to_numpy(dtype=float)
    fftt_csv = ref.set_index("origin_id").loc[oids, "fftt_to_gate_min"].to_numpy(dtype=float)
    d_unr = float(np.abs(ffsum - fftt).max())
    d_csv = float(np.abs(ffsum - fftt_csv).max())
    if d_unr > 1e-3 or d_csv > 1e-3:
        raise ValueError(f"section free-flow minutes do not add up to fftt_to_gate_min "
                         f"(max diff {d_unr:.3g} unrounded, {d_csv:.3g} against origins.csv)")

    w_arr = np.array([weights[o] for o in oids])
    obs = sec["obs_peak_vph"].to_numpy(dtype=float)
    adt_dir = sec["adt_dir"].to_numpy(dtype=float)
    k, tti_k, hist = calibrate_k(rmat, ff, w_arr, obs, adt_dir, r, rd.bpr_alpha, rd.speed_floor,
                                 p.road_tti_target, tuple(p.road_tti_window), tuple(p.road_cap_k_bounds))
    sec["cap_vph"] = np.round(k * adt_dir, 3)
    F = usual_speed_table(obs, sec["cap_vph"].to_numpy(dtype=float), r, rd.bpr_alpha, rd.speed_floor)
    deps = list(range(TTI_HOURS[0][1], TTI_HOURS[-1][2]))
    el = probe_elapsed(rmat, ff, F, deps)
    tti_hour = {lab: round(weighted_tti(el[:, a - deps[0]:b - deps[0]], ffsum, w_arr), 6) for lab, a, b in TTI_HOURS}
    tti_0730 = round(weighted_tti(el[:, [TTI_PROBE_MIN - deps[0]]], ffsum, w_arr), 6)
    win = slice(p.road_tti_window[0] - deps[0], p.road_tti_window[1] - deps[0])
    corr = ref.set_index("origin_id").loc[oids, "corridor_id"].to_numpy(dtype=int)
    tti_corr = {int(c): weighted_tti(el[corr == c, win], ffsum[corr == c], w_arr[corr == c])
                for c in sorted(set(corr.tolist()))}

    # tables
    os_rows = [(o, i, s) for o in oids for i, s in enumerate(osec[o])]
    origin_sections = pd.DataFrame(os_rows, columns=list(ORIGIN_SECTIONS_COLUMNS))
    seg_ids = edges["segment_id"].to_numpy()
    ss_rows = [(sid, i, seg_ids[e]) for sid, es in enumerate(sections) for i, e in enumerate(es)]
    section_segments = pd.DataFrame(ss_rows, columns=list(SECTION_SEGMENTS_COLUMNS))

    # meta
    on_route = sorted({e for es in sections for e in es})
    src_e = vals["adt_source"].to_numpy()
    trav = np.zeros(len(sec))
    for o in oids:
        for s in osec[o]:
            trav[s] += weights[o]
    trav_min = trav * ff
    from_count = (sec["adt_source"] != "default").to_numpy() & np.array(
        [bool(vals["count_peak"].iat[es[0]]) for es in sections])
    used = point_match[~point_match["stale"].astype(bool)]
    mk = counts["kind"].to_numpy()[used["ci"].to_numpy(dtype=int)] if len(used) else np.array([])
    meta: dict[str, Any] = {
        "created_by": "prep.build_roads",
        "k": k, "k_bounds": list(p.road_cap_k_bounds), "k_iterations": K_ITERATIONS,
        "tti_target": p.road_tti_target, "tti_achieved": round(tti_k, 6), "tti_window": list(p.road_tti_window),
        "tti_by_hour": tti_hour, "tti_0730": tti_0730,
        "tti_by_corridor": {str(c): round(v, 6) for c, v in tti_corr.items()},
        "bpr_alpha": rd.bpr_alpha, "bpr_beta": rd.bpr_beta, "speed_floor": rd.speed_floor,
        "flow_window_min": rd.flow_window_min,
        "road_inbound_share": p.road_inbound_share, "road_peak_ratio_default": p.road_peak_ratio_default,
        "peak_ratio_clip": list(PEAK_RATIO_CLIP), "road_commuter_car_share": p.road_commuter_car_share,
        "agents_represented": cfg.engine.agents_represented,
        "adt_match_m": p.adt_match_m, "adt_propagate_m": p.adt_propagate_m,
        "road_profile_start_min": p.road_profile_start_min, "road_profile": list(p.road_profile),
        "n_sections": len(sec), "n_origins": len(oids), "n_origin_section_rows": len(origin_sections),
        "n_section_segments": len(section_segments),
        "sections_by_source": {s: int((sec["adt_source"] == s).sum()) for s in ADT_SOURCES},
        "pregate_edges_by_source": {s: int(sum(src_e[e] == s for e in on_route)) for s in ADT_SOURCES},
        "edges": {"total": len(edges), **{s: int((src_e == s).sum()) for s in ADT_SOURCES}},
        "counts": {**cstats, "n_matched": int(len(used)), "n_stale": int(len(point_match) - len(used)),
                   **{f"matched_{kd}": int((mk == kd).sum()) for kd in ("local", "sh_cway", "sh_ramp")}},
        "defaults_adt_twoway": dinfo,
        "peak_ratio": {"sections_from_count": int(from_count.sum()),
                       "minutes_share_from_count": round(float(trav_min[from_count].sum() / trav_min.sum()), 6)},
        "checks": {"origins_reproduced": True,
                   "max_abs_ffsum_minus_fftt_to_gate": d_unr,
                   "max_abs_ffsum_minus_origins_csv": d_csv},
        "cordon_source": _file_info(cordon_path)["path"],
        "inputs": {
            "roads_shp": _file_info(cfg.resolve_path(p.roads_shp)),
            "roads_dbf": _file_info(cfg.resolve_path(p.roads_shp).with_suffix(".dbf")),
            "adt_geojson": _file_info(cfg.resolve_path(p.adt_geojson)),
            "cordon": _file_info(cordon_path),
            "origins_csv": _file_info(ref_path),
        },
        "k_probes": [[round(a, 9), round(b, 6)] for a, b in hist],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "road_sections.csv", sec[list(SECTIONS_COLUMNS)])
    _write_csv(out_dir / "origin_sections.csv", origin_sections)
    _write_csv(out_dir / "section_segments.csv", section_segments)
    _write_text(out_dir / "road_profile.csv",
                "minute,r\n" + "".join(f"{m},{x:.6f}\n" for m, x in enumerate(r)))
    _write_text(out_dir / "road_meta.json", json.dumps(meta, indent=2) + "\n")
    _write_text(out_dir / "road_report.md",
                render_report(cfg, sec, osec, ref, meta, r, tti_corr, prep["corridors"]) + "\n")
    return {"sections": sec, "origin_sections": origin_sections, "section_segments": section_segments,
            "profile": r, "meta": meta, "edges": edges, "values": vals, "osec": osec}


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="Cordon-Lite road congestion inputs (sections, counts, k)")
    ap.add_argument("--config", default=None, help="path to config.toml")
    ap.add_argument("--out-dir", default=None, help="output folder (default: run.data_dir)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    out = Path(args.out_dir) if args.out_dir else None
    res = run_build_roads(cfg, out)
    m = res["meta"]
    print(f"sections {m['n_sections']}, origin-section rows {m['n_origin_section_rows']}, "
          f"segments {m['n_section_segments']}")
    print("sections by adt_source:", m["sections_by_source"])
    print(f"k {m['k']:.6f}, TTI {m['tti_achieved']:.4f} (target {m['tti_target']}), by hour {m['tti_by_hour']}, "
          f"07:30 {m['tti_0730']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
