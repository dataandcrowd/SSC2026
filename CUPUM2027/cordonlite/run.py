"""Orchestrator CLI: personas, cognitive clock, deciders and engine, day by day. Owner: integrator.

    python -m cordonlite.run --arm R-clock --backend mock --engine py --seed 1
           [--traits on|off] [--n-agents N] [--days D] [--fee-start K] [--regime tou|flat|none]
           [--peak-fee NZ$] [--capacity-scale X] [--config config.toml] [--out runs/] [--name DIR] [--estimate]
           [--set key=value ...]
    python -m cordonlite.run calibrate [--seed 1 | --seeds 1 2 3 [--jobs J]] [--n-agents 950] [--target 15]

calibrate --seeds writes one record per seed under "by_seed" in the calibration file (the first
seed's record stays at the top level); runs use the record of their own seed when present. The
seeds run in parallel processes (--jobs, default one per seed); the records do not depend on it.

Run folders: the default name is "<arm>_<backend>_<engine>_s<seed>[_traitsoff]" followed by one
suffix per setting that differs from config.toml (variant_suffix): _n<N>, _d<D>, _<regime>,
_fs<K>, _peak<NZ$> (fees.peak_fee, the peak charge), _cs<X>, _set-<hash>; e.g. --peak-fee 12
gives R-clock_mock_py_s1_peak12 and --peak-fee 0 (no charge, the same run as --regime none)
R-clock_mock_py_s1_peak0. A run is written to a temporary folder and renamed on success, so a
failed or variant run never overwrites a finished canonical run.

Public API:
    run_dir_name(arm, backend, engine, seed, traits="on") -> str   # "<arm>_<backend>_<engine>_s<seed>[_traitsoff]"
    variant_suffix(cfg, base, capacity_scale=None, set_overrides=None) -> str
    check_llm_credentials(cfg) -> None                               # clear error before day 1
    load_prep(cfg) -> (origins, corridors_prep)
    disruption_corridor(personas, cfg) -> int | None
    capacity_per_min(corridors_prep, agents, cfg, scale=1.0) -> pd.Series   # indexed by corridor_id
    resolve_capacity_scale(cfg, cli_scale=None) -> (scale, source)    # per-seed record if present
    write_scenario(run_dir, corridors_prep, personas, cfg, scale=1.0) -> pd.DataFrame  # + road files if road.enabled
    public_road(road, personas, cfg, entries=None) -> dict[agent_id, tuple[float, ...]]  # TodayInfo.public_road
    simulate(cfg, run_dir, scale, ...) -> SimResult                      # the daily loop
    los_for_run(res, cfg, run_dir, road_entries) -> roads.LosOutputs     # V/C and LoS outputs (SPEC4 B)
    run_simulation(cfg, out_dir=None, capacity_scale=None) -> Path        # simulate + write outputs
    estimate(cfg, capacity_scale=None) -> dict                           # LLM call count with MockLLM
    calibrate(cfg, target=None, progress=True, label="") -> dict         # bisection on capacity_scale
    peak_bin_delay(outcomes, corridor_id, bin_min, with_road=False) -> float
    main(argv=None) -> int

The daily loop follows INTERFACES.md ("Integrator"). Outputs are byte-identical for identical
inputs with the mock backend and either engine (no timestamps or timings are written).
"""

from __future__ import annotations

import argparse
import dataclasses
import gzip
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from cordonlite import fees as feesmod
from cordonlite import roads as roadsmod
from cordonlite.clock import evaluate_triggers, is_discontinuity, should_wake
from cordonlite.config import ARMS, BACKENDS, ENGINES, REGIMES, Config, ConfigError, dump_toml, load_config
from cordonlite.engine import (
    AGENTS_FILE, CORRIDORS_COLUMNS, CORRIDORS_FILE, FEES_FILE, PLAN_COLUMNS, PROFILE_COLUMNS, ROAD_COLUMNS,
    PLANS_COLUMNS, PLANS_FILE, make_engine, outcomes_file, profile_file,
)
from cordonlite.memory import AgentMemory, new_memory, record_from_outcome, set_standing, update_memory
from cordonlite.options import (
    OUTCOME_ROW_COLUMNS, build_options, car_outcome, departure_grid, fee_faced, gc_rank, non_car_outcome,
    public_delay_profile, wtt_filter,
)
from cordonlite.persona import agents_frame, build_personas, personas_to_frame, trait_params, twin_pairs
from cordonlite.rules import RuleDecider
from cordonlite.types import Decision, DecisionContext, Option, Persona, TodayInfo, clock_str

# wtt_removed: CAR options removed that day by the willingness to pay (options.wtt_filter);
# wtt_all_removed: every car option was removed (the commuter could not drive that day)
DECISION_COLUMNS: tuple[str, ...] = (
    "agent_id", "day", "option_id", "mode", "depart_min", "decider", "triggers", "reason",
    "factors", "gc_of_choice", "rank_of_choice_by_gc", "start_used_min", "early_shift",
    "wtt_removed", "wtt_all_removed",
)
CALL_TYPES: tuple[str, ...] = ("rule", "llm", "llm-fallback-rule", "standing", "forced")
SCENARIO_FILE = "scenario.csv"          # key,value: charge_from_day, n_days (read by the NetLogo GUI)
_INT_OUT = ("agent_id", "day", "corridor_id", "depart_min", "road_delay_min", "gate_arrive_min",
            "gate_exit_min", "queue_delay_min", "arrive_min", "start_used_min")
_FLOAT_OUT = ("travel_min", "early_min", "late_min", "fee_paid", "parking_paid", "fuel_paid", "pt_fare_paid")
RUN_OUTPUTS = ("config_snapshot.toml", "personas.csv", "decisions.csv", "outcomes.csv", PLANS_FILE,
               "profile.csv", roadsmod.ROAD_ENTRIES_FILE, roadsmod.ROAD_LOS_FILE, roadsmod.LOS_SUMMARY_FILE,
               "llm_calls.jsonl", "summary.json", CORRIDORS_FILE, AGENTS_FILE, FEES_FILE, SCENARIO_FILE)


ROW_COLUMNS: tuple[str, ...] = OUTCOME_ROW_COLUMNS   # outcomes.csv columns (road_delay_min after depart_min)


# --------------------------------------------------------------------------- inputs


def run_dir_name(arm: str, backend: str, engine: str, seed: int, traits: str = "on") -> str:
    """Run folder name; '_traitsoff' is appended for the traits-off information ladder."""
    name = f"{arm}_{backend}_{engine}_s{seed}"
    return name + ("_traitsoff" if traits == "off" else "")


def _fmt_num(x: float) -> str:
    return f"{x:g}"


def variant_suffix(cfg: Config, base: Config, capacity_scale: float | None = None,
                   set_overrides: dict[str, Any] | None = None) -> str:
    """Suffix naming every setting that differs from the base config (config.toml)."""
    out = ""
    if cfg.run.n_agents != base.run.n_agents:
        out += f"_n{cfg.run.n_agents}"
    if cfg.run.n_days != base.run.n_days:
        out += f"_d{cfg.run.n_days}"
    if cfg.fees.regime != base.fees.regime:
        out += f"_{cfg.fees.regime}"
    if cfg.fees.fee_start_day != base.fees.fee_start_day:
        out += f"_fs{cfg.fees.fee_start_day}"
    if cfg.fees.peak_fee != base.fees.peak_fee:
        out += f"_peak{_fmt_num(cfg.fees.peak_fee)}"
    if capacity_scale is not None:
        out += f"_cs{_fmt_num(capacity_scale)}"
    if set_overrides:
        payload = json.dumps(sorted((k, v) for k, v in set_overrides.items()), default=str)
        out += "_set-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
    return out


