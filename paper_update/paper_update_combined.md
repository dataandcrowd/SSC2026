# Manuscript update pack — calibrated model

*SSC2026 cordon-pricing paper. Combined from `paper_update/` on 2026-07-29. Calibrated NetLogo model (scale-factor 160, suburban destinations), 14 simulated days, seed 11.*

## Contents

- [Overview](#overview) — `README.md`
- [Abstract](#abstract) — `abstract_revised.md`
- [Methods](#methods) — `methods_revised.md`
- [Results](#results) — `results_revised.md`
- [Behavioural extensions](#behavioural-extensions) — `behavioural_extensions.md`
- [Conclusion](#conclusion) — `conclusion_revised.md`
- [Conclusions as bullets](#conclusions-as-bullets) — `conclusions_bullets.md`
- [Numbers and sources](#numbers-and-sources) — `numbers.md`
- [Decisions log](#decisions-log) — `decisions_log.md`

---

<a id="overview"></a>

## Overview

*Source file: `README.md`*


Revised text and figures for `SSC2026_congestion.docm`, rebuilt on the
**calibrated** NetLogo model (scale-factor 160 + suburban destinations,
14 simulated days, seed 11). Every number in the draft's Results section came
from the pre-calibration model and is superseded here.

| File | What it is |
|---|---|
| `abstract_revised.md` | Replacement result sentences for the abstract |
| `methods_revised.md` | Replacement text for *Simulation → Study area and model* and a new *Calibration* subsection |
| `results_revised.md` | Replacement text for *Results* (both subsections) |
| `conclusion_revised.md` | Replacement text for *Conclusion* |
| `conclusions_bullets.md` | Every conclusion as bullets, including what the paper must not claim |
| `behavioural_extensions.md` | Departure-time and route-choice arms, and who bears the charge |
| `numbers.md` | Every quoted figure with its source table, for checking |
| `decisions_log.md` | Why things were done this way, and what was deferred |
| `../output/논문_개정안_한글.md` | Korean summary of the whole pack |

The presentation `presentation/SSC2026_presentation.pptx` has been updated in
place to the same numbers (backups `SSC2026_presentation.pptx.bak` … `.bak8`,
script `presentation/update_presentation.py`). It grew from 6 slides to 16: the
original numbers came from a pre-calibration 500-agent run, and slides were
added for calibration, equity, the two behavioural extensions, the action-space
comparison and the limitations. Chart images are the plotnine (`_gg`) versions;
the map stays in matplotlib.

2026-07-29 revision: a new slide 7, *How Much to Trust Each Number*, states the
evidence status of every result (measured / derived / superseded / known bias);
the equity slide is retitled *Who Would Pay? Derived, Not Yet Measured* and
carries a provenance strip, since no run records entries by income band; the
displacement slide is captioned with the trip-suppression caveat. The
trip-suppression artefact itself — a declined CBD entry cancelled the agent's
whole day — is now **fixed in the model** (`skip-cbd-stops-today` in
`akl_pricing.nls`); all published numbers predate the fix and the 14-day
`paper-figs` re-run is pending.

Also 2026-07-29: the demand section of `methods_revised.md` was rewritten to
describe the generator the code actually runs. The submitted draft credited
TomTom Move data with the time-of-day profile and NZTA TMS screenlines with
corridor inflow; neither is implemented (see decisions log §9). The
origin-destination matrix is synthetic — origins from Census sector shares,
destinations drawn uniformly from the building stock, departure hours from a
fixed weight list — so only volume and spatial distribution are fitted to
observed counts. The calibration and limitations slides now say so.

Figures referenced by the revised text (all in `output/figures/`):

| Figure | File | Source |
|---|---|---|
| Entry rate by day (mechanism) | `entry_trajectory.png` | `paper-figs` experiment |
| Action space vs the answer | `arms_comparison.png` | `retiming`, `rerouting` |
| Who the charge removes | `equity_by_income.png`, `equity_by_income_gg.png` | derived |
| Departure-time choice | `optin_retiming.png`, `optin_retiming_gg.png` | `retiming` |
| Route choice | `optin_rerouting.png`, `optin_rerouting_gg.png` | `rerouting` |
| Hour-of-day V/C profile | `sensitivity_hourly_profile.png` | `hourly-profile` experiment |
| Spatial redistribution map | `map_redistribution.png` | `paper-figs` experiment |
| LoS mix by time band | `sensitivity_los_bands.png` | `los-bands` experiment |
| LoS mix by day | `sensitivity_los_daily.png` | `los-bands` experiment |
| BPR curve and LoS bands | `los_bpr_schematic.png` | analytic, no run |

`map_baseline_los.png` is also produced but is **not** recommended for the
paper: it grades each link on the daily peak of the flow EMA, which saturates
at grade F on nearly every link, so the map is almost uniformly dark. Use the
LoS band figure for the same information with the time dimension kept.

Regenerate everything from the tables with:

```bash
python netlogo/sensitivity_experiment/paper_numbers.py
python netlogo/sensitivity_experiment/plot_hourly_profile.py
python netlogo/sensitivity_experiment/plot_los_bands.py
python netlogo/sensitivity_experiment/plot_map_redistribution.py
python netlogo/sensitivity_experiment/plot_entry_trajectory.py
python netlogo/sensitivity_experiment/plot_retiming.py
python netlogo/sensitivity_experiment/plot_arms.py
python netlogo/sensitivity_experiment/plot_equity_optin.py      # matplotlib
python netlogo/sensitivity_experiment/plot_equity_optin_gg.py   # plotnine (_gg)
```

Figures ending `_gg` are the plotnine versions of the same data; both scripts
read the same tables, so either set can be used in the paper.

---

<a id="abstract"></a>

## Abstract

*Source file: `abstract_revised.md`*


Only the result sentences change. Replacements in context:

> The results show that price-responsive and learning drivers both cut peak
> congestion inside the cordon by about a quarter (23.0 % and 23.8 %), and the
> charge does not push congestion onto the surrounding roads: the cordon
> boundary and the peripheral network fall together with the interior.
> Expectation-based drivers barely respond to the price at all, changing peak
> congestion by 0.2 %, because they read yesterday's congestion rather than
> today's fee.

### What changed and why

1. "about a fifth" becomes "about a quarter". Both rules now give 23 % to 24 %
   on the calibrated model.
2. **"behave erratically from day to day" has been removed.** On the
   uncalibrated model the El Farol rule produced a large alternate-day
   oscillation, with a day-to-day standard deviation of peak V/C around 0.24.
   After calibration that oscillation disappears: the standard deviation is
   0.021, against 0.015 for exponential decay and 0.013 for Q-learning. The
   oscillation was a property of an overloaded network, not of the attendance
   game, and a five-seed replication confirms the null. The rule is now
   *unresponsive*, not *erratic*, and the abstract should say so.
3. The displacement claim is stated with its evidence, since the calibrated
   runs record the cordon boundary and periphery explicitly, which the earlier
   runs did not.

If the flat NZ$2 charge is dropped (no calibrated run exists), the phrase
"one proposed time-of-use (ToU) cordon charge" already covers the design and
needs no change.

---

<a id="methods"></a>

## Methods

*Source file: `methods_revised.md`*


Replaces the paragraphs under *Study area and model* and adds a *Calibration*
subsection before *Time-of-use fee schedule*. Changes of substance are listed
at the end of this file.

---

### Study area and model

We built the simulation in NetLogo 6.4, using the `gis`, `nw`, `csv` and
`table` extensions to construct the road network, compute vehicle routes and
read the observed traffic counts. The model logic was adapted, with
permission, from the NetLogo model originally developed by the AI4CI Hub at
the Urban Big Data Centre, University of Glasgow.

The road network was derived from Stats NZ. The input dataset holds 1,542
nodes and 2,691 road segments; segments sharing the same pair of nodes are
collapsed, giving 1,634 undirected links in the modelled network, with speed
limits from 10 km/h on laneways to 80 km/h on motorway segments. The CBD
cordon boundary polygon was obtained from Stats NZ at the Statistical Area 3
(SA3) level and filtered to the Auckland City Centre unit to represent the
charged zone. Links are tagged by their position relative to that boundary as
inner, boundary or peripheral, and separately as motorway or arterial. Fig. 1
shows the network with the CBD cordon and the broader eleven SA3 study areas.

Road capacity is taken from the observed annual daily traffic (ADT) counts
published by Auckland Transport, converted to an hourly design capacity with a
design-hour factor of k = 0.10, the midpoint of the standard urban range of
0.08 to 0.12. Congestion is reported as Level of Service (LoS), graded from
the ratio of hourly flow to that hourly capacity following the Highway
Capacity Manual thresholds reproduced in the Congestion Question working
paper. The thresholds are class specific, so the same volume-to-capacity (V/C)
ratio grades more severely on an arterial (LoS E from 0.82) than on a motorway
(LoS E from 0.90). Because a single agent represents many vehicles, the
instantaneous count on a link is too coarse to grade, so flow is measured as
an exponentially weighted moving average of link entries with a one-hour time
constant. Travel speed responds to congestion through the standard BPR
function with a = 0.15 and b = 4. A sensitivity test across k = 0.08, 0.10 and
0.12 confirms that the direction and ordering of the pricing results do not
depend on this capacity assumption.

In total, 2,500 heterogeneous agents decide each day whether to enter the
priced cordon. Each agent represents 160 vehicles after calibration, so the
population corresponds to roughly 400,000 vehicle trips per day. Each agent
has an individual value of time, an arbitrary monetary value placed on travel
time savings, that varies across the population. Consequently, the same fee
deters agents with a lower value of time, typically those on a lower income,
more strongly [16].

### Travel demand: a synthetic origin-destination matrix

No observed origin-destination matrix was available, so the matrix is
generated by the model rather than estimated from data. This is stated
explicitly because it bounds what the results can be read as.

Origins follow the residential geography. A share of agents set by
`boundary-inflow-share`, 0.7 at the baseline, are external commuters whose home
lies on the network boundary; the remaining 30 % are residents drawn uniformly
from the local housing stock. Of the boundary agents, 45 % enter through
arterial edges and 55 % through the three motorway mouths, split between the
northern, southern and western corridors in the fixed proportions 0.30, 0.48
and 0.22. Those proportions are the shares of the 2023 Census resident
population of the corresponding sectors (North Shore 350,000, East and South
600,000, West 270,000), so the inflow mix reflects where Aucklanders live
rather than metered flow on each corridor. A share of boundary agents set by
`through-share`, 0.3 at the baseline, is pass-through traffic that crosses the
network without stopping in the cordon and is not charged.

Destinations are drawn uniformly at random, without replacement, from the
non-home building stock: each agent takes between one and four activity stops,
and non-pass-through agents append home as a final stop. There is no gravity
term, no size or attraction weighting and no observed trip-end data, so the
spatial distribution of trips is determined entirely by the composition of the
building stock the draw samples from. This is why the calibration described
below operates on that stock: adding suburban destinations changes where trips
go without altering the sampling rule.

Departure times are drawn per agent per day from two fixed hourly weight
profiles, an outbound profile peaking sharply at 08:00 and a return profile
peaking at 17:00, which give the weekday double peak its shape. The profiles
are stylised rather than fitted: no observed time-of-day distribution enters
the model. Because each agent draws independently, the hourly volume is not
assigned but emerges as a multinomial draw over the population, and the
departure minute is uniform within the drawn hour at a one-minute time step.
The simulated day begins at 05:00.

The matrix so generated is held fixed across scenarios, and mode shift is not
modelled. Every rule and every fee regime therefore faces an identical demand
realisation, which is what makes the comparison between behavioural rules
clean; but the model reproduces observed traffic *volume and spatial
distribution* (see Calibration) rather than observed travel patterns, and no
claim is made about the latter.

Routing uses congestion-aware shortest paths, which are cached per
origin-destination pair and remain fixed. This means that agents adjust their
entry and departure timing, but do not change their route to avoid the charge.
The choice of route is left for future work. The full distributions and
parameters are given in the ODD protocol (see link).

### Calibration

Modelled link volumes were calibrated against the observed ADT counts along
two axes, total volume and spatial distribution, leaving temporal peaking as a
measured residual.

Volume was matched by the number of vehicles each agent represents. Because
routes are cached and every scheduled trip completes, modelled link volumes
scale linearly in that factor, so the fit is a single division. At a factor of
160 the flow-weighted ratio of modelled to observed daily volume across all
1,634 links is 1.013, with a median per-link ratio of 1.010.

Spatial distribution was corrected by adding suburban trip ends. All 1,484
non-home destinations in the original building dataset lie inside the cordon,
so uniform sampling sent every non-home trip into the city centre. Adding
1,400 non-CBD commercial destinations across the suburbs and drawing
destinations from the combined pool brings the group-level ratios of modelled
to observed volume from a range of 0.75 to 1.80 down to 0.82 to 1.20, and the
CBD from 1.80 to 1.12. Closing the remaining gap would require observed
trip-end data, since link counts alone do not determine the
origin-destination matrix.

Temporal peaking remains the one unresolved residual, and it is uncalibrated
by construction: the departure profile is assumed rather than fitted, so
nothing in the procedure above constrains it. With volume and distribution
matched, the model's implied design-hour factor, that is the flow-weighted
peak clock-hour volume divided by the daily volume, is 0.157 against the 0.10
assumed in the capacity conversion. The assumed profile places about a fifth of
outbound departures in the 08:00 hour, which concentrates the morning peak more
sharply than a real network does, so peak-hour flow runs about 1.5 times the
design-hour capacity even when daily volumes match. Absolute LoS levels at the
peak are therefore pessimistic, and we report the difference between the
charged and uncharged cases rather than the absolute level. Fitting the profile
to an observed time-of-day distribution is the obvious next calibration step.

Each scenario runs for 14 simulated days with learning carried across days.
The design crosses two fee schemes, no charge and ToU, with the three decision
rules, giving six scenario combinations. Runs use a fixed random seed, so the
day-to-day spread reported below is variation within one seed rather than
run-to-run uncertainty.

### Agent decision models — replacement for the Q-learning paragraph

> **Q-learning (individual learning and adaptation).** Each agent learns from
> its own experience whether entering the cordon is worth repeating [19]. Its
> state is the pair of departure time band and the congestion band it last
> observed, and its action is binary, to enter or not to enter on that day. The
> departure hour itself is drawn from the demand profile and is not chosen by
> the agent, so the rule cannot retime a trip, only forgo it. The reward pays
> the value of time saved by travelling, less the fee paid and less a penalty
> in the congestion encountered, with an additional penalty for agents whose
> fee exceeds their value of time and a bonus for essential trips. Crucially,
> the fee does not enter the decision itself, only the reward that follows it,
> so the response to a charge has to be learned over successive days rather
> than appearing at once. Agents have bounded rationality with learning: they
> do not optimise globally but refine a personal routine through experience
> [20]. The equations and parameter values of all three rules are provided in
> the ODD protocol.

---

### Substantive changes from the submitted draft

1. **Platform.** The draft says the simulation was developed in Python with
   NetworkX, Shapely and NumPy. The results reported here come from the
   NetLogo model in the repository, so the description has been changed to
   match. Please confirm this is the intended description.
2. **Network size.** "1,542 nodes and 2,691 links" describes the input file.
   The model collapses segments that share a node pair, so it simulates 1,634
   links. Both figures are now given.
3. **Congestion definition.** The draft defines congestion as V/C above 0.85
   on a single threshold. The model grades LoS on class-specific HCM
   thresholds against an hourly capacity derived from observed ADT and
   k = 0.10, so the definition has been rewritten and the k sensitivity test
   noted.
4. **Population.** The agent count is unchanged at 2,500, but the calibrated
   scale factor of 160 vehicles per agent is now stated, since every volume
   and capacity number depends on it.
5. **Calibration.** New subsection. The submitted draft reports no calibration
   against observed counts.
6. **Run length and design.** 20 days becomes 14 days, and the nine-cell
   design (three fee schemes) becomes six cells, because the flat NZ$2 charge
   was not re-run on the calibrated model. If the flat charge is to stay in
   the paper, that run is still outstanding.
7. **Travel demand rewritten to match the code (2026-07-29).** The draft, and
   the earlier version of this file, said that "TomTom Move data for August
   2024 determines the time-of-day profile" and that NZTA TMS screenline counts
   "determine the inflow volume on each corridor", each corridor releasing
   vehicles scaled to its count. **Neither is implemented.** There is no TomTom
   file in the repository and no procedure reads one; the time-of-day shape
   comes from two hardcoded hourly weight lists (`outbound-demand` and
   `return-demand` in `akl_pricing.nls`). The screenline figures exist in the
   code only as the reporters `motorway-aadt` and `tms-screenlines`, which no
   procedure ever calls — they document the targets the corridor shares were
   chosen by hand to reflect, and even then the shares in `pick-home` (0.30 /
   0.48 / 0.22) track the Census sector populations rather than the counts
   (which would imply 0.40 / 0.30 / 0.30). Destinations are drawn uniformly
   from the non-home building stock, so there is no estimated OD matrix at all.
   The section has been rewritten to describe the generator that is actually
   run. This matters beyond bookkeeping: the temporal residual (implied
   k = 0.157 against 0.10) is not a shortfall against a fitted profile, it is
   the consequence of there being no fitted profile.
8. **Q-learning action space.** The draft says the agent "decides whether to
   enter now, shift the time of entry earlier or later, or forgo the trip
   altogether", and later credits the rule with "systematic time-shifting away
   from priced peaks". The implemented rule (`decide-qlearning` and `q-update`
   in `akl_pricing.nls`) chooses between two actions only, enter or do not
   enter; the departure hour is drawn from the demand profile each day. The
   time band appears in the state, not in the action. The runs bear this out:
   the mean fee paid per entering agent is unchanged over the fortnight (2.83
   on day 1, 2.75 on day 14), so no retiming occurs. The description has been
   corrected, and the claim of systematic time-shifting removed. If
   time-shifting is wanted as a result, the action space has to be extended
   first.

---

<a id="results"></a>

## Results

*Source file: `results_revised.md`*


Replaces the whole *Results* section. All numbers come from the calibrated
model, 14 simulated days, seed 11, and are listed with their source table in
`numbers.md`.

---

### Results

#### Comparing behavioural decisions

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

#### Why the three rules reach their results differently

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

#### Spatial redistribution under ToU

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

---

<a id="behavioural-extensions"></a>

## Behavioural extensions

*Source file: `behavioural_extensions.md`*


*Runs of 2026-07-27 and 2026-07-28, calibrated model, 14 simulated days, seed 11.*

The submitted model gives an agent one way to respond to a cordon charge: do not
travel. Real drivers also retime and reroute. These runs add those two channels,
one at a time and then together, so the effect of the charge can be separated
from the effect of the modelling assumption about what an agent is allowed to do.

| Arm | Departure hour | Route | Experiment | File tag |
|---|---|---|---|---|
| Base | fixed by demand profile | fixed shortest path | `retiming` (OFF cells) | — |
| Retime | may move ±1 hour | fixed | `retiming` (ON cells) | `_rt` |
| Reroute | fixed | congestion-dependent, per time band | `rerouting` | `_rr` |
| Both | may move ±1 hour | congestion-dependent | `retiming-rerouting` | `_rt_rr` |

### Precondition: the charged hour now matches the travelled hour

Before retiming could mean anything, one defect had to be fixed. `trip-hour`,
the hour whose fee the agent pays, was drawn independently of `depart-tick`, the
hour it actually travels in. An agent could be charged the 08:00 peak fee for a
trip it made at 14:00, and a retiming rule would have moved the fee without
moving the traffic. `trip-hour` is now read off the departure the agent makes.

**This changes the base numbers**, so the base arm here supersedes the
`paper-figs` numbers in `numbers.md`:

| Rule | ToU reduction in peak inner V/C, paper-figs | Base arm here |
|---|---|---|
| Pay | 23.0 % | **11.7 %** |
| Oscillate | 0.2 % | **0.0 %** |
| Learn | 23.8 % | **38.7 %** |

The direction of the story is unchanged (two rules respond, one does not) but
the magnitudes move substantially, and the new figures are the defensible ones.

### Departure-time choice

An agent may depart one clock hour earlier or later. The window is deliberately
narrow: moving a commute by more than an hour is activity rescheduling, a
different behavioural claim from the marginal shift a ToU schedule is designed
to induce. Each rule chooses in its own idiom — the price rule minimises fee
plus schedule delay, the expectation rule moves toward the hour it predicts will
be quietest, and the learner gets two extra actions (travel an hour earlier,
travel an hour later) alongside travel-as-planned and stay-out.

Schedule delay is priced at `sched-delay-cost` × VoT per hour, 1.6× for arriving
late, following the standard formulation. At the default 0.6 a median commuter
values an hour's shift at about NZ$6, against a maximum ToU saving of NZ$2.

**Result (mean ± day-to-day SD over 14 days, No-Charge → ToU):**

| Rule | Arm | inner | boundary | peripheral | entries |
|---|---|---|---|---|---|
| Pay | fixed | 0.113 → 0.100 (−11.7 %) | 0.344 → 0.258 (−25.2 %) | 0.074 → 0.063 (−15.7 %) | −23.1 % |
| Pay | **retime** | 0.113 → 0.093 (**−17.8 %**) | 0.344 → 0.240 (−30.4 %) | 0.074 → 0.060 (−20.1 %) | −23.1 % |
| Oscillate | fixed | 0.170 → 0.170 (−0.0 %) | 0.739 → 0.728 (−1.5 %) | 0.118 → 0.117 (−0.9 %) | −0.9 % |
| Oscillate | **retime** | 0.162 → 0.162 (0.0 %) | 0.732 → 0.732 (0.0 %) | 0.111 → 0.111 (0.0 %) | 0.0 % |
| Learn | fixed | 0.129 → 0.079 (−38.7 %) | 0.373 → 0.207 (−44.6 %) | 0.073 → 0.053 (−27.2 %) | −36.1 % |
| Learn | **retime** | 0.127 → 0.110 (**−13.7 %**) | 0.468 → 0.375 (−19.7 %) | 0.082 → 0.070 (−14.4 %) | −11.5 % |

Share of entrants who move their departure: Pay 2.7 % (all earlier), Oscillate
7.2 %, Learn 66.7 % (evenly split earlier and later).

**Three findings.**

1. **For the price rule the charge works better when retiming is possible**, and
   only 2.7 % of entrants need to move. The reduction rises from 11.7 % to
   17.8 % because the agents who move are exactly those facing the $6 peak, so a
   small share of the population is a large share of the peak. The morning peak
   falls 21.8 % rather than 15.9 %. This is the peak-spreading mechanism a ToU
   schedule is designed around, and the base model could not express it at all.
2. **For the learner the charge works much worse.** Given somewhere to move, the
   agent stops forgoing the trip: entries under ToU fall only 11.5 % instead of
   36.1 %, and the reduction in peak V/C drops from 38.7 % to 13.7 %. **A model
   whose only response is "do not travel" overstates what the charge achieves.**
   Part of the rise in entries is mechanical, since epsilon-greedy exploration
   over four actions travels three times in four rather than one in two. Netting
   that out at the day-14 exploration rate, the greedy policy travels 6.5 % of
   the time without retiming and 30 % with it, so the effect survives the
   correction.
3. **For the expectation rule nothing changes, and the two fee regimes become
   bit-identical.** Its agents compare predicted congestion with a comfort
   threshold of 0.6, but calibrated congestion runs at 0.09 to 0.17, so the
   prediction never approaches the threshold and the small adjustment the fee
   makes to it never flips a decision. Its 7.2 % of retimers move for congestion
   reasons alone, identically with and without the charge.

### Route choice

Routes are recomputed on congested travel times, the free-flow time divided by
the BPR speed factor at the link's current V/C, and cached per OD pair and time
band with the cache cleared daily. An agent therefore takes the route that was
quick in that band as observed that day, rather than a free-flow route fixed for
the whole run. Four bands, not 24 hours, keep the cache inside the shared heap;
a measured path costs 6.5 ms, which puts the overhead near 8 minutes per run.

**Why this arm matters more than its size suggests.** With fixed routes the
finding "the charge does not displace traffic onto the ring" is close to
untestable: a deterred trip ceases to exist, so there is nowhere for it to
reappear. Only when an agent can keep its trip and go around the cordon does
displacement become a thing the model could show. This arm is therefore the
proper test of the paper's displacement claim.

**A 2-day probe already shows the arm bites**, comparing fixed against adaptive
routes under ToU with retiming off:

| | inner | boundary | peripheral | wall clock |
|---|---|---|---|---|
| fixed routes | 0.110 | **0.267** | 0.063 | 1,699 s |
| route choice | 0.110 | **0.168** | 0.061 | 1,821 s |

Peak V/C on the cordon boundary falls by 37 % simply by letting agents avoid
congestion, with the cordon interior unchanged. Fixed shortest paths were
concentrating load on a handful of approach links; congestion-aware routing
spreads it. The overhead is 7.2 %, matching the 6.5 ms per path measured
earlier. Levels are therefore not comparable across arms — the routing
assumption moves the baseline — so within each arm the No-Charge to ToU
difference is what should be read.

**What route choice responds to, and what it does not.** Routes are chosen on
congestion, not on the charge. In this model the fee is paid for entering the
cordon, which is decided by the behavioural rule, and a CBD-bound agent cannot
avoid it by taking another road, because its destination is inside. So this arm
tests whether congestion-aware routing changes the picture, not whether drivers
drive around the cordon to dodge the charge. Testing the latter would require
the fee to enter the route cost, which is a further extension.

**Result, all four arms (14-day mean, No-Charge → ToU):**

| Rule | Arm | inner | boundary | peripheral | entries |
|---|---|---|---|---|---|
| Pay | base | 0.113 → 0.100 (−11.7 %) | 0.344 → 0.258 (−25.2 %) | 0.074 → 0.063 (−15.7 %) | −23.1 % |
| | retime | 0.113 → 0.093 (−17.8 %) | 0.344 → 0.240 (−30.4 %) | 0.074 → 0.060 (−20.1 %) | −23.1 % |
| | reroute | 0.164 → 0.121 (**−25.9 %**) | 0.241 → 0.162 (−33.0 %) | 0.069 → 0.061 (−12.3 %) | −23.3 % |
| | both | 0.164 → 0.127 (−22.7 %) | 0.241 → 0.162 (−33.0 %) | 0.069 → 0.066 (−4.0 %) | −24.8 % |
| Oscillate | base | 0.170 → 0.170 (−0.0 %) | 0.739 → 0.728 (−1.5 %) | 0.118 → 0.117 (−0.9 %) | −0.9 % |
| | retime | 0.162 → 0.162 (0.0 %) | 0.732 → 0.732 (0.0 %) | 0.111 → 0.111 (0.0 %) | 0.0 % |
| | reroute | 0.231 → 0.233 (−1.1 %) | 0.361 → 0.441 (+22.3 %) | 0.128 → 0.115 (−9.9 %) | −1.6 % |
| | both | 0.238 → 0.238 (0.0 %) | 0.390 → 0.390 (0.0 %) | 0.102 → 0.102 (0.0 %) | 0.0 % |
| Learn | base | 0.129 → 0.079 (**−38.7 %**) | 0.373 → 0.207 (−44.6 %) | 0.073 → 0.053 (−27.2 %) | −36.1 % |
| | retime | 0.127 → 0.110 (−13.7 %) | 0.468 → 0.375 (−19.7 %) | 0.082 → 0.070 (−14.4 %) | −11.5 % |
| | reroute | 0.138 → 0.114 (−17.6 %) | 0.240 → 0.160 (−33.4 %) | 0.068 → 0.054 (−20.2 %) | −35.7 % |
| | both | 0.167 → 0.142 (−15.1 %) | 0.229 → 0.211 (−7.9 %) | 0.081 → 0.069 (−15.5 %) | −12.0 % |

**Four findings.**

1. **Routing changes where congestion sits far more than the charge does.**
   Compare the no-charge baselines: letting agents avoid congested links moves
   peak boundary V/C from 0.344 to 0.241 for Pay, from 0.739 to 0.361 for
   Oscillate and from 0.373 to 0.240 for Learn, while inner-cordon V/C *rises*
   (0.113 → 0.164, 0.170 → 0.231, 0.129 → 0.138). Fixed shortest paths were
   funnelling traffic along a few approach arterials; adaptive routing spreads
   it, some of it through the CBD grid. The single largest effect in this whole
   set of runs is a modelling assumption, not a policy.
2. **The price rule's result is robust and strongest with routing.** Pay reduces
   peak inner V/C by 12, 18, 26 and 23 per cent across the four arms. Every arm
   agrees on the sign and the rough size, and the charge also lowers boundary
   V/C in all four.
3. **The learner's headline is the fragile one.** Learn gives 39 % in the base
   arm and 14 to 18 % in every arm where the agent has an alternative to
   staying home. The base figure is the outlier, not the norm, and it is high
   precisely because forgoing the trip is the only option the base model offers.
4. **Displacement is still not demonstrated, and this arm is where it could
   have been.** In the reroute arms the boundary falls together with the
   interior for both responsive rules (−33.0 % and −33.4 %). The one positive
   number, Oscillate's +22.3 % at the boundary, does not survive its own
   variance: no charge 0.361 ± 0.091 against ToU 0.441 ± 0.132 over 14 days,
   with the daily series overlapping throughout. On a single seed that is
   noise, not displacement. The claim that pricing does not push traffic
   outward therefore survives the extension that could most easily have broken
   it — with the caveat in the paragraph above about what routing responds to.

### What each option buys, side by side

Reading the two opt-in figures together answers the question a planner would
actually ask: if drivers can do this, does the charge still work?

| | Departure-time choice | Route choice |
|---|---|---|
| Who uses it | 2.7 % of Pay entrants, 7.2 % of Oscillate, 66.7 % of Learn | everyone, by construction |
| Entry rate | unchanged for Pay (0.40 both), **Learn 0.34 → 0.62** | unchanged for all three (Pay 0.40, Learn 0.34) |
| Peak inner V/C under ToU | Pay 0.100 → 0.093, Learn 0.079 → 0.110 | Pay 0.100 → 0.121, Learn 0.079 → 0.114 |
| ToU reduction | Pay 12 → 18 %, Learn 39 → 14 % | Pay 12 → 26 %, Learn 39 → 18 % |
| Equity channel | yes, but reaches only the poorest 3 % | none: routes respond to congestion, not to the fee |

The two options work on different quantities. **Retiming changes how many trips
are made** — it is the only extension that moves the entry rate, and it moves it
sharply for the learner, which is why its measured effect collapses. **Rerouting
leaves the number of trips exactly as it was** (entry rates are identical to
three decimal places) and changes only where those trips go, which is why the
no-charge baseline shifts so much while the charge's job stays the same.

That distinction matters for reading any single number out of this model: a
result that depends on how many people travel is sensitive to the retiming
assumption, and a result about where congestion appears is sensitive to the
routing assumption. The displacement question is of the second kind, which is
why it could not be tested before this arm existed.

### Figures

- `output/figures/retiming_profiles.png` — hour-of-day inner-cordon V/C, one
  panel per rule, fixed-hour arm dashed and retiming arm solid, $6 windows
  shaded. The Learn panel is the clearest: the fixed-hour ToU line sits far
  below everything, the retiming ToU line climbs back toward the no-charge line.
- `output/figures/retiming_summary.png` — ToU reduction in peak V/C and in
  entries, both arms, by rule.
- `output/figures/arms_comparison.png` — the headline reduction by rule and arm
  (left) beside the no-charge boundary load by arm (right), which is the figure
  that makes the point about the action space.
- `output/figures/equity_by_income.png` — who the charge removes, by VoT
  quintile: agents still entering under the price rule at each fee step (left),
  and the learner's value of entering at the $6 peak, as implemented and under a
  corrected benefit scale (right). Derived, not measured — see the caveat above.
- `output/figures/optin_retiming.png`, `output/figures/optin_rerouting.png` —
  peak V/C and entry rate with each option off and on, no charge against ToU.

Regenerate with `plot_retiming.py` and `plot_arms.py` in
`netlogo/sensitivity_experiment/`.

### Who bears the charge, and what the two extensions do about it

**Status of this section.** The numbers below are derived from the model's own
decision and reward functions applied to the calibrated VoT distribution
(lognormal, median NZ$10/h), not measured in the runs. No run has recorded entry
by income band: the `burden-quintile` reporter exists but was never included in
an experiment, and it is in any case defective — it computes only the 20th and
80th percentiles, so `burden-quintile` 2, 3 and 4 all return the whole
population rather than the middle bands. Nothing published so far depends on it.
Measuring the distributional result properly needs a run that records entries by
VoT band, which has not been done.

#### The price rule is strongly regressive

Under the exponential-decay rule the deterrent effect scales with the fee
divided by the square of the agent's value of time, because price sensitivity is
itself set inversely to VoT. At the NZ$6 peak fee:

| Quintile | median VoT | fee as hours of own time | entry, no charge | entry, $6 | reduction |
|---|---|---|---|---|---|
| Q1 | $4.6 | **1.30 h** | 0.545 | 0.224 | **−58.8 %** |
| Q2 | $7.3 | 0.82 h | 0.524 | 0.323 | −38.4 % |
| Q3 | $10.0 | 0.60 h | 0.524 | 0.404 | −23.0 % |
| Q4 | $13.7 | 0.44 h | 0.525 | 0.456 | −13.0 % |
| Q5 | $21.5 | **0.28 h** | 0.515 | 0.486 | **−5.7 %** |

The same charge costs the bottom quintile 1.3 hours of its own valuation and the
top quintile 0.28 hours, and removes ten times as large a share of its trips.
**Most of the congestion relief in the base model is bought by low-income agents
giving up travel.** That is a standard result for a flat cordon charge, but the
paper does not currently state it, and it is measurable here.

#### Departure-time choice is an escape valve, but only for the poorest 3 %

Retiming is worth it when the fee saved exceeds the schedule delay, priced at
`sched-delay-cost` × VoT per hour. A one-hour shift out of the peak saves NZ$2
against a cost of 0.6 × VoT early or 0.96 × VoT late, so it pays only for agents
below $3.33/h (early) or $2.08/h (late):

| | break-even VoT | share of population |
|---|---|---|
| depart an hour earlier | < $3.33 | **3.4 %** |
| depart an hour later | < $2.08 | 0.5 % |

The runs match this closely: 2.7 % of Pay entrants retimed, **all of them
earlier**, none later. So the option exists exactly for the group the charge
hits hardest, which softens the regressive effect at the margin — those agents
keep their trip instead of losing it — but it reaches only the bottom few per
cent. For everyone else an hour of their own time is worth more than the
NZ$2 differential, which is the same finding as in the retiming section seen
from the distributional side: **the peak-to-shoulder differential is too small
to buy retiming from anyone but the poorest.**

#### Route choice has no distributional channel at all

Routes here respond to congestion, not to the fee, and every CBD-bound agent
pays the same charge whichever road it takes. Rerouting therefore changes where
congestion sits without changing who pays or who is deterred. Its large effects
on the boundary are an efficiency result, not an equity one.

#### The learner's income gradient is an artefact

Under Q-learning the reward for entering is `vot/10 − fee − 3 × V/C`. The travel
benefit is one tenth of the agent's hourly VoT, about NZ$1 for a median agent,
while the fee is in full dollars. Evaluated at the calibrated congestion level,
entering scores worse than staying out for **every** quintile at every fee in
the schedule, from −8.19 for Q1 to −4.18 for Q5 at $6. The rule therefore
deters across the whole income distribution rather than concentrating on the
poor, and the income gradient visible in the price rule disappears.

This is a scaling choice, not a behavioural finding. Setting the travel benefit
to half an hour of the agent's own time instead — a defensible reading of a
commute — flips the pattern to the expected one: at $6, entering scores −6.34
for Q1, −1.51 for Q3 and **+4.43** for Q5, so low income is priced off and high
income is not. **The Q-learning results in this paper rest on two arbitrary
settings, the benefit scale and the action space**, and the sensitivity of the
headline to the second (39 % against 14 %) suggests the first deserves a test
too.

### A declined CBD trip cancels the agent's whole day

Measured at setup, not inferred: of 2,500 agents, 544 are single-stop
pass-through traffic and the remaining 1,956 carry two or more destinations
(2.98 on average). Of the 1,500 agents with a CBD destination, **all 1,500 have
more than one destination**, averaging 3.76. Every CBD-bound agent in this model
is therefore a multi-stop agent.

When such an agent declines the charge, `new-day-decisions` sets `active?` to
false for the day, so its non-CBD stops are cancelled along with the CBD one.
Summed over the CBD-bound population that is 3,171 non-CBD trips. Under the
price rule ToU moves entry from 0.523 to 0.402, roughly 300 agents, each
carrying about two non-CBD stops, so of the order of 100,000 vehicle-trips per
day leave the network outside the cordon for no modelled reason.

This inflates precisely the results the paper leans on. The peripheral
reductions of 15.7 % for Pay and 27.2 % for Learn, and part of the
no-displacement conclusion, are produced by traffic that a real network would
still be carrying: a driver who abandons a city-centre appointment still runs
the suburban errands. The code comment above the line says "suppressed CBD
destinations are skipped for the day", which is the intended behaviour; the code
stops the agent instead.

**The k-factor sensitivity does not address this.** `k-factor` enters the model
in one place, `r-cap-hr = ADT × k-factor`, which is the denominator of the flow
V/C used for LoS grading. At a fixed seed the traffic is bit-identical across
k = 0.08, 0.10 and 0.12; only the grading changes. That sweep therefore tests
the capacity assumption, and says nothing about whether demand is over-suppressed.

### What this means for the paper

The behavioural-assumption claim gets sharper, and moves one level up. It is not
only that the choice of decision rule changes the predicted effect of the
charge. It is that **the choice of action space does too, and by a comparable
amount**: for the learner, allowing an hour of flexibility moves the predicted
reduction from 38.7 % to 13.7 %, a bigger swing than the gap between the three
rules in the base arm. An appraisal that reports a single number without stating
what its agents were allowed to do is under-specified.

Concretely, three things should change in the paper.

1. **Report the range, not one cell.** Across arms the ToU reduction in peak
   inner-cordon V/C is 12 to 26 per cent for Pay, 14 to 39 per cent for Learn
   and zero for Oscillate. The width of the first two ranges comes from the
   action space alone, with the rule, network, demand and fee schedule held
   fixed.
2. **Retire the base-arm Learn number.** 38.7 % is an artefact of a model in
   which the only response to a charge is to stay home. Quote 14 to 18 per cent,
   from the arms where the agent has somewhere to go.
3. **Keep the displacement conclusion, and say why it now means more.** It was
   previously close to untestable, because a deterred trip ceased to exist. With
   congestion-aware routing the traffic is still there and can move, and the
   boundary still falls with the interior. The remaining gap is that routing
   here responds to congestion rather than to the charge, so cordon-dodging
   proper is still untested.

---

<a id="conclusion"></a>

## Conclusion

*Source file: `conclusion_revised.md`*


Replaces the *Conclusion* section. The submitted version opens with "All three
reduce peak-hour V/C inside the cordon under the proposed ToU schedule", which
the calibrated runs contradict, and it rests the contribution on a claim about
pathways that the new results state far more sharply.

---

### Conclusion

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

Two further sets of runs show that the assumption about *what an agent may do*
matters as much as the assumption about how it decides. Allowing a departure to
move by one hour, or allowing routes to respond to congestion, changes the
predicted reduction in peak inner-cordon V/C from 12 to 26 per cent for the
price rule and from 39 to 14 per cent for the learner, with the network, the
demand and the fee schedule unchanged. The two options act on different
quantities: departure-time choice changes how many trips are made, and is the
reason the learner's headline collapses, because an agent given somewhere to
move stops forgoing the trip; route choice leaves the number of trips
untouched and changes only where they go, moving a third of the load off the
cordon boundary before any charge is applied. The single largest effect
observed across all of these runs is therefore a modelling assumption rather
than a policy.

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
distribution. Two axes of that demand are calibrated to observed Auckland
Transport daily counts, total volume and spatial distribution, giving a
flow-weighted modelled to observed ratio of 1.013 across all 1,634 links; the
temporal axis is not, which is why the assumed profile concentrates the morning
peak more sharply than the real network does, why absolute peak-hour Level of
Service reads pessimistically, and why we report differences between charged
and uncharged cases rather than levels. The model therefore reproduces observed
traffic volume and its spatial spread, not observed travel patterns. Because
every rule and fee regime faces the same demand realisation, this bounds the
external reading of the levels without weakening the comparison between rules,
which is what the study is for. All runs use a single random seed, so the day-to-day
spreads describe variation within one seed. The learning rule's action space is
binary, to enter or not to enter, so the model cannot produce departure-time
substitution and the reductions reported here are deterrence rather than peak
spreading.

One limitation is structural rather than parametric and bounds the results
outside the cordon in particular. Every agent with a city-centre destination in
this model also has others, 3.76 on average, and an agent that declines the
charge is deactivated for the whole day, so its suburban stops are cancelled
with its city-centre one. In the order of a hundred thousand vehicle-trips a
day therefore leave roads outside the cordon for no behavioural reason, which
inflates the peripheral reductions and flatters the no-displacement result. A
driver who abandons a city-centre appointment would in reality still run the
other errands. Note that the k-factor sensitivity does not bear on this: that
parameter sets the denominator of the flow V/C used for grading, and traffic is
identical across its values at a fixed seed, so it tests how congestion is
measured rather than how much demand there is.

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

### What changed and why

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

---

<a id="conclusions-as-bullets"></a>

## Conclusions as bullets

*Source file: `conclusions_bullets.md`*


Calibrated NetLogo model, 14 simulated days, seed 11. Every number traces to
`numbers.md` or `behavioural_extensions.md`.

### The headline

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

### By decision rule

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

### What each behavioural option does

- **Departure-time choice changes how many trips are made.** It is the only
  extension that moves the entry rate: Learn 0.34 → 0.62, so its measured
  benefit collapses. Pay's entry rate is unchanged because only 2.7 % of its
  entrants shift.
- **Route choice changes where the trips go, not how many.** Entry rates are
  identical to three decimals; the no-charge baseline moves instead.
- **So**: a result that depends on how many people travel is sensitive to the
  retiming assumption; a result about where congestion appears is sensitive to
  the routing assumption.

### Displacement

- **The charge does not push traffic outward**, and this now means something.
  Under fixed routes a deterred trip simply ceased to exist, so displacement was
  close to untestable. With congestion-aware routing the traffic is still there
  and free to move, and the boundary still falls with the interior (−33 % for
  both responsive rules).
- **The one positive number is noise.** Oscillate's +22 % at the boundary is
  0.361 ± 0.091 against 0.441 ± 0.132 over 14 days, overlapping throughout.
- **Caveat**: routes here respond to congestion, not to the charge. A CBD-bound
  agent pays whichever road it takes, so cordon-dodging proper is still untested.

### Who pays

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

### Demand provenance: what is fitted and what is assumed

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

### Things the paper must not claim

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

### The largest technical limitation: a declined CBD trip cancels the whole day

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

### Open items

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

---

<a id="numbers-and-sources"></a>

## Numbers and sources

*Source file: `numbers.md`*


Model: calibrated NetLogo model (scale-factor 160, suburban destinations),
14 simulated days, seed 11, slider baselines. Generated by
`netlogo/sensitivity_experiment/paper_numbers.py`; raw output in
`output/tables/paper_numbers.txt`.

### Daily peak V/C and entry rate — `output/tables/days_<Rule>_<fee>.csv`

Written by `save-records` in the `paper-figs` experiment. Mean ± SD over the
14 days; the position values are the daily peak of the position-mean V/C.

| Rule | inner NC | inner ToU | red. | boundary NC | boundary ToU | red. | periph. NC | periph. ToU | red. | entry NC | entry ToU | red. |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Pay | 0.122 ± 0.015 | 0.094 ± 0.013 | 23.0 % | 0.359 ± 0.050 | 0.274 ± 0.033 | 23.5 % | 0.075 ± 0.006 | 0.064 ± 0.007 | 14.7 % | 0.522 | 0.397 | 23.9 % |
| Oscillate | 0.173 ± 0.021 | 0.173 ± 0.020 | 0.2 % | 0.763 ± 0.093 | 0.723 ± 0.097 | 5.3 % | 0.120 ± 0.013 | 0.118 ± 0.017 | 2.2 % | 0.914 | 0.899 | 1.6 % |
| Learn | 0.122 ± 0.013 | 0.093 ± 0.025 | 23.8 % | 0.394 ± 0.038 | 0.248 ± 0.068 | 37.0 % | 0.074 ± 0.005 | 0.058 ± 0.010 | 22.3 % | 0.539 | 0.343 | 36.3 % |

### Hour-of-day inner V/C — `output/tables/hourly_<Rule>_<fee>.csv`

Written by `save-hourly`. Mean over days 8 to 14; "07–09" is clock hours 07
and 08, matching the two-hour bands of the LoS figure.

| Rule | AM 07–09 | PM 16–18 | all day |
|---|---|---|---|
| Pay | 0.0524 → 0.0403 (−23.1 %) | 0.0312 → 0.0257 (−17.7 %) | 0.0202 → 0.0159 (−21.3 %) |
| Oscillate | 0.0805 → 0.0819 (+1.8 %) | 0.0581 → 0.0599 (+3.2 %) | 0.0372 → 0.0368 (−1.1 %) |
| Learn | 0.0501 → 0.0254 (−49.3 %) | 0.0356 → 0.0172 (−51.8 %) | 0.0216 → 0.0110 (−49.1 %) |

### Network-wide LoS — `output/tables/los_hours_<Rule>_<fee>.csv`

Written by `save-los-hours`. Flow-weighted % of traffic on links at LoS E or
F, days 8 to 14.

| Rule | all day | 07–09 | day 1 → day 14 (ToU) |
|---|---|---|---|
| Pay | 56.3 → 49.4 (−7.0 pp) | 64.2 → 59.6 (−4.6 pp) | 50.6 → 50.4 (flat) |
| Oscillate | 71.8 → 71.5 (−0.4 pp) | 76.3 → 76.5 (+0.2 pp) | 59.2 → 71.8 (flat from day 2) |
| Learn | 58.0 → 40.0 (−18.0 pp) | 64.5 → 48.8 (−15.7 pp) | 56.2 → 37.8 (still falling) |

### Link-level map — `output/tables/links_<Rule>_<fee>.csv`

Written by `save-links`. Mean change in per-link peak flow V/C under ToU
(negative is a reduction); the map plots the same quantity per link.

| Rule | inner | boundary | peripheral |
|---|---|---|---|
| Pay | −0.386 | −0.361 | −0.169 |
| Oscillate | −0.005 | −0.000 | +0.031 |
| Learn | −0.289 | −0.261 | −0.226 |

### Entry-rate trajectory — `output/tables/days_<Rule>_<fee>.csv`

Share of agents entering the cordon, first and last simulated day, and the mean
fee paid per *entering* agent (mean_fee ÷ attendance).

| Rule | fee | entry day 1 | entry day 14 | change | fee/entrant d1 → d14 |
|---|---|---|---|---|---|
| Pay | no charge | 0.517 | 0.523 | +1.2 % | — |
| Pay | ToU | 0.400 | 0.387 | −3.3 % | 2.84 → 2.78 |
| Oscillate | no charge | 0.725 | 0.927 | +27.8 % | — |
| Oscillate | ToU | 0.569 | 0.913 | +60.6 % | 2.83 → 2.82 |
| Learn | no charge | 0.505 | 0.579 | +14.7 % | — |
| Learn | ToU | 0.505 | 0.242 | −52.0 % | 2.83 → 2.75 |

Reading: Pay responds in full on day 1 and stays; Learn starts at the no-charge
value and slides for the whole fortnight; Oscillate is deterred on day 1 only,
then returns to near-universal entry under both regimes. The flat fee per
entrant under Learn shows the effect is deterrence, not retiming.

### Calibration — `output/tables/calibration_summary.txt`

- Matched links: 1,634 of 1,634; flow-weighted modelled/observed ratio 1.013,
  median per-link ratio 1.010, at scale-factor 160.
- Group ratios after calibration: CBD 1.12, East 1.20, MWY 0.82, West 1.04
  (before: 1.80, 1.30, 0.75, 0.76).
- Implied design-hour factor k = 0.157 flow-weighted, 0.174 median, against
  the 0.10 used in the capacity conversion.

### Sensitivity checks — `output/tables/sensitivity-*.csv`

- k-factor at 0.08 / 0.10 / 0.12: ToU lowers the LoS E/F share in every group
  at every k, so the direction does not depend on the capacity assumption.
- Exp-Decay base-beta 0.25 / 0.5 / 1.0: ToU reduction 11.7 / 23.0 / 25.4 %.
- Q-learning alpha 0.05 / 0.1 / 0.2: 19.2 / 23.8 / 23.8 %; epsilon 0.2 / 0.4 /
  0.6: 31.7 / 23.8 / 26.0 %.
- El Farol threshold 0.5 / 0.6 / 0.7: 6.6 / 0.2 / 3.6 %; five-seed replication
  at threshold 0.6 gives −1.7 % ± 2.7 pp, range −5.8 % to +1.1 %.

### Numbers in the submitted draft that no longer hold

| Draft | Now | Why |
|---|---|---|
| Pay: inner peak V/C 0.47 → 0.36, −23 % | 0.122 → 0.094, −23.0 % | Calibration lowered the level; the percentage happens to be nearly identical |
| Pay: entry 0.53 → 0.40 | 0.522 → 0.397 | Essentially unchanged |
| Learn: 0.40 → 0.32, −19 %; entry 0.45 → 0.35 | 0.122 → 0.093, −23.8 %; entry 0.539 → 0.343 | Larger effect after calibration |
| Oscillate: 0.465 → 0.459, −1 % | 0.173 → 0.173, −0.2 % | Same conclusion, new level |
| Oscillate: day-to-day SD ≈ 0.24, "5 times higher" | SD 0.021 against 0.015 and 0.013 | **The oscillation was an artefact of the uncalibrated network.** El Farol is no longer volatile, only unresponsive |
| Baseline boundary V/C 0.66 exceeds inner 0.40–0.47 | boundary 0.36–0.76 exceeds inner 0.12–0.17 | Same qualitative ordering |
| Flat NZ$2: Pay −15.5 %, ToU −23.4 %; Learn flat −18 %, ToU +1 % | not re-run | The flat charge has no calibrated run; drop Fig. 5 or re-run |
| "Each scenario runs for 20 simulated days", nine combinations | 14 days, six combinations | New run design |
| Q-learning "shift the time of entry earlier or later"; "systematic time-shifting away from priced peaks" | binary enter / do not enter | The implemented action space has two actions; fee per entering agent is flat over the run, so no retiming happens |

---

<a id="decisions-log"></a>

## Decisions log

*Source file: `decisions_log.md`*


Why things were done the way they were, including the options rejected. The
results themselves are in `numbers.md`, `behavioural_extensions.md` and
`conclusions_bullets.md`; this file records the reasoning that produced them, so
that a reviewer question of the form "why did you not just…" has an answer.

---

### 1. Running the two pending experiments (2026-07-26/27)

**`hourly-profile` and `los-bands` were run at 14 days, not 5.** The XML said 5
days at the time. The plotting scripts discard the first 7 days as burn-in, so
5-day tables would have produced empty figures, and 14 days matched the
sensitivity tables already in the paper.

**`JAVA_HOME` must be set on this host.** NetLogo 6.4.0's bundled `runtime`
directory contains no `java.exe`, so the runner's bundled-JRE fallback fails.
JDK 17 at `C:\Program Files\Java\jdk-17` is used instead. Recorded in
`LOS_IMPLEMENTATION.md` because it will bite the next person.

**Threads 8 for 6-cell runs, 6 for larger ones.** GC was checked directly
(`jstat`) rather than assumed: 72 s of GC over 40 min, no full collections, so
memory was not the constraint and the run was left alone.

### 2. Bugs found and fixed, in the order they surfaced

| What | Why it mattered | Fix |
|---|---|---|
| `pricing-init` set `hr-cur-hour` from `current-hour`, which reads `ticks`, before `reset-ticks` | `setup` failed outright — the model could not run at all, in the GUI or headless | used `sim-start-hour`, then moved `reset-ticks` to the top of `setup` as the root fix |
| `aggregate_sensitivity.py` counted the step-0 row | deflated means, inflated SDs | filtered (pre-existing, already recorded) |
| `trip-hour` (the charged hour) drawn independently of `depart-tick` (the travelled hour) | an agent could pay the 08:00 peak fee for a 14:00 trip; retiming would have moved the fee without moving the traffic | `trip-hour` is now read off the departure the agent makes |
| `burden-quintile` returns the whole population for q = 2, 3, 4 | the equity reporter is unusable as written | **not fixed** — user asked to stop changing the model; recorded as a limitation instead |

**The `trip-hour` fix invalidated the existing control arm.** Once the charged
hour changed, the `paper-figs` runs were no longer a valid "no retiming"
baseline, so both arms of the retiming experiment were re-run together rather
than comparing new runs against old ones. This is why the base-arm numbers in
`behavioural_extensions.md` differ from those in `numbers.md`.

### 3. Scope decisions

**Flat NZ$2 dropped (user decision).** No calibrated run exists for it. The
consequence is that the draft's Fig. 5, which decomposes the flat charge from
the ToU increment, has no basis and must be removed or the run commissioned.

**Deliverable is revised text plus figures, not an edited `.docm` (user
decision).** The Word file carries macros, so editing it risks structural damage
for no gain.

**A separate `paper-figs` experiment was needed** because no calibrated run had
exported `days_*` (entry rate, position V/C) or `links_*` (per-link peak V/C for
the map). The sensitivity experiments recorded metrics but called no `final`
export.

**`map_baseline_los.png` is produced but not recommended.** It grades links on
the daily peak of the flow EMA, which saturates at grade F almost everywhere,
so the map carries no information. The LoS band figure says the same thing with
the time dimension intact.

### 4. Departure-time choice (retiming)

**Window is ±1 hour (user decision, was ±2).** Moving a commute by more than an
hour is activity rescheduling, a different behavioural claim from the marginal
peak-shoulder shift a ToU schedule is designed to induce. All three rules use
the same window (`RETIME-WINDOW`) so the comparison stays like for like.

**Schedule delay is priced in dollars for every rule.** The first
implementation scaled the learner's penalty by 1/10 to match its reward units.
That was wrong: it would have made the learner retime freely while the price
rule barely moved, and the difference would have been an artefact of the unit
choice rather than of behaviour.

**Default `sched-delay-cost` = 0.6 × VoT per hour, 1.6× for arriving late**,
following the standard schedule-delay formulation. This is a parameter with no
local calibration, hence the slider.

**A 2-day probe was run before committing to the 12-cell run.** It showed 2 % of
Pay entrants shifting at 0.6 and 48 % at 0.2, which confirmed both that the
mechanism worked and that `sched-delay-cost` is the lever. Without the probe the
main run could have burned seven hours to show nothing moving.

**Each rule retimes in its own idiom** rather than sharing one rule: the price
rule minimises fee plus schedule delay, the expectation rule moves toward the
hour it predicts will be quietest, and the learner gets two extra actions. A
single shared retiming rule would have smuggled price responsiveness into El
Farol, which is precisely the thing it is supposed not to have.

### 5. Route choice (rerouting)

**Cost measured before designing.** A weighted shortest path costs 6.5 ms on
this network (500 paths in 3.267 s), which put per-departure rerouting at about
8 minutes per 14-day run and per-tick rerouting out of reach. The design
followed the measurement rather than the other way round.

**Cache keyed by OD and time band, four bands not 24 hours.** Twenty-four
hourly caches would multiply cache size by 24 against an 8 GB shared heap. Four
bands mirror the fee schedule, so a rerouting agent and a retiming agent react
to the same division of the day.

**Cache cleared daily**, so each (OD, band) route is computed once per day on
the congestion prevailing when the first agent needs it. This models "agents
route on yesterday's traffic pattern", not a live navigation feed, and keeps the
cost at the measured figure.

**Outbound legs are routed for the band they depart in**, not the band the day
starts in. The day starts at 05:00, so without this every agent would have been
handed an off-peak route.

**Only the rerouting-ON cells were run.** The OFF control is the
`allow-retiming? = false` cells of the `retiming` experiment: same settings,
same seed, same filenames. Re-running them would have cost 3.5 hours to
reproduce identical numbers.

**Both extensions are switches defaulting to off**, so every earlier result
remains reproducible and the 2×2 design (fixed / retime / reroute / both) is
available.

### 6. Things that look like results but are not

**El Farol's two fee regimes are bit-identical under retiming.** Not a bug:
calibrated congestion runs at 0.09–0.17 against a comfort threshold of 0.6, so
the small adjustment the fee makes to that threshold never flips a decision, and
with the same seed the runs coincide exactly.

**El Farol's +22.3 % boundary V/C in the rerouting arm is noise.** No charge
0.361 ± 0.091 against ToU 0.441 ± 0.132 over 14 days, series overlapping
throughout. It was checked before being reported, and is reported as noise.

**Q-learning's entry rise under retiming is partly mechanical.** Epsilon-greedy
over four actions travels three times in four during exploration against one in
two over two actions. Netting that out at the day-14 exploration rate leaves the
greedy policy travelling 6.5 % of the time without retiming and 30 % with it, so
the finding survives, but the raw number overstates it.

### 7. Equity analysis

**Derived, not measured.** The quintile figures come from applying the model's
own decision and reward functions to the calibrated VoT distribution. No
experiment recorded entries by income band, and the reporter that would have
done so is defective (see §2). This is stated at the top of every place the
numbers appear.

**Quintiles are computed in the analysis, not by the model.** The model only
computes the 20th and 80th percentiles, so it has three bands, not five. The
analysis cuts its own quintiles from the same distribution.

### 8. The multi-destination finding (2026-07-28)

Measured at setup: 1,500 of 2,500 agents have a CBD destination and **all 1,500
carry more than one destination**, 3.76 on average. `new-day-decisions`
deactivates the agent for the whole day when it declines the charge, so its
non-CBD stops are cancelled too — 3,171 trips across the CBD-bound population,
of the order of 100,000 vehicle-trips a day at 160 vehicles per agent.

**The k-factor sweep does not cover this**, though it is the natural thing to
point at. `k-factor` appears once, in `r-cap-hr = ADT × k-factor`, the
denominator of the flow V/C used for grading. At a fixed seed the traffic is
identical across k; only the grade changes. It tests measurement, not demand.

**Not fixed** at the time, per the instruction to stop modifying the model.
Recorded as a limitation in four documents and on the limitations slide.

**Update 2026-07-29: fixed on user instruction.** `new-day-decisions` now calls
`skip-cbd-stops-today` instead of deactivating the agent: a declining agent
keeps every non-CBD stop (and the return home) and drops only the CBD stops for
the day; the full itinerary is restored each morning from `full-*` copies
snapshotted on first reset. A 2-day probe (Pay rule, seed 11) confirms the
mechanism: 477–603 of the 727–918 declining agents now record arrivals (zero
before), their working itinerary shrinks from 3.76 to about 2.6 stops, and the
uncharged peripheral and boundary baselines rise as the restored trips return
to the network. All published numbers predate the fix; the 14-day `paper-figs`
re-run is in progress and supersedes them when it lands.

### 9. Demand provenance audited against the code (2026-07-29)

A collaborator asked what the model was calibrated against, which prompted a
line-by-line check of the demand generator rather than a restatement of the
draft. Two claims in the submitted methods text turned out not to be
implemented:

| Claim in the draft | What the code does |
|---|---|
| "TomTom Move data for August 2024 determines the time-of-day profile" | No TomTom file exists in the repository and no procedure reads one. The profile is two hardcoded 24-element weight lists, `outbound-demand` and `return-demand` in `akl_pricing.nls`, with ~20 % of outbound departures at 08:00 |
| "NZTA TMS screenline counts determine the inflow volume on each corridor" | `motorway-aadt` and `tms-screenlines` are reporters **no procedure ever calls**. The corridor split in `pick-home` is the fixed triple 0.30 / 0.48 / 0.22, which tracks the 2023 Census sector populations, not the counts (which would give 0.40 / 0.30 / 0.30) |

Also recorded: destinations are drawn uniformly from the non-home building
stock (`akl_vehicles.nls`), so there is no estimated OD matrix at all, and the
departure minute is uniform within the drawn hour at 60 ticks per hour.

**Why this matters beyond bookkeeping.** The temporal residual — implied
design-hour factor 0.157 against the 0.10 assumed — had been written up as a
shortfall against a fitted profile. It is not: it is the direct consequence of
the profile never having been fitted. Stating it that way makes the residual
explicable rather than mysterious, and names the next calibration step.

**Nothing was changed in the model.** Only the write-up was corrected, in
`methods_revised.md` (rewritten demand section plus change note 7),
`conclusion_revised.md`, `conclusions_bullets.md` and the deck (calibration
slide retitled *Calibrated on Volume and Space — Not on Time or OD*, a new
*OD matrix: synthetic, not estimated* card, and the limitations card
*Demand is synthetic, not observed*).

### 10. Presentation

**Figures redrawn in plotnine (`_gg`) on request**, except the map, which draws
network geometry rather than a statistical mapping.

**Two failures worth remembering.** Facet strip labels containing `$` are read
as matplotlib mathtext and render as garbage, so currency in labels must be
escaped or avoided; and `geom_text` ignores `position_dodge` unless `group=` is
mapped explicitly, which silently stacks value labels on top of each other.

**Deleting and re-adding a slide with python-pptx corrupted the deck.** It
reused the part name, producing duplicate `slide15.xml` entries; the validator
passed but PowerPoint refused the file. The fix was to restore the backup and
rebuild the slide's *content* in place, never removing the slide part. Repacking
by hand also requires `[Content_Types].xml` to be the first archive entry.

**Backups are kept at each step** (`SSC2026_presentation.pptx.bak` … `.bak7`).

### 11. Deferred, with cost

| Item | Cost | Why it matters |
|---|---|---|
| Fee-level sweep on the calibrated model | ~9 cells, 5 h | The only experiment that would let the paper say anything about *how much* to charge. Nothing run so far varies the fee level. |
| Flat NZ$2 re-run | 3 cells, 3.5 h | Restores the draft's Fig. 5 |
| Record entries by income band, and fix `burden-quintile` | small code change plus a re-run | Turns the equity result from derived to measured |
| Q-learning reward scale (benefit is VoT/10 against fees of NZ$2–6) | code change plus a re-run | Under a benefit of half an hour of VoT the regressive pattern returns; the current Learn result rests on this choice |
| Multi-destination cancellation | code change plus a re-run | Would reduce the peripheral and no-displacement effects |
| Multi-seed replication beyond El Farol | 3–5× any experiment | Every spread quoted is within-seed |
| Fit the departure profile to an observed time-of-day distribution | data acquisition plus a re-run | The only fix for the temporal residual (implied k 0.157 against 0.10); the profile is currently assumed, so absolute peak LoS cannot be read |
| Estimate an OD matrix instead of drawing destinations uniformly | observed trip-end data plus a model change | Would let the paper speak to observed travel patterns, not only to volume and spatial spread |

---
