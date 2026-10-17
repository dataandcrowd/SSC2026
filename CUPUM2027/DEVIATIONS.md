# Deviations and interpretations

Each entry records where Cordon-Lite departs from, simplifies or interprets the specification
or the v3 design note (`../docs/design_history/persona_design_v3.md`). Builders append entries under their own heading.

## Scaffold

1. **Extra config sections.** `[engine]` (NetLogo paths, capacity mode) and `[memory]` (window,
   EMA, ratio offset) were added to the sections listed in the specification, so that every
   parameter lives in `config.toml`.
2. **Engine capacity.** The specification gives raw corridor capacity (veh/h) but simulates only
   about 300 commuters. Default `capacity_mode = "demand_share"`: each corridor's capacity is set so
   its own commuters need `rush_window_min` (60 min [A]) to pass, which makes the Vickrey
   rush-hour length N/s directly interpretable. `raw_scaled` (raw capacity scaled by
   n_agents / 19,000 represented vehicles) is available as a sensitivity option.
   *Superseded 2026-10-07/08:* 950 commuters (1 agent = 20 cars) on congested roads, so the gate queue is no longer the only delay; `capacity_scale` is calibrated on gate queue + road delay and the floor is in vehicles. See Road congestion 10 and Motorway flow breakdown 12, 14 and 16.
3. **Archetypes.** v3 codes 6 (escort) and 7 (discretionary visitor) are dropped; code 5
   (student) gets a base weight of 0.10 [A] because v3 only assigns students through the
   university branch. Hour-band conditioning and the trip-frequency tilt are dropped (AM peak
   only, every agent travels every day). VoT-quintile tilts follow v3.
4. **No WFH quota.** v3 limits WFH to 1-3 days per 5-day block; Cordon-Lite allows WFH on any
   day for archetype 1 at cost `wfh_cost * phi(F)` (specification: "keep simple").
5. **Archetype schedule multiplier.** "Flexible start" and "fixed start" are expressed by a
   per-archetype multiplier `sched_mult` [A] on the schedule-delay term, in addition to phi(F).
   The specification's GC formula has no such term; without it, the archetype distinction would
   rest only on t*.
6. **PT attitude.** The specification applies omega(P) to the PT time cost
   (`omega * VoT/60 * pt_time`); v3 applies omega to a separate attitude penalty (PAP). The
   specification is followed; there is no PAP.
   *Recalibration:* PAP is now on (NZ$11, calibrated), in the specification's form omega x (a x T_pt + PAP); see Behaviour recalibration 5.
7. **PT fare.** NZ$7.00 per day (v3 round-trip fare) against a one-way AM cordon charge, because
   the mode choice is a day-level choice and the return car leg has no charge in the AM-only model.
8. **SKIP cost.** v3 has POSTPONE (NZ$6, phi-scaled) and CANCEL (NZ$10). Cordon-Lite merges them
   into SKIP with a deliberately high NZ$25 [A], not phi-scaled.
   *Final fixer:* SKIP now costs `skip_cost + skip_vot_hours x VoT` (1 h of VoT [A]); see Final fixer 4.
   *Superseded 2026-10-09:* SKIP is removed; see "SKIP removed, willingness to travel and the peak charge" 2.
9. **Late tolerance for T3.** v3 uses a fixed 15% threshold for everyone; the specification
   makes it depend on F. Mapping by F level 1..5: 5, 5, 10, 15, 15 minutes [A].
10. **Habit discontinuity.** kappa_H is multiplied by 0.5 on T1, T2, T4 and T6 wakes, as in v3
    section 4.4 (not stated in the specification).
    *Recalibration:* T2 is no longer a discontinuity (Behaviour recalibration 4).
11. **Twins.** To produce the twin table, the last `min(n_twins, n_agents // 2)` agents copy
    Layer A of the first agents and keep their own Layer B draws (default 30 twins of 300).
    *Superseded 2026-10-08:* 95 twins of 950 (10%); see Motorway flow breakdown 12.
12. **Reference fee.** EMA (alpha 0.3) of perceived fees paid, updated every day (0 on non-car
    days) by default, as the specification says "fees paid"; v3 updates with the fee faced.
    `memory.ref_fee_update = "car_days"` is available.
    *Recalibration:* the default is now `"faced"`, v3's fee faced (Behaviour recalibration 1).
13. **Delay ratio.** Ratio uses an offset of 1 minute, `(experienced + 1) / (predicted + 1)`,
    clipped to [0.5, 3.0] [A], so that zero predicted delay does not divide by zero.
14. **Fee rounding.** `fee_at` rounds to 4 decimals so that `fees.csv` and Python agree exactly.
15. **Engine cap.** Cars not served by `sim_end_cap_min` get `-1` sentinels (not expected with
    default capacities).

## LLM builder

1. **Schema property order.** `output_schema` lists `reason`, `factors`, `choice` in that order
   (v3 section 7.4: the reason is written before the action). The key set, the `required` list
   and `additionalProperties: false` are as specified; only the order differs from INTERFACES.md.
2. **No option shuffling.** v3 section 7.3 shuffles the option order per (agent, day). Cordon-Lite
   keeps the deterministic order of `DecisionContext.options` (CAR by departure, PT, WFH, SKIP),
   as the specification asks for deterministic formatting. Position effects are therefore not
   controlled.
   *2026-10-09:* SKIP is removed, so the order is CAR by departure, PT, WFH (template `cl-v3`).
3. **Fallback beta only where it applies.** `betas=["server-side-fallback-2026-07-01"]` and
   `fallbacks="default"` are sent only for `claude-opus-5-5` and `claude-sonnet-5-5`. For
   `claude-haiku-4-5` the request goes through `client.messages.create` without them (and
   without `output_config.effort`, as specified).
4. **Refusals count as invalid output.** A `stop_reason == "refusal"` response is logged with its
   `stop_details.category`, retried once like any invalid output, then replaced by the rule
   decision (`decider = "llm-fallback-rule"`).
   *Final fixer:* a refusal is no longer resent (the server-side fallback has already run); it goes straight to the rule fallback. See Final fixer 13.
5. **API-level retries.** On top of the SDK's own retries (`max_retries = 5`), `AnthropicLLM`
   retries `RateLimitError`, `APIStatusError` with status >= 500 and `APIConnectionError` up to
   2 more times with exponential back-off (2 s, 4 s). `BadRequestError` and other 4xx errors are
   not retried at API level; they still use the single invalid-output retry. These two values are
   constructor arguments, not config keys.
   *Final fixer:* removed. Transport retries are left to the SDK only; see Final fixer 13.
6. **No disk cache for MockLLM.** `make_llm_decider` attaches the disk cache
   (`llm.cache_dir`) only to the anthropic backend. MockLLM is deterministic, and a cache would
   make `llm_calls.jsonl` differ between the first and second run (`cache_hit`), which breaks
   byte-identical reproducibility. Only valid outputs are cached. A cache hit is logged with zero
   usage (no tokens were spent); the original usage stays in the cache file.
   *Final fixer:* the cache is shared across runs and arms by design (v3 7.5); identical prompts in one morning are sent once and shared. See Final fixer 11.
7. **Mock seeding.** MockLLM noise is seeded from the first 64 bits of
   `sha256(system + "\n\n" + user)`. Its latency is logged as `null` so that logs are
   byte-identical.
   *Final fixer:* identical prompts therefore get identical mock answers (consistent with v3 7.5); `llm.replicate > 0` adds a sample index to the seed and the cache key.
8. **Yesterday's delay in the prompt.** The TODAY section shows the PUBLIC corridor delay
   (`Option.expected_public_delay_min`, before the personal EMA ratio) for each car departure.
   The options table shows the personal expectation (`Option.expected_delay_min`). The LLM
   therefore sees both the public information and the agent's own adjusted expectation, as the
   rule does.
   *Extended 2026-10-07 (template `cl-v2`):* the TODAY line now gives yesterday's traffic on the agent's route together with the queue, by departure time (day 1: usual traffic), and the options and memory tables have a "traffic delay" column; see Road congestion 8.
9. **Memory table.** The table shows day, what the agent did, departure, queue at entry,
   door-to-door time, arrival (early or late), charge paid and a note: "bus or train disrupted",
   or "about N min longer/quicker than you expected" when the car time differs from the
   expectation by at least 5 min [A]. The v3 rule-generated summary sentence and the "no trip"
   rows for skipped calendar days are not rendered, because every simulated day is a weekday
   with a record.
10. **Prompt caching is nominal.** The system prompt is about 600 characters (roughly 150 tokens),
    below the 512-token minimum cacheable prefix for `claude-opus-5-5`. The `cache_control`
    marker is sent as specified but will not create cache entries unless the system prompt
    grows.
   *Final fixer:* the per-agent `json_schema` (the choice enum differs per agent) also breaks prefix reuse, so all input should be costed as uncached; the estimate note says so.

## Prep builder

1. **Origins exclude motorway-only nodes.** Candidate origins are graph nodes outside the cordon
   whose incident segments are not all frc 0 [A]: trips do not start on a motorway carriageway.
   Nodes with zero local-road length within 500 m are also dropped (weight 0). 23,772 of 28,507
   giant-component nodes qualify.
2. **Density proxy by segment midpoints.** Local (frc 3-4) road length within 500 m is the sum of
   `distance` over local segments whose midpoint lies within the radius [A]. Segments are short
   (median 26 m), so the error is small.
3. **Parallel segments.** TomTom digitises most two-way roads twice (one segment per direction).
   On the undirected graph these become parallel edges; the fastest is kept (16,119 collapsed).
4. **Gate rule option.** New key `prep.gate_rule` (default `"first_entry"`, the specification).
   `"last_entry"` [A] uses the final outside-to-inside crossing instead. With the default, 834 of
   3,000 origins (27.8%) have paths that touch the SA3 boundary and leave again before the final
   entry: 723 on the SH1 Wellesley Street off-ramp (the undirected path then runs back out via the
   Port ramp and enters at Alten Road) and the zig-zag boundary along The Strand. `last_entry`
   would merge the South corridor into Alten Road (about 56% of origins) and leave two corridors
   of under 1%, so the specification's rule is kept as the default.
   *Recalibration review:* the README used to say these 834 origins "first touch the cordon on an
   Alten Road segment"; that was wrong. The 834 origins of Alten Road gate 2 (the most used gate)
   are single-entry paths from the south-east (median bearing 136 degrees; first entry = last
   entry). The 834 multi-entry paths are a different set (the equal count is a coincidence): 723
   SH1 Wellesley Street off-ramp origins (gate 26), 63 at The Strand, 23 at Parnell Rise and a few
   others; they spend 0.04-1.2 min outside and re-enter at Alten Road. With the first-entry rule they
   keep their first touch, so 97 of the 300 seed-1 agents (all 89 South-corridor agents, the day-20
   disruption corridor) sit on such paths. Free-flow and PT times do not depend on the gate, the fee
   minute moves by under 1 min and capacity follows agent counts, so the bias on the calibration
   targets is negligible; only corridor labels, the per-corridor congestion mix and the disrupted set
   are affected. No re-prep was done; the README, `data/prep_report.md` (gate rule bullet) and the
   matching text in `prep/build_inputs.py` were corrected.
5. **Gate coordinates.** `gates.csv` x, y are where the gate segment crosses the cordon boundary
   (not the inside node). One gate segment (1 origin) stops 0.27 m short of the boundary after
   1 m node rounding and is snapped to the nearest boundary point.
6. **Corridor clustering.** Weighted spherical k-means on unit bearing vectors (weight = origins
   served by the gate), one weighted-quantile start plus 50 k-means++ starts from
   `stream(seed, "prep", "corridors")`, lowest weighted inertia wins. Corridor ids run clockwise
   from north; names use the 8-point compass sector of the weighted circular mean bearing and the
   two most-used street names, with ramp names shortened ("Exit 429B Wellesley Street" ->
   "Wellesley Street ramp"). `gates.csv` keeps the raw TomTom street names.
7. **Free-flow speeds.** `ff_factor = 1.0` (specification default) gives total free-flow times of
   2-24 min (median 13 min) across the TomTom extent, at the low end of the 5-45 min expectation,
   because speed limits ignore junction delay. Raising `prep.ff_factor` (e.g. 1.3) scales every
   time proportionally; the default was not changed.
   *Superseded 2026-10-07:* free-flow time is now only the lower bound of the time to the gate; road delay from background traffic and commuter cars comes on top, with k calibrated to TomTom's index, which absorbs junction delay on the way in (Road congestion 5, 6). `ff_factor` stays 1.0; the post-gate leg is still free flow.

## Engine

1. **Minimum one minute.** The minute loop always processes `sim_start_min`, so a day without cars
   (all PT/WFH/SKIP) yields one all-zero profile row per corridor. The stop test ("all cars served
   or cap reached") is global, so every corridor is profiled over the same minute range.
2. **Arrivals after the cap.** A car whose gate arrival is after `sim_end_cap_min` never joins the
   queue; like cars still queued at the cap it gets `-1` sentinels and fee 0, and it is not counted
   in `queue_len`.
3. **Plan validation.** Both engines validate plans in Python before simulating (NetLogo is not
   called on bad input): duplicate `agent_id`, unknown mode or agent, non-integer CAR `depart_min`
   and a gate arrival before `sim_start_min` raise `ValueError`. Agents absent from `plans` are
   allowed and simply not simulated. Non-car `depart_min` may be missing; it is written as -1 in
   `plans_dayNN.csv`.
4. **Floating-point carry.** Capacities and carry are IEEE doubles, exactly as in the
   specification (CSV floats read round-trip exact in both engines, identical operation order), so
   the two engines agree bit for bit. A capacity that is not a binary fraction can drift: with
   c = 1/3, three minutes of accumulation give 0.9999999999999998, so service slips one minute
   (cars at 400 exit at 400, 403, 406 instead of 400, 402, 405). Not corrected, to keep the
   specified semantics; integer micro-unit arithmetic would remove it in both engines if wanted.
5. **Idle burst.** Because the carry is capped at 1.0 only when the queue empties, a gate that has
   been idle serves floor(1 + c) cars in its first busy minute (two cars when c = 1). This is the
   specified rule, noted because it lets small platoons through slightly faster than c.
6. **`set-clock`.** The NetLogo model has an extra procedure `set-clock <sim-start> <cap>`
   (defaults 330 and 720 in `setup-from-dir`); `NetLogoEngine.load` calls it with the config values.
7. **JVM lifecycle.** `NetLogoEngine.close()` only forgets the scenario; the shared link stays up
   (one JVM per process). `engine.shutdown_netlogo_link()` tries `kill_workspace` in a daemon thread
   with a timeout and `engine.hard_exit(code)` ends the process with `os._exit`.
   *2026-10-09:* `engine.get_netlogo_link` starts NetLogo from the environment variable
   `CORDONLITE_NETLOGO_HOME` when it is set, else from `[engine] netlogo_home`. The variable never
   enters the config, so the run folder name, `config_snapshot.toml` and `summary.json` do not
   record it, and a PyEngine and a NetLogoEngine run made this way differ only in the engine label
   (`--set engine.netlogo_home=...` would add a `_set-<hash>` label and change the snapshot). The
   `--netlogo-home` option of the check scripts sets the variable. New tests
   `test_engine.py::test_netlogo_home_env_var` and `test_run.py::test_netlogo_home_env_var_is_not_recorded`;
   the fast suite gives 399 passed and the NetLogo suite 8 passed.
8. **GUI.** Plots are drawn only by `run-day-gui` (headless `run-day` does no plotting, for speed).
   When `plans_dayNN.csv` is missing, `run-day-gui` writes seeded demo plans (every commuter drives,
   departing 06:45 to 08:00). `netlogo7/demo_scenario/` was synthetic (300 commuters, 5 corridors),
   not Auckland data. The cordon is drawn as a grey disc, corridors as labelled targets placed by
   bearing from the mean corridor position, commuters at their scaled NZTM origins.
   *Superseded:* the schematic GUI was replaced by the network GUI on 2026-10-06 (NetLogo network
   model 8), and `netlogo7/demo_scenario/` was removed on 2026-10-09 (Extreme-charge scenarios,
   NetLogo choosers and clean-up 10); synthetic folders such as the equivalence check's test
   scenarios still get demo plans when they have no plans file.

## Behaviour builder

Simplifications of v3 (`../docs/design_history/persona_design_v3.md` sections 3 to 7) and interpretations of the
specification in `persona.py`, `memory.py`, `options.py`, `rules.py`, `clock.py` and `vickrey.py`.

1. **Rule noise sign.** The specification says `argmin(GC + epsilon), epsilon ~ Gumbel(0, sigma)`.
   With a max-type Gumbel that does not give logit probabilities for a cost minimiser. The rule
   draws `eps ~ Gumbel(0, sigma_rule)` (one per option, in option order, from
   `stream(seed, "rule", agent_id, day)`) and chooses `argmin(gc - eps)`, so choice
   probabilities are multinomial logit with scale `sigma_rule` (checked in `test_rules.py`).
   `Decision.meta["noise"]` stores the term added to GC (`-eps`).
   *Final fixer:* the noise is drawn per (noise id, day, option id) with common random numbers for twins (Final fixer 5). Note that v3 section 8 prefers a deterministic argmin (logit only as a sensitivity run); Cordon-Lite keeps sigma_rule = 0.5 [A], so part of the rule heterogeneity is noise. `--set rules.sigma_rule=0` gives the v3 argmin.
2. **No hour band, essential-day or trip-frequency logic.** v3 stage 0 (trip probability,
   `essential-today?`, carry-over, chain length) is dropped: every agent travels every simulated
   weekday. POSTPONE, CANCEL and SUBSTITUTE collapse into SKIP (scaffold entry 8).
3. **Layer A order and twins.** Origins are drawn with replacement by weight, per agent, on
   stream "A". VoT quintiles are ranked over the base (non-twin) agents; twins copy the quintile
   with every other Layer A field. t* is a normal draw snapped to the 15-minute grid (half away
   from zero) and clipped to 07:00-10:00 [A]; v3 has a stable preferred hour from the SSC
   demand curve instead.
4. **Company car and parking.** Probabilities follow v3 section 3.4 via `config.toml`. Company-car
   agents have parking 0 and perceive no charge (`c = 0`); the levied fee is still shown and paid
   as revenue.
5. **Retiming set.** Every archetype gets the same window (standing departure +/- 0..60 min in
   15-min steps). v3 restricts on-site office to earlier only and fixed shift to none; Cordon-Lite
   expresses this through `sched_mult` and t* (scaffold entry 5) rather than through the
   feasible set.
6. **Generalised cost structure.** The specification's GC is followed, which differs from v3
   section 6.2 in four ways: (a) GC is absolute, not relative to driving at h0, so car time and
   parking appear on the car side; (b) omega(P) multiplies the whole PT time cost, not a separate
   attitude penalty PAP; (c) no `c_bad x n-bad` PT disruption memory cost (the announced disruption
   only doubles today's PT time); (d) WFH and SKIP avoid parking and car time. Consequence (d)
   breaks the v3 zero-fee property: with default values about 15% of the 300 prep-data agents
   (44 hybrid office workers) work from home on the uncharged day 1 under the rule. v3 removed
   PARK from WFH to avoid exactly this. It is not "fixed" here because the specification fixes
   the formula; see the open problem on calibration in the builder report.
   *Recalibration:* (b) PAP is on and (d) is fixed by the v3 WFH form (Behaviour recalibration 3, 5).
7. **Habit reference.** The habit cost kappa_H applies to every option that differs from the
   standing option (specification). v3 uses the modal action of the last 5 trip-days with a 0.6
   share (`habit-action`); Cordon-Lite has no separate habit-action, so habit re-forms at once on
   whatever the agent last chose at a wake.
   *Final fixer:* a standing SKIP is not a habit reference; the most recent non-SKIP option is used instead (Final fixer 3).
   *Superseded 2026-10-09:* SKIP is removed and the standing option is the habit reference again ("SKIP removed, willingness to travel and the peak charge" 2).
8. **Personal delay expectation.** v3 compares PT with remembered car times (T-bar, T_b). Cordon-Lite
   uses yesterday's public corridor delay profile times the agent's EMA delay ratio (specification).
   The public profile is the mean queue delay of yesterday's cars by 5-min gate-arrival bin,
   linearly interpolated between bin mid-points; inside the first and last observed bin the edge
   value is held, and outside the observed range the forecast is 0 [A]. Unserved cars (-1) are
   ignored.
   *Extended 2026-10-07:* a car option also expects the public road delay on the agent's own route (usual traffic on day 1, yesterday's traffic later); its gate arrival, queue lookup, fee minute and time cost follow from it, and the EMA ratio stays queue-only. See Road congestion 7.
9. **Delay ratio and reference fee.** EMA with alpha 0.3 (specification) rather than v3's 0.2
   reference rate; the ratio uses `(experienced + 1) / (forecast + 1)` clipped to [0.5, 3]
   (scaffold entry 13). The reference fee tracks the fee actually paid (0 on non-car days and for
   company cars), not v3's fee faced.
   *Recalibration:* it now tracks the fee faced (Behaviour recalibration 1).
10. **T2 is global.** T2 fires for everyone when any minute of today's fee table differs from
    yesterday's by at least NZ$0.50. v3 compares the fee at the agent's own hour with the last
    fee it saw.
11. **T3 lateness against t*.** v3 defines `late?` as car time above T-bar x 1.15, suppressed for
    the first 3 car days. Cordon-Lite uses lateness against the work start t* (any mode, including
    disrupted PT) with an F-dependent tolerance (scaffold entry 9), with no suppression.
12. **T4 event key.** An announcement on day d and the experience of the same disruption share the
    event key ("T4", d), so one disruption wakes an agent once. An unannounced disruption fires on
    the next day from the memory record.
13. **T5 as an edge.** T5 fires when the last `sustained_days` (2) car records each differ from
    their expected door-to-door time by more than 20%, and that was not yet true one car day
    earlier, and yesterday was a car day. v3 compares the mean of the last 3 car times with the
    previous 3. Car days separated by non-car days count as consecutive car days.
14. **T6 rarely fires.** Feasibility is static in Cordon-Lite (no WFH quota, no PT hours), so T6
    fires only if the standing departure leaves the window or a mode stops being feasible.
    `evaluate_triggers` accepts feasible modes or option ids, so the integrator can call it before
    `build_options` (which needs the discontinuity flag).
   *Final fixer:* with the integrator's standing-SKIP rule, T6 fires the day after every SKIP (level-triggered for SKIP). With the VoT-scaled SKIP cost (Final fixer 4) no agent skips in the seed-1 runs, so T6 does not fire after day 1 there.
   *2026-10-09:* SKIP is removed. T6 now also fires when the willingness to pay removes the standing car departure on a charged day (given option ids, the departure itself must be offered); see "SKIP removed, willingness to travel and the peak charge" 5.
15. **T7 (weekly review) not implemented.**
16. **Traits off is level 3, not neutral.** `--traits off` sets H = F = P = S = 3 (specification),
    so kappa_H = 1, phi = 1, omega = 1, eta = 1. v3's neutral disposition (kappa_H = 0, eta = 0)
    is not available. With traits off, twins choose identically only when `sigma_rule = 0`,
    because rule noise is drawn per agent.
   *Final fixer:* with CRN rule noise (Final fixer 5) twins with traits off now choose identically when their states are identical. The LLM side was asymmetric (it dropped the disposition section); it now shows the four level-3 sentences by default (Final fixer 9).
17. **PT experienced time.** On a disrupted day PT takes `pt_time_min x pt_disruption_time_mult`
    whether or not the disruption was announced; PT departs at t* minus the expected PT time, so a
    disrupted trip arrives late (which can also trigger T3 the next day).
   *Correction (final fixer):* the sentence above holds only for an unannounced disruption. With the default `pt_disruption_announced = true` the rider plans for the doubled time, leaves earlier and is not late. PT now also has early-arrival schedule delay from a 10-min headway (Final fixer 6).
18. **Rule reasons.** The rule's reason is a template naming the GC part in which the chosen option
    saves most against the standing option (or the runner-up); factors are the top three saving
    parts mapped to the closed factor list (`parking` and `skip` map to `other` and
    `work_constraint`), plus `disruption` when T4 fired.
    *2026-10-09:* the `skip` part is gone with SKIP (its noise code 10003 is retired); a `forced`
    decision (PT the only option left) carries the factor `work_constraint`.
19. **Shared-file additions.** `types.Option.expected_public_delay_min` (optional, default None),
    `AgentMemory.company_car` with `new_memory(agent_id, company_car=False)`,
    `options.expected_public_delay(..., bin_min=None)`, `options.non_car_outcome(...,
    disruption_mult=2.0)`, and new helpers `options.car_outcome`, `options.pt_time_today`,
    `options.car_reference_depart`, `memory.record_from_outcome`, `persona.layer_a_key`,
    `vickrey.equilibrium_from_ratios`, `vickrey.departure_rate`, `vickrey.private_cost`.

## Integrator

1. **Capacity calibration metric.** `python -m cordonlite.run calibrate` bisects `capacity_scale`
   on a log scale (R-daily, fee regime "none", PyEngine, days 6-10). "Peak mean queue delay at the
   busiest corridor" is read as: for the corridor with the most cars over days 6-10, the maximum
   over 15-min gate-arrival bins of the mean queue delay of served cars, computed per day and then
   averaged over days 6-10 [A]. The day-to-day rule equilibrium is discrete and noisy (car counts on
   the busiest corridor swing between days), so the delay is not a smooth or monotone function of
   the scale. The tolerance is therefore 2 min (`engine.calib_tol_min`) and bisection also stops when
   the bracket collapses onto a discontinuity. With seed 1 and 300 agents the result is
   `capacity_scale = 0.2995` (peak 13.3 min against the 15 min target); scale 0.2965 gives 29.7 min
   and 0.3027 gives 10.2 min. The calibration is a knife edge because car and PT are close
   substitutes in the GC (see entry 4).
   *Final fixer:* the metric is now the car-weighted mean of the corridor peaks (`engine.calib_metric`), see Final fixer 2; the numbers above describe the superseded busiest-corridor calibration.
2. **Capacity scale applies to the demand-share base.** `capacity_per_min = max(min_capacity_per_min,
   base x capacity_scale)`, base from `engine.capacity_mode`. New keys in `[engine]`:
   `capacity_scale`, `use_calibration`, `calibration_file`, `calib_target_peak_delay_min`,
   `calib_days`, `calib_scale_bounds`, `calib_max_iter`, `calib_tol_min`, `calib_bin_min`. Runs use
   `data/calibration.json` when it exists and `use_calibration = true`; `--capacity-scale` overrides.
   *Superseded 2026-10-08:* the floor is `engine.min_capacity_vph` = 950 veh/h, converted to agents/min with the run's vehicles per agent; `min_capacity_per_min` is used only when `min_capacity_vph = 0`. See Motorway flow breakdown 14.
3. **A standing SKIP wakes the agent the next day.** Skipping is a one-day postponement, so a
   standing SKIP counts as an infeasible standing plan and fires T6 every following day
   (`clock._standing_feasible`). Without this, an agent that skipped once under a clock arm would skip
   for the rest of the run, because no other trigger fires. A rule agent can still choose SKIP again.
   *Final fixer:* the re-decision no longer favours SKIP (Final fixer 3) and SKIP scales with VoT (Final fixer 4).
   *Superseded 2026-10-09:* SKIP is removed, because it had become a permanent choice rather than a one-day postponement ("SKIP removed, willingness to travel and the peak charge" 2).
4. **Response to the charge is much stronger than observed cordons.** With the specification's GC
   and the scaffold values (VoT median about NZ$10/h, loss weight eta on a reference fee of 0, PT fare
   NZ$7, parking NZ$8 for about half of office workers), the car share falls from about 0.53-0.64 on
   day 10 to 0.22-0.32 on day 30 (about -45% to -60%), against about -20% in Stockholm and -12% in
   Gothenburg (v3 section 9). The defaults were NOT changed. A v3-style PT attitude penalty was added as
   an optional key `costs.pt_attitude_penalty` (omega(P) x PAP added to the PT GC; default 0 =
   specification). A quick test with R-clock (scale 0.30) showed that PAP 4-12 NZ$ moves the charge
   response from PT to WFH and SKIP rather than reducing it (day 30 cars 95, 124, 130, 134 of 300 for
   PAP 0, 4, 8, 12), so recalibration needs the VoT, the loss term and the WFH cost together. This is
   left to the authors.
   *Recalibration:* done; see "Behaviour recalibration" below.
5. **Reference fee never catches up for agents who stop driving.** `ref_fee` follows the fee actually
   paid (0 on non-car days), so for someone who left the car the charge keeps its full loss weight.
   Together with edge-triggered wakes this locks in the day-11 response under the clock arms.
   *Recalibration:* the reference now follows the fee faced (Behaviour recalibration 1); the clock arms still keep the day-11 response.
6. **Run folder naming.** `--traits off` appends `_traitsoff` to `<arm>_<backend>_<engine>_s<seed>`
   so the information-ladder run does not overwrite the main run.
   *Final fixer:* every non-default setting now adds a suffix, and runs are written atomically (Final fixer 15).
7. **Plans files for PyEngine runs.** PyEngine runs also write `plans_dayNN.csv` into the run folder
   (NetLogoEngine writes them itself), so any run can be replayed with `run-day-gui` in NetLogo.
8. **summary.json additions.** Besides the specified fields each day has `fee_active`,
   `unserved_cars`, `peak_bin_delay_by_corridor`, `peak_bin_delay` (worst corridor, 15-min bins),
   `cars_by_corridor` and `late_share`; `meta` holds the capacity, corridor names, call totals,
   total revenue and the LLM decider stats. No timestamps or timings are written, so outputs are
   byte-identical between repeated runs and between the two engines.
   *Extended 2026-10-07/08:* road keys per day (`mean_road_delay`, `max_road_delay`, `mean_car_travel_min`; the eight LoS keys of 2026-10-08) and `meta.road`; still no timings. See Road congestion 9 and Motorway flow breakdown 18.
9. **Estimate mode.** `--estimate` (alias `--dry-run`) simulates the L-* arm with MockLLM and
   PyEngine in a temporary folder and counts the prompts. The count is approximate because a real LLM
   would choose differently and so wake agents on other days; tokens are characters / 4 for system
   plus user prompt, excluding schema, adaptive thinking and output.
10. **Forced decisions never occur.** Every agent has at least CAR options and SKIP, so `forced` is
    implemented but never used.
    *Superseded 2026-10-09:* a commuter whose car options the willingness to pay removes and who has
    no WFH is left with PT only and is `forced` (60 a charged day on seed 1); see "SKIP removed,
    willingness to travel and the peak charge" 5.
11. **Vickrey check figure.** The analytical equilibrium uses one t* (the drivers' median, shifted to
    the gate) and mean VoT; simulated commuters have t* spread over 07:00-10:00, so the simulated
    queue is much lower and longer than the single-t* triangle. The figure is a sanity check of
    orders of magnitude, not a validation.

## Final fixer

Changes made after the review. Numbers quoted are from the seed-1, 300-agent, 30-day mock runs
in `runs/` (MockLLM is a deterministic stand-in, not an LLM).

1. **End of a PT disruption wakes the riders it woke (T4).** Under the clock arms a one-day
   disruption used to move PT riders to the car for good: nothing woke them on day 21, and the
   "experienced yesterday" T4 of riders who stayed on PT shared the key of the announcement. The
   clock now adds the event key `("T4-end", d)`: on day d+1, an agent whose day-d decision was a
   T4 wake by the announcement, and whose corridor runs normally again, wakes once more (reported
   as T4, a discontinuity wake). The prompt then says "Buses and trains from your area are running
   normally again today." R-clock PT riders: 123 on day 19, 107 on day 20, 120 on day 21 (before
   the fix, 13 riders switched and only 2 returned).
