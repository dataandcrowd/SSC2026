# Behavioural extensions: departure-time choice and route choice

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

## Precondition: the charged hour now matches the travelled hour

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

## Departure-time choice

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

## Route choice

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

## What each option buys, side by side

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

## Figures

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

## Who bears the charge, and what the two extensions do about it

**Status of this section.** The numbers below are derived from the model's own
decision and reward functions applied to the calibrated VoT distribution
(lognormal, median NZ$10/h), not measured in the runs. No run has recorded entry
by income band: the `burden-quintile` reporter exists but was never included in
an experiment, and it is in any case defective — it computes only the 20th and
80th percentiles, so `burden-quintile` 2, 3 and 4 all return the whole
population rather than the middle bands. Nothing published so far depends on it.
Measuring the distributional result properly needs a run that records entries by
VoT band, which has not been done.

### The price rule is strongly regressive

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

### Departure-time choice is an escape valve, but only for the poorest 3 %

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

### Route choice has no distributional channel at all

Routes here respond to congestion, not to the fee, and every CBD-bound agent
pays the same charge whichever road it takes. Rerouting therefore changes where
congestion sits without changing who pays or who is deterred. Its large effects
on the boundary are an efficiency result, not an equity one.

### The learner's income gradient is an artefact

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

## A declined CBD trip cancels the agent's whole day

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

## What this means for the paper

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
