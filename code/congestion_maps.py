#!/usr/bin/env python3
"""
Comparative congestion maps: No Charge vs Time-of-Use pricing.
Uses the actual Auckland road network shapefiles (EPSG:2193) for geographic context,
with per-link V/C ratios from the ABM simulation overlaid.

Outputs:
  - fig_congestion_comparison.png  (3-model panel: No Charge vs ToU)
  - fig_congestion_diff.png        (difference maps: where congestion shifted)
"""

import csv, math, random, sys, os
import numpy as np
import networkx as nx
import shapefile
from shapely.geometry import Point, LineString, MultiPolygon
from shapely.ops import unary_union
from collections import defaultdict

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
import seaborn as sns

random.seed(42)
np.random.seed(42)

# ── Paths ───────────────────────────────────────────────────────────────
DATA_DIR = "/sessions/gifted-cool-dijkstra/mnt/github--SSC2026/netlogo/Data/"
OUT_DIR  = "/sessions/gifted-cool-dijkstra/mnt/github--SSC2026/output/figures/"
os.makedirs(OUT_DIR, exist_ok=True)

# ── 1. Load network (same as akl_sim_v2.py) ────────────────────────────

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
    buildings = []
    with open(DATA_DIR + "akl_building_list.csv") as f:
        for row in csv.DictReader(f):
            buildings.append({"id": row["id"], "x": float(row["xpos"]), "y": float(row["ypos"])})
    return nodes, links, buildings


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
            s_cbd = G.nodes[s]["is_cbd"]
            e_cbd = G.nodes[e]["is_cbd"]
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


# ── 2. ToU schedule ────────────────────────────────────────────────────

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


# ── 3. Demand profile ──────────────────────────────────────────────────

def _demand_profile(hour):
    profiles = {
        0: 0.05, 1: 0.03, 2: 0.02, 3: 0.02, 4: 0.05, 5: 0.12,
        6: 0.30, 7: 0.60, 8: 0.75, 9: 0.55, 10: 0.42, 11: 0.40,
        12: 0.45, 13: 0.42, 14: 0.45, 15: 0.55, 16: 0.72, 17: 0.70,
        18: 0.50, 19: 0.30, 20: 0.18, 21: 0.12, 22: 0.08, 23: 0.06,
    }
    return profiles.get(hour, 0.1)


# ── 4. Drivers ──────────────────────────────────────────────────────────

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


# ── 5. Decision models ─────────────────────────────────────────────────

def baseline_decision(agent_idx, pop, fee, hour, congestion_level):
    if random.random() < pop.essential_prob[agent_idx]:
        return True
    p = pop.base_rate[agent_idx] * math.exp(-pop.beta[agent_idx] * fee / max(pop.vot[agent_idx], 0.01))
    return random.random() < max(p, 0.05)


class ElFarolAgent:
    def __init__(self, n_agents):
        self.n = n_agents
        self.weights = np.random.dirichlet(np.ones(5), n_agents)
        self.predictor_scores = np.ones((n_agents, 5))
        self.history = [0.5] * 10
        self.comfort_threshold = 0.60
        self.switch_prob = 0.08

    def predict(self, agent_idx):
        h = self.history
        preds = [h[-1], np.mean(h[-2:]), np.mean(h[-5:]),
                 h[-1] + (h[-1] - h[-2]) if len(h) >= 2 else h[-1],
                 h[-1] * 0.5 + np.mean(h[-3:]) * 0.5]
        best = np.argmax(self.predictor_scores[agent_idx])
        if random.random() < self.switch_prob:
            best = random.randint(0, 4)
        return preds[best]

    def decide(self, agent_idx, pop, fee, hour, congestion_level):
        if random.random() < pop.essential_prob[agent_idx]:
            return True
        pred = self.predict(agent_idx)
        fee_factor = math.exp(-pop.beta[agent_idx] * fee / max(pop.vot[agent_idx], 0.01))
        threshold = self.comfort_threshold * fee_factor
        return pred < threshold

    def update(self, actual_congestion):
        h = self.history
        preds = [h[-1], np.mean(h[-2:]), np.mean(h[-5:]),
                 h[-1] + (h[-1] - h[-2]) if len(h) >= 2 else h[-1],
                 h[-1] * 0.5 + np.mean(h[-3:]) * 0.5]
        for i in range(self.n):
            for p in range(5):
                error = abs(preds[p] - actual_congestion)
                self.predictor_scores[i, p] *= 0.9
                self.predictor_scores[i, p] += (1.0 - error)
        self.history.append(actual_congestion)
        if len(self.history) > 20:
            self.history = self.history[-20:]


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
        self.q_table[agent_idx, state, action] += self.alpha * (td_target - self.q_table[agent_idx, state, action])

    def decay_epsilon(self):
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)


