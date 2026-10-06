"""Tests for cordonlite.llm: prompt, schema, validation, MockLLM, AnthropicLLM (fake client), cache.

No test calls the live API: AnthropicLLM always gets a fake client object.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Sequence

import anthropic
import httpx2
import pytest

from cordonlite import llm
from cordonlite import persona as persona_mod
from cordonlite.config import Config, load_config
from cordonlite.types import (
    FACTORS,
    Decision,
    DecisionContext,
    MemoryRecord,
    Option,
    Persona,
    TodayInfo,
    TraitParams,
    option_id_for,
)

_V3_SENTENCES = {
    "H": ("H1 sentence.", "H2 sentence.", "H3 sentence.", "H4 sentence.", "H5 sentence."),
    "F": ("F1 sentence.", "F2 sentence.", "F3 sentence.", "F4 sentence.", "F5 sentence."),
    "P": ("P1 sentence.", "P2 sentence.", "P3 sentence.", "P4 sentence.", "P5 sentence."),
    "S": ("S1 sentence.", "S2 sentence.", "S3 sentence.", "S4 sentence.", "S5 sentence."),
}


@pytest.fixture(autouse=True)
def _dispositions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use persona.disposition_sentences when implemented, else a stand-in."""
    if not hasattr(persona_mod, "disposition_sentences"):
        def stub(p: Persona) -> tuple[str, str, str, str]:
            return tuple(_V3_SENTENCES[t][getattr(p, t) - 1] for t in "HFPS")  # type: ignore[return-value]
        monkeypatch.setattr(persona_mod, "disposition_sentences", stub, raising=False)


# ------------------------------------------------------------------------------------------
# Context builders (independent of options.py so the tests do not depend on its progress)
# ------------------------------------------------------------------------------------------

def make_options(p: Persona, today: TodayInfo, standing: str | None,
                 departs: Sequence[int] = (420, 435, 450, 465, 480)) -> tuple[Option, ...]:
    a = p.vot / 60.0
    out: list[Option] = []
    for d in departs:
        g = d + p.fftt_to_gate_min
        delay = 2.0 + 0.1 * (d - 420)
        x = g + int(round(delay))
        arr = x + p.fftt_gate_to_dest_min
        early, late = max(0, p.tstar_min - arr), max(0, arr - p.tstar_min)
        fee = today.fee_by_minute[x] if today.fee_active else 0.0
        oid = option_id_for("CAR", d)
        parts = {"time": round(a * (p.fftt_total_min + delay), 4),
                 "schedule": round(a * (0.61 * early + 2.38 * late), 4),
                 "fee": 0.0 if p.company_car else fee, "parking": p.parking_cost,
                 "habit": 0.0 if oid == standing else 1.5}
        out.append(Option(
            option_id=oid, mode="CAR", depart_min=d, expected_gate_arrive_min=g,
            expected_delay_min=delay, expected_gate_exit_min=x,
            expected_travel_min=float(p.fftt_total_min + delay), expected_arrive_min=arr,
            early_min=float(early), late_min=float(late), fee=fee, parking=p.parking_cost,
            pt_time_min=None, pt_fare=None, is_standing=oid == standing,
            gc=round(sum(parts.values()), 4) + 123.4567, gc_parts=parts))
    if p.pt_allowed:
        mult = today.pt_disruption_time_mult if p.corridor_id in today.pt_disrupted_corridors else 1.0
        t = p.pt_time_min * mult
        parts = {"pt": round(a * t + p.pt_fare, 4), "habit": 0.0 if standing == "PT" else 1.5}
        out.append(Option(
            option_id="PT", mode="PT", depart_min=int(p.tstar_min - round(t)),
            expected_gate_arrive_min=None, expected_delay_min=None, expected_gate_exit_min=None,
            expected_travel_min=t, expected_arrive_min=p.tstar_min, early_min=0.0, late_min=0.0,
            fee=0.0, parking=0.0, pt_time_min=t, pt_fare=p.pt_fare, is_standing=standing == "PT",
            gc=sum(parts.values()) + 123.4567, gc_parts=parts))
    if p.wfh_allowed:
        parts = {"wfh": 8.0, "habit": 0.0 if standing == "WFH" else 1.5}
        out.append(Option(
            option_id="WFH", mode="WFH", depart_min=None, expected_gate_arrive_min=None,
            expected_delay_min=None, expected_gate_exit_min=None, expected_travel_min=0.0,
            expected_arrive_min=None, early_min=0.0, late_min=0.0, fee=0.0, parking=0.0,
            pt_time_min=None, pt_fare=None, is_standing=standing == "WFH",
            gc=sum(parts.values()) + 123.4567, gc_parts=parts))
    parts = {"skip": 25.0, "habit": 0.0 if standing == "SKIP" else 1.5}
    out.append(Option(
        option_id="SKIP", mode="SKIP", depart_min=None, expected_gate_arrive_min=None,
        expected_delay_min=None, expected_gate_exit_min=None, expected_travel_min=0.0,
        expected_arrive_min=None, early_min=0.0, late_min=0.0, fee=0.0, parking=0.0,
        pt_time_min=None, pt_fare=None, is_standing=standing == "SKIP",
        gc=sum(parts.values()) + 123.4567, gc_parts=parts))
    return tuple(out)


