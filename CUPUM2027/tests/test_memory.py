"""Layer C memory: EMA of the delay ratio, reference fee, standing option, records."""

from __future__ import annotations

import dataclasses

import pytest

from cordonlite.config import load_config
from cordonlite.memory import (AgentMemory, memory_frame, new_memory, record_from_outcome,
                               set_standing, update_memory)
from cordonlite.options import build_options, car_outcome, non_car_outcome
from cordonlite.persona import trait_params
from cordonlite.types import MemoryRecord, MemoryRecord as MR


def rec(day: int, mode: str = "CAR", qd: float | None = 0.0, exp: float | None = 0.0,
        fee: float = 0.0, **kw) -> MemoryRecord:
    base = dict(day=day, option_id="CAR_0800" if mode == "CAR" else mode, mode=mode,
                depart_min=480 if mode in ("CAR", "PT") else None,
                queue_delay_min=qd if mode == "CAR" else None,
                expected_delay_min=exp if mode == "CAR" else None,
                expected_travel_min=30.0 if mode in ("CAR", "PT") else None,
                travel_min=30.0 if mode in ("CAR", "PT") else None, arrive_min=510,
                early_min=0.0, late_min=0.0, fee_paid=fee, pt_disrupted=False,
                decider="rule", triggers=(), reason="")
    base.update(kw)
    return MR(**base)


def test_new_memory_defaults() -> None:
    m = new_memory(3)
    assert isinstance(m, AgentMemory)
    assert (m.agent_id, m.delay_ratio_ema, m.ref_fee, m.standing_option_id) == (3, 1.0, 0.0, None)
    assert m.records == [] and m.consumed_events == set() and m.last() is None and m.recent(5) == ()


def test_delay_ratio_ema_and_clip(tiny_cfg) -> None:
    m = new_memory(0)
    update_memory(m, rec(1, qd=5.0, exp=1.0), tiny_cfg)   # r = 6/2 = 3 -> 1 + 0.3 * 2
    assert m.delay_ratio_ema == pytest.approx(1.6)
    update_memory(m, rec(2, qd=40.0, exp=0.0), tiny_cfg)  # r = 41 clipped to 3
    assert m.delay_ratio_ema == pytest.approx(1.6 + 0.3 * (3.0 - 1.6))
    m2 = new_memory(0)
    update_memory(m2, rec(1, qd=0.0, exp=9.0), tiny_cfg)  # r = 0.1 clipped to 0.5
    assert m2.delay_ratio_ema == pytest.approx(1.0 + 0.3 * (0.5 - 1.0))


def test_ratio_untouched_on_non_car_and_unserved(tiny_cfg) -> None:
    m = new_memory(0)
    update_memory(m, rec(1, mode="PT"), tiny_cfg)
    update_memory(m, rec(2, mode="WFH"), tiny_cfg)
    update_memory(m, rec(3, qd=-1.0, exp=2.0), tiny_cfg)   # unserved sentinel
    update_memory(m, rec(4, qd=3.0, exp=None), tiny_cfg)   # no public forecast
    assert m.delay_ratio_ema == 1.0
    assert len(m.records) == 4 and m.last().day == 4


def test_ref_fee_all_days() -> None:
    tiny_cfg = load_config(overrides={"memory.ref_fee_update": "all_days"})
    m = new_memory(0)
    update_memory(m, rec(1, fee=6.0), tiny_cfg)
    assert m.ref_fee == pytest.approx(1.8)
    update_memory(m, rec(2, mode="PT"), tiny_cfg)          # perceived 0 on non-car days
    assert m.ref_fee == pytest.approx(1.8 * 0.7)
    for d in range(3, 30):
        update_memory(m, rec(d, fee=6.0), tiny_cfg)
    assert m.ref_fee == pytest.approx(6.0, abs=0.01)


def test_ref_fee_car_days_only() -> None:
    cfg = load_config(overrides={"memory.ref_fee_update": "car_days"})
    m = new_memory(0)
    update_memory(m, rec(1, fee=6.0), cfg)
    update_memory(m, rec(2, mode="PT"), cfg)
    assert m.ref_fee == pytest.approx(1.8)


def test_company_car_perceives_no_fee(tiny_cfg) -> None:
    m = new_memory(0, company_car=True)
    update_memory(m, rec(1, fee=6.0), tiny_cfg)
    assert m.ref_fee == 0.0


def test_records_must_advance(tiny_cfg) -> None:
    m = new_memory(0)
    update_memory(m, rec(2), tiny_cfg)
    with pytest.raises(ValueError):
        update_memory(m, rec(2), tiny_cfg)


def test_recent_window(tiny_cfg) -> None:
    m = new_memory(0)
    for d in range(1, 9):
        update_memory(m, rec(d, mode="CAR" if d % 2 else "PT"), tiny_cfg)
    assert [r.day for r in m.recent(5)] == [4, 5, 6, 7, 8]
    assert [r.day for r in m.car_records()] == [1, 3, 5, 7]
    assert m.last_car_depart_min() == 480
    assert m.recent(0) == ()


