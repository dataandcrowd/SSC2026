"""Arm H-clock (prompt template "think-v1"): the model runs the routine, the LLM is the commuter
stopping to think.

A commuter does not decide how to get to work every morning. They repeat what works until something
breaks it. Here the base model supplies the routine and repeats it, and the LLM is asked only at
three kinds of moment:

    something new and lasting    the charge starts, changes or ends (T2), for a commuter whose
                                 arrangement involves driving and who pays the charge
    the arrangement is not       the days of a trial are up; or the commuter keeps arriving late
    working                      (T3, twice beyond their tolerance since they last thought about it);
                                 or the drive has been taking clearly longer than expected (T5)
    something is wrong today     buses and trains are disrupted on a bus or train day and the
                                 commuter has no back-up: a one-day answer, the arrangement stays

Who answers on a given morning (ThinkDecider.decide_batch):
    no routine yet (day 1)                       the base model's rule; this is the commuter's routine
    one of the moments above                     LLM
    bus disrupted, the arrangement has a back-up the back-up (no call)
    today's way has no option (see below)        the base model's rule, for that day only
    anything else                                the routine: the same choice and the same departure

The first day is the base model's, so an H-clock run and an R-clock run start from the same routines.
Between two LLM answers the commuter leaves at the same time; a single late day or a T5 wake never
moves the departure on its own. The departure of each thing the commuter could do is chosen by the
model when the question is put (_pick: lowest generalised cost without the random term; a firm start
is never scheduled late).

The message states only what the model holds about the person and the world, in sentences. It never
states how the rule weighs them: no generalised cost, no calibrated penalty, no sums across days.

Fit with the base model (main, 2026-10-13):
    - no SKIP: a commuter who does not travel works from home, when they can;
    - road traffic: times and arrivals include it; where the message mentions delay it names the
      traffic on the way and the queue at the entry point, as llm.py does;
    - willingness to travel: options.wtt_filter has already removed the car departures charged above
      persona.wtp_fee, so the LLM never sees them (as in the L arms). The message says so with the
      base prompt's own sentence whenever a departure was removed, and when the commuter's usual
      departure is among them there is no keep_as_is: they must answer with something else;
    - lateness is counted as the base model counts it for T3: beyond clock.late_tolerance_by_F.

Assumptions [A] (author decisions 2026-10-07, not calibrated):
    - a week is 5 consecutive simulated days; "n days a week on the second way" uses fixed weekday
      positions (OTHER_DAYS), so a mixed week is deterministic; a trial is reviewed once;
    - until the LLM has answered for a commuter, both "keeps arriving late" and "drive much longer"
      can raise a question; afterwards the commuter's own would_rethink_if list decides;
    - a late or longer-drive question is not put again within 5 days of the last answer;
    - drive_other_time, when the question is about the charge, is the model's choice among the
      departures with a lower charge than the usual one (none offered if there is none); otherwise it
      is the model's choice among all other departures.

Outputs: llm_calls.jsonl (every LLM call, as llm.py) and plan_log.jsonl (one line per agent-day: who
answered, today's choice, the option, and the arrangement whenever it changed).

Public API:
    THINK_TEMPLATE_ID, THINK_SYSTEM, STRATEGIES, strategy_of(option), by_strategy(options)
    Plan, strategy_on(plan, day)
    change_offers(ctx, plan, groups, pick, why) -> dict[str, Option]; today_offers(groups, pick)
    render_think_prompt(ctx, task, offers, plan, why, cfg, since=None, charged_before=False, notes=()) -> str
    think_schema(task, offers, ctx) -> dict; validate_reply(obj, schema) -> (bool, str)
    ThinkMock, ThinkLLM, ThinkDecider, make_hybrid_decider(cfg, run_dir, rule, backend=None)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from cordonlite import llm as L
from cordonlite.config import Config
from cordonlite.options import early_start_for
from cordonlite.types import Decider, Decision, DecisionContext, Option, Persona, clock_str

THINK_TEMPLATE_ID = "think-v1"
STRATEGIES: tuple[str, ...] = ("drive", "drive_early_day", "bus_or_train", "work_from_home")
DRIVING: frozenset[str] = frozenset({"drive", "drive_early_day"})
KEEP = "keep_as_is"
OTHER_TIME = "drive_other_time"
NONE = "none"
RETHINK: tuple[str, ...] = ("late_twice_in_a_week", "trip_much_longer", "nothing_in_particular")
DEFAULT_RETHINK: tuple[str, ...] = RETHINK[:2]
BUS_ANYWAY = "bus_anyway"
NOT_APPLICABLE = "not_applicable"
ASK_AGAIN_AFTER = 5            # days before a late or longer-drive question is put again [A]
OTHER_DAYS: dict[int, tuple[int, ...]] = {0: (), 1: (2,), 2: (1, 3), 3: (0, 2, 4), 4: (0, 1, 3, 4)}
WEEK = 5
# Reason tags of a reply; reason_tags() narrows them to the ones that can apply to the agent-day.
TAGS: tuple[str, ...] = (
    "road_charge", "other_money", "travel_time", "arrival_time", "routine", "bus_train_preference",
    "flexibility", "past_experience", "disruption", "constraint", "other",
)

THINK_SYSTEM = (
    "This is part of a simulation of morning commuting into Auckland's city centre.\n"
    "The simulation handles ordinary mornings itself: each commuter has a routine and repeats it. "
    "You are asked only when a commuter would stop and think, because something has changed or "
    "something has gone wrong.\n"
    "You are given one commuter: their circumstances, how they tend to make decisions, what they have "
    "been doing and how it has gone, and what has happened. The message is written to the commuter, "
    "as \"you\". Answer as that person would actually respond. That is not always the cheapest or the "
    "most sensible option. Some people carry on with what works for them even when it starts to cost "
    "more, some change quickly, and some try something for a while before they settle. Let this "
    "person's circumstances, tendencies and recent experience decide which they are.\n"
    "Everything you need is in the message. Do not add facts about the person that are not there, "
    "such as a family, an occupation or an income, and do not reason from stereotypes. The times and "
    "prices are the simulation's own estimates for this person.\n"
    "You decide how they travel, not the minute they leave. The simulation works out departure times "
    "from your answer, and the times shown are the ones it would use.\n"
    "Write in_my_words first, in the first person, in one or two sentences.\n"
    "Name the one thing that decided the answer (main_reason) and, only if a second thing clearly "
    "mattered, that as well (second_reason; otherwise \"none\"). The tags mean:\n"
    "- road_charge: the charge for driving into the city centre: paying it, its amount, or avoiding it.\n"
    "- other_money: parking, fuel or the bus or train fare.\n"
    "- travel_time: how long the trip takes door to door, traffic and queues included.\n"
    "- arrival_time: arriving early, on time or late against the start time.\n"
    "- routine: keeping the usual way of making the trip, or the bother of changing it.\n"
    "- bus_train_preference: liking or disliking buses and trains in themselves, apart from their "
    "cost and time.\n"
    "- flexibility: being able, or not able, to change the hours of the day or to work from home.\n"
    "- past_experience: something that happened on recent days.\n"
    "- disruption: a disruption to buses and trains.\n"
    "- constraint: something the day requires that rules other options out.\n"
    "- other: none of these.\n"
    "Only tags that can apply are offered."
)


# --------------------------------------------------------------------------------------------
# Ways of travelling and arrangements
# --------------------------------------------------------------------------------------------

def strategy_of(o: Option) -> str:
    """The way of travelling an option belongs to."""
    if o.mode == "CAR":
        return "drive_early_day" if o.early_shift else "drive"
    return {"PT": "bus_or_train", "WFH": "work_from_home"}[o.mode]


def by_strategy(options: Sequence[Option]) -> dict[str, tuple[Option, ...]]:
    """Today's options grouped by way of travelling, in STRATEGIES order."""
    groups: dict[str, list[Option]] = {}
    for o in options:
        groups.setdefault(strategy_of(o), []).append(o)
    return {s: tuple(groups[s]) for s in STRATEGIES if s in groups}


