"""Persona construction: determinism, A/B independence, twins, feasibility, trait mapping."""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from cordonlite.config import load_config, stream
from cordonlite.engine import AGENTS_COLUMNS
from cordonlite.persona import (TRAIT_SENTENCES, agents_frame, build_personas, disposition_sentences,
                                draw_traits, layer_a_key, personas_to_frame, trait_params, twin_pairs)
from cordonlite.types import Persona

A_FIELDS = [f.name for f in dataclasses.fields(Persona) if f.name not in ("agent_id", "H", "F", "P", "S")]


def _a(p: Persona) -> tuple:
    return tuple(getattr(p, f) for f in A_FIELDS)


def _b(p: Persona) -> tuple:
    return (p.H, p.F, p.P, p.S)


def test_deterministic(tiny_origins, tiny_corridors_prep, tiny_cfg) -> None:
    a = build_personas(tiny_origins, tiny_corridors_prep, tiny_cfg)
    b = build_personas(tiny_origins, tiny_corridors_prep, tiny_cfg)
    assert a == b
    assert len(a) == tiny_cfg.run.n_agents
    assert [p.agent_id for p in a] == list(range(len(a)))
    assert personas_to_frame(a).equals(personas_to_frame(b))


def test_changing_a_tables_leaves_traits_unchanged(tiny_origins, tiny_corridors_prep) -> None:
    c1 = load_config(overrides={"run.n_agents": 60})
    c2 = load_config(overrides={"run.n_agents": 60, "persona.arch_weight": [0.1, 0.1, 0.1, 0.6, 0.1],
                                "persona.vot_mu": 3.0, "persona.tstar_mean_min": [480, 480, 480, 480, 480]})
    p1 = build_personas(tiny_origins, tiny_corridors_prep, c1)
    p2 = build_personas(tiny_origins, tiny_corridors_prep, c2)
    assert [_b(p) for p in p1] == [_b(p) for p in p2]
    assert [_a(p) for p in p1] != [_a(p) for p in p2]


def test_changing_trait_tables_leaves_a_unchanged(tiny_origins, tiny_corridors_prep) -> None:
    c1 = load_config(overrides={"run.n_agents": 60})
    c2 = load_config(overrides={"run.n_agents": 60, "traits.shares_P": [0.5, 0.2, 0.1, 0.1, 0.1],
                                "traits.shares_H": [0.2, 0.2, 0.2, 0.2, 0.2]})
    p1 = build_personas(tiny_origins, tiny_corridors_prep, c1)
    p2 = build_personas(tiny_origins, tiny_corridors_prep, c2)
    assert [_a(p) for p in p1] == [_a(p) for p in p2]
    assert [_b(p) for p in p1] != [_b(p) for p in p2]


def test_seed_changes_both_layers(tiny_origins, tiny_corridors_prep) -> None:
    p1 = build_personas(tiny_origins, tiny_corridors_prep, load_config(overrides={"run.n_agents": 40}))
    p2 = build_personas(tiny_origins, tiny_corridors_prep, load_config(overrides={"run.n_agents": 40, "run.seed": 12}))
    assert [_a(p) for p in p1] != [_a(p) for p in p2]
    assert [_b(p) for p in p1] != [_b(p) for p in p2]


def test_traits_from_b_stream_only(tiny_origins, tiny_corridors_prep, tiny_cfg) -> None:
    ps = build_personas(tiny_origins, tiny_corridors_prep, tiny_cfg)
    expected = draw_traits(len(ps), tiny_cfg, stream(tiny_cfg.run.seed, "B"))
    assert np.array_equal(np.array([_b(p) for p in ps]), expected)


