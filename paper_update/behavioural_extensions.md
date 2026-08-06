# Behavioural extensions: departure-time choice and route choice

*All four arms re-run 2026-08-06 on the trip-suppression-fixed model
(v3), calibrated, 14 simulated days, seed 11. The pre-fix (v2) set is
preserved in `output/tables_prefix_backup_20260805/`; per-cell pre/post
comparison via `netlogo/sensitivity_experiment/compare_arms_postfix.py`.
The `retiming` experiment's OFF cells rewrote the base tables byte-identically
to the 2026-08-06 `paper-figs` run, confirming the runs are deterministic at a
fixed seed.*

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

**This changed the base numbers once, and the trip-suppression fix changed
them again.** The current base-arm figures (post both fixes, re-run
2026-08-06) live in `numbers.md`; the sequence for the headline number is:

| Rule | 07-27 calibrated | 07-28 trip-hour fix | **08-06 trip-suppression fix (current)** |
|---|---|---|---|
| Pay | 23.0 % | 11.7 % | **18.8 %** |
| Oscillate | 0.2 % | 0.0 % | **1.7 %** |
| Learn | 23.8 % | 38.7 % | **24.1 %** |

The direction of the story is unchanged at every step (two rules respond, one
does not) but the magnitudes move substantially, and only the last column is
current.

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

**Result (mean over 14 days, No-Charge → ToU), post-fix model:**

| Rule | Arm | inner | boundary | peripheral | entries |
|---|---|---|---|---|---|
| Pay | fixed | 0.120 → 0.097 (−18.8 %) | 0.535 → 0.470 (−12.3 %) | 0.095 → 0.083 (−12.7 %) | −23.5 % |
| Pay | **retime** | 0.120 → 0.091 (**−23.8 %**) | 0.535 → 0.469 (−12.3 %) | 0.095 → 0.086 (−9.5 %) | −23.1 % |
| Oscillate | fixed | 0.166 → 0.163 (−1.7 %) | 0.793 → 0.783 (−1.2 %) | 0.128 → 0.125 (−2.3 %) | −1.8 % |
| Oscillate | **retime** | 0.162 → 0.162 (0.0 %) | 0.749 → 0.749 (0.0 %) | 0.117 → 0.117 (0.0 %) | 0.0 % |
| Learn | fixed | 0.116 → 0.088 (−24.1 %) | 0.553 → 0.428 (−22.6 %) | 0.092 → 0.078 (−15.1 %) | −37.2 % |
| Learn | **retime** | 0.132 → 0.119 (**−9.5 %**) | 0.608 → 0.529 (−12.9 %) | 0.099 → 0.086 (−13.3 %) | −11.9 % |

Share of entrants who move their departure (day 14, ToU): Pay 2.5 % (13 of 15
earlier), Oscillate 7.0 % (identically with and without the charge), Learn
64.3 % (evenly split earlier and later).

**Three findings.** (Same qualitative findings as the pre-fix runs, at the
post-fix magnitudes — the fix did not change this story.)

1. **For the price rule the charge works better when retiming is possible**, and
   only 2.5 % of entrants need to move. The reduction rises from 18.8 % to
   23.8 % because the agents who move are exactly those facing the $6 peak, so a
   small share of the population is a large share of the peak. The morning peak
   falls 23.9 % rather than 17.0 %. This is the peak-spreading mechanism a ToU
   schedule is designed around, and the base model could not express it at all.
2. **For the learner the charge works much worse.** Given somewhere to move, the
   agent stops forgoing the trip: entries under ToU fall only 11.9 % instead of
   37.2 %, and the reduction in peak V/C drops from 24.1 % to 9.5 %. **A model
   whose only response is "do not travel" overstates what the charge achieves.**
   Part of the rise in entries is mechanical, since epsilon-greedy exploration
   over four actions travels three times in four rather than one in two — the
   no-charge entry rate itself rises from 0.53 to 0.70 when the two extra
   actions are added — but the ToU-minus-No-Charge gap collapses far beyond
   that mechanical shift, so the effect survives the correction.
3. **For the expectation rule nothing changes, and the two fee regimes become
   bit-identical.** Its agents compare predicted congestion with a comfort
   threshold of 0.6, but calibrated congestion runs at 0.09 to 0.17, so the
   prediction never approaches the threshold and the small adjustment the fee
   makes to it never flips a decision. Its 7.0 % of retimers move for congestion
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

**A 2-day probe already showed the arm bites** (pre-fix model; kept for the
mechanism, not the levels), comparing fixed against adaptive routes under ToU
with retiming off:

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

**Result, all four arms (14-day mean, No-Charge → ToU), post-fix model:**

