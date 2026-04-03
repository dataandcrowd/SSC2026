#!/usr/bin/env python3
"""
Comparative congestion maps v2:
  Q-Learning (No Charge) as the realistic baseline vs ToU / Flat fee.
  Real drivers learn and converge on optimal routes, so Q-Learning
  no-charge represents the status-quo Auckland network more faithfully
  than the exponential-decay Baseline model.

Outputs:
  fig_ql_baseline_vs_tou.png   – side-by-side: Q-Learn no charge / flat / ToU
  fig_ql_redistribution.png    – difference maps: where congestion shifted
  fig_ql_road_type_barplot.png – seaborn bar chart: V/C by road type & regime
"""

import csv, math, random, os
import numpy as np
import networkx as nx
import shapefile
from shapely.geometry import Point
from shapely.ops import unary_union
from collections import defaultdict

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import seaborn as sns

random.seed(42)
np.random.seed(42)

DATA_DIR = "/sessions/gifted-cool-dijkstra/mnt/github--SSC2026/netlogo/Data/"
OUT_DIR  = "/sessions/gifted-cool-dijkstra/mnt/github--SSC2026/output/figures/"
os.makedirs(OUT_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════
# Network loading (identical to akl_sim_v2.py)
# ══════════════════════════════════════════════════════════════════════

def load_network():
    nodes = {}
    with open(DATA_DIR + "akl_node_list.csv") as f:
        for row in csv.DictReader(f):
            nodes[row["id"]] = {"x": float(row["xpos"]), "y": float(row["ypos"])}
    links = []
    with open(DATA_DIR + "akl_link_list.csv") as f:
        for row in csv.DictReader(f):
            speed_str = row["maxspeed"].replace(" km/h", "")
            try:
                speed_kmh = float(speed_str)
            except ValueError:
                speed_kmh = 50.0
            links.append({
                "id": row["id"], "start": row["start"], "end": row["end"],
                "speed_kmh": speed_kmh, "street": row["streetName"],
            })
    return nodes, links


def load_sa3_boundary():
    sf = shapefile.Reader(DATA_DIR + "roads/akl_boundary")
    sf_roads = shapefile.Reader(DATA_DIR + "roads/akl_rd_cleaned")
    x_min, y_min, x_max, y_max = sf_roads.bbox
    all_polys = []
    cbd_polygon = None
    for rec, shp in zip(sf.records(), sf.shapes()):
        name = rec[1]
        pts = [((p[0] - x_min) / (x_max - x_min),
                (p[1] - y_min) / (y_max - y_min)) for p in shp.points]
        from shapely.geometry import Polygon as ShapelyPolygon
        try:
            poly = ShapelyPolygon(pts)
            if poly.is_valid:
                all_polys.append((name, poly))
                if name == "Auckland City Centre":
                    cbd_polygon = poly
        except:
            pass
    study_area = unary_union([p for _, p in all_polys])
    return cbd_polygon, all_polys, study_area, (x_min, y_min, x_max, y_max)


def compute_capacity(speed_kmh):
    if speed_kmh >= 80: return 18
    elif speed_kmh >= 60: return 14
    elif speed_kmh >= 50: return 10
    elif speed_kmh >= 40: return 7
    else: return 5


def build_graph(nodes, links, boundary):
    G = nx.Graph()
    for nid, info in nodes.items():
        pt = Point(info["x"], info["y"])
        is_cbd = boundary.contains(pt)
        G.add_node(nid, x=info["x"], y=info["y"], is_cbd=is_cbd)
    for link in links:
        s, e = link["start"], link["end"]
        if s in G.nodes and e in G.nodes:
            dx = G.nodes[s]["x"] - G.nodes[e]["x"]
            dy = G.nodes[s]["y"] - G.nodes[e]["y"]
            dist = math.sqrt(dx * dx + dy * dy)
            speed_norm = link["speed_kmh"] / 100.0
            travel_time = dist / max(speed_norm, 0.01)
            s_cbd, e_cbd = G.nodes[s]["is_cbd"], G.nodes[e]["is_cbd"]
            if s_cbd and e_cbd:
                road_type = "inner"
            elif s_cbd or e_cbd:
                road_type = "boundary"
            else:
                road_type = "peripheral"
            G.add_edge(s, e,
                       link_id=link["id"], street=link["street"],
                       speed_kmh=link["speed_kmh"], distance=dist,
                       travel_time=travel_time, road_type=road_type,
                       capacity=compute_capacity(link["speed_kmh"]),
                       volume=0)
    return G


# ══════════════════════════════════════════════════════════════════════
# Fee schedules & demand
# ══════════════════════════════════════════════════════════════════════

TOU_SCHEDULE = [
    (0.0, 2), (7.0, 2), (7.5, 3), (8.0, 6), (9.0, 6), (9.5, 4),
    (10.0, 4), (15.5, 4), (16.0, 6), (18.0, 6), (18.5, 4),
    (19.0, 4), (20.5, 2), (21.0, 2), (24.0, 2),
]

def get_tou_fee(hour):
    for i in range(len(TOU_SCHEDULE) - 1):
        t0, f0 = TOU_SCHEDULE[i]
        t1, f1 = TOU_SCHEDULE[i + 1]
        if t0 <= hour < t1:
            frac = (hour - t0) / (t1 - t0) if t1 > t0 else 0
            return f0 + frac * (f1 - f0)
    return 2.0

def get_fee(hour, fee_regime):
    if fee_regime == "none": return 0.0
    elif fee_regime == "flat": return 2.0
    else: return get_tou_fee(hour)

def _demand_profile(hour):
    profiles = {
        0: 0.05, 1: 0.03, 2: 0.02, 3: 0.02, 4: 0.05, 5: 0.12,
        6: 0.30, 7: 0.60, 8: 0.75, 9: 0.55, 10: 0.42, 11: 0.40,
        12: 0.45, 13: 0.42, 14: 0.45, 15: 0.55, 16: 0.72, 17: 0.70,
        18: 0.50, 19: 0.30, 20: 0.18, 21: 0.12, 22: 0.08, 23: 0.06,
    }
    return profiles.get(hour, 0.1)


# ══════════════════════════════════════════════════════════════════════
# Drivers & Q-Learning model
# ══════════════════════════════════════════════════════════════════════

class DriverPopulation:
    def __init__(self, n=500):
        self.n = n
        self.vot = np.random.lognormal(2.3, 0.6, n)
        self.quintile = np.zeros(n, dtype=int)
        thresholds = np.percentile(self.vot, [20, 40, 60, 80])
        for i in range(n):
            self.quintile[i] = np.searchsorted(thresholds, self.vot[i]) + 1
        self.beta = 1.0 / self.vot
        self.essential_prob = np.where(self.quintile <= 2, 0.15, 0.05)
        self.base_rate = np.full(n, 0.35)


class QLearningDriver:
    def __init__(self, n_agents):
        self.n = n_agents
        self.q_table = np.zeros((n_agents, 24, 2))
        self.alpha = 0.1
        self.gamma = 0.9
        self.epsilon = 0.4
        self.epsilon_min = 0.05
        self.epsilon_decay = 0.97

    def get_state(self, hour, congestion):
        time_bin = min(int(hour / 4), 5)
        cong_bin = min(int(congestion * 4), 3)
        return time_bin * 4 + cong_bin

    def decide(self, agent_idx, pop, fee, hour, congestion_level):
        if random.random() < pop.essential_prob[agent_idx]:
            return True
        state = self.get_state(hour, congestion_level)
        if random.random() < self.epsilon:
            return random.random() < 0.5
        return self.q_table[agent_idx, state, 0] > self.q_table[agent_idx, state, 1]

    def update(self, agent_idx, pop, entered, fee, hour, congestion, next_congestion):
        state = self.get_state(hour, congestion)
        next_state = self.get_state(min(hour + 1, 23), next_congestion)
        action = 0 if entered else 1
        if entered:
            trip_value = pop.vot[agent_idx] * 0.5
            cong_penalty = congestion * pop.vot[agent_idx] * 0.3
            reward = trip_value - fee - cong_penalty
        else:
            reward = pop.vot[agent_idx] * 0.05
        best_next = np.max(self.q_table[agent_idx, next_state, :])
        td_target = reward + self.gamma * best_next
        self.q_table[agent_idx, state, action] += self.alpha * (
            td_target - self.q_table[agent_idx, state, action])

    def decay_epsilon(self):
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)


