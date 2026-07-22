# Level of Service (LoS) implementation and sensitivity results

*Session notes, 2026-07-21; demand calibration added 2026-07-22.*

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

## Demand calibration (2026-07-22)

Modelled daily link volumes are now calibrated to AT observed ADT along two
axes — **total volume** (`scale-factor`) and **spatial distribution**
(suburban destinations) — leaving **temporal peaking** (implied k) as the one
measured-but-unresolved residual.

Infrastructure: `r-entries-cum` (cumulative link-entry counter, never reset),
`r-peak-hr-entries` (peak clock-hour entries, for implied k), `r-vcf-am-*`
(AM-peak 07-09 mean flow V/C), `save-calibration` (per-link CSV: observed ADT
vs modelled veh/day, implied k, AM V/C), BehaviorSpace experiment
`calibration-demand` (No-Charge, Exp-Decay, 5 days), and
`sensitivity_experiment/calibrate_demand.py` (ratios, implied k, suggested
`scale-factor`, log-log scatter).

**1. Total volume (`scale-factor` 300 → 160).** Link entries are
route-determined (cached shortest paths; every trip completes each day), so
modelled volumes scale linearly in `scale-factor` and the fit is a one-shot
division. All 1,634 links match an ADT count. At the original sf = 300 the
flow-weighted ratio sum(model)/sum(obs) was 1.543 (→ sf ≈ 195); after adding
suburban destinations (axis 2) it rose to 1.225 (suburban trips lengthen mean
route), giving **sf = 160**. Final verification at sf = 160: ratio **1.013**,
median per-link ratio 1.010, fitted line on top of y = x
(`output/figures/calibration_scatter.png`,
`output/tables/calibration_summary.txt`). `number_of_vehicles` stays 2500, so
the model now represents ~400k vehicles.

**2. Spatial distribution (suburban destinations).** The root cause of CBD
over-loading: all 1,484 non-home destinations from `akl_building_list.csv` sit
inside the cordon, so uniform destination sampling sent *every* non-home trip
downtown. `create-suburban-destinations` (in `akl_buildings.nls`,
`suburban-dest-count` = 1400) places non-CBD commercial trip-ends across the
suburbs; destinations are then drawn over the combined pool, pulling trips out
of the CBD. Group flow-weighted ratios (model/obs), before → after, at the
matched sf:

| Group | sf 300 (orig) | sf 160 (+ suburban) |
|---|---|---|
| CBD  | 1.80 | **1.12** |
| East | 1.30 | 1.20 |
| MWY  | 0.75 | 0.82 |
| West | 0.76 | 1.04 |

The inter-group range collapses from [0.75, 1.80] to [0.82, 1.20], and CBD is
no longer the outlier. (Finer flattening — East is now the high group — would
need observed trip-end data, which we do not have; link ADT under-determines
the OD matrix.)

**3. Temporal peaking (implied k = 0.157, unresolved).** With volume and space
matched, the model's implied design-hour factor — flow-weighted peak clock-hour
volume ÷ daily volume — is **0.157** (median 0.174), well above the physical
k = 0.10 that `r-cap-hr` assumes. The departure profile (`outbound-demand`,
8am weight 30/145 ≈ 21% of outbound trips) concentrates the AM peak harder than
a real network, so peak-hour flow runs ~1.5× the design-hour capacity even when
daily volumes match. **This is the residual driver of high peak-hour LoS E/F**,
and it is a departure-timing limitation, not a demand-level one.

Post-calibration No-Charge LoS (sf 160, 5-day mean, % traffic at LoS E/F):

| Group | Daily-peak-of-EMA | AM-peak-hour mean | (pre-cal daily, sf 300) |
|---|---|---|---|
| MWY  | 92.4 | **75.9** | 96.3 |
| CBD  | 86.9 | **83.3** | 97.8 |
| East | 87.7 | **83.9** | 96.1 |
| West | 83.3 | **80.1** | 86.1 |

Calibration lowered every group's daily-peak E/F (CBD most, −11 pp), and the
AM-peak-hour mean (`pct-los-ef-am-g`, the standard peak-hour LoS a traffic
engineer would report) reads a further ~4–16 pp lower than the daily peak of
the EMA. Inner-cordon peak V/C fell to 0.11. Levels are still high because of
the temporal residual above; the **ToU-vs-No-Charge difference** remains the
defensible headline, not the absolute E/F level.

## Caveats / next steps

- LoS is computed from a rolling-hour flow analogue (EMA), not a fixed
  clock-hour count — state this in the methods. The AM-peak-hour mean metric
  (`pct-los-ef-am-g`) is the clock-hour alternative and reads less extreme.
- **Temporal calibration is the open item.** Implied k = 0.157 vs physical
  0.10: flatten `outbound-demand`/`return-demand` (and `draw-trip-hour`)
  toward a ~10%-peak-hour profile so peak-hour flow matches design-hour
  capacity, then absolute LoS levels become quotable. Until then, report the
  ToU−NoCharge difference or the AM-peak metric, not absolute daily-peak E/F.
- Spatial calibration is aggregate-good but not exact (East ~1.2×, MWY ~0.8×);
  closing this needs observed trip-end/OD data beyond link ADT.
- **Sensitivity suite re-run is pending (blocked on runtime, not correctness).**
  The earlier tables were at sf = 300; the calibrated model is sf 160 + suburban
  destinations. Only `sensitivity-pay` has been re-run on the calibrated model
  so far (`output/tables/sensitivity-pay.csv`, 2026-07-23 02:53); `-elfarol`,
  `-ql-alpha`, `-ql-epsilon`, `-kfactor` are still the sf = 300 tables and must
  not be quoted together with the pay table until re-run.
  Performance diagnosis (measured on the 8 GB dev machine): the calibrated
  model costs **~195 s per simulated day** — suburban destinations lengthen
  trips, so vehicles spend more ticks on-road; setup and the destination scan
  are negligible by comparison. One 20-day run ≈ 65 min. Worse, BehaviorSpace
  runs an experiment's 6 runs concurrently in a single JVM heap capped at 50 %
  of 8 GB (≈4 GB); with 2500 vehicles + 3245 buildings + a scattered-OD path
  cache per run, the heap thrashes GC and an experiment takes ~4.5 h instead of
  the ~65 min ideal. To finish overnight, **cap concurrency to `--threads 3`**
  (≈2.2 h/experiment, ~11 h for all five) or additionally cut `n-sim-days` to
  ~12. The ToU-improves-LoS direction is expected to hold (k-factor showed
  robustness to a ±20 % capacity shift; calibration is a demand shift of similar
  order), but the numbers will change — replace all five tables once re-run.
- Sensitivity runs are single-seed (repetitions = 1): boxes show day-to-day
  variation within one seed. Replicate with 3–5 seeds for real error bars,
  especially for the El Farol damping claim.
