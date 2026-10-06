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
9. **Late tolerance for T3.** v3 uses a fixed 15% threshold for everyone; the specification
   makes it depend on F. Mapping by F level 1..5: 5, 5, 10, 15, 15 minutes [A].
10. **Habit discontinuity.** kappa_H is multiplied by 0.5 on T1, T2, T4 and T6 wakes, as in v3
    section 4.4 (not stated in the specification).
    *Recalibration:* T2 is no longer a discontinuity (Behaviour recalibration 4).
11. **Twins.** To produce the twin table, the last `min(n_twins, n_agents // 2)` agents copy
    Layer A of the first agents and keep their own Layer B draws (default 30 twins of 300).
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
8. **GUI.** Plots are drawn only by `run-day-gui` (headless `run-day` does no plotting, for speed).
   When `plans_dayNN.csv` is missing, `run-day-gui` writes seeded demo plans (every commuter drives,
   departing 06:45 to 08:00). `netlogo7/demo_scenario/` is synthetic (300 commuters, 5 corridors),
   not Auckland data. The cordon is drawn as a grey disc, corridors as labelled targets placed by
   bearing from the mean corridor position, commuters at their scaled NZTM origins.

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
8. **Personal delay expectation.** v3 compares PT with remembered car times (T-bar, T_b). Cordon-Lite
   uses yesterday's public corridor delay profile times the agent's EMA delay ratio (specification).
   The public profile is the mean queue delay of yesterday's cars by 5-min gate-arrival bin,
   linearly interpolated between bin mid-points; inside the first and last observed bin the edge
   value is held, and outside the observed range the forecast is 0 [A]. Unserved cars (-1) are
   ignored.
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
3. **A standing SKIP wakes the agent the next day.** Skipping is a one-day postponement, so a
   standing SKIP counts as an infeasible standing plan and fires T6 every following day
   (`clock._standing_feasible`). Without this, an agent that skipped once under a clock arm would skip
   for the rest of the run, because no other trigger fires. A rule agent can still choose SKIP again.
   *Final fixer:* the re-decision no longer favours SKIP (Final fixer 3) and SKIP scales with VoT (Final fixer 4).
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
9. **Estimate mode.** `--estimate` (alias `--dry-run`) simulates the L-* arm with MockLLM and
   PyEngine in a temporary folder and counts the prompts. The count is approximate because a real LLM
   would choose differently and so wake agents on other days; tokens are characters / 4 for system
   plus user prompt, excluding schema, adaptive thinking and output.
10. **Forced decisions never occur.** Every agent has at least CAR options and SKIP, so `forced` is
    implemented but never used.
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
3. **A standing SKIP is not a habit.** On the re-decision after a SKIP, every non-SKIP option
   carried kappa_H and SKIP none, which pushed agents to skip again (agent 94 skipped 30 of 30
   days). `AgentMemory.habit_option_id` returns the most recent non-SKIP option for a standing
   SKIP; it is the habit reference in `build_options`, the "usual" option in the prompt and
   `DecisionContext.standing_option_id`.
4. **SKIP cost scales with the value of time.** A flat NZ$25 made SKIP the cheapest option for
   high-VoT agents even without a charge. SKIP now costs `skip_cost + skip_vot_hours x VoT` with
   `skip_vot_hours = 1.0` [A] (a lost or postponed day is worth more to someone whose time is worth
   more). No agent skips in the canonical runs, so the clock arms no longer have a floor of daily
   T6 calls (R-clock: 0 decider calls on most days after day 12).
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
8. **Recalibration.** Same targets, seeds (1-3 search, 4-5 held out, 6-12 out of sample), loss,
   selection rule, grid (PAP 10-36 x k_WFH 2-16, 405 points) and two scalars; parking and fuel
   fixed. Result: **PAP 20, k_WFH 10 again** (6 feasible points of 405; the feasible point nearest
   the anchors; neither on an edge). R-daily, mean of seeds 1-3: base car 0.843, PT 0.154, WFH
   0.001, SKIP 0.003, days 11-13 -25.2%, days 21-30 -16.0%. Per seed: base car 0.866 / 0.844 /
   0.819, PT 0.131 / 0.155 / 0.175, SKIP 0.001 / 0.001 / 0.006, days 11-13 -23.8 / -28.0 / -23.8%,
   days 21-30 -15.2 / -17.8 / -15.0%.
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
4. **Routes.** Home -> outside end of the prep gate segment -> gate point (the shortest free-flow
   path, a prefix of the prep path to the destination node), then gate point -> inside end ->
   building node -> the building point [A]. Origins whose path touches the cordon more than once
   (README, "Simplified network") cross at their first-entry gate. The leg after the gate is
   routed with 60 minutes added to every road with an end outside the cordon [A], because on the
   plain shortest path about two thirds of these legs left the cordon and re-entered it (a second
   crossing without a queue or a charge). On roads it still leaves where the cordon's own roads
   do not connect (they fall into 15 pieces; buildings attach to the largest, 1,066 of 1,106
   nodes): from the Wellesley Street ramp gate for about 100 to 160 m and from Hopetoun Street for
   about 180 m (90 of the 300 seed-1 legs). The car parks at the cordon node nearest its
   building (in the largest connected set of cordon roads; median 65 m from the building, up to
   about 780 m for buildings on the wharves, which the major-road network does not reach) and the
   commuter is drawn at the building on arrival [A]: an earlier version drove the last stretch in
   a straight line, across the water in front of the wharves. The network keeps the giant
   component only (28,507 nodes), the graph prep routes on.
5. **Workplaces.** Uniform over the 1,484 building points (LINZ outlines clipped to the SA3; one
   `point_on_surface` per footprint), not weighted by floor area or use, with replacement, fixed
   seed 2027 [A, author: "randomly one of the buildings", the same building every day].
6. **Drawing.** Queued cars are red and stand on the approach road about 220 m apart: one agent
   stands for agents_represented / agents (about 63) cars, at 7 m per car in 2 lanes [A], so the
   queue on the map is as long as the real one (a first version drew them 15 m apart, which hid the
   queues). PT riders are hidden while travelling. WFH and SKIP stay at home.
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