# ══════════════════════════════════════════════════════════════════════
# Simulation with per-link V/C + per-link road-type tracking
# ══════════════════════════════════════════════════════════════════════

def get_cbd_paths(G, n_paths=300):
    cbd_nodes = [n for n in G.nodes if G.nodes[n]["is_cbd"]]
    non_cbd_nodes = [n for n in G.nodes if not G.nodes[n]["is_cbd"]]
    paths = []
    attempts = 0
    while len(paths) < n_paths and attempts < n_paths * 15:
        o = random.choice(non_cbd_nodes)
        d = random.choice(cbd_nodes)
        try:
            p = nx.shortest_path(G, o, d, weight="travel_time")
            if len(p) > 2:
                paths.append(p)
        except nx.NetworkXNoPath:
            pass
        attempts += 1
    return_paths = [list(reversed(p)) for p in paths[:n_paths // 3]]
    paths.extend(return_paths)
    return paths


def run_qlearning_sim(G, fee_regime, n_days=20, n_agents=500,
                      peak_hours=(7, 8, 16, 17)):
    """Run Q-Learning ABM. Returns per-link mean V/C during peak hours (last 5 days)
    AND per-link-per-hour V/C for the full 24h profile (last 5 days)."""
    random.seed(42)
    np.random.seed(42)

    pop = DriverPopulation(n_agents)
    paths = get_cbd_paths(G, n_paths=300)
    model = QLearningDriver(n_agents)

    link_vc_peak = defaultdict(list)       # peak-hour accumulator
    link_vc_hourly = defaultdict(lambda: defaultdict(list))  # hour -> link -> [vc]
    prev_congestion = 0.3

    for day in range(n_days):
        hourly_volumes = defaultdict(lambda: defaultdict(int))

        for hour in range(24):
            fee = get_fee(hour, fee_regime)
            demand_factor = _demand_profile(hour)
            n_potential = int(n_agents * demand_factor)

            entered_agents = []
            for i in range(n_potential):
                agent_idx = random.randint(0, n_agents - 1)
                enters = model.decide(agent_idx, pop, fee, hour, prev_congestion)
                if enters:
                    entered_agents.append(agent_idx)
                    path = random.choice(paths) if paths else []
                    for j in range(len(path) - 1):
                        edge = (path[j], path[j + 1])
                        hourly_volumes[hour][edge] += 1

            # Compute overall V/C for model updates
            all_vcs = []
            for (u, v), vol in hourly_volumes[hour].items():
                edge_data = G.edges.get((u, v), G.edges.get((v, u)))
                if edge_data:
                    all_vcs.append(vol / max(edge_data["capacity"], 1))
            current_congestion = np.mean(all_vcs) if all_vcs else 0.0

            # Q-Learning updates
            for ai in entered_agents:
                model.update(ai, pop, True, fee, hour, prev_congestion, current_congestion)
            for _ in range(min(20, n_agents)):
                ai = random.randint(0, n_agents - 1)
                if ai not in entered_agents:
                    model.update(ai, pop, False, fee, hour, prev_congestion, current_congestion)
            prev_congestion = current_congestion

            # Record per-link V/C for last 5 days
            if day >= n_days - 5:
                for (u, v), vol in hourly_volumes[hour].items():
                    edge_data = G.edges.get((u, v), G.edges.get((v, u)))
                    if edge_data:
                        vc = vol / max(edge_data["capacity"], 1)
                        lid = edge_data["link_id"]
                        link_vc_hourly[hour][lid].append(vc)
                        if hour in peak_hours:
                            link_vc_peak[lid].append(vc)

        model.decay_epsilon()

    # Averages
    peak_mean = {lid: np.mean(vcs) for lid, vcs in link_vc_peak.items()}
    hourly_mean = {}
    for hour in range(24):
        hourly_mean[hour] = {lid: np.mean(vcs)
                             for lid, vcs in link_vc_hourly[hour].items()}

    return peak_mean, hourly_mean


# ══════════════════════════════════════════════════════════════════════
# Link-to-shapefile mapping
# ══════════════════════════════════════════════════════════════════════

def build_link_mapping(G, gdf_roads, nztm_bbox):
    from scipy.spatial import cKDTree
    x_min, y_min, x_max, y_max = nztm_bbox

    link_ids = []
    midpoints = []
    for u, v, d in G.edges(data=True):
        lid = d["link_id"]
        x0 = G.nodes[u]["x"] * (x_max - x_min) + x_min
        y0 = G.nodes[u]["y"] * (y_max - y_min) + y_min
        x1 = G.nodes[v]["x"] * (x_max - x_min) + x_min
        y1 = G.nodes[v]["y"] * (y_max - y_min) + y_min
        link_ids.append(lid)
        midpoints.append(((x0 + x1) / 2, (y0 + y1) / 2))
    midpoints = np.array(midpoints)
    tree = cKDTree(midpoints)

    shp_midpoints = []
    for _, row in gdf_roads.iterrows():
        mid = row.geometry.interpolate(0.5, normalized=True)
        shp_midpoints.append((mid.x, mid.y))
    shp_midpoints = np.array(shp_midpoints)

    dists, indices = tree.query(shp_midpoints)
    shp_to_link = {}
    for shp_idx, (dist, link_idx) in enumerate(zip(dists, indices)):
        if dist < 100:
            shp_to_link[shp_idx] = link_ids[link_idx]
    return shp_to_link


# Build road_type lookup from graph
def build_link_road_type(G):
    """link_id -> road_type"""
    lrt = {}
    for u, v, d in G.edges(data=True):
        lrt[d["link_id"]] = d["road_type"]
    return lrt


# ══════════════════════════════════════════════════════════════════════
# Figure 1: Side-by-side maps (No Charge / Flat / ToU)
# ══════════════════════════════════════════════════════════════════════

def plot_three_panel(gdf_roads, gdf_sa3, gdf_cbd_sa3, shp_to_link,
                     vc_none, vc_flat, vc_tou, out_path):
    sns.set_theme(style="white", font_scale=1.05)

    fig, axes = plt.subplots(1, 3, figsize=(21, 8))

    vmin, vmax = 0.0, 1.4
    cmap = sns.color_palette("YlOrRd", as_cmap=True)
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

    datasets = [
        (vc_none, "No Charge\n(Learned equilibrium)"),
        (vc_flat, "Flat $2 Cordon"),
        (vc_tou,  "Time-of-Use ($2\u20136)"),
    ]

    for col, (link_vc, title) in enumerate(datasets):
        ax = axes[col]

        vc_values = []
        for shp_idx in range(len(gdf_roads)):
            lid = shp_to_link.get(shp_idx)
            vc_values.append(link_vc.get(lid, 0.0) if lid else 0.0)

        gdf_plot = gdf_roads.copy()
        gdf_plot["vc"] = vc_values

        # SA3 background
        gdf_sa3.plot(ax=ax, facecolor="#f7f7f7", edgecolor="#bbbbbb",
                     linewidth=0.5)

        # CBD cordon
        cbd_row = gdf_cbd_sa3[gdf_cbd_sa3["SA32025_V1_00_NAME"] == "Auckland City Centre"]
        if not cbd_row.empty:
            cbd_row.plot(ax=ax, facecolor="#e8f5e9", edgecolor="#2e7d32",
                         linewidth=2.0, alpha=0.4, linestyle="--")

        # All roads as light base
        gdf_roads.plot(ax=ax, color="#e0e0e0", linewidth=0.3)

        # Roads with traffic, coloured by V/C
        active = gdf_plot[gdf_plot["vc"] > 0.01]
        if not active.empty:
            active.plot(ax=ax, column="vc", cmap=cmap, norm=norm,
                        linewidth=1.0, legend=False)

        # Severe congestion overlay (V/C > 0.85)
        severe = gdf_plot[gdf_plot["vc"] > 0.85]
        if not severe.empty:
            severe.plot(ax=ax, color="#b71c1c", linewidth=2.5, alpha=0.85)

        # SA3 labels
        for idx, row in gdf_sa3.iterrows():
            c = row.geometry.centroid
            name = row.get("SA32025__1", "")
            if name:
                short = name.replace("Auckland City Centre", "CBD")
                ax.annotate(short, xy=(c.x, c.y), fontsize=6.5,
                            ha="center", va="center", color="#444444",
                            fontstyle="italic",
                            bbox=dict(boxstyle="round,pad=0.15",
                                      fc="white", ec="none", alpha=0.6))

        # Mean V/C annotation
        all_vc = [v for v in vc_values if v > 0.01]
        mean_val = np.mean(all_vc) if all_vc else 0
        severe_pct = (sum(1 for v in all_vc if v > 0.85) / max(len(all_vc), 1)) * 100
        ax.text(0.02, 0.02,
                f"Mean V/C: {mean_val:.2f}\nSevere (>0.85): {severe_pct:.0f}%",
                transform=ax.transAxes, fontsize=9, va="bottom",
                bbox=dict(boxstyle="round", fc="white", ec="#999999", alpha=0.85))

        ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
        ax.set_axis_off()

    # Shared colourbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes, orientation="horizontal",
                        fraction=0.025, pad=0.06, aspect=45)
    cbar.set_label("Volume / Capacity (V/C) Ratio", fontsize=11)
    cbar.ax.axvline(0.85, color="#b71c1c", linewidth=2, linestyle="--")
    cbar.ax.text(0.85 / vmax, -0.6, "LoS E", transform=cbar.ax.transAxes,
                 fontsize=8, ha="center", color="#b71c1c", fontweight="bold")

    fig.suptitle(
        "Q-Learning Agents: Peak-Hour Congestion Under Three Pricing Regimes\n"
        "Auckland CBD network, mean V/C over last 5 simulation days (hours 7\u20139 & 16\u201318)",
        fontsize=14, fontweight="bold", y=1.01)
    plt.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved {out_path}")


# ══════════════════════════════════════════════════════════════════════
# Figure 2: Difference maps (Flat/ToU minus No Charge)
# ══════════════════════════════════════════════════════════════════════

def plot_redistribution(gdf_roads, gdf_sa3, gdf_cbd_sa3, shp_to_link,
                        vc_none, vc_flat, vc_tou, out_path):
    sns.set_theme(style="white", font_scale=1.1)

    fig, axes = plt.subplots(1, 2, figsize=(16, 8))

    cmap = sns.color_palette("RdBu_r", as_cmap=True)
    vmin, vmax = -0.6, 0.6
    norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=0, vmax=vmax)

    pairs = [
        (vc_flat, "Flat $2 minus No Charge"),
        (vc_tou,  "Time-of-Use minus No Charge"),
    ]

    for col, (vc_after, title) in enumerate(pairs):
        ax = axes[col]

        diff_values = []
        for shp_idx in range(len(gdf_roads)):
            lid = shp_to_link.get(shp_idx)
            if lid:
                diff_values.append(vc_after.get(lid, 0.0) - vc_none.get(lid, 0.0))
            else:
                diff_values.append(0.0)

        gdf_plot = gdf_roads.copy()
        gdf_plot["vc_diff"] = diff_values

        # Background
        gdf_sa3.plot(ax=ax, facecolor="#fafafa", edgecolor="#cccccc", linewidth=0.5)

        # CBD cordon (dashed)
        cbd_row = gdf_cbd_sa3[gdf_cbd_sa3["SA32025_V1_00_NAME"] == "Auckland City Centre"]
        if not cbd_row.empty:
            cbd_row.boundary.plot(ax=ax, edgecolor="#333333", linewidth=2.0,
                                  linestyle="--")

        # Base roads (light grey)
        gdf_roads.plot(ax=ax, color="#e8e8e8", linewidth=0.3)

        # Active diff links
        active = gdf_plot[gdf_plot["vc_diff"].abs() > 0.01]
        if not active.empty:
            active.plot(ax=ax, column="vc_diff", cmap=cmap, norm=norm,
                        linewidth=1.8, legend=False)

        # SA3 labels
        for idx, row in gdf_sa3.iterrows():
            c = row.geometry.centroid
            name = row.get("SA32025__1", "")
            if name:
                short = name.replace("Auckland City Centre", "CBD")
                ax.annotate(short, xy=(c.x, c.y), fontsize=7,
                            ha="center", va="center", color="#444444",
                            fontstyle="italic",
                            bbox=dict(boxstyle="round,pad=0.15",
                                      fc="white", ec="none", alpha=0.6))

        # Count links increased vs decreased
        increased = sum(1 for d in diff_values if d > 0.05)
        decreased = sum(1 for d in diff_values if d < -0.05)
        ax.text(0.02, 0.02,
                f"Links with increased V/C: {increased}\n"
                f"Links with decreased V/C: {decreased}",
                transform=ax.transAxes, fontsize=9, va="bottom",
                bbox=dict(boxstyle="round", fc="white", ec="#999999", alpha=0.85))

        ax.set_title(title, fontsize=13, fontweight="bold", pad=10)
        ax.set_axis_off()

    # Shared colourbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes, orientation="horizontal",
                        fraction=0.035, pad=0.06, aspect=45)
    cbar.set_label("Change in V/C Ratio (red = more congested, blue = less congested)",
                   fontsize=11)

    legend_elements = [
        Line2D([0], [0], color="#d32f2f", linewidth=2.5,
               label="Congestion increased"),
        Line2D([0], [0], color="#1565c0", linewidth=2.5,
               label="Congestion decreased"),
        Line2D([0], [0], color="#333333", linewidth=2, linestyle="--",
               label="CBD cordon"),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=3,
               fontsize=10, frameon=True, bbox_to_anchor=(0.5, -0.02))

    fig.suptitle(
        "Where Does Congestion Shift Under Cordon Pricing?\n"
        "Q-Learning agents, difference in peak-hour V/C relative to no-charge baseline",
        fontsize=14, fontweight="bold", y=1.02)
    plt.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved {out_path}")