@dataclass
class Plan:
    """A commuter's standing arrangement (state kept by ThinkDecider between days)."""

    usual: str
    other: str | None = None
    other_days: int = 0                        # days per 5-day week on ``other``
    if_bus_disrupted: str = NOT_APPLICABLE
    reconsider: tuple[str, ...] = ()
    review_day: int | None = None              # day of the single review of a trial
    settled: str = "firm"
    made_on: int = 0
    words: str = ""
    slots: dict[str, str] = field(default_factory=dict)   # way -> option id last used

    def uses_car(self) -> bool:
        return self.usual in DRIVING or (self.other in DRIVING and self.other_days > 0)

    def public(self) -> dict:
        d = asdict(self)
        d.pop("slots")
        return d


def strategy_on(plan: Plan, day: int) -> str:
    """The arrangement's way on a simulated day (weekday position = (day - 1) mod 5)."""
    if plan.other and (day - 1) % WEEK in OTHER_DAYS.get(int(plan.other_days), ()):
        return plan.other
    return plan.usual


def _bus_disrupted_today(ctx: DecisionContext) -> bool:
    t = ctx.today
    return bool(t.pt_disruption_announced and ctx.persona.corridor_id in t.pt_disrupted_corridors)


def _record_strategy(r: Any) -> str:
    if r.mode == "CAR":
        return "drive_early_day" if r.early_shift else "drive"
    return {"PT": "bus_or_train", "WFH": "work_from_home"}.get(r.mode, "work_from_home")


def _pick(ctx: DecisionContext, options: Sequence[Option]) -> Option:
    """The model chooses the minute: the option of one way with the lowest generalised cost (the
    rule's cost, without its random term; ties go to the earlier departure). A commuter whose start
    time is firm or fixed (sched_mult >= 1) is never scheduled to arrive late while a departure that
    arrives on time is offered [A]: on the 15-minute grid the cost alone would accept one to three
    minutes of lateness every day."""
    opts = list(options)
    if ctx.persona.sched_mult >= 1.0:
        opts = [o for o in opts if o.late_min <= 0] or opts
    return min(opts, key=lambda o: o.gc)


def _by_id(ctx: DecisionContext, option_id: str | None) -> Option | None:
    return next((o for o in ctx.options if o.option_id == option_id), None)


def _tolerance(ctx: DecisionContext, cfg: Config) -> float:
    """Minutes of lateness the base model lets pass before it counts a trip as late (T3)."""
    return float(cfg.clock.late_tolerance_by_F[ctx.persona.F - 1])


# --------------------------------------------------------------------------------------------
# What the commuter could do
# --------------------------------------------------------------------------------------------

