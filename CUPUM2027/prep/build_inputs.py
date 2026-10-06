"""Offline network preparation (run once): TomTom roads -> origins, gates, corridors.

Owner: prep builder. See INTERFACES.md. Outputs into cordon_lite/data/.

    python -m prep.build_inputs [--config config.toml] [--out-dir data]

Demand is city-wide, simulation is gate-bottleneck: every sampled origin gets one shortest
free-flow path into the cordon (one single-source Dijkstra from the destination node on the
undirected TomTom graph), the gate it enters through and the free-flow time split at that gate.

Public API:
    load_cordon(cfg) -> BaseGeometry          # unary_union of named SA3 polygons, buffer(0)
    load_roads(cfg) -> gpd.GeoDataFrame
    build_graph(roads, cfg) -> nx.Graph       # giant component
    destination_node(G, cordon) -> tuple[float, float]
    candidate_origins(G, roads, cordon, cfg) -> pd.DataFrame   # node, x_nztm, y_nztm, weight
    sample_origins(candidates, cfg) -> pd.DataFrame
    trace_paths(G, dest, origins, cordon) -> pd.DataFrame
    gate_table(paths, roads, cordon) -> pd.DataFrame
    group_corridors(gates, cordon, cfg) -> tuple[pd.DataFrame, pd.DataFrame]
    write_outputs(...) -> None
    main(argv=None) -> int
"""

from __future__ import annotations

import argparse
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from cordonlite.config import Config, load_config, stream

Node = tuple[float, float]

ORIGINS_COLUMNS: tuple[str, ...] = (
    "origin_id", "x_nztm", "y_nztm", "weight", "corridor_id", "gate_id",
    "fftt_to_gate_min", "fftt_gate_to_dest_min", "path_km",
)
GATES_COLUMNS: tuple[str, ...] = (
    "gate_id", "corridor_id", "segment_id", "streetName", "frc", "speedLimit",
    "x_nztm", "y_nztm", "n_origins",
)
CORRIDORS_COLUMNS: tuple[str, ...] = (
    "corridor_id", "name", "n_gates", "capacity_vph_raw", "bearing_deg",
    "x_nztm", "y_nztm", "main_streets",
)
COMPASS8: tuple[str, ...] = ("North", "North-east", "East", "South-east",
                             "South", "South-west", "West", "North-west")


# --------------------------------------------------------------------------- geometry helpers


def bearing_deg(cx: float, cy: float, x: float | np.ndarray, y: float | np.ndarray) -> Any:
    """Compass bearing (degrees clockwise from grid north, 0..360) from (cx, cy) to (x, y)."""
    b = np.degrees(np.arctan2(np.asarray(x) - cx, np.asarray(y) - cy)) % 360.0
    return float(b) if np.ndim(b) == 0 else b


