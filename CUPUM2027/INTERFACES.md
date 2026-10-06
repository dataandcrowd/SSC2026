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

Shared files (`config.py`, `types.py`, `config.toml`, `conftest.py`) may only gain new
optional items; do not rename or remove existing ones. If a builder needs a new config key,
add it to `config.toml` with an [A] or source comment and to the matching dataclass in
`config.py` (the loader rejects unknown and missing keys), and note it in `DEVIATIONS.md`.

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
Config: run, time, fees, prep, engine, persona, traits, costs, memory, clock, events, rules, llm (llm.mock)
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
fee_at(minute: float, regime: str = "tou", *, fee_flat=6.0, points=TOU_POINTS, round_dp=4) -> float
fee_table(regime: str = "tou", *, fee_flat=6.0, points=TOU_POINTS, round_dp=4) -> list[float]   # 1440 entries
fee_table_from_config(cfg: Config, regime: str | None = None) -> list[float]
fee_active(day: int, regime: str, fee_start_day: int) -> bool
write_fees_csv(path, table, round_dp=4) -> Path      # minute,fee with 4 decimals
read_fees_csv(path) -> list[float]
max_table_change(a, b) -> float                       # for T2
describe_schedule(table, start_min, end_min, step_min=15) -> list[tuple[int, float]]
```

Engines take `fee_paid` from `fees.csv` (the table), never by recomputing the schedule.

### `cordonlite/types.py`

`Persona`, `TraitParams`, `Option`, `MemoryRecord`, `TodayInfo`, `DecisionContext`, `Decision`,
the `Decider` Protocol, `DelayProfile`, constants `MODES`, `DECIDERS`, `TRIGGERS`, `FACTORS`,
`GC_PARTS`, and helpers `option_id_for(mode, depart_min)` and `clock_str(minute)`. Read the file
for field lists; they are the contract.

Key conventions:
- Option ids: `CAR_hhmm` (e.g. `CAR_0745`), `PT`, `WFH`, `SKIP`.
- Option order in `DecisionContext.options`: CAR by `depart_min` ascending, then PT, WFH, SKIP.
- `Option.gc == sum(Option.gc_parts.values())`, keys from `GC_PARTS`
  (`time, schedule, fee, parking, fuel, pt, wfh, skip, habit`; absent keys mean 0).
- `Decision.decider` in `rule`, `llm`, `llm-fallback-rule`, `standing`, `forced`.

### `cordonlite/engine.py`

`Engine` Protocol (`load`, `run_day`, `close`), `DayResult(outcomes, profile)`, column tuples
`PLAN_COLUMNS`, `OUTCOME_COLUMNS`, `PROFILE_COLUMNS`, `CORRIDORS_COLUMNS`, `AGENTS_COLUMNS`,
file names `CORRIDORS_FILE`, `AGENTS_FILE`, `FEES_FILE`, and `plans_file(day)`,
`outcomes_file(day)`, `profile_file(day)` (`plans_dayNN.csv` etc., two-digit day).

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

## Engine builder: implementations in `cordonlite/engine.py`

```python
class PyEngine:      # implements Engine
    def __init__(self, cfg: Config) -> None
class NetLogoEngine: # implements Engine
    def __init__(self, cfg: Config, link: object | None = None) -> None   # link: shared pynetlogo.NetLogoLink
def make_engine(kind: str, cfg: Config) -> Engine                       # "py" | "netlogo"
def get_netlogo_link(cfg: Config) -> object                             # one NetLogoLink per process (cached)
# added by the engine builder:
def simulate_point_queues(cars, corridor_ids, capacities, sim_start_min, sim_end_cap_min)
    -> (exit_min_by_agent, profile_rows, last_minute)                   # reference algorithm