def change_offers(ctx: DecisionContext, plan: Plan, groups: Mapping[str, Sequence[Option]],
                  pick: Callable[[str], Option], why: str) -> dict[str, Option]:
    """Choice id -> the option it stands for today, for a lasting answer. keep_as_is comes first and
    is the main way of the present arrangement at the departure the commuter has been using; it is
    left out when that departure is no longer offered because its charge is above what the commuter
    would pay (options.wtt_filter)."""
    usual = plan.usual
    keep = _by_id(ctx, plan.slots.get(usual))
    if keep is not None and usual in groups and keep not in groups[usual]:
        keep = None                                # the departure now belongs to the other working day
    if keep is None and usual in groups and ctx.wtt_removed == 0:
        keep = pick(usual)                         # the grid moved: the model's departure for the same way
    out: dict[str, Option] = {} if keep is None else {KEEP: keep}
    if usual == "drive" and "drive" in groups:
        others = [o for o in groups["drive"] if keep is None or o.option_id != keep.option_id]
        if why == "charge" and keep is not None:
            others = [o for o in others if o.fee < keep.fee - 0.005]
        if others:
            out[OTHER_TIME] = _pick(ctx, others)
    for s in STRATEGIES:
        if s in groups and (s != usual or (keep is None and s != "drive")):
            out[s] = pick(s)
    return out


def today_offers(groups: Mapping[str, Sequence[Option]], pick: Callable[[str], Option]) -> dict[str, Option]:
    """Choice id -> option for a one-day answer on a disrupted morning; the bus or train comes first."""
    order = ("bus_or_train", "drive", "drive_early_day", "work_from_home")
    return {s: pick(s) for s in order if s in groups}


# --------------------------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------------------------

def _join(parts: Sequence[str]) -> str:
    parts = list(parts)
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _pays_charge(o: Option, p: Persona) -> bool:
    return (not p.company_car) and float(o.fee) > 0.005


def _against_start(o: Option, p: Persona) -> str:
    start = clock_str(o.start_used_min if o.start_used_min is not None else p.tstar_min)
    e, lt = int(round(o.early_min)), int(round(o.late_min))
    if lt > 0:
        return f"{lt} min after your {start} start"
    if e > 0:
        return f"{e} min before your {start} start"
    return f"right on your {start} start"


def _trip(o: Option, p: Persona) -> str:
    return (f"leaving home about {clock_str(o.depart_min)} and arriving about "
            f"{clock_str(o.expected_arrive_min)}, {_against_start(o, p)}")


def _delays(o: Option) -> str:
    """The traffic and queue a car time allows for, when either is a minute or more."""
    parts = []
    r, q = float(o.expected_road_delay_min or 0.0), float(o.expected_delay_min or 0.0)
    if r >= 0.5:
        parts.append(f"about {L._road_mins(r)} of traffic on the way")
    if q >= 1.0:
        parts.append(f"a queue of about {L._mins(q)} at your entry point")
    return f" That allows for {' and '.join(parts)}." if parts else ""


def _drive_costs(o: Option, p: Persona, when: str) -> str:
    """What a day of driving costs someone who is not driving now. ``when``: "Today" or "Each day"."""
    parts = []
    if p.parking_cost > 0:
        parts.append(f"{L._money(p.parking_cost)} for parking")
    if p.fuel_cost > 0:
        parts.append(f"about {L._money(p.fuel_cost)} for fuel")
    if _pays_charge(o, p):
        parts.append(f"{L._money(o.fee)} for the charge")
    if not parts:
        return "Driving would cost you nothing."
    return f"{when} you would pay {_join(parts)}."


def _early_hours(p: Persona, cfg: Config) -> str:
    es = early_start_for(p, cfg) or int(cfg.costs.early_start_min)
    return f"{clock_str(es)} to {clock_str(es + 480)}"


def _describe(cid: str, o: Option, ctx: DecisionContext, plan: Plan, keep: Option | None,
              task: str, cfg: Config) -> str:
    """One line of WHAT YOU COULD DO."""
    p, t = ctx.persona, ctx.today
    s = strategy_of(o)
    when = "Today" if task == "today" else "Each day"
    driving_now = plan.usual in DRIVING
    if cid == KEEP:
        mixed = bool(plan.other and plan.other_days > 0)
        tail = " as your main way" if mixed else ""
        if o.mode == "CAR":
            hours = f" and working {_early_hours(p, cfg)}" if s == "drive_early_day" else ""
            text = f"carry on driving{hours}{tail}, {_trip(o, p)}.{_delays(o)}"
            if _pays_charge(o, p):
                text += (f" You would pay the {L._money(o.fee)} charge each day, on top of what driving "
                         "already costs you." if t.fee_changed_today else
                         f" You would go on paying the charge, {L._money(o.fee)} a day at that time.")
        elif s == "bus_or_train":
            text = f"carry on taking the bus or train{tail}, {_trip(o, p)}."
        else:
            text = f"carry on working from home{tail}."
    elif cid == OTHER_TIME:
        text = f"still drive, but at a different time, {_trip(o, p)}.{_delays(o)}"
        if _pays_charge(o, p):
            text += f" The charge would be {L._money(o.fee)} a day"
            if keep is not None and _pays_charge(keep, p):
                text += f" instead of {L._money(keep.fee)}"
            text += "."
    elif o.mode == "CAR":
        lead = f"drive in and work {_early_hours(p, cfg)}" if s == "drive_early_day" else "drive in"
        text = f"{lead}, {_trip(o, p)}.{_delays(o)}"
        if driving_now and task != "today":
            if _pays_charge(o, p):
                text += f" The charge would be {L._money(o.fee)} a day"
                if keep is not None and _pays_charge(keep, p):
                    text += f" instead of {L._money(keep.fee)}"
                text += "."
        else:
            text += " " + _drive_costs(o, p, when)
    elif s == "bus_or_train":
        if task == "today":
            text = (f"take the bus or train anyway. Today it would take about {L._mins(o.expected_travel_min)} "
                    f"door to door, {_trip(o, p)}. The fare is {L._money(float(o.pt_fare or 0.0))}.")
        else:
            text = (f"take the bus or train, {_trip(o, p)}. It takes about {L._mins(o.expected_travel_min)} "
                    f"door to door. The fare is {L._money(float(o.pt_fare or 0.0))} for the day, and you "
                    "would have no driving costs.")
    else:
        text = "do your day's work at home. There is no trip and nothing to pay."
    return f"- {cid}: {text}"


