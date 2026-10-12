"""Willingness to travel (2026-10-09): the exponential-decay willingness to pay, the CAR option filter and
its exceptions, the clock (T6), fee_faced, the prompt, and the run-level invariances (wtt.beta0 = 0 is the
model without it; uncharged days do not depend on beta0)."""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cordonlite import fees, llm
from cordonlite import run as R
from cordonlite.clock import evaluate_triggers
from cordonlite.config import ConfigError, load_config
from cordonlite.memory import new_memory, set_standing
from cordonlite.options import build_options, fee_faced, initial_depart_min, wtt_filter
from cordonlite.persona import (build_personas, layer_a_key, personas_to_frame, twin_pairs, willingness_to_pay,
                                wtt_vot_ref)
from cordonlite.types import DecisionContext, Persona, TodayInfo, TraitParams

P3 = TraitParams(kappa_h=1.0, phi=1.0, omega=1.0, eta=1.0)


def persona(**kw) -> Persona:
    base = dict(agent_id=0, origin_id=0, corridor_id=0, x_nztm=0.0, y_nztm=0.0, fftt_to_gate_min=20,
                fftt_gate_to_dest_min=5, path_km=20.0, vot=30.0, vot_quintile=3, archetype=2,
                activity="work", tstar_min=510, fixed_start=True, must_drive=False, sched_mult=1.0,
                pt_allowed=True, wfh_allowed=False, company_car=False, parking_cost=8.0,
                pt_time_min=50.0, pt_fare=7.0, H=3, F=3, P=3, S=3)
    base.update(kw)
    return Persona(**base)


def today(day: int = 11, active: bool = True) -> TodayInfo:
    return TodayInfo(day=day, fee_regime="tou", fee_active=active,
                     fee_by_minute=tuple(fees.fee_table("tou" if active else "none")),
                     fee_changed_today=False, public_delay={0: ()}, pt_disrupted_corridors=frozenset(),
                     pt_disruption_announced=True, pt_disruption_time_mult=2.0)


# --------------------------------------------------------------------------- the draw


def test_willingness_to_pay_formula_and_exponential_share() -> None:
    """WTP = -ln(u) x VoT / beta (to the cent), beta = clip(beta0 x VoT_ref / VoT, 0.1, 2.0), so the share
    of draws with WTP >= F is exp(-beta F / VoT) at every VoT; beta0 = 0 is no limit (and no clip)."""
    cfg = load_config(overrides={"wtt.beta0": 0.5, "wtt.beta_clip": [0.1, 2.0]})
    ref = wtt_vot_ref(np.array([1.0, 2.0]), cfg)
    assert ref == pytest.approx(math.exp(cfg.persona.vot_mu))            # distribution median, not the sample's
    u = np.random.default_rng(7).random(200_000)
    for vot in (2.0, 5.0, 10.0, 20.0, 60.0, 200.0):
        beta = min(max(0.5 * ref / vot, 0.1), 2.0)
        draws = [willingness_to_pay(float(x), vot, ref, cfg) for x in u]
        assert all(b == beta for b, _ in draws[:5])
        assert draws[0][1] == round(-math.log(u[0]) * vot / beta, 2)
        wtp = np.array([w for _, w in draws])
        for f in (2.0, 4.0, 6.0, 12.0, 30.0):
            assert np.mean(wtp >= f) == pytest.approx(math.exp(-beta * f / vot), abs=0.006), (vot, f)
    assert willingness_to_pay(0.0, 10.0, ref, cfg) == (pytest.approx(0.5 * ref / 10.0), math.inf)
    off = load_config(overrides={"wtt.beta0": 0.0})
    assert willingness_to_pay(0.3, 10.0, ref, off) == (0.0, math.inf)


def test_wtt_config_keys_and_validation() -> None:
    cfg = load_config()
    assert cfg.wtt.beta0 > 0 and tuple(cfg.wtt.beta_clip) == (0.1, 2.0) and cfg.wtt.vot_ref == "distribution_median"
    sample = load_config(overrides={"wtt.vot_ref": "sample_median"})
    assert wtt_vot_ref(np.array([4.0, 9.0, 30.0]), sample) == 9.0
    for bad in ({"wtt.beta0": -0.1}, {"wtt.beta_clip": [0.0, 2.0]}, {"wtt.beta_clip": [2.0, 1.0]},
                {"wtt.vot_ref": "mean"}):
        with pytest.raises(ConfigError, match="wtt"):
            load_config(overrides=bad)


