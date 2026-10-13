"""Configuration loader: config.toml -> frozen dataclasses, plus seeded random streams.

Usage:
    cfg = load_config()                                   # cordon_lite/config.toml
    cfg = load_config(overrides={"run.n_agents": 20})     # dotted-key overrides
    rng = stream(cfg.run.seed, "rule", agent_id, day)     # named numpy Generator

Every key in config.toml must map to a dataclass field and vice versa; unknown or
missing keys raise ``ConfigError`` so builders cannot silently diverge.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping

import numpy as np

ROOT: Path = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH: Path = ROOT / "config.toml"

ARMS: tuple[str, ...] = ("R-daily", "R-clock", "L-clock", "L-daily", "H-clock")   # H-clock: thinker.py
BACKENDS: tuple[str, ...] = ("mock", "anthropic")
ENGINES: tuple[str, ...] = ("py", "netlogo")
REGIMES: tuple[str, ...] = ("tou", "flat", "none")
EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")
TEMPLATE_ID: str = "cl-v3"   # cl-v3 (2026-10-09): no SKIP option, the willingness-to-pay sentence; cl-v2 added road traffic
# Templates of earlier runs: their config_snapshot.toml still loads, but the LLM decider renders TEMPLATE_ID only.
RETIRED_TEMPLATE_IDS: tuple[str, ...] = ("cl-v1", "cl-v2")
WTT_VOT_REFS: tuple[str, ...] = ("distribution_median", "sample_median")
# The server-side refusal fallback beta that accepts fallbacks="default".
FALLBACK_BETAS: tuple[str, ...] = ("server-side-fallback-2026-07-01",)
N_ARCHETYPES: int = 5
N_LEVELS: int = 5


class ConfigError(ValueError):
    """Raised for unknown, missing or invalid configuration values."""


# --------------------------------------------------------------------------- sections


@dataclass(frozen=True)
class RunConfig:
    seed: int
    n_agents: int
    n_days: int
    arm: str
    backend: str
    engine: str
    traits: str
    data_dir: str
    runs_dir: str
    compress_csv_over_mb: float = 100.0   # 2026-10-09: road_entries.csv above this size is written as .csv.gz


@dataclass(frozen=True)
class TimeConfig:
    sim_start_min: int
    sim_end_cap_min: int
    depart_earliest_min: int
    depart_latest_min: int
    depart_step_min: int
    tstar_earliest_min: int
    tstar_latest_min: int
    tstar_step_min: int
    retime_offsets_min: tuple[int, ...]
    initial_buffer_min: int
    anchor_offsets_min: tuple[int, ...] = (0, 15)   # early-start addition: departures added around each start anchor


@dataclass(frozen=True)
class FeesConfig:
    regime: str
    fee_start_day: int
    tou_points: tuple[tuple[float, float], ...]
    round_dp: int
    # 2026-10-09: NZ$ peak of the schedule (tou_points scaled to it; regime "flat" charges it all day);
    # 0 = no charge (as regime "none"). Replaced fees.scale and fees.fee_flat (_migrate_fees)
    peak_fee: float = 6.0


@dataclass(frozen=True)
class PrepConfig:
    roads_gpkg: str
    roads_layer: str
    cordon_gpkg: str
    cordon_name_field: str
    cordon_names: tuple[str, ...]
    crs_epsg: int
    node_round_m: float
    ff_factor: float
    n_origin_points: int
    local_frc: tuple[int, ...]
    density_radius_m: float
    od_csv: str
    n_corridors: int
    frc_capacity_vph: tuple[float, ...]
    map_sample_origins: int
    gate_rule: str = "first_entry"
    seed: int = 11
    # road congestion inputs (prep.build_roads, 2026-10-07)
    roads_shp: str = "netlogo7/gis/tomtom_major_roads.shp"
    adt_geojson: str = "../../SSC2026/netlogo/Data/Average_Daily_Traffic_Counts.geojson"
    adt_match_m: float = 30.0
    adt_propagate_m: float = 1000.0
    road_inbound_share: float = 0.6
    road_peak_ratio_default: float = 0.096
    road_commuter_car_share: float = 0.8
    road_tti_target: float = 1.714
    road_tti_window: tuple[int, int] = (480, 540)
    road_cap_k_bounds: tuple[float, float] = (0.02, 0.3)
    road_adt_floor_pct: float = 5.0
    road_tti_exclude_mwy: bool = True
    road_profile_start_min: int = 360
    road_profile: tuple[float, ...] = (0.32, 0.38, 0.46, 0.56, 0.67, 0.77, 0.87, 0.93, 1.01, 1.05,
                                       1.00, 0.93, 0.81, 0.73, 0.69, 0.65, 0.62, 0.60)


@dataclass(frozen=True)
class EngineConfig:
    netlogo_home: str
    model_path: str
    gui: bool
    capacity_mode: str
    rush_window_min: float
    agents_represented: float
    min_capacity_per_min: float
    min_capacity_vph: float = 0.0             # 2026-10-08: floor in vehicles/h; 0 = use min_capacity_per_min
    # integrator additions (calibration of corridor capacity)
    capacity_scale: float = 1.0
    use_calibration: bool = True
    calibration_file: str = "data/calibration.json"
    calib_target_peak_delay_min: float = 15.0
    calib_days: tuple[int, int] = (6, 10)
    calib_scale_bounds: tuple[float, float] = (0.05, 10.0)
    calib_max_iter: int = 25
    calib_tol_min: float = 0.25
    calib_bin_min: int = 15
    calib_metric: str = "car_weighted_mean"   # final fixer: "car_weighted_mean", "worst" or "busiest"
    calib_delay: str = "total"                # 2026-10-07: "total" (queue + road) or "queue"


@dataclass(frozen=True)
class RoadConfig:
    """Road congestion on the way to the gate (2026-10-07); enabled = False gives free-flow roads."""

    enabled: bool = True
    bpr_alpha: float = 0.15
    bpr_beta: int = 4
    speed_floor: float = 0.18
    flow_window_min: int = 15
    # motorway flow breakdown (2026-10-08)
    mwy_breakdown: bool = True
    mwy_breakdown_vc: float = 1.0
    mwy_recover_vc: float = 0.95
    mwy_capacity_drop: float = 0.10
    mwy_jam_speed: float = 0.45


@dataclass(frozen=True)
class PersonaConfig:
    vot_mu: float
    vot_sigma: float
    archetype_labels: tuple[str, ...]
    arch_weight: tuple[float, ...]
    vot_tilt: tuple[tuple[float, ...], ...]
    tstar_mean_min: tuple[int, ...]
    tstar_sd_min: tuple[float, ...]
    activity: tuple[str, ...]
    fixed_start: tuple[bool, ...]
    must_drive: tuple[bool, ...]
    sched_mult: tuple[float, ...]
    pt_allowed: tuple[bool, ...]
    wfh_allowed: tuple[bool, ...]
    company_car_prob: tuple[float, ...]
    company_car_prob_q5: tuple[float, ...]
    park_free_prob: tuple[float, ...]
    park_cost_paid: tuple[float, ...]
    n_twins: int
    early_shift_prob: tuple[float, ...] = (0.0, 0.0, 0.0, 0.0, 0.0)   # early-start addition: P(employer allows the early day)


@dataclass(frozen=True)
class TraitsConfig:
    shares_H: tuple[float, ...]
    shares_F: tuple[float, ...]
    shares_P: tuple[float, ...]
    shares_S: tuple[float, ...]
    off_level: int
    kappa_h: tuple[float, ...]
    phi: tuple[float, ...]
    omega: tuple[float, ...]
    eta: tuple[float, ...]
    kappa_h_disc_factor: float


@dataclass(frozen=True)
class CostsConfig:
    beta_ratio: float
    gamma_ratio: float
    fee_eps: float
    pt_fare: float
    pt_access_min: float
    pt_ratio_default: float
    pt_ratio_by_corridor: tuple[float, ...]
    pt_unavailable_corridors: tuple[int, ...]
    wfh_cost: float
    delay_bin_min: int
    pt_attitude_penalty: float = 0.0   # integrator addition (v3 PAP); 0 = specification GC
    pt_headway_min: int = 0            # final fixer: PT services on a headway grid (0 = exact t*)
    wfh_form: str = "spec"             # behaviour recalibration: "spec" (wfh_cost x phi) or "v3_relative"
    fuel_cost_per_km: float = 0.0      # fuel addition: NZ$/km of fuel; car fuel = 2 x path_km x this; 0 = no fuel cost
    early_start_min: int = 420         # early-start addition: start of the earlier working day (07:00)
    early_shift_cost: float = 0.0      # early-start addition: NZ$/day inconvenience of the early day, x phi(F)


@dataclass(frozen=True)
class WttConfig:
    """Willingness to travel (2026-10-09): exponential-decay willingness to pay (persona.willingness_to_pay).
    The defaults are the model before it (beta0 0 = no limit), so an older config_snapshot.toml loads."""

    beta0: float = 0.0                 # price sensitivity at VoT_ref; 0 = off (no limit)
    beta_clip: tuple[float, float] = (0.1, 2.0)   # bounds on beta = beta0 x VoT_ref / VoT
    vot_ref: str = "distribution_median"          # "distribution_median" (exp(persona.vot_mu)) or "sample_median"


@dataclass(frozen=True)
class MemoryConfig:
    window_days: int
    ema_alpha: float
    ratio_offset_min: float
    ratio_clip: tuple[float, float]
    ref_fee_update: str


@dataclass(frozen=True)
class ClockConfig:
    fee_change_threshold: float
    late_tolerance_by_F: tuple[int, ...]
    sustained_rel: float
    sustained_days: int
    discontinuity_triggers: tuple[str, ...]
    review_every_days: int = 0


@dataclass(frozen=True)
class EventsConfig:
    pt_disruption_day: int | tuple[int, ...]    # one day, or several (a list; 2026-10-13)
    pt_disruption_corridor: int
    pt_disruption_time_mult: float
    pt_disruption_announced: bool

    @property
    def disruption_days(self) -> tuple[int, ...]:
        """The PT disruption days: pt_disruption_day as a tuple (one day or a list of days)."""
        d = self.pt_disruption_day
        return tuple(int(x) for x in d) if isinstance(d, tuple) else (int(d),)


@dataclass(frozen=True)
class RulesConfig:
    sigma_rule: float


@dataclass(frozen=True)
class MockLLMConfig:
    w_time: float
    w_schedule: float
    w_fee: float
    w_parking: float
    w_pt: float
    w_wfh: float
    w_habit: float
    noise_sigma: float
    w_fuel: float = 1.0                # fuel addition: weight on gc_parts["fuel"]


@dataclass(frozen=True)
class LLMConfig:
    model: str
    allowed_models: tuple[str, ...]
    effort: str
    max_tokens: int
    use_fallbacks: bool
    fallback_beta: str
    max_concurrency: int
    max_retries: int
    invalid_output_retries: int
    template_id: str
    reason_max_words: int
    cache_dir: str
    mock: MockLLMConfig
    replicate: int = 0                 # final fixer: >0 adds a sample index to the cache key
    max_consecutive_errors: int = 5    # final fixer: stop the run after this many API errors in a row
    traits_off_prompt: str = "sentences"   # final fixer: "sentences" (level-3 text) or "omit"


@dataclass(frozen=True)
class Config:
    run: RunConfig
    time: TimeConfig
    fees: FeesConfig
    prep: PrepConfig
    engine: EngineConfig
    road: RoadConfig
    persona: PersonaConfig
    traits: TraitsConfig
    costs: CostsConfig
    wtt: WttConfig
    memory: MemoryConfig
    clock: ClockConfig
    events: EventsConfig
    rules: RulesConfig
    llm: LLMConfig
    source_path: str = field(default="", compare=False)

    def resolve_path(self, p: str | Path) -> Path:
        """Resolve a config path relative to the cordon_lite root."""
        p = Path(p)
        return p if p.is_absolute() else (ROOT / p).resolve()

    def to_dict(self) -> dict[str, Any]:
        """Nested plain dict (lists, not tuples) mirroring config.toml."""
        d = _to_plain(dataclasses.asdict(self))
        d.pop("source_path", None)
        return d

    def pt_ratio(self, corridor_id: int) -> float:
        """PT time ratio for a corridor (override list or default)."""
        lst = self.costs.pt_ratio_by_corridor
        if 0 <= corridor_id < len(lst):
            return float(lst[corridor_id])
        return float(self.costs.pt_ratio_default)


_SECTIONS: dict[str, type] = {
    "run": RunConfig,
    "time": TimeConfig,
    "fees": FeesConfig,
    "prep": PrepConfig,
    "engine": EngineConfig,
    "road": RoadConfig,
    "persona": PersonaConfig,
    "traits": TraitsConfig,
    "costs": CostsConfig,
    "wtt": WttConfig,
    "memory": MemoryConfig,
    "clock": ClockConfig,
    "events": EventsConfig,
    "rules": RulesConfig,
    "llm": LLMConfig,
}
_NESTED: dict[tuple[str, str], type] = {("llm", "mock"): MockLLMConfig}
# Keys added after the canonical runs were made (2026-10-09). A config_snapshot.toml written before then
# lacks them; load_config reads them with their dataclass default (wtt.beta0 0 is no willingness-to-pay
# limit). A section in _ADDED_SECTIONS may be missing as a whole. fees.peak_fee is derived from the
# snapshot's own schedule instead (_migrate_fees). Every other key must be present.
_ADDED_KEYS: tuple[tuple[str, str], ...] = (("run", "compress_csv_over_mb"),
                                           ("wtt", "beta0"), ("wtt", "beta_clip"), ("wtt", "vot_ref"))
_ADDED_SECTIONS: tuple[str, ...] = ("wtt",)
# Keys retired since (section path, key). An older config_snapshot.toml still has them; load_config drops
# them, so it loads. 2026-10-09: SKIP removed (costs.skip_cost, costs.skip_vot_hours, llm.mock.w_skip);
# the charge multiplier fees.scale and fees.fee_flat replaced by fees.peak_fee (_migrate_fees).
# An override of a retired key is an error (the key is not found).
_RETIRED_KEYS: tuple[tuple[str, str], ...] = (("costs", "skip_cost"), ("costs", "skip_vot_hours"),
                                             ("llm.mock", "w_skip"), ("fees", "scale"), ("fees", "fee_flat"))


# --------------------------------------------------------------------------- loading


def _to_tuple(v: Any) -> Any:
    if isinstance(v, list):
        return tuple(_to_tuple(x) for x in v)
    return v


def _to_plain(v: Any) -> Any:
    if isinstance(v, (list, tuple)):
        return [_to_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: _to_plain(x) for k, x in v.items()}
    return v


def _raw_table(raw: Mapping[str, Any], section: str) -> dict[str, Any] | None:
    """The table at a dotted section path ("costs", "llm.mock") of a raw TOML dict, or None."""
    node: Any = raw
    for part in section.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    return node if isinstance(node, dict) else None


def _migrate_fees(raw: dict[str, Any]) -> None:
    """fees.peak_fee for a config_snapshot.toml written before it existed (2026-10-09): the peak that run
    charged, fees.scale (1 when absent, i.e. before the charge multiplier) x fees.fee_flat for regime
    "flat", x the highest tou_points charge otherwise. A table that has peak_fee, or no fee_flat and no
    scale (the current config.toml), is left alone; scale and fee_flat are dropped later (_RETIRED_KEYS)."""
    f = raw.get("fees")
    if not isinstance(f, dict) or "peak_fee" in f or not ({"scale", "fee_flat"} & set(f)):
        return
    scale = float(f.get("scale", 1.0))
    if f.get("regime") == "flat" and "fee_flat" in f:
        f["peak_fee"] = float(f["fee_flat"]) * scale
    elif f.get("tou_points"):
        f["peak_fee"] = max(float(x[1]) for x in f["tou_points"]) * scale


def _build(cls: type, section: str, raw: Mapping[str, Any]) -> Any:
    names = {f.name for f in fields(cls)}
    unknown = set(raw) - names
    missing = names - set(raw)
    if unknown:
        raise ConfigError(f"[{section}] unknown keys: {sorted(unknown)}")
    if missing:
        raise ConfigError(f"[{section}] missing keys: {sorted(missing)}")
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        v = raw[f.name]
        nested = _NESTED.get((section, f.name))
        if nested is not None:
            kwargs[f.name] = _build(nested, f"{section}.{f.name}", v)
        else:
            kwargs[f.name] = _to_tuple(v)
    return cls(**kwargs)


def _kind(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, (list, tuple)):
        return "list"
    if isinstance(v, dict):
        return "table"
    return type(v).__name__


# keys that take one day or a list of days (--set events.pt_disruption_day=8 or =[3,8])
_DAY_OR_DAYS: frozenset[str] = frozenset({"events.pt_disruption_day"})


def _apply_overrides(raw: dict[str, Any], overrides: Mapping[str, Any]) -> None:
    """Apply dotted overrides; the value must have the same kind as the config value
    (bool, number, string, list), and an int config value only accepts an integral number."""
    for dotted, value in overrides.items():
        parts = dotted.split(".")
        node = raw
        for p in parts[:-1]:
            if p not in node or not isinstance(node[p], dict):
                raise ConfigError(f"override path not found: {dotted}")
            node = node[p]
        if parts[-1] not in node:
            raise ConfigError(f"override key not found: {dotted}")
        old = node[parts[-1]]
        if isinstance(value, tuple):
            value = list(value)
        if dotted in _DAY_OR_DAYS:      # an integral day or a non-empty list of them, whichever the config has
            days = value if isinstance(value, list) else [value]
            if not days or not all(_kind(x) == "number" and float(x).is_integer() for x in days):
                raise ConfigError(f"override {dotted}={value!r}: expected a day or a list of days")
            node[parts[-1]] = [int(x) for x in days] if isinstance(value, list) else int(value)
            continue
        if _kind(old) != _kind(value):
            raise ConfigError(f"override {dotted}={value!r}: expected a {_kind(old)} "
                              f"(current value {old!r})")
        if isinstance(old, int) and not isinstance(old, bool) and isinstance(value, float):
            if not value.is_integer():
                raise ConfigError(f"override {dotted}={value!r}: expected an integer")
            value = int(value)
        if isinstance(old, float) and isinstance(value, int) and not isinstance(value, bool):
            value = float(value)
        node[parts[-1]] = value


def _validate(cfg: Config) -> None:
    def check(cond: bool, msg: str) -> None:
        if not cond:
            raise ConfigError(msg)

    check(cfg.run.arm in ARMS, f"run.arm must be one of {ARMS}")
    check(cfg.run.backend in BACKENDS, f"run.backend must be one of {BACKENDS}")
    check(cfg.run.engine in ENGINES, f"run.engine must be one of {ENGINES}")
    check(cfg.run.traits in ("on", "off"), "run.traits must be 'on' or 'off'")
    check(cfg.fees.regime in REGIMES, f"fees.regime must be one of {REGIMES}")
    check(cfg.fees.peak_fee >= 0, "fees.peak_fee must be >= 0 (NZ$; 0 = no charge, as regime \"none\")")
    check(len(cfg.fees.tou_points) >= 1 and max(float(x[1]) for x in cfg.fees.tou_points) > 0,
          "fees.tou_points need a charge above 0 (fees.peak_fee scales them to the peak)")
    check(cfg.engine.capacity_mode in ("demand_share", "raw_scaled"), "engine.capacity_mode invalid")
    check(cfg.engine.capacity_scale > 0, "engine.capacity_scale must be > 0")
    lo, hi = cfg.engine.calib_scale_bounds
    check(0 < lo < hi, "engine.calib_scale_bounds must satisfy 0 < lo < hi")
    d0, d1 = cfg.engine.calib_days
    check(1 <= d0 <= d1, "engine.calib_days must satisfy 1 <= first <= last")
    check(cfg.memory.ref_fee_update in ("all_days", "car_days", "faced"),
          "memory.ref_fee_update must be all_days, car_days or faced")
    check(cfg.costs.wfh_form in ("spec", "v3_relative"), "costs.wfh_form must be spec or v3_relative")
    check(cfg.llm.model in cfg.llm.allowed_models, "llm.model not in llm.allowed_models")
    check(cfg.llm.effort in EFFORTS, f"llm.effort must be one of {EFFORTS}")
    check(cfg.llm.template_id == TEMPLATE_ID or cfg.llm.template_id in RETIRED_TEMPLATE_IDS,
          f"llm.template_id must be {TEMPLATE_ID!r} (the only implemented prompt template; an older run's "
          f"snapshot may name one of {RETIRED_TEMPLATE_IDS})")
    check(cfg.llm.fallback_beta in FALLBACK_BETAS,
          f"llm.fallback_beta must be one of {FALLBACK_BETAS} (the beta that accepts fallbacks='default')")
    check(cfg.llm.replicate >= 0, "llm.replicate must be >= 0")
    check(cfg.llm.traits_off_prompt in ("sentences", "omit"), "llm.traits_off_prompt must be sentences or omit")
    check(cfg.llm.max_tokens >= 1 and cfg.llm.max_concurrency >= 1, "llm.max_tokens and max_concurrency must be >= 1")
    check(cfg.engine.calib_metric in ("car_weighted_mean", "worst", "busiest"),
          "engine.calib_metric must be car_weighted_mean, worst or busiest")
    check(cfg.engine.calib_delay in ("total", "queue"), "engine.calib_delay must be total or queue")
    check(cfg.costs.pt_headway_min >= 0, "costs.pt_headway_min must be >= 0")
    pd_ = cfg.events.pt_disruption_day
    check(all(isinstance(x, int) and not isinstance(x, bool) for x in (pd_ if isinstance(pd_, tuple) else (pd_,)))
          and pd_ != (), "events.pt_disruption_day must be a day or a non-empty list of days")
    w = cfg.wtt
    check(w.beta0 >= 0, "wtt.beta0 must be >= 0 (0 = no willingness-to-pay limit)")
    check(len(w.beta_clip) == 2 and 0 < w.beta_clip[0] <= w.beta_clip[1],
          "wtt.beta_clip must be [lo, hi] with 0 < lo <= hi")
    check(w.vot_ref in WTT_VOT_REFS, f"wtt.vot_ref must be one of {WTT_VOT_REFS}")
    check(cfg.costs.fuel_cost_per_km >= 0, "costs.fuel_cost_per_km must be >= 0")
    check(cfg.costs.early_shift_cost >= 0, "costs.early_shift_cost must be >= 0")
    check(0 <= cfg.costs.early_start_min < 1440, "costs.early_start_min must be a minute of the day")
    check(all(0.0 <= x <= 1.0 for x in cfg.persona.early_shift_prob), "persona.early_shift_prob entries must be in [0, 1]")
    check(all(x >= 0 for x in cfg.time.anchor_offsets_min), "time.anchor_offsets_min entries must be >= 0")
    p = cfg.persona
    for name in ("archetype_labels", "arch_weight", "vot_tilt", "tstar_mean_min", "tstar_sd_min",
                 "activity", "fixed_start", "must_drive", "sched_mult", "pt_allowed", "wfh_allowed",
                 "company_car_prob", "company_car_prob_q5", "park_free_prob", "park_cost_paid",
                 "early_shift_prob"):
        check(len(getattr(p, name)) == N_ARCHETYPES, f"persona.{name} needs {N_ARCHETYPES} entries")
    check(all(len(r) == 5 for r in p.vot_tilt), "persona.vot_tilt rows need 5 quintiles")
    t = cfg.traits
    for name in ("shares_H", "shares_F", "shares_P", "shares_S", "kappa_h", "phi", "omega", "eta"):
        check(len(getattr(t, name)) == N_LEVELS, f"traits.{name} needs {N_LEVELS} entries")
    for name in ("shares_H", "shares_F", "shares_P", "shares_S"):
        check(abs(sum(getattr(t, name)) - 1.0) < 1e-9, f"traits.{name} must sum to 1")
    check(1 <= t.off_level <= N_LEVELS, "traits.off_level out of range")
    check(len(cfg.clock.late_tolerance_by_F) == N_LEVELS, "clock.late_tolerance_by_F needs 5 entries")
    check(cfg.prep.gate_rule in ("last_entry", "first_entry"), "prep.gate_rule must be last_entry or first_entry")
    check(len(cfg.prep.frc_capacity_vph) == 5, "prep.frc_capacity_vph needs 5 entries (frc 0..4)")
    r = cfg.road
    check(r.bpr_beta == 4, "road.bpr_beta must be 4 (the engines compute (x*x)*(x*x))")
    check(r.bpr_alpha >= 0, "road.bpr_alpha must be >= 0")
    check(0 < r.speed_floor <= 1, "road.speed_floor must be in (0, 1]")
    check(r.flow_window_min >= 1, "road.flow_window_min must be >= 1")
    check(0 < r.mwy_recover_vc <= r.mwy_breakdown_vc, "road.mwy_recover_vc must be in (0, mwy_breakdown_vc]")
    check(0 <= r.mwy_capacity_drop < 1, "road.mwy_capacity_drop must be in [0, 1)")
    check(r.speed_floor <= r.mwy_jam_speed <= 1, "road.mwy_jam_speed must be in [speed_floor, 1]")
    check(cfg.engine.min_capacity_vph >= 0, "engine.min_capacity_vph must be >= 0")
    pr = cfg.prep
    check(0 < pr.road_inbound_share <= 1, "prep.road_inbound_share must be in (0, 1]")
    check(0 < pr.road_commuter_car_share <= 1, "prep.road_commuter_car_share must be in (0, 1]")
    check(len(pr.road_profile) >= 1 and all(x >= 0 for x in pr.road_profile),
          "prep.road_profile needs non-negative entries")
    k0, k1 = pr.road_cap_k_bounds
    check(0 < k0 < k1, "prep.road_cap_k_bounds must satisfy 0 < lo < hi")
    w0, w1 = pr.road_tti_window
    check(0 <= w0 < w1 <= 1440, "prep.road_tti_window must be minutes with first < last")
    tm = cfg.time
    check(tm.sim_start_min <= tm.depart_earliest_min <= tm.depart_latest_min < tm.sim_end_cap_min,
          "time window inconsistent")
    check(p.n_twins >= 0, "persona.n_twins must be >= 0 (effective value is min(n_twins, n_agents // 2))")
    check(cfg.run.n_agents >= 1 and cfg.run.n_days >= 1, "run.n_agents and run.n_days must be >= 1")
    check(cfg.run.compress_csv_over_mb >= 0, "run.compress_csv_over_mb must be >= 0")


def load_config(path: str | Path | None = None,
                overrides: Mapping[str, Any] | None = None) -> Config:
    """Read config.toml (default: cordon_lite/config.toml), apply dotted overrides, validate.

    Unknown and missing keys are errors, except the _ADDED_KEYS (and _ADDED_SECTIONS), which an
    older run's config_snapshot.toml may lack (they take their dataclass default), fees.peak_fee,
    which it may lack too (_migrate_fees: the peak of its own schedule), and the _RETIRED_KEYS, which
    it may still have (they are dropped)."""
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    raw = copy.deepcopy(raw)
    _migrate_fees(raw)
    for section in _ADDED_SECTIONS:
        raw.setdefault(section, {})
    for section, key in _ADDED_KEYS:
        if isinstance(raw.get(section), dict) and key not in raw[section]:
            raw[section][key] = _to_plain({f.name: f.default for f in fields(_SECTIONS[section])}[key])
    for section, key in _RETIRED_KEYS:
        table = _raw_table(raw, section)
        if table is not None:
            table.pop(key, None)
    if overrides:
        _apply_overrides(raw, overrides)
    unknown = set(raw) - set(_SECTIONS)
    missing = set(_SECTIONS) - set(raw)
    if unknown:
        raise ConfigError(f"unknown sections: {sorted(unknown)}")
    if missing:
        raise ConfigError(f"missing sections: {sorted(missing)}")
    sections = {name: _build(cls, name, raw[name]) for name, cls in _SECTIONS.items()}
    cfg = Config(**sections, source_path=str(path))
    _validate(cfg)
    return cfg


# --------------------------------------------------------------------------- TOML dump


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    raise TypeError(f"cannot serialise {type(v)}")


def dump_toml(cfg: Config) -> str:
    """Serialise the effective config (after overrides) as TOML, for config_snapshot.toml."""
    out: list[str] = []
    d = cfg.to_dict()
    for section, body in d.items():
        scalars = {k: v for k, v in body.items() if not isinstance(v, dict)}
        tables = {k: v for k, v in body.items() if isinstance(v, dict)}
        out.append(f"[{section}]")
        out += [f"{k} = {_toml_value(v)}" for k, v in scalars.items()]
        out.append("")
        for tname, tbody in tables.items():
            out.append(f"[{section}.{tname}]")
            out += [f"{k} = {_toml_value(v)}" for k, v in tbody.items()]
            out.append("")
    return "\n".join(out)


# --------------------------------------------------------------------------- random streams


def _key_int(part: int | str) -> int:
    """Map a stream key part to a non-negative int (strings via sha256, stable across runs)."""
    if isinstance(part, (bool, np.bool_)):
        raise TypeError("bool is not a valid stream key part")
    if isinstance(part, (int, np.integer)):
        if part < 0:
            raise ValueError("stream key ints must be non-negative")
        return int(part)
    if isinstance(part, str):
        return int.from_bytes(hashlib.sha256(part.encode("utf-8")).digest()[:4], "big")
    raise TypeError(f"invalid stream key part: {part!r}")


def seed_sequence(seed: int, *key: int | str) -> np.random.SeedSequence:
    """SeedSequence for a named stream, e.g. seed_sequence(11, "rule", 5, 12)."""
    return np.random.SeedSequence(entropy=int(seed), spawn_key=tuple(_key_int(k) for k in key))


def stream(seed: int, *key: int | str) -> np.random.Generator:
    """Independent numpy Generator for a named stream.

    Conventional keys: ("A",), ("B",), ("rule", agent_id, day), ("events",), ("prep",).
    """
    return np.random.default_rng(seed_sequence(seed, *key))
