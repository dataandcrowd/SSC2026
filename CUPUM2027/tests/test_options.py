"""Options and generalised cost: grid, delay forecast, GC formula, monotonicity, outcomes."""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from cordonlite import fees
from cordonlite.config import load_config
from cordonlite.engine import OUTCOME_COLUMNS
from cordonlite.memory import new_memory, set_standing
from cordonlite.options import (OUTCOME_ROW_COLUMNS, build_options, car_departures, car_outcome,
                                expected_public_delay, feasible_modes, fee_faced, gc_rank,
                                initial_depart_min, non_car_outcome, public_delay_profile)
from cordonlite.persona import trait_params
from cordonlite.types import GC_PARTS, Persona, TodayInfo, TraitParams


def persona(**kw) -> Persona:
    base = dict(agent_id=0, origin_id=0, corridor_id=0, x_nztm=0.0, y_nztm=0.0, fftt_to_gate_min=20,
                fftt_gate_to_dest_min=5, path_km=20.0, vot=30.0, vot_quintile=3, archetype=2,
                activity="work", tstar_min=510, fixed_start=True, must_drive=False, sched_mult=1.0,
                pt_allowed=True, wfh_allowed=False, company_car=False, parking_cost=8.0,
                pt_time_min=50.0, pt_fare=7.0, H=3, F=3, P=3, S=3)
    base.update(kw)
    return Persona(**base)


def today(day: int = 11, active: bool = True, table=None, public_delay=None, disrupted=(),
          announced: bool = True) -> TodayInfo:
    t = table if table is not None else fees.fee_table("tou" if active else "none")
    return TodayInfo(day=day, fee_regime="tou", fee_active=active, fee_by_minute=tuple(t),
                     fee_changed_today=False, public_delay=public_delay or {0: ()},
                     pt_disrupted_corridors=frozenset(disrupted), pt_disruption_announced=announced,
                     pt_disruption_time_mult=2.0)


P3 = TraitParams(kappa_h=1.0, phi=1.0, omega=1.0, eta=1.0)


def test_car_departures(tiny_cfg) -> None:
    assert car_departures(480, tiny_cfg) == list(range(420, 541, 15))
    assert car_departures(360, tiny_cfg) == [360, 375, 390, 405, 420]
    assert car_departures(585, tiny_cfg) == [525, 540, 555, 570, 585]
    assert car_departures(487, tiny_cfg) == list(range(420, 541, 15))   # snapped down to the grid
    assert car_departures(300, tiny_cfg) == [360, 375, 390, 405, 420]


def test_initial_depart(tiny_cfg) -> None:
    p = persona(tstar_min=510)                       # 510 - 25 - 10 = 475 -> 465
    assert initial_depart_min(p, tiny_cfg) == 465
    assert initial_depart_min(persona(tstar_min=420, fftt_to_gate_min=80), tiny_cfg) == 360


def test_public_delay_profile_and_interp() -> None:
    out = pd.DataFrame({
        "agent_id": [0, 1, 2, 3, 4], "day": 1, "corridor_id": [0, 0, 0, 1, 1],
        "depart_min": [400, 401, 420, 400, 400], "gate_arrive_min": [450, 452, 470, 450, 451],
        "gate_exit_min": [452, 458, 480, -1, 451], "queue_delay_min": [2, 6, 10, -1, 0],
        "arrive_min": [460, 466, 488, -1, 460], "fee_paid": 0.0,
    })[list(OUTCOME_COLUMNS)]
    prof = public_delay_profile(out, [0, 1, 2], 5)
    assert prof[0] == ((452.0, 4.0), (472.0, 10.0))
    assert prof[1] == ((452.0, 0.0),)           # unserved car ignored
    assert prof[2] == ()
    assert expected_public_delay(prof, 0, 462) == pytest.approx(7.0)
    assert expected_public_delay(prof, 0, 452) == pytest.approx(4.0)
    assert expected_public_delay(prof, 0, 449) == 0.0              # outside, no half-bin
    assert expected_public_delay(prof, 0, 450, bin_min=5) == pytest.approx(4.0)
    assert expected_public_delay(prof, 0, 474, bin_min=5) == pytest.approx(10.0)
    assert expected_public_delay(prof, 0, 475, bin_min=5) == 0.0
    assert expected_public_delay(prof, 2, 460) == 0.0
    assert expected_public_delay(prof, 9, 460) == 0.0
    assert public_delay_profile(None, [0, 1], 5) == {0: (), 1: ()}


