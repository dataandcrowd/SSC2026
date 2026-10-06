"""Persona construction: Layer A (constraints, stream "A") and Layer B (traits, stream "B").

Adapted and simplified from ../docs/design_history/persona_design_v3.md sections 3 and 4 (see DEVIATIONS.md,
"Behaviour builder"). Layer A uses only ``stream(seed, "A")`` and Layer B only
``stream(seed, "B")``, so changing the archetype tables never changes any trait and vice versa.

Public API:
    build_personas(origins, corridors, cfg, n_agents=None, traits=None) -> list[Persona]
    draw_traits(n, cfg, rng) -> np.ndarray                 # (n, 4) int, columns H, F, P, S
    trait_params(persona, cfg) -> TraitParams              # v3 section 4.4 lookup
    disposition_sentences(persona) -> tuple[str, str, str, str]   # v3 section 4.5, order H, F, P, S
    TRAIT_SENTENCES: dict[str, tuple[str, ...]]
    personas_to_frame(personas) -> pd.DataFrame            # personas.csv (Persona fields, in order)
    agents_frame(personas) -> pd.DataFrame                 # engine agents.csv columns
    twin_pairs(personas) -> list[tuple[int, int]]          # (original agent_id, twin agent_id)
"""

from __future__ import annotations

import dataclasses
import math
from statistics import NormalDist
from typing import Sequence

import numpy as np
import pandas as pd

from cordonlite.config import Config, stream
from cordonlite.engine import AGENTS_COLUMNS
from cordonlite.types import Persona, TraitParams

TRAIT_NAMES: tuple[str, ...] = ("H", "F", "P", "S")

# v3 section 4.5, verbatim. Index = level - 1. Trait names never appear in prompts.
TRAIT_SENTENCES: dict[str, tuple[str, str, str, str, str]] = {
    "H": (
        "You have no fixed routine for this trip and readily try another way if it looks better.",
        "You have a loose routine for this trip and change it without much thought if another way looks better.",
        "You usually travel the way you did last time, but you will change when there is a clear reason.",
        "You mostly stick to your usual way of travelling and change only for a fairly strong reason.",
        "You almost always travel exactly as you did last time and rethink it only when something important changes.",
    ),
    "F": (
        "Leaving at a different time from usual, or rearranging your day, is a real burden for you.",
        "Leaving at a different time or rearranging your day is quite inconvenient for you.",
        "Changing when you leave, or rearranging your day, is possible but a nuisance.",
        "You can fairly easily leave at a different time or rearrange your day.",
        "You do not mind leaving an hour earlier or later, or rearranging your day, if it saves money or hassle.",
    ),
    "P": (
        "You strongly dislike buses and trains and avoid them even when they are practical.",
        "You would rather not use buses or trains, but you might if they were clearly better.",
        "You have no strong feelings about buses or trains and would use them if they were clearly worth it.",
        "You are fairly comfortable using buses or trains for this kind of trip.",
        "You are happy to use buses or trains and see them as a normal way to get to the city centre.",
    ),
    "S": (
        "A new charge does not bother you much. You treat it like any other cost.",
        "A new or higher charge annoys you a little more than its dollar value.",
        "A new or higher charge annoys you somewhat more than its dollar value.",
        "A new or higher charge feels like a loss, clearly more than its dollar value, until you get used to it.",
        "A new or higher charge feels like a real loss, much more than its dollar value, until you get used to it.",
    ),
}

# Persona fields that are NOT Layer A (used to detect twins).
_NON_A_FIELDS: frozenset[str] = frozenset({"agent_id", "H", "F", "P", "S"})


def _round_half_away(x: float) -> int:
    """Round half away from zero (Python's round() is banker's rounding)."""
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def _snap_tstar(z: float, cfg: Config) -> int:
    """Discretise a continuous start time onto the t* grid and clip it."""
    t = cfg.time
    k = _round_half_away((z - t.tstar_earliest_min) / t.tstar_step_min)
    m = t.tstar_earliest_min + k * t.tstar_step_min
    return int(min(max(m, t.tstar_earliest_min), t.tstar_latest_min))


def _quintiles(values: np.ndarray) -> np.ndarray:
    """Population quintile 1..5 by rank (stable; ties keep agent order)."""
    n = len(values)
    order = np.argsort(values, kind="stable")
    rank = np.empty(n, dtype=np.int64)
    rank[order] = np.arange(n)
    return 1 + (5 * rank) // max(n, 1)


