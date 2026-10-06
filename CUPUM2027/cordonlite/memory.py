"""Layer C memory: per-agent day records, delay-ratio EMA, reference fee, standing option.

Simplified from ../docs/design_history/persona_design_v3.md section 5 (see DEVIATIONS.md, "Behaviour builder").

Public API:
    AgentMemory                     dataclass (records, delay_ratio_ema, ref_fee, standing option,
                                    consumed_events for clock.py edge triggering)
    new_memory(agent_id, company_car=False) -> AgentMemory
    update_memory(mem, record, cfg, fee_faced=None) -> None
        Appends the record. On car days with a served car and a public forecast:
        r = (queue_delay + offset) / (expected_public_delay + offset), clipped to ratio_clip,
        ema <- ema + alpha * (r - ema). Reference fee: ref <- ref + alpha * (perceived - ref)
        every day ("all_days", perceived = fee paid, 0 on non-car days), on car days only
        ("car_days"), or every day with the fee FACED ("faced", v3 5.2 fee-ref: the fee paid on a
        car day, otherwise ``fee_faced``, the charge at the agent's car reference departure, see
        options.fee_faced; behaviour recalibration). Perceived fee is 0 for company-car agents.
    set_standing(mem, option) -> None
    record_from_outcome(row, option, decider, triggers, reason) -> MemoryRecord
    memory_frame(memories) -> pd.DataFrame          # one row per (agent, day) record
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

import pandas as pd

from cordonlite.config import Config
from cordonlite.types import MemoryRecord, Option


@dataclass
class AgentMemory:
    """Mutable per-agent memory (Layer C)."""

    agent_id: int
    records: list[MemoryRecord] = field(default_factory=list)
    delay_ratio_ema: float = 1.0
    ref_fee: float = 0.0
    standing_option_id: str | None = None
    standing_mode: str | None = None
    standing_depart_min: int | None = None
    consumed_events: set[tuple[str, int]] = field(default_factory=set)
    company_car: bool = False          # perceived fee 0 for the reference-fee update

    def recent(self, n: int) -> tuple[MemoryRecord, ...]:
        """Last n records, oldest first."""
        return tuple(self.records[-n:]) if n > 0 else ()

    def last(self) -> MemoryRecord | None:
        return self.records[-1] if self.records else None

    def car_records(self) -> list[MemoryRecord]:
        """All car-day records, oldest first."""
        return [r for r in self.records if r.mode == "CAR"]

    @property
    def habit_option_id(self) -> str | None:
        """Habit reference: the standing option, except that a standing SKIP is not a habit (a
        one-day postponement); then the most recent non-SKIP option, or None."""
        if self.standing_option_id != "SKIP":
            return self.standing_option_id
        for r in reversed(self.records):
            if r.mode != "SKIP":
                return r.option_id
        return None

    def last_car_depart_min(self) -> int | None:
        """Departure minute of the most recent car day, if any."""
        for r in reversed(self.records):
            if r.mode == "CAR" and r.depart_min is not None:
                return int(r.depart_min)
        return None


def new_memory(agent_id: int, company_car: bool = False) -> AgentMemory:
    """Empty memory: no standing option, ratio 1, reference fee 0."""
    return AgentMemory(agent_id=int(agent_id), company_car=bool(company_car))


def _served(record: MemoryRecord) -> bool:
    return record.queue_delay_min is not None and record.queue_delay_min >= 0


def update_memory(mem: AgentMemory, record: MemoryRecord, cfg: Config,
                  fee_faced: float | None = None) -> None:
    """Append a day record and update the delay-ratio EMA and the reference fee.

    ``fee_faced`` is used only with ``memory.ref_fee_update = "faced"`` on non-car days (the
    charge the agent would have met at its car reference departure; None counts as 0)."""
    if mem.records and record.day <= mem.records[-1].day:
        raise ValueError(f"agent {mem.agent_id}: record day {record.day} not after {mem.records[-1].day}")
    mem.records.append(record)
    mc = cfg.memory
    alpha = float(mc.ema_alpha)
    is_car = record.mode == "CAR"
    if is_car and _served(record) and record.expected_delay_min is not None:
        off = float(mc.ratio_offset_min)
        r = (float(record.queue_delay_min) + off) / (float(record.expected_delay_min) + off)
        lo, hi = mc.ratio_clip
        r = min(max(r, float(lo)), float(hi))
        mem.delay_ratio_ema = mem.delay_ratio_ema + alpha * (r - mem.delay_ratio_ema)
    if mc.ref_fee_update == "faced":
        if mem.company_car:
            perceived = 0.0
        elif is_car:
            perceived = float(record.fee_paid)
        else:
            perceived = float(fee_faced or 0.0)
        mem.ref_fee = mem.ref_fee + alpha * (perceived - mem.ref_fee)
    elif mc.ref_fee_update == "all_days" or is_car:
        perceived = 0.0 if (mem.company_car or not is_car) else float(record.fee_paid)
        mem.ref_fee = mem.ref_fee + alpha * (perceived - mem.ref_fee)


def set_standing(mem: AgentMemory, option: Option) -> None:
    """Make ``option`` the standing option executed until the next wake."""
    mem.standing_option_id = option.option_id
    mem.standing_mode = option.mode
    mem.standing_depart_min = option.depart_min if option.mode == "CAR" else None


def _opt_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        if pd.isna(v):  # type: ignore[arg-type]
            return None
    except (TypeError, ValueError):
        pass
    return float(v)  # type: ignore[arg-type]


def _opt_int(v: object) -> int | None:
    f = _opt_float(v)
    return None if f is None else int(round(f))


def record_from_outcome(row: Mapping[str, object], option: Option, decider: str,
                        triggers: Sequence[str] = (), reason: str = "") -> MemoryRecord:
    """MemoryRecord from an outcomes.csv-style row (see options.car_outcome / non_car_outcome).

    ``expected_delay_min`` is the option's PUBLIC forecast; ``expected_travel_min`` the option's
    expected door-to-door time (including the personal ratio).
    """
    mode = str(row["mode"])
    car = mode == "CAR"
    return MemoryRecord(
        day=int(row["day"]),  # type: ignore[arg-type]
        option_id=str(row["option_id"]),
        mode=mode,
        depart_min=_opt_int(row.get("depart_min")),
        queue_delay_min=_opt_float(row.get("queue_delay_min")) if car else None,
        expected_delay_min=option.expected_public_delay_min if car else None,
        expected_travel_min=float(option.expected_travel_min) if mode in ("CAR", "PT") else None,
        travel_min=_opt_float(row.get("travel_min")) if mode in ("CAR", "PT") else None,
        arrive_min=_opt_int(row.get("arrive_min")),
        early_min=_opt_float(row.get("early_min")) or 0.0,
        late_min=_opt_float(row.get("late_min")) or 0.0,
        fee_paid=_opt_float(row.get("fee_paid")) or 0.0,
        pt_disrupted=bool(row.get("pt_disrupted", False)) and mode == "PT",
        decider=str(decider),
        triggers=tuple(triggers),
        reason=str(reason),
        start_used_min=_opt_int(row.get("start_used_min")) if mode in ("CAR", "PT") else None,
        early_shift=bool(row.get("early_shift") or False) and mode in ("CAR", "PT"),
    )


def memory_frame(memories: Iterable[AgentMemory]) -> pd.DataFrame:
    """Long frame: agent_id + MemoryRecord fields (triggers ';'-joined), sorted by agent, day."""
    cols = ["agent_id"] + [f.name for f in dataclasses.fields(MemoryRecord)]
    rows = []
    for m in memories:
        for r in m.records:
            d = dataclasses.asdict(r)
            d["triggers"] = ";".join(r.triggers)
            rows.append({"agent_id": m.agent_id, **d})
    df = pd.DataFrame(rows, columns=cols)
    return df.sort_values(["agent_id", "day"], kind="stable").reset_index(drop=True)