def compass8(bearing: float) -> str:
    """Eight-point compass name for a bearing in degrees."""
    return COMPASS8[int(((bearing % 360.0) + 22.5) // 45.0) % 8]


def clean_street_name(name: str) -> str:
    """Readable label for corridor names: 'Exit 429B Wellesley Street' -> 'Wellesley Street ramp'."""
    import re
    m = re.match(r"^(Exit|Entry)\s+\S+\s+(.+)$", str(name).strip())
    return f"{m.group(2)} ramp" if m else str(name).strip()


def circular_mean_deg(bearings: np.ndarray, weights: np.ndarray | None = None) -> float:
    """Weighted circular mean of bearings in degrees (0..360)."""
    b = np.radians(np.asarray(bearings, dtype=float))
    w = np.ones_like(b) if weights is None else np.asarray(weights, dtype=float)
    return float(np.degrees(np.arctan2((w * np.sin(b)).sum(), (w * np.cos(b)).sum())) % 360.0)


def inside_mask(cordon: BaseGeometry, xy: np.ndarray) -> np.ndarray:
    """Boolean mask of points strictly inside or on the cordon polygon."""
    xy = np.asarray(xy, dtype=float).reshape(-1, 2)
    shapely.prepare(cordon)
    return np.asarray(shapely.intersects_xy(cordon, xy[:, 0], xy[:, 1]), dtype=bool)


# --------------------------------------------------------------------------- loading


def load_cordon(cfg: Config) -> BaseGeometry:
    """Union of the configured SA3 polygons, made valid with buffer(0)."""
    p = cfg.prep
    gdf = gpd.read_file(cfg.resolve_path(p.cordon_gpkg))
    if gdf.crs is not None and gdf.crs.to_epsg() != p.crs_epsg:
        gdf = gdf.to_crs(epsg=p.crs_epsg)
    names = set(gdf[p.cordon_name_field].astype(str))
    missing = [n for n in p.cordon_names if n not in names]
    if missing:
        raise ValueError(f"cordon names not found in {p.cordon_gpkg}: {missing}")
    sel = gdf[gdf[p.cordon_name_field].isin(p.cordon_names)]
    geom = unary_union([shapely.make_valid(g) for g in sel.geometry]).buffer(0)
    if geom.is_empty:
        raise ValueError("cordon geometry is empty")
    return geom


def load_roads(cfg: Config) -> gpd.GeoDataFrame:
    """TomTom major roads, EPSG:2193, index reset to 0..n-1 (the row id used by the graph)."""
    p = cfg.prep
    roads = gpd.read_file(cfg.resolve_path(p.roads_gpkg), layer=p.roads_layer)
    if roads.crs is not None and roads.crs.to_epsg() != p.crs_epsg:
        roads = roads.to_crs(epsg=p.crs_epsg)
    roads = roads[roads.geometry.notna() & ~roads.geometry.is_empty].reset_index(drop=True)
    roads["streetName"] = roads["streetName"].fillna("").astype(str)
    roads["frc"] = roads["frc"].astype(int)
    return roads


# --------------------------------------------------------------------------- graph


def edge_minutes(distance_m: float | np.ndarray, speed_kmh: float | np.ndarray,
                 ff_factor: float = 1.0) -> Any:
    """Free-flow minutes = distance / (speed km/h * 1000 / 60) * ff_factor."""
    return np.asarray(distance_m, dtype=float) / (np.asarray(speed_kmh, dtype=float) * 1000.0 / 60.0) * ff_factor


def round_xy(x: np.ndarray, y: np.ndarray, r: float) -> tuple[np.ndarray, np.ndarray]:
    """Round coordinates to a grid of r metres."""
    return np.round(np.asarray(x) / r) * r, np.round(np.asarray(y) / r) * r


def build_graph(roads: gpd.GeoDataFrame, cfg: Config) -> nx.Graph:
    """Undirected graph on rounded segment endpoints; keeps the giant component.

    Edge attributes: minutes, segment_id, frc, speed_limit, street_name, distance_m, row
    (row = positional index in ``roads``). Parallel segments keep the fastest one.
    """
    r = cfg.prep.node_round_m
    geoms = roads.geometry.values
    p0 = shapely.get_coordinates(shapely.get_point(geoms, 0))
    p1 = shapely.get_coordinates(shapely.get_point(geoms, -1))
    x0, y0 = round_xy(p0[:, 0], p0[:, 1], r)
    x1, y1 = round_xy(p1[:, 0], p1[:, 1], r)
    dist = roads["distance"].to_numpy(dtype=float)
    spd = roads["speedLimit"].to_numpy(dtype=float)
    mins = edge_minutes(dist, spd, cfg.prep.ff_factor)
    seg = roads["newSegmentId"].astype(str).to_numpy()
    frc = roads["frc"].to_numpy(dtype=int)
    name = roads["streetName"].to_numpy()
    G = nx.Graph()
    for i in range(len(roads)):
        u = (float(x0[i]), float(y0[i]))
        v = (float(x1[i]), float(y1[i]))
        if u == v:
            continue
        if G.has_edge(u, v) and G.edges[u, v]["minutes"] <= mins[i]:
            continue
        G.add_edge(u, v, minutes=float(mins[i]), segment_id=seg[i], frc=int(frc[i]),
                   speed_limit=float(spd[i]), street_name=str(name[i]),
                   distance_m=float(dist[i]), row=int(i))
    giant = max(nx.connected_components(G), key=len)
    return G.subgraph(giant).copy()


def node_array(G: nx.Graph) -> tuple[list[Node], np.ndarray]:
    """Nodes in a fixed (sorted) order and their coordinates as an (n, 2) array."""
    nodes = sorted(G.nodes)
    return nodes, np.array(nodes, dtype=float).reshape(-1, 2)


def destination_node(G: nx.Graph, cordon: BaseGeometry) -> Node:
    """Graph node inside the cordon nearest to the cordon centroid."""
    nodes, xy = node_array(G)
    ins = inside_mask(cordon, xy)
    if not ins.any():
        raise ValueError("no graph node inside the cordon")
    c = cordon.centroid
    d2 = (xy[:, 0] - c.x) ** 2 + (xy[:, 1] - c.y) ** 2
    d2[~ins] = np.inf
    return nodes[int(np.argmin(d2))]


# --------------------------------------------------------------------------- origins


def local_road_length(points_xy: np.ndarray, roads: gpd.GeoDataFrame, local_frc: Sequence[int],
                      radius_m: float) -> np.ndarray:
    """Length (m) of local-class road whose segment midpoint lies within radius of each point."""
    loc = roads[roads["frc"].isin(list(local_frc))]
    if len(loc) == 0:
        return np.zeros(len(points_xy))
    mid = shapely.get_coordinates(shapely.line_interpolate_point(loc.geometry.values, 0.5, normalized=True))
    lens = loc["distance"].to_numpy(dtype=float)
    tree = cKDTree(mid)
    idx = tree.query_ball_point(np.asarray(points_xy, dtype=float), r=radius_m)
    return np.array([lens[i].sum() if len(i) else 0.0 for i in idx])


def candidate_origins(G: nx.Graph, roads: gpd.GeoDataFrame, cordon: BaseGeometry,
                      cfg: Config) -> pd.DataFrame:
    """Candidate origin nodes outside the cordon with their demand weight.

    Proxy (default): weight = local (frc in local_frc) road length within density_radius_m [A].
    Nodes whose incident edges are all motorway (frc 0) are excluded [A]: trips do not start
    on a motorway carriageway. With ``prep.od_csv`` set, each SA2 point is snapped to the
    nearest such node and weight = commuters_to_cordon (summed per node).
    """
    nodes, xy = node_array(G)
    outside = ~inside_mask(cordon, xy)
    non_motorway = np.array([any(d["frc"] != 0 for _, _, d in G.edges(n, data=True)) for n in nodes])
    keep = outside & non_motorway
    nodes_k = [n for n, k in zip(nodes, keep) if k]
    xy_k = xy[keep]
    if cfg.prep.od_csv:
        od = pd.read_csv(cfg.resolve_path(cfg.prep.od_csv))
        need = {"sa2_code", "x_nztm", "y_nztm", "commuters_to_cordon"}
        if not need.issubset(od.columns):
            raise ValueError(f"od_csv needs columns {sorted(need)}")
        _, j = cKDTree(xy_k).query(od[["x_nztm", "y_nztm"]].to_numpy(dtype=float))
        w = np.zeros(len(nodes_k))
        np.add.at(w, j, od["commuters_to_cordon"].to_numpy(dtype=float))
    else:
        w = local_road_length(xy_k, roads, cfg.prep.local_frc, cfg.prep.density_radius_m)
    df = pd.DataFrame({"node": nodes_k, "x_nztm": xy_k[:, 0], "y_nztm": xy_k[:, 1], "weight": w})
    return df[df["weight"] > 0].reset_index(drop=True)


def sample_origins(candidates: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Weighted sample of n_origin_points candidates on stream(seed, "prep").

    Without replacement unless there are fewer positive-weight candidates than requested.
    """
    n = int(cfg.prep.n_origin_points)
    w = candidates["weight"].to_numpy(dtype=float)
    p = w / w.sum()
    rng = stream(cfg.prep.seed, "prep")
    replace = n > int((w > 0).sum())
    idx = rng.choice(len(candidates), size=n, replace=replace, p=p)
    out = candidates.iloc[idx].reset_index(drop=True)
    out.insert(0, "origin_id", np.arange(n, dtype=int))
    return out


# --------------------------------------------------------------------------- paths and gates


def first_entry(path: Sequence[Node], inside: dict[Node, bool]) -> int:
    """Index of the first node on an origin->destination path that lies inside the cordon.

    The gate edge is (path[i-1], path[i]). Returns 0 if the origin itself is inside.
    """
    for i, n in enumerate(path):
        if inside[n]:
            return i
    raise ValueError("path never enters the cordon")


def last_entry(path: Sequence[Node], inside: dict[Node, bool]) -> int:
    """Index i of the final outside->inside transition (path[i-1] outside, path[i] inside).

    After it the path stays inside the cordon up to the destination. Returns 0 if the whole
    path is inside.
    """
    if not inside[path[-1]]:
        raise ValueError("path does not end inside the cordon")
    for i in range(len(path) - 1, 0, -1):
        if not inside[path[i - 1]]:
            return i
    return 0


def gate_index(path: Sequence[Node], inside: dict[Node, bool], rule: str = "first_entry") -> int:
    """Gate node index on an origin->destination path under ``rule`` (last_entry | first_entry)."""
    if rule == "first_entry":
        return first_entry(path, inside)
    if rule == "last_entry":
        return last_entry(path, inside)
    raise ValueError(f"unknown gate rule {rule!r}")


def count_entries(path: Sequence[Node], inside: dict[Node, bool]) -> int:
    """Number of outside->inside transitions along a path."""
    return sum(1 for a, b in zip(path[:-1], path[1:]) if not inside[a] and inside[b])


def trace_paths(G: nx.Graph, dest: Node, origins: pd.DataFrame, cordon: BaseGeometry,
                rule: str = "first_entry") -> pd.DataFrame:
    """Shortest free-flow path, gate and time split for every origin.

    One single-source Dijkstra from ``dest`` (graph is undirected). Gate edge = (path[i-1],
    path[i]) with i from ``gate_index``: "first_entry" is the first edge whose far end is inside
    the cordon (specification, default); "last_entry" (default) is the final outside->inside crossing,
    which ignores paths that clip the boundary on a ramp and leave again.
    """
    dist, paths = nx.single_source_dijkstra(G, dest, weight="minutes")
    nodes, xy = node_array(G)
    ins = dict(zip(nodes, inside_mask(cordon, xy).tolist()))
    rows = []
    cache: dict[Node, dict[str, Any]] = {}
    for o in origins.itertuples(index=False):
        node = o.node
        if node not in cache:
            path = list(reversed(paths[node]))
            if ins[path[0]]:
                raise ValueError(f"origin {node} is inside the cordon")
            i = gate_index(path, ins, rule)
            i_first = first_entry(path, ins)
            i_last = last_entry(path, ins)
            if i == 0:
                raise ValueError(f"origin {node} is inside the cordon")
            u, v = path[i - 1], path[i]
            e = G.edges[u, v]
            km = sum(G.edges[a, b]["distance_m"] for a, b in zip(path[:-1], path[1:])) / 1000.0
            cache[node] = {
                "gate_u": u, "gate_v": v, "gate_row": e["row"], "segment_id": e["segment_id"],
                "fftt_to_gate_min": dist[node] - dist[v],
                "fftt_gate_to_dest_min": dist[v],
                "path_km": km, "n_entries": count_entries(path, ins), "n_edges": len(path) - 1,
                "first_segment_id": G.edges[path[i_first - 1], path[i_first]]["segment_id"],
                "last_segment_id": G.edges[path[i_last - 1], path[i_last]]["segment_id"],
            }
        rows.append({"origin_id": o.origin_id, "x_nztm": o.x_nztm, "y_nztm": o.y_nztm,
                     "weight": o.weight, "node": node, **cache[node]})
    return pd.DataFrame(rows)


def gate_point(line: BaseGeometry, cordon: BaseGeometry, inside_end: tuple[float, float]) -> Point:
    """Point where a gate segment crosses the cordon boundary (nearest to its inside end)."""
    inter = line.intersection(cordon.boundary)
    pts = [g for g in getattr(inter, "geoms", [inter]) if not g.is_empty]
    pts = [p if p.geom_type == "Point" else p.representative_point() for p in pts]
    if not pts:
        # rounding the endpoint to the node grid can leave the segment just short of the
        # boundary: snap to the nearest boundary point of the inside end
        bnd = cordon.boundary
        return bnd.interpolate(bnd.project(Point(inside_end)))
    tgt = Point(inside_end)
    return min(pts, key=lambda p: p.distance(tgt))


def gate_table(paths: pd.DataFrame, roads: gpd.GeoDataFrame, cordon: BaseGeometry) -> pd.DataFrame:
    """One row per distinct gate segment; gate_id by segment_id order (corridor_id added later)."""
    g = (paths.groupby("segment_id", sort=True)
         .agg(gate_row=("gate_row", "first"), gate_v=("gate_v", "first"), n_origins=("origin_id", "size"))
         .reset_index())
    pts = [gate_point(roads.geometry.iloc[r], cordon, v) for r, v in zip(g["gate_row"], g["gate_v"])]
    rr = roads.iloc[g["gate_row"].to_numpy()]
    out = pd.DataFrame({
        "gate_id": np.arange(len(g), dtype=int),
        "segment_id": g["segment_id"].to_numpy(),
        "streetName": rr["streetName"].to_numpy(),
        "frc": rr["frc"].to_numpy(dtype=int),
        "speedLimit": rr["speedLimit"].to_numpy(dtype=int),
        "x_nztm": [p.x for p in pts],
        "y_nztm": [p.y for p in pts],
        "n_origins": g["n_origins"].to_numpy(dtype=int),
        "gate_row": g["gate_row"].to_numpy(dtype=int),
    })
    return out


# --------------------------------------------------------------------------- corridors


def _unrolled_quantile_init(bearings: np.ndarray, weights: np.ndarray, k: int) -> np.ndarray:
    """Initial centre angles (deg) at weighted quantiles of bearings, cutting the circle at its largest gap."""
    order = np.argsort(bearings, kind="stable")
    b = np.asarray(bearings, dtype=float)[order]
    w = np.asarray(weights, dtype=float)[order]
    gaps = np.diff(np.r_[b, b[0] + 360.0])
    cut = int(np.argmax(gaps)) + 1
    b = np.r_[b[cut:], b[:cut] + 360.0]
    w = np.r_[w[cut:], w[:cut]]
    cw = (np.cumsum(w) - 0.5 * w) / w.sum()
    return np.interp((np.arange(k) + 0.5) / k, cw, b) % 360.0


def weighted_bearing_kmeans(bearings: np.ndarray, weights: np.ndarray, k: int,
                            rng: np.random.Generator | None = None, n_starts: int = 50,
                            max_iter: int = 100) -> np.ndarray:
    """Weighted k-means on unit bearing vectors (spherical k-means on the circle).

    Starts: one at weighted quantiles of the bearings (circle cut at its largest gap) plus
    ``n_starts`` weighted k-means++ starts drawn from ``rng`` (default: default_rng(0)), so the
    result is deterministic. The start with the lowest weighted inertia sum w * (1 - cos) wins.
    Returns labels 0..k'-1 (k' = min(k, distinct bearings)) ordered by centre bearing clockwise
    from north.
    """
    bdeg = np.asarray(bearings, dtype=float)
    w = np.asarray(weights, dtype=float)
    k = int(min(k, len(np.unique(np.round(bdeg, 6)))))
    if k <= 1:
        return np.zeros(len(bdeg), dtype=int)
    rng = rng if rng is not None else np.random.default_rng(0)
    b = np.radians(bdeg)
    v = np.column_stack([np.sin(b), np.cos(b)])
    starts = [np.radians(_unrolled_quantile_init(bdeg, w, k))]
    for _ in range(n_starts):
        idx = [int(rng.choice(len(b), p=w / w.sum()))]
        for _j in range(1, k):
            d = np.clip(1.0 - v @ v[idx].T, 0.0, None).min(axis=1) * w
            if d.sum() <= 0:
                break
            idx.append(int(rng.choice(len(b), p=d / d.sum())))
        if len(idx) == k:
            starts.append(b[idx])
    best: tuple[float, np.ndarray, np.ndarray] | None = None
    for ang in starts:
        c = np.column_stack([np.sin(ang), np.cos(ang)])
        lab = np.full(len(b), -1)
        for _ in range(max_iter):
            new = np.argmax(v @ c.T, axis=1)
            if np.array_equal(new, lab):
                break
            lab = new
            for j in range(k):
                m = lab == j
                if m.any():
                    s_ = (w[m, None] * v[m]).sum(axis=0)
                    nrm = np.linalg.norm(s_)
                    if nrm > 0:
                        c[j] = s_ / nrm
        if len(np.unique(lab)) < k:
            continue
        inertia = float((w * (1.0 - (v * c[lab]).sum(axis=1))).sum())
        if best is None or inertia < best[0] - 1e-12:
            best = (inertia, lab.copy(), c.copy())
    if best is None:
        raise ValueError("bearing k-means found no start with all clusters non-empty")
    _, lab, c = best
    cb = np.degrees(np.arctan2(c[:, 0], c[:, 1])) % 360.0
    order = np.argsort(cb, kind="stable")
    remap = np.empty(k, dtype=int)
    remap[order] = np.arange(k)
    return remap[lab]


def group_corridors(gates: pd.DataFrame, cordon: BaseGeometry, cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cluster gates into corridors by entry bearing from the cordon centroid.

    Returns (gates with corridor_id and bearing_deg, corridors in the prep format).
    """
    c = cordon.centroid
    gates = gates.copy()
    gates["bearing_deg"] = bearing_deg(c.x, c.y, gates["x_nztm"].to_numpy(), gates["y_nztm"].to_numpy())
    gates["corridor_id"] = weighted_bearing_kmeans(gates["bearing_deg"].to_numpy(),
                                                   gates["n_origins"].to_numpy(), cfg.prep.n_corridors,
                                                   rng=stream(cfg.prep.seed, "prep", "corridors"))
    cap = cfg.prep.frc_capacity_vph
    rows = []
    for cid, g in gates.groupby("corridor_id", sort=True):
        brg = circular_mean_deg(g["bearing_deg"].to_numpy(), g["n_origins"].to_numpy())
        named = g[g["streetName"] != ""].assign(label=lambda d: d["streetName"].map(clean_street_name))
        streets = named.groupby("label")["n_origins"].sum()
        top = sorted(streets.index, key=lambda s: (-streets[s], s))[:3]
        label = ", ".join(top[:2]) if top else "unnamed"
        rows.append({
            "corridor_id": int(cid),
            "name": f"{compass8(brg)} ({label})",
            "n_gates": int(len(g)),
            "capacity_vph_raw": float(sum(cap[int(f)] for f in g["frc"])),
            "bearing_deg": round(brg, 2),
            "x_nztm": round(float(g["x_nztm"].mean()), 1),
            "y_nztm": round(float(g["y_nztm"].mean()), 1),
            "main_streets": ";".join(top),
        })
    corridors = pd.DataFrame(rows, columns=list(CORRIDORS_COLUMNS))
    # Disambiguate duplicate names (two corridors in the same compass sector).
    dup = corridors["name"].duplicated(keep=False)
    if dup.any():
        corridors.loc[dup, "name"] = [f"{n} [{int(b)} deg]" for n, b in
                                      zip(corridors.loc[dup, "name"], corridors.loc[dup, "bearing_deg"])]
    return gates, corridors


# --------------------------------------------------------------------------- outputs


def _fmt_quant(s: pd.Series) -> str:
    q = s.quantile([0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0])
    return " | ".join(f"{v:.1f}" for v in q.to_numpy()) + f" | {s.mean():.1f}"


def write_map(path: Path, roads: gpd.GeoDataFrame, cordon: BaseGeometry, gates: pd.DataFrame,
              origins: pd.DataFrame, corridors: pd.DataFrame, dest: Node, cfg: Config) -> None:
    """prep_map.png: whole extent plus a zoom on the cordon."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    cmap = plt.get_cmap("tab10")
    col = {int(c): cmap(int(c) % 10) for c in corridors["corridor_id"]}
    rng = np.random.default_rng(0)
    n_s = min(cfg.prep.map_sample_origins, len(origins))
    samp = origins.iloc[np.sort(rng.choice(len(origins), size=n_s, replace=False))]
    cgs = gpd.GeoSeries([cordon], crs=roads.crs)
    major = roads[roads["frc"] <= 2]
    fig, axes = plt.subplots(1, 2, figsize=(16, 8.5), gridspec_kw={"width_ratios": [1, 1]})
    for ax, zoom in zip(axes, (False, True)):
        roads.plot(ax=ax, color="#d4d4d4", linewidth=0.25 if not zoom else 0.6, zorder=1)
        major.plot(ax=ax, color="#a8a8a8", linewidth=0.5 if not zoom else 1.0, zorder=1)
        cgs.boundary.plot(ax=ax, color="black", linewidth=1.2, zorder=3)
        if not zoom:
            ax.scatter(samp["x_nztm"], samp["y_nztm"], s=4,
                       c=[col[int(c)] for c in samp["corridor_id"]], alpha=0.7, zorder=2, linewidths=0)
        sz = 12 + 140 * np.sqrt(gates["n_origins"] / gates["n_origins"].max())
        ax.scatter(gates["x_nztm"], gates["y_nztm"], s=sz if zoom else sz / 3,
                   c=[col[int(c)] for c in gates["corridor_id"]], edgecolors="black",
                   linewidths=0.5, zorder=4)
        ax.plot(*dest, marker="*", color="black", markersize=14 if zoom else 9, zorder=5)
        ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        if zoom:
            minx, miny, maxx, maxy = cordon.bounds
            pad = 900.0
            ax.set_xlim(minx - pad, maxx + pad); ax.set_ylim(miny - pad, maxy + pad)
            ax.set_title("Cordon (SA3) and gates; marker area ~ origins served")
        else:
            ax.set_title(f"{len(origins)} sampled origins coloured by corridor (showing {n_s})")
    handles = [Line2D([], [], marker="o", linestyle="", color=col[int(r.corridor_id)],
                      markeredgecolor="black", label=f"{int(r.corridor_id)}: {r.name}")
               for r in corridors.itertuples()]
    handles.append(Line2D([], [], marker="*", linestyle="", color="black", label="destination node"))
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False, fontsize=9)
    fig.suptitle("Cordon-Lite prep: TomTom major roads, city-wide origins, cordon gates")
    fig.tight_layout(rect=(0, 0.07, 1, 0.96))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_outputs(out_dir: Path, cfg: Config, roads: gpd.GeoDataFrame, G: nx.Graph,
                  cordon: BaseGeometry, dest: Node, candidates: pd.DataFrame,
                  paths: pd.DataFrame, gates: pd.DataFrame, corridors: pd.DataFrame,
                  stats: dict[str, Any]) -> None:
    """Write origins.csv, gates.csv, corridors.csv, cordon.geojson, prep_map.png, prep_report.md."""
    out_dir.mkdir(parents=True, exist_ok=True)
    seg2gate = dict(zip(gates["segment_id"], gates["gate_id"]))
    seg2corr = dict(zip(gates["segment_id"], gates["corridor_id"]))
    origins = pd.DataFrame({
        "origin_id": paths["origin_id"].astype(int),
        "x_nztm": paths["x_nztm"].round(1),
        "y_nztm": paths["y_nztm"].round(1),
        "weight": paths["weight"].round(3),
        "corridor_id": paths["segment_id"].map(seg2corr).astype(int),
        "gate_id": paths["segment_id"].map(seg2gate).astype(int),
        "fftt_to_gate_min": paths["fftt_to_gate_min"].round(3),
        "fftt_gate_to_dest_min": paths["fftt_gate_to_dest_min"].round(3),
        "path_km": paths["path_km"].round(3),
    })[list(ORIGINS_COLUMNS)]
    origins.to_csv(out_dir / "origins.csv", index=False)
    g_out = gates.copy()
    g_out["x_nztm"] = g_out["x_nztm"].round(1)
    g_out["y_nztm"] = g_out["y_nztm"].round(1)
    g_out[list(GATES_COLUMNS)].to_csv(out_dir / "gates.csv", index=False)
    corridors[list(CORRIDORS_COLUMNS)].to_csv(out_dir / "corridors.csv", index=False)
    gj = out_dir / "cordon.geojson"
    if gj.exists():
        gj.unlink()
    gpd.GeoDataFrame({"name": [";".join(cfg.prep.cordon_names)]}, geometry=[cordon],
                     crs=f"EPSG:{cfg.prep.crs_epsg}").to_file(gj, driver="GeoJSON")
    write_map(out_dir / "prep_map.png", roads, cordon, gates, origins, corridors, dest, cfg)
    (out_dir / "prep_report.md").write_text(
        render_report(cfg, roads, G, cordon, dest, candidates, paths, origins, gates, corridors, stats),
        encoding="utf-8")


def render_report(cfg: Config, roads: gpd.GeoDataFrame, G: nx.Graph, cordon: BaseGeometry, dest: Node,
                  candidates: pd.DataFrame, paths: pd.DataFrame, origins: pd.DataFrame,
                  gates: pd.DataFrame, corridors: pd.DataFrame, stats: dict[str, Any]) -> str:
    """Markdown prep report: counts, corridor shares, fftt distribution, assumptions."""
    p = cfg.prep
    tot = origins["fftt_to_gate_min"] + origins["fftt_gate_to_dest_min"]
    L: list[str] = ["# Cordon-Lite prep report", ""]
    L += ["## Inputs and counts", "",
          f"- Roads: `{p.roads_gpkg}` layer `{p.roads_layer}`, {stats['n_segments']} segments.",
          f"- Graph: endpoints rounded to {p.node_round_m:g} m; {stats['n_nodes_all']} nodes, "
          f"{stats['n_edges_all']} edges, {stats['n_components']} components; giant component "
          f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges. Self-loops dropped: "
          f"{stats['n_self_loops']}; parallel segments collapsed to the fastest: {stats['n_parallel']}.",
          f"- Cordon: SA3 {list(p.cordon_names)} from `{p.cordon_gpkg}`, area "
          f"{cordon.area / 1e6:.2f} km2, perimeter {cordon.length / 1000:.2f} km; graph nodes inside: "
          f"{stats['n_nodes_inside']}.",
          f"- Destination node (inside cordon, nearest centroid): ({dest[0]:.0f}, {dest[1]:.0f}), "
          f"{Point(dest).distance(cordon.centroid):.0f} m from the centroid.",
          f"- Candidate origins: {len(candidates)} nodes outside the cordon, not motorway-only, with "
          f"positive weight ({stats['weight_source']}).",
          f"- Sampled origins: {len(origins)} (distinct nodes {paths['node'].nunique()}), "
          f"seed {cfg.prep.seed}, stream ('prep',), replacement {stats['replace']}.",
          f"- Gates used: {len(gates)} distinct segments; corridors: {len(corridors)}.", ""]
    L += ["## Corridors", "",
          "| id | name | gates | raw capacity veh/h | bearing | origins | share | median fftt total (min) |",
          "|---|---|---|---|---|---|---|---|"]
    for r in corridors.itertuples():
        m = origins["corridor_id"] == r.corridor_id
        L.append(f"| {r.corridor_id} | {r.name} | {r.n_gates} | {r.capacity_vph_raw:.0f} | "
                 f"{r.bearing_deg:.0f} | {int(m.sum())} | {m.mean():.1%} | {tot[m].median():.1f} |")
    L += ["", "Gates (most used first, top 15):", "",
          "| gate | corridor | street | frc | speed | origins |", "|---|---|---|---|---|---|"]
    for r in gates.sort_values(["n_origins", "gate_id"], ascending=[False, True]).head(15).itertuples():
        L.append(f"| {r.gate_id} | {r.corridor_id} | {r.streetName or '(unnamed)'} | {r.frc} | "
                 f"{r.speedLimit} | {r.n_origins} |")
    L += ["", "## Free-flow time and distance distribution", "",
          "| quantity | min | p5 | p25 | median | p75 | p95 | max | mean |",
          "|---|---|---|---|---|---|---|---|---|",
          f"| fftt to gate (min) | {_fmt_quant(origins['fftt_to_gate_min'])} |",
          f"| fftt gate to destination (min) | {_fmt_quant(origins['fftt_gate_to_dest_min'])} |",
          f"| fftt total (min) | {_fmt_quant(tot)} |",
          f"| path length (km) | {_fmt_quant(origins['path_km'])} |",
          f"| crow-fly origin to destination (km) | {_fmt_quant(stats['crow_km'])} |", ""]
    L += ["## Checks", "",
          f"- Origins inside the cordon: {stats['n_origins_inside']} (must be 0).",
          f"- Gate crossing points: max distance to the cordon boundary {stats['gate_pt_max_dist_m']:.3f} m; "
          f"gate segments whose geometry stops short of the boundary (rounded node inside, segment end "
          f"outside): {stats['n_gate_not_crossing']}, max gap {stats['gate_seg_max_gap_m']:.2f} m (gate point "
          "snapped to the boundary).",
          f"- Gate inside-end node distance to the boundary: median {stats['gate_node_med_dist_m']:.0f} m, "
          f"max {stats['gate_node_max_dist_m']:.0f} m.",
          f"- Paths entering the cordon more than once (leave and re-enter after the first gate): "
          f"{stats['n_multi_entry']} origins ({stats['n_multi_entry'] / len(origins):.1%}). Gate rule "
          f"`{cfg.prep.gate_rule}`; origins whose first-entry and last-entry gates differ: "
          f"{stats['n_rules_differ']}.",
          f"- Origins less than 1 min (free flow) from their gate: {stats['n_to_gate_lt1']} "
          "(inner suburbs next to the cordon; kept, persona rounds fftt_to_gate_min up to at least 1).",
          f"- Gates on motorway (frc 0): {int((gates['frc'] == 0).sum())} gates serving "
          f"{int(gates.loc[gates['frc'] == 0, 'n_origins'].sum())} origins.",
          f"- Ratio path km / crow-fly km: median {stats['detour_median']:.2f}.", ""]
    L += ["## Assumptions", "",
          "- [SPEC] Undirected graph: TomTom major roads carry no one-way or lane information, so "
          "every segment is usable in both directions (paths may use ramps the wrong way).",
          f"- [A] Free-flow minutes = distance / speed limit x ff_factor ({p.ff_factor:g}); no "
          "junction delay.",
          "- [SPEC] Graph nodes are segment endpoints rounded to the grid above; segments whose "
          "rounded endpoints coincide are dropped; parallel segments between the same two nodes keep "
          "the fastest.",
          "- [A] Origins are graph nodes (TomTom extent = Auckland urban extent), outside the cordon, "
          "excluding nodes whose incident segments are all motorway (frc 0).",
          f"- [A] Residential-density proxy: length of frc {list(p.local_frc)} road whose segment "
          f"midpoint lies within {p.density_radius_m:g} m of the node. With `prep.od_csv` set, SA2 "
          "commuter counts snapped to the nearest candidate node replace the proxy.",
          "- [SPEC] Destination = the graph node inside the cordon nearest to the cordon centroid; "
          "every commuter drives to this one node, so fftt gate-to-destination is a city-centre "
          "internal leg.",
          f"- [SPEC] Gate rule `{p.gate_rule}`. `first_entry`: the first edge on the "
          "origin-to-destination path whose far end is inside the cordon. `last_entry` [A]: the "
          "final outside-to-inside crossing, after which the path stays inside. They differ only "
          "for paths that touch the SA3 boundary and leave again (the SH1 Wellesley Street off-ramp, "
          "which the undirected graph then follows back out via the Port ramp and Alten Road, and "
          "the zig-zag boundary along The Strand). With `first_entry` these multi-entry paths keep "
          "their first touch (mostly the Wellesley Street ramp gate, also The Strand and Parnell Rise), "
          "spend under about 1.2 min outside and re-enter at Alten Road; the origins assigned to the "
          "Alten Road gate itself are single-entry paths from the south-east. Gate coordinates are where the gate segment "
          "crosses the cordon boundary (nearest boundary point if node rounding leaves it short).",
          f"- [A] Corridors = weighted k-means (weights = origins served, k = {p.n_corridors}) on unit "
          "bearing vectors from the cordon centroid to the gate points, deterministic multi-start; "
          "corridor ids run clockwise from north; corridor bearing is the weighted circular mean; "
          "name = 8-point compass sector plus the two most-used street names.",
          f"- [A] Raw corridor capacity = sum over its gates of per-frc capacity {list(p.frc_capacity_vph)} "
          "veh/h (frc 0..4). The engine uses `engine.capacity_mode` to turn this into agents/min.",
          "- [A] Corridor x, y = unweighted mean of its gate crossing points.", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------- main


def run_prep(cfg: Config, out_dir: Path | None = None) -> dict[str, Any]:
    """Run the full prep pipeline and write outputs; returns summary stats."""
    out_dir = out_dir or cfg.resolve_path(cfg.run.data_dir)
    roads = load_roads(cfg)
    cordon = load_cordon(cfg)
    # raw graph statistics before the giant component is taken
    r = cfg.prep.node_round_m
    p0 = shapely.get_coordinates(shapely.get_point(roads.geometry.values, 0))
    p1 = shapely.get_coordinates(shapely.get_point(roads.geometry.values, -1))
    a = np.column_stack(round_xy(p0[:, 0], p0[:, 1], r))
    b = np.column_stack(round_xy(p1[:, 0], p1[:, 1], r))
    self_loops = int((a == b).all(axis=1).sum())
    H = nx.Graph()
    H.add_edges_from((tuple(u), tuple(v)) for u, v in zip(a.tolist(), b.tolist()) if u != v)
    n_parallel = len(roads) - self_loops - H.number_of_edges()
    G = build_graph(roads, cfg)
    dest = destination_node(G, cordon)
    candidates = candidate_origins(G, roads, cordon, cfg)
    origins = sample_origins(candidates, cfg)
    paths = trace_paths(G, dest, origins, cordon, cfg.prep.gate_rule)
    gates = gate_table(paths, roads, cordon)
    gates, corridors = group_corridors(gates, cordon, cfg)

    _, xy = node_array(G)
    bnd = cordon.boundary
    gate_pts = shapely.points(gates["x_nztm"].to_numpy(), gates["y_nztm"].to_numpy())
    gate_lines = roads.geometry.values[gates["gate_row"].to_numpy()]
    crossing = shapely.intersects(gate_lines, bnd)
    v_nodes = paths.drop_duplicates("segment_id")["gate_v"].tolist()
    v_dist = np.array([Point(v).distance(bnd) for v in v_nodes])
    crow = np.hypot(paths["x_nztm"] - dest[0], paths["y_nztm"] - dest[1]) / 1000.0
    stats = {
        "n_segments": len(roads), "n_nodes_all": H.number_of_nodes(), "n_edges_all": H.number_of_edges(),
        "n_components": nx.number_connected_components(H), "n_self_loops": self_loops,
        "n_parallel": n_parallel, "n_nodes_inside": int(inside_mask(cordon, xy).sum()),
        "weight_source": f"od_csv {cfg.prep.od_csv}" if cfg.prep.od_csv else
        f"local road length proxy, frc {list(cfg.prep.local_frc)}, {cfg.prep.density_radius_m:g} m",
        "replace": cfg.prep.n_origin_points > len(candidates),
        "n_origins_inside": int(inside_mask(cordon, paths[["x_nztm", "y_nztm"]].to_numpy()).sum()),
        "gate_pt_max_dist_m": float(shapely.distance(gate_pts, bnd).max()),
        "n_gate_not_crossing": int((~crossing).sum()),
        "gate_node_med_dist_m": float(np.median(v_dist)), "gate_node_max_dist_m": float(v_dist.max()),
        "n_multi_entry": int((paths["n_entries"] > 1).sum()),
        "n_rules_differ": int((paths["first_segment_id"] != paths["last_segment_id"]).sum()),
        "gate_seg_max_gap_m": float(shapely.distance(gate_lines[~crossing], bnd).max()) if (~crossing).any() else 0.0,
        "n_to_gate_lt1": int((paths["fftt_to_gate_min"] < 1.0).sum()),
        "crow_km": crow, "detour_median": float(np.median(paths["path_km"] / crow)),
    }
    write_outputs(out_dir, cfg, roads, G, cordon, dest, candidates, paths, gates, corridors, stats)
    stats["n_gates"] = len(gates)
    stats["corridors"] = corridors
    stats["origins"] = pd.read_csv(out_dir / "origins.csv")
    return stats


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="Cordon-Lite offline network preparation")
    ap.add_argument("--config", default=None, help="path to config.toml")
    ap.add_argument("--out-dir", default=None, help="output folder (default: run.data_dir)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    out = Path(args.out_dir) if args.out_dir else None
    st = run_prep(cfg, out)
    o = st["origins"]
    tot = o["fftt_to_gate_min"] + o["fftt_gate_to_dest_min"]
    print(f"origins {len(o)}, gates {st['n_gates']}, corridors {len(st['corridors'])}")
    print(st["corridors"][["corridor_id", "name", "n_gates", "capacity_vph_raw", "bearing_deg"]].to_string(index=False))
    print("share:", o["corridor_id"].value_counts(normalize=True).sort_index().round(3).to_dict())
    print(f"fftt total min: p5 {tot.quantile(.05):.1f} median {tot.median():.1f} p95 {tot.quantile(.95):.1f} max {tot.max():.1f}")
    print(f"origins inside cordon {st['n_origins_inside']}, gates not crossing {st['n_gate_not_crossing']}, "
          f"multi-entry paths {st['n_multi_entry']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
