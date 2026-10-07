"""LLM deciders: prompt rendering (template cl-v1), schema, MockLLM and AnthropicLLM backends.

Owner: llm builder. See INTERFACES.md. Never call the live API in tests.

Public API:
    TEMPLATE_ID = "cl-v1"
    SYSTEM_PROMPT: str
    system_prompt(cfg) -> str                                           # SYSTEM_PROMPT with cfg word limit
    render_user_prompt(ctx: DecisionContext, cfg: Config) -> str       # byte-stable, no GC, no archetype code/label
    output_schema(option_ids: Sequence[str]) -> dict                    # {"reason","factors","choice"}, additionalProperties false
    validate_output(obj: object, option_ids: Sequence[str]) -> tuple[bool, str]
    cache_key(model, effort, template_id, system, user, schema, extra=None) -> str
    prompt_sha256(system, user) -> str
    flexibility_sentence(sched_mult) -> str
    class LLMCache, MockLLM, AnthropicLLM, LLMDecider, LLMFatalError
    make_llm_decider(cfg, run_dir, fallback, backend=None) -> LLMDecider
    estimate_tokens(prompts) -> dict                                    # chars/4, approximate

Design notes
- The prompt never shows the generalised cost (GC) or its parts, the archetype code or label,
  or trait names. It shows constraints, disposition sentences, the memory table, today's
  information and the options with their attributes.
- MockLLM is a deterministic stand-in, NOT an LLM. Its outputs carry backend="mock".
- AnthropicLLM uses the official SDK (anthropic 1.x) with structured outputs
  (output_config.format = json_schema) and, by default, the server-side refusal fallback
  (beta server-side-fallback-2026-07-01, fallbacks="default"). No sampling parameters are sent.
- Every call is appended to llm_calls.jsonl as soon as it completes (input order for the
  deterministic MockLLM, completion order for the live API).
- Prompt caching is nominal: the system prompt (about 150 tokens) is below the minimum cacheable
  prefix, and the json_schema format differs per agent, so input should be costed as uncached.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from cordonlite.config import Config
from cordonlite.types import (
    FACTORS,
    Decider,
    Decision,
    DecisionContext,
    MemoryRecord,
    Option,
    Persona,
    clock_str,
)

TEMPLATE_ID = "cl-v1"
# cl-v2 (llm.template_id = "cl-v2") changes two things and leaves the rest of cl-v1 as it is:
#   1. the options table has a "you pay today" column (road charge the commuter pays + parking + fuel,
#      or the fare), so a money comparison needs no arithmetic;
#   2. the reply names one main_factor and an optional second_factor instead of a free list. Both are
#      enums in the JSON schema, narrowed per agent-day to the factors that can apply (factor_ids):
#      no road_charge without a charge, no disruption without one, no routine or past_experience on
#      the first day, no bus_train_preference when no bus or train is offered. Tags that cannot
#      apply therefore cannot be returned. The tags are defined in the system prompt; their names
#      avoid the trait names, which never appear in a prompt.
TEMPLATE_V2 = "cl-v2"
FACTORS_V2: tuple[str, ...] = (
    "road_charge", "other_money", "travel_time", "arrival_time", "routine", "bus_train_preference",
    "flexibility", "past_experience", "disruption", "constraint", "other",
)
NO_FACTOR = "none"
# cl-v2 tag -> types.FACTORS tag, to compare with the rule arms and with cl-v1 runs
FACTOR_V2_TO_V1: dict[str, str] = {
    "road_charge": "fee", "other_money": "other", "travel_time": "travel_time",
    "arrival_time": "arrival_time", "routine": "habit", "bus_train_preference": "pt",
    "flexibility": "flexibility", "past_experience": "past_experience", "disruption": "disruption",
    "constraint": "work_constraint", "other": "other",
}

# Models that accept the server-side refusal fallback ("default" form). Claude Haiku 4.5 does
# not run the classifiers that trigger it, so the fallback beta is not sent for it.
FALLBACK_MODELS: frozenset[str] = frozenset({"claude-opus-5-5", "claude-sonnet-5-5"})
# Models for which output_config.effort must not be sent.
NO_EFFORT_MODELS: frozenset[str] = frozenset({"claude-haiku-4-5"})
MOCK_MODEL = "mock-v1"

_SYSTEM_TEMPLATE = (
    "You simulate the morning travel decision of one commuter who travels into Auckland city "
    "centre on a weekday. You are given this person's circumstances, how they tend to decide, "
    "their recent trips, today's information and the options open to them today.\n"
    "Decide as this person would, weighing their own circumstances, tendencies and recent "
    "experience. Use only the information given. Do not rely on demographic or occupational "
    "stereotypes.\n"
    "Choose exactly one option id from the options table. Give the person's reason in the first "
    "person, in at most {words} words, and list the factors that mattered most."
)


# How a reply names its factors (cl-v2 and the plan template in planner.py).
FACTOR_DEFINITIONS = (
    "Name the one factor that decided the choice (main_factor) and, only if a second factor "
    "clearly mattered, that one as well (second_factor; otherwise \"none\"). The factors mean:\n"
    "- road_charge: the charge for driving into the city centre: paying it, its amount, or avoiding it.\n"
    "- other_money: parking, fuel or the bus or train fare.\n"
    "- travel_time: how long the trip takes door to door, queues included.\n"
    "- arrival_time: arriving early, on time or late against the start time.\n"
    "- routine: keeping the usual way of making the trip, or the bother of changing it.\n"
    "- bus_train_preference: liking or disliking buses and trains in themselves, apart from their "
    "cost and time.\n"
    "- flexibility: being able, or not able, to change the hours of the day or to work from home.\n"
    "- past_experience: something that happened on the recent days shown.\n"
    "- disruption: a disruption to buses and trains.\n"
    "- constraint: something the day requires that rules other options out.\n"
    "- other: none of these.\n"
    "Only factors that can apply today are offered."
)

_SYSTEM_TEMPLATE_V2 = (
    "You simulate the morning travel decision of one commuter who travels into Auckland city "
    "centre on a weekday. You are given this person's circumstances, how they tend to decide, "
    "their recent trips, today's information and the options open to them today.\n"
    "Decide as this person would, weighing their own circumstances, tendencies and recent "
    "experience. Use only the information given. Do not rely on demographic or occupational "
    "stereotypes.\n"
    "Choose exactly one option id from the options table. Give the person's reason in the first "
    "person, in at most {words} words. When the reason compares money, use the \"you pay today\" "
    "column.\n"
) + FACTOR_DEFINITIONS


def system_prompt(cfg: Config | None = None) -> str:
    """System prompt of the configured template (cl-v1 by default) with the reason word limit."""
    words = cfg.llm.reason_max_words if cfg is not None else 30
    if cfg is not None and cfg.llm.template_id == TEMPLATE_V2:
        return _SYSTEM_TEMPLATE_V2.format(words=words)
    return _SYSTEM_TEMPLATE.format(words=words)


SYSTEM_PROMPT: str = system_prompt(None)


# --------------------------------------------------------------------------------------------
# Formatting helpers (fixed formats so prompts are byte-stable)
# --------------------------------------------------------------------------------------------

def _money(x: float) -> str:
    return f"NZ${x:.2f}"


def _mins(x: float | None) -> str:
    if x is None:
        return "-"
    return f"{int(round(x))} min"


def _clock(m: int | float | None) -> str:
    return "-" if m is None else clock_str(m)


def _early_late(early: float, late: float) -> str:
    e, lt = int(round(early)), int(round(late))
    if lt > 0:
        return f"{lt} min late"
    if e > 0:
        return f"{e} min early"
    return "on time"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    out = [" | ".join(header), " | ".join("---" for _ in header)]
    out.extend(" | ".join(r) for r in rows)
    return out


def _mode_phrase(mode: str, activity: str) -> str:
    return {
        "CAR": "drove",
        "PT": "bus or train",
        "WFH": "worked from home",
        "SKIP": "did not go into the city centre",
    }.get(mode, mode.lower())


def _dispositions(persona: Persona) -> tuple[str, ...]:
    from cordonlite import persona as persona_mod  # lazy: built in parallel by another builder

    return tuple(persona_mod.disposition_sentences(persona))


def _public_delay_at(ctx: DecisionContext, o: Option, cfg: Config) -> float:
    """Yesterday's public corridor delay (before the personal ratio) for a car option."""
    pub = getattr(o, "expected_public_delay_min", None)
    if pub is not None:  # set by options.build_options
        return float(pub)
    gate_arrive_min = o.expected_gate_arrive_min if o.expected_gate_arrive_min is not None \
        else int(o.depart_min or 0) + ctx.persona.fftt_to_gate_min
    try:
        from cordonlite.options import expected_public_delay
    except ImportError:
        expected_public_delay = None
    if expected_public_delay is not None:
        return float(expected_public_delay(ctx.today.public_delay, ctx.persona.corridor_id,
                                           gate_arrive_min, cfg.costs.delay_bin_min))
    pts = ctx.today.public_delay.get(ctx.persona.corridor_id, ())
    if not pts:
        return 0.0
    xs = [p[0] for p in pts]
    if gate_arrive_min < xs[0] or gate_arrive_min > xs[-1]:
        return 0.0
    return float(np.interp(gate_arrive_min, xs, [p[1] for p in pts]))