def test_feasible_modes(tiny_cfg, make_today) -> None:
    t = make_today(1)
    assert feasible_modes(persona(), t, tiny_cfg) == ("CAR", "PT", "SKIP")
    assert feasible_modes(persona(wfh_allowed=True), t, tiny_cfg) == ("CAR", "PT", "WFH", "SKIP")
    assert feasible_modes(persona(pt_allowed=False, must_drive=True), t, tiny_cfg) == ("CAR", "SKIP")
    assert feasible_modes(persona(), make_today(5, disrupted=[0]), tiny_cfg) == ("CAR", "PT", "SKIP")


def test_build_options_structure(tiny_personas, tiny_cfg, make_today) -> None:
    for p in tiny_personas:
        m = new_memory(p.agent_id)
        opts = build_options(p, m, make_today(3), trait_params(p, tiny_cfg), tiny_cfg, False)
        ids = [o.option_id for o in opts]
        assert len(ids) == len(set(ids))
        cars = [o for o in opts if o.mode == "CAR"]
        assert [o.depart_min for o in cars] == sorted(o.depart_min for o in cars)
        assert [o.mode for o in opts[len(cars):]] == [x for x in feasible_modes(p, make_today(3), tiny_cfg) if x != "CAR"]
        for o in opts:
            assert set(o.gc_parts) == set(GC_PARTS)
            assert o.gc == pytest.approx(sum(o.gc_parts.values()))
            assert o.gc_parts["habit"] == 0.0 and not o.is_standing   # no standing option yet


def test_gc_formula_car(tiny_cfg) -> None:
    p = persona(vot=30.0, tstar_min=510, parking_cost=8.0)
    m = new_memory(0)
    m.ref_fee = 2.0
    prm = TraitParams(kappa_h=2.0, phi=0.67, omega=1.5, eta=2.0)
    t = today(public_delay={0: ((480.0, 4.0), (500.0, 8.0))})
    m.delay_ratio_ema = 1.5
    opts = build_options(p, m, t, prm, tiny_cfg, discontinuity=False)
    o = next(x for x in opts if x.option_id == "CAR_0745")   # depart 465
    a = 0.5
    g = 485
    d_pub = 5.0
    D = 7.5
    x = g + 8                                                 # round(7.5) half away = 8
    arr = x + 5
    f = fees.fee_at(x)
    assert (o.expected_gate_arrive_min, o.expected_gate_exit_min, o.expected_arrive_min) == (g, x, arr)
    assert o.expected_public_delay_min == pytest.approx(d_pub) and o.expected_delay_min == pytest.approx(D)
    assert o.fee == f
    early = max(0, 510 - arr)
    assert o.gc_parts["time"] == pytest.approx(a * (25 + D))
    assert o.gc_parts["schedule"] == pytest.approx(0.67 * 1.0 * a * 0.61 * early)
    assert o.gc_parts["fee"] == pytest.approx(f + 2.0 * max(0.0, f - 2.0))
    assert o.gc_parts["parking"] == 8.0
    assert o.expected_travel_min == pytest.approx(25 + D)
    late_o = next(x for x in opts if x.option_id == "CAR_0830")   # depart 510, late
    assert late_o.late_min > 0 and late_o.early_min == 0
    assert late_o.gc_parts["schedule"] == pytest.approx(0.67 * a * 2.38 * late_o.late_min)


SPEC_GC = {"costs.wfh_form": "spec", "costs.wfh_cost": 8.0, "costs.pt_attitude_penalty": 0.0}


def test_gc_formula_pt_wfh_skip() -> None:
    # the specification GC (no PAP, WFH = wfh_cost x phi), still selectable
    tiny_cfg = load_config(overrides={"run.n_agents": 20, **SPEC_GC})
    p = persona(wfh_allowed=True, vot=30.0, pt_time_min=50.0)
    prm = TraitParams(kappa_h=2.0, phi=0.5, omega=1.5, eta=2.0)
    m = new_memory(0)
    opts = build_options(p, m, today(), prm, tiny_cfg, False)
    pt, wfh, skip = (next(o for o in opts if o.mode == k) for k in ("PT", "WFH", "SKIP"))
    assert pt.gc == pytest.approx(1.5 * 0.5 * 50.0 + 7.0)
    assert (pt.depart_min, pt.expected_arrive_min, pt.early_min, pt.late_min) == (460, 510, 0.0, 0.0)
    assert wfh.gc == pytest.approx(8.0 * 0.5)
    assert skip.gc == pytest.approx(30.0 + 1.0 * 30.0)   # skip_cost + skip_vot_hours x VoT
    # PT services on a 10-min headway: the latest service arriving by t* (510)
    q = persona(wfh_allowed=True, vot=30.0, pt_time_min=47.0)
    ptq = next(o for o in build_options(q, m, today(), prm, tiny_cfg, False) if o.mode == "PT")
    assert (ptq.depart_min, ptq.expected_arrive_min, ptq.early_min) == (460, 507, 3.0)
    assert ptq.gc_parts["schedule"] == pytest.approx(0.5 * q.sched_mult * 0.5 * 0.61 * 3.0)
    # announced disruption on own corridor doubles PT time
    d = build_options(p, m, today(disrupted=[0]), prm, tiny_cfg, False)
    ptd = next(o for o in d if o.mode == "PT")
    assert ptd.pt_time_min == 100.0 and ptd.gc == pytest.approx(1.5 * 0.5 * 100.0 + 7.0)
    # not announced or other corridor: unchanged
    for t in (today(disrupted=[0], announced=False), today(disrupted=[1])):
        assert next(o for o in build_options(p, m, t, prm, tiny_cfg, False) if o.mode == "PT").pt_time_min == 50.0