def read_scenario(scenario_dir) -> Scenario                             # validated scenario files
def shutdown_netlogo_link(timeout_s=5.0) -> bool                        # guarded kill_workspace
def hard_exit(code=0) -> None                                           # flush + os._exit (end of CLI with NetLogo)
```

Equivalence check in its own process: `python scripts/check_netlogo_equivalence.py [--scenario DIR]
[--gui-smoke] [--timing-agents 300]` (exit code 0 when PyEngine == NetLogoEngine).

Scenario files (written by the integrator into the run directory, read by `load`):

| File | Columns |
|---|---|
| `corridors.csv` | `corridor_id, name, capacity_per_min, x, y` (x, y in NZTM metres) |
| `agents.csv` | `agent_id, corridor_id, fftt_to_gate_min, fftt_gate_to_dest_min, x, y` (ints for times) |
| `fees.csv` | `minute, fee` (1440 rows, active regime; used only when `fee_active`) |

`run_day(day, plans, fee_active)`: `plans` has `PLAN_COLUMNS` for every agent; CAR rows are
simulated. Semantics are in the `engine.py` module docstring (point queue, carry rule, cap
sentinel `-1`). Outputs: `DayResult.outcomes` with `OUTCOME_COLUMNS` sorted by `agent_id`,
`DayResult.profile` with `PROFILE_COLUMNS` sorted by `corridor_id, minute`, covering every
corridor and every minute from `sim_start_min` to the last minute processed.

NetLogoEngine file exchange in the scenario directory: Python writes `plans_dayNN.csv`
(`agent_id, mode, depart_min`), calls `command('run-day <day> "<dir>" <true|false>')`, NetLogo
writes `outcomes_dayNN.csv` and `profile_dayNN.csv` with the same columns as the DataFrames.
NetLogo procedures required: `setup-from-dir <dir>` (reads scenario files), `run-day <day> <dir> <fee-active?>`.
GUI: the same model replays a run on the TomTom road network (see "NetLogo network model" below);
headless use never loads the map.
Tests: PyEngine hand-computed cases; PyEngine == NetLogoEngine on random plans, marked
`@pytest.mark.netlogo`, executed in a subprocess or separate pytest process, ending with
`os._exit` or a guarded `kill_workspace`.

Capacity is NOT the engine's job: `capacity_per_min` arrives in `corridors.csv`.

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
`n_agents - k + j` copies every Layer A field of agent `j` (j = 0..k-1).

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
`MemoryRecord.expected_delay_min` stores the public forecast (before the personal ratio).
Reference fee: `ref <- ref + alpha * (fee_paid_perceived - ref)` every day
(`ref_fee_update = "all_days"`, 0 on non-car days) or on car days only. `fee_paid_perceived`
is 0 for company-car agents.
Behaviour recalibration: `update_memory(mem, record, cfg, fee_faced=None)`; with
`ref_fee_update = "faced"` (the default) the update uses the fee paid on car days and `fee_faced`
(from `options.fee_faced`) on other days.

### `cordonlite/options.py`

```python
car_departures(standing_depart_min: int, cfg: Config, persona: Persona | None = None) -> list[int]
initial_depart_min(persona: Persona, cfg: Config) -> int
public_delay_profile(outcomes: pd.DataFrame | None, corridor_ids: Sequence[int], bin_min: int) -> DelayProfile
expected_public_delay(profile: DelayProfile, corridor_id: int, gate_arrive_min: int) -> float
feasible_modes(persona: Persona, today: TodayInfo, cfg: Config) -> tuple[str, ...]
build_options(persona: Persona, memory: AgentMemory, today: TodayInfo, params: TraitParams,
              cfg: Config, discontinuity: bool) -> tuple[Option, ...]
