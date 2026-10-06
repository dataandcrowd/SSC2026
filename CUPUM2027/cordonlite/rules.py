"""Rule decider: random-utility choice over options, argmin of GC minus Gumbel noise.

Noise: eps_i ~ Gumbel(0, sigma_rule), one draw per option from
``stream(seed, "rule", noise_id, day, option_code(option_id))``. The choice is argmin_i
(gc_i - eps_i), which equals argmax_i (-gc_i + eps_i), so choice probabilities are multinomial
logit with scale sigma_rule (see DEVIATIONS.md). sigma_rule = 0 gives a pure argmin. Ties go to
the lower index.

Common random numbers (final fixer): the draw for an option depends on (noise_id, day, option id)
only, not on its position in the option list. ``noise_id`` is the agent's own id, except that a
twin uses the id of the agent whose Layer A it copies (``noise_ids``). Twins in the same state
therefore receive the same noise, so a difference in their choices comes from Layer B or their
history, never from independent noise.

Public API:
    class RuleDecider:                         # implements types.Decider
        name = "rule"
        def __init__(self, cfg, noise_ids=None) -> None   # noise_ids: {agent_id: noise_id}
        def decide(self, ctx) -> Decision
        def decide_batch(self, contexts) -> list[Decision]
    option_code(option_id) -> int              # CAR_hhmm -> hhmm, PT 10001, WFH 10002, SKIP 10003
    explain(ctx, option_id) -> tuple[str, tuple[str, ...]]   # templated reason and factors
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

from cordonlite.config import Config, stream
from cordonlite.types import GC_PARTS, Decision, DecisionContext, Option, clock_str

# GC part -> closed factor list (types.FACTORS)
PART_FACTOR: dict[str, str] = {
    "time": "travel_time", "schedule": "arrival_time", "fee": "fee", "parking": "other",
    "fuel": "other", "pt": "pt", "wfh": "flexibility", "skip": "work_constraint", "habit": "habit",
}
PART_LABEL: dict[str, str] = {
    "time": "travel time", "schedule": "arrival time", "fee": "the charge", "parking": "parking",
    "fuel": "fuel", "pt": "the PT trip", "wfh": "working from home", "skip": "missing the day", "habit": "changing routine",
}


def _describe(o: Option) -> str:
    if o.mode == "CAR":
        return f"drive at {clock_str(o.depart_min)}" + (" for the early start" if o.early_shift else "")  # type: ignore[arg-type]
    if o.mode == "PT" and o.early_shift:
        return "take PT for the early start"
    return {"PT": "take PT", "WFH": "work from home", "SKIP": "skip the trip"}[o.mode]


def explain(ctx: DecisionContext, option_id: str) -> tuple[str, tuple[str, ...]]:
    """Templated reason and factors: compare the choice with the standing option (or runner-up)."""
    chosen = ctx.option(option_id)
    others = [o for o in ctx.options if o.option_id != option_id]
    if not others:
        return f"Only option: {_describe(chosen)}.", ("work_constraint",)
    alt = None
    if ctx.standing_option_id and ctx.standing_option_id != option_id:
        alt = next((o for o in others if o.option_id == ctx.standing_option_id), None)
    if alt is None:
        alt = min(others, key=lambda o: o.gc)
    saving = {k: float(alt.gc_parts.get(k, 0.0)) - float(chosen.gc_parts.get(k, 0.0)) for k in GC_PARTS}
    pos = sorted((k for k in GC_PARTS if saving[k] > 1e-9), key=lambda k: (-saving[k], GC_PARTS.index(k)))
    factors: list[str] = []
    for k in pos[:3]:
        f = PART_FACTOR[k]
        if f not in factors:
            factors.append(f)
    if "T4" in ctx.triggers and "disruption" not in factors:
        factors.append("disruption")
    if not factors:
        factors = ["other"]
    driver = PART_LABEL[pos[0]] if pos else "overall cost"
    reason = (f"Chose to {_describe(chosen)} over {_describe(alt)}: lowest total cost "
              f"(NZ${chosen.gc:.2f} vs NZ${alt.gc:.2f}), mainly {driver}.")
    return reason, tuple(factors)


_MODE_CODE = {"PT": 10001, "WFH": 10002, "SKIP": 10003}


def option_code(option_id: str) -> int:
    """Stable non-negative integer for an option id (stream key part)."""
    if option_id.startswith("CAR_"):
        return int(option_id[4:])
    if option_id in _MODE_CODE:
        return _MODE_CODE[option_id]
    raise ValueError(f"unknown option id {option_id!r}")


class RuleDecider:
    """Deterministic random-utility decider over ``ctx.options``."""

    name = "rule"

    def __init__(self, cfg: Config, noise_ids: dict[int, int] | None = None) -> None:
        self.cfg = cfg
        self.sigma = float(cfg.rules.sigma_rule)
        self.seed = int(cfg.run.seed)
        self.noise_ids = dict(noise_ids or {})

    def noise(self, agent_id: int, day: int, option_ids: Sequence[str]) -> np.ndarray:
        """Gumbel(0, sigma) draws for (noise id of agent, day, option id), one per option."""
        if self.sigma <= 0.0:
            return np.zeros(len(option_ids))
        nid = int(self.noise_ids.get(int(agent_id), int(agent_id)))
        return np.array([stream(self.seed, "rule", nid, int(day), option_code(o)).gumbel(0.0, self.sigma)
                         for o in option_ids], dtype=float)

    def decide(self, ctx: DecisionContext) -> Decision:
        if not ctx.options:
            raise ValueError(f"agent {ctx.agent_id} day {ctx.day}: no options")
        gc = np.array([o.gc for o in ctx.options], dtype=float)
        eps = self.noise(ctx.agent_id, ctx.day, [o.option_id for o in ctx.options])
        util = gc - eps
        i = int(np.argmin(util))  # first minimum on ties
        oid = ctx.options[i].option_id
        reason, factors = explain(ctx, oid)
        return Decision(agent_id=ctx.agent_id, day=ctx.day, option_id=oid, decider="rule",
                        reason=reason, factors=factors,
                        meta={"gc": [float(x) for x in gc], "noise": [float(-e) for e in eps],
                              "sigma_rule": self.sigma})

    def decide_batch(self, contexts: Sequence[DecisionContext]) -> list[Decision]:
        return [self.decide(c) for c in contexts]
