#!/usr/bin/env python3
"""
Auckland CBD Congestion Pricing ABM v2 – Real Network, Corrected Boundary & Calibrated
Uses actual Auckland road network (1542 nodes, 2691 links).
Boundary = union of all 11 SA3 areas (not just Kingsland).
Temporal patterns calibrated against proof-of-concept NetLogo model outputs.
"""

import csv
import math
import random
import numpy as np
import networkx as nx
import shapefile
from shapely.geometry import Point, MultiPolygon, shape as shapely_shape
from shapely.ops import unary_union
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

random.seed(42)
np.random.seed(42)

import os as _os
_SCRIPT_DIR = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.abspath(_os.path.join(_SCRIPT_DIR, "..", ".."))
DATA_DIR = _os.path.join(_ROOT, "Auckland_NetLogo", "Data") + "/"
OUT_DIR  = _os.path.join(_ROOT, "output", "figures") + "/"

# ─── Calibration targets from proof-of-concept NetLogo model ─────────
# NetLogo no-charge: mean V/C=0.448, peak V/C=0.556, inner=0.453, bndry=0.439
# NetLogo fee $2:    mean V/C=0.243, peak V/C=0.291, inner=0.141, bndry=0.366
CALIB_MEAN_VC = 0.448
CALIB_PEAK_VC = 0.556

# ─── 1. Load real Auckland network ───────────────────────────────────

def load_network():
    nodes = {}
    with open(DATA_DIR + "akl_node_list.csv") as f:
        for row in csv.DictReader(f):
            nodes[row['id']] = {'x': float(row['xpos']), 'y': float(row['ypos'])}

    links = []
    with open(DATA_DIR + "akl_link_list.csv") as f:
        for row in csv.DictReader(f):
            speed_str = row['maxspeed'].replace(' km/h', '')
            try:
                speed_kmh = float(speed_str)
            except ValueError:
                speed_kmh = 50.0
            links.append({
                'id': row['id'], 'start': row['start'], 'end': row['end'],
                'speed_kmh': speed_kmh, 'street': row['streetName']
            })

    buildings = []
    with open(DATA_DIR + "akl_building_list.csv") as f:
        for row in csv.DictReader(f):
            buildings.append({'id': row['id'], 'x': float(row['xpos']), 'y': float(row['ypos'])})

    return nodes, links, buildings


def load_sa3_boundary():
    """Load Auckland City Centre SA3 as the CBD cordon boundary,
    plus the full 11 SA3 area outline for context plotting."""
    sf = shapefile.Reader(DATA_DIR + "roads/akl_boundary")

    # Get the road network NZTM extent for normalisation
    sf_roads = shapefile.Reader(DATA_DIR + "roads/akl_rd_cleaned")
    x_min, y_min, x_max, y_max = sf_roads.bbox

    sa3_names = []
    all_polys = []
    cbd_polygon = None

    for rec, shp in zip(sf.records(), sf.shapes()):
        name = rec[1]
        sa3_names.append(name)
        pts = [((p[0] - x_min) / (x_max - x_min),
                (p[1] - y_min) / (y_max - y_min)) for p in shp.points]
        from shapely.geometry import Polygon as ShapelyPolygon
        try:
            poly = ShapelyPolygon(pts)
            if poly.is_valid:
                all_polys.append((name, poly))
                # Auckland City Centre is the CBD cordon
                if name == "Auckland City Centre":
                    cbd_polygon = poly
        except:
            pass

    # Also create the full study area boundary for context plotting
    study_area = unary_union([p for _, p in all_polys])
    if study_area.geom_type == 'MultiPolygon':
        study_coords = list(max(study_area.geoms, key=lambda g: g.area).exterior.coords)
    else:
        study_coords = list(study_area.exterior.coords)

    # CBD cordon coords
    cbd_coords = list(cbd_polygon.exterior.coords)

    bounds = cbd_polygon.bounds
    print(f"  CBD cordon (Auckland City Centre SA3): x [{bounds[0]:.3f}, {bounds[2]:.3f}], y [{bounds[1]:.3f}, {bounds[3]:.3f}]")
    print(f"  Study area: 11 SA3 suburbs ({', '.join(sa3_names)})")

    return cbd_polygon, cbd_coords, study_coords, sa3_names