def _way_done(s: str, p: Persona, cfg: Config) -> str:
    return {"drive": "driven in",
            "drive_early_day": f"driven in and worked {_early_hours(p, cfg)}",
            "bus_or_train": "taken the bus or train",
            "work_from_home": "worked from home"}[s]


_DID = {"drive": "drove in", "drive_early_day": "drove in", "bus_or_train": "took the bus or train anyway",
        "work_from_home": "worked from home"}


def _doing(ctx: DecisionContext, plan: Plan, cfg: Config, since: int | None,
           notes: Sequence[tuple[int, str]] = ()) -> list[str]:
    """WHAT YOU HAVE BEEN DOING: the arrangement, how the last trips went, and the last answer.
    ``notes``: (day, what the commuter did) for mornings when a bus or train day was disrupted."""
    p = ctx.persona
    n = max(1, ctx.day - (plan.made_on if since is None else since))
    span = f"For the last {n} working day{'s' if n != 1 else ''}"

    def way(s: str) -> str:
        d = next((r.depart_min for r in reversed(ctx.recent)
                  if _record_strategy(r) == s and r.depart_min is not None), None)
        if d is None:
            o = _by_id(ctx, plan.slots.get(s))
            d = o.depart_min if o is not None else None
        return _way_done(s, p, cfg) + (f", leaving home about {clock_str(d)}" if d is not None else "")

    if plan.other and plan.other_days > 0:
        k = int(plan.other_days)
        lines = [f"- {span} you have had a mixed week: on {WEEK - k} day{'s' if WEEK - k != 1 else ''} "
                 f"you have {way(plan.usual)}, and on the other {k} you have {way(plan.other)}."]
    else:
        lines = [f"- {span} you have {way(plan.usual)}."]
    trips = [r for r in ctx.recent if r.mode in ("CAR", "PT")]
    if trips:
        last, m = trips[-1], len(trips)
        by = {"CAR": "car", "PT": "bus or train"}
        both = len({r.mode for r in trips}) > 1     # the window holds drives and bus or train trips
        tol = _tolerance(ctx, cfg)
        lates = [r for r in trips if r.late_min is not None and r.late_min > tol]
        late = len(lates)
        lines.append(f"- Your most recent trip{', by ' + by[last.mode] + ',' if both else ''} got you there at "
                     f"{L._clock(last.arrive_min)} ({L._early_late(last.early_min, last.late_min)}).")
        seen = (f"- {'None' if late == 0 else late} of your last {m} trips arrived more than {tol:g} min after "
                f"your start time" if m > 1 else "")
        if seen and both and late:
            seen += " (" + ", ".join(f"day {r.day} by {by[r.mode]}" for r in lates) + ")"
        cars = [r for r in trips if r.mode == "CAR" and r.queue_delay_min is not None and r.queue_delay_min >= 0]
        if cars:
            q = float(np.mean([r.queue_delay_min for r in cars]))
            queue = (f"the queue at your entry point was about {L._mins(q)}" if q >= 0.5
                     else "there was no queue at your entry point")
            if L._roads_on(ctx):
                tr = float(np.mean([float(r.road_delay_min or 0.0) for r in cars]))
                queue = (f"traffic on the way added about {L._road_mins(tr)}" if tr >= 0.5
                         else "there was no traffic delay on the way") + f" and {queue}"
            seen = f"{seen}, and {queue}" if seen else f"- On that trip {queue}"
        if seen:
            lines.append(seen + ".")
        paid = [float(r.fee_paid) for r in trips if r.mode == "CAR" and r.fee_paid > 0.005]
        if paid and not p.company_car:
            lines.append(f"- The charge has cost you about {L._money(float(np.mean(paid)))} on each day you drove.")
    first = ctx.recent[0].day if ctx.recent else ctx.day
    noted = {d: s for d, s in notes if first <= d < ctx.day}
    for r in ctx.recent:
        if r.pt_disrupted and r.day not in noted:
            noted[r.day] = "bus_or_train"
    for d in sorted(noted):
        lines.append(f"- On day {d} buses and trains from your area were disrupted, and you "
                     f"{_DID.get(noted[d], 'changed your plans')} that day.")
    if plan.words:
        lines.append(f"- When you last thought about this, on day {plan.made_on}, you said: \"{plan.words}\"")
    return lines