def check_llm_credentials(cfg: Config) -> None:
    """Fail before day 1 when an anthropic-backend LLM arm has no resolvable credentials.

    The SDK resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, an `ant auth login` profile or
    workload identity federation; constructing the client reads them without a request."""
    if not (cfg.run.arm.startswith("L-") and cfg.run.backend == "anthropic"):
        return
    import anthropic

    try:
        c = anthropic.AsyncAnthropic()
    except Exception as e:  # noqa: BLE001 - surface any credential-resolution failure clearly
        raise RuntimeError(f"Anthropic client could not be created: {e}") from e
    if c.api_key is None and c.auth_token is None and getattr(c, "credentials", None) is None:
        raise RuntimeError(
            "No Anthropic credentials found. Set ANTHROPIC_API_KEY (or run `ant auth login`) before "
            "using --backend anthropic; see README.md, 'Running with the real Claude API'.")


def load_prep(cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """origins.csv and corridors.csv (prep format) from run.data_dir."""
    d = cfg.resolve_path(cfg.run.data_dir)
    for f in ("origins.csv", "corridors.csv"):
        if not (d / f).exists():
            raise FileNotFoundError(f"{d / f} missing: run `python -m prep.build_inputs` first")
    return pd.read_csv(d / "origins.csv"), pd.read_csv(d / "corridors.csv")


def disruption_corridor(personas: Sequence[Persona], cfg: Config) -> int | None:
    """Corridor hit by the PT disruption (the same on every disruption day): configured id, else most
    PT-feasible agents (ties: lowest id). None when no disruption day falls inside the run."""
    ev = cfg.events
    if not any(1 <= d <= cfg.run.n_days for d in ev.disruption_days):
        return None
    if ev.pt_disruption_corridor >= 0:
        return int(ev.pt_disruption_corridor)
    counts: dict[int, int] = {}
    for p in personas:
        if p.pt_allowed:
            counts[p.corridor_id] = counts.get(p.corridor_id, 0) + 1
    if not counts:
        return None
    return min(counts, key=lambda c: (-counts[c], c))


def capacity_per_min(corridors_prep: pd.DataFrame, agents: pd.DataFrame, cfg: Config,
                     scale: float = 1.0) -> pd.Series:
    """Engine capacity (agents/min) per corridor_id: base by engine.capacity_mode, times scale, floored.

    The floor is engine.min_capacity_vph vehicles/h in agents/min, min_capacity_vph / 60 /
    vehicles_per_agent (vehicles_per_agent = agents_represented / n_agents, as in the road files),
    rounded to 6 dp like the base, so it is the same traffic at any n_agents (950 veh/h = 0.25
    agents/min at 300 agents); min_capacity_vph = 0 uses engine.min_capacity_per_min (agents/min)."""
    ec = cfg.engine
    ids = corridors_prep["corridor_id"].astype(int).tolist()
    n_agents = len(agents)
    counts = agents["corridor_id"].astype(int).value_counts()
    if ec.min_capacity_vph > 0:
        vehicles_per_agent = float(ec.agents_represented) / n_agents
        floor = round(float(ec.min_capacity_vph) / 60.0 / vehicles_per_agent, 6)
    else:
        floor = float(ec.min_capacity_per_min)
    out = {}
    for _, r in corridors_prep.iterrows():
        c = int(r["corridor_id"])
        if ec.capacity_mode == "demand_share":
            base = float(counts.get(c, 0)) / float(ec.rush_window_min)
        else:
            base = float(r["capacity_vph_raw"]) / 60.0 * n_agents / float(ec.agents_represented)
        out[c] = max(floor, round(base * float(scale), 6))
    return pd.Series(out, name="capacity_per_min").reindex(ids)


def resolve_capacity_scale(cfg: Config, cli_scale: float | None = None,
                           warn: bool = True) -> tuple[float, str]:
    """Capacity scale: CLI value, else calibration file (if enabled and present), else config.

    The calibration file may hold per-seed records under ``by_seed`` (written by
    ``calibrate --seeds ...``); the record of the run's seed is used when its n_agents matches.
    Otherwise the top-level record is used. When that was made for another seed or n_agents, or
    other road settings (roads.road_settings: road.enabled, BPR parameters, flow window, k of
    data/road_meta.json, the motorway breakdown keys; a record without them was made with free-flow
    roads, one without mwy_breakdown without the motorway breakdown rule), or, with roads on,
    another engine.calib_delay (a record without it measured the queue only), the scale is still
    used, a warning is printed (warn=True) and the source says so. The traits setting is not
    checked: the information-ladder run deliberately keeps the main runs' capacity."""
    if cli_scale is not None:
        return float(cli_scale), "cli"
    if cfg.engine.use_calibration:
        p = cfg.resolve_path(cfg.engine.calibration_file)
        if p.exists():
            rec = json.loads(p.read_text())
            src = f"calibration:{p.name}"
            road_now = roadsmod.road_settings(cfg)

            def delay_diff(recorded: str) -> list[str]:
                if not cfg.road.enabled or recorded == cfg.engine.calib_delay:
                    return []  # with free-flow roads the total delay is the queue delay
                return [f"calib_delay {recorded} (this run {cfg.engine.calib_delay})"]

            def mismatch(source: str, diff: list[str]) -> str:
                if warn:
                    print(f"WARNING: {p} was calibrated for " + ", ".join(diff)
                          + "; recalibrate with `python -m cordonlite.run calibrate` for this setting.",
                          file=sys.stderr)
                return source + " MISMATCH calibrated for " + ", ".join(diff)

            per = rec.get("by_seed", {}).get(str(cfg.run.seed))
            if per is not None and per.get("n_agents") == cfg.run.n_agents:
                src = f"{src}[seed {cfg.run.seed}]"
                rdiff = roadsmod.road_settings_diff(per.get("road", rec.get("road")), road_now)
                rdiff += delay_diff(per.get("calib_delay", rec.get("calib_delay", "queue")))
                return float(per["capacity_scale"]), (mismatch(src, rdiff) if rdiff else src)
            diff = [f"{k} {rec[k]} (this run {v})" for k, v in
                    (("seed", cfg.run.seed), ("n_agents", cfg.run.n_agents))
                    if k in rec and rec[k] != v]
            diff += roadsmod.road_settings_diff(rec.get("road"), road_now)
            diff += delay_diff(rec.get("calib_delay", "queue"))
            if diff:
                src = mismatch(src, diff)
            return float(rec["capacity_scale"]), src
    return float(cfg.engine.capacity_scale), "config"


def write_scenario(run_dir: Path, corridors_prep: pd.DataFrame, personas: Sequence[Persona],
                   cfg: Config, scale: float = 1.0) -> pd.DataFrame:
    """Write corridors.csv, agents.csv, fees.csv for the engines, plus the road files
    (roads.write_road_scenario, from the prep outputs in run.data_dir) when road.enabled; returns
    the corridors frame."""
    run_dir.mkdir(parents=True, exist_ok=True)
    ag = agents_frame(personas)
    cap = capacity_per_min(corridors_prep, ag, cfg, scale)
    cor = pd.DataFrame({
        "corridor_id": corridors_prep["corridor_id"].astype(int),
        "name": corridors_prep["name"].astype(str),
        "capacity_per_min": cap.to_numpy(),
        "x": corridors_prep["x_nztm"].astype(float),
        "y": corridors_prep["y_nztm"].astype(float),
    })[list(CORRIDORS_COLUMNS)]
    cor.to_csv(run_dir / CORRIDORS_FILE, index=False, lineterminator="\n")
    ag.to_csv(run_dir / AGENTS_FILE, index=False, lineterminator="\n")
    feesmod.write_fees_csv(run_dir / FEES_FILE, feesmod.fee_table_from_config(cfg), cfg.fees.round_dp)
    levied = feesmod.levied_regime(cfg.fees.regime, cfg.fees.peak_fee)   # "none" at peak_fee 0
    charge_from = 0 if levied == "none" else int(cfg.fees.fee_start_day)
    pd.DataFrame({"key": ["charge_from_day", "n_days"], "value": [charge_from, int(cfg.run.n_days)]}).to_csv(
        run_dir / SCENARIO_FILE, index=False, lineterminator="\n")
    if cfg.road.enabled:
        roadsmod.write_road_scenario(run_dir, personas, cfg)
    else:
        roadsmod.remove_road_scenario(run_dir)  # no road files = free-flow roads in both engines
    return cor


def public_road(road: roadsmod.RoadScenario, personas: Sequence[Persona], cfg: Config,
                entries: pd.DataFrame | None = None) -> dict[int, tuple[float, ...]]:
    """TodayInfo.public_road: for every agent, the road delay (min) a car on its route would
    have for each departure minute from time.sim_start_min to time.depart_latest_min (agents
    without a route: zeros). entries None = usual traffic (counts only); otherwise a day's road
    entries (DayResult.road), i.e. that day's actual traffic.

    The delays are the probe's unrounded el - ffsum: every whole-minute use (expected gate arrival,
    start anchor, prompt) rounds them once with floor(R + 0.5), as the engine rounds a car's extra
    minutes, so yesterday's probe gives the whole-minute road delay the car had. A value rounded
    to 2 dp first would round twice (5.4959 -> 5.5 -> 6 where the engine has 5).

    Only the departures on options.departure_grid are computed (every reader, options and the
    prompt, uses a CAR option's departure, which is on that grid); the other minutes hold NaN, so
    a read off the grid fails loudly instead of giving a wrong delay. The tuples keep one entry
    per minute (index = depart_min - time.sim_start_min, roads.road_delay_at)."""
    t = cfg.time
    table = roadsmod.speed_table(road, entries,
                                 range(t.sim_start_min, t.sim_end_cap_min + roadsmod.TABLE_TAIL_MIN + 1))
    routes = {p.agent_id: road.routes.get(p.agent_id, ()) for p in sorted(personas, key=lambda q: q.agent_id)}
    deps = departure_grid(cfg)
    delays = roadsmod.route_delays(road, table, routes, deps)
    cols = np.asarray(deps, dtype=np.int64) - t.sim_start_min
    full = np.full((len(routes), t.depart_latest_min - t.sim_start_min + 1), np.nan)
    for i, aid in enumerate(routes):
        full[i, cols] = delays[aid]
    return {aid: tuple(full[i].tolist()) for i, aid in enumerate(routes)}


# --------------------------------------------------------------------------- simulation


@dataclass
class SimResult:
    """Everything one run produced, in memory."""

    personas: list[Persona]
    corridors: pd.DataFrame
    decisions: list[dict] = field(default_factory=list)
    outcomes: list[dict] = field(default_factory=list)
    profiles: list[pd.DataFrame] = field(default_factory=list)
    roads: list[pd.DataFrame] = field(default_factory=list)       # DayResult.road per day
    plans: list[pd.DataFrame] = field(default_factory=list)       # the plans of each day (PLANS_COLUMNS)
    days: list[dict] = field(default_factory=list)
    llm_stats: dict = field(default_factory=dict)
    disruption_corridor: int | None = None
    prompt_chars_by_day: dict[int, int] = field(default_factory=dict)
    road: roadsmod.RoadScenario | None = None                     # the run's road files (None: free flow)


def _forced_decision(ctx: DecisionContext) -> Decision:
    return Decision(agent_id=ctx.agent_id, day=ctx.day, option_id=ctx.options[0].option_id,
                    decider="forced", reason="Only feasible option.", factors=("work_constraint",))


def _today(cfg: Config, day: int, table: tuple[float, ...], prev_table: tuple[float, ...] | None,
           public_delay: Any, disrupted: frozenset[int], public_road: Any = None,
           public_road_source: str = "usual") -> TodayInfo:
    # peak_fee 0 levies nothing: regime "none" (no charge day, no T2, no charge in the prompt)
    regime = feesmod.levied_regime(cfg.fees.regime, cfg.fees.peak_fee)
    active = feesmod.fee_active(day, regime, cfg.fees.fee_start_day)
    tbl = table if active else tuple(0.0 for _ in table)
    prev = tbl if prev_table is None else prev_table
    changed = feesmod.max_table_change(tbl, prev) >= cfg.clock.fee_change_threshold
    return TodayInfo(day=day, fee_regime=regime, fee_active=active, fee_by_minute=tbl,
                     fee_changed_today=bool(changed), public_delay=public_delay,
                     pt_disrupted_corridors=disrupted,
                     pt_disruption_announced=bool(cfg.events.pt_disruption_announced),
                     pt_disruption_time_mult=float(cfg.events.pt_disruption_time_mult),
                     public_road=public_road if public_road is not None else {},
                     public_road_source=public_road_source)


def noise_ids(personas: Sequence[Persona]) -> dict[int, int]:
    """Common-random-number ids: each twin uses the id of the agent whose Layer A it copies."""
    return {twin: orig for orig, twin in twin_pairs(personas)}


def _make_decider(cfg: Config, run_dir: Path, backend: str | None = None,
                  personas: Sequence[Persona] = ()) -> Any:
    rule = RuleDecider(cfg, noise_ids(personas))
    if cfg.run.arm.startswith("R-"):
        return rule
    from cordonlite.llm import make_llm_decider  # imported lazily: rule arms never need it

    return make_llm_decider(cfg, run_dir, rule, backend or cfg.run.backend)


def simulate(cfg: Config, run_dir: Path, scale: float, *, backend: str | None = None,
             engine_kind: str | None = None, progress: bool = False) -> SimResult:
    """Run the daily loop for cfg.run.n_days days; scenario and exchange files go into run_dir."""
    origins, corridors_prep = load_prep(cfg)
    personas = build_personas(origins, corridors_prep, cfg)
    corridors = write_scenario(run_dir, corridors_prep, personas, cfg, scale)
    corridor_ids = corridors["corridor_id"].astype(int).tolist()
    road = roadsmod.read_road_scenario(run_dir)   # the files the engine reads; None = free-flow roads
    res = SimResult(personas=personas, corridors=corridors, road=road)
    res.disruption_corridor = disruption_corridor(personas, cfg)

    kind = engine_kind or cfg.run.engine
    engine = make_engine(kind, cfg)
    engine.load(run_dir)
    decider = _make_decider(cfg, run_dir, backend, personas)
    table = tuple(feesmod.fee_table_from_config(cfg))
    params = [trait_params(p, cfg) for p in personas]
    mems: list[AgentMemory] = [new_memory(p.agent_id, p.company_car) for p in personas]
    window = int(cfg.memory.window_days)
    traits_shown = cfg.run.traits == "on"
    prev_table: tuple[float, ...] | None = None
    yesterday_out: pd.DataFrame | None = None
    yesterday_road: pd.DataFrame | None = None
    usual_road: dict[int, tuple[float, ...]] | None = None
    try:
        for day in range(1, cfg.run.n_days + 1):
            t0 = time.perf_counter()
            disrupted = (frozenset({res.disruption_corridor})
                         if res.disruption_corridor is not None and day in cfg.events.disruption_days
                         else frozenset())
            public = public_delay_profile(yesterday_out, corridor_ids, cfg.costs.delay_bin_min)
            # road information: day 1 usual traffic (commuters know it), later yesterday's traffic
            pub_road: dict[int, tuple[float, ...]] = {}
            road_src = "usual"
            if road is not None:
                if yesterday_road is None:
                    if usual_road is None:
                        usual_road = public_road(road, personas, cfg)
                    pub_road = usual_road
                else:
                    pub_road, road_src = public_road(road, personas, cfg, yesterday_road), "yesterday"
            today = _today(cfg, day, table, prev_table, public, disrupted, pub_road, road_src)
            prev_table = today.fee_by_minute

            chosen: list[Decision | None] = [None] * len(personas)
            opts_by_agent: list[tuple[Option, ...]] = []
            faced_by_agent: list[float] = []
            trig_by_agent: list[tuple[str, ...]] = []
            removed_by_agent: list[tuple[int, bool]] = []
            woken: list[DecisionContext] = []
            for i, p in enumerate(personas):
                mem = mems[i]
                # every feasible option, then the ones offered (willingness to pay applied). The triggers
                # read the offered ids (T6: a standing car departure removed today wakes the agent); a
                # discontinuity changes only the habit costs, so the options are rebuilt with it
                full = build_options(p, mem, today, params[i], cfg, False, wtt=False)
                opts = wtt_filter(p, full)
                trig = evaluate_triggers(p, mem, today, [o.option_id for o in opts], cfg)
                disc = is_discontinuity(trig, cfg)
                if disc:
                    full = build_options(p, mem, today, params[i], cfg, True, wtt=False)
                    opts = wtt_filter(p, full)
                opts_by_agent.append(opts)
                # the charge at the car reference departure, also when the willingness to pay removed it
                faced_by_agent.append(fee_faced(p, mem, full, cfg, today))
                trig_by_agent.append(trig)
                n_removed = len(full) - len(opts)
                removed_by_agent.append((n_removed, n_removed > 0 and not any(o.mode == "CAR" for o in opts)))
                ctx = DecisionContext(
                    agent_id=p.agent_id, day=day, persona=p, params=params[i], options=opts,
                    standing_option_id=mem.standing_option_id, triggers=trig, discontinuity=disc,
                    recent=mem.recent(window), delay_ratio_ema=mem.delay_ratio_ema,
                    ref_fee=mem.ref_fee, today=today, traits_shown=traits_shown, wtt_removed=n_removed)
                if len(opts) == 1:
                    chosen[i] = _forced_decision(ctx)
                elif should_wake(cfg.run.arm, trig) or mem.standing_option_id is None:
                    woken.append(ctx)
                else:
                    ids = [o.option_id for o in opts]
                    if mem.standing_option_id not in ids:
                        raise RuntimeError(f"agent {p.agent_id} day {day}: standing option "
                                           f"{mem.standing_option_id} not offered and no wake")
                    chosen[i] = Decision(agent_id=p.agent_id, day=day,
                                         option_id=mem.standing_option_id, decider="standing")
            for d in decider.decide_batch(woken):
                chosen[d.agent_id] = d

            plans = []
            chosen_opt: list[Option] = []
            for i, p in enumerate(personas):
                dec = chosen[i]
                assert dec is not None
                opt = next(o for o in opts_by_agent[i] if o.option_id == dec.option_id)
                chosen_opt.append(opt)
                if dec.decider != "standing":
                    set_standing(mems[i], opt)
                plans.append((p.agent_id, opt.mode, int(opt.depart_min) if opt.mode == "CAR" else -1))
            plans_df = pd.DataFrame(plans, columns=list(PLAN_COLUMNS))
            fee_active = today.fee_active
            res.plans.append(plans_df.assign(day=day)[list(PLANS_COLUMNS)])
            result = engine.run_day(day, plans_df, fee_active)
            car_rows = {int(r["agent_id"]): r for r in result.outcomes.to_dict("records")}

            calls = {k: 0 for k in CALL_TYPES}
            day_rows = []
            for i, p in enumerate(personas):
                dec, opt = chosen[i], chosen_opt[i]
                assert dec is not None
                if opt.mode == "CAR":
                    row = car_outcome(p, car_rows[p.agent_id], opt.option_id, opt.start_used_min)
                else:
                    hit = p.corridor_id in disrupted and opt.mode == "PT"
                    row = non_car_outcome(p, opt, day, hit, cfg.events.pt_disruption_time_mult)
                day_rows.append(row)
                trig = trig_by_agent[i] if dec.decider != "standing" else ()
                rec = record_from_outcome(row, opt, dec.decider, trig, dec.reason)
                update_memory(mems[i], rec, cfg, faced_by_agent[i])
                calls[dec.decider] += 1
                res.decisions.append({
                    "agent_id": p.agent_id, "day": day, "option_id": opt.option_id,
                    "mode": opt.mode, "depart_min": opt.depart_min if opt.mode == "CAR" else None,
                    "decider": dec.decider, "triggers": ";".join(trig_by_agent[i]),
                    "reason": dec.reason, "factors": ";".join(dec.factors),
                    "gc_of_choice": round(float(opt.gc), 4),
                    "rank_of_choice_by_gc": gc_rank(opts_by_agent[i], opt.option_id),
                    "start_used_min": opt.start_used_min, "early_shift": bool(opt.early_shift),
                    "wtt_removed": removed_by_agent[i][0], "wtt_all_removed": removed_by_agent[i][1],
                })
            res.outcomes.extend(day_rows)
            res.profiles.append(result.profile)
            res.roads.append(result.road)
            res.days.append(_day_summary(day, day_rows, result.profile, calls, fee_active, cfg,
                                         corridor_ids, removed_by_agent))
            yesterday_out = result.outcomes
            yesterday_road = result.road
            if progress:
                s = res.days[-1]
                print(f"day {day:2d}  car {s['cars']:3d}  pt {s['pt']:3d}  wfh {s['wfh']:3d}  "
                      f"no-car {s['wtt_no_car']:3d}  delay mean {s['mean_queue_delay']:5.1f} "
                      f"max {s['max_queue_delay']:3d}  road mean {s['mean_road_delay']:5.1f}  "
                      f"woken {len(woken):3d}  "
                      f"({time.perf_counter() - t0:.2f}s)", flush=True)
    finally:
        engine.close()
        if hasattr(decider, "close"):
            decider.close()
    if hasattr(decider, "stats"):
        st = dict(decider.stats)
        st["approx_input_tokens"] = int(math.ceil(st.get("prompt_chars", 0) / 4))
        st["approx_note"] = "approximate: prompt characters / 4"
        res.llm_stats = st
    return res


def peak_bin_delay(outcomes: pd.DataFrame, corridor_id: int, bin_min: int, with_road: bool = False) -> float:
    """Max over gate-arrival bins of the mean queue delay of served cars on one corridor; with_road
    adds each car's road delay (the total congestion delay on the way in)."""
    df = outcomes[(outcomes["mode"] == "CAR") & (outcomes["corridor_id"] == corridor_id)
                  & (outcomes["gate_exit_min"].fillna(-1) >= 0)]
    if len(df) == 0:
        return 0.0
    b = (df["gate_arrive_min"].astype(int) // int(bin_min))
    delay = df["queue_delay_min"].astype(float)
    if with_road:
        delay = delay + df["road_delay_min"].astype(float)
    return float(delay.groupby(b).mean().max())


def _day_summary(day: int, rows: list[dict], profile: pd.DataFrame, calls: dict, fee_active: bool,
                 cfg: Config, corridor_ids: Sequence[int],
                 wtt_removed: Sequence[tuple[int, bool]] = ()) -> dict:
    df = pd.DataFrame(rows, columns=list(ROW_COLUMNS))
    car = df[df["mode"] == "CAR"]
    served = car[car["gate_exit_min"].astype(float) >= 0]
    qd = served["queue_delay_min"].astype(float)
    rd = car["road_delay_min"].astype(float)          # served and unserved cars
    door = served["arrive_min"].astype(float) - served["depart_min"].astype(float)
    entries = {}
    exits = served["gate_exit_min"].astype(int)
    for b in range(cfg.time.depart_earliest_min, cfg.time.sim_end_cap_min, 15):
        entries[clock_str(b)] = int(((exits >= b) & (exits < b + 15)).sum())
    peak_by_c = {str(c): round(peak_bin_delay(df, c, cfg.engine.calib_bin_min), 4) for c in corridor_ids}
    total_by_c = {str(c): round(peak_bin_delay(df, c, cfg.engine.calib_bin_min, with_road=True), 4)
                  for c in corridor_ids}
    cars_by_c = {str(c): int((car["corridor_id"] == c).sum()) for c in corridor_ids}
    n_car = sum(cars_by_c.values())
    peak_w = (sum(peak_by_c[c] * cars_by_c[c] for c in peak_by_c) / n_car) if n_car else 0.0
    total_w = (sum(total_by_c[c] * cars_by_c[c] for c in total_by_c) / n_car) if n_car else 0.0
    fee = served["fee_paid"].astype(float)
    return {
        "day": day, "fee_active": bool(fee_active),
        "cars": int(len(car)), "pt": int((df["mode"] == "PT").sum()),
        "wfh": int((df["mode"] == "WFH").sum()),
        # willingness to pay (2026-10-09): commuters with at least one car option removed, and with
        # every car option removed (decisions.csv wtt_removed > 0 and wtt_all_removed)
        "wtt_limited": int(sum(1 for n, _ in wtt_removed if n > 0)),
        "wtt_no_car": int(sum(1 for _, no_car in wtt_removed if no_car)),
        # commuters working the early day (start_used_min = costs.early_start_min), car or PT
        "early_shift": int((df["early_shift"] == True).sum()),  # noqa: E712 (None for unserved rows)
        "early_shift_cars": int((car["early_shift"] == True).sum()),  # noqa: E712
        "unserved_cars": int(len(car) - len(served)),
        "entries_per_15min": entries,
        "mean_queue_delay": round(float(qd.mean()), 4) if len(qd) else 0.0,
        "max_queue_delay": int(qd.max()) if len(qd) else 0,
        "mean_road_delay": round(float(rd.mean()), 4) if len(rd) else 0.0,
        "max_road_delay": int(rd.max()) if len(rd) else 0,
        "mean_car_travel_min": round(float(door.mean()), 4) if len(door) else 0.0,
        "peak_bin_delay_by_corridor": peak_by_c,
        "peak_bin_delay": max(peak_by_c.values()) if peak_by_c else 0.0,
        "peak_bin_delay_wmean": round(float(peak_w), 4),
        # the same peaks of queue + road delay (the capacity calibration target when
        # engine.calib_delay = "total")
        "peak_bin_total_delay_by_corridor": total_by_c,
        "peak_bin_total_delay_wmean": round(float(total_w), 4),
        "cars_by_corridor": cars_by_c,
        "mean_fee": round(float(fee.mean()), 4) if len(fee) else 0.0,
        "revenue": round(float(fee.sum()), 4),
        "late_share": round(float((df["late_min"].astype(float).fillna(0) > 0).mean()), 4),
        "calls": dict(calls),
    }


# --------------------------------------------------------------------------- outputs


def _outcomes_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=list(ROW_COLUMNS))
    for c in _INT_OUT:
        df[c] = pd.array(pd.to_numeric(df[c]).round(), dtype="Int64")
    for c in _FLOAT_OUT:
        df[c] = pd.to_numeric(df[c]).astype("float64").round(4)
    df["pt_disrupted"] = df["pt_disrupted"].astype(bool)
    df["early_shift"] = (df["early_shift"] == True)  # noqa: E712
    return df.sort_values(["day", "agent_id"], kind="stable").reset_index(drop=True)


def _decisions_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=list(DECISION_COLUMNS))
    df["depart_min"] = pd.array(pd.to_numeric(df["depart_min"]), dtype="Int64")
    df["start_used_min"] = pd.array(pd.to_numeric(df["start_used_min"]), dtype="Int64")
    df["early_shift"] = df["early_shift"].astype(bool)
    df["wtt_removed"] = df["wtt_removed"].astype("int64")
    df["wtt_all_removed"] = df["wtt_all_removed"].astype(bool)
    return df.sort_values(["day", "agent_id"], kind="stable").reset_index(drop=True)