| Rule | Arm | inner | boundary | peripheral | entries |
|---|---|---|---|---|---|
| Pay | base | 0.120 → 0.097 (−18.8 %) | 0.535 → 0.470 (−12.3 %) | 0.095 → 0.083 (−12.7 %) | −23.5 % |
| | retime | 0.120 → 0.091 (**−23.8 %**) | 0.535 → 0.469 (−12.3 %) | 0.095 → 0.086 (−9.5 %) | −23.1 % |
| | reroute | 0.153 → 0.155 (**+1.8 %, ns**) | 0.325 → 0.261 (−19.5 %) | 0.092 → 0.080 (−13.1 %) | −24.2 % |
| | both | 0.153 → 0.147 (−3.7 %, ns) | 0.325 → 0.283 (−12.9 %) | 0.092 → 0.083 (−10.2 %) | −23.9 % |
| Oscillate | base | 0.166 → 0.163 (−1.7 %) | 0.793 → 0.783 (−1.2 %) | 0.128 → 0.125 (−2.3 %) | −1.8 % |
| | retime | 0.162 → 0.162 (0.0 %) | 0.749 → 0.749 (0.0 %) | 0.117 → 0.117 (0.0 %) | 0.0 % |
| | reroute | 0.255 → 0.204 (−20.0 %, ns) | 0.381 → 0.472 (+23.9 %, ns) | 0.117 → 0.142 (+21.1 %, ns) | −1.9 % |
| | both | 0.228 → 0.228 (0.0 %) | 0.357 → 0.357 (0.0 %) | 0.116 → 0.116 (0.0 %) | 0.0 % |
| Learn | base | 0.116 → 0.088 (−24.1 %) | 0.553 → 0.428 (−22.6 %) | 0.092 → 0.078 (−15.1 %) | −37.2 % |
| | retime | 0.132 → 0.119 (−9.5 %) | 0.608 → 0.529 (−12.9 %) | 0.099 → 0.086 (−13.3 %) | −11.9 % |
| | reroute | 0.147 → 0.124 (−15.5 %) | 0.302 → 0.243 (−19.7 %) | 0.117 → 0.087 (−26.0 %) | −36.4 % |
| | both | 0.186 → 0.168 (−9.4 %) | 0.251 → 0.250 (−0.1 %) | 0.084 → 0.083 (−0.9 %) | −9.1 % |

("ns" = inside the day-to-day spread: Pay reroute inner is 0.153 ± 0.033
against 0.155 ± 0.034; Oscillate's reroute cells swing by less than one SD,
e.g. boundary 0.381 ± 0.077 against 0.472 ± 0.184.)

**Four findings.**

1. **Routing changes where congestion sits far more than the charge does.**
   Compare the no-charge baselines: letting agents avoid congested links moves
   peak boundary V/C from 0.535 to 0.325 for Pay, from 0.793 to 0.381 for
   Oscillate and from 0.553 to 0.302 for Learn, while inner-cordon V/C *rises*
   (0.120 → 0.153, 0.166 → 0.255, 0.116 → 0.147). Fixed shortest paths were
   funnelling traffic along a few approach arterials; adaptive routing spreads
   it, some of it through the CBD grid. The single largest effect in this whole
   set of runs is a modelling assumption, not a policy.
2. **With routing, the price rule's inner-cordon effect disappears — the
   benefit relocates to the boundary.** This is new since the trip-suppression
   fix, and it is the most consequential change the fix produced. Entries
   still fall by 24 %, but inner V/C is unchanged (0.153 → 0.155, inside the
   day-to-day spread): the road space freed inside the cordon is refilled by
   suburban and pass-through traffic that congestion-aware routing steers
   through the CBD grid — the classic triple-convergence result. What the
   charge buys in this arm shows up on the cordon boundary instead (−19.5 %).
   In the pre-fix runs this backfill traffic had been deleted along with the
   decliners' days, which is why the same cell then read −25.9 %. **The action
   space therefore changes not only how much the charge achieves but *where*
   it achieves it** — and a Pay headline quoted without the routing assumption
   is under-specified even in sign of location.
3. **The learner's headline is the fragile one, still.** Learn gives 24.1 % in
   the base arm and 9 to 16 % in every arm where the agent has an alternative
   to staying home. The base figure is the outlier, not the norm, and it is
   high precisely because forgoing the trip is the only option the base model
   offers.
4. **Displacement outward is still not demonstrated, and this arm is where it
   could have been.** In the reroute arm the boundary falls for both
   responsive rules (−19.5 % and −19.7 %) together with the periphery
   (−13.1 % and −26.0 %). The positive numbers all sit in Oscillate's reroute
   cells and inside their own variance (boundary 0.381 ± 0.077 against
   0.472 ± 0.184, overlapping throughout): on a single seed that is noise, not
   displacement. The claim that pricing does not push traffic *outward*
   survives the extension that could most easily have broken it — while
   finding 2 shows the flow that does move goes *inward*, into road space the
   charge has freed. The caveat above about what routing responds to still
   applies.

## What each option buys, side by side

Reading the two opt-in figures together answers the question a planner would
actually ask: if drivers can do this, does the charge still work?