def test_twins(tiny_origins, tiny_corridors_prep, tiny_cfg) -> None:
    ps = build_personas(tiny_origins, tiny_corridors_prep, tiny_cfg)
    n, k = len(ps), min(tiny_cfg.persona.n_twins, len(ps) // 2)
    assert k == 4
    for j in range(k):
        assert _a(ps[j]) == _a(ps[n - k + j])
        assert layer_a_key(ps[j]) == layer_a_key(ps[n - k + j])
    assert twin_pairs(ps) == [(j, n - k + j) for j in range(k)]
    # twins keep their own traits: at least one pair differs
    assert any(_b(ps[j]) != _b(ps[n - k + j]) for j in range(k))


def test_twins_capped_at_half(tiny_origins, tiny_corridors_prep) -> None:
    cfg = load_config(overrides={"run.n_agents": 6, "persona.n_twins": 30})
    ps = build_personas(tiny_origins, tiny_corridors_prep, cfg)
    assert twin_pairs(ps) == [(0, 3), (1, 4), (2, 5)]


def test_traits_off(tiny_origins, tiny_corridors_prep, tiny_cfg) -> None:
    on = build_personas(tiny_origins, tiny_corridors_prep, tiny_cfg, traits="on")
    off = build_personas(tiny_origins, tiny_corridors_prep, tiny_cfg, traits="off")
    assert all(_b(p) == (3, 3, 3, 3) for p in off)
    assert [_a(p) for p in on] == [_a(p) for p in off]
    with pytest.raises(ValueError):
        build_personas(tiny_origins, tiny_corridors_prep, tiny_cfg, traits="maybe")


def test_trait_shares_match_v3() -> None:
    cfg = load_config()
    tr = draw_traits(40000, cfg, stream(1, "B"))
    for j, name in enumerate("HFPS"):
        shares = np.bincount(tr[:, j], minlength=6)[1:] / len(tr)
        assert np.allclose(shares, getattr(cfg.traits, f"shares_{name}"), atol=0.01)
    # independence of traits: correlation near zero
    corr = np.corrcoef(tr.T)
    assert np.all(np.abs(corr[np.triu_indices(4, 1)]) < 0.03)


def test_layer_a_rules(tiny_origins, tiny_corridors_prep) -> None:
    cfg = load_config(overrides={"run.n_agents": 400, "persona.n_twins": 0})
    ps = build_personas(tiny_origins, tiny_corridors_prep, cfg)
    pc, tc = cfg.persona, cfg.time
    q = np.bincount([p.vot_quintile for p in ps], minlength=6)[1:]
    assert q.tolist() == [80] * 5
    vots = np.array([p.vot for p in ps])
    quint = np.array([p.vot_quintile for p in ps])
    for a, b in zip(range(1, 5), range(2, 6)):
        assert vots[quint == a].max() <= vots[quint == b].min()
    assert abs(np.log(vots).mean() - pc.vot_mu) < 0.1
    archs = {p.archetype for p in ps}
    assert archs == {1, 2, 3, 4, 5}
    for p in ps:
        ai = p.archetype - 1
        assert tc.tstar_earliest_min <= p.tstar_min <= tc.tstar_latest_min
        assert (p.tstar_min - tc.tstar_earliest_min) % tc.tstar_step_min == 0
        assert p.must_drive == pc.must_drive[ai] and p.fixed_start == pc.fixed_start[ai]
        assert p.sched_mult == pc.sched_mult[ai]
        assert p.activity == pc.activity[ai]
        if p.must_drive:
            assert not p.pt_allowed and not p.wfh_allowed
        assert p.wfh_allowed == (pc.wfh_allowed[ai] and not p.must_drive)
        if p.company_car:
            assert p.parking_cost == 0.0
        else:
            assert p.parking_cost in (0.0, pc.park_cost_paid[ai])
        assert p.fftt_to_gate_min >= 1 and p.fftt_gate_to_dest_min >= 0
        assert p.pt_time_min == pytest.approx(cfg.pt_ratio(p.corridor_id) * p.fftt_total_min + cfg.costs.pt_access_min)
        assert p.pt_fare == cfg.costs.pt_fare
    # company cars only where the probability is positive; most archetype-4 agents have one
    a4 = [p for p in ps if p.archetype == 4]
    assert 0.5 < np.mean([p.company_car for p in a4]) < 0.9
    assert not any(p.company_car for p in ps if p.archetype in (3, 5))
    # VoT tilt: hybrid office over-represented in Q5, students in Q1
    share = lambda arch, qq: np.mean([p.archetype == arch for p in ps if p.vot_quintile == qq])
    assert share(1, 5) > share(1, 1)
    assert share(5, 1) > share(5, 5)


def test_rounding_and_origin_fields(tiny_corridors_prep) -> None:
    origins = pd.DataFrame({
        "origin_id": [7], "x_nztm": [1.0], "y_nztm": [2.0], "weight": [1.0], "corridor_id": [1],
        "gate_id": [3], "fftt_to_gate_min": [0.4], "fftt_gate_to_dest_min": [2.5], "path_km": [3.3],
    })
    cfg = load_config(overrides={"run.n_agents": 3, "persona.n_twins": 0})
    ps = build_personas(origins, tiny_corridors_prep, cfg)
    for p in ps:
        assert (p.origin_id, p.corridor_id, p.x_nztm, p.y_nztm, p.path_km) == (7, 1, 1.0, 2.0, 3.3)
        assert p.fftt_to_gate_min == 1          # 0.4 -> 0 -> minimum 1
        assert p.fftt_gate_to_dest_min == 3     # 2.5 -> 3 (half away from zero)


def test_pt_unavailable_corridor(tiny_origins, tiny_corridors_prep) -> None:
    cfg = load_config(overrides={"run.n_agents": 60, "costs.pt_unavailable_corridors": [0]})
    ps = build_personas(tiny_origins, tiny_corridors_prep, cfg)
    assert not any(p.pt_allowed for p in ps if p.corridor_id == 0)
    assert any(p.pt_allowed for p in ps if p.corridor_id != 0)


def test_unknown_corridor_raises(tiny_origins, tiny_corridors_prep, tiny_cfg) -> None:
    with pytest.raises(ValueError):
        build_personas(tiny_origins, tiny_corridors_prep[tiny_corridors_prep.corridor_id != 2], tiny_cfg)


def test_origin_weights_respected(tiny_corridors_prep) -> None:
    origins = pd.DataFrame({
        "origin_id": [0, 1], "x_nztm": [0.0, 1.0], "y_nztm": [0.0, 1.0], "weight": [0.0, 1.0],
        "corridor_id": [0, 2], "gate_id": [0, 1], "fftt_to_gate_min": [10.0, 20.0],
        "fftt_gate_to_dest_min": [3.0, 4.0], "path_km": [8.0, 16.0],
    })
    ps = build_personas(origins, tiny_corridors_prep, load_config(overrides={"run.n_agents": 30}))
    assert {p.origin_id for p in ps} == {1}


def test_trait_params_and_sentences(tiny_personas, tiny_cfg) -> None:
    t = tiny_cfg.traits
    for p in tiny_personas:
        tp = trait_params(p, tiny_cfg)
        assert tp.kappa_h == t.kappa_h[p.H - 1] and tp.phi == t.phi[p.F - 1]
        assert tp.omega == t.omega[p.P - 1] and tp.eta == t.eta[p.S - 1]
        s = disposition_sentences(p)
        assert s == (TRAIT_SENTENCES["H"][p.H - 1], TRAIT_SENTENCES["F"][p.F - 1],
                     TRAIT_SENTENCES["P"][p.P - 1], TRAIT_SENTENCES["S"][p.S - 1])
    all_s = [x for v in TRAIT_SENTENCES.values() for x in v]
    assert len(all_s) == 20 and len(set(all_s)) == 20
    for x in all_s:
        assert "habit" not in x.lower() and "salience" not in x.lower() and "\u2014" not in x
    # kappa_h and eta rise with level; phi and omega fall
    assert list(t.kappa_h) == sorted(t.kappa_h) and list(t.eta) == sorted(t.eta)
    assert list(t.phi) == sorted(t.phi, reverse=True) and list(t.omega) == sorted(t.omega, reverse=True)


def test_frames(tiny_personas) -> None:
    df = personas_to_frame(tiny_personas)
    assert list(df.columns) == [f.name for f in dataclasses.fields(Persona)]
    assert len(df) == len(tiny_personas)
    ag = agents_frame(tiny_personas)
    assert tuple(ag.columns) == AGENTS_COLUMNS
    assert ag["fftt_to_gate_min"].dtype.kind == "i"
    assert ag["x"].tolist() == [p.x_nztm for p in tiny_personas]


def test_fuel_cost_from_path_length(tiny_origins, tiny_corridors_prep) -> None:
    """Fuel = 2 x path_km x costs.fuel_cost_per_km to the cent; company cars pay none; no extra draw."""
    base = {"run.n_agents": 400, "persona.n_twins": 0}
    cfg = load_config(overrides={**base, "costs.fuel_cost_per_km": 0.25})
    ps = build_personas(tiny_origins, tiny_corridors_prep, cfg)
    assert any(p.company_car for p in ps) and any(not p.company_car for p in ps)
    for p in ps:
        want = 0.0 if p.company_car else round(2.0 * p.path_km * 0.25, 2)
        assert p.fuel_cost == pytest.approx(want)
        if not p.company_car and p.path_km > 0.02:
            assert p.fuel_cost > 0
    # the per-km value changes nothing else (fuel is derived, not drawn)
    ps0 = build_personas(tiny_origins, tiny_corridors_prep, load_config(overrides={**base, "costs.fuel_cost_per_km": 0.0}))
    assert all(p.fuel_cost == 0.0 for p in ps0)
    assert [dataclasses.replace(p, fuel_cost=0.0) for p in ps] == ps0
    assert "fuel_cost" in personas_to_frame(ps).columns
    # shipped default: fixed from evidence, in the fuel-only range
    assert 0.15 <= load_config().costs.fuel_cost_per_km <= 0.30


def test_early_shift_permission_drawn_last(tiny_origins, tiny_corridors_prep) -> None:
    """The early-start permission is drawn after every other Layer A draw: switching it off changes no
    other field; shares follow persona.early_shift_prob by archetype; twins copy it; deterministic."""
    import dataclasses
    base = {"run.n_agents": 400, "run.seed": 3}
    cfg = load_config(overrides=base)
    assert tuple(cfg.persona.early_shift_prob) == (0.8, 0.5, 0.0, 0.5, 0.0)
    ps = build_personas(tiny_origins, tiny_corridors_prep, cfg)
    ps0 = build_personas(tiny_origins, tiny_corridors_prep,
                         load_config(overrides={**base, "persona.early_shift_prob": [0.0] * 5}))
    assert not any(p.early_shift_ok for p in ps0)
    assert [dataclasses.replace(p, early_shift_ok=False) for p in ps] == ps0
    assert ps == build_personas(tiny_origins, tiny_corridors_prep, cfg)
    assert not any(p.early_shift_ok for p in ps if p.archetype in (3, 5))
    for arch, lo, hi in ((1, 0.65, 0.95), (2, 0.3, 0.7), (4, 0.2, 0.8)):
        g = [p.early_shift_ok for p in ps if p.archetype == arch]
        assert lo <= sum(g) / len(g) <= hi
    by_id = {p.agent_id: p for p in ps}
    for a, b in twin_pairs(ps):
        assert by_id[a].early_shift_ok == by_id[b].early_shift_ok