def los_for_run(res: SimResult, cfg: Config, run_dir: Path, road_entries: pd.DataFrame) -> roadsmod.LosOutputs:
    """V/C and Level of Service outputs of a run (roads.los_outputs, SPEC4 B) from the road scenario
    files in run_dir, the run's road entries and the section descriptions of run.data_dir; empty
    (header-only files, None day keys) when the run has no road files (free-flow roads). Computed
    from files both engines share, so a PyEngine and a NetLogoEngine run give the same bytes."""
    days = [int(d["day"]) for d in res.days]
    road = res.road if res.road is not None else roadsmod.read_road_scenario(run_dir)
    if road is None:
        return roadsmod.empty_los_outputs(days)
    info = roadsmod.los_section_info(road, cfg.resolve_path(cfg.run.data_dir))
    return roadsmod.los_outputs(road, road_entries, info, days)


def write_csv_or_gz(df: pd.DataFrame, path: Path, limit_mb: float) -> Path:
    """Write df as CSV at path; when the CSV is larger than limit_mb megabytes (10**6 bytes), write it
    gzip-compressed as <name>.gz instead. The bytes are deterministic (no time stamp or file name in the
    gzip header), so PyEngine and NetLogoEngine runs stay byte-identical. The other form is removed, so a
    folder never holds both. Returns the path written."""
    data = df.to_csv(index=False, lineterminator="\n").encode("utf-8")
    gz = path.with_name(path.name + ".gz")
    if len(data) > limit_mb * 1e6:
        gz.write_bytes(gzip.compress(data, compresslevel=6, mtime=0))
        path.unlink(missing_ok=True)
        return gz
    path.write_bytes(data)
    gz.unlink(missing_ok=True)
    return path