# --------------------------------------------------------------------------------------------
# Prompt sections
# --------------------------------------------------------------------------------------------

def flexibility_sentence(sched_mult: float) -> str:
    """Start-time flexibility, graded like the rule's schedule-delay multiplier (sched_mult)."""
    if sched_mult <= 0.5:
        return ("Your start time is flexible: arriving somewhat early or late costs you little.")
    if sched_mult <= 0.75:
        return ("Your start time has some give: arriving a little early or late is acceptable but "
                "not ideal.")
    if sched_mult <= 1.0:
        return ("Your start time is firm: arriving late is a problem for you, and arriving early is "
                "wasted time.")
    return ("Your start time is fixed: arriving late is a serious problem for you, and arriving "
            "early is wasted time.")


def _situation(ctx: DecisionContext, cfg: Config) -> list[str]:
    p = ctx.persona
    # Work and study are described by the same constraint sentences (no occupational cue).
    lines = [f"- You travel to your regular destination in Auckland city centre and need to be "
             f"there by {clock_str(p.tstar_min)}.",
             f"- {flexibility_sentence(p.sched_mult)}"]
    from cordonlite.options import early_start_for

    es = early_start_for(p, cfg)
    if es is not None:
        # stated in plain words; the working day is taken as 8 hours (07:00 to 15:00)
        lines.append(f"- Your employer lets you work {clock_str(es)} to {clock_str(es + 480)} instead of "
                     f"your usual hours on any day you choose.")
    if p.must_drive:
        lines.append("- You need your vehicle during the day to carry tools or goods, so a bus "
                     "or train is not an option and your day's work cannot be done from home.")
    else:
        if p.wfh_allowed:
            lines.append("- You can do your day's work from home on a day when you choose to.")
        else:
            lines.append("- Doing your day's work from home is not possible for you.")
        if p.pt_allowed:
            lines.append(f"- A bus or train is available from your area: about "
                         f"{_mins(p.pt_time_min)} door to door, {_money(p.pt_fare)} for the day.")
        else:
            lines.append("- There is no practical bus or train from your area.")
    lines.append(f"- With no queues the drive takes about {_mins(p.fftt_total_min)}: "
                 f"{_mins(p.fftt_to_gate_min)} to reach the city-centre boundary and "
                 f"{_mins(p.fftt_gate_to_dest_min)} from there. Queues can form at the entry "
                 f"point you use in the morning.")
    if p.parking_cost > 0:
        lines.append(f"- Parking at your destination costs you {_money(p.parking_cost)} a day.")
    else:
        lines.append("- Parking at your destination costs you nothing.")
    if p.fuel_cost > 0:
        lines.append(f"- Fuel for the drive there and back costs you about {_money(p.fuel_cost)} a day.")
    elif p.company_car:
        lines.append("- Fuel for the drive costs you nothing: your employer pays for it.")
    else:
        lines.append("- Fuel for the drive costs you nothing.")
    if p.company_car:
        lines.append("- You drive an employer-provided vehicle; your employer pays any road "
                     "charge for it.")
    else:
        lines.append("- You pay any road charge yourself.")
    lines.append(f"- Your time is worth about NZ${int(round(p.vot))} per hour to you.")
    if ctx.standing_option_id is None:
        lines.append("- You have not settled on a usual way of making this trip yet.")
    else:
        lines.append(f"- Your usual choice lately: {_standing_phrase(ctx)}.")
    return lines


