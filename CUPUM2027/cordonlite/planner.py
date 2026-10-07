"""Hybrid decider for arm H-clock: the LLM plans, the model chooses the minute.

What the LLM decides is a PLAN: how the commuter travels from now on (drive, drive and work the
earlier day, bus or train, work from home), optionally a second choice on some days of the week,
what to do when buses and trains are disrupted, what would make them think again, and whether the
plan is a trial with a review date. The model then chooses the departure inside the plan's choice
for the day: the one with the lowest generalised cost (the rule's cost function without its random
term, see HybridDecider._pick). A one-off day (a disruption the plan does not cover) gets a "today"
call that leaves the plan as it is. The rule decider itself is used only as the fallback when the
LLM gives no valid answer.

Who answers on a given morning (HybridDecider.decide_batch):
    no plan yet (day 1)                                   LLM, task "routine"
    charge starts or changes (T2), plan involves driving,
        and the commuter pays the charge                  LLM, task "change"
    review date set by a trial plan reached               LLM, task "change"
    a would_reconsider_if condition of the plan is met    LLM, task "change"
    bus or train disrupted today, plan has no answer      LLM, task "today"
    bus or train disrupted today, plan has an answer      the plan's contingency (no call)
    late yesterday (T3) or car time changed (T5)          rule, inside today's choice
    anything else                                         the plan (same departure as last time)

Template "plan-v1" uses only facts the model already has (Persona, memory, today's information).
The prompt shows one row per choice with the departure the model would pick today, and every money
figure is already summed per day and per week. The generalised cost is never shown.

Assumptions [A] (author decisions 2026-10-08, not calibrated):
    - a week is 5 consecutive simulated days; "n days a week on the second choice" uses fixed
      weekday positions (OTHER_DAYS), so a mixed plan is deterministic;
    - a trial plan is reviewed once, review_after_days after it was made;
    - "late twice in a week" counts late days among the recent days in memory (memory.window_days).

Outputs: llm_calls.jsonl (every LLM call, as in llm.py) and plan_log.jsonl (one line per
agent-day: who answered, today's choice, the option, and the plan whenever it changed).

Public API:
    STRATEGIES, PLAN_STRATEGIES, strategy_of(option), by_strategy(options)
    Plan, strategy_on(plan, day)
    render_plan_prompt(ctx, task, picks, plan, why, cfg) -> str
    plan_schema(task, picks, ctx) -> dict; validate_reply(obj, schema) -> (bool, str)
    PlanMock, PlanLLM, HybridDecider, make_hybrid_decider(cfg, run_dir, rule, backend=None)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from cordonlite import llm as L
from cordonlite.config import Config
from cordonlite.options import early_start_for
from cordonlite.rules import explain
from cordonlite.types import Decider, Decision, DecisionContext, Option, Persona, clock_str

# plan-v2 (the default for H-clock) states four quantities the base model already holds in the words a
# person would use; plan-v1 (llm.template_id = "plan-v1") is the same prompt without them. No new fact
# about a commuter is introduced: both arms see the same agents.
#   - value of time: "Ten minutes of your time is worth about NZ$x" (VoT / 6) instead of NZ$/h;
#   - bus or train: the 10 min of walking and waiting inside its time, and the 10-min headway;
#   - bus or train reluctance: what the rule adds to that option beyond its fare and its time at the
#     commuter's own value of time, omega(P) x PAP + (omega(P) - 1) x VoT/60 x T_pt (bus_reluctance);
#   - working from home: the rule's cost of a day at home (the "wfh" part of its generalised cost);
#   - the earlier working day: the rule's inconvenience cost, costs.early_shift_cost x phi(F).
# The second pair are the two scalars the rule arm was calibrated with (costs.pt_attitude_penalty,
# costs.wfh_cost), so wording them carries that calibration to the LLM arm.
PLAN_TEMPLATE_ID = "plan-v2"
PLAN_TEMPLATES: tuple[str, ...] = ("plan-v1", "plan-v2")
STRATEGIES: tuple[str, ...] = ("drive", "drive_early_day", "bus_or_train", "work_from_home", "stay_home_today")
PLAN_STRATEGIES: tuple[str, ...] = STRATEGIES[:4]          # stay_home_today is a one-off, never a plan
DRIVING: frozenset[str] = frozenset({"drive", "drive_early_day"})
NONE = "none"
RECONSIDER: tuple[str, ...] = ("late_twice_in_a_week", "trip_much_longer_or_shorter", "nothing_in_particular")
BUS_DISRUPTED: tuple[str, ...] = ("bus_anyway",) + PLAN_STRATEGIES[:2] + ("work_from_home", "stay_home_today",
                                                                         "not_applicable")
OTHER_DAYS: dict[int, tuple[int, ...]] = {0: (), 1: (2,), 2: (1, 3), 3: (0, 2, 4), 4: (0, 1, 3, 4)}
WEEK = 5

PLAN_SYSTEM = (
    "You are helping build a traffic simulation by answering as one ordinary commuter to Auckland "
    "city centre. You are told about this person's circumstances, how they tend to decide, what "
    "they do now and what is new.\n"
    "Say what this person would most plausibly do, not what would be best or cheapest. People weigh "
    "money, time, hassle, routine and the things their day has to fit around, and different people "
    "weigh them differently. Staying with a routine that is not the cheapest is a valid answer when "
    "their situation or tendencies point that way; so is changing.\n"
    "Use only what you are told. Do not rely on demographic or occupational stereotypes. All sums "
    "are done for you: use the figures as given.\n"
    "You choose how this person travels, not the exact minute they leave: the simulation works out "
    "each morning's departure from your answer, and the times shown are the ones it would pick "
    "today.\n"
    "Write in_their_words in the first person, in at most 40 words.\n"
) + L.FACTOR_DEFINITIONS


# --------------------------------------------------------------------------------------------
# Strategies and plans
# --------------------------------------------------------------------------------------------

def strategy_of(o: Option) -> str:
    """The choice an option belongs to."""
    if o.mode == "CAR":
        return "drive_early_day" if o.early_shift else "drive"
    return {"PT": "bus_or_train", "WFH": "work_from_home", "SKIP": "stay_home_today"}[o.mode]


def by_strategy(options: Sequence[Option]) -> dict[str, tuple[Option, ...]]:
    """Today's options grouped by choice, in STRATEGIES order."""
    groups: dict[str, list[Option]] = {}
    for o in options:
        groups.setdefault(strategy_of(o), []).append(o)
    return {s: tuple(groups[s]) for s in STRATEGIES if s in groups}