def _charge_lines(ctx: DecisionContext, cfg: Config) -> list[str]:
    """The charge by crossing time, as llm._today lists it (its indented lines)."""
    return [ln for ln in L._today(ctx, cfg) if ln.startswith("  ")]


def _would_not_pay(ctx: DecisionContext, plan: Plan, keep: Option | None) -> list[str]:
    """The base prompt's willingness-to-pay sentence (llm._today), on a morning a car time was removed."""
    if ctx.wtt_removed <= 0 or not ctx.today.fee_active:
        return []
    limit = L._money(ctx.persona.wtp_fee)
    lead = f"- You would not pay more than {limit} a day to drive into the city centre"
    if not any(o.mode == "CAR" for o in ctx.options):
        return [f"{lead}, and every time you could drive is charged more than that, so driving is not offered."]
    if keep is None and plan.usual in DRIVING:
        return [f"{lead}. The charge at your usual time is more than that, so carrying on as you are is not "
                "offered; driving at times when the charge is higher than that is not offered either."]
    return [f"{lead}, so driving at times when the charge is higher than that is not offered."]


def _happened(ctx: DecisionContext, task: str, why: str, plan: Plan, keep: Option | None,
              cfg: Config, charged_before: bool) -> list[str]:
    """Heading and lines of the section that says why the commuter is thinking now."""
    t, p = ctx.today, ctx.persona
    limit = _would_not_pay(ctx, plan, keep)
    still = (["- The charge for driving into the city centre is still in place."]
             if (t.fee_active and not t.fee_changed_today) else []) + limit
    if task == "today":
        return ["WHAT IS DIFFERENT TODAY",
                "- Buses and trains from your area are disrupted today: trips are taking about "
                f"{t.pt_disruption_time_mult:g} times as long as usual."] + still
    if why == "charge":
        if not t.fee_active:
            return ["WHAT IS NEW", "- From today the charge for driving into the city centre no longer applies."]
        lead = ("- From today the charge for driving into the city centre changes."
                if charged_before else "- From today there is a charge for driving into the city centre.")
        lines = ["WHAT IS NEW", lead + " It depends on the time you cross into the city centre:"]
        lines += _charge_lines(ctx, cfg)
        if keep is not None and keep.mode == "CAR" and _pays_charge(keep, p):
            lines.append(f"- At the time you usually cross, it would be {L._money(keep.fee)} a day.")
        return lines + limit
    if why == "review":
        d = (plan.review_day or ctx.day) - plan.made_on
        first = f"- The {d} days you gave yourself to try this are up."
    elif why == "late":
        first = f"- You keep arriving more than {_tolerance(ctx, cfg):g} min after your start time."
    else:
        first = "- Your drive has been taking clearly longer than you expected."
    return ["WHY YOU ARE THINKING ABOUT THIS AGAIN", first] + still


def render_think_prompt(ctx: DecisionContext, task: str, offers: Mapping[str, Option], plan: Plan,
                        why: str, cfg: Config, since: int | None = None,
                        charged_before: bool = False, notes: Sequence[tuple[int, str]] = ()) -> str:
    """User message of template think-v1. ``task``: "change" (a lasting answer) or "today"."""
    keep = offers.get(KEEP)
    out = ["WHO YOU ARE"] + L._situation(ctx, cfg)[:-1]
    if ctx.traits_shown or cfg.llm.traits_off_prompt == "sentences":
        out += ["", "HOW YOU TEND TO DECIDE"] + [f"- {s}" for s in L._dispositions(ctx.persona)]
    out += ["", "WHAT YOU HAVE BEEN DOING"] + _doing(ctx, plan, cfg, since, notes)
    out += [""] + _happened(ctx, task, why, plan, keep, cfg, charged_before)
    out += ["", "WHAT YOU COULD DO THIS MORNING" if task == "today" else "WHAT YOU COULD DO"]
    out += [_describe(cid, o, ctx, plan, keep, task, cfg) for cid, o in offers.items()]
    if task == "today":
        out += ["", "What do you do this morning (what_i_do_today)? This is about today only: your usual "
                    "arrangement stays as it is. Say too whether you would do the same on any morning "
                    "when buses and trains are disrupted (same_whenever_disrupted)."]
    else:
        out += ["", "What do you do from now on? Give your main way (what_i_do). If you would use a second "
                    "way on some days, give it (second_choice) and say on how many days out of 5 "
                    "(days_a_week_on_second); otherwise \"none\" and 0. Your answer replaces your present "
                    "arrangement, so repeat any part of it you want to keep.",
                "Say too whether you are trying this out (trying_it_out_for_days: 5 or 10) or have decided "
                "(0); what you would do on a morning when buses and trains are disrupted (if_bus_disrupted; "
                "\"not_applicable\" if you would not be using them); what would make you think again "
                "(would_rethink_if); and how settled you feel (how_settled)."]
    out += ["", "Times are clock times (hh:mm) and are estimates for today. Money is in New Zealand dollars."]
    return "\n".join(line.rstrip() for line in out) + "\n"


# --------------------------------------------------------------------------------------------
# Schema and validation
# --------------------------------------------------------------------------------------------