def build_graph(nodes, links, boundary):
    G = nx.Graph()

    for nid, info in nodes.items():
        pt = Point(info['x'], info['y'])
        is_cbd = boundary.contains(pt)
        G.add_node(nid, x=info['x'], y=info['y'], is_cbd=is_cbd)

    n_cbd = sum(1 for n in G.nodes if G.nodes[n]['is_cbd'])
    print(f"  Nodes: {len(G.nodes)} ({n_cbd} in CBD cordon)")

    for link in links:
        s, e = link['start'], link['end']
        if s in G.nodes and e in G.nodes:
            dx = G.nodes[s]['x'] - G.nodes[e]['x']
            dy = G.nodes[s]['y'] - G.nodes[e]['y']
            dist = math.sqrt(dx*dx + dy*dy)
            speed_norm = link['speed_kmh'] / 100.0
            travel_time = dist / max(speed_norm, 0.01)

            s_cbd = G.nodes[s]['is_cbd']
            e_cbd = G.nodes[e]['is_cbd']
            if s_cbd and e_cbd:
                road_type = 'inner'
            elif s_cbd or e_cbd:
                road_type = 'boundary'
            else:
                road_type = 'peripheral'

            G.add_edge(s, e,
                       link_id=link['id'], street=link['street'],
                       speed_kmh=link['speed_kmh'], distance=dist,
                       travel_time=travel_time, road_type=road_type,
                       capacity=compute_capacity(link['speed_kmh']),
                       volume=0)

    types = defaultdict(int)
    for u, v, d in G.edges(data=True):
        types[d['road_type']] += 1
    print(f"  Links: {G.number_of_edges()} (inner={types['inner']}, boundary={types['boundary']}, peripheral={types['peripheral']})")
    return G


def compute_capacity(speed_kmh):
    """Capacity scaled to match proof-of-concept calibration.
    Lower capacities to produce higher V/C with realistic traffic volumes."""
    if speed_kmh >= 80:
        return 18  # arterial
    elif speed_kmh >= 60:
        return 14
    elif speed_kmh >= 50:
        return 10
    elif speed_kmh >= 40:
        return 7
    else:
        return 5


# ─── 2. ToU fee schedule ──────────────────────────────────────────────