non_car_outcome(persona: Persona, option: Option, day: int, pt_disrupted: bool) -> dict
gc_rank(options: Sequence[Option], option_id: str) -> int
```

Feasibility: CAR always; PT if `persona.pt_allowed` (a disrupted corridor keeps PT feasible
but slower); WFH if `persona.wfh_allowed`; SKIP always.

Generalised cost, per option (NZ$), with `a = VoT/60`, `k = kappa_h * (kappa_h_disc_factor if discontinuity else 1)`:

```
CAR at depart d:
  g     = d + fftt_to_gate_min                                (expected gate arrival)
  D     = expected_public_delay(profile, corridor, g) * memory.delay_ratio_ema
  x     = g + round(D)                                        (expected gate exit; fee minute)
  arr   = x + fftt_gate_to_dest_min
  early = max(0, t* - arr); late = max(0, arr - t*)
  time     = a * (fftt_total + D)
  schedule = phi * sched_mult * a * (beta_ratio * early + gamma_ratio * late)
  fee      = c * (f + eta * max(0, f - ref_fee))   with f = fee_by_minute[x], c = 0 if company_car else 1
             (equivalently f * (1 + eta * max(0, f - ref)/max(f, fee_eps)))
  parking  = persona.parking_cost
  fuel     = persona.fuel_cost                    (fuel addition; also `Option.fuel`, 0 for non-car options)
PT:   pt = omega * (a * T_pt + PAP) + pt_fare, T_pt = pt_time_min * (pt_disruption_time_mult if disrupted and announced else 1)
      final fixer: services leave on a pt_headway_min grid; depart = latest service arriving by t*,
      early = t* - arrival (< headway), schedule = phi * sched_mult * a * beta_ratio * early
WFH:  wfh  = wfh_cost * phi                                   (costs.wfh_form = "spec")
      wfh  = wfh_cost * phi + a * fftt_total + parking_cost + fuel_cost   ("v3_relative", default; recalibration; fuel addition)
SKIP: skip = skip_cost + skip_vot_hours * VoT   (final fixer)
habit = k for every option whose option_id differs from the habit reference (0 when none):
        the standing option, or for a standing SKIP the most recent non-SKIP option (final fixer)
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
inside the departure window; a standing SKIP is always infeasible). Edge triggering: an event key
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
TEMPLATE_ID = "cl-v1"
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

Engine capacity from prep corridors (`engine.capacity_mode`):
- `demand_share`: `capacity_per_min_c = max(min_capacity_per_min, n_agents_on_c / rush_window_min)`.
- `raw_scaled`: `capacity_per_min_c = max(min_capacity_per_min, capacity_vph_raw_c / 60 * n_agents / agents_represented)`.

Daily loop (per day, agents in ascending `agent_id`):
1. `fee_active = fees.fee_active(day, regime, fee_start_day)`; `today.fee_by_minute` = table or zeros;
   `fee_changed_today = max_table_change(today, yesterday) >= clock.fee_change_threshold`
   (day 1 compares with itself, so False).
2. PT disruption: on `events.pt_disruption_day`, corridor = configured id or, if -1, the
   corridor with most `pt_allowed` personas (ties to lowest id).
3. `public_delay = options.public_delay_profile(yesterday_outcomes, corridors, delay_bin_min)`.
4. For each agent: `params = trait_params`; feasible modes; `triggers = evaluate_triggers`;
   `discontinuity = is_discontinuity`; `options = build_options`; if only one option ->
   `forced`; elif `should_wake(arm, triggers)` -> collect context; else execute standing
   option (`standing`).
5. `decider.decide_batch(woken)` (RuleDecider for R-*, LLMDecider for L-*).
6. Update standing option to the chosen option for every agent that decided (rule/llm/fallback/forced).
7. Plans -> `engine.run_day` -> car outcomes; non-car outcomes from `options.non_car_outcome`.
8. Build `MemoryRecord`s and `update_memory`.

Run outputs in `runs/<arm>_<backend>_<engine>_s<seed>/`:

