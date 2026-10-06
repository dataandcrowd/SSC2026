"""Options and generalised costs (NZ$), shared by rules, MockLLM and the LLM prompt.

GC per option, with a = VoT/60 and k = kappa_H (x kappa_h_disc_factor at a discontinuity wake):

    CAR at depart d:  g = d + fftt_to_gate; D = public_delay(g) * delay_ratio_ema;
                      x = g + round(D) (fee minute); arr = x + fftt_gate_to_dest
                      time     = a * (fftt_total + D)
                      schedule = phi * sched_mult * a * (beta_ratio * early + gamma_ratio * late)
                      fee      = c * (f + eta * max(0, f - ref_fee)), f = fee_by_minute[x], c = 0 for company cars
                      parking  = persona.parking_cost
                      fuel     = persona.fuel_cost = 2 * path_km * costs.fuel_cost_per_km (round trip, to
                                 the cent; 0 for company cars; fixed from evidence, not calibrated)
    PT:               pt = omega * (a * T_pt + PAP) + fare   (T_pt x disruption multiplier if announced on own
                      corridor; PAP = costs.pt_attitude_penalty, integrator addition, 0 = specification)
                      schedule = phi * sched_mult * a * beta_ratio * early, where services leave on a
                      costs.pt_headway_min grid and the rider takes the latest one arriving by t*
                      (final fixer; headway 0 = arrive exactly at t*, the earlier behaviour)
    WFH:              wfh = wfh_cost * phi                                  (costs.wfh_form = "spec")
                      wfh = wfh_cost * phi + a * fftt_total + parking_cost + fuel_cost   ("v3_relative")
                      v3 6.2 prices WFH relative to driving at the usual time with no charge and
                      gives it no PARK credit (zero-fee property); in absolute GC this means WFH
                      does not save the free-flow commute time, the parking cost or the fuel cost
                      (fuel follows the parking logic, so WFH relative to an uncharged, unqueued
                      drive stays k_WFH x phi), but it does avoid congestion delay, schedule delay
                      and the charge (behaviour recalibration; fuel addition)
    SKIP:             skip = skip_cost + skip_vot_hours * VoT   (final fixer; skip_vot_hours 0 = spec)
    Early start (2026-10-05): a commuter with persona.early_shift_ok whose usual start t* is later than
    costs.early_start_min may work the earlier day. Every CAR and PT option is then measured against the
    cheaper of two starts: t* (schedule as above), or the early start, with the same schedule formula
    against that start plus costs.early_shift_cost x phi (added to the "schedule" part). Ties keep t*.
    Option.start_used_min / Option.early_shift record the start; early_min and late_min refer to it,
    and so do the outcome row, the memory record and trigger T3. For PT the service is the latest one
    arriving by the start used. Such a commuter is also offered the car departures around the reference
    departure of each start (time.anchor_offsets_min) on top of the standing +/- retime set.
    every option that differs from the habit reference: habit = k. The habit reference is the
    standing option, except that a standing SKIP is not a habit: then the most recent non-SKIP
    option is the reference (memory.AgentMemory.habit_option_id; final fixer).

Public API:
    car_departures(standing_depart_min, cfg, persona=None) -> list[int]
    early_start_for(persona, cfg) -> int | None               # early start if allowed and earlier than t*
    initial_depart_min(persona, cfg) -> int
    public_delay_profile(outcomes, corridor_ids, bin_min) -> DelayProfile
    expected_public_delay(profile, corridor_id, gate_arrive_min, bin_min=None) -> float
    feasible_modes(persona, today, cfg) -> tuple[str, ...]
    build_options(persona, memory, today, params, cfg, discontinuity) -> tuple[Option, ...]
    car_outcome(persona, engine_row, option_id) -> dict      # outcomes.csv row for a car agent
    non_car_outcome(persona, option, day, pt_disrupted, disruption_mult=2.0) -> dict
    gc_rank(options, option_id) -> int                        # 1 = lowest GC
    fee_faced(persona, memory, options, cfg) -> float         # charge at the car reference departure
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from cordonlite.config import Config
from cordonlite.memory import AgentMemory
from cordonlite.types import (GC_PARTS, DelayProfile, Option, Persona, TodayInfo, TraitParams,
                              option_id_for)

OUTCOME_ROW_COLUMNS: tuple[str, ...] = (
    "agent_id", "day", "mode", "option_id", "corridor_id", "depart_min", "gate_arrive_min",
    "gate_exit_min", "queue_delay_min", "arrive_min", "travel_min", "early_min", "late_min",
    "fee_paid", "parking_paid", "fuel_paid", "pt_fare_paid", "pt_disrupted",
    "start_used_min", "early_shift",
)


def _round_half_away(x: float) -> int:
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def _floor_to_grid(x: float, cfg: Config) -> int:
    t = cfg.time
    m = t.depart_earliest_min + t.depart_step_min * math.floor((x - t.depart_earliest_min) / t.depart_step_min)
    return int(min(max(m, t.depart_earliest_min), t.depart_latest_min))


def early_start_for(persona: Persona, cfg: Config) -> int | None:
    """Start of the earlier working day if the employer allows it and it is earlier than t*; else None."""
    e = int(cfg.costs.early_start_min)
    return e if (persona.early_shift_ok and e < persona.tstar_min) else None


def start_anchor_depart(persona: Persona, start_min: int, cfg: Config) -> int:
    """Reference departure for a start time: start - free-flow time - buffer, floored to the grid, clipped."""
    return _floor_to_grid(start_min - persona.fftt_total_min - cfg.time.initial_buffer_min, cfg)


def car_departures(standing_depart_min: int, cfg: Config, persona: Persona | None = None) -> list[int]:
    """Standing departure +/- retime offsets, snapped to the grid, clipped to the window, unique.

    With a ``persona`` that may start early (early_start_for), the departures around the reference
    departure of the early start and of the usual start (+/- time.anchor_offsets_min) are added, so
    both starts stay reachable whatever the standing departure is."""
    ref = _floor_to_grid(standing_depart_min, cfg)
    t = cfg.time
    out = set()
    for off in t.retime_offsets_min:
        for d in (ref - off, ref + off):
            out.add(int(min(max(d, t.depart_earliest_min), t.depart_latest_min)))
    if persona is not None:
        e = early_start_for(persona, cfg)
        if e is not None:
            for start in (e, persona.tstar_min):
                anchor = start_anchor_depart(persona, start, cfg)
                for off in t.anchor_offsets_min:
                    for d in (anchor - off, anchor + off):
                        out.add(int(min(max(d, t.depart_earliest_min), t.depart_latest_min)))
    return sorted({_floor_to_grid(d, cfg) for d in out})


def initial_depart_min(persona: Persona, cfg: Config) -> int:
    """Day-1 reference departure: t* - free-flow time - buffer, floored to the grid, clipped."""
    return start_anchor_depart(persona, persona.tstar_min, cfg)


def schedule_against(arr: float, start_min: int, phi_s: float, a: float, cfg: Config) -> tuple[float, float, float]:
    """(early min, late min, schedule-delay cost) of arriving at ``arr`` for a start at ``start_min``."""
    early = float(max(0, start_min - arr))
    late = float(max(0, arr - start_min))
    return early, late, phi_s * a * (cfg.costs.beta_ratio * early + cfg.costs.gamma_ratio * late)


def effective_start(arr: float, persona: Persona, params: TraitParams, cfg: Config
                    ) -> tuple[int, bool, float, float, float]:
    """Start an arrival at ``arr`` is measured against: (start, early_shift, early, late, schedule cost).

    The usual start t*, unless the commuter may start early and the early start is strictly cheaper
    once costs.early_shift_cost x phi is added (that cost is included in the returned schedule cost)."""
    a = persona.vot / 60.0
    phi_s = params.phi * persona.sched_mult
    e0, l0, c0 = schedule_against(arr, persona.tstar_min, phi_s, a, cfg)
    es = early_start_for(persona, cfg)
    if es is not None:
        e1, l1, c1 = schedule_against(arr, es, phi_s, a, cfg)
        c1 += float(cfg.costs.early_shift_cost) * params.phi
        if c1 < c0:
            return es, True, e1, l1, c1
    return int(persona.tstar_min), False, e0, l0, c0


def public_delay_profile(outcomes: pd.DataFrame | None, corridor_ids: Sequence[int],
                         bin_min: int) -> DelayProfile:
    """Mean queue delay by gate-arrival bin per corridor from yesterday's engine outcomes.

    Points are (bin mid-minute, mean delay), sorted. Unserved cars (-1) are ignored.
    None or an empty frame gives an empty profile for every corridor (day 1).
    """
    prof: dict[int, tuple[tuple[float, float], ...]] = {int(c): () for c in corridor_ids}
    if outcomes is None or len(outcomes) == 0:
        return prof
    df = outcomes[(outcomes["gate_exit_min"] >= 0) & (outcomes["queue_delay_min"] >= 0)]
    if len(df) == 0:
        return prof
    b = (df["gate_arrive_min"].to_numpy(dtype=np.int64) // int(bin_min))
    g = pd.DataFrame({"corridor_id": df["corridor_id"].to_numpy(dtype=np.int64), "bin": b,
                      "d": df["queue_delay_min"].to_numpy(dtype=float)})
    means = g.groupby(["corridor_id", "bin"], sort=True)["d"].mean()
    half = (int(bin_min) - 1) / 2.0
    for (c, bn), v in means.items():
        c = int(c)
        if c not in prof:
            prof[c] = ()
        prof[c] = prof[c] + ((float(bn * bin_min + half), float(v)),)
    return prof


def expected_public_delay(profile: DelayProfile, corridor_id: int, gate_arrive_min: int,
                          bin_min: int | None = None) -> float:
    """Linear interpolation over bin mid-points; 0 with no data or outside the observed range.

    With ``bin_min`` the range is widened by half a bin on each side (edge values held), so a
    gate arrival inside the first or last observed bin gets that bin's delay.
    """
    pts = profile.get(int(corridor_id), ())
    if not pts:
        return 0.0
    xs = np.fromiter((p[0] for p in pts), dtype=float)
    ys = np.fromiter((p[1] for p in pts), dtype=float)
    h = bin_min / 2.0 if bin_min else 0.0
    g = float(gate_arrive_min)
    if g < xs[0] - h or g > xs[-1] + h:
        return 0.0
    return float(np.interp(g, xs, ys))


def feasible_modes(persona: Persona, today: TodayInfo, cfg: Config) -> tuple[str, ...]:
    """CAR always; PT if allowed (a disrupted corridor keeps PT feasible but slower); WFH if allowed; SKIP."""
    modes = ["CAR"]
    if persona.pt_allowed and not persona.must_drive:
        modes.append("PT")
    if persona.wfh_allowed:
        modes.append("WFH")
    modes.append("SKIP")
    return tuple(modes)


def _parts(**kw: float) -> dict[str, float]:
    return {k: float(kw.get(k, 0.0)) for k in GC_PARTS}


def _gc(parts: Mapping[str, float]) -> float:
    total = 0.0
    for k in GC_PARTS:
        total += parts[k]
    return total


def pt_time_today(persona: Persona, today: TodayInfo) -> float:
    """Expected PT door-to-door minutes today (announced disruption on own corridor applied)."""
    t = float(persona.pt_time_min)
    if today.pt_disruption_announced and persona.corridor_id in today.pt_disrupted_corridors:
        t *= float(today.pt_disruption_time_mult)
    return t


def pt_depart_min(tstar_min: int, t_pt: float, headway_min: int) -> int:
    """Departure of the latest PT service (on a headway grid from midnight) arriving by t*."""
    t = _round_half_away(t_pt)
    if headway_min <= 0:
        return int(tstar_min - t)
    return int(headway_min * math.floor((tstar_min - t) / headway_min))


def skip_cost(persona: Persona, cfg: Config) -> float:
    """Cost of postponing or cancelling the day: base plus skip_vot_hours x VoT."""
    return float(cfg.costs.skip_cost + cfg.costs.skip_vot_hours * persona.vot)


def car_reference_depart(persona: Persona, memory: AgentMemory, cfg: Config) -> int:
    """Centre of today's departure grid: standing car departure, else last car day, else day-1 rule."""
    if memory.standing_depart_min is not None:
        return int(memory.standing_depart_min)
    last = memory.last_car_depart_min()
    return last if last is not None else initial_depart_min(persona, cfg)


