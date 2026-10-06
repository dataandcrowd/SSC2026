# Cordon-Lite

A deliberately simple commuter simulation for the CUPUM 2027 book chapter "LLM agents in traffic
behaviour modelling: a 'cognitive clock' for drivers in congestion" (Hyesop Shin and Milad
Malekzadeh).

## Purpose

Cordon-Lite asks where an LLM should sit in a traffic agent-based model. Commuters normally follow
a standing plan (habit). A "cognitive clock" wakes a decider only when something meaningful happens.
The decider is either a rule (random-utility choice over a generalised cost) or an LLM. The model
compares the two on:

- the aggregate response at the cordon;
- who adapts;
- interpretability (every decision carries a logged reason);
- call volume (how many decisions need the decider at all).

Scope: the Auckland city-centre cordon (SA3 "Auckland City Centre"), AM peak only, about 300
commuters, 30 repeated weekdays. A time-of-use (ToU) charge starts on day 11 and a PT disruption
hits one corridor on day 20.

## Design

### City-wide demand, gate-bottleneck simulation

The TomTom major-road network (46,965 segments, about 28.5k nodes) is used **offline** in Python
(`prep/build_inputs.py`). For 3,000 city-wide origins it finds:

- the shortest free-flow path into the cordon;
- the gate where that path first enters the cordon;
- the free-flow minutes to the gate and from the gate to the destination.

The 27 gates used are grouped into 5 corridors by entry bearing. During the simulation **only the
corridors are congested**, as Vickrey point queues at minute resolution.

Why not simulate the full network?

- The cordon test only needs to know whether and when a car enters the cordon, and each path's
  gate is known exactly. Expanding the network to the whole city therefore maximises OD coverage at
  no simulation cost.
- Simulating 47k links would add network dynamics (spillback, route choice, signal effects) that
  could create or hide differences between rule and LLM deciders. With gate bottlenecks, any
  difference between arms comes from the deciders, not from the network.
- A point queue has a known analytical benchmark (Vickrey 1969; Arnott, de Palma and Lindsey), used
  as a sanity check (`cordonlite/vickrey.py`).

The engine exists twice with identical semantics: `PyEngine` (Python reference) and `NetLogoEngine`
(NetLogo 7.0.4 through pynetlogo, model `netlogo7/cordon_lite.nlogox`, which is also the GUI that
replays a run on the road network). Python handles every
decision and the PT, WFH and SKIP outcomes. The engine handles only cars. The two engines give
identical run outputs apart from the engine label.

### Persona layers

- **Layer A, constraints** (random stream "A"): origin (weighted city-wide sample, which fixes
  the corridor and free-flow times), value of time (lognormal, as in SSC2026), archetype (hybrid
  office, on-site office, shift/service, trades/work vehicle, tertiary student) conditioned on the
  VoT quintile, work start t*, company car, parking cost, PT and WFH feasibility, and whether the
  employer allows an earlier working day (07:00 to 15:00; drawn last, so no other field depends on it).
- **Layer B, dispositions** (independent stream "B"): habit H, schedule flexibility F, PT openness
  P and cost salience S, each on a 5-level scale (v3 design note). Rules map them to cost
  parameters. The LLM receives them as fixed sentences. The last 30 agents are "twins": they copy
  the Layer A of agents 0-29 and keep their own Layer B.
- **Layer C, memory**: one record per day; the last 5 days are shown in the prompt. EMAs track the
  experienced versus forecast queue delay and the reference fee.

Options per agent and day: car departures at the standing time plus or minus 0-60 min (15-min
grid, 06:00-09:45), PT (services every 10 min; the rider takes the latest one arriving by the
start time), WFH (hybrid workers only) and SKIP (a one-day postponement that costs NZ$30 plus one
hour of the value of time [A, author decision 2026-10-05]).

**Starting work earlier** (2026-10-05). A commuter whose employer allows it (probability 0.8 for
hybrid office, 0.5 on-site office, 0 shift/service, 0.5 trades, 0 students [A]) can work 07:00 to
15:00 on any day instead of the usual hours. This is a real option, not arriving early and waiting:
every car and PT option of such a commuter is measured against the cheaper of two starts, the usual
start t* or 07:00 plus an inconvenience cost of NZ$3 x phi(F) a day [A]. The car departures that
reach each start (reference departure plus or minus 15 min) are added to the standing set, so a
commuter with t* = 08:30 can leave at 06:15 or 06:30 for a 07:00 start. Early and late minutes,
the lateness trigger T3 and the stored outcome all use the start the chosen option implies
(`start_used_min`, `early_shift` in `decisions.csv` and `outcomes.csv`). The LLM prompt states the
permission in plain words and shows the start time of every option. The rules and MockLLM use the generalised cost (time, schedule delay with Small
1982 ratios, fee with a loss term on the part above a reference fee that follows the fee faced,
parking, fuel, PT with an attitude penalty, WFH without a commute, parking or fuel credit, SKIP,
habit). Two money costs of driving are fixed inputs and are never calibrated. Paid parking is NZ$17 a
day for office archetypes (student NZ$12.75, trades and company vehicles 0) [author decision;
consistent with the AT 2014 Victoria St daily rate already noted in config comments]. Fuel is 2 x
path length x NZ$0.30/km (round trip; 0 for employer vehicles): petrol NZ$3.30/L [author-supplied,
Oct 2026] x 9.0 L/100 km (real-world light petrol vehicles, Metcalfe and Sridhar 2016 for the
Ministry of Transport; sources in `config.toml`), about NZ$8.6 a day for a driver who pays it. The
petrol price was supplied by the authors and has not been verified here against a published series.
The real LLM sees the same options with
their attributes, including the daily parking and fuel costs, but never the generalised cost. Rule noise uses common
random numbers, so twins in the same state draw the same noise.

### Behaviour calibration

