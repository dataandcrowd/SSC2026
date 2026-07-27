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

Results on the **calibrated model** (sf 160 + suburban destinations; full
suite re-run on Windows, completed 2026-07-25), mean ± SD over 20 days,
daily-peak % of traffic at LoS E/F:

| k | fee | MWY | CBD | East | West |
|---|---|---|---|---|---|
| 0.08 | No-Charge | 94.5±0.6 | 91.5±1.5 | 90.6±0.9 | 85.9±0.9 |
| 0.08 | tou | 93.8±0.7 | 88.3±2.3 | 88.7±1.0 | 84.9±1.2 |
| 0.10 | No-Charge | 91.9±0.6 | 86.9±1.9 | 87.1±1.1 | 83.0±1.1 |
| 0.10 | tou | 90.8±1.2 | 82.1±2.7 | 84.9±1.5 | 81.8±1.2 |
| 0.12 | No-Charge | 87.1±2.3 | 82.0±1.7 | 84.1±1.0 | 80.5±1.6 |
| 0.12 | tou | 83.6±2.3 | 77.5±2.5 | 81.0±2.2 | 78.6±1.9 |

**Headline holds after calibration: at every k and in every group, ToU lowers
the LoS E/F share — the LoS-improvement conclusion is robust to the capacity
assumption.** The ToU gap is largest for CBD (≈3–5 pp) and smallest for
Arterial West (≈1 pp). Absolute E/F levels are ~5–10 pp lower than the
pre-calibration (sf 300) tables, but still high because of the temporal
residual (implied k = 0.157; see Demand calibration below).

## Behavioural sensitivity (calibrated model, final 14-day tables 2026-07-26)

ToU reduction in 14-day mean of daily peak inner-cordon V/C. Calibration
lowered the No-Charge baseline from ~0.45 to ~0.12, so these are proportional
reductions off a much lower congestion level. (Numbers from the final
2026-07-26 tables; an earlier partial re-run quoted slightly different
values.)

- Exp-Decay base-beta 0.25 / 0.5 / 1.0 → 11.7% / 23.0% / 25.4% (still
  monotone in price sensitivity; No-Charge baseline identical across beta by
  construction).
- El Farol threshold 0.5 / 0.6 / 0.7 → 6.6% / 0.2% / 3.6% — essentially no
  effect, and day-to-day SD collapsed to ~0.02 (was 0.245 at sf 300).
- Q-Learning alpha 0.05 / 0.1 / 0.2 → 19.2% / 23.8% / 23.8% (insensitive to
  alpha).
- Q-Learning epsilon 0.2 / 0.4 / 0.6 → 31.7% / 23.8% / 26.0% (largest at low
  exploration).

**El Farol changed qualitatively under calibration — treat the earlier
"pricing damps oscillation" story as an artifact.** At sf 300 the El Farol
rule produced near-perfect alternate-day V/C cycling (0.15 ↔ 0.7) that ToU
appeared to damp. On the calibrated model that oscillation is gone (daily peak
sits in a narrow 0.13–0.21 band, No-Charge and ToU nearly overlapping, see
`sensitivity_elfarol_timeseries.png`), and the ToU effect is ~0. The
oscillation was driven by the over-loaded uncalibrated network, not by the
attendance game itself; with realistic demand there is little collective
congestion swing for pricing to act on. The five-seed replication
(`elfarol-seeds`, threshold 0.6, seeds 11/101/202/303/404) confirms the null:
ToU reduction −1.7% ± 2.7 pp across seeds, range [−5.8%, +1.1%]. Exp-Decay
and Q-Learning, by contrast, keep a clear positive ToU effect after
calibration.

Full write-up with tables: `CALIBRATION_AND_SENSITIVITY.md`.

## Figures and tables

- `output/figures/sensitivity_box_behaviour.png` — paired No-Charge/ToU boxes
  (20 days per box) for the four behavioural experiments.
- `output/figures/sensitivity_box_kfactor.png` — same, per group, k sweep.
- `output/figures/sensitivity_reduction.png` — ToU reduction (%) vs parameter,
  with one line per cordon position (inner / boundary / peripheral). A position
  whose line falls below zero got *worse* under pricing, which is what
  displacement onto the cordon boundary would look like.