| File | Columns / content |
|---|---|
| `config_snapshot.toml` | `config.dump_toml(cfg)` |
| `personas.csv` | `Persona` fields |
| `decisions.csv` | `agent_id, day, option_id, mode, depart_min, decider, triggers, reason, factors, gc_of_choice, rank_of_choice_by_gc, start_used_min, early_shift` (`triggers`, `factors` `;`-joined) |
| `outcomes.csv` | `agent_id, day, mode, option_id, corridor_id, depart_min, gate_arrive_min, gate_exit_min, queue_delay_min, arrive_min, travel_min, early_min, late_min, fee_paid, parking_paid, fuel_paid, pt_fare_paid, pt_disrupted, start_used_min, early_shift` |
| `profile.csv` | `PROFILE_COLUMNS`, all days |
| `llm_calls.jsonl` | see LLM section (empty for R-* arms) |
| `summary.json` | `{"meta": {...}, "days": [{"day", "cars", "pt", "wfh", "skip", "entries_per_15min": {"hh:mm": n}, "mean_queue_delay", "max_queue_delay", "mean_fee", "revenue", "calls": {"rule", "llm", "llm-fallback-rule", "standing", "forced"}}]}` |

### Integrator additions (implemented)

- `run.py`: `run_dir_name(arm, backend, engine, seed, traits="on")`, `load_prep(cfg)`,
  `disruption_corridor(personas, cfg)`, `capacity_per_min(corridors_prep, agents, cfg, scale=1.0)`,
  `resolve_capacity_scale(cfg, cli_scale=None)`, `write_scenario(run_dir, corridors_prep, personas, cfg, scale)`,
  `simulate(cfg, run_dir, scale, ...) -> SimResult`, `run_simulation(cfg, out_dir=None, capacity_scale=None, name=None)`,
  `estimate(cfg)`, `calibrate(cfg, target=None)`, `peak_bin_delay(outcomes, corridor_id, bin_min)`, `main(argv)`.
- CLI: `python -m cordonlite.run --arm ... --backend ... --engine ... --days 30 --fee-start 11
  --n-agents 300 --seed 1 [--traits off] [--estimate] [--capacity-scale X] [--set key=value]`;
  `python -m cordonlite.run calibrate [--seed 1] [--target 15]` writes `data/calibration.json`.
- `analysis.py`: `discover_runs`, `load_run`, `compare_runs`, `summary_table`, the figure functions
  and `table_who_adapts`, `table_twins`; `python -m cordonlite.analysis [--compare A B]`.
- New config keys: `[engine]` calibration keys, `costs.pt_attitude_penalty` (default 0). See DEVIATIONS.md, Integrator.

### Final fixer additions