def make_recent(p: Persona, upto_day: int) -> tuple[MemoryRecord, ...]:
    recs = []
    for d in range(max(1, upto_day - 4), upto_day + 1):
        mode = "PT" if (d == upto_day - 2 and p.pt_allowed) else "CAR"
        q = 3.0 + d if mode == "CAR" else None
        travel = (p.fftt_total_min + (q or 0)) if mode == "CAR" else p.pt_time_min
        arr = 450 + p.fftt_total_min + int(q or 0)
        recs.append(MemoryRecord(
            day=d, option_id="CAR_0730" if mode == "CAR" else "PT", mode=mode,
            depart_min=450, queue_delay_min=q, expected_delay_min=3.0 if mode == "CAR" else None,
            expected_travel_min=float(p.fftt_total_min + 3) if mode == "CAR" else None,
            travel_min=float(travel), arrive_min=arr,
            early_min=float(max(0, p.tstar_min - arr)), late_min=float(max(0, arr - p.tstar_min)),
            fee_paid=6.0 if (mode == "CAR" and d >= 3) else 0.0, pt_disrupted=False,
            decider="standing", triggers=(), reason=""))
    return tuple(recs)


def make_ctx(p: Persona, today: TodayInfo, standing: str | None = "CAR_0730",
             traits_shown: bool = True, recent: tuple[MemoryRecord, ...] | None = None) -> DecisionContext:
    return DecisionContext(
        agent_id=p.agent_id, day=today.day, persona=p,
        params=TraitParams(kappa_h=1.5, phi=1.0, omega=1.0, eta=0.5),
        options=make_options(p, today, standing), standing_option_id=standing,
        triggers=("T2",), discontinuity=True,
        recent=make_recent(p, today.day - 1) if recent is None else recent,
        delay_ratio_ema=1.0, ref_fee=0.0, today=today, traits_shown=traits_shown)


PROFILE = {0: ((440.0, 1.0), (460.0, 4.0), (480.0, 6.0)), 1: (), 2: ((450.0, 2.0),)}


@pytest.fixture
def ctxs(tiny_personas: list[Persona], make_today: Callable[..., TodayInfo]) -> list[DecisionContext]:
    today = make_today(6, fee_active=True, public_delay=PROFILE, fee_changed_today=True)
    return [make_ctx(p, today) for p in tiny_personas]


class FakeFallback:
    """Stand-in for RuleDecider: argmin GC."""

    name = "rule"

    def __init__(self) -> None:
        self.calls: list[int] = []

    def decide_batch(self, contexts: Sequence[DecisionContext]) -> list[Decision]:
        out = []
        for c in contexts:
            self.calls.append(c.agent_id)
            o = min(c.options, key=lambda o: o.gc)
            out.append(Decision(agent_id=c.agent_id, day=c.day, option_id=o.option_id,
                                decider="rule", reason="rule", factors=("other",),
                                meta={"gc": o.gc}))
        return out


# ------------------------------------------------------------------------------------------
# Prompt
# ------------------------------------------------------------------------------------------

FORBIDDEN = ["archetype", "hybrid", "on-site", "onsite", "shift", "trades", "tradesperson",
             "tertiary", "student", "service worker", "generalised cost", "gc", "kappa", "omega",
             "phi", "eta", "habit", "salience", "vot", "quintile", "trait"]


def test_prompt_has_no_archetype_label_gc_or_trait_names(ctxs: list[DecisionContext],
                                                         tiny_cfg: Config) -> None:
    import re

    for c in ctxs:
        text = (llm.SYSTEM_PROMPT + "\n" + llm.render_user_prompt(c, tiny_cfg)).lower()
        words = set(re.findall(r"[a-z\-]+", text))
        for w in FORBIDDEN:
            if " " in w:
                assert w not in text, (c.agent_id, w)
            else:
                assert w not in words, (c.agent_id, w)
        assert "123.45" not in text  # GC offset never rendered
        for o in c.options:
            assert f"{o.gc:.2f}" not in text
        assert f"archetype {c.persona.archetype}" not in text
        assert not re.search(r"\b[hfps]\s*=\s*\d", text)


def test_prompt_byte_stable_and_complete(ctxs: list[DecisionContext], tiny_cfg: Config,
                                         tiny_personas: list[Persona],
                                         make_today: Callable[..., TodayInfo]) -> None:
    c = ctxs[0]
    a = llm.render_user_prompt(c, tiny_cfg)
    # rebuild everything from scratch: identical bytes
    today = make_today(6, fee_active=True, public_delay=dict(PROFILE), fee_changed_today=True)
    b = llm.render_user_prompt(make_ctx(tiny_personas[0], today), tiny_cfg)
    assert a.encode() == b.encode()
    assert llm.prompt_sha256(llm.SYSTEM_PROMPT, a) == llm.prompt_sha256(llm.SYSTEM_PROMPT, b)
    for oid in c.option_ids:
        assert f"\n{oid} | " in a
    for header in ("ABOUT YOUR SITUATION", "HOW YOU TEND TO DECIDE", "YOUR RECENT DAYS",
                   "TODAY", "OPTIONS"):
        assert header in a
    for s in persona_mod.disposition_sentences(c.persona):
        assert s in a
    assert "starts today" in a
    assert "Yesterday's queue at your entry point" in a


