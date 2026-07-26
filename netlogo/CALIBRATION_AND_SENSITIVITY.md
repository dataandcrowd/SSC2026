# Demand calibration and sensitivity analysis: results

*SSC2026 Auckland congestion-pricing ABM. Results computed from the
BehaviorSpace tables of 2026-07-26 (calibrated model, 14 simulated days per
run unless noted). Figures in `output/figures/`, raw tables in
`output/tables/`.*

## 1. Summary

The model's travel demand is now calibrated against Auckland Transport
observed Average Daily Traffic (ADT) on all 1,634 network links, along two
axes: **total volume** (agent scale factor) and **spatial distribution**
(suburban trip-ends). A third axis, **temporal peaking**, was measured and
left uncorrected; it is the documented reason absolute Level-of-Service (LoS)
readings remain high.

On the calibrated model, the headline policy result survives: **time-of-use
(ToU) cordon pricing lowers congestion under every capacity assumption and
under two of the three behavioural rules.** The exception is informative: the
El Farol attendance rule shows no ToU effect once demand is realistic, and a
five-seed replication confirms the null. An apparent "pricing damps
collective oscillation" effect seen before calibration was an artifact of the
over-loaded network.

## 2. Demand calibration

### 2.1 Total volume: scale-factor 300 → 160

Each agent represents `scale-factor` real vehicles. Link entries are
route-determined (cached shortest paths, all trips complete daily), so
modelled link volumes scale linearly in `scale-factor` and the fit is a
one-shot division by the flow-weighted ratio Σmodel/Σobserved.

| Step | Configuration | Flow-weighted ratio |
|---|---|---|
| Original | sf 300, CBD-only destinations | 1.543 |
| + suburban destinations | sf 195 | 1.225 |
| **Final** | **sf 160** | **1.013** (median per-link 1.010) |

With `number_of_vehicles` = 2500 the model represents ~400k vehicles. The
fitted line lies on y = x in the log-log scatter
(`calibration_scatter.png`); per-link dispersion remains (shortest-path
routing concentrates flow), which is expected of a stylised one-route ABM —
the calibrated quantity is the aggregate.

### 2.2 Spatial distribution: suburban destinations

Root cause of CBD over-loading: all 1,484 non-home destinations in
`akl_building_list.csv` sit inside the cordon, so uniform destination
sampling sent every non-home trip downtown. `create-suburban-destinations`
adds 1,400 non-CBD commercial trip-ends across the suburbs
(`suburban-dest-count`), and destinations are drawn over the combined pool.

Group-level flow-weighted ratios (model/observed):

| Group | Before (sf 300) | After (sf 160 + suburban) |
|---|---|---|
| CBD | 1.80 | **1.12** |
| East | 1.30 | 1.20 |
| MWY | 0.75 | 0.82 |
| West | 0.76 | 1.04 |

The inter-group range collapses from [0.75, 1.80] to [0.82, 1.20] and the CBD
is no longer the outlier. Finer flattening would require observed trip-end/OD
data; link ADT alone under-determines the OD matrix.

### 2.3 Temporal peaking: measured, not corrected

The implied design-hour factor — peak clock-hour volume ÷ daily volume,
flow-weighted across links — is **k = 0.157** (median 0.174), well above the
physical k = 0.10 used to derive hourly capacities (ADT × k). The model's
departure-time profile concentrates ~21% of outbound trips into the 8am hour,
so peak-hour flow runs ~1.5× design-hour capacity even with daily totals
matched. This is why absolute peak-hour LoS E/F shares stay high after
calibration, and why the **ToU−No-Charge difference, not the absolute E/F
level, is the defensible headline**. Flattening the departure profile toward
k ≈ 0.10 is the remaining calibration item.

### 2.4 Post-calibration congestion levels (No-Charge baseline)

Five-day means, Exp-Decay, k = 0.10. "Daily peak" is the worst moment of the
day by construction; "AM peak" is the 07:00–09:00 mean — the metric a traffic
engineer would report:

| Group | Daily-peak % at LoS E/F | AM-peak-hour % at LoS E/F |
|---|---|---|
| MWY | 92.4 | 75.9 |
| CBD | 86.9 | 83.3 |
| East | 87.7 | 83.9 |
| West | 83.3 | 80.1 |

Inner-cordon daily peak V/C fell from ~0.45 (uncalibrated) to ~0.12.

## 3. Sensitivity analysis (calibrated model)

All runs: 14 simulated days, single seed (11) unless noted, No-Charge vs ToU.
Metric for behavioural sweeps: mean over days of the daily peak inner-cordon
V/C. `red%` = ToU reduction relative to No-Charge; SD is day-to-day within
the run.

### 3.1 Behavioural rules

**Exp-Decay (price sensitivity `base-beta`)** — effect is immediate (ToU sits
below No-Charge from day 1) and monotone in beta:

| base-beta | No-Charge | ToU | red% | SD(ToU) |
|---|---|---|---|---|
| 0.25 | 0.122 | 0.107 | 11.7% | 0.014 |
| 0.5 | 0.122 | 0.094 | 23.0% | 0.012 |
| 1.0 | 0.122 | 0.091 | 25.4% | 0.014 |

