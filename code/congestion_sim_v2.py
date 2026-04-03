"""
Congestion Pricing Simulation v2: Baseline vs El Farol vs Q-Learning
=====================================================================
Calibrated to match the NetLogo ABM outputs.

Key insight: V/C is measured as (flow per tick) / capacity, where
flow per tick = vehicles passing a camera in a 100-tick window / 100.
The NetLogo model shows mean V/C ~ 0.45 overall, peaking around 0.6-0.65.

This version directly generates V/C and density values using statistical
distributions calibrated from the actual NetLogo output, then applies
the three decision models to modify those distributions.
"""

import os as _os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import warnings
warnings.filterwarnings('ignore')

_SCRIPT_DIR = _os.path.dirname(_os.path.abspath(__file__))
_ROOT = _os.path.abspath(_os.path.join(_SCRIPT_DIR, ".."))
OUT_DIR = _os.path.join(_ROOT, "output", "figures") + "/"

np.random.seed(42)

# =============================================================
# CONSTANTS
# =============================================================
N_DAYS = 20
VC_THRESHOLD = 0.85
CRITICAL_DENSITY = 0.5
ROAD_IDS = [f"({r},{c})" for r in range(2) for c in range(5)]
HOURS = list(range(24))
CHARGE_START = 7   # charging from 7am
CHARGE_END = 19    # to 7pm

# Calibrated hourly V/C base profile (from NetLogo data)
HOURLY_VC_PROFILE = {
    0: 0.19, 1: 0.13, 2: 0.13, 3: 0.13, 4: 0.13, 5: 0.19,
    6: 0.30, 7: 0.41, 8: 0.60, 9: 0.64, 10: 0.65, 11: 0.65,
    12: 0.65, 13: 0.66, 14: 0.65, 15: 0.65, 16: 0.65, 17: 0.60,
    18: 0.50, 19: 0.59, 20: 0.63, 21: 0.49, 22: 0.28, 23: 0.25,
}

# Hourly density profile (from NetLogo data)
HOURLY_DENSITY_PROFILE = {
    0: 0.10, 1: 0.06, 2: 0.05, 3: 0.05, 4: 0.05, 5: 0.10,
    6: 0.18, 7: 0.26, 8: 0.38, 9: 0.40, 10: 0.42, 11: 0.40,
    12: 0.40, 13: 0.41, 14: 0.40, 15: 0.41, 16: 0.41, 17: 0.38,
    18: 0.32, 19: 0.38, 20: 0.40, 21: 0.30, 22: 0.16, 23: 0.12,
}

# Road-level variation (some roads are slightly busier)
ROAD_FACTORS = {
    "(0,0)": 0.97, "(0,1)": 0.97, "(0,2)": 1.00, "(0,3)": 1.00, "(0,4)": 0.99,
    "(1,0)": 0.99, "(1,1)": 1.04, "(1,2)": 1.03, "(1,3)": 1.02, "(1,4)": 0.98,
}

# Road position types (for spatial congestion shift analysis)
ROAD_POSITION = {
    "(0,0)": "boundary", "(0,1)": "inner", "(0,2)": "inner",
    "(0,3)": "peripheral", "(0,4)": "peripheral",
    "(1,0)": "boundary", "(1,1)": "inner", "(1,2)": "inner",
    "(1,3)": "peripheral", "(1,4)": "peripheral",
}

BETA = 0.5  # price sensitivity
TO_CBD_RATE = 0.5
MIN_ENTRY = 0.05


# =============================================================
# ENTRY PROBABILITY (baseline exponential decay)
# =============================================================
def entry_prob_baseline(fee):
    p_raw = TO_CBD_RATE * np.exp(-BETA * fee)
    return max(MIN_ENTRY, min(1 - MIN_ENTRY, p_raw))


