# Conclusion — revised text

Replaces the *Conclusion* section. The submitted version opens with "All three
reduce peak-hour V/C inside the cordon under the proposed ToU schedule", which
the calibrated runs contradict, and it rests the contribution on a claim about
pathways that the new results state far more sharply.

---

## Conclusion

This study placed three agent decision rules for cordon congestion pricing side
by side in one Auckland CBD network, with the same population, the same value
of time distribution and the same time-of-use schedule, so that the only thing
varying between runs was the assumption about how a driver decides. On the
calibrated model the rules do not merely differ in the size of the response.
Two of them cut the daily peak volume-to-capacity ratio inside the cordon by
about a quarter, 23.0 % for the price-responsive rule and 23.8 % for the
learning rule, while the expectation-based rule changes it by 0.2 %, which is
well inside its own day-to-day variation. The same charge on the same road
therefore either works or does nothing at all, depending on a behavioural
assumption that is rarely stated and never observed.

The two rules that do respond arrive at their result by different routes, and
the route matters for appraisal. The price-responsive rule reads the fee inside
the decision, so its full effect is present on the first charged day and
nothing accumulates thereafter. The learning rule never sees the fee when it
decides and feels it only through the reward that follows, so its entry rate
begins at the uncharged level and falls for the whole fortnight, from 0.51 to
0.24, without having levelled off when the run ended. An evaluation carried out
a week after launch would read these two behavioural worlds very differently,
even though their fortnight-average reductions are almost identical. The
expectation-based rule is more cautionary still. It does deter on the first
day, when entry falls to 0.57 against 0.73 without a charge, but its own
feedback erases that deterrence within a single day, and by the second day both
regimes sit at about 0.91. A policy that appeared to work at first inspection
would have unwound before the second week.

On the question of displacement, the calibrated runs support the more
reassuring answer. The uncharged network is loaded on the cordon boundary
rather than inside it, with peak boundary V/C of 0.36 to 0.76 against 0.12 to
0.17 in the interior, and under both responsive rules the boundary and the
peripheral network fall together with the interior rather than absorbing the
deterred traffic. The link-level map shows the same pattern at a finer grain.
This result is conditional on the design: routes are fixed shortest paths, so
the only adjustment available to an agent is whether and when to travel, and a
model with endogenous rerouting could still find diversion that this one cannot
express.

We acknowledge that the simulation is a stylised abstraction that cannot stand
in for the full complexity of Auckland travel behaviour. It uses 2,500 agents
on a static origin-destination matrix with no mode shift, rather than the
roughly 70,000 agents and dynamic activity-based modelling of a full regional
demand model. Demand is calibrated to observed daily counts, with a
flow-weighted modelled to observed ratio of 1.013 across all 1,634 links, but
the departure profile still concentrates the morning peak more sharply than the
real network does, which is why absolute peak-hour Level of Service reads
pessimistically and why we report differences between charged and uncharged
cases rather than levels. All runs use a single random seed, so the day-to-day
spreads describe variation within one seed. The learning rule's action space is
binary, to enter or not to enter, so the model cannot produce departure-time
substitution and the reductions reported here are deterrence rather than peak
spreading.

Within those bounds, the contribution is not a forecast. It is that an
agent-based framework can hold competing behavioural theories in one network
and one pricing environment and show what each of them implies, including when
the implication is that the policy does nothing. For a city about to choose a
cordon design, the honest output of such an exercise is a range rather than a
point estimate, in this case a peak reduction of anywhere between zero and
about a quarter, bracketed by an assumption that no aggregate elasticity makes
visible. That framing also disciplines the modeller. The oscillatory behaviour
that an earlier, uncalibrated version of this model produced under the
expectation-based rule, and the apparent ability of pricing to damp it,
disappeared once demand was matched to observed counts, which shows how much a
behavioural finding can depend on the demand level it is measured at. Future
work will extend the action space to departure-time choice, add modal shift and
household travel survey data for value of time calibration, replicate across
seeds, and test the other cordon configurations under consideration by the
council.

---

## What changed and why

1. **"All three reduce peak-hour V/C" is removed.** On the calibrated model the
   El Farol rule changes peak inner-cordon V/C by 0.2 %, inside its own
   day-to-day spread, and a five-seed replication confirms the null.
2. **The pathway claim is made concrete.** The draft asserted that pathways
   differ without saying how. The entry-rate trajectories give the mechanism:
   immediate, cumulative and self-erasing, with the evaluation-timing
   implication spelled out.
3. **Displacement is now evidence, not assertion**, since the calibrated runs
   record boundary and peripheral V/C explicitly.
4. **New limitations added**: single seed, the temporal residual in the
   departure profile, and the binary action space of the learning rule.
5. **The framework claim is sharpened.** It is stronger when one assumption
   nullifies the policy than when all three merely differ in degree, so the
   contribution is stated as a bracket, zero to about a quarter, that an
   aggregate elasticity cannot produce.