def test_wtt_draw_is_last_layer_a_draw_and_twins_copy_it(tiny_origins, tiny_corridors_prep) -> None:
    """beta0 changes only wtt_beta and wtp_fee (the uniform draw comes after every other Layer A draw);
    beta0 = 0 gives no limit; twins copy the three fields with the rest of Layer A; personas.csv has them."""
    base = {"run.n_agents": 200, "persona.n_twins": 20, "run.seed": 3}
    ps = build_personas(tiny_origins, tiny_corridors_prep, load_config(overrides={**base, "wtt.beta0": 0.5}))
    p0 = build_personas(tiny_origins, tiny_corridors_prep, load_config(overrides={**base, "wtt.beta0": 0.0}))
    p2 = build_personas(tiny_origins, tiny_corridors_prep, load_config(overrides={**base, "wtt.beta0": 2.0}))
    assert all(p.wtt_beta == 0.0 and p.wtp_fee == math.inf for p in p0)
    assert [dataclasses.replace(p, wtt_beta=0.0, wtp_fee=math.inf) for p in ps] == p0
    assert [p.wtt_u for p in p2] == [p.wtt_u for p in ps] and len({p.wtt_u for p in ps}) == 180
    assert all(0.0 <= p.wtt_u < 1.0 and 0.1 <= p.wtt_beta <= 2.0 and p.wtp_fee >= 0.0 for p in ps)
    ref = math.exp(2.3)
    assert all(p.wtt_beta == min(max(0.5 * ref / p.vot, 0.1), 2.0) for p in ps)
    assert sum(q.wtp_fee < p.wtp_fee for p, q in zip(ps, p2)) > 150         # more sensitive: lower WTP
    by_id = {p.agent_id: p for p in ps}
    pairs = twin_pairs(ps)
    assert len(pairs) == 20
    for a, b in pairs:
        assert layer_a_key(by_id[a]) == layer_a_key(by_id[b])
        assert (by_id[a].wtt_u, by_id[a].wtt_beta, by_id[a].wtp_fee) == (by_id[b].wtt_u, by_id[b].wtt_beta,
                                                                         by_id[b].wtp_fee)
    assert list(personas_to_frame(ps).columns)[-3:] == ["wtt_u", "wtt_beta", "wtp_fee"]
    assert personas_to_frame(p0)["wtp_fee"].tolist() == [math.inf] * 200


def test_population_share_willing_falls_exponentially(tiny_origins, tiny_corridors_prep) -> None:
    """Over the built commuters the share willing to pay F matches the mean of exp(-beta_i F / VoT_i)."""
    ps = build_personas(tiny_origins, tiny_corridors_prep,
                        load_config(overrides={"run.n_agents": 4000, "persona.n_twins": 0, "wtt.beta0": 0.5}))
    wtp = np.array([p.wtp_fee for p in ps])
    for f in (2.0, 4.0, 6.0, 12.0, 30.0):
        want = np.mean([math.exp(-p.wtt_beta * f / p.vot) for p in ps])
        assert np.mean(wtp >= f) == pytest.approx(want, abs=0.025), f


# --------------------------------------------------------------------------- the choice set