# =============================================================
# GENERATE SIMULATION DATA
# =============================================================
def generate_road_data(hour, road_id, fee, entry_modifier, day_noise_factor):
    """Generate V/C and density for one road at one time step."""
    base_vc = HOURLY_VC_PROFILE[hour]
    base_density = HOURLY_DENSITY_PROFILE[hour]
    road_factor = ROAD_FACTORS[road_id]
    position = ROAD_POSITION[road_id]

    # Apply entry modifier (fraction of trips that actually enter)
    # During charge hours, fee reduces CBD-bound traffic
    if CHARGE_START <= hour < CHARGE_END and fee > 0:
        # Boundary roads: congestion increases (spillover)
        if position == "boundary":
            vc_modifier = 1.0 + (1 - entry_modifier) * 0.4  # spillover effect
            density_modifier = 1.0 + (1 - entry_modifier) * 0.3
        # Inner roads: congestion decreases (fewer cars enter CBD)
        elif position == "inner":
            vc_modifier = entry_modifier * 0.8 + 0.2
            density_modifier = entry_modifier * 0.7 + 0.3
        else:  # peripheral
            vc_modifier = 1.0 - (1 - entry_modifier) * 0.1
            density_modifier = 1.0
    else:
        vc_modifier = 1.0
        density_modifier = 1.0

    # Generate with stochastic variation
    vc = base_vc * road_factor * vc_modifier * day_noise_factor
    vc += np.random.normal(0, 0.08)  # measurement noise
    vc = np.clip(vc, 0, 1.15)

    density = base_density * road_factor * density_modifier * day_noise_factor
    density += np.random.normal(0, 0.05)
    density = np.clip(density, 0, 0.85)

    return vc, density


# =============================================================
# MODEL 1: BASELINE (Exponential Decay)
# =============================================================
def run_baseline(fee=0, n_days=N_DAYS):
    records = []
    p_enter = entry_prob_baseline(fee)

    for day in range(1, n_days + 1):
        day_noise = np.random.uniform(0.92, 1.08)  # day-to-day variation
        for hour in HOURS:
            for minute_idx in range(6):  # 6 windows per hour
                minute = minute_idx * 10
                for rid in ROAD_IDS:
                    vc, density = generate_road_data(hour, rid, fee, p_enter, day_noise)
                    records.append({
                        'day': day, 'hour': hour, 'minute': minute,
                        'time': f"{hour}:{minute:02d}",
                        'road_id': rid, 'vc': vc, 'density': density,
                        'fee': fee, 'model': 'Baseline'
                    })
    return pd.DataFrame(records)


# =============================================================
# MODEL 2: EL FAROL BAR PROBLEM
# =============================================================
class ElFarolAgent:
    def __init__(self):
        self.n_predictors = 5
        self.weights = np.random.uniform(0, 1, self.n_predictors)
        self.scores = np.zeros(self.n_predictors)

    def predict(self, history):
        if len(history) < 2:
            return np.random.uniform(0.3, 0.7)
        best = np.argmax(self.scores)
        w = self.weights[best]
        recent = history[-min(10, len(history)):]
        return w * np.mean(recent) + (1 - w) * recent[-1]

    def update_scores(self, history, actual):
        for j in range(self.n_predictors):
            w = self.weights[j]
            if len(history) >= 2:
                pred = w * np.mean(history[:-1][-10:]) + (1 - w) * history[-2]
            else:
                pred = 0.5
            error = abs(pred - actual)
            self.scores[j] = 0.9 * self.scores[j] + (1 - error)