2. **Calibration metric.** The integrator calibrated the busiest corridor only, so other corridors
   ran at 2-3 times the target and the summary's "peak delay" (worst corridor) showed 30-55 min.
   `engine.calib_metric` (default `car_weighted_mean` [A]) now averages the per-corridor peak
   15-min mean queue delay with the day's car counts as weights; `worst` and `busiest` remain
   available. Result: `capacity_scale = 0.3961`, metric 15.75 min against 15 (corridor peaks
   0 / 22.0 / 4.3 / 27.7 / 15.6 min for corridors 0-4). The response to the scale is smoother than
   before (0.3646 gives 18.8, 0.4303 gives 10.9). `summary.json` now has `peak_bin_delay_wmean`
   (the calibrated metric) next to `peak_bin_delay` (worst corridor); both appear in the summary
   table and in `queue_delay.png`. The calibration file stores seed and n_agents; a run with a
   different seed or n_agents prints a warning and records "MISMATCH" in
   `meta.capacity_scale_source` (the traits setting is not checked: the information-ladder run
   deliberately keeps the main runs' capacity). The default `run.seed` in `config.toml` is now 1,
   the seed of the canonical runs and of the calibration (it was 11).
   *Superseded 2026-10-07/08:* with congested roads the target measures the car-weighted peak of gate queue + road delay (`engine.calib_delay = "total"`), at 950 agents; the scales above are for 300 agents on free-flow roads. See Road congestion 10 and Motorway flow breakdown 16.
3. **A standing SKIP is not a habit.** On the re-decision after a SKIP, every non-SKIP option
   carried kappa_H and SKIP none, which pushed agents to skip again (agent 94 skipped 30 of 30
   days). `AgentMemory.habit_option_id` returns the most recent non-SKIP option for a standing
   SKIP; it is the habit reference in `build_options`, the "usual" option in the prompt and
   `DecisionContext.standing_option_id`.
   *Superseded 2026-10-09:* SKIP is removed and `habit_option_id` is deleted; the standing option is
   the reference ("SKIP removed, willingness to travel and the peak charge" 2).
4. **SKIP cost scales with the value of time.** A flat NZ$25 made SKIP the cheapest option for
   high-VoT agents even without a charge. SKIP now costs `skip_cost + skip_vot_hours x VoT` with
   `skip_vot_hours = 1.0` [A] (a lost or postponed day is worth more to someone whose time is worth
   more). No agent skips in the canonical runs, so the clock arms no longer have a floor of daily
   T6 calls (R-clock: 0 decider calls on most days after day 12).
   *Superseded 2026-10-09:* SKIP and its keys `costs.skip_cost` and `costs.skip_vot_hours` are removed.
5. **Common random numbers for rule noise.** Rule noise was drawn per agent id, so twins with
   identical A (and, with traits off, identical B) got independent draws and about half of the
   rule-arm twin divergence was noise. The draw for an option is now
   `stream(seed, "rule", noise_id, day, option_code(option_id))`, where `noise_id` is the source
   agent's id for a twin (`run.noise_ids`). With traits off, twin pairs now agree on day 1 (0 of
   30 differ, was 8) and differ later only through their histories (3 of 30; the engine serves
   ties in agent-id order, so twins can see different delays). MockLLM keeps the specified
   prompt-hash seed, which already gives identical answers to identical prompts.