def test_set_standing_and_record_from_outcome(tiny_personas, tiny_cfg, make_today) -> None:
    p = tiny_personas[0]   # archetype 1: CAR, PT, WFH, SKIP
    m = new_memory(p.agent_id)
    opts = build_options(p, m, make_today(1, fee_active=False), trait_params(p, tiny_cfg), tiny_cfg, True)
    car = opts[0]
    set_standing(m, car)
    assert (m.standing_option_id, m.standing_mode, m.standing_depart_min) == (car.option_id, "CAR", car.depart_min)
    engine_row = {"agent_id": p.agent_id, "day": 1, "corridor_id": p.corridor_id, "depart_min": car.depart_min,
                  "gate_arrive_min": car.depart_min + p.fftt_to_gate_min,
                  "gate_exit_min": car.depart_min + p.fftt_to_gate_min + 4, "queue_delay_min": 4,
                  "arrive_min": car.depart_min + p.fftt_total_min + 4, "fee_paid": 0.0}
    row = car_outcome(p, engine_row, car.option_id)
    r = record_from_outcome(row, car, "rule", ("T1",), "because")
    assert r.mode == "CAR" and r.queue_delay_min == 4.0 and r.travel_min == p.fftt_total_min + 4
    assert r.expected_delay_min == car.expected_public_delay_min == 0.0
    assert r.expected_travel_min == car.expected_travel_min and r.triggers == ("T1",)
    update_memory(m, r, tiny_cfg)
    assert m.delay_ratio_ema == pytest.approx(1.6)   # r = (4 + 1) / (0 + 1) = 5, clipped to 3

    pt = next(o for o in opts if o.mode == "PT")
    set_standing(m, pt)
    assert (m.standing_option_id, m.standing_mode, m.standing_depart_min) == ("PT", "PT", None)
    prow = non_car_outcome(p, pt, 2, pt_disrupted=True, disruption_mult=2.0)
    pr = record_from_outcome(prow, pt, "standing")
    assert pr.pt_disrupted and pr.travel_min == pytest.approx(2 * p.pt_time_min)
    assert pr.queue_delay_min is None and pr.expected_delay_min is None
    wfh = next(o for o in opts if o.mode == "WFH")
    wr = record_from_outcome(non_car_outcome(p, wfh, 3, False), wfh, "rule")
    assert wr.travel_min is None and wr.fee_paid == 0.0 and not wr.pt_disrupted


def test_memory_frame(tiny_cfg) -> None:
    ms = [new_memory(1), new_memory(0)]
    update_memory(ms[0], rec(1, triggers=("T1", "T2")), tiny_cfg)
    update_memory(ms[1], rec(1), tiny_cfg)
    update_memory(ms[1], rec(2, mode="PT"), tiny_cfg)
    df = memory_frame(ms)
    assert list(df.columns) == ["agent_id"] + [f.name for f in dataclasses.fields(MemoryRecord)]
    assert df[["agent_id", "day"]].values.tolist() == [[0, 1], [0, 2], [1, 1]]
    assert df.loc[2, "triggers"] == "T1;T2"


def test_ref_fee_faced() -> None:
    """v3 5.2 fee-ref: the reference follows the fee FACED on every day, so it catches up with the
    charge also for agents who stopped driving (and the loss term fades)."""
    cfg = load_config(overrides={"memory.ref_fee_update": "faced", "memory.ema_alpha": 0.3})
    m = new_memory(0)
    update_memory(m, rec(1, fee=6.0), cfg)                       # car day: fee paid
    assert m.ref_fee == pytest.approx(1.8)
    update_memory(m, rec(2, mode="PT"), cfg, fee_faced=6.0)      # PT day: fee faced at the car reference time
    assert m.ref_fee == pytest.approx(1.8 + 0.3 * 4.2)
    update_memory(m, rec(3, mode="WFH"), cfg)                    # nothing faced given -> 0
    assert m.ref_fee == pytest.approx((1.8 + 0.3 * 4.2) * 0.7)
    for d in range(4, 40):
        update_memory(m, rec(d, mode="PT"), cfg, fee_faced=4.0)
    assert m.ref_fee == pytest.approx(4.0, abs=0.01)
    c = new_memory(1, company_car=True)
    update_memory(c, rec(1, mode="PT"), cfg, fee_faced=6.0)
    assert c.ref_fee == 0.0
    # the old rules ignore fee_faced
    old = load_config(overrides={"memory.ref_fee_update": "all_days"})
    m2 = new_memory(0)
    update_memory(m2, rec(1, mode="PT"), old, fee_faced=6.0)
    assert m2.ref_fee == 0.0