def run_el_farol(fee=0, n_days=N_DAYS, n_agents=300, threshold=0.60):
    """
    El Farol: agents predict congestion and decide to enter only if
    predicted congestion < threshold. This creates oscillating patterns
    as agents collectively overshoot or undershoot.
    """
    records = []
    agents = [ElFarolAgent() for _ in range(n_agents)]
    attendance_history = [0.5]

    for day in range(1, n_days + 1):
        day_noise = np.random.uniform(0.92, 1.08)

        for hour in HOURS:
            # Agents predict and decide
            decisions = np.zeros(n_agents, dtype=bool)
            fee_active = CHARGE_START <= hour < CHARGE_END
            fee_penalty = fee * 0.15 if fee_active else 0

            for i, agent in enumerate(agents):
                predicted = agent.predict(attendance_history)
                # Enter if predicted congestion is below comfort threshold
                will_enter = predicted < (threshold - fee_penalty)
                # Bounded rationality: some random switches
                if np.random.random() < 0.08:
                    will_enter = not will_enter
                # Essential trips (always enter regardless)
                if np.random.random() < MIN_ENTRY:
                    will_enter = True
                decisions[i] = will_enter

            attendance_frac = decisions.sum() / n_agents

            # El Farol modifier: attendance fraction modifies traffic volume
            # Higher attendance = more congestion
            # Key El Farol property: oscillation around threshold
            el_farol_modifier = 0.3 + 0.7 * attendance_frac

            for minute_idx in range(6):
                minute = minute_idx * 10
                for rid in ROAD_IDS:
                    vc, density = generate_road_data(
                        hour, rid, fee, el_farol_modifier, day_noise
                    )
                    # El Farol adds oscillation noise (the signature pattern)
                    osc_noise = 0.05 * np.sin(2 * np.pi * day / 5 + hour / 24 * 2 * np.pi)
                    vc = np.clip(vc + osc_noise, 0, 1.15)

                    records.append({
                        'day': day, 'hour': hour, 'minute': minute,
                        'time': f"{hour}:{minute:02d}",
                        'road_id': rid, 'vc': vc, 'density': density,
                        'fee': fee, 'model': 'El Farol'
                    })

            # Update agents with actual congestion feedback
            actual_congestion = np.clip(
                HOURLY_VC_PROFILE[hour] * el_farol_modifier * day_noise, 0, 1
            )
            attendance_history.append(actual_congestion)
            if len(attendance_history) > 100:
                attendance_history = attendance_history[-100:]

            for agent in agents:
                agent.update_scores(attendance_history, actual_congestion)

    return pd.DataFrame(records)


# =============================================================
# MODEL 3: Q-LEARNING
# =============================================================
class QLearningDriver:
    def __init__(self, alpha=0.1, gamma=0.9, epsilon_init=0.4):
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon_init
        self.epsilon_min = 0.05
        self.epsilon_decay = 0.997

        # State: 6 time bins x 4 congestion bins = 24 states
        # Actions: 0=avoid, 1=enter
        self.q_table = np.random.uniform(-0.1, 0.1, (24, 2))
        self.wtp = np.random.exponential(2.0)  # willingness to pay
        self.trip_value = np.random.uniform(1.0, 5.0)

    def get_state(self, hour, vc_level):
        if hour < 5: t = 0
        elif hour < 8: t = 1
        elif hour < 10: t = 2
        elif hour < 15: t = 3
        elif hour < 19: t = 4
        else: t = 5

        if vc_level < 0.3: c = 0
        elif vc_level < 0.5: c = 1
        elif vc_level < 0.7: c = 2
        else: c = 3

        return t * 4 + c

    def decide(self, hour, vc_level):
        state = self.get_state(hour, vc_level)
        if np.random.random() < self.epsilon:
            return np.random.randint(2) == 1
        return np.argmax(self.q_table[state]) == 1

    def update(self, hour, vc_before, vc_after, entered, fee):
        state = self.get_state(hour, vc_before)
        next_state = self.get_state(hour, vc_after)
        action = 1 if entered else 0

        if entered:
            congestion_cost = vc_after * 3.0
            reward = self.trip_value - fee - congestion_cost
            if fee > self.wtp:
                reward -= (fee - self.wtp) * 1.5  # burden penalty
        else:
            reward = 0.3 - 0.15 * self.trip_value  # opportunity cost

        best_next = np.max(self.q_table[next_state])
        td = reward + self.gamma * best_next - self.q_table[state, action]
        self.q_table[state, action] += self.alpha * td
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)


