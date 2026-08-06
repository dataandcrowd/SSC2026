# Conclusions, as bullets

Calibrated NetLogo model **after the trip-suppression fix**, all four arms
re-run 2026-08-06, 14 simulated days, seed 11. Every number traces to
`numbers.md` or `behavioural_extensions.md`.

## The headline

- **The same charge on the same road either works or does nothing, depending on
  a behavioural assumption that is never observed.** Two rules cut peak
  inner-cordon V/C (18.8 % and 24.1 %); one changes it by 1.7 %, inside its own
  day-to-day spread.
- **The action space moves the answer as much as the decision rule does — and
  it moves where the answer lands, not only its size.** With the rule, network,
  demand and fee schedule all held fixed, the predicted ToU reduction in inner
  V/C is 0–24 % for the price rule (zero in the routing arms, where the
  benefit appears at the boundary, −19.5 %, instead) and 9–24 % for the
  learner, the range coming purely from what responses agents are allowed.
- **The single largest effect in these runs is a modelling assumption, not a
  policy.** Letting routes respond to congestion moves 39–52 % of the load off
  the cordon boundary before any charge is applied (Pay 0.535 → 0.325,
  Oscillate 0.793 → 0.381, Learn 0.553 → 0.302).

## By decision rule

- **Pay (exponential decay)** — robust in entries, not in location. Entries
  fall 23–24 % in every arm, but the inner-cordon reduction is −18.8 % (base),
  −23.8 % (retime) and **zero in the routing arms** (+1.8 % / −3.7 %, both
  inside the day-to-day spread), where the freed interior space is refilled by
  rerouting traffic and the benefit shows up on the boundary (−19.5 %).
  Responds in full on day 1 and stays flat, because the fee sits inside the
  decision.
- **Learn (Q-learning)** — largest base-arm cut, converged, and fragile to the
  action space. −24.1 % in the base arm but 9–16 % wherever the agent has an
  alternative to staying home (retime −9.5 %, reroute −15.5 %, both −9.4 %).
  Never sees the fee when it decides, only in the reward, so its response
  accumulates over the fortnight — and by day 14 it has hit the floor set by
  its own exploration: ε ≈ 0.385 on day 14 and an exploring agent enters half
  the time, so ε/2 ≈ 0.19 of entries are exploration noise, against an
  observed 0.208. **The learned policy is near-total deterrence; do not
  describe the trajectory as "still falling".** The size of the effect remains
  hostage to the reward scaling and the action space.
- **Oscillate (El Farol)** — inert. −1.7 % base arm; the retime and both arms
  are bit-identical across fee regimes, and its reroute-arm swings (−20 %
  inner, +24 % boundary) sit inside their own day-to-day SDs. It reads
  yesterday's congestion, not today's price, and calibrated congestion
  (0.09–0.17) never approaches its comfort threshold (0.6), so the fee never
  flips a decision. Its day-1 deterrence is erased by day 2. Five-seed
  replication confirms the null.

## What each behavioural option does

- **Departure-time choice changes how many trips are made.** It is the only
  extension that moves the entry rate: Learn 0.33 → 0.62, so its measured
  benefit collapses (−24.1 % → −9.5 %). Pay's entry rate is unchanged because
  only 2.5 % of its entrants shift (13 of 15 earlier).
- **Route choice changes where the trips go, not how many.** Entry rates are
  nearly identical; the no-charge baseline moves instead — and under ToU the
  freed interior space is partly refilled, so for Pay the interior benefit
  vanishes while the boundary benefit stays.
- **So**: a result that depends on how many people travel is sensitive to the
  retiming assumption; a result about where congestion appears is sensitive to
  the routing assumption. The displacement question is of the second kind.

## Level of service: where the charge acts

- **Post-fix, the charge acts where it is levied — the CBD arterial group —
  and only marginally elsewhere.** Flow-weighted traffic at LoS E or worse in
  the CBD group falls 4.9–6.6 pp under Pay and 4.2–6.0 pp under Learn, against
  a point or so on the motorway corridors and the outer arterial groups.
- **The pre-fix motorway headline is gone.** The −11.5 to −13.6 pp AM-peak
  motorway movements in earlier drafts were produced by the trip-suppression
  artefact (deleting a decliner's whole day emptied the motorways too). Post-fix
  the motorway AM effect is −1.3 pp (Pay) to −3.0 pp (Learn). **Do not quote
  the old motorway numbers.**
- **The link-count grade shares barely move post-fix** (arterial −0.3 pp Pay,
  −2.0 pp Learn): arterials sit so deep in E/F that removing the CBD-bound
  slice rarely changes a link's peak grade. Read the flow-weighted measure and
  the V/C tables, not the grade counts.
- **Arterials start worse and stay worse**, ~80 % at E/F against ~60 % on
  motorways. Part definitional (an arterial grades E from V/C 0.82, a motorway
  from 0.90), part signalised capacity.
- **Oscillate does nothing on either class.**

## Displacement

- **The charge does not push traffic outward.** In the post-fix base arm V/C
  falls in every zone under both responsive rules (boundary −12.3 % Pay,
  −22.6 % Learn; periphery −12.7 % and −15.1 %), and the margin is honest now:
  decliners keep their suburban trips, so outer roads carry the traffic they
  should and lose only the CBD-bound through-component.
- With congestion-aware routing — the proper test — the deterred traffic is
  still on the network and free to move, and nothing piles up outside: the
  boundary falls −19.5 % (Pay) and −19.7 % (Learn) with the periphery falling
  too. Oscillate's +24 % at the boundary is noise (0.381 ± 0.077 vs
  0.472 ± 0.184). What the routing arm adds is an *inward* flow: freed space
  inside the cordon is partly refilled (triple convergence), capping the
  interior benefit when drivers reroute freely.