def reason_tags(ctx: DecisionContext) -> tuple[str, ...]:
    """The reason tags that can apply to this agent-day, in TAGS order: no road_charge without a
    charge, no disruption without one, no bus_train_preference when no bus or train is offered."""
    t, p = ctx.today, ctx.persona
    can_apply = {
        "road_charge": bool(t.fee_active or t.fee_changed_today),
        "routine": ctx.standing_option_id is not None,
        "bus_train_preference": any(o.mode == "PT" for o in ctx.options),
        "past_experience": bool(ctx.recent),
        "disruption": bool((p.corridor_id in t.pt_disrupted_corridors and t.pt_disruption_announced)
                           or "T4" in ctx.triggers or any(r.pt_disrupted for r in ctx.recent)),
    }
    return tuple(f for f in TAGS if can_apply.get(f, True))


def think_schema(task: str, offers: Mapping[str, Option], ctx: DecisionContext) -> dict:
    """JSON schema of the reply; every choice is an enum of what is offered today."""
    tags = list(reason_tags(ctx))
    ids = list(offers)
    if task == "today":
        props: dict[str, Any] = {
            "in_my_words": {"type": "string"},
            "what_i_do_today": {"type": "string", "enum": ids},
            "same_whenever_disrupted": {"type": "boolean"},
        }
    else:
        modes = {o.mode for o in ctx.options}
        backups = [NOT_APPLICABLE]
        if "PT" in modes:
            backups = ([BUS_ANYWAY] + (["drive"] if "CAR" in modes else [])
                       + (["work_from_home"] if "WFH" in modes else []) + [NOT_APPLICABLE])
        props = {
            "in_my_words": {"type": "string"},
            "what_i_do": {"type": "string", "enum": ids},
            "second_choice": {"type": "string", "enum": ids + [NONE]},
            "days_a_week_on_second": {"type": "integer", "enum": [0, 1, 2, 3, 4]},
            "trying_it_out_for_days": {"type": "integer", "enum": [0, 5, 10]},
            "if_bus_disrupted": {"type": "string", "enum": backups},
            "would_rethink_if": {"type": "array", "items": {"type": "string", "enum": list(RETHINK)}},
            "how_settled": {"type": "string", "enum": ["firm", "leaning", "torn"]},
        }
    props["main_reason"] = {"type": "string", "enum": tags}
    props["second_reason"] = {"type": "string", "enum": tags + [NONE]}
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def validate_reply(obj: object, schema: dict) -> tuple[bool, str]:
    """Check a parsed reply against a think_schema (types and enums; free text must not be empty)."""
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


def _reasons(reply: Mapping[str, Any]) -> tuple[str, ...]:
    main, second = reply["main_reason"], reply.get("second_reason", NONE)
    return (main,) if second in (NONE, main) else (main, second)


# --------------------------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------------------------

class ThinkMock(L.MockLLM):
    """Deterministic stand-in for think-v1, NOT an LLM: takes the offered choice with the lowest
    re-weighted generalised cost (plus prompt-seeded noise) and returns a plain, decided answer."""

    def __init__(self, cfg: Config) -> None:
        super().__init__(cfg)
        self.offers: dict[tuple[int, int], Mapping[str, Option]] = {}

    def complete(self, system: str, user: str, schema: dict, ctx: DecisionContext) -> dict:
        props = schema["properties"]
        key = "what_i_do_today" if "what_i_do_today" in props else "what_i_do"
        offered = self.offers[(ctx.agent_id, ctx.day)]
        ids = [i for i in props[key]["enum"] if i in offered]
        rep = int(self.cfg.llm.replicate)
        seed = int(L.prompt_sha256(system, user + (f"\n#replicate {rep}" if rep > 0 else ""))[:16], 16)
        sigma = self.cfg.llm.mock.noise_sigma
        noise = np.random.default_rng(seed).gumbel(0.0, sigma, len(ids)) if sigma > 0 else np.zeros(len(ids))
        totals = [sum(self._score(offered[i]).values()) + float(e) for i, e in zip(ids, noise)]
        choice = ids[int(np.argmin(totals))]
        out: dict[str, Any] = {"in_my_words": f"[mock] I chose {choice}."}
        if key == "what_i_do_today":
            out.update(what_i_do_today=choice, same_whenever_disrupted=False)
        else:
            backups = props["if_bus_disrupted"]["enum"]
            out.update(what_i_do=choice, second_choice=NONE, days_a_week_on_second=0,
                       trying_it_out_for_days=0,
                       if_bus_disrupted=BUS_ANYWAY if BUS_ANYWAY in backups else NOT_APPLICABLE,
                       would_rethink_if=[], how_settled="firm")
        out.update(main_reason="other", second_reason=NONE)
        return out


class ThinkLLM(L.LLMDecider):
    """LLMDecider plumbing (cache, log, retry on an invalid reply, stop on fatal errors) for think-v1."""

    def __init__(self, cfg: Config, backend: Any, fallback: Decider, log_path: Path,
                 cache: L.LLMCache | None) -> None:
        super().__init__(cfg, backend, fallback, log_path, cache)
        self.system = THINK_SYSTEM
        self.template_id = THINK_TEMPLATE_ID

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