@dataclass
class Plan:
    """A commuter's standing plan (state kept by HybridDecider between days)."""

    usual: str
    other: str | None = None
    other_days: int = 0                        # days per 5-day week on ``other``
    if_bus_disrupted: str = "not_applicable"
    reconsider: tuple[str, ...] = ()
    review_day: int | None = None              # day of the single review of a trial plan
    settled: str = "firm"
    made_on: int = 0
    words: str = ""
    slots: dict[str, str] = field(default_factory=dict)   # choice -> option id last used

    def uses_car(self) -> bool:
        return self.usual in DRIVING or (self.other in DRIVING and self.other_days > 0)

    def public(self) -> dict:
        d = asdict(self)
        d.pop("slots")
        return d


def strategy_on(plan: Plan, day: int) -> str:
    """The plan's choice on a simulated day (weekday position = (day - 1) mod 5)."""
    if plan.other and (day - 1) % WEEK in OTHER_DAYS.get(int(plan.other_days), ()):
        return plan.other
    return plan.usual


def _bus_disrupted_today(ctx: DecisionContext) -> bool:
    t = ctx.today
    return bool(t.pt_disruption_announced and ctx.persona.corridor_id in t.pt_disrupted_corridors)


# --------------------------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------------------------

def plan_template(cfg: Config) -> str:
    """Template used by H-clock: "plan-v1" when asked for, otherwise "plan-v2"."""
    return "plan-v1" if cfg.llm.template_id == "plan-v1" else PLAN_TEMPLATE_ID


def bus_reluctance(persona: Persona, omega: float, cfg: Config) -> float:
    """NZ$ a day the rule adds to the bus or train beyond its fare and its travel time valued at the
    commuter's own value of time: omega x PAP + (omega - 1) x VoT/60 x T_pt (undisrupted)."""
    return (omega * float(cfg.costs.pt_attitude_penalty)
            + (omega - 1.0) * persona.vot / 60.0 * float(persona.pt_time_min))


