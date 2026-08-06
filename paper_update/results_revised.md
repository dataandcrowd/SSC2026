# Results — revised text

Replaces the whole *Results* section. All numbers come from the calibrated
model **after the trip-suppression fix** (base-arm tables of 2026-08-06),
14 simulated days, seed 11, and are listed with their source table in
`numbers.md`.

---

## Results

### Comparing behavioural decisions

Table 1 summarises the three rules. Under exponential decay (Pay), the daily
peak volume-to-capacity ratio inside the cordon averages 0.120 with no charge
and falls to 0.097 under ToU, a reduction of 18.8 %, while the share of agents
entering the cordon falls from 0.52 to 0.40. The response is smooth and stable,
with a day-to-day standard deviation of about 0.015 in both cases.

Q-learning (Learn) produces a somewhat larger reduction by a different route,
from 0.116 to 0.088, a fall of 24.1 %, and it does so by cutting entries much
harder, from 0.53 to 0.33. Its day-to-day spread in the entry rate widens by a
factor of three under the charge (standard deviation 0.027 with no charge
against 0.095 under ToU) because the entry level is still moving across the
fortnight as the learned policies settle; the mechanism, and why the day-14
state should be read as converged, is set out in the next subsection.

The El Farol rule (Oscillate) is the clear outlier. Its peak inner-cordon V/C
is essentially unchanged by the charge, 0.166 against 0.163, a difference of
1.7 % that sits well inside the day-to-day spread, and its entry rate barely
moves, from 0.92 to 0.90. Two features explain this. First, agents respond to
recent congestion rather than to the fee, so the price enters their decision
only weakly. Second, almost all of them enter every day: an entry rate of 0.92
against 0.52 and 0.53 for the other rules means the cordon carries far more
traffic, and its uncharged baseline is correspondingly higher.

**Table 1.** Daily peak V/C by cordon position and cordon entry rate, mean plus
or minus day-to-day standard deviation over 14 simulated days.

| Rule | Position | No charge | ToU | Change |
|---|---|---|---|---|
| Pay (exponential decay) | inner | 0.120 ± 0.015 | 0.097 ± 0.014 | −18.8 % |
| | boundary | 0.535 ± 0.038 | 0.470 ± 0.058 | −12.3 % |
| | peripheral | 0.095 ± 0.007 | 0.083 ± 0.010 | −12.7 % |
| | entry rate | 0.517 ± 0.018 | 0.395 ± 0.009 | −23.5 % |
| Oscillate (El Farol) | inner | 0.166 ± 0.020 | 0.163 ± 0.018 | −1.7 % |
| | boundary | 0.793 ± 0.079 | 0.783 ± 0.099 | −1.2 % |
| | peripheral | 0.128 ± 0.017 | 0.125 ± 0.016 | −2.3 % |
| | entry rate | 0.917 ± 0.051 | 0.900 ± 0.093 | −1.8 % |
| Learn (Q-learning) | inner | 0.116 ± 0.017 | 0.088 ± 0.019 | −24.1 % |
| | boundary | 0.553 ± 0.055 | 0.428 ± 0.084 | −22.6 % |
| | peripheral | 0.092 ± 0.010 | 0.078 ± 0.007 | −15.1 % |
| | entry rate | 0.531 ± 0.027 | 0.333 ± 0.095 | −37.2 % |

### Why the three rules reach their results differently

The daily entry rates (Fig. 4) show that the three rules do not merely differ
in how far congestion falls, but in *when* and *whether* the charge reaches the
decision at all.

Under exponential decay the fee is an argument of the decision itself, so the
response is complete on day 1: entry is 0.40 under ToU against 0.54 with no
charge from the first day, and both series are flat thereafter. The rule has no
memory, so there is nothing to accumulate.

Q-learning never sees the fee when it decides. The action is chosen from the
Q-values of the current state, which is the pair of time band and recent
congestion band, and the fee enters only afterwards, through the reward the
agent collects. The consequence is visible in the figure: on days 1 and 2 the
charged and uncharged runs are identical (entry 0.473 and 0.490 in both), and
the charged run then slides away from the baseline day after day, reaching
0.208 by day 14, a fall of 56 % from its own first day. Three features of the
reward make that slide one-directional. Entering pays vot/10 minus the fee
minus three times the realised V/C, while not entering pays a flat 0.3 less a
small VoT term, about 0.15 for the median agent. With the calibrated network
the realised inner V/C is only 0.09 to 0.14, so the congestion term is worth
about 0.3 to 0.4, whereas the fee is NZ$2 to NZ$6, and agents whose fee exceeds
their value of time take a further penalty. The fee therefore dominates the
reward by roughly an order of magnitude, and the one force that could pull
agents back in, namely the congestion they avoid by staying out, is far too
small to offset it. Because the update moves each Q-value by only a fraction of
that error each day, the argmax of successive states flips over several days
rather than at once, which is why the decline is gradual and monotone. The
same mechanism explains the opposite drift in the uncharged run, where entry
*rises* by 16 % over the fortnight: without a fee, entering is simply the
better-rewarded action and the agents learn that too.

By day 14 the charged run has converged — not to an equilibrium demand level,
but to the floor set by its own exploration. Agents explore with probability
ε, which decays from 0.4 by 0.3 % per day and stands at about 0.385 on day 14;
an exploring agent enters with probability one half, so exploration alone
produces an entry rate of ε/2 ≈ 0.19. The observed day-14 rate of 0.208 sits
on that floor: the learned (greedy) policy is "do not enter" for essentially
every agent, and the residual fifth of entries is exploration noise rather
than willingness to pay. The converged Q-learning prediction is therefore
near-total deterrence, and the day-14 congestion figures measure that policy
plus its exploration dice, not a demand curve.