def write_outputs(res: SimResult, cfg: Config, run_dir: Path, scale: float, scale_source: str,
                  variant: str = "") -> None:
    """config_snapshot.toml, personas.csv, decisions.csv, outcomes.csv, plans.csv (every day), profile.csv,
    road_entries.csv (road_entries.csv.gz when larger than run.compress_csv_over_mb MB), road_los.csv
    and los_summary.csv (header only without roads), summary.json
    (each day also gets roads.LOS_DAY_KEYS: LoS E/F shares by V/C and by speed, mean V/C and the AT
    congested share of motorways and other roads over 07:00-09:00; None without roads)."""
    (run_dir / "config_snapshot.toml").write_text(dump_toml(cfg), encoding="utf-8")
    personas_to_frame(res.personas).to_csv(run_dir / "personas.csv", index=False, lineterminator="\n")
    _decisions_frame(res.decisions).to_csv(run_dir / "decisions.csv", index=False, lineterminator="\n")
    _outcomes_frame(res.outcomes).to_csv(run_dir / "outcomes.csv", index=False, lineterminator="\n")
    pd.concat(res.plans, ignore_index=True)[list(PLANS_COLUMNS)].to_csv(
        run_dir / PLANS_FILE, index=False, lineterminator="\n")
    prof = pd.concat(res.profiles, ignore_index=True)[list(PROFILE_COLUMNS)]
    prof.to_csv(run_dir / "profile.csv", index=False, lineterminator="\n")
    road_days = [r for r in res.roads if len(r)]
    road = (pd.concat(road_days, ignore_index=True)[list(ROAD_COLUMNS)] if road_days
            else pd.DataFrame({c: pd.Series(dtype="int64") for c in ROAD_COLUMNS}))
    write_csv_or_gz(road, run_dir / roadsmod.ROAD_ENTRIES_FILE, cfg.run.compress_csv_over_mb)
    los = los_for_run(res, cfg, run_dir, road)
    roadsmod.write_los_outputs(run_dir, los)
    days = [{**d, **los.day_keys.get(int(d["day"]), {k: None for k in roadsmod.LOS_DAY_KEYS})} for d in res.days]
    llm_log = run_dir / "llm_calls.jsonl"
    if not llm_log.exists():
        llm_log.write_text("", encoding="utf-8")
    totals = {k: sum(d["calls"][k] for d in res.days) for k in CALL_TYPES}
    meta = {
        "arm": cfg.run.arm, "backend": cfg.run.backend, "engine": cfg.run.engine,
        "seed": cfg.run.seed, "n_agents": cfg.run.n_agents, "n_days": cfg.run.n_days,
        "traits": cfg.run.traits, "fee_regime": cfg.fees.regime,
        "fee_start_day": cfg.fees.fee_start_day,
        # the highest charge of the levied table, NZ$ (fees.peak_fee; 0 for regime none and for peak_fee 0,
        # which levies nothing). Runs of the charge multiplier (before peak_fee, 2026-10-09) also wrote fee_scale
        "fee_peak": round(max(feesmod.fee_table_from_config(cfg)), int(cfg.fees.round_dp)),
        "pt_disruption_day": cfg.events.pt_disruption_day,
        "pt_disruption_corridor": res.disruption_corridor,
        "capacity_scale": scale, "capacity_scale_source": scale_source,
        "capacity_per_min": {str(int(c)): float(v) for c, v in
                             zip(res.corridors["corridor_id"], res.corridors["capacity_per_min"])},
        "corridor_names": {str(int(c)): str(n) for c, n in
                           zip(res.corridors["corridor_id"], res.corridors["name"])},
        # roads on or off (free flow) and their settings: enabled, BPR alpha and beta, speed floor,
        # flow window, capacity factor k of data/road_meta.json (None with roads off); the same for
        # both engines
        "road": roadsmod.road_settings(cfg),
        "variant": variant,
        "calls_total": totals,
        "decider_calls_total": totals["rule"] + totals["llm"] + totals["llm-fallback-rule"],
        "early_shift_ok_agents": int(sum(1 for p in res.personas if p.early_shift_ok)),
        "early_shift_days_total": int(sum(d["early_shift"] for d in res.days)),
        # willingness to pay (2026-10-09): its settings, and the agent-days with a car option removed and
        # with every car option removed
        "wtt": {"beta0": float(cfg.wtt.beta0), "beta_clip": [float(x) for x in cfg.wtt.beta_clip],
                "vot_ref": cfg.wtt.vot_ref},
        "wtt_limited_days_total": int(sum(d["wtt_limited"] for d in res.days)),
        "wtt_no_car_days_total": int(sum(d["wtt_no_car"] for d in res.days)),
        "llm_fallback_share": (round(totals["llm-fallback-rule"] / (totals["llm"] + totals["llm-fallback-rule"]), 4)
                               if totals["llm"] + totals["llm-fallback-rule"] else None),
        "revenue_total": round(sum(d["revenue"] for d in res.days), 4),
        "llm": res.llm_stats,
    }
    summary = {"meta": meta, "days": days}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=False) + "\n",
                                          encoding="utf-8")