def test_standing_skip_is_not_a_habit(tiny_cfg) -> None:
    """After a SKIP the habit reference is the last non-SKIP option, so SKIP carries the habit cost."""
    from cordonlite.memory import record_from_outcome, update_memory
    from cordonlite.options import car_outcome, non_car_outcome
    p = persona()
    m = new_memory(0)
    prm = TraitParams(kappa_h=2.0, phi=1.0, omega=1.0, eta=1.0)
    opts = build_options(p, m, today(), prm, tiny_cfg, False)
    car = next(o for o in opts if o.mode == "CAR")
    row = {"agent_id": 0, "day": 1, "depart_min": car.depart_min, "gate_arrive_min": car.expected_gate_arrive_min,
           "gate_exit_min": car.expected_gate_arrive_min, "queue_delay_min": 0,
           "arrive_min": car.expected_arrive_min, "fee_paid": 0.0}
    update_memory(m, record_from_outcome(car_outcome(p, row, car.option_id), car, "rule"), tiny_cfg)
    set_standing(m, car)
    skip = next(o for o in opts if o.mode == "SKIP")
    update_memory(m, record_from_outcome(non_car_outcome(p, skip, 2, False), skip, "rule"), tiny_cfg)
    set_standing(m, skip)
    assert m.standing_option_id == "SKIP" and m.habit_option_id == car.option_id
    opts2 = build_options(p, m, today(), prm, tiny_cfg, False)
    assert next(o for o in opts2 if o.mode == "SKIP").gc_parts["habit"] == 2.0
    assert next(o for o in opts2 if o.option_id == car.option_id).gc_parts["habit"] == 0.0
    assert [o.option_id for o in opts2 if o.is_standing] == [car.option_id]


def test_habit_and_discontinuity(tiny_cfg) -> None:
    p = persona()
    m = new_memory(0)
    prm = TraitParams(kappa_h=3.0, phi=1.0, omega=1.0, eta=1.0)
    opts = build_options(p, m, today(), prm, tiny_cfg, False)
    set_standing(m, opts[4])
    sid = opts[4].option_id
    for disc, k in ((False, 3.0), (True, 1.5)):
        opts2 = build_options(p, m, today(), prm, tiny_cfg, disc)
        assert [o.option_id for o in opts2 if o.is_standing] == [sid]
        for o in opts2:
            assert o.gc_parts["habit"] == (0.0 if o.option_id == sid else k)
    # standing PT: car grid centred on the last car departure, else the initial departure
    pt = next(o for o in opts if o.mode == "PT")
    m2 = new_memory(0)
    set_standing(m2, pt)
    opts3 = build_options(p, m2, today(), prm, tiny_cfg, False)
    cars = [o.depart_min for o in opts3 if o.mode == "CAR"]
    assert cars == car_departures(initial_depart_min(p, tiny_cfg), tiny_cfg)
    assert next(o for o in opts3 if o.mode == "PT").gc_parts["habit"] == 0.0


def test_gc_monotone_in_fee(tiny_cfg) -> None:
    p = persona(wfh_allowed=True)
    m = new_memory(0)
    m.ref_fee = 1.0
    base = fees.fee_table("tou")
    prev = None
    for scale in (0.0, 0.5, 1.0, 2.0, 3.0):
        opts = build_options(p, m, today(table=[scale * v for v in base]), P3, tiny_cfg, False)
        gcs = {o.option_id: o.gc for o in opts}
        if prev is not None:
            for oid, g in gcs.items():
                if oid.startswith("CAR_"):
                    assert g > prev[oid]
                else:
                    assert g == prev[oid]
        prev = gcs


def test_gc_monotone_in_eta_and_inactive_fee(tiny_cfg) -> None:
    p = persona()
    m = new_memory(0)
    car_fee = [next(o for o in build_options(p, m, today(), TraitParams(1.0, 1.0, 1.0, eta), tiny_cfg, False)
                    if o.mode == "CAR").gc_parts["fee"] for eta in (0.0, 0.5, 1.0, 2.0, 3.0)]
    assert car_fee == sorted(car_fee) and car_fee[0] < car_fee[-1]
    for o in build_options(p, m, today(active=False), P3, tiny_cfg, False):
        assert o.fee == 0.0 and o.gc_parts["fee"] == 0.0