def build_options(persona: Persona, memory: AgentMemory, today: TodayInfo, params: TraitParams,
                  cfg: Config, discontinuity: bool) -> tuple[Option, ...]:
    """Feasible options with GC and prompt attributes; order CAR by depart, PT, WFH, SKIP."""
    a = persona.vot / 60.0
    cc = cfg.costs
    standing = memory.habit_option_id
    k = params.kappa_h * (cfg.traits.kappa_h_disc_factor if discontinuity else 1.0)
    modes = feasible_modes(persona, today, cfg)
    fees = today.fee_by_minute
    c_fee = 0.0 if persona.company_car else 1.0
    phi_s = params.phi * persona.sched_mult

    def habit(oid: str) -> float:
        return 0.0 if standing is None or oid == standing else float(k)

    out: list[Option] = []
    for d in car_departures(car_reference_depart(persona, memory, cfg), cfg, persona):
        oid = option_id_for("CAR", d)
        g = d + persona.fftt_to_gate_min
        d_pub = expected_public_delay(today.public_delay, persona.corridor_id, g, cc.delay_bin_min)
        D = d_pub * memory.delay_ratio_ema
        x = g + _round_half_away(D)
        arr = x + persona.fftt_gate_to_dest_min
        start, is_early, early, late, sched = effective_start(arr, persona, params, cfg)
        f = float(fees[min(max(x, 0), len(fees) - 1)])
        parts = _parts(
            time=a * (persona.fftt_total_min + D),
            schedule=sched,
            fee=c_fee * (f + params.eta * max(0.0, f - memory.ref_fee)),
            parking=persona.parking_cost,
            fuel=persona.fuel_cost,
            habit=habit(oid),
        )
        out.append(Option(
            option_id=oid, mode="CAR", depart_min=d, expected_gate_arrive_min=g,
            expected_delay_min=D, expected_gate_exit_min=x,
            expected_travel_min=float(persona.fftt_total_min + D), expected_arrive_min=arr,
            early_min=early, late_min=late, fee=f, parking=float(persona.parking_cost),
            pt_time_min=None, pt_fare=None, is_standing=(oid == standing),
            gc=_gc(parts), gc_parts=parts, expected_public_delay_min=d_pub,
            fuel=float(persona.fuel_cost), start_used_min=start, early_shift=is_early,
        ))
    if "PT" in modes:
        t_pt = pt_time_today(persona, today)
        # the rider takes the latest service arriving by the start; with the early-start permission the
        # service for each start is priced and the cheaper start is used (ties keep the usual start)
        pt_start, pt_is_early = int(persona.tstar_min), False
        dep_pt = pt_depart_min(pt_start, t_pt, cc.pt_headway_min)
        arr_pt = dep_pt + _round_half_away(t_pt)
        early_pt, late_pt, sched_pt = schedule_against(arr_pt, pt_start, phi_s, a, cfg)
        es = early_start_for(persona, cfg)
        if es is not None:
            dep_e = pt_depart_min(es, t_pt, cc.pt_headway_min)
            arr_e = dep_e + _round_half_away(t_pt)
            early_e, late_e, sched_e = schedule_against(arr_e, es, phi_s, a, cfg)
            sched_e += float(cc.early_shift_cost) * params.phi
            if sched_e < sched_pt:
                pt_start, pt_is_early, dep_pt, arr_pt = es, True, dep_e, arr_e
                early_pt, late_pt, sched_pt = early_e, late_e, sched_e
        parts = _parts(pt=params.omega * (a * t_pt + cc.pt_attitude_penalty) + persona.pt_fare,
                       schedule=sched_pt,
                       habit=habit("PT"))
        out.append(Option(
            option_id="PT", mode="PT", depart_min=dep_pt,
            expected_gate_arrive_min=None, expected_delay_min=None, expected_gate_exit_min=None,
            expected_travel_min=t_pt, expected_arrive_min=arr_pt,
            early_min=early_pt, late_min=late_pt, fee=0.0, parking=0.0,
            pt_time_min=t_pt, pt_fare=float(persona.pt_fare), is_standing=(standing == "PT"),
            gc=_gc(parts), gc_parts=parts, start_used_min=pt_start, early_shift=pt_is_early,
        ))
    if "WFH" in modes:
        wfh = cc.wfh_cost * params.phi
        if cc.wfh_form == "v3_relative":
            wfh += a * persona.fftt_total_min + persona.parking_cost + persona.fuel_cost
        parts = _parts(wfh=wfh, habit=habit("WFH"))
        out.append(Option(
            option_id="WFH", mode="WFH", depart_min=None, expected_gate_arrive_min=None,
            expected_delay_min=None, expected_gate_exit_min=None, expected_travel_min=0.0,
            expected_arrive_min=None, early_min=0.0, late_min=0.0, fee=0.0, parking=0.0,
            pt_time_min=None, pt_fare=None, is_standing=(standing == "WFH"),
            gc=_gc(parts), gc_parts=parts,
        ))
    parts = _parts(skip=skip_cost(persona, cfg), habit=habit("SKIP"))
    out.append(Option(
        option_id="SKIP", mode="SKIP", depart_min=None, expected_gate_arrive_min=None,
        expected_delay_min=None, expected_gate_exit_min=None, expected_travel_min=0.0,
        expected_arrive_min=None, early_min=0.0, late_min=0.0, fee=0.0, parking=0.0,
        pt_time_min=None, pt_fare=None, is_standing=(standing == "SKIP"),
        gc=_gc(parts), gc_parts=parts,
    ))
    return tuple(out)