6. **PT schedule delay.** PT used to arrive exactly at t* with no schedule cost, a structural
   advantage over the car (15-min grid with schedule cost). PT services now leave on a
   `costs.pt_headway_min = 10` grid [A]; the rider takes the latest service that arrives by t*,
   and the early arrival (0-9 min) is costed like the car's (`phi x sched_mult x VoT/60 x
   beta_ratio x early`). The prompt shows the PT departure and arrival time, so the LLM sees it.
7. **Zero-fee property (v3 RT3) still fails.** Before the charge (day 10) 20-29% of agents use PT
   or WFH (R-clock: car 0.787, PT 0.063, WFH 0.150), whereas v3 RT3 asks for at least 99% driving
   at zero fee. This follows from the specified GC (WFH and PT avoid parking and car time; see
   Behaviour 6) and is not changed. The charge response stays much stronger than observed cordons
   (R-clock car share 0.787 to 0.340, -57%; Stockholm about -20%). Recalibration (VoT, eta, WFH
   cost, PAP) remains the authors' decision.
   *Recalibration:* R-daily base car 0.85 and response -21% (seeds 1-3); see "Behaviour recalibration".
8. **Who adapts.** `table_who_adapts` compares the modal mode over days 6-10 with the modal mode
   over the last 5 days (not two single days), excludes twins, and reports n and 95% Wilson
   intervals; `who_adapts.png` greys out cells with fewer than 10 drivers, labels archetypes and
   marks archetype 4 (car only) as a structural zero. The habit effect is still weak and
   non-monotone (R-clock share leaving the car by H level 1-5: 0.90 (n=10 drivers), 0.27, 0.62, 0.62, 0.58).
   This is a result of the assumed mapping, not a finding: at T2 kappa_H is halved (at most
   NZ$1.5) while the S loss term on a reference fee of 0 adds up to 3 x NZ$6. Not changed;
   report it with the intervals, or run a capped-eta or unhalved-kappa sensitivity before claiming
   trait effects.
   *Recalibration:* eta is capped and kappa_H is no longer halved at T2. The unbiased trait check is
   now the population manipulation in `docs/calibration_report.md`; who-adapts tables conditional on
   being a driver are biased by selection.
9. **Traits-off information parity.** With `--traits off` the rule used level-3 parameters while
   the LLM prompt dropped the disposition section. The specification says traits off sets every
   trait to level 3, so the prompt now shows the four level-3 sentences by default
   (`llm.traits_off_prompt = "sentences"`), which matches the rule. `"omit"` drops the section (the
   v3 section 8 neutral cell, which would also need a neutral rule: eta = 0, kappa_H = 0).
10. **Information parity between rule and LLM.** The prompt no longer names the activity: work and
    study share the same sentences ("You travel to your regular destination ... and need to be
    there by hh:mm"; "Doing your day's work from home ..."). Start-time flexibility is a graded
    sentence following the rule's `sched_mult` (0.5, 0.75, 1.0, 1.5), not a fixed/flexible binary.
    Remaining asymmetries, kept on purpose: the LLM is not told `wfh_cost` or the SKIP cost (they
    stand for intangible costs the LLM is asked to judge); the rule sees the memory only through
    the delay-ratio and reference-fee EMAs, while the LLM sees the 5-day table; MockLLM scores GC
    parts (`ref_fee`, kappa_H, `sched_mult`) that the prompt shows only in words.
11. **LLM cache and identical prompts.** The key is the specified one (model, effort, template id,
    system, user, schema) plus, as `extra`, `max_tokens`, the fallback setting and `llm.replicate`
    when it is above 0. `llm.template_id` from config is now used (and must be `cl-v1`). The
    reviewer's proposal to add the agent id to the key was not adopted: v3 section 7.5 says agents
    share an answer only if every rendered line is identical and the key is never per agent.
    Instead, identical keys within one morning are sent once and the answer is shared (`shared`
    records in `llm_calls.jsonl`), so a live run and its cache replay give the same decisions.
    The cache is shared across arms, so L-clock and L-daily share their identical day-1 prompts
    (common random numbers across arms). For independent samples set `llm.replicate`. The v3 7.5
    diagnostics are in `runs/figures/llm_diagnostics.*`: cache hit rate, shared answers, distinct
    prompts per agent overall and per A cell on day 11, and within-cell mode entropy against the
    matched rule arm (L-clock traits off: 58 shared answers, 0.93 distinct prompts per agent).
    *Superseded 2026-10-07:* `llm.template_id` must now be `cl-v2` (road traffic in the prompt; the text equals `cl-v1` with `road.enabled = false`); see Road congestion 8.
12. **Fail fast and log every call.** 401, 402, 403 and 404 (and missing credentials) raise
    `LLMFatalError` and stop the run; so do `llm.max_consecutive_errors` (5 [A]) API errors in a
    row. Any other exception from a call is recorded and the agent falls back to the rule, instead
    of aborting the morning batch. Each record is appended to `llm_calls.jsonl` when its call
    completes, and a failed run keeps its partial folder as `<run>.failed`. `run_simulation`
    checks that the SDK can resolve credentials (API key, auth token or an `ant auth login`
    profile) before day 1. `llm.effort` and `llm.fallback_beta` are validated in `config.py`.
    `summary.json` reports `llm_fallback_share`, and the summary table lists LLM decisions and
    rule fallbacks separately.
13. **Retry policy.** The app-level API retry loop is gone: 429, 5xx and connection errors are
    retried by the SDK client only (`max_retries = 5`). The invalid-output retry is used only for
    unparsable or truncated JSON, a missing text block or a choice outside the option ids. A 400
    or any other API error, and a refusal, go to the rule fallback without being resent. (Before,
    a persistent 529 produced 36 HTTP requests for one agent-day.)
14. **Twin evidence.** `twins_summary.*` reports, per run, the pairs that choose differently on
    days 1, 10, 11, 12, 20 and 30, and on day 11 among the pairs that held the same option on
    day 10. The traits-off rows are the noise-and-history baseline. Seed 1: day-11 divergence given
    the same day-10 option is 6 of 20 (R-clock), 1 of 13 (L-clock mock), 3 of 27 (both traits-off
    runs). The MockLLM rows are pipeline checks only; v3 10.2 repeated-sample probes remain the
    proper twin test for a real LLM.
15. **Run folders and CLI.** The default run folder adds a suffix for every setting that differs
    from `config.toml`: `_n<N>`, `_d<D>`, `_<regime>`, `_fs<K>`, `_cs<X>`, `_set-<hash>`. A run is
    written to a temporary folder and renamed only on success, so neither a variant nor a crash can
    overwrite or destroy a finished canonical run. `--set` values are type-checked against the
    config (a string for a number is a config error, not a traceback mid-run), and explicit flags
    take precedence over `--set` with a warning. `python -m cordonlite.analysis` uses only canonical
    runs of one seed by default (`--seed`, `--all`, `--run-dirs`); variant runs are labelled with
    their suffix.
16. **NetLogo outputs and GUI.** After a NetLogo run, the per-day exchange files
    (`outcomes_dayNN.csv`, `profile_dayNN.csv`) are removed, so both engines leave the same set of
    files; `compare_runs` checks the file set, and compares `summary.json` and
    `config_snapshot.toml` without the engine label. The two engines are identical apart from that
    label. GUI: run folders carry `scenario.csv` (`charge_from_day`, `n_days`), which
    `setup-from-dir` reads, so replay uses the run's charge days; `run-day-gui` writes into
    `gui_replay/` and stops after the last plans file. Corridor labels are short (compass, id,
    "agents/h", the scaled service rate of the simulated sample) and nudged apart; green is no
    longer a corridor colour (it marks PT users); the charge in the entries plot is scaled to the
    highest bar; axes say "minutes after midnight".
17. **Clock behaviour kept but stated.** T3 is keyed per late day, so a chronically late agent wakes
    on consecutive days (per event day, not per episode); T6 is level-triggered for a standing
    SKIP. After day 12 the clock is almost silent apart from the disruption, which locks in the
    day-11 response; the specification lists only T1-T6, so no periodic review (v3 T7) or
    reference-fee re-anchoring trigger was added.
18. **Figures.** `departure_hist.png` is now `crossings_hist.png` (it shows gate exits); crossing
    figures end at 10:15. LLM arms are labelled "(mock)" when the backend is MockLLM.
19. **Call share.** The integrator's "9-11% of the daily arms' calls" was inaccurate (R-clock was
    1,086 of 9,000 = 12.1%). With the final code: R-clock 917 (10.2%), L-clock 882 (9.8%).

## Behaviour recalibration

The rule decider responded to the charge about three times as strongly as observed cordons (R-daily
car crossings -56% on days 21-30 against days 6-10; Stockholm about -20%, Gothenburg about -12%).
Structural fixes that the v3 note already justifies were applied first; then three scalars were
calibrated on R-daily only (rule decider, PyEngine, seeds 1-3, n = 300, 30 days) by
`scripts/calibrate_behaviour.py` (grid search, every point logged in `data/behaviour_calibration.json`;
report and figures in `docs/calibration_report.md`). The LLM deciders are never tuned; shared Layer A
inputs set by the rule calibration (paid parking) do reach the LLM prompt (item 6). The previous
behaviour remains selectable through config keys, and the pre-recalibration runs are kept in
`runs_pre_recalibration/`.

1. **Reference fee follows the fee faced** (`memory.ref_fee_update = "faced"`, new value; v3 5.2
   fee-ref). Every day `ref <- ref + alpha x (f - ref)`, where f is the fee paid on a car day and
   otherwise the fee at the agent's car reference departure (`options.fee_faced`: standing car
   departure, else the last car day, else the day-1 rule; 0 for company cars). `alpha` is
   `memory.ema_alpha` (0.3, SPEC) rather than v3's 0.2. Before, agents who left the car kept a
   reference of 0 and a loss term on the full fee for ever (only 2-8% returned). New:
   `update_memory(mem, record, cfg, fee_faced=None)` and `options.fee_faced(...)`; `run.simulate`
   passes the fee faced. `"all_days"` (the specification) and `"car_days"` remain available.
   Two differences from v3 5.2 remain [A]: on car days the fee actually paid (after any retiming)
   is used, whereas v3's fee-faced is the fee at the preferred hour h0 before retiming, so a
   retimer's reference converges to the lower fee it now pays and a loss term eta x (peak fee -
   ref) stays on a return to the peak; and alpha is 0.3 (SPEC) rather than v3's 0.2. Not changed,
   because it would move the calibrated behaviour; `options.fee_faced` on car days would match v3.
2. **Loss weight capped** (`traits.eta = [0, 0.25, 0.5, 0.75, 1]`; was `[0, 0.5, 1, 2, 3]`): the v3
   4.4 capped variant; De Borger and Fosgerau (2008) make a total weight of 1 + eta = 4 generous. For
   day-11 leavers the loss term (mean NZ$6.5) had been larger than the fee itself (NZ$4.9).
3. **WFH priced as in v3** (`costs.wfh_form = "v3_relative"`, new key; `"spec"` keeps
   `wfh_cost x phi`). v3 6.2 prices WFH relative to driving at the usual time without a charge and
   gives it no PARK term (zero-fee property). In Cordon-Lite's absolute GC this is
   `wfh_cost x phi + VoT/60 x free-flow time + parking`: WFH earns no commute-time or parking credit
   but still avoids congestion delay, schedule delay and the charge. Before, the 13-16% who worked
   from home before the charge were high-VoT agents saving parking and car time.
4. **No habit discontinuity at a price change** (`clock.discontinuity_triggers = ["T1", "T4",
   "T6"]`; v3 7.1 also lists T2) [A]. Verplanken et al. (2008) tie habit discontinuity to a change in
   the performance context (relocation); a charge leaves route, time and cues intact. kappa_H is
   therefore not halved at the charge wake (`kappa_h_disc_factor` stays 0.5 for T1, T4, T6).
5. **PT attitude penalty on** (`costs.pt_attitude_penalty = 11`, [CAL]; v3 6.2 PAP NZ$8, swept
   {4, 8, 12}). The specification's form `omega(P) x (VoT/60 x T_pt + PAP) + fare` is kept (v3
   applies omega to PAP only and says omega "scales only the attitude penalty, not PT time"), and
   v3's home-transit-access factor HTA/2 is not represented: one PAP for all homes [A]. The value
   is therefore not comparable with v3's: v3's attitude term is omega x PAP x HTA/2 (HTA 1 local,
   2 boundary), i.e. 2 to 12 x omega over its sweep, so Cordon-Lite's 11 x omega equals v3 PAP 11
   (boundary homes) to 22 (local homes), on top of omega-scaled PT time. It is not "inside the v3
   sweep" in effect; P = 1-2 agents practically never ride PT (PT share 0.00 and 0.03 at P = 1, 2 in
   the population manipulation).
6. **Paid parking NZ$17/day** for office archetypes 1-3 (student 0.75 x = NZ$12.75; were 8 and 6),
   [CAL], in effect a fitted value and the largest lever (x2.1). NZ$17 is not on the coarse grid
   (8, 10, 12, 15, 18); it entered with the refinement grid along the ridge the coarse grid found,
   so it was fixed after coarse-grid results had been seen. It is used as a plausibility check, not
   an independent anchor: NZ$17 was the casual all-day rate of Auckland Transport's Downtown, Civic
   and Victoria Street car parks from 1 December 2014 (Greater Auckland, 18 Nov 2014, quoting AT;
   the $13 earlybird ended then; not in the v3 reference list); current rates are higher and leased
   spaces cheaper. v3 swept {4, 8}, says its parking values "are not Auckland parking prices", and
   warns that paid parking above NZ$8 fails the zero-fee property for P = 5 local agents (v3 6.2
   PARK row); at NZ$17 many P >= 4 agents with paid parking ride PT before any charge.
   `park_free_prob` (0.5) is unchanged. Parking is a shared Layer A input: the LLM prompt states it
   ("Parking at your destination costs you NZ$17.00 a day"), so "the LLM arms are never calibrated"
   means the LLM deciders were not tuned, while their inputs include values set by the rule calibration.
7. **k_WFH kept at NZ$8** [v3]; searched 2-8. 8 is the edge of the searched range, so the value
   is the v3 value, not identified by the calibration. At 8, WFH is about 1% before the charge. k_WFH = 4 gives
   about 6%, but then the charge pushes hybrid workers near indifference into WFH every day and the
   response reaches about -30%. v3's WFH quota (1-3 days per 5-day block) would bound that margin and
   is still not implemented (scaffold entry 4): a rolling or block quota synchronises WFH days across
   agents unless office days are staggered.
8. **Search and selection.** Coarse grid PAP {4, 6, 8, 10, 12} x parking {8, 10, 12, 15, 18} x k_WFH
   {2, 4, 6, 8}, refinement PAP 6-12 x parking 14-18 at k_WFH 8: 127 points x 3 seeds. For every
   point and seed, capacity is recalibrated first with `run.calibrate` (a nested solve, so behaviour
   and capacity are consistent at every point). Selection: feasible points (3-seed means in band at
   the targets' stated precision, every seed within ±0.05 in shares and ±4 pp in the response), then
   nearest to the anchors (PAP 8, parking 17, k_WFH 8), then a loss. Only 2 points are feasible (PAP
   11 with parking 17 or 18), and only because feasibility rounds the means (base car 0.8533 ->
   0.85, overshoot -30.2% -> -30%): strictly, no grid point meets every band. PAP 11 / parking 17
   is chosen and is also the lowest-loss point, so the choice survives without rounding. The
   targets are tight because base car and base PT nearly sum to 1 when WFH is about 1%, and PAP and
   parking are nearly collinear for the baseline. The soft overshoot target ("about -30%") acts as
   a hard bound and decides between PAP 8 and PAP 11: with the bound at -31% (not -32%, as stated
   before) PAP 8 / parking 15 is chosen; it keeps the v3 PAP and meets the base car and PT bands
   strictly (0.841, 0.150) and misses only the overshoot, by 1.2 pp. The defensible reason to keep
   PAP 11 is out of sample (`--stage oos`, run after the selection): on seeds 4-12 PAP 8 / parking
   15 gives -22.8% and an overshoot of -32.6% against -20.7% and -29.8% for the chosen point (PAP 10
   / parking 17 is about as good as the chosen point; the choice was not changed). The selection
   log is append-only from this version (`search.selection_history`); earlier selection rules were
   overwritten and are not recoverable.
9. **Result** (R-daily, mean of seeds 1-3; targets in brackets): base car 0.853 (0.75-0.85; 0.85 at
   the stated precision; seed 1 0.899, within tolerance), PT 0.137 (0.08-0.15), WFH 0.009 (at most
   0.10), SKIP 0 (at most 0.02), days 11-13 -29.4% (to about -30%), days 21-30 -20.9% (-12% to -22%,
   centre -20%); per seed -21.5%, -21.1%, -20.2%; held-out seeds 4 and 5 -22.1% and -23.2%; unseen
   seeds 6-12 -20.2% (mean; base car 0.859, overshoot -29.5%; seed 6 base car 0.907 and seed 12
   overshoot -36.0% are outside the single-seed tolerance). Over seeds 1-12 base car is 0.861, just
   above its band. Before: base car 0.713, WFH 0.161, response -56.5%, overshoot -60.4%. With the
   structural fixes alone at the v3 values (PAP 8, parking 8, k_WFH 8) the response is already
   -15.4% (overshoot -25.0%), inside both response bands; only the assumed baseline shares miss
   (car 0.968, PT 0.019). The scalars were moved to meet the baseline, which also strengthened the
   response to -20.9%; the match with Stockholm is partly a by-product of that fit.
10. **Capacity per seed.** `python -m cordonlite.run calibrate --seeds 1 2 3` stores one record per
    seed under `by_seed` in `data/calibration.json` (the top level stays the seed-1 record);
    `resolve_capacity_scale` uses the run's own seed record when its n_agents matches, so seeds 2 and
    3 no longer run with the seed-1 scale. Scales 0.4974, 0.4303, 0.4128 (was 0.3961 for all seeds).
11. **Still open.** VoT stays at the SSC lognormal (mu 2.3; median about NZ$10/h; not calibrated).
    Retiming is weak: the peak-band share of crossings is 0.4-4.7 points below a same-capacity
    no-charge run in two of three seeds and not in seed 2; NZ$6-band crossings fall 26% against 8%
    before 07:30, and crossings after 09:30 rise 29%. This is consistent with Karlström and Franklin
    (2009) but thin. H damps the day 11-13 response only from level 2 upwards (-32.6% at H = 2 to
    -25.2% at H = 5, population manipulation) and not in the long run, because habit re-forms on the
    new mode. The charge-induced PT switch peaks at P = 3-4 (at P = 5 most agents for whom PT is viable
    already ride PT). Clock arms keep the day-11 overshoot (no trigger after day 12; v3 7.1).
    The F response gradient (-10% to -37% across F) comes mainly from F = 4-5 hybrid workers
    switching to daily WFH (WFH share d21-30 about 0.00 at F = 1, 0.04 at F = 3, 0.25 at F = 5),
    which is unbounded without v3's quota; retiming of car keepers against the no-charge run is
    flat across F (the paired departure change rises from 0.27 to 0.44). It is not evidence that
    high F retimes more.
12. **Tests.** Specification-form tests now set the spec keys explicitly (`test_gc_formula_pt_wfh_skip`,
    `test_ref_fee_all_days`). New tests cover the fee-faced reference, the v3 WFH form, `fee_faced`,
    PAP x omega, per-seed calibration records, T2 as a non-discontinuity and monotone trait effects at
    the charge wake (H keeps the standing car, P raises PT, S lowers car, F raises retiming to a cheaper
    crossing). Review fix: the worked-example tests now take the discontinuity flag from the config
    (`is_discontinuity(("T2",), cfg)`); before, they passed `discontinuity=True` on the T2 wake and so
    certified a habit-halving path the shipped model never takes. `test_identical_a_different_b`
    runs the shipped config (sigma 0 only) with paid parking NZ$17 and personas payer (5,1,1,1), PT
    (2,3,3,4) and retimer (1,5,1,5): retiming needs H = 1, because kappa_H(H = 2) = 0.5 is no longer
    halved. `test_v3_worked_example` reproduces v3 section 11 (free parking, payer (5,1,1,1), PT
    (2,3,5,4), retimer (2,5,1,5) with S = 5 because eta is capped at 1) only with the v3 settings:
    PAP 4 (= v3 PAP 8 x HTA/2 for a local home) and T2 a discontinuity.
    `test_v3_worked_example_does_not_separate_under_defaults` records that under the defaults those
    three free-parking personas all keep driving at their standing time.
13. **Canonical runs and documents.** All canonical mock runs, the NetLogo R-clock run (identical to
    PyEngine), the estimates and the figures were regenerated, and the README results and limitations
    updated. MockLLM numbers changed because MockLLM re-weights the same GC parts.
14. **Response anchors are not like-for-like.** Stockholm (about -20%) and Gothenburg (about
    -12%) are reductions of total cordon-crossing traffic in charged hours (all vehicles and
    purposes), observed over months to years. v3 10.5 treats them as soft checks, notes that
    private-car elasticities (-0.85 to -1.9) are about twice the total-traffic ones (-0.4 to -0.9),
    and asks for a qualitative comparison only. Cordon-Lite uses them as a hard band for AM
    car-commuter crossings on days 21-30, with days 11-13 standing in for Stockholm's early -28%
    then -23%. The band is a stated assumption, not a validation; a private-car commuter response is
    likely larger. AT option 1a (v3 10.5: about -3,600 AM-peak vehicle trips against about 19,000
    charged vehicles, about 19%) is indicative Auckland support only.
15. **Rule versus LLM on the WFH margin.** Under `wfh_form = "v3_relative"` the rule and MockLLM
    give WFH no parking or free-flow commute credit, but the LLM prompt states the daily parking cost
    and offers WFH. A real LLM will naturally count the parking saving, which the calibrated rule
    deliberately omits, so live-LLM WFH shares are not comparable with R-daily on this margin
    (MockLLM inherits the rule's GC parts and cannot reveal it). Not changed: rephrasing the parking
    line would change every MockLLM prompt, hence the mock runs.

## Fuel cost

Added on 2026-10-03, after the behaviour recalibration, at the first author's request: paid parking
at NZ$17 a day was only that high because the car option had no fuel cost (driving cost time,
schedule delay, charge and parking). The entries above describe the model before this change; where
they give NZ$17, PAP 11 or results of the canonical runs, the values below replace them. The earlier
state is kept in `data/behaviour_calibration_pre_fuel.json`, `data/calibration_pre_fuel.json`,
`docs/calibration_report_pre_fuel.md`, `docs/figures/pre_fuel/` and `runs_pre_fuel/`.

1. **Fuel is a separate cost of the car option** (departure from the specification and from v3).
   `fuel = round(2 x path_km x costs.fuel_cost_per_km, 2)` NZ$ a day: a round trip, like the daily
   parking cost and the round-trip PT fare. `persona.path_km` is the one-way path length from prep
   (mean about 14.3 km over seeds 1-3). Company-car and work-vehicle agents pay 0, the same rule as
   for parking. v3 6.2 has no fuel term and states that fuel and other operating costs are folded
   into its parking value [v3 A]; here parking is parking alone.
2. **The per-km value is fixed from evidence, not calibrated**: `costs.fuel_cost_per_km = 0.23` [L]
   = regular petrol NZ$2.53/L x 9.0 L/100 km (0.228, rounded).
   - Price: MBIE Weekly Fuel Price Monitoring, regular petrol, first week of September 2025, sum of
     the published components (importer cost 95.68 + ETS 13.22 + taxes 77.37 + importer margin 34.12
     + GST 33.06 = 253.45 c/L); series page
     https://www.mbie.govt.nz/building-and-energy/energy-and-natural-resources/energy-statistics-and-modelling/energy-statistics/weekly-fuel-price-monitoring,
     components read from the Figure.NZ chart of the MBIE release of 30 September 2026
     (https://figure.nz/chart/TOUlLL81q1WORRyQ). The MBIE page itself could not be read by the fetch
     tool, so the figure rests on the Figure.NZ copy; the components are internally consistent (GST
     is 15% of the rest). 2025 is used because the charge schedule and the other prices are 2025
     values. The same series gives 296.70 c/L for the first week of September 2026, i.e. NZ$0.27/km.
   - Consumption: 9.0 L/100 km, the estimated real-world fuel use of NZ petrol light vehicles of
     build years 2013-2014 (9.0-9.3 for 2010-2014), Metcalfe and Sridhar (2016), *Real world energy
     use projections for VFEM*, Emission Impossible Ltd for the Ministry of Transport, Table 5
     (https://www.transport.govt.nz/assets/Uploads/Data/Transport-outlook-updated/Emission-Impossible-Real-World-Energy-Use-Projections-for-VFEM-20160905.pdf).
     A current EECA or NZTA fleet average could not be retrieved. A web search summary of an AA
     "Ask an expert" answer attributes about 10 L/100 km for the petrol fleet to Ministry of
     Transport data (the page itself returned 404), so 9.0 may be on the low side.
   - It is fuel only, not the IRD mileage rate, which covers ownership costs. Every paying driver is
     priced as a petrol car; electric vehicles, fuel cards and other running costs are not modelled.
   - Mean daily fuel cost of an agent who pays it: NZ$6.5, 6.6 and 6.7 on seeds 1-3 (10th to 90th
     percentile about NZ$2 to NZ$10).
3. **Where fuel appears** (the same places as parking). `Persona.fuel_cost` (Layer A, derived, no
   random draw, so no other persona field changes); `Option.fuel` and `gc_parts["fuel"]` for CAR
   options (`GC_PARTS` has nine keys); `outcomes.csv` column `fuel_paid`; `personas.csv` column
   `fuel_cost`; MockLLM weight `llm.mock.w_fuel = 1.0` (as parking); rule and MockLLM reasons map
   fuel to the factor `other`. The NetLogo engine is unaffected (it handles queues and fees only).
4. **WFH earns no fuel credit** under `wfh_form = "v3_relative"`: WFH = k_WFH x phi + VoT/60 x
   free-flow time + parking + fuel. This follows the logic already used for parking (Behaviour
   recalibration 3): v3 prices WFH relative to an uncharged drive at the usual time, so every cost
   of that drive that WFH avoids is added back, and WFH minus an uncharged, unqueued drive stays
   k_WFH x phi (zero-fee property). Left as a WFH saving, the fixed fuel cost would act as a WFH
   advantage of about NZ$7 a day for hybrid workers, against that property (not run as a variant).
   Under `wfh_form = "spec"` WFH carries neither parking nor fuel.
5. **Prompt** (information parity). The situation section states "Fuel for the drive there and back
   costs you about NZ$x a day." (or that it costs nothing, naming the employer for an employer
   vehicle), and the options table has a `fuel` column after `parking`. The template id stays
   `cl-v1`: the live API has never been called, so no stored answer uses the old wording, and the
   cache key includes the full prompt. Every MockLLM prompt changed, hence all mock runs.
   *Superseded 2026-10-07:* the template id is now `cl-v2` (Road congestion 8).
6. **Recalibration.** Same targets, seeds (1-3, held-out 4-5, unseen 6-12), loss and selection rule;
   only the paid-parking grid moved down (coarse 4, 6, 8, 10, 12, 15, 18; refinement 7-13 in NZ$1
   steps at k_WFH 8; both fixed before the runs; 178 points). Result: **PAP 12, paid parking NZ$11
   (student NZ$8.25), k_WFH 8** (before: PAP 11, parking NZ$17, k_WFH 8). Parking fell by about the
   mean daily fuel cost. R-daily, mean of seeds 1-3: base car 0.835, PT 0.154, WFH 0.009, SKIP
   0.001, days 11-13 -30.9%, days 21-30 -20.3% (per seed -18.3%, -20.8%, -21.7%); held-out seeds 4
   and 5 -20.7% and -20.3%; unseen seeds 6-12 -20.3% (base car 0.839, PT 0.146, overshoot -31.4%).
7. **What did not work as before.** No grid point is feasible, even after rounding (before: two).
   The rule's fallback, the lowest loss, picked the point. It misses the soft overshoot bound by
   about 1 pp and has base PT in band only after rounding (0.154 -> 0.15). PAP 12 is the upper edge
   of the searched range (4-12). An edge check run after the selection (PAP 13-14, parking 9-14;
   `pap_edge_check` in the log) shows that PAP 14 / parking 12 would meet every band (base car
   0.850, PT 0.138, overshoot -28.5%, response -19.3%). It was not adopted, to keep the method and
   range unchanged; extending the PAP range is an open decision for the authors. On unseen seeds,
   seed 6 responds by -11.7% and seed 12 by -30.1% (overshoot -39.9%), the latter outside the
   stated single-seed tolerance.
8. **The v3-valued sensitivity changed meaning.** With fuel on top of v3's NZ$8 parking (which v3
   meant to include fuel) the structural-fixes-only model gives base car 0.818, PT 0.175 and a
   response of -24.5% (overshoot -36.6%), outside the bands. The like-for-like v3-valued model is
   the one without fuel (-15.4%, overshoot -25.0%; `--set costs.fuel_cost_per_km=0` with the v3
   scalars).
9. **Script changes** (`scripts/calibrate_behaviour.py`). The `before` state sets fuel to 0 (the
   specification); the ridge alternatives for the out-of-sample stage are chosen from the log
   (`ridge_alternatives`: points that become feasible at an overshoot bound of -33%, nearest the
   anchors) instead of being hard-coded; the `oos` stage adds the PAP edge check; the report has a
   "Fuel cost added" section and a parking-anchor sensitivity; the `search` stage carries the
   archived selection history forward and appends the replaced selection.
10. **Capacity.** Recalibrated per seed: 0.5078, 0.4128, 0.4128 (before 0.4974, 0.4303, 0.4128).
11. **Tests.** New: fuel as a car GC part and attribute, WFH without fuel credit, `fuel_paid` rows,
    persona fuel from path length (company cars 0, no other field changes), config key and bounds,
    the prompt's fuel sentence and column, MockLLM fuel weight. `test_identical_a_different_b` now
    gives the three personas paid parking NZ$11 and the fuel cost of their 20 km path (NZ$9.20).
    `test_v3_worked_example_does_not_separate_under_defaults` records the new limitation: with fuel
    the free-parking PT persona switches to PT, the retimer (H = 2) still does not retime (449 of
    625 trait combinations keep the car at the usual time, 170 switch to PT, 6 retime); without fuel
    all three keep driving, as before. 231 tests pass (3 NetLogo tests run separately).
12. **Rule versus LLM on the WFH margin** (extends Behaviour recalibration 15). The prompt now
    states two costs of driving that the rule does not count as WFH savings, parking and fuel, so a
    real LLM is even more likely than before to favour WFH relative to the rule.
13. **Canonical runs and documents.** All canonical mock runs, the NetLogo R-clock run (identical
    to PyEngine), the estimates, the figures and `docs/example_prompt.md` were regenerated; README,
    `../docs/technical_reference.md` and `../paper/architecture.md` carry the new numbers.

## Periodic review trigger (T7), 2026-10-03

`clock.review_every_days` (default 0 = off) adds T7: an agent that has followed its standing plan
for N days is woken. v3 listed a weekly review as an off-by-default variant. It is used only as a
sensitivity test of clock lock-in; canonical runs are unchanged (default off). Rule results, car
crossings days 21-30 vs 6-10, seeds 1-3, with parking and fuel fixed by the authors (next entry):
event-only clock -22 to -27% (935 to 1,250 decisions), review every 10 days -18 to -22% (1,212 to
1,526), every 5 days -17 to -23% (2,134 to 2,361), daily -16 to -21% (9,000). Per seed (1 / 2 / 3):
daily -18.3 / -20.5 / -16.4%; event-only -24.2 / -26.9 / -22.4%; review 10 -17.5 / -22.4 / -19.2%;
review 5 -16.5 / -23.0 / -17.3%. Days 11-13: daily -28.3 / -31.0 / -27.3%; event-only -27.8 / -33.7 /
-25.1%; review 10 -27.8 / -33.7 / -25.1%; review 5 -26.3 / -33.8 / -24.1%. Before that change (fuel
NZ$0.23/km, parking NZ$11; `runs_fuel023_park11/`) the values were -30 to -34%, -23 to -27%, -21 to
-25% and -18 to -22%. Not yet run with the mock or a real LLM.

*Superseded 2026-10-07/08:* these numbers are for 300 agents on free-flow roads (before Road congestion and Motorway flow breakdown, below). Rerun on 2026-10-09 at 950 agents with congested roads, PAP 22 and k_WFH 9 (Motorway flow breakdown 17), car crossings days 21-30 vs 6-10, seeds 1 / 2 / 3: daily -19.8 / -22.8 / -19.6% (28,500 decisions); event-only -25.3 / -27.1 / -26.4% (2,629 / 2,695 / 2,504); review every 10 days -22.2 / -24.6 / -21.9% (3,502 / 3,579 / 3,413); every 5 days -20.2 / -23.3 / -20.5% (6,308 / 6,396 / 6,234). Days 11-13: daily -25.3 / -29.4 / -26.9%; event-only and review 10 -27.6 / -30.2 / -29.1%; review 5 -25.7 / -28.9 / -28.6%. Still not run with the mock or a real LLM.

## Parking and fuel fixed by the authors

Dated 2026-10-03, after the "Fuel cost" entry, whose values this entry replaces (PAP 12, parking
NZ$11, fuel NZ$0.23/km, and the results of the canonical runs). The earlier state is kept in
`data/behaviour_calibration_fuel023_park11.json`, `data/calibration_fuel023_park11.json`,
`docs/calibration_report_fuel023_park11.md`, `docs/figures/fuel023_park11/` and
`runs_fuel023_park11/`.

1. **Two values are now fixed inputs decided by the first author from real-world knowledge, not
   calibrated.**
   - Paid parking: `persona.park_cost_paid = [17, 17, 17, 0, 12.75]`, NZ$17 a day for office
     archetypes, student 0.75 x, trades and company vehicles 0. Tag: [author decision; consistent
     with the AT 2014 Victoria St daily rate already noted in config comments].
   - Fuel: `costs.fuel_cost_per_km = 0.30` = petrol NZ$3.30/L x 9.0 L/100 km / 100 (0.297,
     rounded). The price is tagged [author-supplied, Oct 2026]: the author reports a sharp rise.
     We did not verify it. The last published figure we read was NZ$2.97/L for the first week of
     September 2026 (MBIE series via Figure.NZ, see Fuel cost 2). Consumption stays at 9.0 L/100 km.
   - Mean daily fuel cost of an agent who pays it: NZ$8.5, 8.7 and 8.8 on seeds 1-3 (mean 8.6;
     10th to 90th percentile about NZ$2.6 to NZ$13.5). Parking plus fuel is about NZ$26 a day for
     a paying driver, against about NZ$18 in the two earlier states.
2. **Parking is no longer a calibrated scalar.** `scripts/calibrate_behaviour.py` searches two
   scalars, PAP (`costs.pt_attitude_penalty`) and k_WFH (`costs.wfh_cost`), with parking held at
   `PARK_FIXED = 17`. Targets, seeds (1-3 search, 4-5 held out, 6-12 out of sample), loss and
   selection rule are unchanged. Parking stays in the scalar dict as a constant, so the loss prior
   and the anchor distance keep their form (its terms are the same at every point).
3. **Wider ranges, no edge.** A range-finding probe (PAP 12 to 40 in steps of 4 at k_WFH 8 and 12,
   seeds 1-3, logged as `search.range_probe`) was run first, then the grid was fixed: PAP 10 to 36
   and k_WFH 2 to 16, both in NZ$1 steps, 405 points x 3 seeds = 1,215 evaluations with nested
   capacity calibration (about 18 min on 13 cores). The earlier ranges were PAP 4-12 and k_WFH 2-8,
   and both earlier choices sat on an edge. Result: **PAP 20, k_WFH 10**, neither on an edge.
4. **Result against the targets** (R-daily, mean of seeds 1-3): base car 0.830, PT 0.147, WFH
   0.003, SKIP 0.020, days 11-13 -28.8%, days 21-30 -18.4%. Every 3-seed mean is inside its band.
   Per seed: base car 0.867 / 0.811 / 0.811, PT 0.121 / 0.159 / 0.163, SKIP 0.009 / 0.025 / 0.025,
   days 11-13 -28.3 / -31.0 / -27.3%, days 21-30 -18.3 / -20.5 / -16.4%.
5. **What is missed.** No grid point is feasible (0 of 405). The rule also requires every seed to
   be within the stated single-seed tolerance, and that tolerance is 0 for the SKIP share: seeds 2
   and 3 have 0.025 against 0.02, a miss of 0.005 (about 1.5 commuters a day). The chosen point is
   therefore the rule's fallback (lowest loss, 1.57). The targets were not relaxed. Held-out seed 4:
   SKIP 0.022, response -14.9%; seed 5: SKIP 0.017, -19.3%. Unseen seeds 6-12 (mean): base car
   0.810, PT 0.156 (0.16 at the stated precision, above 0.15), SKIP 0.026 (0.03, above 0.02),
   days 11-13 -25.4%, days 21-30 -16.0%; seed 6 responds by -9.3% (outside the band by 2.7 pp,
   within tolerance); SKIP is above 0.02 on seeds 6, 7, 9 and 11 (0.025 to 0.037).
6. **Why SKIP appears.** A day's driving now costs a paying commuter about NZ$26 in parking and
   fuel, close to the SKIP cost (NZ$25 plus one hour of VoT) [A]. For commuters with P = 1-2 the PT
   penalty is 1.5 to 2 x PAP 20, so SKIP is their next-best option. Under the charge the SKIP share
   rises from 0.020 to 0.047 (days 21-30), so part of the fall in car crossings is postponed trips.
7. **What would close the gap (logged, not adopted;** `gap_sensitivity` in the log, stage `gap`).
   With a local re-search (PAP 17-24, k_WFH 7-11) under one changed assumption: SKIP cost NZ$30
   gives 7 feasible points of 40 (rule's choice PAP 21 / k_WFH 8: base car 0.843, PT 0.145, SKIP
   0.003, -28.2%, -18.8%); SKIP cost NZ$35 gives 9; fuel at NZ$0.27/km (MBIE September 2026) gives
   1; fuel at NZ$0.23/km (2025, the base year of the PT fare and the charge) gives 7. The most
   plausible single assumption is therefore the cost of postponing, which was set when driving was
   cheaper; the base-year mismatch (2026 fuel, 2025 fare, charge and SKIP cost, 2014 parking) is
   the reason to revisit it. This is the authors' decision.
8. **PAP is a fitted residual.** With parking and fuel fixed it is the only scalar that can hold
   the assumed baseline split. PAP 20 equals v3 PAP 20-40 in v3's form; P = 1-2 commuters never
   ride PT. k_WFH 10 (v3: 8) is identified by the response and overshoot, not by the WFH share.
   The earlier caveat that parking is in effect a fitted value no longer applies.
9. **Clock arms.** A standing SKIP is never a plan (T6 wakes the agent every morning), so with
   more postponed trips the event-only clock now makes 150 to 270 decisions after day 12 outside
   the disruption days (seeds 1-3; one a day before). The lock-in gap is smaller: R-clock -24.2 /
   -26.9 / -22.4% against R-daily -18.3 / -20.5 / -16.4%. T7 numbers are in the entry above.
10. **Single-agent example.** With paid parking NZ$17 and the fuel cost of a 20 km path (NZ$12)
    nobody retimes on the charge morning: of 625 trait combinations 250 already ride PT, 146 keep
    the car, 93 switch to PT and 136 postpone. With free parking 497 keep the car, 120 switch to
    PT and 8 retime (H = 1).
11. **Script changes.** Two-scalar grid (`GRID`), `PARK_FIXED`, `on_grid_edge`, the range probe in
    the log, a `gap` stage, a "Parking and fuel fixed by the authors" section and a three-state
    comparison table in the report, a search figure over PAP x k_WFH, the SKIP share in the report
    tables, and the mean daily fuel cost per seed. The PAP edge check, the refinement grid and the
    parking-anchor sensitivity were removed. The selection history is carried forward from the
    archived log and the replaced selection appended.
12. **Capacity.** Recalibrated per seed: 0.4674, 0.4259, 0.4303 (before 0.5078, 0.4128, 0.4128).
13. **Tests.** `test_identical_a_different_b` now uses free parking with the fuel cost (pay / PT /
    retime still separates there). New `test_paid_parking_split_is_pay_pt_postpone` records the
    paid-parking split in item 10. `test_trait_effects_monotone_at_charge_wake` uses parking NZ$17
    and the fuel cost of a 10 km path and compares rounded shares (with PAP 20 the PT share
    saturates at 0 for low P). 233 tests pass (3 NetLogo tests run separately and pass).
14. **Canonical runs and documents.** All canonical mock runs, the NetLogo R-clock run (identical
    to PyEngine), the T7 sensitivity runs, the estimates, the figures and `docs/example_prompt.md`
    were regenerated; README, `../docs/technical_reference.md` and `../paper/architecture.md`
    carry the new numbers. Methods M2 now says that fuel and parking costs are fixed from observed
    prices and that the grid search sets two cost scalars.

## Early start and SKIP cost, 2026-10-05

Two decisions of the first author, made after the "Parking and fuel fixed by the authors" entry,
whose results this entry replaces. Reason: with parking NZ$17 and fuel about NZ$8.6 a day's driving
cost about NZ$26, close to the assumed cost of postponing (NZ$25 plus one hour of VoT), so 2 to 5%
of commuters postponed and almost nobody retimed, because leaving early carried a schedule-delay
penalty against a fixed start. The earlier state is kept in
`data/behaviour_calibration_skip25_noearly.json`, `data/calibration_skip25_noearly.json`,
`docs/calibration_report_skip25_noearly.md`, `docs/figures/skip25_noearly/` and
`runs_skip25_noearly/`.

1. **SKIP cost.** `costs.skip_cost = 30` (was 25) [A, author decision 2026-10-05; raised with the
   driving cost]. SKIP = NZ$30 + 1 h x VoT. Not calibrated.
   *Superseded 2026-10-09:* SKIP is removed ("SKIP removed, willingness to travel and the peak charge" 2).
2. **Starting work earlier is a real option** (departure from the specification and from v3, which
   have one start time per commuter). Many employers encourage a 07:00 to 15:00 day [A, author].
   Every assumption, with its value:
   - `costs.early_start_min = 420` (07:00) [A, author: employers encourage 07:00 to 15:00]. The
     prompt gives the day as 07:00 to 15:00, i.e. an 8-hour day [A]; the end time has no role in
     the model (AM peak only).
   - `persona.early_shift_prob = [0.8, 0.5, 0.0, 0.5, 0.0]` [A, author decision; no empirical
     source]: probability that the employer allows it, for hybrid office, on-site office,
     shift/service (fixed roster), trades/work vehicle, tertiary student (class times). It applies
     to on-site office workers although their usual start is `fixed_start` (the employer offers a
     second fixed start).
   - `costs.early_shift_cost = 3.0` NZ$ a day, multiplied by phi(F) (6.0 at F = 1 to 1.5 at F = 5)
     [A]: the inconvenience of working the early day, small relative to the charge (NZ$4 to 6).
   - `time.anchor_offsets_min = [0, 15]` [A]: departures added around each start (item 4).
   - The permission holds on any day the commuter chooses, with no notice and no weekly limit [A].
   - The early start is used only when it is earlier than the usual start t* (a commuter with
     t* = 07:00 has no early option) [A].
   None of these is searched or calibrated.
3. **Layer A constraint `early_shift_ok`.** Drawn on stream "A" after every other Layer A draw
   (one uniform per base agent), so no earlier persona field changes: personas are identical to
   the previous state apart from the new field (tested). Twins copy it. Seeds 1-3: 43.7%, 52.0%
   and 50.3% of commuters have the permission, and 41.0%, 50.3% and 49.7% have it with t* later
   than 07:00.
4. **Options.** For a commuter who may start early, every CAR and PT option is measured against the
   cheaper of two starts: schedule delay against t*, or schedule delay against 07:00 plus
   `early_shift_cost x phi(F)`; ties keep t*. The inconvenience cost is part of
   `gc_parts["schedule"]`, so `GC_PARTS` keeps its nine keys and MockLLM (schedule weight 1.25)
   picks the same start as the rule for a given option. `Option.start_used_min` and
   `Option.early_shift` record the start; `early_min` and `late_min` refer to it. PT: the service
   is the latest one arriving by the start used. Car departures: on top of the standing +/- 60 min
   set, the reference departure of each start (start - free-flow time - 10 min buffer, floored to
   the 15-min grid) +/- 15 min is offered, for 07:00 and for t*, so the early start is reachable
   from a usual-time plan and the usual start stays reachable from an early plan (in R-daily the
   set is centred on yesterday's departure). Option ids stay `CAR_hhmm`; the engines are unchanged.
   A commuter without the permission has exactly the options of the previous state.
   *Extended 2026-10-07:* the reference departure of each start also allows for the public road delay at that departure (day 1: usual traffic); see Road congestion 7.
5. **Outcome, memory and T3.** `outcomes.csv` and `decisions.csv` gain `start_used_min` and
   `early_shift`; early and late minutes of the outcome are measured against the start of the
   chosen option, so a commuter who planned the 07:00 start and is held up is late for 07:00 and
   can be woken by T3. The start is fixed at the decision from the expected arrival and is not
   re-chosen after the trip [A]. For an agent on a standing plan the start is read from that
   morning's option (the options are rebuilt every morning in every arm).
6. **Habit, PT disruption, WFH, SKIP.** Unchanged. An early-start departure is one more option id
   for the habit cost.
7. **Prompt** (information parity). The situation section states "Your employer lets you work
   07:00 to 15:00 instead of your usual hours on any day you choose." only for a commuter with
   the option. The options table and the memory table have a `start time` column for every
   commuter, and the closing line says that early or late is measured against it. No archetype
   label. The LLM is not told the NZ$3 x phi(F) cost (it reads the flexibility sentence), in the
   same way that it is not told k_WFH. The template id stays `cl-v1` (the live API has never been
   called). Every MockLLM prompt changed, hence all mock runs.
   *Superseded 2026-10-07:* the template id is now `cl-v2` (Road congestion 8).
8. **Recalibration.** Same targets, seeds (1-3 search, 4-5 held out, 6-12 out of sample), loss,
   selection rule, grid (PAP 10-36 x k_WFH 2-16, 405 points) and two scalars; parking and fuel
   fixed. Result: **PAP 20, k_WFH 10 again** (6 feasible points of 405; the feasible point nearest
   the anchors; neither on an edge). R-daily, mean of seeds 1-3: base car 0.843, PT 0.154, WFH
   0.001, SKIP 0.003, days 11-13 -25.2%, days 21-30 -16.0%. Per seed: base car 0.866 / 0.844 /
   0.819, PT 0.131 / 0.155 / 0.175, SKIP 0.001 / 0.001 / 0.006, days 11-13 -23.8 / -28.0 / -23.8%,
   days 21-30 -15.2 / -17.8 / -15.0%.
   *Superseded 2026-10-08/09:* items 8 to 15 are for 300 agents on free-flow roads (archived as `freeflow300`); the search was rerun at 950 agents with congested roads and chose PAP 22, k_WFH 9 (Motorway flow breakdown 16, 17). With PAP 22 / k_WFH 9 the single-agent counts of item 12 (`tests/test_rules.py`) are 315 keep, 54 switch to PT, 4 retime by 15 min (H = 1) and 2 postpone without the permission, and 298 keep, 53 switch to PT, 22 leave at 06:30 for the 07:00 start and 2 postpone with it (250 ride PT before the charge in both). The clock and T7 results at 950 agents are in the T7 entry above; the event-only clock makes 255, 233 and 212 decisions after day 12 outside the disruption days (seeds 1-3).
9. **What is and is not met.** Every 3-seed mean is in its band at the precision the targets are
   stated in, and every seed is within the single-seed tolerance, so the point is feasible under
   the unchanged rule. Not met exactly: the unrounded mean PT share is 0.1536 (0.0036 above 0.15;
   no grid point is feasible on unrounded means), base car on seed 1 is 0.866 (0.016 above the
   band, tolerance 0.05) and base PT on seeds 2 and 3 is 0.155 and 0.175 (0.005 and 0.025 above,
   tolerance 0.05). Held-out seeds 4 and 5: base PT 0.147 and 0.167, days 21-30 -15.4% and -18.1%.
   Unseen seeds 6-12 (mean): base car 0.840, PT 0.154, SKIP 0.004, days 11-13 -23.0%, days 21-30
   -15.0% (single seeds -12.0% to -18.3%); nothing outside the tolerance. The response is in the
   weaker half of the band (centre -20%). The lowest-loss point, PAP 21 / k_WFH 8 (-19.2%,
   overshoot -27.8%), is also feasible, but the rule ranks the distance to the anchors first. The
   targets were not relaxed.
10. **Early start, postponing and retiming** (R-daily, seeds 1-3; "no charge" is the run without
    the charge at the same capacity and seed).
    - Early start, share of all commuters: 6.1% on days 6-10 (7.1 / 6.4 / 4.9%), 6.4% on days
      11-13, 4.2% on days 21-30 (3.7 / 3.5 / 5.4%), against 6.1% without the charge. The charge
      does not raise it: the early start mainly avoids the queue (peak delay about 15 min before
      the charge, about 3 min after), and the remaining saving of about NZ$2 of charge is below
      the assumed NZ$3 x phi(F).
    - SKIP: 0.3% on days 6-10 and 1.0% on days 21-30 (before this change 2.0% and 4.7%).
    - Retiming: 32% of commuters have a different modal car departure on days 26-30 than on days
      6-10, against 37% without the charge (day-to-day churn of the daily arm). In the paired
      check 43.8% of those driving in both runs leave at a different time with the charge, 15.1%
      earlier and 28.7% later.
    - Peak spreading: car crossings 08:00-09:00 fall by 18.6% against 16.0% for the whole morning
      (per seed 13.7 / 16.8 / 25.4% against 15.2 / 17.8 / 15.0%); before 07:30 they fall by 11.2%.
      Over seeds 1-12 the figures are 23.9%, 15.6% and 2.2%.
11. **Sensitivity to the new assumptions** (chosen PAP and k_WFH, seeds 1-3, capacity
    recalibrated; logged as `gap_sensitivity`, never adopted). SKIP cost back at NZ$25: SKIP 0.022
    before and 0.047 after the charge, not feasible. No early start: SKIP 0.004 and 0.010, base
    PT 0.161, response -14.5%, peak crossings -14.4%. Early cost NZ$1.5 x phi(F): early start
    10.0% before and 11.5% after the charge, peak crossings -32.7%. Early cost NZ$6: 1.6% and
    0.6%. Permission for all of archetypes 1, 2 and 4: 8.4% and 6.5%. So the fall in postponing
    comes from the SKIP cost, and the use of the early start depends on its assumed cost.
12. **Single-agent example** (`tests/test_rules.py`, paid parking NZ$17, fuel NZ$12, t* 08:00). Of
    625 trait combinations 250 ride PT before the charge. Without the permission 276 keep the car,
    93 switch to PT, 4 retime by 15 min (H = 1) and 2 postpone (before: 146, 93, 0, 136). With the
    permission 260 keep, 93 switch to PT, 20 leave at 06:30 for the 07:00 start and 2 postpone.
13. **Script changes** (`scripts/calibrate_behaviour.py`). The `before` state sets the SKIP cost to
    25 and the permission probabilities to 0 explicitly. New metrics (`end_skip`, `base_early`,
    `end_early`, `peak_cross_change`, `pre0730_cross_change`), `early_start_summary`, a report
    section "Early start and SKIP cost", a four-state comparison table, and sensitivities to the
    fixed assumptions in place of the gap variants; the local re-search (`--stage gap`) is no
    longer part of the default run. The selection history is carried forward and the replaced
    selection appended (4 entries).
14. **Capacity.** Recalibrated per seed: 0.4215, 0.3961, 0.3961 (before 0.4674, 0.4259, 0.4303).
15. **Clock arms and T7.** Car crossings days 21-30 vs 6-10, seeds 1 / 2 / 3: daily -15.2 / -17.8 /
    -15.0%; event-only clock -19.5 / -22.5 / -20.8% (835 / 944 / 954 decisions); review every 10
    days -14.1 / -18.8 / -18.9% (1,112 / 1,204 / 1,224); every 5 days -13.7 / -19.0 / -17.7%
    (2,004 / 2,098 / 2,138). Days 11-13: daily -23.8 / -28.0 / -23.8%; event-only -21.2 / -27.0 /
    -22.1%; review 10 the same as event-only; review 5 -19.4 / -27.0 / -21.6%. With few postponed
    trips the event-only clock makes 12, 49 and 123 decisions after day 12 outside the disruption
    days (150 to 270 before).
16. **Tests.** New: early-start departures and the effective start, an early-start commuter who
    prefers an early departure to SKIP under the charge in a constructed case while the same
    commuter without the permission postpones, outcome rows, memory and T3 on the effective start,
    PT for the cheaper start, the permission drawn last (no other persona field changes, twins,
    shares), the prompt sentence only when allowed and the `start time` columns, early-start days
    in `summary.json` and byte-identical reruns. `test_paid_parking_split_is_pay_pt_postpone` became
    `test_paid_parking_split_and_early_start` (item 12). 241 tests pass (3 NetLogo tests run
    separately and pass).
17. **Canonical runs and documents.** All canonical mock runs, the NetLogo R-clock run (identical
    to PyEngine: 9,000 outcome rows, 6,866 car rows), the T7 sensitivity runs, the estimates, the
    figures and `docs/example_prompt.md` (now a commuter with the permission) were regenerated;
    README, `INTERFACES.md`, `../docs/technical_reference.md` and `../paper/architecture.md` carry
    the new model and numbers. Fig. 3 of the paper lists the early start among the constraints.
    *Superseded 2026-10-07/08:* these runs are for 300 agents on free-flow roads; the canonical runs, the T7 sensitivity runs, the estimates, the figures and `docs/example_prompt.md` (agent 0, still a commuter with the permission) were regenerated on 2026-10-09 at 950 agents with congested roads, PAP 22 and k_WFH 9 (Motorway flow breakdown 17). The NetLogo R-clock run equals PyEngine's (28,500 outcome rows, 20,220 car rows; 46 of 48 files byte-identical; `summary.json` and `config_snapshot.toml` differ only in the engine label), and `python -m cordonlite.analysis --compare` reports identical = true. It was started with `CORDONLITE_NETLOGO_HOME`, which the run does not record (Engine item 7).

## NetLogo network model, 2026-10-06

Additions beyond the specification at the authors' request: convert the TomTom GeoPackage to a
shapefile and load it as the road network of a NetLogo model in which commuters at their origins
across Auckland drive to the city centre, each to a building inside the cordon drawn at random and
kept for every day. Nothing below changes a run, an engine or `config.toml`.

1. **Conversion.** `prep/build_netlogo_layers.py` writes the shapefile beside the GeoPackage
   (`../netlogo/Data/roads/tomtom_major_roads.shp`): all 46,965 segments, same order and geometry,
   all five attributes. `newSegmentId` becomes `segment_id` because a shapefile field name has at
   most 10 characters (the gates already call it `segment_id`). Text fields are shrunk to their
   longest value (`RESIZE=YES`). The building paths are a module default and a CLI flag, not
   config keys, because no run reads them [A].
2. **New model, not a change to the engine model.** `cordon_lite.nlogox` stays the headless
   engine and its schematic replay; the network model is a separate file that reuses its point
   queue code, so the minutes of every car equal the run's (checked by
   `scripts/check_network_model.py`).
3. **Timing follows the engine, the network gives the place** [A]. A car covers its network route
   to the gate in exactly its engine minutes (departure to gate arrival, free-flow minutes rounded
   as in `agents.csv`) and its route from the gate to its building in the engine's gate-to-
   destination minutes. The building therefore changes where a car parks, not when it arrives; a
   building-specific last leg would change `arrive_min` and every early/late outcome, which only
   the Python model may decide. The cost is the implied speed: in the seed-1 R-clock run a median
   of 76 km/h to the gate (5-95%: 50-94) and 40 km/h from the gate to the parking node (5-95%: 13-72,
   up to about 95 km/h on a few long legs with a short engine leg; seed 2 gives the same picture).
   *Superseded 2026-10-07:* with congested roads a car follows its own section times from the engine's road model, stretched slightly so that it reaches the gate at the engine's whole gate-arrival minute (Road congestion 11); the implied speeds above are those of free-flow roads. In the canonical R-clock run of 2026-10-09 (950 agents, days 6 and 25) the median is 42 km/h to the gate (5-95%: 23-72) and 43 km/h from the gate to the parking node (5-95%: 14-77, at most about 96 km/h).
4. **Routes.** Home -> outside end of the prep gate segment -> gate point (the shortest free-flow
   path, a prefix of the prep path to the destination node), then gate point -> inside end ->
   building node -> the building point [A]. Origins whose path touches the cordon more than once
   (README, "Simplified network") cross at their first-entry gate. The leg after the gate is
   routed with 60 minutes added to every road with an end outside the cordon [A], because on the
   plain shortest path about two thirds of these legs left the cordon and re-entered it (a second
   crossing without a queue or a charge). On roads it still leaves where the cordon's own roads
   do not connect (they fall into 15 pieces; buildings attach to the largest, 1,066 of 1,106
   nodes): from the Wellesley Street ramp gate for about 100 to 160 m and from Hopetoun Street for
   about 180 m (90 of the 300 seed-1 legs; with 950 agents 269 of 950 legs leave the cordon, by at
   most 178 m, `check_network_model.py` on the canonical R-clock run). The car parks at the cordon
   node nearest its building (in the largest connected set of cordon roads; median 65 m from the
   building, up to about 780 m for buildings on the wharves, which the major-road network does not
   reach) and the commuter is drawn at the building on arrival [A]: an earlier version drove the last stretch in
   a straight line, across the water in front of the wharves. The network keeps the giant
   component only (28,507 nodes), the graph prep routes on.
5. **Workplaces.** Uniform over the 1,484 building points (LINZ outlines clipped to the SA3; one
   `point_on_surface` per footprint), not weighted by floor area or use, with replacement, fixed
   seed 2027 [A, author: "randomly one of the buildings", the same building every day].
6. **Drawing.** Queued cars are red and stand on the approach road about 220 m apart: one agent
   stands for agents_represented / agents (about 63) cars, at 7 m per car in 2 lanes [A], so the
   queue on the map is as long as the real one (a first version drew them 15 m apart, which hid the
   queues). PT riders are hidden while travelling. WFH and SKIP stay at home.
   *Superseded 2026-10-08:* at 950 agents one agent stands for 20 cars, so queued cars stand about 70 m apart (Motorway flow breakdown 12).
7. **Day length and animation** [author decisions 2026-10-06]. A day plays until every commuter has
   arrived (2 minutes after the last arrival; `sim-end-cap-min` if a car is never served), then the
   next day can start. A version that stopped each day at 09:00 was dropped the same day. One tick
   is 15 simulated seconds at up to 30 frames per second; one tick per minute was too jerky. The
   Python engine keeps departures until 09:45 (`time.depart_latest_min`).
8. **One NetLogo model** [author decision 2026-10-06]. The NetLogoEngine model and the network
   model were two files in one folder, which was confusing. They are now one file,
   `netlogo7/cordon_lite.nlogox`: the headless procedures (`setup-from-dir`, `set-clock`,
   `run-day`) and the GUI share one engine procedure, `point-queues`, so the two cannot drift
   apart. The schematic replay GUI (`run-day-gui`, outputs in `gui_replay/`) is gone, and runs no
   longer create `gui_replay/`. `cordon_lite/netlogo` was renamed `cordon_lite/netlogo7`.
9. **Road shapefile inside the model folder.** The top-level `netlogo/` folder (the SSC2026 model and
   its data) was removed from the repository on 2026-10-06 (commit dc40f08). The roads shapefile the
   GUI loads was restored from git history, unchanged, to `netlogo7/gis/tomtom_major_roads.shp`,
   which is now the default output of `prep.build_netlogo_layers`. The prep inputs in
   `config.toml` (`[prep] roads_gpkg`, `cordon_gpkg`) and the building outlines still point into the
   removed folder: re-running prep needs them restored; runs and the GUI do not.

## Road congestion (2026-10-07)

Added at the authors' request: from about 07:30 the roads into Auckland's city centre are heavily
congested, so a commuter's time from home to the cordon gate now depends on when it leaves and on
the traffic on its route, in both engines. Before this change the roads were free flow and the gate
queue was the only congestion (the specification); `road.enabled = false` still gives that model.
Code: `cordonlite/roads.py` (engine rule, what agents are told, outputs), `prep/build_roads.py`
(inputs `data/road_*.csv`, report `data/road_report.md`), the `[road]` section and the `[prep]
road_*` keys of `config.toml`, and the port in `netlogo7/cordon_lite.nlogox`. Values quoted are those
of the current `data/road_meta.json`, which also holds the 2026-10-08 changes of the next entry. The
300-agent free-flow state is kept in `data/calibration_freeflow300.json`,
`data/behaviour_calibration_freeflow300.json`, `docs/calibration_report_freeflow300.md` and
`docs/figures/freeflow300/`; its canonical runs were overwritten when `runs/` was regenerated on
2026-10-09 and are kept only in git history (commit 55a1dbb).

1. **Decisions** [author decisions 2026-10-07].
   - Roads are congested in both engines (PyEngine and NetLogoEngine), which stay output-identical.
   - Congestion = background traffic (the counts minus the commuters) + the commuter agents' own
     cars, so a charge that removes commuter cars eases the roads they used.
   - Agents see the road delay and react to it (prompt `cl-v2` for the LLM).
   - The level is anchored to the TomTom Traffic Index, Auckland 2025.
2. **Road sections** [SPEC 2026-10-07]. `python -m prep.build_roads` rebuilds the prep shortest paths
   in memory and stops unless they reproduce `data/origins.csv` exactly (gate, corridor and free-flow
   minutes of every origin). The pre-gate part of each of the 3,000 origin paths (origin to the
   inside end of the gate segment) is cut into sections, maximal chains of edges used by the same set
   of origins with the same frc, speed limit, normalised street name and count values: 5,903
   sections, 849.4 km, 47.5 per origin (at most 124); their free-flow minutes add up to each origin's
   `fftt_to_gate_min` (within 3e-14). The gate-to-destination leg is not sectioned and stays free
   flow. Routes stay the undirected shortest free-flow paths, with no rerouting.
3. **Traffic counts** [DATA, A]. Auckland Transport average daily traffic counts, which include NZTA
   state-highway records, from the copy in the SSC2026 repository
   (`../../SSC2026/netlogo/Data/Average_Daily_Traffic_Counts.geojson`; 13,835 points, 13,717 with
   ADT > 0; 7-day averages of mixed vintage).
   - Matching [A]: the nearest graph edge with the same normalised street name within 30 m
     (`prep.adt_match_m`); state-highway records by route to the motorway names (01N Northern and
     Southern, 016 Northwestern, 018 Upper Harbour, 020 Southwestern, 20A George Bolt Memorial
     Drive); several counts on one edge keep the most recent. A count holds along the same street for
     up to 1 km through the network (`prep.adt_propagate_m`; motorway, frc 1 and ramp edges need the
     identical TomTom name, carriageway counts stay within 60 degrees of their bearing); other edges
     take the median two-way ADT of count edges of the same frc and speed band.
   - Not used [A]: 11 state-highway records without a direction, 8 bus-only ramp records, and 66 AT
     counts below 0.25 of a more recent count of the same street within 1 km (stale or misplaced).
     3,179 counts are used. Origin-weighted pre-gate minutes by source: count 25.6%, propagated
     15.1%, default 3.7%, NZTA motorway sites 55.6% (next entry).
   - Direction [SPEC 2026-10-07, A]: a count of one carriageway or direction (state-highway `-I`/`-D`
     records, state-highway ramps, AT counts whose name carries a direction) is directional (`adt_dir
     = adt`, two-way equivalent `2 x adt`); any other AT count is a two-way total (`adt_dir = adt /
     2`). The design also made an AT count on an edge without a reversed TomTom twin directional; that
     was dropped, because such edges are mostly carriageways of divided arterials whose AT count is a
     two-way total.
   - AM peak ratio: `peaktraffic / adt` of the count where its peak hour starts 06:00-09:45, else
     0.096 (`prep.road_peak_ratio_default` [DATA]), clipped to [0.05, 0.20]. It comes from a count on
     1,446 sections, 8.5% of origin-weighted pre-gate minutes.
4. **Observed flow, background and commuter weight** [A]. Per section: `obs_peak_vph = 0.6 x
   peak_ratio x adt_twoway` (inbound AM peak-hour flow; `prep.road_inbound_share` 0.6, no data behind
   it); time profile `r(m)` = the 15-min ratios of `prep.road_profile` from 06:00 (peak timing from the
   counts' peak hour [DATA], shape [A]), linear between bin centres, falling to 0.15 x the first value
   at 05:00. The commuters are netted out of the counts: `expected = 19,000 x 0.8 x (origin weight
   using the section) / (all origin weight)` (`prep.road_commuter_car_share` 0.8), `am_volume` = the
   observed flow summed over 06:00-10:00, `phi = min(1, expected / am_volume)`, background
   `bg_peak_vph = obs_peak_vph x (1 - phi)`, commuter weight `w_factor = min(1, am_volume /
   expected)`. The weight is below 1 on 4 sections near the gates, where all-or-nothing routing puts
   more commuter cars than counted (Alten Road keeps 0.422 of each car). Origin-weighted mean phi over
   pre-gate minutes: 0.158.
5. **Capacity and k** [SSC, DATA]. `cap_vph = k x adt_dir`, SSC2026's rule capacity = k x ADT (with a
   floor by road class since 2026-10-08, Motorway flow breakdown 11). k is bisected in [0.02, 0.3] so
   that the origin-weighted travel time index (time to the gate over free-flow time to the gate, of a
   probe car that adds no load, under usual traffic `v = obs_peak_vph x r(m)`) of departures
   08:00-08:59 is 1.714 (`prep.road_tti_target`): TomTom Traffic Index, Auckland 2025, morning rush
   hour congestion level 71.4%, average speed 25.4 km/h
   (https://www.tomtom.com/traffic-index/auckland-traffic/). Since 2026-10-08 the index is matched on
   the non-motorway part of the trips (Motorway flow breakdown 10). k = 0.076999 now; it moved between
   about 0.0769 and 0.0777 as the later prep rules were added. Usual-traffic TTI by departure hour
   06 / 07 / 08 / 09: all roads 1.239 / 1.747 / 1.927 / 1.529, non-motorway part 1.042 / 1.410 /
   1.714 / 1.205.
6. **Engine rule, identical in both engines** [SPEC 2026-10-07; values A]. For a section at whole
   minute m: `v = bg_peak_vph x r(m) + c x fpe`, with c = commuter cars that entered it at minutes
   m-15 .. m-1 (`road.flow_window_min` 15) and `fpe = vehicles_per_agent x w_factor x 60 / 15` (veh/h
   per entry); `f = 1 / (1 + 0.15 (V/C)^4)` with `V/C = v / cap_vph`, at least 0.18 (`road.bpr_alpha`
   0.15, `bpr_beta` 4 and `speed_floor` 0.18, as SSC2026; the motorway rule of 2026-10-08 is in the
   next entry). A car enters each section of its route at its current whole minute, takes that
   minute's f and spends `ff_min / f` there. Entries of minute m count from minute m + 1, so the order
   of cars within a minute does not matter (they are still processed in agent_id order).
   `road_delay_min = floor(extra + 0.5)`, extra = elapsed minus free-flow minutes; gate arrival =
   depart + `fftt_to_gate_min` + `road_delay_min`. The point queue and the free-flow post-gate leg are
   unchanged. Both engines use only + - * / and floor in one fixed order (no pow, no NetLogo
   `round`), so they produce the same doubles. `vehicles_per_agent = agents_represented / n_agents`
   is written into the run's `road_params.csv` and read by both engines (the NetLogo GUI does not
   recompute it). The four scenario files (`road_sections.csv`, `agent_routes.csv`,
   `road_profile.csv`, `road_params.csv`) are written into the run folder only with `road.enabled`;
   without them both engines use free flow. Plan validation still rejects a free-flow gate arrival
   before `sim_start_min`, which also covers the congested one (road delay is never negative).
7. **What agents know and do** [SPEC 2026-10-07, A]. `TodayInfo.public_road` gives each agent, for
   each departure, the road delay a probe car (adding no load) would have had on its route: on day 1
   under usual traffic (what the counts say; commuters know their usual traffic), from day 2 under
   yesterday's actual traffic. For a car option leaving at d: R = that delay, gate arrival `g = d +
   fftt_to_gate + floor(R + 0.5)`, then the queue expectation at g as before, time cost `a x
   (fftt_total + R + D)`, new `Option.expected_road_delay_min`. The personal delay-ratio EMA stays
   queue-only, because the road delay is already route-specific [A]. The day-1 reference departure is
   the latest grid departure with `d + fftt_total + floor(R + 0.5) + 10 <= start`
   (`time.initial_buffer_min`), so day-1 drivers are not systematically late. `MemoryRecord` gains
   `road_delay_min` and `expected_road_delay_min`; T3 and T5 see road delay through arrival and
   expected travel time, with no trigger code change. PT time is fixed (rail and busway assumption)
   and WFH keeps `a x fftt_total` [A], so WFH now also avoids the road delay.
8. **Prompt `cl-v2`.** `llm.template_id` is now `cl-v2`; with `road.enabled = false` the text equals
   `cl-v1`. Situation: "With no traffic the drive takes about N min: A min to reach the city-centre
   boundary and B min from there. In the morning, traffic on the way and a queue at your entry point
   can make it longer." TODAY on day 1: "Usual traffic on your route, by time of leaving home: ..."
   before the existing no-queue-information line; from day 2: "Yesterday's traffic on your route and
   queue at your entry point, by time of leaving home: leaving 07:30: 6 min traffic + 2 min queue,
   ...". The options and memory tables gain a "traffic delay" column before the queue column. The
   live API has never been called, so no stored answer uses the old wording. `TEMPLATE_ID` is one
   constant, so `load_config` rejects the config snapshot of a `cl-v1` run folder.
9. **Outputs.** `outcomes.csv` gains `road_delay_min` after `depart_min` (0 on free-flow roads, empty
   on non-car rows). New run output `road_entries.csv` (`day, section_id, minute, entries`, non-zero
   rows; header only with roads off); NetLogoEngine's exchange file `road_dayNN.csv` is deleted after
   the run, so both engines leave the same files. `summary.json` per day gains `mean_road_delay` and
   `max_road_delay` (all car agents) and `mean_car_travel_min` (served cars), and `meta.road` the road
   settings (enabled, alpha, beta, floor, window, k). Calibration records carry the same block, and a
   run warns (MISMATCH) when its road settings differ from the calibration's. Analysis:
   `summary_table` columns `mean_road_delay_dX_Y` and `car_door_to_door_dX_Y`, figure
   `road_delay.png`. `analysis.compare_runs` now needs `road_entries.csv`, so it cannot compare run
   folders made before 2026-10-07.
10. **Capacity calibration on total delay** [A, author decision 2026-10-07]. New key
    `engine.calib_delay`: `"total"` (default) bisects `capacity_scale` so that the car-weighted peak
    15-min mean of gate queue plus road delay (R-daily, no charge, days 6-10) is 15 min
    (`calib_target_peak_delay_min`); `"queue"` is the old metric (the same thing with roads off). With
    congested roads the 15 min that the gate queue used to stand for alone is shared with the roads.
    The authors re-confirmed the target after the motorway change (Motorway flow breakdown 16).
11. **NetLogo GUI.** The engine part (`road-arrivals`, shared by the headless `run-day` and the GUI)
    ports `simulate_roads` line by line. Cars drive their own section times, stretched slightly so
    that they reach the gate at the engine's whole gate-arrival minute. The design coloured roads by
    V/C Level of Service; with k calibrated to TomTom the peak V/C is about 1.4-1.5 on almost every
    section, so nearly every route section was F from 07:15 to 09:15 and a charged day looked like an
    uncharged one. Roads are therefore coloured by speed factor [A]: f >= 0.80 grey (normal), 0.60-0.80
    light yellow (slow), 0.40-0.60 orange (heavy), below 0.40 purple (jammed); since 2026-10-08 a
    broken-down motorway is purple at any speed. No red (queued cars), no green (PT) and none of the
    corridor car colours. Grades are recomputed every 5 simulated minutes and at most 60 changed
    sections are redrawn per tick. New monitor "traffic delay (min)": mean road delay of today's cars
    that have reached their gate.
12. **Verification.** PyEngine and NetLogoEngine give byte-identical run folders apart from the engine
    label (`analysis.compare_runs` and a byte comparison of every file; 30-day R-clock at 300 agents
    with roads on, and again at 950 agents after each change of the next entry).
    `scripts/check_netlogo_equivalence.py` has road variants (synthetic sections with speed-floor
    hits, gate ties and agents without a route; real data) and compares the road entries;
    `scripts/check_network_model.py` checks that the GUI's section times equal a probe on
    `roads.speed_table` (difference 0.0), that drawn cars are within 1 m of their computed positions,
    also at off-grid clocks, and the road grades. With `road.enabled = false` a run reproduces the
    free-flow canonical run (decisions, profile and plans byte-identical; outcomes apart from the new
    column; summary days apart from the new keys). Independent code that rebuilds every car's traversal
    from `road_entries.csv` reproduces every `road_delay_min`. Prep reruns are byte-identical. Roads
    add about 30% to the run time at 300 agents.
13. **Limitations.**
    - Routing is undirected and fixed (shortest free-flow path, no rerouting): 43% of motorway
      traversals follow the opposite carriageway's geometry. Congestion uses the inbound flow at the
      location, so the values do not depend on which carriageway is drawn; a directed rebuild would
      change gates and corridors.
    - Capacity = k x ADT is SSC2026's rule and circular: k is fitted so that the BPR curve gives
      TomTom's index, so capacity is an effective curve parameter, not a physical capacity, and usual
      V/C is `2 x 0.6 x peak_ratio x r(m) / k` (1.50 r(m) at the default peak ratio) on every
      count-based section. Spatial variation comes only from the count-based peak ratios (8.5% of
      minutes), the commuters' own cars, the capacity floor and, since 2026-10-08, the NZTA motorway
      sites.
    - TomTom's 1.714 is a city-wide index over all roads in the morning rush hour, not an index of
      inbound routes to the city centre; since 2026-10-08 it sets only the non-motorway level.
    - The 15-min time profile shape is assumed (peak timing from the counts). The counts are 7-day ADT
      of mixed vintage: state-highway records are mostly a 2016 bulk load (before the Waterview
      tunnel opened in 2017), local counts have a median year of 2022, and some 2020-21 counts may be
      lowered by lockdowns.
    - Simulated uncharged days are slower than usual traffic: the commuters are more bunched in time
      and on the gate approaches and ramps than the netting assumes, and their car share is above the
      0.8 used for netting. Test runs of 2026-10-07/08 gave 1.89 to 1.99 for 08:xx departures on days
      6-10 (the non-motorway part; the whole trip before the motorway rule) against 1.714 under usual
      traffic. In the canonical R-clock runs of 2026-10-09 the non-motorway part is 1.988 on seed 1
      (2.104 and 2.123 on seeds 2 and 3) and the motorway part 2.186 (2.032 under usual traffic): time
      over free-flow time of the cars leaving 08:00-08:59 on days 6-10.
    - The post-gate leg and PT are not congested.
    - Day 1: drivers know usual traffic but not the queue, and the actual road delay exceeds the
      usual-traffic forecast, so many arrive late (canonical R-clock runs: 28.9% of all commuters and
      33.6% of car commuters on seed 1, 34.0% and 32.8% of all commuters on seeds 2 and 3; day 1 is
      the same in R-daily); in the 300-agent test runs about half of the day-1 lateness was chosen
      (the option was already late in the agent's own estimate), which was not recounted at 950.
    - `w_factor` below 1 on 4 sections is a patch for all-or-nothing routing.

## Motorway flow breakdown, NZTA counts, 950 agents and Level of Service outputs (2026-10-08/09)

Changes of 2026-10-08 and 2026-10-09 at the authors' request, on top of the previous entry. In the
2026-10-07 model every section had the same usual V/C (about 1.50 r(m)), so motorways were no worse
than arterials, the commuters were only 4-8% of motorway V/C, and the congestion that differed between
roads sat on the arterials and ramps near the gates (300 agents, days 6-10: motorway TTI 1.45, arterial
1.73). The evidence points the other way [L]: Auckland motorways run over capacity for 6-7 hours a
day (NZTA and Auckland Council, Auckland Motorway Strategic Plan, 2026; read from search snippets
only); bottleneck speeds were 25-35 km/h in 15-min intervals before ramp metering (SH20, Brown, Clark,
Evans and Wee 2005); discharge after breakdown is about 10% below the pre-queue flow (Cassidy and
Bertini 1999, Transportation Research B 33(1); 3-18% in the literature); and stop-and-go waves form
even without a bottleneck (Sugiyama et al. 2008, New Journal of Physics 10, 033001).

1. **Decisions** [author decisions 2026-10-08/09].
   - Motorways get realistic morning congestion, including stop-and-go flow, without making the model
     slower.
   - Motorway inputs come from NZTA Traffic Monitoring System counts: 2024 quarter-hourly profiles
     scaled to 2025-26 daily volumes.
   - 950 agents, 5% of the 19,000 AM charged vehicles (was 300).
   - The capacity calibration keeps its 15-min target on total delay (gate queue + road delay),
     re-confirmed after the motorway change.
   - V/C-based LoS outputs as in SSC2026, with a speed-based LoS added next to them.
   - The throughput limitation of the counts is stated as a limitation (item 21).
2. **Nothing to import from SSC2026.** SSC2026 never slowed motorway traffic: its signal rule halved
   arterial capacity only, and the median peak speed factor of its motorway links was 0.999 (3.4% of
   links below 0.8, no-charge run). Its high motorway LoS E/F shares (87.8% of motorway traffic at
   07:00-09:00) were a measurement on ADT x 0.10 that never changed speeds or routes, and it had no
   breakdown, hysteresis or spillback. Motorway congestion therefore comes from new data and a new
   rule (items 3-9).
3. **Motorway mainline** (`mwy = 1`, new column of `road_sections.csv`) [A]: frc 0 or a street name
   holding "Motorway", not a ramp by name (Entry, Exit, Entry And Exit, Ramp, On-Ramp, Off-Ramp) and
   signed at least 70 km/h. The 70 km/h test is an addition to the design: without it Stanley Street
   (50 km/h, signalised, 832 origins) and the 60 km/h part of George Bolt Memorial Drive would count
   as motorway. The name test adds the Harbour Bridge stretch, which TomTom classes frc 1-2 (6
   sections). 285 sections, 147.1 km, 91.7 free-flow minutes, 56.2% of origin-weighted pre-gate
   minutes. One section (1024, Airport Motorway) also holds a ramp edge that prep joined to it.
4. **Flow breakdown rule**, identical in both engines and in what agents are told (`speed_table`,
   `route_delays`) [A, L]. A motorway section is broken down at minute m inside its usual-traffic
   window `[bd_on, bd_off)` or when today's `V/C >= road.mwy_breakdown_vc` (1.0, HCM LoS F). Broken
   down: `f = min(mwy_jam_speed, 1 / (1 + 0.15 (V/C / (1 - cap_drop))^4))`; otherwise the plain BPR
   curve; f at least 0.18 in both cases. `1 - cap_drop` is computed once per section in both engines.
   - `road.mwy_capacity_drop` 0.10 for sections without a measured drop [L] (Cassidy and Bertini
     1999; 3-18% in the literature); `road.mwy_jam_speed` 0.45 [A] (45 km/h on a 100 km/h motorway;
     25-35 km/h at the SH20 bottleneck in Brown et al. 2005); `road.mwy_recover_vc` 0.95 [A]: the
     usual-traffic window runs from the first minute with V/C >= 1 to the first later minute with
     V/C < 0.95 (hysteresis), where no NZTA site gives it (items 6-9).
   - The static window gives a jam its persistence; the dynamic trigger lets today's extra commuters
     start a breakdown early. The trigger has no hysteresis: a per-section state stepped every minute
     would have cost about +75% on `simulate_roads` and more in NetLogo.
   - `road.mwy_breakdown = false` gives byte-identical 2026-10-07 outputs. `road_sections.csv` gains
     `mwy, bd_on, bd_off` (and `profile_id, cap_drop`, item 6), `road_params.csv` the `mwy_*` keys,
     and `meta.road` and calibration records the `mwy_*` settings when the rule is on.
5. **NZTA motorway counts** [DATA]. `prep/fetch_nzta.py` wrote `data/nzta/` (see its README) on
   2026-10-08: 36 Traffic Monitoring System sites on the city-centre approaches (SH1 southbound from the
   North Shore including the Harbour Bridge, SH1 northbound from the south, SH16 eastbound, SH20
   northbound, the Waterview links and the CBD exit ramps); weekday daily counts 2025-10-01 to
   2026-09-30; quarter-hourly counts 05:00-11:00 on the weekdays of May, August and November 2024.
   Attribution, as the licence asks: "Traffic counts sourced from the New Zealand Transport Agency
   (NZTA Waka Kotahi) Traffic Monitoring System via the NZTA Open Data portal, licensed for re-use
   under CC BY 4.0." The same line is in `data/road_report.md`, `data/road_meta.json` and the NetLogo
   Info tab. Prep reads only these files (no network). A 2024 weekday is valid with no lane outage,
   every quarter hour present, the site-month's level within 0.67-1.5 x the 2025-26 median and no
   holiday [A] (this drops the doubled counts of 01N19424 in May 2024 and of 01N10420 in May and August
   2024). A site is used when it counts CBD-bound through lanes on at least 20 valid days: 19 of 36
   (not the mixed site 01N20429, 01N10420 with 19 valid days, 01620013 without 2024 quarter-hourly
   data, the two Waterview links or the 12 exit ramps).
6. **Capacity, profile and breakdown window per site** [A]. From the mean weekday 15-min flow q(t)
   (veh/h, all lanes and classes): `q_max` at `t_max`; plateau = median of q from t_max + 30 min to
   09:30; `delta = 1 - plateau / q_max`.
   - Breakdown when delta >= 0.05 (onset: the first quarter hour after t_max with `q <= q_max (1 -
     delta / 2)`; `cap_drop = delta`) or when saturated, `q >= 0.95 q_max` for at least 60 min (onset:
     the start of that run; `cap_drop = max(delta, 0.10)`, as the drop cannot be measured at the
     bottleneck itself).
   - Recovery: from 09:30, the first quarter hour from which q stays for two quarter hours below `0.95
     x plateau` (demand fell) or above `plateau + 0.5 (q_max - plateau)` (the downstream bottleneck
     cleared and throughput rose back; this rise test was added later on 2026-10-08); 11:00 when
     neither happens by 10:45.
   - Capacity `C = q_max x scale` and flow `q x scale`, scale = 2025-26 median weekday / 2024 median
     valid day of the same site (0.905 to 1.019). `obs_peak_vph` = the peak-hour mean of the scaled
     flow; the site's own time profile = scaled q / obs_peak_vph (`profile_id`; `road_profile.csv` is
     now long format, profile 0 = the default profile).
   - Two amendments to the design rule, kept behind constants in `prep/build_roads.py` (both windows
     are listed in `data/road_report.md`): a drop or saturated run counts only when it starts by 07:00
     (`NZTA_ONSET_LATEST_MIN`; after a later maximum, as on SH20 and at the SH16 city end at
     07:45-08:00, the counts cannot tell a capacity drop from the end of the demand peak, and the
     literal rule flagged every SH20 site), and recovery is looked for only from 09:30
     (`NZTA_RECOVERY_FROM_MIN`; dips inside the plateau are still congested flow). Sites without
     breakdown get cap_drop 0.10, not their delta, which there measures the end of the demand peak.
7. **Windows by site** (usual traffic, `data/road_report.md`): Harbour Bridge (01N19424) and its
   city end, Shelly Beach Road to Fanshawe Street (01N10425), both saturated, 06:15-09:30; SH1 north
   at Tristram Avenue (01N10417) 06:45-09:30 (ended by the rise test) and at Northcote (01N10419)
   06:45-11:00; SH1 south at Newmarket (01N20431) 06:45-11:00, Greenlane (01N20433) 07:00-11:00,
   Mt Wellington (01N20439) 07:15-11:00 and Panama Road (01N20440) 07:15-09:45; SH16 06:30-09:30
   (01620006), 06:45-09:45 (01620008) and 07:15-09:45 (01620009, 01620011). The SH16 city end
   (01620002) and the SH20 sites peak at 07:45-08:00 and have no window. Measured capacity drops:
   0.058 to 0.264. Share of motorway minutes broken down under usual traffic (network /
   origin-weighted): 07:00 36% / 59%, 07:30 to 09:00 81% / 94%, 09:30 60% / 73%, 10:00 31% / 48%.
8. **Mapping to sections** [A]. Every motorway section of a corridor with valid sites takes the nearest
   valid site of the same corridor, at any distance (Northern to SH1 north, Southern to SH1 south,
   Northwestern to SH16, Southwestern and "20", the Waterview SH20-SH16 link, to SH20), with its
   capacity, flow, time profile, window and cap_drop (`adt_source = "nzta"`; phi, background and
   w_factor recomputed from the site's profile): 232 of 285 sections, 98.9% of origin-weighted motorway
   minutes. Distance to the site: median 1.5 km, at most 12.6 km, 40 sections beyond 6 km (3.7% of the
   mapped minutes). The design's 6 km limit was dropped on 2026-10-08, because it left the south ends
   of the Southern and Southwestern Motorways on the default rule between mapped stretches.
   Usual-traffic motorway TTI, 08:00-08:59 departures: SH1 north 2.222, SH1 south 2.222, SH16 1.490,
   SH20 1.117.
9. **Motorways without a count site** [A]: the Upper Harbour Motorway (46 sections), George Bolt
   Memorial Drive (5) and the Airport Motorway (2) keep k x max(ADT, floor), the default peak ratio and
   profile, the global drop 0.10 and a window from usual traffic: 47 sections break down together
   07:08-10:01, and 6 Upper Harbour sections whose capacity the floor raised (item 11) have shorter
   windows (07:16-09:40, 07:23-09:22, 07:26-09:19). Their usual motorway TTI at 08:00-08:59 is 2.252.
10. **k matched on the non-motorway part** (`prep.road_tti_exclude_mwy = true` [A]). The TomTom index
    (1.714 for 08:00-08:59 departures) is matched on the time on non-motorway sections over their
    free-flow time, so it sets the arterial level and the motorway level follows from the NZTA timing
    and the breakdown rule. Whole trips under usual traffic are then 1.927 at 08:00-08:59 (motorway
    part 2.032), on the argument that inbound routes at the peak are slower than TomTom's all-roads
    city average.
11. **Capacity floor by road class** [A]. `cap_vph = k x max(adt_dir, adt_floor[frc])`, with
    `adt_floor` the 5th percentile of adt_dir over the sections of that frc (`prep.road_adt_floor_pct
    = 5`; unweighted, before k, inside the k calibration). It sets capacity only (flows stay from the
    counts); NZTA sections keep their measured capacity. Floors (adt_dir / veh/h at k = 0.076999): frc
    0 15,989.75 / 1,231.2; frc 1 6,432 / 495.3; frc 2 4,627.5 / 356.3; frc 3 2,566.5 / 197.6; frc 4
    1,851 / 142.5. 280 sections are raised (1.39% of origin-weighted pre-gate minutes), and sections
    below 100 veh/h fall from 56 to 0 (Williams Road, ADT 88, had 3.4 veh/h, so a single agent pinned
    it at the speed floor).
12. **950 agents** [A, author decision 2026-10-08]. `run.n_agents = 950` (5% of
    `engine.agents_represented` = 19,000; 1 agent = 20 cars, was 63.3) and `persona.n_twins = 95` (10%,
    was 30 of 300). Personas are not nested (the 300 agents are not a subset of the 950), so every run,
    figure and calibration is redone. A 30-day run takes about twice as long as at 300 (R-clock about
    40 s with PyEngine, about 100 s with NetLogoEngine). The NetLogo GUI draws queued cars about 70 m
    apart (20 cars x 7 m in 2 lanes).
13. **Why a 5% sample is defensible here.**
    - Convergence against a 19,000-agent run (1 agent = 1 car; R-daily, 10 days, seed 1, capacity
      scale 0.430, roads of 2026-10-07; days 6-10), n = 300 / 950 / 1,900 / 19,000: car share 0.863 /
      0.857 / 0.845 / 0.845; road delay 4.84 / 4.78 / 4.75 / 4.85 min; TTI of 08:00 departures 1.856 /
      1.875 / 1.864 / 1.872; gate queue 1.45 / 0.76 / 0.48 / 0.31 min.
    - Seed-to-seed SD (seeds 1-5, R-daily, same scale), n = 300 / 950 / 1,900: days 21-30 response
      1.9 / 1.1 / 0.5 pp; days 6-10 car share 0.017 / 0.014 / 0.008; mean road delay 0.29 / 0.24 /
      0.02 min.
    - At 300 one agent added 253 veh/h to every section it entered for 15 min (41% of the median
      section capacity of 618 veh/h; 80 veh/h or 13% at 950), and in the scale study 16% of the
      sections expected to carry at least 50 commuter vehicles had no sampled agent (0.2% at 950).
    - Literature [L]: downscaled MATSim runs keep the main traffic statistics at shares of 25% or more
      and can deviate below 10% (Ben-Dor, Ben-Elia and Benenson 2021, Simulation Modelling Practice
      and Theory 108, 102233; abstract read); traffic dynamics suffer below 30% (Saprykin, Chokani and
      Abhari 2021, Networks and Spatial Economics 21(2); abstract read); averages become unreliable
      below 10% (Mersini and Ziemke 2025, MATSim User Meeting, paper 30); 10% samples are usual
      MATSim practice. Those studies take all congestion from the agents and shrink capacity to the
      sample. Here the background traffic comes from the counts (commuters are about 16% of the
      counted morning volume on their routes, Road congestion 4), each agent enters as 20 weighted
      vehicles (scaling the vehicle, not the capacity), and the gate capacity is calibrated at each n.
    - LLM cost grows linearly with n. Research estimate with the 2026-10-07 model: L-clock 821 calls
      and 1.0M input tokens at 300, 2,437 calls and 2.97M at 950; L-daily 9,000 and 28,500 calls.
      Canonical estimate at 950 (`--estimate`, seed 1, final model, `runs/estimates/*_n950_d30_s1.json`):
      L-clock 2,726 calls and about 3.34M input tokens (about 4,900 prompt characters a call), L-daily
      28,500 calls and about 36.5M (about 5,130 characters a call), no shared answers.
    - The gate queue still shrinks with n (first bullet), so gate-queue figures are the least
      converged; 10% would be safer if they are reported on their own.
14. **Capacity floor in vehicles** [A]. `engine.min_capacity_vph = 950` veh/h, converted with the run's
    vehicles per agent (`round(950 / 60 / vehicles_per_agent, 6)` agents/min: 0.25 at 300, 0.791667
    at 950). The old `min_capacity_per_min = 0.25` agents/min was worth only 300 veh/h at 950 agents;
    it is used only when `min_capacity_vph = 0`. Only the East corridor (The Strand, Gladstone Road)
    reaches the floor; at 300 agents outputs are unchanged.
15. **Speed-ups with identical outputs.** `options.expected_public_delay` builds its corridor arrays
    once per day; `run.public_road` computes probe delays only for the departure grid
    (`options.departure_grid`), the only minutes any reader uses, with NaN elsewhere so that an
    off-grid read fails; `calibrate --seeds` runs the seeds in parallel processes (`--jobs`). Every
    output file is byte-identical before and after at 300 and 950 agents, and random draws are
    unchanged. The motorway rule and the NZTA data add no measurable run time.
16. **Capacity calibration** (`python -m cordonlite.run calibrate --seeds 1 2 3`; 950 agents, roads and
    breakdown on, `calib_delay = "total"`, 15 min [A, author decision 2026-10-07, re-confirmed
    2026-10-08]). Road delay now makes up most of the target: with an unlimited gate (scale 10) the
    car-weighted peak is already 11.1-11.6 min (11.2 / 11.6 / 11.1 on seeds 1-3, at PAP 22, k_WFH 9),
    so the calibrated gate queue adds only a few minutes. Split of the calibrated peak (in the peak bin
    of each corridor and day, car-weighted, days 6-10), seeds 1 / 2 / 3: queue 5.5 / 5.4 / 3.6 min and
    road 10.6 / 10.8 / 10.4 min of 16.2 / 16.2 / 14.0 min, a road share of 66%, 67% and 74%. Scales:
    0.396105 on all three seeds, recalibrated at the behaviour values chosen in item 17 (achieved
    16.15, 16.23 and 14.02 min against 15 +/- 2; converged after 8 probes each; 0.396105, 0.396105 and
    0.380043 at PAP 20, k_WFH 10). Runs with seed 4 or higher use the seed-1 record and print
    MISMATCH, by design.
17. **Behaviour calibration at 950 agents.** `scripts/calibrate_behaviour.py` reads n from
    `config.toml` (was fixed at 300), and single-seed tolerances scale as `x sqrt(300 / n)` [A]:
    shares +/-0.028 and response +/-2.2 pp at 950 (+/-0.05 and +/-4 pp at 300; SKIP 0), consistent with
    the measured seed SD of the days 21-30 response (1.9 to 1.1 pp from 300 to 950, ratio 0.58
    against 0.56). Stages that reuse a logged search keep that search's n. The 300-agent free-flow
    search is archived as `freeflow300`. Same targets, seeds (1-3 search, 4-5 held out, 6-12 out of
    sample), grid (PAP 10-36 x k_WFH 2-16, 405 points), nested capacity calibration and selection
    rule; started on 2026-10-09. Result: **PAP 22, k_WFH 9** (300 agents on free-flow roads: PAP 20,
    k_WFH 10), neither on an edge; PAP 22 equals v3 PAP 22-44 in v3's form. 8 of 405 points are
    feasible, all at PAP 22 (k_WFH 9-16): at the stated precision base PT is 0.16 at PAP 21 and base
    car 0.86-0.87 at PAP 23 for every k_WFH from 7 to 16. The chosen point is the feasible point
    nearest the anchors and also the lowest-loss point of the grid (loss 1.81); on unrounded 3-seed
    means two points are feasible (k_WFH 9 and 10), the chosen one among them. R-daily, mean of seeds
    1-3: base car 0.848, PT 0.146, WFH 0.004, SKIP 0.002, days 11-13 -27.2%, days 21-30 -20.7% (per
    seed -19.8 / -22.8 / -19.6%). Two single-seed values are outside their band but within the
    tolerance, both on seed 2: base car 0.856 and the days 21-30 response -22.8%. Held-out seeds 4 and
    5: -21.6% and -21.7%. Unseen seeds 6-12 (mean): -21.0% (single seeds -19.9% to -23.0%), nothing
    outside the tolerance, but base car 0.856 is above its band at the stated precision (0.853 over
    seeds 1-12). Capacity scales are in item 16; report in `docs/calibration_report.md`.
18. **V/C and Level of Service outputs** (as SSC2026; definitions in one place, `cordonlite/roads.py`).
    - V/C of a section at minute m = the engine's volume / cap_vph (usual traffic: obs_peak_vph x r(m)
      / cap_vph). Grade: HCM 1994 bands as used by SSC2026 (The Congestion Question WS1 "Defining
      congestion", Feb 2019; SSC2026 `netlogo/LOS_IMPLEMENTATION.md`): motorway mainline A < 0.30, B <
      0.48, C < 0.70, D < 0.90, E < 1.0, F >= 1.0; other roads A < 0.26, B < 0.43, C < 0.62, D <
      0.82, E < 1.0, F >= 1.0; a bound belongs to the worse grade, and a broken-down motorway is F.
    - "% of traffic at LoS E/F" and mean V/C are vehicle-km weighted (SSC2026 weighted by flow) [A];
      groups: motorway, other roads, all, and each corridor (the corridor with the most origin weight
      through the section).
    - Run outputs, written after the run from the scenario files and `road_entries.csv` (so identical
      for both engines; header only without roads): `road_los.csv`, one row per section x period
      (days 6-10, days 21-30) x bin (the four hours 06:00-10:00 and 07:00-09:00) with vc_mean, vc_max,
      speed_factor_mean, share_EF, los, commuter_veh, usual_vc_mean, speed_los, share_EF_speed and
      share_congested_AT; `los_summary.csv`, one row per day x bin x group. `summary.json` per day
      gains eight 07:00-09:00 keys (null without roads): `los_ef_share_mwy`, `los_ef_share_other`,
      `vc_mean_mwy`, `vc_mean_other`, `los_ef_speed_share_mwy`, `los_ef_speed_share_other`,
      `congested_at_share_mwy`, `congested_at_share_other`. Analysis: matching `summary_table` columns
      and `los.png` (E/F by V/C, E/F by speed, AT congested and mean V/C by hour).
    - NetLogo: monitors for LoS E/F, mean V/C and LoS E/F by speed (motorways, other roads) at the
      last 5-minute mark and a plot "% traffic at LoS E/F"; `check_network_model.py` requires them to
      equal the Python values within 1e-9. The LoS outputs add about 2-3 s to a 30-day run.
19. **Speed-based LoS next to the V/C grade** [author decision 2026-10-08/09; L]. The V/C grade stays
    as it is, for comparability with SSC2026, but it saturates: k is set so that the BPR curve gives
    TomTom's index, which needs a peak V/C of about 1.4, so other roads are E/F almost everywhere at
    07:00-09:00 (99.6% of their traffic in the test runs of 2026-10-08, and on days 6-10 and 21-30 of
    the canonical R-clock run) and the charge hardly moves the share. Speed grade: HCM 2010 urban street segment bands on the speed factor f (speed / free-flow
    speed, the engine's f): A f > 0.85, B > 0.67, C > 0.50, D > 0.40, E > 0.30, F <= 0.30, the same on
    every road; a broken-down motorway is F. E/F by speed = f <= 0.40 or broken down. Congested in
    Auckland Transport's sense = f < 0.5 (average speed below 50% of the posted limit; the free-flow
    speed is the posted limit here, `prep.ff_factor` 1.0). With alpha 0.15 these need V/C >= 1.778
    (E/F by speed), V/C > 1.607 (AT congested) and V/C >= 1.986 (F) on other roads.
20. **Verification.** After each change PyEngine and NetLogoEngine give byte-identical run folders
    apart from the engine label (30-day R-clock, 950 agents: 46 of 48 files byte-identical, including
    `road_los.csv` and `los_summary.csv`; the other two differ only in the engine label). Off-switches
    reproduce the earlier state byte for byte: `road.mwy_breakdown = false` with the 2026-10-07 data;
    every section on profile 0 with the global drop; prep with the floor, the rise test and the 6 km
    limit undone. `check_netlogo_equivalence.py` adds `road_mwy` (motorways with a full, a short and no
    window; commuter-triggered breakdowns; jam-cap hits) and `road_nzta` (3 profiles, 5 drops)
    variants. Independent code recomputed the NZTA site table, the mapping, the floors, k and every
    car's road delay (0 mismatches), and plain loops spot-checked `road_los.csv`, `los_summary.csv`
    and the summary keys. `tests/test_netlogo_interface.py` checks the NetLogo Info text against
    `data/road_meta.json`. Fast suite 397 passed, NetLogo suite 8 passed (2026-10-08); again 397 and
    8 passed on 2026-10-09 at PAP 22 / k_WFH 9, with the updated single-agent counts in
    `tests/test_rules.py`.
21. **Limitations.**
    - Throughput, not demand. NZTA TMS counts measure throughput: they give when a motorway breaks
      down and recovers, its pre-breakdown capacity and its post-breakdown discharge (capacity drop
      6-26%), but not how much demand queues behind the bottleneck. Broken-down speed is capped at
      0.45 of free flow (`road.mwy_jam_speed`), so the measured drop almost never sets the speed (155
      of 324,174 broken-down NZTA section-minutes with commuters in a 30-day test run, 0 under usual
      traffic): the counts decide when motorways jam, not how badly. A count that stays flat until
      10:45 cannot tell "still jammed" from "demand happens to equal that level" (Northcote,
      Newmarket, Greenlane, Mt Wellington, which keep their windows to 11:00).
    - Flat-count sites: Northcote stays broken down to 11:00 while Tristram upstream and the Harbour
      Bridge downstream clear at 09:30, an isolated jammed stretch that the data cannot settle.
    - The charge cannot shorten the static window: the window comes from usual traffic (the counts),
      and commuters are a few percent of motorway flow. The charge only prevents the breakdowns that
      today's commuters would start through the dynamic trigger.
    - SSC2026 had no motorway congestion dynamics (item 2): the motorway rule has no precedent in the
      earlier model, and SSC2026's motorway LoS figures are not comparable with Cordon-Lite's.
    - The motorway level is not anchored to a measured travel time: TomTom's index is matched on
      non-motorway sections only (item 10), no public source gives corridor-level AM motorway speeds,
      and the 2.0-2.5 motorway TTI that the evidence suggests is derived from all-day speeds, not
      measured.
    - Capacity = k x ADT stays circular on the sections without an NZTA site (previous entry, item
      13), and the V/C grade saturates (item 19). On NZTA sections capacity is the highest observed
      15-min flow, a lower bound where the site never broke down (SH20, SH16 city end): their usual
      V/C peaks just below 1, so small commuter surpluses trip the dynamic trigger, jams there depend
      on run-to-run noise, and the agents' usual-traffic information never shows them.
    - Upper Harbour, Airport and George Bolt Memorial Drive keep the default rule (item 9): 47 of
      their 53 sections share one window to 10:01, later than the nearby SH1 north stretch from
      Albany to Tristram Avenue, which clears at 09:30.
    - Mapping at any distance puts 40 sections 6 to 12.6 km from their site on its timing and capacity.
    - Motorway speed grades are effectively A or F: a section not broken down has V/C < 1, so f > 0.87,
      and a broken-down one runs at f <= 0.45; on motorways speed-based E/F, AT congested and the
      broken-down share are therefore the same number. Many motorway sections graded F have V/C below
      1, because counts during breakdown show the reduced discharge flow.
    - The speed factor jumps up at bd_off, so a later car can overtake an earlier one on long
      sections; the road delay agents are told jumps at the onset (test runs showed no rush of
      departures just before it).
    - HCM 2010 urban street bands are applied to motorways too (HCM grades freeways by density).
    - `commuter_veh` in `road_los.csv` is entries x vehicles per agent without w_factor, so it
      overstates the commuter load on the 4 sections with w_factor < 1.
    - The frc-0 floor is set by the high motorway ADTs and also raises 6 ramps (Exit 4A Northern
      Motorway by 39%, used by 582 origins).
    - 950 agents: see item 13; the gate queue is the least converged figure.
    - The gate queue is now a few minutes of the 15-min target; most of the calibrated delay is road
      delay (item 16).

## Extreme-charge scenarios, NetLogo choosers and clean-up, 2026-10-09

Changes of 2026-10-09 at the authors' request. At the usual schedule (peak NZ$6, from SSC2026) the
charge removes 20-38% of the commuters' car crossings on days 21-30 (seed 1, four arms), but
motorway congestion hardly moves, so the authors asked for an extreme scenario in which the charge
is high enough to change whether commuters travel at all. The same request asked for a simpler
NetLogo interface and for unneeded files to be removed. Nothing in the engine changed
(`engine.py`, `roads.py`, `vickrey.py`, the NetLogo procedures `road-arrivals`, `point-queues` and
`run-day`); PyEngine and NetLogoEngine stay output-identical.

*Superseded later on 2026-10-09* by "SKIP removed, willingness to travel and the peak charge"
below: the charge multiplier `fees.scale` and `fees.fee_flat` (item 2) are replaced by the peak
charge `fees.peak_fee` and the `_fx` runs (items 6-8) by `_peak` runs compared with a no-charge run
of the same days; SKIP is removed, and the willingness to travel is an exponential decay (item 3);
the behaviour is recalibrated (item 4). The NetLogo changes (item 9, with a new run list), the file
removals (item 10) and the review fixes not about `fees.scale` (item 13) still hold. The numbers
below describe the model before these changes.

1. **Decisions** [author requests 2026-10-09].
   - Raise the charge above the NZ$6 schedule so that it can change the commuters' willingness to
     travel; run it for the four arms.
   - NetLogo: remove inputs that are not needed (`fee-start-day`), make `scenario-dir` a chooser,
     and add a chooser of the days to watch (all days, before the charge, with the charge); the
     monitor of today's charge stays.
   - Remove files that nothing uses.
2. **Charge multiplier `fees.scale`** [A, author request 2026-10-09; addition to the
   specification]. It multiplies every NZ$ value of the schedule (the `tou_points` charges, or
   `fee_flat`) before the fee table is built and rounded; the hours, the regime and the charge day
   (`fee_start_day` 11) are unchanged, and regime "none" stays 0. Default 1 (the SSC2026 schedule,
   peak NZ$6); it must be > 0. The extreme-charge runs use 2, 3 and 5 (peak NZ$12, NZ$18 and NZ$30;
   NZ$30 is about London's daily charge). CLI `--fee-scale X`, folder suffix `_fx<X>`, `summary.json`
   meta `fee_scale` and `fee_peak`. Every consumer reads the scaled table (`fees.csv` for both
   engines and the GUI; `TodayInfo.fee_by_minute` for the options, T2 and the LLM prompt, which
   shows NZ$12.00 at scale 2). Because the scaled values are rounded, a scaled `fees.csv` differs
   from k x the scale-1 file by NZ$0.0001 (k = 2, 3) or NZ$0.0002 (k = 5) on the ramp minutes.
   At scale 1 every data file of a run is byte-identical to before.
   *Superseded 2026-10-09:* `fees.peak_fee` (`--peak-fee`, suffix `_peak<NZ$>`); `fees.scale` and
   `fees.fee_flat` are retired keys ("SKIP removed, willingness to travel and the peak charge" 6).
3. **Willingness to travel is the existing choice** [interpretation]. No new behaviour was added.
   A commuter who decides chooses between options that travel into the city centre (CAR at a
   departure time, PT) and options that do not. In the daily arms every commuter decides every day;
   in the clock arms only the commuters woken by a trigger decide, and the others repeat their
   standing option (decider "standing"). The rule arms make the logit choice (Gumbel noise on the
   generalised cost, Behaviour builder 1); MockLLM takes the lowest re-weighted sum of the same cost
   parts plus Gumbel noise. The options that do not travel are WFH, open only to hybrid office
   workers (303 of 950 on seed 1) and priced as k_WFH x phi(F) with no commute, parking or fuel
   credit (v3 relative form), and SKIP, a one-day
   postponement that costs NZ$30 plus one hour of the value of time. The share that travels is
   reported as `travel_share` (car + PT) in `summary_table` and `fee_response`. Not travelling
   cannot mean moving home or job, or giving up the trip for good, and WFH has no quota.
   *Superseded 2026-10-09:* SKIP is removed and the willingness to travel is an exponential decay
   in the charge that removes car options ("SKIP removed, willingness to travel and the peak
   charge" 2-4).
4. **Calibration not extended** [A]. PAP 22 and k_WFH 9 were calibrated on R-daily at scale 1
   (Motorway flow breakdown 17); the capacity scale was calibrated on uncharged days and is used
   unchanged. Results at scales 2-5 extrapolate the same cost model (fee term with the loss weight
   on the part above a reference fee that follows the fee faced, logit noise, WFH and SKIP costs)
   to prices it was never fitted to. The L arms use MockLLM, a pipeline check.
5. **Company cars and trades** [v3 3.1, 3.4; unchanged]. The charge of a company car is paid by
   the employer at any level: the agent perceives 0 (c = 0 in the generalised cost) and the fee
   counts as revenue (126 of 950 seed-1 agents: 104 trades and 22 others). Trades (149) must drive
   and have no PT or WFH option. At NZ$30 (days 21-30) the 104 trades with a company car drive on
   every day in every arm; the 45 without one keep driving under the rule (over 99% of their days)
   and postpone on 52-62% of their days under MockLLM; the 22 other company-car holders drive on
   91-100% of their days.
6. **Runs and outputs.** `runs/<arm>_mock_py_s1_fx2`, `_fx3`, `_fx5` for R-daily, R-clock, L-clock
   and L-daily (seed 1, 950 agents, mock backend, PyEngine). `python -m cordonlite.analysis` writes
   `runs/figures/fee_response.csv/.md` (one row per arm and charge level for days 21-30, plus the
   uncharged days 6-10), `fee_response_by_group.csv` (by archetype and company car) and
   `fee_response.png`; `summary_table` gains `travel_share_d10` and `_d30`. In every arm days 1-10
   of `decisions.csv` and `outcomes.csv` equal the canonical run's (`same_before_charge`).
7. **Results** (days 21-30 against days 6-10 of the canonical run, four arms). At a NZ$30 peak the
   car share is 0.16-0.26 (0.49-0.68 at NZ$6, 0.79-0.86 uncharged), the travel share 0.66-0.69
   (0.84-0.91 at NZ$6, about 0.99 uncharged), and car crossings fall by 69-80%. WFH levels off at
   0.18-0.20 (56-64% of the hybrid office workers' days) and SKIP rises to 0.10-0.16. The mean road
   delay of a car falls from 6.8-7.0 to 4.5-5.1 min and the share of other-road traffic at LoS E/F
   by speed from 5.2-5.4% to 3.5-3.6% (AT congested 13.0-13.7% to 7.0-7.3%), but on motorways LoS
   E/F by speed only goes from 79.2-79.7% to 76.1-76.3%. Weighted by vehicle-km, the commuters are
   about 5.6% of the counted peak-hour traffic on the motorway sections of their routes and 2.9% on
   the other sections (`phi` in `data/road_sections.csv`), and the usual breakdown windows come
   from the NZTA counts, which fewer commuter cars cannot shorten (Motorway flow breakdown 21).
   The full table was in the README until the `_peak` runs replaced it.
8. **Values against the trend, not explained.** The peak gate-queue delay rises from NZ$6 to NZ$12
   in R-clock (2.83 -> 3.03 min) and L-daily (0.94 -> 0.98 min). In both L arms the mean road delay
   of the remaining cars rises again at NZ$30 (L-clock 4.48 -> 4.92 min, L-daily 4.52 -> 5.06 min),
   and with it, slightly, the other-road shares at LoS E/F by speed (L-clock 3.53% -> 3.55%,
   L-daily 3.51% -> 3.53%) and AT congested (7.07% -> 7.16%, 7.08% -> 7.10%), and in L-clock the
   motorway share (76.09% -> 76.16%). L-clock's WFH share also dips at NZ$30 (0.192 -> 0.184) while
   SKIP grows. The likely cause of the congestion rises is the mix of the cars left (mostly trades
   and company cars, on other routes and at other times); it has not been checked.
9. **NetLogo interface** [author decisions 2026-10-09].
   - The `fee-start-day` input and its note are removed. A run's `scenario.csv` says from which day
     it is charged; a folder without it (a synthetic folder) is charged from day 11, the
     `config.toml` value, instead of from the input.
   - `scenario-dir` is a chooser of 20 runs: the four arms, their `_fx2`, `_fx3` and `_fx5` runs,
     the two traits-off runs and R-clock with a review every 5 and 10 days. A NetLogo 7 chooser
     refuses any value not in its list, so scripts can no longer `set scenario-dir` to a path: a new
     procedure `setup-run [dir]` sets up any folder and `setup` calls `setup-run scenario-dir`
     (`check_netlogo_equivalence.py` and `check_network_model.py` use it). Without `agents.csv`
     setup stops with an error that says to make the run with `python -m cordonlite.run`.
   - `charge-on` is a chooser of the days `go` and `finish-day` play: "all days", "off: before the
     charge", "on: with the charge" (`days-to-show`, `next-day-to-show`). After the last day picked
     they stop with a message. The reporter `charge-on?` is renamed `charged-day?` because the
     chooser now has that name; the monitor of today's charge is labelled "charged today".
   - A run folder that lacks one day's plans gives a message; only a folder without any plans file
     gets demo plans.
   - The note and the Info tab have five numbered how-to steps; the Info tab describes the runs in
     the chooser and says that the `_fx` runs go beyond what the calibration covers.
10. **Files removed** (2026-10-09).
    - `netlogo7/demo_scenario/` (59 files): a synthetic 300-commuter folder that nothing in
      `cordonlite/`, `scripts/`, `tests/` or `prep/` read. The code paths it used stay for synthetic
      folders such as the equivalence check's test scenarios: demo plans, straight lines for homes
      that are not road nodes, the queue at the corridor point.
    - `runs/estimates/L-clock_n300_d30_s1.json` and `L-daily_n300_d30_s1.json`: the out-of-date
      300-agent free-flow estimates (in git history).
    - `data/.gitkeep`: `data/` holds files.
11. **Verification** (2026-10-09). `check_netlogo_equivalence.py --gui-smoke`: equivalence 69 of 69
    and the GUI smoke, including `charge_on` (off: day 1 uncharged; on: day 2 charged). The NetLogo
    suite passed after the interface change (8 tests), and `tests/test_run_netlogo.py` (5 tests,
    including the new NetLogoEngine = PyEngine check at `--fee-scale 5`) after the multiplier. The R-clock and
    L-clock runs at scale 1 rerun with the new code equal the canonical runs in every data file.
    After the review fixes (item 13): fast suite (`pytest -q`) 415 passed, 9 skipped (the NetLogo
    tests); NetLogo suite (`-m netlogo --run-netlogo`) 9 passed; `--gui-smoke` again 69 of 69 with
    the GUI smoke and `charge_on` passing.
12. **Limitations.**
    - Charges above NZ$6 extrapolate (item 4); the L arms are MockLLM.
    - The only ways not to travel are WFH (hybrid office workers, no quota) and a one-day SKIP; a
      SKIP share of 0.10-0.16 at NZ$30 means repeated one-day postponements.
    - About 18% of commuters (company-car holders and trades) are almost untouched by the price
      under the rule, and the commuters are a small part of motorway traffic, so the scenarios cannot
      say what a charge on all traffic would do to the motorways.
    - Single seed (1) for every scale.
    - The canonical scale-1 runs were not regenerated: their `summary.json` lacks `fee_scale` and
      `fee_peak` (analysis takes 1 and the peak of `fees.csv`), and their `config_snapshot.toml`
      lacks `fees.scale` and `run.compress_csv_over_mb` (item 13).
13. **Review fixes** (2026-10-09).
    - `load_config` gives `fees.scale` and `run.compress_csv_over_mb` (`config._ADDED_KEYS`) their
      defaults (1.0, 100.0) when a file lacks them, as the snapshots of runs made before 2026-10-09
      do; any other missing key is still an error. `scripts/make_example_prompt.py` loads the
      canonical L-clock run again and rebuilds `docs/example_prompt.md` unchanged.
    - `--estimate` adds the run's variant suffix (without `_n`/`_d`, which the name has) to the file
      name, so `--estimate --fee-scale 5` writes `L-clock_n950_d30_s1_fx5.json` and leaves the
      canonical estimate alone.
    - `crossings_hist.png` and `cordon_entries.png` draw the charge from the runs' own `fees.csv`
      instead of `config.toml`: with `--all` the `_fx` schedules appear too, each labelled by its
      peak. The default figures (canonical runs, one schedule) are byte-identical to before.
    - The `_fx` check of `test_netlogo_interface.py` allows the rounding of item 2 ((k + 1) halves
      of NZ$0.0001) and checks the peak exactly.

## SKIP removed, willingness to travel and the peak charge, 2026-10-09

Decisions of the first author later on 2026-10-09, after the extreme-charge runs of the entry
above. They change the choice set and how charge levels are compared, and they supersede that
entry's charge multiplier, `_fx` runs and reading of the willingness to travel. Nothing in the
engines changed (`engine.py`, `roads.py`, `vickrey.py`, the NetLogo procedures `road-arrivals`,
`point-queues` and `run-day`); PyEngine and NetLogoEngine stay output-identical. The rule decider
was then recalibrated (next entry).

1. **Decisions** [author decisions 2026-10-09].
   - SKIP is removed completely. Every commuter chooses among CAR (a departure time), PT (if
     allowed) and WFH (if allowed).
   - The willingness to travel follows an exponential decay in the charge, as in the SSC2026
     model, in the form of a threshold fixed per commuter. Its price sensitivity `wtt.beta0` is
     calibrated together with PAP and k_WFH against the existing targets, with SSC2026's 0.5 as the
     anchor.
   - The peak charge is a plain NZ$ parameter (`fees.peak_fee`, CLI `--peak-fee`), replacing the
     charge multiplier `fees.scale`. Charge levels are compared with a no-charge run (peak 0) on the
     same days 21-30, not with days 6-10 of the charged run. The charge still starts on day 11, so
     the before/after design and the clock-versus-daily contrast stay. Levels run: 0, 3, 12, 18 and
     30 next to the canonical 6.
   - Wherever LoS E/F is reported, the mean V/C is shown beside it.
   - The calibration targets stay as they are and must be met again.
2. **Why SKIP was removed.** SKIP was meant as a one-day postponement (Scaffold 8, Integrator 3;
   NZ$30 plus one hour of VoT since Early start and SKIP cost 1), but it had become a permanent
   choice: at the NZ$30 peak (`_fx5`, item 7 of the entry above) 97 of R-clock's 102 skippers
   skipped every one of days 21-30, and at NZ$6, 8 commuters skipped every day. In the rule arms
   every skipper could have taken PT. Ten postponements in a row are a different behaviour (giving
   up the trip) that the SKIP cost did not represent. Not travelling now means WFH, which only
   hybrid office workers can do (no quota, Scaffold 4); a commuter who will not pay the charge
   takes PT, works from home or drives at a cheaper time (item 3).
   - Removed: SKIP from `options.feasible_modes` and `build_options`, the GC part `skip`
     (`types.GC_PARTS`), `types.MODES`, the rule's option code and labels, MockLLM's `w_skip`, the
     prompt row and the output schema (template `cl-v3`, item 5), and the `summary.json` day key
     `skip` (the run's progress line prints `no-car` instead).
   - Habit reference: `AgentMemory.habit_option_id` is deleted; the habit reference, the prompt's
     "usual" option and `DecisionContext.standing_option_id` are the standing option itself
     (supersedes Final fixer 3). T6 has no standing-SKIP clause (supersedes Integrator 3).
   - Retired keys `costs.skip_cost`, `costs.skip_vot_hours` and `llm.mock.w_skip`
     (`config._RETIRED_KEYS`): the `config_snapshot.toml` of an older run still loads (the keys are
     dropped), and `--set` of a retired key is an error.
   - Left as is: the engines still accept a plan whose mode is neither CAR nor PT (the commuter
     stays home), because `engine.py` was not to change; `conftest.tiny_plans`, the engine tests and
     the equivalence check's `all_skip` plan set still use such plans.
3. **Willingness to travel: exponential decay** [author decision 2026-10-09; SSC; A]. Each commuter
   draws u ~ U(0, 1) once, on stream "A" after every other Layer A draw (the early-start permission
   included), so no existing persona field changes; twins copy it with the rest of Layer A. Then
   beta = clip(beta0 x VoT_ref / VoT, 0.1, 2.0) with VoT_ref = exp(`persona.vot_mu`) = NZ$9.97/h
   (`wtt.vot_ref = "distribution_median"`, the median of the VoT distribution), and the most the
   commuter would pay a day to drive into the city centre is WTP = -ln(u) x VoT / beta (NZ$, VoT in
   NZ$/h, rounded to the cent). Then P(WTP >= F) = exp(-beta F / VoT): the share of commuters
   willing to drive falls exponentially in the charge F.
   - Rule: on a charged day a CAR option whose levied charge (`Option.fee`, the fee at its expected
     cordon crossing, the one the commuter would pay) is above WTP is removed from the choice set;
     a charge equal to WTP stays (`options.wtt_filter`, applied by `build_options` unless
     `wtt=False`). Cheaper shoulder departures stay (retiming), and a commuter unwilling to pay any
     of them takes PT or works from home.
   - Exceptions: a company car never loses a car option (the employer pays; its perceived charge
     is 0), and neither does a commuter with neither PT nor WFH (the must-drive trades: an
     essential trip). Seed 1: 171 of 950 commuters (126 company cars, 45 trades without one).
   - `wtt.beta0 = 0` switches the rule off (no clip, WTP infinite), which reproduces the model
     without it (tested); it is also the dataclass default, so an older snapshot loads as before.
   - It applies in every arm (rule, MockLLM, live LLM). It is a choice-set constraint like
     `pt_allowed`, so the R and L arms face the same options; the LLM cannot decide to pay more.
   - On an uncharged day every fee is 0 <= WTP and nothing is removed, so days 1-10, the base
     shares and the capacity calibration do not depend on beta0 (tested; checked in the
     calibration: identical scales at beta0 0 and 0.5).
   - Calibrated value (next entry): beta0 = 0.15. A commuter with the median VoT pays the NZ$6 peak
     with probability exp(-0.15 x 6 / 9.97) = 0.91. On seed 1, 14.4% of commuters have a WTP below
     NZ$6 (exempt ones included) and 8.6% of commuter-days on days 21-30 have no car option left.
4. **Differences from SSC2026** (`akl_pricing.nls`, `decide-baseline`: p_enter =
   clip(base_trip_rate x exp(-beta x fee / VoT), 0.05, 0.95), beta = clip(base_beta x median VoT /
   VoT, 0.1, 2.0), base_beta 0.5) [A].
   - A threshold fixed per commuter (u drawn once) instead of a new entry draw every day: the same
     commuters are limited on every charged day, and the share of the population willing to pay F
     is exp(-beta F / VoT) exactly.
   - VoT_ref is the median of the VoT distribution, exp(2.3) = NZ$9.97/h, not the sample median
     that SSC2026 used (`median [vot] of vehicles`; NZ$10.40 on seed 1). `wtt.vot_ref =
     "sample_median"` gives SSC2026's choice; at the chosen point it leaves the response unchanged
     (-21.4%, `docs/calibration_report.md`).
   - No base trip rate (SSC2026 draws one per vehicle, U(0.3, 0.7)): a commuter travels every day
     at no charge (rate 1), and not travelling means WFH.
   - No 0.05-0.95 clip: at no charge everyone is willing, and at a high charge the share willing
     can fall below 0.05.
   - No essential-trip draw (SSC2026: 5-15% a day by VoT, entry probability at least 0.8 that day):
     replaced by the two structural exemptions of item 3.
   - The decay removes car options rather than deciding entry. The decider (rule or LLM) then
     chooses among what is left, so a commuter can retime to a cheaper departure, take PT or work
     from home. SSC2026 first picks the best fee shift and then applies the entry probability at
     the fee it would pay.
   - WTP is rounded to the cent, so the rule and the prompt use the same number.
   - beta0 is calibrated (0.15), not fixed at SSC2026's 0.5 (0.5 gives -32.3% on days 21-30 at
     the chosen PAP and k_WFH, beyond the band).
5. **Where it acts.**
   - `run.simulate`: per agent and day it builds every feasible option (`wtt=False`), filters them,
     evaluates the triggers on the offered option ids and rebuilds the options only when a trigger
     is a discontinuity.
   - `fee_faced` reads the unfiltered options, so the reference fee follows the charge at the car
     reference departure even when that departure was removed.
   - T6 given option ids requires the standing car departure itself to be offered: a standing
     departure removed today wakes a clock-arm agent. Given modes it behaves as before.
   - A commuter left with one option (PT only: every car option removed and no WFH) gets decider
     `forced`, and no decider or LLM is called (supersedes Integrator 10). Seed 1: 60 forced
     decisions on each charged day, 1,200 over days 11-30, so the daily arms make 27,300 decider
     calls rather than 28,500.
   - Prompt template `cl-v3`: no SKIP row or choice. On a day when the limit removed a car option
     (`DecisionContext.wtt_removed > 0`) TODAY says "You would not pay more than NZ$x a day to drive
     into the city centre", followed by "so driving at times when the charge is higher than that is
     not offered today" or, when every car option is gone, "and every time you could drive today is
     charged more than that, so driving is not offered today". `cl-v1` and `cl-v2` snapshots still
     load (`config.RETIRED_TEMPLATE_IDS`), but `LLMDecider` renders `cl-v3` only.
   - Outputs: `personas.csv` gains `wtt_u`, `wtt_beta`, `wtp_fee` (the last three columns; `inf`
     with beta0 = 0; a 60-agent run with beta0 = 0 is byte-identical under both engines, whose
     headless part does not read `personas.csv`; the GUI reads only its `origin_id` column, and
     replaying such a run in the GUI was not tried); `decisions.csv` gains `wtt_removed` (car
     options removed that agent-day) and `wtt_all_removed`; `summary.json` days gain `wtt_limited` and `wtt_no_car`,
     and `meta` gains `wtt`, `wtt_limited_days_total` and `wtt_no_car_days_total`.
6. **Peak charge `fees.peak_fee`** [A, author decision 2026-10-09]. It replaces `fees.scale` and
   `fees.fee_flat`.
   - Every ToU charge is multiplied by `peak_fee` / 6 (the points' highest charge) before the table
     is built and rounded; the hours stay, and 6 gives the SSC2026 schedule unchanged. Peaks 12, 18
     and 30 give exactly the `fees.csv` of the earlier `_fx2`, `_fx3` and `_fx5` runs (checked).
     Regime "flat" charges `peak_fee` all day.
   - `peak_fee` must be >= 0. Peak 0 levies nothing (`fees.levied_regime`): it is the same run as
     regime "none", with no charge day (`scenario.csv` `charge_from_day` 0), no T2 and no charge in
     the prompt; its outputs are byte-identical to a `--regime none` run (tested for R-clock and
     L-daily).
   - CLI `--peak-fee NZ$`, folder suffix `_peak<NZ$>` (for example `R-clock_mock_py_s1_peak12`); the
     canonical NZ$6 runs have no suffix. `summary.json` `meta.fee_peak` stays; new runs no longer
     write `fee_scale`.
   - Retired keys `fees.scale` and `fees.fee_flat`. An older snapshot loads with `peak_fee` = its
     scale (1 if absent) x its own peak (`config._migrate_fees`): the earlier canonical runs load as
     6, an `_fx3` run as 18.
   - Comparison: `analysis.fee_response_table` compares each run with the same arm's peak-0 run on
     the same days 21-30 (`car_crossings_change_pct`, the main measure); the change against the
     run's own days 6-10 is kept as a secondary column. Days 1-10 of every peak run equal the
     peak-0 run's (`same_before_charge_as_peak0` True in all 20 charged rows).
   - Runs: peaks 0, 3 (AT's modelled NZ$3 and the 2026 consultation's NZ$3-4), 12, 18 and 30 for
     the four arms on seed 1 (`runs/<arm>_mock_py_s1_peak<NZ$>`), next to the canonical NZ$6 runs.
     The `_fx` runs are no longer used: analysis leaves them out and the NetLogo chooser no longer
     lists them. At the time of writing 11 of the 12 `_fx` folders were still in `runs/` (deleting
     them was refused by the permission system; one is in the Recycle Bin). Until they are deleted
     (`rm -rf runs/*_mock_py_s1_fx2 runs/*_mock_py_s1_fx3 runs/*_mock_py_s1_fx5` from
     `cordon_lite/`), `.gitignore` ignores `cordon_lite/runs/*_fx*/`, so they cannot be committed.
7. **LoS E/F shown with the mean V/C** [author decision 2026-10-09]. `analysis.LOS_NOTE` is printed
   under `summary_table.md`, `fee_response.md`, `los.png` and `fee_response.png`; `fee_response`
   has LoS E/F by speed, LoS E/F by V/C and the mean V/C side by side for motorways and other
   roads; `los.png` panels are reordered (E/F by V/C, mean V/C, E/F by speed, AT congested); the
   NetLogo GUI has a mean V/C plot under the LoS plot. The note says why the V/C grade hardly
   moves: on other roads about 99% of the traffic is at E/F from 07:00, because their capacity is a
   BPR scale fitted to the TomTom index (k = 0.077 x ADT), not a lane capacity; on motorways about
   76% of the vehicle-km is inside the fixed usual breakdown windows, which are graded F whatever
   the flow. These two numbers are fixed text from the analysis of 2026-10-09, not computed per run.
8. **Results** (seed 1, days 21-30, four arms, each against its peak-0 run on the same days;
   `runs/figures/fee_response.md`). The share of commuters with a WTP below the peak is the same in
   every arm (a persona property): 8.6%, 14.4%, 24.4%, 34.4% and 44.3% at NZ$3, 6, 12, 18 and 30,
   and 4.3%, 8.6%, 14.4%, 20.1% and 29.5% of commuter-days have no car option left.
   - What falls: car crossings by 8.5-18.8% at NZ$3, 21.2-38.0% at NZ$6 and 68.8-77.2% at NZ$30;
     the car share from 0.81-0.87 to 0.51-0.68 (NZ$6) and 0.19-0.27 (NZ$30); the travel share
     (car + PT) from 0.999 to 0.90-0.96 and 0.81-0.84; the mean road delay of a car from 6.99-7.16 to
     5.27-5.69 and 4.64-5.02 min; the peak gate queue from 3.07-4.48 to 0.95-1.86 and 0.34-0.54 min;
     traffic at LoS E/F by speed on other roads from 5.4-5.6% to 3.8-4.1% and 3.5% (AT congested
     13.6-14.2% to 8.8-9.9% and 6.8-7.3%).
   - What hardly falls: motorway LoS E/F by speed, 79.5-80.0% to 77.0-77.6% and 76.0-76.2%; LoS
     E/F by V/C, motorways 93.7-94.8% to 93.5-94.1% and 91.4-92.3% (mean V/C 0.916-0.920 to
     0.886-0.897 and 0.866-0.871), other roads 99.6-99.7% to 99.5-99.6% and 99.3-99.4% (mean V/C
     1.409-1.413 to 1.379-1.388 and 1.359-1.363); and the peak 15-min queue + road delay, which
     falls from 13.55-15.10 min to about 10 min at NZ$3 and stays there (9.66-11.50 min from NZ$3
     to NZ$30): most of it is road delay in the worst bin, which background traffic dominates.
   - WFH levels off at 0.16-0.19 (only the 303 hybrid office workers can work from home; they do
     on 50-59% of their days at NZ$30), so the travel share levels off too.
   - Against the trend, not explained: in both L arms the mean road delay of the remaining cars
     rises from NZ$18 to NZ$30 (4.52 to 4.91 min, 4.63 to 5.02 min), probably because the cars left
     are mostly trades and company cars (not checked); L-clock's peak gate queue rises from NZ$3 to
     NZ$6 (0.93 to 1.62 min).
9. **NetLogo interface** [author decisions 2026-10-09].
   - `scenario-dir` lists 28 runs: the four arms (R-clock first, the default), their `_peak0`,
     `_peak3`, `_peak12`, `_peak18` and `_peak30` runs, the two traits-off runs and R-clock with a
     review every 5 or 10 days. No `_fx` entry or text is left in the model.
   - A "Mean V/C (1 = at capacity)" plot (pens "motorways" and "other roads") sits directly under
     the "% traffic at LoS E/F" plot; `plot-los` feeds both from the same 5-minute `los-at` pass,
     so the engines compute nothing new. The LoS note says "1 = at capacity" and ends with the
     advice to read LoS E/F together with the mean V/C; the Info tab gains a "Level of service"
     paragraph with the saturation explanation of item 7.
   - The how-to note names the `_peak` runs (`_peak12`: peak NZ$12 instead of NZ$6; `_peak0`: no
     charge), and the dots read "grey = works from home". A `_peak0` run has no charge day
     (`scenario.csv` `charge_from_day` 0), so "charged today" is false on every day and "on: with
     the charge" has no days (the Info tab says so). The Info tab describes car, PT and WFH, the
     willingness to pay (with its exemptions: company cars and commuters who can neither take PT
     nor work from home) and the `_peak` runs, compared on the same days.
   - Two display problems that showed only with a real run were fixed: the queue plot's legend uses
     short corridor names ("0: East", reporter `corridor-short-name`) and its y-axis reads "cars";
     the hour axes end on the next quarter hour (10.25 instead of 10.1833...). The interface is
     about 970 px tall (five plots in the right-hand column).
10. **Verification** (2026-10-09). `check_netlogo_equivalence.py --gui-smoke`: equivalence 69 of 69
    and the GUI smoke (minutes of days 1 and 2 with 0 mismatches, both LoS plots with their pens:
    `los_vc_pens_ok`, `los_mark` 510, `charge_on`). The canonical NetLogo R-clock run equals the
    PyEngine run (`--compare` identical; 46 of 48 files byte-identical, the other two differ only in
    the engine label). Fast suite after the regenerated runs: 437 passed, 10 skipped (the NetLogo
    tests); `tests/test_run_netlogo.py` 6 passed (including NetLogoEngine = PyEngine at `--peak-fee
    30` and at `--peak-fee 0`). The full NetLogo suite was not rerun after the final runs.
11. **Limitations.**
    - The threshold is fixed per commuter: the same commuters lose the same car options on every
      charged day, with no day-to-day variation.
    - beta is clipped below at 0.1. At beta0 = 0.15 the floor binds for every commuter with a VoT
      above NZ$14.96/h (28.8% on seed 1), and any positive beta0 removes some car options; the
      limit can only be made weaker than the floor by switching it off.
    - Behaviour is calibrated at the NZ$6 peak. At other peaks the share willing to pay falls as
      exp(-beta F / VoT) by construction, so the response at NZ$12-30 is steep whatever the rest of
      the cost model says.
    - The limit is a constraint, not a preference: a live LLM cannot choose to pay more than WTP,
      and the L arms share the rule's willingness to pay.
    - The 171 exempt commuters (company cars and trades) keep every car option although 26 of them
      have a WTP below NZ$6 and 76 below NZ$30 (seed 1).
    - Without SKIP the only way not to travel is WFH (hybrid office workers, no quota); nobody can
      give up a day's trip.
    - One seed (1) for every peak; the L arms are MockLLM.

## Behaviour recalibration with the willingness to travel, 2026-10-09

After SKIP was removed and the willingness to travel (`[wtt]`) was added [author decisions
2026-10-09; the model changes are described in "SKIP removed, willingness to travel and the peak
charge" above], the rule decider was recalibrated with `wtt.beta0` as a third searched scalar.
Nothing in the engines changed.

1. **Archive.** The state before these changes (950 agents, congested roads, SKIP NZ$30, no
   willingness to travel, PAP 22 / k_WFH 9) is kept as `skip30_nowtt`:
   `data/behaviour_calibration_skip30_nowtt.json`, `data/calibration_skip30_nowtt.json`,
   `docs/calibration_report_skip30_nowtt.md` (with an archive note and its figure links) and
   `docs/figures/skip30_nowtt/` (the four `calib_*.png` and `example_prompt_skip30_nowtt.md`, the
   `cl-v2` example of that state), the same convention as `freeflow300`. It is the script's new
   `LAST_JSON`; `freeflow300` stays in the report's history table (`FREEFLOW_JSON`).
2. **Unchanged:** the targets (less the SKIP share, which went with SKIP), the seeds (1-3 search, 4-5
   held out, 6-12 out of sample), the loss, the single-seed tolerances, the selection rule, the PAP and
   k_WFH ranges, the nested capacity calibration and the fixed inputs. **Changed** [A]: the anchors and
   the loss prior gain beta0 0.5 (SSC2026 base_beta); the "before" state sets beta0 0 and has no SKIP
   any more; the "structural" state runs at the design values PAP 8, k_WFH 8 and beta0 0.5; points
   with beta0 = 0 (the limit switched off) are run as references and are never selected.
3. **Staged search** [A]. The full 27 x 15 x 7 grid would take about 11 hours on 14 workers even with
   the capacity calibration shared, so the search has three stages: (1) beta0 0.05, 0.1, 0.2, 0.3,
   0.5, 0.75, 1.0 (and 0) on PAP 21-23 x k_WFH 4, 6, 8, 9, 10, 12, 14, 16 around the earlier optimum and
   on the four grid corners; (2) the full NZ$1 k_WFH range at every stage-1 beta0, on the PAP values at
   which stage 1 meets the three base-share targets, widened by one PAP at the edge (it ran PAP 22-24);
   (3) the midpoints between the stage-2 choice (k_WFH 13 / beta0 0.2) and its neighbours, beta0 0.15
   and 0.25. The capacity calibration runs without the charge, where the willingness to pay removes
   nothing, so it is solved once per (PAP, k_WFH, seed) and shared by every beta0 (checked: identical
   scale and peak at beta0 0 and 0.5); the base shares are the same for every beta0 too. 171
   calibrations and 1,638 charged runs, 489 points and 57 references; search 1.9 h, `--stage all`
   2.3 h on 14 workers. The search keeps a checkpoint in the system temp folder so that it can resume
   after an interruption.
4. **Result: PAP 22, k_WFH 12, beta0 0.15** (previously PAP 22, k_WFH 9, no willingness to travel),
   put into `config.toml`; `data/calibration.json` recalibrated at them (scales 0.430292, 0.396105,
   0.396105; achieved 13.57, 16.52, 14.51 min). 15 of 489 points are feasible at the stated precision,
   all at PAP 22, on a ridge from k_WFH 10 / beta0 0.05 to k_WFH 14 / beta0 0.25: a higher k_WFH weakens
   the WFH response as much as a higher beta0 strengthens the willingness-to-pay response. The chosen
   point is the feasible point nearest the anchors, only 0.011 ahead of k_WFH 13 / beta0 0.2 in anchor
   distance, so the anchors place the model on the ridge; the lowest-loss point is k_WFH 10 / beta0
   0.05. None is feasible on unrounded means (base car 0.853-0.855). R-daily, seeds 1-3: base car
   0.854, PT 0.145, WFH 0.001; days 11-13 -25.2%, days 21-30 -21.4% (-20.9 / -23.1 / -20.4%). Base car
   on seeds 1 and 2 (0.853, 0.859) and the seed-2 response are outside their bands but within the
   tolerance. 14.2% of commuters have a WTP below NZ$6 and 8.3% have no car option on charged days;
   5.6% of all commuters are left with PT only.
5. **Out of sample** (seeds 6-12, after the selection): response -21.1% (single seeds -19.2% to
   -23.1%), overshoot -25.4%, no seed outside the tolerance; but base car is 0.863 (0.859 over seeds
   1-12), above the band at the stated precision. The ridge alternatives (k_WFH 11 / beta0 0.1 and
   k_WFH 10 / beta0 0.05) give -20.7% and -21.0% on seeds 4-12.
6. **Sensitivities** (chosen PAP and k_WFH, seeds 1-3, not adopted): beta0 0 gives -14.5% (the
   willingness to travel adds about 7 pp at the chosen point); SSC2026's beta0 0.5 gives -32.3%
   (overshoot -35.5%), beyond the band; VoT_ref from the sample median, as SSC2026, leaves the response
   practically unchanged (-21.4%); without the early start the response is -22.8% with seed 2 beyond
   the tolerance. Because beta is clipped below at 0.1, any positive beta0 removes some car options
   (4.3% of commuters at beta0 0.05).
7. **Limits.** Behaviour is calibrated at the NZ$6 peak only; the `--peak-fee` runs extrapolate, steeply
   for the willingness to travel by construction. Where on the ridge the model sits is decided by the
   anchors, not by the targets. Base car runs high out of sample. Full account:
   `docs/calibration_report.md`.
8. **Script and tests.** `scripts/calibrate_behaviour.py` (three scalars, staged search, shared
   capacity, WTT metrics, new sensitivities, report and figures; INTERFACES.md, "Behaviour calibration
   with the willingness to travel"). `tests/test_run.py`: the two calibration tests drop `base_skip`,
   and a new test covers the helpers of the search (anchors, references, stage rules, grid edge).

## Origins from the 2023 Census OD, 2026-10-16

The specification placed origins by a local-road density proxy, with an unused hook for Census SA2
counts (`prep.od_csv`, [SPEC] empty). The origins now come from the Census.

1. **Decisions** [author decisions 2026-10-16]. Origins from the 2023 Census origin-destination table;
   only car drivers are counted; the destination stays the one node in the centre (origins only).
2. **Data** [DATA]. Stats NZ, "2023 Census main means of travel to work by statistical area 2" (usual
   residence SA2 x workplace SA2, counts by mode, CC BY 4.0), and Auckland SA2 2026 polygons, both from
   the gtfs-isochrone repository (`prep.census_od_csv`, `prep.sa2_gpkg`). The workplace SA2s in the
   cordon are the 17 whose representative point lies inside SA3 "Auckland City Centre" (they fill it
   exactly). Drivers = `2023_Drive_a_private_car_truck_or_van` + `2023_Drive_a_company_car_truck_or_van`
   (`prep.od_modes`), residence outside the cordon. 2023 codes are matched to the 2026 polygons by code;
   14 residence SA2s without a polygon (Waiheke, Pokeno, Mangawhai and others; 114 drivers) are dropped.
3. **Suppression** [A]. The table shows no zero: every count below 6 is -999, the others are multiples
   of 3 (random rounding). Of 8,952 driver cells of outside-to-cordon pairs, 7,104 are suppressed, and so
   are 1,049 of the 4,476 pair totals. A suppressed cell gets part of its pair's residual (Total_stated
   minus the shown cells) in proportion to the shown mode shares of all outside-to-cordon pairs, at most
   5 a cell (`prep.od_suppressed_cap`); a pair whose total is suppressed is given 3 commuters
   (`prep.od_suppressed_total`, the middle of 1-5), split the same way. Drivers: 19,887 shown (a lower
   bound), 27,215 filled. The shown cells alone would put 60% of the drivers within 10 km of the centre
   and 5.4% beyond 20 km; filled, 56% and 8.7%.
4. **Within an SA2** [A] (`prep.od_within_sa2 = "proxy"`). An SA2's drivers go to the candidate nodes
   inside its polygon in proportion to the old proxy (frc 3-4 road within 500 m). 116 SA2s (2,355
   drivers, 8.7%) have no candidate node inside and go to the node nearest their representative point;
   92 of them (1,614 drivers, 6.0%) lie more than 2 km away, beyond the TomTom extent (Kumeū, Riverhead,
   Millwater, Orewa, Karaka), so their trip starts at the network edge and their free-flow time is too
   short.
5. **Double weighting fixed** [A] (`prep.origin_draw = "iid"`). `sample_origins` drew 3,000 origins
   without replacement in proportion to the weight, and each kept its candidate weight; `build_personas`
   then drew agents by that weight again (and `prep.build_roads` weighted origins by it), so a node's
   share went roughly with its weight squared. With the even proxy this mattered little; with the
   Census weights (coefficient of variation 3.8 over the candidates) the seed-1 agents would have been
   14.6% South-east (Census 20.1%) and 33.3% West (24.4%). The origins are now 3,000 independent draws in
   proportion to the weight, a node drawn k times being one origin of weight k (2,361 origins, at most
   57 draws on one). The expected agent shares by corridor are within 0.6 pp of the Census; seeds 1-3
   differ from them by up to about 2 pp (sampling noise). `"unique"` keeps the old draw.
6. **Prep results.** 23 gates (27 before), corridor shares of the draws E 6.6, SE 19.9, S 13.2, SW 35.7,
   W 24.6% (before 2.3, 30.0, 24.1, 23.4, 20.2); 4,799 road sections (5,903), 752 km; k = 0.077563
   (0.076999); motorway TTI 08:00-08:59 2.099 (2.032); 262 motorway sections (285); commuters 13% of the
   counted volume on their routes (16%). The NetLogo Info tab's sentence on the floor-raised Upper
   Harbour stretches was updated (seven, clearing 09:15-09:30). The engines, personas, clock, options
   and deciders are unchanged.
7. **Recalibration.** Capacity (days 2-5): 0.396105, 0.396105, 0.430292 (peaks 13.93, 13.35, 14.70
   min). Behaviour: `scripts/calibrate_behaviour_d10.py`, same targets, seeds and selection rule; 46 of
   1,085 points feasible on the NZ$1 grid (no stage 3), all at PAP 20 but one; chosen PAP 20 / k_WFH 16
   / beta0 0.15 (previously 21.5 / 16 / 0.15). Seeds 1-3: base car 0.846, PT 0.154, response -22.2%;
   seeds 4-12: base car 0.849, response -22.1%, in band. k_WFH sits at the top of its range, as before.
8. **Runs.** The canonical runs, the charge-level runs, the traits-off runs, seeds 2-3, the GUI replays
   and the MockLLM estimates were regenerated (README, "Census OD origins"). R-daily -20.9%, R-clock
   -23.0%, L-clock (mock) -38.6%, L-daily (mock) -35.1% (days 6-10 vs 2-5). Not regenerated: the H-clock
   pilot (`think_*`, live API) and the `_d10_fs6` runs of the proxy origins.
9. **Archive.** `data/behaviour_calibration_proxy.json`, `data/calibration_proxy.json`,
   `docs/calibration_report_proxy.md`; the proxy-origin `data/` and runs are in git history (commit
   54bc265).
10. **Limitations.**
    - The Census table has no time of day: it counts drivers to a cordon workplace whenever they
      travel, so it sets where commuters live, not how many enter in the charged hours (19,000 stays).
    - It has no trip purpose other than work, and no students' trips to study.
    - Suppressed cells are imputed, not observed: 27% of the 27,215 drivers.
    - Origins beyond the TomTom extent start at its edge; within an SA2 the spread is the old proxy.
    - The destination is still one node, although the table knows each driver's workplace SA2.
11. **Code and tests.** `prep/build_od.py` (new), `prep/build_inputs.py` (`od_weights`, the `iid` draw,
    report lines), `cordonlite/config.py` (nine `[prep]` keys, in `_ADDED_KEYS`, so older snapshots
    load); `tests/test_od.py` (new: allocation with the cap, imputation, a toy Census table end to end,
    the split within an SA2 and the snap), `tests/test_prep.py` (the `iid` draw; the shipped-data check
    allows fewer distinct origins), `tests/test_prep_roads.py` (the toy networks keep the proxy and the
    old draw).