# ── 6. Simulation with per-link V/C capture ────────────────────────────

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


def run_sim_with_link_vc(G, model_name, fee_regime, n_days=20, n_agents=500,
                         peak_hours=(7, 8, 16, 17)):
    """Run the ABM and return per-link mean V/C during peak hours (last 5 days)."""
    pop = DriverPopulation(n_agents)
    paths = get_cbd_paths(G, n_paths=300)

    if model_name == "el_farol":
        model = ElFarolAgent(n_agents)
    elif model_name == "qlearning":
        model = QLearningDriver(n_agents)
    else:
        model = None

    # Accumulators for per-link V/C over last 5 days' peak hours
    link_vc_accum = defaultdict(list)
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
                if model_name == "baseline":
                    enters = baseline_decision(agent_idx, pop, fee, hour, prev_congestion)
                elif model_name == "el_farol":
                    enters = model.decide(agent_idx, pop, fee, hour, prev_congestion)
                elif model_name == "qlearning":
                    enters = model.decide(agent_idx, pop, fee, hour, prev_congestion)
                else:
                    enters = random.random() < 0.5

                if enters:
                    entered_agents.append(agent_idx)
                    path = random.choice(paths) if paths else []
                    for j in range(len(path) - 1):
                        edge = (path[j], path[j + 1])
                        hourly_volumes[hour][edge] += 1

            # Compute current-hour overall V/C for model updates
            all_vcs = []
            for (u, v), vol in hourly_volumes[hour].items():
                edge_data = G.edges.get((u, v), G.edges.get((v, u)))
                if edge_data:
                    all_vcs.append(vol / max(edge_data["capacity"], 1))
            current_congestion = np.mean(all_vcs) if all_vcs else 0.0

            if model_name == "el_farol":
                model.update(min(current_congestion, 1.0))
            elif model_name == "qlearning":
                for ai in entered_agents:
                    model.update(ai, pop, True, fee, hour, prev_congestion, current_congestion)
                for _ in range(min(20, n_agents)):
                    ai = random.randint(0, n_agents - 1)
                    if ai not in entered_agents:
                        model.update(ai, pop, False, fee, hour, prev_congestion, current_congestion)
            prev_congestion = current_congestion

            # Capture per-link V/C during peak hours in last 5 days
            if day >= n_days - 5 and hour in peak_hours:
                for (u, v), vol in hourly_volumes[hour].items():
                    edge_data = G.edges.get((u, v), G.edges.get((v, u)))
                    if edge_data:
                        vc = vol / max(edge_data["capacity"], 1)
                        lid = edge_data["link_id"]
                        link_vc_accum[lid].append(vc)

        if model_name == "qlearning":
            model.decay_epsilon()

    # Average per-link V/C
    link_vc_mean = {}
    for lid, vcs in link_vc_accum.items():
        link_vc_mean[lid] = np.mean(vcs)

    return link_vc_mean


# ── 7. Build link_id -> shapefile index mapping ────────────────────────