def car_outcome(persona: Persona, engine_row: Mapping[str, object], option_id: str | None = None,
                start_min: int | None = None) -> dict:
    """outcomes.csv row for a car agent from one engine outcome row (OUTCOME_COLUMNS).

    Early and late minutes are measured against ``start_min`` (the chosen option's
    ``start_used_min``; None = the usual start t*). Unserved cars (gate_exit_min == -1) keep the -1
    sentinels with travel/early/late empty.
    """
    start = int(persona.tstar_min if start_min is None else start_min)
    dep = int(engine_row["depart_min"])  # type: ignore[arg-type]
    exit_m = int(engine_row["gate_exit_min"])  # type: ignore[arg-type]
    arr = int(engine_row["arrive_min"])  # type: ignore[arg-type]
    served = exit_m >= 0
    return {
        "agent_id": persona.agent_id, "day": int(engine_row["day"]),  # type: ignore[arg-type]
        "mode": "CAR", "option_id": option_id or option_id_for("CAR", dep),
        "corridor_id": persona.corridor_id, "depart_min": dep,
        "gate_arrive_min": int(engine_row["gate_arrive_min"]),  # type: ignore[arg-type]
        "gate_exit_min": exit_m, "queue_delay_min": int(engine_row["queue_delay_min"]),  # type: ignore[arg-type]
        "arrive_min": arr,
        "travel_min": float(arr - dep) if served else None,
        "early_min": float(max(0, start - arr)) if served else None,
        "late_min": float(max(0, arr - start)) if served else None,
        "fee_paid": float(engine_row["fee_paid"]),  # type: ignore[arg-type]
        "parking_paid": float(persona.parking_cost),
        "fuel_paid": float(persona.fuel_cost),
        "pt_fare_paid": 0.0, "pt_disrupted": False,
        "start_used_min": start, "early_shift": bool(start != persona.tstar_min),
    }


