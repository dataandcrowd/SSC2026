# Cordon-Lite interfaces

This file fixes the public functions, data classes, file formats and column names that each
builder must implement, so that the four builders (prep, engine, behaviour, llm) and the
integrator can work in parallel without collisions. The authoritative behaviour is in the
specification; where this file is more precise, follow this file. Record any departure in
`DEVIATIONS.md`.

General rules

- Python 3.12, only `/Users/hshi103/github/CUPUM2027/cordon_lite/.venv/bin/python`.
- Run modules as `python -m cordonlite.<module>` or `python -m prep.build_inputs` from the
  `cordon_lite` folder. Never run a file inside `cordonlite/` as a script: `cordonlite/types.py`
  would shadow the standard library `types` module.
- Never modify anything outside `cordon_lite/`.
- Times are integer minutes since midnight. Money is NZ$. VoT is NZ$/h.
- IDs: `agent_id` 0..N-1, `corridor_id` 0..K-1, `origin_id` 0..M-1, `gate_id` 0..G-1, all int.
- Days are 1-based (`day = 1..n_days`).
- Every random draw comes from `cordonlite.config.stream(seed, *key)`. Named keys:
  `("A",)` persona constraints, `("B",)` traits, `("rule", noise_id, day, option_code)` rule noise
  (noise_id = own id, or the source agent's id for a twin; final fixer),
  `("events",)` event draws, `("prep",)` origin sampling. MockLLM noise is seeded from
  `sha256(prompt)`, not from a stream.
- CSV files: comma separated, header row, no index column, `\n` line endings, floats written by
  pandas defaults unless stated. Booleans written as `True`/`False` by pandas.

## Ownership

| Builder | Owns |
|---|---|
| scaffold (done) | `cordonlite/__init__.py`, `config.py`, `fees.py`, `types.py`, `engine.py` (Protocol, DayResult, constants), `config.toml`, `tests/conftest.py`, `tests/test_fees.py`, `tests/test_config.py`, `tests/test_fixtures.py`, `pytest.ini`, `requirements.txt`, this file |
| prep | `prep/`, `data/` (outputs), `tests/test_prep*.py` |
| engine | engine implementations appended to `cordonlite/engine.py`, `netlogo/`, `tests/test_engine*.py` |
| behaviour | `persona.py`, `memory.py`, `options.py`, `rules.py`, `clock.py`, `vickrey.py`, `tests/test_persona*.py`, `test_memory*.py`, `test_options*.py`, `test_rules*.py`, `test_clock*.py`, `test_vickrey*.py` |
| llm | `llm.py`, `tests/test_llm*.py` |
| integrator (later) | `run.py`, `analysis.py`, `README.md`, `tests/test_run*.py`, `tests/test_analysis*.py` |
| road congestion (2026-10-07 to 09) | `cordonlite/roads.py`, `prep/build_roads.py`, `prep/fetch_nzta.py`, `data/road_*`, `data/origin_sections.csv`, `data/section_segments.csv`, `data/nzta/`, `tests/test_roads.py`, `tests/test_prep_roads.py`, `tests/test_analysis_roads.py`, `tests/test_netlogo_interface.py`; see "Road congestion" at the end |
| peak charge and NetLogo choosers (2026-10-09) | `fees.peak_fee` (`config.py`, `fees.py`, `run.py`; the charge multiplier `fees.scale` of the same day is retired), the fee-response part of `analysis.py`, `tests/test_peak_fee.py`; the GUI part of `netlogo7/cordon_lite.nlogox`; see "Peak charge, fee response and NetLogo choosers" near the end |
| SKIP removed and willingness to travel (2026-10-09) | `[wtt]` (`config.py`), `persona.py`, `options.py`, `clock.py`, `memory.py`, `rules.py`, `llm.py`, `run.py`, `types.py`, `tests/test_wtt.py`; see "SKIP removed and the willingness to travel" near the end |

Shared files (`config.py`, `types.py`, `config.toml`, `conftest.py`) may only gain new
optional items; do not rename or remove existing ones. If a builder needs a new config key,
add it to `config.toml` with an [A] or source comment and to the matching dataclass in
`config.py` (the loader rejects unknown and missing keys; only the keys in `config._ADDED_KEYS` and
the sections in `config._ADDED_SECTIONS` may be absent, and the keys in `config._RETIRED_KEYS` are
dropped, see "SKIP removed and the willingness to travel"), and note it in `DEVIATIONS.md`.

## Already implemented (scaffold)

### `cordonlite/config.py`

```python
ROOT: Path                      # cordon_lite folder
load_config(path: str | Path | None = None, overrides: Mapping[str, Any] | None = None) -> Config
    # overrides use dotted keys, e.g. {"run.n_agents": 20, "llm.mock.noise_sigma": 0.0}
dump_toml(cfg: Config) -> str   # effective config, used for config_snapshot.toml
stream(seed: int, *key: int | str) -> np.random.Generator
seed_sequence(seed: int, *key: int | str) -> np.random.SeedSequence
class ConfigError(ValueError)
Config: run, time, fees, prep, engine, road, persona, traits, costs, memory, clock, events, rules, llm (llm.mock)
                                # road (RoadConfig) added 2026-10-07; see "Road congestion"
Config.resolve_path(p) -> Path  # relative to ROOT
Config.pt_ratio(corridor_id) -> float
Config.to_dict() -> dict
```

Archetype-indexed lists in `[persona]` have 5 entries (index `archetype - 1`). Trait-indexed
lists (`traits.kappa_h` by H, `phi` by F, `omega` by P, `eta` by S, `clock.late_tolerance_by_F`)
have 5 entries (index `level - 1`).

### `cordonlite/fees.py`

```python
TOU_POINTS: tuple[tuple[float, float], ...]
DEFAULT_PEAK: float = 6.0                             # the SSC2026 schedule's peak (was DEFAULT_FLAT)
fee_at(minute: float, regime: str = "tou", *, peak_fee=None, points=TOU_POINTS, round_dp=4) -> float
fee_table(regime: str = "tou", *, peak_fee=None, points=TOU_POINTS, round_dp=4) -> list[float]   # 1440 entries
fee_table_from_config(cfg: Config, regime: str | None = None) -> list[float]   # peak_fee = cfg.fees.peak_fee
schedule_peak(points) -> float                        # 2026-10-09: the points' highest charge
peak_points(points, peak_fee) -> tuple[tuple[float, float], ...]   # charges x peak_fee / schedule_peak, hours unchanged
levied_regime(regime: str, peak_fee: float) -> str   # "none" when peak_fee is 0, else regime
fee_active(day: int, regime: str, fee_start_day: int) -> bool    # pass levied_regime(...) as regime
write_fees_csv(path, table, round_dp=4) -> Path      # minute,fee with 4 decimals
read_fees_csv(path) -> list[float]
max_table_change(a, b) -> float                       # for T2
describe_schedule(table, start_min, end_min, step_min=15) -> list[tuple[int, float]]
```

Engines take `fee_paid` from `fees.csv` (the table), never by recomputing the schedule.
`peak_fee` (2026-10-09, config `fees.peak_fee`, NZ$) is the schedule's highest charge: every ToU
charge is multiplied by `peak_fee / schedule_peak(points)` before evaluation and rounding (None =
the points as given, peak NZ$6); regime "flat" charges `peak_fee` all day; regime "none" and
`peak_fee` 0 are 0. It replaced the same day's charge multiplier `scale` (`fees.scale`) and
`fee_flat`. See "Peak charge, fee response and NetLogo choosers" near the end.

### `cordonlite/types.py`

`Persona`, `TraitParams`, `Option`, `MemoryRecord`, `TodayInfo`, `DecisionContext`, `Decision`,
the `Decider` Protocol, `DelayProfile`, constants `MODES`, `DECIDERS`, `TRIGGERS`, `FACTORS`,
`GC_PARTS`, and helpers `option_id_for(mode, depart_min)` and `clock_str(minute)`. Read the file
for field lists; they are the contract.

Key conventions:
- Option ids: `CAR_hhmm` (e.g. `CAR_0745`), `PT`, `WFH` (`SKIP` until 2026-10-09; `MODES` =
  `("CAR", "PT", "WFH")`).
- Option order in `DecisionContext.options`: CAR by `depart_min` ascending, then PT, WFH.
- `Option.gc == sum(Option.gc_parts.values())`, keys from `GC_PARTS`
  (`time, schedule, fee, parking, fuel, pt, wfh, habit`; absent keys mean 0; `skip` until
  2026-10-09).
- `Decision.decider` in `rule`, `llm`, `llm-fallback-rule`, `standing`, `forced` (`forced`: one
  option left, since 2026-10-09 a commuter whose car options the willingness to pay removed and who
  has no WFH; no decider is called).

### `cordonlite/engine.py`

`Engine` Protocol (`load`, `run_day`, `close`), `DayResult(outcomes, profile, road)` (`road`
defaults to an empty int64 frame), column tuples `PLAN_COLUMNS`, `OUTCOME_COLUMNS` (with
`road_delay_min` after `depart_min`), `PROFILE_COLUMNS`, `ROAD_COLUMNS` (`day, section_id, minute,
entries`), `CORRIDORS_COLUMNS`, `AGENTS_COLUMNS`, file names `CORRIDORS_FILE`, `AGENTS_FILE`,
`FEES_FILE`, `PLANS_FILE` (`plans.csv`: every day of a run, `PLANS_COLUMNS` = `day` + `PLAN_COLUMNS`), and
`plans_file(day)`, `outcomes_file(day)`, `profile_file(day)`, `road_file(day)` (`plans_dayNN.csv`,
`road_dayNN.csv` etc., two-digit day: NetLogoEngine's per-day exchange files, which `run_simulation` deletes).

## Prep builder: `prep/build_inputs.py`

CLI: `python -m prep.build_inputs [--config config.toml]`. Seeded with `stream(seed, "prep")`.

```python
load_cordon(cfg) -> BaseGeometry          # shapely.ops.unary_union of the named SA3 geometries, .buffer(0)
load_roads(cfg) -> gpd.GeoDataFrame       # layer cfg.prep.roads_layer, EPSG:2193
build_graph(roads, cfg) -> nx.Graph       # undirected, endpoints rounded to node_round_m, giant component
    # edge attrs: minutes, segment_id, frc, speed_limit, street_name, distance_m
    # minutes = distance_m / (speedLimit * 1000 / 60) * ff_factor
destination_node(G, cordon) -> tuple[float, float]   # node inside cordon nearest its centroid
candidate_origins(G, roads, cordon, cfg) -> pd.DataFrame   # node, x_nztm, y_nztm, weight
sample_origins(candidates, cfg) -> pd.DataFrame            # n_origin_points, weighted, with replacement allowed only if needed
trace_paths(G, dest, origins, cordon) -> pd.DataFrame      # one single-source Dijkstra from dest
group_corridors(gates, cordon, cfg) -> tuple[pd.DataFrame, pd.DataFrame]
write_outputs(...) -> None
main(argv=None) -> int
```

Gate = the first edge on the origin-to-destination path whose far end is inside the cordon.
`fftt_to_gate_min` = path minutes up to the gate node (the far end); `fftt_gate_to_dest_min`
= remaining minutes. Optional OD hook: if `cfg.prep.od_csv` is set, it has columns
`sa2_code, x_nztm, y_nztm, commuters_to_cordon` and replaces the proxy weights.

Outputs in `data/` (exact columns):

| File | Columns |
|---|---|
| `origins.csv` | `origin_id, x_nztm, y_nztm, weight, corridor_id, gate_id, fftt_to_gate_min, fftt_gate_to_dest_min, path_km` |
| `gates.csv` | `gate_id, corridor_id, segment_id, streetName, frc, speedLimit, x_nztm, y_nztm, n_origins` |
| `corridors.csv` | `corridor_id, name, n_gates, capacity_vph_raw, bearing_deg, x_nztm, y_nztm, main_streets` |
| `cordon.geojson` | cordon polygon (EPSG:2193 coordinates; crs member stated) |
| `prep_map.png` | roads light grey, cordon, gates coloured by corridor, origin sample coloured by corridor |
| `prep_report.md` | counts, share of origins per corridor, fftt distribution, every assumption |

`corridors.csv` (prep format) is different from the engine scenario `corridors.csv`; the
integrator converts it (see below). `x_nztm, y_nztm` of a corridor = mean gate position.
`name` like `"North (Harbour Bridge, Fanshawe St)"`. `main_streets` is `;`-separated.

The road congestion inputs (road sections, counts, capacity, NZTA motorway sites) come from a second
prep step, `python -m prep.build_roads`, run after this one; it rebuilds these paths and must
reproduce `origins.csv` exactly. See "Road congestion" at the end.

## Engine builder: implementations in `cordonlite/engine.py`

```python
class PyEngine:      # implements Engine
    def __init__(self, cfg: Config) -> None
class NetLogoEngine: # implements Engine
    def __init__(self, cfg: Config, link: object | None = None) -> None   # link: shared pynetlogo.NetLogoLink
def make_engine(kind: str, cfg: Config) -> Engine                       # "py" | "netlogo"
def get_netlogo_link(cfg: Config) -> object                             # one NetLogoLink per process (cached)
def resolve_netlogo_home(cfg: Config) -> str                            # 2026-10-09: $CORDONLITE_NETLOGO_HOME if set,
                                                                        # else [engine] netlogo_home (never stored in
                                                                        # the config, snapshot or variant label)
NETLOGO_HOME_ENV = "CORDONLITE_NETLOGO_HOME"
# added by the engine builder:
def simulate_point_queues(cars, corridor_ids, capacities, sim_start_min, sim_end_cap_min)
    -> (exit_min_by_agent, profile_rows, last_minute)                   # reference algorithm
def read_scenario(scenario_dir) -> Scenario                             # validated scenario files
def shutdown_netlogo_link(timeout_s=5.0) -> bool                        # guarded kill_workspace
def hard_exit(code=0) -> None                                           # flush + os._exit (end of CLI with NetLogo)
NETLOGO_JVM_ARGS = ("-XX:MaxRAMPercentage=50",)                         # 2026-10-07: passed by get_netlogo_link
                                                                        # (the NetLogo app's heap; avoids GC pauses)
```

Equivalence check in its own process: `python scripts/check_netlogo_equivalence.py [--scenario DIR]
[--n-random 6] [--seed 7] [--real-agents N] [--timing-agents 300] [--gui-smoke] [--netlogo-home PATH]
[--json OUT]` (exit code 0 when PyEngine == NetLogoEngine on outcomes, profile and road entries).
Variants: `base`, `lowcap`, and since 2026-10-07 `road` (synthetic road files), `road_mwy` (motorway
breakdown by window and by trigger), `road_nzta` (several time profiles, per-section `cap_drop`) and,
with `--real-agents N`, `real` (`run.write_scenario` on N real personas and the prep road data).
`--gui-smoke` runs on `road_nzta`. NetLogo runs, scripts and tests read `CORDONLITE_NETLOGO_HOME` when set
(`--netlogo-home` sets it).

Scenario files (written by the integrator into the run directory, read by `load`):

| File | Columns |
|---|---|
| `corridors.csv` | `corridor_id, name, capacity_per_min, x, y` (x, y in NZTM metres) |
| `agents.csv` | `agent_id, corridor_id, fftt_to_gate_min, fftt_gate_to_dest_min, x, y` (ints for times; both fftt values are FREE-FLOW minutes: with road files the gate arrival adds the car's `road_delay_min`, the leg after the gate stays free flow) |
| `fees.csv` | `minute, fee` (1440 rows, active regime; used only when `fee_active`) |
| `road_sections.csv`, `agent_routes.csv`, `road_profile.csv`, `road_params.csv` | optional (2026-10-07), all four or none; none = free-flow roads. Columns in "Road congestion", run scenario files |

`run_day(day, plans, fee_active)`: `plans` has `PLAN_COLUMNS` for every agent; CAR rows are
simulated. Semantics are in the `engine.py` module docstring (road traversal, point queue, carry
rule, cap sentinel `-1`): a car leaving at `d` drives its pre-gate route (`roads.simulate_roads`,
"Road congestion", engine semantics), joins its corridor queue at `a = d + fftt_to_gate_min +
road_delay_min` (`road_delay_min = 0` without road files or without a route), and after the gate
`arrive_min = gate_exit_min + fftt_gate_to_dest_min`. The `a < sim_start_min` check is made on the
free-flow arrival (road delay is never negative). Outputs: `DayResult.outcomes` with
`OUTCOME_COLUMNS` sorted by `agent_id` (`road_delay_min` is known for unserved cars too),
`DayResult.profile` with `PROFILE_COLUMNS` sorted by `corridor_id, minute`, covering every
corridor and every minute from `sim_start_min` to the last minute processed, and `DayResult.road`
with `ROAD_COLUMNS` (int64, non-zero entries only, sorted by `section_id, minute`; empty without
road files).

NetLogoEngine file exchange in the scenario directory (temporary: `run_simulation` deletes the per-day
files, and `plans.csv` holds every day): Python writes `plans_dayNN.csv`
(`agent_id, mode, depart_min`), calls `command('run-day <day> "<dir>" <true|false>')`, NetLogo
writes `outcomes_dayNN.csv`, `profile_dayNN.csv` and `road_dayNN.csv` (header only without road
files) with the same columns as the DataFrames. Python deletes stale copies of the three before the
call; a missing `road_dayNN.csv` when the scenario has road files raises RuntimeError. The run
deletes `outcomes_day*.csv`, `profile_day*.csv` and `road_day*.csv` at the end, so py and NetLogo run
folders hold the same files.
NetLogo procedures required: `setup-from-dir <dir>` (reads the scenario files, and the four road
files when present: `read-roads`), `run-day <day> <dir> <fee-active?>` (= `run-day-io d dir dir
fee?`). Both share the reporters `road-arrivals [cars]` and `point-queues [arrivals]` with the GUI.
GUI: the same model replays a run on the TomTom road network (see "NetLogo network model" below);
headless use never loads the map.
Tests: PyEngine hand-computed cases; PyEngine == NetLogoEngine on random plans, marked
`@pytest.mark.netlogo`, executed in a subprocess or separate pytest process, ending with
`os._exit` or a guarded `kill_workspace`.

Capacity is NOT the engine's job: the gate capacity `capacity_per_min` arrives in `corridors.csv`,
and the road capacities `cap_vph` with the background flows, time profiles, breakdown windows and
capacity drops arrive in `road_sections.csv` / `road_profile.csv` / `road_params.csv` (prep values;
the breakdown windows of motorway sections without an NZTA site are recomputed by
`roads.write_road_scenario` on the run side). The engines compute none of them; they only apply the
speed-factor rule to the volumes of the day.

## Behaviour builder

### `cordonlite/persona.py`

```python
TRAIT_SENTENCES: dict[str, tuple[str, str, str, str, str]]   # keys "H","F","P","S"; v3 section 4.5 text, verbatim
build_personas(origins: pd.DataFrame, corridors: pd.DataFrame, cfg: Config,
               n_agents: int | None = None, traits: str | None = None) -> list[Persona]
draw_traits(n: int, cfg: Config, rng: np.random.Generator) -> np.ndarray     # (n, 4) int, columns H, F, P, S
trait_params(persona: Persona, cfg: Config) -> TraitParams
disposition_sentences(persona: Persona) -> tuple[str, str, str, str]          # order H, F, P, S
personas_to_frame(personas: Sequence[Persona]) -> pd.DataFrame               # personas.csv
agents_frame(personas: Sequence[Persona]) -> pd.DataFrame                    # AGENTS_COLUMNS (x, y = x_nztm, y_nztm)
twin_pairs(personas: Sequence[Persona]) -> list[tuple[int, int]]
```

Layer A, all on `stream(seed, "A")`, in this order per agent: origin by weight, VoT
lognormal(`vot_mu`, `vot_sigma`); after all VoTs, quintiles (1..5 by population rank); then per
agent archetype (`arch_weight` x `vot_tilt[arch][q]`, renormalised), t* (discretised normal
`tstar_mean_min`, `tstar_sd_min` on the t* grid, clipped), company car (`company_car_prob`, or
`company_car_prob_q5` when quintile 5), parking (free with `park_free_prob`, else
`park_cost_paid`; 0 for company car). Derived (no draw): `fuel_cost = round(2 * path_km *
costs.fuel_cost_per_km, 2)`, 0 for company car (fuel addition; fixed from evidence, never
calibrated). Derived: `pt_allowed = persona.pt_allowed[arch] and
corridor not in costs.pt_unavailable_corridors`; `wfh_allowed`, `fixed_start`, `must_drive`,
`activity`, `sched_mult` from archetype; `fftt_*_min = round()` of origins values (half away
from zero, minimum 1 for `fftt_to_gate_min`, 0 for the other); `pt_time_min =
cfg.pt_ratio(corridor) * (fftt_to_gate_min + fftt_gate_to_dest_min) + pt_access_min`;
`pt_fare = costs.pt_fare`. Twins: with `k = min(n_twins, n_agents // 2)`, agent
`n_agents - k + j` copies every Layer A field of agent `j` (j = 0..k-1). Two later Layer A draws
come after all of these, in this order: the early-start permission (2026-10-05) and the uniform of
the willingness to pay (2026-10-09; `wtt_u`, `wtt_beta`, `wtp_fee`, see "SKIP removed and the
willingness to travel").

Layer B on `stream(seed, "B")` only: one latent N(0,1) per agent per trait (draw shape (n, 4),
columns H, F, P, S), cut at cumulative share boundaries. With `traits == "off"` every trait is
`traits.off_level` (the B stream is still not used by A).

`personas.csv` columns: the `Persona` dataclass fields in declaration order.

### `cordonlite/memory.py`

```python
@dataclass
class AgentMemory:
    agent_id: int
    records: list[MemoryRecord] = field(default_factory=list)
    delay_ratio_ema: float = 1.0
    ref_fee: float = 0.0
    standing_option_id: str | None = None
    standing_mode: str | None = None
    standing_depart_min: int | None = None
    consumed_events: set[tuple[str, int]] = field(default_factory=set)
    def recent(self, n: int) -> tuple[MemoryRecord, ...]
    def last(self) -> MemoryRecord | None
new_memory(agent_id: int) -> AgentMemory
update_memory(mem: AgentMemory, record: MemoryRecord, cfg: Config) -> None
set_standing(mem: AgentMemory, option: Option) -> None
memory_frame(memories: Iterable[AgentMemory]) -> pd.DataFrame
```

Delay ratio on car days: `r = (queue_delay_min + ratio_offset_min) / (expected_public_delay +
ratio_offset_min)` where `expected_public_delay` is the public (pre-ratio) forecast for the
chosen option, clipped to `ratio_clip`; `ema <- ema + alpha * (r - ema)`. To support this,
`MemoryRecord.expected_delay_min` stores the public forecast (before the personal ratio). The
ratio is queue-only (2026-10-07): the road delay before the gate is stored in the record
(`road_delay_min`, `expected_road_delay_min`) but not learned from, because the public road
information is already specific to the agent's route.
Reference fee: `ref <- ref + alpha * (fee_paid_perceived - ref)` every day
(`ref_fee_update = "all_days"`, 0 on non-car days) or on car days only. `fee_paid_perceived`
is 0 for company-car agents.
Behaviour recalibration: `update_memory(mem, record, cfg, fee_faced=None)`; with
`ref_fee_update = "faced"` (the default) the update uses the fee paid on car days and `fee_faced`
(from `options.fee_faced`) on other days.

### `cordonlite/options.py`

```python
departure_grid(cfg: Config) -> list[int]          # 2026-10-08: every CAR departure (grid + depart_latest_min)
car_departures(standing_depart_min: int, cfg: Config, persona: Persona | None = None,
               today: TodayInfo | None = None) -> list[int]
expected_road_delay(persona: Persona, today: TodayInfo | None, depart_min: int, cfg: Config) -> float
start_anchor_depart(persona: Persona, start_min: int, cfg: Config, today: TodayInfo | None = None) -> int
initial_depart_min(persona: Persona, cfg: Config, today: TodayInfo | None = None) -> int
car_reference_depart(persona: Persona, memory: AgentMemory, cfg: Config, today: TodayInfo | None = None) -> int
public_delay_profile(outcomes: pd.DataFrame | None, corridor_ids: Sequence[int], bin_min: int) -> DelayProfile
expected_public_delay(profile: DelayProfile, corridor_id: int, gate_arrive_min: int) -> float
feasible_modes(persona: Persona, today: TodayInfo, cfg: Config) -> tuple[str, ...]
build_options(persona: Persona, memory: AgentMemory, today: TodayInfo, params: TraitParams,
              cfg: Config, discontinuity: bool, wtt: bool = True) -> tuple[Option, ...]
wtt_filter(persona: Persona, options: Sequence[Option]) -> tuple[Option, ...]   # 2026-10-09
non_car_outcome(persona: Persona, option: Option, day: int, pt_disrupted: bool) -> dict
gc_rank(options: Sequence[Option], option_id: str) -> int
```

`today` in the departure helpers supplies the public road delays (`TodayInfo.public_road`); without
it, or with roads off (empty mapping), they use free-flow roads. Pass the TodayInfo that
`build_options` gets. Every departure they read a road delay for is on `departure_grid`.
`expected_road_delay` = `roads.road_delay_at(today.public_road, agent_id, d, time.sim_start_min)`,
0.0 without information. `start_anchor_depart` = the latest grid departure `d` (window-clipped) with
`d + fftt_total_min + floor(R_d + 0.5) + time.initial_buffer_min <= start` (the earliest departure
when none qualifies); with `R = 0` it is the earlier `start - fftt_total - buffer`, floored to the
grid.

Feasibility: CAR always; PT if `persona.pt_allowed` (a disrupted corridor keeps PT feasible
but slower); WFH if `persona.wfh_allowed`; SKIP always until 2026-10-09, when it was removed. Since
then `build_options` (unless `wtt=False`) drops the CAR options whose levied charge `Option.fee` is
above `persona.wtp_fee` (`wtt_filter`; the mode stays feasible, some or all of its departures go).

Generalised cost, per option (NZ$), with `a = VoT/60`, `k = kappa_h * (kappa_h_disc_factor if discontinuity else 1)`:

```
CAR at depart d:
  R     = expected_road_delay(persona, today, d, cfg)         (public road delay, unrounded; 0 with roads off; 2026-10-07)
  g     = d + fftt_to_gate_min + floor(R + 0.5)               (expected gate arrival; the engine's rounding)
  D     = expected_public_delay(profile, corridor, g) * memory.delay_ratio_ema
  x     = g + round(D)                                        (expected gate exit; fee minute)
  arr   = x + fftt_gate_to_dest_min
  early = max(0, t* - arr); late = max(0, arr - t*)
  time     = a * (fftt_total + R + D)                         (expected_travel_min = fftt_total + R + D)
  schedule = phi * sched_mult * a * (beta_ratio * early + gamma_ratio * late)
  fee      = c * (f + eta * max(0, f - ref_fee))   with f = fee_by_minute[x], c = 0 if company_car else 1
             (equivalently f * (1 + eta * max(0, f - ref)/max(f, fee_eps)))
  parking  = persona.parking_cost
  fuel     = persona.fuel_cost                    (fuel addition; also `Option.fuel`, 0 for non-car options)
PT:   pt = omega * (a * T_pt + PAP) + pt_fare, T_pt = pt_time_min * (pt_disruption_time_mult if disrupted and announced else 1)
      (T_pt does not depend on road traffic: rail and busway assumption)
      final fixer: services leave on a pt_headway_min grid; depart = latest service arriving by t*,
      early = t* - arrival (< headway), schedule = phi * sched_mult * a * beta_ratio * early
WFH:  wfh  = wfh_cost * phi                                   (costs.wfh_form = "spec")
      wfh  = wfh_cost * phi + a * fftt_total + parking_cost + fuel_cost   ("v3_relative", default; recalibration; fuel addition)
SKIP: skip = skip_cost + skip_vot_hours * VoT   (final fixer; removed 2026-10-09)
habit = k for every option whose option_id differs from the habit reference (0 when none):
        the standing option (until 2026-10-09, for a standing SKIP the most recent non-SKIP option)
```

`Option.fee` is the levied charge `f` (shown in the prompt, flagged employer-paid for company
cars); the perceived part goes in `gc_parts["fee"]`.

`non_car_outcome` row: same columns as `outcomes.csv` below, with car-only fields empty.

### `cordonlite/rules.py`

```python
class RuleDecider:   # Decider
    name = "rule"
    def __init__(self, cfg: Config) -> None
    def decide(self, ctx: DecisionContext) -> Decision
    def decide_batch(self, contexts: Sequence[DecisionContext]) -> list[Decision]
```

`argmin_i (gc_i - eps_i)`, `eps_i ~ Gumbel(0, sigma_rule)` from `stream(seed, "rule", noise_id,
day, option_code(option_id))` (common random numbers: twins use their source agent's id; final
fixer); ties to the lower index. `decider="rule"`.

### `cordonlite/clock.py`

```python
evaluate_triggers(persona: Persona, memory: AgentMemory, today: TodayInfo,
                  feasible_option_ids: Sequence[str], cfg: Config) -> tuple[str, ...]
is_discontinuity(triggers: Sequence[str], cfg: Config) -> bool
should_wake(arm: str, triggers: Sequence[str]) -> bool
```

T1 no standing option; T2 `today.fee_changed_today`; T3 yesterday `late_min >
late_tolerance_by_F[F-1]`; T4 PT disrupted yesterday (record `pt_disrupted`), or announced
today on own corridor while standing mode is PT; T5 last `sustained_days` car records each
have `|travel_min / expected_travel_min - 1| > sustained_rel` (both fields of `MemoryRecord`);
T6 standing option id not in `feasible_option_ids` (a standing CAR departure is feasible if
inside the departure window and, given option ids, listed itself; until 2026-10-09 a standing SKIP
was always infeasible). Pass the offered option ids (willingness to pay applied), so that a standing
car departure the limit removes today wakes the agent. Edge triggering: an event key
`(trigger, event_day)` fires once and is added to `memory.consumed_events`. Final fixer: the day
after an announced disruption that woke the agent, key `("T4-end", d)` wakes it once more (reported
as T4). Output sorted.

### Behaviour builder additions (implemented; additive)

- `Option.expected_public_delay_min` (types.py, default None): yesterday's public forecast for a
  CAR option, before the personal ratio. Store it in `MemoryRecord.expected_delay_min`.
- `memory.new_memory(agent_id, company_car=False)`; pass `persona.company_car` so the reference
  fee ignores employer-paid charges. `memory.record_from_outcome(row, option, decider, triggers,
  reason) -> MemoryRecord` builds the record from an outcomes.csv-style row.
- `options.car_outcome(persona, engine_row, option_id=None) -> dict` and
  `options.non_car_outcome(persona, option, day, pt_disrupted, disruption_mult=2.0)` return full
  `outcomes.csv` rows (`options.OUTCOME_ROW_COLUMNS`); pass
  `cfg.events.pt_disruption_time_mult` as `disruption_mult`.
- `clock.evaluate_triggers` accepts feasible MODES (from `options.feasible_modes`) or option ids,
  so it can run before `build_options`.
- Rule noise: the decider takes `argmin(gc - eps)` with `eps ~ Gumbel(0, sigma_rule)` (logit
  probabilities); see DEVIATIONS.md, behaviour entry 1.
- T5 is an edge (fires when the condition becomes true on yesterday's car day); see DEVIATIONS.md.

### `cordonlite/vickrey.py`

```python
@dataclass(frozen=True)
class VickreyResult: N, s, alpha, beta, gamma, t_star, delta, rush_len, t_first, t_last,
                     cost_per_commuter, rate_early, rate_late
equilibrium(N, s, alpha, beta, gamma, t_star=0.0) -> VickreyResult
queue_length(res, t: np.ndarray) -> np.ndarray
queue_delay(res, t: np.ndarray) -> np.ndarray
```

## LLM builder: `cordonlite/llm.py`

```python
TEMPLATE_ID = "cl-v3"     # 2026-10-09 (cl-v2 2026-10-07, cl-v1 before); = config.TEMPLATE_ID, the only template rendered
                          # (a snapshot naming one of config.RETIRED_TEMPLATE_IDS = ("cl-v1", "cl-v2") still loads)
SYSTEM_PROMPT: str
render_user_prompt(ctx: DecisionContext, cfg: Config) -> str
output_schema(option_ids: Sequence[str]) -> dict
validate_output(obj: object, option_ids: Sequence[str]) -> tuple[bool, str]
cache_key(model: str, effort: str | None, template_id: str, system: str, user: str, schema: dict,
          extra: dict | None = None) -> str   # extra: max_tokens, fallback setting, replicate (final fixer)
class LLMCache:
    def __init__(self, cache_dir: Path) -> None
    def get(self, key: str) -> dict | None
    def put(self, key: str, record: dict) -> None
class MockLLM:
    backend = "mock"
    def __init__(self, cfg: Config) -> None
    def complete(self, system: str, user: str, schema: dict, ctx: DecisionContext) -> dict
class AnthropicLLM:
    backend = "anthropic"
    def __init__(self, cfg: Config, client: object | None = None) -> None
    def build_request(self, system: str, user: str, schema: dict) -> dict
    async def acomplete(self, system: str, user: str, schema: dict) -> tuple[dict | None, dict]
class LLMDecider:     # Decider
    name = "llm"
    def __init__(self, cfg, backend, fallback: Decider, log_path: Path, cache: LLMCache | None) -> None
    def decide_batch(self, contexts: Sequence[DecisionContext]) -> list[Decision]
make_llm_decider(cfg: Config, run_dir: Path, fallback: Decider, backend: str | None = None) -> LLMDecider
estimate_tokens(prompts: Sequence[str]) -> dict    # n_calls, prompt_chars, approx_tokens (chars/4, "approximate")
```

Prompt sections (in order): situation (constraints from `Persona` fields `activity`,
`tstar_min`, `fixed_start`, `must_drive`, `wfh_allowed`, `pt_allowed`, `company_car`,
`parking_cost`, `fuel_cost`, `vot`, never `archetype` or its label), dispositions
(`persona.disposition_sentences`, omitted when `ctx.traits_shown` is False), memory table
(`ctx.recent`), today (charge by crossing time from `today.fee_by_minute`, yesterday's
corridor delay by departure time from the options, announced disruption), options table
(every `Option` attribute except `gc`, `gc_parts`; columns `road charge`, `parking`, `fuel`,
`fare`). The situation section states the daily fuel cost of driving next to the parking cost, so
the rule (`gc_parts["fuel"]`) and the LLM have the same information. Deterministic formatting.
Template cl-v2 (road traffic) is described under "Road congestion", prompt; with roads off the
user message is exactly the cl-v1 text (only `template_id` and the cache key differ). Template cl-v3
(2026-10-09) drops the SKIP row and choice and adds the willingness-to-pay sentence on a day the
limit removed a car option ("SKIP removed and the willingness to travel").

Schema: `{"type": "object", "properties": {"choice": {"type": "string", "enum": [...]},
"reason": {"type": "string"}, "factors": {"type": "array", "items": {"type": "string", "enum":
FACTORS}}}, "required": ["choice", "reason", "factors"], "additionalProperties": false}`.

`Decision.meta` for LLM decisions: `backend`, `model`, `cache_hit`, `prompt_sha256`,
`call_id`, `attempts`. `llm_calls.jsonl` one JSON object per call: `call_id, day, agent_id,
triggers, backend, model, effort, template_id, cache_key, cache_hit, system_sha256, user,
schema_option_ids, raw_text, parsed, valid, error, stop_reason, refusal_category, usage
{input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens},
latency_s, model_served, request_id, attempt`.

## Integrator: `cordonlite/run.py`, `cordonlite/analysis.py`

Engine capacity from prep corridors (`engine.capacity_mode`), times `capacity_scale`, rounded to 6 dp:
- `demand_share`: `capacity_per_min_c = max(floor, n_agents_on_c / rush_window_min)`.
- `raw_scaled`: `capacity_per_min_c = max(floor, capacity_vph_raw_c / 60 * n_agents / agents_represented)`.
- `floor` (2026-10-08): `round(min_capacity_vph / 60 / vehicles_per_agent, 6)` agents/min with
  `vehicles_per_agent = agents_represented / n_agents` when `engine.min_capacity_vph > 0` (950 veh/h at
  any n: 0.25 agents/min at 300 agents, 0.791667 at 950); `min_capacity_per_min` when it is 0 (the
  earlier agents/min floor).

Daily loop (per day, agents in ascending `agent_id`):
1. `fee_active = fees.fee_active(day, regime, fee_start_day)`; `today.fee_by_minute` = table or zeros;
   `fee_changed_today = max_table_change(today, yesterday) >= clock.fee_change_threshold`
   (day 1 compares with itself, so False).
2. PT disruption: on `events.pt_disruption_day`, corridor = configured id or, if -1, the
   corridor with most `pt_allowed` personas (ties to lowest id).
3. `public_delay = options.public_delay_profile(yesterday_outcomes, corridors, delay_bin_min)`;
   with road files (2026-10-07) `today.public_road = run.public_road(road, personas, cfg, entries)`:
   day 1 usual traffic (`entries=None`, `public_road_source = "usual"`, computed once), later days
   yesterday's `DayResult.road` (`"yesterday"`); `{}` with roads off.
4. For each agent: `params = trait_params`; feasible modes; `triggers = evaluate_triggers`;
   `discontinuity = is_discontinuity`; `options = build_options` (and `fee_faced(..., today)`); if
   only one option -> `forced`; elif `should_wake(arm, triggers)` -> collect context; else execute
   standing option (`standing`). Since 2026-10-09: `full = build_options(..., wtt=False)`, `options
   = wtt_filter(persona, full)`, triggers on the offered option ids, both rebuilt when the triggers
   hold a discontinuity; `fee_faced` reads `full`; `DecisionContext.wtt_removed = len(full) -
   len(options)`.
5. `decider.decide_batch(woken)` (RuleDecider for R-*, LLMDecider for L-*).
6. Update standing option to the chosen option for every agent that decided (rule/llm/fallback/forced).
7. Plans -> `engine.run_day` -> car outcomes (with `road_delay_min`) and the day's road entries;
   non-car outcomes from `options.non_car_outcome`.
8. Build `MemoryRecord`s and `update_memory`.

Run outputs in `runs/<arm>_<backend>_<engine>_s<seed>/`:

| File | Columns / content |
|---|---|
| `config_snapshot.toml` | `config.dump_toml(cfg)` |
| `personas.csv` | `Persona` fields |
| `decisions.csv` | `agent_id, day, option_id, mode, depart_min, decider, triggers, reason, factors, gc_of_choice, rank_of_choice_by_gc, start_used_min, early_shift, wtt_removed, wtt_all_removed` (`triggers`, `factors` `;`-joined; the last two since 2026-10-09) |
| `outcomes.csv` | `agent_id, day, mode, option_id, corridor_id, depart_min, road_delay_min, gate_arrive_min, gate_exit_min, queue_delay_min, arrive_min, travel_min, early_min, late_min, fee_paid, parking_paid, fuel_paid, pt_fare_paid, pt_disrupted, start_used_min, early_shift` (`road_delay_min`: int, CAR rows only, served or not, 0 with free-flow roads; empty for non-car rows) |
| `profile.csv` | `PROFILE_COLUMNS`, all days |
| `road_entries.csv` | `ROAD_COLUMNS` (`day, section_id, minute, entries`), all days (2026-10-07; header only without roads) |
| `road_los.csv`, `los_summary.csv` | V/C and Level of Service per road and aggregated (2026-10-08; header only without roads); see "Road congestion", run outputs |
| `llm_calls.jsonl` | see LLM section (empty for R-* arms) |
| `summary.json` | `{"meta": {...}, "days": [{"day", "cars", "pt", "wfh", "entries_per_15min": {"hh:mm": n}, "mean_queue_delay", "max_queue_delay", "mean_fee", "revenue", "calls": {"rule", "llm", "llm-fallback-rule", "standing", "forced"}}]}` (the day key `"skip"` was removed on 2026-10-09); later additions below, under "Road congestion" and under "SKIP removed and the willingness to travel" |

### Integrator additions (implemented)

- `run.py`: `run_dir_name(arm, backend, engine, seed, traits="on")`, `load_prep(cfg)`,
  `disruption_corridor(personas, cfg)`, `capacity_per_min(corridors_prep, agents, cfg, scale=1.0)`,
  `resolve_capacity_scale(cfg, cli_scale=None)`, `write_scenario(run_dir, corridors_prep, personas, cfg, scale)`,
  `simulate(cfg, run_dir, scale, ...) -> SimResult`, `run_simulation(cfg, out_dir=None, capacity_scale=None, name=None)`,
  `estimate(cfg)`, `calibrate(cfg, target=None, progress=True, label="")`,
  `peak_bin_delay(outcomes, corridor_id, bin_min, with_road=False)` (`with_road` adds each car's
  road delay to its queue delay; 2026-10-07), `main(argv)`.
- CLI: `python -m cordonlite.run --arm ... --backend ... --engine ... --days 30 --fee-start 11
  --n-agents 950 --seed 1 [--traits off] [--estimate] [--capacity-scale X] [--set key=value]`;
  `python -m cordonlite.run calibrate [--seed 1 | --seeds 1 2 3 [--jobs J]] [--n-agents N]
  [--target 15] [--output PATH]` writes `data/calibration.json` (`--jobs`: 2026-10-08, see
  "Road congestion", calibration).
- `analysis.py`: `discover_runs`, `load_run`, `compare_runs`, `summary_table`, the figure functions
  and `table_who_adapts`, `table_twins`; `python -m cordonlite.analysis [--compare A B]`.
- New config keys: `[engine]` calibration keys, `costs.pt_attitude_penalty` (default 0). See DEVIATIONS.md, Integrator.

### Final fixer additions

- `run.py`: `variant_suffix(cfg, base, capacity_scale=None, set_overrides=None)`,
  `check_llm_credentials(cfg)`, `calib_value(days, metric, delay="queue")` (`delay` added
  2026-10-07: `"total"` reads `peak_bin_total_delay_by_corridor`), `noise_ids(personas)`;
  `run_simulation(..., variant="")` writes to a temporary folder and renames it on success
  (`<name>.failed` keeps a failed run's partial outputs); `write_scenario` also writes
  `scenario.csv` (`charge_from_day`, `n_days`), which the NetLogo GUI reads when replaying.
- `summary.json`: each day has `peak_bin_delay_wmean` (car-weighted mean of corridor peaks of the
  queue delay; the calibrated metric when `engine.calib_delay = "queue"`; with the default "total"
  it is `peak_bin_total_delay_wmean`, see "Road congestion"); `meta` has `variant` and
  `llm_fallback_share`.
- `llm.py`: `LLMFatalError`, `flexibility_sentence(sched_mult)`, `AnthropicLLM.key_extra()`;
  log records carry `error_kind` (`fatal`, `api`, `refusal`, `invalid`), `shared`, `shared_from`.
- `analysis.py`: `discover_runs(runs_dir, include_netlogo=False, seed=None, include_all=False)`,
  `table_who_adapts(run, base=(6, 10), end=None)`, `twin_summary(run)`,
  `llm_diagnostics(run, rule_run=None)`, `fig_crossings_hist` (was `fig_departure_hist`).
- `memory.AgentMemory.habit_option_id`, `options.pt_depart_min`, `options.skip_cost`,
  `rules.option_code`, `RuleDecider(cfg, noise_ids=None)` (`habit_option_id` and `skip_cost`
  removed with SKIP on 2026-10-09).
- Config keys: `engine.calib_metric`, `costs.skip_vot_hours`, `costs.pt_headway_min`,
  `llm.replicate`, `llm.traits_off_prompt`, `llm.max_consecutive_errors` (`costs.skip_vot_hours`
  retired on 2026-10-09).

### Behaviour recalibration additions

- `options.fee_faced(persona, memory, options, cfg, today=None) -> float`: levied fee of the CAR
  option at the grid-snapped car reference departure (0 for company cars; `today`, added 2026-10-07,
  gives the day-1 rule its public road delays: pass the TodayInfo the options were built with);
  `memory.update_memory(..., fee_faced=None)`.
- Config: `costs.wfh_form` ("spec" | "v3_relative"), `memory.ref_fee_update` gains "faced".
- `python -m cordonlite.run calibrate --seeds 1 2 3`: `data/calibration.json` gains `by_seed`
  (`{"<seed>": record without history}`); `resolve_capacity_scale` prefers the run's seed record.
- `scripts/calibrate_behaviour.py [--stage all|search|select|final|oos|gap|report] [--workers N]` ->
  `data/behaviour_calibration.json`, `docs/calibration_report.md`, `docs/figures/calib_*.png`.
  The JSON gains `out_of_sample` (stage `oos`: chosen point on seeds 6-12, ridge alternatives on
  seeds 4-12, F decomposition), `selection_sensitivity` (strict vs rounded feasibility, overshoot
  bound) and the append-only `search.selection_history`.

### Early-start additions (2026-10-05)

- `types.Persona.early_shift_ok: bool = False` (Layer A constraint, last field): the employer allows the
  earlier working day. Drawn in `persona.build_personas` on stream "A" AFTER every other Layer A draw (one
  uniform per base agent, compared with `persona.early_shift_prob[archetype - 1]`), so no earlier field
  changes; twins copy it. `personas.csv` gains the column.
- Config: `persona.early_shift_prob` (5 entries), `costs.early_start_min` (420), `costs.early_shift_cost`
  (NZ$ a day, x phi(F)), `time.anchor_offsets_min` ([0, 15]); `costs.skip_cost` is 30 (retired with
  SKIP on 2026-10-09).
- `options.early_start_for(persona, cfg) -> int | None`: `costs.early_start_min` when
  `persona.early_shift_ok` and it is earlier than `persona.tstar_min`, else None.
- `options.car_departures(standing_depart_min, cfg, persona=None, today=None)`: with a persona that
  may start early the set also holds `anchor +/- time.anchor_offsets_min` for the reference departure
  of each start (`options.start_anchor_depart(persona, start, cfg, today=None)` = start - free-flow
  time - `initial_buffer_min`, floored to the grid, clipped; since 2026-10-07 also minus the public
  road delay, see "Behaviour builder", options), for the early start and for t*. Option ids stay
  `CAR_hhmm`.
- `options.effective_start(arr, persona, params, cfg) -> (start, early_shift, early, late, schedule_cost)`
  and `options.schedule_against(arr, start, phi_s, a, cfg)`. For CAR and PT options:
  ```
  usual:  c0 = phi * sched_mult * a * (beta_ratio * early0 + gamma_ratio * late0)            against t*
  early:  c1 = phi * sched_mult * a * (beta_ratio * early1 + gamma_ratio * late1) + early_shift_cost * phi
          against costs.early_start_min; used only when c1 < c0 (ties keep t*)
  schedule = min(c0, c1)        # the inconvenience cost is part of gc_parts["schedule"] (GC_PARTS unchanged)
  ```
  PT: the service is the latest one arriving by the start used (both starts are priced).
- `types.Option.start_used_min: int | None` and `Option.early_shift: bool`: the start the option's
  `early_min` / `late_min` refer to (None for WFH and SKIP). `types.MemoryRecord` gains the same two fields.
- `options.car_outcome(persona, engine_row, option_id=None, start_min=None)`: early and late minutes
  against `start_min` (the chosen option's `start_used_min`; None = t*). `non_car_outcome` uses
  `option.start_used_min`. `OUTCOME_ROW_COLUMNS` and `outcomes.csv` gain `start_used_min, early_shift`;
  `decisions.csv` gains the same two columns. Trigger T3 reads the record's `late_min`, so lateness is
  measured against the start actually used.
- `summary.json`: each day has `early_shift` (commuters whose day is measured against the early start, car
  or PT) and `early_shift_cars`; `meta` has `early_shift_ok_agents` and `early_shift_days_total`.
  `analysis.summary_table` adds `early_shift_share_d<day>`.
- Prompt (`llm.render_user_prompt`): the situation section states "Your employer lets you work 07:00 to
  15:00 instead of your usual hours on any day you choose." (times from `costs.early_start_min`, an 8-hour
  day) only when `early_start_for` is not None. The options table and the memory table have a `start time`
  column before the arrival column; "x min early / late" refers to that start, and the closing line says
  so. No GC, no archetype label. MockLLM scores the same `gc_parts`.
- `rules.explain`: an early-start option is described as "drive at hh:mm for the early start".
- `scripts/calibrate_behaviour.py`: metrics gain `end_skip`, `base_early`, `end_early`,
  `base_early_of_cars`, `end_early_of_cars`, `peak_cross_change` (08:00-09:00 crossings, days 21-30 vs
  6-10) and `pre0730_cross_change`; the JSON gains `early_start`, `skip` and `early_start_summary`;
  `gap_sensitivity` now holds sensitivities to the fixed assumptions. The early-start assumptions and the
  SKIP cost are never searched.

### NetLogo network model (2026-10-06)

Additive; no engine, run or config change. Owner: prep builder (`prep/build_netlogo_layers.py`) and
the GUI of the NetLogo model `netlogo7/cordon_lite.nlogox` (merged on 2026-10-06 with the
NetLogoEngine model; one file). Neither engine path reads the files below.

```python
# prep/build_netlogo_layers.py   CLI: python -m prep.build_netlogo_layers [--config] [--out-dir netlogo7/gis]
#                                                                         [--roads-out PATH] [--buildings PATH]
load_buildings(path, cfg) -> gpd.GeoDataFrame             # footprints in EPSG cfg.prep.crs_epsg, made valid
building_points(buildings, cordon) -> (gpd.GeoDataFrame, pd.DataFrame)
    # footprints whose point_on_surface lies inside the cordon (inside_mask), and BUILDINGS_COLUMNS
roads_for_shapefile(roads) -> gpd.GeoDataFrame            # ROAD_FIELDS renamed (<= 10 characters), order kept
build_layers(cfg, out_dir=None, buildings_path=None, roads_out=None) -> dict   # counts, paths
```

| File | Content |
|---|---|
| `netlogo7/gis/tomtom_major_roads.shp` (default: in `--out-dir`) | every segment of the GeoPackage layer, same order and geometry; fields `segment_id` (newSegmentId), `speedLimit`, `frc`, `streetName`, `distance`; EPSG:2193, UTF-8 `.cpg` |
| `netlogo7/gis/cordon.shp` | `load_cordon(cfg)` (the geometry of `data/cordon.geojson`) |
| `netlogo7/gis/cbd_buildings.shp` | footprints inside the cordon; fields `building_i` (LINZ building_id), `use` |
| `netlogo7/gis/cbd_buildings.csv` | `building_id, x_nztm, y_nztm, use`: one point inside each footprint above |

NetLogo model (NetLogo 7.0.4, GUI; extensions csv, table, gis, nw). Reads a run folder
(`corridors.csv`, `agents.csv`, `fees.csv`, `scenario.csv`, `plans.csv`, and when present
`personas.csv` for `origin_id`, `outcomes.csv` for PT minutes and, since 2026-10-07, the four road
scenario files), `../data/origins.csv`, `../data/gates.csv`, the roads shapefile and
`netlogo7/gis/`; with road files also `../data/section_segments.csv` (section -> TomTom segments,
for the road colours) and `../data/road_sections.csv` (`km`, `mwy` for the LoS monitors), which
must come from the prep that made the run. Writes nothing. The road part of the GUI is described
under "Road congestion", NetLogo.

- `setup` (since 2026-10-09 `setup-run scenario-dir`, see "Peak charge, fee response and NetLogo choosers"): scenario files; `build-network` (node per 1 m-rounded segment end, coinciding ends
  dropped, fastest parallel segment kept, giant component only: 28,507 nodes, 30,835 roads; link
  variables `tt` = free-flow minutes and `tt-in` = `tt` + `cordon-exit-penalty` (60) on a road with
  an end outside the cordon; nodes flagged `in-cordon?` with `gis:intersects?`; `main-inner` = the
  largest connected set of cordon nodes); one gate turtle per prep gate used (`origins.csv` gate of
  the agent's origin, via `personas.csv` origin_id or the origin coordinates; the corridor point
  when the agents are not prep origins); `assign-workplaces` (uniform draw over the buildings,
  `random-seed 2027` inside `with-local-randomness`, agent_id order; building node = nearest node of
  `main-inner`); routes home -> outside end of the gate segment -> gate point on `tt`, and gate
  point -> inside end -> building node on `tt-in` (the car parks there; the commuter is drawn at
  the building point); clock from `[time]` of the run's `config_snapshot.toml` (330 / 720 without it)
  (`nw:turtles-on-weighted-path-to`; the weight name must be a literal string in NetLogo 7).
- `start-day d` takes day d's rows from `day-plans` (`read-plans` reads `plans.csv` once in `setup-run`;
  before 2026-10-10 it read `plans_dayNN.csv`: demo plans only when the folder has no `plans.csv`; a
  folder with plans that lacks day d gives a message), runs the
  engine code of `cordon_lite.nlogox` (`simulate-queues`: `road-arrivals`, then `point-queues`),
  so `dep`, `road-delay`, `gate-arr`, `gate-exit` (`-1` = not served by `sim-end-cap-min`) and
  `arr` equal the run's `outcomes.csv`; then `plan-drives` and `index-road-entries`.
- `road-arrivals [cars]` and `point-queues [arrivals]` are the engine core used by both `run-day`
  (headless) and `simulate-queues` (GUI): `road-arrivals` takes `[agent_id depart_min]` pairs and
  reports `[delays rows times extras counts]` (see "Road congestion", NetLogo); `point-queues` takes
  arrivals `[gate-arrival agent_id corridor_id]` and reports `[exits profile last-minute]`.
- `go` advances `clock` by 1/`steps-per-minute` (4: 1 tick = 15 s; `start-day` resets the counter
  to the steps since `sim-start-min`) and draws every commuter with `state-at clock` (`home`,
  `driving`, `queued`, `transit` (PT), `work`). The day ends 2 minutes after the last arrival (at
  `sim-end-cap-min` if a car is never served); `go` then stops unless the `keep-going?` switch is
  on. `finish-day` (button "skip to end of day") jumps to the end of the day. Since 2026-10-09 both
  start the day `next-day-to-show` reports, inside the days `charge-on` picks (see the
  section "Peak charge, fee response and NetLogo choosers"). Queued cars are red,
  `queue-spacing-m` = max(15, vehicles per agent x 7 m / 2 lanes) (70 m at 950 agents, 20 cars per
  agent; about 220 m at 300), and `update-tags` labels each corridor with its queue in the City
  centre view; `set-map-view "Auckland" | "City centre"`.
- Coordinates: `gis:set-world-envelope` then `map-env = gis:world-envelope`; `map-xy` / `nztm-of`
  are the linear map `gis:location-of` uses (`gis:set-transformation` rescales and is not used).
- Check: `python scripts/check_network_model.py [--run-dir DIR] [--days 1 11] [--views DIR]
  [--view-times HH:MM ...] [--netlogo-home PATH] [--json OUT]` (own process, exit code 0 when every
  check passes; the road checks are listed under "Road congestion", NetLogo);
  `tests/test_network_model_netlogo.py` (`@pytest.mark.netlogo`; builds an 11-day R-clock run in
  tmp_path with roads on and with roads off and checks days 1 and 11); `tests/test_prep_layers.py`.

## Road congestion (2026-10-07 to 2026-10-09)

Roads before the gate are congested in both engines, motorways break down, the default run has 950
agents, and runs write V/C- and speed-based Level of Service (LoS) outputs. Code: `cordonlite/roads.py`
(the one place for the road rules and the LoS definitions), `prep/build_roads.py`,
`prep/fetch_nzta.py`; changes in `config.py`, `engine.py`, `run.py`, `options.py`, `memory.py`,
`types.py`, `llm.py`, `analysis.py`, `netlogo7/cordon_lite.nlogox` and the check scripts. Road
congestion draws no random numbers (no new stream key). PyEngine and NetLogoEngine stay
byte-identical apart from the engine label.

Off-switches (identity with the earlier model tested for each):
- `road.enabled = false`: no road scenario files, both engines drive free flow and the gate queue is
  the only congestion (the model of 2026-10-06 at the same settings); the additions are inert
  (`road_delay_min` 0 for cars, road delays 0 and LoS keys null in `summary.json`, header-only
  `road_entries.csv`, `road_los.csv`, `los_summary.csv`; the prompt text is cl-v1's, only
  `template_id` reads cl-v2).
- `road.mwy_breakdown = false`: the road files and results of 2026-10-07 (plain BPR on every road).
- Prep data without `profile_id` / `cap_drop`: one-profile files; every section on profile 0 with
  `cap_drop = road.mwy_capacity_drop` gives exactly the results of the one-profile model.

### Decisions (the user's)

Fixed by the authors; never calibrated or searched.
1. Roads are congested in both engines, which stay output-identical: a car's time from home to its
   gate depends on when it leaves, and agents are told the road delay. [author decision 2026-10-07]
2. Congestion = background traffic from the SSC2026 AT/NZTA ADT counts plus the commuter agents' own
   cars (one agent = `agents_represented / n_agents` cars), so a charge that removes commuter cars
   eases the roads they used. [author decision 2026-10-07]
3. The capacity calibration targets 15 min of TOTAL delay, gate queue plus road delay
   (`engine.calib_delay = "total"`, `calib_target_peak_delay_min = 15`), re-confirmed after the
   motorway breakdown change. [author decision 2026-10-07, re-confirmed 2026-10-08]
4. 950 agents, 5% of the 19,000 AM charged vehicles (one agent = 20 cars), with 95 twins (10%).
   [author decision 2026-10-08]
5. Motorway capacity, time profile, breakdown window and capacity drop come from NZTA TMS counts:
   the 2024 quarter-hourly weekday counts (May, August, November) for the profiles and windows, and
   the weekday daily volumes of 2025-10 to 2026-09 to scale them to 2025-26. [author decision 2026-10-08]
6. A speed-based LoS is reported next to SSC2026's V/C-based LoS, which is kept unchanged for
   comparability. [author decision 2026-10-08]
7. Stated as a limitation, not modelled: NZTA counts measure throughput, not demand. They give when a
   motorway breaks down and recovers, its pre-breakdown capacity and its discharge rate, but not the
   demand queued behind the bottleneck; with `road.mwy_jam_speed` capping broken-down speed, the
   measured capacity drop rarely sets the speed, so the counts decide when motorways jam, not how
   badly. [author decision 2026-10-08]

### Configuration

`[road]` (new section; `RoadConfig`, `cfg.road`; validated by `load_config`):

| Key | Default | Meaning |
|---|---|---|
| `enabled` | true | false = free-flow roads (no road scenario files) |
| `bpr_alpha` | 0.15 | f = 1 / (1 + alpha x (V/C)^4); >= 0 |
| `bpr_beta` | 4 | only 4 (the engines compute `(x * x) * (x * x)`); other values are rejected |
| `speed_floor` | 0.18 | lowest speed factor, in (0, 1] |
| `flow_window_min` | 15 | W: a section's commuter flow = its commuter entries in the last W minutes; int >= 1 |
| `mwy_breakdown` | true | motorway flow breakdown rule; false = plain BPR on motorways |
| `mwy_breakdown_vc` | 1.0 | breakdown at V/C >= this |
| `mwy_recover_vc` | 0.95 | a usual-traffic window ends at the first later minute with V/C < this; in (0, mwy_breakdown_vc] |
| `mwy_capacity_drop` | 0.10 | capacity drop in broken-down flow on sections without an NZTA site; in [0, 1) |
| `mwy_jam_speed` | 0.45 | highest speed factor in broken-down flow; in [speed_floor, 1] |

`[prep]` road keys (`PrepConfig`; read only by `prep.build_roads`):

| Key | Default | Meaning |
|---|---|---|
| `roads_shp` | `netlogo7/gis/tomtom_major_roads.shp` | TomTom major roads, field `segment_id` = newSegmentId, EPSG:2193 |
| `adt_geojson` | `../../SSC2026/netlogo/Data/Average_Daily_Traffic_Counts.geojson` | AT/NZTA count points, EPSG:4326 |
| `adt_match_m` | 30.0 | a count matches the nearest edge of the same normalised street name within this |
| `adt_propagate_m` | 1000.0 | a count holds along the same street this far through the network |
| `road_inbound_share` | 0.6 | inbound share of the two-way AM peak-hour flow |
| `road_peak_ratio_default` | 0.096 | AM peak hour / ADT where the count has no AM peak of its own |
| `road_commuter_car_share` | 0.8 | car share used to net the commuters out of the counts |
| `road_tti_target` | 1.714 | travel time index target: TomTom Traffic Index, Auckland 2025, AM rush hour |
| `road_tti_window` | [480, 540] | departures over which the target is matched (08:00-08:59) |
| `road_cap_k_bounds` | [0.02, 0.3] | bisection bracket of k |
| `road_adt_floor_pct` | 5.0 | capacity floor: this percentile of `adt_dir` within the frc; <= 0 no floor, > 100 an error in prep |
| `road_tti_exclude_mwy` | true | match the target on the non-motorway part of each trip |
| `road_profile_start_min` | 360 | first 15-min bin of `road_profile` |
| `road_profile` | 18 values | default time profile: ratio to the AM peak-hour mean, 15-min bins from 06:00 |

Changed elsewhere:
- `engine.calib_delay` (new): `"total"` (default; gate queue + road delay) or `"queue"` (gate queue
  only, the model before 2026-10-07; the same thing with roads off). `calib_target_peak_delay_min`
  (15.0) measures the delay it names.
- `engine.min_capacity_vph` (new): 950.0, the gate capacity floor in vehicles/h, independent of
  n_agents; 0 = use `min_capacity_per_min` (agents/min). Formula under "Integrator".
- `run.n_agents`: 950 (300 before 2026-10-08). `persona.n_twins`: 95 (30 before; 10% of n_agents).
- `llm.template_id`: `"cl-v2"` (`config.TEMPLATE_ID`; `load_config` accepts no other value, so the
  `config_snapshot.toml` of a cl-v1 run no longer loads). Since 2026-10-09 `"cl-v3"`; snapshots
  naming `cl-v1` or `cl-v2` load again (`config.RETIRED_TEMPLATE_IDS`), but `LLMDecider` refuses any
  template other than `cl-v3`.
- `time.initial_buffer_min` (10) keeps its value; the reference departure now subtracts the public
  road delay too (`options.start_anchor_depart`).

### Prep: CLI, inputs and outputs

`python -m prep.fetch_nzta [--out data/nzta] [--cache DIR] [--offline]` (run once, needs internet
unless `--offline` with a complete `--cache`): NZTA Traffic Monitoring System counts of 36 motorway
sites on the CBD approaches, NZTA Open Data, CC BY 4.0 (attribution text
`prep.fetch_nzta.ATTRIBUTION`, also in `data/nzta/README.md` and `road_meta.json` `nzta.attribution`).
A rerun on the same downloaded data writes identical files.

| `data/nzta/` file | Columns |
|---|---|
| `tms_sites.csv` | `site_ref, description, corridor, direction, flow_direction, kind, cbd_bound, cbd_role, lanes, lat, lon, x_nztm, y_nztm, note`: 36 sites; corridor `SH1_north`, `SH1_south`, `SH16`, `SH20` (mainline), `SH20_to_SH16` (link), `CBD_exit_*` (ramps) |
| `tms_daily_weekday.csv` | `site_ref, local_date, flow_direction, lane, class, count`: vehicles per day by lane and class (light, heavy), Mon-Fri 2025-10-01 to 2026-09-30 |
| `tms_15min_am_2024.csv` | `site_ref, local_date, time, flow_direction, lane, class, count`: vehicles per quarter hour (NZ local start 05:00 to 10:45), Mon-Fri of May, August and November 2024 |
| `tms_15min_daily_2024.csv` | `site_ref, local_date, flow_direction, lane, class, count, n_qh`: full-day totals of the same records, `n_qh` = quarter hours present |
| `README.md` | sources, licence and attribution, filters, row counts, coverage |

`python -m prep.build_roads [--config config.toml] [--out-dir data]` (run after `prep.build_inputs`;
no network; about a minute). Inputs: `prep.roads_shp`, `prep.adt_geojson`, the cordon
(`prep.cordon_gpkg`, else `../../SSC2026/netlogo/Data/roads/akl_CBD_SA3.gpkg`, else
`data/cordon.geojson`), `data/origins.csv`, `data/nzta/*`. It rebuilds the prep paths with the
`build_inputs` functions and stops (ValueError naming the columns) unless they reproduce
`data/origins.csv` exactly. LF line endings; a rerun writes byte-identical files; no run time in
any file. Public API in the module docstring (`norm_name`, `match_counts`, `build_sections`,
`site_breakdown`, `nzta_sites`, `map_sections_to_sites`, `apply_nzta`, `adt_floors`, `capacity_adt`,
`is_motorway`, `usual_breakdown`, `calibrate_k`, `run_build_roads(cfg, out_dir=None) -> dict`, `main`).

A road SECTION is a maximal chain of consecutive graph edges on the pre-gate routes (origin node to
the inside end of its gate segment, the edges whose minutes add up to `fftt_to_gate_min`) used by the
same set of origins with the same frc, speed limit, normalised street name and count values;
`section_id` 0.. by first appearance walking the origins in origin_id order, then seq. The leg after
the gate is not sectioned (free flow).

| `data/` file | Columns / content |
|---|---|
| `road_sections.csv` | one row per section, sorted by `section_id` (columns below) |
| `origin_sections.csv` | `origin_id, seq, section_id`: each origin's pre-gate route, seq 0 at the origin. Per origin the sum of `ff_min` equals the unrounded `fftt_to_gate_min` (checked: within 3e-14; within 0.0005 of the 3-dp `origins.csv` value) |
| `section_segments.csv` | `section_id, seq, segment_id` (TomTom newSegmentId in travel order; the NetLogo GUI colours roads with it) |
| `road_profile.csv` | long format `profile_id, minute, r`: 1440 rows per profile, r with 6 dp. Profile 0 = default (`prep.road_profile`: value at each bin centre, linear between centres, constant after the last, a ramp down to 0.15 x the first value at 05:00 and 0.15 x it before); 1 to 19 = NZTA sites (`road_meta.json` `profiles.site_of`) |
| `road_meta.json` | parameters and results: `k` (read by `roads.road_k`), `k_bounds`, `k_iterations`, `k_probes`, `tti_target`, `tti_achieved`, `tti_window`, `tti_match`, `tti_by_hour`, `tti_0730`, `tti_by_corridor`, the prep and road keys used, counts (`n_sections`, `sections_by_source`, `counts`, `edges`, ...), `capacity_floor`, `motorway` (rule, names, windows, broken share, TTI by class), `nzta` (rule, sites, mapping, `mapping_dist_m`, `farthest_sections`, `dist_m_by_section`, attribution), `profiles`, `checks`, `inputs` (paths relative to cordon_lite, sizes, modification dates) |
| `road_report.md` | human-readable summary: capacity floor, TTI under usual traffic, count matching, V/C, motorway breakdown, NZTA sites and mapping, commuter share, busiest sections, assumptions |

`road_sections.csv` columns (`prep.build_roads.SECTIONS_COLUMNS`):

| Column | Meaning |
|---|---|
| `section_id, n_seg, ff_min, km` | id; graph edges; free-flow minutes (full precision); length |
| `frc, speed_limit, street_name` | TomTom values of the first edge |
| `adt_twoway, adt_dir` | two-way ADT and the inbound direction's ADT: an AT count is a two-way total (`adt_dir = adt / 2`) unless its road_name names a direction (EASTBOUND, ...); a state-highway carriageway or ramp record counts one direction (`adt_twoway = 2 x adt`). AT counts below 0.25 x a more recent same-street count within `adt_propagate_m` (stale) and bus-only ramp records are not used |
| `adt_source` | `count` (an edge holds a matched count), `propagated` (same street within `adt_propagate_m`), `default` (median two-way ADT of matched edges by frc and speed band), `nzta` (motorway section mapped to an NZTA site) |
| `peak_ratio` | AM peak-hour volume / ADT of the count when its peak hour starts 06:00-09:45, else `road_peak_ratio_default`; clipped to [0.05, 0.20] |
| `cap_vph` | `k x max(adt_dir, adt_floor[frc])`, 3 dp; `adt_floor` = the `road_adt_floor_pct`-th percentile of `adt_dir` over all sections of the frc (unweighted, before k, inside the k calibration). `nzta` sections: the site's capacity |
| `obs_peak_vph` | observed inbound AM peak-hour flow: `road_inbound_share x peak_ratio x adt_twoway`; `nzta` sections: the site's peak-hour flow |
| `am_volume_veh` | `obs_peak_vph x (sum of r over minutes 360..599) / 60`, with the section's profile |
| `expected_commuter_veh` | `agents_represented x road_commuter_car_share x` (origin weight through the section / total origin weight) |
| `phi` | `min(1, expected_commuter_veh / am_volume_veh)`: the commuters' share of the counted volume |
| `bg_peak_vph` | `obs_peak_vph x (1 - phi)`: background traffic (the counts minus the commuters) |
| `w_factor` | `min(1, am_volume_veh / expected_commuter_veh)`: weight of a commuter entry (below 1 only where the commuters would exceed the counted volume) |
| `n_origins, x_mid, y_mid` | prep origins whose route uses it; NZTM point at half its length along travel |
| `mwy` | 1 = motorway mainline: frc 0 or a street name with the word Motorway, not a ramp by name (Entry, Exit, Ramp), signed at least 70 km/h |
| `bd_on, bd_off` | usual-traffic breakdown window [bd_on, bd_off), minutes; -1, -1 = none (always for mwy 0). `nzta` sections: the site's window; other motorway sections: `roads.breakdown_windows` of `obs_peak_vph x r / cap_vph` with `road.mwy_breakdown_vc` and `mwy_recover_vc` |
| `profile_id` | time profile in `road_profile.csv` (0 = default; the site's for `nzta` sections) |
| `cap_drop` | capacity drop in broken-down flow: the site's measured drop for `nzta` sections of a breakdown site (a saturated site: at least `road.mwy_capacity_drop`); `road.mwy_capacity_drop` otherwise |

k: bisected (30 fixed steps, 6 dp) in `road_cap_k_bounds` so that the origin-weighted mean travel time
index of a probe car leaving every minute of `road_tti_window`, under usual traffic (`v =
obs_peak_vph x r`, with the breakdown rule), equals `road_tti_target`; with `road_tti_exclude_mwy`
the index is taken over the non-motorway part of each trip (time on mwy 0 sections over their
free-flow time) and the `nzta` sections are held fixed.

NZTA site analysis (`nzta_sites`, `site_breakdown`; constants in `prep/build_roads.py`, each with
its source tag there): a valid site is a CBD-bound through-lane site with at least 20 valid 2024
weekdays (lane outages and doubled site-months excluded). q(t) = mean weekday flow by quarter hour,
veh/h, all lanes and classes, 05:00 to 10:45; q_max at t_max; plateau = median of q from t_max + 30
min to 09:30; delta = 1 - plateau / q_max. Breakdown when saturated (q >= 0.95 q_max for at least 60
consecutive minutes; onset = the start of that run; drop = max(delta, `road.mwy_capacity_drop`)) or
when delta >= 0.05 (onset = the first bin after t_max with q <= q_max (1 - delta / 2); drop =
delta), in both cases only when the maximum or the run starts by 07:00 (`NZTA_ONSET_LATEST_MIN`).
Recovery `bd_off`: searching from 09:30 (`NZTA_RECOVERY_FROM_MIN`), the start of the first bin from
which two consecutive bins are each below 0.95 x plateau or above plateau + 0.5 x (q_max - plateau)
(`NZTA_RECOVER_RISE`); 660 (11:00) when none by 10:45. Capacity = q_max x scale, scale = median
weekday daily volume 2025-26 (no lane outage, no holiday) / median valid 2024 day of the site (else
the corridor's median scale, else 1). `obs_peak_vph` = the peak-hour mean of the scaled q; the site
profile = scaled q / `obs_peak_vph`, linear between bin centres, the default profile scaled to match
before the first and after the last centre. Mapping (`MWY_NAME_CORRIDOR`,
`NZTA_MAP_M = None`): each mwy 1 section takes the nearest valid site of its motorway's corridor at
any distance (Northern Motorway, Harbour Bridge included: SH1_north; Southern: SH1_south;
Northwestern: SH16; Southwestern and "20": SH20); Upper Harbour Motorway, Airport Motorway and George
Bolt Memorial Drive have no site and keep `k x max(ADT, floor)`, profile 0 and the computed window. A
motorway name missing from the map stops the prep. `NZTA_ONSET_LATEST_MIN`,
`NZTA_RECOVERY_FROM_MIN` and `NZTA_RECOVER_RISE` set to None and `NZTA_MAP_M` to 6000 restore the
literal rule of the 2026-10-08 design (SPEC3); road_meta.json and road_report.md list each site's
literal-rule window next to the one used.

Current data (`data/road_meta.json`, `data/road_report.md`; fixed by the data and the prep):
- 5,903 sections on the pre-gate routes of the 3,000 prep origins (count 1,953, propagated 3,460,
  default 258, nzta 232); 142,470 `origin_sections.csv` rows (47.5 sections per origin, max 124);
  19,517 `section_segments.csv` rows; 20 profiles (0 default, 1 to 19 sites).
- Counts: 13,835 points, 13,717 with ADT > 0; 3,179 matched (AT 2,741, SH carriageway 230, SH
  ramp 208); 66 stale AT counts and 8 bus-ramp records not used.
- k = 0.076999. Usual-traffic TTI, departures 08:00-08:59: non-motorway 1.714 (achieved 1.713983,
  `tti_match = "non_motorway"`), motorway 2.032, whole trip 1.927.
- Capacity floor (adt_dir / veh/h): frc 0 15,989.75 / 1,231.2; frc 1 6,432 / 495.3; frc 2 4,627.5 /
  356.3; frc 3 2,566.5 / 197.6; frc 4 1,851 / 142.5. 280 sections raised (1.39% of origin-weighted
  pre-gate minutes).
- Motorway mainline: 285 sections, 147.05 km, 230 with a usual window. NZTA: 36 sites, 19 valid, 12
  with breakdown; 232 sections take a site's values (98.9% of origin-weighted motorway minutes).
  Site windows: `road_meta.json` `nzta.sites`.

### Run scenario files (road)

Written by `roads.write_road_scenario(run_dir, personas, cfg, data_dir=None)` (called by
`run.write_scenario` when `road.enabled`; `roads.remove_road_scenario` deletes them otherwise). All
four or none. A missing prep file raises FileNotFoundError naming `python -m prep.build_roads`.

| File | Columns / content |
|---|---|
| `road_sections.csv` | `section_id, ff_min, cap_vph, bg_peak_vph, obs_peak_vph, w_factor` (`roads.ROAD_SECTIONS_COLUMNS`), then `mwy, bd_on, bd_off` with `road.mwy_breakdown`, then `profile_id` (data with NZTA columns) and `cap_drop` (with both). Only the sections used by the run's agents, sorted by `section_id`; values copied round-trip exact from `data/road_sections.csv` |
| `agent_routes.csv` | `agent_id, seq, section_id`: each persona's route from `data/origin_sections.csv` via `origin_id`; an agent without rows drives free flow |
| `road_profile.csv` | `minute, r` (one profile, profile 0) or `profile_id, minute, r` (the profiles the sections use); 1440 rows per profile |
| `road_params.csv` | `key, value`: `bpr_alpha`, `bpr_beta`, `speed_floor`, `flow_window_min`, `vehicles_per_agent` (= `agents_represented / n_agents` written with Python `repr`: 20.0 at 950 agents; both engines read it, the NetLogo GUI never recomputes it), and with `road.mwy_breakdown` `mwy_breakdown` (1), `mwy_breakdown_vc`, `mwy_recover_vc`, `mwy_capacity_drop`, `mwy_jam_speed` |

Breakdown windows and drops in the run: `nzta` sections keep the data's window and `cap_drop`; every
other motorway section gets the window recomputed with the run's `mwy_breakdown_vc` and
`mwy_recover_vc` (equal to the prep columns at the defaults) and `road.mwy_capacity_drop`. So
`--set road.mwy_recover_vc` or `road.mwy_capacity_drop` changes only motorway sections without a
site; `road.mwy_breakdown_vc` also sets the V/C trigger, and `road.mwy_jam_speed` the jam speed, of
every motorway section.

`roads.read_road_scenario(dir) -> RoadScenario | None`: None when no road file exists; ValueError
when only some exist or values are invalid (`cap_vph > 0`; `bpr_beta == 4`; minutes 0..1439 per
profile; seq 0..n-1; mwy 0/1; `bd_on, bd_off` = -1, -1 or 0 <= bd_on < bd_off <= 1440; `cap_drop` in
[0, 1)). `engine.read_scenario` stores it as `Scenario.road` (None = free-flow roads) and also
rejects routes of unknown agents.

### Engine semantics (both engines)

```
per run, section s:
  fpe_s  = ((vehicles_per_agent * w_factor_s) * 60) / W       # veh/h per commuter entry; W = flow_window_min
  keep_s = 1 - cap_drop_s                                     # computed once at load (NetLogo sec-keep)
speed factor of s at integer minute m, c = commuter entries into s at minutes m-W .. m-1:
  v = bg_peak_vph_s * r[profile_id_s][m] + c * fpe_s          # r[...][1439] for m > 1439
  x = v / cap_vph_s
  broken = mwy_breakdown and mwy_s == 1 and ((bd_on_s <= m and m < bd_off_s) or x >= mwy_breakdown_vc)
  if broken: y = x / keep_s; f = 1 / (1 + alpha * ((y * y) * (y * y))); if f > mwy_jam_speed: f = mwy_jam_speed
  else:      f = 1 / (1 + alpha * ((x * x) * (x * x)))
  if f < speed_floor: f = speed_floor
one day (today's CAR agents; a car without a route has road_delay_min 0):
  each car: el = 0.0, k = 0, ffsum = sum of ff_min over its route, added in seq order
  for m = earliest departure upwards while a car is unfinished:
    for each car with d + floor(el) == m, in ascending agent_id:
      while the car is unfinished and d + floor(el) == m:
        s = route[k]; f = speed factor of s at m; record one entry of s at minute m
        el = el + ff_min_s / f; k = k + 1
    (an unfinished car waits for minute d + floor(el), always later)
  road_delay_min  = max(0, floor(el - ffsum + 0.5))
  gate_arrive_min = d + fftt_to_gate_min + road_delay_min       # then the point queue, unchanged
```

Entries recorded at minute m are never read at minute m, so the order of cars within a minute does
not change results. Only `+ - * /`, floor and comparisons in this order (no pow, no numpy or pandas
reductions, no NetLogo `^`, `sum`, `mean` or `round` in anything that feeds outputs); rounding is
`floor(x + 0.5)` in both engines. The static window gives the persistence of a breakdown, the
trigger (x >= `mwy_breakdown_vc` with today's commuters) lets extra commuters start one early; the
charge cannot shorten a usual window. The leg after the gate stays free flow and PT is not affected
(rail and busway assumption). Reference implementation `roads.simulate_roads(cars, road) ->
RoadDay(delay_min, extra_min, entries)` (cars = `(agent_id, depart_min)`); NetLogo port
`road-arrivals`. The outcome column `road_delay_min` sits after `depart_min`; `DayResult.road`, the
exchange file `road_dayNN.csv` and the run file `road_entries.csv` carry `day, section_id, minute,
entries` (int, non-zero rows, sorted by `section_id, minute` within a day).

### What agents know (Python only)

- `run.public_road(road, personas, cfg, entries=None) -> dict[agent_id, tuple[float, ...]]` gives
  `TodayInfo.public_road`: per persona one value per departure minute `time.sim_start_min ..
  time.depart_latest_min` (index `depart_min - sim_start_min`), the unrounded road delay `el - ffsum`
  of a probe car on its route that adds no load. Only the minutes of `options.departure_grid(cfg)`
  (06:00 to 09:45 every 15 min) are computed; the others hold NaN, so a read off the grid fails
  loudly; zeros for an agent without a route. Table: `roads.speed_table(road, entries,
  range(sim_start_min, sim_end_cap_min + 300 + 1))`; `entries=None` = usual traffic, `v =
  obs_peak_vph x r[profile][m]` (the counts: background plus the usual commuters) with the same
  breakdown rule; a day's entries = that day's engine traffic. `roads.route_delays` follows the
  engine's traversal (entry minute -> that minute's f; past the table's end its last minute), so a
  table built from a day's entries reproduces every car's float extra exactly.
- Day 1: usual traffic (`public_road_source = "usual"`; commuters know usual traffic); day >= 2:
  yesterday's road entries (`"yesterday"`); `{}` with roads off. Every whole-minute use (expected
  gate arrival, start anchor, prompt) rounds once with `floor(R + 0.5)`, the engine's rounding.
- `types.RoadDelayInfo = Mapping[int, tuple[float, ...]]`; `TodayInfo.public_road: RoadDelayInfo =
  {}`, `TodayInfo.public_road_source: str = "usual"` (`"usual"` | `"yesterday"`).
- `Option.expected_road_delay_min: float | None = None`: R of a CAR option (0.0 with roads off), in
  `expected_gate_arrive_min` (as `floor(R + 0.5)`), `expected_travel_min` and `gc_parts["time"]`;
  None for other modes. GC formula under "Behaviour builder", options.
- `MemoryRecord.road_delay_min: float | None = None` (as driven, from the outcome row) and
  `MemoryRecord.expected_road_delay_min: float | None = None` (the chosen option's R); CAR only,
  filled by `memory.record_from_outcome`. The delay ratio EMA stays queue-only.
- `options.OUTCOME_ROW_COLUMNS` gains `road_delay_min` after `depart_min`; `car_outcome` takes it
  from the engine row (0 when the row has none), non-car rows leave it empty.
- Triggers (no code change): T3 (late) and T5 (travel against expected travel) include the road
  delay through `late_min` and `expected_travel_min`.

### Prompt (template cl-v2)

`llm.render_user_prompt`; the traffic parts appear only when `today.public_road` is non-empty (in a
run: `road.enabled`), otherwise the user message is the cl-v1 text.
1. Situation: "With no traffic the drive takes about N min: A min to reach the city-centre boundary
   and B min from there. In the morning, traffic on the way and a queue at your entry point can make
   it longer." (replaces the "With no queues ..." sentence).
2. TODAY, day 1: "Usual traffic on your route, by time of leaving home: leaving hh:mm: N min, ..."
   then the existing "No information on yesterday's queues at your entry point is available.".
   Day >= 2 with a queue profile: "Yesterday's traffic on your route and queue at your entry point,
   by time of leaving home: leaving hh:mm: N min traffic + M min queue, ..."; day >= 2 without one:
   "Yesterday's traffic on your route, by time of leaving home: ..." and the no-queue line. The
   departures are those of the CAR options.
3. Options table: column `traffic delay` after `leave home`, before `expected queue`. Memory table:
   `traffic delay` after `left home`, before `queue at entry`.
4. Road delays are shown in whole minutes `floor(R + 0.5)` (`_road_mins`), the rounding built into
   the row's crossing time and arrival; queue minutes keep `_mins`.

The system prompt, the schema and the `llm_calls.jsonl` record format are unchanged; records carry
`template_id = "cl-v2"`, which enters the cache key. MockLLM scores the same `gc_parts` (time
includes R). `scripts/make_example_prompt.py` titles the example with `cfg.llm.template_id`. The
traffic parts are unchanged in `cl-v3` (2026-10-09), which records carry since.

### Run outputs (road)

`run.RUN_OUTPUTS` and `analysis.OUTPUT_FILES` gain `road_entries.csv`, `road_los.csv` and
`los_summary.csv`; all three exist in every run folder (header only without roads), so py and NetLogo
folders hold the same file set.

| File | Columns / content |
|---|---|
| `road_entries.csv` | `day, section_id, minute, entries`: commuter entries per section and minute, all days, non-zero rows |
| `road_los.csv` | one row per section of the run's `road_sections.csv` x period x bin, in that order (columns below) |
| `los_summary.csv` | `day, bin, group, share_EF, vc_mean, speed_factor_mean, veh_km, share_EF_speed, share_congested_AT`: every run day x the five bins x group (`motorway`, `other`, `all`, `corridor k`); shares and means vehicle-km weighted over the group's section-minutes in the bin; `veh_km` = sum of v x km / 60 over the bin's minutes (the weight to pool days); NaN when a group has no traffic |

`road_los.csv` columns (`roads.ROAD_LOS_COLUMNS`):

| Column | Meaning |
|---|---|
| `section_id, street_name, frc, mwy, corridor, km` | from `data/road_sections.csv` (`mwy` the prep column, also with `road.mwy_breakdown` off; `corridor` = the corridor with the most origin weight among the prep origins using the section, ties to the lowest id, -1 none; `km` empty for data without it, which then weight by `ff_min`) |
| `period` | `d6-10`, `d21-30` (each when the run has all its days), else `all` |
| `bin` | `06:00-07:00`, `07:00-08:00`, `08:00-09:00`, `09:00-10:00`, `07:00-09:00` |
| `vc_mean`, `vc_max` | mean and largest V/C over the section-minutes of the period's days |
| `speed_factor_mean` | mean speed factor |
| `share_EF` | share of minutes at V/C grade E or F |
| `los` | V/C grade of `vc_mean`; F when broken down in at least half the minutes |
| `commuter_veh` | commuter cars entering per day: entries x `vehicles_per_agent`, mean over the period's days (not x `w_factor`, so it can exceed the engine's load where `w_factor < 1`) |
| `usual_vc_mean` | mean V/C under usual traffic, same bin |
| `speed_los` | speed grade of `speed_factor_mean`; F when broken down in at least half the minutes |
| `share_EF_speed`, `share_congested_AT` | share of minutes at speed grade E or F; share of minutes with f < 0.5 |

Floats in both files are rounded to 4 dp. Both are computed after the run by
`run.los_for_run(res, cfg, run_dir, road_entries) -> roads.LosOutputs` from the run folder's road
files, `road_entries.csv` and the section descriptions in `run.data_dir`, over minutes 06:00 to
09:59.

`summary.json` additions (existing keys unchanged):
- per day: `mean_road_delay` (mean over car agents, served and unserved, 4 dp), `max_road_delay`
  (int), `mean_car_travel_min` (served cars, `arrive_min - depart_min`, 4 dp),
  `peak_bin_total_delay_by_corridor` (per corridor, the largest mean `queue_delay_min +
  road_delay_min` of served cars over `calib_bin_min` gate-arrival bins), `peak_bin_total_delay_wmean`
  (its car-weighted mean), and `roads.LOS_DAY_KEYS` over 07:00-09:00, vehicle-km weighted, 4 dp,
  null without roads or without sections of the group: `los_ef_share_mwy`, `los_ef_share_other`,
  `vc_mean_mwy`, `vc_mean_other`, `los_ef_speed_share_mwy`, `los_ef_speed_share_other`,
  `congested_at_share_mwy`, `congested_at_share_other`.
- `meta.road` = `roads.road_settings(cfg)`: `enabled`, `bpr_alpha`, `bpr_beta`, `speed_floor`,
  `flow_window_min`, `k` (from `road_meta.json`; null with roads off), and with roads and
  `mwy_breakdown` on also `mwy_breakdown`, `mwy_breakdown_vc`, `mwy_recover_vc`,
  `mwy_capacity_drop`, `mwy_jam_speed`.

### V/C and Level of Service definitions (`cordonlite/roads.py`)

The same everywhere (run outputs, analysis, the NetLogo monitors and plot):
- V/C of section s at minute m: `x = v / cap_vph` with v the engine's volume (a day: `bg_peak_vph x
  r + c x fpe`; usual traffic: `obs_peak_vph x r`).
- V/C grade, SSC2026's (HCM 1994 bands; The Congestion Question WS1, Feb 2019): motorway mainline
  (`mwy` 1) A < 0.30, B < 0.48, C < 0.70, D < 0.90, E < 1.0, F >= 1.0; other roads A < 0.26, B <
  0.43, C < 0.62, D < 0.82, E < 1.0, F >= 1.0. A bound belongs to the worse grade. A motorway section
  in breakdown at that minute is F (so a motorway F can have V/C below 1).
- Speed grade (HCM 2010 urban street bands on f = speed / free-flow speed, every road): A f > 0.85,
  B > 0.67, C > 0.50, D > 0.40, E > 0.30, F f <= 0.30; a bound belongs to the worse grade; a
  broken-down motorway is F. E/F by speed: f <= 0.40 or broken down.
- Congested (Auckland Transport): f < 0.5 (AT measures against the posted limit, here against
  free-flow speed).
- "% of traffic at E/F" of a group = vehicle-km (v x km) weighted share of its section-minutes at E
  or F; mean V/C and mean f are vehicle-km weighted. Groups: `motorway` (mwy 1), `other` (mwy 0),
  `all`, `corridor k`.
- A motorway section not broken down has x < `mwy_breakdown_vc` (1.0), so f > 1 / (1 + alpha) (0.87
  at alpha 0.15; grade A); broken down, f <= `mwy_jam_speed` (F). On motorways the speed-based E/F share, the AT
  congested share and the broken-down share are therefore the same number.
- Constants: `LOS_BANDS_MWY`, `LOS_BANDS_OTHER`, `SPEED_LOS_BANDS`, `SPEED_LOS_E_FROM` (0.40),
  `AT_CONGESTED_BELOW` (0.5), `LOS_BINS`, `LOS_PEAK_BIN`, `LOS_PERIODS`, `LOS_DAY_KEYS`,
  `ROAD_LOS_COLUMNS`, `LOS_SUMMARY_COLUMNS`, `LOS_DP` (4).

### Python API (`cordonlite/roads.py`, run additions)

```python
# scenario files
ROAD_SCENARIO_FILES; ROAD_SECTIONS_COLUMNS; AGENT_ROUTES_COLUMNS; ROAD_PROFILE_COLUMNS; ROAD_PROFILE_LONG_COLUMNS
MWY_COLUMNS; PROFILE_COLUMNS_SEC; ROAD_PARAMS_KEYS; MWY_PARAMS_KEYS; ROAD_ENTRIES_COLUMNS; ROAD_ENTRIES_FILE
class RoadScenario      # frozen; arrays aligned with section_ids (ascending); routes agent_id -> section ids;
                        # sec_r, sec_keep derived once; .index, .fpe
read_road_scenario(scenario_dir) -> RoadScenario | None
read_profiles(prof: pd.DataFrame) -> dict[int, tuple[float, ...]]
write_road_scenario(run_dir, personas, cfg, data_dir=None) -> None
remove_road_scenario(run_dir) -> None
# engine dynamics
broken_down(road, i, m, x) -> bool
speed_factor(road, i, m, c) -> float                     # section index i, minute m, window count c
breakdown_windows(x, breakdown_vc, recover_vc) -> (bd_on, bd_off)   # int64; (-1, -1) none; n if no recovery
simulate_roads(cars, road) -> RoadDay(delay_min, extra_min, entries)
entries_frame(day, rows) -> pd.DataFrame; typed_entries(df) -> pd.DataFrame
# public information
speed_table(road, entries, minutes) -> SpeedTable(start_min, f, broken)
route_delays(road, table, routes, departures) -> dict[int, np.ndarray]
road_delay_at(public_road, agent_id, depart_min, start_min) -> float
# V/C and LoS
traffic_table(road, entries, minutes) -> TrafficTable(start_min, v, x, f, broken)
los_grade(vc, mwy, broken=None) -> np.ndarray; speed_los_grade(f, broken=None) -> np.ndarray   # 0..5 = A..F
los_section_info(road, data_dir) -> pd.DataFrame   # section_id, street_name, frc, mwy, corridor, km, weight_km
los_at_minute(table, info, m) -> dict              # what the GUI shows at a 5-minute mark
los_periods(days) -> list[tuple[str, list[int]]]
los_outputs(road, entries, info, days) -> LosOutputs(road_los, summary, day_keys); empty_los_outputs(days)
write_los_outputs(run_dir, out) -> None
# calibration record
road_k(cfg, data_dir=None) -> float | None; road_settings(cfg) -> dict
road_settings_diff(recorded, current) -> list[str]
# run.py
public_road(road, personas, cfg, entries=None) -> dict[int, tuple[float, ...]]
los_for_run(res, cfg, run_dir, road_entries) -> roads.LosOutputs
calib_value(days, metric, delay="queue") -> (value, busiest corridor, mean peak per corridor)
SimResult.roads (DayResult.road per day), SimResult.road (the run's RoadScenario or None)
```

### Capacity calibration

- `engine.calib_delay = "total"`: per day and corridor the peak is the largest mean over
  `calib_bin_min` gate-arrival bins of `queue_delay_min + road_delay_min` of served cars (summary key
  `peak_bin_total_delay_by_corridor`); `"queue"`: the queue delay alone (`peak_bin_delay_by_corridor`).
  `calib_value(days, metric, delay)` combines corridors by `calib_metric` and averages over
  `calib_days`; the target is `calib_target_peak_delay_min` (15).
- Each record in `data/calibration.json` (top level and every `by_seed` entry) gains `calib_delay`
  and `road` (= `roads.road_settings(cfg)` of the calibration run).
- `python -m cordonlite.run calibrate --seeds 1 2 3 [--jobs J]`: the seeds run in parallel processes
  (default one per seed, at most the CPU count; `--jobs 1` one after another); duplicate seeds are
  dropped; the records are the same either way; `label` prefixes each seed's progress lines.
- Mismatch rule (`run.resolve_capacity_scale`): `--capacity-scale` wins (source `cli`). Otherwise,
  with `engine.use_calibration` and the file present, the run's seed record under `by_seed` is used
  when its `n_agents` equals the run's, else the top-level record, compared on `seed` and
  `n_agents`. Either record is also compared on the road settings (`roads.road_settings_diff`: a
  record without `road` counts as `road.enabled = false`, one without `mwy_breakdown` as the rule
  off; with roads off on both sides nothing else is compared; otherwise `bpr_alpha`, `bpr_beta`,
  `speed_floor`, `flow_window_min`, `k` and, with the rule on in both, the `mwy_*` keys) and, with
  roads on, on `calib_delay` (a record without it counts as `"queue"`). On any difference the scale
  is still used, a WARNING goes to stderr and `meta.capacity_scale_source` reads
  `calibration:<file>[seed s] MISMATCH calibrated for <differences>`. Without a usable file:
  `engine.capacity_scale` (source `config`). The traits setting is never compared.
- `data/calibration.json` must be rewritten (`calibrate --seeds 1 2 3`) whenever config.toml changes
  n_agents, the road settings, `calib_delay` or the behaviour values the behaviour calibration
  chooses. The 300-agent free-flow state is archived as `data/calibration_freeflow300.json`.
- `scripts/calibrate_behaviour.py`: `N_AGENTS` = `run.n_agents` of config.toml; single-seed
  tolerances `seed_tolerance(n)` = the n = 300 values x sqrt(300 / n), 3 dp (at 950: shares +/- 0.028,
  response +/- 2.2 pp, SKIP 0); `use_logged_n(res, stage)`: `select` and `report` use the logged
  search's n, `final`, `oos` and `gap` stop when it differs from config.toml; `archive_paths(log)`;
  `LAST_JSON` = `data/behaviour_calibration_freeflow300.json` (300 agents, free-flow roads;
  `data/calibration_freeflow300.json`, `docs/calibration_report_freeflow300.md`,
  `docs/figures/freeflow300/`), `SKIP25_JSON` keeps the earlier archive. Capacity is recalibrated at
  every grid point with `engine.calib_delay`; n_agents, the `[road]` settings and `calib_delay` are
  never searched. (Superseded on 2026-10-09 by "Behaviour calibration with the willingness to
  travel" at the end: no SKIP tolerance, `LAST_JSON` is the `skip30_nowtt` log.)

### Analysis (`cordonlite/analysis.py`)

- `compare_runs` hashes the three new files too (a run folder made before them raises
  FileNotFoundError); `load_run` adds `los_summary` (an empty frame when the file is missing).
- `summary_table(runs, days=(10, 30), periods=((6, 10), (21, 30)))` adds per period
  `mean_road_delay_dX_Y` (car agents, served and unserved), `car_door_to_door_dX_Y` (served cars)
  and, over 07:00-09:00, `los_ef_share_{mwy,other}_dX_Y`, `vc_mean_{mwy,other}_dX_Y`,
  `los_ef_speed_share_{mwy,other}_dX_Y`, `congested_at_share_{mwy,other}_dX_Y` (NaN without the data).
- `road_delay_by_departure(run, days, bin_min=15)` -> `bin_start, bin_mid, cars, mean_road_delay`;
  `los_by_bin(run, days, groups=("motorway", "other"))` -> `bin, group, share_EF, vc_mean, veh_km,
  share_EF_speed, share_congested_AT` (pooled over the days by vehicle-km).
- `fig_road_delay(runs, out)` -> `road_delay.png`; `fig_los(runs, out)` -> `los.png` (per run four
  panels: E/F by V/C, E/F by speed, AT congested, mean V/C; motorways and other roads; days 6-10
  solid, 21-30 dashed). `main` draws both. Since 2026-10-09 the panels are E/F by V/C, mean V/C,
  E/F by speed, AT congested, and `analysis.LOS_NOTE` is printed under the figure and under
  `summary_table.md` (why the V/C grade saturates; see "Peak charge, fee response and NetLogo
  choosers").

### NetLogo (`netlogo7/cordon_lite.nlogox`)

Engine part (headless `setup-from-dir` / `run-day`, and the GUI):
- `read-roads` reads the four road files or none (`road-on?` false: free flow); rejects `bpr_beta`
  other than 4; takes `vehicles-per-agent` from `road_params.csv`; reads the optional mwy columns and
  keys (`mwy-on?`, `sec-mwy`, `sec-bd-on`, `sec-bd-off`, `mwy-vc`, `mwy-jam`) and `profile_id` /
  `cap_drop` (`road-profiles` = table profile_id -> 1440 values, `sec-r`, `sec-keep`).
- `road-arrivals [cars]`, cars = `[agent_id depart_min]` in any order, reports
  `[delays rows times extras counts]`: `delays` table agent_id -> road_delay_min; `rows`
  `[section_id minute entries]` sorted by section, then minute; `times` table agent_id -> `[t0 = 0
  t1 .. tn]`, elapsed minutes at each section boundary; `extras` the unrounded `el - ffsum`; `counts`
  one table keyed `i x 100000 + m` (section position i, minute m). Helpers `road-speed-factor [i m
  c]`, `road-volume [i m c]`, `road-window-count [counts i m]`, `road-broken? [i m x]`, `entry-key
  [i m]` port `roads.speed_factor` and `broken_down` line by line.
- `run-day-io`: the free-flow `sim-start-min` check, gate arrival = depart + fftt to the gate + road
  delay, then `point-queues`; writes `outcomes_dayNN.csv` (with `road_delay_min`),
  `profile_dayNN.csv` and `road_dayNN.csv`.

GUI part:
- `setup` also calls `read-roads`; `start-day d` runs `simulate-queues` (`road-arrivals`, then
  `point-queues`), `plan-drives` (each car's `t-out` from its section times, stretched by
  `(gate-arr - dep) / tn` so it reaches the gate point at the engine's whole gate-arrival minute; a
  car without a route moves at constant speed by metres, `even-clock`) and `index-road-entries`.
- Road colours (`regrade-roads` at every 5-minute mark, `5 x floor(clock / 5)`): the speed grade of
  the engine's speed factor at that minute with today's window counts (`section-grade`,
  `grade-bands`, `grade-colors`): normal f >= 0.80 keeps the road's grey, slow 0.60 to 0.80 light
  yellow, heavy 0.40 to 0.60 amber orange, jammed below 0.40 bright purple; a motorway section in
  breakdown is jammed at any speed. No red (queued cars), no green (PT). Only sections whose grade
  changed are redrawn, at most `road-redraw-budget` (60) per tick; a view change redraws all.
- Monitors: "traffic delay (min)" (`traffic-delay-now`: mean road delay of today's cars with
  `gate-arr <= clock`); at the last 5-minute mark ("-" without roads) "LoS E/F % motorways" and "LoS
  E/F % other roads" (`los-ef-pct`), "mean V/C motorways" and "mean V/C other roads" (`los-vc`),
  "LoS E/F by speed % motorways" and "LoS E/F by speed % other roads" (`los-ef-speed-pct`). Plot
  "% traffic at LoS E/F" (V/C-based; one pen per region of `los-region-names`: SH1, SH16, SH20, North
  Shore, New Lynn, Green Lane, Other roads, since 2026-10-10 instead of "motorways" and "other roads"),
  one point per 5-minute mark, cleared each day; marks that `finish-day` skips are filled in.
  `los-at [m cs]` mirrors `roads.los_at_minute` and reports `[grades ef-mwy ef-other vc-mwy vc-other
  speed-grades efs-mwy efs-other region-ef region-vc]` (-1 = no traffic; the last two are lists, one
  value per region); `los-grade-of [x mw]`, `speed-los-grade-of
  [f]`. `region-of [street-name mid-x mid-y]` gives a section's region (`sec-region`, set by
  `read-los-sections` from `data/road_sections.csv`), with the same rules as `roads.los_region_of`
  (`LOS_REGIONS`, `LOS_REGION_STREETS`, `LOS_NORTH_SHORE_MIN_X/Y`, `LOS_REGION_DISCS`);
  `los_section_info` has the columns `x_mid`, `y_mid` and `region`, and `los_at_minute` the lists
  `region_ef_share` and `region_vc_mean`. The regions are for the GUI only (no run output). The AT
  congested share is not shown (CSVs and summary.json only). Since 2026-10-09 a plot
  "Mean V/C (1 = at capacity)" (same pens) sits under the LoS plot, fed by the same `los-at` pass
  ("Peak charge, fee response and NetLogo choosers").
- Kept: 15 s ticks (4 steps per minute), `keep-going?`, the day ends 2 minutes after the last
  arrival, the tick counter, red queues.

Checks:
- `scripts/check_network_model.py` with road files also checks: `road_delay_min` against
  `outcomes.csv`; each car's section times against a probe on `roads.speed_table` built from the
  day's `road_entries.csv` (exact); drawn positions before the gate within 1 m; `drive-point
  gate-arr` = the gate point; road colours = speed grades (broken-down motorways jammed); the
  traffic delay monitor; every section's LoS grade by V/C and by speed against `los_at_minute`
  (exact) and the shares and mean V/C within `LOS_TOL`; the plot's points at the end of the day.
  `--view-times HH:MM ...` exports views there and checks there too (a clock after the day's end is
  skipped and listed in `marks_after_day_end`).
- `tests/test_netlogo_interface.py` (no JVM): no two widgets overlap, the notes fit, the LoS
  monitors and plot pens exist, the bands equal `roads.py`, and the Info tab's motorway jam times
  match `data/road_meta.json` and `data/road_sections.csv` (it fails by design when prep changes the
  windows and the Info tab is not updated).
- Fast tests: `tests/test_roads.py`, `tests/test_prep_roads.py` (toy shapefile, cordon, counts and
  NZTA sites), `tests/test_analysis_roads.py`; `conftest.tiny_cfg` sets `road.enabled = false` (the
  hand-computed free-flow numbers), `make_today(..., public_road=None, public_road_source="usual")`,
  `write_tiny_road_data(data_dir, origins, cap_vph=1200.0, w_factor=0.05)` writes prep-style road
  files. NetLogo tests (`test_engine_netlogo.py`, `test_run_netlogo.py`,
  `test_network_model_netlogo.py`) cover roads on and off and read `CORDONLITE_NETLOGO_HOME`.

## Peak charge, fee response and NetLogo choosers (2026-10-09)

At the authors' request (DEVIATIONS.md, "Extreme-charge scenarios, NetLogo choosers and clean-up"
and "SKIP removed, willingness to travel and the peak charge" 6-9). The same day's first version, a
charge multiplier `fees.scale` with the runs `_fx2`, `_fx3` and `_fx5`, is retired; this section
describes the peak charge that replaced it. No engine change: `engine.py`, `roads.py`, `vickrey.py`
and the NetLogo procedures `road-arrivals`, `point-queues` and `run-day` are untouched.

### Configuration

| Key | Default | Meaning |
|---|---|---|
| `fees.peak_fee` | `6.0` | Peak charge, NZ$ per entry: every `tou_points` charge is multiplied by `peak_fee / 6` (their highest charge) before the table is built, so 6 is the SSC2026 schedule; regime "flat" charges it all day. Must be >= 0; 0 levies no charge at all, the same run as regime "none". `FeesConfig.peak_fee: float = 6.0`; `tou_points` must have a charge above 0. The comparison runs 0, 3, 12, 18 and 30 next to 6 |

Retired: `fees.scale` (the multiplier, peak NZ$6 x scale) and `fees.fee_flat` (NZ$6 for regime
"flat"), in `config._RETIRED_KEYS`: an older snapshot still loads, and `--set` of either is an error.
`config._migrate_fees` gives a snapshot without `peak_fee` the peak of its own schedule: its scale (1
if absent) x `fee_flat` for regime "flat", else x the highest `tou_points` charge (the earlier
canonical runs load as 6, an `_fx3` run as 18). The loader's other allowances are listed under "SKIP
removed and the willingness to travel".

### Python API

```python
# fees.py (see the scaffold section for the signatures)
DEFAULT_PEAK = 6.0; schedule_peak(points); peak_points(points, peak_fee); levied_regime(regime, peak_fee)
fee_at(minute, regime="tou", *, peak_fee=None, points=TOU_POINTS, round_dp=4) -> float
fee_table(regime="tou", *, peak_fee=None, points=TOU_POINTS, round_dp=4) -> list[float]
fee_table_from_config(cfg, regime=None) -> list[float]            # passes cfg.fees.peak_fee
# run.py
variant_suffix(cfg, base, capacity_scale=None, set_overrides=None)
    # suffix order: _n<N>, _d<D>, _<regime>, _fs<K>, _peak<NZ$> (fees.peak_fee), _cs<X>, _set-<hash>
```

The factor `peak_fee / schedule_peak` is applied before evaluation and rounding, so peaks 12, 18 and
30 give exactly the `fees.csv` of the earlier `_fx2`, `_fx3` and `_fx5` runs. Every consumer reads the
levied table: `run.write_scenario` writes it to `fees.csv` (read by PyEngine, NetLogoEngine and the
GUI), and `TodayInfo.fee_by_minute` (the options, trigger T2, `fee_faced`, the willingness to pay and
the LLM prompt) comes from `fee_table_from_config(cfg)`. `run._today` and `write_scenario` use
`levied_regime`, so peak 0 has no charge day (`scenario.csv` `charge_from_day` 0), no T2 and no
charge in the prompt.

- CLI: `python -m cordonlite.run ... [--peak-fee NZ$]` sets `fees.peak_fee` (a float, printed with
  `%g`: `--peak-fee 12` gives `<arm>_<backend>_<engine>_s<seed>_peak12`, `--peak-fee 0` `..._peak0`).
  Like the other explicit flags it wins over `--set fees.peak_fee=...` and warns when the two differ.
  `--fee-start-day` is still accepted as an alias of `--fee-start`. `--fee-scale` is gone.
- `summary.json` `meta.fee_peak`: the highest value of the levied table, NZ$, rounded to `round_dp`
  (0 for regime "none" and for peak 0). New runs no longer write `meta.fee_scale` (runs of the
  multiplier have it).
- `--estimate` writes `<runs>/estimates/<arm>_n<N>_d<D>_s<seed><variant>.json`, where `<variant>` is
  the run suffix without its `_n`/`_d` part: `--peak-fee 30` gives `..._s1_peak30.json` and does not
  overwrite the canonical estimate (empty variant).

### Analysis (`cordonlite/analysis.py`)

```python
FEE_RESPONSE_PEAKS = (0.0, 3.0, 6.0, 12.0, 18.0, 30.0)   # the comparison's peaks (documentation: any _peak run is read)
LOS_NOTE: str                            # under summary_table.md, fee_response.md, los.png, fee_response.png
run_fee_peak(meta, run_dir) -> float     # meta.fee_peak, else max of the run's fees.csv; nan without both
run_charged(meta) -> bool                # a charge is levied: regime not "none", fee_start_day set, peak > 0
discover_fee_response_runs(runs_dir, seed=None, include_netlogo=False) -> dict[(arm label, peak NZ$), Path]
    # per arm the canonical run (empty variant; its peak from run_fee_peak, NZ$6) and the runs whose only
    # variant is _peak<NZ$> (0 = the no-charge run); other variants, the retired _fx<X> runs, traits-off
    # runs and (unless include_netlogo) NetLogo runs are left out; one seed (as discover_runs)
fee_response_table(runs, base=(6, 10), charged=(21, 30)) -> pd.DataFrame
fee_response_by_group(runs, archetype_labels=(), charged=(21, 30)) -> pd.DataFrame   # no base argument
fig_fee_response(table, out) -> Path     # fee_response.png
_fee_tables(runs, cfg) -> list[list[float]]  # the charge panel of crossings_hist.png and cordon_entries.png:
    # each different non-zero fees.csv of the runs, highest peak first (labelled by peak when several,
    # e.g. with --all); the ToU schedule of cfg when no run has a charge
FEE_RESPONSE_FILES = ("fee_response.csv", "fee_response.md", "fee_response_by_group.csv", "fee_response.png")
```

Removed: `run_fee_scale`, `discover_fee_scale_runs`, the `skip_share` columns.

- `fee_response_table` columns: `arm, seed, peak_fee, window, car_share, pt_share, wfh_share,
  travel_share, wtt_limited_share, wtt_no_car_share, wtp_below_peak_share, car_crossings_per_day,
  car_crossings_change_pct, car_crossings_change_vs_own_d6_10_pct, mean_road_delay,
  peak_queue_delay, peak_total_delay, los_ef_speed_share_mwy, los_ef_share_mwy, vc_mean_mwy,
  los_ef_speed_share_other, los_ef_share_other, vc_mean_other, congested_at_share_mwy,
  congested_at_share_other, revenue_per_day, same_before_charge_as_peak0, run`. One row per arm and
  peak over the `charged` days. Shares are of all commuter-days in the window (`travel_share` = car +
  PT). `wtt_limited_share` and `wtt_no_car_share` are the commuter-days with at least one and with
  every car option removed by the willingness to pay (`summary.json` `wtt_limited`, `wtt_no_car`);
  `wtp_below_peak_share` the commuters whose `wtp_fee` is below the peak, exempt ones included (nan
  for runs made before the willingness to pay). Crossings are served cars per day;
  `car_crossings_change_pct` (the main measure) compares them with the same arm's peak-0 run on the
  same days, `car_crossings_change_vs_own_d6_10_pct` with the run's own `base` days.
  `peak_queue_delay` is the mean of `peak_bin_delay_wmean` (gate queue), `peak_total_delay` of
  `peak_bin_total_delay_wmean` (gate queue + road, the calibrated metric). The LoS columns are
  07:00-09:00 (`los_by_bin`): per road group LoS E/F by speed, LoS E/F by V/C and the mean V/C side
  by side, then the AT congested shares. `same_before_charge_as_peak0` is True when `decisions.csv`
  and `outcomes.csv` before `fee_start_day` equal those of the arm's peak-0 run (values compared, not
  dtypes); None for the peak-0 run and for an arm without one.
- `fee_response_by_group` columns: `arm, seed, peak_fee, window, archetype, archetype_label,
  company_car, n_agents, car_share, pt_share, wfh_share, travel_share, wtt_limited_share,
  wtt_no_car_share, wtp_below_peak_share`: one row per archetype x company car x arm x peak; shares of
  the cell's commuter-days (`wtp_below_peak_share` of its commuters).
- `fig_fee_response`: six panels against the peak charge, one line per arm: (a) car, PT and WFH
  shares; (b) travel share and the share with a WTP below the peak; (c) mean road delay and peak
  gate-queue delay; (d) LoS E/F by speed and by V/C, motorways and other roads; (e) mean V/C; (f)
  revenue per day; `LOS_NOTE` underneath.
- `summary_table`: car, PT and WFH shares and the travel share (no SKIP columns); a run made before
  SKIP was removed still loads, and its skippers stay in every share's denominator
  (`fig_mode_shares` draws them as a separate layer, `OLD_MODE`). `table_twins` returns an empty
  table for a run shorter than its day; the cordon-entries legend is drawn only when the panel has
  lines.
- `main()` calls the private `_write_fee_response` after the summary table: when the runs folder holds
  `_peak` runs of the canonical runs' seed (`--seed`, else the seed of the runs analysed) that reach
  the last charged day, it writes the four `FEE_RESPONSE_FILES` and warns on stderr when any
  `same_before_charge_as_peak0` is False; otherwise it deletes them.

### NetLogo (`netlogo7/cordon_lite.nlogox`, GUI part)

- Widgets: `experiment` (was `scenario-dir`, 2026-10-10) is a chooser of 8 readable labels, "<who
  decides>, <when>: $<peak> charge", in this order: "Rule, reacts to events" (R-clock), "Rule, decides every day"
  (R-daily), "LLM, reacts to events" (L-clock), "LLM, decides every day" (L-daily), each at `$6` (`../runs/<arm>_mock_py_s1_d10_fs6`)
  and `$18` (`../runs/<arm>_mock_py_s1_d10_fs6_peak18`): since 2026-10-10 runs of 10 days charged from day 6
  (`--days 10 --fee-start 6`; the 30-day runs charged from day 11 are not in the chooser, their folders stay). The reporters `experiment-labels` and `experiment-folders`
  list the labels and folders in the same order and `run-folder-of` maps one to the other. The `_peak0`,
  `_peak3`, `_peak12`, `_peak30`, traits-off and review runs are no longer in the chooser (their folders stay).
  `pt-disruption` (2026-10-10; its display was "PT disruption" until 2026-10-13, which the NetLogo GUI took as
  the variable name, so pt-disruption was undefined there: a widget's display must equal its variable) is a second chooser: "none" or "day 3 and day 8"
  (until 2026-10-13 "day 3 (before the charge)" and "day 8 (with the charge)" as separate choices).
  `pt-disruption-labels` and `pt-disruption-suffixes` (`""`, `_pt3_pt8`) list them and
  `run-folder-of [experiment-label disruption-label]` appends the suffix to the experiment's folder
  (`<arm>_mock_py_s1_d10_fs6[_peak18]_pt3_pt8`, made with `--set events.pt_disruption_day=[3,8]` and `--name`;
  the default day 20 lies outside the 10 days, so the runs without suffix have no disruption; the single-day
  `_pt3` and `_pt8` runs stay in `runs/` but are not in the chooser). Day 3 is before the charge starts
  (day 6) and day 8 after it, so a disruption never falls on the day the charge starts.
  `events.pt_disruption_day` (`EventsConfig`) is one day or a list of days; `EventsConfig.disruption_days`
  gives the tuple, `run.disruption_corridor` picks one corridor for all of them, and `--set` accepts either.
- Breed `bus-riders` (2026-10-13, `bus-riders-own [rider]`, shape "bus" added to the model's shapes): in
  `start-day` each commuter on public transport that day hatches one bus rider; `place-bus-rider` (called by
  `update-commuters`) draws it where its commuter is and hides the commuter, which keeps every variable.
  `drawn-agent` (commuter reporter) is the turtle that draws a commuter; `check_network_model.py` checks
  the end-of-day positions through it and that each PT rider has exactly one bus.
  `charge-on` (which days `go` plays) is a global without a widget (the chooser was removed 2026-10-10): `setup-run` sets it to "all days" (`go` starts at day 1; before 2026-10-10 "on: with the charge", which started at the first charged day); the check scripts set "off: before the charge" or "on: with the charge".
  The `fee-start-day` input and its note are removed. The "charged today" monitor of `fee-active-today?`
  is removed too (2026-10-10, when `go` played only charged days it was always true); the variable stays.
  A run with no charge day (`scenario.csv` `charge_from_day` 0, such as `_peak0`, which the chooser no
  longer lists) has "off: before the charge" play all 30 days and "on: with the charge" none ("This run
  has no days with the charge").
- Plots, right-hand column (x = 890, width 430): "Commuters", "Queue length by corridor" (legend
  names from `corridor-entry-name` (the first road in the brackets), such as "4: Fanshawe Street ramp"; the map tags read "<id> <entry road>: <n> waiting" (`compass-abbrev` is removed); y-axis
  "cars"), "Cordon entries per 15 min" (with the pen "charge (scaled)"), "% traffic at LoS E/F" and,
  directly under it, "Mean V/C (1 = at capacity)" (y = 795, height 175; the seven region pens with the LoS
  plot's colours). `plot-los` feeds both LoS plots from the same 5-minute `los-at`
  pass (items 8 and 9, one value per region; a point is skipped when -1) and `setup-day-plots` clears both; the engines
  compute nothing new. The hour axes end on the next quarter hour. The interface is about 970 px tall.
- Notes: the LoS note (height 270) says "1 = at capacity" and ends with the advice to read LoS E/F
  together with the mean V/C; the how-to note (height 360) names the `_peak` runs and the dot colours
  (grey = works from home). The Info tab has a "Level of service" paragraph (why the V/C grade
  saturates) and describes the `_peak` runs, compared on the same days.
- `setup` = `setup-run run-folder-of experiment`. `setup-run [dir]` sets up any folder; scripts call it with a
  path (`setup-run "<path>"`), because a NetLogo 7 chooser refuses a value that is not in its list
  ("Value must be one of: [...]"). It stops with `error` when `dir` has no `agents.csv`.
- `read-scenario-meta`: `charge-from-day` and `scen-n-days` from `scenario.csv`; without the file
  11 (the `config.toml` `fee_start_day`) and -1 (unknown: `go` plays on).
- `charged-day? [d]` (was `charge-on?`, renamed because the chooser took the name): `charge-from-day
  > 0 and d >= charge-from-day`; `start-day` sets `fee-active-today?` from it.
- `days-to-show` reports `[first last]` of the days `charge-on` picks: all days `[1 n]`; before the
  charge `[1 charge-from-day - 1]` (all days in a run that is never charged, `[]` when the charge
  starts on day 1); with the charge `[charge-from-day n]` (`[]` in a run never charged); `last` is
  -1 when the run's days are unknown. An unknown choice is an `error`.
- `next-day-to-show` reports the day `go` and `finish-day` start next: `current-day + 1` when it is
  inside `days-to-show`, the first day picked when it is before them or when the day shown was not
  one of them; when the day shown was the last day picked (or nothing is picked) it reports the
  message for the user instead, which only `go` and `finish-day` show (`user-message`).
- `start-day d`: demo plans only when the folder has no `plans.csv`; otherwise a day missing from it
  gives a message and no day starts.

Checks:
- `scripts/check_netlogo_equivalence.py --gui-smoke`: `gui_smoke` writes `scenario.csv`
  (`charge_from_day` 2, `n_days` 2) into its copy of the scenario and calls `setup-run`; it checks
  the short queue pen names and that both the LoS plot and the mean V/C plot have their "motorways"
  and "other roads" pens (`los_vc_pens_ok`), and records `los_mark`. After day 2 `charge_on_smoke(link)`
  checks that "all days" is over (`is-string? next-day-to-show`, read without `go`), that "off:
  before the charge" makes `go` start day 1 uncharged and is over after it, and that "on: with the
  charge" makes `finish-day` play day 2 charged (`out["charge_on"]`, part of `out["ok"]`). No
  `user-message` is reached. The engine variants still use `MODES` with "SKIP" and an `all_skip`
  plan set: the engines treat any mode other than CAR and PT as staying home.
- `scripts/check_network_model.py` sets up the run with `setup-run "<path>"`.
- `tests/test_netlogo_interface.py` (no JVM, 18 tests; `ARM_LABELS`, `BASE_PEAK = 6`, `PEAKS = (6,
  18)`): the `experiment` labels and the folders behind them in order, each run folder present with
  `agents.csv`; the Info tab's experiments paragraph and the note's `$6`/`$18` sentence, each folder's
  `fees.csv` peaking at its charge (NZ$6 for the four base runs) and no `_fx` or `_peak0` text left; the mean V/C
  plot, its pens, colours and place directly under the LoS plot, the `plot-los` and `setup-day-plots`
  code and the note wording; the Info tab's "Level of service" paragraph; no "SKIP", "postpone" or
  "stays home" anywhere, the grey-dot wording and the willingness-to-pay sentence in WHAT IS IT only;
  the short queue legend and axes; the `charge-on` choices and the code that uses them; no
  `fee-start-day` or `demo_scenario`; no "charged today" monitor and unique labels; the numbered
  how-to steps. Note heights are checked at a measured 14 px per line at font size 10. The note is
  found by its text "Pick an experiment".
- `tests/test_peak_fee.py` (fast; was `test_fee_scale.py`): the suffix and folder name, the CLI flag
  and its warning, the estimate file name, the outputs of a peak run (levied `fees.csv`, the engine's
  `fee_paid`, the prompt), peak 0 byte-identical to regime "none" (decisions, outcomes, plans,
  profile, personas, fees, scenario, LLM log and road and LoS outputs; R-clock and L-daily),
  `discover_fee_response_runs` and `fee_response_table`, `fee_response_by_group` and the files `main`
  writes with the LoS note, and runs made before the new keys. `tests/test_fees.py` and
  `tests/test_config.py` cover `peak_fee` (scaling, flat, none, >= 0, migration of older snapshots).
  `tests/test_run_netlogo.py` (netlogo): NetLogoEngine equals PyEngine at `--peak-fee 30` and at
  `--peak-fee 0`.

Removed on 2026-10-09: `netlogo7/demo_scenario/` (synthetic, read by nothing), the 300-agent
estimates `runs/estimates/L-clock_n300_d30_s1.json` and `L-daily_n300_d30_s1.json` (in git history)
and `data/.gitkeep`. The `_fx` run folders are no longer read by anything (analysis leaves them out,
the chooser does not list them); `.gitignore` ignores `cordon_lite/runs/*_fx*/` until they are deleted.

## SKIP removed and the willingness to travel (2026-10-09)

Author decisions of 2026-10-09 (DEVIATIONS.md, "SKIP removed, willingness to travel and the peak
charge" 1-5): SKIP is removed, and each commuter has a fixed willingness to pay to drive into the
city centre, exponential in the charge after the SSC2026 model; a CAR option charged above it is not
offered. Owners: behaviour (`persona.py`, `options.py`, `clock.py`, `memory.py`, `rules.py`), llm
(`llm.py`), integrator (`run.py`), scaffold (`config.py`, `types.py`, `config.toml`). No engine
change: the engines still accept a plan whose mode is neither CAR nor PT (the commuter stays home).

### Configuration

`[wtt]` (new section; `WttConfig`, `cfg.wtt`):

| Key | Default (config.toml / dataclass) | Meaning |
|---|---|---|
| `beta0` | `0.15` / `0.0` | Price sensitivity at VoT_ref [CAL with PAP and k_WFH; anchor 0.5 = SSC2026 base_beta]. 0 = off: no limit (WTP infinite, no clip), the model before 2026-10-09, which an older snapshot without `[wtt]` loads as |
| `beta_clip` | `[0.1, 2.0]` | Bounds on beta = beta0 x VoT_ref / VoT [SSC] |
| `vot_ref` | `"distribution_median"` | VoT_ref: `"distribution_median"` = exp(`persona.vot_mu`) = NZ$9.97/h; `"sample_median"` = the median VoT of the simulated commuters (twins' copies included), as SSC2026 |

Retired with SKIP: `costs.skip_cost`, `costs.skip_vot_hours`, `llm.mock.w_skip`. Loader
(`load_config`): unknown and missing keys stay errors, except that an older `config_snapshot.toml`
may lack the keys of `config._ADDED_KEYS` (`run.compress_csv_over_mb`, `wtt.beta0`, `wtt.beta_clip`,
`wtt.vot_ref`; they take their dataclass default) and the sections of `config._ADDED_SECTIONS`
(`wtt`), and may hold the keys of `config._RETIRED_KEYS` (the three above, `fees.scale`,
`fees.fee_flat`; dropped). An override of a retired key is an error (the key is not found).
`fees.peak_fee` is derived instead (`_migrate_fees`, previous section). `llm.template_id` is
`"cl-v3"`; `config.RETIRED_TEMPLATE_IDS = ("cl-v1", "cl-v2")` still load.

### Python API

```python
# types.py
MODES = ("CAR", "PT", "WFH"); GC_PARTS = ("time", "schedule", "fee", "parking", "fuel", "pt", "wfh", "habit")
Persona.wtt_u: float = 0.0               # the uniform draw (last Layer A draw)
Persona.wtt_beta: float = 0.0            # clip(beta0 x VoT_ref / VoT, beta_clip); 0 with beta0 = 0
Persona.wtp_fee: float = math.inf        # -ln(u) x VoT / beta, NZ$ to the cent; inf with beta0 = 0
DecisionContext.wtt_removed: int = 0     # CAR options removed today by the willingness to pay
# persona.py
wtt_vot_ref(vots, cfg) -> float                          # VoT_ref (wtt.vot_ref)
willingness_to_pay(u, vot, vot_ref, cfg) -> (beta, wtp)  # (0.0, inf) with beta0 = 0; u = 0 -> inf
# options.py
build_options(persona, memory, today, params, cfg, discontinuity, wtt=True) -> tuple[Option, ...]
wtt_filter(persona, options) -> tuple[Option, ...]
fee_faced(persona, memory, options, cfg, today=None) -> float   # pass the options built with wtt=False
# clock.py
evaluate_triggers(persona, memory, today, feasible_option_ids, cfg)  # pass the offered option ids
# run.py
DECISION_COLUMNS += ("wtt_removed", "wtt_all_removed")
```

- Draw: in `persona.build_personas`, one `stream(seed, "A")` uniform per base agent after every other
  Layer A draw (after the early-start permission), so no earlier field changes; twins copy all three
  fields. VoT_ref is computed once per population. `personas.csv` gains `wtt_u`, `wtt_beta`,
  `wtp_fee` as its last three columns (`wtp_fee` is written `inf` with beta0 = 0; the engines do not
  read `personas.csv`, and the NetLogo GUI reads only its `origin_id` column; replaying a beta0 = 0
  run in the GUI was not tried).
- `wtt_filter(persona, options)`: removes every CAR option with `Option.fee > persona.wtp_fee` (the
  levied charge at its expected gate exit; a charge equal to WTP stays); order and the other options
  unchanged. Nothing is removed for a company car, for a commuter whose options are all CAR (no PT
  and no WFH: the must-drive trades, or no PT where WFH is not allowed) or when `wtp_fee` is
  infinite. On an uncharged day every fee is 0 and nothing is removed.
- `feasible_modes`: CAR, PT (if `pt_allowed` and not `must_drive`), WFH (if `wfh_allowed`); the limit
  removes departures, never the mode as such.
- `evaluate_triggers`: given option ids, a standing CAR departure is feasible only when it is in the
  window and offered itself (given modes, when "CAR" is), so T6 wakes an agent whose standing
  departure the limit removed. The standing-SKIP clause is gone.
- `memory.AgentMemory.habit_option_id` is deleted; callers use `standing_option_id`.
- Rules: `rules.option_code` keeps PT 10001 and WFH 10002 (SKIP's 10003 retired); `PART_FACTOR` has
  no `skip`.
- `run.simulate`, per agent and day: `full = build_options(..., wtt=False)`, `opts =
  wtt_filter(p, full)`, triggers on `[o.option_id for o in opts]`, both rebuilt with
  `discontinuity=True` when a trigger is a discontinuity; `fee_faced(p, mem, full, cfg, today)`;
  `wtt_removed = len(full) - len(opts)`; one option left -> decider `forced` (no decider or LLM
  call; reason "Only feasible option.", factor `work_constraint`).
- Prompt (`llm.render_user_prompt`, template `cl-v3`): no SKIP row or choice; the options table and
  the schema list the offered options only. When `ctx.wtt_removed > 0` the TODAY section adds "- You
  would not pay more than NZ$x a day to drive into the city centre, so driving at times when the
  charge is higher than that is not offered today." or, when no CAR option is left, "..., and every
  time you could drive today is charged more than that, so driving is not offered today." With roads
  off the user message is the cl-v2 text without traffic (cl-v1 without the SKIP row). MockLLM:
  no `w_skip`.

### Run outputs

| File | Addition |
|---|---|
| `personas.csv` | `wtt_u, wtt_beta, wtp_fee` (last three columns) |
| `decisions.csv` | `wtt_removed` (int: CAR options removed that agent-day), `wtt_all_removed` (bool: every CAR option removed) |
| `summary.json` days | `wtt_limited` (agents with at least one CAR option removed), `wtt_no_car` (agents with every CAR option removed); the key `skip` is gone; `calls.forced` counts the forced decisions |
| `summary.json` meta | `wtt` (`beta0`, `beta_clip`, `vot_ref`), `wtt_limited_days_total`, `wtt_no_car_days_total` |

The run's progress line prints `no-car` (agents with no car option) where it printed the SKIP count.

### Tests

- `tests/test_wtt.py` (fast, 14 tests): the formula and the exponential share; the `[wtt]` keys and
  their validation; the draw is the last Layer A draw and twins copy it; the population share
  willing falls exponentially; the filter (above WTP removed, equal kept) and its exceptions (company
  car, essential trip); `fee_faced` at a removed reference departure; T6 when the standing car
  option is not offered; the prompt sentence only when driving was removed; a run with beta0 = 0
  equals the model without the limit; uncharged days do not depend on beta0, and the diagnostics.
- Updated: `test_options.py`, `test_clock.py`, `test_rules.py`, `test_llm.py`
  (`test_prompt_has_no_skip_option`), `test_run.py`, `test_config.py`
  (`test_snapshot_before_skip_removal_and_wtt_loads`), `test_memory.py`. `conftest.tiny_plans` and
  the engine tests still use SKIP plans (the engines are unchanged).

## Behaviour calibration with the willingness to travel (2026-10-09)

`scripts/calibrate_behaviour.py` after SKIP was removed and `[wtt]` added (the model changes are
described in "SKIP removed and the willingness to travel" above):

- Three free scalars: `costs.pt_attitude_penalty`, `costs.wfh_cost` and `wtt.beta0`.
  `point_overrides(pap, park_paid, wfh, beta0)` sets `wtt.beta0`; `point_label(sc)` =
  `pap<g>_park<g>_wfh<g>_b<g>`. `V3_SCALARS` (the loss prior) and `ANCHORS` gain `beta0` 0.5 (SSC2026
  base_beta); `anchor_distance` and the prior skip a scalar an archived point does not have.
- Targets: `base_skip` is dropped from `TARGETS`, `SEED_TOL_300` and `SUMMARY_KEYS` (and `end_skip`
  from the summaries); the archived logs keep them. `BASE_KEYS` = the three base shares, which do not
  depend on beta0. `BEFORE` drops `costs.skip_cost` (retired key) and sets `wtt.beta0` 0.
- Staged search (`SEARCH_DESIGN`): `BETA0_STAGE1` = 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0; `STAGE1`
  (PAP 21-23 x k_WFH 4, 6, 8, 9, 10, 12, 14, 16) plus `STAGE1_CORNERS`; `stage2_paps(points)` (PAP values
  of stage 1 that meet the base targets, widened by one at the edge); `stage3_betas(b)` (midpoints
  around the stage-2 choice). `BETA0_REFERENCE` = 0 runs on every stage 1-2 pair; such points carry
  `reference: true` and `candidates(points)` leaves them out of `select`, `ridge_alternatives`
  (which now returns scalar dicts) and `selection_sensitivity`.
- Shared capacity: `capacity(job)` calibrates one (PAP, k_WFH, seed) (`cal_key`), and `evaluate`
  takes that record as `job["calibration"]` with a float `scale`; `task(job)` dispatches either;
  `run_jobs(..., fn=evaluate, on_result=None)`. `Checkpoint` keeps the search's calibrations and runs
  in the system temp folder (`cordonlite_behaviour_search_checkpoint.json`), resumes an interrupted
  search when the model, n, seeds and design are unchanged, and is deleted once the log is written.
- Metrics gain `share_by_day["no_car"]` and `["limited"]`, `wtt_no_car_11_13`, `end_wtt_no_car`,
  `end_wtt_limited`, `end_forced` (decisions forced onto PT), and per evaluation
  `wtt_limitable_share`, `wtp_below_peak_share`, `wtp_below_peak_limitable_share`.
- JSON: `skip` is replaced by `skip_removed`; new `wtt` (beta_clip, vot_ref, its value, peak fee,
  form); `search` gains `stages` (pairs, beta0 values, calibrations, runs, seconds; `paps` for stage
  2, `chosen_after_stage2` for stage 3), `beta0_values`, `beta0_reference`, `n_calibrations`,
  `n_runs`, `wall_seconds`, `workers`; points gain `reference` and `stage`; `structural_only` gains
  `scalars`; the report section reads `freeflow300` and `last` through `archive_summary(log)`.
- Archives: `FREEFLOW_JSON` = `data/behaviour_calibration_freeflow300.json`; `LAST_JSON` =
  `data/behaviour_calibration_skip30_nowtt.json` (950 agents, congested roads, SKIP NZ$30, no
  willingness to travel; with `data/calibration_skip30_nowtt.json`,
  `docs/calibration_report_skip30_nowtt.md` and `docs/figures/skip30_nowtt/`, which also holds
  `example_prompt_skip30_nowtt.md`, the `cl-v2` example of that state).
- `gap_sensitivity` variants: `nowtt` (beta0 0), `ssc` (beta0 0.5, left out when chosen),
  `samplemedian` (`wtt.vot_ref`), `noearly`, `early1.5`, `early6`, `earlyall` (the `skip25` variant
  went with SKIP). The optional `--stage gap` re-search holds beta0 at the chosen value.
- `calib_search.png` has four panels: the days 21-30 and 11-13 responses over k_WFH x beta0 at the
  chosen PAP (feasible cells outlined, references dashed) and the base PT and car shares over
  k_WFH x PAP.
- Result: PAP 22, k_WFH 12, beta0 0.15 in `config.toml`; `data/calibration.json` recalibrated at them
  (`calibrate --seeds 1 2 3`: 0.430292, 0.396105, 0.396105).