def _situation(ctx: DecisionContext, cfg: Config) -> list[str]:
    """cl-v1's situation lines without its last one ("usual choice"); plan-v2 rewords three of them."""
    lines = L._situation(ctx, cfg)[:-1]
    if plan_template(cfg) == "plan-v1":
        return lines
    p = ctx.persona
    wfh = next((o for o in ctx.options if o.mode == "WFH"), None)
    out = []
    for ln in lines:
        if ln.startswith("- A bus or train is available from your area:"):
            ln += f" About {int(round(cfg.costs.pt_access_min))} min of that is walking and waiting"
            ln += (f", and a service runs every {int(cfg.costs.pt_headway_min)} min."
                   if cfg.costs.pt_headway_min > 0 else ".")
        elif ln.startswith("- Your time is worth about"):
            ln = f"- Ten minutes of your time is worth about {L._money(p.vot / 6.0)} to you."
        elif ln.startswith("- Your employer lets you work"):
            ln += (" Working those hours is an inconvenience you would value at about "
                   f"{L._money(float(cfg.costs.early_shift_cost) * ctx.params.phi)} a day.")
        elif ln.startswith("- You can do your day's work from home") and wfh is not None:
            ln += (" A day at home has drawbacks for you, though, which you would value at about "
                   f"NZ${wfh.gc_parts['wfh']:.0f}.")
        out.append(ln)
    return out


def _tendencies(ctx: DecisionContext, cfg: Config) -> list[str]:
    """The four disposition sentences; plan-v2 adds the bus or train reluctance in dollars a day."""
    lines = list(L._dispositions(ctx.persona))
    if plan_template(cfg) != "plan-v1" and any(o.mode == "PT" for o in ctx.options):
        x = bus_reluctance(ctx.persona, ctx.params.omega, cfg)
        lines[2] += (" Leaving aside its fare and its travel time, taking a bus or train rather than driving "
                     f"is a nuisance you would pay about NZ${x:.0f} a day to avoid." if x >= 0.5 else
                     " Leaving aside its fare and its travel time, you find a bus or train about as "
                     "agreeable as driving.")
    return lines


def _phrase(s: str, persona: Persona, cfg: Config) -> str:
    # neutral wording: no choice is called "usual", so the first day does not read as an existing routine
    if s == "drive_early_day":
        es = early_start_for(persona, cfg) or int(cfg.costs.early_start_min)
        return f"drive in and work {clock_str(es)} to {clock_str(es + 480)}"
    return {"drive": f"drive in for your {clock_str(persona.tstar_min)} start",
            "bus_or_train": "take the bus or train",
            "work_from_home": "work from home", "stay_home_today": "do not go in today"}[s]


def _pay(o: Option, persona: Persona) -> float:
    return float(L.you_pay_today(o, persona) or 0.0)


def _record_cost(r: Any, persona: Persona) -> float:
    if r.mode == "CAR":
        return (0.0 if persona.company_car else float(r.fee_paid)) + persona.parking_cost + persona.fuel_cost
    return float(persona.pt_fare) if r.mode == "PT" else 0.0


def _record_strategy(r: Any) -> str:
    if r.mode == "CAR":
        return "drive_early_day" if r.early_shift else "drive"
    return {"PT": "bus_or_train", "WFH": "work_from_home", "SKIP": "stay_home_today"}[r.mode]


def weekly_cost_now(ctx: DecisionContext, plan: Plan, picks: Mapping[str, Option]) -> float:
    """Money per 5-day week under the current plan at what the commuter last paid for each choice."""
    def cost(s: str) -> float:
        for r in reversed(ctx.recent):
            if _record_strategy(r) == s:
                return _record_cost(r, ctx.persona)
        return _pay(picks[s], ctx.persona) if s in picks else 0.0
    k = int(plan.other_days) if plan.other else 0
    return (WEEK - k) * cost(plan.usual) + (k * cost(plan.other) if plan.other else 0.0)


def _diff(x: float) -> str:
    if abs(x) < 0.005:
        return "the same"
    return f"{L._money(abs(x))} {'more' if x > 0 else 'less'}"


def _choices(ctx: DecisionContext, picks: Mapping[str, Option], week_now: float | None,
             cfg: Config, weekly: bool = True) -> list[str]:
    p = ctx.persona
    header = ["choice", "what it is", "leave home", "door to door", "arrive",
              "you pay each day" if weekly else "you pay today"]
    if weekly:
        header += ["each week, compared with now"] if week_now is not None else ["you pay each week"]
    rows = []
    for s, o in picks.items():
        trip = o.mode in ("CAR", "PT")
        if s == "stay_home_today":
            pay_day = week = "-"
        else:
            pay = _pay(o, p)
            pay_day = L._money(pay)
            week = _diff(WEEK * pay - week_now) if week_now is not None else L._money(WEEK * pay)
        start = o.start_used_min if o.start_used_min is not None else p.tstar_min
        rows.append([
            s, _phrase(s, p, cfg),
            L._clock(o.depart_min) if trip else "-",
            L._mins(o.expected_travel_min) if trip else "-",
            f"{L._clock(o.expected_arrive_min)} ({L._early_late(o.early_min, o.late_min)} for a "
            f"{clock_str(start)} start)" if trip else "-",
            pay_day,
        ] + ([week] if weekly else []))
    return L._table(header, rows)


