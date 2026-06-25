# SSC2026 congestion-pricing extension: integration guide

This adds a cordon charge and three CBD-entry decision rules (Baseline exponential
decay, El Farol, Q-Learning) to `akl_traffic.nlogo`, ported from
`code/congestion_tou_v3.py`. The agent decision is binary CBD entry, but congestion
is now emergent from real movement on the Auckland network.

I could not run NetLogo in this session, so treat this as a draft to open and test in
NetLogo. Static checks (bracket / paren / to-end balance) pass.

## What was changed already

- `akl_pricing.nls` (new) — fee schedule, heterogeneous VOT, the three rules, the
  multi-day learning loop, and tracking reporters.
- `akl_nodes.nls` — `roads-own` gained `r-cbd?` and `r-position`.
- `akl_vehicles.nls` — `vehicles-own` gained the pricing / decision-state variables.
- `akl_traffic.nlogo` — added `akl_pricing.nls` to `__includes`, and `pricing-init`
  to `setup`.

## Three things you still need to do in NetLogo

### 1. Add interface widgets (the module reads these as globals)

Choosers:

- `decision-rule` : "Baseline" "El Farol" "Q-Learning"
- `fee-regime`    : "none" "flat" "tou"

Sliders (min, max, default):

- `flat-fee-level`     0, 10, 2
- `base-beta`          0.1, 1.5, 0.5
- `el-farol-threshold` 0.3, 0.9, 0.6
- `ql-alpha`           0.01, 0.5, 0.1
- `ql-gamma`           0.5, 0.99, 0.9
- `ql-epsilon-init`    0.05, 0.9, 0.4
- `ql-epsilon-decay`   0.99, 0.999, 0.997
- `n-sim-days`         1, 50, 20
- `ticks-per-hour`     60, 1200, 600

Button: `go-days` (forever off).

### 2. Enforce the entry decision in movement (one hook)

`new-day-decisions` sets `enters-cbd?` per agent, but movement still visits every
destination. Add a guard so a vehicle that chose not to enter skips its CBD
destinations for the day. Suggested minimal edit near the top of the `at-activity?`
branch in `vehicles-travel` (akl_vehicles.nls), placed just before the existing
`while [length trip = 0 ...]` loop:

```netlogo
;; SSC2026: skip CBD destinations the agent chose not to enter today
while [ i-destination + 1 < length b-destinations
        and [is-cbd?] of (item i-destination b-destinations)
        and not enters-cbd? ] [
  move-to item i-destination b-destinations
  set i-destination i-destination + 1
  set b-destination item i-destination b-destinations
  set trip []
]
```

Test this placement when you run it; the exact spot may need a small adjustment given
how `i-destination` advances elsewhere. Without this hook the model still records
`enters-cbd?` but does not physically remove suppressed trips, so congestion will not
fall.

### 3. Run

`setup` then press `go-days`. Per-day summary rows accumulate in the `day-records`
global (day, rule, regime, attendance, CBD congestion, inner / boundary / peripheral
density, mean fee). Export with, for example:

```netlogo
csv:to-file "../output/tables/netlogo_pricing_runs.csv" day-records
```

## Mapping to the reviewer comments

- R1-C3 (equations): the governing rules are in `decide-baseline`, `decide-el-farol`
  / `el-predict` / `el-update`, and `q-state` / `decide-qlearning` / `q-update`.
- R1-C4 (sensitivity): sweep `base-beta`, `el-farol-threshold`, `ql-alpha`,
  `ql-epsilon-init` / `ql-epsilon-decay` via BehaviorSpace over the new sliders.
- R1-C5 (spatial displacement): now genuinely emergent. `r-position`
  (inner / boundary / peripheral) and `mean-density-at` let you show whether the
  charge displaces load to the cordon fringe rather than removing it.
- R2-C1 (aim): `fee-regime` is held fixed while `decision-rule` varies, so the design
  reads as a behavioural comparison under one price.

## Assumptions to revisit

- Clock: hour-of-day is derived as `(floor (ticks / ticks-per-hour)) mod 24`. The base
  model is trip-driven, not anchored to a 24 h clock, so confirm `ticks-per-hour`
  matches your intended time mapping (README states 600 ticks per hour).
- Each agent draws one peak-weighted `trip-hour` per day in `draw-trip-hour`; adjust
  the bands if your demand profile differs.
- Q-learning persists across days because `go-days` does not call `clear-all`. Do not
  press the old `setup`/`go` between days if you want learning to accumulate.
