#!/usr/bin/env python3
"""Three figures: who pays, and what each behavioural option buys.

1. equity_by_income.png   Who is deterred, by value-of-time quintile, under the
                          price rule and under the learner. DERIVED from the
                          model's own decision and reward functions applied to
                          the calibrated VoT distribution, not measured in a
                          run: no experiment has recorded entries by income band.
2. optin_retiming.png     Peak V/C and entry rate with the departure hour fixed
                          against free to move by an hour. MEASURED.
3. optin_rerouting.png    The same for fixed against congestion-dependent
                          routes. MEASURED.

Reads  output/tables/days_<Rule>_<fee>{,_rt,_rr}.csv
Writes output/figures/{equity_by_income,optin_retiming,optin_rerouting}.png
"""
import csv, math, os, random, statistics as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.environ.get("SENS_TABLES") or os.path.join(HERE, "..", "..", "output", "tables")
FIGS = os.environ.get("SENS_FIGS") or os.path.join(HERE, "..", "..", "output", "figures")
os.makedirs(FIGS, exist_ok=True)

RULES = [("Exp-Decay", "Pay"), ("ElFarol", "Oscillate"), ("Q-Learning", "Learn")]
N_AGENTS = 2500          # model population
SCALE = 160              # vehicles per agent after calibration
BASE_BETA, VC = 0.5, 0.12

# ---------------------------------------------------------------- equity ----
random.seed(11)
N = 200000
vots = [math.exp(random.gauss(2.3, 0.6)) for _ in range(N)]
srt = sorted(vots)
cuts = [srt[int(k * N / 5)] for k in range(1, 5)]
med, q20, q80 = st.median(vots), srt[int(.2 * N)], srt[int(.8 * N)]


def quint(v):
    return sum(v >= c for c in cuts)


pop = [(v, min(max(BASE_BETA * (med / v), 0.1), 2.0), random.uniform(0.3, 0.7),
        0.15 if v <= q20 else (0.05 if v >= q80 else 0.08)) for v in vots]
groups = [[] for _ in range(5)]
for a in pop:
    groups[quint(a[0])].append(a)


def p_enter(a, fee):
    v, beta, btr, ess = a
    p = min(max(btr * math.exp(-beta * fee / v), 0.05), 0.95)
    return ess * max(p, 0.8) + (1 - ess) * p          # essential trips floored


def q_reward_gap(v, fee, benefit):
    """Q-learning: reward(enter) - reward(stay out), in dollars."""
    r = benefit(v) - fee - VC * 3.0
    if fee > v:
        r -= (fee - v) * 1.5
    return r - (0.3 - 0.15 * (v / 10.0))


fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.4))
FEES = [(0, "no charge", "#b8b8b8"), (2, "$2 off-peak", "#8fb2cf"),
        (4, "$4 shoulder", "#d19a4e"), (6, "$6 peak", "#c0504d")]
x = range(5)
w = 0.2
for k, (fee, label, colour) in enumerate(FEES):
    vals = [sum(p_enter(a, fee) for a in g) / len(g) * N_AGENTS / 5 for g in groups]
    off = (k - 1.5) * w
    axes[0].bar([i + off for i in x], vals, w, color=colour, label=label)
axes[0].set_title("Pay: agents entering the cordon, by income band\n"
                  "(of 500 agents per quintile = 80,000 vehicles)", fontsize=10)
axes[0].set_ylabel("agents entering")
axes[0].legend(frameon=False, fontsize=8, ncol=2)
red = [100 * (sum(p_enter(a, 0) for a in g) - sum(p_enter(a, 6) for a in g))
       / sum(p_enter(a, 0) for a in g) for g in groups]
for i, r in zip(x, red):
    axes[0].text(i, 5, f"−{r:.0f}%", ha="center", fontsize=9, color="#c0504d",
                 fontweight="bold")

