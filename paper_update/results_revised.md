# Results — revised text

Replaces the whole *Results* section. All numbers come from the calibrated
model, 14 simulated days, seed 11, and are listed with their source table in
`numbers.md`.

---

## Results

### Comparing behavioural decisions

Table 1 summarises the three rules. Under exponential decay (Pay), the daily
peak volume-to-capacity ratio inside the cordon averages 0.122 with no charge
and falls to 0.094 under ToU, a reduction of 23.0 %, while the share of agents
entering the cordon falls from 0.52 to 0.40. The response is smooth and stable,
with a day-to-day standard deviation of about 0.015 in both cases.

Q-learning (Learn) produces a reduction of the same size by a different route,
from 0.122 to 0.093, a fall of 23.8 %, but it does so by cutting entries much
harder, from 0.54 to 0.34. Its day-to-day spread widens under the charge
(standard deviation 0.013 with no charge against 0.025 under ToU) because the
policies are still moving: the network-wide share of traffic at LoS E or worse
falls steadily from 56 % on day 1 to 38 % on day 14 and had not levelled off
when the run ended. The Q-learning figures below are therefore a lower bound on
the converged effect.

The El Farol rule (Oscillate) is the clear outlier. Its peak inner-cordon V/C
is unchanged by the charge, 0.173 against 0.173, a difference of 0.2 % that
sits well inside the day-to-day spread, and its entry rate barely moves, from
0.91 to 0.90. Two features explain this. First, agents respond to recent
congestion rather than to the fee, so the price enters their decision only
weakly. Second, almost all of them enter every day: an entry rate of 0.91
against 0.52 and 0.54 for the other rules means the cordon carries far more
traffic, and its uncharged baseline is correspondingly higher.

**Table 1.** Daily peak V/C by cordon position and cordon entry rate, mean plus
or minus day-to-day standard deviation over 14 simulated days.

| Rule | Position | No charge | ToU | Change |
|---|---|---|---|---|
| Pay (exponential decay) | inner | 0.122 ± 0.015 | 0.094 ± 0.013 | −23.0 % |
| | boundary | 0.359 ± 0.050 | 0.274 ± 0.033 | −23.5 % |
| | peripheral | 0.075 ± 0.006 | 0.064 ± 0.007 | −14.7 % |
| | entry rate | 0.522 ± 0.011 | 0.397 ± 0.011 | −23.9 % |
| Oscillate (El Farol) | inner | 0.173 ± 0.021 | 0.173 ± 0.020 | −0.2 % |
| | boundary | 0.763 ± 0.093 | 0.723 ± 0.097 | −5.3 % |
| | peripheral | 0.120 ± 0.013 | 0.118 ± 0.017 | −2.2 % |
| | entry rate | 0.914 ± 0.055 | 0.899 ± 0.095 | −1.6 % |
| Learn (Q-learning) | inner | 0.122 ± 0.013 | 0.093 ± 0.025 | −23.8 % |
| | boundary | 0.394 ± 0.038 | 0.248 ± 0.068 | −37.0 % |
| | peripheral | 0.074 ± 0.005 | 0.058 ± 0.010 | −22.3 % |
| | entry rate | 0.539 ± 0.024 | 0.343 ± 0.094 | −36.3 % |

### Why the three rules reach their results differently

The daily entry rates (Fig. 4) show that the three rules do not merely differ
in how far congestion falls, but in *when* and *whether* the charge reaches the
decision at all.

Under exponential decay the fee is an argument of the decision itself, so the
response is complete on day 1: entry is 0.40 under ToU against 0.52 with no
charge from the first day, and both series are flat thereafter. The rule has no
memory, so there is nothing to accumulate.

Q-learning never sees the fee when it decides. The action is chosen from the
Q-values of the current state, which is the pair of time band and recent
congestion band, and the fee enters only afterwards, through the reward the
agent collects. The consequence is visible in the figure: on day 1 the charged
and uncharged runs are identical (entry 0.505 in both), and the charged run
then slides away from the baseline day after day, reaching 0.24 by day 14, a
fall of 52 % from its own first day. Three features of the reward make that
slide one-directional. Entering pays vot/10 minus the fee minus three times the
realised V/C, while not entering pays a flat 0.3 less a small VoT term, about
0.15 for the median agent. With the calibrated network the realised inner V/C
is only 0.10 to 0.14, so the congestion term is worth about 0.3 to 0.4, whereas
the fee is NZ$2 to NZ$6, and agents whose fee exceeds their value of time take
a further penalty. The fee therefore dominates the reward by roughly an order
of magnitude, and the one force that could pull agents back in, namely the
congestion they avoid by staying out, is far too small to offset it. Because
the update moves each Q-value by only a fraction of that error each day, the
argmax of successive states flips over several days rather than at once, which
is why the decline is gradual, monotone and still incomplete on day 14. The
same mechanism explains the opposite drift in the uncharged run, where entry
*rises* by 15 % over the fortnight: without a fee, entering is simply the
better-rewarded action and the agents learn that too.