def test_company_car_fee(tiny_cfg) -> None:
    p = persona(company_car=True, parking_cost=0.0)
    opts = build_options(p, new_memory(0), today(), P3, tiny_cfg, False)
    car = [o for o in opts if o.mode == "CAR"]
    assert any(o.fee > 0 for o in car)
    assert all(o.gc_parts["fee"] == 0.0 for o in car)


def test_fee_at_gate_exit_minute(tiny_cfg) -> None:
    # 07:40 departure (460) + 20 = 480 gate arrival; a 30-min public delay pushes the exit to 510
    p = persona()
    t = today(public_delay={0: ((470.0, 30.0), (490.0, 30.0))})
    o = next(x for x in build_options(p, new_memory(0), t, P3, tiny_cfg, False) if x.depart_min == 465)
    assert o.expected_gate_exit_min == 485 + 30
    assert o.fee == fees.fee_at(515)


def test_outcome_rows(tiny_cfg) -> None:
    p = persona(wfh_allowed=True, tstar_min=510)
    opts = build_options(p, new_memory(0), today(), P3, tiny_cfg, False)
    pt = next(o for o in opts if o.mode == "PT")
    r = non_car_outcome(p, pt, 4, pt_disrupted=False)
    assert tuple(r) == OUTCOME_ROW_COLUMNS
    assert (r["depart_min"], r["arrive_min"], r["travel_min"], r["late_min"], r["pt_fare_paid"]) == (460, 510, 50.0, 0.0, 7.0)
    assert r["gate_exit_min"] is None and r["fee_paid"] == 0.0
    rd = non_car_outcome(p, pt, 4, pt_disrupted=True, disruption_mult=2.0)
    assert rd["travel_min"] == 100.0 and rd["late_min"] == 50.0 and rd["pt_disrupted"]
    w = non_car_outcome(p, next(o for o in opts if o.mode == "WFH"), 4, False)
    assert w["depart_min"] is None and w["travel_min"] == 0.0 and w["mode"] == "WFH"
    with pytest.raises(ValueError):
        non_car_outcome(p, opts[0], 4, False)
    row = {"agent_id": 0, "day": 4, "corridor_id": 0, "depart_min": 465, "gate_arrive_min": 485,
           "gate_exit_min": 490, "queue_delay_min": 5, "arrive_min": 495, "fee_paid": 6.0}
    c = car_outcome(p, row)
    assert tuple(c) == OUTCOME_ROW_COLUMNS
    assert (c["option_id"], c["travel_min"], c["early_min"], c["late_min"], c["parking_paid"]) == ("CAR_0745", 30.0, 15.0, 0.0, 8.0)
    un = car_outcome(p, {**row, "gate_exit_min": -1, "queue_delay_min": -1, "arrive_min": -1, "fee_paid": 0.0})
    assert un["travel_min"] is None and un["late_min"] is None


def test_gc_rank(tiny_cfg) -> None:
    opts = build_options(persona(), new_memory(0), today(), P3, tiny_cfg, False)
    order = sorted(opts, key=lambda o: o.gc)
    assert gc_rank(opts, order[0].option_id) == 1
    assert gc_rank(opts, order[-1].option_id) == len(opts)
    with pytest.raises(KeyError):
        gc_rank(opts, "NOPE")


def test_zero_fee_day1_mostly_car(tiny_cfg) -> None:
    """With no charge and no queue, a typical commuter with free parking prefers driving."""
    p = persona(parking_cost=0.0)
    opts = build_options(p, new_memory(0), today(active=False), P3, tiny_cfg, False)
    assert min(opts, key=lambda o: o.gc).mode == "CAR"


# --------------------------------------------------------------------------- behaviour recalibration


def test_pt_attitude_penalty_scales_with_omega() -> None:
    cfg = load_config(overrides={"costs.pt_attitude_penalty": 8.0})
    p = persona(vot=30.0, pt_time_min=50.0)
    for omega in (0.5, 1.0, 2.0):
        prm = TraitParams(kappa_h=0.0, phi=1.0, omega=omega, eta=0.0)
        pt = next(o for o in build_options(p, new_memory(0), today(), prm, cfg, False) if o.mode == "PT")
        assert pt.gc_parts["pt"] == pytest.approx(omega * (0.5 * 50.0 + 8.0) + 7.0)