def draw_traits(n: int, cfg: Config, rng: np.random.Generator) -> np.ndarray:
    """Draw (n, 4) trait levels 1..5 (columns H, F, P, S): latent N(0,1) cut at share boundaries."""
    z = rng.standard_normal((n, 4))
    out = np.empty((n, 4), dtype=np.int64)
    nd = NormalDist()
    for j, name in enumerate(TRAIT_NAMES):
        shares = getattr(cfg.traits, f"shares_{name}")
        cum = np.cumsum(shares)[:-1]
        bounds = np.array([nd.inv_cdf(min(max(c, 1e-12), 1 - 1e-12)) for c in cum])
        out[:, j] = 1 + np.searchsorted(bounds, z[:, j], side="right")
    return out


def build_personas(origins: pd.DataFrame, corridors: pd.DataFrame, cfg: Config,
                   n_agents: int | None = None, traits: str | None = None) -> list[Persona]:
    """Build n_agents personas from prep origins (weights) and corridors.

    Layer A draw order on stream "A": per base agent (origin by weight, VoT); then quintiles over
    the base agents; then per base agent (archetype, t*, company car, parking); then per base agent
    the early-start permission (persona.early_shift_prob by archetype). Fuel cost is
    derived (no draw): 2 x path_km x costs.fuel_cost_per_km, 0 for a company car. Twins: the last
    k = min(n_twins, n // 2) agents copy every Layer A field of agents 0..k-1 and keep their own
    Layer B draw. Layer B: draw_traits(n) on stream "B" (not used when traits == "off").
    """
    n = int(cfg.run.n_agents if n_agents is None else n_agents)
    traits = cfg.run.traits if traits is None else traits
    if traits not in ("on", "off"):
        raise ValueError("traits must be 'on' or 'off'")
    if n < 1:
        raise ValueError("n_agents must be >= 1")
    if len(origins) == 0:
        raise ValueError("origins is empty")
    known = set(int(c) for c in corridors["corridor_id"])
    bad = set(int(c) for c in origins["corridor_id"]) - known
    if bad:
        raise ValueError(f"origins refer to unknown corridors: {sorted(bad)}")

    pc, cc, tc = cfg.persona, cfg.costs, cfg.time
    k = min(cfg.persona.n_twins, n // 2)
    n_base = n - k

    w = origins["weight"].to_numpy(dtype=float)
    if np.any(w < 0) or w.sum() <= 0:
        raise ValueError("origin weights must be non-negative with a positive sum")
    p_origin = w / w.sum()

    rng_a = stream(cfg.run.seed, "A")
    origin_idx = np.empty(n_base, dtype=np.int64)
    vots = np.empty(n_base, dtype=float)
    for i in range(n_base):
        origin_idx[i] = rng_a.choice(len(origins), p=p_origin)
        vots[i] = rng_a.lognormal(pc.vot_mu, pc.vot_sigma)
    quint = _quintiles(vots)

    base = np.asarray(pc.arch_weight, dtype=float)
    tilt = np.asarray(pc.vot_tilt, dtype=float)
    pt_unavail = set(int(c) for c in cc.pt_unavailable_corridors)
    a_rows: list[dict] = []
    for i in range(n_base):
        q = int(quint[i])
        wa = base * tilt[:, q - 1]
        arch = int(rng_a.choice(5, p=wa / wa.sum())) + 1
        ai = arch - 1
        tstar = _snap_tstar(rng_a.normal(pc.tstar_mean_min[ai], pc.tstar_sd_min[ai]), cfg)
        p_cc = pc.company_car_prob_q5[ai] if q == 5 else pc.company_car_prob[ai]
        company = bool(rng_a.random() < p_cc)
        park_free = bool(rng_a.random() < pc.park_free_prob[ai])
        parking = 0.0 if (company or park_free) else float(pc.park_cost_paid[ai])

        o = origins.iloc[int(origin_idx[i])]
        corridor = int(o["corridor_id"])
        to_gate = max(1, _round_half_away(float(o["fftt_to_gate_min"])))
        to_dest = max(0, _round_half_away(float(o["fftt_gate_to_dest_min"])))
        must_drive = bool(pc.must_drive[ai])
        pt_ok = bool(pc.pt_allowed[ai]) and not must_drive and corridor not in pt_unavail
        a_rows.append(dict(
            origin_id=int(o["origin_id"]), corridor_id=corridor,
            x_nztm=float(o["x_nztm"]), y_nztm=float(o["y_nztm"]),
            fftt_to_gate_min=to_gate, fftt_gate_to_dest_min=to_dest,
            path_km=float(o["path_km"]),
            vot=float(vots[i]), vot_quintile=q, archetype=arch,
            activity=str(pc.activity[ai]), tstar_min=tstar,
            fixed_start=bool(pc.fixed_start[ai]), must_drive=must_drive,
            sched_mult=float(pc.sched_mult[ai]),
            pt_allowed=pt_ok, wfh_allowed=bool(pc.wfh_allowed[ai]) and not must_drive,
            company_car=company, parking_cost=parking,
            # fuel: round trip, to the cent so the rule and the prompt use the same number; the
            # employer pays for a company car / work vehicle (same rule as parking)
            fuel_cost=0.0 if company else round(2.0 * float(o["path_km"]) * float(cc.fuel_cost_per_km), 2),
            pt_time_min=round(cfg.pt_ratio(corridor) * (to_gate + to_dest) + cc.pt_access_min, 4),
            pt_fare=float(cc.pt_fare),
        ))
    # Early-start permission: one uniform draw per base agent AFTER every other Layer A draw, so no
    # earlier field changes with this addition (twins copy it with the rest of Layer A).
    for i in range(n_base):
        u = float(rng_a.random())
        a_rows[i]["early_shift_ok"] = bool(u < pc.early_shift_prob[a_rows[i]["archetype"] - 1])
    a_rows += [dict(a_rows[j]) for j in range(k)]

    if traits == "off":
        lv = int(cfg.traits.off_level)
        tr = np.full((n, 4), lv, dtype=np.int64)
    else:
        tr = draw_traits(n, cfg, stream(cfg.run.seed, "B"))

    return [Persona(agent_id=i, **a_rows[i], H=int(tr[i, 0]), F=int(tr[i, 1]),
                    P=int(tr[i, 2]), S=int(tr[i, 3])) for i in range(n)]


def trait_params(persona: Persona, cfg: Config) -> TraitParams:
    """Rule parameters from trait levels (v3 section 4.4)."""
    t = cfg.traits
    return TraitParams(kappa_h=float(t.kappa_h[persona.H - 1]), phi=float(t.phi[persona.F - 1]),
                       omega=float(t.omega[persona.P - 1]), eta=float(t.eta[persona.S - 1]))


def disposition_sentences(persona: Persona) -> tuple[str, str, str, str]:
    """One fixed sentence per trait level, order H, F, P, S (v3 section 4.5)."""
    return tuple(TRAIT_SENTENCES[name][getattr(persona, name) - 1] for name in TRAIT_NAMES)  # type: ignore[return-value]


def personas_to_frame(personas: Sequence[Persona]) -> pd.DataFrame:
    """personas.csv: one row per persona, Persona fields in declaration order."""
    cols = [f.name for f in dataclasses.fields(Persona)]
    return pd.DataFrame([dataclasses.asdict(p) for p in personas], columns=cols)


def agents_frame(personas: Sequence[Persona]) -> pd.DataFrame:
    """Engine agents.csv frame (x, y = origin NZTM coordinates)."""
    rows = [{"agent_id": p.agent_id, "corridor_id": p.corridor_id,
             "fftt_to_gate_min": int(p.fftt_to_gate_min),
             "fftt_gate_to_dest_min": int(p.fftt_gate_to_dest_min),
             "x": p.x_nztm, "y": p.y_nztm} for p in personas]
    return pd.DataFrame(rows, columns=list(AGENTS_COLUMNS))


def layer_a_key(persona: Persona) -> tuple:
    """Tuple of all Layer A fields (everything except agent_id and the traits)."""
    return tuple(getattr(persona, f.name) for f in dataclasses.fields(Persona)
                 if f.name not in _NON_A_FIELDS)


def twin_pairs(personas: Sequence[Persona]) -> list[tuple[int, int]]:
    """(original, twin) agent_id pairs: personas with identical Layer A, lowest id as original."""
    groups: dict[tuple, list[int]] = {}
    for p in personas:
        groups.setdefault(layer_a_key(p), []).append(p.agent_id)
    pairs: list[tuple[int, int]] = []
    for ids in groups.values():
        ids = sorted(ids)
        pairs += [(ids[0], j) for j in ids[1:]]
    return sorted(pairs)