class ThinkDecider:
    """Arm H-clock. run.py passes every commuter with a real choice each morning; this class decides
    who answers (the routine, the base rule, or the LLM) and returns one Decision per commuter, in
    order.

    Decision.decider is "rule" (the first day; a day on which today's way has no option), "standing"
    (the routine, including its back-up), "llm" or "llm-fallback-rule". Decision.meta["set_standing"]
    is False on days that are not the main way of the arrangement, so memory keeps the main option as
    the standing one."""

    name = "hybrid"

    def __init__(self, cfg: Config, run_dir: Path, rule: Decider, backend: str | None = None) -> None:
        self.cfg, self.rule = cfg, rule
        kind = backend or cfg.run.backend
        if kind == "mock":
            self.backend: Any = ThinkMock(cfg)
            cache = None
        elif kind == "anthropic":
            self.backend = L.AnthropicLLM(cfg)
            cache = L.LLMCache(cfg.resolve_path(cfg.llm.cache_dir))
        else:
            raise ValueError(f"unknown LLM backend {kind!r}")
        self.llm = ThinkLLM(cfg, self.backend, rule, Path(run_dir) / "llm_calls.jsonl", cache)
        self.plans: dict[int, Plan] = {}
        self.since: dict[int, int] = {}            # day the present arrangement started
        self.answered: dict[int, int] = {}         # day of the LLM's last lasting answer
        self.notes: dict[int, list[tuple[int, str]]] = {}   # disrupted bus or train days: (day, what they did)
        self.charged_before = False
        self.log_path = Path(run_dir) / "plan_log.jsonl"

    @property
    def stats(self) -> dict:
        return self.llm.stats

    def close(self) -> None:
        self.llm.close()

    def _why(self, ctx: DecisionContext, plan: Plan) -> str | None:
        """Reason for a lasting question today, or None."""
        t, p = ctx.today, ctx.persona
        if "T2" in ctx.triggers and not p.company_car and (plan.uses_car() or not t.fee_active):
            return "charge"
        if plan.review_day is not None and ctx.day >= plan.review_day:
            return "review"
        last = self.answered.get(ctx.agent_id)
        if last is not None and ctx.day - last < ASK_AGAIN_AFTER:
            return None
        rethink = DEFAULT_RETHINK if last is None else plan.reconsider
        if "late_twice_in_a_week" in rethink and "T3" in ctx.triggers:
            tol = _tolerance(ctx, self.cfg)
            if sum(1 for r in ctx.recent if r.day >= plan.made_on and r.late_min is not None
                   and r.late_min > tol) >= 2:
                return "late"
        if "trip_much_longer" in rethink and "T5" in ctx.triggers:
            cars = [r for r in ctx.recent if r.mode == "CAR" and r.travel_min is not None
                    and r.expected_travel_min is not None]
            if cars and cars[-1].travel_min > cars[-1].expected_travel_min:
                return "trip"
        return None

    def _apply(self, ctx: DecisionContext, reply: Mapping[str, Any], offers: Mapping[str, Option],
               old: Plan) -> Plan:
        def resolve(cid: str) -> tuple[str, Option]:
            o = offers[cid]
            return (old.usual if cid == KEEP else strategy_of(o)), o

        s1, o1 = resolve(reply["what_i_do"])
        other, k = None, 0
        slots = dict(old.slots)
        slots[s1] = o1.option_id
        c2, days = reply["second_choice"], int(reply["days_a_week_on_second"])
        if c2 not in (NONE, reply["what_i_do"]) and days > 0:
            s2, o2 = resolve(c2)
            if s2 != s1:
                other, k = s2, days
                slots[s2] = o2.option_id
        trial = int(reply["trying_it_out_for_days"])
        new = Plan(usual=s1, other=other, other_days=k, if_bus_disrupted=reply["if_bus_disrupted"],
                   reconsider=tuple(dict.fromkeys(x for x in reply["would_rethink_if"]
                                                  if x != "nothing_in_particular")),
                   review_day=(ctx.day + trial) if trial > 0 else None, settled=reply["how_settled"],
                   made_on=ctx.day, words=reply["in_my_words"].strip(), slots=slots)
        same = (new.usual, new.other, new.other_days, slots.get(s1)) == \
               (old.usual, old.other, old.other_days, old.slots.get(old.usual))
        if not same:
            self.since[ctx.agent_id] = ctx.day
        return new

    def _by_rule(self, ctx: DecisionContext) -> tuple[Decision, str]:
        d = self.rule.decide_batch([ctx])[0]
        return d, strategy_of(ctx.option(d.option_id))

    def decide_batch(self, contexts: Sequence[DecisionContext]) -> list[Decision]:
        n = len(contexts)
        groups = [by_strategy(c.options) for c in contexts]
        memo: dict[tuple[int, str], Option] = {}

        def pick(i: int, s: str) -> Option:
            if (i, s) not in memo:
                memo[(i, s)] = _pick(contexts[i], groups[i][s])
            return memo[(i, s)]

        task: list[str | None] = [None] * n
        why: list[str] = [""] * n
        offers: list[dict[str, Option]] = [{} for _ in range(n)]
        ask = []
        for i, c in enumerate(contexts):
            plan = self.plans.get(c.agent_id)
            if plan is None:
                continue
            w = self._why(c, plan)
            if w is not None:
                task[i], why[i] = "change", w
                offers[i] = change_offers(c, plan, groups[i], lambda s, i=i: pick(i, s), w)
            elif (strategy_on(plan, c.day) == "bus_or_train" and "bus_or_train" in groups[i]
                  and _bus_disrupted_today(c) and plan.if_bus_disrupted == NOT_APPLICABLE):
                task[i], why[i] = "today", "disruption"
                offers[i] = today_offers(groups[i], lambda s, i=i: pick(i, s))
            if task[i] is not None and len(offers[i]) < 2:
                task[i] = None                         # nothing to choose between: no question
            if task[i] is not None:
                if isinstance(self.backend, ThinkMock):
                    self.backend.offers[(c.agent_id, c.day)] = offers[i]
                ask.append((c, render_think_prompt(c, task[i], offers[i], plan, why[i], self.cfg,
                                                   self.since.get(c.agent_id), self.charged_before,
                                                   self.notes.get(c.agent_id, ())),
                            think_schema(task[i], offers[i], c)))
        replies = iter(self.llm.ask(ask))

        out: list[Decision] = []
        for i, c in enumerate(contexts):
            plan = self.plans.get(c.agent_id)
            g = groups[i]
            if plan is None:                           # no routine yet: the base model's rule sets it
                d, s = self._by_rule(c)
                plan = self.plans[c.agent_id] = Plan(usual=s, made_on=c.day, slots={s: d.option_id})
                self.since[c.agent_id] = c.day
                self._record(c, plan, s, d.option_id, "rule", "base", True)
                out.append(Decision(agent_id=c.agent_id, day=c.day, option_id=d.option_id, decider="rule",
                                    reason=d.reason, factors=tuple(d.factors),
                                    meta={"set_standing": True, "handler": "base", "strategy": s}))
                continue
            handler, new_plan, reason, factors = "plan", False, "", ()
            oid: str | None = None
            if task[i] is not None:
                reply = next(replies)
                if reply is None:                      # no valid answer: the rule decides over everything
                    d, s = self._by_rule(c)
                    if task[i] == "change":
                        plan.usual, plan.other, plan.other_days = s, None, 0
                        plan.slots[s] = d.option_id
                        plan.review_day, plan.made_on = None, c.day
                        self.since[c.agent_id] = c.day
                        new_plan = True
                    out.append(self._finish(c, plan, s, d.option_id, "llm-fallback-rule", d.reason,
                                            tuple(d.factors), f"{task[i]}:{why[i]}", new_plan))
                    continue
                handler, reason, factors = "llm", reply["in_my_words"].strip(), _reasons(reply)
                if task[i] == "today":
                    o = offers[i][reply["what_i_do_today"]]
                    s, oid = strategy_of(o), o.option_id
                    if reply["same_whenever_disrupted"]:
                        plan.if_bus_disrupted = BUS_ANYWAY if s == "bus_or_train" else s
                else:
                    plan = self.plans[c.agent_id] = self._apply(c, reply, offers[i], plan)
                    self.answered[c.agent_id] = c.day
                    new_plan = True
                    s = strategy_on(plan, c.day)
            else:
                s = strategy_on(plan, c.day)
            hit = _bus_disrupted_today(c) and (task[i] == "today" or s == "bus_or_train")
            if task[i] != "today" and hit:
                alt = plan.if_bus_disrupted
                if alt in g and alt != "bus_or_train":
                    s, handler = alt, ("contingency" if handler == "plan" else handler)
            if hit:                                    # remembered for the next time the commuter thinks
                self.notes.setdefault(c.agent_id, []).append((c.day, s))
            if s not in g and plan.usual in g:         # today's way has no option: the main way instead
                s = plan.usual
            if s not in g:                             # nor has the main way (every car time is charged
                d, s = self._by_rule(c)                # above what they would pay): the rule, for today
                out.append(self._finish(c, plan, s, d.option_id, "rule", d.reason, tuple(d.factors),
                                        "unavailable", False, set_standing=False))
                continue
            if oid is None:                            # the routine: the same departure as last time
                slot = plan.slots.get(s)
                oid = slot if slot in {o.option_id for o in g[s]} else pick(i, s).option_id
                plan.slots[s] = oid
            decider = "llm" if handler == "llm" else "standing"
            label = f"{task[i]}:{why[i]}" if task[i] is not None else handler
            out.append(self._finish(c, plan, s, oid, decider, reason, factors, label, new_plan))
        if contexts and contexts[0].today.fee_active:
            self.charged_before = True
        return out

    def _record(self, ctx: DecisionContext, plan: Plan | None, strategy: str, option_id: str,
                decider: str, handler: str, with_plan: bool) -> None:
        rec = {"day": ctx.day, "agent_id": ctx.agent_id, "handler": handler, "decider": decider,
               "strategy": strategy, "option_id": option_id, "triggers": list(ctx.triggers)}
        if with_plan and plan is not None:
            rec["plan"] = plan.public()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")

    def _finish(self, ctx: DecisionContext, plan: Plan, strategy: str, option_id: str, decider: str,
                reason: str, factors: Sequence[str], handler: str, new_plan: bool,
                set_standing: bool | None = None) -> Decision:
        self._record(ctx, plan, strategy, option_id, decider, handler, new_plan or handler.startswith("today"))
        keep = (strategy == plan.usual) if set_standing is None else set_standing
        return Decision(agent_id=ctx.agent_id, day=ctx.day, option_id=option_id, decider=decider,
                        reason=reason, factors=tuple(factors),
                        meta={"set_standing": keep, "handler": handler, "strategy": strategy})


def make_hybrid_decider(cfg: Config, run_dir: Path, rule: Decider, backend: str | None = None) -> ThinkDecider:
    """The H-clock decider, writing run_dir/llm_calls.jsonl and run_dir/plan_log.jsonl."""
    return ThinkDecider(cfg, run_dir, rule, backend)