def non_car_outcome(persona: Persona, option: Option, day: int, pt_disrupted: bool,
                    disruption_mult: float = 2.0) -> dict:
    """outcomes.csv row for PT/WFH/SKIP (car-only fields None).

    PT departs at ``option.depart_min``. If PT is disrupted on the agent's corridor today, the
    experienced time is ``persona.pt_time_min * disruption_mult`` (whether or not it was announced).
    Pass ``cfg.events.pt_disruption_time_mult`` as ``disruption_mult``.
    """
    if option.mode == "CAR":
        raise ValueError("non_car_outcome called with a CAR option")
    row = {c: None for c in OUTCOME_ROW_COLUMNS}
    row.update(agent_id=persona.agent_id, day=int(day), mode=option.mode, option_id=option.option_id,
               corridor_id=persona.corridor_id, fee_paid=0.0, parking_paid=0.0, fuel_paid=0.0, pt_fare_paid=0.0,
               early_min=0.0, late_min=0.0, travel_min=0.0, pt_disrupted=False, early_shift=False)
    if option.mode == "PT":
        start = int(persona.tstar_min if option.start_used_min is None else option.start_used_min)
        t = float(persona.pt_time_min) * (float(disruption_mult) if pt_disrupted else 1.0)
        dep = int(option.depart_min)  # type: ignore[arg-type]
        arr = dep + _round_half_away(t)
        row.update(depart_min=dep, arrive_min=arr, travel_min=t,
                   early_min=float(max(0, start - arr)),
                   late_min=float(max(0, arr - start)),
                   pt_fare_paid=float(persona.pt_fare), pt_disrupted=bool(pt_disrupted),
                   start_used_min=start, early_shift=bool(start != persona.tstar_min))
    return row


def gc_rank(options: Sequence[Option], option_id: str) -> int:
    """Rank of option_id by GC (1 = lowest); ties keep option order."""
    order = sorted(range(len(options)), key=lambda i: (options[i].gc, i))
    for r, i in enumerate(order, start=1):
        if options[i].option_id == option_id:
            return r
    raise KeyError(option_id)


def fee_faced(persona: Persona, memory: AgentMemory, options: Sequence[Option], cfg: Config) -> float:
    """Charge the agent faces today at its car reference departure (v3 5.2 ``fee-faced``).

    The reference departure is the centre of today's car grid (standing car departure, else the
    last car day, else the day-1 rule; ``car_reference_depart``), and the fee is the levied charge
    ``Option.fee`` of that CAR option (at its expected gate exit). 0 for company-car agents (the
    employer pays) and when no CAR option is offered. Call it with today's options before the
    standing option is updated.
    """
    if persona.company_car:
        return 0.0
    d0 = _floor_to_grid(car_reference_depart(persona, memory, cfg), cfg)
    for o in options:
        if o.mode == "CAR" and o.depart_min == d0:
            return float(o.fee)
    return 0.0
