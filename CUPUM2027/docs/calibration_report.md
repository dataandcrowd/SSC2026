# Behaviour calibration, 10-day design

Written by `scripts/calibrate_behaviour_d10.py` on 2026-10-16. Log: `data/behaviour_calibration.json`. The 30-day calibration is archived in `data/behaviour_calibration_d30.json`.

## Design

R-daily, rule decider, 950 agents, 10 days, seeds 1-3. Days 1-5 uncharged, NZ$6 peak ToU charge from day 6, no PT disruption. Base shares and the capacity calibration on days 2-5; response = mean car cordon crossings of days 6-10 against days 2-5.

| Target | Band | Centre | Single-seed tolerance |
|---|---|---|---|
| car share, mean of days 2-5 (uncharged) | 0.75 to 0.85 | 0.8 | ±0.028 |
| PT share, days 2-5 | 0.08 to 0.15 | 0.115 | ±0.028 |
| WFH share, days 2-5 (at most) | 0 to 0.1 | - | ±0.028 |
| car cordon crossings, mean days 6-10 (charged) vs mean days 2-5 | -0.3 to -0.15 | -0.2 | ±0.022 |

Selection: lexicographic [author decision 2026-10-16]: (1) feasible = every 3-seed mean in its target band at the targets' stated precision (shares to 2 decimals, changes to whole percent) and every seed within the stated single-seed tolerance; (2) beta0 >= 0.15, so that the willingness-to-pay limit stays in force (beta0 0.05-0.1 lie at the bottom of the searched range, where the limit almost vanishes); (3) the 3-seed mean response of days 6-10 nearest the -20% centre (Stockholm), at the stated precision (whole percent); (4) loss as tie-break. If no point is feasible, the lowest loss. beta0 = 0 references are never selected. This replaces the anchor rule of the 30-day calibration (nearest PAP 8 / k_WFH 8 / beta0 0.5), which with the wider 10-day band picked a point at its edge (PAP 21.25 / k_WFH 11 / beta0 0.25, -29.1%).

## Search

Stage 1: PAP [20.0, 21.0, 22.0, 23.0, 24.0], k_WFH [4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0], beta0 [0.05, 0.1, 0.15, 0.2, 0.3, 0.5] (+ beta0 0 reference). Stage 2: k_WFH 2-16 x beta0 [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0] on PAP [19.0, 20.0, 21.0, 22.0, 23.0, 24.0, 25.0]. 1085 points, 46 feasible, 37 min.

## Chosen point

PAP 20, k_WFH 16, beta0 0.15 (feasible: True).

| Seed | Base car | Base PT | Base WFH | Days 6-10 | Day 6 | Days 8-10 | Capacity scale |
|---|---|---|---|---|---|---|---|
| 1 | 0.844 | 0.156 | 0.000 | -20.9% | -21.7% | -20.4% | 0.3961 |
| 2 | 0.840 | 0.160 | 0.000 | -22.1% | -23.8% | -21.2% | 0.3961 |
| 3 | 0.855 | 0.145 | 0.000 | -23.7% | -24.5% | -23.2% | 0.4303 |
| mean | 0.846 | 0.154 | 0.000 | -22.2% | -23.3% | -21.6% | 0.4075 |

Days 6-10: car 0.658, PT 0.324, WFH 0.018; 14.2% of commuters have a WTP below the NZ$6 peak, 8.3% no car option on charged days. Peak 15-min road + queue delay 14.0 -> 9.2 min; mean road delay 6.68 -> 5.30 min.

Feasible points:

