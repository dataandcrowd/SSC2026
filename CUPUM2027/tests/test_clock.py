"""Cognitive clock: each trigger, edge triggering, discontinuity and arm wake rules."""

from __future__ import annotations

import pytest

from cordonlite.clock import evaluate_triggers, is_discontinuity, should_wake
from cordonlite.config import load_config
from cordonlite.memory import new_memory, set_standing
from cordonlite.types import MemoryRecord, Option, Persona


def persona(F: int = 3, corridor: int = 0) -> Persona:
    return Persona(agent_id=0, origin_id=0, corridor_id=corridor, x_nztm=0.0, y_nztm=0.0,
                   fftt_to_gate_min=20, fftt_gate_to_dest_min=5, path_km=20.0, vot=20.0,
                   vot_quintile=3, archetype=2, activity="work", tstar_min=480, fixed_start=True,
                   must_drive=False, sched_mult=1.0, pt_allowed=True, wfh_allowed=False,
                   company_car=False, parking_cost=0.0, pt_time_min=50.0, pt_fare=7.0,
                   H=3, F=F, P=3, S=3)


def opt(oid: str, mode: str, depart: int | None = None) -> Option:
    return Option(option_id=oid, mode=mode, depart_min=depart, expected_gate_arrive_min=None,
                  expected_delay_min=None, expected_gate_exit_min=None, expected_travel_min=0.0,
                  expected_arrive_min=None, early_min=0.0, late_min=0.0, fee=0.0, parking=0.0,
                  pt_time_min=None, pt_fare=None, is_standing=False, gc=0.0)


def rec(day: int, mode: str = "CAR", late: float = 0.0, travel: float = 25.0, expected: float = 25.0,
        pt_disrupted: bool = False, qd: float = 0.0) -> MemoryRecord:
    return MemoryRecord(day=day, option_id="CAR_0730" if mode == "CAR" else mode, mode=mode,
                        depart_min=450, queue_delay_min=qd if mode == "CAR" else None,
                        expected_delay_min=0.0 if mode == "CAR" else None,
                        expected_travel_min=expected if mode in ("CAR", "PT") else None,
                        travel_min=travel if mode in ("CAR", "PT") else None, arrive_min=475,
                        early_min=0.0, late_min=late, fee_paid=0.0, pt_disrupted=pt_disrupted,
                        decider="standing", triggers=(), reason="")


IDS = ("CAR_0730", "PT", "SKIP")


def standing_car():
    m = new_memory(0)
    set_standing(m, opt("CAR_0730", "CAR", 450))
    return m


def test_t1_first_day(make_today, tiny_cfg) -> None:
    m = new_memory(0)
    assert evaluate_triggers(persona(), m, make_today(1), IDS, tiny_cfg) == ("T1",)
    assert ("T1", 1) in m.consumed_events
    set_standing(m, opt("CAR_0730", "CAR", 450))
    assert evaluate_triggers(persona(), m, make_today(2), IDS, tiny_cfg) == ()


def test_t2_fee_change_once(make_today, tiny_cfg) -> None:
    m = standing_car()
    t = make_today(3, fee_changed_today=True)
    assert evaluate_triggers(persona(), m, t, IDS, tiny_cfg) == ("T2",)
    assert evaluate_triggers(persona(), m, t, IDS, tiny_cfg) == ()       # same event, consumed
    assert evaluate_triggers(persona(), m, make_today(4), IDS, tiny_cfg) == ()


@pytest.mark.parametrize("F,late,fires", [(1, 5.0, False), (1, 6.0, True), (3, 10.0, False),
                                          (3, 11.0, True), (5, 15.0, False), (5, 16.0, True)])
def test_t3_late_tolerance_by_f(make_today, tiny_cfg, F, late, fires) -> None:
    m = standing_car()
    m.records.append(rec(1, late=late))
    assert evaluate_triggers(persona(F=F), m, make_today(2), IDS, tiny_cfg) == (("T3",) if fires else ())


def test_t3_edge(make_today, tiny_cfg) -> None:
    m = standing_car()
    m.records.append(rec(1, late=30.0))
    assert evaluate_triggers(persona(), m, make_today(2), IDS, tiny_cfg) == ("T3",)
    assert evaluate_triggers(persona(), m, make_today(2), IDS, tiny_cfg) == ()
    m.records.append(rec(2, late=30.0))                                  # a new late day is a new event
    assert evaluate_triggers(persona(), m, make_today(3), IDS, tiny_cfg) == ("T3",)