def test_wfh_v3_relative_form() -> None:
    """v3 6.2: WFH earns no free-flow time or parking credit against driving; it scales with VoT and phi."""
    cfg = load_config(overrides={"costs.wfh_form": "v3_relative", "costs.wfh_cost": 6.0})
    m = new_memory(0)
    vals = {}
    for vot in (10.0, 30.0):
        for phi in (0.5, 2.0):
            p = persona(wfh_allowed=True, vot=vot, parking_cost=8.0)
            prm = TraitParams(kappa_h=0.0, phi=phi, omega=1.0, eta=0.0)
            w = next(o for o in build_options(p, m, today(active=False), prm, cfg, False) if o.mode == "WFH")
            assert w.gc == pytest.approx(6.0 * phi + vot / 60.0 * p.fftt_total_min + 8.0)
            vals[(vot, phi)] = w.gc
    assert vals[(30.0, 0.5)] > vals[(10.0, 0.5)] and vals[(10.0, 2.0)] > vals[(10.0, 0.5)]
    # zero-fee property: with no queue and no charge the best car option beats WFH by about phi x k_WFH
    p = persona(wfh_allowed=True, vot=30.0, parking_cost=8.0, fixed_start=False, sched_mult=0.5)
    prm = TraitParams(kappa_h=0.0, phi=0.5, omega=1.0, eta=0.0)
    opts = build_options(p, m, today(active=False), prm, cfg, False)
    best_car = min(o.gc for o in opts if o.mode == "CAR")
    wfh = next(o for o in opts if o.mode == "WFH")
    assert wfh.gc - best_car == pytest.approx(6.0 * 0.5 - min(o.gc_parts["schedule"] for o in opts if o.mode == "CAR"))
    assert min(opts, key=lambda o: o.gc).mode == "CAR"
    # the spec form is unchanged
    spec = load_config(overrides={"costs.wfh_form": "spec", "costs.wfh_cost": 6.0})
    w = next(o for o in build_options(p, m, today(active=False), prm, spec, False) if o.mode == "WFH")
    assert w.gc == pytest.approx(3.0)


def test_fee_faced(tiny_cfg) -> None:
    p = persona()
    m = new_memory(0)
    opts = build_options(p, m, today(), P3, tiny_cfg, False)
    d0 = initial_depart_min(p, tiny_cfg)
    ref = next(o for o in opts if o.depart_min == d0 and o.mode == "CAR")
    assert fee_faced(p, m, opts, tiny_cfg) == ref.fee > 0
    # standing PT after a car day at 07:00: the fee at the last car departure
    set_standing(m, next(o for o in opts if o.mode == "PT"))
    from cordonlite.types import MemoryRecord
    m.records.append(MemoryRecord(day=1, option_id="CAR_0700", mode="CAR", depart_min=420, queue_delay_min=0.0,
                                  expected_delay_min=0.0, expected_travel_min=25.0, travel_min=25.0,
                                  arrive_min=445, early_min=65.0, late_min=0.0, fee_paid=4.0,
                                  pt_disrupted=False, decider="rule", triggers=(), reason=""))
    opts2 = build_options(p, m, today(), P3, tiny_cfg, False)
    assert fee_faced(p, m, opts2, tiny_cfg) == next(o for o in opts2 if o.depart_min == 420).fee
    assert fee_faced(p, m, build_options(p, m, today(active=False), P3, tiny_cfg, False), tiny_cfg) == 0.0
    pc = persona(company_car=True, parking_cost=0.0)
    assert fee_faced(pc, new_memory(0), build_options(pc, new_memory(0), today(), P3, tiny_cfg, False),
                     tiny_cfg) == 0.0


def _logit_shares(opts, sigma: float = 0.5) -> dict[str, float]:
    g = np.array([o.gc for o in opts])
    w = np.exp(-(g - g.min()) / sigma)
    return {o.option_id: float(x) for o, x in zip(opts, w / w.sum())}