Two consequences of this design should be stated plainly. First, the effect is
deterrence, not retiming: the mean fee paid per entering agent is 2.83 on day 1
and 2.74 on day 14, so the agents who still enter are not moving into cheaper
hours, they are the same mix of hours with fewer agents in it. This matches the
hour-of-day result below, where the reduction is nearly uniform across the day.
Second, the size of the effect is set by the reward scaling — the fee dominates
every other term — so it should be read as a property of the learning design as
much as of the charge.

El Farol fails for a third reason again. Its agents compare predicted
congestion with a comfort threshold, and the fee only shifts that threshold, so
once the calibrated network is uncongested the prediction sits below the
threshold on almost every day and almost every agent enters. The charge does
deter on day 1, when entry is 0.58 under ToU against 0.74 with no charge, but
that deterrence is undone within a single day: by day 2 both regimes are at
0.92 to 0.93 and they stay there. What looks like insensitivity in the summary
table is in fact an initial response that the rule's own feedback erases.

The hour-of-day profile (Fig. 5) shows where within the day the charge acts.
Every cell is twin peaked, with a morning peak around 08:00 to 09:00 and an
evening peak around 17:00 to 18:00. Under exponential decay the morning peak
mean falls by 17.0 % and the evening peak by 18.4 %, and under Q-learning by
39.4 % and 41.7 %. Under El Farol neither peak moves outside the day-to-day
band (−0.6 % and +3.5 %). Notably, for both responsive rules the whole-day
mean falls by almost exactly as much as the peaks do, 18.4 % and 44.7 %, so
the charge lowers the level of cordon traffic across the day rather than
moving trips out of the charged windows into cheaper ones. The temporal
mechanism here is deterrence rather than the peak spreading that a ToU
schedule is designed to induce, a consequence of routes being fixed and of the
decision being framed as whether to enter rather than exactly when.

Grading the same runs on Level of Service (Fig. 6) gives the network-wide
picture. Over the whole day, the share of traffic on links at LoS E or worse
falls from 65.7 % to 63.2 % under exponential decay and from 66.4 % to 60.3 %
under Q-learning, and is unchanged under El Farol, 72.8 % against 72.2 %. The
absolute shares are high, and the worst two-hour band is 09:00 to 11:00 rather
than the morning peak itself, because the flow measure is a one-hour moving
average that lags the departure peak. As set out in the calibration, the
model's implied design-hour factor of 0.157 exceeds the 0.10 assumed in the
capacity conversion, so absolute peak-hour LoS is pessimistic. The difference
between the charged and uncharged cases, which is what we report, is not
affected by that assumption: a sensitivity test at k = 0.08, 0.10 and 0.12
gives the same ordering and direction throughout.

### Spatial redistribution under ToU

A standing concern with cordon pricing is that traffic deterred from the
charged zone reappears on the cordon boundary or on peripheral roads. Two
features of the uncharged baseline frame the test. First, congestion does not
concentrate inside the cordon but on its boundary: peak boundary V/C is 0.54
to 0.79 depending on the rule, against 0.12 to 0.17 inside and 0.09 to 0.13 on
the periphery. The ring of approach roads, not the interior, is where the
network is loaded. Second, the three rules differ in level as well as in
response, so each is compared against its own baseline.

Under both responsive rules the charge lowers V/C in all three zones at once.
For exponential decay the interior falls by 18.8 %, the boundary by 12.3 % and
the periphery by 12.7 %. For Q-learning the interior falls by 24.1 %, the
boundary by 22.6 % and the periphery by 15.1 %. In both cases the reduction is
largest inside the cordon, where the charge is levied, and smaller — but still
present — outside it. There is no zone in which V/C rises, so on this evidence
the charge does not push congestion outward. The link-level map (Fig. 7) shows
the same result at a finer grain: the arterials inside the cordon and the
approach roads leading to it turn blue together, and the few red links are
scattered rather than forming a ring outside the boundary.

The size of the outer-zone reductions deserves a note, because it separates
two things a cordon charge does. Agents deterred from the CBD still make their
suburban trips in this model, so the roads outside the cordon keep most of
their traffic; what they lose is the through-component of journeys that would
have crossed into the CBD. That is why the boundary and periphery fall by
around 12 to 23 per cent rather than emptying: the charge removes CBD-bound
travel, not suburban travel.

El Farol again behaves differently. Its mean change is close to zero in every
zone, −1.2 % at the boundary and −2.3 % on the periphery, and its map is
mottled, with reductions on some approaches and increases on others. This is
what an unpriced reallocation looks like: agents move relative to one another
in response to yesterday's congestion, but the total does not fall.

Two limitations bound the displacement result. Routing is held to fixed
shortest paths, so the only adjustment available to an agent is temporal,
whether and when to travel, not spatial. A model with rerouting could show
diversion around the cordon that this design cannot express. In addition, all
runs use a single random seed, so the day-to-day spreads quoted describe
variation within one seed rather than run-to-run uncertainty. A five-seed
replication of the El Farol case confirms its null result, with a mean ToU
effect of −1.7 % and a range from −5.8 % to +1.1 % across seeds.