def test_filter_removes_car_options_charged_above_wtp(tiny_cfg) -> None:
    p = persona(wfh_allowed=True, wtp_fee=5.0)
    m = new_memory(0)
    m.standing_depart_min = 465                                    # grid 06:45-08:45, charges 4 to 6
    full = build_options(p, m, today(), P3, tiny_cfg, False, wtt=False)
    kept = build_options(p, m, today(), P3, tiny_cfg, False)
    assert kept == wtt_filter(p, full)
    assert {o.mode for o in full} == {"CAR", "PT", "WFH"}
    assert [o for o in full if o.mode != "CAR" or o.fee <= 5.0] == list(kept)
    assert any(o.mode == "CAR" and o.fee > 5.0 for o in full)          # peak departures removed
    assert any(o.mode == "CAR" and o.fee == 4.0 for o in kept)          # shoulder departures stay (retiming)
    mid = sorted({o.fee for o in full if o.mode == "CAR"})[2]
    assert 4.0 < mid < 6.0
    q = dataclasses.replace(p, wtp_fee=mid)                             # a charge equal to WTP stays
    assert [o.fee for o in build_options(q, m, today(), P3, tiny_cfg, False) if o.mode == "CAR"] == \
        [o.fee for o in full if o.mode == "CAR" and o.fee <= mid]
    assert any(o.fee == mid for o in build_options(q, m, today(), P3, tiny_cfg, False))
    # below every charged crossing: no car option, PT and WFH remain
    low = dataclasses.replace(p, wtp_fee=3.99)
    assert [o.mode for o in build_options(low, m, today(), P3, tiny_cfg, False)] == ["PT", "WFH"]
    # no limit, or an uncharged day: nothing removed (every fee 0 <= WTP, also WTP 0)
    assert build_options(dataclasses.replace(p, wtp_fee=math.inf), m, today(), P3, tiny_cfg, False) == full
    zero = dataclasses.replace(p, wtp_fee=0.0)
    free = build_options(zero, m, today(active=False), P3, tiny_cfg, False, wtt=False)
    assert build_options(zero, m, today(active=False), P3, tiny_cfg, False) == free


def test_filter_exceptions_company_car_and_essential_trip(tiny_cfg) -> None:
    """A company car (the employer pays) and a commuter with neither PT nor WFH keep every car option;
    WFH alone, or PT alone, is enough of an alternative for the rule to apply."""
    m = new_memory(0)
    m.standing_depart_min = 465
    cases = {
        "company": (dict(company_car=True, parking_cost=0.0), False),
        "must_drive": (dict(must_drive=True, pt_allowed=False, archetype=4), False),
        "no_pt_no_wfh": (dict(pt_allowed=False), False),                 # e.g. a corridor without PT
        "wfh_only": (dict(pt_allowed=False, wfh_allowed=True), True),
        "pt_only": (dict(), True),
    }
    for name, (kw, filtered) in cases.items():
        p = persona(wtp_fee=0.5, **kw)
        full = build_options(p, m, today(), P3, tiny_cfg, False, wtt=False)
        kept = build_options(p, m, today(), P3, tiny_cfg, False)
        assert any(o.mode == "CAR" and o.fee > 0.5 for o in full), name
        assert (kept != full) is filtered, name
        if filtered:
            assert all(o.mode != "CAR" for o in kept), name


def test_fee_faced_uses_the_reference_departure_even_when_removed(tiny_cfg) -> None:
    p = persona(wtp_fee=1.0)
    m = new_memory(0)
    full = build_options(p, m, today(), P3, tiny_cfg, False, wtt=False)
    kept = build_options(p, m, today(), P3, tiny_cfg, False)
    assert [o.mode for o in kept] == ["PT"]                            # every car option charged above NZ$1
    d0 = initial_depart_min(p, tiny_cfg)
    ref = next(o for o in full if o.mode == "CAR" and o.depart_min == d0)
    assert fee_faced(p, m, full, tiny_cfg, today()) == ref.fee > 1.0


def test_t6_wakes_when_the_standing_car_option_is_not_offered(tiny_cfg) -> None:
    """With option ids the standing departure itself must be offered (a departure removed by the
    willingness to pay is not); with feasible modes any car option will do, as before."""
    def standing(depart: int):
        mem = new_memory(0)
        set_standing(mem, next(o for o in build_options(persona(), mem, today(5, False), P3, tiny_cfg, False)
                               if o.depart_min == depart))
        return mem
    t = today(11)
    assert evaluate_triggers(persona(), standing(480), t, ("CAR_0700", "CAR_0715", "PT"), tiny_cfg) == ("T6",)
    assert evaluate_triggers(persona(), standing(480), t, ("PT",), tiny_cfg) == ("T6",)
    assert evaluate_triggers(persona(), standing(480), t, ("CAR_0700", "CAR_0800", "PT"), tiny_cfg) == ()
    assert evaluate_triggers(persona(), standing(480), t, ("CAR", "PT"), tiny_cfg) == ()
    # built options: WTP NZ$5 removes the 08:00 departure (crossing at NZ$6) but keeps 07:15 (NZ$4)
    p = persona(wtp_fee=5.0)
    mem = standing(480)
    ids = [o.option_id for o in build_options(p, mem, t, P3, tiny_cfg, False)]
    assert "CAR_0800" not in ids and "CAR_0715" in ids
    assert evaluate_triggers(p, mem, t, ids, tiny_cfg) == ("T6",)
    mem2 = standing(480)
    ids2 = [o.option_id for o in build_options(persona(), mem2, t, P3, tiny_cfg, False)]
    assert evaluate_triggers(persona(), mem2, t, ids2, tiny_cfg) == ()