def _standing_phrase(ctx: DecisionContext) -> str:
    sid = ctx.standing_option_id or ""
    if sid.startswith("CAR_"):
        return f"drive, leaving home at {sid[4:6]}:{sid[6:8]} (option {sid})"
    return {
        "PT": "bus or train (option PT)",
        "WFH": "work from home (option WFH)",
        "SKIP": "not going into the city centre (option SKIP)",
    }.get(sid, f"option {sid}")


def _memory(ctx: DecisionContext) -> list[str]:
    recs: Sequence[MemoryRecord] = ctx.recent
    if not recs:
        return ["No trips recorded yet."]
    rows = []
    for r in recs:
        travel = r.travel_min if r.mode in ("CAR", "PT") else None
        note = []
        if r.pt_disrupted:
            note.append("bus or train disrupted")
        if (r.mode == "CAR" and r.travel_min is not None and r.expected_travel_min is not None):
            gap = int(round(r.travel_min - r.expected_travel_min))
            if gap >= 5:
                note.append(f"about {gap} min longer than you expected")
            elif gap <= -5:
                note.append(f"about {-gap} min quicker than you expected")
        if r.mode in ("CAR", "PT"):
            arrived = f"{_clock(r.arrive_min)} ({_early_late(r.early_min, r.late_min)})"
            start = _clock(r.start_used_min if r.start_used_min is not None else ctx.persona.tstar_min)
        else:
            arrived = "-"
            start = "-"
        if r.mode == "CAR":
            fee = _money(r.fee_paid) + (" (employer)" if ctx.persona.company_car and r.fee_paid > 0 else "")
            queue = _mins(r.queue_delay_min)
        else:
            fee, queue = "-", "-"
        rows.append([
            str(r.day), _mode_phrase(r.mode, ctx.persona.activity),
            _clock(r.depart_min) if r.mode in ("CAR", "PT") else "-",
            queue, _mins(travel), start, arrived, fee, "; ".join(note),
        ])
    return _table(["day", "what you did", "left home", "queue at entry", "door to door",
                   "start time", "arrived", "charge paid", "note"], rows)


def _today(ctx: DecisionContext, cfg: Config) -> list[str]:
    t = ctx.today
    p = ctx.persona
    lines = [f"- Today is day {ctx.day}."]
    if t.fee_active:
        lead = "A congestion charge on cars entering the city centre starts today." if t.fee_changed_today \
            else "A congestion charge applies to cars entering the city centre."
        lines.append(f"- {lead} It depends on the time you cross into the city centre:")
        from cordonlite.fees import describe_schedule

        start = cfg.time.depart_earliest_min
        end = cfg.time.tstar_latest_min + 60
        grid = describe_schedule(t.fee_by_minute, start, end, 15)
        segs: list[tuple[int, int, float]] = []
        for m, f in grid:
            if segs and abs(segs[-1][2] - f) < 1e-9:
                segs[-1] = (segs[-1][0], m, f)
            else:
                segs.append((m, m, f))
        for a, b, f in segs:
            span = f"at {clock_str(a)}" if a == b else f"from {clock_str(a)} to {clock_str(b)}"
            lines.append(f"  - crossing {span}: {_money(f)}")
        if len(segs) > 1:
            lines.append("  Between the listed times the charge moves gradually from one value "
                         "to the next.")
        if p.company_car:
            lines.append("  Your employer pays this charge for your vehicle.")
    elif t.fee_changed_today:
        lines.append("- The congestion charge for driving into the city centre ends today; "
                     "there is no charge.")
    else:
        lines.append("- There is no charge for driving into the city centre today.")
    cars = [o for o in ctx.options if o.mode == "CAR" and o.depart_min is not None]
    if cars:
        prof = t.public_delay.get(p.corridor_id, ())
        if not prof:
            lines.append("- No information on yesterday's queues at your entry point is available.")
        else:
            parts = []
            for o in cars:
                parts.append(f"leaving {clock_str(o.depart_min)}: "
                             f"{_mins(_public_delay_at(ctx, o, cfg))}")
            lines.append("- Yesterday's queue at your entry point, by time of leaving home: "
                         + ", ".join(parts) + ".")
    if p.corridor_id in t.pt_disrupted_corridors and t.pt_disruption_announced \
            and any(o.mode == "PT" for o in ctx.options):
        lines.append(f"- Announcement: buses and trains from your area are disrupted today; "
                     f"trips take about {t.pt_disruption_time_mult:g} times as long as usual.")
    elif "T4" in ctx.triggers and p.corridor_id not in t.pt_disrupted_corridors \
            and any(o.mode == "PT" for o in ctx.options):
        lines.append("- Buses and trains from your area are running normally again today.")
    return lines


def you_pay_today(o: Option, persona: Persona) -> float | None:
    """Money the commuter pays for the day under an option (cl-v2 column "you pay today").

    CAR: road charge (0 when the employer pays it) + parking + fuel. PT: the fare. WFH: 0.
    SKIP: None (shown as "-"; postponing is not a money trade-off)."""
    if o.mode == "CAR":
        return round((0.0 if persona.company_car else float(o.fee)) + float(o.parking) + float(o.fuel), 2)
    if o.mode == "PT":
        return round(float(o.pt_fare or 0.0), 2)
    if o.mode == "WFH":
        return 0.0
    return None