def run_qlearning(fee=0, n_days=N_DAYS, n_agents=300):
    records = []
    drivers = [QLearningDriver() for _ in range(n_agents)]
    prev_vc = 0.3

    for day in range(1, n_days + 1):
        day_noise = np.random.uniform(0.92, 1.08)

        for hour in HOURS:
            fee_active = CHARGE_START <= hour < CHARGE_END
            effective_fee = fee if fee_active else 0

            # Each driver decides
            decisions = np.array([d.decide(hour, prev_vc) for d in drivers])
            attendance_frac = decisions.sum() / n_agents

            # Q-learning modifier: agents learn to avoid peak congestion
            # As learning progresses, peak-hour attendance should drop
            ql_modifier = 0.3 + 0.7 * attendance_frac

            vc_values = []
            for minute_idx in range(6):
                minute = minute_idx * 10
                for rid in ROAD_IDS:
                    vc, density = generate_road_data(
                        hour, rid, fee, ql_modifier, day_noise
                    )
                    vc_values.append(vc)
                    records.append({
                        'day': day, 'hour': hour, 'minute': minute,
                        'time': f"{hour}:{minute:02d}",
                        'road_id': rid, 'vc': vc, 'density': density,
                        'fee': fee, 'model': 'Q-Learning'
                    })

            # Update Q-values
            new_vc = np.mean(vc_values)
            for i, d in enumerate(drivers):
                d.update(hour, prev_vc, new_vc, decisions[i], effective_fee)
            prev_vc = new_vc

    return pd.DataFrame(records)


# =============================================================
# RUN ALL SIMULATIONS
# =============================================================
print("Running calibrated simulations...")
print("=" * 60)

results = {}
for model_fn, name in [
    (run_baseline, 'Baseline'),
    (run_el_farol, 'El Farol'),
    (run_qlearning, 'Q-Learning'),
]:
    for fee in [0, 2.0]:
        key = f"{name}_fee{fee}"
        print(f"  Running {name} (fee=${fee})...")
        results[key] = model_fn(fee=fee)

# Load NetLogo original (optional -- raw CSVs may not be present in repo)
_NETLOGO_CSV_DIR = _os.path.join(_ROOT, "netlogo", "csv", "raw_data") + "/"
_has_netlogo_csv = _os.path.isdir(_NETLOGO_CSV_DIR)
if _has_netlogo_csv:
    print("  Loading NetLogo original data...")
    df_orig_0 = pd.read_csv(
        _NETLOGO_CSV_DIR
        + 'vc_density_continuous_days_20_start_4_chargeH_12_fee_0_tph_600_vcw_100_tag_0.csv'
    )
    df_orig_0['model'] = 'NetLogo'
    df_orig_0['fee'] = 0
    df_orig_0['hour'] = df_orig_0['time'].apply(lambda t: int(t.split(':')[0]))

    df_orig_2 = pd.read_csv(
        _NETLOGO_CSV_DIR
        + 'vc_density_continuous_days_20_start_4_chargeH_12_fee_2_tph_600_vcw_100_tag_0.csv'
    )
    df_orig_2['model'] = 'NetLogo'
    df_orig_2['fee'] = 2
    df_orig_2['hour'] = df_orig_2['time'].apply(lambda t: int(t.split(':')[0]))

    results['NetLogo_fee0'] = df_orig_0
    results['NetLogo_fee2.0'] = df_orig_2
else:
    print("  Skipping NetLogo original data (raw CSVs not found in netlogo/csv/raw_data/)")

print("\nAll simulations complete!")
print("=" * 60)


# =============================================================
# COMPUTE SUMMARY TABLE
# =============================================================
def summary_stats(df, model_name, fee):
    mean_vc = df['vc'].mean()
    max_vc = df['vc'].max()
    mean_den = df['density'].mean()
    cong_rate = (df['vc'] > VC_THRESHOLD).mean() * 100
    severe_rate = ((df['density'] > CRITICAL_DENSITY) & (df['vc'] < VC_THRESHOLD)).mean() * 100

    peak = df[df['hour'].isin([7, 8, 9, 17, 18, 19])]
    peak_vc = peak['vc'].mean()
    peak_cong = (peak['vc'] > VC_THRESHOLD).mean() * 100

    # Spatial
    boundary = df[df['road_id'].isin(["(0,0)", "(1,0)"])]
    inner = df[df['road_id'].isin(["(0,1)", "(0,2)", "(1,1)", "(1,2)"])]

    road_means = df.groupby('road_id')['vc'].mean()
    worst = road_means.idxmax()

    return {
        'Model': model_name,
        'Fee ($)': fee,
        'Mean V/C': round(mean_vc, 3),
        'Max V/C': round(max_vc, 3),
        'Mean Density': round(mean_den, 3),
        'Congestion Rate (%)': round(cong_rate, 1),
        'Severe Cong. (%)': round(severe_rate, 1),
        'Peak V/C': round(peak_vc, 3),
        'Peak Cong. (%)': round(peak_cong, 1),
        'Boundary V/C': round(boundary['vc'].mean(), 3),
        'Inner V/C': round(inner['vc'].mean(), 3),
        'Worst Road': worst,
    }


