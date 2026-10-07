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

# H-clock (cordonlite/planner.py): the LLM plans, the rule chooses the minute
ARMS: tuple[str, ...] = ("R-daily", "R-clock", "L-clock", "L-daily", "H-clock")
BACKENDS: tuple[str, ...] = ("mock", "anthropic")
ENGINES: tuple[str, ...] = ("py", "netlogo")
REGIMES: tuple[str, ...] = ("tou", "flat", "none")
EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")
TEMPLATE_ID: str = "cl-v1"
# Implemented prompt templates: cl-v1 (default) and cl-v2 (adds the "you pay today" column and the
# main_factor / second_factor reply; see cordonlite/llm.py).
TEMPLATE_IDS: tuple[str, ...] = ("cl-v1", "cl-v2", "plan-v1", "plan-v2", "think-v1")   # plan-*, think-*: arm H-clock only (planner.py, thinker.py)
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
    fee_flat: float
    tou_points: tuple[tuple[float, float], ...]
    round_dp: int


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


@dataclass(frozen=True)
class EngineConfig:
    netlogo_home: str
    model_path: str
    gui: bool
    capacity_mode: str
    rush_window_min: float
    agents_represented: float
    min_capacity_per_min: float
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
    skip_cost: float
    delay_bin_min: int
    pt_attitude_penalty: float = 0.0   # integrator addition (v3 PAP); 0 = specification GC
    skip_vot_hours: float = 0.0        # final fixer: SKIP cost = skip_cost + skip_vot_hours * VoT
    pt_headway_min: int = 0            # final fixer: PT services on a headway grid (0 = exact t*)
    wfh_form: str = "spec"             # behaviour recalibration: "spec" (wfh_cost x phi) or "v3_relative"
    fuel_cost_per_km: float = 0.0      # fuel addition: NZ$/km of fuel; car fuel = 2 x path_km x this; 0 = no fuel cost
    early_start_min: int = 420         # early-start addition: start of the earlier working day (07:00)
    early_shift_cost: float = 0.0      # early-start addition: NZ$/day inconvenience of the early day, x phi(F)


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
    pt_disruption_day: int
    pt_disruption_corridor: int
    pt_disruption_time_mult: float
    pt_disruption_announced: bool


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
    w_skip: float
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
    persona: PersonaConfig
    traits: TraitsConfig
    costs: CostsConfig
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
    "persona": PersonaConfig,
    "traits": TraitsConfig,
    "costs": CostsConfig,
    "memory": MemoryConfig,
    "clock": ClockConfig,
    "events": EventsConfig,
    "rules": RulesConfig,
    "llm": LLMConfig,
}
_NESTED: dict[tuple[str, str], type] = {("llm", "mock"): MockLLMConfig}


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
    check(cfg.llm.template_id in TEMPLATE_IDS, f"llm.template_id must be one of {TEMPLATE_IDS} (the "
          "implemented prompt templates)")
    check(not (cfg.llm.template_id.startswith(("plan-", "think-")) and cfg.run.arm.startswith("L-")),
          "llm.template_id plan-v1 / plan-v2 / think-v1 belongs to arm H-clock; the L arms use cl-v1 or cl-v2")
    check(cfg.llm.fallback_beta in FALLBACK_BETAS,
          f"llm.fallback_beta must be one of {FALLBACK_BETAS} (the beta that accepts fallbacks='default')")
    check(cfg.llm.replicate >= 0, "llm.replicate must be >= 0")
    check(cfg.llm.traits_off_prompt in ("sentences", "omit"), "llm.traits_off_prompt must be sentences or omit")
    check(cfg.llm.max_tokens >= 1 and cfg.llm.max_concurrency >= 1, "llm.max_tokens and max_concurrency must be >= 1")
    check(cfg.engine.calib_metric in ("car_weighted_mean", "worst", "busiest"),
          "engine.calib_metric must be car_weighted_mean, worst or busiest")
    check(cfg.costs.skip_vot_hours >= 0 and cfg.costs.pt_headway_min >= 0,
          "costs.skip_vot_hours and costs.pt_headway_min must be >= 0")
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
    tm = cfg.time
    check(tm.sim_start_min <= tm.depart_earliest_min <= tm.depart_latest_min < tm.sim_end_cap_min,
          "time window inconsistent")
    check(p.n_twins >= 0, "persona.n_twins must be >= 0 (effective value is min(n_twins, n_agents // 2))")
    check(cfg.run.n_agents >= 1 and cfg.run.n_days >= 1, "run.n_agents and run.n_days must be >= 1")


def load_config(path: str | Path | None = None,
                overrides: Mapping[str, Any] | None = None) -> Config:
    """Read config.toml (default: cordon_lite/config.toml), apply dotted overrides, validate."""
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    raw = copy.deepcopy(raw)
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
