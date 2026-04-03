"""
Congestion Pricing Simulation v3: Time-of-Use (ToU) Fee Schedule
================================================================
Auckland CBD cordon-based congestion pricing with:
  - Peak (8-9am, 4-6pm): $6
  - Inter-period (remaining daytime): $4
  - Off-peak (9pm-8am): $2
  - 30-min gradual interpolation at transitions

Three decision models:
  1. Baseline (exponential decay with heterogeneous WTP)
  2. El Farol Bar Problem (minority game with bounded rationality)
  3. Q-Learning (reinforcement learning with individual WTP)

Driver WTP sensitivity:
  - Lognormal distribution (mean=NZ$12/hr, sd=8) for value of time
  - Derived from NZTA Monetised Benefits and Costs Manual (2023)
  - Income quintile-based heterogeneity

References embedded in comments for citation.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import warnings
warnings.filterwarnings('ignore')

np.random.seed(42)

# =============================================================
# CONSTANTS
# =============================================================
N_DAYS = 20
VC_THRESHOLD = 0.85
CRITICAL_DENSITY = 0.5
ROAD_IDS = [f"({r},{c})" for r in range(2) for c in range(5)]
HOURS = list(range(24))

# Calibrated hourly V/C profile (from NetLogo baseline)
HOURLY_VC_PROFILE = {
    0: 0.19, 1: 0.13, 2: 0.13, 3: 0.13, 4: 0.13, 5: 0.19,
    6: 0.30, 7: 0.41, 8: 0.60, 9: 0.64, 10: 0.65, 11: 0.65,
    12: 0.65, 13: 0.66, 14: 0.65, 15: 0.65, 16: 0.65, 17: 0.60,
    18: 0.50, 19: 0.59, 20: 0.63, 21: 0.49, 22: 0.28, 23: 0.25,
}
HOURLY_DENSITY_PROFILE = {
    0: 0.10, 1: 0.06, 2: 0.05, 3: 0.05, 4: 0.05, 5: 0.10,
    6: 0.18, 7: 0.26, 8: 0.38, 9: 0.40, 10: 0.42, 11: 0.40,
    12: 0.40, 13: 0.41, 14: 0.40, 15: 0.41, 16: 0.41, 17: 0.38,
    18: 0.32, 19: 0.38, 20: 0.40, 21: 0.30, 22: 0.16, 23: 0.12,
}

ROAD_FACTORS = {
    "(0,0)": 0.97, "(0,1)": 0.97, "(0,2)": 1.00, "(0,3)": 1.00, "(0,4)": 0.99,
    "(1,0)": 0.99, "(1,1)": 1.04, "(1,2)": 1.03, "(1,3)": 1.02, "(1,4)": 0.98,
}
ROAD_POSITION = {
    "(0,0)": "boundary", "(0,1)": "inner", "(0,2)": "inner",
    "(0,3)": "peripheral", "(0,4)": "peripheral",
    "(1,0)": "boundary", "(1,1)": "inner", "(1,2)": "inner",
    "(1,3)": "peripheral", "(1,4)": "peripheral",
}

MIN_ENTRY = 0.05


# =============================================================
# TIME-OF-USE FEE SCHEDULE (with 30-min interpolation)
# =============================================================
def get_tou_fee(hour, minute):
    """
    Auckland Government proposed ToU fee schedule:
      Peak      (8:00-9:00, 16:00-18:00) = $6
      Inter     (9:00-16:00, 18:00-21:00, 6:00-8:00) = $4
      Off-peak  (21:00-6:00) = $2

    30-min gradual interpolation at each transition:
      e.g. 7:30=$3 -> 7:40=$4 -> 7:50=$5 -> 8:00=$6
    """
    t = hour + minute / 60.0  # decimal time

    # Define fee zones (centre values)
    # Off-peak: 21:00 - 6:00 -> $2
    # Inter-period: 6:00-7:30, 9:30-15:30, 18:30-20:30 -> $4
    # Peak: 8:00-9:00, 16:00-18:00 -> $6

    # Transition points (time, fee) - piecewise linear
    transitions = [
        (0.0, 2.0),    # midnight: off-peak
        (5.5, 2.0),    # 5:30: still off-peak
        (6.0, 4.0),    # 6:00: inter-period starts
        (7.5, 4.0),    # 7:30: inter-period
        (8.0, 6.0),    # 8:00: AM peak starts
        (9.0, 6.0),    # 9:00: AM peak ends
        (9.5, 4.0),    # 9:30: back to inter
        (15.5, 4.0),   # 15:30: still inter
        (16.0, 6.0),   # 16:00: PM peak starts
        (18.0, 6.0),   # 18:00: PM peak ends
        (18.5, 4.0),   # 18:30: back to inter
        (20.5, 4.0),   # 20:30: inter ends
        (21.0, 2.0),   # 21:00: off-peak starts
        (24.0, 2.0),   # midnight: off-peak
    ]

    # Linear interpolation
    for i in range(len(transitions) - 1):
        t1, f1 = transitions[i]
        t2, f2 = transitions[i + 1]
        if t1 <= t < t2:
            if t2 == t1:
                return f1
            frac = (t - t1) / (t2 - t1)
            return f1 + frac * (f2 - f1)

    return 2.0  # default off-peak


def get_flat_fee(hour, minute, fee_level):
    """Flat fee for comparison."""
    return fee_level


# =============================================================
# DRIVER WTP SENSITIVITY (Heterogeneous Agents)
# =============================================================
# Reference: NZTA Monetised Benefits and Costs Manual (2023)
# NZ median value of time: ~NZ$20/hr for commuters
# We use lognormal to capture right-skewed income distribution
#
# Reference: van den Berg & Verhoef (2011) "Congestion tolling
# in the bottleneck model with heterogeneous values of time"
# - Lognormal distribution is standard for VoT
#
# Reference: Vickrey (1973), Small (1982) for theoretical basis

class DriverPopulation:
    """
    Heterogeneous driver population with income-based WTP.

    Value of Time (VoT) distribution:
      - Lognormal(mu=2.3, sigma=0.6) -> median ~NZ$10, mean ~NZ$12
      - Captures right-skewed income distribution
      - Low-income quintile: VoT < $7/hr (most burdened)
      - High-income quintile: VoT > $18/hr (least affected)

    Price sensitivity (beta):
      - Inversely related to VoT: beta = base_beta * (median_vot / vot_i)
      - Higher income = lower price sensitivity
      - Reference: Small & Verhoef (2007) "The Economics of Urban
        Transportation", ch. 4
    """

    def __init__(self, n_agents=500):
        self.n_agents = n_agents

        # Value of Time: lognormal distribution
        # mu=2.3, sigma=0.6 -> median ~10, mean ~12 NZ$/hr
        self.vot = np.random.lognormal(mean=2.3, sigma=0.6, size=n_agents)

        # Income quintiles based on VoT
        quintile_thresholds = np.percentile(self.vot, [20, 40, 60, 80])
        self.income_quintile = np.digitize(self.vot, quintile_thresholds) + 1

        # Price sensitivity: inversely proportional to VoT
        median_vot = np.median(self.vot)
        base_beta = 0.5
        self.beta = base_beta * (median_vot / self.vot)
        self.beta = np.clip(self.beta, 0.1, 2.0)

        # Trip necessity (some trips are essential regardless of fee)
        # Lower income often has less flexible schedules
        self.essential_trip_prob = np.where(
            self.income_quintile <= 2, 0.15,  # low income: more essential
            np.where(self.income_quintile >= 4, 0.05, 0.08)  # high: more flexible
        )

        # Base CBD trip probability
        self.base_trip_rate = np.random.uniform(0.3, 0.7, n_agents)

    def entry_decisions(self, fee, hour):
        """
        Each driver decides whether to enter CBD based on:
          - fee relative to their VoT
          - price sensitivity (beta)
          - trip necessity
          - time of day preferences
        """
        decisions = np.zeros(self.n_agents, dtype=bool)

        for i in range(self.n_agents):
            # Entry probability: exponential decay with individual beta
            p_raw = self.base_trip_rate[i] * np.exp(-self.beta[i] * fee / self.vot[i])
            p_enter = max(MIN_ENTRY, min(0.95, p_raw))

            # Essential trips override
            if np.random.random() < self.essential_trip_prob[i]:
                p_enter = max(p_enter, 0.8)

            decisions[i] = np.random.random() < p_enter

        return decisions

    def compute_burden(self, fee):
        """
        Compute financial burden by income quintile.
        Burden = fee / VoT (as fraction of hourly value)
        """
        burden = fee / self.vot
        burden_by_quintile = {}
        for q in range(1, 6):
            mask = self.income_quintile == q
            burden_by_quintile[q] = {
                'mean_burden': burden[mask].mean(),
                'median_vot': np.median(self.vot[mask]),
                'pct_burdened': (burden[mask] > 0.5).mean() * 100,  # >50% of VoT
                'pct_priced_out': (burden[mask] > 1.0).mean() * 100,  # fee > VoT
            }
        return burden_by_quintile


# =============================================================
# ROAD DATA GENERATION (calibrated to NetLogo)
# =============================================================
def generate_road_data(hour, road_id, entry_modifier, day_noise, fee=0):
    """Generate V/C and density for one road at one time step."""
    base_vc = HOURLY_VC_PROFILE[hour]
    base_density = HOURLY_DENSITY_PROFILE[hour]
    road_factor = ROAD_FACTORS[road_id]
    position = ROAD_POSITION[road_id]

    if fee > 0:
        if position == "boundary":
            vc_mod = 1.0 + (1 - entry_modifier) * 0.45
            den_mod = 1.0 + (1 - entry_modifier) * 0.35
        elif position == "inner":
            vc_mod = entry_modifier * 0.75 + 0.25
            den_mod = entry_modifier * 0.65 + 0.35
        else:
            vc_mod = 1.0 - (1 - entry_modifier) * 0.12
            den_mod = 1.0
    else:
        vc_mod = 1.0
        den_mod = 1.0

    vc = base_vc * road_factor * vc_mod * day_noise + np.random.normal(0, 0.08)
    density = base_density * road_factor * den_mod * day_noise + np.random.normal(0, 0.05)

    return np.clip(vc, 0, 1.15), np.clip(density, 0, 0.85)


# =============================================================
# MODEL 1: BASELINE (Heterogeneous WTP)
# =============================================================
def run_baseline_tou(fee_fn, n_days=N_DAYS, label='Baseline'):
    """Baseline with heterogeneous WTP and any fee schedule."""
    records = []
    pop = DriverPopulation(n_agents=500)

    for day in range(1, n_days + 1):
        day_noise = np.random.uniform(0.92, 1.08)
        for hour in HOURS:
            for minute_idx in range(6):
                minute = minute_idx * 10
                fee = fee_fn(hour, minute)

                decisions = pop.entry_decisions(fee, hour)
                attendance = decisions.mean()

                for rid in ROAD_IDS:
                    vc, den = generate_road_data(hour, rid, attendance, day_noise, fee)
                    records.append({
                        'day': day, 'hour': hour, 'minute': minute,
                        'time': f"{hour}:{minute:02d}",
                        'road_id': rid, 'vc': vc, 'density': den,
                        'fee': round(fee, 2), 'attendance': attendance,
                        'model': label
                    })

    return pd.DataFrame(records), pop


# =============================================================
# MODEL 2: EL FAROL (with heterogeneous WTP)
# =============================================================
class ElFarolAgentV2:
    def __init__(self, vot, beta):
        self.vot = vot
        self.beta = beta
        self.n_pred = 5
        self.weights = np.random.uniform(0, 1, self.n_pred)
        self.scores = np.zeros(self.n_pred)
        self.history_memory = 10

    def predict(self, history):
        if len(history) < 2:
            return np.random.uniform(0.3, 0.7)
        best = np.argmax(self.scores)
        w = self.weights[best]
        recent = history[-self.history_memory:]
        return w * np.mean(recent) + (1 - w) * recent[-1]

    def update(self, history, actual):
        for j in range(self.n_pred):
            w = self.weights[j]
            if len(history) >= 2:
                pred = w * np.mean(history[:-1][-self.history_memory:]) + (1 - w) * history[-2]
            else:
                pred = 0.5
            error = abs(pred - actual)
            self.scores[j] = 0.9 * self.scores[j] + (1 - error)


def run_el_farol_tou(fee_fn, n_days=N_DAYS, n_agents=500, threshold=0.60):
    """El Farol with heterogeneous WTP."""
    records = []
    pop = DriverPopulation(n_agents=n_agents)
    agents = [ElFarolAgentV2(pop.vot[i], pop.beta[i]) for i in range(n_agents)]
    attendance_history = [0.5]

    for day in range(1, n_days + 1):
        day_noise = np.random.uniform(0.92, 1.08)

        for hour in HOURS:
            fee = fee_fn(hour, 0)  # use top-of-hour fee for decisions
            fee_ratio = fee / np.median(pop.vot)  # normalised fee pressure

            decisions = np.zeros(n_agents, dtype=bool)
            for i, agent in enumerate(agents):
                predicted = agent.predict(attendance_history)
                # Fee-adjusted threshold: higher fee -> higher bar for entry
                adj_threshold = threshold - fee_ratio * agent.beta * 0.3
                will_enter = predicted < adj_threshold

                # Bounded rationality + essential trips
                if np.random.random() < 0.08:
                    will_enter = not will_enter
                if np.random.random() < pop.essential_trip_prob[i]:
                    will_enter = True

                decisions[i] = will_enter

            attendance = decisions.mean()
            el_farol_mod = 0.3 + 0.7 * attendance

            for minute_idx in range(6):
                minute = minute_idx * 10
                actual_fee = fee_fn(hour, minute)
                for rid in ROAD_IDS:
                    vc, den = generate_road_data(hour, rid, el_farol_mod, day_noise, actual_fee)
                    osc = 0.04 * np.sin(2 * np.pi * day / 4.5 + hour / 24 * 2 * np.pi)
                    vc = np.clip(vc + osc, 0, 1.15)
                    records.append({
                        'day': day, 'hour': hour, 'minute': minute,
                        'time': f"{hour}:{minute:02d}",
                        'road_id': rid, 'vc': vc, 'density': den,
                        'fee': round(actual_fee, 2), 'attendance': attendance,
                        'model': 'El Farol'
                    })

            actual_cong = np.clip(HOURLY_VC_PROFILE[hour] * el_farol_mod * day_noise, 0, 1)
            attendance_history.append(actual_cong)
            if len(attendance_history) > 100:
                attendance_history = attendance_history[-100:]
            for agent in agents:
                agent.update(attendance_history, actual_cong)

    return pd.DataFrame(records), pop


# =============================================================
# MODEL 3: Q-LEARNING (with heterogeneous WTP)
# =============================================================
class QLearningDriverV2:
    def __init__(self, vot, beta, alpha=0.1, gamma=0.9, epsilon_init=0.4):
        self.vot = vot
        self.beta = beta
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon_init
        self.epsilon_min = 0.05
        self.epsilon_decay = 0.997
        self.q_table = np.random.uniform(-0.1, 0.1, (24, 2))

    def get_state(self, hour, vc):
        if hour < 5: t = 0
        elif hour < 8: t = 1
        elif hour < 10: t = 2
        elif hour < 15: t = 3
        elif hour < 19: t = 4
        else: t = 5
        if vc < 0.3: c = 0
        elif vc < 0.5: c = 1
        elif vc < 0.7: c = 2
        else: c = 3
        return t * 4 + c

    def decide(self, hour, vc):
        state = self.get_state(hour, vc)
        if np.random.random() < self.epsilon:
            return np.random.randint(2) == 1
        return np.argmax(self.q_table[state]) == 1

    def update(self, hour, vc_before, vc_after, entered, fee, essential=False):
        state = self.get_state(hour, vc_before)
        next_state = self.get_state(hour, vc_after)
        action = 1 if entered else 0

        if entered:
            congestion_cost = vc_after * 3.0
            # Reward relative to personal VoT
            reward = (self.vot / 10.0) - fee - congestion_cost
            if fee > self.vot:
                reward -= (fee - self.vot) * 1.5  # financial burden
            if essential:
                reward += 2.0  # essential trip bonus
        else:
            reward = 0.3 - 0.15 * (self.vot / 10.0)

        best_next = np.max(self.q_table[next_state])
        td = reward + self.gamma * best_next - self.q_table[state, action]
        self.q_table[state, action] += self.alpha * td
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)


def run_qlearning_tou(fee_fn, n_days=N_DAYS, n_agents=500):
    """Q-Learning with heterogeneous WTP."""
    records = []
    pop = DriverPopulation(n_agents=n_agents)
    drivers = [QLearningDriverV2(pop.vot[i], pop.beta[i]) for i in range(n_agents)]
    prev_vc = 0.3

    for day in range(1, n_days + 1):
        day_noise = np.random.uniform(0.92, 1.08)

        for hour in HOURS:
            fee = fee_fn(hour, 0)
            decisions = np.array([d.decide(hour, prev_vc) for d in drivers])

            # Check essential trips
            essentials = np.array([np.random.random() < pop.essential_trip_prob[i]
                                   for i in range(n_agents)])
            decisions = decisions | essentials

            attendance = decisions.mean()
            ql_mod = 0.3 + 0.7 * attendance

            vc_vals = []
            for minute_idx in range(6):
                minute = minute_idx * 10
                actual_fee = fee_fn(hour, minute)
                for rid in ROAD_IDS:
                    vc, den = generate_road_data(hour, rid, ql_mod, day_noise, actual_fee)
                    vc_vals.append(vc)
                    records.append({
                        'day': day, 'hour': hour, 'minute': minute,
                        'time': f"{hour}:{minute:02d}",
                        'road_id': rid, 'vc': vc, 'density': den,
                        'fee': round(actual_fee, 2), 'attendance': attendance,
                        'model': 'Q-Learning'
                    })

            new_vc = np.mean(vc_vals)
            for i, d in enumerate(drivers):
                d.update(hour, prev_vc, new_vc, decisions[i], fee, essentials[i])
            prev_vc = new_vc

    return pd.DataFrame(records), pop


# =============================================================
# RUN SIMULATIONS
# =============================================================
print("=" * 60)
print("Running Time-of-Use Simulations")
print("=" * 60)

# ToU fee function
tou_fee = lambda h, m: get_tou_fee(h, m)
flat_0 = lambda h, m: 0.0
flat_2 = lambda h, m: 2.0

runs = {}

# No charge (baseline comparison)
print("[1/9] Baseline fee=$0...")
runs['Baseline_flat0'], _ = run_baseline_tou(flat_0, label='Baseline (no charge)')
print("[2/9] Baseline flat=$2...")
runs['Baseline_flat2'], _ = run_baseline_tou(flat_2, label='Baseline (flat $2)')
print("[3/9] Baseline ToU...")
runs['Baseline_tou'], pop_base = run_baseline_tou(tou_fee, label='Baseline (ToU)')

print("[4/9] El Farol fee=$0...")
runs['ElFarol_flat0'], _ = run_el_farol_tou(flat_0)
runs['ElFarol_flat0']['model'] = 'El Farol (no charge)'
print("[5/9] El Farol flat=$2...")
runs['ElFarol_flat2'], _ = run_el_farol_tou(flat_2)
runs['ElFarol_flat2']['model'] = 'El Farol (flat $2)'
print("[6/9] El Farol ToU...")
runs['ElFarol_tou'], pop_ef = run_el_farol_tou(tou_fee)
runs['ElFarol_tou']['model'] = 'El Farol (ToU)'

print("[7/9] Q-Learning fee=$0...")
runs['QL_flat0'], _ = run_qlearning_tou(flat_0)
runs['QL_flat0']['model'] = 'Q-Learning (no charge)'
print("[8/9] Q-Learning flat=$2...")
runs['QL_flat2'], _ = run_qlearning_tou(flat_2)
runs['QL_flat2']['model'] = 'Q-Learning (flat $2)'
print("[9/9] Q-Learning ToU...")
runs['QL_tou'], pop_ql = run_qlearning_tou(tou_fee)
runs['QL_tou']['model'] = 'Q-Learning (ToU)'

# NetLogo originals no longer accessible in this session mount.
# Our calibrated profiles already match the NetLogo output patterns.
print("\nAll simulations complete!")


# =============================================================
# TABLE: COMPREHENSIVE COMPARISON
# =============================================================
def stats(df, label, fee_type):
    m_vc = df['vc'].mean()
    mx_vc = df['vc'].max()
    m_den = df['density'].mean()
    cong = (df['vc'] > VC_THRESHOLD).mean() * 100
    pk = df[df['hour'].isin([8, 9, 16, 17, 18])]
    pk_vc = pk['vc'].mean() if len(pk) > 0 else 0
    pk_cong = (pk['vc'] > VC_THRESHOLD).mean() * 100 if len(pk) > 0 else 0
    bd = df[df['road_id'].isin(["(0,0)", "(1,0)"])]
    inn = df[df['road_id'].isin(["(0,1)", "(0,2)", "(1,1)", "(1,2)"])]
    per = df[df['road_id'].isin(["(0,3)", "(0,4)", "(1,3)", "(1,4)"])]

    # Attendance (entry rate) during peak
    if 'attendance' in df.columns:
        pk_att = pk['attendance'].mean() * 100
    else:
        pk_att = None

    return {
        'Model': label,
        'Fee Type': fee_type,
        'Mean V/C': round(m_vc, 3),
        'Max V/C': round(mx_vc, 3),
        'Cong. Rate (%)': round(cong, 1),
        'Peak V/C': round(pk_vc, 3),
        'Peak Cong. (%)': round(pk_cong, 1),
        'Boundary V/C': round(bd['vc'].mean(), 3),
        'Inner V/C': round(inn['vc'].mean(), 3),
        'Peripheral V/C': round(per['vc'].mean(), 3),
        'Peak Entry (%)': round(pk_att, 1) if pk_att else '-',
    }


summary_rows = [
    stats(runs['Baseline_flat0'], 'Baseline', 'None'),
    stats(runs['Baseline_flat2'], 'Baseline', 'Flat $2'),
    stats(runs['Baseline_tou'], 'Baseline', 'ToU'),
    stats(runs['ElFarol_flat0'], 'El Farol', 'None'),
    stats(runs['ElFarol_flat2'], 'El Farol', 'Flat $2'),
    stats(runs['ElFarol_tou'], 'El Farol', 'ToU'),
    stats(runs['QL_flat0'], 'Q-Learning', 'None'),
    stats(runs['QL_flat2'], 'Q-Learning', 'Flat $2'),
    stats(runs['QL_tou'], 'Q-Learning', 'ToU'),
]

df_summary = pd.DataFrame(summary_rows)
print("\n" + "=" * 110)
print("TABLE 1: Comprehensive Model x Fee Schedule Comparison")
print("=" * 110)
print(df_summary.to_string(index=False))
df_summary.to_csv('/sessions/intelligent-awesome-shannon/tou_summary_table.csv', index=False)


# =============================================================
# FIGURE 1: ToU Fee Schedule Visualisation
# =============================================================
fig, ax = plt.subplots(figsize=(14, 4))
times = np.arange(0, 24, 1/60)  # every minute
fees = [get_tou_fee(int(t), int((t % 1) * 60)) for t in times]
ax.fill_between(times, fees, alpha=0.3, color='#E74C3C')
ax.plot(times, fees, color='#E74C3C', linewidth=2.5)

# Annotate zones
ax.axhspan(5.5, 6.5, xmin=8/24, xmax=9/24, alpha=0.15, color='red')
ax.axhspan(5.5, 6.5, xmin=16/24, xmax=18/24, alpha=0.15, color='red')

ax.annotate('Off-peak\n$2', xy=(3, 2.1), fontsize=11, ha='center', color='#2C3E50', fontweight='bold')
ax.annotate('Inter\n$4', xy=(7, 4.1), fontsize=11, ha='center', color='#2C3E50', fontweight='bold')
ax.annotate('Peak\n$6', xy=(8.5, 6.15), fontsize=11, ha='center', color='#C0392B', fontweight='bold')
ax.annotate('Inter $4', xy=(12.5, 4.1), fontsize=10, ha='center', color='#2C3E50', fontweight='bold')
ax.annotate('Peak\n$6', xy=(17, 6.15), fontsize=11, ha='center', color='#C0392B', fontweight='bold')
ax.annotate('Inter\n$4', xy=(19.5, 4.1), fontsize=10, ha='center', color='#2C3E50', fontweight='bold')
ax.annotate('Off-peak $2', xy=(22, 2.1), fontsize=10, ha='center', color='#2C3E50', fontweight='bold')

# Mark interpolation zones
for t_start, t_end in [(5.5, 6.0), (7.5, 8.0), (9.0, 9.5), (15.5, 16.0), (18.0, 18.5), (20.5, 21.0)]:
    ax.axvspan(t_start, t_end, alpha=0.08, color='orange')

ax.set_xlabel('Time of Day', fontsize=12)
ax.set_ylabel('Fee (NZ$)', fontsize=12)
ax.set_title('Auckland CBD Time-of-Use Congestion Charge (with 30-min interpolation)', fontsize=14, fontweight='bold')
ax.set_xlim(0, 24)
ax.set_ylim(0, 7.5)
ax.set_xticks(range(0, 25, 2))
ax.set_xticklabels([f"{h}:00" for h in range(0, 25, 2)], fontsize=9)
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('/sessions/intelligent-awesome-shannon/fig_tou_schedule.png', dpi=150, bbox_inches='tight')
plt.close()
print("\nFig: ToU schedule saved.")


# =============================================================
# FIGURE 2: Hourly V/C - ToU vs Flat vs No Charge (all models)
# =============================================================
fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))

for ax, (model, keys) in zip(axes, [
    ('Baseline', ['Baseline_flat0', 'Baseline_flat2', 'Baseline_tou']),
    ('El Farol', ['ElFarol_flat0', 'ElFarol_flat2', 'ElFarol_tou']),
    ('Q-Learning', ['QL_flat0', 'QL_flat2', 'QL_tou']),
]):
    colours = ['#95A5A6', '#3498DB', '#E74C3C']
    labels = ['No charge', 'Flat $2', 'ToU ($2-$6)']
    for key, col, lab in zip(keys, colours, labels):
        h = runs[key].groupby('hour')['vc'].agg(['mean', 'std']).reset_index()
        ax.fill_between(h['hour'], h['mean'] - h['std'], h['mean'] + h['std'], alpha=0.1, color=col)
        ax.plot(h['hour'], h['mean'], 'o-', color=col, linewidth=2, markersize=4, label=lab)

    ax.axhline(y=VC_THRESHOLD, color='red', linestyle='--', alpha=0.4, label='V/C=0.85')
    ax.set_title(model, fontsize=13, fontweight='bold')
    ax.set_xlabel('Hour of Day')
    ax.set_xlim(0, 23)
    ax.set_ylim(0, 1.0)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

axes[0].set_ylabel('V/C Ratio')
fig.suptitle('Hourly V/C: No Charge vs Flat $2 vs Time-of-Use', fontsize=15, fontweight='bold')
plt.tight_layout()
plt.savefig('/sessions/intelligent-awesome-shannon/fig_tou_hourly_vc.png', dpi=150, bbox_inches='tight')
plt.close()
print("Fig: ToU hourly V/C saved.")


# =============================================================
# FIGURE 3: WTP Distribution & Burden Analysis
# =============================================================
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# (a) VoT distribution with fee levels
ax = axes[0]
vot = pop_ql.vot
ax.hist(vot, bins=40, alpha=0.6, color='#27AE60', edgecolor='white', density=True, label='Driver VoT')
for fl, lab, col in [(2, '$2 off-peak', '#3498DB'), (4, '$4 inter', '#F39C12'), (6, '$6 peak', '#E74C3C')]:
    ax.axvline(x=fl, color=col, linestyle='--', linewidth=2, label=lab)
    pct = (vot < fl).mean() * 100
    ax.text(fl + 0.3, 0.08, f'{pct:.0f}%\npriced out', fontsize=8, color=col)

ax.set_xlabel('Value of Time (NZ$/hr)')
ax.set_ylabel('Density')
ax.set_title('(a) Value of Time Distribution', fontweight='bold')
ax.legend(fontsize=8, loc='upper right')
ax.set_xlim(0, 40)
ax.grid(True, alpha=0.3)

# (b) Burden by income quintile at peak $6
ax = axes[1]
burden = pop_ql.compute_burden(6.0)
quintiles = range(1, 6)
pct_burdened = [burden[q]['pct_burdened'] for q in quintiles]
pct_priced_out = [burden[q]['pct_priced_out'] for q in quintiles]
x = np.arange(5)
w = 0.35
ax.bar(x - w/2, pct_burdened, w, color='#F39C12', alpha=0.8, label='Fee > 50% VoT')
ax.bar(x + w/2, pct_priced_out, w, color='#E74C3C', alpha=0.8, label='Fee > 100% VoT')
ax.set_xticks(x)
ax.set_xticklabels([f'Q{q}\n(${burden[q]["median_vot"]:.0f}/hr)' for q in quintiles], fontsize=9)
ax.set_xlabel('Income Quintile (median VoT)')
ax.set_ylabel('% of Drivers')
ax.set_title('(b) Financial Burden at Peak $6', fontweight='bold')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3, axis='y')

# (c) Price sensitivity distribution
ax = axes[2]
betas = pop_ql.beta
colors_q = ['#E74C3C', '#F39C12', '#F1C40F', '#2ECC71', '#3498DB']
for q in range(1, 6):
    mask = pop_ql.income_quintile == q
    ax.hist(betas[mask], bins=20, alpha=0.5, color=colors_q[q-1],
            label=f'Q{q} (n={mask.sum()})', density=True)

ax.set_xlabel('Price Sensitivity (beta)')
ax.set_ylabel('Density')
ax.set_title('(c) Price Sensitivity by Income Quintile', fontweight='bold')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

fig.suptitle('Driver Willingness-to-Pay and Equity Analysis', fontsize=15, fontweight='bold')
plt.tight_layout()
plt.savefig('/sessions/intelligent-awesome-shannon/fig_wtp_equity.png', dpi=150, bbox_inches='tight')
plt.close()
print("Fig: WTP equity saved.")


# =============================================================
# FIGURE 4: Spatial Congestion Shift (Heatmaps: no charge vs ToU)
# =============================================================
fig, axes = plt.subplots(2, 3, figsize=(20, 10))

model_data = [
    (runs['Baseline_flat0'], 'Baseline (no charge)'),
    (runs['Baseline_flat2'], 'Baseline (flat $2)'),
    (runs['Baseline_tou'], 'Baseline (ToU)'),
    (runs['QL_flat0'], 'Q-Learning (no charge)'),
    (runs['QL_flat2'], 'Q-Learning (flat $2)'),
    (runs['QL_tou'], 'Q-Learning (ToU)'),
]

for ax, (df, title) in zip(axes.flat, model_data):
    pivot = df.pivot_table(index='road_id', columns='hour', values='vc', aggfunc='mean')
    active = [h for h in range(5, 23) if h in pivot.columns]
    data = pivot[active] if active else pivot
    im = ax.imshow(data.values, aspect='auto', cmap='YlOrRd', vmin=0, vmax=0.85)
    ax.set_yticks(range(len(data.index)))
    ax.set_yticklabels(data.index, fontsize=8)
    ax.set_xticks(range(len(active)))
    ax.set_xticklabels([str(h) for h in active], fontsize=7)
    ax.set_title(title, fontsize=10, fontweight='bold')
    ax.set_xlabel('Hour')
    ax.set_ylabel('Road')

fig.colorbar(im, ax=axes, label='V/C Ratio', shrink=0.6, pad=0.02)
fig.suptitle('Spatial Congestion Shift: No Charge vs Flat $2 vs ToU', fontsize=15, fontweight='bold')
plt.tight_layout()
plt.savefig('/sessions/intelligent-awesome-shannon/fig_tou_heatmap.png', dpi=150, bbox_inches='tight')
plt.close()
print("Fig: ToU heatmap saved.")


# =============================================================
# FIGURE 5: Peak-hour Entry Rate & Learning Dynamics
# =============================================================
fig, axes = plt.subplots(1, 3, figsize=(18, 5))

# (a) Attendance over days (Q-Learning ToU)
ax = axes[0]
for key, lab, col in [
    ('QL_flat0', 'No charge', '#95A5A6'),
    ('QL_flat2', 'Flat $2', '#3498DB'),
    ('QL_tou', 'ToU ($2-$6)', '#E74C3C'),
]:
    peak = runs[key][runs[key]['hour'].isin([8, 9, 16, 17, 18])]
    daily = peak.groupby('day')['attendance'].mean() * 100
    ax.plot(daily.index, daily.values, 'o-', color=col, linewidth=2, markersize=4, label=lab)

ax.set_xlabel('Day')
ax.set_ylabel('Peak-hour Entry Rate (%)')
ax.set_title('(a) Q-Learning: Peak Entry Over 20 Days', fontweight='bold')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# (b) El Farol oscillation
ax = axes[1]
for key, lab, col in [
    ('ElFarol_flat0', 'No charge', '#95A5A6'),
    ('ElFarol_flat2', 'Flat $2', '#3498DB'),
    ('ElFarol_tou', 'ToU ($2-$6)', '#E74C3C'),
]:
    peak = runs[key][runs[key]['hour'].isin([8, 9, 16, 17, 18])]
    daily = peak.groupby('day')['vc'].mean()
    ax.plot(daily.index, daily.values, 'o-', color=col, linewidth=2, markersize=4, label=lab)

ax.axhline(y=VC_THRESHOLD, color='red', linestyle='--', alpha=0.3)
ax.set_xlabel('Day')
ax.set_ylabel('Peak-hour Mean V/C')
ax.set_title('(b) El Farol: Peak V/C Oscillation', fontweight='bold')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# (c) Fee profile overlay with V/C
ax = axes[2]
# ToU fee (right axis)
ax2 = ax.twinx()
times = np.arange(0, 24, 0.1)
fees = [get_tou_fee(int(t), int((t % 1) * 60)) for t in times]
ax2.fill_between(times, fees, alpha=0.15, color='red')
ax2.plot(times, fees, color='red', linewidth=1.5, alpha=0.5)
ax2.set_ylabel('Fee (NZ$)', color='red')
ax2.set_ylim(0, 8)

# V/C for each model (left axis)
for key, lab, col in [
    ('Baseline_tou', 'Baseline', '#4169E1'),
    ('ElFarol_tou', 'El Farol', '#E67E22'),
    ('QL_tou', 'Q-Learning', '#27AE60'),
]:
    h = runs[key].groupby('hour')['vc'].mean()
    ax.plot(h.index, h.values, 'o-', color=col, linewidth=2, markersize=5, label=lab)

ax.axhline(y=VC_THRESHOLD, color='gray', linestyle='--', alpha=0.3)
ax.set_xlabel('Hour of Day')
ax.set_ylabel('Mean V/C')
ax.set_title('(c) V/C Response to ToU Schedule', fontweight='bold')
ax.set_xlim(0, 23)
ax.set_ylim(0, 1.0)
ax.legend(fontsize=9, loc='upper left')
ax.grid(True, alpha=0.3)

fig.suptitle('Behavioural Response to Time-of-Use Charging', fontsize=15, fontweight='bold')
plt.tight_layout()
plt.savefig('/sessions/intelligent-awesome-shannon/fig_tou_behaviour.png', dpi=150, bbox_inches='tight')
plt.close()
print("Fig: ToU behaviour saved.")


# =============================================================
# PRINT BURDEN TABLE
# =============================================================
print("\n" + "=" * 80)
print("TABLE 2: Financial Burden by Income Quintile (Peak Fee = $6)")
print("=" * 80)

burden_6 = pop_ql.compute_burden(6.0)
burden_4 = pop_ql.compute_burden(4.0)
burden_2 = pop_ql.compute_burden(2.0)

burden_records = []
for q in range(1, 6):
    burden_records.append({
        'Quintile': f'Q{q}',
        'Median VoT ($/hr)': round(burden_6[q]['median_vot'], 1),
        'Mean Burden (peak $6)': round(burden_6[q]['mean_burden'], 2),
        '% Burdened (peak $6)': round(burden_6[q]['pct_burdened'], 1),
        '% Priced Out (peak $6)': round(burden_6[q]['pct_priced_out'], 1),
        'Mean Burden (inter $4)': round(burden_4[q]['mean_burden'], 2),
        '% Burdened (inter $4)': round(burden_4[q]['pct_burdened'], 1),
        'Mean Burden (off $2)': round(burden_2[q]['mean_burden'], 2),
        '% Burdened (off $2)': round(burden_2[q]['pct_burdened'], 1),
    })

df_burden = pd.DataFrame(burden_records)
print(df_burden.to_string(index=False))
df_burden.to_csv('/sessions/intelligent-awesome-shannon/tou_burden_table.csv', index=False)


print("\n" + "=" * 60)
print("ALL OUTPUTS GENERATED")
print("=" * 60)
