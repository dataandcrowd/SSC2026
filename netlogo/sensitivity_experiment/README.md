# Sensitivity experiment (NetLogo headless)

A focused sensitivity analysis for the SSC2026 congestion-pricing model, run through
BehaviorSpace headless so it uses the paper's decision rules exactly (unlike the Python
`code/akl_sim_v2.py`, whose El Farol rule diverges, see note below).

## What it does

Each rule's main behavioural parameter is varied across a small set of values around its
baseline, under No-Charge and ToU, for 20 simulated days, recording `peak-vc-inner` each
day. This is a sensitivity check on the main parameters, not an exhaustive grid search.

| Experiment | Rule | Parameter | Values (baseline in bold) |
|---|---|---|---|
| sensitivity-pay | Exp-Decay | base-beta | 0.25, **0.5**, 1.0 |
| sensitivity-elfarol | El Farol | el-farol-threshold | 0.5, **0.6**, 0.7 |
| sensitivity-ql-alpha | Q-Learning | ql-alpha | 0.05, **0.1**, 0.2 |
| sensitivity-ql-epsilon | Q-Learning | ql-epsilon-init | 0.2, **0.4**, 0.6 |

Because `peak-vc-inner` is recorded for each of the 20 days, the aggregator reports both
the mean reduction (No-Charge to ToU) and the day-to-day standard deviation (volatility).
To widen the analysis later, add more values to each `enumeratedValueSet`.

## How to run

1. Install NetLogo 6.x (tested 6.4.0 headless, Java 11+).
2. From this folder:

   ```bash
   export NETLOGO=~/NetLogo-6.4.0-64        # your install dir
   bash run_sensitivity.sh                   # writes output/tables/sensitivity-*.csv
   python3 aggregate_sensitivity.py          # prints the summary
   ```

`run_sensitivity.sh` runs from the `netlogo/` folder so the model's relative `Data/...`
paths resolve, and uses all cores via `--threads`.

## Note on the Python model (important)

The public `code/akl_sim_v2.py` implements El Farol as
`threshold = comfort_threshold * exp(-beta*fee/vot)` (multiplicative), whereas the paper
and this NetLogo model use `adj_threshold = comfort_threshold - (fee/median_VoT)*beta*0.3`
(subtractive). With the multiplicative form El Farol becomes the most price-responsive
rule, reversing the paper's central finding. On the same network, switching only the El
Farol formula to the NetLogo version moved its ToU reduction from about 25% to about 1%,
matching the paper. The Python script should be corrected to match this model.