def _prompt(p: Persona, cfg, t: TodayInfo) -> tuple[str, tuple]:
    m = new_memory(0)
    m.standing_depart_min = 465
    full = build_options(p, m, t, P3, cfg, False, wtt=False)
    opts = build_options(p, m, t, P3, cfg, False)
    ctx = DecisionContext(agent_id=0, day=t.day, persona=p, params=P3, options=opts, standing_option_id=None,
                          triggers=("T1",), discontinuity=True, recent=(), delay_ratio_ema=1.0, ref_fee=0.0,
                          today=t, wtt_removed=len(full) - len(opts))
    return llm.render_user_prompt(ctx, cfg), opts


def test_prompt_states_the_limit_only_when_driving_was_removed(tiny_cfg) -> None:
    some = ("- You would not pay more than NZ$5.00 a day to drive into the city centre, so driving at times "
            "when the charge is higher than that is not offered today.")
    text, opts = _prompt(persona(wtp_fee=5.0), tiny_cfg, today())
    assert some in text.splitlines()
    rows = [ln.split(" | ")[0] for ln in text.splitlines() if ln.startswith(("CAR_", "PT |", "WFH |"))]
    assert rows == [o.option_id for o in opts]                         # only the offered options
    assert llm.output_schema([o.option_id for o in opts])["properties"]["choice"]["enum"] == rows
    text_all, opts_all = _prompt(persona(wtp_fee=3.0), tiny_cfg, today())
    assert ("- You would not pay more than NZ$3.00 a day to drive into the city centre, and every time you "
            "could drive today is charged more than that, so driving is not offered today.") in text_all.splitlines()
    assert [o.option_id for o in opts_all] == ["PT"] and "| drive |" not in text_all
    for p, t in ((persona(wtp_fee=50.0), today()), (persona(wtp_fee=0.0), today(5, False)),
                 (persona(wtp_fee=0.0, company_car=True, parking_cost=0.0), today())):
        text, _ = _prompt(p, tiny_cfg, t)
        assert "would not pay more than" not in text


# --------------------------------------------------------------------------- tiny runs


@pytest.fixture
def data_dir(tmp_path: Path, tiny_origins: pd.DataFrame, tiny_corridors_prep: pd.DataFrame) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    tiny_origins.to_csv(d / "origins.csv", index=False)
    tiny_corridors_prep.to_csv(d / "corridors.csv", index=False)
    return d


def tiny(data_dir: Path, **ov: object):
    base = {"run.n_agents": 40, "run.n_days": 6, "fees.fee_start_day": 3, "persona.n_twins": 4,
            "events.pt_disruption_day": 5, "run.data_dir": str(data_dir), "run.seed": 3,
            "engine.use_calibration": False, "engine.capacity_scale": 0.5, "road.enabled": False}
    base.update(ov)
    return load_config(overrides=base)


def _read(d: Path) -> dict:
    return {"decisions": pd.read_csv(d / "decisions.csv"), "outcomes": pd.read_csv(d / "outcomes.csv"),
            "personas": pd.read_csv(d / "personas.csv"), "summary": json.loads((d / "summary.json").read_text()),
            "llm": (d / "llm_calls.jsonl").read_text(encoding="utf-8")}