The rule decider is calibrated on the R-daily arm (seeds 1-3) to stated targets: before the charge
car 0.75-0.85, PT 0.08-0.15, WFH at most 0.10, SKIP at most 0.02; car cordon crossings on days
21-30 12-22% below days 6-10 (Stockholm about -20%, Gothenburg about -12%; Börjesson et al. 2012,
Börjesson and Kristoffersson 2015), with an overshoot on days 11-13 of about -30% at most. These
anchors are total cordon traffic in charged hours, observed over months to years; the band applies
to AM car commuters over days, so the comparison is qualitative (v3 10.5), and a private-car
commuter response is likely larger. Four structural fixes come first (reference fee follows the fee
faced, capped loss weight eta, WFH priced as in v3, no habit discontinuity at a price change), and
paid parking and fuel are fixed inputs. Two scalars are then searched on a grid in NZ$1 steps, with
capacity recalibrated at every point: the PT attitude penalty (PAP, searched 10-36, chosen 20; in
the specification form omega(P) x (VoT/60 x T_pt + PAP), so omega also scales PT time and there is
no v3 HTA/2 factor; not comparable with v3's NZ$8) and k_WFH (searched 2-16, chosen 10). Neither
chosen value is on an edge of its range. The SKIP cost, the early start time, its cost and the
permission probabilities are fixed assumptions and are never searched.

**Result (2026-10-05, after the SKIP cost was raised to NZ$30 and the early start was added).** The
same search (targets, seeds, loss, rule, grid) gives 6 feasible points of 405, and the rule picks
the one nearest the anchors: PAP 20 / k_WFH 10, the values already in use. R-daily, mean of seeds
1-3: base car 0.843, PT 0.154, WFH 0.001, SKIP 0.003, response -16.0% (days 21-30), overshoot
-25.2% (days 11-13). Every target is met at the precision the targets are stated in, and every
seed is within the stated single-seed tolerance. What is not met exactly: the unrounded mean PT
share is 0.154 (0.0036 above 0.15; 0.15 at two decimals), and three single-seed values are outside
their band but inside the tolerance (base car 0.866 on seed 1; base PT 0.155 and 0.175 on seeds 2
and 3). Held-out seeds 4 and 5 respond by -15.4% and -18.1%, unseen seeds 6-12 by -15.0% on
average (-12.0% to -18.3%), with base car 0.840, PT 0.154 and SKIP 0.004; no seed is outside the
tolerance. The targets were not relaxed. The response is in the weaker half of the band (centre
-20%); the lowest-loss point (PAP 21 / k_WFH 8, -19.2%) is also feasible but further from the
anchors.

**What the two changes did.** Postponing is rare again: SKIP is 0.003 of commuters before the
charge and 0.010 on days 21-30 (0.020 and 0.047 before the change). Sensitivity runs show this is
the SKIP cost, not the early start: without the early-start option SKIP is the same, and with the
SKIP cost back at NZ$25 it returns to 0.022 and 0.047. About 47% of commuters may start early, and
6.1% of all commuters do so on days 6-10, mainly to avoid the queue (peak delay about 15 min).
Under the charge the share does not rise: 6.4% on days 11-13 and 4.2% on days 21-30 (6.1% without
the charge), because the queues almost vanish and the remaining saving (about NZ$2 of charge) is
below the assumed NZ$3 x phi(F). With that cost at NZ$1.5 the share rises under the charge (10.0%
to 11.5%), so the result depends on an assumption. Car crossings in the 08:00-09:00 peak fall by
18.6% against 16.0% for the whole morning (seeds 1-3: 13.7 / 16.8 / 25.4% against 15.2 / 17.8 /
15.0%), and by 23.9% against 15.6% over seeds 1-12: some peak spreading, uneven across seeds.

**History.** Before fuel was a separate cost, three scalars were searched and the search chose PAP
11 and parking NZ$17. With fuel fixed at NZ$0.23/km (September 2025 petrol price) it chose PAP 12
and parking NZ$11, both PAP values on the edge of the range 4-12. On 2026-10-03 the authors fixed
parking at NZ$17 and fuel at NZ$0.30/km, and parking left the search; that search chose PAP 20 /
k_WFH 10 with no feasible point, because the SKIP share of two seeds (0.025) exceeded 0.02. On
2026-10-05 the authors raised the SKIP cost to NZ$30 and added the early start. The LLM deciders
are never tuned, but the shared Layer A inputs (paid parking, fuel, early-start permission) appear
in the LLM prompt. Results, out-of-sample seeds 4-12, the sensitivity to the fixed assumptions,
figures and the trait checks are in `docs/calibration_report.md`; the search log is
`data/behaviour_calibration.json`. Earlier logs and reports are kept as
`data/behaviour_calibration_pre_fuel.json` with `docs/calibration_report_pre_fuel.md` (no fuel),
`data/behaviour_calibration_fuel023_park11.json` with `docs/calibration_report_fuel023_park11.md`
(fuel NZ$0.23/km, parking searched) and `data/behaviour_calibration_skip25_noearly.json` with
`docs/calibration_report_skip25_noearly.md` (SKIP cost NZ$25, no early start).

### Cognitive clock

The clock is edge-triggered: each event wakes an agent once.

| Trigger | Wakes the agent when |
|---|---|
| T1 | it is the first day (no standing plan) |
| T2 | the charge starts or changes |
| T3 | it was late yesterday beyond a tolerance that depends on F (per late day, so a chronically late agent wakes on consecutive days) |
| T4 | PT was disrupted yesterday, or a disruption is announced on its corridor while it is a PT user; and once more on the day after an announced disruption that woke it, when service is back |
| T5 | its car time differed from expectation by more than 20% on 2 consecutive car days |
| T6 | its standing option is infeasible today; a standing SKIP always counts as infeasible (skipping is a one-day postponement) |

On any other day the agent repeats its standing option.

### Arms

| Arm | Decider | When |
|---|---|---|
| `R-daily` | rule | every agent, every day |
| `R-clock` | rule | only on triggers |
| `L-clock` | LLM | only on triggers |
| `L-daily` | LLM | every agent, every day (upper bound on calls) |

`--traits off` sets every disposition to level 3 for both deciders: the rule uses level-3
parameters and the LLM sees the four level-3 sentences (information ladder).

## Setup

- Python 3.12 and a virtual environment in this folder:
  `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
- NetLogo 7.0.4, only for the NetLogo engine and GUI. The default location is
  `/Applications/NetLogo 7.0.4` (`[engine] netlogo_home` in `config.toml`). If NetLogo is not
  there, a NetLogo run stops with a one-line message naming that key. NetLogo runs print a few JVM
  `WARNING: ... restricted method` / `sun.misc.Unsafe` lines; they are harmless.
- Input data, read only by the prep step and kept outside this folder (`[prep]` in
  `config.toml`): `../netlogo/Data/roads/tomtom_major_roads.gpkg` (TomTom major roads) and
  `../netlogo/Data/roads/akl_CBD_SA3.gpkg` (SA3 polygons), and for step 1b the LINZ building
  outlines in `../netlogo/Data/building_api/`. That folder was removed from this repository on
  2026-10-06: restore it from git history (commit d22e3cf) to re-run steps 1 and 1b. The prep
  outputs in `data/` and `netlogo7/gis/` are included, so everything from step 2 on and the
  NetLogo GUI run without them.
- The NetLogo model's GUI (below) reads its map layers from `netlogo7/gis/`: the TomTom roads as a
  shapefile, the cordon and the city-centre buildings, written by step 1b from the GeoPackage, the
  SA3 polygons and the LINZ building outlines. These are already included, so the GUI runs
  without the prep inputs.
- An Anthropic credential only for `--backend anthropic` (see below).

## How to run

Run every command from this folder with the project interpreter.

```bash
PY=.venv/bin/python

# 1. Prep: TomTom network -> data/origins.csv, gates.csv, corridors.csv, cordon.geojson, prep_map.png
$PY -m prep.build_inputs            # optional --out-dir FOLDER; uses prep.seed = 11 (separate from run.seed), so it reproduces data/ byte for byte

# 1b. NetLogo map layers (for the GUI of netlogo7/cordon_lite.nlogox; no Cordon-Lite run reads them):
#     netlogo7/gis/tomtom_major_roads.shp (the TomTom gpkg as a shapefile, same segments and
#     attributes), cordon.shp, cbd_buildings.shp (footprints inside the cordon), cbd_buildings.csv
$PY -m prep.build_netlogo_layers    # optional --out-dir, --roads-out, --buildings

# 2. Calibrate corridor capacity (R-daily, no charge, days 6-10) -> data/calibration.json
#    Target: car-weighted mean over corridors of the peak 15-min mean queue delay = 15 min
#    (engine.calib_metric). Individual corridors sit above and below the target. --seeds stores
#    one record per seed (by_seed); each run uses the record of its own seed.
$PY -m cordonlite.run calibrate --seeds 1 2 3 --n-agents 300   # optional --output FILE --target MIN

# 2b. (Optional, about 30 min on 13 cores) behaviour calibration of the rule decider; rerun step 2
#     afterwards if it changes the values in config.toml
$PY scripts/calibrate_behaviour.py      # -> data/behaviour_calibration.json, docs/calibration_report.md
#     (stages search, select, final, oos = out-of-sample seeds 4-12, neighbouring points and sensitivities to the
#      fixed assumptions (never adopted), report; gap = optional local re-search, not part of the default;
#      --stage report rebuilds the report from the JSON log without new runs)

# 3. Run the arms (mock backend = deterministic stand-in, not an LLM)
for ARM in R-daily R-clock L-clock L-daily; do
  $PY -m cordonlite.run --arm $ARM --backend mock --engine py --n-agents 300 --days 30 --seed 1
done
$PY -m cordonlite.run --arm R-clock --backend mock --engine netlogo --n-agents 300 --days 30 --seed 1
$PY -m cordonlite.run --arm R-clock --backend mock --engine py --n-agents 300 --days 30 --seed 1 --traits off
$PY -m cordonlite.run --arm L-clock --backend mock --engine py --n-agents 300 --days 30 --seed 1 --traits off
for SEED in 2 3; do   # seed robustness of the rule arms (calibrated capacity records exist for seeds 1-3)
  for ARM in R-daily R-clock; do
    $PY -m cordonlite.run --arm $ARM --backend mock --engine py --n-agents 300 --days 30 --seed $SEED
  done
done

# 4. Estimate LLM calls and input tokens (MockLLM run; approximate) -> runs/estimates/
$PY -m cordonlite.run --arm L-clock --n-agents 300 --days 30 --seed 1 --estimate
$PY -m cordonlite.run --arm L-daily --n-agents 300 --days 30 --seed 1 --estimate

# 5. Figures and tables -> runs/figures/ (canonical runs of one seed; see below)
$PY -m cordonlite.analysis
$PY -m cordonlite.analysis --compare runs/R-clock_mock_py_s1 runs/R-clock_mock_netlogo_s1

# 6. Tests: non-NetLogo tests, then the NetLogo tests in their own process
$PY -m pytest -q
$PY -m pytest -q --run-netlogo tests/test_engine_netlogo.py tests/test_run_netlogo.py
```

Other useful options:

- `--fee-start K` and `--regime tou|flat|none` change the charge; `--capacity-scale X`
  overrides the calibration; `--set key=value` sets any config key (the value is parsed as JSON
  and must match the key's type), for example `--set costs.pt_attitude_penalty=8` or `--set costs.fuel_cost_per_km=0.27`, or the T7 review sensitivity `--set clock.review_every_days=5 --name R-clock_mock_py_s1_review5`. An explicit
  flag wins over `--set` for the same key (with a warning).
- Run folders: `runs/<arm>_<backend>_<engine>_s<seed>[_traitsoff]`, plus one suffix for every
  setting that differs from `config.toml` (`_n<N>`, `_d<D>`, `_<regime>`, `_fs<K>`, `_cs<X>`,
  `_set-<hash>`). Variant runs therefore never overwrite the canonical runs. A run is written to a
  temporary folder and moved into place only when it finishes; a failed run leaves
  `<name>.failed`. `--name DIR` and `--out FOLDER` choose the folder explicitly.
- A run whose seed or number of agents has no record in `data/calibration.json` prints a warning:
  recalibrate for that setting (seeds 1-3 with 300 agents are calibrated).
- Analysis: by default only canonical runs (no variant suffix) of the seed with the most runs are
  used. `--seed S` picks the seed, `--all` adds variant runs (labelled with their suffix),
  `--run-dirs DIR ...` takes an explicit list, `--include-netlogo` adds the NetLogo run.

### NetLogo model

`netlogo7/cordon_lite.nlogox` (NetLogo 7.0.4) is one model with two uses. Python drives it headless
as NetLogoEngine (`--engine netlogo`: `setup-from-dir`, `set-clock`, `run-day`, which load no map).
Opened in NetLogo, it replays a run with every car driving on the TomTom road network.

1. Set `scenario-dir` to a run folder (default `../runs/R-clock_mock_py_s1`) and press `setup`
   (about 40 s).
2. Press `go`: one morning plays until every commuter has arrived at work, and `go` stops.
3. To run day after day, switch `keep-going?` on before pressing `go`.
4. `skip to end of day` jumps to the end of the morning; `Auckland view` and `City-centre view`
   switch the map (the City-centre view shows the gate queues best). One tick is 15 simulated
   seconds; the NetLogo speed slider sets the pace.

- **Network.** The TomTom shapefile is built into nodes and links as the prep graph is (segment
  ends rounded to 1 m, coinciding ends dropped, the fastest of parallel segments kept), and only
  the giant component is kept, as prep routes on it: 28,507 nodes, 30,835 links and 1,106 nodes
  inside the cordon, as in `data/prep_report.md`. The link weight is free-flow minutes.
- **Homes, gates, workplaces.** Commuters start at their Cordon-Lite origins. Each car's gate is
  the prep gate of its origin (`data/origins.csv`): it drives the free-flow shortest path to the
  outside end of the gate segment, crosses the cordon at the gate point (`data/gates.csv`) and
  drives on to its workplace, a building inside the cordon (one point inside each of the 1,484
  LINZ footprints). The workplace is drawn uniformly at random once per commuter (fixed seed,
  agent_id order) and kept for every day. After its gate a car stays inside the cordon: that
  leg is routed with 60 minutes added to every road with an end outside the cordon (on plain
  free-flow minutes about two thirds of these legs would leave and re-enter it). It still leaves
  where the cordon's own roads do not connect: from the Wellesley Street ramp gate for about 100 to
  160 m and from Hopetoun Street for about 180 m (90 of the 300 seed-1 legs). The car parks at the
  cordon node nearest its building (median 65 m away, up to about 780 m for buildings on the
  wharves, which the major roads do not reach) and the commuter is drawn at the building.
- **Clock.** The minutes are the engine's. Gate arrival = departure + free-flow minutes to the gate;
  the gate exit comes from the procedure `point-queues`, the Vickrey point queue per corridor that
  `run-day` also uses (the same as PyEngine); arrival = gate exit + free-flow minutes from the gate.
  Between those minutes a car moves along its route at constant speed, drawn every 15 simulated
  seconds. A day lasts until the last commuter has arrived. Cars waiting in a gate queue are red and
  are drawn back along the approach road: each agent stands for about 63 cars
  (`agents_represented` / agents) and takes up about 220 m (7 m per car, 2 lanes), so a queue on
  the map is as long as the real queue it stands for; in the City-centre view each corridor label
  shows how many cars are waiting. The workplace sets where a car parks, not when it arrives: the
  engine's gate-to-destination minutes refer to the single prep destination. In the canonical
  R-clock run the implied speeds are a median of 76 km/h to the gate (5-95%: 50-94) and 40 km/h
  from the gate to the parking node (5-95%: 13-72; a few short engine legs give up to about
  95 km/h). PT riders vanish while travelling and appear at their building at the run's PT arrival
  minute; WFH and SKIP stay at home. Replaying a run in the GUI writes nothing.
- **Demo.** `netlogo7/demo_scenario` is synthetic: its homes are not prep origins and some lie
  kilometres from any road, so its cars start with a straight line (setup prints how many) and
  its speeds mean nothing. Without a plans file every commuter drives, leaving 06:45 to 08:00.
- **Checks.** `scripts/check_netlogo_equivalence.py` compares NetLogoEngine with PyEngine (and
  exercises the GUI). `$PY scripts/check_network_model.py [--days 1 11] [--views DIR]` (own
  process, `--netlogo-home` overrides `[engine] netlogo_home`) checks the network counts, every gate
  and workplace, how far the legs from the gate run outside the cordon, that every car's depart,
  gate-arrive, gate-exit and arrive minute equals the run's `outcomes.csv`, the tick clock, where
  queued and driving cars stand during the animation and every commuter's place at the end of the
  day, and reports the implied speeds; `tests/test_network_model_netlogo.py` runs it under
  `--run-netlogo` (`CORDONLITE_NETLOGO_HOME` overrides the NetLogo folder).

### Running with the real Claude API

The live API has not been called from this machine. Before a full run:

1. Provide a credential: `export ANTHROPIC_API_KEY=...` (never written to a file) or `ant auth
   login`. Without one, the run stops before day 1 with a one-line message.
2. Choose a model and budget. The default model is `claude-opus-5-5` (`[llm] model`);
   `claude-sonnet-5-5` and `claude-haiku-4-5` are allowed. Model choice and cost are the authors'
   decision; run `--estimate` first. Cost all input as uncached: the system prompt is below the
   minimum cacheable prefix and the output schema differs per agent.
3. Start small, for example
   `$PY -m cordonlite.run --arm L-clock --backend anthropic --n-agents 20 --days 12 --seed 1`,
   and read `llm_calls.jsonl` and `decisions.csv` before scaling up.

Behaviour of the anthropic backend:

- Transport errors (429, 5xx, connection) are retried by the SDK (`max_retries = 5`). An invalid
  output (unparsable or truncated JSON, a choice that was not offered) is resent once. A refusal
  or another API error goes straight to the rule (`decider = llm-fallback-rule`).
- 401, 402, 403 or 404 errors, or 5 API errors in a row (`llm.max_consecutive_errors`), stop the
  run. Every call is logged as soon as it completes, so a stopped run keeps its log in
  `<name>.failed/llm_calls.jsonl`. `summary.json` reports `llm_fallback_share`.
- Responses are cached on disk (`runs/llm_cache/`), keyed on model, effort, template, prompts,
  schema, `max_tokens` and the fallback setting. A rerun replays the same answers. Agents with
  byte-identical prompts on the same morning are sent once and share the answer (v3 7.5), also
  across arms (L-clock and L-daily share day 1). Set `--set llm.replicate=1` (2, ...) to draw fresh
  samples.

## Outputs

Each run writes `runs/<run folder>/`:

| File | Content |
|---|---|
| `config_snapshot.toml` | effective configuration |
| `personas.csv` | Layer A and B fields per agent |
| `decisions.csv` | agent, day, option, mode, departure, decider, triggers, reason, factors, GC of the choice and its GC rank, start time used and early-start flag |
| `outcomes.csv` | every agent-day, including PT/WFH/SKIP: times, queue delay, early/late against the start used, fee, parking, fuel, fare, start time used and early-start flag |
| `profile.csv` | arrivals, served cars and queue length per corridor per minute |
| `llm_calls.jsonl` | every LLM call: prompt, parsed output, error kind, usage, cache hit, shared answer, latency |
| `summary.json` | per day: mode counts, commuters on the early start, cordon entries per 15 min, mean/max delay, peak delay (car-weighted mean of corridors and worst corridor), mean fee, revenue, calls by decider type |
| `corridors.csv`, `agents.csv`, `fees.csv`, `plans_dayNN.csv`, `scenario.csv` | engine scenario and plans (also used by the NetLogo GUI) |

`python -m cordonlite.analysis` writes to `runs/figures/`: `mode_shares.png`,
`crossings_hist.png` (gate exits, day 10 vs day 30), `cordon_entries.png` (with the ToU
schedule), `queue_delay.png`, `calls_per_day.png`, `who_adapts.png` (with 95% intervals),
`vickrey_check.png`, `summary_table.csv/.md`, `twins_summary.csv/.md` (with the traits-off
baseline), `llm_diagnostics.csv/.md` (v3 7.5), and per run `who_adapts_*.csv` and
`twins_day11_*.csv`.

Both engines give identical outputs apart from the engine label in `config_snapshot.toml` and
`summary.json` (`--compare` checks this and the file set).

### Results of the canonical mock runs (300 agents; seed 1 unless stated)

"L" arms use MockLLM, a deterministic stand-in, so these rows test the pipeline; they say nothing
about how a real LLM behaves. Shares are day 10 -> day 30. The crossing change compares the mean
daily car cordon crossings of days 21-30 with days 6-10 (the calibrated response). Peak delay is
the car-weighted mean of corridor peaks (the calibrated capacity metric).

| Arm | Car d10 -> d30 | PT d10 -> d30 | WFH d10 -> d30 | SKIP d10 -> d30 | Early start d6-10 -> d21-30 | Car crossings change d21-30 vs d6-10 | Peak delay d10 -> d30 (min) | Revenue NZ$ d30 / total | Decider calls |
|---|---|---|---|---|---|---|---|---|---|
| R-daily | 0.843 -> 0.743 | 0.143 -> 0.223 | 0.010 -> 0.033 | 0.003 -> 0.000 | 0.071 -> 0.037 | -15.2% | 16.8 -> 3.5 | 1,123 / 21,454 | 9,000 |
| R-clock | 0.877 -> 0.707 | 0.123 -> 0.223 | 0.000 -> 0.070 | 0.000 -> 0.000 | 0.073 -> 0.053 | -19.5% | 10.8 -> 3.1 | 1,060 / 21,133 | 835 |
| L-clock (mock) | 0.807 -> 0.527 | 0.193 -> 0.343 | 0.000 -> 0.127 | 0.000 -> 0.003 | 0.055 -> 0.053 | -34.7% | 9.8 -> 4.3 | 752 / 14,780 | 907 |
| L-daily (mock) | 0.810 -> 0.563 | 0.183 -> 0.327 | 0.007 -> 0.083 | 0.000 -> 0.027 | 0.058 -> 0.033 | -29.1% | 15.6 -> 4.0 | 841 / 16,312 | 9,000 |
| R-clock, traits off | 0.927 -> 0.667 | 0.073 -> 0.277 | 0.000 -> 0.057 | 0.000 -> 0.000 | 0.071 -> 0.080 | -28.3% | 12.4 -> 5.2 | 954 / 18,944 | 930 |
| L-clock (mock), traits off | 0.817 -> 0.437 | 0.183 -> 0.397 | 0.000 -> 0.167 | 0.000 -> 0.000 | 0.054 -> 0.043 | -46.7% | 10.7 -> 2.8 | 607 / 12,013 | 844 |
| R-daily, seed 2 | 0.850 -> 0.697 | 0.147 -> 0.250 | 0.000 -> 0.043 | 0.003 -> 0.010 | 0.064 -> 0.035 | -17.8% | 11.8 -> 3.5 | 1,040 / 19,713 | 9,000 |
| R-clock, seed 2 | 0.840 -> 0.653 | 0.160 -> 0.263 | 0.000 -> 0.083 | 0.000 -> 0.000 | 0.087 -> 0.061 | -22.5% | 13.7 -> 5.7 | 935 / 18,265 | 944 |
| R-daily, seed 3 | 0.820 -> 0.697 | 0.173 -> 0.247 | 0.000 -> 0.037 | 0.007 -> 0.020 | 0.049 -> 0.054 | -15.0% | 17.2 -> 2.5 | 1,027 / 19,659 | 9,000 |
| R-clock, seed 3 | 0.833 -> 0.660 | 0.163 -> 0.270 | 0.000 -> 0.053 | 0.003 -> 0.017 | 0.063 -> 0.050 | -20.8% | 11.6 -> 4.2 | 970 / 19,260 | 954 |

Rows without a seed are seed 1. "Early start" is the share of all commuters whose day is measured
against the 07:00 start, mean of days 6-10 -> mean of days 21-30 (single days are noisy: R-daily
seed 1 has 0.080 on day 10 and 0.030 on day 30). The NetLogo R-clock run (seed 1) is identical to
the PyEngine run (`--compare`: same file set, identical outcomes, 9,000 rows of which 6,866 car
rows). Single days are noisy; the calibrated quantities are means over days. In R-daily, the only
calibrated arm, the response is in band on all three seeds (-15.2%, -17.8%, -15.0%; mean -16.0%).
The overshoot on days 11-13 is -23.8%, -28.0%, -23.8% (mean -25.2%), inside the soft bound of
about -30%. The baseline shares are within the stated single-seed tolerance (seed 1 base car 0.866;
seeds 2-3 base PT 0.155, 0.175). On unseen seeds 6-12 the mean response is -15.0%, with single
seeds between -12.0% and -18.3%, base PT 0.154 and base SKIP 0.004 (calibration report). The clock
arms keep more of the day-11 response than R-daily (-19.5% to -22.5% against -15.0% to -17.8%).
With few postponed trips the event-only clock is quiet after day 12: 12, 49 and 123 decisions on
seeds 1-3 outside the disruption days (commuters who postponed the day before, late arrivals and
sustained changes in car time). The uncalibrated MockLLM arms respond much more strongly (-29% to
-35%; MockLLM weights the fee 1.5 times), which says nothing about a real LLM. Traits off
strengthens the response in both deciders (R-clock -28.3% against -19.5%). Postponed trips are 0-2%
of commuters on day 30 in the rule arms (0-1% on day 10). The early start is used by 5-9% of
commuters before the charge and by 3-6% after it in the rule arms: it mainly avoids the queue, and
the queue almost disappears once the charge removes about a sixth of the cars (peak delay about
3-6 min against the calibrated 15 min before the charge on days 6-10). Estimated LLM input (MockLLM
run, characters / 4, approximate): L-clock 907 calls, about 1.0M tokens; L-daily 9,000 calls, about
10.6M tokens (prompts are longer: an extra `start time` column and more car departures for
commuters who may start early). Earlier runs are kept in `runs_skip25_noearly/` (SKIP cost NZ$25,
no early start), `runs_fuel023_park11/` (fuel NZ$0.23/km, parking NZ$11, PAP 12), `runs_pre_fuel/`
(before the fuel cost) and `runs_pre_recalibration/`.

**Periodic review (T7) sensitivity**, rule decider, car crossings against days 6-10 and decisions
with `decider != "standing"` (`runs/R-clock_mock_py_s<seed>_review<N>`):

| Seed | Arm | d21-30 | d11-13 | Decisions |
|---|---|---|---|---|
| 1 | R-daily | -15.2% | -23.8% | 9,000 |
| 1 | R-clock (event only) | -19.5% | -21.2% | 835 |
| 1 | review every 10 days | -14.1% | -21.2% | 1,112 |
| 1 | review every 5 days | -13.7% | -19.4% | 2,004 |
| 2 | R-daily | -17.8% | -28.0% | 9,000 |
| 2 | R-clock (event only) | -22.5% | -27.0% | 944 |
| 2 | review every 10 days | -18.8% | -27.0% | 1,204 |
| 2 | review every 5 days | -19.0% | -27.0% | 2,098 |
| 3 | R-daily | -15.0% | -23.8% | 9,000 |
| 3 | R-clock (event only) | -20.8% | -22.1% | 954 |
| 3 | review every 10 days | -18.9% | -22.1% | 1,224 |
| 3 | review every 5 days | -17.7% | -21.6% | 2,138 |

Twins (30 pairs that share Layer A, seed 1, `twins_summary.md`): the number of pairs choosing a
different option on day 11 (day 30) is 14 (11) in R-daily, 17 (16) in R-clock, 16 (15) in L-clock
(mock) and 13 (11) in L-daily (mock). With traits off, which leaves only history to separate the
twins, it falls to 3 (3) in R-clock and 4 (5) in L-clock (mock).

## Further reading

- `docs/example_prompt.md`: one complete request as the LLM sees it (made by
  `scripts/make_example_prompt.py` from a logged call).
- `INTERFACES.md`: module contracts. `DEVIATIONS.md`: every departure from the specification and
  the v3 note, including the final review fixes. `data/prep_report.md`: network assumptions.
- `scripts/check_netlogo_equivalence.py`: PyEngine vs NetLogoEngine on random plans.

## Assumptions

Every parameter is in `config.toml`, with a comment marking it as an assumption `[A]`, as
calibrated `[CAL target=...]` (by `scripts/calibrate_behaviour.py`, to the stated target; two
scalars, PAP and k_WFH), as a fixed input decided by the authors (paid parking, petrol price, SKIP
cost, early start), or naming
its source (`[SPEC]`, `[v3]`, `[SSC]`, or `[L]` with a literature reference). Every departure from the
specification or from the v3 design note is listed in `DEVIATIONS.md`. `data/prep_report.md`
lists the network assumptions. `INTERFACES.md` documents the module contracts.

## Limitations

- **Behaviour calibration is to stated targets, on the rule arm only.** The R-daily response
  (-16.0%, mean of seeds 1-3; -15.0% on unseen seeds 6-12) lies in the target band, in its weaker
  half, but the targets are assumptions and the Stockholm/Gothenburg anchors are total-traffic
  reductions over months to years, so the match is qualitative. The chosen point (PAP 20, k_WFH 10)
  is feasible at the stated precision only: the unrounded mean PT share is 0.154, and base car on
  seed 1 (0.866) and base PT on seeds 2 and 3 (0.155, 0.175) are outside their bands but within the
  single-seed tolerance.
- **The early start is an assumption, and the charge does not increase its use.** The permission
  probabilities (0.8, 0.5, 0, 0.5, 0), the 07:00 start and the cost of NZ$3 x phi(F) have no
  empirical source. In R-daily 6.1% of commuters start early before the charge and 4.2% on days
  21-30: the option mainly avoids the queue, which the charge removes. At NZ$1.5 x phi(F) the share
  rises under the charge (10.0% to 11.5%); at NZ$6 it is almost unused. The LLM is told the
  permission but not this cost. It does not replace postponing in the rule: the fall in SKIP
  (0.020 to 0.003 before the charge, 0.047 to 0.010 after) comes from the SKIP cost of NZ$30
  (`docs/calibration_report.md`, "Sensitivity to the fixed assumptions").
- **PAP is a fitted residual.** With parking and fuel fixed, PAP alone holds the assumed baseline
  split and stays at 20 (v3 PAP 20-40 in v3's form). Commuters with P = 1-2 never ride PT. k_WFH 10
  is identified by the response and overshoot, not by the WFH share (about 0.00 before the
  charge); a realistic hybrid-work WFH baseline would need v3's WFH quota (not implemented).
- **Fixed inputs are not validated.** The petrol price (NZ$3.30/L, October 2026) is author-supplied
  and was not verified here; the MBIE series gave NZ$2.97/L for September 2026 (NZ$0.27/km). The
  parking rate is a 2014 casual all-day rate. Base years are mixed (2026 fuel, 2025 fare and charge,
  2014 parking). Every driver without an employer vehicle pays petrol at 9.0 L/100 km; electric
  vehicles and other running costs are not represented. The SKIP cost (NZ$30 plus one hour of VoT)
  is an author assumption.
- **Rule and LLM see the same Layer A, but not the same WFH accounting.** The LLM deciders are not
  tuned, yet the parking cost and the fuel cost are stated in the prompt. The rule's
  WFH earns no parking, fuel or commute credit (v3 zero-fee form), whereas a real LLM told that
  parking costs NZ$17 and fuel about NZ$9 a day will likely count both as a WFH saving, so
  live-LLM WFH shares are not comparable with R-daily on that margin.
- **Lock-in under the clock.** The reference fee follows the fee faced, so the loss term fades
  for everyone, but under the clock only woken agents can act on it. Apart from the PT disruption
  few triggers fire after day 12 (12 to 123 decisions over seeds 1-3), so the clock arms keep more
  of the day-11 response (R-clock 0.877 -> 0.707 against R-daily 0.843 -> 0.743; -19.5% against
  -15.2%). A periodic review (T7, off by default) closes the gap: with a review every 10 days the
  response is -14.1%, -18.8%, -18.9% on seeds 1-3.
- **Trait effects follow the assumed mapping.** On population manipulations S acts monotonically
  (response -14% to -18% across S, overshoot -15% to -36%). The response also grows with F (-11% to
  -34%), but mainly because F = 4-5 hybrid workers switch to daily WFH, which is unbounded without
  v3's quota (WFH share about 0.20 at F = 5). With the early start the 08:00-09:00 share of
  crossings falls with F against the no-charge run (+0.05 at F = 1 to -0.15 at F = 5), but retiming
  of car keepers against the no-charge run stays small. H damps the day-11 overshoot only
  at level 5 and not the long-run response (habit re-forms on the new mode); the charge-induced PT
  switch is largest at P = 3 because P = 4-5 agents with viable PT already ride PT, and P = 1-2
  agents never do. Peak spreading is uneven: 08:00-09:00 crossings fall 18.6% against 16.0% for the
  whole morning on seeds 1-3 (23.9% against 15.6% over seeds 1-12), crossings before 07:30 fall
  11% and crossings after 09:30 rise by about a quarter; against the no-charge run the peak share
  falls only in seed 3, and in the paired check more drivers leave later (29%) than earlier (15%).
  For a single agent with paid parking and a 20 km path, of 625 trait combinations 250 already
  ride PT; without the early-start permission 276 keep the car, 93 switch to PT, 4 retime (H = 1)
  and 2 postpone on the charge morning; with the permission 260 keep, 93 switch to PT, 20 leave at
  06:30 for the 07:00 start and 2 postpone. The v3 worked example (identical A: pay / PT / retime)
  separates only with the v3 settings (PAP 8 x HTA/2 = 4, T2 a habit discontinuity) or with free
  parking (`tests/test_rules.py`). Treat trait patterns as properties of the mapping, not findings.
- **Capacity calibration.** It targets the car-weighted mean of corridor peaks per seed; corridor
  peaks range from 0 to about 33 min at the calibrated scales (seed 1: corridor 3 at 33 min).
- **Simplified network.** Free-flow times assume the speed limit (median 13 min); no one-way
  information; one destination node and one path per origin. With the first-entry gate rule,
  834 origins (28%; 97 of the 300 seed-1 agents, including all 89 South-corridor agents) first touch the cordon
  at the SH1 Wellesley Street off-ramp (723), The Strand or Parnell Rise, run outside for under
  1.2 min and re-enter at Alten Road. The first-entry rule assigns them to their first touch, so
  the South (Wellesley Street ramp) corridor, which is also the day-20 disruption corridor,
  includes these undirected-graph paths. The 834 origins of Alten Road gate 2 are single-entry
  paths from the south-east (the equal count is a coincidence). Free-flow times do not depend on
  the gate, and the fee minute moves by under 1 min (`data/prep_report.md`, DEVIATIONS.md Prep 4).
- **No congestion outside the cordon gates**, by design.
- **The mock backend is not an LLM.** It re-weights the same cost and adds prompt-seeded noise. It
  tests the plumbing, call counts and reproducibility.
- **Small sample.** 300 agents; every arm runs on seed 1, and the rule arms R-daily and R-clock
  also on seeds 2 and 3. The East corridor holds about 2% of agents.

## 한국어 요약

Cordon-Lite는 CUPUM 2027 북챕터를 위한 단순화된 통근 시뮬레이션입니다. 통근자는 평소 습관(standing plan)대로
움직이고, "인지 시계(cognitive clock)"가 의미 있는 사건(첫날, 혼잡통행료 도입, 지각, PT 장애와 그 종료, 지속적인
통행시간 변화, 계획 불가능)이 있을 때만 의사결정자(규칙 또는 LLM)를 깨웁니다.

- **네트워크:** TomTom 도로망은 Python에서 오프라인으로만 사용해 도시 전체 출발지 3,000곳의 최단경로, 코든 진입
  게이트, 자유통행시간을 계산합니다. 시뮬레이션에서는 5개 corridor만 Vickrey 점대기행렬로 혼잡을 계산합니다.
- **엔진:** Python(PyEngine)과 NetLogo 7.0.4(NetLogoEngine)의 결과는 엔진 표시를 제외하면 완전히 같습니다.
- **NetLogo 모델:** `netlogo7/cordon_lite.nlogox` 하나입니다. Python은 이를 화면 없이 엔진(NetLogoEngine)으로
  쓰고, NetLogo에서 열면 run을 도로망 위에서 재생합니다. setup 후 go를 누르면 모든 통근자가 출근을 마칠 때까지
  하루 아침이 진행되고 멈춥니다(1 tick = 15초). 여러 날을 연속으로 돌리려면 go를 누르기 전에 keep-going?
  스위치를 켜야 합니다. 게이트 대기열의 차량은 빨간색이며, 에이전트 하나가 실제 차량 약 63대(약 220 m)를
  나타내도록 접근 도로를 따라 그려집니다. 이 모델은 run 폴더를 재생하면서 모든 차량이 TomTom
  도로망 위를 실제로 달리게 합니다. TomTom gpkg는 `python -m prep.build_netlogo_layers`로
  `netlogo7/gis/tomtom_major_roads.shp`로 변환되고(세그먼트와 속성 동일), NetLogo가 이를 읽어 prep과
  경로를 찾는 것과 같은 노드-링크 망(최대 연결 성분: 노드 28,507, 링크 30,835, 코든 내부 노드 1,106)을 만듭니다. 통근자는 자기 origin에서
  출발해 origin의 prep 게이트까지 자유통행 최단경로로 달리고, 코리도 대기열에서 기다린 뒤, 코든 안의 건물
  1,484개 중 무작위로 한 번 뽑힌(고정 시드) 자기 직장 건물로 갑니다. 직장은 매일 같습니다. 게이트를 지난 차는
  코든 안의 도로로 건물까지 가며, 코든 안 도로가 서로 이어지지 않는 곳(Wellesley Street 램프 게이트에서 약
  100-160 m, Hopetoun Street에서 약 180 m)에서만 잠깐 코든 밖 도로를 지납니다. 차는 건물에서 가장 가까운
  코든 안 도로 노드에 주차하고(중앙값 65 m), 도착 시각에 통근자가 건물 위치에 나타납니다. 분 단위 시각은
  엔진과 같으며(출발, 게이트 도착, 게이트 통과, 도착이 run의 outcomes.csv와 일치), 도로망은 그 사이에 차가
  어디 있는지만 정합니다. PT는 이동 중 숨겨졌다가 도착 시각에 건물에 나타나고, WFH와 SKIP은 집에 있습니다.
- **리뷰 후 수정:** PT 장애가 끝난 다음 날 다시 깨우는 T4 추가, 용량 보정을 corridor 차량 가중 평균으로 변경,
  SKIP을 습관으로 보지 않고 SKIP 비용을 VoT에 비례하게 변경, 쌍둥이 비교를 위한 공통 난수, PT 배차간격(10분)에
  따른 조기 도착 비용, traits off에서 LLM에도 3단계 문장 제공, LLM 오류 시 즉시 중단 및 모든 호출 즉시 기록,
  실행 폴더 이름에 설정 차이를 반영해 덮어쓰기 방지. 자세한 내용은 `DEVIATIONS.md`의 "Final fixer"에 있습니다.
- **실행:** 위의 Setup과 How to run 순서(prep, calibrate, run, analysis)를 따르십시오. 실제 API는
  `ANTHROPIC_API_KEY` 또는 `ant auth login` 후 작은 규모부터 시작하십시오.
- **행동 보정:** 규칙 의사결정자(R-daily, 시드 1-3)만 보정했습니다. 구조 수정(기준 요금은 직면 요금 추종, eta 상한 1,
  v3 방식의 WFH 비용, 요금 변화는 습관 단절 아님) 후 스칼라 2개(PT 태도 벌점 PAP, k_WFH)만 격자 탐색했습니다.
- **주차비와 연료비는 저자가 고정(2026-10-03):** 유료 주차는 사무직 NZ$17/일(학생 NZ$12.75, 회사 차량 0)로 고정했고
  [저자 결정; AT 2014년 Victoria St 일일 요금과 일치], 연료비는 2 × 경로 거리 × NZ$0.30/km(휘발유 NZ$3.30/L
  [저자 제공, 2026년 10월] × 9.0 L/100 km)로 고정했습니다. 연료비를 내는 통근자의 하루 평균은 약 NZ$8.6입니다.
  두 값은 보정하지 않으며, 휘발유 가격은 우리가 공개 자료로 검증하지 않았습니다.
- **연기 비용 인상과 조기 출근(2026-10-05, 저자 결정):** 연기(SKIP) 비용을 NZ$30 + 시간가치 1시간으로 올렸고
  [A, 운전 비용 상승에 맞춤], 고용주가 허용하는 통근자는 평소 시작 시각 대신 07:00에 일을 시작할 수 있게 했습니다
  (07:00 to 15:00 근무). 허용 확률은 하이브리드 사무직 0.8, 상근 사무직 0.5, 교대·서비스 0, 현장직 0.5, 학생 0이고,
  조기 출근일의 불편 비용은 NZ$3 × phi(F)입니다. 모두 가정이며 보정하지 않습니다. 조기 출근은 "일찍 도착해서
  기다리는 것"이 아니라 실제 선택지입니다. 각 차량·PT 선택지는 두 시작 시각 중 비용이 낮은 쪽을 기준으로
  이르거나 늦은 정도를 계산하고, 지각 trigger(T3)와 결과 기록도 그 시작 시각을 씁니다. 프롬프트에는 허용 문장과
  선택지별 시작 시각 열이 들어갑니다.
- **재보정 결과:** 같은 목표·시드·손실·선택 규칙·격자로 다시 탐색하니 PAP 20(범위 10-36), k_WFH 10(범위 2-16)이
  다시 선택되었고, 이번에는 조건을 만족하는 격자점이 6개(405개 중)입니다. 시드 1-3 평균은 요금 전 차량 0.843,
  PT 0.154, 재택 0.001, 연기 0.003, 11-13일 -25.2%, 21-30일 -16.0%입니다. 목표를 표기 정밀도(비율은 소수 둘째
  자리)로 보면 모두 만족하고 시드별 허용오차도 모두 만족합니다. 정확히 보면 PT 평균 0.154는 한계 0.15를 0.0036
  넘고(반올림하면 0.15), 시드 1의 차량 0.866과 시드 2·3의 PT 0.155·0.175는 범위 밖이지만 허용오차 안입니다.
  보정에 쓰지 않은 시드 6-12는 반응 -15.0%(-12.0 to -18.3%), PT 0.154, 연기 0.004입니다. 목표는 완화하지 않았습니다.
- **조기 출근의 실제 효과(정직한 보고):** 통근자의 약 47%가 조기 출근이 가능하고, 요금 전에 6.1%가 사용합니다
  (주로 대기열 회피). 요금 후에는 늘지 않고 4.2%로 줄어듭니다(요금이 없는 run은 6.1%). 요금으로 대기열이 거의
  사라지고, 남는 이득(요금 차이 약 NZ$2)이 가정한 불편 비용보다 작기 때문입니다. 불편 비용을 NZ$1.5로 낮추면
  요금 후에 늘어납니다(10.0% → 11.5%). 연기 감소(요금 전 2.0% → 0.3%, 요금 후 4.7% → 1.0%)는 조기 출근이 아니라
  연기 비용 인상 때문입니다. 08:00 to 09:00 차량 통과는 18.6% 줄어 오전 전체(16.0%)보다 조금 더 줄지만 시드마다
  다릅니다(시드 1-12 평균 23.9% 대 15.6%). LLM 의사결정자는 보정하지 않지만 주차비, 연료비, 조기 출근 허용 여부는
  프롬프트에 나타납니다. 자세한 내용은 `docs/calibration_report.md`를 보십시오.
- **주의:** mock 결과는 LLM 결과가 아닙니다.
