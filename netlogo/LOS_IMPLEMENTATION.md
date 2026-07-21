# Level of Service (LoS) implementation and sensitivity results

*Session notes, 2026-07-21.*

## Motivation

Instead of reporting delay patterns, the model now reports Level of Service
(LoS) on motorways and local/arterial roads, following Table 1 of
The Congestion Question WS1 working paper "Defining congestion" (Feb 2019),
which reproduces the Highway Capacity Manual (TRB 1994) thresholds:

| LoS | Motorway/Expressway V/C | Local/Arterial V/C |
|---|---|---|
| A | < 0.30 | < 0.26 |
| B | 0.30–0.48 | 0.26–0.43 |
| C | 0.48–0.70 | 0.43–0.62 |
| D | 0.70–0.90 | 0.62–0.82 |
| E | 0.90–1.0 | 0.82–1.0 |
| F | ≥ 1.0 | ≥ 1.0 |

The same V/C therefore grades stricter on an arterial than on a motorway.
Target LoS is D; flow destabilises approaching E (V/C ≈ 0.85+).

## Why flow-based V/C (not the instantaneous count)

With `scale-factor` = 300 vehicles per agent, a typical arterial
(`r-capacity` ≈ 400) jumps from V/C 0 to 0.75 the moment a single agent is on
the link, so the snapshot V/C is too lumpy to grade LoS. The HCM definition is
hourly flow over hourly capacity, so LoS now uses:

- `r-flow` — EMA of the link's entering flow (real veh/h) with a one-hour time
  constant (`alpha = 1 / ticks-per-hour`), fed by an entry counter in
  `set-destination` (the single choke point where a vehicle starts a link).
- `r-cap-hr` — hourly capacity = observed ADT × `k-factor` (design-hour
  factor, slider, default 0.10, standard urban range 0.08–0.12). Links with no
  ADT match fall back to the road-class multiplier.
- `r-vcf = r-flow / r-cap-hr` — the flow-based hourly V/C that feeds
  `los-grade` and the link colouring (A green … F dark red).

The BPR congestion dynamics still run on the density-style `r-vc`; `k-factor`
is measurement-only, so traffic trajectories are identical across its values
(same seed), only the LoS reading changes.

`r-flow` is zeroed at the start of each simulated day (`run-one-day`): ticks
pause overnight (the movement loop ends with the last trip), so without the
reset the EMA never decays between days and LoS starts each morning inflated.

## Reporting groups

`tag-los-groups` (called from `pricing-init`) assigns each link a `r-group`:

| Group | Definition | Links |
|---|---|---|
| MWY | all motorway-class links (80 km/h: SH1N/SH1S/SH16 corridors) | 174 |
| CBD | non-motorway links inside the cordon (`r-position` = "inner") | 314 |
| East | remaining links with midpoint x ≥ 63 (fixed line through patch 63 31) | 572 |
| West | remaining links with midpoint x < 63 | 574 |

Reporters: `los-share-g g grp` (flow-weighted % of a group's traffic at grade
g), `pct-los-ef-g grp` (% at E or worse), `group-vcf grp` (flow-weighted mean
hourly V/C). Daily peaks `peak-ef-mwy/cbd/east/west` are tracked in
`update-vc` and reset each day, mirroring `peak-vc-inner`.

Interface: plots "% traffic at LoS E/F by group" and "Mean flow V/C by group"
(MWY black / CBD red / East blue / West green), four per-group E/F monitors,
and the `k-factor` slider. `save-links` now exports `class`, `group`,
`vcf_peak` and `los_peak` per link.

## k-factor sensitivity (BehaviorSpace)