for k, (benefit, label, colour, style) in enumerate([
        (lambda v: v / 10.0, "as implemented (benefit = VoT/10)", "#c0504d", "-"),
        (lambda v: v * 0.5, "benefit = half an hour of VoT", "#4878a8", "--")]):
    vals = [q_reward_gap(st.median([a[0] for a in g]), 6, benefit) for g in groups]
    axes[1].plot(list(x), vals, style, marker="o", color=colour, lw=2, label=label)
axes[1].axhline(0, color="black", lw=1)
axes[1].fill_between([-0.5, 4.5], -12, 0, color="#c0504d", alpha=0.05)
axes[1].text(0.05, -10.5, "below the line: the agent learns not to enter",
             fontsize=8.5, color="#666666")
axes[1].set_xlim(-0.5, 4.5)
axes[1].set_title("Learn: value of entering at the $6 peak fee, by income band\n"
                  "(reward for entering minus reward for staying out)", fontsize=10)
axes[1].set_ylabel("reward difference (NZ$)")
axes[1].legend(frameon=False, fontsize=8.5, loc="upper left")

for ax in axes:
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"Q{i+1}\n${st.median([a[0] for a in groups[i]]):.0f}/h"
                        for i in range(5)])
    ax.set_xlabel("value-of-time quintile (Q1 = lowest income)")
    ax.grid(axis="y", alpha=0.25)
fig.suptitle("Who the charge removes from the road. Derived from the model's "
             "decision and reward functions, not measured in a run.", y=1.03)
fig.tight_layout()
out = os.path.join(FIGS, "equity_by_income.png")
fig.savefig(out, dpi=200, bbox_inches="tight")
print("wrote", out)
plt.close(fig)


# ------------------------------------------------------------- opt-in arms --
def days(rule, fee, tag):
    path = os.path.join(TABLES, f"days_{rule}_{fee}{tag}.csv")
    return list(csv.DictReader(open(path))) if os.path.exists(path) else None


def mean(rows, field):
    return st.mean(float(r[field]) for r in rows)


def optin_figure(tag, off_label, on_label, title, fname):
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.3))
    series = [("", "No-Charge", f"no charge, {off_label}", "#c9c9c9"),
              ("", "tou", f"ToU, {off_label}", "#8a8a8a"),
              (tag, "No-Charge", f"no charge, {on_label}", "#8fb8dc"),
              (tag, "tou", f"ToU, {on_label}", "#2f6fa8")]
    x = range(len(RULES))
    w = 0.2
    for k, (tg, fee, label, colour) in enumerate(series):
        vc, en = [], []
        for rule, _ in RULES:
            rows = days(rule, fee, tg)
            vc.append(mean(rows, "vc_inner") if rows else 0)
            en.append(mean(rows, "attendance") if rows else 0)
        off = (k - 1.5) * w
        axes[0].bar([i + off for i in x], vc, w, color=colour, label=label)
        axes[1].bar([i + off for i in x], en, w, color=colour, label=label)
        for i, v in zip(x, vc):
            axes[0].text(i + off, v + 0.004, f"{v:.3f}", ha="center", fontsize=7)
        for i, v in zip(x, en):
            axes[1].text(i + off, v + 0.015, f"{v:.2f}", ha="center", fontsize=7)
    axes[0].set_title("daily peak inner-cordon V/C", fontsize=10)
    axes[1].set_title("share of agents entering the cordon", fontsize=10)
    for ax in axes:
        ax.set_xticks(list(x))
        ax.set_xticklabels([t for _, t in RULES])
        ax.grid(axis="y", alpha=0.25)
        ax.margins(y=0.16)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=4, frameon=False,
               fontsize=8.5, bbox_to_anchor=(0.5, 0.99))
    fig.suptitle(title, y=1.06)
    fig.tight_layout()
    out = os.path.join(FIGS, fname)
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print("wrote", out)
    plt.close(fig)


optin_figure("_rt", "fixed hour", "may retime",
             "Departure-time choice: what an hour of flexibility does to "
             "congestion and to the number of trips", "optin_retiming.png")
optin_figure("_rr", "fixed route", "may reroute",
             "Route choice: what congestion-aware routing does to congestion "
             "and to the number of trips", "optin_rerouting.png")