Two consequences of this design should be stated plainly. First, the effect is
deterrence, not retiming: the mean fee paid per entering agent is 2.83 on day 1
and 2.75 on day 14, so the agents who still enter are not moving into cheaper
hours, they are the same mix of hours with fewer agents in it. This matches the
hour-of-day result below, where the reduction is nearly uniform across the day.
Second, the reported Q-learning effect is a lower bound, since the series had
not levelled off when the run ended.

El Farol fails for a third reason again. Its agents compare predicted
congestion with a comfort threshold, and the fee only shifts that threshold, so
once the calibrated network is uncongested the prediction sits below the
threshold on almost every day and almost every agent enters. The charge does
deter on day 1, when entry is 0.57 under ToU against 0.73 with no charge, but
that deterrence is undone within a single day: by day 2 both regimes are at
0.91 to 0.93 and they stay there. What looks like insensitivity in the summary
table is in fact an initial response that the rule's own feedback erases.

The hour-of-day profile (Fig. 5) shows where within the day the charge acts.
Every cell is twin peaked, with a morning peak around 08:00 to 09:00 and an
evening peak around 17:00 to 18:00. Under exponential decay the morning peak
mean falls by 23.1 % and the evening peak by 17.7 %, and under Q-learning by
49.3 % and 51.8 %. Under El Farol both peaks are marginally higher with the
charge than without it, by 1.8 % and 3.2 %, which is within the day-to-day
band. Notably, for both responsive rules the whole-day mean falls by almost
exactly as much as the peaks do, 21.3 % and 49.1 %, so the charge lowers the
level of cordon traffic across the day rather than moving trips out of the
charged windows into cheaper ones. The temporal mechanism here is deterrence
rather than the peak spreading that a ToU schedule is designed to induce, a
consequence of routes being fixed and of the decision being framed as whether
to enter rather than exactly when.

Grading the same runs on Level of Service (Fig. 6) gives the network-wide
picture. Over the whole day, the share of traffic on links at LoS E or worse
falls from 56.3 % to 49.4 % under exponential decay and from 58.0 % to 40.0 %
under Q-learning, and is unchanged under El Farol, 71.8 % against 71.5 %. The
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
concentrate inside the cordon but on its boundary: peak boundary V/C is 0.36
to 0.76 depending on the rule, against 0.12 to 0.17 inside and 0.07 to 0.12 on
the periphery. The ring of approach roads, not the interior, is where the
network is loaded. Second, the three rules differ in level as well as in
response, so each is compared against its own baseline.

Under both responsive rules the charge lowers V/C in all three zones at once.
For exponential decay the boundary falls by 23.5 %, matching the 23.0 % fall
inside the cordon, and the periphery falls by 14.7 %. For Q-learning the
boundary falls furthest, by 37.0 %, against 23.8 % inside and 22.3 % on the
periphery. There is no zone in which V/C rises, so on this evidence the charge
does not push congestion outward. The link-level map (Fig. 7) shows the same
result at a finer grain: the arterials inside the cordon and the approach
roads leading to it turn blue together, and the few red links are scattered
rather than forming a ring outside the boundary.

El Farol again behaves differently. Its mean change is close to zero in every
zone, −5.3 % at the boundary and −2.2 % on the periphery, and its map is
mottled, with reductions on some approaches and increases on others, including
a small mean increase on peripheral links. This is what an unpriced
reallocation looks like: agents move relative to one another in response to
yesterday's congestion, but the total does not fall.

Two limitations bound the displacement result. Routing is held to fixed
shortest paths, so the only adjustment available to an agent is temporal,
whether and when to travel, not spatial. A model with rerouting could show
diversion around the cordon that this design cannot express. In addition, all
runs use a single random seed, so the day-to-day spreads quoted describe
variation within one seed rather than run-to-run uncertainty. A five-seed
replication of the El Farol case confirms its null result, with a mean ToU
effect of −1.7 % and a range from −5.8 % to +1.1 % across seeds.