| PAP | k_WFH | beta0 | Base car | Base PT | Days 6-10 | Loss |
|---|---|---|---|---|---|---|
| 20 | 8 | 0.05 | 0.840 | 0.153 | -30.4% | 8.818 |
| 20 | 9 | 0.05 | 0.843 | 0.154 | -27.9% | 5.933 |
| 20 | 9 | 0.1 | 0.843 | 0.154 | -29.0% | 7.062 |
| 20 | 9 | 0.15 | 0.843 | 0.154 | -30.4% | 8.925 |
| 20 | 10 | 0.05 | 0.844 | 0.154 | -25.7% | 4.156 |
| 20 | 10 | 0.1 | 0.844 | 0.154 | -26.9% | 5.044 |
| 20 | 10 | 0.15 | 0.844 | 0.154 | -28.4% | 6.549 |
| 20 | 10 | 0.2 | 0.844 | 0.154 | -29.8% | 8.068 |
| 20 | 11 | 0.05 | 0.845 | 0.154 | -23.8% | 3.080 |
| 20 | 11 | 0.1 | 0.845 | 0.154 | -24.9% | 3.705 |
| 20 | 11 | 0.15 | 0.845 | 0.154 | -26.6% | 4.886 |
| 20 | 11 | 0.2 | 0.845 | 0.154 | -27.8% | 6.013 |
| 20 | 11 | 0.25 | 0.845 | 0.154 | -29.4% | 7.734 |
| 20 | 12 | 0.05 | 0.846 | 0.154 | -22.5% | 2.614 |
| 20 | 12 | 0.1 | 0.846 | 0.154 | -23.7% | 3.047 |
| 20 | 12 | 0.15 | 0.846 | 0.154 | -25.4% | 3.997 |
| 20 | 12 | 0.2 | 0.846 | 0.154 | -26.6% | 4.930 |
| 20 | 12 | 0.25 | 0.846 | 0.154 | -28.2% | 6.421 |
| 20 | 12 | 0.3 | 0.846 | 0.154 | -30.2% | 8.691 |
| 20 | 13 | 0.05 | 0.846 | 0.154 | -21.4% | 2.347 |
| 20 | 13 | 0.1 | 0.846 | 0.154 | -22.6% | 2.647 |
| 20 | 13 | 0.15 | 0.846 | 0.154 | -24.3% | 3.353 |
| 20 | 13 | 0.2 | 0.846 | 0.154 | -25.6% | 4.133 |
| 20 | 13 | 0.25 | 0.846 | 0.154 | -27.2% | 5.434 |
| 20 | 13 | 0.3 | 0.846 | 0.154 | -29.1% | 7.432 |
| 20 | 14 | 0.05 | 0.846 | 0.154 | -20.5% | 2.233 |
| 20 | 14 | 0.1 | 0.846 | 0.154 | -21.6% | 2.377 |
| 20 | 14 | 0.15 | 0.846 | 0.154 | -23.3% | 2.892 |
| 20 | 14 | 0.2 | 0.846 | 0.154 | -24.7% | 3.565 |
| 20 | 14 | 0.25 | 0.846 | 0.154 | -26.3% | 4.662 |
| 20 | 14 | 0.3 | 0.846 | 0.154 | -28.2% | 6.435 |
| 20 | 15 | 0.05 | 0.846 | 0.154 | -19.9% | 2.224 |
| 20 | 15 | 0.1 | 0.846 | 0.154 | -21.0% | 2.287 |
| 20 | 15 | 0.15 | 0.846 | 0.154 | -22.7% | 2.669 |
| 20 | 15 | 0.2 | 0.846 | 0.154 | -24.1% | 3.243 |
| 20 | 15 | 0.25 | 0.846 | 0.154 | -25.6% | 4.197 |
| 20 | 15 | 0.3 | 0.846 | 0.154 | -27.7% | 5.878 |
| 20 | 15 | 0.4 | 0.846 | 0.154 | -30.3% | 8.811 |
| 20 | 16 | 0.05 | 0.846 | 0.154 | -19.5% | 2.247 |
| 20 | 16 | 0.1 | 0.846 | 0.154 | -20.6% | 2.248 |
| 20 | 16 | 0.15 | 0.846 | 0.154 | -22.2% | 2.538 |
| 20 | 16 | 0.2 | 0.846 | 0.154 | -23.6% | 3.036 |
| 20 | 16 | 0.25 | 0.846 | 0.154 | -25.3% | 3.947 |
| 20 | 16 | 0.3 | 0.846 | 0.154 | -27.3% | 5.503 |
| 20 | 16 | 0.4 | 0.846 | 0.154 | -29.8% | 8.265 |
| 21 | 8 | 0.05 | 0.853 | 0.140 | -29.5% | 7.427 |

## Out of sample (seeds 4-12, own capacity calibration)

Mean: base car 0.849, PT 0.151, WFH 0.000, days 6-10 -22.1% (single seeds -23.8% to -20.0%); in band at the stated precision: True.

## Sensitivity to fixed assumptions (seeds 1-3, capacity recalibrated, never adopted)

| Variant | Base car | Days 6-10 | Day 6 | Days 8-10 |
|---|---|---|---|---|
| chosen | 0.846 | -22.2% | -23.3% | -21.6% |
| no willingness-to-pay limit (wtt.beta0 = 0) | 0.846 | -16.1% | -17.3% | -15.4% |
| SSC2026's price sensitivity (wtt.beta0 = 0.5) | 0.846 | -32.6% | -33.6% | -32.0% |
| VoT_ref = median VoT of the simulated commuters (wtt.vot_ref = sample_median) | 0.846 | -22.2% | -23.3% | -21.6% |
| no early-start option (persona.early_shift_prob all 0) | 0.841 | -23.5% | -24.9% | -22.8% |
| early day costs NZ$1.5 x phi(F) (costs.early_shift_cost 3 -> 1.5) | 0.844 | -21.4% | -21.9% | -20.9% |
| early day costs NZ$6 x phi(F) (costs.early_shift_cost 3 -> 6) | 0.846 | -23.3% | -24.6% | -22.6% |
| every employer of archetypes 1, 2 and 4 allows the early day | 0.844 | -21.8% | -22.7% | -21.3% |