def run_simulation(cfg: Config, out_dir: Path | None = None, capacity_scale: float | None = None,
                   name: str | None = None, progress: bool = False, variant: str = "") -> Path:
    """Simulate one arm and write every output; returns the run directory.

    The default folder is run_dir_name(...) + variant. The run is written to a temporary sibling
    folder and moved into place only when it has finished, so a failed run never destroys an
    earlier complete run of the same name."""
    check_llm_credentials(cfg)
    runs = Path(out_dir) if out_dir is not None else cfg.resolve_path(cfg.run.runs_dir)
    final = runs / (name or (run_dir_name(cfg.run.arm, cfg.run.backend, cfg.run.engine,
                                          cfg.run.seed, cfg.run.traits) + variant))
    runs.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".tmp_{final.name}_", dir=runs))
    try:
        scale, source = resolve_capacity_scale(cfg, capacity_scale)
        res = simulate(cfg, tmp, scale, progress=progress)
        write_outputs(res, cfg, tmp, scale, source, variant)
        # NetLogoEngine's per-day exchange files (the same data is in plans.csv, outcomes.csv,
        # profile.csv and road_entries.csv)
        for pat in ("plans_day*.csv", "outcomes_day*.csv", "profile_day*.csv", "road_day*.csv"):
            for f in tmp.glob(pat):
                f.unlink()
        if final.exists():
            if progress:
                print(f"replacing existing run folder {final}", flush=True)
            shutil.rmtree(final)
        tmp.rename(final)
    except BaseException:
        failed = runs / (final.name + ".failed")
        shutil.rmtree(failed, ignore_errors=True)
        try:
            tmp.rename(failed)  # keep llm_calls.jsonl of paid calls for inspection
            print(f"run failed; partial outputs kept in {failed}", file=sys.stderr)
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)
        raise
    return final


