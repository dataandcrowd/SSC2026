# Conclusions, as bullets

Calibrated NetLogo model, 14 simulated days, seed 11. Every number traces to
`numbers.md` or `behavioural_extensions.md`.

## The headline

- **The same charge on the same road either works or does nothing, depending on
  a behavioural assumption that is never observed.** Two rules cut peak
  inner-cordon V/C; one changes it by 0.2 %, inside its own day-to-day spread.
- **The action space moves the answer as much as the decision rule does.** With
  the rule, network, demand and fee schedule all held fixed, the predicted ToU
  reduction is 12–26 % for the price rule and 14–39 % for the learner, the range
  coming purely from what responses agents are allowed.
- **The single largest effect in these runs is a modelling assumption, not a
  policy.** Letting routes respond to congestion moves a third of the load off
  the cordon boundary before any charge is applied.

## By decision rule

- **Pay (exponential decay)** — robust. 12, 18, 26 and 23 % across the four
  arms, same sign and rough size everywhere. Responds in full on day 1 and stays
  flat, because the fee sits inside the decision.
- **Learn (Q-learning)** — fragile. 39 % only in the base arm, 14–18 % wherever
  the agent has an alternative to staying home. Never sees the fee when it
  decides, only in the reward, so its response accumulates over the fortnight
  and had not converged by day 14.
- **Oscillate (El Farol)** — inert. Zero in every arm. It reads yesterday's
  congestion, not today's price, and calibrated congestion (0.09–0.17) never
  approaches its comfort threshold (0.6), so the fee never flips a decision. Its
  day-1 deterrence is erased by day 2. Five-seed replication confirms the null.

## What each behavioural option does

- **Departure-time choice changes how many trips are made.** It is the only
  extension that moves the entry rate: Learn 0.34 → 0.62, so its measured
  benefit collapses. Pay's entry rate is unchanged because only 2.7 % of its
  entrants shift.
- **Route choice changes where the trips go, not how many.** Entry rates are
  identical to three decimals; the no-charge baseline moves instead.
- **So**: a result that depends on how many people travel is sensitive to the
  retiming assumption; a result about where congestion appears is sensitive to
  the routing assumption.

## Level of service: motorways against arterials

- **The charge acts on arterials, and barely on motorways.** On the link count
  the arterial share at LoS E or worse falls 6.2 pp under both responsive rules,
  against 1.7 pp on motorways. That is what a cordon charge should do: it prices
  entry to a centre reached by arterial streets, while motorway corridors carry
  through traffic that is never charged.
- **Arterials start worse and stay worse**, 74–80 % at E/F against 58–61 % on
  motorways. Part of that is definitional — an arterial grades E from V/C 0.82
  and a motorway from 0.90 — and part is signalised capacity.
- **The motorway result flips depending on which measure you use.** The
  daily-peak flow-weighted figure looks inert (−1.3 pp for Pay) because the
  daily peak of a rolling-hour average saturates near 92 %. The AM clock-hour
  measure on the very same runs gives −11.5 pp for Pay and −13.6 pp for Learn,
  the largest movements anywhere in these results. **Quote the clock-hour
  measure, which is also the one a traffic engineer would report.**
- **Oscillate does nothing on either class**, +0.7 pp on arterials and −0.6 pp
  on motorways, both inside the noise.

## Displacement

- **The charge does not push traffic outward**, and this now means something.
  Under fixed routes a deterred trip simply ceased to exist, so displacement was
  close to untestable. With congestion-aware routing the traffic is still there
  and free to move, and the boundary still falls with the interior (−33 % for
  both responsive rules).
- **The one positive number is noise.** Oscillate's +22 % at the boundary is
  0.361 ± 0.091 against 0.441 ± 0.132 over 14 days, overlapping throughout.
- **Caveat**: routes here respond to congestion, not to the charge. A CBD-bound
  agent pays whichever road it takes, so cordon-dodging proper is still untested.

## Who pays

- **The charge is strongly regressive.** The NZ$6 peak fee removes 59 % of the
  lowest value-of-time quintile's trips and 6 % of the highest's, and costs them
  1.30 and 0.28 hours of their own valuation respectively.
- **Most of the congestion relief is bought by low-income agents giving up
  travel.**
- **Retiming is the only remedy in the model, and it is thin.** A one-hour shift
  saves NZ$2 against a schedule-delay cost of 0.6 × VoT, so it pays only below
  about NZ$3.30/h — some 3 % of the population. The runs agree: 2.7 % of Pay
  entrants retimed, every one of them earlier.
- **The peak-to-shoulder differential is too small to buy retiming from anyone
  else.** That is a finding about the fee *structure*, not evidence that fee
  level is irrelevant.
- **Route choice has no distributional channel at all.**

## Who the 2,500 agents are (measured at setup, seed 11)

- **Nobody lives inside the cordon.** 0 agents have a CBD home, so every charged
  trip is an inbound trip crossing a boundary.
- **1,765 (70.6 %) enter from outside**: arterial edges 767, southern corridor
  484, northern 309, western 205. **735 (29.4 %) are isthmus residents** — also
  outside the cordon, just inside the modelled network.