def _now(ctx: DecisionContext, plan: Plan, picks: Mapping[str, Option], week_now: float,
         cfg: Config) -> list[str]:
    p = ctx.persona

    def leaving(s: str) -> str:
        # the departure the commuter has been using (plan.slots), not the one the model would pick today
        o = next((x for x in ctx.options if x.option_id == plan.slots.get(s)), None) or picks.get(s)
        return f", leaving about {clock_str(o.depart_min)}" if (o and o.depart_min is not None) else ""

    if plan.other and plan.other_days > 0:
        k = int(plan.other_days)
        lines = [f"- On {WEEK - k} day{'s' if WEEK - k != 1 else ''} a week you "
                 f"{_phrase(plan.usual, p, cfg)}{leaving(plan.usual)}.",
                 f"- On the other {k} you {_phrase(plan.other, p, cfg)}{leaving(plan.other)}."]
    else:
        lines = [f"- You {_phrase(plan.usual, p, cfg)}{leaving(plan.usual)}."]
    lines.append(f"- This costs you about {L._money(week_now)} a week.")
    recs = [r for r in ctx.recent if r.mode in ("CAR", "PT")]
    if recs:
        late = sum(1 for r in recs if r.late_min > 0)
        cars = [r for r in recs if r.mode == "CAR" and r.queue_delay_min is not None and r.queue_delay_min >= 0]
        seen = f"- On your last {len(recs)} trip{'s' if len(recs) != 1 else ''} you were late {late} time{'s' if late != 1 else ''}"
        if cars:
            seen += f", and the queue at your entry point was about {L._mins(float(np.mean([r.queue_delay_min for r in cars])))}"
        lines.append(seen + ".")
    if plan.words:
        lines.append(f"- When you settled on this (day {plan.made_on}) you said: \"{plan.words}\"")
    return lines


def _news(ctx: DecisionContext, why: str, cfg: Config) -> list[str]:
    skip = ("- Yesterday's queue at your entry point", "- No information on yesterday's queues")
    lines = [ln for ln in L._today(ctx, cfg) if not ln.startswith(skip)]
    extra = {
        "review": "- You said you would try your plan and then look at it again. That time has come.",
        "late": "- You have been late more than once lately.",
        "trip": "- Your drive has lately taken clearly longer or shorter than you expected.",
    }.get(why)
    return lines + ([extra] if extra else [])


def render_plan_prompt(ctx: DecisionContext, task: str, picks: Mapping[str, Option], plan: Plan | None,
                       why: str, cfg: Config) -> str:
    """User message of template plan-v1. ``task``: "routine", "change" or "today"."""
    out = ["ABOUT YOUR SITUATION"] + _situation(ctx, cfg)
    if plan is None:
        out.append("- You have not settled on a usual way of making this trip yet.")
    if ctx.traits_shown or cfg.llm.traits_off_prompt == "sentences":
        out += ["", "HOW YOU TEND TO DECIDE"] + [f"- {s}" for s in _tendencies(ctx, cfg)]
    week_now = None
    if plan is not None:
        week_now = weekly_cost_now(ctx, plan, picks)
        out += ["", "WHAT YOU DO NOW"] + _now(ctx, plan, picks, week_now, cfg)
    out += ["", "TODAY"] + _news(ctx, why, cfg)
    note = ("Times are clock times (hh:mm) and estimates for today; money is in NZ dollars and counts the "
            "road charge you pay, parking and fuel, or the fare; it does not count your time.")
    if task == "today":
        out += ["", "YOUR CHOICES FOR TODAY"] + _choices(ctx, picks, None, cfg, weekly=False)
        out += ["", "Choose what you do today only (today_choice). Your usual plan stays as it is. If you "
                    "would do the same whenever buses and trains are disrupted, say so in add_to_plan."]
    else:
        title = "YOUR CHOICES" if plan is None else "YOUR CHOICES FROM NOW ON"
        out += ["", title] + _choices(ctx, picks, week_now if task == "change" else None, cfg)
        out += ["", "Choose how you will travel from now on (usual_choice). If you would mix two choices "
                    "across the week, give the second one (other_choice) and on how many days out of 5 "
                    "you would use it (days_per_week_on_other); otherwise \"none\" and 0."]
        out += ["Also say what you would do on a day when buses and trains are disrupted "
                "(if_bus_disrupted; \"not_applicable\" if you would not be using them), what would make you "
                "think again (would_reconsider_if), whether this is something you are trying out "
                "(trying_it_out, and review_after_days: 5 or 10, else 0), and how settled you are."]
        note += (" \"Each week\" is five working days of that choice" +
                 (", compared with what your current plan costs you a week." if (task == "change" and plan) else "."))
    out += ["", note]
    return "\n".join(line.rstrip() for line in out) + "\n"