def test_t4_announced_only_for_pt_standing(make_today, tiny_cfg) -> None:
    t = make_today(5, disrupted=[0])
    assert evaluate_triggers(persona(), standing_car(), t, IDS, tiny_cfg) == ()
    m = new_memory(0)
    set_standing(m, opt("PT", "PT"))
    assert evaluate_triggers(persona(corridor=1), m, t, IDS, tiny_cfg) == ()   # other corridor
    assert evaluate_triggers(persona(), m, t, IDS, tiny_cfg) == ("T4",)


def test_t4_experienced_and_single_wake_per_disruption(make_today, tiny_cfg) -> None:
    m = new_memory(0)
    set_standing(m, opt("PT", "PT"))
    assert evaluate_triggers(persona(), m, make_today(5, disrupted=[0]), IDS, tiny_cfg) == ("T4",)
    m.records.append(rec(5, mode="PT", pt_disrupted=True))               # took PT anyway
    assert evaluate_triggers(persona(), m, make_today(6), IDS, tiny_cfg) == ()   # same event
    m2 = new_memory(0)
    set_standing(m2, opt("PT", "PT"))
    m2.records.append(rec(5, mode="PT", pt_disrupted=True))              # unannounced, experienced
    assert evaluate_triggers(persona(), m2, make_today(6), IDS, tiny_cfg) == ("T4",)
    assert evaluate_triggers(persona(), m2, make_today(6), IDS, tiny_cfg) == ()


def test_t5_sustained_change_edge(make_today, tiny_cfg) -> None:
    m = standing_car()
    p = persona()
    m.records.append(rec(1, travel=40.0))                                # one day beyond 20%
    assert evaluate_triggers(p, m, make_today(2), IDS, tiny_cfg) == ()
    m.records.append(rec(2, travel=40.0))                                # second consecutive car day
    assert evaluate_triggers(p, m, make_today(3), IDS, tiny_cfg) == ("T5",)
    m.records.append(rec(3, travel=40.0))                                # still beyond: level, not edge
    assert evaluate_triggers(p, m, make_today(4), IDS, tiny_cfg) == ()
    m.records.append(rec(4, travel=25.0))
    m.records.append(rec(5, travel=29.0))                                # within 20%
    assert evaluate_triggers(p, m, make_today(6), IDS, tiny_cfg) == ()
    m.records.append(rec(6, travel=15.0))
    m.records.append(rec(7, travel=15.0))                                # faster than expected: new edge
    assert evaluate_triggers(p, m, make_today(8), IDS, tiny_cfg) == ("T5",)


def test_t5_needs_car_yesterday_and_skips_non_car_days(make_today, tiny_cfg) -> None:
    m = standing_car()
    p = persona()
    m.records += [rec(1, travel=40.0), rec(2, mode="PT"), rec(3, travel=40.0)]
    assert evaluate_triggers(p, m, make_today(4), IDS, tiny_cfg) == ("T5",)   # consecutive car days 1, 3
    m2 = standing_car()
    m2.records += [rec(1, travel=40.0), rec(2, travel=40.0), rec(3, mode="PT")]
    assert evaluate_triggers(p, m2, make_today(4), IDS, tiny_cfg) == ()       # yesterday was not a car day


def test_t6_standing_infeasible(make_today, tiny_cfg) -> None:
    m = new_memory(0)
    set_standing(m, opt("PT", "PT"))
    assert evaluate_triggers(persona(), m, make_today(5), ("CAR_0730", "SKIP"), tiny_cfg) == ("T6",)
    m2 = new_memory(0)
    set_standing(m2, opt("WFH", "WFH"))
    assert evaluate_triggers(persona(), m2, make_today(5), ("CAR", "PT", "WFH", "SKIP"), tiny_cfg) == ()
    m3 = new_memory(0)
    set_standing(m3, opt("CAR_0545", "CAR", 345))                         # outside the window
    assert evaluate_triggers(persona(), m3, make_today(5), ("CAR", "SKIP"), tiny_cfg) == ("T6",)
    # feasible modes or option ids are both accepted for a standing car
    assert evaluate_triggers(persona(), standing_car(), make_today(5), ("CAR", "SKIP"), tiny_cfg) == ()