- **1,500 have a CBD destination** and are exposed to the charge; the other
  1,000 never enter, forming an unpriced comparison group in the same run.
- **544 (21.8 %) are pass-through** and are never charged, so they load the ring
  roads whatever the fee.
- **2.98 destinations per agent** on average (1–4 stops plus home).
- One agent = 160 real vehicles → roughly 400,000 vehicle-trips a day.

## Demand provenance: what is fitted and what is assumed

- **Fitted to observed Auckland Transport ADT on all 1,634 links**: total
  volume (via the scale factor, ratio 1.013) and spatial distribution (via the
  suburban trip ends).
- **Not fitted, and not estimated from any data**: the origin-destination
  matrix and the time-of-day profile. Origins follow 2023 Census sector shares
  (North 0.30 / East-South 0.48 / West 0.22 of motorway inflow, 70 % of agents
  external); destinations are drawn **uniformly at random** from the non-home
  building stock, with no gravity term and no observed trip ends; departure
  hours are drawn per agent per day from two hardcoded hourly weight lists,
  uniform within the hour at a one-minute step.
- **The earlier claim that TomTom Move data set the profile and that NZTA TMS
  screenlines set corridor inflow is not implemented in the code.** No TomTom
  file exists in the repository; `motorway-aadt` and `tms-screenlines` are
  reporters that no procedure calls. Corrected in `methods_revised.md`.
- **So**: the model reproduces observed traffic *volume and spatial spread*,
  not observed travel patterns. The temporal residual (implied k = 0.157
  against 0.10) is not a shortfall against a fitted profile — it is what
  happens when there is no fitted profile.

## Things the paper must not claim

- **Not** "all three rules reduce congestion" — Oscillate does not.
- **Not** "El Farol behaves erratically" — after calibration its day-to-day SD
  is 0.021 against 0.015 and 0.013 for the others. The oscillation was an
  artefact of an uncalibrated, overloaded network.
- **Not** Learn's 38.7 % as the headline — it assumes staying home is the only
  alternative.
- **Not** "systematic time-shifting away from priced peaks" for Q-learning in
  the base model — its action space has two actions, and the fee paid per
  entering agent is flat across the run (2.83 → 2.75), so no retiming occurs.
- **Not** any claim about fee level — no fee-level sweep has been run on the
  calibrated model. The β sensitivity (11.7 / 23.0 / 25.4 % for 0.25 / 0.5 /
  1.0) suggests a saturating response, but that is price *sensitivity*, not
  price.

## The largest technical limitation: a declined CBD trip cancels the whole day

> **Status 2026-07-29: fixed in the model** (`skip-cbd-stops-today` — decliners
> now keep their non-CBD stops). Every number below describes the runs as
> published, which predate the fix; the 14-day re-run is pending.

- **Every CBD-bound agent is a multi-stop agent.** Measured at setup: of 2,500
  agents, 1,500 have a CBD destination, and **all 1,500 of them carry more than
  one destination**, 3.76 on average. Only the 544 pass-through agents have a
  single stop.
- **Declining the charge removes all of them.** `new-day-decisions` sets
  `active? false` for the day, so an agent that gives up one CBD stop also gives
  up its non-CBD stops. Across the CBD-bound population that is **3,171 non-CBD
  trips** that would vanish if all declined.
- **Scale of the distortion.** Under Pay, ToU moves entry from 0.523 to 0.402,
  about 300 agents. At 160 vehicles per agent and roughly two non-CBD stops
  each, of the order of 100,000 vehicle-trips per day disappear from roads
  outside the cordon for no modelled reason.
- **It inflates the results that matter most.** The peripheral reductions
  (−15.7 % for Pay, −27.2 % for Learn) and part of the no-displacement
  conclusion are produced by traffic that should still have been on the network.
- The code comment says "suppressed CBD destinations are skipped for the day",
  which is what should happen; the code deactivates the agent instead.
- **The k-factor sweep does not cover this.** `k-factor` appears in one place,
  `r-cap-hr = ADT × k-factor`, the denominator of the flow V/C used for LoS
  grading. Traffic trajectories are bit-identical across k at a given seed, so
  the sweep tests how congestion is *graded*, never how much demand there is.
  Demand-side over-suppression is untested by it.

## Open items

- Fee-level sweep on the calibrated model (≈ 9 cells, 5 h) — the one experiment
  that would let the paper say anything about how much to charge.
- Q-learning reward scale: the travel benefit is VoT/10, about NZ$1 for a median
  agent, against fees of NZ$2–6, which is why entering scores negative for every
  income band. Under a benefit of half an hour of VoT the expected regressive
  pattern returns. **Two arbitrary settings — benefit scale and action space —
  carry the Learn result.**
- Distributional results are derived from the decision and reward functions, not
  measured; `burden-quintile` was never recorded and is defective (q = 2, 3, 4
  return the whole population).
- Single seed throughout except the El Farol replication.
- Flat NZ$2 regime not re-run, so the draft's Fig. 5 has no calibrated basis.