# ══════════════════════════════════════════════════════════════════════
# Figure 3: Seaborn grouped bar chart – V/C by road type and regime
# ══════════════════════════════════════════════════════════════════════

def plot_road_type_bars(G, vc_none, vc_flat, vc_tou, link_road_type, out_path):
    """Grouped bar chart: mean peak-hour V/C by road type for each fee regime."""
    sns.set_theme(style="whitegrid", font_scale=1.15)

    records = []
    for regime_label, link_vc in [("No Charge", vc_none),
                                   ("Flat $2", vc_flat),
                                   ("Time-of-Use", vc_tou)]:
        for rtype in ["inner", "boundary", "peripheral"]:
            rtype_lids = [d["link_id"] for u, v, d in G.edges(data=True)
                          if d["road_type"] == rtype]
            vals = [link_vc.get(lid, 0.0) for lid in rtype_lids
                    if lid in link_vc]
            if vals:
                records.append({
                    "Fee Regime": regime_label,
                    "Road Type": rtype.title(),
                    "Mean V/C": np.mean(vals),
                    "Std V/C": np.std(vals),
                })

    import pandas as pd
    df = pd.DataFrame(records)

    fig, ax = plt.subplots(figsize=(10, 6))
    palette = {"No Charge": "#e53935", "Flat $2": "#fb8c00", "Time-of-Use": "#1e88e5"}
    bar_order = ["Inner", "Boundary", "Peripheral"]

    bars = sns.barplot(data=df, x="Road Type", y="Mean V/C", hue="Fee Regime",
                       palette=palette, order=bar_order, ax=ax,
                       edgecolor="white", linewidth=1.2)

    # Add value labels on bars
    for container in bars.containers:
        bars.bar_label(container, fmt="%.2f", fontsize=9, padding=3)

    # LoS E threshold line
    ax.axhline(0.85, color="#b71c1c", linewidth=1.5, linestyle="--", alpha=0.7)
    ax.text(2.55, 0.87, "LoS E threshold", fontsize=9, color="#b71c1c",
            fontweight="bold", ha="right")

    ax.set_xlabel("Road Type (relative to CBD cordon)", fontsize=12)
    ax.set_ylabel("Mean Peak-Hour V/C Ratio", fontsize=12)
    ax.set_title("Q-Learning Agents: Congestion by Road Type and Pricing Regime\n"
                 "(Peak hours 7\u20139 & 16\u201318, last 5 simulation days)",
                 fontsize=13, fontweight="bold")
    ax.set_ylim(0, max(df["Mean V/C"]) * 1.2)
    ax.legend(title="Fee Regime", fontsize=10, title_fontsize=11)

    plt.tight_layout()
    plt.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved {out_path}")


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def main():
    print("Loading network...")
    nodes, links = load_network()
    cbd_polygon, sa3_polys, study_area, nztm_bbox = load_sa3_boundary()

    print("Building graph...")
    G = build_graph(nodes, links, cbd_polygon)
    link_road_type = build_link_road_type(G)
    print(f"  {len(G.nodes)} nodes, {G.number_of_edges()} edges")

    print("Loading shapefiles...")
    gdf_roads = gpd.read_file(DATA_DIR + "roads/akl_rd_cleaned.shp")
    gdf_sa3 = gpd.read_file(DATA_DIR + "roads/akl_boundary.shp")
    gdf_cbd_sa3 = gpd.read_file(DATA_DIR + "roads/akl_CBD_SA3.gpkg")

    print("Mapping links to shapefile geometry...")
    shp_to_link = build_link_mapping(G, gdf_roads, nztm_bbox)
    print(f"  Matched {len(shp_to_link)}/{len(gdf_roads)} segments")

    # Run Q-Learning simulations for three fee regimes
    print("\n--- Q-Learning: No Charge (realistic baseline) ---")
    vc_none_peak, vc_none_hourly = run_qlearning_sim(G, "none")
    print(f"  Active links: {sum(1 for v in vc_none_peak.values() if v > 0)}, "
          f"mean peak V/C: {np.mean(list(vc_none_peak.values())):.3f}")

    print("--- Q-Learning: Flat $2 ---")
    vc_flat_peak, vc_flat_hourly = run_qlearning_sim(G, "flat")
    print(f"  Active links: {sum(1 for v in vc_flat_peak.values() if v > 0)}, "
          f"mean peak V/C: {np.mean(list(vc_flat_peak.values())):.3f}")

    print("--- Q-Learning: Time-of-Use ---")
    vc_tou_peak, vc_tou_hourly = run_qlearning_sim(G, "tou")
    print(f"  Active links: {sum(1 for v in vc_tou_peak.values() if v > 0)}, "
          f"mean peak V/C: {np.mean(list(vc_tou_peak.values())):.3f}")

    # Generate figures
    print("\nGenerating Figure 1: Three-panel comparison...")
    plot_three_panel(gdf_roads, gdf_sa3, gdf_cbd_sa3, shp_to_link,
                     vc_none_peak, vc_flat_peak, vc_tou_peak,
                     OUT_DIR + "fig_ql_baseline_vs_tou.png")

    print("Generating Figure 2: Redistribution difference maps...")
    plot_redistribution(gdf_roads, gdf_sa3, gdf_cbd_sa3, shp_to_link,
                        vc_none_peak, vc_flat_peak, vc_tou_peak,
                        OUT_DIR + "fig_ql_redistribution.png")

    print("Generating Figure 3: Road-type bar chart...")
    plot_road_type_bars(G, vc_none_peak, vc_flat_peak, vc_tou_peak,
                        link_road_type, OUT_DIR + "fig_ql_road_type_barplot.png")

    # Summary statistics by road type
    print("\n=== Congestion redistribution summary (Q-Learning) ===")
    for regime_label, link_vc in [("No Charge", vc_none_peak),
                                   ("Flat $2", vc_flat_peak),
                                   ("Time-of-Use", vc_tou_peak)]:
        print(f"\n  {regime_label}:")
        for rtype in ["inner", "boundary", "peripheral"]:
            rtype_lids = [d["link_id"] for u, v, d in G.edges(data=True)
                          if d["road_type"] == rtype]
            vals = [link_vc.get(lid, 0.0) for lid in rtype_lids if lid in link_vc]
            if vals:
                print(f"    {rtype:12s}: mean V/C={np.mean(vals):.3f}, "
                      f"max={np.max(vals):.3f}, "
                      f">0.85: {sum(1 for v in vals if v > 0.85)}/{len(vals)} links")

    # Redistribution: which SA3 areas gained/lost congestion
    print("\n=== Spatial redistribution by SA3 area ===")
    # Map links to SA3 via centroid containment
    sa3_gdf = gdf_sa3.copy()
    for regime_label, link_vc in [("Flat - NoCharge", vc_flat_peak),
                                   ("ToU - NoCharge", vc_tou_peak)]:
        print(f"\n  {regime_label}:")
        for idx, sa3_row in sa3_gdf.iterrows():
            sa3_name = sa3_row.get("SA32025__1", f"SA3-{idx}")
            sa3_geom = sa3_row.geometry
            gained = 0
            lost = 0
            for shp_idx, lid in shp_to_link.items():
                mid = gdf_roads.iloc[shp_idx].geometry.interpolate(0.5, normalized=True)
                if sa3_geom.contains(mid):
                    diff = link_vc.get(lid, 0.0) - vc_none_peak.get(lid, 0.0)
                    if diff > 0.05:
                        gained += 1
                    elif diff < -0.05:
                        lost += 1
            if gained > 0 or lost > 0:
                print(f"    {sa3_name:25s}: +{gained} links gained, "
                      f"-{lost} links lost congestion")

    print("\nDone!")


if __name__ == "__main__":
    main()