# --------------------------------------------------------------------------------------------
# Schema and validation
# --------------------------------------------------------------------------------------------

def plan_schema(task: str, picks: Mapping[str, Option], ctx: DecisionContext) -> dict:
    """JSON schema of the reply; every choice field is an enum of what is offered today."""
    factors = list(L.factor_ids(ctx))
    tail = {"main_factor": {"type": "string", "enum": factors},
            "second_factor": {"type": "string", "enum": factors + [L.NO_FACTOR]}}
    if task == "today":
        props: dict[str, Any] = {
            "in_their_words": {"type": "string"},
            "today_choice": {"type": "string", "enum": list(picks)},
            "add_to_plan": {"type": "string", "enum": ["no", "whenever_bus_or_train_is_disrupted"]},
        }
    else:
        offered = [s for s in picks if s in PLAN_STRATEGIES]
        props = {
            "in_their_words": {"type": "string"},
            "usual_choice": {"type": "string", "enum": offered},
            "other_choice": {"type": "string", "enum": offered + [NONE]},
            "days_per_week_on_other": {"type": "integer", "enum": [0, 1, 2, 3, 4]},
            "if_bus_disrupted": {"type": "string", "enum": [s for s in BUS_DISRUPTED
                                                           if s in picks or s in ("bus_anyway", "stay_home_today",
                                                                                  "not_applicable")]},
            "would_reconsider_if": {"type": "array", "items": {"type": "string", "enum": list(RECONSIDER)}},
            "trying_it_out": {"type": "boolean"},
            "review_after_days": {"type": "integer", "enum": [0, 5, 10]},
            "how_settled": {"type": "string", "enum": ["firm", "leaning", "torn"]},
        }
    props.update(tail)
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def validate_reply(obj: object, schema: dict) -> tuple[bool, str]:
    """Check a parsed reply against a plan_schema (types and enums; free text must not be empty)."""
    if not isinstance(obj, dict):
        return False, "output is not a JSON object"
    props = schema["properties"]
    if set(obj) != set(props):
        return False, f"keys {sorted(obj)} != {sorted(props)}"
    for k, spec in props.items():
        v, t = obj[k], spec["type"]
        if t == "string":
            ok = isinstance(v, str) and (v in spec["enum"] if "enum" in spec else bool(v.strip()))
        elif t == "integer":
            ok = isinstance(v, int) and not isinstance(v, bool) and v in spec.get("enum", [v])
        elif t == "boolean":
            ok = isinstance(v, bool)
        else:
            ok = isinstance(v, list) and all(x in spec["items"]["enum"] for x in v)
        if not ok:
            return False, f"{k} = {v!r} is not valid"
    return True, ""


# --------------------------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------------------------