@pytest.mark.parametrize("arm", ["R-clock", "L-daily"])
def test_run_with_beta0_zero_is_the_model_without_wtt(tmp_path: Path, data_dir: Path, arm: str,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """wtt.beta0 = 0: every WTP is infinite and nothing is removed, so the run equals one in which the
    willingness-to-pay rule is switched off altogether (outputs other than the persona's WTT columns)."""
    a = _read(R.run_simulation(tiny(data_dir, **{"run.arm": arm, "wtt.beta0": 0.0}), tmp_path / "a"))
    monkeypatch.setattr(R, "wtt_filter", lambda p, opts: tuple(opts))
    b = _read(R.run_simulation(tiny(data_dir, **{"run.arm": arm, "wtt.beta0": 2.0}), tmp_path / "b"))
    assert (a["personas"]["wtp_fee"] == math.inf).all() and (a["personas"]["wtt_beta"] == 0.0).all()
    assert (a["decisions"]["wtt_removed"] == 0).all() and not a["decisions"]["wtt_all_removed"].any()
    for k in ("decisions", "outcomes"):
        pd.testing.assert_frame_equal(a[k], b[k])
    assert a["summary"]["days"] == b["summary"]["days"] and a["llm"] == b["llm"]
    keep = [c for c in a["personas"].columns if c not in ("wtt_beta", "wtp_fee")]
    pd.testing.assert_frame_equal(a["personas"][keep], b["personas"][keep])


@pytest.mark.parametrize("arm", ["R-clock", "R-daily", "L-clock"])
def test_uncharged_days_do_not_depend_on_beta0_and_diagnostics(tmp_path: Path, data_dir: Path, arm: str) -> None:
    """Days before the charge are identical whatever beta0 is; on charged days a large beta0 removes car
    options (decisions.csv wtt_removed, wtt_all_removed; summary.json wtt_limited, wtt_no_car), never for a
    company car or a commuter without PT and WFH, and a commuter left without a car option does not drive.
    The clock arms run through (a standing car option that is removed wakes the agent: T6)."""
    runs = {b: _read(R.run_simulation(tiny(data_dir, **{"run.arm": arm, "wtt.beta0": b}), tmp_path / str(b)))
            for b in (0.0, 2.0)}
    for k in ("decisions", "outcomes"):
        x, y = (runs[b][k] for b in (0.0, 2.0))
        pd.testing.assert_frame_equal(x[x["day"] < 3].reset_index(drop=True), y[y["day"] < 3].reset_index(drop=True))
    assert runs[0.0]["summary"]["days"][:2] == runs[2.0]["summary"]["days"][:2]
    dec, per, s = runs[2.0]["decisions"], runs[2.0]["personas"].set_index("agent_id"), runs[2.0]["summary"]
    assert dec["wtt_removed"].dtype.kind == "i" and dec["wtt_all_removed"].dtype == bool
    hit = dec[dec["wtt_removed"] > 0]
    assert len(hit) > 0 and (hit["day"] >= 3).all()
    exempt = per.index[per["company_car"] | ~(per["pt_allowed"] | per["wfh_allowed"])]
    assert not dec["agent_id"].isin(exempt)[dec["wtt_removed"] > 0].any()
    assert (dec.loc[dec["wtt_all_removed"], "mode"] != "CAR").all() and (dec["wtt_removed"][dec["wtt_all_removed"]] > 0).all()
    assert [d["wtt_limited"] for d in s["days"]] == [int((g["wtt_removed"] > 0).sum()) for _, g in dec.groupby("day")]
    assert [d["wtt_no_car"] for d in s["days"]] == [int(g["wtt_all_removed"].sum()) for _, g in dec.groupby("day")]
    if arm.endswith("clock"):
        # an agent whose standing car departure was removed decided again (T6) instead of standing
        d = dec.sort_values(["agent_id", "day"]).reset_index(drop=True)
        d["prev"] = d.groupby("agent_id")["option_id"].shift()
        assert ((d["wtt_removed"] > 0) & (d["decider"] != "standing")).any()
        st = d[d["decider"] == "standing"]
        assert (st["option_id"] == st["prev"]).all()
        # a standing car departure that is not offered today wakes the agent (T6)
        assert ((d["wtt_removed"] > 0) & d["triggers"].fillna("").str.contains("T6")).any()
        assert not d.loc[d["triggers"].fillna("").str.contains("T6"), "decider"].eq("standing").any()