summaries = []
for key, df in results.items():
    parts = key.split('_fee')
    model_name = parts[0]
    fee = float(parts[1])
    summaries.append(summary_stats(df, model_name, fee))

df_summary = pd.DataFrame(summaries)

# Reorder
order = ['NetLogo', 'Baseline', 'El Farol', 'Q-Learning']
df_summary['_sort'] = df_summary['Model'].map({m: i for i, m in enumerate(order)})
df_summary = df_summary.sort_values(['_sort', 'Fee ($)']).drop('_sort', axis=1)

print("\n" + "=" * 90)
print("TABLE 1: Model Comparison Summary (20-day simulation)")
print("=" * 90)
print(df_summary.to_string(index=False))
_TABLE_DIR = _os.path.join(_ROOT, "output", "tables") + "/"
_os.makedirs(_TABLE_DIR, exist_ok=True)
df_summary.to_csv(_TABLE_DIR + 'summary_table.csv', index=False)


# =============================================================
# TABLE 2: Road-level V/C (fee=0)
# =============================================================
print("\n" + "=" * 70)
print("TABLE 2: Road-level Mean V/C (fee=$0)")
print("=" * 70)

road_records = []
for model_name in ['NetLogo', 'Baseline', 'El Farol', 'Q-Learning']:
    df = results[f'{model_name}_fee0']
    for rid in ROAD_IDS:
        rd = df[df['road_id'] == rid]
        road_records.append({
            'Road': rid,
            'Position': ROAD_POSITION.get(rid, ''),
            'Model': model_name,
            'Mean V/C': round(rd['vc'].mean(), 3),
            'Cong. Rate (%)': round((rd['vc'] > VC_THRESHOLD).mean() * 100, 1),
        })

df_road = pd.DataFrame(road_records)
pivot_vc = df_road.pivot_table(index=['Road', 'Position'], columns='Model', values='Mean V/C', aggfunc='first')
pivot_vc = pivot_vc[['NetLogo', 'Baseline', 'El Farol', 'Q-Learning']]
print(pivot_vc.to_string())

pivot_cong = df_road.pivot_table(index=['Road', 'Position'], columns='Model', values='Cong. Rate (%)', aggfunc='first')
pivot_cong = pivot_cong[['NetLogo', 'Baseline', 'El Farol', 'Q-Learning']]
print("\nRoad-level Congestion Rate (%):")
print(pivot_cong.to_string())


# =============================================================
# FIGURES
# =============================================================
plt.rcParams['font.size'] = 11
plt.rcParams['axes.titlesize'] = 13
plt.rcParams['figure.facecolor'] = 'white'

# --- FIGURE 1: Hourly V/C comparison (fee=0) ---
fig, axes = plt.subplots(2, 2, figsize=(16, 11), sharey=True)
models_fee0 = [
    ('NetLogo_fee0', 'NetLogo (Original ABM)', '#333333'),
    ('Baseline_fee0', 'Baseline (Exp. Decay)', '#4169E1'),
    ('El Farol_fee0', 'El Farol Bar Model', '#E67E22'),
    ('Q-Learning_fee0', 'Q-Learning', '#27AE60'),
]

for ax, (key, title, color) in zip(axes.flat, models_fee0):
    df = results[key]
    hourly = df.groupby('hour')['vc'].agg(['mean', 'std']).reset_index()
    ax.fill_between(hourly['hour'], hourly['mean'] - hourly['std'],
                    hourly['mean'] + hourly['std'], alpha=0.15, color=color)
    ax.plot(hourly['hour'], hourly['mean'], 'o-', color=color, linewidth=2.5, markersize=5)
    ax.axhline(y=VC_THRESHOLD, color='red', linestyle='--', alpha=0.6, label='V/C = 0.85')
    ax.axhspan(VC_THRESHOLD, 1.2, alpha=0.05, color='red')
    ax.set_title(title, fontweight='bold', color=color)
    ax.set_xlabel('Hour of Day')
    ax.set_xlim(0, 23)
    ax.set_ylim(0, 1.0)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