class PlanMock(L.MockLLM):
    """Deterministic stand-in for the plan template, NOT an LLM: picks the choice whose best option
    has the lowest re-weighted generalised cost (plus prompt-seeded noise) and returns a plain plan."""

    def complete(self, system: str, user: str, schema: dict, ctx: DecisionContext) -> dict:
        props = schema["properties"]
        key = "today_choice" if "today_choice" in props else "usual_choice"
        groups = by_strategy(ctx.options)
        offered = [s for s in props[key]["enum"] if s in groups]
        rep = int(self.cfg.llm.replicate)
        seed = int(L.prompt_sha256(system, user + (f"\n#replicate {rep}" if rep > 0 else ""))[:16], 16)
        sigma = self.cfg.llm.mock.noise_sigma
        noise = np.random.default_rng(seed).gumbel(0.0, sigma, len(offered)) if sigma > 0 else np.zeros(len(offered))
        best = {s: min(groups[s], key=lambda o: sum(self._score(o).values())) for s in offered}
        totals = [sum(self._score(best[s]).values()) + float(e) for s, e in zip(offered, noise)]
        k = int(np.argmin(totals))
        choice = offered[k]
        chosen = self._score(best[choice])
        others = [self._score(best[s]) for j, s in enumerate(offered) if j != k]
        main = "other"
        if others:
            parts = sorted({p for s in [chosen] + others for p in s})
            adv = {p: float(np.mean([s.get(p, 0.0) for s in others])) - chosen.get(p, 0.0) for p in parts}
            top = max(parts, key=lambda p: (round(adv[p], 9), -parts.index(p)))
            if adv[top] > 0:
                main = L._PART_FACTOR_V2.get(top, "other")
        if main not in props["main_factor"]["enum"]:
            main = "other"
        out: dict[str, Any] = {"in_their_words": f"[mock] I chose {choice}."}
        if key == "today_choice":
            out.update(today_choice=choice, add_to_plan="no")
        else:
            out.update(usual_choice=choice, other_choice=NONE, days_per_week_on_other=0,
                       if_bus_disrupted="bus_anyway" if choice == "bus_or_train" else "not_applicable",
                       would_reconsider_if=[], trying_it_out=False, review_after_days=0, how_settled="firm")
        out.update(main_factor=main, second_factor=L.NO_FACTOR)
        return out


class PlanLLM(L.LLMDecider):
    """LLMDecider plumbing (cache, log, retry on an invalid reply, stop on fatal errors) for plan-v1."""

    def __init__(self, cfg: Config, backend: Any, fallback: Decider, log_path: Path,
                 cache: L.LLMCache | None) -> None:
        super().__init__(cfg, backend, fallback, log_path, cache)
        self.system = PLAN_SYSTEM
        self.template_id = plan_template(cfg)
        self.v2 = False

    def _validate(self, parsed: object, ids: Sequence[str], schema: dict) -> tuple[bool, str]:
        return validate_reply(parsed, schema)

    def ask(self, items: Sequence[tuple[DecisionContext, str, dict]]) -> list[dict | None]:
        """One reply per (context, user message, schema), None where the LLM gave no valid answer.
        Identical prompts are sent once and share the answer, as in LLMDecider.decide_batch."""
        if not items:
            return []
        keyed, first = [], {}
        for i, (ctx, user, schema) in enumerate(items):
            key = self._key(user, schema)
            first.setdefault(key, i)
            keyed.append((ctx, user, schema, key))
        uniq = sorted(set(first.values()))
        got = dict(zip(uniq, self._run(self._gather([keyed[i] for i in uniq]))))
        out: list[dict | None] = []
        for i, (ctx, user, _schema, key) in enumerate(keyed):
            if i in got:
                parsed, recs = got[i]
            else:
                parsed, src = got[first[key]][0], got[first[key]][1][-1]
                rec = dict(src, call_id=f"d{ctx.day:02d}-a{ctx.agent_id:05d}-s", day=ctx.day,
                           agent_id=ctx.agent_id, triggers=list(ctx.triggers), cache_hit=False,
                           shared=True, shared_from=src["call_id"], usage=L._empty_usage(),
                           latency_s=None, attempt=0)
                self._log(rec)
                recs = [rec]
            st = self.stats
            st["n_contexts"] += 1
            st["prompt_chars"] += len(self.system) + len(user)
            for r in recs:
                real = not (r["cache_hit"] or r["shared"])
                st["n_calls"] += 1 if real else 0
                st["n_cache_hits"] += 1 if r["cache_hit"] else 0
                st["n_shared"] += 1 if r["shared"] else 0
                if real:
                    st["n_invalid"] += 1 if r["error_kind"] == "invalid" else 0
                    st["n_api_errors"] += 1 if r["error_kind"] in ("api", "fatal") else 0
                    st["n_refusals"] += 1 if r["error_kind"] == "refusal" else 0
                for k in L._empty_usage():
                    st[k] += int(r["usage"].get(k, 0) or 0)
            st["n_fallback"] += 1 if parsed is None else 0
            out.append(parsed)
        return out


# --------------------------------------------------------------------------------------------
# Decider
# --------------------------------------------------------------------------------------------