def test_prompt_traits_off_shows_level3_or_omits(ctxs: list[DecisionContext], tiny_cfg: Config) -> None:
    """traits off: the level-3 sentences by default (matching the rule's level-3 parameters),
    no disposition section with llm.traits_off_prompt = "omit" (v3 neutral cell)."""
    from dataclasses import replace

    lv = tiny_cfg.traits.off_level
    c = replace(ctxs[3], traits_shown=False, persona=replace(ctxs[3].persona, H=lv, F=lv, P=lv, S=lv))
    text = llm.render_user_prompt(c, tiny_cfg)
    assert "HOW YOU TEND TO DECIDE" in text
    for t in "HFPS":
        assert persona_mod.TRAIT_SENTENCES[t][lv - 1] in text
    omit = load_config(overrides={"llm.traits_off_prompt": "omit", "run.n_agents": 20})
    text2 = llm.render_user_prompt(c, omit)
    assert "HOW YOU TEND TO DECIDE" not in text2
    for s in persona_mod.disposition_sentences(c.persona):
        assert s not in text2


def test_prompt_neutral_constraints_and_graded_flexibility(ctxs: list[DecisionContext],
                                                           tiny_cfg: Config) -> None:
    from dataclasses import replace

    texts = {m: llm.render_user_prompt(replace(ctxs[0], persona=replace(ctxs[0].persona, sched_mult=m,
                                                                         activity=act)), tiny_cfg)
             for m, act in ((0.5, "study"), (0.75, "work"), (1.0, "work"), (1.5, "work"))}
    assert len({llm.flexibility_sentence(m) for m in texts}) == 4
    for m, t in texts.items():
        assert llm.flexibility_sentence(m) in t
        for cue in ("study", "class", "workplace"):
            assert cue not in t.lower()


def test_prompt_twins_differ_only_in_dispositions(tiny_personas: list[Persona], tiny_cfg: Config,
                                                  make_today: Callable[..., TodayInfo]) -> None:
    from dataclasses import replace

    p = tiny_personas[2]
    q = replace(p, agent_id=99, H=(p.H % 5) + 1, F=(p.F % 5) + 1, P=(p.P % 5) + 1, S=(p.S % 5) + 1)
    today = make_today(6, fee_active=True, public_delay=PROFILE)
    a = llm.render_user_prompt(make_ctx(p, today, recent=()), tiny_cfg).splitlines()
    b = llm.render_user_prompt(make_ctx(q, today, recent=()), tiny_cfg).splitlines()
    diff = [(x, y) for x, y in zip(a, b) if x != y]
    assert len(a) == len(b) and len(diff) == 4


def test_prompt_disruption_and_no_charge(tiny_personas: list[Persona], tiny_cfg: Config,
                                         make_today: Callable[..., TodayInfo]) -> None:
    p = next(x for x in tiny_personas if x.pt_allowed)
    today = make_today(5, fee_active=False, disrupted=[p.corridor_id])
    text = llm.render_user_prompt(make_ctx(p, today, standing="PT"), tiny_cfg)
    assert "disrupted today" in text and "2 times as long" in text
    assert "no charge" in text
    assert "No information on yesterday's queues" in text


def test_company_car_prompt_mentions_employer(tiny_personas: list[Persona], tiny_cfg: Config,
                                              make_today: Callable[..., TodayInfo]) -> None:
    p = next(x for x in tiny_personas if x.company_car)
    text = llm.render_user_prompt(make_ctx(p, make_today(6)), tiny_cfg)
    assert "employer pays" in text
    assert "bus or train is not an option" in text  # must_drive constraint, described not labelled


# ------------------------------------------------------------------------------------------
# Schema, validation, keys
# ------------------------------------------------------------------------------------------

def test_schema_enum_equals_option_ids(ctxs: list[DecisionContext]) -> None:
    for c in ctxs:
        s = llm.output_schema(c.option_ids)
        assert s["properties"]["choice"]["enum"] == list(c.option_ids)
        assert s["properties"]["factors"]["items"]["enum"] == list(FACTORS)
        assert s["additionalProperties"] is False
        assert sorted(s["required"]) == ["choice", "factors", "reason"]
        assert set(s["properties"]) == {"choice", "factors", "reason"}


@pytest.mark.parametrize("obj,ok", [
    ({"choice": "PT", "reason": "x", "factors": ["fee"]}, True),
    ({"choice": "PT", "reason": "x", "factors": []}, True),
    ({"choice": "CAR_0900", "reason": "x", "factors": ["fee"]}, False),
    ({"choice": "PT", "reason": "", "factors": ["fee"]}, False),
    ({"choice": "PT", "reason": "x", "factors": ["cost"]}, False),
    ({"choice": "PT", "reason": "x"}, False),
    ({"choice": "PT", "reason": "x", "factors": [], "extra": 1}, False),
    (["PT"], False),
    (None, False),
])
def test_validate_output(obj: object, ok: bool) -> None:
    assert llm.validate_output(obj, ["CAR_0730", "PT", "SKIP"])[0] is ok


def test_cache_key_properties() -> None:
    s1 = {"type": "object", "properties": {"a": 1, "b": 2}}
    s2 = {"properties": {"b": 2, "a": 1}, "type": "object"}
    k = llm.cache_key("m", "low", "cl-v1", "sys", "user", s1)
    assert k == llm.cache_key("m", "low", "cl-v1", "sys", "user", s2)
    assert k != llm.cache_key("m2", "low", "cl-v1", "sys", "user", s1)
    assert k != llm.cache_key("m", None, "cl-v1", "sys", "user", s1)
    assert k != llm.cache_key("m", "low", "cl-v1", "sys", "user2", s1)
    assert len(k) == 64