def build_link_id_to_geom(G, gdf_roads, nodes, nztm_bbox):
    """Map simulation link_id to shapefile row index using start/end coordinate matching."""
    x_min, y_min, x_max, y_max = nztm_bbox

    # Build lookup: link_id -> normalised start/end coords
    link_coords = {}
    for u, v, d in G.edges(data=True):
        lid = d["link_id"]
        x0 = G.nodes[u]["x"] * (x_max - x_min) + x_min
        y0 = G.nodes[u]["y"] * (y_max - y_min) + y_min
        x1 = G.nodes[v]["x"] * (x_max - x_min) + x_min
        y1 = G.nodes[v]["y"] * (y_max - y_min) + y_min
        link_coords[lid] = ((x0, y0), (x1, y1))

    # For each shapefile road segment, find nearest simulation link by midpoint
    from scipy.spatial import cKDTree

    # Build KD-tree of link midpoints
    link_ids = list(link_coords.keys())
    midpoints = []
    for lid in link_ids:
        (x0, y0), (x1, y1) = link_coords[lid]
        midpoints.append(((x0 + x1) / 2, (y0 + y1) / 2))
    midpoints = np.array(midpoints)
    tree = cKDTree(midpoints)

    # Match each shapefile segment
    shp_midpoints = []
    for idx, row in gdf_roads.iterrows():
        geom = row.geometry
        mid = geom.interpolate(0.5, normalized=True)
        shp_midpoints.append((mid.x, mid.y))
    shp_midpoints = np.array(shp_midpoints)

    dists, indices = tree.query(shp_midpoints)

    # Map: shapefile row idx -> link_id
    shp_to_link = {}
    for shp_idx, (dist, link_idx) in enumerate(zip(dists, indices)):
        if dist < 100:  # within 100m tolerance in NZTM
            shp_to_link[shp_idx] = link_ids[link_idx]

    return shp_to_link


# ── 8. Create comparison maps ──────────────────────────────────────────

def plot_comparison_maps(gdf_roads, gdf_sa3, gdf_cbd_sa3, shp_to_link,
                         results_dict, out_path):
    """
    results_dict: {(model, fee_regime): {link_id: mean_vc}}
    Creates a 3x2 panel: rows = models, cols = No Charge / ToU
    """
    sns.set_theme(style="whitegrid", font_scale=1.0)

    models = ["baseline", "el_farol", "qlearning"]
    model_labels = {"baseline": "Baseline (Exponential Decay)",
                    "el_farol": "El Farol (Minority Game)",
                    "qlearning": "Q-Learning (Reinforcement)"}
    fees = ["none", "tou"]
    fee_labels = {"none": "No Charge", "tou": "Time-of-Use ($2\u20136)"}

    fig, axes = plt.subplots(3, 2, figsize=(14, 18))

    # Colour normalisation: V/C 0 to 1.2
    vmin, vmax = 0.0, 1.2
    cmap = sns.color_palette("YlOrRd", as_cmap=True)
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)

    for row, model in enumerate(models):
        for col, fee in enumerate(fees):
            ax = axes[row, col]
            key = (model, fee)
            link_vc = results_dict.get(key, {})

            # Assign V/C to each road segment
            vc_values = []
            for shp_idx in range(len(gdf_roads)):
                lid = shp_to_link.get(shp_idx)
                if lid and lid in link_vc:
                    vc_values.append(link_vc[lid])
                else:
                    vc_values.append(0.0)  # no traffic recorded

            gdf_plot = gdf_roads.copy()
            gdf_plot["vc"] = vc_values

            # Background: SA3 boundaries
            gdf_sa3.plot(ax=ax, facecolor="#f0f0f0", edgecolor="#cccccc",
                         linewidth=0.5)

            # CBD SA3 highlight
            cbd_row = gdf_cbd_sa3[gdf_cbd_sa3["SA32025_V1_00_NAME"] == "Auckland City Centre"]
            if not cbd_row.empty:
                cbd_row.plot(ax=ax, facecolor="#d4edda", edgecolor="#28a745",
                             linewidth=1.5, alpha=0.5)

            # Roads coloured by V/C
            gdf_plot.plot(ax=ax, column="vc", cmap=cmap, norm=norm,
                          linewidth=0.8, legend=False)

            # High-congestion roads (V/C > 0.85) drawn thicker
            high_cong = gdf_plot[gdf_plot["vc"] > 0.85]
            if not high_cong.empty:
                high_cong.plot(ax=ax, color="#d32f2f", linewidth=2.0, alpha=0.9)

            ax.set_title(f"{model_labels[model]}\n{fee_labels[fee]}",
                         fontsize=11, fontweight="bold")
            ax.set_axis_off()

    # Shared colour bar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes, orientation="horizontal",
                        fraction=0.03, pad=0.04, aspect=40)
    cbar.set_label("Volume/Capacity (V/C) Ratio", fontsize=12)
    cbar.ax.axvline(0.85, color="red", linewidth=1.5, linestyle="--")

    fig.suptitle("Peak-Hour Congestion: No Charge vs Time-of-Use Pricing\n"
                 "(Auckland CBD, mean V/C over last 5 simulation days, hours 7\u20139 & 16\u201318)",
                 fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0.05, 1, 0.96])
    plt.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved {out_path}")


