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
a fifth to a quarter, 18.8 % for the price-responsive rule and 24.1 % for the
learning rule, while the expectation-based rule changes it by 1.7 %, which is
well inside its own day-to-day variation. The same charge on the same road
therefore either works or does nothing at all, depending on a behavioural
assumption that is rarely stated and never observed.

The two rules that do respond arrive at their result by different routes, and
the route matters for appraisal. The price-responsive rule reads the fee inside
the decision, so its full effect is present on the first charged day and
nothing accumulates thereafter. The learning rule never sees the fee when it
decides and feels it only through the reward that follows, so its entry rate
begins at the uncharged level and falls for the whole fortnight, from 0.47 to
0.21, coming to rest on the floor set by its own exploration: by the last day
the learned policy is not to enter for essentially every agent, and the
remaining fifth of entries is the exploration the algorithm still performs
rather than willingness to pay. An evaluation carried out a week after launch
would read these two behavioural worlds very differently, even though their
fortnight-average reductions are of similar size. The
expectation-based rule is more cautionary still. It does deter on the first
day, when entry falls to 0.58 against 0.74 without a charge, but its own
feedback erases that deterrence within a single day, and by the second day both
regimes sit at about 0.92. A policy that appeared to work at first inspection
would have unwound before the second week.

On the question of displacement, the calibrated runs support the more
reassuring answer. The uncharged network is loaded on the cordon boundary
rather than inside it, with peak boundary V/C of 0.54 to 0.79 against 0.12 to
0.17 in the interior, and under both responsive rules the boundary and the
peripheral network fall together with the interior rather than absorbing the
deterred traffic. Agents deterred from the city centre keep their suburban
trips in this model, so those roads keep the traffic they should carry and
lose only the through-component of journeys bound for the cordon. The link-level map shows the same pattern at a finer grain.
This result is conditional on the design: routes are fixed shortest paths, so
the only adjustment available to an agent is whether and when to travel, and a
model with endogenous rerouting could still find diversion that this one cannot
express.

Two further sets of runs show that the assumption about *what an agent may do*
matters as much as the assumption about how it decides. Allowing a departure
to move by one hour, or allowing routes to respond to congestion, moves the
predicted reduction in peak inner-cordon V/C between zero and 24 per cent for
the price rule and between 9 and 24 per cent for the learner, with the
network, the demand and the fee schedule unchanged — and for the price rule
the routing assumption moves not only the size of the benefit but its
location. With congestion-aware routing the charge still deters a quarter of
entries, but the road space freed inside the cordon is refilled by rerouting
traffic, so the interior is unchanged while the cordon boundary falls by a
fifth: the familiar triple-convergence result, reproduced here by a behavioural
mechanism rather than assumed. The two options act on different
quantities: departure-time choice changes how many trips are made, and is the
reason the learner's headline collapses, because an agent given somewhere to
move stops forgoing the trip; route choice leaves the number of trips
untouched and changes only where they go, moving two fifths to half of the
load off the cordon boundary before any charge is applied. The single largest
effect observed across all of these runs is therefore a modelling assumption
rather than a policy.

The distributional result deserves its own sentence, because the aggregate
figures conceal it. Under the price rule the deterrent scales with the fee
divided by the square of an agent's value of time, so the NZ$6 peak charge
removes 59 per cent of the trips made by the lowest value-of-time quintile and
6 per cent of those made by the highest, and costs the former 1.3 hours of its
own valuation against 0.28 hours for the latter. Most of the congestion relief
is bought by low-income agents giving up travel. Departure-time choice offers
them the only partial remedy in the model, since retiming pays only for agents
below about NZ$3.30 an hour, some 3 per cent of the population, and the runs
bear that out: 2.7 per cent of price-rule entrants retimed and every one of
them moved earlier. Route choice offers no distributional remedy at all,
because routes here respond to congestion rather than to the charge.

We acknowledge that the simulation is a stylised abstraction that cannot stand
in for the full complexity of Auckland travel behaviour. It uses 2,500 agents
with no mode shift, rather than the roughly 70,000 agents and dynamic
activity-based modelling of a full regional demand model. The
origin-destination matrix is synthetic rather than estimated: origins follow
the 2023 Census sector populations, destinations are drawn uniformly from the
building stock with no gravity term or observed trip ends, and departure hours
come from a fixed weight profile rather than a measured time-of-day
distribution. Two axes of that demand were calibrated to observed Auckland
Transport daily counts, total volume and spatial distribution; the volume fit,
however, predates the trip-suppression correction, and with the suppressed
suburban trips restored the model carries about 31 per cent more traffic than
the observed counts (flow-weighted modelled to observed ratio 1.308 across all
1,634 links, concentrated on suburban arterials). We keep the fitted scale
factor and state this overshoot as a limitation rather than re-fitting,
because the deterrence decisions do not depend on the vehicle weight, so the
comparisons the study reports are essentially unaffected. The temporal axis
is not calibrated at all, which is why the assumed profile concentrates the
morning peak more sharply than the real network does. Absolute congestion
levels therefore read high on two counts, and we report differences between
charged and uncharged cases rather than levels throughout. The model therefore reproduces observed
traffic volume and its spatial spread, not observed travel patterns. Because
every rule and fee regime faces the same demand realisation, this bounds the
external reading of the levels without weakening the comparison between rules,
which is what the study is for. All runs use a single random seed, so the day-to-day
spreads describe variation within one seed. The learning rule's action space is
binary, to enter or not to enter, so the model cannot produce departure-time
substitution and the reductions reported here are deterrence rather than peak
spreading.

One check was structural rather than parametric and materially moved the
results outside the cordon. Every agent with a city-centre destination in this
model also has others, 3.76 on average, and in an earlier version an agent
that declined the charge was deactivated for the whole day, cancelling its
suburban stops with its city-centre one — in the order of a hundred thousand
vehicle-trips a day leaving roads outside the cordon for no behavioural
reason. Correcting this (a declining agent now skips only its city-centre
stops) raised the uncharged baseline outside the cordon substantially and
roughly halved the measured outer-zone reductions, from 44.6 to 22.6 per cent
at the boundary for the learning rule; the no-displacement conclusion
survived, and now rests on roads that carry the traffic they should. We report
it because it shows how easily a demand-suppression artefact can flatter
exactly the spatial results a cordon study leans on. Note that the k-factor
sensitivity could never have caught it: that parameter sets the denominator of
the flow V/C used for grading, and traffic is identical across its values at a
fixed seed, so it tests how congestion is measured rather than how much demand
there is.

Within those bounds, the contribution is not a forecast. It is that an
agent-based framework can hold competing behavioural theories in one network
and one pricing environment and show what each of them implies, including when
the implication is that the policy does nothing. For a city about to choose a
cordon design, the honest output of such an exercise is a range rather than a
point estimate, in this case a peak reduction of anywhere between zero and
about a quarter, bracketed by assumptions that no aggregate elasticity makes
visible: which rule the drivers follow, and which responses they are permitted.
The same framing turns the distributional finding from a caveat into a result,
since the model can say not only how much congestion falls but which quintile
paid for it. That framing also disciplines the modeller. The oscillatory behaviour
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