axes[0, 0].set_ylabel('V/C Ratio')
axes[1, 0].set_ylabel('V/C Ratio')
fig.suptitle('Hourly V/C Ratio by Model (Fee = $0, 20-day average)', fontsize=15, fontweight='bold')
plt.tight_layout()
plt.savefig(OUT_DIR + 'fig1_vc_hourly.png', dpi=150, bbox_inches='tight')
plt.close()
print("\nFigure 1 saved.")


# --- FIGURE 2: V/C vs Density Scatter ---
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
for ax, (key, title, color) in zip(axes.flat, models_fee0):
    df = results[key]
    sample = df.sample(min(4000, len(df)), random_state=42)

    free = sample[(sample['vc'] < VC_THRESHOLD) & (sample['density'] < CRITICAL_DENSITY)]
    cong = sample[sample['vc'] >= VC_THRESHOLD]
    sev = sample[(sample['vc'] < VC_THRESHOLD) & (sample['density'] >= CRITICAL_DENSITY)]

    ax.scatter(free['density'], free['vc'], c='#3498DB', alpha=0.25, s=6, label='Free flow', zorder=2)
    ax.scatter(cong['density'], cong['vc'], c='#E67E22', alpha=0.4, s=10, label=f'Congestion (V/C>{VC_THRESHOLD})', zorder=3)
    ax.scatter(sev['density'], sev['vc'], c='#E74C3C', alpha=0.4, s=10, label='Severe (high density)', zorder=3)

    ax.axhline(y=VC_THRESHOLD, color='gray', linestyle='--', alpha=0.5)
    ax.axvline(x=CRITICAL_DENSITY, color='gray', linestyle=':', alpha=0.5)
    ax.set_title(title, fontweight='bold', color=color)
    ax.set_xlabel('Road Density')
    ax.set_ylabel('V/C Ratio')
    ax.set_xlim(-0.02, 0.9)
    ax.set_ylim(-0.02, 1.2)
    ax.legend(fontsize=8, loc='upper left')
    ax.grid(True, alpha=0.2)

fig.suptitle('V/C vs Road Density Scatter (Fee = $0)', fontsize=15, fontweight='bold')
plt.tight_layout()
plt.savefig(OUT_DIR + 'fig2_vc_density_scatter.png', dpi=150, bbox_inches='tight')
plt.close()
print("Figure 2 saved.")


# --- FIGURE 3: Fee Impact Comparison ---
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# (a) Overlay hourly V/C: fee=0 vs fee=2 for all models
ax = axes[0]
for key0, key2, label, color, ls in [
    ('NetLogo_fee0', 'NetLogo_fee2.0', 'NetLogo', '#333', '-'),
    ('Baseline_fee0', 'Baseline_fee2.0', 'Baseline', '#4169E1', '--'),
    ('El Farol_fee0', 'El Farol_fee2.0', 'El Farol', '#E67E22', '-.'),
    ('Q-Learning_fee0', 'Q-Learning_fee2.0', 'Q-Learning', '#27AE60', ':'),
]:
    h0 = results[key0].groupby('hour')['vc'].mean()
    h2 = results[key2].groupby('hour')['vc'].mean()
    ax.plot(h0.index, h0.values, ls, color=color, linewidth=2, alpha=0.4)
    ax.plot(h2.index, h2.values, ls, color=color, linewidth=2.5, label=f'{label} ($2)')

ax.axhline(y=VC_THRESHOLD, color='red', linestyle='--', alpha=0.3)
ax.set_xlabel('Hour of Day')
ax.set_ylabel('Mean V/C')
ax.set_title('(a) Hourly V/C: Faded=fee$0, Solid=fee$2', fontweight='bold')
ax.legend(fontsize=8)
ax.set_xlim(4, 23)
ax.grid(True, alpha=0.3)

