"""Tests for prompt template cl-v2: the "you pay today" column and the main_factor / second_factor
reply with a factor enum narrowed per agent-day. No test calls the live API."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Callable

import pytest

from cordonlite import llm
from cordonlite.config import Config, ConfigError, load_config
from cordonlite.types import DecisionContext, Persona, TodayInfo
from tests.test_llm import FORBIDDEN, PROFILE, FakeFallback, make_ctx


@pytest.fixture
def v2_cfg() -> Config:
    return load_config(overrides={"run.n_agents": 20, "run.n_days": 6, "fees.fee_start_day": 3,
                                  "persona.n_twins": 4, "events.pt_disruption_day": 5,
                                  "llm.template_id": "cl-v2"})


@pytest.fixture
def ctxs(tiny_personas: list[Persona], make_today: Callable[..., TodayInfo]) -> list[DecisionContext]:
    today = make_today(6, fee_active=True, public_delay=PROFILE, fee_changed_today=True)
    return [make_ctx(p, today) for p in tiny_personas]


def _rows(text: str) -> tuple[list[str], dict[str, list[str]]]:
    lines = text.splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.startswith("option id |"))
    header = [c.strip() for c in lines[i].split("|")]
    rows = {}
    for ln in lines[i + 2:]:
        if not ln.strip():
            break
        cells = [c.strip() for c in ln.split("|")]   # the empty "usual" cell leaves a trailing "|"
        rows[cells[0]] = cells
    return header, rows


def test_config_accepts_both_templates_only() -> None:
    assert load_config().llm.template_id == "cl-v1"
    assert load_config(overrides={"llm.template_id": "cl-v2"}).llm.template_id == "cl-v2"
    with pytest.raises(ConfigError):
        load_config(overrides={"llm.template_id": "cl-v3"})


def test_v1_prompt_and_schema_unchanged(ctxs: list[DecisionContext], tiny_cfg: Config) -> None:
    text = llm.render_user_prompt(ctxs[0], tiny_cfg)
    assert "you pay today" not in text.lower()
    assert llm.system_prompt(tiny_cfg) == llm.SYSTEM_PROMPT
    assert set(llm.output_schema(ctxs[0].option_ids)["properties"]) == {"choice", "factors", "reason"}


def test_v2_total_column(ctxs: list[DecisionContext], v2_cfg: Config) -> None:
    for c in ctxs:
        header, rows = _rows(llm.render_user_prompt(c, v2_cfg))
        assert header[-2:] == ["you pay today", "usual"]
        k = header.index("you pay today")
        for o in c.options:
            cell = rows[o.option_id][k]
            if o.mode == "CAR":
                fee = 0.0 if c.persona.company_car else o.fee
                assert cell == f"NZ${fee + o.parking + o.fuel:.2f}"
            elif o.mode == "PT":
                assert cell == f"NZ${o.pt_fare:.2f}"
            elif o.mode == "WFH":
                assert cell == "NZ$0.00"
            else:
                assert cell == "-"
    assert "does not count your time" in llm.render_user_prompt(ctxs[0], v2_cfg)


def test_v2_company_car_pays_nothing(tiny_personas: list[Persona], v2_cfg: Config,
                                     make_today: Callable[..., TodayInfo]) -> None:
    p = next(x for x in tiny_personas if x.company_car)
    header, rows = _rows(llm.render_user_prompt(make_ctx(p, make_today(6)), v2_cfg))
    car = next(v for k, v in rows.items() if k.startswith("CAR_"))
    assert "employer pays" in car[header.index("road charge")]
    assert car[header.index("you pay today")] == "NZ$0.00"


def test_v2_prompts_avoid_trait_and_archetype_words(ctxs: list[DecisionContext], v2_cfg: Config) -> None:
    for c in ctxs:
        text = (llm.system_prompt(v2_cfg) + "\n" + llm.render_user_prompt(c, v2_cfg)).lower()
        words = set(re.findall(r"[a-z\-]+", text))
        for w in FORBIDDEN:
            assert (w not in text) if " " in w else (w not in words), (c.agent_id, w)
    for tag in llm.FACTORS_V2:
        assert f"- {tag}:" in llm.system_prompt(v2_cfg)


def test_v2_schema_shape(ctxs: list[DecisionContext]) -> None:
    c = ctxs[0]
    f = llm.factor_ids(c)
    s = llm.output_schema(c.option_ids, f)
    assert list(s["properties"]) == ["reason", "main_factor", "second_factor", "choice"]
    assert s["properties"]["main_factor"]["enum"] == list(f)
    assert s["properties"]["second_factor"]["enum"] == list(f) + ["none"]
    assert s["properties"]["choice"]["enum"] == list(c.option_ids)
    assert sorted(s["required"]) == ["choice", "main_factor", "reason", "second_factor"]
    assert s["additionalProperties"] is False


def test_v2_factors_narrowed_to_the_day(tiny_personas: list[Persona],
                                        make_today: Callable[..., TodayInfo]) -> None:
    p = next(x for x in tiny_personas if x.pt_allowed)
    first_day = make_ctx(p, make_today(1, fee_active=False), standing=None, recent=())
    f = llm.factor_ids(first_day)
    for absent in ("road_charge", "routine", "past_experience", "disruption"):
        assert absent not in f
    assert {"other_money", "travel_time", "arrival_time", "bus_train_preference", "flexibility",
            "constraint", "other"} <= set(f)

    charged = make_ctx(p, make_today(6, fee_active=True, fee_changed_today=True))
    f = llm.factor_ids(charged)
    assert {"road_charge", "routine", "past_experience"} <= set(f) and "disruption" not in f

    disrupted = make_ctx(p, make_today(5, fee_active=False, disrupted=[p.corridor_id]), standing="PT")
    assert "disruption" in llm.factor_ids(disrupted) and "road_charge" not in llm.factor_ids(disrupted)
    woken_after = replace(charged, triggers=("T4",))
    assert "disruption" in llm.factor_ids(woken_after)

    no_pt = next(x for x in tiny_personas if not x.pt_allowed)
    assert "bus_train_preference" not in llm.factor_ids(make_ctx(no_pt, make_today(6)))
    assert all(t in llm.FACTORS_V2 for t in f) and list(f) == [t for t in llm.FACTORS_V2 if t in f]


@pytest.mark.parametrize("obj,ok", [
    ({"choice": "PT", "reason": "x", "main_factor": "road_charge", "second_factor": "none"}, True),
    ({"choice": "PT", "reason": "x", "main_factor": "road_charge", "second_factor": "other_money"}, True),
    ({"choice": "PT", "reason": "x", "main_factor": "disruption", "second_factor": "none"}, False),
    ({"choice": "PT", "reason": "x", "main_factor": "road_charge", "second_factor": "disruption"}, False),
    ({"choice": "PT", "reason": "x", "main_factor": "none", "second_factor": "none"}, False),
    ({"choice": "CAR_0900", "reason": "x", "main_factor": "road_charge", "second_factor": "none"}, False),
    ({"choice": "PT", "reason": " ", "main_factor": "road_charge", "second_factor": "none"}, False),
    ({"choice": "PT", "reason": "x", "main_factor": "road_charge"}, False),
    ({"choice": "PT", "reason": "x", "factors": ["fee"]}, False),
    (None, False),
])
def test_v2_validate_output(obj: object, ok: bool) -> None:
    offered = ["road_charge", "other_money", "travel_time", "other"]
    assert llm.validate_output(obj, ["CAR_0730", "PT", "SKIP"], offered)[0] is ok


def test_reply_factors() -> None:
    assert llm.reply_factors({"main_factor": "road_charge", "second_factor": "none"}) == ("road_charge",)
    assert llm.reply_factors({"main_factor": "road_charge", "second_factor": "road_charge"}) == ("road_charge",)
    assert llm.reply_factors({"main_factor": "routine", "second_factor": "other_money"}) == ("routine", "other_money")
    assert llm.reply_factors({"factors": ["fee", "pt"]}) == ("fee", "pt")
    assert set(llm.FACTOR_V2_TO_V1) == set(llm.FACTORS_V2)


def test_v2_mock_decider_end_to_end(ctxs: list[DecisionContext], v2_cfg: Config, tmp_path: Path) -> None:
    d = llm.make_llm_decider(v2_cfg, tmp_path, FakeFallback(), backend="mock")
    dec = d.decide_batch(ctxs)
    d.close()
    recs = [json.loads(x) for x in (tmp_path / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(dec) == len(ctxs) == len(recs)
    for c, x, r in zip(ctxs, dec, recs):
        assert x.decider == "llm" and x.option_id in c.option_ids
        assert r["template_id"] == "cl-v2" and r["valid"] is True
        assert r["schema_factor_ids"] == list(llm.factor_ids(c))
        assert set(r["parsed"]) == {"reason", "main_factor", "second_factor", "choice"}
        assert 1 <= len(x.factors) <= 2 and set(x.factors) <= set(r["schema_factor_ids"])


def test_v2_and_v1_use_different_cache_keys(ctxs: list[DecisionContext], tiny_cfg: Config,
                                            v2_cfg: Config) -> None:
    c = ctxs[0]
    k1 = llm.cache_key("m", "low", "cl-v1", llm.system_prompt(tiny_cfg), llm.render_user_prompt(c, tiny_cfg),
                       llm.output_schema(c.option_ids))
    k2 = llm.cache_key("m", "low", "cl-v2", llm.system_prompt(v2_cfg), llm.render_user_prompt(c, v2_cfg),
                       llm.output_schema(c.option_ids, llm.factor_ids(c)))
    assert k1 != k2