- `run.py`: `variant_suffix(cfg, base, capacity_scale=None, set_overrides=None)`,
  `check_llm_credentials(cfg)`, `calib_value(days, metric)`, `noise_ids(personas)`;
  `run_simulation(..., variant="")` writes to a temporary folder and renames it on success
  (`<name>.failed` keeps a failed run's partial outputs); `write_scenario` also writes
  `scenario.csv` (`charge_from_day`, `n_days`), which the NetLogo GUI reads when replaying.
- `summary.json`: each day has `peak_bin_delay_wmean` (car-weighted mean of corridor peaks, the
  calibrated metric); `meta` has `variant` and `llm_fallback_share`.
- `llm.py`: `LLMFatalError`, `flexibility_sentence(sched_mult)`, `AnthropicLLM.key_extra()`;
  log records carry `error_kind` (`fatal`, `api`, `refusal`, `invalid`), `shared`, `shared_from`.
- `analysis.py`: `discover_runs(runs_dir, include_netlogo=False, seed=None, include_all=False)`,
  `table_who_adapts(run, base=(6, 10), end=None)`, `twin_summary(run)`,
  `llm_diagnostics(run, rule_run=None)`, `fig_crossings_hist` (was `fig_departure_hist`).
- `memory.AgentMemory.habit_option_id`, `options.pt_depart_min`, `options.skip_cost`,
  `rules.option_code`, `RuleDecider(cfg, noise_ids=None)`.
- Config keys: `engine.calib_metric`, `costs.skip_vot_hours`, `costs.pt_headway_min`,
  `llm.replicate`, `llm.traits_off_prompt`, `llm.max_consecutive_errors`.

### Behaviour recalibration additions

- `options.fee_faced(persona, memory, options, cfg) -> float`: levied fee of the CAR option at the
  grid-snapped car reference departure (0 for company cars); `memory.update_memory(..., fee_faced=None)`.
- Config: `costs.wfh_form` ("spec" | "v3_relative"), `memory.ref_fee_update` gains "faced".
- `python -m cordonlite.run calibrate --seeds 1 2 3`: `data/calibration.json` gains `by_seed`
  (`{"<seed>": record without history}`); `resolve_capacity_scale` prefers the run's seed record.
- `scripts/calibrate_behaviour.py [--stage all|search|select|final|oos|report] [--workers N]` ->
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
  (NZ$ a day, x phi(F)), `time.anchor_offsets_min` ([0, 15]); `costs.skip_cost` is 30.
- `options.early_start_for(persona, cfg) -> int | None`: `costs.early_start_min` when
  `persona.early_shift_ok` and it is earlier than `persona.tstar_min`, else None.
- `options.car_departures(standing_depart_min, cfg, persona=None)`: with a persona that may start early
  the set also holds `anchor +/- time.anchor_offsets_min` for the reference departure of each start
  (`options.start_anchor_depart(persona, start, cfg)` = start - free-flow time - `initial_buffer_min`,
  floored to the grid, clipped), for the early start and for t*. Option ids stay `CAR_hhmm`.
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
(`corridors.csv`, `agents.csv`, `fees.csv`, `scenario.csv`, `plans_dayNN.csv`, and when present
`personas.csv` for `origin_id` and `outcomes.csv` for PT minutes), `../data/origins.csv`,
`../data/gates.csv`, the roads shapefile and `netlogo7/gis/`. Writes nothing.

- `setup`: scenario files; `build-network` (node per 1 m-rounded segment end, coinciding ends
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
- `start-day d` reads `plans_dayNN.csv` (demo plans when absent outside a run folder), runs the
  point-queue code of `cordon_lite.nlogox` (`simulate-queues`), so `dep`, `gate-arr`, `gate-exit`
  (`-1` = not served by `sim-end-cap-min`) and `arr` equal the run's `outcomes.csv`.
- `point-queues [arrivals]` is the engine core used by both `run-day` (headless) and
  `simulate-queues` (GUI): arrivals `[gate-arrival agent_id corridor_id]`, reports
  `[exits profile last-minute]`.
- `go` advances `clock` by 1/`steps-per-minute` (4: 1 tick = 15 s; `start-day` resets the counter
  to the steps since `sim-start-min`) and draws every commuter with `state-at clock` (`home`,
  `driving`, `queued`, `transit` (PT), `work`). The day ends 2 minutes after the last arrival (at
  `sim-end-cap-min` if a car is never served); `go` then stops unless the `keep-going?` switch is
  on. `finish-day` (button "skip to end of day") jumps to the end of the day. Queued cars are red, `queue-spacing-m` = vehicles per agent x 7 m / 2
  lanes (about 220 m), and `update-tags` labels each corridor with its queue in the City centre view;
  `set-map-view "Auckland" | "City centre"`.
- Coordinates: `gis:set-world-envelope` then `map-env = gis:world-envelope`; `map-xy` / `nztm-of`
  are the linear map `gis:location-of` uses (`gis:set-transformation` rescales and is not used).
- Check: `python scripts/check_network_model.py [--run-dir DIR] [--days 1 11] [--views DIR]
  [--netlogo-home PATH] [--json OUT]` (own process, exit code 0 when every check passes);
  `tests/test_network_model_netlogo.py` (`@pytest.mark.netlogo`); `tests/test_prep_layers.py`.