def _options(ctx: DecisionContext, total: bool = False) -> list[str]:
    p = ctx.persona
    rows = []
    for o in ctx.options:
        what = {
            "CAR": "drive",
            "PT": "bus or train",
            "WFH": "work from home",
            "SKIP": "do not go into the city centre today",
        }.get(o.mode, o.mode.lower())
        trip = o.mode in ("CAR", "PT")
        if o.mode == "CAR":
            fee = _money(o.fee) + (" (employer pays)" if p.company_car and o.fee > 0 else "")
            cross = _clock(o.expected_gate_exit_min)
            queue = _mins(o.expected_delay_min)
            park = _money(o.parking)
            fuel = _money(o.fuel)
        else:
            fee, cross, queue, park, fuel = "-", "-", "-", "-", "-"
        rows.append([
            o.option_id, what,
            _clock(o.depart_min) if trip else "-",
            queue, cross,
            _mins(o.expected_travel_min) if trip else "-",
            _clock(o.start_used_min if o.start_used_min is not None else p.tstar_min) if trip else "-",
            f"{_clock(o.expected_arrive_min)} ({_early_late(o.early_min, o.late_min)})" if trip else "-",
            fee, park, fuel,
            _money(o.pt_fare) if (o.mode == "PT" and o.pt_fare is not None) else "-",
            "yes" if o.is_standing else "",
        ])
        if total:
            pay = you_pay_today(o, p)
            rows[-1].insert(len(rows[-1]) - 1, "-" if pay is None else _money(pay))
    header = ["option id", "what", "leave home", "expected queue", "cross into centre",
              "door to door", "start time", "expected arrival", "road charge", "parking", "fuel", "fare", "usual"]
    if total:
        header.insert(len(header) - 1, "you pay today")
    return _table(header, rows)


def render_user_prompt(ctx: DecisionContext, cfg: Config) -> str:
    """User message of template cl-v1. Deterministic; shows no GC and no archetype."""
    out = ["ABOUT YOUR SITUATION"]
    out += _situation(ctx, cfg)
    if ctx.traits_shown or cfg.llm.traits_off_prompt == "sentences":
        # traits off: the persona's traits are all at the off level, so the level-3 sentences
        # are shown, matching the rule's level-3 parameters (llm.traits_off_prompt = "omit"
        # drops the section instead, the v3 neutral cell).
        out += ["", "HOW YOU TEND TO DECIDE"]
        out += [f"- {s}" for s in _dispositions(ctx.persona)]
    out += ["", f"YOUR RECENT DAYS (up to {cfg.memory.window_days}, most recent last)"]
    out += _memory(ctx)
    out += ["", "TODAY"]
    out += _today(ctx, cfg)
    v2 = cfg.llm.template_id == TEMPLATE_V2
    out += ["", "OPTIONS (choose one option id)"]
    out += _options(ctx, total=v2)
    note = ("Times are clock times (hh:mm) and estimates for today; money is in NZ dollars. "
            "Early or late is measured against the start time shown for that option.")
    if v2:
        note += (" \"You pay today\" is the money you would pay for the day under that option (road "
                 "charge, parking and fuel, or the fare); it does not count your time.")
    out += ["", note]
    return "\n".join(line.rstrip() for line in out) + "\n"


# --------------------------------------------------------------------------------------------
# Schema, validation, keys
# --------------------------------------------------------------------------------------------

def factor_ids(ctx: DecisionContext) -> tuple[str, ...]:
    """cl-v2: the factor tags that can apply to this agent-day, in FACTORS_V2 order."""
    t, p = ctx.today, ctx.persona
    can_apply = {
        "road_charge": bool(t.fee_active or t.fee_changed_today),
        "routine": ctx.standing_option_id is not None,
        "bus_train_preference": any(o.mode == "PT" for o in ctx.options),
        "past_experience": bool(ctx.recent),
        "disruption": bool((p.corridor_id in t.pt_disrupted_corridors and t.pt_disruption_announced)
                           or "T4" in ctx.triggers or any(r.pt_disrupted for r in ctx.recent)),
    }
    return tuple(f for f in FACTORS_V2 if can_apply.get(f, True))


def reply_factors(parsed: dict) -> tuple[str, ...]:
    """Factor tags of a valid reply as a tuple: the cl-v1 list, or cl-v2 (main[, second])."""
    if "main_factor" in parsed:
        main, second = parsed["main_factor"], parsed.get("second_factor", NO_FACTOR)
        return (main,) if second in (NO_FACTOR, main) else (main, second)
    return tuple(parsed["factors"])


def output_schema(option_ids: Sequence[str], factors: Sequence[str] | None = None) -> dict:
    """JSON schema for one decision. Reason first, so it is written before the choice (v3 7.4).

    With ``factors`` (cl-v2, see factor_ids) the reply has main_factor and second_factor, each an
    enum of the given tags (second_factor also accepts "none"), instead of the cl-v1 list."""
    if factors is not None:
        return {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "main_factor": {"type": "string", "enum": list(factors)},
                "second_factor": {"type": "string", "enum": list(factors) + [NO_FACTOR]},
                "choice": {"type": "string", "enum": list(option_ids)},
            },
            "required": ["reason", "main_factor", "second_factor", "choice"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": {
            "reason": {"type": "string"},
            "factors": {"type": "array", "items": {"type": "string", "enum": list(FACTORS)}},
            "choice": {"type": "string", "enum": list(option_ids)},
        },
        "required": ["reason", "factors", "choice"],
        "additionalProperties": False,
    }


