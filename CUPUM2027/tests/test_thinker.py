"""Tests for cordonlite.thinker (arm H-clock, template think-v1): the model runs the routine, the LLM
is the commuter stopping to think. No test calls the live API (ThinkMock only)."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Callable

import pytest

from cordonlite import planner as P
from cordonlite import thinker as T
from cordonlite.config import TEMPLATE_IDS, Config
from cordonlite.run import simulate
from cordonlite.types import DecisionContext, Persona, TodayInfo
from tests.test_llm import FORBIDDEN, PROFILE, FakeFallback, make_ctx


@pytest.fixture
def cfg(tiny_cfg: Config) -> Config:
    return replace(tiny_cfg, llm=replace(tiny_cfg.llm, template_id=T.THINK_TEMPLATE_ID))


@pytest.fixture
def ctxs(tiny_personas: list[Persona], make_today: Callable[..., TodayInfo]) -> list[DecisionContext]:
    today = make_today(6, fee_active=True, public_delay=PROFILE, fee_changed_today=True)
    return [make_ctx(p, today) for p in tiny_personas]


def _offers(c: DecisionContext, plan: P.Plan, why: str) -> dict:
    g = P.by_strategy(c.options)
    return T.change_offers(c, plan, g, lambda s: P.HybridDecider._pick(c, g[s]), why)


def _plan_for(c: DecisionContext) -> P.Plan:
    o = c.option(c.standing_option_id)
    return P.Plan(usual=P.strategy_of(o), made_on=1, slots={P.strategy_of(o): o.option_id})


def test_template_is_registered_and_dispatched(cfg: Config, tmp_path: Path) -> None:
    assert T.THINK_TEMPLATE_ID in TEMPLATE_IDS
    d = P.make_hybrid_decider(cfg, tmp_path, FakeFallback(), backend="mock")
    assert isinstance(d, T.ThinkDecider)
    d.close()


def test_first_day_is_the_base_rule_and_the_routine_repeats(ctxs: list[DecisionContext], cfg: Config,
                                                            tmp_path: Path,
                                                            make_today: Callable[..., TodayInfo]) -> None:
    rule = FakeFallback()
    d = P.make_hybrid_decider(cfg, tmp_path, rule, backend="mock")
    first = d.decide_batch(ctxs)
    assert [x.decider for x in first] == ["rule"] * len(ctxs)
    assert rule.calls == [c.agent_id for c in ctxs] and d.stats["n_contexts"] == 0
    # a first day of staying at home is not a routine: the rule is asked again the next morning
    settled = {x.agent_id for x in first if x.option_id != "SKIP"}
    assert set(d.plans) == settled and settled
    quiet = make_today(7, fee_active=True, public_delay=PROFILE)
    nxt = [replace(make_ctx(c.persona, quiet, standing=x.option_id), triggers=()) for c, x in zip(ctxs, first)]
    second = d.decide_batch(nxt)
    d.close()
    assert d.stats["n_contexts"] == 0
    for x, y in zip(first, second):
        if x.agent_id in settled:
            assert y.decider == "standing" and y.option_id == x.option_id
        else:
            assert y.decider == "rule"
    # a single late day or a T5 wake does not move the departure and does not ask the LLM
    log = [json.loads(x) for x in (tmp_path / "plan_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["handler"] for r in log} == {"base", "plan"}


def test_the_charge_asks_only_drivers_who_pay(ctxs: list[DecisionContext], cfg: Config, tmp_path: Path) -> None:
    d = P.make_hybrid_decider(cfg, tmp_path, FakeFallback(), backend="mock")
    for c in ctxs:
        d.plans[c.agent_id] = _plan_for(c)
    out = d.decide_batch(ctxs)
    d.close()
    for c, x in zip(ctxs, out):
        asked = d.plans[c.agent_id].made_on == c.day
        assert asked == (not c.persona.company_car) and x.decider == ("llm" if asked else "standing")
        assert x.option_id in c.option_ids


def test_offers_and_schema(ctxs: list[DecisionContext], cfg: Config) -> None:
    for c in ctxs:
        plan = _plan_for(c)
        offers = _offers(c, plan, "charge")
        assert next(iter(offers)) == T.KEEP and offers[T.KEEP].option_id == c.standing_option_id
        if T.OTHER_TIME in offers:
            assert offers[T.OTHER_TIME].mode == "CAR" and offers[T.OTHER_TIME].fee < offers[T.KEEP].fee
        s = T.think_schema("change", offers, c)
        assert s["properties"]["what_i_do"]["enum"] == list(offers)
        assert s["properties"]["second_choice"]["enum"] == list(offers) + ["none"]
        assert s["required"] == list(s["properties"]) and s["additionalProperties"] is False
        assert next(iter(s["properties"])) == "in_my_words"
        mock = T.ThinkMock(cfg)
        mock.offers[(c.agent_id, c.day)] = offers
        good = mock.complete(T.THINK_SYSTEM, "u", s, c)
        assert P.validate_reply(good, s) == (True, "")
        assert not P.validate_reply({**good, "what_i_do": "teleport"}, s)[0]
        assert not P.validate_reply({**good, "trying_it_out_for_days": 7}, s)[0]
        g = P.by_strategy(c.options)
        today = T.today_offers(g, lambda k: P.HybridDecider._pick(c, g[k]))
        assert set(T.think_schema("today", today, c)["properties"]) == {
            "in_my_words", "what_i_do_today", "same_whenever_disrupted", "main_reason", "second_reason"}


def test_messages(ctxs: list[DecisionContext], cfg: Config, capsys: pytest.CaptureFixture) -> None:
    for c in ctxs:
        plan = _plan_for(c)
        texts = {"charge": T.render_think_prompt(c, "change", _offers(c, plan, "charge"), plan, "charge", cfg)}
        mixed = replace(plan, other="work_from_home", other_days=1, review_day=6, made_on=1,
                        words="I will see how it goes.")
        g = P.by_strategy(c.options)
        if "work_from_home" in g:
            texts["review"] = T.render_think_prompt(c, "change", _offers(c, mixed, "review"), mixed, "review", cfg)
            assert "you have had a mixed week" in texts["review"] and "as your main way" in texts["review"]
            assert "- The 5 days you gave yourself to try this are up." in texts["review"]
            assert "you said: \"I will see how it goes.\"" in texts["review"]
        noted = T.render_think_prompt(c, "change", _offers(c, plan, "late"), plan, "late", cfg,
                                      notes=((c.day - 1, "drive"), (c.day - 40, "work_from_home")))
        assert f"- On day {c.day - 1} buses and trains from your area were disrupted, and you drove in that day." in noted
        assert f"On day {c.day - 40}" not in noted      # only days inside the recent window are recalled
        texts["late"] = T.render_think_prompt(c, "change", _offers(c, plan, "late"), plan, "late", cfg)
        texts["trip"] = T.render_think_prompt(c, "change", _offers(c, plan, "trip"), plan, "trip", cfg)
        texts["today"] = T.render_think_prompt(
            c, "today", T.today_offers(g, lambda k: P.HybridDecider._pick(c, g[k])), plan, "disruption", cfg)
        assert "WHAT IS NEW" in texts["charge"] and "From today there is a charge" in texts["charge"]
        assert "WHY YOU ARE THINKING ABOUT THIS AGAIN" in texts["late"]
        assert "WHAT YOU COULD DO THIS MORNING" in texts["today"]
        for name, text in texts.items():
            for head in ("WHO YOU ARE", "WHAT YOU HAVE BEEN DOING", "WHAT YOU COULD DO"):
                assert head in text, (c.agent_id, name, head)
            low = (T.THINK_SYSTEM + "\n" + text).lower()
            words = set(re.findall(r"[a-z\-]+", low))
            for w in FORBIDDEN:
                assert (w not in low) if " " in w else (w not in words), (c.agent_id, name, w)
            assert "123.45" not in text                 # the generalised cost is never shown
            for o in c.options:
                assert f"{o.gc:.2f}" not in text
            assert "a week" not in text.replace("days a week", "") or name == "review"   # no weekly sums
        if c.agent_id == ctxs[0].agent_id:
            with capsys.disabled():
                for name, text in texts.items():
                    print(f"\n######## {name} (commuter {c.agent_id})\n{text}")


def test_full_run_with_the_stand_in(cfg: Config, tiny_origins, tiny_corridors_prep, tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    import cordonlite.run as run_mod

    monkeypatch.setattr(run_mod, "load_prep", lambda c: (tiny_origins, tiny_corridors_prep))
    base = replace(cfg, run=replace(cfg.run, arm="R-clock", backend="mock"))
    think = replace(cfg, run=replace(cfg.run, arm="H-clock", backend="mock"))
    a = simulate(base, tmp_path / "base", 1.0)
    b = simulate(think, tmp_path / "think", 1.0)
    assert len(b.decisions) == think.run.n_agents * think.run.n_days
    day1 = lambda res: [(r["agent_id"], r["option_id"], r["decider"]) for r in res.decisions if r["day"] == 1]
    assert day1(a) == day1(b)                           # the first day is the base model's
    assert all(r["decider"] != "llm" for r in b.decisions if r["day"] == 1)
    assert sum(d["calls"]["llm"] for d in b.days) < len(b.decisions) / 4