def test_trait_effects_monotone_at_charge_wake() -> None:
    """At the T2 (charge) wake, under the default config: P(keep the standing car option) rises with H,
    P(PT) rises with P, P(car) falls with S and P(retime to a cheaper crossing) rises with F (logit
    shares of the rule)."""
    from cordonlite.clock import is_discontinuity
    cfg = load_config()
    t = cfg.traits
    disc = is_discontinuity(("T2",), cfg)
    assert not disc                                  # a price change is not a habit discontinuity
    # paid parking at the fixed office rate and the fuel cost of a 10 km path (2 x 10 km x NZ$0.30)
    p0 = persona(wfh_allowed=False, parking_cost=17.0, fuel_cost=6.0, vot=20.0, tstar_min=510, fixed_start=False,
                 sched_mult=0.5)
    m = new_memory(0)
    first = build_options(p0, m, today(active=False), trait_params(p0, cfg), cfg, False)
    standing = min((o for o in first if o.mode == "CAR"), key=lambda o: o.gc)   # best uncharged departure
    set_standing(m, standing)
    m.ref_fee = 0.0

    def shares(**lv):
        p = dataclasses.replace(p0, **lv)
        return _logit_shares(build_options(p, m, today(), trait_params(p, cfg), cfg, disc))

    keep = [shares(H=h)[standing.option_id] for h in range(1, 6)]
    assert keep == sorted(keep) and keep[-1] > keep[0]
    pt = [round(shares(P=lv)["PT"], 9) for lv in range(1, 6)]            # rounded: shares saturate at 0 and 1
    assert pt == sorted(pt) and pt[-1] > pt[0]
    car = [round(sum(v for k, v in shares(S=lv).items() if k.startswith("CAR")), 9) for lv in range(1, 6)]
    assert car == sorted(car, reverse=True) and car[0] > car[-1]
    retime = []
    for lv in range(1, 6):
        p = dataclasses.replace(p0, F=lv)
        opts = build_options(p, m, today(), trait_params(p, cfg), cfg, disc)
        sh = _logit_shares(opts)
        fee0 = next(o for o in opts if o.option_id == standing.option_id).fee
        retime.append(sum(sh[o.option_id] for o in opts if o.mode == "CAR" and o.fee < fee0))
    assert retime == sorted(retime) and retime[-1] > retime[0]
    assert list(t.eta) == sorted(t.eta) and max(t.eta) <= 1.0


# ---------------------------------------------------------------------------- fuel addition

def test_fuel_is_a_car_cost_part(tiny_cfg) -> None:
    """Fuel enters every CAR option as its own GC part and attribute; other modes carry none."""
    p0 = persona(wfh_allowed=True, parking_cost=8.0)
    p1 = persona(wfh_allowed=True, parking_cost=8.0, fuel_cost=9.2)
    spec = load_config(overrides={"costs.wfh_form": "spec"})
    o0 = build_options(p0, new_memory(0), today(), P3, spec, False)
    o1 = build_options(p1, new_memory(0), today(), P3, spec, False)
    assert "fuel" in GC_PARTS
    for a, b in zip(o0, o1):
        assert a.option_id == b.option_id
        assert b.gc == pytest.approx(sum(b.gc_parts.values()))
        if b.mode == "CAR":
            assert b.fuel == 9.2 and b.gc_parts["fuel"] == 9.2 and a.fuel == 0.0
            assert b.gc - a.gc == pytest.approx(9.2)
            assert b.gc_parts["parking"] == 8.0          # parking is unchanged by fuel
        else:
            assert b.fuel == 0.0 and b.gc_parts["fuel"] == 0.0
            assert b.gc == pytest.approx(a.gc)           # spec form: PT, WFH, SKIP unaffected


def test_wfh_v3_relative_earns_no_fuel_credit() -> None:
    """v3_relative: WFH carries the fuel cost like the parking cost, so WFH minus an uncharged,
    unqueued drive does not depend on fuel (zero-fee property kept)."""
    cfg = load_config(overrides={"costs.wfh_form": "v3_relative", "costs.wfh_cost": 6.0})
    prm = TraitParams(kappa_h=0.0, phi=0.5, omega=1.0, eta=0.0)
    gaps = []
    for fuel in (0.0, 9.2):
        p = persona(wfh_allowed=True, vot=30.0, parking_cost=8.0, fuel_cost=fuel, fixed_start=False,
                    sched_mult=0.5)
        opts = build_options(p, new_memory(0), today(active=False), prm, cfg, False)
        w = next(o for o in opts if o.mode == "WFH")
        assert w.gc == pytest.approx(6.0 * 0.5 + 0.5 * p.fftt_total_min + 8.0 + fuel)
        assert w.fuel == 0.0 and w.gc_parts["fuel"] == 0.0     # carried inside the wfh part
        gaps.append(w.gc - min(o.gc for o in opts if o.mode == "CAR"))
    assert gaps[0] == pytest.approx(gaps[1])
    # PT does gain against the car when fuel is added
    p = persona(fuel_cost=9.2)
    opts = build_options(p, new_memory(0), today(active=False), prm, cfg, False)
    pt = next(o for o in opts if o.mode == "PT")
    assert "fuel" in pt.gc_parts and pt.gc_parts["fuel"] == 0.0