def validate_output(obj: object, option_ids: Sequence[str],
                    factors: Sequence[str] | None = None) -> tuple[bool, str]:
    """Check a parsed output against the schema of this agent-day (cl-v2 when ``factors`` is given)."""
    if not isinstance(obj, dict):
        return False, "output is not a JSON object"
    keys = set(obj)
    if factors is not None:
        if keys != {"choice", "reason", "main_factor", "second_factor"}:
            return False, f"keys {sorted(keys)} != ['choice', 'main_factor', 'reason', 'second_factor']"
        if not isinstance(obj["choice"], str) or obj["choice"] not in option_ids:
            return False, f"choice {obj['choice']!r} not in option ids"
        if not isinstance(obj["reason"], str) or not obj["reason"].strip():
            return False, "reason missing or empty"
        if obj["main_factor"] not in factors:
            return False, f"main_factor {obj['main_factor']!r} not offered"
        if obj["second_factor"] != NO_FACTOR and obj["second_factor"] not in factors:
            return False, f"second_factor {obj['second_factor']!r} not offered"
        return True, ""
    if keys != {"choice", "reason", "factors"}:
        return False, f"keys {sorted(keys)} != ['choice', 'factors', 'reason']"
    if not isinstance(obj["choice"], str) or obj["choice"] not in option_ids:
        return False, f"choice {obj['choice']!r} not in option ids"
    if not isinstance(obj["reason"], str) or not obj["reason"].strip():
        return False, "reason missing or empty"
    f = obj["factors"]
    if not isinstance(f, list) or any(not isinstance(x, str) or x not in FACTORS for x in f):
        return False, f"factors {f!r} invalid"
    return True, ""


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def prompt_sha256(system: str, user: str) -> str:
    """Hash of the full prompt (system + user)."""
    return _sha(system + "\n\n" + user)


def cache_key(model: str, effort: str | None, template_id: str, system: str, user: str,
              schema: dict, extra: dict | None = None) -> str:
    """sha256 over (model, effort, template id, system, user, schema with sorted keys).

    ``extra`` holds further request-shaping settings (max_tokens, fallback setting, replicate);
    it is appended only when given, so the specified key is unchanged without it."""
    parts: list[Any] = [model, effort, template_id, system, user, json.dumps(schema, sort_keys=True)]
    if extra:
        parts.append(json.dumps(extra, sort_keys=True))
    payload = json.dumps(parts, ensure_ascii=False)
    return _sha(payload)


# --------------------------------------------------------------------------------------------
# Disk cache
# --------------------------------------------------------------------------------------------