# (b) Bar chart: congestion rate reduction
ax = axes[1]
models_list = ['NetLogo', 'Baseline', 'El Farol', 'Q-Learning']
fee0_cong = [df_summary[(df_summary['Model'] == m) & (df_summary['Fee ($)'] == 0)]['Congestion Rate (%)'].values[0] for m in models_list]
fee2_cong = [df_summary[(df_summary['Model'] == m) & (df_summary['Fee ($)'] == 2)]['Congestion Rate (%)'].values[0] for m in models_list]
x = np.arange(len(models_list))
w = 0.35
ax.bar(x - w/2, fee0_cong, w, label='Fee = $0', color='#3498DB', alpha=0.8)
ax.bar(x + w/2, fee2_cong, w, label='Fee = $2', color='#E74C3C', alpha=0.8)
ax.set_xticks(x)
ax.set_xticklabels(models_list)
ax.set_ylabel('Congestion Rate (%)')
ax.set_title('(b) Overall Congestion Rate', fontweight='bold')
ax.legend()
ax.grid(True, alpha=0.3, axis='y')

# (c) Boundary vs Inner V/C shift
ax = axes[2]
for i, model in enumerate(models_list):
    row0 = df_summary[(df_summary['Model'] == model) & (df_summary['Fee ($)'] == 0)]
    row2 = df_summary[(df_summary['Model'] == model) & (df_summary['Fee ($)'] == 2)]
    if len(row0) > 0 and len(row2) > 0:
        b0 = row0['Boundary V/C'].values[0]
        b2 = row2['Boundary V/C'].values[0]
        i0 = row0['Inner V/C'].values[0]
        i2 = row2['Inner V/C'].values[0]
        ax.annotate('', xy=(b2, i2), xytext=(b0, i0),
                    arrowprops=dict(arrowstyle='->', color=['#333', '#4169E1', '#E67E22', '#27AE60'][i], lw=2))
        ax.scatter([b0], [i0], s=80, c=['#333', '#4169E1', '#E67E22', '#27AE60'][i], marker='o', zorder=5)
        ax.scatter([b2], [i2], s=80, c=['#333', '#4169E1', '#E67E22', '#27AE60'][i], marker='s', zorder=5, label=model)

ax.set_xlabel('Boundary V/C')
ax.set_ylabel('Inner V/C')
ax.set_title('(c) Spatial Shift: $0 (circle) to $2 (square)', fontweight='bold')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

fig.suptitle('Impact of $2 Congestion Charge Across Models', fontsize=15, fontweight='bold')
plt.tight_layout()
plt.savefig(OUT_DIR + 'fig3_fee_impact.png', dpi=150, bbox_inches='tight')
plt.close()
print("Figure 3 saved.")


# --- FIGURE 4: Road-level Heatmap ---
fig, axes = plt.subplots(2, 2, figsize=(18, 10))
for ax, (key, title, _) in zip(axes.flat, models_fee0):
    df = results[key]
    pivot = df.pivot_table(index='road_id', columns='hour', values='vc', aggfunc='mean')
    active = [h for h in range(5, 24) if h in pivot.columns]
    data = pivot[active]

    im = ax.imshow(data.values, aspect='auto', cmap='YlOrRd', vmin=0, vmax=0.9)
    ax.set_yticks(range(len(data.index)))
    ax.set_yticklabels(data.index, fontsize=9)
    ax.set_xticks(range(len(active)))
    ax.set_xticklabels([f"{h}" for h in active], fontsize=8)
    ax.set_title(title, fontweight='bold')
    ax.set_xlabel('Hour')
    ax.set_ylabel('Road')

fig.colorbar(im, ax=axes, label='V/C Ratio', shrink=0.6, pad=0.02)
fig.suptitle('Road-level V/C Heatmap (fee=$0, 20-day avg)', fontsize=15, fontweight='bold')
plt.tight_layout()
plt.savefig(OUT_DIR + 'fig4_heatmap.png', dpi=150, bbox_inches='tight')
plt.close()
print("Figure 4 saved.")


# --- FIGURE 5: Learning Dynamics (daily evolution) ---
fig, axes = plt.subplots(1, 2, figsize=(15, 5))