- `output/figures/sensitivity_positions.png` — daily peak V/C by position,
  No-Charge vs ToU, at each rule's baseline parameter. Shows the levels behind
  the percentages (a large % off the small inner base can look bigger than it
  is next to the boundary's ~0.5).
- `output/figures/sensitivity_timeseries.png` — daily peak inner V/C over the
  simulated days, one panel per decision rule at its baseline parameter,
  No-Charge vs ToU. The two Q-Learning panels show the same runs (alpha = 0.1
  with epsilon = 0.4 is the shared baseline cell of both sweeps) — kept for
  side-by-side reading, not independent evidence.
- `output/figures/sensitivity_timeseries_{pay,elfarol,ql_alpha,ql_epsilon}.png`
  — per-rule daily series across the full parameter sweep (one column per
  swept value, inner-cordon daily peak V/C, No-Charge vs ToU).
- `output/figures/sensitivity_elfarol_timeseries.png` — El Farol daily series,
  one row per cordon position (inner / boundary / peripheral) x one column per
  threshold. Rows keep separate y-scales on purpose: the boundary sits near 0.5
  while inner and peripheral sit near 0.1, and a shared scale would flatten the
  oscillation the figure exists to show. Falls back to an inner-only single row
  on pre-2026-07-25 tables.

- `output/figures/sensitivity_hourly_profile.png` — hour-of-day inner-cordon
  V/C, one panel per rule, No-Charge vs ToU, min–max band over days 8+, ToU
  $6/$4 fee windows shaded (from `hourly_<Rule>_<fee>.csv`).
- `output/figures/sensitivity_los_bands.png` — flow-weighted LoS A–F mix by
  2-hour band (07–09 … 21–23 + all day), No-Charge vs ToU bars, one row per
  rule; `sensitivity_los_daily.png` — the same mix by simulated day (from
  `los_hours_<Rule>_<fee>.csv`).
- `output/figures/los_bpr_schematic.png` — BPR speed curve with the HCM LoS
  bands on the V/C axis, per road class (methods figure, no run needed).
- `output/figures/map_redistribution.png` — link-level change in peak flow V/C
  under ToU, one panel per rule, blue where pricing lowers the peak and red
  where it raises it, over a network shaded by the no-charge peak; dashed
  outline is the cordon (`plot_map_redistribution.py`, from the `paper-figs`
  experiment). `map_baseline_los.png` is the matching no-charge LoS map, but
  the daily peak of the flow EMA saturates at grade F on nearly every link, so
  it carries little information — use the LoS band figure instead.

The two position figures need `peak-vc-boundary` / `peak-vc-peripheral` and so
stay empty until a run made after 2026-07-25 exists; `plot_sensitivity.py`
skips them with a printed note rather than failing. `SENS_TABLES` /
`SENS_FIGS` env vars redirect input/output dirs (used to test the figures
against a fixture).
- `output/tables/sensitivity-*.csv` — raw BehaviorSpace tables (6 runs × 20
  days each), calibrated model, 2026-07-25; `sensitivity_summary.txt` —
  aggregated means/SDs.

All figures and the summary are regenerated from the CSVs with
`python3 aggregate_sensitivity.py` and `python3 plot_sensitivity.py` in
`sensitivity_experiment/` (needs `matplotlib` for the plots).

## Fixes made along the way

- `aggregate_sensitivity.py` included the step-0 row (all metrics 0, recorded
  before day 1) in every run's series, deflating means and inflating SDs
  (k-factor SDs read ±20 pp instead of the true ±0.2–2.8 pp). Now filtered.
- Flow EMA carried over between days (see above); now reset per day.
- `save-plots` exported the deleted "On-road vehicles by sector" plot, which
  would have thrown at runtime; the line was removed.
- `pricing-init` initialised `hr-cur-hour` from `current-hour` (which reads
  `ticks`) although it runs before `reset-ticks`, so `setup` failed outright
  with "The tick counter has not been started yet". Now uses `sim-start-hour`,
  the value tick 0 corresponds to. Found 2026-07-27 when the two within-day
  experiments would not start.

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
- **Sensitivity suite re-run is DONE (2026-07-25).** All five experiments
  were re-run on the calibrated model (sf 160 + suburban destinations) on a
  Windows machine and pushed (commit `edc7fce`); the tables above and the
  figures now reflect the calibrated model. The ToU-improves-LoS direction
  held for k-factor, Exp-Decay and Q-Learning; El Farol's effect collapsed
  to ~0 (see the behavioural section). The Windows run took ~14 h wall-clock
  at `--threads 3` (each simulated day ≈ 195 s; suburban destinations lengthen
  trips so vehicles spend more ticks on-road). For future re-runs the plotting
  step needs `matplotlib` on the run host, or regenerate figures elsewhere with
  `python3 plot_sensitivity.py` — the Windows run produced the tables and the
  summary but not the PNGs (matplotlib absent), which were regenerated on the
  Mac.
- **El Farol needs a multi-seed check before any claim.** The qualitative
  change between sf 300 (wild oscillation, apparent ToU damping) and the
  calibrated model (no oscillation, ~0 ToU effect) rests on single-seed runs
  (repetitions = 1). Replicate El Farol with 3–5 seeds to confirm the
  oscillation really is demand-driven and not seed-specific. The other rules'
  positive ToU effect is large enough to be less seed-fragile, but multi-seed
  error bars would strengthen all of them.
- Sensitivity runs are single-seed (repetitions = 1): boxes show day-to-day
  variation within one seed, not run-to-run uncertainty.

## Metric coverage gap and the seed trap (found 2026-07-25)

Two defects in the experiment definitions, both now fixed in
`sensitivity_experiment.xml`; **they invalidate nothing already computed, but
they limited what the completed runs can answer.**

**1. Only the inner cordon was recorded.** The four behavioural experiments
recorded just `peak-vc-inner` (+ `current-sim-day`) — a leftover from the
pricing work, where inner-CBD V/C is the congestion signal fed to the decision
rules (`cbd-congestion`). The group LoS reporters added this session were wired
only into `sensitivity-kfactor`, and `peak-vc-boundary` / `peak-vc-peripheral`
were being computed every tick but never recorded. All seven experiments now
record a common 12-metric set: inner / boundary / peripheral peak V/C, the four
daily-peak group E/F shares, and the four AM-peak (07–09) group E/F shares
(`pct-los-ef-am-g`, the clock-hour LoS a traffic engineer would report).

This matters because **the boundary is far more congested than the inner
cordon**: a validated 1-day calibrated run gives peak V/C inner 0.145,
**boundary 0.518**, peripheral 0.099 — the same ordering the GUI's "CBD V/C
over time" plot has shown all along (boundary pen above inner). So the headline
`peak-vc-inner` ≈ 0.12 describes the *least* congested of the three positions,
and every ToU reduction reported above (9.5–42.7 %) is measured there. Whether
pricing improves the cordon boundary — or merely displaces queues onto it —
cannot be answered from the completed tables. Re-running with the full metric
set is what settles it.

**2. `repetitions` does not vary the seed.** `setup` calls
`random-seed current-seed` whenever `control-seed?` is on, and it is on with
`current-seed` = 11. Verified headless: a 2-repetition experiment produced
bit-identical runs (vehicle x-coordinate sum 137349.8696 in both). Every
sensitivity result to date is therefore one seed, and raising `repetitions`
would have silently produced duplicate rows rather than replicates. Seeds must
be varied through an `enumeratedValueSet` on `current-seed` (as
`elfarol-seeds` does), or `control-seed?` set false.

## Planned: El Farol multi-seed replication

`elfarol-seeds` — El Farol at the baseline threshold 0.6, No-Charge vs ToU,
`current-seed` ∈ {11, 101, 202, 303, 404} (seed 11 first so one cell reproduces
the existing `sensitivity-elfarol` result), 20 days, full 12-metric set. Ten
runs. Tests whether the two single-seed El Farol findings — ToU effect ≈ 0 and
the disappearance of the sf300 alternate-day oscillation — are demand-driven
or seed-specific.

**`n-sim-days` is now 5 in every experiment (was 20), set 2026-07-25; nothing
has been re-run at 5 days yet.** This cuts a full-suite re-run to roughly a
quarter of the 20-day cost (the calibrated model costs ~195 s per simulated
day). Two consequences to keep in mind when the runs happen:

- **Not directly comparable with the 20-day tables above.** Those tables stay
  valid for what they measured; 5-day results are a separate series and should
  not be quoted alongside them without saying so.
- **5 days is short relative to how the rules learn.** Exp-Decay, El Farol
  predictor scores and the Q-tables all update once per day, and
  `ql-epsilon-decay` = 0.997/day barely moves in 5 days, so a 5-day run
  measures largely transient rather than settled behaviour — Q-Learning
  especially. It is adequate for a No-Charge baseline (which is why
  `calibration-demand` always used 5 days) and probably adequate to see whether
  El Farol oscillates at all (the sf300 cycle alternated day-to-day, so 5 days
  is ~2 cycles), but the ToU effect sizes will not be the converged ones.
  Consider 5 days for a fast diagnostic pass and a longer run for the numbers
  that go in the paper.

## Within-day results: hourly profile and LoS bands (run 2026-07-27)

The two remaining experiments — `hourly-profile` and `los-bands` — were run on
the Windows server on 2026-07-27 (14 days, 3 rules × 2 fee regimes at the
slider baselines, calibrated model, `--threads 8`, ~3.3 h each). Both exited 0
and all twelve tables were written. Command used:

```powershell
$env:NETLOGO = "C:\Program Files\NetLogo 6.4.0"
$env:JAVA_HOME = "C:\Program Files\Java\jdk-17"
$env:EXPERIMENTS = "hourly-profile los-bands"
.\netlogo\sensitivity_experiment\run_calibrated_suite.ps1
```

`JAVA_HOME` is **required** on this host: NetLogo 6.4.0's bundled `runtime`
directory ships no `java.exe`, so the runner's bundled-JRE fallback fails and
`netlogo-headless.bat` has no Java on PATH. JDK 17 is installed at the path
above. Figures were then generated in place (matplotlib installed on the
server, 3.11.1):

```powershell
python netlogo\sensitivity_experiment\plot_hourly_profile.py
python netlogo\sensitivity_experiment\plot_los_bands.py
```

**Blocker fixed before the run.** `pricing-init` set `hr-cur-hour` from
`current-hour`, which reads `ticks`, but `pricing-init` runs *before*
`reset-ticks` in `setup` (and after `clear-all`, which un-starts the tick
counter). Every run therefore died with `RUNTIME ERROR: The tick counter has
not been started yet` — the new LoS-hour recording code made `setup` itself
unusable in the GUI as well as headless. Tick 0 is `sim-start-hour`:00 by
definition, so the initialiser now uses `sim-start-hour` directly. A 2-day
diagnostic also confirmed each simulated day consumes exactly 24 × 600 ticks
(`day-start-tick` 0 → 14400, `current-hour` back to 5 at each day end), so the
absolute-tick `current-hour` stays aligned with the day clock across days and
the hour labels in both new tables are trustworthy.

**1. Hour-of-day profile** (`sensitivity_hourly_profile.png`; mean inner-cordon
V/C over days 8+, min–max band, ToU fee windows shaded):

| Rule | AM 07–09 | PM 16–18 | all day |
|---|---|---|---|
| Exp-Decay | 0.0524 → 0.0403 (−23.1 %) | 0.0312 → 0.0257 (−17.7 %) | 0.0202 → 0.0159 (−21.3 %) |
| El Farol | 0.0805 → 0.0819 (**+1.8 %**) | 0.0581 → 0.0599 (**+3.2 %**) | 0.0372 → 0.0368 (−1.1 %) |
| Q-Learning | 0.0501 → 0.0254 (−49.3 %) | 0.0356 → 0.0172 (−51.8 %) | 0.0216 → 0.0110 (−49.1 %) |

(Bands are half-open, so "07–09" is clock hours 07 and 08 — the same
convention as the two-hour bands of `sensitivity_los_bands.png`, and what
`paper_numbers.py` reports.)

(No-Charge → ToU.) The profile is twin-peaked (AM peak ≈ 08–09, PM peak ≈
17–18) in every cell. **The ToU effect is not peak-shaving: the proportional
reduction is essentially the same in the AM peak, the PM peak and the daily
mean**, so pricing shifts the whole day's level rather than redistributing
trips out of the charged windows — the earlier "AM-peak shaving" wording was a
hypothesis, and this figure does not support it. El Farol again shows no
effect, and its PM peak is marginally *worse* under ToU, consistent with the
~0 daily-peak result and the five-seed null above.

**2. Hourly LoS mix** (`sensitivity_los_bands.png` by 2-hour band,
`sensitivity_los_daily.png` by day; flow-weighted over all 1,634 links, days
8+, % of traffic at LoS E or F):

| Rule | all day | 07–09 | 09–11 |
|---|---|---|---|
| Exp-Decay | 56.3 → 49.4 (−7.0 pp) | 64.2 → 59.6 (−4.6 pp) | 83.2 → 79.8 (−3.5 pp) |
| El Farol | 71.8 → 71.5 (−0.4 pp) | 76.3 → 76.5 (**+0.2 pp**) | 89.3 → 89.2 (−0.1 pp) |
| Q-Learning | 58.0 → 40.0 (−18.0 pp) | 64.5 → 48.8 (−15.7 pp) | 84.9 → 71.1 (−13.7 pp) |

The worst band is 09–11, not 07–09, because `r-flow` is a one-hour EMA and so
lags the departure peak by roughly its time constant. Absolute E/F levels are
high for the reason given under Demand calibration (implied k = 0.157 against
an assumed 0.10), so read the No-Charge → ToU difference, not the level. The
daily figure also shows Q-Learning still improving at the end of the run under
ToU — its E/F share falls 56.2 % (day 1) → 37.8 % (day 14) and is still
declining — while Exp-Decay (≈ 49–50 %) and El Farol (≈ 71–72 %) are flat from
day 2, and all three No-Charge baselines are flat throughout. **The Q-Learning
ToU numbers above are therefore not converged**; a longer run would report a
larger effect for that rule.

`los_bpr_schematic.png` (BPR speed curve + LoS bands on the V/C axis, the
methods figure) needs no simulation run and is regenerated by
`plot_los_bands.py`.