def test_estimate_tokens() -> None:
    e = llm.estimate_tokens(["abcd" * 10, "xy"])
    assert e["n_calls"] == 2 and e["prompt_chars"] == 42 and e["approx_tokens"] == 11
    assert "approximate" in e["note"]


# ------------------------------------------------------------------------------------------
# MockLLM
# ------------------------------------------------------------------------------------------

def test_mock_deterministic_and_valid(ctxs: list[DecisionContext], tiny_cfg: Config) -> None:
    m = llm.MockLLM(tiny_cfg)
    for c in ctxs:
        u = llm.render_user_prompt(c, tiny_cfg)
        s = llm.output_schema(c.option_ids)
        a = m.complete(llm.SYSTEM_PROMPT, u, s, c)
        b = llm.MockLLM(tiny_cfg).complete(llm.SYSTEM_PROMPT, u, s, c)
        assert a == b
        assert llm.validate_output(a, c.option_ids) == (True, "")
        assert a["reason"].startswith("[mock]")


def test_mock_without_noise_is_weighted_argmin(ctxs: list[DecisionContext]) -> None:
    cfg = load_config(overrides={"llm.mock.noise_sigma": 0.0})
    m = llm.MockLLM(cfg)
    for c in ctxs:
        out = m.complete(llm.SYSTEM_PROMPT, "u", llm.output_schema(c.option_ids), c)
        best = min(c.options, key=lambda o: sum(m.weights[k] * v for k, v in o.gc_parts.items()))
        assert out["choice"] == best.option_id


def test_mock_decider_log_is_byte_identical(ctxs: list[DecisionContext], tiny_cfg: Config,
                                            tmp_path: Path) -> None:
    outs = []
    for run in ("a", "b"):
        d = llm.make_llm_decider(tiny_cfg, tmp_path / run, FakeFallback(), backend="mock")
        assert d.cache is None
        dec = d.decide_batch(ctxs)
        d.close()
        assert [x.agent_id for x in dec] == [c.agent_id for c in ctxs]
        assert all(x.decider == "llm" and x.meta["backend"] == "mock" for x in dec)
        outs.append((tmp_path / run / "llm_calls.jsonl").read_bytes())
    assert outs[0] == outs[1]
    recs = [json.loads(line) for line in outs[0].decode().splitlines()]
    assert len(recs) == len(ctxs)
    need = {"call_id", "day", "agent_id", "triggers", "backend", "model", "effort", "template_id",
            "cache_key", "cache_hit", "system_sha256", "user", "schema_option_ids", "raw_text",
            "parsed", "valid", "error", "stop_reason", "refusal_category", "usage", "latency_s",
            "model_served", "request_id", "attempt"}
    assert need <= set(recs[0])


# ------------------------------------------------------------------------------------------
# AnthropicLLM with a fake client (no network)
# ------------------------------------------------------------------------------------------

_REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def rate_limit_error() -> anthropic.RateLimitError:
    return anthropic.RateLimitError("rate limited", response=httpx2.Response(429, request=_REQ), body=None)


def bad_request_error() -> anthropic.BadRequestError:
    return anthropic.BadRequestError("bad", response=httpx2.Response(400, request=_REQ), body=None)


def server_error() -> anthropic.InternalServerError:
    return anthropic.InternalServerError("boom", response=httpx2.Response(500, request=_REQ), body=None)


def response(text: str | None, stop_reason: str = "end_turn", category: str | None = None) -> Any:
    content = [SimpleNamespace(type="thinking", thinking="")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        content=content if stop_reason != "refusal" else [], stop_reason=stop_reason,
        stop_details=SimpleNamespace(type="refusal", category=category, explanation="x")
        if stop_reason == "refusal" else None,
        usage=SimpleNamespace(input_tokens=900, output_tokens=60, cache_creation_input_tokens=0,
                              cache_read_input_tokens=None),
        model="claude-opus-5-5", _request_id="req_test")


class FakeMessages:
    def __init__(self, script: Callable[[dict], Any], log: list[dict], state: dict) -> None:
        self.script, self.log, self.state = script, log, state

    async def create(self, **kwargs: Any) -> Any:
        self.log.append(kwargs)
        self.state["active"] += 1
        self.state["max_active"] = max(self.state["max_active"], self.state["active"])
        try:
            await asyncio.sleep(0.005)
            out = self.script(kwargs)
        finally:
            self.state["active"] -= 1
        if isinstance(out, BaseException):
            raise out
        return out


class FakeClient:
    """Captures kwargs of beta.messages.create and messages.create; replies from a script."""

    def __init__(self, script: Callable[[dict], Any]) -> None:
        self.beta_calls: list[dict] = []
        self.calls: list[dict] = []
        self.state = {"active": 0, "max_active": 0}
        self.beta = SimpleNamespace(messages=FakeMessages(script, self.beta_calls, self.state))
        self.messages = FakeMessages(script, self.calls, self.state)

    @property
    def all_calls(self) -> list[dict]:
        return self.beta_calls + self.calls


def queue_script(*items: Any) -> Callable[[dict], Any]:
    q = list(items)

    def f(_kwargs: dict) -> Any:
        return q.pop(0) if len(q) > 1 else q[0]
    return f


def choice_script(kind: str = "valid") -> Callable[[dict], Any]:
    """Reply with the first option id of the request's schema."""
    def f(kwargs: dict) -> Any:
        ids = kwargs["output_config"]["format"]["schema"]["properties"]["choice"]["enum"]
        return response(json.dumps({"reason": "I keep my routine.", "factors": ["habit"],
                                    "choice": ids[-1]}))
    return f


