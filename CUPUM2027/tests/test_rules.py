"""Rule decider: determinism, logit noise, and individual judgement from Layer B.

The key demonstration (``test_identical_a_different_b``): commuters with identical Layer A
(same job constraints, home, VoT, parking, t*) but different Layer B traits make different
choices on the morning the charge starts, under the shipped config (calibrated PAP, T2 not a
habit discontinuity; free parking). With paid parking and the early-start permission the flexible
commuter starts work at 07:00 instead (``test_paid_parking_split_and_early_start``). ``test_v3_worked_example`` reproduces the v3 section 11 worked example,
which needs the v3 settings (PAP 8 x HTA/2 = 4 for a local home, T2 a discontinuity). With traits
off they all choose identically.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from cordonlite import fees
from cordonlite.clock import is_discontinuity
from cordonlite.config import load_config, stream
from cordonlite.memory import AgentMemory, new_memory, set_standing
from cordonlite.options import build_options
from cordonlite.persona import trait_params
from cordonlite.rules import RuleDecider, explain
from cordonlite.types import FACTORS, DecisionContext, Persona, TodayInfo, TraitParams

# Shared Layer A: on-site office worker, starts 08:00, 20 + 5 min free flow, VoT NZ$20/h, free
# parking, PT 50 min (1.6 x 25 + 10), no company car. No WFH.
SHARED_A = dict(agent_id=0, origin_id=0, corridor_id=0, x_nztm=0.0, y_nztm=0.0, fftt_to_gate_min=20,
                fftt_gate_to_dest_min=5, path_km=20.0, vot=20.0, vot_quintile=4, archetype=2,
                activity="work", tstar_min=480, fixed_start=True, must_drive=False, sched_mult=1.0,
                pt_allowed=True, wfh_allowed=False, company_car=False, parking_cost=0.0,
                pt_time_min=50.0, pt_fare=7.0)


def _fuel(cfg) -> float:
    """Daily fuel cost of the shared 20 km path under cfg (as persona.build_personas derives it)."""
    return round(2.0 * SHARED_A["path_km"] * cfg.costs.fuel_cost_per_km, 2)


def today(day: int, active: bool, changed: bool = False, disrupted=()) -> TodayInfo:
    return TodayInfo(day=day, fee_regime="tou", fee_active=active,
                     fee_by_minute=tuple(fees.fee_table("tou" if active else "none")),
                     fee_changed_today=changed, public_delay={0: ()},
                     pt_disrupted_corridors=frozenset(disrupted), pt_disruption_announced=True,
                     pt_disruption_time_mult=2.0)


def context(p: Persona, mem: AgentMemory, t: TodayInfo, cfg, triggers=("T1",), disc=True) -> DecisionContext:
    prm = trait_params(p, cfg)
    opts = build_options(p, mem, t, prm, cfg, disc)
    return DecisionContext(agent_id=p.agent_id, day=t.day, persona=p, params=prm, options=opts,
                           standing_option_id=mem.standing_option_id, triggers=tuple(triggers),
                           discontinuity=disc, recent=mem.recent(5), delay_ratio_ema=mem.delay_ratio_ema,
                           ref_fee=mem.ref_fee, today=t)


def baseline_then_charge(p: Persona, cfg) -> tuple[str, str, DecisionContext]:
    """Day 1 (no charge, T1) then the charge-start morning (day 11, T2). The discontinuity flag
    follows ``cfg.clock.discontinuity_triggers``, as in the model."""
    rd = RuleDecider(cfg)
    mem = new_memory(p.agent_id)
    c1 = context(p, mem, today(1, False), cfg, ("T1",), is_discontinuity(("T1",), cfg))
    d1 = rd.decide(c1)
    set_standing(mem, c1.option(d1.option_id))
    c11 = context(p, mem, today(11, True, changed=True), cfg, ("T2",), is_discontinuity(("T2",), cfg))
    d11 = rd.decide(c11)
    return d1.option_id, d11.option_id, c11


@pytest.fixture
def cfg0():
    """Shipped config, deterministic argmin (no other overrides)."""
    return load_config(overrides={"rules.sigma_rule": 0.0})


@pytest.fixture
def cfg_v3():
    """v3 section 11 worked-example settings: the v3 attitude term PAP x HTA/2 = 8 x 1/2 = 4 for a local
    home, and T2 a habit discontinuity (v3 7.1), so kappa_H is halved on the charge morning."""
    return load_config(overrides={"rules.sigma_rule": 0.0, "costs.pt_attitude_penalty": 4.0,
                                  "clock.discontinuity_triggers": ["T1", "T2", "T4", "T6"]})


def _check_pay_pt_retime(res: dict) -> None:
    # everyone drives at the same time before the charge
    assert {r[0] for r in res.values()} == {"CAR_0730"}
    assert res["payer"][1] == "CAR_0730"                      # keeps driving and pays
    assert res["pt"][1] == "PT"                               # switches to PT
    retime = res["retimer"][1]
    assert retime.startswith("CAR_") and retime < "CAR_0730"  # leaves earlier, cheaper crossing
    ctx = res["retimer"][2]
    assert ctx.option(retime).fee < ctx.option("CAR_0730").fee
    # reasons name the trait-relevant drivers
    assert "fee" in explain(res["pt"][2], "PT")[1]


def test_identical_a_different_b(cfg0) -> None:
    """Shipped config: payer, PT switcher and retimer share Layer A (employer-paid parking and the fuel
    cost of their 20 km path); only (H, F, P, S) differ. Under the defaults retiming needs H = 1
    (kappa_H = 0): with T2 no longer a discontinuity, kappa_H(H = 2) = 0.5 outweighs the 15-min
    retime saving. With paid parking the split is different (next test)."""
    a = {**SHARED_A, "fuel_cost": _fuel(cfg0)}
    people = {
        "payer":   (5, 1, 1, 1),   # strong habit, inflexible, dislikes PT, charge not salient
        "pt":      (2, 3, 5, 4),   # loose habit, PT-open, charge salient
        "retimer": (1, 5, 1, 5),   # no habit cost, flexible, dislikes PT, charge very salient
    }
    res = {name: baseline_then_charge(Persona(**a, H=h, F=f, P=pp, S=s), cfg0)
           for name, (h, f, pp, s) in people.items()}
    _check_pay_pt_retime(res)


def test_paid_parking_split_and_early_start(cfg0) -> None:
    """Shared Layer A with paid parking NZ$17 and the fuel cost of a 20 km path, on the charge morning.
    Without the employer's early-start permission the split is pay / PT, with a few retimers (H = 1) and
    almost nobody postponing (SKIP costs NZ$30 plus one hour of VoT since 2026-10-05). With the permission
    (07:00 start instead of 08:00) the flexible, cost-salient commuters leave at 06:30 for the early start:
    the same Layer A and Layer B, a different constraint, a different choice."""
    import itertools
    from collections import Counter
    a = {**SHARED_A, "parking_cost": cfg0.persona.park_cost_paid[1], "fuel_cost": _fuel(cfg0)}
    assert (a["parking_cost"], a["fuel_cost"]) == (17.0, 12.0)
    assert (cfg0.costs.skip_cost, cfg0.costs.early_start_min, cfg0.costs.early_shift_cost) == (30.0, 420, 3.0)

    def run(t, early=False):
        h, f, pp, s = t
        d1, d11, c11 = baseline_then_charge(Persona(**a, H=h, F=f, P=pp, S=s, early_shift_ok=early), cfg0)
        return d1, d11, c11.option(d11)

    assert run((5, 1, 1, 1))[:2] == ("CAR_0730", "CAR_0730")     # keeps driving and pays
    assert run((2, 3, 3, 4))[:2] == ("CAR_0730", "PT")           # switches to PT
    assert run((1, 5, 1, 5))[:2] == ("CAR_0730", "CAR_0715")     # no permission: retimes by 15 min
    assert run((2, 5, 1, 5))[:2] == ("CAR_0730", "CAR_0730")     # no permission, loose habit: stays
    for t in ((1, 5, 1, 5), (2, 5, 1, 5)):                       # with the permission both start early
        d1, d11, o = run(t, early=True)
        assert (d1, d11) == ("CAR_0730", "CAR_0630")
        assert o.early_shift and o.start_used_min == 420 and o.late_min == 0.0 and o.fee == pytest.approx(4.0)
    assert run((5, 1, 1, 1), early=True)[:2] == ("CAR_0730", "CAR_0730")   # the payer is unchanged
    assert run((2, 3, 3, 4), early=True)[:2] == ("CAR_0730", "PT")
    for early, want in ((False, {"keep": 276, "PT": 93, "retime": 4, "SKIP": 2, "pt_before": 250}),
                        (True, {"keep": 260, "PT": 93, "early_start": 20, "SKIP": 2, "pt_before": 250})):
        kinds = Counter()
        for t in itertools.product(range(1, 6), repeat=4):
            d1, d11, o = run(t, early)
            kinds["pt_before" if d1 == "PT" else "keep" if d11 == d1 else d11 if d11 in ("PT", "SKIP")
                  else "early_start" if o.early_shift else "retime"] += 1
        assert kinds == want


def test_v3_worked_example(cfg_v3) -> None:
    """v3 section 11: free parking, local home; separates only with the v3 settings (cfg_v3)."""
    people = {
        "payer":   (5, 1, 1, 1),   # strong habit, inflexible, dislikes PT, charge not salient
        "pt":      (2, 3, 5, 4),   # loose habit, PT-open, charge salient
        "retimer": (2, 5, 1, 5),   # loose habit, flexible, dislikes PT, charge very salient (eta capped at 1)
    }
    res = {name: baseline_then_charge(Persona(**SHARED_A, H=h, F=f, P=pp, S=s), cfg_v3)
           for name, (h, f, pp, s) in people.items()}
    _check_pay_pt_retime(res)


def test_v3_worked_example_does_not_separate_under_defaults(cfg0) -> None:
    """Documented limitation: with free parking, the calibrated PAP and no T2 discontinuity, the v3
    worked-example personas do not give the pay / PT / retime split on the charge morning. With the
    fuel cost of their 20 km path the PT persona does switch, but the retimer (H = 2) keeps its
    standing time; without any fuel cost (the model before the fuel addition) all three keep driving."""
    people = ((5, 1, 1, 1), (2, 3, 5, 4), (2, 5, 1, 5))
    a = {**SHARED_A, "fuel_cost": _fuel(cfg0)}
    res = [baseline_then_charge(Persona(**a, H=h, F=f, P=pp, S=s), cfg0)[:2] for (h, f, pp, s) in people]
    assert res == [("CAR_0730", "CAR_0730"), ("CAR_0730", "PT"), ("CAR_0730", "CAR_0730")]
    res0 = {baseline_then_charge(Persona(**SHARED_A, H=h, F=f, P=pp, S=s), cfg0)[:2] for (h, f, pp, s) in people}
    assert res0 == {("CAR_0730", "CAR_0730")}


def test_traits_off_identical(cfg0) -> None:
    """With every trait at the off level, the same Layer A gives the same choice."""
    lv = cfg0.traits.off_level
    choices = set()
    for agent_id in range(5):
        p = Persona(**{**SHARED_A, "agent_id": agent_id}, H=lv, F=lv, P=lv, S=lv)
        choices.add(baseline_then_charge(p, cfg0)[:2])
    assert len(choices) == 1


def test_traits_on_population_differs_off_does_not(tiny_origins, tiny_corridors_prep) -> None:
    """build_personas twins (identical A): traits on gives some different charge-day choices, off none."""
    from cordonlite.persona import build_personas, twin_pairs
    cfg = load_config(overrides={"run.n_agents": 120, "persona.n_twins": 60, "rules.sigma_rule": 0.0})
    diff = {}
    for mode in ("on", "off"):
        ps = build_personas(tiny_origins, tiny_corridors_prep, cfg, traits=mode)
        pairs = twin_pairs(ps)
        assert len(pairs) == 60
        ch = {p.agent_id: baseline_then_charge(p, cfg)[1] for p in ps}
        diff[mode] = sum(ch[i] != ch[j] for i, j in pairs)
    assert diff["off"] == 0
    assert diff["on"] >= 10


def test_deterministic_and_noise_stream(tiny_cfg) -> None:
    p = Persona(**SHARED_A, H=3, F=3, P=3, S=3)
    mem = new_memory(0)
    ctx = context(p, mem, today(11, True), tiny_cfg)
    rd = RuleDecider(tiny_cfg)
    d1, d2 = rd.decide(ctx), RuleDecider(tiny_cfg).decide(ctx)
    assert d1 == d2
    from cordonlite.rules import option_code
    eps = np.array([stream(tiny_cfg.run.seed, "rule", 0, 11, option_code(o.option_id)).gumbel(
        0.0, tiny_cfg.rules.sigma_rule) for o in ctx.options])
    assert np.allclose(d1.meta["noise"], -eps)
    util = np.array([o.gc for o in ctx.options]) - eps
    assert d1.option_id == ctx.options[int(np.argmin(util))].option_id
    assert d1.decider == "rule" and d1.agent_id == 0 and d1.day == 11
    assert d1.reason and set(d1.factors) <= set(FACTORS)
    other_day = rd.noise(0, 12, [o.option_id for o in ctx.options])
    assert not np.allclose(other_day, eps)
    # common random numbers: the draw for an option does not depend on its position
    ids = [o.option_id for o in ctx.options]
    assert np.allclose(rd.noise(0, 11, ids[::-1]), eps[::-1])
    # a twin (noise id = its source agent) gets the source agent's draws
    rt = RuleDecider(tiny_cfg, {7: 0})
    assert np.allclose(rt.noise(7, 11, ids), eps)
    assert not np.allclose(rd.noise(7, 11, ids), eps)


def test_sigma_zero_is_argmin(cfg0) -> None:
    p = Persona(**SHARED_A, H=3, F=3, P=3, S=3)
    ctx = context(p, new_memory(0), today(11, True), cfg0)
    d = RuleDecider(cfg0).decide(ctx)
    assert d.option_id == min(ctx.options, key=lambda o: o.gc).option_id
    assert d.meta["noise"] == [0.0] * len(ctx.options)


def test_logit_probabilities() -> None:
    """argmin(gc - Gumbel) reproduces binary logit: P(cheaper) = 1 / (1 + exp(-dGC / sigma))."""
    cfg = load_config(overrides={"rules.sigma_rule": 1.0})
    rd = RuleDecider(cfg)
    p = Persona(**{**SHARED_A, "pt_allowed": False}, H=3, F=3, P=3, S=3)
    base = context(p, new_memory(0), today(11, True), cfg)
    car = min((o for o in base.options if o.mode == "CAR"), key=lambda o: o.gc)
    skip = base.option("SKIP")
    car = dataclasses.replace(car, gc=10.0)
    skip = dataclasses.replace(skip, gc=11.0)
    n, wins = 6000, 0
    for i in range(n):
        ctx = dataclasses.replace(base, agent_id=i, options=(car, skip))
        wins += rd.decide(ctx).option_id == car.option_id
    assert wins / n == pytest.approx(1 / (1 + np.exp(-1.0)), abs=0.02)


def test_ties_go_to_lower_index(cfg0) -> None:
    p = Persona(**SHARED_A, H=3, F=3, P=3, S=3)
    base = context(p, new_memory(0), today(11, True), cfg0)
    a = dataclasses.replace(base.options[0], gc=5.0)
    b = dataclasses.replace(base.options[1], gc=5.0)
    ctx = dataclasses.replace(base, options=(a, b))
    assert RuleDecider(cfg0).decide(ctx).option_id == a.option_id


def test_batch_order_and_disruption_factor(tiny_personas, tiny_cfg) -> None:
    rd = RuleDecider(tiny_cfg)
    ctxs = []
    for p in tiny_personas:
        m = new_memory(p.agent_id)
        ctxs.append(context(p, m, today(5, True, disrupted=[0, 1, 2]), tiny_cfg, ("T4",), True))
    ds = rd.decide_batch(ctxs)
    assert [d.agent_id for d in ds] == [p.agent_id for p in tiny_personas]
    assert ds == [rd.decide(c) for c in ctxs]
    for d, c in zip(ds, ctxs):
        assert d.option_id in c.option_ids
        assert "disruption" in d.factors and set(d.factors) <= set(FACTORS)


def test_empty_options_raise(tiny_cfg) -> None:
    p = Persona(**SHARED_A, H=3, F=3, P=3, S=3)
    ctx = dataclasses.replace(context(p, new_memory(0), today(1, False), tiny_cfg), options=())
    with pytest.raises(ValueError):
        RuleDecider(tiny_cfg).decide(ctx)
