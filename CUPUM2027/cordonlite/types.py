"""Shared dataclasses passed between modules. No logic beyond trivial properties.

Conventions:
- Times are integer minutes since midnight unless a name says otherwise.
- Money is NZ$. VoT is NZ$/h.
- Modes: "CAR", "PT", "WFH", "SKIP".
- Option ids: "CAR_hhmm" (departure clock time, e.g. "CAR_0745"), "PT", "WFH", "SKIP".
- Deciders: "rule", "llm", "llm-fallback-rule", "standing", "forced".
- Triggers: "T1".."T6" (see clock.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence

MODES: tuple[str, ...] = ("CAR", "PT", "WFH", "SKIP")
DECIDERS: tuple[str, ...] = ("rule", "llm", "llm-fallback-rule", "standing", "forced")
TRIGGERS: tuple[str, ...] = ("T1", "T2", "T3", "T4", "T5", "T6", "T7")
FACTORS: tuple[str, ...] = (
    "fee", "travel_time", "arrival_time", "habit", "pt", "flexibility",
    "past_experience", "disruption", "work_constraint", "other",
)
# Keys of Option.gc_parts; gc == sum(gc_parts.values()).
GC_PARTS: tuple[str, ...] = ("time", "schedule", "fee", "parking", "fuel", "pt", "wfh", "skip", "habit")

# Public corridor delay profile from yesterday: corridor_id -> sorted ((bin_mid_minute, mean_queue_delay_min), ...).
# Empty tuple for a corridor = no information (expected public delay 0).
DelayProfile = Mapping[int, tuple[tuple[float, float], ...]]


def option_id_for(mode: str, depart_min: int | None = None) -> str:
    """Canonical option id: CAR_hhmm for cars, otherwise the mode."""
    if mode == "CAR":
        if depart_min is None:
            raise ValueError("CAR option needs depart_min")
        return f"CAR_{depart_min // 60:02d}{depart_min % 60:02d}"
    return mode


def clock_str(minute: int | float) -> str:
    """'hh:mm' for a minute since midnight (rounded to the nearest minute)."""
    m = int(round(minute))
    return f"{m // 60:02d}:{m % 60:02d}"


@dataclass(frozen=True)
class Persona:
    """One commuter: Layer A constraints and Layer B traits (static for the run)."""

    agent_id: int
    # Layer A: geography (from origins.csv)
    origin_id: int
    corridor_id: int
    x_nztm: float
    y_nztm: float
    fftt_to_gate_min: int          # rounded free-flow minutes origin -> gate (engine input)
    fftt_gate_to_dest_min: int     # rounded free-flow minutes gate -> destination (engine input)
    path_km: float
    # Layer A: economics and constraints
    vot: float                     # NZ$/h
    vot_quintile: int              # 1..5 within this population
    archetype: int                 # 1..5, internal only (never rendered to the LLM)
    activity: str                  # "work" or "study"
    tstar_min: int                 # desired arrival (work/class start)
    fixed_start: bool
    must_drive: bool               # tools/goods; no PT, no WFH
    sched_mult: float              # archetype multiplier on schedule-delay cost
    pt_allowed: bool               # archetype allows PT AND corridor has PT
    wfh_allowed: bool
    company_car: bool              # charge paid by employer (perceived fee 0, still counted as revenue)
    parking_cost: float            # NZ$/day when driving
    pt_time_min: float             # undisrupted door-to-door PT time
    pt_fare: float                 # NZ$/day
    # Layer B: traits, levels 1..5
    H: int
    F: int
    P: int
    S: int
    # Layer A (fuel addition; declared last with a default so older constructors keep working):
    # NZ$/day of fuel when driving = round(2 x path_km x costs.fuel_cost_per_km, 2); 0 for a company car
    fuel_cost: float = 0.0
    # Layer A (early-start addition): the employer allows an earlier working day (costs.early_start_min,
    # e.g. 07:00 to 15:00) on any day the commuter chooses; drawn after every other Layer A draw
    early_shift_ok: bool = False

    @property
    def fftt_total_min(self) -> int:
        return self.fftt_to_gate_min + self.fftt_gate_to_dest_min


@dataclass(frozen=True)
class TraitParams:
    """Rule parameters derived from Layer B (v3 section 4.4)."""

    kappa_h: float   # by H
    phi: float       # by F
    omega: float     # by P
    eta: float       # by S


@dataclass(frozen=True)
class Option:
    """One feasible option for one agent-day, with human-readable attributes and GC.

    The prompt shows every attribute except ``gc`` and ``gc_parts``.
    For non-car options the car-specific fields are None.
    """

    option_id: str
    mode: str
    depart_min: int | None
    expected_gate_arrive_min: int | None
    expected_delay_min: float | None       # expected queue delay at the gate
    expected_gate_exit_min: int | None     # minute at which the fee is evaluated
    expected_travel_min: float             # door to door (0 for WFH/SKIP)
    expected_arrive_min: int | None        # at destination
    early_min: float
    late_min: float
    fee: float                             # charge levied (0 if inactive); company-car agents see it as employer-paid
    parking: float
    pt_time_min: float | None
    pt_fare: float | None
    is_standing: bool
    gc: float
    gc_parts: Mapping[str, float] = field(default_factory=dict)
    # Added by the behaviour builder (additive): yesterday's PUBLIC corridor delay forecast at the
    # expected gate arrival (before the personal EMA ratio). CAR only; None otherwise. The
    # integrator stores it in MemoryRecord.expected_delay_min; the prompt may show it as
    # "yesterday's corridor delay for this departure time".
    expected_public_delay_min: float | None = None
    # Fuel addition: NZ$/day of fuel for the round trip (persona.fuel_cost) for CAR options, 0 otherwise.
    # Shown in the prompt (options table column "fuel"); the rule adds it as gc_parts["fuel"].
    fuel: float = 0.0
    # Early-start addition: the start time this option is measured against (CAR and PT; None for
    # WFH/SKIP). It is the usual start t*, or costs.early_start_min when the commuter may start early
    # and that target is cheaper for this option; early_min and late_min refer to it. Shown in the
    # prompt (options table column "start").
    start_used_min: int | None = None
    early_shift: bool = False              # True when start_used_min is the early start


@dataclass(frozen=True)
class MemoryRecord:
    """What one agent did and experienced on one day (Layer C)."""

    day: int
    option_id: str
    mode: str
    depart_min: int | None
    queue_delay_min: float | None
    expected_delay_min: float | None       # PUBLIC forecast (before personal ratio) for the chosen car option
    expected_travel_min: float | None      # Option.expected_travel_min of the chosen option (incl. personal ratio)
    travel_min: float | None               # experienced door to door
    arrive_min: int | None
    early_min: float
    late_min: float
    fee_paid: float
    pt_disrupted: bool
    decider: str
    triggers: tuple[str, ...]
    reason: str
    # Early-start addition: the start the day was measured against (None for WFH/SKIP)
    start_used_min: int | None = None
    early_shift: bool = False


@dataclass(frozen=True)
class TodayInfo:
    """Public information for one morning, shared by all agents."""

    day: int
    fee_regime: str
    fee_active: bool
    fee_by_minute: tuple[float, ...]       # 1440 entries; all zero when inactive
    fee_changed_today: bool                # T2 condition (global)
    public_delay: DelayProfile             # yesterday's mean queue delay by gate-arrival minute
    pt_disrupted_corridors: frozenset[int] # corridors with PT disruption today
    pt_disruption_announced: bool
    pt_disruption_time_mult: float


@dataclass(frozen=True)
class DecisionContext:
    """Everything a decider sees for one agent-day."""

    agent_id: int
    day: int
    persona: Persona
    params: TraitParams
    options: tuple[Option, ...]            # feasible only, deterministic order (CAR by depart, PT, WFH, SKIP)
    standing_option_id: str | None
    triggers: tuple[str, ...]
    discontinuity: bool                    # kappa_H was scaled by kappa_h_disc_factor
    recent: tuple[MemoryRecord, ...]       # last window_days records, oldest first
    delay_ratio_ema: float
    ref_fee: float
    today: TodayInfo
    traits_shown: bool = True              # False when run.traits == "off" (prompt omits dispositions)

    @property
    def option_ids(self) -> tuple[str, ...]:
        return tuple(o.option_id for o in self.options)

    def option(self, option_id: str) -> Option:
        for o in self.options:
            if o.option_id == option_id:
                return o
        raise KeyError(option_id)


@dataclass(frozen=True)
class Decision:
    """A decider's output for one agent-day."""

    agent_id: int
    day: int
    option_id: str
    decider: str
    reason: str = ""
    factors: tuple[str, ...] = ()
    meta: Mapping[str, object] = field(default_factory=dict)


class Decider(Protocol):
    """Rule, MockLLM-backed or Anthropic-backed decision maker."""

    name: str

    def decide_batch(self, contexts: Sequence[DecisionContext]) -> list[Decision]:
        """Decide for every context; output order matches input order."""
        ...