def plot_difference_maps(gdf_roads, gdf_sa3, gdf_cbd_sa3, shp_to_link,
                         results_dict, out_path):
    """
    Difference maps: V/C(ToU) - V/C(No Charge)
    Positive = MORE congested under ToU, Negative = LESS congested
    """
    sns.set_theme(style="whitegrid", font_scale=1.1)

    models = ["baseline", "el_farol", "qlearning"]
    model_labels = {"baseline": "Baseline", "el_farol": "El Farol", "qlearning": "Q-Learning"}

    fig, axes = plt.subplots(1, 3, figsize=(20, 8))

    # Diverging colour map: blue = less congestion, red = more congestion
    cmap = sns.color_palette("RdBu_r", as_cmap=True)
    vmin, vmax = -0.5, 0.5
    norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=0, vmax=vmax)

    for col, model in enumerate(models):
        ax = axes[col]
        vc_none = results_dict.get((model, "none"), {})
        vc_tou = results_dict.get((model, "tou"), {})

        diff_values = []
        for shp_idx in range(len(gdf_roads)):
            lid = shp_to_link.get(shp_idx)
            if lid:
                v_tou = vc_tou.get(lid, 0.0)
                v_none = vc_none.get(lid, 0.0)
                diff_values.append(v_tou - v_none)
            else:
                diff_values.append(0.0)

        gdf_plot = gdf_roads.copy()
        gdf_plot["vc_diff"] = diff_values

        # Background
        gdf_sa3.plot(ax=ax, facecolor="#f5f5f5", edgecolor="#cccccc", linewidth=0.5)

        # CBD cordon
        cbd_row = gdf_cbd_sa3[gdf_cbd_sa3["SA32025_V1_00_NAME"] == "Auckland City Centre"]
        if not cbd_row.empty:
            cbd_row.boundary.plot(ax=ax, edgecolor="#333333", linewidth=1.5,
                                  linestyle="--")

        # Only plot links that had some traffic in either scenario
        active = gdf_plot[(gdf_plot["vc_diff"] != 0.0)]
        if not active.empty:
            active.plot(ax=ax, column="vc_diff", cmap=cmap, norm=norm,
                        linewidth=1.5, legend=False)

        # Add SA3 suburb labels
        for idx, row in gdf_sa3.iterrows():
            centroid = row.geometry.centroid
            name = row["SA32025__1"] if "SA32025__1" in gdf_sa3.columns else ""
            if name and name != "Auckland City Centre":
                ax.annotate(name, xy=(centroid.x, centroid.y),
                            fontsize=6, ha="center", va="center",
                            color="#555555", fontstyle="italic")

        ax.set_title(f"{model_labels[model]}\n(ToU minus No Charge)", fontsize=13, fontweight="bold")
        ax.set_axis_off()

    # Shared colour bar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes, orientation="horizontal",
                        fraction=0.04, pad=0.08, aspect=40)
    cbar.set_label("Change in V/C Ratio (positive = more congestion under ToU)", fontsize=11)

    # Legend
    legend_elements = [
        Line2D([0], [0], color="#d32f2f", linewidth=2, label="More congested (ToU)"),
        Line2D([0], [0], color="#1565c0", linewidth=2, label="Less congested (ToU)"),
        Line2D([0], [0], color="#333333", linewidth=1.5, linestyle="--", label="CBD cordon"),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=3,
               fontsize=10, frameon=True, bbox_to_anchor=(0.5, -0.01))

    fig.suptitle("Congestion Redistribution Under Time-of-Use Charging\n"
                 "(Difference in peak-hour V/C: red = increased, blue = decreased)",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout(rect=[0, 0.04, 1, 0.98])
    plt.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close()
    print(f"  Saved {out_path}")


# ── 9. Main ────────────────────────────────────────────────────────────

def main():
    print("Loading network data...")
    nodes, links, buildings = load_network()
    cbd_polygon, sa3_polys, study_area, nztm_bbox = load_sa3_boundary()

    print("Building graph...")
    G = build_graph(nodes, links, cbd_polygon)
    n_edges = G.number_of_edges()
    print(f"  Graph: {len(G.nodes)} nodes, {n_edges} edges")

    print("Loading shapefiles...")
    gdf_roads = gpd.read_file(DATA_DIR + "roads/akl_rd_cleaned.shp")
    gdf_sa3 = gpd.read_file(DATA_DIR + "roads/akl_boundary.shp")
    gdf_cbd_sa3 = gpd.read_file(DATA_DIR + "roads/akl_CBD_SA3.gpkg")

    print("Mapping simulation links to shapefile geometry...")
    shp_to_link = build_link_id_to_geom(G, gdf_roads, nodes, nztm_bbox)
    print(f"  Matched {len(shp_to_link)}/{len(gdf_roads)} road segments")

    # Run simulations
    results = {}
    configs = [
        ("baseline", "none"), ("baseline", "tou"),
        ("el_farol", "none"), ("el_farol", "tou"),
        ("qlearning", "none"), ("qlearning", "tou"),
    ]

    for model, fee in configs:
        label = f"{model} / {fee}"
        print(f"Running simulation: {label}...")
        random.seed(42)
        np.random.seed(42)
        link_vc = run_sim_with_link_vc(G, model, fee, n_days=20, n_agents=500)
        results[(model, fee)] = link_vc
        active = sum(1 for v in link_vc.values() if v > 0)
        mean_vc = np.mean(list(link_vc.values())) if link_vc else 0
        print(f"  {label}: {active} active links, mean V/C = {mean_vc:.3f}")

    print("\nCreating comparison maps...")
    plot_comparison_maps(gdf_roads, gdf_sa3, gdf_cbd_sa3, shp_to_link,
                         results, OUT_DIR + "fig_congestion_comparison.png")

    print("Creating difference maps...")
    plot_difference_maps(gdf_roads, gdf_sa3, gdf_cbd_sa3, shp_to_link,
                         results, OUT_DIR + "fig_congestion_diff.png")

    # Summary statistics
    print("\n=== Congestion redistribution summary ===")
    for model in ["baseline", "el_farol", "qlearning"]:
        vc_none = results[(model, "none")]
        vc_tou = results[(model, "tou")]
        all_lids = set(vc_none.keys()) | set(vc_tou.keys())

        increased = sum(1 for lid in all_lids
                        if vc_tou.get(lid, 0) > vc_none.get(lid, 0) + 0.05)
        decreased = sum(1 for lid in all_lids
                        if vc_tou.get(lid, 0) < vc_none.get(lid, 0) - 0.05)
        print(f"  {model}: {increased} links MORE congested under ToU, "
              f"{decreased} links LESS congested")

        # By road type
        for rtype in ["inner", "boundary", "peripheral"]:
            rtype_lids = [lid for u, v, d in G.edges(data=True)
                          if d["road_type"] == rtype
                          for lid in [d["link_id"]]]
            rtype_set = set(rtype_lids)
            none_vals = [vc_none.get(lid, 0) for lid in rtype_set if lid in all_lids]
            tou_vals = [vc_tou.get(lid, 0) for lid in rtype_set if lid in all_lids]
            if none_vals:
                print(f"    {rtype}: no-charge mean V/C={np.mean(none_vals):.3f}, "
                      f"ToU mean V/C={np.mean(tou_vals):.3f}, "
                      f"change={np.mean(tou_vals)-np.mean(none_vals):+.3f}")

    print("\nDone!")


if __name__ == "__main__":
    main()
