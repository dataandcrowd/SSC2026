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