def test_outcome_rows_fuel_paid(tiny_cfg) -> None:
    p = persona(wfh_allowed=True, fuel_cost=9.2)
    opts = build_options(p, new_memory(0), today(), P3, tiny_cfg, False)
    row = {"agent_id": 0, "day": 4, "corridor_id": 0, "depart_min": 465, "gate_arrive_min": 485,
           "gate_exit_min": 490, "queue_delay_min": 5, "arrive_min": 495, "fee_paid": 6.0}
    c = car_outcome(p, row)
    assert "fuel_paid" in OUTCOME_ROW_COLUMNS and tuple(c) == OUTCOME_ROW_COLUMNS
    assert c["fuel_paid"] == 9.2 and c["parking_paid"] == 8.0
    for mode in ("PT", "WFH", "SKIP"):
        r = non_car_outcome(p, next(o for o in opts if o.mode == mode), 4, False)
        assert r["fuel_paid"] == 0.0 and tuple(r) == OUTCOME_ROW_COLUMNS


# ------------------------------------------------------------------------------------------
# Early start (2026-10-05): the employer allows an earlier working day
# ------------------------------------------------------------------------------------------

def _early_cfg(**ov):
    return load_config(overrides={"rules.sigma_rule": 0.0, **ov})


def test_early_shift_departures_and_effective_start() -> None:
    """With the permission the car set also holds the departures around both start anchors, and each
    option is measured against the cheaper start; without it nothing changes."""
    from cordonlite.options import early_start_for
    cfg = _early_cfg()
    assert (cfg.costs.early_start_min, cfg.costs.early_shift_cost) == (420, 3.0)
    p0 = persona(tstar_min=510)                       # 08:30, 25 min free flow
    p1 = dataclasses.replace(p0, early_shift_ok=True)
    assert early_start_for(p0, cfg) is None and early_start_for(p1, cfg) == 420
    assert early_start_for(dataclasses.replace(p1, tstar_min=420), cfg) is None    # not earlier than t*
    base = car_departures(465, cfg)
    assert car_departures(465, cfg, p0) == base
    # early anchor 420 - 25 - 10 = 385 -> 375 (06:15), +/- 15 -> 06:00, 06:15, 06:30
    assert car_departures(465, cfg, p1) == sorted(set(base) | {360, 375, 390})
    # standing on the early departure: the usual-start anchor (465 +/- 15) stays reachable
    assert {450, 465, 480} <= set(car_departures(375, cfg, p1))

    m = new_memory(0)
    o0 = {o.option_id: o for o in build_options(p0, m, today(), P3, cfg, False)}
    o1 = {o.option_id: o for o in build_options(p1, m, today(), P3, cfg, False)}
    assert all(o.start_used_min == 510 and not o.early_shift for o in o0.values() if o.mode in ("CAR", "PT"))
    assert all(o.start_used_min is None and not o.early_shift for o in o0.values() if o.mode in ("WFH", "SKIP"))
    e = o1["CAR_0615"]                                 # arrives 06:40, 20 min before 07:00
    assert (e.start_used_min, e.early_shift, e.early_min, e.late_min) == (420, True, 20.0, 0.0)
    a = p1.vot / 60.0
    assert e.gc_parts["schedule"] == pytest.approx(a * 0.61 * 20.0 + 3.0 * P3.phi)
    # the same costs otherwise (time, fee at the early crossing, parking, fuel)
    assert e.gc == pytest.approx(sum(e.gc_parts.values()))
    # options near the usual start keep t* and are identical with and without the permission
    for oid in ("CAR_0745", "CAR_0800", "PT", "SKIP"):
        assert o1[oid] == o0[oid]
    # an arrival between the two starts takes the cheaper one: CAR_0645 arrives 07:10 (80 min before t*)
    mid = o1["CAR_0645"]
    c_usual = a * 0.61 * 80.0
    c_early = a * 2.38 * 10.0 + 3.0
    assert mid.gc_parts["schedule"] == pytest.approx(min(c_usual, c_early))
    assert mid.early_shift == (c_early < c_usual)
    # the inconvenience cost scales with phi(F)
    e2 = next(o for o in build_options(p1, m, today(), dataclasses.replace(P3, phi=2.0), cfg, False)
              if o.option_id == "CAR_0615")
    assert e2.gc_parts["schedule"] == pytest.approx(2.0 * a * 0.61 * 20.0 + 3.0 * 2.0)