# --------------------------------------------------------------------------- estimate


def estimate(cfg: Config, capacity_scale: float | None = None) -> dict:
    """Count the LLM calls an L-* arm would make, simulating with MockLLM (approximate).

    The real LLM would choose differently, so trajectories (and hence later wakes) can differ;
    tokens are prompt characters / 4 and exclude thinking and output tokens.
    """
    if not cfg.run.arm.startswith("L-"):
        raise ValueError("--estimate applies to L-clock and L-daily")
    scale, source = resolve_capacity_scale(cfg, capacity_scale)
    with tempfile.TemporaryDirectory(prefix="cordonlite_est_") as tmp:
        res = simulate(cfg, Path(tmp), scale, backend="mock", engine_kind="py")
        n_by_day: dict[int, int] = {}
        chars = 0
        log = Path(tmp) / "llm_calls.jsonl"
        recs = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
        lines = [r for r in recs if not r.get("shared")]  # a shared answer sends no request
        n_shared = len(recs) - len(lines)
        for r in lines:
            n_by_day[r["day"]] = n_by_day.get(r["day"], 0) + 1
            chars += len(r["user"])
        from cordonlite.llm import system_prompt

        sys_chars = len(system_prompt(cfg))
    n = len(lines)
    total_chars = chars + n * sys_chars
    return {
        "arm": cfg.run.arm, "n_agents": cfg.run.n_agents, "n_days": cfg.run.n_days,
        "seed": cfg.run.seed, "model": cfg.llm.model, "capacity_scale": scale,
        "capacity_scale_source": source, "n_llm_calls": n, "n_shared_answers": n_shared,
        "calls_by_day": {str(k): v for k, v in sorted(n_by_day.items())},
        "prompt_chars": total_chars, "mean_prompt_chars": round(total_chars / n, 1) if n else 0.0,
        "approx_input_tokens": int(math.ceil(total_chars / 4)),
        "note": ("APPROXIMATE: call count from a MockLLM run (a real LLM may wake agents on other "
                 "days); tokens = prompt characters / 4, input only, excluding schema, adaptive "
                 "thinking and output tokens. Cost all input as uncached: the system prompt is "
                 "below the minimum cacheable prefix and the json_schema differs per agent"),
    }