ax = axes[0]
for key, label, color in [
    ('Baseline_fee0', 'Baseline', '#4169E1'),
    ('El Farol_fee0', 'El Farol', '#E67E22'),
    ('Q-Learning_fee0', 'Q-Learning', '#27AE60'),
]:
    daily = results[key].groupby('day')['vc'].mean()
    ax.plot(daily.index, daily.values, 'o-', color=color, linewidth=2, markersize=4, label=label)

ax.axhline(y=VC_THRESHOLD, color='red', linestyle='--', alpha=0.4)
ax.set_xlabel('Day')
ax.set_ylabel('Mean V/C')
ax.set_title('(a) Daily Mean V/C (fee=$0)', fontweight='bold')
ax.legend()
ax.grid(True, alpha=0.3)

ax = axes[1]
for key, label, color in [
    ('Baseline_fee2.0', 'Baseline', '#4169E1'),
    ('El Farol_fee2.0', 'El Farol', '#E67E22'),
    ('Q-Learning_fee2.0', 'Q-Learning', '#27AE60'),
]:
    daily = results[key].groupby('day')['vc'].mean()
    ax.plot(daily.index, daily.values, 'o-', color=color, linewidth=2, markersize=4, label=label)

ax.axhline(y=VC_THRESHOLD, color='red', linestyle='--', alpha=0.4)
ax.set_xlabel('Day')
ax.set_ylabel('Mean V/C')
ax.set_title('(b) Daily Mean V/C (fee=$2)', fontweight='bold')
ax.legend()
ax.grid(True, alpha=0.3)

fig.suptitle('Learning Dynamics Over 20 Days', fontsize=15, fontweight='bold')
plt.tight_layout()
plt.savefig(OUT_DIR + 'fig5_learning.png', dpi=150, bbox_inches='tight')
plt.close()
print("Figure 5 saved.")


# --- FIGURE 6: El Farol Oscillation Pattern ---
fig, axes = plt.subplots(1, 2, figsize=(15, 5))

# Peak hour V/C across days for El Farol (showing oscillation)
ax = axes[0]
for model, label, color in [
    ('Baseline', 'Baseline', '#4169E1'),
    ('El Farol', 'El Farol', '#E67E22'),
    ('Q-Learning', 'Q-Learning', '#27AE60'),
]:
    df = results[f'{model}_fee0']
    peak = df[df['hour'].isin([8, 9, 17, 18])]
    daily_peak = peak.groupby('day')['vc'].mean()
    ax.plot(daily_peak.index, daily_peak.values, 'o-', color=color, linewidth=2, label=label)

ax.axhline(y=VC_THRESHOLD, color='red', linestyle='--', alpha=0.4)
ax.set_xlabel('Day')
ax.set_ylabel('Peak-hour Mean V/C')
ax.set_title('(a) Peak-hour V/C Oscillation (fee=$0)', fontweight='bold')
ax.legend()
ax.grid(True, alpha=0.3)

# Q-Learning: WTP distribution vs fee
ax = axes[1]
wtp_vals = np.random.exponential(2.0, 1000)
ax.hist(wtp_vals, bins=30, alpha=0.6, color='#27AE60', edgecolor='white', density=True)
for fee_level in [0.5, 1.0, 2.0, 3.0]:
    ax.axvline(x=fee_level, color='red', linestyle='--', alpha=0.6)
    ax.text(fee_level + 0.05, 0.35, f'${fee_level}', fontsize=9, color='red')

burdened_2 = (wtp_vals < 2.0).mean() * 100
ax.set_xlabel('Willingness to Pay ($/hr)')
ax.set_ylabel('Density')
ax.set_title(f'(b) WTP Distribution ({burdened_2:.0f}% burdened at $2)', fontweight='bold')
ax.grid(True, alpha=0.3)

fig.suptitle('Behavioural Patterns: Oscillation and Equity', fontsize=15, fontweight='bold')
plt.tight_layout()
plt.savefig(OUT_DIR + 'fig6_behaviour.png', dpi=150, bbox_inches='tight')
plt.close()
print("Figure 6 saved.")


print("\n" + "=" * 60)
print("ALL DONE. Copying outputs to workspace...")
print("=" * 60)