def make_decider(cfg: Config, client: FakeClient, tmp_path: Path,
                 cache: bool = True) -> tuple[llm.LLMDecider, FakeFallback]:
    fb = FakeFallback()
    be = llm.AnthropicLLM(cfg, client=client)
    d = llm.LLMDecider(cfg, be, fb, tmp_path / "run" / "llm_calls.jsonl",
                       llm.LLMCache(tmp_path / "cache") if cache else None)
    return d, fb


def read_log(tmp_path: Path) -> list[dict]:
    p = tmp_path / "run" / "llm_calls.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()]


def test_build_request_default_model(tiny_cfg: Config) -> None:
    be = llm.AnthropicLLM(tiny_cfg, client=object())
    schema = llm.output_schema(["CAR_0730", "PT"])
    req = be.build_request("SYS", "USER", schema)
    assert req == {
        "model": "claude-opus-5-5",
        "max_tokens": 4000,
        "system": [{"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": "USER"}],
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        "betas": ["server-side-fallback-2026-07-01"],
        "fallbacks": "default",
    }
    for banned in ("temperature", "top_p", "top_k", "thinking"):
        assert banned not in req


def test_build_request_haiku_and_no_fallbacks() -> None:
    cfg = load_config(overrides={"llm.model": "claude-haiku-4-5"})
    req = llm.AnthropicLLM(cfg, client=object()).build_request("S", "U", llm.output_schema(["PT"]))
    assert "effort" not in req["output_config"] and "betas" not in req and "fallbacks" not in req
    cfg2 = load_config(overrides={"llm.use_fallbacks": False})
    be2 = llm.AnthropicLLM(cfg2, client=object())
    req2 = be2.build_request("S", "U", llm.output_schema(["PT"]))
    assert not be2.uses_beta and "betas" not in req2 and req2["output_config"]["effort"] == "low"