# --------------------------------------------------------------------------- calibration


def calib_value(days: Sequence[dict], metric: str, delay: str = "queue") -> tuple[float, int, dict[str, float]]:
    """Calibration metric over day summaries: (value, busiest corridor, mean peak per corridor).

    Per day and corridor the peak is the maximum over calib_bin_min gate-arrival bins of the mean
    queue delay of served cars (delay "queue"), or of their queue + road delay (delay "total").
    "car_weighted_mean" averages the corridor peaks with the day's car counts as weights, "worst"
    takes the largest, "busiest" the peak of the corridor with the most cars over all the days. The
    daily values are then averaged over the days."""
    key = "peak_bin_total_delay_by_corridor" if delay == "total" else "peak_bin_delay_by_corridor"
    cars_tot: dict[str, int] = {}
    for d in days:
        for c, n in d["cars_by_corridor"].items():
            cars_tot[c] = cars_tot.get(c, 0) + int(n)
    if not days or sum(cars_tot.values()) == 0:
        return 0.0, -1, {}
    busiest = min((c for c in cars_tot if cars_tot[c] == max(cars_tot.values())), key=int)
    vals = []
    for d in days:
        pk, cars = d[key], d["cars_by_corridor"]
        if metric == "worst":
            vals.append(max(pk.values()))
        elif metric == "busiest":
            vals.append(pk[busiest])
        else:
            n = sum(cars.values())
            vals.append(sum(pk[c] * cars[c] for c in pk) / n if n else 0.0)
    per_c = {c: round(float(np.mean([d[key][c] for d in days])), 4) for c in cars_tot}
    return float(np.mean(vals)), int(busiest), per_c


def calibrate(cfg: Config, target: float | None = None, progress: bool = True, label: str = "") -> dict:
    """Bisection (log scale) on capacity_scale so that the R-daily no-charge run has a peak mean
    delay of about target (queue, or queue + road with engine.calib_delay = "total"), measured by
    engine.calib_metric (calib_value) over calib_days. Uses PyEngine. Returns the calibration record.
    label prefixes the progress lines (calibrate --seeds runs the seeds side by side)."""
    ec = cfg.engine
    target = float(ec.calib_target_peak_delay_min if target is None else target)
    d0, d1 = ec.calib_days
    ccfg = dataclasses.replace(
        cfg, run=dataclasses.replace(cfg.run, arm="R-daily", n_days=int(d1)),
        fees=dataclasses.replace(cfg.fees, regime="none"))

    def measure(scale: float) -> tuple[float, int, dict]:
        with tempfile.TemporaryDirectory(prefix="cordonlite_cal_") as tmp:
            res = simulate(ccfg, Path(tmp), scale, engine_kind="py")
        days = res.days[d0 - 1:d1]
        peak, busiest, per_c = calib_value(days, ec.calib_metric, ec.calib_delay)
        info = {"mean_cars": float(np.mean([d["cars"] for d in days])),
                "mean_pt": float(np.mean([d["pt"] for d in days])),
                "mean_wfh": float(np.mean([d["wfh"] for d in days])),
                "mean_queue_delay": float(np.mean([d["mean_queue_delay"] for d in days])),
                "peak_by_corridor": per_c}
        return peak, busiest, info

    lo, hi = (float(x) for x in ec.calib_scale_bounds)
    history: list[dict] = []

    def probe(s: float) -> float:
        peak, busiest, info = measure(s)
        history.append({"capacity_scale": round(s, 6), "peak_delay_min": round(peak, 4),
                        "busiest_corridor": busiest,
                        **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in info.items()}})
        if progress:
            print(f"  {label}scale {s:8.4f}  {ec.calib_metric} {ec.calib_delay} peak {peak:6.2f} min  by corridor "
                  f"{info.get('peak_by_corridor', {})}  cars {info.get('mean_cars', 0):.0f}", flush=True)
        return peak - target

    f_lo, f_hi = probe(lo), probe(hi)
    status = "converged"
    if f_lo < 0:
        best, status = lo, "target above the delay at the lowest scale; lower bound used"
    elif f_hi > 0:
        best, status = hi, "target below the delay at the highest scale; upper bound used"
    else:
        best = None
        for _ in range(int(ec.calib_max_iter)):
            mid = math.sqrt(lo * hi)
            f_mid = probe(mid)
            if abs(f_mid) <= ec.calib_tol_min:
                best = mid
                break
            if f_mid > 0:
                lo = mid
            else:
                hi = mid
            if hi / lo < 1.0 + 1e-4:  # bracket collapsed onto a discontinuity
                break
        if best is None:
            status = "max iterations reached; closest probe used"
            best = min(history, key=lambda h: abs(h["peak_delay_min"] - target))["capacity_scale"]
    final = min((h for h in history if abs(h["capacity_scale"] - round(best, 6)) < 1e-9),
                key=lambda h: abs(h["peak_delay_min"] - target))
    return {
        "capacity_scale": round(float(best), 6),
        "target_peak_delay_min": target,
        "achieved_peak_delay_min": final["peak_delay_min"],
        "busiest_corridor": final["busiest_corridor"],
        "peak_by_corridor": final.get("peak_by_corridor", {}),
        "calib_metric": ec.calib_metric,
        "calib_delay": ec.calib_delay,
        "status": status,
        "method": ("bisection on log(capacity_scale); R-daily, fee regime none, PyEngine; per day and "
                   f"corridor the peak is the max over {ec.calib_bin_min}-min gate-arrival bins of the "
                   f"mean {'queue + road' if ec.calib_delay == 'total' else 'queue'} delay of served cars; "
                   f"metric '{ec.calib_metric}' over corridors, "
                   f"averaged over days {d0}-{d1}"),
        "seed": cfg.run.seed, "n_agents": cfg.run.n_agents, "capacity_mode": ec.capacity_mode,
        "rush_window_min": ec.rush_window_min, "traits": cfg.run.traits,
        "road": roadsmod.road_settings(cfg),
        "history": history,
    }


# --------------------------------------------------------------------------- CLI