New experiment `sensitivity-kfactor` (in `sensitivity_experiment.xml`, the
runner scripts, and the model's embedded BehaviorSpace list):
k ∈ {0.08, 0.10, 0.12} × fee ∈ {No-Charge, tou}, Exp-Decay, 20 days,
recording the four daily-peak group E/F metrics.

Results (mean ± SD over 20 days, daily-peak % of traffic at LoS E/F):

| k | fee | MWY | CBD | East | West |
|---|---|---|---|---|---|
| 0.08 | No-Charge | 97.4±0.2 | 98.6±0.3 | 97.4±0.3 | 89.4±2.0 |
| 0.08 | tou | 96.9±0.3 | 97.6±0.6 | 96.2±0.5 | 87.3±2.0 |
| 0.10 | No-Charge | 96.3±0.3 | 97.8±0.4 | 96.1±0.6 | 86.1±2.8 |
| 0.10 | tou | 95.3±0.5 | 96.2±0.7 | 94.2±1.2 | 82.2±1.9 |
| 0.12 | No-Charge | 94.7±0.5 | 96.8±0.5 | 94.7±0.8 | 82.0±2.5 |
| 0.12 | tou | 93.3±0.6 | 94.3±1.4 | 91.7±1.3 | 76.9±2.1 |

**Headline: at every k and in every group, ToU lowers the LoS E/F share — the
LoS-improvement conclusion is robust to the capacity assumption.** The effect
is largest for Arterial West (78.1→73.2 pp at k = 0.12 in the earlier
mean-only table; boxes barely overlap in the boxplot).

## Behavioural sensitivity (re-run, day-0 bug fixed)

ToU reduction in 20-day mean of daily peak inner-cordon V/C:

- Exp-Decay base-beta 0.25 / 0.5 / 1.0 → 11.5% / 21.3% / 30.5% (monotone in
  price sensitivity; No-Charge baseline identical across beta by construction).
- El Farol threshold 0.5 / 0.6 / 0.7 → 1.2% / 7.8% / 11.1%, with large
  day-to-day SD (0.245 at 0.5).
- Q-Learning alpha 0.05 / 0.1 / 0.2 → 20.3% / 17.9% / 19.4% (insensitive).
- Q-Learning epsilon 0.2 / 0.4 / 0.6 → 26.4% / 17.9% / 15.3% (more
  exploration, less effect).

The El Farol time series shows the boxplot spread is endogenous oscillation,
not noise: at threshold 0.5 near-perfect alternate-day cycling
(V/C 0.15 ↔ 0.7) that ToU barely dents; at threshold 0.7 No-Charge keeps
oscillating widely while **ToU visibly damps the amplitude** (≈0.5–0.65 band).
Under El Farol, pricing acts less by lowering the mean than by damping
collective over-correction — a day-to-day reliability benefit. (Single seed;
needs a multi-seed replication before claiming it in the paper.)

## Figures and tables

- `output/figures/sensitivity_box_behaviour.png` — paired No-Charge/ToU boxes
  (20 days per box) for the four behavioural experiments.
- `output/figures/sensitivity_box_kfactor.png` — same, per group, k sweep.
- `output/figures/sensitivity_reduction.png` — ToU reduction (%) vs parameter.
- `output/figures/sensitivity_elfarol_timeseries.png` — El Farol daily series.
- `output/tables/sensitivity-*.csv` — raw BehaviorSpace tables (6 runs × 20
  days each); `sensitivity_summary.txt` — aggregated means/SDs.

Regenerate with `python3 aggregate_sensitivity.py` and
`python3 plot_sensitivity.py` in `sensitivity_experiment/`.

## Fixes made along the way

- `aggregate_sensitivity.py` included the step-0 row (all metrics 0, recorded
  before day 1) in every run's series, deflating means and inflating SDs
  (k-factor SDs read ±20 pp instead of the true ±0.2–2.8 pp). Now filtered.
- Flow EMA carried over between days (see above); now reset per day.
- `save-plots` exported the deleted "On-road vehicles by sector" plot, which
  would have thrown at runtime; the line was removed.

## Caveats / next steps

- LoS is computed from a rolling-hour flow analogue (EMA), not a fixed
  clock-hour count — state this in the methods.
- Absolute E/F levels (~90%+ at the daily peak) are high: the daily-peak
  metric is by construction the worst moment of the day, and model demand
  appears high relative to ADT-based capacities (max `r-vcf` ≈ 8 on a few
  local links). Demand-side calibration — match modelled daily link volumes
  to observed ADT by adjusting `number_of_vehicles` × `scale-factor` — should
  precede any headline use of absolute LoS levels; `k-factor` then stays at
  its physical 0.10. An AM-peak-hour mean metric would also read less
  extreme than the daily peak.
- Sensitivity runs are single-seed (repetitions = 1): boxes show day-to-day
  variation within one seed. Replicate with 3–5 seeds for real error bars,
  especially for the El Farol damping claim.