def test_early_shift_preferred_over_skip_under_charge() -> None:
    """Constructed case: a long queue from 06:45, the charge, paid parking and a strong dislike of PT make
    postponing the cheapest option; with the employer's permission the commuter starts early instead."""
    from cordonlite.rules import RuleDecider
    from cordonlite.types import DecisionContext
    cfg = _early_cfg()
    queue = {0: tuple((float(m), 45.0) for m in range(402, 600, 5))}       # 45 min for gate arrivals from 06:40
    t = today(day=11, active=True, public_delay=queue)
    p0 = persona(tstar_min=510, vot=30.0, parking_cost=17.0, fuel_cost=12.0, P=1, F=3, S=3, H=3)
    choices = {}
    for name, p in (("no", p0), ("yes", dataclasses.replace(p0, early_shift_ok=True))):
        prm = trait_params(p, cfg)
        m = new_memory(0)
        set_standing(m, next(o for o in build_options(p, m, today(day=10, active=False), prm, cfg, False)
                             if o.option_id == "CAR_0745"))
        opts = build_options(p, m, t, prm, cfg, False)
        ctx = DecisionContext(agent_id=0, day=11, persona=p, params=prm, options=opts,
                              standing_option_id=m.habit_option_id, triggers=("T2",), discontinuity=False,
                              recent=(), delay_ratio_ema=1.0, ref_fee=0.0, today=t)
        choices[name] = ctx.option(RuleDecider(cfg).decide(ctx).option_id)
    assert choices["no"].option_id == "SKIP"
    c = choices["yes"]
    assert c.mode == "CAR" and c.early_shift and c.start_used_min == 420 and c.depart_min <= 390
    assert c.late_min == 0.0 and c.fee == pytest.approx(4.0)               # crosses before 07:30 at NZ$4


def test_early_shift_outcome_and_lateness_use_effective_start(tiny_cfg) -> None:
    """Outcome rows, the memory record and trigger T3 measure early/late against the start the option implies."""
    from cordonlite.clock import candidate_events
    from cordonlite.memory import record_from_outcome, update_memory
    cfg = _early_cfg()
    p = persona(tstar_min=510, early_shift_ok=True, F=3)                    # T3 tolerance 10 min at F = 3
    m = new_memory(0)
    opts = build_options(p, m, today(day=1, active=False), trait_params(p, cfg), cfg, False)
    e = next(o for o in opts if o.option_id == "CAR_0615")
    assert e.early_shift
    eng = {"agent_id": 0, "day": 1, "depart_min": 375, "gate_arrive_min": 395, "gate_exit_min": 430,
           "queue_delay_min": 35, "arrive_min": 435, "fee_paid": 0.0}       # arrives 07:15
    row = car_outcome(p, eng, e.option_id, e.start_used_min)
    assert (row["start_used_min"], row["early_shift"], row["early_min"], row["late_min"]) == (420, True, 0.0, 15.0)
    usual = car_outcome(p, eng, e.option_id)                                # no start given: the usual t*
    assert (usual["start_used_min"], usual["early_shift"], usual["early_min"], usual["late_min"]) == (510, False, 75.0, 0.0)
    assert set(row) == set(OUTCOME_ROW_COLUMNS)
    rec = record_from_outcome(row, e, "rule", ("T1",), "")
    assert (rec.start_used_min, rec.early_shift, rec.late_min) == (420, True, 15.0)
    set_standing(m, e)
    update_memory(m, rec, cfg)
    ev = candidate_events(p, m, today(day=2, active=False), ("CAR", "PT", "SKIP"), cfg)
    assert ("T3", 1) in ev                                                  # 15 min late for 07:00 > 10 min
    # the same arrival measured against the usual start would be 75 min early: no T3
    m2 = new_memory(0)
    set_standing(m2, e)
    update_memory(m2, record_from_outcome(usual, e, "rule", ("T1",), ""), cfg)
    assert ("T3", 1) not in candidate_events(p, m2, today(day=2, active=False), ("CAR", "PT", "SKIP"), cfg)
    # PT: the early-start service is used only when cheaper; the row follows the option
    pt = next(o for o in opts if o.mode == "PT")
    r_pt = non_car_outcome(p, pt, 1, False)
    assert r_pt["start_used_min"] == pt.start_used_min and r_pt["early_shift"] == pt.early_shift
    skip = non_car_outcome(p, next(o for o in opts if o.mode == "SKIP"), 1, False)
    assert skip["start_used_min"] is None and skip["early_shift"] is False


def test_early_shift_pt_takes_cheaper_start() -> None:
    """PT is priced for both starts; the early start wins only when its schedule saving exceeds the
    inconvenience cost (never with the default NZ$3 here, always when the cost is 0 and the wait is shorter)."""
    p = persona(tstar_min=515, early_shift_ok=True, pt_time_min=50.0, vot=30.0)   # 08:35: service 07:40, 5 min early
    for cost, early in ((3.0, False), (0.0, True)):
        cfg = _early_cfg(**{"costs.early_shift_cost": cost})
        pt = next(o for o in build_options(p, new_memory(0), today(), P3, cfg, False) if o.mode == "PT")
        assert pt.early_shift is early
        if early:   # 07:00 start: service 06:10 arrives 07:00 exactly
            assert (pt.depart_min, pt.expected_arrive_min, pt.early_min, pt.start_used_min) == (370, 420, 0.0, 420)
        else:
            assert (pt.depart_min, pt.expected_arrive_min, pt.early_min, pt.start_used_min) == (460, 510, 5.0, 515)