def _common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--config", default=None, help="config.toml (default: cordon_lite/config.toml)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--n-agents", type=int, default=None)
    ap.add_argument("--traits", choices=("on", "off"), default=None)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="extra dotted config override, value parsed as JSON (repeatable)")


def _set_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """--set KEY=VALUE pairs; the value is parsed as JSON, else kept as a string."""
    ov: dict[str, Any] = {}
    for item in args.set:
        key, sep, raw = item.partition("=")
        if not sep or not key:
            raise SystemExit(f"--set expects KEY=VALUE, got {item!r}")
        try:
            ov[key] = json.loads(raw)
        except json.JSONDecodeError:
            ov[key] = raw
    return ov


def _overrides(args: argparse.Namespace) -> dict[str, Any]:
    """--set overrides, then the explicit flags, which take precedence (with a warning)."""
    ov = _set_overrides(args)
    for k, attr in (("run.seed", "seed"), ("run.n_agents", "n_agents"), ("run.traits", "traits"),
                    ("run.arm", "arm"), ("run.backend", "backend"), ("run.engine", "engine"),
                    ("run.n_days", "days"), ("fees.fee_start_day", "fee_start"),
                    ("fees.regime", "regime"), ("fees.peak_fee", "peak_fee")):
        v = getattr(args, attr, None)
        if v is not None:
            if k in ov and ov[k] != v:
                print(f"WARNING: --{attr.replace('_', '-')} {v} overrides --set {k}={ov[k]}", file=sys.stderr)
            ov[k] = v
    return ov


def _load(args: argparse.Namespace) -> Config:
    try:
        return load_config(args.config, overrides=_overrides(args))
    except ConfigError as e:
        raise SystemExit(f"config error: {e}") from None


def _calibrate_seed(cfg: Config, seed: int, target: float | None, label: str = "") -> dict:
    """calibrate() for one seed (also a process-pool task: seeds are independent)."""
    scfg = dataclasses.replace(cfg, run=dataclasses.replace(cfg.run, seed=int(seed)))
    return calibrate(scfg, target, label=label)


def _print_calibration(seed: int, r: dict) -> None:
    print(f"seed {seed}: capacity_scale = {r['capacity_scale']} (peak {r['achieved_peak_delay_min']:.2f} "
          f"min, target {r['target_peak_delay_min']}; {r['status']})", flush=True)


def _main_calibrate(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m cordonlite.run calibrate",
                                 description="Calibrate corridor capacity_scale (PyEngine, R-daily, no charge).")
    _common_args(ap)
    ap.add_argument("--target", type=float, default=None,
                    help="peak mean delay target (min): queue + road delay with engine.calib_delay = total, "
                         "the gate queue alone with queue (default engine.calib_target_peak_delay_min)")
    ap.add_argument("--output", default=None, help="calibration JSON (default engine.calibration_file)")
    ap.add_argument("--seeds", type=int, nargs="+", default=None,
                    help="calibrate each seed; the file keeps the first seed's record at the top "
                         "level and every seed's record under by_seed (runs pick their own seed)")
    ap.add_argument("--jobs", type=int, default=None,
                    help="processes for --seeds (default one per seed, at most the CPU count); "
                         "1 = one seed after another. The records are the same either way")
    args = ap.parse_args(argv)
    cfg = _load(args)
    t0 = time.perf_counter()
    out = Path(args.output) if args.output else cfg.resolve_path(cfg.engine.calibration_file)
    seeds = list(dict.fromkeys(int(s) for s in (args.seeds or [cfg.run.seed])))
    jobs = max(1, min(len(seeds), args.jobs or os.cpu_count() or 1))
    recs: dict[int, dict] = {}
    if jobs == 1:
        for s in seeds:
            recs[s] = _calibrate_seed(cfg, s, args.target)
            _print_calibration(s, recs[s])
    else:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            futures = {s: pool.submit(_calibrate_seed, cfg, s, args.target, f"seed {s}: ") for s in seeds}
            for s in seeds:
                recs[s] = futures[s].result()
        for s in seeds:
            _print_calibration(s, recs[s])
    rec = dict(recs[seeds[0]])
    if len(seeds) > 1:
        rec["by_seed"] = {str(s): {k: v for k, v in r.items() if k != "history"} for s, r in recs.items()}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(f"-> {out} [{time.perf_counter() - t0:.1f}s]")
    return 0


def _main_run(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m cordonlite.run",
                                 description="Run one Cordon-Lite arm (or 'calibrate').")
    _common_args(ap)
    ap.add_argument("--arm", choices=ARMS, default=None)
    ap.add_argument("--backend", choices=BACKENDS, default=None)
    ap.add_argument("--engine", choices=ENGINES, default=None)
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--fee-start", "--fee-start-day", dest="fee_start", type=int, default=None)
    ap.add_argument("--regime", choices=REGIMES, default=None)
    ap.add_argument("--peak-fee", type=float, default=None,
                    help="peak charge in NZ$ (fees.peak_fee: the ToU schedule scaled to this peak; 6 = the "
                         "SSC2026 schedule, 0 = no charge, the same run as --regime none)")
    ap.add_argument("--capacity-scale", type=float, default=None,
                    help="override the calibrated capacity scale")
    ap.add_argument("--out", default=None, help="runs folder (default run.runs_dir)")
    ap.add_argument("--name", default=None, help="run folder name (default <arm>_<backend>_<engine>_s<seed>)")
    ap.add_argument("--estimate", "--dry-run", dest="estimate", action="store_true",
                    help="count LLM calls with MockLLM and print an approximate token estimate")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    cfg = _load(args)
    variant = variant_suffix(cfg, load_config(args.config), args.capacity_scale, _set_overrides(args))
    if args.estimate:
        est = estimate(cfg, args.capacity_scale)
        out = cfg.resolve_path(args.out or cfg.run.runs_dir) / "estimates"
        out.mkdir(parents=True, exist_ok=True)
        # the name carries n and d already; the rest of the variant keeps e.g. --peak-fee 30 from
        # overwriting the canonical estimate
        rest = variant.removeprefix(f"_n{cfg.run.n_agents}").removeprefix(f"_d{cfg.run.n_days}")
        path = out / f"{cfg.run.arm}_n{cfg.run.n_agents}_d{cfg.run.n_days}_s{cfg.run.seed}{rest}.json"
        path.write_text(json.dumps(est, indent=1) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in est.items() if k != "calls_by_day"}, indent=1))
        print(f"-> {path}")
        return 0
    t0 = time.perf_counter()
    try:
        run_dir = run_simulation(cfg, Path(args.out) if args.out else None, args.capacity_scale,
                                 args.name, progress=not args.quiet, variant=variant)
    except RuntimeError as e:  # credentials, LLM fatal errors: one clear line, no traceback
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    finally:
        if cfg.run.engine == "netlogo":
            from cordonlite.engine import shutdown_netlogo_link

            shutdown_netlogo_link()
    meta = json.loads((run_dir / "summary.json").read_text())["meta"]
    print(f"run written to {run_dir} [{time.perf_counter() - t0:.1f}s]; decider calls "
          f"{meta['decider_calls_total']}, revenue NZ${meta['revenue_total']:.2f}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "calibrate":
        return _main_calibrate(argv[1:])
    return _main_run(argv)


if __name__ == "__main__":
    _argv = sys.argv[1:]
    _netlogo = "netlogo" in _argv
    rc = main(_argv)
    if _netlogo:  # the JVM may hang on interpreter exit
        from cordonlite.engine import hard_exit

        hard_exit(rc)
    sys.exit(rc)
