# Decisions log — calibrated re-analysis, 2026-07-26 to 2026-07-28

Why things were done the way they were, including the options rejected. The
results themselves are in `numbers.md`, `behavioural_extensions.md` and
`conclusions_bullets.md`; this file records the reasoning that produced them, so
that a reviewer question of the form "why did you not just…" has an answer.

---

## 1. Running the two pending experiments (2026-07-26/27)

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

## 2. Bugs found and fixed, in the order they surfaced

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

## 3. Scope decisions

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

## 4. Departure-time choice (retiming)

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

## 5. Route choice (rerouting)

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

## 6. Things that look like results but are not

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

## 7. Equity analysis

**Derived, not measured.** The quintile figures come from applying the model's
own decision and reward functions to the calibrated VoT distribution. No
experiment recorded entries by income band, and the reporter that would have
done so is defective (see §2). This is stated at the top of every place the
numbers appear.

**Quintiles are computed in the analysis, not by the model.** The model only
computes the 20th and 80th percentiles, so it has three bands, not five. The
analysis cuts its own quintiles from the same distribution.

## 8. The multi-destination finding (2026-07-28)

Measured at setup: 1,500 of 2,500 agents have a CBD destination and **all 1,500
carry more than one destination**, 3.76 on average. `new-day-decisions`
deactivates the agent for the whole day when it declines the charge, so its
non-CBD stops are cancelled too — 3,171 trips across the CBD-bound population,
of the order of 100,000 vehicle-trips a day at 160 vehicles per agent.

**The k-factor sweep does not cover this**, though it is the natural thing to
point at. `k-factor` appears once, in `r-cap-hr = ADT × k-factor`, the
denominator of the flow V/C used for grading. At a fixed seed the traffic is
identical across k; only the grade changes. It tests measurement, not demand.

**Not fixed**, per the instruction to stop modifying the model. Recorded as a
limitation in four documents and on the limitations slide.

## 9. Presentation

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

## 10. Deferred, with cost

| Item | Cost | Why it matters |
|---|---|---|
| Fee-level sweep on the calibrated model | ~9 cells, 5 h | The only experiment that would let the paper say anything about *how much* to charge. Nothing run so far varies the fee level. |
| Flat NZ$2 re-run | 3 cells, 3.5 h | Restores the draft's Fig. 5 |
| Record entries by income band, and fix `burden-quintile` | small code change plus a re-run | Turns the equity result from derived to measured |
| Q-learning reward scale (benefit is VoT/10 against fees of NZ$2–6) | code change plus a re-run | Under a benefit of half an hour of VoT the regressive pattern returns; the current Learn result rests on this choice |
| Multi-destination cancellation | code change plus a re-run | Would reduce the peripheral and no-displacement effects |
| Multi-seed replication beyond El Farol | 3–5× any experiment | Every spread quoted is within-seed |