**Q-Learning (`ql-alpha`, `ql-epsilon-init`)** — the strongest and most
robust effect. The time series shows the signature of learning: ToU starts at
the No-Charge level and diverges downward as Q-tables absorb the fee
(`sensitivity_timeseries_ql_alpha.png`, `_ql_epsilon.png`):

| ql-alpha | red% | | ql-epsilon-init | red% |
|---|---|---|---|---|
| 0.05 | 19.2% | | 0.2 | 31.7% |
| 0.1 | 23.8% | | 0.4 | 23.8% |
| 0.2 | 23.8% | | 0.6 | 26.0% |

Insensitive to the learning rate; decreasing in exploration (more random
choice dilutes the learned avoidance).

**El Farol (comfort threshold) — no effect after calibration:**

| threshold | No-Charge | ToU | red% |
|---|---|---|---|
| 0.5 | 0.174 | 0.163 | 6.6% |
| 0.6 | 0.173 | 0.173 | 0.2% |
| 0.7 | 0.172 | 0.166 | 3.6% |

Five-seed replication at threshold 0.6 (`elfarol-seeds`, seeds 11–404):
ToU reduction = **−1.7% ± 2.7 pp across seeds, range [−5.8%, +1.1%]** — the
effect is indistinguishable from zero. The pre-calibration finding that
pricing damps El Farol's alternate-day oscillation (V/C 0.15 ↔ 0.7) does not
survive: with realistic demand the oscillation itself disappears (daily peaks
sit in a narrow 0.13–0.21 band; `sensitivity_timeseries_elfarol.png`), so
there is no collective over-correction for pricing to act on. **The
oscillation was a property of the over-loaded network, not of the attendance
game** — and a reliability-benefit claim for pricing should not be made from
this rule.

### 3.2 Capacity assumption (k-factor sweep)

Daily-peak % of traffic at LoS E/F, mean ± SD over 14 days, Exp-Decay:

| k | fee | MWY | CBD | East | West |
|---|---|---|---|---|---|
| 0.08 | No-Charge | 94.6±0.7 | 91.9±1.5 | 90.9±1.0 | 86.1±1.0 |
| 0.08 | ToU | 93.7±0.5 | 87.9±2.2 | 88.7±1.1 | 84.7±1.4 |
| 0.10 | No-Charge | 92.0±0.6 | 87.0±2.0 | 87.2±1.1 | 83.2±1.0 |
| 0.10 | ToU | 90.7±1.5 | 81.8±2.5 | 84.7±1.3 | 81.9±1.1 |
| 0.12 | No-Charge | 87.1±2.7 | 82.0±1.6 | 84.0±0.7 | 80.9±1.1 |
| 0.12 | ToU | 83.2±2.5 | 77.1±2.4 | 80.5±2.1 | 79.0±1.5 |

**At every k and in every group, ToU lowers the E/F share** — the
LoS-improvement conclusion is robust to the ±20% capacity assumption. The
gap is largest in the CBD (4–5 pp) and smallest on Arterial West (~1–2 pp).

### 3.3 Spatial displacement check

`sensitivity_reduction.png` breaks the ToU reduction out by cordon position
(inner / boundary / peripheral). Under Exp-Decay and Q-Learning all three
positions improve — the boundary most (its baseline V/C ~0.4 is the highest,
`sensitivity_positions.png`) — so pricing is not simply displacing queues
onto the cordon boundary.

## 4. Interpretation

1. **The policy conclusion is calibration-robust.** ToU pricing reduces peak
   congestion under Exp-Decay and Q-Learning across all tested parameters,
   and reduces LoS E/F shares across all capacity assumptions — before and
   after demand calibration.
2. **Behavioural mechanism matters more than its parameters.** Within a rule,
   parameter choice shifts the effect by at most ~1.5×; switching from a
   price-responsive rule to the threshold-based El Farol rule switches the
   effect off entirely. Model choice, not tuning, is the first-order
   uncertainty.
3. **Calibration can delete phenomena, not just rescale them.** The El Farol
   oscillation-damping story looked publishable on the uncalibrated model and
   is gone on the calibrated one. Reporting it would have been wrong.
4. **Absolute LoS levels remain overstated** until the departure-time profile
   is flattened (implied k 0.157 vs physical 0.10). Report differences, or
   the AM-peak metric, not absolute daily-peak E/F shares.

## 5. Reproduction

```
# macOS
caffeinate -is bash netlogo/sensitivity_experiment/run_calibrated_suite.sh
# Windows (PowerShell)
$env:NETLOGO = "C:\Program Files\NetLogo 6.4.0"
.\netlogo\sensitivity_experiment\run_calibrated_suite.ps1
```

Then `python3 aggregate_sensitivity.py` (summary tables) and
`python3 plot_sensitivity.py` (all figures) in
`netlogo/sensitivity_experiment/`. Calibration diagnostics:
`calibrate_demand.py` after a `calibration-demand` run. Implementation notes
and session history: `LOS_IMPLEMENTATION.md`.