class LLMCache:
    """One JSON file per key under cache_dir/<key[:2]>/<key>.json. Only valid outputs are stored."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = Path(cache_dir)

    def _path(self, key: str) -> Path:
        return self.cache_dir / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict | None:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, key: str, record: dict) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)


# --------------------------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------------------------

_PART_FACTOR = {
    "time": "travel_time", "schedule": "arrival_time", "fee": "fee", "parking": "other",
    "fuel": "other", "pt": "pt", "wfh": "flexibility", "skip": "work_constraint", "habit": "habit",
}
_PART_FACTOR_V2 = {
    "time": "travel_time", "schedule": "arrival_time", "fee": "road_charge", "parking": "other_money",
    "fuel": "other_money", "pt": "bus_train_preference", "wfh": "flexibility", "skip": "constraint",
    "habit": "routine",
}
_FACTOR_TEXT = {
    "travel_time": "travel time", "arrival_time": "arrival time", "fee": "the charge",
    "other": "parking or fuel cost", "pt": "the bus or train", "flexibility": "working from home",
    "work_constraint": "the day's commitments", "habit": "my routine",
}


def _empty_usage() -> dict:
    return {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0}


class MockLLM:
    """Deterministic stand-in, NOT an LLM: argmin of re-weighted GC parts plus Gumbel noise
    seeded by sha256 of the prompt; templated reason naming the main factor."""

    backend = "mock"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.model = MOCK_MODEL
        self.effort = None
        m = cfg.llm.mock
        self.weights = {"time": m.w_time, "schedule": m.w_schedule, "fee": m.w_fee,
                        "parking": m.w_parking, "fuel": m.w_fuel, "pt": m.w_pt, "wfh": m.w_wfh, "skip": m.w_skip,
                        "habit": m.w_habit}

    def _score(self, o: Option) -> dict[str, float]:
        return {k: self.weights.get(k, 1.0) * float(v) for k, v in o.gc_parts.items()}

    def complete(self, system: str, user: str, schema: dict, ctx: DecisionContext) -> dict:
        ids = schema["properties"]["choice"]["enum"]
        opts = [ctx.option(i) for i in ids]
        rep = int(self.cfg.llm.replicate)
        seed = int(prompt_sha256(system, user + (f"\n#replicate {rep}" if rep > 0 else ""))[:16], 16)
        rng = np.random.default_rng(seed)
        noise = rng.gumbel(0.0, self.cfg.llm.mock.noise_sigma, len(opts)) \
            if self.cfg.llm.mock.noise_sigma > 0 else np.zeros(len(opts))
        scored = [self._score(o) for o in opts]
        totals = [sum(s.values()) + float(e) for s, e in zip(scored, noise)]
        k = int(np.argmin(totals))
        chosen = scored[k]
        others = [s for j, s in enumerate(scored) if j != k]
        factor = "other"
        part = None
        if others:
            parts = sorted({p for s in scored for p in s})
            adv = {p: float(np.mean([s.get(p, 0.0) for s in others])) - chosen.get(p, 0.0)
                   for p in parts}
            best = max(parts, key=lambda p: (round(adv[p], 9), -parts.index(p)))
            if adv[best] > 0:
                part = best
                factor = _PART_FACTOR.get(best, "other")
        text = _FACTOR_TEXT.get(factor, "overall cost")
        reason = f"[mock] I chose {opts[k].option_id} mainly because of {text}."
        if "main_factor" in schema["properties"]:   # cl-v2 reply shape
            offered = schema["properties"]["main_factor"]["enum"]
            main = _PART_FACTOR_V2.get(part or "", "other")
            return {"reason": reason, "main_factor": main if main in offered else "other",
                    "second_factor": NO_FACTOR, "choice": opts[k].option_id}
        return {"reason": reason, "factors": [factor], "choice": opts[k].option_id}


class LLMFatalError(RuntimeError):
    """An error that would hit every call (credentials, permission, unknown model, billing, or a
    run of consecutive API errors). The run stops instead of silently becoming a rule run."""


class AnthropicLLM:
    """Claude via the official SDK (AsyncAnthropic), structured outputs, refusal handling.

    Transport retries (429, 5xx, connection errors) are left to the SDK client
    (``max_retries = llm.max_retries``); this class makes exactly one request per call."""

    backend = "anthropic"

    def __init__(self, cfg: Config, client: object | None = None) -> None:
        self.cfg = cfg
        self.model = cfg.llm.model
        self.effort = None if self.model in NO_EFFORT_MODELS else cfg.llm.effort
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(max_retries=self.cfg.llm.max_retries)
        return self._client

    @property
    def uses_beta(self) -> bool:
        return bool(self.cfg.llm.use_fallbacks) and self.model in FALLBACK_MODELS

    def key_extra(self) -> dict:
        """Request-shaping settings outside the prompt, added to the cache key."""
        ex: dict[str, Any] = {"max_tokens": int(self.cfg.llm.max_tokens),
                              "fallbacks": ("default", self.cfg.llm.fallback_beta) if self.uses_beta else None}
        if self.cfg.llm.replicate > 0:
            ex["replicate"] = int(self.cfg.llm.replicate)
        return ex

    def build_request(self, system: str, user: str, schema: dict) -> dict:
        """Keyword arguments for messages.create (or beta.messages.create when fallbacks are on)."""
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
        if self.effort is not None:
            output_config = {"effort": self.effort, **output_config}
        req: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.cfg.llm.max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}],
            "output_config": output_config,
        }
        if self.uses_beta:
            req["betas"] = [self.cfg.llm.fallback_beta]
            req["fallbacks"] = "default"
        return req

    async def acomplete(self, system: str, user: str, schema: dict) -> tuple[dict | None, dict]:
        """One request. Returns (parsed JSON or None, call meta).

        meta["error_kind"]: None (parsed), "fatal" (401, 402, 403, 404 or missing credentials:
        every call would fail), "api" (another API or transport error, after the SDK's own
        retries), "refusal" (stop_reason refusal, after the server-side fallback), "invalid" (no
        text block, truncated or unparsable JSON)."""
        import anthropic

        req = self.build_request(system, user, schema)
        meta: dict[str, Any] = {"raw_text": None, "error": None, "error_kind": None, "stop_reason": None,
                                "refusal_category": None, "usage": _empty_usage(),
                                "latency_s": None, "model_served": None, "request_id": None}
        t0 = time.perf_counter()
        resp = None
        try:
            create = self.client.beta.messages.create if self.uses_beta else self.client.messages.create
            resp = await create(**req)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                anthropic.NotFoundError) as e:                       # 401, 403, 404: stop the run
            meta["error"], meta["error_kind"] = f"{type(e).__name__} {e.status_code}: {e.message}", "fatal"
        except anthropic.BadRequestError as e:                        # 400: not retried
            meta["error"], meta["error_kind"] = f"BadRequestError: {e.message}", "api"
        except anthropic.RateLimitError as e:                         # 429 after the SDK's retries
            meta["error"], meta["error_kind"] = f"RateLimitError: {e.message}", "api"
        except anthropic.APIStatusError as e:                         # 5xx after SDK retries, other 4xx
            meta["error"] = f"APIStatusError {e.status_code}: {e.message}"
            meta["error_kind"] = "fatal" if e.status_code == 402 else "api"   # 402 billing
        except anthropic.APIConnectionError as e:                     # network, after SDK retries
            meta["error"], meta["error_kind"] = f"APIConnectionError: {e}", "api"
        except Exception as e:  # noqa: BLE001 - malformed body, missing credentials, SDK bugs
            msg = f"{type(e).__name__}: {e}"
            meta["error"] = msg
            meta["error_kind"] = "fatal" if "authentication" in msg.lower() else "api"
        meta["latency_s"] = round(time.perf_counter() - t0, 3)
        if resp is None:
            return None, meta
        meta["stop_reason"] = getattr(resp, "stop_reason", None)
        meta["model_served"] = getattr(resp, "model", None)
        meta["request_id"] = getattr(resp, "_request_id", None)
        u = getattr(resp, "usage", None)
        if u is not None:
            meta["usage"] = {k: int(getattr(u, k, 0) or 0) for k in _empty_usage()}
        if meta["stop_reason"] == "refusal":
            details = getattr(resp, "stop_details", None)
            meta["refusal_category"] = getattr(details, "category", None) if details else None
            meta["error"], meta["error_kind"] = "refusal", "refusal"
            return None, meta
        text = next((b.text for b in (getattr(resp, "content", None) or [])
                     if getattr(b, "type", None) == "text"), None)
        meta["raw_text"] = text
        if text is None:
            meta["error"] = f"no text block (stop_reason={meta['stop_reason']})"
            meta["error_kind"] = "invalid"
            return None, meta
        try:
            return json.loads(text), meta
        except json.JSONDecodeError as e:
            meta["error"] = f"invalid JSON: {e.msg} (stop_reason={meta['stop_reason']})"
            meta["error_kind"] = "invalid"
            return None, meta


# --------------------------------------------------------------------------------------------
# Decider
# --------------------------------------------------------------------------------------------

class LLMDecider:
    """Decider that asks an LLM backend; invalid output -> retry, then the fallback decider.

    Retry policy: only an invalid output (unparsable JSON, truncation, choice not in the option
    ids, schema mismatch) is resent, up to llm.invalid_output_retries times. API errors are not
    retried here (the SDK has already retried transport errors); refusals are not resent (the
    server-side fallback has already run). Both go straight to the rule fallback.

    Fatal errors (see AnthropicLLM.acomplete) and llm.max_consecutive_errors API errors in a row
    raise LLMFatalError. Every call record is appended to llm_calls.jsonl as soon as it completes,
    so paid calls are logged even when the run stops.

    Identical prompts (same cache key) within one morning are sent once and the answer is shared;
    the other agents get a record with shared = true (v3 7.5: agents share an answer only if every
    rendered line is identical). This keeps a live run and its cache replay identical."""

    name = "llm"

    def __init__(self, cfg: Config, backend: MockLLM | AnthropicLLM, fallback: Decider,
                 log_path: Path, cache: LLMCache | None) -> None:
        self.cfg = cfg
        self.backend = backend
        self.fallback = fallback
        self.log_path = Path(log_path)
        self.cache = cache
        self.system = system_prompt(cfg)
        self.template_id = cfg.llm.template_id
        self.v2 = self.template_id == TEMPLATE_V2
        self.key_extra = backend.key_extra() if hasattr(backend, "key_extra") else (
            {"replicate": int(cfg.llm.replicate)} if cfg.llm.replicate > 0 else None)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._consecutive_errors = 0
        self._aborted: str | None = None
        self.stats = {"n_contexts": 0, "n_calls": 0, "n_cache_hits": 0, "n_shared": 0, "n_invalid": 0,
                      "n_api_errors": 0, "n_refusals": 0, "n_fallback": 0, "prompt_chars": 0,
                      "input_tokens": 0, "output_tokens": 0,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}

    # one persistent loop: the async HTTP client must not move between event loops
    def _run(self, coro: Any) -> Any:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        return self._loop.run_until_complete(coro)

    def close(self) -> None:
        if self._loop is not None and not self._loop.is_closed():
            client = getattr(self.backend, "_client", None)
            if client is not None and hasattr(client, "close"):
                try:
                    self._loop.run_until_complete(client.close())
                except Exception:  # noqa: BLE001 - best effort on shutdown
                    pass
            self._loop.close()

    def _log(self, rec: dict) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")

    def _key(self, user: str, schema: dict) -> str:
        return cache_key(self.backend.model, self.backend.effort, self.template_id, self.system,
                         user, schema, self.key_extra)

    def _validate(self, parsed: object, ids: Sequence[str], schema: dict) -> tuple[bool, str]:
        """Validity of one parsed reply (a hook: the plan template in planner.py has its own check)."""
        offered = schema["properties"]["main_factor"]["enum"] if self.v2 else None
        return validate_output(parsed, ids, offered)

    async def _one(self, ctx: DecisionContext, user: str, schema: dict, key: str,
                   sem: asyncio.Semaphore) -> tuple[dict | None, list[dict]]:
        ids = list(ctx.option_ids)
        records: list[dict] = []
        parsed_ok: dict | None = None
        n_attempts = 1 + max(0, self.cfg.llm.invalid_output_retries)
        for attempt in range(n_attempts):
            hit = self.cache.get(key) if (self.cache is not None and attempt == 0) else None
            if hit is not None:
                parsed, meta = hit.get("parsed"), {
                    "raw_text": hit.get("raw_text"), "error": None, "error_kind": None,
                    "stop_reason": hit.get("stop_reason"), "refusal_category": None,
                    "usage": _empty_usage(), "latency_s": 0.0,
                    "model_served": hit.get("model_served"), "request_id": hit.get("request_id")}
            elif isinstance(self.backend, MockLLM):
                parsed = self.backend.complete(self.system, user, schema, ctx)
                meta = {"raw_text": json.dumps(parsed, ensure_ascii=False), "error": None,
                        "error_kind": None, "stop_reason": "end_turn", "refusal_category": None,
                        "usage": _empty_usage(), "latency_s": None,
                        "model_served": MOCK_MODEL, "request_id": None}
            else:
                async with sem:
                    if self._aborted is not None:   # another call of this batch stopped the run
                        raise LLMFatalError(self._aborted)
                    parsed, meta = await self.backend.acomplete(self.system, user, schema)
            offered = schema["properties"]["main_factor"]["enum"] if self.v2 else None
            valid, why = (self._validate(parsed, ids, schema) if parsed is not None
                          else (False, meta.get("error") or "no output"))
            if parsed is not None and not valid:
                meta["error"], meta["error_kind"] = why, "invalid"
            rec = {
                "call_id": f"d{ctx.day:02d}-a{ctx.agent_id:05d}-{attempt}",
                "day": ctx.day, "agent_id": ctx.agent_id, "triggers": list(ctx.triggers),
                "backend": self.backend.backend, "model": self.backend.model,
                "effort": self.backend.effort, "template_id": self.template_id, "cache_key": key,
                "cache_hit": hit is not None, "shared": False, "shared_from": None,
                "system_sha256": _sha(self.system), "user": user,
                "schema_option_ids": ids, "raw_text": meta.get("raw_text"), "parsed": parsed,
                "valid": valid, "error": meta.get("error"), "error_kind": meta.get("error_kind"),
                "stop_reason": meta.get("stop_reason"),
                "refusal_category": meta.get("refusal_category"),
                "usage": meta.get("usage", _empty_usage()), "latency_s": meta.get("latency_s"),
                "model_served": meta.get("model_served"), "request_id": meta.get("request_id"),
                "attempt": attempt,
            }
            if offered is not None:
                rec["schema_factor_ids"] = list(offered)
            records.append(rec)
            self._log(rec)
            kind = meta.get("error_kind")
            if valid:
                self._consecutive_errors = 0
                parsed_ok = parsed
                if self.cache is not None and hit is None:
                    self.cache.put(key, {
                        "key": key, "model": self.backend.model, "effort": self.backend.effort,
                        "template_id": self.template_id, "key_extra": self.key_extra, "parsed": parsed,
                        "raw_text": meta.get("raw_text"), "usage": meta.get("usage"),
                        "stop_reason": meta.get("stop_reason"),
                        "model_served": meta.get("model_served"),
                        "request_id": meta.get("request_id"), "latency_s": meta.get("latency_s")})
                break
            if kind == "fatal":
                self._aborted = ("LLM call failed with a non-recoverable error, run stopped: "
                                 f"{meta.get('error')}")
                raise LLMFatalError(self._aborted)
            if kind == "api":
                self._consecutive_errors += 1
                limit = int(self.cfg.llm.max_consecutive_errors)
                if limit > 0 and self._consecutive_errors >= limit:
                    self._aborted = (f"{self._consecutive_errors} consecutive LLM API errors, run "
                                     f"stopped; last: {meta.get('error')}")
                    raise LLMFatalError(self._aborted)
                break                      # transport retries belong to the SDK
            self._consecutive_errors = 0   # a response arrived
            if kind == "refusal":
                break                      # the server-side fallback has already run
        return parsed_ok, records

    async def _gather(self, items: list[tuple[DecisionContext, str, dict, str]]) -> list:
        sem = asyncio.Semaphore(max(1, self.cfg.llm.max_concurrency))
        tasks = [asyncio.ensure_future(self._one(c, u, s, k, sem)) for c, u, s, k in items]
        try:
            return await asyncio.gather(*tasks)
        except BaseException:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    def decide_batch(self, contexts: Sequence[DecisionContext]) -> list[Decision]:
        """Decide for every context (order preserved); log every call to llm_calls.jsonl."""
        if not contexts:
            return []
        items = []
        first: dict[str, int] = {}
        for i, ctx in enumerate(contexts):
            user = render_user_prompt(ctx, self.cfg)
            schema = output_schema(ctx.option_ids, factor_ids(ctx) if self.v2 else None)
            key = self._key(user, schema)
            first.setdefault(key, i)
            items.append((ctx, user, schema, key))
        uniq = sorted(set(first.values()))
        res_u = self._run(self._gather([items[i] for i in uniq]))
        by_i = dict(zip(uniq, res_u))
        results: list[tuple[dict | None, list[dict]]] = []
        for i, (ctx, _user, _schema, key) in enumerate(items):
            if i in by_i:
                results.append(by_i[i])
                continue
            parsed, recs = by_i[first[key]]
            src = recs[-1]
            rec = dict(src, call_id=f"d{ctx.day:02d}-a{ctx.agent_id:05d}-s", day=ctx.day,
                       agent_id=ctx.agent_id, triggers=list(ctx.triggers), cache_hit=False,
                       shared=True, shared_from=src["call_id"], usage=_empty_usage(),
                       latency_s=None, attempt=0)
            self._log(rec)
            results.append((parsed, [rec]))

        decisions: list[Decision | None] = []
        metas: list[dict] = []
        need_fb: list[int] = []
        for i, ((ctx, user, _schema, _key), (parsed, recs)) in enumerate(zip(items, results)):
            self.stats["n_contexts"] += 1
            self.stats["prompt_chars"] += len(self.system) + len(user)
            for r in recs:
                real = not (r["cache_hit"] or r["shared"])
                self.stats["n_calls"] += 1 if real else 0
                self.stats["n_cache_hits"] += 1 if r["cache_hit"] else 0
                self.stats["n_shared"] += 1 if r["shared"] else 0
                if real:
                    self.stats["n_invalid"] += 1 if r["error_kind"] == "invalid" else 0
                    self.stats["n_api_errors"] += 1 if r["error_kind"] in ("api", "fatal") else 0
                    self.stats["n_refusals"] += 1 if r["error_kind"] == "refusal" else 0
                for k in _empty_usage():
                    self.stats[k] += int(r["usage"].get(k, 0) or 0)
            meta = {"backend": self.backend.backend, "model": self.backend.model,
                    "cache_hit": bool(recs and recs[-1]["cache_hit"]),
                    "shared": bool(recs and recs[-1]["shared"]),
                    "prompt_sha256": prompt_sha256(self.system, user),
                    "call_id": recs[-1]["call_id"] if recs else None, "attempts": len(recs)}
            if parsed is None:
                decisions.append(None)
                need_fb.append(i)
                meta["error"] = recs[-1]["error"] if recs else "no call"
            else:
                decisions.append(Decision(
                    agent_id=ctx.agent_id, day=ctx.day, option_id=parsed["choice"],
                    decider="llm", reason=parsed["reason"].strip(),
                    factors=reply_factors(parsed), meta=meta))
            metas.append(meta)
        if need_fb:
            self.stats["n_fallback"] += len(need_fb)
            fb = self.fallback.decide_batch([items[i][0] for i in need_fb])
            for i, d in zip(need_fb, fb):
                m = dict(d.meta)
                m.update(metas[i])
                decisions[i] = replace(d, decider="llm-fallback-rule", meta=m)
        return [d for d in decisions if d is not None]


def make_llm_decider(cfg: Config, run_dir: Path, fallback: Decider,
                     backend: str | None = None) -> LLMDecider:
    """LLMDecider writing run_dir/llm_calls.jsonl. The disk cache is used for the anthropic
    backend only (MockLLM is deterministic; caching it would make logs differ between runs)."""
    kind = backend or cfg.run.backend
    if kind == "mock":
        be: MockLLM | AnthropicLLM = MockLLM(cfg)
        cache = None
    elif kind == "anthropic":
        be = AnthropicLLM(cfg)
        cache = LLMCache(cfg.resolve_path(cfg.llm.cache_dir))
    else:
        raise ValueError(f"unknown LLM backend {kind!r}")
    return LLMDecider(cfg, be, fallback, Path(run_dir) / "llm_calls.jsonl", cache)


def estimate_tokens(prompts: Sequence[str]) -> dict:
    """Approximate token count of a set of prompts: characters / 4 (clearly approximate)."""
    chars = int(sum(len(p) for p in prompts))
    return {"n_calls": len(prompts), "prompt_chars": chars,
            "approx_tokens": int(math.ceil(chars / 4)),
            "note": "approximate: characters / 4, input only, excludes schema and output"}