| | Departure-time choice | Route choice |
|---|---|---|
| Who uses it | 2.5 % of Pay entrants, 7.0 % of Oscillate, 64.3 % of Learn | everyone, by construction |
| Entry rate | unchanged for Pay (0.40 both), **Learn 0.33 → 0.62** | unchanged for all three (Pay 0.40, Learn 0.34) |
| Peak inner V/C under ToU | Pay 0.097 → 0.091, Learn 0.088 → 0.119 | Pay 0.097 → 0.155, Learn 0.088 → 0.124 |
| ToU reduction | Pay 19 → 24 %, Learn 24 → 9 % | Pay 19 → ~0 % (inner; boundary −19.5 %), Learn 24 → 16 % |
| Equity channel | yes, but reaches only the poorest 3 % | none: routes respond to congestion, not to the fee |

The two options work on different quantities. **Retiming changes how many trips
are made** — it is the only extension that moves the entry rate, and it moves it
sharply for the learner, which is why its measured effect collapses. **Rerouting
leaves the number of trips exactly as it was** (entry rates are nearly
identical) and changes only where those trips go — which post-fix includes
moving other traffic *into* the road space the charge frees, so for the price
rule the interior benefit is routed away while the boundary benefit remains.

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

## A declined CBD trip cancelled the agent's whole day — **fixed 2026-07-30**

Measured at setup, not inferred: of 2,500 agents, 544 are single-stop
pass-through traffic and the remaining 1,956 carry two or more destinations
(2.98 on average). Of the 1,500 agents with a CBD destination, **all 1,500 have
more than one destination**, averaging 3.76. Every CBD-bound agent in this model
is therefore a multi-stop agent.

**The defect:** when such an agent declined the charge, `new-day-decisions` set
`active?` to false for the day, so its non-CBD stops were cancelled along with
the CBD one — of the order of 100,000 vehicle-trips per day leaving the network
outside the cordon for no modelled reason.

**The fix** (`skip-cbd-stops-today` in `akl_pricing.nls`, commit of
2026-07-30): a declining agent now removes only the CBD stops from the day's
itinerary and still makes its suburban trips.

**Measured effect of the fix** (base arm re-run 2026-08-06): the no-charge
baseline outside the cordon rose — Pay boundary 0.344 → 0.535, peripheral
0.074 → 0.095 — because the restored trips load those roads under every
regime, and the ToU reductions shrank accordingly (Pay peripheral −15.7 % →
−12.7 %, Learn boundary −44.6 % → −22.6 %). The suppressed trips had indeed
been inflating exactly the results the paper leans on. **The no-displacement
conclusion survives the correction** — V/C still falls in every zone under
every rule — and is now measured on roads that carry the traffic they should.

**The k-factor sensitivity does not address this.** `k-factor` enters the model
in one place, `r-cap-hr = ADT × k-factor`, which is the denominator of the flow
V/C used for LoS grading. At a fixed seed the traffic is bit-identical across
k = 0.08, 0.10 and 0.12; only the grading changes. That sweep therefore tests
the capacity assumption, and says nothing about whether demand is over-suppressed.

## What this means for the paper

The behavioural-assumption claim gets sharper, and moves one level up. It is not
only that the choice of decision rule changes the predicted effect of the
charge. It is that **the choice of action space does too, and by a comparable
amount — and it can move not just the size of the effect but its location**:
allowing the learner an hour of flexibility moves the predicted reduction from
24.1 % to 9.5 %, a swing as large as the gap between the three rules in the
base arm, and allowing routes to respond to congestion moves the price rule's
benefit off the cordon interior (unchanged, within noise) onto the boundary
(−19.5 %). An appraisal that reports a single number without stating what its
agents were allowed to do is under-specified.

Concretely, three things should change in the paper.

1. **Report the range, not one cell.** Across the post-fix arms the ToU
   reduction in peak inner-cordon V/C is 0 to 24 per cent for Pay (zero in the
   routing arms, where the benefit appears at the boundary instead), 9 to 24
   per cent for Learn and zero for Oscillate. The width of the ranges comes
   from the action space alone, with the rule, network, demand and fee
   schedule held fixed.
2. **Retire the stay-home-only Learn number as the headline.** 24.1 % is the
   artefact of an action space where staying home is the only alternative;
   quote 9 to 16 per cent, from the arms where the agent has somewhere to go.
3. **Keep the outward-displacement conclusion, and say why it now means
   more — then state the inward result beside it.** Displacement was
   previously close to untestable, because a deterred trip ceased to exist.
   With congestion-aware routing the traffic is still there and free to move,
   and the boundary still falls with the interior for the learner and falls
   while the interior holds for the price rule. Nothing piles up outside the
   cordon; what the routing arm adds is that freed space *inside* the cordon
   is partly refilled (triple convergence), which caps the interior benefit a
   cordon charge can deliver when drivers reroute freely. The remaining gap is
   that routing here responds to congestion rather than to the charge, so
   cordon-dodging proper is still untested.