class HybridDecider:
    """Arm H-clock. run.py passes every commuter with a real choice each morning; this class decides
    who answers (the plan, the rule or the LLM) and returns one Decision per commuter, in order.

    Decision.decider is "standing" (the plan, including its contingency), "rule", "llm" or
    "llm-fallback-rule". Decision.meta["set_standing"] is False on days that are not the plan's usual
    choice, so memory keeps the usual option as the habit reference."""

    name = "hybrid"

    def __init__(self, cfg: Config, run_dir: Path, rule: Decider, backend: str | None = None) -> None:
        self.cfg, self.rule = cfg, rule
        kind = backend or cfg.run.backend
        if kind == "mock":
            be: Any = PlanMock(cfg)
            cache = None
        elif kind == "anthropic":
            be = L.AnthropicLLM(cfg)
            cache = L.LLMCache(cfg.resolve_path(cfg.llm.cache_dir))
        else:
            raise ValueError(f"unknown LLM backend {kind!r}")
        self.llm = PlanLLM(cfg, be, rule, Path(run_dir) / "llm_calls.jsonl", cache)
        self.plans: dict[int, Plan] = {}
        self.log_path = Path(run_dir) / "plan_log.jsonl"

    @property
    def stats(self) -> dict:
        return self.llm.stats

    def close(self) -> None:
        self.llm.close()

    @staticmethod
    def _pick(ctx: DecisionContext, options: Sequence[Option]) -> Option:
        """The model chooses the minute: the option of one choice with the lowest generalised cost
        (the rule's cost, without its random term; ties go to the earlier departure). A commuter
        whose start time is firm or fixed (sched_mult >= 1) is never scheduled to arrive late while a
        departure that arrives on time is offered [A]: on the 15-minute grid the cost alone would
        accept one to three minutes of lateness every day."""
        opts = list(options)
        if ctx.persona.sched_mult >= 1.0:
            opts = [o for o in opts if o.late_min <= 0] or opts
        return min(opts, key=lambda o: o.gc)

    def _why(self, ctx: DecisionContext, plan: Plan) -> str | None:
        """Reason for a "change" call today, or None."""
        if "T2" in ctx.triggers and plan.uses_car() and not ctx.persona.company_car:
            return "charge"
        if plan.review_day is not None and ctx.day >= plan.review_day:
            return "review"
        if ("late_twice_in_a_week" in plan.reconsider and "T3" in ctx.triggers
                and sum(1 for r in ctx.recent if r.late_min > 0) >= 2):
            return "late"
        if "trip_much_longer_or_shorter" in plan.reconsider and "T5" in ctx.triggers:
            return "trip"
        return None

    def _apply(self, ctx: DecisionContext, reply: dict, groups: Mapping[str, Sequence[Option]],
               old: Plan | None) -> Plan:
        other = reply["other_choice"]
        days = int(reply["days_per_week_on_other"])
        if other in (NONE, reply["usual_choice"]) or days == 0 or other not in groups:
            other, days = None, 0
        review = int(reply["review_after_days"]) if reply["trying_it_out"] else 0
        return Plan(usual=reply["usual_choice"], other=other, other_days=days,
                    if_bus_disrupted=reply["if_bus_disrupted"],
                    reconsider=tuple(dict.fromkeys(x for x in reply["would_reconsider_if"]
                                                   if x != "nothing_in_particular")),
                    review_day=(ctx.day + review) if review > 0 else None,
                    settled=reply["how_settled"], made_on=ctx.day, words=reply["in_their_words"].strip(),
                    slots=dict(old.slots) if old else {})

    def decide_batch(self, contexts: Sequence[DecisionContext]) -> list[Decision]:
        n = len(contexts)
        groups = [by_strategy(c.options) for c in contexts]
        memo: dict[tuple[int, str], Option] = {}

        def pick(i: int, s: str) -> Option:
            """Today's departure for one choice, as the rule picks it (shown in prompts, used afterwards)."""
            if (i, s) not in memo:
                memo[(i, s)] = self._pick(contexts[i], groups[i][s])
            return memo[(i, s)]

        task: list[str | None] = [None] * n
        why: list[str] = [""] * n
        ask = []
        for i, c in enumerate(contexts):
            plan = self.plans.get(c.agent_id)
            if plan is None:
                task[i] = "routine"
            else:
                w = self._why(c, plan)
                if w is not None:
                    task[i], why[i] = "change", w
                elif (strategy_on(plan, c.day) == "bus_or_train" and _bus_disrupted_today(c)
                      and plan.if_bus_disrupted == "not_applicable"):
                    task[i], why[i] = "today", "disruption"
            if task[i] is not None:
                shown = {s: pick(i, s) for s in groups[i] if task[i] == "today" or s in PLAN_STRATEGIES}
                ask.append((c, render_plan_prompt(c, task[i], shown, plan, why[i], self.cfg),
                            plan_schema(task[i], shown, c)))
        replies = iter(self.llm.ask(ask))

        out: list[Decision] = []
        for i, c in enumerate(contexts):
            plan = self.plans.get(c.agent_id)
            g, handler, reply, new_plan = groups[i], "plan", None, False
            if task[i] is not None:
                reply = next(replies)
                if reply is None:                      # no valid answer: the rule decides over everything
                    d = self.rule.decide_batch([c])[0]
                    s = strategy_of(c.option(d.option_id))
                    if plan is None:
                        plan = self.plans[c.agent_id] = Plan(usual=s if s in PLAN_STRATEGIES else "drive",
                                                             made_on=c.day)
                        new_plan = True
                    if s != "stay_home_today":
                        plan.slots[s] = d.option_id
                    out.append(self._finish(c, plan, s, d.option_id, "llm-fallback-rule", d.reason, d.factors,
                                            task[i], new_plan))
                    continue
                handler = "llm"
                if task[i] == "today":
                    s = reply["today_choice"]
                    if reply["add_to_plan"] != "no" and s != "bus_or_train":
                        plan.if_bus_disrupted = s
                else:
                    plan = self.plans[c.agent_id] = self._apply(c, reply, g, plan)
                    new_plan = True
                    s = strategy_on(plan, c.day)
            else:
                s = strategy_on(plan, c.day)
            if task[i] != "today" and s == "bus_or_train" and _bus_disrupted_today(c):
                alt = plan.if_bus_disrupted
                if alt in g and alt != "bus_or_train":
                    s, handler = alt, ("contingency" if handler == "plan" else handler)
            if s not in g:                             # the choice has no option today
                s = plan.usual if plan.usual in g else next(iter(g))
            # the minute: a new answer or a routine wake re-picks; otherwise the last departure is kept
            slot = plan.slots.get(s)
            routine_wake = bool({"T3", "T5"} & set(c.triggers))
            if handler == "llm" or routine_wake or slot not in {o.option_id for o in g[s]}:
                oid = pick(i, s).option_id
                if handler in ("plan", "contingency") and (routine_wake or slot is not None):
                    handler = "rule"
            else:
                oid = slot
            if s != "stay_home_today":
                plan.slots[s] = oid
            if handler == "llm":
                decider, reason, factors = "llm", reply["in_their_words"].strip(), L.reply_factors(reply)
            elif handler == "rule":
                reason, factors = explain(replace(c, options=tuple(g[s])), oid)
                decider = "rule"
            else:
                decider, reason, factors = "standing", "", ()
            out.append(self._finish(c, plan, s, oid, decider, reason, factors,
                                    task[i] or handler, new_plan))
        return out

    def _finish(self, ctx: DecisionContext, plan: Plan, strategy: str, option_id: str, decider: str,
                reason: str, factors: Sequence[str], handler: str, new_plan: bool) -> Decision:
        rec = {"day": ctx.day, "agent_id": ctx.agent_id, "handler": handler, "decider": decider,
               "strategy": strategy, "option_id": option_id, "triggers": list(ctx.triggers)}
        if new_plan or handler == "today":
            rec["plan"] = plan.public()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
        return Decision(agent_id=ctx.agent_id, day=ctx.day, option_id=option_id, decider=decider,
                        reason=reason, factors=tuple(factors),
                        meta={"set_standing": strategy == plan.usual, "handler": handler, "strategy": strategy})


def make_hybrid_decider(cfg: Config, run_dir: Path, rule: Decider, backend: str | None = None) -> Any:
    """The H-clock decider for cfg.llm.template_id, writing run_dir/llm_calls.jsonl and
    run_dir/plan_log.jsonl: thinker.ThinkDecider for "think-v1", otherwise HybridDecider."""
    if cfg.llm.template_id == "think-v1":
        from cordonlite.thinker import ThinkDecider  # imported lazily: thinker imports this module

        return ThinkDecider(cfg, run_dir, rule, backend)
    return HybridDecider(cfg, run_dir, rule, backend)
