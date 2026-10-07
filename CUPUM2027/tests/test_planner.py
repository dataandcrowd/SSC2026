"""Tests for cordonlite.planner (arm H-clock): the LLM plans, the model chooses the minute.
No test calls the live API (PlanMock only)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Callable

import pytest

from cordonlite import planner as P
from cordonlite.config import ARMS, Config, load_config
from cordonlite.run import simulate
from cordonlite.types import DecisionContext, Persona, TodayInfo
from tests.test_llm import FORBIDDEN, PROFILE, FakeFallback, make_ctx


@pytest.fixture
def ctxs(tiny_personas: list[Persona], make_today: Callable[..., TodayInfo]) -> list[DecisionContext]:
    today = make_today(6, fee_active=True, public_delay=PROFILE, fee_changed_today=True)
    return [make_ctx(p, today) for p in tiny_personas]


def test_arm_is_registered() -> None:
    assert "H-clock" in ARMS


def test_strategies_cover_every_option(ctxs: list[DecisionContext]) -> None:
    for c in ctxs:
        g = P.by_strategy(c.options)
        assert sum(len(v) for v in g.values()) == len(c.options)
        assert list(g) == [s for s in P.STRATEGIES if s in g]
        assert all(P.strategy_of(o) == s for s, opts in g.items() for o in opts)


def test_weekly_pattern() -> None:
    plan = P.Plan(usual="drive", other="bus_or_train", other_days=2)
    week = [P.strategy_on(plan, d) for d in range(1, 11)]
    assert week[:5] == week[5:] and week.count("bus_or_train") == 4
    assert all(P.strategy_on(P.Plan(usual="drive"), d) == "drive" for d in range(1, 11))
    for k, days in P.OTHER_DAYS.items():
        assert len(days) == k


def test_model_picks_lowest_cost_and_never_late_for_a_firm_start(ctxs: list[DecisionContext]) -> None:
    for c in ctxs:
        cars = P.by_strategy(c.options)["drive"]
        o = P.HybridDecider._pick(c, cars)
        if c.persona.sched_mult >= 1.0 and any(x.late_min <= 0 for x in cars):
            assert o.late_min <= 0
            assert o.gc == min(x.gc for x in cars if x.late_min <= 0)
        else:
            assert o.gc == min(x.gc for x in cars)


def test_prompt_and_schema(ctxs: list[DecisionContext], tiny_cfg: Config) -> None:
    import re

    for c in ctxs:
        picks = {s: P.HybridDecider._pick(c, opts) for s, opts in P.by_strategy(c.options).items()
                 if s in P.PLAN_STRATEGIES}
        first = P.render_plan_prompt(c, "routine", picks, None, "", tiny_cfg)
        assert "WHAT YOU DO NOW" not in first and "you pay each week" in first
        plan = P.Plan(usual="drive", made_on=1, words="I drive.")
        change = P.render_plan_prompt(c, "change", picks, plan, "charge", tiny_cfg)
        assert "WHAT YOU DO NOW" in change and "each week, compared with now" in change
        assert "When you settled on this (day 1) you said: \"I drive.\"" in change
        for text in (first, change):
            low = (P.PLAN_SYSTEM + "\n" + text).lower()
            words = set(re.findall(r"[a-z\-]+", low))
            for w in FORBIDDEN:
                assert (w not in low) if " " in w else (w not in words), (c.agent_id, w)
            assert "123.45" not in text                 # the generalised cost is never shown
            for s in picks:
                assert f"\n{s} | " in text
        s = P.plan_schema("change", picks, c)
        assert s["properties"]["usual_choice"]["enum"] == list(picks)
        assert s["properties"]["other_choice"]["enum"] == list(picks) + ["none"]
        assert s["required"] == list(s["properties"]) and s["additionalProperties"] is False
        today = P.plan_schema("today", dict(picks), c)
        assert set(today["properties"]) == {"in_their_words", "today_choice", "add_to_plan",
                                            "main_factor", "second_factor"}


def test_validate_reply(ctxs: list[DecisionContext], tiny_cfg: Config) -> None:
    c = ctxs[0]
    picks = {s: opts[0] for s, opts in P.by_strategy(c.options).items() if s in P.PLAN_STRATEGIES}
    schema = P.plan_schema("routine", picks, c)
    good = P.PlanMock(tiny_cfg).complete(P.PLAN_SYSTEM, "u", schema, c)
    assert P.validate_reply(good, schema) == (True, "")
    assert not P.validate_reply({**good, "usual_choice": "teleport"}, schema)[0]
    assert not P.validate_reply({**good, "days_per_week_on_other": 7}, schema)[0]
    assert not P.validate_reply({**good, "trying_it_out": "yes"}, schema)[0]
    assert not P.validate_reply({**good, "would_reconsider_if": ["mood"]}, schema)[0]
    assert not P.validate_reply({**good, "in_their_words": " "}, schema)[0]
    assert not P.validate_reply({k: v for k, v in good.items() if k != "how_settled"}, schema)[0]


def test_decider_day_one_then_plan(ctxs: list[DecisionContext], tiny_cfg: Config, tmp_path: Path,
                                   make_today: Callable[..., TodayInfo]) -> None:
    d = P.make_hybrid_decider(tiny_cfg, tmp_path, FakeFallback(), backend="mock")
    first = d.decide_batch(ctxs)
    assert [x.agent_id for x in first] == [c.agent_id for c in ctxs]
    assert all(x.decider == "llm" and x.option_id in c.option_ids for x, c in zip(first, ctxs))
    assert set(d.plans) == {c.agent_id for c in ctxs}
    # next day, nothing happens: everyone follows the plan with the same departure, and no call is made
    quiet = make_today(7, fee_active=True, public_delay=PROFILE)
    nxt = [replace(make_ctx(c.persona, quiet), triggers=()) for c in ctxs]
    calls = d.stats["n_contexts"]
    second = d.decide_batch(nxt)
    d.close()
    assert d.stats["n_contexts"] == calls
    assert all(x.decider == "standing" for x in second)
    assert [x.option_id for x in second] == [x.option_id for x in first]
    log = [json.loads(x) for x in (tmp_path / "plan_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(log) == 2 * len(ctxs) and {r["handler"] for r in log} == {"routine", "plan"}


def test_full_run_with_the_stand_in(tiny_cfg: Config, tiny_origins, tiny_corridors_prep, tmp_path: Path,
                                    monkeypatch: pytest.MonkeyPatch) -> None:
    import cordonlite.run as run_mod

    monkeypatch.setattr(run_mod, "load_prep", lambda cfg: (tiny_origins, tiny_corridors_prep))
    cfg = replace(tiny_cfg, run=replace(tiny_cfg.run, arm="H-clock", backend="mock"))
    res = simulate(cfg, tmp_path, 1.0)
    assert len(res.decisions) == cfg.run.n_agents * cfg.run.n_days
    day1 = [r for r in res.decisions if r["day"] == 1]
    assert all(r["decider"] == "llm" for r in day1)
    assert sum(d["calls"]["llm"] for d in res.days) < len(res.decisions) / 2