def test_multiple_sorted(make_today, tiny_cfg) -> None:
    m = new_memory(0)
    set_standing(m, opt("PT", "PT"))
    m.records.append(rec(4, mode="PT", late=40.0, pt_disrupted=True))
    t = make_today(5, fee_changed_today=True)
    assert evaluate_triggers(persona(), m, t, IDS, tiny_cfg) == ("T2", "T3", "T4")


def test_discontinuity_and_wake(tiny_cfg) -> None:
    # behaviour recalibration: a price change (T2) is not a habit discontinuity (Verplanken et al. 2008)
    for t in ("T1", "T4", "T6"):
        assert is_discontinuity((t,), tiny_cfg)
    for t in ("T2", "T3", "T5"):
        assert not is_discontinuity((t,), tiny_cfg)
    assert is_discontinuity(("T3", "T1"), tiny_cfg) and not is_discontinuity((), tiny_cfg)
    v3 = load_config(overrides={"clock.discontinuity_triggers": ["T1", "T2", "T4", "T6"]})
    assert is_discontinuity(("T2",), v3)
    assert should_wake("R-daily", ()) and should_wake("L-daily", ())
    assert not should_wake("R-clock", ()) and not should_wake("L-clock", ())
    assert should_wake("R-clock", ("T3",)) and should_wake("L-clock", ("T1",))
    with pytest.raises(ValueError):
        should_wake("X", ())


def test_standing_skip_wakes_next_day(tiny_cfg, make_today) -> None:
    """Integrator addition: a standing SKIP is not a standing plan, so T6 fires each following day."""
    from cordonlite.memory import new_memory, set_standing
    from cordonlite.types import Option

    m = new_memory(0)
    skip = Option(option_id="SKIP", mode="SKIP", depart_min=None, expected_gate_arrive_min=None,
                  expected_delay_min=None, expected_gate_exit_min=None, expected_travel_min=0.0,
                  expected_arrive_min=None, early_min=0.0, late_min=0.0, fee=0.0, parking=0.0,
                  pt_time_min=None, pt_fare=None, is_standing=False, gc=25.0)
    set_standing(m, skip)
    ids = ("CAR", "PT", "WFH", "SKIP")
    assert evaluate_triggers(persona(), m, make_today(5), ids, tiny_cfg) == ("T6",)
    assert evaluate_triggers(persona(), m, make_today(6), ids, tiny_cfg) == ("T6",)


def test_t4_disruption_end_wakes_once(make_today, tiny_cfg) -> None:
    """Final fixer: the riders woken by an announced disruption on day d wake again on day d+1
    (service back), whether they switched to the car or stayed on PT; once only."""
    import dataclasses

    for mode in ("CAR", "PT"):
        m = new_memory(0)
        set_standing(m, opt("PT", "PT"))
        assert evaluate_triggers(persona(), m, make_today(5, disrupted=[0]), IDS, tiny_cfg) == ("T4",)
        r = dataclasses.replace(rec(5, mode=mode, pt_disrupted=(mode == "PT")), triggers=("T4",), decider="rule")
        m.records.append(r)
        set_standing(m, opt("CAR_0730", "CAR", 450) if mode == "CAR" else opt("PT", "PT"))
        assert evaluate_triggers(persona(), m, make_today(6), IDS, tiny_cfg) == ("T4",)
        m.records.append(dataclasses.replace(rec(6, mode=mode), triggers=("T4",), decider="rule"))
        assert evaluate_triggers(persona(), m, make_today(7), IDS, tiny_cfg) == ()
    # an unannounced disruption: the experienced T4 on d+1 does not also cause an end wake on d+2
    m2 = new_memory(0)
    set_standing(m2, opt("PT", "PT"))
    m2.records.append(rec(5, mode="PT", pt_disrupted=True))
    assert evaluate_triggers(persona(), m2, make_today(6), IDS, tiny_cfg) == ("T4",)
    m2.records.append(dataclasses.replace(rec(6, mode="PT"), triggers=("T4",), decider="rule"))
    assert evaluate_triggers(persona(), m2, make_today(7), IDS, tiny_cfg) == ()


def test_t7_periodic_review_fires_only_when_enabled():
    """T7 wakes an agent after review_every_days standing days, and is off by default."""
    import dataclasses
    import inspect
    import cordonlite.clock as clock
    src = inspect.getsource(clock.candidate_events)
    assert "review_every_days" in src
    from cordonlite.config import load_config
    cfg = load_config()
    assert cfg.clock.review_every_days == 0
    assert dataclasses.replace(cfg.clock, review_every_days=5).review_every_days == 5
