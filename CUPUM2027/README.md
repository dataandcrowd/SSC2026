# Cordon-Lite

A deliberately simple commuter simulation for the CUPUM 2027 book chapter "LLM agents in traffic
behaviour modelling: a 'cognitive clock' for drivers in congestion" (Hyesop Shin and Milad
Malekzadeh).

## Purpose

Cordon-Lite asks where an LLM should sit in a traffic agent-based model. Commuters normally follow
a standing plan (habit). A "cognitive clock" wakes a decider only when something meaningful happens.
The decider is either a rule (random-utility choice over a generalised cost) or an LLM. The model
compares the two on:

- the aggregate response at the cordon;
- who adapts;
- interpretability (every decision carries a logged reason);
- call volume (how many decisions need the decider at all).

Scope: the Auckland city-centre cordon (SA3 "Auckland City Centre"), AM peak only, 950 commuters (a
5% sample of the 19,000 cars that enter in the charged morning hours, so one agent stands for 20
cars), 30 repeated weekdays. Cars drive congested roads to their cordon gate (background traffic
from counts plus the commuters' own cars, with motorway flow breakdown) and queue at the gate. A
time-of-use (ToU) charge starts on day 11 and a PT disruption hits one corridor on day 20. Each
morning a commuter drives (at a departure time it picks), takes PT or works from home; each has its
own willingness to pay to drive into the city centre, and the share willing to pay falls
exponentially as the charge rises.

State described: 2026-10-09, after road congestion (2026-10-07), motorway flow breakdown from NZTA
counts, 950 agents and the Level of Service outputs (2026-10-08) were added. On 2026-10-09 SKIP
(postponing the day) was removed, the willingness to travel with an exponential decay was added,
and the peak charge became a plain NZ$ setting (`fees.peak_fee`), run at NZ$0, 3, 12, 18 and 30
next to the canonical NZ$6 ("Charge levels" below). The behaviour calibration (PAP 22, k_WFH 12,
beta0 0.15), the capacity calibration and the canonical runs were regenerated for this state the
same day. The NetLogo model got two choosers (the run and the days to watch) and a mean V/C plot.

## Design

### City-wide demand, congested roads, gate queues

The TomTom major-road network (46,965 segments, about 28.5k nodes) is used **offline** in Python
(`prep/build_inputs.py`). For 3,000 city-wide origins it finds:

- the shortest free-flow path into the cordon;
- the gate where that path first enters the cordon;
- the free-flow minutes to the gate and from the gate to the destination.

The 27 gates used are grouped into 5 corridors by entry bearing. A car's morning then has three
parts (user decision, 2026-10-07: roads are congested in both engines, with background traffic plus
the commuters' own cars):

1. **Roads to the gate, congested.** `prep/build_roads.py` cuts the pre-gate part of the 3,000
   paths into 5,903 road sections (849 km, about 48 sections per path). Every minute a section
   carries background traffic from the traffic counts plus the commuters' cars that entered it in
   the last 15 minutes. Its speed follows the BPR curve of volume over capacity, so a car that
   leaves at 07:45 takes longer than one that leaves at 06:30. The car's road delay is its time
   over free flow, in whole minutes.
2. **Gate queue.** One Vickrey point queue per corridor at minute resolution. A car joins it at
   gate arrival = departure + free-flow minutes to the gate + road delay.
3. **Gate to destination, free flow.** Inside the cordon the gate queue stands for the congestion.

A charge that removes commuter cars therefore eases both the roads they used and the gate queues.

### Road congestion

- **Background traffic [DATA, A].** Two-way average daily traffic (ADT) from the AT/NZTA count
  points of the SSC2026 repository: 13,835 points, of which 3,179 match a road of the same name
  within 30 m. A count holds along its street for up to 1 km; other roads take the median of
  their road class and speed band. Observed inbound peak-hour flow = 0.6 x AM peak ratio x
  two-way ADT, spread over the morning by a 15-min time profile (peak timing from the counts,
  shape assumed). Of the origin-weighted pre-gate minutes, 25.6% are on sections with their own
  count, 15.1% propagated, 3.7% default and 55.6% on motorway sections that take their values from
  the NZTA counts (below).
- **Commuters [A].** The commuters' expected cars are netted out of the counts (car share 0.8 of
  19,000 cars), so background plus usual commuters equals the counts. In a run each agent adds its
  20 cars to every section it enters, for 15 minutes. Commuters are about 16% of the counted
  morning volume on their routes (origin-weighted mean over pre-gate minutes).
- **Speed [SSC].** BPR: time = free flow x (1 + 0.15 (V/C)^4), at least 0.18 of free-flow speed,
  as in SSC2026.
- **Capacity [A, DATA].** Capacity = k x directional ADT (SSC2026's rule), with the directional
  ADT at least the 5th percentile of its road class, so that a tiny or stale count does not give a
  near-zero capacity (280 sections raised, 1.4% of the minutes). k = 0.076999 is bisected so that
  the origin-weighted travel time index (TTI) of departures 08:00-08:59 under usual traffic, on the
  non-motorway part of each trip, equals 1.714: the TomTom Traffic Index, Auckland 2025, morning
  rush-hour congestion level 71.4% (https://www.tomtom.com/traffic-index/auckland-traffic/).
  Motorways do not enter this match; their level follows from the breakdown rule.

Usual-traffic TTI to the gate by departure hour (`data/road_report.md`):

| Departures | Non-motorway part | Motorway part | Whole trip to the gate |
|---|---|---|---|
| 06:00-06:59 | 1.042 | 1.410 | 1.239 |
| 07:00-07:59 | 1.410 | 1.997 | 1.747 |
| 08:00-08:59 | 1.714 (target) | 2.032 | 1.927 |
| 09:00-09:59 | 1.205 | 1.774 | 1.529 |

### Motorway flow breakdown

Auckland's motorways run over capacity for hours every morning and break down into stop-and-go
flow. SSC2026 never slowed its motorways (its high motorway LoS E/F shares were measurement only),
so this rule is new in Cordon-Lite (2026-10-08).

- **Motorway mainline sections**: frc 0 or a motorway name (the Harbour Bridge stretch has a lower
  TomTom class), not a ramp, signed 70 km/h or more: 285 sections, 147 km, 56% of the
  origin-weighted pre-gate minutes.
- **Rule [A, L].** A motorway section is broken down inside its breakdown window and at any other
  minute when today's V/C, with the commuters' cars, reaches 1. Broken-down flow loses capacity
  (the drop the counts show, else 10%; Cassidy and Bertini 1999) and moves at no more than 45% of
  free-flow speed (45 km/h on a 100 km/h motorway; bottleneck speeds of 25-35 km/h at SH20, Brown et
  al. 2005).
- **NZTA counts [DATA]** (user decision: 2024 quarter-hourly profiles plus 2025-26 daily volumes).
  `prep/fetch_nzta.py` reads the NZTA Traffic Monitoring System counts of 36 sites on the CBD
  approaches into `data/nzta/`; 19 CBD-bound through-lane sites have enough valid weekdays. Their
  counts show when flow breaks down (it peaks at 06:00-06:30 and falls by 6-26% to a plateau), the
  pre-breakdown capacity and when flow recovers. Each motorway section of a corridor with sites
  (232 sections, 99% of the origin-weighted motorway minutes) takes capacity, observed flow, time
  profile, window and capacity drop from the nearest site of its corridor.

| Motorway stretch | Usual breakdown window |
|---|---|
| Harbour Bridge | 06:15-09:30 |
| Northern, Albany to Tristram Avenue | 06:45-09:30 |
| Northern around Northcote | 06:45-11:00 (no recovery in the counts) |
| Southern, city to Mt Wellington | from 06:45-07:15 until 11:00 (no recovery in the counts) |
| Southern, south of Mt Wellington | 07:15-09:45 |
| Northwestern | from 06:30-07:15 until 09:30-09:45 |
| Northwestern city end, Southwestern | none: the counts show no breakdown, so they break down only when today's traffic fills them |
| No count site (Upper Harbour, George Bolt Memorial Drive, Airport) | 07:08-10:01, from usual V/C (six floor-raised Upper Harbour sections a little shorter) |

Under usual traffic 81% of the motorway network (by free-flow minutes) is broken down from 07:30 to
09:00 (36% at 07:00, 60% at 09:30, 31% at 10:00). The usual windows come from the counts, so fewer
commuter cars on charged days cannot shorten them; they can only prevent the breakdowns that
today's traffic starts.

NZTA attribution (CC BY 4.0): Traffic counts sourced from the New Zealand Transport Agency (NZTA
Waka Kotahi) Traffic Monitoring System via the NZTA Open Data portal, licensed for re-use under CC BY
4.0.

### Gate queues and capacity calibration

The 5 corridors are Vickrey point queues at minute resolution. A point queue has a known
analytical benchmark (Vickrey 1969; Arnott, de Palma and Lindsey), used as a sanity check
(`cordonlite/vickrey.py`). Corridor capacity is the number of the corridor's agents divided by 60
min, times a calibrated scale, and at least 950 veh/h (converted to agents per minute at the run's
n).

`python -m cordonlite.run calibrate --seeds 1 2 3` bisects the scale per seed so that, in the
R-daily no-charge run, the car-weighted mean over corridors of the peak 15-min mean delay on days
6-10 is 15 min, where the delay is the gate queue plus the road delay before the gate
(`engine.calib_delay = "total"`). The 15-min total-delay target is a user decision, re-confirmed
after the motorway breakdown rule was added. Most of it is now road delay, and the gate queue adds a
few minutes on most corridors. In the peak bin of each corridor and day (seeds 1-3, days 6-10,
car-weighted) road delay is 67-78% of the calibrated peak: road 10.56, 11.11 and 10.56 min, queue
3.01, 5.41 and 3.96 min. Per corridor the gate queue alone peaks at 0.4 to 3.2 min, except West on
seeds 1 and 3 (12.4 and 7.0 min), South-west on seed 2 (20.1 min) and South-east on seed 3 (5.9
min). Seeds 1-3 with 950 agents are calibrated at the chosen PAP, k_WFH and beta0 (beta0 does not
enter: the calibration runs have no charge): scales 0.430292, 0.396105 and 0.396105, with achieved
peaks of 13.57, 16.52 and 14.51 min against 15 +/- 2 min (`engine.calib_tol_min`).

### Why this level of detail

- The cordon test only needs to know whether and when a car enters the cordon, and each path's
  gate is known exactly. Expanding demand to the whole city therefore maximises OD coverage.
- The morning traffic on the way in is part of what a commuter weighs: leaving later costs road
  delay as well as queue, and a charge that removes cars eases the roads. Sections along fixed
  routes give that time dependence at little cost, deterministically and identically in both
  engines.
- Route choice, spillback, signals and junction delay are left out on purpose. Such network
  dynamics could create or hide differences between rule and LLM deciders; with fixed routes, any
  difference between arms comes from the deciders.
- Most of the road volume is background traffic from counts, not agents, which is why a 5% sample
  is enough (below). The gate queue keeps an analytical benchmark.

### 950 agents (a 5% sample)

User decision (2026-10-08): 950 agents, 5% of the 19,000 AM charged vehicles
(`engine.agents_represented`), so one agent stands for 20 cars; 95 of them (10%) are twins. The
model used 300 agents (63 cars each) before. Why 5% is enough:

- **Convergence.** In a scale study (2026-10-08: roads on, before the motorway breakdown rule,
  R-daily, seed 1, capacity scale fixed at 0.430, days 6-10), 950 agents come within about 1-2% of a
  full-population run (19,000 agents, one car each) in car share, road delay and TTI:

  | Agents | Car share | Road delay (min) | TTI, 08:00 | Gate queue (min) |
  |---|---|---|---|---|
  | 300 | 0.863 | 4.84 | 1.856 | 1.45 |
  | 950 | 0.857 | 4.78 | 1.875 | 0.76 |
  | 1,900 | 0.845 | 4.75 | 1.864 | 0.48 |
  | 19,000 | 0.845 | 4.85 | 1.872 | 0.31 |

  The gate queue is what changes with n (each agent reaches the gate as a platoon of its cars in one
  minute), and capacity is recalibrated at every n anyway.
- **Seed spread.** Over seeds 1-5 at a fixed capacity scale, the standard deviation of the R-daily
  response (car crossings, days 21-30 against 6-10) is 1.9 pp at 300 agents, 1.1 at 950 and 0.5 at
  1,900; of the base car share 0.017, 0.014 and 0.008; of the mean road delay 0.29, 0.24 and 0.02 min.
  The single-seed tolerances of the behaviour calibration scale with sqrt(300 / n): shares +/-0.028
  and responses +/-2.2 pp at 950 (+/-0.05 and +/-4 pp at 300).
- **Load granularity.** At 950 agents one agent adds 80 veh/h to a section for 15 minutes, 13% of
  the median section capacity (618 veh/h); at 300 it added 253 veh/h (41%). In the scale study 16% of
  the sections expected to carry at least 50 commuter vehicles got no sampled agent at 300, against
  0.2% at 950.
- **Literature.** Ben-Dor, Ben-Elia and Benenson (2021, Simulation Modelling Practice and Theory
  108, 102233, doi:10.1016/j.simpat.2020.102233) find in MATSim that samples of 25% or more keep the
  main traffic statistics, 10-25% are unstable for some and below 10% results can deviate
  substantially. Mersini and Ziemke (2025, MATSim User Meeting, paper 30, preliminary results) find
  scores and travel times deviating at 5% and clearly at 1% and average statistics unreliable below
  10%, and note that 10% samples are usual MATSim practice.
  These thresholds hold where all congestion comes from the agents and capacity is scaled down with
  the sample. In Cordon-Lite most of the road volume is background traffic from counts (commuters
  are about 16% of it on their routes), the agents' load enters as weighted vehicles (scaling up the
  vehicle instead of scaling down capacity) and the gate capacity is calibrated at every n.
- **LLM cost.** Calls and tokens grow linearly with n. L-daily makes up to n x 30 calls (28,500 at
  950, 57,000 at 1,900; 27,300 on seed 1 at 950, because 1,200 decisions are forced onto PT by the
  willingness to pay and need no call); L-clock made 2,250 at 950 (seed 1, MockLLM estimate: about
  2.65M input tokens, against about 34.1M for L-daily). A 10% sample
  (1,900) would halve the seed spread again at twice the cost of every LLM arm.

A 30-day PyEngine run at 950 agents takes about 40 s (R-clock) to 65 s (R-daily), a NetLogoEngine
run about 100 s.

### Engines

The engine exists twice with identical semantics: `PyEngine` (Python reference) and `NetLogoEngine`
(NetLogo 7.0.4 through pynetlogo, model `netlogo7/cordon_lite.nlogox`, which is also the GUI that
replays a run on the road network). Python handles every decision and the PT and WFH outcomes.
The engine handles only cars: the drive section by section to the gate (`cordonlite/roads.py`
`simulate_roads`, ported line by line to the NetLogo procedure `road-arrivals`; both use only
`+ - * /` and floor, so they compute the same doubles), then the gate queue. The two engines give
byte-identical run outputs apart from the engine label.

### Persona layers

- **Layer A, constraints** (random stream "A"): origin (weighted city-wide sample, which fixes
  the corridor, the road route and the free-flow times), value of time (lognormal, as in SSC2026),
  archetype (hybrid office, on-site office, shift/service, trades/work vehicle, tertiary student)
  conditioned on the VoT quintile, work start t*, company car, parking cost, PT and WFH
  feasibility, whether the employer allows an earlier working day (07:00 to 15:00), and the
  willingness to pay to drive into the city centre (2026-10-09). The last two are drawn after every
  other field, in that order, so adding them changed no other field.
- **Layer B, dispositions** (independent stream "B"): habit H, schedule flexibility F, PT openness
  P and cost salience S, each on a 5-level scale (v3 design note). Rules map them to cost
  parameters. The LLM receives them as fixed sentences. The last 95 agents are "twins": they copy
  the Layer A of agents 0-94 and keep their own Layer B.
- **Layer C, memory**: one record per day (including the road delay met and expected); the last 5
  days are shown in the prompt. EMAs track the experienced versus forecast queue delay and the
  reference fee.

### Options and what commuters know about the roads

Options per agent and day: car departures at the standing time plus or minus 0-60 min (15-min
grid, 06:00-09:45), PT (services every 10 min; the rider takes the latest one arriving by the
start time; not for trades) and WFH (hybrid workers only). SKIP, a one-day postponement, was
removed on 2026-10-09 [author decision]: it had become a permanent choice (at a NZ$30 peak 97 of
R-clock's 102 skippers skipped every one of days 21-30; at NZ$6, 8 commuters skipped every day),
and in the rule arms every skipper could have taken PT.

**Willingness to travel** (2026-10-09, author decision; after the exponential decay of the SSC2026
model). Each commuter draws u ~ U(0, 1) once and has a fixed most it would pay a day to drive into
the city centre:

    beta = clip(beta0 x VoT_ref / VoT, 0.1, 2.0),   WTP = -ln(u) x VoT / beta   (NZ$, to the cent)

so the share willing to pay a charge F is P(WTP >= F) = exp(-beta F / VoT): it falls exponentially
in the charge. VoT_ref = exp(`persona.vot_mu`) = NZ$9.97/h, the median of the VoT distribution
(`wtt.vot_ref`; SSC2026 used the sample median). beta0 = 0.15 is calibrated with PAP and k_WFH
("Behaviour calibration" below; SSC2026's base_beta 0.5 is the anchor); a commuter with the median
VoT pays the NZ$6 peak with probability exp(-0.15 x 6 / 9.97) = 0.91. On a charged day a car option
whose charge (the fee at its expected cordon crossing) is above the commuter's WTP is not offered:
cheaper shoulder departures stay (retiming), and a commuter unwilling to pay any of them takes PT or
works from home; one left with PT only is "forced" (no decision is asked). Company cars (the
employer pays) and commuters with neither PT nor WFH (the trades: an essential trip) keep every car
option. The rule applies in every arm, rule and LLM alike, as a constraint on the choice set like
PT availability. Uncharged days are unaffected (every fee is 0), and `wtt.beta0 = 0` switches it off.
On seed 1, 14.4% of commuters have a WTP below NZ$6 and 44.3% below NZ$30. Differences from SSC2026
(a threshold fixed per commuter instead of a daily draw, no base trip rate, no 0.05-0.95 clip, the
exemptions in place of an essential-trip draw) are in `DEVIATIONS.md`.

**Road information.** Every car option carries the road delay a car on the commuter's route would
have when leaving at that time: usual traffic on day 1 (what commuters know from experience),
yesterday's actual traffic from day 2 (a probe car on the route that adds no load). The expected
gate arrival, the queue forecast, the crossing minute (and so the charge), the arrival and the time
cost all include it. The LLM prompt (template `cl-v3`: road traffic since `cl-v2`, no SKIP row
since 2026-10-09) gives the free-flow drive and, by time of leaving home, the usual traffic (day 1)
or yesterday's traffic and queue; the options and memory tables have a "traffic delay" column. On a
day when the willingness to pay removed a car option the prompt says so ("You would not pay more
than NZ$x a day to drive into the city centre, ..."). PT time does not depend on road traffic (rail
and busway assumption). WFH saves the congestion delay (road and queue), not the free-flow commute.

**Starting work earlier** (2026-10-05). A commuter whose employer allows it (probability 0.8 for
hybrid office, 0.5 on-site office, 0 shift/service, 0.5 trades, 0 students [A]) can work 07:00 to
15:00 on any day instead of the usual hours. This is a real option, not arriving early and waiting:
every car and PT option of such a commuter is measured against the cheaper of two starts, the usual
start t* or 07:00 plus an inconvenience cost of NZ$3 x phi(F) a day [A]. The car departures that
reach each start (a reference departure that allows for the day's expected road delay, plus or minus
15 min) are added to the standing set, so a commuter with t* = 08:30 can leave at 06:15 or
06:30 for a 07:00 start. Early and late minutes, the lateness trigger T3 and the stored outcome all
use the start the chosen option implies (`start_used_min`, `early_shift` in `decisions.csv` and
`outcomes.csv`). The LLM prompt states the permission in plain words and shows the start time of
every option.

**Costs.** The rules and MockLLM use the generalised cost (time including road and queue delay,
schedule delay with Small 1982 ratios, fee with a loss term on the part above a reference fee that
follows the fee faced, parking, fuel, PT with an attitude penalty, WFH without a commute, parking or
fuel credit, habit). Two money costs of driving are fixed inputs and are never calibrated.
Paid parking is NZ$17 a day for office archetypes (student NZ$12.75, trades and company vehicles 0)
[author decision; consistent with the AT 2014 Victoria St daily rate already noted in config
comments]. Fuel is 2 x path length x NZ$0.30/km (round trip; 0 for employer vehicles): petrol
NZ$3.30/L [author-supplied, Oct 2026] x 9.0 L/100 km (real-world light petrol vehicles, Metcalfe and
Sridhar 2016 for the Ministry of Transport; sources in `config.toml`), about NZ$8.6 a day for a driver
who pays it (950-agent personas, seeds 1-3). The petrol price was supplied by the authors and has
not been verified here against a published series. The real LLM sees the same options with their
attributes, including the daily parking and fuel costs and the traffic delay, but never the
generalised cost, and it is offered the same options (the willingness to pay removes the same car
options). Rule noise uses common random numbers, so twins in the same state draw the same noise.

### Behaviour calibration

The rule decider is calibrated on the R-daily arm (seeds 1-3), at the NZ$6 peak, to stated targets:
before the charge car 0.75-0.85, PT 0.08-0.15, WFH at most 0.10 (and SKIP at most 0.02 until SKIP
was removed on 2026-10-09); car cordon crossings on days
21-30 12-22% below days 6-10 (Stockholm about -20%, Gothenburg about -12%; Börjesson et al. 2012,
Börjesson and Kristoffersson 2015), with an overshoot on days 11-13 of about -30% at most. These
anchors are total cordon traffic in charged hours, observed over months to years; the band applies
to AM car commuters over days, so the comparison is qualitative (v3 10.5), and a private-car
commuter response is likely larger. Four structural fixes come first (reference fee follows the fee
faced, capped loss weight eta, WFH priced as in v3, no habit discontinuity at a price change).
Paid parking, fuel and the early start are fixed inputs, and so are the number of agents, the road
settings and the capacity target. Three scalars are then searched (two before 2026-10-09), with
capacity recalibrated at every (PAP, k_WFH) pair and seed: the PT attitude penalty (PAP, 10-36 in
NZ$1 steps; in the specification form omega(P) x (VoT/60 x T_pt + PAP), so omega also scales PT
time and there is no v3 HTA/2 factor), k_WFH (2-16 in NZ$1 steps) and beta0, the price sensitivity
of the willingness to travel (`wtt.beta0`, 0.05-1.0, anchor 0.5 = SSC2026's base_beta). The
single-seed tolerance scales with sqrt(300 / n): at 950 agents +/-0.028 in shares and +/-2.2 pp in
responses. Other peaks (`--peak-fee`) extrapolate from the NZ$6 calibration.

**Current search (2026-10-09, SKIP removed, willingness to travel added).** The search is staged
because a full 27 x 15 x 7 grid would take about 11 hours on 14 workers: stage 1 runs beta0 0.05,
0.1, 0.2, 0.3, 0.5, 0.75 and 1.0 on PAP 21-23 x k_WFH 4-16 (8 values) and the four corners of the
grid; stage 2 the full k_WFH range 2-16 at PAP 22-24 (the PAP values that meet the base shares, the
base shares not depending on beta0); stage 3 the beta0 midpoints 0.15 and 0.25. Capacity is
calibrated once per (PAP, k_WFH, seed) and shared by every beta0, since the calibration has no
charge and the willingness to pay then removes nothing; beta0 = 0 runs as a reference only
(`scripts/calibrate_behaviour.py --stage all --workers 14`: 171 calibrations and 1,638 charged
runs, search 1.9 h, all stages 2.3 h). It chose PAP 22 / k_WFH 12 / beta0 0.15, now in
`config.toml` (previously PAP 22 / k_WFH 9, no willingness to travel). 15 of 489 points are
feasible at the stated precision, all at PAP 22 on a ridge from k_WFH 10 / beta0 0.05 to k_WFH 14 /
beta0 0.25 (a higher k_WFH weakens the WFH response as much as a higher beta0 strengthens the
willingness-to-pay response); none is feasible on unrounded means (base car 0.853-0.855). The
chosen point is the feasible point nearest the anchors, ahead of k_WFH 13 / beta0 0.2 by 0.011 in
anchor distance; no value is on an edge of its range. R-daily, mean of seeds 1-3: base car 0.854,
PT 0.145, WFH 0.001, response -21.4% (days 21-30 vs 6-10), overshoot -25.2% (days 11-13); 8.3% of
commuters have no car option on charged days and 14.2% a WTP below NZ$6. Without the willingness to
travel the same PAP and k_WFH give -14.5%, and SSC2026's beta0 0.5 gives -32.3%. On unseen seeds
6-12 the response is -21.1% (single seeds -19.2% to -23.1%), but base car is 0.863, above the band
at the stated precision (0.859 over seeds 1-12). Capacity was then recalibrated at the chosen values
(step 2 below; scales 0.430292, 0.396105, 0.396105). Full account, out-of-sample seeds,
sensitivities, figures and trait checks: `docs/calibration_report.md` (written by the run); search
log `data/behaviour_calibration.json`.

**History.** Before fuel was a separate cost, three scalars were searched and the search chose PAP
11 and parking NZ$17. With fuel fixed at NZ$0.23/km (September 2025 petrol price) it chose PAP 12
and parking NZ$11, both PAP values on the edge of the range 4-12. On 2026-10-03 the authors fixed
parking at NZ$17 and fuel at NZ$0.30/km, and parking left the search; that search chose PAP 20 /
k_WFH 10 with no feasible point, because the SKIP share of two seeds (0.025) exceeded 0.02. On
2026-10-05 the authors raised the SKIP cost to NZ$30 and added the early start; with 300 agents,
free-flow roads and capacity calibrated to the gate queue alone, the same search found 6 feasible
points of 405 and chose PAP 20 / k_WFH 10 again (R-daily, seeds 1-3: base car 0.843, PT 0.154,
response -16.0%, overshoot -25.2%). In that state the fall in postponing came from the SKIP cost,
not from the early start, and the early start was used mainly to avoid the gate queue. The first
search at 950 agents with congested roads, the motorway breakdown rule and capacity calibrated to
the total delay (2026-10-09, still with SKIP at NZ$30 and no willingness to travel; 1,221
evaluations, about 4.4 h) found 8 feasible points of 405, all at PAP 22, and chose PAP 22 / k_WFH 9
(base car 0.848, PT 0.146, SKIP 0.002, response -20.7%, overshoot -27.2%). The LLM
deciders are never tuned, but the shared Layer A inputs (paid parking, fuel, early-start
permission) appear in the LLM prompt. Archived logs and reports: `data/behaviour_calibration_<tag>.json`
with `docs/calibration_report_<tag>.md`, for `pre_fuel` (no fuel), `fuel023_park11` (fuel
NZ$0.23/km, parking searched), `skip25_noearly` (SKIP cost NZ$25, no early start), `freeflow300`
(300 agents, free-flow roads) and `skip30_nowtt` (950 agents, congested roads, SKIP at NZ$30, no
willingness to travel), the last two with `data/calibration_<tag>.json` and `docs/figures/<tag>/`
(which also holds that state's example prompt).

### Cognitive clock

The clock is edge-triggered: each event wakes an agent once.

| Trigger | Wakes the agent when |
|---|---|
| T1 | it is the first day (no standing plan) |
| T2 | the charge starts or changes |
| T3 | it was late yesterday beyond a tolerance that depends on F (per late day, so a chronically late agent wakes on consecutive days) |
| T4 | PT was disrupted yesterday, or a disruption is announced on its corridor while it is a PT user; and once more on the day after an announced disruption that woke it, when service is back |
| T5 | its car time differed from expectation by more than 20% on 2 consecutive car days |
| T6 | its standing option is not offered today, for example a standing car departure whose charge is above the commuter's willingness to pay (until 2026-10-09 also every day after a SKIP) |

On any other day the agent repeats its standing option. Road delay enters T3 (through the arrival
time) and T5 (through the car time and its expectation).

### Arms

| Arm | Decider | When |
|---|---|---|
| `R-daily` | rule | every agent, every day |
| `R-clock` | rule | only on triggers |
| `L-clock` | LLM | only on triggers |
| `L-daily` | LLM | every agent, every day (upper bound on calls) |

`--traits off` sets every disposition to level 3 for both deciders: the rule uses level-3
parameters and the LLM sees the four level-3 sentences (information ladder).

### Level of Service

Each run also grades the road sections, as SSC2026 did, but on the engine's own traffic
(`cordonlite/roads.py`, the one place these are defined):

- **By V/C** (SSC2026): HCM 1994 bands, motorway mainline A < 0.30, B < 0.48, C < 0.70, D < 0.90,
  E < 1.0, F from 1.0; other roads A < 0.26, B < 0.43, C < 0.62, D < 0.82, E < 1.0, F from 1.0.
- **By speed** (added next to it, user decision 2026-10-08): HCM 2010 urban-street bands on the
  speed as a share of free-flow speed, on every road: A above 0.85, B above 0.67, C above 0.50, D
  above 0.40, E above 0.30, F at most 0.30. Also the share "congested" by Auckland Transport's
  definition (below 50% of free-flow speed).
- A motorway in flow breakdown is F in both. Shares are weighted by vehicle-km.

Both are needed, and wherever LoS E/F by V/C is reported the mean V/C is shown beside it
(`summary_table.md`, `fee_response.md`, `los.png`, `fee_response.png` and the NetLogo GUI, each with
the same note), because the V/C grade saturates:

- **Other roads.** Their capacity is a BPR scale fitted to the TomTom index (k = 0.077 x the daily
  traffic count), not a lane capacity, which puts usual V/C at about 1.2-1.6 in the peak: from
  07:00 about 99% of their traffic is at E/F by V/C at any charge level, while the mean V/C next to
  it moves a little (1.41 to 1.36 between no charge and NZ$30).
- **Motorways.** About 76% of the motorway vehicle-km lies inside the fixed usual breakdown windows
  from the NZTA counts, which are graded F whatever the flow, so motorway LoS E/F (by V/C and by
  speed) is pinned by the windows; fewer commuter cars cannot shorten them.

The speed-based grade and the AT share of the other roads respond to the charge.

## Setup

- Python 3.12 and a virtual environment in this folder:
  `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt` (on Windows the
  interpreter is `.venv\Scripts\python.exe`).
- NetLogo 7.0.4, only for the NetLogo engine and GUI. The default location is
  `/Applications/NetLogo 7.0.4` (`[engine] netlogo_home` in `config.toml`). If NetLogo is not
  there, a NetLogo run stops with a one-line message. Set the environment variable
  `CORDONLITE_NETLOGO_HOME` to the NetLogo folder (for example `C:\Program Files\NetLogo 7.0.4`):
  runs, scripts and tests read it, and it takes precedence over the key. It only says where NetLogo
  is on this machine, so it changes neither the run folder name nor `config_snapshot.toml`. Do not
  use `--set engine.netlogo_home=...` for this: it adds a `_set-<hash>` suffix to the folder name
  and changes the config snapshot, so `--compare` would report the two engines' runs as different.
  NetLogo runs print a few JVM `WARNING: ... restricted method` / `sun.misc.Unsafe` lines; they are
  harmless.
- Input data, read only by the prep steps (`[prep]` in `config.toml`). Every prep output in
  `data/` and `netlogo7/gis/` is included, so everything from step 2 on and the NetLogo GUI run
  without these inputs.
  - Steps 1 and 1b: `../netlogo/Data/roads/tomtom_major_roads.gpkg` (TomTom major roads),
    `../netlogo/Data/roads/akl_CBD_SA3.gpkg` (SA3 polygons) and the LINZ building outlines in
    `../netlogo/Data/building_api/`. That folder was removed from this repository on 2026-10-06:
    restore it from git history (commit d22e3cf) to re-run steps 1 and 1b.
  - Step 1c: internet access to the NZTA Open Data portal (`data/nzta/README.md`).
  - Step 1d: the roads shapefile `netlogo7/gis/tomtom_major_roads.shp` (`prep.roads_shp`), the
    AT/NZTA count points `../../SSC2026/netlogo/Data/Average_Daily_Traffic_Counts.geojson`
    (`prep.adt_geojson`, in the SSC2026 repository next to this one), the cordon (`prep.cordon_gpkg`
    if it exists, else `../../SSC2026/netlogo/Data/roads/akl_CBD_SA3.gpkg`, else
    `data/cordon.geojson`) and `data/nzta/`.
- The NetLogo model's GUI (below) reads its map layers from `netlogo7/gis/`: the TomTom roads as a
  shapefile, the cordon and the city-centre buildings, written by step 1b, and the road sections
  from `data/section_segments.csv`.
- An Anthropic credential only for `--backend anthropic` (see below).

## How to run

Run every command from this folder with the project interpreter.

```bash
PY=.venv/bin/python               # Windows (Git Bash): PY=.venv/Scripts/python.exe

# 1. Prep: TomTom network -> data/origins.csv, gates.csv, corridors.csv, cordon.geojson, prep_map.png
$PY -m prep.build_inputs            # optional --out-dir FOLDER; uses prep.seed = 11 (separate from run.seed), so it reproduces data/ byte for byte

# 1b. NetLogo map layers (for the GUI of netlogo7/cordon_lite.nlogox; no Cordon-Lite run reads them):
#     netlogo7/gis/tomtom_major_roads.shp (the TomTom gpkg as a shapefile, same segments and
#     attributes), cordon.shp, cbd_buildings.shp (footprints inside the cordon), cbd_buildings.csv
$PY -m prep.build_netlogo_layers    # optional --out-dir, --roads-out, --buildings

# 1c. (Optional, needs internet) NZTA motorway counts -> data/nzta/ (included; data/nzta/README.md)
$PY -m prep.fetch_nzta --cache CACHE_DIR   # --offline rebuilds from CACHE_DIR without downloading

# 1d. Road congestion inputs (about 70 s): road sections, counts, NZTA sites, capacity floor, k
#     -> data/road_sections.csv, origin_sections.csv, section_segments.csv, road_profile.csv,
#        road_meta.json, road_report.md; stops unless it reproduces data/origins.csv; a rerun
#        writes byte-identical files
$PY -m prep.build_roads             # optional --out-dir FOLDER

# 2. Calibrate corridor capacity (R-daily, no charge, days 6-10) -> data/calibration.json
#    Target: car-weighted mean over corridors of the peak 15-min mean delay (gate queue + road
#    delay, engine.calib_delay = "total") = 15 min. Seeds run in parallel (about 3 min at 950
#    agents); each run uses the record of its own seed (by_seed).
$PY -m cordonlite.run calibrate --seeds 1 2 3   # optional --jobs N (1 = one seed after another), --output FILE, --target MIN

# 2b. Behaviour calibration of the rule decider (about 2.3 h on 14 workers at 950 agents). It never
#     writes data/calibration.json or config.toml: put the chosen PAP, k_WFH and wtt.beta0 into
#     config.toml by hand and rerun step 2
$PY scripts/calibrate_behaviour.py --stage all --workers 14   # -> data/behaviour_calibration.json, docs/calibration_report.md, docs/figures/calib_*.png
#     (stages search (staged grid over PAP x k_WFH x beta0: 171 capacity calibrations and 1,638
#      charged runs), select, final, oos = out-of-sample seeds 4-12, neighbouring points and
#      sensitivities to the fixed assumptions (never adopted), report; gap = optional local
#      re-search, not part of the default; --stage report rebuilds the report from the JSON log
#      without new runs; the search keeps a resumable checkpoint in the system temp folder and
#      writes the log when it is done)

# 3. Run the arms (950 agents by default; mock backend = deterministic stand-in, not an LLM)
for ARM in R-daily R-clock L-clock L-daily; do
  $PY -m cordonlite.run --arm $ARM --backend mock --engine py --days 30 --seed 1
done
# NetLogoEngine: the variable gives this machine's NetLogo folder (see Setup; not --set)
CORDONLITE_NETLOGO_HOME="/Applications/NetLogo 7.0.4" $PY -m cordonlite.run --arm R-clock --backend mock --engine netlogo --days 30 --seed 1
$PY -m cordonlite.run --arm R-clock --backend mock --engine py --days 30 --seed 1 --traits off
$PY -m cordonlite.run --arm L-clock --backend mock --engine py --days 30 --seed 1 --traits off
for SEED in 2 3; do   # seed robustness of the rule arms (calibrated capacity records exist for seeds 1-3)
  for ARM in R-daily R-clock; do
    $PY -m cordonlite.run --arm $ARM --backend mock --engine py --days 30 --seed $SEED
  done
done

# 3b. Other charge levels: the ToU schedule scaled to a peak of NZ$0 (no charge, the comparison
#     run), 3, 12, 18 and 30 -> runs/<arm>_mock_py_s1_peak0, _peak3, ... ("Charge levels" below)
for ARM in R-daily R-clock L-clock L-daily; do
  for P in 0 3 12 18 30; do
    $PY -m cordonlite.run --arm $ARM --backend mock --engine py --days 30 --seed 1 --peak-fee $P
  done
done
# 3c. Periodic review (T7) sensitivity of the clock arm
for SEED in 1 2 3; do
  for N in 5 10; do
    $PY -m cordonlite.run --arm R-clock --backend mock --engine py --seed $SEED --set clock.review_every_days=$N --name R-clock_mock_py_s${SEED}_review$N
  done
done

# 4. Estimate LLM calls and input tokens (MockLLM run; approximate) -> runs/estimates/
$PY -m cordonlite.run --arm L-clock --days 30 --seed 1 --estimate
$PY -m cordonlite.run --arm L-daily --days 30 --seed 1 --estimate

# 5. Figures and tables -> runs/figures/ (canonical runs of one seed; see below), and the
#    fee-response outputs when the _peak runs of that seed exist
$PY -m cordonlite.analysis
$PY -m cordonlite.analysis --compare runs/R-clock_mock_py_s1 runs/R-clock_mock_netlogo_s1

# 6. Tests: the fast suite, then the NetLogo tests in their own process (about 11 min)
$PY -m pytest -q -m "not netlogo"
CORDONLITE_NETLOGO_HOME="/Applications/NetLogo 7.0.4" $PY -m pytest -q -m netlogo --run-netlogo
```

Other useful options:

- `--fee-start K` and `--regime tou|flat|none` change the charge; `--peak-fee NZ$` sets the peak
  charge (`fees.peak_fee`, default 6; the ToU schedule is scaled to it, and 0 levies no charge, the
  same run as `--regime none`; it replaced the same day's `--fee-scale` multiplier); `--capacity-scale X`
  overrides the calibration; `--set key=value` sets any config key (the value is parsed as JSON
  and must match the key's type), for example `--set costs.pt_attitude_penalty=8` or `--set costs.fuel_cost_per_km=0.27`, or the T7 review sensitivity `--set clock.review_every_days=5 --name R-clock_mock_py_s1_review5`. An explicit
  flag wins over `--set` for the same key (with a warning).
- Road variants: `--set road.enabled=false` gives free-flow roads, where the gate queue is the only
  congestion (the model before 2026-10-07); `--set road.mwy_breakdown=false` gives motorways the
  plain BPR curve; `--n-agents 300 --set persona.n_twins=30` gives the earlier population. Each needs
  its own capacity calibration, for example `calibrate --seeds 1 2 3 --set road.enabled=false
  --output data/calibration_roadsoff.json`, then runs with `--set
  engine.calibration_file=data/calibration_roadsoff.json`; otherwise the run warns and uses the
  mismatched scale.
- Run folders: `runs/<arm>_<backend>_<engine>_s<seed>[_traitsoff]`, plus one suffix for every
  setting that differs from `config.toml` (`_n<N>`, `_d<D>`, `_<regime>`, `_fs<K>`, `_peak<NZ$>`,
  `_cs<X>`, `_set-<hash>`; for example `--peak-fee 12` gives `R-clock_mock_py_s1_peak12`). Variant
  runs therefore never overwrite the canonical runs. A run is written to a
  temporary folder and moved into place only when it finishes; a failed run leaves
  `<name>.failed`. `--name DIR` and `--out FOLDER` choose the folder explicitly.
- A run whose seed, number of agents, road settings (k, BPR, flow window, motorway breakdown keys)
  or capacity target delay has no matching record in `data/calibration.json` prints a warning and
  records the mismatch in `summary.json`: recalibrate for that setting (seeds 1-3 with 950 agents
  and the current road settings are calibrated).
- Analysis: by default only canonical runs (no variant suffix) of the seed with the most runs are
  used. `--seed S` picks the seed, `--all` adds variant runs (labelled with their suffix),
  `--run-dirs DIR ...` takes an explicit list, `--include-netlogo` adds the NetLogo run. The
  fee-response outputs always compare each canonical arm with its `_peak<NZ$>` runs of the same
  seed, each against the arm's `_peak0` run on the same days (they are written only when such runs
  exist; the retired `_fx<X>` runs of the charge multiplier are left out).

### NetLogo model

`netlogo7/cordon_lite.nlogox` (NetLogo 7.0.4) is one model with two uses. Python drives it headless
as NetLogoEngine (`--engine netlogo`: `setup-from-dir`, `set-clock`, `run-day`, which load no map).
Opened in NetLogo, it replays a run with every car driving on the TomTom road network.

1. Pick an experiment in the `experiment` chooser and a PT disruption in the `pt-disruption` chooser
   ("none", or "day 3 and day 8": on each of the two days the public transport time of one corridor
   doubles, announced that morning; day 3 is before the charge and day 8 with it, so a disruption never
   falls on the day the charge starts; the runs are the experiment's folder plus `_pt3_pt8`, made with
   `--set events.pt_disruption_day=[3,8]`, which takes one day or a list of days since 2026-10-13) and
   press `setup` (about 50 s). The chooser lists 8
   experiments on seed 1: who decides (a rule or an LLM), when (only when an event wakes them, such as the charge starting, or every day) and the
   peak charge, such as "Rule, reacts to events: $6 charge" (the default) or "LLM, decides every day: $18 charge". Each
   is a 10-day run charged from day 6 (days 1-5 without the charge, days 6-10 with it), made with
   `python -m cordonlite.run --arm <arm> --days 10 --fee-start 6` (the $18 ones with `--peak-fee 18` too:
   folders `<arm>_mock_py_s1_d10_fs6[_peak18]`; the 30-day runs of the study stay in `runs/` and are not
   in the chooser). An experiment whose run is not on this computer makes `setup` stop with an error.
2. Press `go`: one morning plays until every commuter has arrived at work, and `go` stops. `go`
   starts at day 1 and plays the days in order (the first five without the charge, the last five with
   it); the `charge-on` variable ("all days", "off: before the charge" or "on: with the charge") has no
   widget: `setup` sets it to "all days" and only the check scripts change it. One tick
   is 15 simulated seconds; the NetLogo speed slider sets the pace.
3. To run day after day, switch `keep-going?` on before pressing `go`. `go` stops after day 10, the last
   day of the run, and says so.
4. `skip to end of day` jumps to the end of the morning; `Auckland view` and `City-centre view`
   switch the map (the City-centre view shows the gate queues best).

The model has no input for the charge day: each run's `scenario.csv` says from which day it is
charged (the `fee-start-day` input was removed on 2026-10-09). Dots are commuters: colour = entry
corridor, grey = works from home; commuters on public transport are drawn as green buses (breed
`bus-riders`, one per PT rider of the day). The interface is about 970 px tall (five plots in the
right-hand column).

- **Road colours.** The road sections on the commuters' routes are drawn wider and coloured by
  how fast their traffic moves at the last 5-minute mark, as a share of free-flow speed (the
  engine's speed for a car entering at that minute): 80% or more keeps the road's grey, 60-80% is
  light yellow (slow), 40-60% orange (heavy) and below 40% purple (jammed). **A purple motorway is
  in stop-and-go flow:** a motorway section in flow breakdown is purple whatever its speed. The
  slower the traffic, the wider the line. Red stays for queued cars and green for PT. Every 5
  minutes only the sections whose colour changed are redrawn (at most 60 a tick), so the map
  catches up over a few simulated minutes when many change at once.
- **Monitors and plots.** "traffic delay (min)": mean road delay of today's cars that have reached their gate;
  "mean queue wait (min)": today's mean wait at the gates. Six Level of Service monitors show the
  last 5-minute mark for motorways and for other roads: "LoS E/F %" (by V/C), "mean V/C" and "LoS E/F by speed %". The plot "% traffic at LoS E/F"
  (V/C grade) adds a point every 5 minutes for each of seven road groups, and the plot "Mean V/C (1 = at
  capacity)" directly under it shows the mean V/C of the same traffic (same pens, from the same
  5-minute pass). The groups (since 2026-10-10, instead of one line for motorways and one for other
  roads; the monitors still show the two): SH1 (Northern and Southern Motorway), SH16 (Northwestern),
  SH20 (Southwestern), North Shore (north of the Harbour Bridge, y above 5,922,500 and x above 1,753,000
  NZTM), New Lynn (within 2.5 km of its centre), Green Lane (within 1.5 km of its centre) and Other
  roads; a section belongs to the first that fits (`LOS_REGIONS`, `los_region_of` in
  `cordonlite/roads.py`, the same rules in the model's `region-of`). They are for the GUI only: `road_los.csv`
  and `los_summary.csv` keep their groups. Read the two together: from 07:00 nearly all traffic on other roads is at E/F,
  and motorways are F in their usual jam hours ("Level of Service" above); the LoS note on the
  interface and the Info tab say so. The values equal the Python definitions
  (`scripts/check_network_model.py` compares them). Further plots: commuters by state, queue length
  by corridor (legend "0: The Strand", "4: Fanshawe Street ramp", ... named by the first entry road; y-axis in cars), cordon entries per 15 min
  with the charge. The hour axes end on the next quarter hour.
- **Network.** The TomTom shapefile is built into nodes and links as the prep graph is (segment
  ends rounded to 1 m, coinciding ends dropped, the fastest of parallel segments kept), and only
  the giant component is kept, as prep routes on it: 28,507 nodes, 30,835 links and 1,106 nodes
  inside the cordon, as in `data/prep_report.md`. The link weight is free-flow minutes.
- **Homes, gates, workplaces.** Commuters start at their Cordon-Lite origins. Each car's gate is
  the prep gate of its origin (`data/origins.csv`): it drives the free-flow shortest path to the
  outside end of the gate segment, crosses the cordon at the gate point (`data/gates.csv`) and
  drives on to its workplace, a building inside the cordon (one point inside each of the 1,484
  LINZ footprints). The workplace is drawn uniformly at random once per commuter (fixed seed,
  agent_id order) and kept for every day. After its gate a car stays inside the cordon: that
  leg is routed with 60 minutes added to every road with an end outside the cordon (on plain
  free-flow minutes about two thirds of these legs would leave and re-enter it). It still leaves
  where the cordon's own roads do not connect: from the Wellesley Street ramp gate for about 100 to
  160 m and from Hopetoun Street for about 180 m. The car parks at the cordon node nearest its
  building (median 65 m away, up to about 780 m for buildings on the wharves, which the major roads
  do not reach) and the commuter is drawn at the building.
- **Clock.** The minutes are the engine's. Gate arrival = departure + free-flow minutes to the gate
  + road delay; the gate exit comes from the procedure `point-queues`, the Vickrey point queue per
  corridor that `run-day` also uses (the same as PyEngine); arrival = gate exit + free-flow minutes
  from the gate. Before its gate a car follows its section times from `road-arrivals`, the
  engine's procedure: it slows down on busy sections and reaches the gate point exactly at its gate
  arrival minute. After the gate (and on free-flow roads) it moves at constant speed. A day lasts
  until the last commuter has arrived. Cars waiting in a gate queue are red and are drawn back along
  the approach road: each agent stands for 20 cars (`agents_represented` / agents) and takes up
  about 70 m (7 m per car, 2 lanes), so a queue on the map is as long as the real queue it stands
  for; in the City-centre view each corridor label shows how many cars are waiting. The workplace
  sets where a car parks, not when it arrives: the engine's gate-to-destination minutes refer to
  the single prep destination. In the canonical R-clock run the implied speeds to the gate on days
  6 and 25 have a median of 42 km/h and a 5-95% range of 23-72 km/h (free flow: a median of 78
  km/h; measured by `check_network_model.py` on the run made before the 2026-10-09 recalibration;
  measured on the road section lengths, that run and the current one both give a median of 42 km/h
  and a 5-95% range of about 24-72 km/h). PT riders vanish while travelling and appear at their
  building at the run's PT arrival minute; WFH commuters stay at home. Replaying a run in the GUI
  writes nothing.
- **Synthetic folders.** A folder whose agents are not prep origins, such as the equivalence
  check's test scenarios, queues each corridor at its corridor point; its homes can lie kilometres
  from any road, so its cars start with a straight line (setup prints how many) and its speeds mean
  nothing. Without road files its roads are free-flow. A folder without any plans file gets demo
  plans (every commuter drives, leaving 06:45 to 08:00); a run folder that lacks one day's plans
  gives a message instead. A folder without `scenario.csv` is charged from day 11 (the
  `config.toml` value) and has no known last day, so `go` plays on. The synthetic
  `netlogo7/demo_scenario/` folder was removed on 2026-10-09; nothing read it.
- **Checks.** `scripts/check_netlogo_equivalence.py` compares NetLogoEngine with PyEngine on random
  and edge-case plans, with synthetic congested roads, motorway breakdown, per-site time profiles and
  capacity drops and the real road files (and exercises the GUI, including the three `charge-on`
  choices and the pens of the LoS and mean V/C plots). The scripts open a folder with `setup-run "<path>"` (what `setup` does with the chosen
  run), because the `experiment` chooser accepts only the experiments it lists. `$PY scripts/check_network_model.py
  [--days 1 11] [--views DIR] [--view-times HH:MM ...]` (own process, `--netlogo-home` overrides
  `[engine] netlogo_home`) checks the network counts, every gate and workplace, how far the legs
  from the gate run outside the cordon, that every car's depart, gate-arrive, gate-exit and arrive
  minute equals the run's `outcomes.csv`, that each car's drive follows its section times, the
  road colours, the traffic delay monitor, every section's LoS grade, the LoS monitors and plot
  against Python, the tick clock, where queued and driving cars stand and every commuter's place at
  the end of the day, and reports the implied speeds; `tests/test_network_model_netlogo.py` runs it
  under `--run-netlogo` (`CORDONLITE_NETLOGO_HOME` overrides the NetLogo folder). GUI sessions
  started through pynetlogo leave NetLogo autosaves in the user's `.nlogo` folder, which make the
  next GUI start wait on a "Recover Autosave" dialog: remove your own afterwards.

### Running with the real Claude API

The live API has not been called from this machine. Before a full run:

1. Provide a credential: `export ANTHROPIC_API_KEY=...` (never written to a file) or `ant auth
   login`. Without one, the run stops before day 1 with a one-line message.
2. Choose a model and budget. The default model is `claude-opus-5-5` (`[llm] model`);
   `claude-sonnet-5-5` and `claude-haiku-4-5` are allowed. Model choice and cost are the authors'
   decision; run `--estimate` first (950 agents, seed 1: L-clock 2,250 calls and about 2.65M input
   tokens, L-daily 27,300 calls and about 34.1M). Cost all input as uncached: the system prompt is
   below the minimum cacheable prefix and the output schema differs per agent.
3. Start small, for example
   `$PY -m cordonlite.run --arm L-clock --backend anthropic --n-agents 20 --days 12 --seed 1`
   (it prints a capacity warning: 20 agents have no calibration record; fine for a pilot), and read
   `llm_calls.jsonl` and `decisions.csv` before scaling up.

Behaviour of the anthropic backend:

- Transport errors (429, 5xx, connection) are retried by the SDK (`max_retries = 5`). An invalid
  output (unparsable or truncated JSON, a choice that was not offered) is resent once. A refusal
  or another API error goes straight to the rule (`decider = llm-fallback-rule`).
- 401, 402, 403 or 404 errors, or 5 API errors in a row (`llm.max_consecutive_errors`), stop the
  run. Every call is logged as soon as it completes, so a stopped run keeps its log in
  `<name>.failed/llm_calls.jsonl`. `summary.json` reports `llm_fallback_share`.
- Responses are cached on disk (`runs/llm_cache/`), keyed on model, effort, template, prompts,
  schema, `max_tokens` and the fallback setting. A rerun replays the same answers. Agents with
  byte-identical prompts on the same morning are sent once and share the answer (v3 7.5), also
  across arms (L-clock and L-daily share day 1). Set `--set llm.replicate=1` (2, ...) to draw fresh
  samples.

## Outputs

Each run writes `runs/<run folder>/`:

| File | Content |
|---|---|
| `config_snapshot.toml` | effective configuration |
| `personas.csv` | Layer A and B fields per agent, ending with the willingness to pay: `wtt_u` (the uniform draw), `wtt_beta` and `wtp_fee` (NZ$; `inf` with `wtt.beta0 = 0`) |
| `decisions.csv` | agent, day, option, mode, departure, decider (`rule`, `llm`, `llm-fallback-rule`, `standing`, or `forced` when PT was the only option left), triggers, reason, factors, GC of the choice and its GC rank, start time used and early-start flag, and `wtt_removed` / `wtt_all_removed` (car options removed that day by the willingness to pay / all of them) |
| `outcomes.csv` | every agent-day, including PT and WFH: departure, road delay before the gate, gate arrival, gate exit, queue delay, arrival, early/late against the start used, fee, parking, fuel, fare, start time used and early-start flag |
| `profile.csv` | arrivals, served cars and queue length per corridor per minute |
| `road_entries.csv` | commuter entries per road section and minute (`day, section_id, minute, entries`); header only with free-flow roads |
| `road_los.csv` | per road section x period (days 6-10, days 21-30) x hour (06-07, 07-08, 08-09, 09-10 and the 07-09 peak): street, road class, motorway flag, corridor, km, mean and max V/C, mean speed factor, share of minutes at LoS E/F, LoS by V/C, commuter vehicles, usual-traffic V/C, LoS by speed, share at E/F by speed, share congested by AT's definition; header only with free-flow roads |
| `los_summary.csv` | per day x hour x group (motorway, other, all, each corridor): vehicle-km weighted share at LoS E/F by V/C and by speed, AT congested share, mean V/C, mean speed factor, vehicle-km; header only with free-flow roads |
| `llm_calls.jsonl` | every LLM call: prompt, parsed output, error kind, usage, cache hit, shared answer, latency |
| `summary.json` | per day: mode counts, commuters on the early start, cordon entries per 15 min, mean/max queue delay, mean/max road delay, mean car door-to-door time, peak queue delay (per corridor, car-weighted mean and worst corridor), peak queue + road delay (per corridor and car-weighted mean: the calibrated metric), mean fee, revenue, calls by decider type, `wtt_limited` and `wtt_no_car` (commuters with some / every car option removed by the willingness to pay), and for 07:00-09:00 the LoS E/F shares (by V/C, by speed), AT congested shares and mean V/C of motorways and other roads; `meta` holds the run settings, including `fee_peak` (the highest charge, NZ$; runs of the retired charge multiplier also have `fee_scale`) and `wtt` (beta0, beta_clip, vot_ref) with the totals `wtt_limited_days_total` and `wtt_no_car_days_total` |
| `plans.csv` | the plans of every day in one file, written once at the end of the run: `day, agent_id, mode, depart_min` (the NetLogo GUI reads it; the per-day `plans_dayNN.csv` files of earlier runs were merged into it on 2026-10-10) |
| `corridors.csv`, `agents.csv`, `fees.csv`, `scenario.csv` | engine scenario (also used by the NetLogo GUI) |
| `road_sections.csv`, `agent_routes.csv`, `road_profile.csv`, `road_params.csv` | road scenario: the sections this run's agents use, each agent's route, the time profiles, the BPR and motorway breakdown parameters (read by both engines and the GUI; absent with free-flow roads) |

`python -m cordonlite.analysis` writes to `runs/figures/`: `mode_shares.png`,
`crossings_hist.png` (gate exits, day 10 vs day 30), `cordon_entries.png` (with the ToU
schedule), `queue_delay.png`, `road_delay.png` (mean road delay by departure time, days 6-10 vs
21-30), `los.png` (hourly % of traffic at LoS E/F by V/C next to the mean V/C, then E/F by speed
and the AT congested share, motorways and other roads, days 6-10 vs 21-30), `calls_per_day.png`,
`who_adapts.png` (with 95% intervals), `vickrey_check.png`, `summary_table.csv/.md` (with road delay, door-to-door time
and the LoS columns for days 6-10 and 21-30), `twins_summary.csv/.md` (with the traits-off
baseline), `llm_diagnostics.csv/.md` (v3 7.5), and per run `who_adapts_*.csv` and
`twins_day11_*.csv`. `summary_table` also gives the travel share (`travel_share_d10`, `_d30`: car +
PT, the share of commuters who travel into the city centre). `summary_table.md`, `los.png` and
the fee-response outputs carry the same note on reading LoS E/F with the mean V/C ("Level of
Service" above). When the runs folder holds `_peak<NZ$>` runs of the seed analysed, it also writes
`fee_response.csv/.md` (one row per arm and peak charge over days 21-30, peak 0 being the no-charge
run: shares, willingness to pay, car crossings against the peak-0 run of the same days and against
the run's own days 6-10, delays, LoS E/F by speed and by V/C with the mean V/C side by side,
revenue), `fee_response_by_group.csv` (the same shares by archetype and company car) and
`fee_response.png` (six panels against the peak charge); without them it removes stale copies.

Both engines give identical outputs apart from the engine label in `config_snapshot.toml` and
`summary.json` (`--compare` checks this and the file set).

### Results of the canonical mock runs (950 agents; seed 1 unless stated)

The canonical runs were regenerated on 2026-10-09 with the calibrated PAP 22, k_WFH 12 and
beta0 0.15, without SKIP, and the capacity scales 0.430292, 0.396105 and 0.396105 of seeds 1-3. The
day-10 and day-30 shares, road delay, revenue and calls of the seed-1 rows are also in
`runs/figures/summary_table.md`; the crossing changes and the queue + road peak come from each run's
`outcomes.csv` and `summary.json` (`peak_bin_total_delay_wmean`). The `peak_delay` columns of
`summary_table.md` are the gate queue alone (`peak_bin_delay_wmean`), for example 3.8 -> 1.3 min in
R-daily and 4.5 -> 1.9 min in R-clock.

"L" arms use MockLLM, a deterministic stand-in, so these rows test the pipeline; they say nothing
about how a real LLM behaves. Shares are day 10 -> day 30. The crossing change compares the mean
daily car cordon crossings of days 21-30 with days 6-10 (the calibrated response). Peak delay is
the car-weighted mean of corridor peaks of queue + road delay (the calibrated capacity metric).
Road delay is the mean over cars before their gate.

| Arm | Car d10 -> d30 | PT d10 -> d30 | WFH d10 -> d30 | Early start d6-10 -> d21-30 | Car crossings change d21-30 vs d6-10 | Peak delay d10 -> d30 (min) | Road delay d6-10 -> d21-30 (min) | Revenue NZ$ d30 / total | Decider calls |
|---|---|---|---|---|---|---|---|---|---|
| R-daily | 0.851 -> 0.675 | 0.148 -> 0.285 | 0.001 -> 0.040 | 0.064 -> 0.098 | -20.9% | 14.1 -> 9.8 | 6.93 -> 5.58 | 3,089 / 61,182 | 27,300 |
| R-clock | 0.862 -> 0.643 | 0.137 -> 0.298 | 0.001 -> 0.059 | 0.077 -> 0.096 | -25.4% | 15.1 -> 10.6 | 7.13 -> 5.69 | 2,939 / 58,545 | 2,229 |
| L-clock (mock) | 0.813 -> 0.507 | 0.186 -> 0.396 | 0.001 -> 0.097 | 0.060 -> 0.066 | -37.6% | 14.1 -> 10.0 | 7.03 -> 5.27 | 2,278 / 44,656 | 2,250 |
| L-daily (mock) | 0.813 -> 0.542 | 0.186 -> 0.381 | 0.001 -> 0.077 | 0.050 -> 0.072 | -32.2% | 16.5 -> 9.9 | 7.07 -> 5.40 | 2,441 / 47,496 | 27,300 |
| R-clock, traits off | 0.949 -> 0.679 | 0.051 -> 0.291 | 0.000 -> 0.031 | 0.112 -> 0.133 | -28.5% | 19.3 -> 10.6 | 7.54 -> 5.43 | 3,006 / 59,534 | 2,337 |
| L-clock (mock), traits off | 0.861 -> 0.438 | 0.139 -> 0.445 | 0.000 -> 0.117 | 0.057 -> 0.068 | -49.1% | 19.5 -> 9.8 | 7.56 -> 4.57 | 1,889 / 36,870 | 2,305 |
| R-daily, seed 2 | 0.856 -> 0.661 | 0.143 -> 0.289 | 0.001 -> 0.049 | 0.089 -> 0.096 | -23.1% | 15.1 -> 10.3 | 7.49 -> 6.06 | 3,059 / 60,038 | 27,500 |
| R-clock, seed 2 | 0.865 -> 0.633 | 0.134 -> 0.302 | 0.001 -> 0.065 | 0.095 -> 0.103 | -26.9% | 17.1 -> 9.7 | 7.68 -> 5.88 | 2,884 / 57,363 | 2,320 |
| R-daily, seed 3 | 0.848 -> 0.681 | 0.151 -> 0.278 | 0.001 -> 0.041 | 0.075 -> 0.090 | -20.4% | 13.2 -> 9.2 | 7.45 -> 6.11 | 3,141 / 61,645 | 27,520 |
| R-clock, seed 3 | 0.863 -> 0.644 | 0.137 -> 0.299 | 0.000 -> 0.057 | 0.077 -> 0.099 | -25.4% | 17.5 -> 9.9 | 7.98 -> 6.17 | 2,988 / 59,270 | 2,243 |

Rows without a seed are seed 1. Every arm has 950 x 30 = 28,500 decisions; "decider calls" leave
out the standing decisions and the forced ones: on every charged day 60 commuters on seed 1 (50 and
49 on seeds 2 and 3) have no car option left and no WFH, so PT is chosen for them without asking a
decider (1,200, 1,000 and 980 forced decisions over days 11-30). The daily arms therefore make
27,300 (27,500, 27,520) decider calls. "Early start" is the share of all commuters whose day is
measured against the 07:00 start, mean of days 6-10 -> mean of days 21-30 (single days are noisy).
The NetLogo R-clock run (seed 1) has the same outputs as the PyEngine run: `--compare` reports
`identical: true` (same file set; decisions, outcomes, profile, road entries, both LoS files,
personas and call log identical; 28,500 outcome rows, of which 20,360 car rows). 46 of the 48 files
are byte-identical; `summary.json` and `config_snapshot.toml` differ only in the engine label.
NetLogo is not at the default path on the machine that made the run, so it was started with
`CORDONLITE_NETLOGO_HOME`, which the run does not record. Single days are noisy; the calibrated
quantities are means over days. In R-daily, the only calibrated arm, the response on seeds 1-3 is
-20.9%, -23.1%, -20.4% (mean -21.4%; seed 2 is 1.1 pp beyond -22%, within the single-seed
tolerance) and the overshoot on days 11-13 -24.4%, -27.1%, -24.2% (mean -25.2%). The clock arms keep
more of their day-11 response than R-daily: on days 21-30 R-clock still has 95-96% of its days 11-13
response (-25.4%, -26.9%, -25.4% against -26.4%, -28.1%, -26.7%), R-daily 84-86%; outside the
disruption days the event-only clock makes 43, 8 and 55 decider calls after day 12 on seeds 1-3 (of
15,200 agent-days). The uncalibrated MockLLM arms weight the fee 1.5 times, which says nothing about
a real LLM (L-clock -37.6%, L-daily -32.2%). Traits off strengthens the response in both deciders
(R-clock -28.5% against -25.4%, L-clock (mock) -49.1% against -37.6%). Road delay before the gate
falls with the charge: the mean road delay of a car goes from 6.93 to 5.58 min in R-daily and from
7.13 to 5.69 min in R-clock (days 6-10 -> 21-30). In R-daily the share of 07:00-09:00 vehicle-km at
LoS E/F by speed goes from 79.8% to 77.6% on motorways and from 5.2% to 4.1% on other roads (AT
congested share of other roads 13.7% to 9.9%), while by V/C it barely moves (94.4% to 94.1% on
motorways, mean V/C 0.920 to 0.897; 99.6% to 99.6% on other roads, mean V/C 1.410 to 1.388; see
"Level of Service" for why). No car is left unserved at the gate in any of these runs. Estimated LLM
input (MockLLM run, characters / 4, approximate): L-clock 2,250 calls, about 2.65M tokens; L-daily
27,300 calls, about 34.1M tokens. The runs of the previous state (PAP 22 / k_WFH 9, SKIP at NZ$30, no
willingness to travel) are in git history (commit 75d8feb), the 300-agent free-flow runs before them
too (commit 55a1dbb). Earlier runs are kept locally (not in git) in `runs_skip25_noearly/` (SKIP cost
NZ$25, no early start), `runs_fuel023_park11/` (fuel NZ$0.23/km, parking NZ$11, PAP 12),
`runs_pre_fuel/` (before the fuel cost) and `runs_pre_recalibration/`.

**Periodic review (T7) sensitivity**, rule decider, car crossings against days 6-10 and decider
calls (`runs/R-clock_mock_py_s<seed>_review<N>`; every run also has the 1,200, 1,000 or 980 forced
decisions of its seed):

| Seed | Arm | d21-30 | d11-13 | Decider calls |
|---|---|---|---|---|
| 1 | R-daily | -20.9% | -24.4% | 27,300 |
| 1 | R-clock (event only) | -25.4% | -26.4% | 2,229 |
| 1 | review every 10 days | -22.3% | -26.4% | 3,041 |
| 1 | review every 5 days | -20.8% | -25.1% | 5,766 |
| 2 | R-daily | -23.1% | -27.1% | 27,500 |
| 2 | R-clock (event only) | -26.9% | -28.1% | 2,320 |
| 2 | review every 10 days | -24.6% | -28.1% | 3,155 |
| 2 | review every 5 days | -23.4% | -27.2% | 5,894 |
| 3 | R-daily | -20.4% | -24.2% | 27,520 |
| 3 | R-clock (event only) | -25.4% | -26.7% | 2,243 |
| 3 | review every 10 days | -22.7% | -26.7% | 3,098 |
| 3 | review every 5 days | -21.5% | -25.2% | 5,849 |

Twins (95 pairs that share Layer A, seed 1, `twins_summary.md`): the number of pairs choosing a
different option on day 11 (day 30) is 40 (38) in R-daily, 39 (40) in R-clock, 45 (45) in L-clock
(mock) and 39 (41) in L-daily (mock). With traits off, which leaves only history to separate the
twins, it falls to 6 (6) in R-clock and 21 (22) in L-clock (mock).

### Charge levels (2026-10-09)

At the usual schedule (peak NZ$6) the charge removes 21-38% of the car crossings, but motorway
congestion barely changes, so the authors asked for runs at other charge levels. `fees.peak_fee`
(`--peak-fee NZ$`) scales the time-of-use schedule to the given peak (6 is the SSC2026 schedule;
NZ$12, 18 and 30 are 2, 3 and 5 times it); the hours, the charge day (11) and everything else stay
as in the canonical runs. The runs use peaks of NZ$0, 3 (AT's modelled NZ$3 and the 2026
consultation's NZ$3-4), 12, 18 and 30 (about London's daily charge) for the four arms on seed 1
(`runs/<arm>_mock_py_s1_peak<NZ$>`; commands in "How to run", step 3b). Peak 0 levies no charge at
all (the same run as `--regime none`) and is the counterfactual: each charge level is compared with
the peak-0 run of the same arm on the same days 21-30, so only the charge differs. Days 1-10 of every
peak run equal the peak-0 run's (`same_before_charge_as_peak0` in `fee_response.csv`). This replaced
the same day's charge multiplier (`fees.scale`, runs `_fx2`, `_fx3`, `_fx5`), whose runs were
compared with their own days 6-10 (that change is still a column,
`car_crossings_change_vs_own_d6_10_pct`).

A commuter who will not pay the charge has fewer car options (the willingness to pay, "Options"
above) and drives at a cheaper time, takes PT or works from home; only hybrid office workers can work
from home. Company-car holders (126 of 950 on seed 1) perceive no charge and keep every car option at
any level, because their employer pays it, and the 149 trades must drive (no PT or WFH; 104 of them
have a company car).

R-daily, the calibrated arm, days 21-30 (`runs/figures/fee_response.md` has all four arms and every
column, `fee_response.png` plots them). "WTP < peak" is the share of commuters whose willingness to
pay is below the peak, exempt ones included; "no car" the share of commuter-days with every car
option removed. LoS and V/C are of the 07:00-09:00 vehicle-km; E/F by V/C and the mean V/C are shown
side by side. Delays in minutes; revenue NZ$ a day.

| Peak NZ$ | Car | PT | WFH | Travel (car + PT) | WTP < peak | No car | Car crossings vs peak 0 | Road delay | Peak gate queue | Peak queue + road | Motorways E/F by speed | Motorways E/F by V/C | Motorways mean V/C | Other roads E/F by speed | Other roads E/F by V/C | Other roads mean V/C | Other roads AT congested | Revenue |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.858 | 0.141 | 0.001 | 0.999 | 0.0% | 0.0% | 0 | 7.04 | 3.80 | 14.24 | 79.5% | 94.5% | 0.920 | 5.6% | 99.6% | 1.413 | 14.2% | 0 |
| 3 | 0.784 | 0.208 | 0.008 | 0.992 | 8.6% | 4.3% | -8.5% | 6.27 | 1.16 | 10.32 | 78.8% | 94.4% | 0.908 | 4.6% | 99.6% | 1.401 | 11.9% | 1,861 |
| 6 | 0.675 | 0.287 | 0.037 | 0.963 | 14.4% | 8.6% | -21.2% | 5.58 | 1.08 | 9.91 | 77.6% | 94.1% | 0.897 | 4.1% | 99.6% | 1.388 | 9.9% | 3,088 |
| 12 | 0.497 | 0.377 | 0.127 | 0.873 | 24.4% | 14.4% | -42.1% | 5.03 | 1.05 | 10.50 | 76.7% | 93.8% | 0.884 | 3.8% | 99.5% | 1.373 | 8.0% | 4,272 |
| 18 | 0.378 | 0.458 | 0.165 | 0.835 | 34.4% | 20.1% | -56.0% | 4.72 | 0.78 | 11.50 | 76.3% | 93.3% | 0.877 | 3.6% | 99.5% | 1.368 | 7.6% | 4,789 |
| 30 | 0.267 | 0.546 | 0.187 | 0.813 | 44.3% | 29.5% | -68.8% | 4.64 | 0.37 | 10.10 | 76.2% | 92.3% | 0.871 | 3.5% | 99.4% | 1.363 | 7.3% | 5,675 |

Car crossings against the peak-0 run of the same days, all four arms:

| Peak NZ$ | R-daily | R-clock | L-clock (mock) | L-daily (mock) |
|---|---|---|---|---|
| 3 | -8.5% | -9.6% | -18.8% | -14.6% |
| 6 | -21.2% | -25.8% | -38.0% | -32.1% |
| 12 | -42.1% | -47.9% | -61.4% | -55.1% |
| 18 | -56.0% | -61.4% | -71.0% | -66.9% |
| 30 | -68.8% | -73.3% | -77.2% | -76.2% |

How to read them (four arms unless stated):

- **What falls.** Car use: the car share goes from 0.81-0.87 without a charge to 0.51-0.68 at NZ$6
  and 0.19-0.27 at NZ$30, the travel share from 0.999 to 0.90-0.96 and 0.81-0.84. The share with a
  WTP below the peak is the same in every arm (a property of the personas): 8.6%, 14.4%, 24.4%,
  34.4% and 44.3% at NZ$3, 6, 12, 18 and 30, and 4.3% to 29.5% of commuter-days have no car option
  left. The mean road delay of a car falls from 6.99-7.16 min to 5.27-5.69 (NZ$6) and 4.64-5.02 min
  (NZ$30), the peak gate queue from 3.07-4.48 to 0.95-1.86 and 0.34-0.54 min, the other-road traffic
  at LoS E/F by speed from 5.4-5.6% to 3.8-4.1% and 3.5%, and its AT congested share from 13.6-14.2%
  to 8.8-9.9% and 6.8-7.3%.
- **What hardly falls.** Motorway LoS E/F by speed goes only from 79.5-80.0% to 76.0-76.2% at
  NZ$30; by V/C it goes from 93.7-94.8% to 91.4-92.3% (mean V/C 0.916-0.920 to 0.866-0.871), and on
  other roads it stays at 99.3-99.7% at every level (mean V/C 1.409-1.413 to 1.359-1.363). The peak
  15-min queue + road delay falls from 13.55-15.10 min to about 10 min at NZ$3 and then stays at
  9.66-11.50 min: most of it is road delay in the worst bin, which background traffic dominates.
- **Why.** Motorway LoS is pinned by the fixed usual breakdown windows: about 76% of the motorway
  vehicle-km lies inside them and is graded F, by V/C and by speed, whatever the flow; the windows
  come from the NZTA counts, which fewer commuter cars cannot shorten (they can only prevent the
  breakdowns that today's traffic starts). The other-road V/C grade is pinned by the capacity
  scale: capacity is k x ADT with k = 0.077 fitted to the TomTom index, not a lane capacity, so
  usual V/C is about 1.2-1.6 in the peak and almost all traffic is E/F by V/C at any level; the mean
  V/C beside it, the speed grade and the AT share do move. And the commuters are a small part of
  the traffic: weighted by vehicle-km they are about 5.6% of the counted peak-hour traffic on the
  motorway sections of their routes and 2.9% on the other sections (`phi` in
  `data/road_sections.csv`; the 16% under "Road congestion" weights each section by the commuters'
  own minutes on it).
- **Who responds.** The 171 exempt commuters (company cars and trades) drive on at least 99.6% of
  their days at every level in every arm, although 76 of them have a WTP below NZ$30. WFH levels off
  at 0.16-0.19: only the 303 hybrid office workers can work from home, and they do on 50-59% of their
  days at NZ$30. Everyone else (779 commuters) at NZ$30: car 0.01-0.11, PT 0.67-0.79, WFH 0.20-0.23,
  travel 0.77-0.80; 35.9% of their commuter-days have no car option.
- **Against the trend, not explained.** In both L arms the mean road delay of the remaining cars
  rises from NZ$18 to NZ$30 (4.52 to 4.91 min in L-clock, 4.63 to 5.02 in L-daily), probably because
  the cars left are mostly trades and company cars on other routes and at other times (not checked).
  L-clock's peak gate queue rises from NZ$3 to NZ$6 (0.93 to 1.62 min), and its WFH share dips from
  NZ$18 to NZ$30 (0.166 to 0.163).
- **Extrapolation.** Behaviour is calibrated at the NZ$6 peak (PAP 22, k_WFH 12, beta0 0.15 on
  R-daily), so nothing anchors the response at NZ$3 or NZ$12-30, and the willingness to pay makes it
  steep by construction (the share willing to pay falls exponentially). The L rows are MockLLM, a
  pipeline check. One seed.

## Further reading

- `docs/example_prompt.md`: one complete request as the LLM sees it (made by
  `scripts/make_example_prompt.py` from a logged call; template `cl-v3`, the canonical L-clock run,
  agent 0, day 11, trigger T2: 5,267 characters, about 1,317 tokens; agent 0 has a company car, so
  the example has no willingness-to-pay sentence). The script loads the run's `config_snapshot.toml`;
  `load_config` also loads the snapshot of an older run (missing keys of `config._ADDED_KEYS` and
  the `[wtt]` section take their defaults, retired keys are dropped, `fees.peak_fee` is derived from
  its schedule). The `cl-v2` example of the previous state is archived as
  `docs/figures/skip30_nowtt/example_prompt_skip30_nowtt.md`.
- `data/road_report.md`: the road inputs (sections, count matching, capacity floor, TTI by class and
  corridor, motorway rule, every NZTA site with its window, capacity and drop, the mapping).
  `data/nzta/README.md`: the NZTA files, filters, gaps and licence.
- `INTERFACES.md`: module contracts. `DEVIATIONS.md`: every departure from the specification and
  the v3 note, including the final review fixes. `data/prep_report.md`: network assumptions.
- `scripts/check_netlogo_equivalence.py`: PyEngine vs NetLogoEngine on random plans and road
  scenarios.

## Assumptions

Every parameter is in `config.toml`, with a comment marking it as an assumption `[A]`, as
calibrated `[CAL target=...]` (by `scripts/calibrate_behaviour.py`, to the stated target; three
scalars, PAP, k_WFH and `wtt.beta0`), as a fixed input decided by the authors (paid parking, petrol
price, early start, the peak charge `fees.peak_fee`, the form of the willingness to travel), as data
`[DATA]` (traffic counts, TomTom index), or naming
its source (`[SPEC]`, `[v3]`, `[SSC]`, or `[L]` with a literature reference). The road inputs are in
`[prep]` (counts, peak ratio, inbound share, time profile, TTI target, capacity floor) and `[road]`
(BPR, speed floor, flow window, motorway breakdown). Every departure from the specification or from
the v3 design note is listed in `DEVIATIONS.md`. `data/prep_report.md` and `data/road_report.md`
list the network and road assumptions. `INTERFACES.md` documents the module contracts.

## Limitations

- **Behaviour calibration is to stated targets, on the rule arm only.** The targets are
  assumptions and the Stockholm/Gothenburg anchors are total-traffic reductions over months to
  years, so the match is qualitative. The R-daily response (-21.4%, mean of seeds 1-3; -21.1% on
  unseen seeds 6-12) lies near the centre of the band (-20%). The chosen point (PAP 22, k_WFH 12,
  beta0 0.15) is one of 15 feasible points of 489 at the stated precision (none on unrounded means),
  all at PAP 22 on a ridge in k_WFH and beta0; the anchors, not the targets, pick the point on it.
  Seeds 1 and 2 have base car 0.853 and 0.859 and seed 2 a response of -23.1%, outside their bands
  but within the single-seed tolerance. Out of sample base car runs high: 0.863 on the unseen seeds
  6-12 and 0.859 over seeds 1-12, both above the band at the stated precision.
- **NZTA counts measure throughput, not demand.** They show when a motorway breaks down and
  recovers, its pre-breakdown capacity and its discharge after breakdown (capacity drop 6-26%), but
  not how much demand queues behind the bottleneck. In the model broken-down flow is capped at 45%
  of free-flow speed (`road.mwy_jam_speed`), and the measured drop sets the speed only above V/C
  1.24 to 1.59 (at a drop of 26% and 6%); in a 30-day 950-agent check run (2026-10-08) it did so in
  155 of 324,174 broken-down NZTA section-minutes. The NZTA data decide **when** motorways jam, not
  **how badly**. A count that stays flat until 10:45 cannot tell "still jammed" from "demand happens
  to equal that level" (Northcote, Newmarket, Greenlane, Mt Wellington), so those stretches stay
  broken down to 11:00, and the Northcote stretch stays purple after both its upstream neighbour
  (Tristram) and the Harbour Bridge have cleared.
- **The charge cannot shorten a usual breakdown window.** Windows come from the counts; fewer
  commuter cars only prevent the breakdowns that today's traffic starts. The dynamic trigger has
  no hysteresis, and speed jumps at the window edges. Where a site shows no breakdown (SH20, the
  Northwestern city end) capacity is the highest counted flow, a lower bound, so jams there depend
  on run-to-run noise around V/C 1. Motorways without a count site (Upper Harbour, George Bolt
  Memorial Drive, Airport) keep a window from usual V/C (07:08-10:01).
- **Usual-traffic level.** The TomTom TTI 1.714 is matched on the non-motorway part of the trips
  only; the motorway level (usual TTI 2.03 at 08:00-08:59) follows from the breakdown rule and the
  NZTA timing and is not matched to a measured motorway index (none is published per corridor).
  Simulated uncharged days are above the usual-traffic TTI (TTI of the commuters' own trips,
  departures 08:00-08:59, days 6-10, time over free-flow time summed over the cars: 1.973 on the
  non-motorway part and 2.179 on motorways in the canonical R-clock run, against 1.714 and 2.032
  under usual traffic; 1.953 to 2.114 and 2.174 to 2.197 over R-daily and R-clock, seeds 1-3),
  because the commuters bunch in time and on the approaches near the gates more than the netting of
  the counts assumes.
- **Capacity from k x ADT is circular.** SSC2026's rule makes usual V/C the same (1.50 x the time
  profile) on every section with the default peak ratio, no NZTA site and no floor; spatial
  variation comes only from the
  AM peak ratios of the counts (8.5% of the minutes), the capacity floor, the commuters and the NZTA
  sites. With k calibrated to TomTom's TTI, usual V/C on arterials is about 1.2-1.6 at the peak, so
  LoS by V/C is E/F on almost every arterial and barely moves with the charge; LoS by speed and the
  AT share move. A motorway that is not broken down has V/C below 1 and speed above 87% of free
  flow, so motorway speed grades are effectively A or F, and many motorway F grades come with V/C
  below 1 (the counted flow during breakdown is the reduced discharge). The speed bands are HCM's
  urban-street bands, also applied to motorways, and AT's "congested" is defined against the posted
  limit, here against free-flow speed.
- **Routing is undirected and fixed.** Routes are the prep shortest free-flow paths on the
  undirected graph (no rerouting, no one-way information, one destination node); 43% of motorway
  traversals follow the opposite carriageway's geometry. Congestion uses the inbound flow at that
  location, so the numbers do not depend on which carriageway is drawn. With the first-entry gate
  rule, 834 origins (28%) first touch the cordon at the SH1 Wellesley Street off-ramp (723), The
  Strand or Parnell Rise, run outside for under 1.2 min and re-enter at Alten Road. The first-entry
  rule assigns them to their first touch, so the South (Wellesley Street ramp) corridor, which is
  also the day-20 disruption corridor, includes these undirected-graph paths (288 of the 950 seed-1
  agents use them, including all 257 South-corridor and all 16 East-corridor agents). The 834
  origins of Alten Road gate 2 are single-entry paths from the south-east (the equal count is a
  coincidence). Free-flow times do not depend on the gate, and the fee minute moves by under 1 min
  (`data/prep_report.md`, DEVIATIONS.md Prep 4).
- **Not congested: the leg after the gate and PT.** Inside the cordon the gate queue stands for the
  congestion; PT time is fixed (rail and busway assumption), so road congestion does not slow buses.
- **Count data.** AT/NZTA ADT counts are 7-day averages of mixed vintage (state-highway records
  mostly 2016); the default time profile's shape is assumed; NZTA profiles are 2024 weekday means
  scaled to 2025-26 daily volumes. AM peak ratios come from a count on 8.5% of the minutes, the rest
  use 0.096. The road-class capacity floor also raises six motorway ramps (Exit 4A Northern
  Motorway by 39%).
- **Capacity calibration.** It targets the car-weighted mean of corridor peaks of queue + road
  delay per seed (15 min, a user decision re-confirmed after the motorway breakdown rule). Most of
  that is road delay, so the gate queue that the clock and the prompt report is short on most
  corridors. At the calibrated scales (days 6-10, seeds 1-3) the corridor peaks of queue + road
  delay range from 8.3 to 26.7 min and those of the gate queue alone from 0.4 to 20.1 min; the
  highest are South-west on seed 2 (26.7 min, queue alone 20.1) and West on seed 1 (21.8 min, queue
  alone 12.4).
- **The early start is an assumption.** The permission probabilities (0.8, 0.5, 0, 0.5, 0), the
  07:00 start and the cost of NZ$3 x phi(F) have no empirical source. About 48% of commuters may
  start early. In R-daily (mean of seeds 1-3) 7.6% of all commuters do so on days 6-10 and 9.5% on
  days 21-30, against 6.9% in the run without the charge. The result depends on the assumed cost:
  at NZ$1.5 x phi(F) the share is 14.0% before and 17.0% after the charge, at NZ$6 x phi(F) the
  option is almost unused (1.8%, then 1.4%). The LLM is told the permission but not this cost.
  Without the early start the response is -22.8% and seed 2 reaches -24.3%, beyond the tolerance
  (`docs/calibration_report.md`, "Sensitivity to the fixed assumptions").
- **PAP is a fitted residual.** With parking and fuel fixed, PAP alone holds the assumed baseline
  split (22, up from 20 with 300 agents and free-flow roads; v3 PAP 22-44 in v3's form, against
  v3's NZ$8). Commuters with P = 1-2 practically never ride PT before the charge. k_WFH (12) and
  beta0 (0.15) are identified together by the response and overshoot rather than by the WFH share
  (0.001 before the charge): a higher k_WFH weakens the response about as much as a higher beta0
  strengthens it; a realistic hybrid-work WFH baseline would need v3's WFH quota (not implemented).
- **Fixed inputs are not validated.** The petrol price (NZ$3.30/L, October 2026) is author-supplied
  and was not verified here; the MBIE series gave NZ$2.97/L for September 2026 (NZ$0.27/km). The
  parking rate is a 2014 casual all-day rate. Base years are mixed (2026 fuel, 2025 fare and charge,
  2024-26 motorway counts, 2014 parking, mostly 2016 state-highway ADT). Every driver without an
  employer vehicle pays petrol at 9.0 L/100 km; electric vehicles and other running costs are not
  represented.
- **Rule and LLM see the same Layer A, but not the same WFH accounting.** The LLM deciders are not
  tuned, yet the parking cost and the fuel cost are stated in the prompt, and the willingness to pay
  removes the same car options in every arm (a constraint, so a live LLM cannot choose to pay more
  than it). The rule's
  WFH earns no parking, fuel or commute credit (v3 zero-fee form), whereas a real LLM told that
  parking costs NZ$17 and fuel about NZ$9 a day will likely count both as a WFH saving, so
  live-LLM WFH shares are not comparable with R-daily on that margin.
- **Lock-in under the clock.** The reference fee follows the fee faced, so the loss term fades
  for everyone, but under the clock only woken agents can act on it, and few triggers fire after
  day 12 apart from the PT disruption (43, 8 and 55 decider calls on seeds 1-3 outside days 20-21).
  The clock arms therefore keep more of the day-11 response: R-clock 0.862 -> 0.643 car share
  against R-daily 0.851 -> 0.675 (seed 1), and on days 21-30 -25.4%, -26.9%, -25.4% against
  -20.9%, -23.1%, -20.4% (seeds 1-3), beyond the -22% band on every seed (the band is calibrated
  on R-daily only). A periodic review (T7, off by default) is the sensitivity: a review every 10
  days gives -22.3%, -24.6%, -22.7% with 3,041-3,155 decider calls, every 5 days -20.8%, -23.4%,
  -21.5% with 5,766-5,894, against 27,300-27,520 in R-daily.
- **Trait effects follow the assumed mapping.** S, F, H and P act through the cost parameters they
  are mapped to. In the population manipulations of the 950-agent search (every agent at one
  level, seeds 1-3) S acts monotonically (days 21-30 -19.2% to -22.5%, days 11-13 -17.1% to -32.8%
  for S = 1-5). The response grows with F from -17.8% to -33.9%, mainly because F = 4-5 hybrid
  workers switch to daily WFH, which is unbounded without v3's quota (WFH share about 0.17 at F = 5
  on days 21-30). H damps only the days 11-13 response, at H = 4-5 (-25.2%, -23.0% against -26.5% to
  -27.4%), and not the long-run one. The charge-induced switch to PT is largest at P = 3 (+0.197),
  because P = 4-5 agents with viable PT already ride it and P = 1-2 agents never do. Treat trait
  patterns as properties of the mapping, not findings (`docs/calibration_report.md`, "Trait
  monotonicity").
- **Day-1 lateness.** On day 1 commuters know usual traffic but not the gate queue: 27.5% of all
  commuters arrive late in R-daily and R-clock on seed 1 (34.2% and 33.4% on seeds 2 and 3; 23.4%
  in L-clock and L-daily (mock), seed 1).
- **The mock backend is not an LLM.** It re-weights the same cost and adds prompt-seeded noise. It
  tests the plumbing, call counts and reproducibility.
- **The willingness to travel is a fixed threshold.** Each commuter's WTP is drawn once, so the
  same commuters lose the same car options on every charged day (SSC2026 draws entry every day).
  beta is clipped below at 0.1: at beta0 0.15 the floor binds for every commuter with a VoT above
  NZ$14.96/h (28.8% on seed 1), and any positive beta0 removes some car options. Without the limit
  (beta0 = 0) the chosen PAP and k_WFH respond by -14.5%, with SSC2026's beta0 0.5 by -32.3%. Its
  form (no base trip rate, no 0.05-0.95 clip, exemptions instead of an essential-trip draw, VoT_ref
  the distribution median) is an assumption; `DEVIATIONS.md` lists the differences from SSC2026.
- **Charges other than NZ$6 extrapolate.** PAP, k_WFH and beta0 were calibrated at the NZ$6
  schedule, and the runs at NZ$3, 12, 18 and 30 only show what the same model does at other prices;
  the willingness to pay makes the response steep by construction. Not travelling means WFH (hybrid
  office workers only, no quota); nobody moves, changes job or gives up a trip, since SKIP was
  removed. Company-car holders never see the charge (their employer pays it) and trades must drive:
  these 171 of 950 commuters (18%) are exempt from the willingness to pay and drive on at least
  99.6% of their days at any level. Motorway congestion depends little on the commuters (about 5.6%
  of the peak-hour motorway vehicle-km on their routes), and its LoS is pinned by the usual
  breakdown windows ("Charge levels").
- **A sample.** 950 agents (5%; see "950 agents" above for why that is enough); every arm runs on
  seed 1, and the rule arms R-daily and R-clock also on seeds 2 and 3. The East corridor holds
  about 2% of agents and sits at the capacity floor.
- **Not from SSC2026.** SSC2026 had no motorway congestion dynamics (its motorway LoS E/F was a
  measurement that never slowed traffic), so the motorway rule has no precedent in that model; on
  the road side only its count file, BPR form, speed floor, k x ADT capacity rule and LoS bands are
  carried over.

## 한국어 요약

Cordon-Lite는 CUPUM 2027 북챕터를 위한 단순화된 통근 시뮬레이션입니다. 통근자는 평소 습관(standing plan)대로
움직이고, "인지 시계(cognitive clock)"가 의미 있는 사건(첫날, 혼잡통행료 도입, 지각, PT 장애와 그 종료, 지속적인
통행시간 변화, 계획 불가능)이 있을 때만 의사결정자(규칙 또는 LLM)를 깨웁니다. 통근자는 매일 아침 자동차(출발 시각
선택), PT, 재택(WFH) 중 하나를 고르며, 각자 도심으로 운전해 들어가는 데 낼 의향이 있는 최대 금액(지불 의향)이 있어
요금이 오를수록 지불 의향이 있는 비율이 지수적으로 줄어듭니다. 이 문서는 2026-10-09 상태(도로 혼잡, NZTA 기반 고속도로
정체, 950명, LoS 출력, SKIP 제거, 통행 의향, 최고 요금 설정)를 설명하며, 행동 보정(PAP 22, k_WFH 12, beta0 0.15), 용량
보정, 표준 run은 이 상태에서 2026-10-09에 다시 만들었습니다.

- **수요와 도로:** TomTom 도로망은 Python에서 오프라인으로만 사용해 도시 전체 출발지 3,000곳의 최단경로, 코든
  진입 게이트, 자유통행시간을 계산합니다. 도로는 양쪽 엔진 모두에서 혼잡합니다(사용자 결정 2026-10-07). 게이트까지의
  경로를 도로 구간 5,903개로 나누고, 각 구간에는 매 분 교통량 측정값(SSC2026의 AT/NZTA ADT)에서 온 배경 교통과
  지난 15분 동안 들어온 통근자 차량(에이전트 하나 = 20대)이 실립니다. 속도는 BPR(0.15, 4, 하한 0.18)을 따르고,
  용량은 k x 방향별 ADT(도로 등급별 5백분위 하한)입니다. k = 0.076999는 평소 교통에서 08:00-08:59 출발의 비고속도로
  구간 TTI가 TomTom 2025 오클랜드 출근 혼잡 지수 1.714가 되도록 맞췄습니다. 게이트에서는 5개 corridor의 Vickrey
  점대기행렬이 있고, 게이트 이후 구간은 자유통행입니다.
- **고속도로 정체(2026-10-08):** 고속도로 본선 구간은 정체 시간대 안에서, 또는 그날 교통량으로 V/C가 1에 도달하면
  정체(stop-and-go) 상태가 되어 용량이 줄고(측정값 6-26%, 없으면 10%) 속도가 자유통행의 45% 이하가 됩니다. 정체
  시간대, 용량, 시간 분포, 용량 감소는 NZTA TMS 측정값(2024년 15분 자료와 2025-26 일 교통량, 사용자 결정, CC BY
  4.0)에서 가장 가까운 같은 고속도로 지점의 값을 씁니다: Harbour Bridge 06:15-09:30, Northern(Albany-Tristram)
  06:45-09:30, Northcote 부근 06:45-11:00, Southern(도심-Mt Wellington) 06:45-07:15부터 11:00까지, Mt Wellington
  남쪽 07:15-09:45, Northwestern 06:30-07:15부터 09:30-09:45까지. SH20과 Northwestern 도심 끝은 측정상 정체가 없어
  그날 교통량이 찰 때만 정체합니다. SSC2026은 고속도로를 실제로 느리게 한 적이 없습니다(LoS E/F는 측정용).
- **950명(5% 표본, 사용자 결정 2026-10-08):** 19,000대의 5%이며 쌍둥이 95명(10%)을 포함합니다. 근거: 19,000명
  전수 run과 비교해 차량 분담률, 도로 지연, TTI가 약 1-2% 이내로 수렴하고, 시드 간 반응 표준편차가 300명 1.9 pp에서
  950명 1.1 pp로 줄며, 문헌(Ben-Dor, Ben-Elia & Benenson 2021, doi:10.1016/j.simpat.2020.102233; Mersini &
  Ziemke 2025, MATSim User Meeting paper 30; MATSim의 10% 관행)의 기준은 모든 혼잡이 에이전트에서 오는 경우인데
  Cordon-Lite는 도로 교통의 대부분이 측정값 배경이고(통근자는 약 16%) 게이트 용량을 n마다 보정합니다. LLM 비용은
  n에 비례합니다(950명, 시드 1, MockLLM 추정: L-daily 27,300회·입력 약 3,415만 토큰, L-clock 2,250회·약 265만 토큰).
- **SKIP 제거(2026-10-09, 저자 결정):** 하루 연기(SKIP)는 하루짜리 연기가 아니라 영구적인 선택이 되어 있었습니다
  (NZ$30 최고 요금에서 R-clock의 SKIP 이용자 102명 중 97명이 21-30일 매일 SKIP, NZ$6에서도 8명이 매일 SKIP; 규칙
  실험군에서는 모두 PT를 탈 수 있었음). 이제 선택지는 자동차(출발 시각), PT(가능한 경우), 재택(가능한 경우)뿐이고,
  이동하지 않는다는 것은 재택(하이브리드 사무직만)을 뜻합니다. 프롬프트 템플릿은 `cl-v3`입니다.
- **통행 의향(지수 감소, 2026-10-09, 저자 결정):** SSC2026 모형의 지수 감소를 따르되, 통근자마다 한 번 뽑은
  u ~ U(0,1)로 고정된 문턱을 씁니다: beta = clip(beta0 x VoT_ref / VoT, 0.1, 2.0), WTP = -ln(u) x VoT / beta
  (NZ$, VoT_ref = exp(vot_mu) = NZ$9.97/h, 분포의 중앙값; SSC2026은 표본 중앙값). 그러면 요금 F를 낼 의향이 있는
  비율은 exp(-beta F / VoT)입니다. 요금이 부과되는 날, 예상 통과 시각의 요금이 WTP보다 높은 자동차 선택지는 빠지고
  (더 싼 시간대 출발은 남음), 모두 빠지면 PT나 재택을 고르며 PT만 남으면 "forced"(의사결정자 호출 없음)입니다.
  회사 차량(고용주가 요금 부담)과 PT·재택이 모두 불가능한 통근자(trades)는 예외입니다. 모든 실험군(규칙, MockLLM,
  LLM)에 같은 선택지 제약으로 적용되고, 무요금 날에는 아무것도 빠지지 않으며, beta0 = 0이면 꺼집니다. 시드 1에서
  WTP가 NZ$6 미만인 통근자는 14.4%, NZ$30 미만은 44.3%입니다. SSC2026과의 차이(매일 추첨 대신 고정 문턱, 기본
  통행률 없음, 0.05-0.95 절단 없음, 필수 통행 추첨 대신 구조적 예외)는 DEVIATIONS.md에 있습니다.
- **에이전트가 아는 것:** 각 차량 선택지에는 그 출발 시각의 경로 도로 지연이 포함됩니다(첫날은 평소 교통, 둘째 날부터는
  어제의 실제 교통). LLM 프롬프트(`cl-v3`)에는 출발 시각별 도로 지연과 대기열, 선택지·기억 표의 "traffic delay" 열이
  있고, 지불 의향 때문에 자동차 선택지가 빠진 날에만 그 사실을 알려 줍니다. PT는 도로 혼잡의 영향을 받지 않습니다
  (철도·버스전용로 가정).
- **엔진:** Python(PyEngine)과 NetLogo 7.0.4(NetLogoEngine)는 도로 주행(`simulate_roads` = `road-arrivals`)과
  게이트 대기열을 같은 연산 순서로 계산하며, 결과는 엔진 표시를 제외하면 바이트 단위로 같습니다. 표준 NetLogo
  R-clock run은 NetLogo가 기본 경로에 없어 환경 변수 `CORDONLITE_NETLOGO_HOME`으로 경로를 알려 주고 만들었습니다.
  이 변수는 run에 기록되지 않으므로 `--compare`가 `identical: true`를 보고합니다(outcomes 28,500행, 그중 차량
  20,360행; 48개 파일 중 46개가 바이트 단위로 같고 `summary.json`과 `config_snapshot.toml`은 엔진 표시만 다릅니다).
- **용량 보정:** R-daily 무요금 6-10일에 corridor별 15분 최대 평균 지연(게이트 대기 + 도로 지연)의 차량 가중 평균이
  15분이 되도록 시드별로 맞춥니다(사용자가 고속도로 규칙 추가 후 재확인). 이제 대부분이 도로 지연이고 게이트 대기는
  대부분의 corridor에서 몇 분입니다. 선택된 값에서 시드 1-3의 척도는 0.430292, 0.396105, 0.396105이고(달성값 13.57,
  16.52, 14.51분), 최대 구간 지연의 67-78%가 도로 지연입니다. 보정 run에는 요금이 없으므로 beta0와 무관합니다.
  `calibrate --seeds 1 2 3`은 시드를 병렬로 돌립니다(`--jobs`).
- **행동 보정:** 규칙 의사결정자(R-daily, 시드 1-3)만 보정합니다. 구조 수정 후 PAP, k_WFH, beta0 세 스칼라를 단계별
  격자로 탐색하며(용량 보정 171회, 요금 run 1,638회, 14 workers에서 약 2.3시간), 주차비·연료비·조기 출근·에이전트
  수·도로 설정은 고정입니다. 시드별 허용오차는 sqrt(300/n)로 줄어 950명에서 비율 ±0.028, 반응 ±2.2 pp입니다. 선택은
  PAP 22, k_WFH 12, beta0 0.15입니다(이전: PAP 22, k_WFH 9, 통행 의향 없음). 표기 정밀도로 조건을 만족하는 점은
  489개 중 15개로 모두 PAP 22이며, k_WFH 10 / beta0 0.05에서 k_WFH 14 / beta0 0.25까지 이어지는 능선 위에 있고, 앵커에
  가장 가까운 점이 선택되었습니다. R-daily 시드 1-3 평균은 요금 전 차량 0.854, PT 0.145, 재택 0.001, 21-30일 반응
  -21.4%, 11-13일 -25.2%입니다. 보정에 쓰지 않은 시드 6-12는 반응 -21.1%이지만 요금 전 차량 평균이 0.863으로 표기
  정밀도에서 범위(0.85)를 넘습니다(시드 1-12 평균 0.859). 통행 의향이 없으면(beta0 = 0) 반응은 -14.5%, SSC2026의
  beta0 0.5이면 -32.3%입니다. 이전 상태는 `skip30_nowtt`로 보관했습니다.
- **표준 run 결과(950명, mock 백엔드, 따로 적지 않으면 시드 1):** 21-30일 차량 코든 통과는 6-10일 대비 R-daily -20.9%,
  R-clock -25.4%, L-clock(mock) -37.6%, L-daily(mock) -32.2% 변합니다. 의사결정자 호출은 R-daily 27,300회,
  R-clock 2,229회이고, 요금 부과일마다 60명은 PT만 남아 forced로 처리됩니다. 시드 1-3에서 R-clock은 11-13일 반응의
  95-96%를 21-30일까지 유지하고(R-daily 84-86%), 모두 -22% 범위를 넘습니다(-25.4%, -26.9%, -25.4%; 범위는 R-daily에만
  보정). 10일마다 재검토(T7)하면 -22.3%, -24.6%, -22.7%가 됩니다. 요금 후 차량의 평균 도로 지연은 R-daily에서
  6.93분에서 5.58분으로 줄고, 07:00-09:00 속도 기준 LoS E/F 비율은 고속도로 79.8% → 77.6%, 기타 도로 5.2% → 4.1%입니다
  (V/C 기준은 거의 그대로이며 평균 V/C를 함께 봅니다). L 결과는 MockLLM의 것이며 실제 LLM에 대해서는 아무것도 말하지
  않습니다.
- **LoS 출력:** SSC2026과 같은 V/C 기준 LoS(HCM 1994)에 더해 속도 기준 LoS(HCM 2010, 자유통행 대비 속도)와 AT
  혼잡 비율(자유통행의 50% 미만)을 추가했습니다(사용자 결정). V/C 기준 LoS E/F가 나오는 곳(요약표, 요금 반응표와
  그림, `los.png`, NetLogo)에는 평균 V/C를 함께 보여 줍니다(사용자 결정 2026-10-09). V/C 기준 등급은 포화합니다:
  기타 도로의 용량은 TomTom 지수에 맞춘 BPR 척도(k = 0.077 x ADT)이지 차로 용량이 아니어서 07:00부터 교통의 약 99%가
  E/F이고, 고속도로는 차량-km의 약 76%가 고정된 평소 정체 시간대 안에 있어 교통량과 관계없이 F입니다. `road_los.csv`
  (구간별), `los_summary.csv`(일·시간·그룹별), `summary.json` 키, `los.png`에 기록됩니다.
- **요금 수준(2026-10-09, 저자 결정):** 최고 요금은 NZ$ 값 `fees.peak_fee`(`--peak-fee`, 폴더 접미사 `_peak<NZ$>`)로
  정하고 ToU 요금표를 그 최고값에 맞춰 늘리거나 줄입니다(같은 날의 배수 `fees.scale`과 `_fx` run을 대체). 네
  실험군(시드 1)을 최고 NZ$0(무요금), 3(AT 모형의 NZ$3, 2026 협의안 NZ$3-4), 12, 18, 30(런던 일일 요금 수준)으로 돌렸고
  (표준은 NZ$6), 요금은 여전히 11일부터 시작합니다. 비교는 같은 실험군의 무요금(peak 0) run과 같은 21-30일로 합니다.
  21-30일 차량 코든 통과는 무요금 대비 NZ$3에서 -8.5%에서 -18.8%, NZ$6에서 -21.2%에서 -38.0%, NZ$30에서 -68.8%에서
  -77.2% 변하고, 통행 비율(자동차 + PT)은 약 0.999에서 NZ$30의 0.81-0.84로 내려갑니다. 반면 고속도로의 속도 기준 LoS
  E/F 비율은 79.5-80.0%에서 76.0-76.2%로만, V/C 기준 기타 도로 E/F는 99.3-99.7%에 머뭅니다(평균 V/C 1.41 → 1.36).
  고속도로 LoS는 고정된 평소 정체 시간대가, 기타 도로의 V/C 등급은 용량 척도가 묶어 두기 때문이고, 통근자는 경로상
  고속도로 첨두 차량-km의 약 5.6%(기타 도로 2.9%)뿐입니다. 회사 차량과 trades(171명)는 예외라 모든 요금 수준에서 거의
  매일 운전합니다. 행동은 NZ$6에서 보정했으므로 다른 요금의 결과는 외삽이며, 지불 의향 때문에 높은 요금의 반응은
  구조적으로 가파릅니다. 결과는 `runs/figures/fee_response.*`에 있습니다.
- **NetLogo 모델:** `netlogo7/cordon_lite.nlogox` 하나입니다. Python은 이를 화면 없이 엔진으로 쓰고, NetLogo에서 열면
  run을 TomTom 도로망 위에서 재생합니다. `experiment` 선택 상자에서 실험(8개: 네 실험군 각각의 요금 NZ$6, NZ$18 run, 모두 10일 중 6일째부터 요금)을 고르고
  setup(약 50초)을 누른 뒤 go를 누르면(1일부터 재생: 1-5일 요금 없음, 6-10일 요금 있음) 모든 통근자가 출근을 마칠 때까지 하루 아침이 진행되고
  멈춥니다(1 tick = 15초). 여러 날을 연속으로 돌리려면 go 전에 keep-going? 스위치를 켜야 하며, go는 run의 마지막
  날 뒤에 멈춥니다. `fee-start-day` 입력과 `netlogo7/demo_scenario/`는 2026-10-09에 없앴습니다(요금 시작일은 각 run의
  `scenario.csv`에 있습니다). 통근자 점은 corridor 색, PT 초록, 재택 회색입니다. 통근자 경로의 도로는 자유통행 대비
  속도로 색칠됩니다: 80% 이상 회색, 60-80% 연노랑, 40-60% 주황, 40% 미만 보라. 보라색 고속도로는 정체(stop-and-go)
  상태입니다. 게이트 대기열의 차량은 빨간색이며 에이전트 하나가 실제 차량 20대(약 70 m)를 나타냅니다. "traffic delay
  (min)"과 LoS 모니터 6개(V/C 기준 E/F, 평균 V/C, 속도 기준 E/F; 고속도로와 기타 도로), "% traffic at LoS E/F" 그래프와
  그 바로 아래 "Mean V/C (1 = at capacity)" 그래프가 있으며 값은 Python 정의와 같습니다. 대기열 그래프 범례는 짧은
  corridor 이름("0: East")을 씁니다.
- **실행:** Setup과 How to run 순서(prep, fetch_nzta(선택), build_roads, calibrate, calibrate_behaviour, run,
  요금 수준 run, analysis)를 따르십시오. 실제 API는 `ANTHROPIC_API_KEY` 또는 `ant auth login` 후 작은 규모부터
  시작하십시오.
- **한계:** NZTA 측정값은 수요가 아니라 처리량이므로 고속도로가 **언제** 막히는지는 정하지만 **얼마나** 막히는지는
  정하지 못합니다(정체 속도는 45% 상한이 정함). 평소 정체 시간대는 요금으로 줄어들지 않습니다. 경로는 무방향 그래프의
  고정 최단경로입니다(고속도로 통과의 43%가 반대 차로 형상). 게이트 이후 구간과 PT는 혼잡하지 않습니다. k x ADT
  용량은 순환적이며(SSC2026 규칙), 요금 전 시뮬레이션 TTI는 평소 교통 TTI보다 높습니다(게이트 근처 통근자 집중;
  08:00-08:59 출발, 6-10일, 표준 R-clock run: 비고속도로 1.973, 고속도로 2.179, 평소 교통 1.714, 2.032). 통행 의향은
  통근자마다 고정된 문턱이어서 같은 통근자가 요금 부과일마다 같은 선택지를 잃고, beta 하한 0.1이 시드 1 통근자의
  28.8%(VoT NZ$14.96/h 초과)에 걸립니다. 주차비, 연료비, 조기 출근, 통행 의향의 형태는 저자가 고정한 가정입니다.
- **주의:** mock 결과는 LLM 결과가 아닙니다.
