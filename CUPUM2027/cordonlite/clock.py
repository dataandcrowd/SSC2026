"""Cognitive clock: edge-triggered wake-up events T1..T6.

Triggers (event key used for edge triggering in brackets):
    T1 no standing option yet                                                  [("T1", today)]
    T2 fee regime change today (TodayInfo.fee_changed_today)                   [("T2", today)]
    T3 late yesterday by more than late_tolerance_by_F[F-1] minutes            [("T3", record day)]
    T4 PT disruption experienced on the last day, or announced today on own
       corridor while the standing mode is PT                                  [("T4", disruption day)]
       and, as the end of the same event, the day after an announced disruption that woke the
       agent, once its corridor runs normally again (final fixer)              [("T4-end", disruption day)]
    T5 the last sustained_days car days each had |travel / expected - 1| >
       sustained_rel, and this was not yet so at the previous car day (edge)   [("T5", latest car day)]
    T6 standing option infeasible today; a standing SKIP is always infeasible
       (skipping is a one-day postponement, not a plan; integrator addition)  [("T6", today)]
    T7 periodic review (off by default): the agent has followed its standing plan without a
       decision for clock.review_every_days days (sensitivity to event-only waking) [("T7", today)]
An event key fires once: it is stored in ``memory.consumed_events`` when returned.
A T4 announcement on day d and the experience of the same disruption share key ("T4", d), so
one disruption wakes an agent once when it starts. The "T4-end" key wakes the agents that the
announcement woke once more on day d+1 (reported as trigger "T4"), so a rider who switched mode for
the disrupted day, or who stayed on PT, reconsiders when service is back. Without it a one-day
disruption would move riders to the car for good under the clock arms.

Public API:
    evaluate_triggers(persona, memory, today, feasible_option_ids, cfg) -> tuple[str, ...]
        ``feasible_option_ids`` may be option ids or feasible modes: a non-car standing option is
        feasible if its id is listed; a standing CAR departure is feasible if "CAR" (or any CAR_
        id) is listed and the departure lies inside the departure window.
    is_discontinuity(triggers, cfg) -> bool
    should_wake(arm, triggers) -> bool
"""

from __future__ import annotations

from typing import Sequence

from cordonlite.config import ARMS, Config
from cordonlite.memory import AgentMemory
from cordonlite.types import MemoryRecord, Persona, TodayInfo


def _gap_exceeded(r: MemoryRecord, rel: float) -> bool:
    if r.queue_delay_min is not None and r.queue_delay_min < 0:  # unserved car: counts as a large gap
        return True
    if r.travel_min is None or r.expected_travel_min is None or r.expected_travel_min <= 0:
        return False
    return abs(r.travel_min / r.expected_travel_min - 1.0) > rel


def _sustained_at(cars: list[MemoryRecord], end: int, n: int, rel: float) -> bool:
    """True if the n car records ending at index ``end`` (inclusive) all exceed the gap."""
    if n <= 0 or end - n + 1 < 0:
        return False
    return all(_gap_exceeded(cars[j], rel) for j in range(end - n + 1, end + 1))


def _standing_feasible(memory: AgentMemory, ids: set[str], cfg: Config) -> bool:
    sid = memory.standing_option_id
    if sid is None:
        return True
    if sid == "SKIP":  # integrator: skipping is a one-day postponement, never a standing plan
        return False
    if memory.standing_mode == "CAR" or sid.startswith("CAR_"):
        car_ok = "CAR" in ids or any(i.startswith("CAR_") for i in ids)
        d = memory.standing_depart_min
        t = cfg.time
        return car_ok and d is not None and t.depart_earliest_min <= d <= t.depart_latest_min
    return sid in ids


def candidate_events(persona: Persona, memory: AgentMemory, today: TodayInfo,
                     feasible_option_ids: Sequence[str], cfg: Config) -> list[tuple[str, int]]:
    """Event keys whose condition holds today (before edge filtering)."""
    cc = cfg.clock
    ev: list[tuple[str, int]] = []
    day = int(today.day)
    if memory.standing_option_id is None:
        ev.append(("T1", day))
    if today.fee_changed_today:
        ev.append(("T2", day))
    last = memory.last()
    if last is not None and last.late_min is not None:
        if last.late_min > cc.late_tolerance_by_F[persona.F - 1]:
            ev.append(("T3", int(last.day)))
    if last is not None and last.pt_disrupted:
        ev.append(("T4", int(last.day)))
    if (today.pt_disruption_announced and persona.corridor_id in today.pt_disrupted_corridors
            and memory.standing_mode == "PT"):
        ev.append(("T4", day))
    if (last is not None and "T4" in last.triggers and ("T4", int(last.day)) in memory.consumed_events
            and persona.corridor_id not in today.pt_disrupted_corridors):
        ev.append(("T4-end", int(last.day)))
    cars = memory.car_records()
    if cars and last is not None and last.mode == "CAR":
        end = len(cars) - 1
        n = int(cc.sustained_days)
        if _sustained_at(cars, end, n, cc.sustained_rel) and not _sustained_at(cars, end - 1, n, cc.sustained_rel):
            ev.append(("T5", int(cars[end].day)))
    if not _standing_feasible(memory, set(feasible_option_ids), cfg):
        ev.append(("T6", day))
    n_rev = int(cc.review_every_days)
    if n_rev > 0 and memory.records:
        decided = [int(r.day) for r in memory.records if r.decider != "standing"]
        if decided and day - max(decided) >= n_rev:
            ev.append(("T7", day))
    return ev


def evaluate_triggers(persona: Persona, memory: AgentMemory, today: TodayInfo,
                      feasible_option_ids: Sequence[str], cfg: Config) -> tuple[str, ...]:
    """Sorted unique triggers firing today; consumes their event keys (side effect)."""
    fired: set[str] = set()
    for key in candidate_events(persona, memory, today, feasible_option_ids, cfg):
        if key in memory.consumed_events:
            continue
        memory.consumed_events.add(key)
        fired.add(key[0].split("-")[0])
    return tuple(sorted(fired))


def is_discontinuity(triggers: Sequence[str], cfg: Config) -> bool:
    """True if any trigger is a habit discontinuity (kappa_H scaled down)."""
    disc = set(cfg.clock.discontinuity_triggers)
    return any(t in disc for t in triggers)


def should_wake(arm: str, triggers: Sequence[str]) -> bool:
    """Daily arms decide every day; clock arms only when a trigger fired."""
    if arm not in ARMS:
        raise ValueError(f"unknown arm: {arm!r}")
    if arm.endswith("-daily"):
        return True
    return bool(triggers)