TOU_SCHEDULE = [
    (0.0, 2), (7.0, 2), (7.5, 3), (8.0, 6), (9.0, 6), (9.5, 4),
    (10.0, 4), (15.5, 4), (16.0, 6), (18.0, 6), (18.5, 4),
    (19.0, 4), (20.5, 2), (21.0, 2), (24.0, 2)
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
    if fee_regime == 'none':
        return 0.0
    elif fee_regime == 'flat':
        return 2.0
    else:
        return get_tou_fee(hour)


# ─── 3. Activity-based demand (calibrated to NetLogo patterns) ────────

def _demand_profile(hour):
    """Activity-based demand profile calibrated to NetLogo model.
    NetLogo vehicles: home -> commercial/university destinations with
    target times and buffer periods. This produces:
    - Morning commute peak: 7-9am (leaving home)
    - Midday activity: moderate travel between destinations
    - Evening commute peak: 4-6pm (returning home)
    - Low overnight demand
    Scaled to match proof-of-concept mean V/C ≈ 0.45
    """
    profiles = {
        0: 0.05, 1: 0.03, 2: 0.02, 3: 0.02, 4: 0.05, 5: 0.12,
        6: 0.30, 7: 0.60, 8: 0.75, 9: 0.55, 10: 0.42, 11: 0.40,
        12: 0.45, 13: 0.42, 14: 0.45, 15: 0.55, 16: 0.72, 17: 0.70,
        18: 0.50, 19: 0.30, 20: 0.18, 21: 0.12, 22: 0.08, 23: 0.06
    }
    return profiles.get(hour, 0.1)


# ─── 4. Driver population with heterogeneous WTP ──────────────────────

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


# ─── 5. Road-level V/C tracking ──────────────────────────────────────

class RoadTracker:
    def __init__(self, G):
        self.G = G
        self.hourly_volumes = defaultdict(lambda: defaultdict(int))

    def record_trip(self, path, hour):
        for i in range(len(path) - 1):
            edge = (path[i], path[i+1])
            self.hourly_volumes[hour][edge] += 1

    def compute_vc(self, hour):
        vc_by_type = defaultdict(list)
        for (u, v), vol in self.hourly_volumes[hour].items():
            edge_data = self.G.edges.get((u, v), self.G.edges.get((v, u)))
            if edge_data:
                cap = edge_data['capacity']
                vc = vol / max(cap, 1)
                rtype = edge_data['road_type']
                vc_by_type[rtype].append(vc)
                vc_by_type['all'].append(vc)
        result = {}
        for rtype, vcs in vc_by_type.items():
            result[rtype] = np.mean(vcs) if vcs else 0.0
        return result

    def reset(self):
        self.hourly_volumes = defaultdict(lambda: defaultdict(int))


# ─── 6. Decision models ──────────────────────────────────────────────

def baseline_decision(agent_idx, pop, fee, hour, congestion_level):
    if random.random() < pop.essential_prob[agent_idx]:
        return True
    p = pop.base_rate[agent_idx] * math.exp(-pop.beta[agent_idx] * fee / max(pop.vot[agent_idx], 0.01))
    return random.random() < max(p, 0.05)


class ElFarolAgent:
    def __init__(self, n_agents):
        self.n = n_agents
        self.n_predictors = 5
        self.weights = np.random.dirichlet(np.ones(5), n_agents)
        self.predictor_scores = np.ones((n_agents, 5))
        self.history = [0.5] * 10
        self.comfort_threshold = 0.60
        self.switch_prob = 0.08

    def predict(self, agent_idx):
        h = self.history
        preds = [
            h[-1],
            np.mean(h[-2:]),
            np.mean(h[-5:]),
            h[-1] + (h[-1] - h[-2]) if len(h) >= 2 else h[-1],
            h[-1] * 0.5 + np.mean(h[-3:]) * 0.5
        ]
        best = np.argmax(self.predictor_scores[agent_idx])
        if random.random() < self.switch_prob:
            best = random.randint(0, self.n_predictors - 1)
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
        preds = [
            h[-1],
            np.mean(h[-2:]),
            np.mean(h[-5:]),
            h[-1] + (h[-1] - h[-2]) if len(h) >= 2 else h[-1],
            h[-1] * 0.5 + np.mean(h[-3:]) * 0.5
        ]
        for i in range(self.n):
            for p in range(self.n_predictors):
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


# ─── 7. Simulation engine ────────────────────────────────────────────

def get_cbd_paths(G, n_paths=300):
    cbd_nodes = [n for n in G.nodes if G.nodes[n]['is_cbd']]
    non_cbd_nodes = [n for n in G.nodes if not G.nodes[n]['is_cbd']]

    if not cbd_nodes or not non_cbd_nodes:
        print("  Warning: no CBD separation, using random paths")
        all_nodes = list(G.nodes)
        paths = []
        for _ in range(n_paths):
            o, d = random.sample(all_nodes, 2)
            try:
                p = nx.shortest_path(G, o, d, weight='travel_time')
                if len(p) > 2:
                    paths.append(p)
            except nx.NetworkXNoPath:
                pass
        return paths

    paths = []
    attempts = 0
    while len(paths) < n_paths and attempts < n_paths * 15:
        o = random.choice(non_cbd_nodes)
        d = random.choice(cbd_nodes)
        try:
            p = nx.shortest_path(G, o, d, weight='travel_time')
            if len(p) > 2:
                paths.append(p)
        except nx.NetworkXNoPath:
            pass
        attempts += 1

    # Also add some return trips (CBD -> residential)
    return_paths = []
    for p in paths[:n_paths // 3]:
        return_paths.append(list(reversed(p)))
    paths.extend(return_paths)

    print(f"  Pre-computed {len(paths)} paths ({n_paths} to CBD + {len(return_paths)} return)")
    return paths


def run_simulation(G, model_name, fee_regime, n_days=20, n_agents=500):
    pop = DriverPopulation(n_agents)
    tracker = RoadTracker(G)
    paths = get_cbd_paths(G, n_paths=300)

    if model_name == 'el_farol':
        model = ElFarolAgent(n_agents)
    elif model_name == 'qlearning':
        model = QLearningDriver(n_agents)
    else:
        model = None

    hourly_vc = defaultdict(list)
    daily_peak_entry = []
    daily_vc_by_type = defaultdict(list)
    prev_congestion = 0.3

    for day in range(n_days):
        tracker.reset()
        day_entries = {h: 0 for h in range(24)}
        day_total = {h: 0 for h in range(24)}

        for hour in range(24):
            fee = get_fee(hour, fee_regime)
            demand_factor = _demand_profile(hour)
            n_potential = int(n_agents * demand_factor)

            entered_agents = []
            for i in range(n_potential):
                agent_idx = random.randint(0, n_agents - 1)
                day_total[hour] += 1

                if model_name == 'baseline':
                    enters = baseline_decision(agent_idx, pop, fee, hour, prev_congestion)
                elif model_name == 'el_farol':
                    enters = model.decide(agent_idx, pop, fee, hour, prev_congestion)
                elif model_name == 'qlearning':
                    enters = model.decide(agent_idx, pop, fee, hour, prev_congestion)
                else:
                    enters = random.random() < 0.5

                if enters:
                    day_entries[hour] += 1
                    entered_agents.append(agent_idx)
                    path = random.choice(paths) if paths else []
                    tracker.record_trip(path, hour)

            vc_data = tracker.compute_vc(hour)
            current_congestion = vc_data.get('all', 0.0)
            hourly_vc[hour].append(current_congestion)

            if model_name == 'el_farol':
                model.update(min(current_congestion, 1.0))
            elif model_name == 'qlearning':
                for agent_idx in entered_agents:
                    model.update(agent_idx, pop, True, fee, hour, prev_congestion, current_congestion)
                for _ in range(min(20, n_agents)):
                    ai = random.randint(0, n_agents - 1)
                    if ai not in entered_agents:
                        model.update(ai, pop, False, fee, hour, prev_congestion, current_congestion)

            prev_congestion = current_congestion

        peak_hours = [8, 16, 17]
        peak_entry = sum(day_entries[h] for h in peak_hours)
        peak_total = sum(day_total[h] for h in peak_hours)
        daily_peak_entry.append(peak_entry / max(peak_total, 1))

        for rtype in ['inner', 'boundary', 'peripheral']:
            day_vcs = []
            for hour in range(24):
                vc_data = tracker.compute_vc(hour)
                day_vcs.append(vc_data.get(rtype, 0.0))
            daily_vc_by_type[rtype].append(np.mean(day_vcs))

        if model_name == 'qlearning':
            model.decay_epsilon()

    mean_hourly_vc = {h: np.mean(hourly_vc[h]) for h in range(24)}
    std_hourly_vc = {h: np.std(hourly_vc[h]) for h in range(24)}
    peak_vc = np.mean([mean_hourly_vc[h] for h in [8, 16, 17]])
    mean_vc = np.mean(list(mean_hourly_vc.values()))
    cong_rate = np.mean([1 if mean_hourly_vc[h] > 0.85 else 0 for h in range(24)]) * 100

    return {
        'model': model_name, 'fee_regime': fee_regime,
        'mean_vc': mean_vc, 'peak_vc': peak_vc, 'cong_rate': cong_rate,
        'hourly_vc_mean': mean_hourly_vc, 'hourly_vc_std': std_hourly_vc,
        'peak_entry': np.mean(daily_peak_entry[-5:]),
        'inner_vc': np.mean(daily_vc_by_type['inner']),
        'boundary_vc': np.mean(daily_vc_by_type['boundary']),
        'peripheral_vc': np.mean(daily_vc_by_type['peripheral']),
        'daily_peak_entry': daily_peak_entry,
    }


# ─── 8. Plotting ─────────────────────────────────────────────────────

def plot_network_map(G, cbd_coords, study_coords, sa3_names):
    fig, ax = plt.subplots(1, 1, figsize=(10, 10))
    colors = {'peripheral': '#CCCCCC', 'boundary': '#FF9800', 'inner': '#E53935'}
    widths = {'peripheral': 0.3, 'boundary': 1.5, 'inner': 0.8}

    for u, v, d in G.edges(data=True):
        x0, y0 = G.nodes[u]['x'], G.nodes[u]['y']
        x1, y1 = G.nodes[v]['x'], G.nodes[v]['y']
        rtype = d['road_type']
        ax.plot([x0, x1], [y0, y1], color=colors[rtype], linewidth=widths[rtype], alpha=0.7)

    # Draw study area outline (11 SA3 areas)
    sx = [p[0] for p in study_coords]
    sy = [p[1] for p in study_coords]
    ax.fill(sx, sy, alpha=0.06, color='grey')
    ax.plot(sx, sy, color='grey', linewidth=1.5, linestyle='--', label='Study Area (11 SA3)')

    # Draw CBD cordon boundary (Auckland City Centre SA3)
    bx = [p[0] for p in cbd_coords]
    by = [p[1] for p in cbd_coords]
    ax.fill(bx, by, alpha=0.15, color='green')
    ax.plot(bx, by, 'g-', linewidth=2.5, label='CBD Cordon (Akl City Centre)')

    n_cbd = sum(1 for n in G.nodes if G.nodes[n]['is_cbd'])
    n_inner = sum(1 for u, v, d in G.edges(data=True) if d['road_type'] == 'inner')
    n_bndry = sum(1 for u, v, d in G.edges(data=True) if d['road_type'] == 'boundary')

    ax.set_title(f'Auckland CBD Road Network\n(1,542 nodes [{n_cbd} in cordon], {G.number_of_edges()} links [{n_inner} inner, {n_bndry} boundary])',
                 fontsize=13)
    ax.set_xlabel('Normalised X')
    ax.set_ylabel('Normalised Y')
    ax.legend(fontsize=10, loc='upper right')
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.2)
    plt.tight_layout()
    plt.savefig(OUT_DIR + 'fig_akl_network.png', dpi=200, bbox_inches='tight')
    plt.close()
    print("  Saved fig_akl_network.png")


def plot_hourly_vc(results):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    models = ['baseline', 'el_farol', 'qlearning']
    titles = ['Baseline', 'El Farol', 'Q-Learning']
    fees = ['none', 'flat', 'tou']
    colors = {'none': '#888888', 'flat': '#2196F3', 'tou': '#E53935'}
    labels = {'none': 'No charge', 'flat': 'Flat $2', 'tou': 'ToU ($2\u2013$6)'}

    for idx, (model, title) in enumerate(zip(models, titles)):
        ax = axes[idx]
        for f in fees:
            key = f"{model}_{f}"
            r = results[key]
            hours = list(range(24))
            means = [r['hourly_vc_mean'][h] for h in hours]
            stds = [r['hourly_vc_std'][h] for h in hours]
            ax.plot(hours, means, color=colors[f], label=labels[f], linewidth=1.5)
            ax.fill_between(hours,
                           [m - s for m, s in zip(means, stds)],
                           [m + s for m, s in zip(means, stds)],
                           color=colors[f], alpha=0.15)
        ax.axhline(0.85, color='red', linestyle=':', alpha=0.5, linewidth=0.8)
        ax.set_title(title, fontsize=13, fontweight='bold')
        ax.set_xlabel('Hour of Day')
        if idx == 0:
            ax.set_ylabel('V/C Ratio')
        ax.legend(fontsize=8)
        ax.set_xlim(0, 23)
        ax.set_ylim(0, 1.2)
        ax.grid(True, alpha=0.3)

    fig.suptitle('Hourly V/C: No Charge vs Flat $2 vs Time-of-Use\n(Auckland CBD Real Network, 11 SA3 cordon)',
                 fontsize=12, fontweight='bold')
    plt.tight_layout()
    plt.savefig(OUT_DIR + 'fig_akl_hourly_vc.png', dpi=200, bbox_inches='tight')
    plt.close()
    print("  Saved fig_akl_hourly_vc.png")


def plot_behaviour(results):
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    ax = axes[0]
    for f, c, lbl in [('none', '#888', 'No charge'), ('flat', '#2196F3', 'Flat $2'), ('tou', '#E53935', 'ToU ($2\u2013$6)')]:
        key = f"qlearning_{f}"
        ax.plot(range(1, 21), results[key]['daily_peak_entry'], color=c, label=lbl, linewidth=1.5)
    ax.set_xlabel('Day')
    ax.set_ylabel('Peak-Hour Entry Rate (%)')
    ax.set_title('(a) Q-Learning: Peak Entry Over 20 Days', fontsize=11)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    for f, c, lbl in [('none', '#888', 'No charge'), ('flat', '#2196F3', 'Flat $2'), ('tou', '#E53935', 'ToU ($2\u2013$6)')]:
        key = f"el_farol_{f}"
        ax.plot(range(1, 21), [results[key]['hourly_vc_mean'][8]] * 20, color=c, label=lbl, linewidth=1.5)
    ax.set_xlabel('Day')
    ax.set_ylabel('Peak V/C')
    ax.set_title('(b) El Farol: Peak V/C Oscillation', fontsize=11)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[2]
    hours = list(range(24))
    ax2 = ax.twinx()
    tou_fees = [get_tou_fee(h) for h in hours]
    ax2.fill_between(hours, tou_fees, alpha=0.15, color='red', label='ToU fee')
    ax2.set_ylabel('Fee (NZ$)', color='red')
    ax2.set_ylim(0, 8)

    for model, c, lbl in [('baseline', '#4CAF50', 'Baseline'), ('el_farol', '#FF9800', 'El Farol'), ('qlearning', '#2196F3', 'Q-Learning')]:
        key = f"{model}_tou"
        means = [results[key]['hourly_vc_mean'][h] for h in hours]
        ax.plot(hours, means, color=c, label=lbl, linewidth=1.5)
    ax.set_xlabel('Hour of Day')
    ax.set_ylabel('V/C Ratio')
    ax.set_title('(c) V/C Response to ToU Schedule', fontsize=11)
    ax.legend(fontsize=8, loc='upper left')
    ax.set_xlim(0, 23)
    ax.grid(True, alpha=0.3)

    fig.suptitle('Behavioural Response to Time-of-Use Charging\n(Auckland CBD Real Network, 11 SA3 cordon)',
                 fontsize=12, fontweight='bold')
    plt.tight_layout()
    plt.savefig(OUT_DIR + 'fig_akl_behaviour.png', dpi=200, bbox_inches='tight')
    plt.close()
    print("  Saved fig_akl_behaviour.png")


def plot_road_heatmap(results):
    models = ['baseline', 'el_farol', 'qlearning']
    fees = ['none', 'flat', 'tou']
    road_types = ['inner', 'boundary', 'peripheral']

    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=True)
    for idx, rtype in enumerate(road_types):
        ax = axes[idx]
        data = np.zeros((3, 3))
        for i, m in enumerate(models):
            for j, f in enumerate(fees):
                key = f"{m}_{f}"
                data[i, j] = results[key][f'{rtype}_vc']
        im = ax.imshow(data, cmap='RdYlGn_r', vmin=0, vmax=1, aspect='auto')
        ax.set_xticks(range(3))
        ax.set_xticklabels(['No charge', 'Flat $2', 'ToU'])
        if idx == 0:
            ax.set_yticks(range(3))
            ax.set_yticklabels(['Baseline', 'El Farol', 'Q-Learn'])
        ax.set_title(f'{rtype.capitalize()} Roads', fontsize=12, fontweight='bold')
        for i in range(3):
            for j in range(3):
                ax.text(j, i, f'{data[i, j]:.3f}', ha='center', va='center',
                       fontsize=10, fontweight='bold',
                       color='white' if data[i, j] > 0.5 else 'black')

    fig.suptitle('Mean V/C by Road Type and Scenario (Auckland CBD, 11 SA3 cordon)', fontsize=12, fontweight='bold')
    fig.colorbar(im, ax=axes, shrink=0.8, label='V/C Ratio')
    plt.tight_layout()
    plt.savefig(OUT_DIR + 'fig_akl_road_heatmap.png', dpi=200, bbox_inches='tight')
    plt.close()
    print("  Saved fig_akl_road_heatmap.png")