def test_anthropic_valid_call_uses_beta_endpoint_and_logs(ctxs: list[DecisionContext],
                                                         tiny_cfg: Config, tmp_path: Path) -> None:
    client = FakeClient(choice_script())
    d, fb = make_decider(tiny_cfg, client, tmp_path)
    out = d.decide_batch(ctxs[:3])
    assert len(client.beta_calls) == 3 and not client.calls
    assert all(x.decider == "llm" and x.option_id == c.option_ids[-1] for x, c in zip(out, ctxs))
    assert out[0].factors == ("habit",) and out[0].meta["attempts"] == 1
    assert not fb.calls
    log = read_log(tmp_path)
    assert [r["agent_id"] for r in log] == [c.agent_id for c in ctxs[:3]]
    r = log[0]
    assert r["valid"] and r["request_id"] == "req_test" and r["model_served"] == "claude-opus-5-5"
    assert r["usage"] == {"input_tokens": 900, "output_tokens": 60,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    assert r["user"] == client.beta_calls[0]["messages"][0]["content"]
    assert client.beta_calls[0]["system"][0]["text"] == llm.system_prompt(tiny_cfg)
    d.close()


def test_anthropic_refusal_falls_back_without_resend(ctxs: list[DecisionContext], tiny_cfg: Config,
                                                     tmp_path: Path) -> None:
    """A refusal (after the server-side fallback) is not resent: straight to the rule."""
    client = FakeClient(queue_script(response(None, "refusal", "cyber")))
    d, fb = make_decider(tiny_cfg, client, tmp_path)
    [dec] = d.decide_batch(ctxs[:1])
    assert dec.decider == "llm-fallback-rule" and fb.calls == [ctxs[0].agent_id]
    assert dec.meta["attempts"] == 1 and dec.meta["error"] == "refusal"
    assert len(client.all_calls) == 1 and d.stats["n_refusals"] == 1
    log = read_log(tmp_path)
    assert len(log) == 1 and all(r["refusal_category"] == "cyber" for r in log)
    assert all(r["stop_reason"] == "refusal" and not r["valid"] for r in log)
    assert d.stats["n_fallback"] == 1
    assert not list((tmp_path / "cache").rglob("*.json"))  # nothing cached


def test_anthropic_invalid_json_then_valid(ctxs: list[DecisionContext], tiny_cfg: Config,
                                           tmp_path: Path) -> None:
    c = ctxs[0]
    good = response(json.dumps({"reason": "ok", "factors": ["fee"], "choice": c.option_ids[0]}))
    client = FakeClient(queue_script(response('{"reason": "trunc', "max_tokens"), good))
    d, fb = make_decider(tiny_cfg, client, tmp_path)
    [dec] = d.decide_batch([c])
    assert dec.decider == "llm" and dec.option_id == c.option_ids[0] and dec.meta["attempts"] == 2
    log = read_log(tmp_path)
    assert "invalid JSON" in log[0]["error"] and log[1]["valid"]
    assert not fb.calls


def test_anthropic_invalid_choice_twice_falls_back(ctxs: list[DecisionContext], tiny_cfg: Config,
                                                   tmp_path: Path) -> None:
    bad = response(json.dumps({"reason": "x", "factors": ["fee"], "choice": "CAR_1200"}))
    client = FakeClient(queue_script(bad))
    d, fb = make_decider(tiny_cfg, client, tmp_path)
    [dec] = d.decide_batch(ctxs[:1])
    assert dec.decider == "llm-fallback-rule" and len(client.all_calls) == 2
    assert "not in option ids" in read_log(tmp_path)[-1]["error"]


def test_anthropic_api_errors_not_retried_by_app(ctxs: list[DecisionContext], tiny_cfg: Config,
                                                  tmp_path: Path) -> None:
    """429 and 5xx reach the app only after the SDK's own retries: one request, then the rule."""
    for err in (rate_limit_error(), server_error()):
        client = FakeClient(queue_script(err))
        d, fb = make_decider(tiny_cfg, client, tmp_path / type(err).__name__)
        [dec] = d.decide_batch(ctxs[:1])
        assert len(client.all_calls) == 1 and dec.decider == "llm-fallback-rule"
        assert d.stats["n_api_errors"] == 1 and d.stats["n_fallback"] == 1


@pytest.mark.parametrize("status,cls", [(401, "AuthenticationError"), (403, "PermissionDeniedError"),
                                        (404, "NotFoundError")])
def test_anthropic_fatal_error_stops_run_and_logs(ctxs: list[DecisionContext], tiny_cfg: Config,
                                                  tmp_path: Path, status: int, cls: str) -> None:
    err = getattr(anthropic, cls)("no", response=httpx2.Response(status, request=_REQ), body=None)
    client = FakeClient(queue_script(err))
    d, fb = make_decider(tiny_cfg, client, tmp_path)
    with pytest.raises(llm.LLMFatalError):
        d.decide_batch(ctxs[:4])
    log = read_log(tmp_path)
    assert log and all(r["error_kind"] == "fatal" for r in log) and not fb.calls
    d.close()


def test_anthropic_consecutive_errors_stop_run(ctxs: list[DecisionContext], tmp_path: Path) -> None:
    cfg = load_config(overrides={"llm.max_consecutive_errors": 3, "llm.max_concurrency": 1})
    client = FakeClient(queue_script(bad_request_error()))
    d, _ = make_decider(cfg, client, tmp_path)
    with pytest.raises(llm.LLMFatalError):
        d.decide_batch(ctxs[:6])
    assert len(client.all_calls) == 3
    d.close()


def test_anthropic_unexpected_exception_is_recorded(ctxs: list[DecisionContext], tiny_cfg: Config,
                                                    tmp_path: Path) -> None:
    """A malformed 200 body (or any exception outside the SDK's error classes) does not abort the
    batch: it is logged and the agent falls back to the rule."""
    client = FakeClient(queue_script(ValueError("malformed body")))
    d, fb = make_decider(tiny_cfg, client, tmp_path)
    out = d.decide_batch(ctxs[:2])
    assert [x.decider for x in out] == ["llm-fallback-rule"] * 2
    log = read_log(tmp_path)
    assert len(log) == 2 and all("malformed body" in r["error"] for r in log)
    d.close()


def test_identical_prompts_share_one_call(ctxs: list[DecisionContext], tiny_cfg: Config,
                                          tmp_path: Path) -> None:
    """Two agents with byte-identical prompts in one morning: one request, a shared answer."""
    from dataclasses import replace

    c0 = ctxs[0]
    twin = replace(c0, agent_id=c0.agent_id + 100)
    assert llm.render_user_prompt(twin, tiny_cfg) == llm.render_user_prompt(c0, tiny_cfg)
    client = FakeClient(choice_script())
    d, _ = make_decider(tiny_cfg, client, tmp_path)
    a, b = d.decide_batch([c0, twin])
    assert len(client.all_calls) == 1 and a.option_id == b.option_id
    log = read_log(tmp_path)
    assert [r["shared"] for r in log] == [False, True] and log[1]["agent_id"] == twin.agent_id
    assert d.stats["n_calls"] == 1 and d.stats["n_shared"] == 1
    d.close()


def test_cache_key_includes_request_settings(tiny_cfg: Config) -> None:
    be = llm.AnthropicLLM(tiny_cfg, client=object())
    ex = be.key_extra()
    assert ex["max_tokens"] == 4000 and ex["fallbacks"][0] == "default" and "replicate" not in ex
    be2 = llm.AnthropicLLM(load_config(overrides={"llm.use_fallbacks": False, "llm.replicate": 2}),
                           client=object())
    ex2 = be2.key_extra()
    assert ex2["fallbacks"] is None and ex2["replicate"] == 2
    s = llm.output_schema(["PT"])
    assert llm.cache_key("m", "low", "cl-v1", "s", "u", s, ex) != llm.cache_key("m", "low", "cl-v1", "s", "u", s, ex2)


def test_anthropic_bad_request_not_retried(ctxs: list[DecisionContext], tiny_cfg: Config,
                                           tmp_path: Path) -> None:
    client = FakeClient(queue_script(bad_request_error()))
    d, fb = make_decider(tiny_cfg, client, tmp_path)
    [dec] = d.decide_batch(ctxs[:1])
    # a 400 is not resent (neither at API level nor as an invalid output): one request, then rule
    assert len(client.all_calls) == 1 and dec.decider == "llm-fallback-rule"
    assert read_log(tmp_path)[0]["error"].startswith("BadRequestError")


def test_anthropic_cache_hit_replays_without_calls(ctxs: list[DecisionContext], tiny_cfg: Config,
                                                   tmp_path: Path) -> None:
    client = FakeClient(choice_script())
    d, _ = make_decider(tiny_cfg, client, tmp_path)
    first = d.decide_batch(ctxs[:4])
    d.close()

    def boom(_k: dict) -> Any:
        raise AssertionError("network call on cache hit")
    client2 = FakeClient(boom)
    d2, _ = make_decider(tiny_cfg, client2, tmp_path)
    second = d2.decide_batch(ctxs[:4])
    assert not client2.all_calls
    assert [x.option_id for x in first] == [x.option_id for x in second]
    assert [x.reason for x in first] == [x.reason for x in second]
    assert all(x.meta["cache_hit"] for x in second)
    log = read_log(tmp_path)
    assert [r["cache_hit"] for r in log] == [False] * 4 + [True] * 4
    assert d2.stats["n_cache_hits"] == 4 and d2.stats["n_calls"] == 0
    d2.close()


def test_anthropic_concurrency_limited(ctxs: list[DecisionContext], tmp_path: Path) -> None:
    cfg = load_config(overrides={"llm.max_concurrency": 2})
    client = FakeClient(choice_script())
    d, _ = make_decider(cfg, client, tmp_path, cache=False)
    out = d.decide_batch(ctxs[:8])
    assert len(out) == 8 and client.state["max_active"] == 2
    d.close()


def test_make_llm_decider_anthropic_uses_cache_dir(tiny_cfg: Config, tmp_path: Path) -> None:
    d = llm.make_llm_decider(tiny_cfg, tmp_path, FakeFallback(), backend="anthropic")
    assert isinstance(d.backend, llm.AnthropicLLM) and d.cache is not None
    assert d.cache.cache_dir == tiny_cfg.resolve_path(tiny_cfg.llm.cache_dir)
    assert d.log_path == tmp_path / "llm_calls.jsonl"
    with pytest.raises(ValueError):
        llm.make_llm_decider(tiny_cfg, tmp_path, FakeFallback(), backend="openai")


# ------------------------------------------------------------------------------------------
# Integration with the behaviour modules (options, memory, persona, rules)
# ------------------------------------------------------------------------------------------

def test_integration_real_options_and_rule_fallback(tiny_personas: list[Persona], tiny_cfg: Config,
                                                    make_today: Callable[..., TodayInfo],
                                                    tmp_path: Path) -> None:
    options = pytest.importorskip("cordonlite.options")
    memory = pytest.importorskip("cordonlite.memory")
    rules = pytest.importorskip("cordonlite.rules")
    if not hasattr(options, "build_options") or not hasattr(rules, "RuleDecider"):
        pytest.skip("behaviour modules not implemented yet")
    today = make_today(3, fee_active=True, public_delay=PROFILE, fee_changed_today=True)
    ctxs_ = []
    for p in tiny_personas:
        mem = memory.new_memory(p.agent_id, p.company_car)
        params = persona_mod.trait_params(p, tiny_cfg)
        opts = options.build_options(p, mem, today, params, tiny_cfg, True)
        ctxs_.append(DecisionContext(
            agent_id=p.agent_id, day=3, persona=p, params=params, options=opts,
            standing_option_id=None, triggers=("T1", "T2"), discontinuity=True, recent=(),
            delay_ratio_ema=1.0, ref_fee=0.0, today=today))
    for c in ctxs_:
        text = llm.render_user_prompt(c, tiny_cfg)
        for o in c.options:
            assert f"{o.gc:.4f}" not in text
        assert "not settled on a usual way" in text
    # mock path
    d = llm.make_llm_decider(tiny_cfg, tmp_path / "mock", rules.RuleDecider(tiny_cfg), backend="mock")
    out = d.decide_batch(ctxs_)
    assert all(x.decider == "llm" and x.option_id in c.option_ids for x, c in zip(out, ctxs_))
    # refusal path: real RuleDecider fallback
    client = FakeClient(queue_script(response(None, "refusal", None)))
    d2 = llm.LLMDecider(tiny_cfg, llm.AnthropicLLM(tiny_cfg, client=client),
                        rules.RuleDecider(tiny_cfg), tmp_path / "a" / "llm_calls.jsonl", None)
    out2 = d2.decide_batch(ctxs_[:2])
    ref = rules.RuleDecider(tiny_cfg).decide_batch(ctxs_[:2])
    assert [x.option_id for x in out2] == [x.option_id for x in ref]
    assert all(x.decider == "llm-fallback-rule" for x in out2)
    d.close()
    d2.close()


# ------------------------------------------------------------------------------------------
# Fuel addition: information parity between the rule and the prompt
# ------------------------------------------------------------------------------------------

def test_prompt_states_fuel_cost_and_fuel_column(tiny_personas: list[Persona], tiny_cfg: Config,
                                                 make_today: Callable[..., TodayInfo]) -> None:
    from dataclasses import replace as dc_replace

    p = dc_replace(next(x for x in tiny_personas if not x.company_car and x.pt_allowed), fuel_cost=6.81)
    ctx = make_ctx(p, make_today(11))
    ctx = dc_replace(ctx, options=tuple(dc_replace(o, fuel=6.81) if o.mode == "CAR" else o for o in ctx.options))
    text = llm.render_user_prompt(ctx, tiny_cfg)
    assert "- Fuel for the drive there and back costs you about NZ$6.81 a day." in text
    header = next(ln for ln in text.splitlines() if ln.startswith("option id |"))
    cols = header.split(" | ")
    assert cols[cols.index("parking") + 1] == "fuel"
    i = cols.index("fuel")
    rows = [ln.split(" | ") for ln in text.splitlines() if ln.startswith(("CAR_", "PT |", "SKIP |"))]
    assert all(r[i] == "NZ$6.81" for r in rows if r[0].startswith("CAR_"))
    assert all(r[i] == "-" for r in rows if not r[0].startswith("CAR_"))
    # no fuel cost: stated as nothing; an employer vehicle names the employer
    assert "- Fuel for the drive costs you nothing." in llm.render_user_prompt(
        make_ctx(dc_replace(p, fuel_cost=0.0), make_today(11)), tiny_cfg)
    pc = next(x for x in tiny_personas if x.company_car)
    assert "Fuel for the drive costs you nothing: your employer pays for it." in llm.render_user_prompt(
        make_ctx(pc, make_today(6)), tiny_cfg)


def test_mock_weights_fuel_part(ctxs: list[DecisionContext]) -> None:
    cfg = load_config(overrides={"llm.mock.noise_sigma": 0.0, "llm.mock.w_fuel": 2.0})
    m = llm.MockLLM(cfg)
    assert m.weights["fuel"] == 2.0
    o = ctxs[0].options[0]
    from dataclasses import replace as dc_replace

    o2 = dc_replace(o, gc_parts={**o.gc_parts, "fuel": 5.0})
    assert sum(m._score(o2).values()) - sum(m._score(o).values()) == pytest.approx(10.0)


# ------------------------------------------------------------------------------------------
# Early start: information parity between the rule and the prompt
# ------------------------------------------------------------------------------------------

EARLY_SENTENCE = "- Your employer lets you work 07:00 to 15:00 instead of your usual hours on any day you choose."


def test_prompt_states_early_start_only_when_allowed(tiny_personas: list[Persona],
                                                     make_today: Callable[..., TodayInfo]) -> None:
    from dataclasses import replace as dc_replace

    from cordonlite import memory, options

    cfg = load_config()
    base = dc_replace(next(x for x in tiny_personas if not x.company_car and x.pt_allowed), tstar_min=510)
    today = make_today(11, fee_changed_today=True)
    texts = {}
    for name, p in (("no", base), ("yes", dc_replace(base, early_shift_ok=True)),
                    ("at7", dc_replace(base, early_shift_ok=True, tstar_min=420))):
        params = persona_mod.trait_params(p, cfg)
        opts = options.build_options(p, memory.new_memory(p.agent_id), today, params, cfg, False)
        ctx = DecisionContext(agent_id=p.agent_id, day=11, persona=p, params=params, options=opts,
                              standing_option_id=None, triggers=("T1", "T2"), discontinuity=True, recent=(),
                              delay_ratio_ema=1.0, ref_fee=0.0, today=today)
        texts[name] = (llm.render_user_prompt(ctx, cfg), opts)
    assert EARLY_SENTENCE in texts["yes"][0]
    assert EARLY_SENTENCE not in texts["no"][0]
    assert "Your employer lets you work" not in texts["at7"][0]      # the usual start is already 07:00
    for name, (text, opts) in texts.items():
        assert "archetype" not in text.lower() and "early_shift" not in text
        header = next(ln for ln in text.splitlines() if ln.startswith("option id |")).split(" | ")
        i = header.index("start time")
        assert header[i + 1] == "expected arrival"
        rows = {r[0]: r for r in (ln.split(" | ") for ln in text.splitlines()
                                  if ln.startswith(("CAR_", "PT |", "WFH |", "SKIP |")))}
        for o in opts:
            want = "-" if o.mode in ("WFH", "SKIP") else f"{o.start_used_min // 60:02d}:{o.start_used_min % 60:02d}"
            assert rows[o.option_id][i] == want
    y_text, y_opts = texts["yes"]
    early = [o for o in y_opts if o.early_shift]
    assert early and all(o.mode == "CAR" for o in early)
    rows = {r[0]: r for r in (ln.split(" | ") for ln in y_text.splitlines() if ln.startswith("CAR_"))}
    o = early[0]
    cell = rows[o.option_id][header.index("expected arrival")]
    # minutes early or late are stated against the 07:00 start
    assert cell.endswith(f"({int(o.early_min)} min early)") or cell.endswith("(on time)") or "late" in cell
    assert all(not x.early_shift for x in texts["no"][1])
    assert "Early or late is measured against the start time shown for that option." in y_text


def test_prompt_memory_table_shows_start_used(tiny_personas: list[Persona], tiny_cfg: Config,
                                              make_today: Callable[..., TodayInfo]) -> None:
    from dataclasses import replace as dc_replace

    p = dc_replace(next(x for x in tiny_personas if not x.company_car and x.pt_allowed), early_shift_ok=True,
                   tstar_min=510)
    rec = MemoryRecord(day=10, option_id="CAR_0615", mode="CAR", depart_min=375, queue_delay_min=0.0,
                       expected_delay_min=0.0, expected_travel_min=25.0, travel_min=25.0, arrive_min=400,
                       early_min=20.0, late_min=0.0, fee_paid=0.0, pt_disrupted=False, decider="rule",
                       triggers=(), reason="", start_used_min=420, early_shift=True)
    text = llm.render_user_prompt(make_ctx(p, make_today(11), recent=(rec,)), tiny_cfg)
    line = next(ln for ln in text.splitlines() if ln.startswith("10 | drove"))
    assert " | 07:00 | 06:40 (20 min early) | " in line