- **Caveat**: routes respond to congestion, not to the charge. A CBD-bound
  agent pays whichever road it takes, so cordon-dodging proper is still
  untested.

## Who pays *(derived from the equations, not measured in runs)*

- **The charge is strongly regressive.** The NZ$6 peak fee removes 59 % of the
  lowest value-of-time quintile's trips and 6 % of the highest's, and costs them
  1.30 and 0.28 hours of their own valuation respectively.
- **Most of the congestion relief is bought by low-income agents giving up
  travel.**
- **Retiming is the only remedy in the model, and it is thin.** A one-hour shift
  saves NZ$2 against a schedule-delay cost of 0.6 × VoT, so it pays only below
  about NZ$3.30/h — some 3 % of the population. The post-fix runs agree: 2.5 %
  of Pay entrants retimed, 13 of 15 earlier.
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

- **Fitted to observed Auckland Transport ADT on all 1,634 links** — but the
  fit predates the trip-suppression fix. The post-fix re-check (2026-08-06)
  gives a flow-weighted modelled/observed ratio of **1.308** at scale-factor
  160 (was 1.013 pre-fix): restoring decliners' suburban trips overshoots
  observed volume by 31 %, concentrated on suburban arterials (East 1.57,
  West 1.40) with motorways near 1 (1.04). **Do not quote 1.013.** Suggested
  re-fit: scale-factor ≈ 122; re-fitting means re-running all four arms.
  Decision pending.
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
  is 0.020 against 0.015 and 0.017 for the others. The oscillation was an
  artefact of an uncalibrated, overloaded network.
- **Not** Learn's stay-home-only figure (24.1 %) as the headline — the action
  space moves it to 9–16 % wherever the agent has an alternative; quote the
  range.
- **Not** "the price rule's effect is robust across arms" — its entries are
  (−23 to −24 % everywhere), but its inner-cordon reduction is zero in the
  routing arms; say *where* the benefit lands per arm.
- **Not** "still learning / had not converged" for Q-learning — entry has
  reached the exploration floor (0.208 observed vs ε/2 ≈ 0.19); the policy has
  converged to near-total deterrence and the residual entries are exploration.
- **Not** "systematic time-shifting away from priced peaks" for Q-learning in
  the base model — its action space has two actions, and the fee paid per
  entering agent is flat across the run (2.83 → 2.74), so no retiming occurs.
- **Not** the pre-fix motorway AM improvements (−11.5 / −13.6 pp) — they were
  the trip-suppression artefact; post-fix values are −1.3 / −3.0 pp.
- **Not** any claim about fee level — no fee-level sweep has been run on the
  calibrated model. The β sensitivity (pre-fix: 11.7 / 23.0 / 25.4 % for
  0.25 / 0.5 / 1.0) suggests a saturating response, but that is price
  *sensitivity*, not price.

## The trip-suppression artefact: found, fixed, measured

- **Every CBD-bound agent is a multi-stop agent** (all 1,500, 3.76 destinations
  on average), and in the pre-fix model a declined CBD entry deactivated the
  agent for the whole day — of the order of 100,000 suburban vehicle-trips a
  day off the network for no behavioural reason.
- **Fixed 2026-07-30** (`skip-cbd-stops-today`): decliners keep their non-CBD
  stops. Base arm re-run 2026-08-06.
- **Measured effect**: the uncharged baseline outside the cordon rose (Pay
  boundary 0.344 → 0.535, periphery 0.074 → 0.095) and the outer-zone
  reductions roughly halved (Learn boundary −44.6 % → −22.6 %; Pay periphery
  −15.7 % → −12.7 %). The artefact had been inflating exactly the results the
  paper leans on.
- **The no-displacement conclusion survived the correction** — smaller margins,
  firmer ground.
- **The k-factor sweep could never have caught it**: traffic is bit-identical
  across k at a fixed seed; the sweep tests how congestion is graded, not how
  much demand there is.

## Open items

- **Calibration re-fit decision**: the post-fix re-check measured
  modelled/observed at 1.308 (sf 160); re-fitting to sf ≈ 122 restores the
  volume match but requires re-running all four arms (~13 h) and the sweeps.
  Alternative: keep sf 160, report differences only, and state the 1.31 ratio
  as a limitation. Undecided.
- **Sensitivity sweeps are pre-fix** (β, α, ε, k, El Farol threshold): quote
  directions only until re-run.
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