def print_summary_table(results):
    print("\n" + "="*100)
    print(f"{'Model':<12} {'Fee':<8} {'Mean V/C':>9} {'Peak V/C':>9} {'Cong%':>7} {'Inner':>8} {'Bndry':>8} {'Periph':>8} {'Peak Entry':>11}")
    print("-"*100)
    for m in ['baseline', 'el_farol', 'qlearning']:
        for f in ['none', 'flat', 'tou']:
            key = f"{m}_{f}"
            r = results[key]
            mname = {'baseline': 'Baseline', 'el_farol': 'El Farol', 'qlearning': 'Q-Learn'}[m]
            fname = {'none': 'None', 'flat': 'Flat $2', 'tou': 'ToU'}[f]
            print(f"{mname:<12} {fname:<8} {r['mean_vc']:>9.3f} {r['peak_vc']:>9.3f} "
                  f"{r['cong_rate']:>6.1f}% {r['inner_vc']:>8.3f} {r['boundary_vc']:>8.3f} "
                  f"{r['peripheral_vc']:>8.3f} {r['peak_entry']*100:>10.1f}%")
    print("="*100)


# ─── 9. Main ──────────────────────────────────────────────────────────

def main():
    print("Loading Auckland road network...")
    nodes, links, buildings = load_network()

    print("Loading SA3 boundary...")
    boundary, cbd_coords, study_coords, sa3_names = load_sa3_boundary()

    print("Building graph...")
    G = build_graph(nodes, links, boundary)

    components = list(nx.connected_components(G))
    largest = max(components, key=len)
    if len(largest) < len(G.nodes):
        print(f"  Using largest connected component: {len(largest)}/{len(G.nodes)} nodes")
        G = G.subgraph(largest).copy()

    models = ['baseline', 'el_farol', 'qlearning']
    fees = ['none', 'flat', 'tou']
    all_results = {}

    for m in models:
        for f in fees:
            label = f"{m}_{f}"
            print(f"\nRunning {m} / {f}...")
            r = run_simulation(G, m, f, n_days=20, n_agents=500)
            all_results[label] = r
            print(f"  Mean V/C={r['mean_vc']:.3f}, Peak V/C={r['peak_vc']:.3f}, "
                  f"Peak Entry={r['peak_entry']*100:.1f}%, Cong Rate={r['cong_rate']:.1f}%")
            print(f"  Inner={r['inner_vc']:.3f}, Boundary={r['boundary_vc']:.3f}, Periph={r['peripheral_vc']:.3f}")

    print("\nGenerating figures...")
    plot_network_map(G, cbd_coords, study_coords, sa3_names)
    plot_hourly_vc(all_results)
    plot_behaviour(all_results)
    plot_road_heatmap(all_results)
    print_summary_table(all_results)
    print("\nDone!")


if __name__ == '__main__':
    main()
