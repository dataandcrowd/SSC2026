"""Options and generalised costs (NZ$), shared by rules, MockLLM and the LLM prompt.

GC per option, with a = VoT/60 and k = kappa_H (x kappa_h_disc_factor at a discontinuity wake):

    CAR at depart d:  R = public road delay on the agent's route when leaving at d (TodayInfo.public_road:
                      usual traffic on day 1, yesterday's traffic later; 0 with roads off);
                      g = d + fftt_to_gate + floor(R + 0.5); D = public_delay(g) * delay_ratio_ema
                      (the ratio stays queue-only: R is already route-specific);
                      x = g + round(D) (fee minute); arr = x + fftt_gate_to_dest
                      time     = a * (fftt_total + R + D)
                      schedule = phi * sched_mult * a * (beta_ratio * early + gamma_ratio * late)
                      fee      = c * (f + eta * max(0, f - ref_fee)), f = fee_by_minute[x], c = 0 for company cars
                      parking  = persona.parking_cost
                      fuel     = persona.fuel_cost = 2 * path_km * costs.fuel_cost_per_km (round trip, to
                                 the cent; 0 for company cars; fixed from evidence, not calibrated)
    PT:               pt = omega * (a * T_pt + PAP) + fare   (T_pt x disruption multiplier if announced on own
                      corridor; PAP = costs.pt_attitude_penalty, integrator addition, 0 = specification;
                      T_pt is not affected by road traffic: rail and busway assumption)
                      schedule = phi * sched_mult * a * beta_ratio * early, where services leave on a
                      costs.pt_headway_min grid and the rider takes the latest one arriving by t*
                      (final fixer; headway 0 = arrive exactly at t*, the earlier behaviour)
    WFH:              wfh = wfh_cost * phi                                  (costs.wfh_form = "spec")
                      wfh = wfh_cost * phi + a * fftt_total + parking_cost + fuel_cost   ("v3_relative")
                      v3 6.2 prices WFH relative to driving at the usual time with no charge and
                      gives it no PARK credit (zero-fee property); in absolute GC this means WFH
                      does not save the free-flow commute time, the parking cost or the fuel cost
                      (fuel follows the parking logic, so WFH relative to an uncharged, unqueued
                      drive stays k_WFH x phi), but it does avoid congestion delay (road traffic and
                      the gate queue), schedule delay and the charge (behaviour recalibration; fuel addition)
    SKIP (postpone or cancel the day) was removed on 2026-10-09 [author decision]: it had become a
    permanent choice for some commuters rather than a one-day postponement.
    Early start (2026-10-05): a commuter with persona.early_shift_ok whose usual start t* is later than
    costs.early_start_min may work the earlier day. Every CAR and PT option is then measured against the
    cheaper of two starts: t* (schedule as above), or the early start, with the same schedule formula
    against that start plus costs.early_shift_cost x phi (added to the "schedule" part). Ties keep t*.
    Option.start_used_min / Option.early_shift record the start; early_min and late_min refer to it,
    and so do the outcome row, the memory record and trigger T3. For PT the service is the latest one
    arriving by the start used. Such a commuter is also offered the car departures around the reference
    departure of each start (time.anchor_offsets_min) on top of the standing +/- retime set.
    Reference departure of a start (start_anchor_depart): the latest grid departure d with
    d + fftt_total + floor(R_d + 0.5) + time.initial_buffer_min <= start, using today's public road
    delays (usual traffic on day 1, so day-1 drivers are not systematically late); with roads off
    this is start - fftt_total - buffer floored to the grid.
    Habit (every mode): habit = k for every option that differs from the standing option (until
    2026-10-09 a standing SKIP was not a habit and the last other option was the reference).
    Willingness to travel (2026-10-09, author decision): each commuter would pay at most persona.wtp_fee a
    day to drive into the city centre (exponential decay in the charge, persona.willingness_to_pay). A CAR
    option whose charge Option.fee (the fee at its expected gate exit) is above it is not offered
    (wtt_filter), so cheaper shoulder departures stay and a commuter unwilling to pay any of them takes PT
    or works from home. A company car (the employer pays) and a commuter with neither PT nor WFH (an
    essential trip) keep every car option. On an uncharged day every fee is 0 and nothing is removed.
    build_options applies it unless wtt=False, so every decider (rule, MockLLM, LLM) sees the same options.

Public API:
    departure_grid(cfg) -> list[int]                          # every departure a CAR option can have
    car_departures(standing_depart_min, cfg, persona=None, today=None) -> list[int]
    early_start_for(persona, cfg) -> int | None               # early start if allowed and earlier than t*
    expected_road_delay(persona, today, depart_min, cfg) -> float   # public road delay R (0 without)
    start_anchor_depart(persona, start_min, cfg, today=None) -> int
    initial_depart_min(persona, cfg, today=None) -> int
    public_delay_profile(outcomes, corridor_ids, bin_min) -> DelayProfile
    expected_public_delay(profile, corridor_id, gate_arrive_min, bin_min=None) -> float
    feasible_modes(persona, today, cfg) -> tuple[str, ...]
    build_options(persona, memory, today, params, cfg, discontinuity, wtt=True) -> tuple[Option, ...]
    wtt_filter(persona, options) -> tuple[Option, ...]       # drop CAR options charged above persona.wtp_fee
    car_outcome(persona, engine_row, option_id) -> dict      # outcomes.csv row for a car agent
    non_car_outcome(persona, option, day, pt_disrupted, disruption_mult=2.0) -> dict
    gc_rank(options, option_id) -> int                        # 1 = lowest GC
    fee_faced(persona, memory, options, cfg, today=None) -> float   # charge at the car reference departure
                                                              # (pass the options built with wtt=False)

``today`` in the departure helpers supplies the public road delays; without it (or with roads off)
they use free-flow roads. Pass the same TodayInfo that build_options gets. Every departure these
helpers read the public road delay for is on departure_grid (run.public_road computes only those).
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from cordonlite.config import Config
from cordonlite.memory import AgentMemory
from cordonlite.roads import road_delay_at
from cordonlite.types import (GC_PARTS, DelayProfile, Option, Persona, TodayInfo, TraitParams,
                              option_id_for)

OUTCOME_ROW_COLUMNS: tuple[str, ...] = (
    "agent_id", "day", "mode", "option_id", "corridor_id", "depart_min", "road_delay_min",
    "gate_arrive_min", "gate_exit_min", "queue_delay_min", "arrive_min", "travel_min", "early_min",
    "late_min", "fee_paid", "parking_paid", "fuel_paid", "pt_fare_paid", "pt_disrupted",
    "start_used_min", "early_shift",
)


def _round_half_away(x: float) -> int:
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def _floor_to_grid(x: float, cfg: Config) -> int:
    t = cfg.time
    m = t.depart_earliest_min + t.depart_step_min * math.floor((x - t.depart_earliest_min) / t.depart_step_min)
    return int(min(max(m, t.depart_earliest_min), t.depart_latest_min))


def departure_grid(cfg: Config) -> list[int]:
    """Every car departure an option can have: the grid time.depart_earliest_min + k x depart_step_min
    up to time.depart_latest_min, plus depart_latest_min itself (the clip in _floor_to_grid)."""
    t = cfg.time
    out = list(range(int(t.depart_earliest_min), int(t.depart_latest_min) + 1, int(t.depart_step_min)))
    if out[-1] != int(t.depart_latest_min):
        out.append(int(t.depart_latest_min))
    return out


def early_start_for(persona: Persona, cfg: Config) -> int | None:
    """Start of the earlier working day if the employer allows it and it is earlier than t*; else None."""
    e = int(cfg.costs.early_start_min)
    return e if (persona.early_shift_ok and e < persona.tstar_min) else None


def expected_road_delay(persona: Persona, today: TodayInfo | None, depart_min: int, cfg: Config) -> float:
    """Public road delay R (min) on the persona's route when leaving at ``depart_min``.

    From TodayInfo.public_road (usual traffic on day 1, yesterday's traffic later); 0.0 without
    ``today``, with roads off (empty mapping) or outside the published departure minutes."""
    if today is None:
        return 0.0
    return road_delay_at(today.public_road, persona.agent_id, depart_min, cfg.time.sim_start_min)


def start_anchor_depart(persona: Persona, start_min: int, cfg: Config, today: TodayInfo | None = None) -> int:
    """Reference departure for a start time: the latest grid departure d (window-clipped) with
    d + free-flow time + floor(R_d + 0.5) + buffer <= start, R_d = expected_road_delay (today's
    public road delays); the earliest departure when none qualifies.

    Without road information R_d = 0 and this is start - free-flow time - buffer, floored to the
    grid, clipped. Road delay is never negative, so the search walks down the grid from that
    free-flow departure."""
    t = cfg.time
    d = _floor_to_grid(start_min - persona.fftt_total_min - t.initial_buffer_min, cfg)
    if today is None or not today.public_road:
        return d
    while d > t.depart_earliest_min and (
            d + persona.fftt_total_min + math.floor(expected_road_delay(persona, today, d, cfg) + 0.5)
            + t.initial_buffer_min > start_min):
        d = _floor_to_grid(d - t.depart_step_min, cfg)
    return d


def car_departures(standing_depart_min: int, cfg: Config, persona: Persona | None = None,
                   today: TodayInfo | None = None) -> list[int]:
    """Standing departure +/- retime offsets, snapped to the grid, clipped to the window, unique.

    With a ``persona`` that may start early (early_start_for), the departures around the reference
    departure of the early start and of the usual start (+/- time.anchor_offsets_min) are added, so
    both starts stay reachable whatever the standing departure is (reference departures use
    ``today``'s public road delays, see start_anchor_depart)."""
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
                anchor = start_anchor_depart(persona, start, cfg, today)
                for off in t.anchor_offsets_min:
                    for d in (anchor - off, anchor + off):
                        out.add(int(min(max(d, t.depart_earliest_min), t.depart_latest_min)))
    return sorted({_floor_to_grid(d, cfg) for d in out})


def initial_depart_min(persona: Persona, cfg: Config, today: TodayInfo | None = None) -> int:
    """Day-1 reference departure: start_anchor_depart for t* (t* - free-flow time - expected road
    delay - buffer, on the grid, clipped)."""
    return start_anchor_depart(persona, persona.tstar_min, cfg, today)


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


# expected_public_delay runs for every car option of every agent every day. The interpolation arrays
# of a corridor are built once per DelayProfile object (public_delay_profile makes a new one each day)
# and every (gate arrival, bin) value is kept, instead of rebuilding the arrays on every call. The
# cache holds the profile and each corridor's points, so a new profile, or points replaced in a
# profile, start afresh; the values are the ones the uncached computation gives.
_PUBLIC_DELAY_CACHE: list = [None, {}]   # [DelayProfile, {corridor_id: (points, xs, ys, {key: delay})}]


def _interp_public_delay(xs: np.ndarray, ys: np.ndarray, g: float, h: float) -> float:
    if g < xs[0] - h or g > xs[-1] + h:
        return 0.0
    return float(np.interp(g, xs, ys))


def expected_public_delay(profile: DelayProfile, corridor_id: int, gate_arrive_min: int,
                          bin_min: int | None = None) -> float:
    """Linear interpolation over bin mid-points; 0 with no data or outside the observed range.

    With ``bin_min`` the range is widened by half a bin on each side (edge values held), so a
    gate arrival inside the first or last observed bin gets that bin's delay.
    """
    c = int(corridor_id)
    pts = profile.get(c, ())
    if not pts:
        return 0.0
    h = bin_min / 2.0 if bin_min else 0.0
    g = float(gate_arrive_min)
    if not isinstance(pts, tuple):   # a mutable sequence could change behind the cache
        return _interp_public_delay(np.fromiter((p[0] for p in pts), dtype=float),
                                    np.fromiter((p[1] for p in pts), dtype=float), g, h)
    if _PUBLIC_DELAY_CACHE[0] is not profile:
        _PUBLIC_DELAY_CACHE[0], _PUBLIC_DELAY_CACHE[1] = profile, {}
    by_c = _PUBLIC_DELAY_CACHE[1]
    ent = by_c.get(c)
    if ent is None or ent[0] is not pts:
        ent = (pts, np.fromiter((p[0] for p in pts), dtype=float),
               np.fromiter((p[1] for p in pts), dtype=float), {})
        by_c[c] = ent
    v = ent[3].get((g, h))
    if v is None:
        v = ent[3][(g, h)] = _interp_public_delay(ent[1], ent[2], g, h)
    return v


def feasible_modes(persona: Persona, today: TodayInfo, cfg: Config) -> tuple[str, ...]:
    """CAR always; PT if allowed (a disrupted corridor keeps PT feasible but slower); WFH if allowed.
    The willingness to pay may remove car departures, never the mode as such (wtt_filter)."""
    modes = ["CAR"]
    if persona.pt_allowed and not persona.must_drive:
        modes.append("PT")
    if persona.wfh_allowed:
        modes.append("WFH")
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


def car_reference_depart(persona: Persona, memory: AgentMemory, cfg: Config,
                         today: TodayInfo | None = None) -> int:
    """Centre of today's departure grid: standing car departure, else last car day, else day-1 rule
    (initial_depart_min with ``today``'s public road delays)."""
    if memory.standing_depart_min is not None:
        return int(memory.standing_depart_min)
    last = memory.last_car_depart_min()
    return last if last is not None else initial_depart_min(persona, cfg, today)


def build_options(persona: Persona, memory: AgentMemory, today: TodayInfo, params: TraitParams,
                  cfg: Config, discontinuity: bool, wtt: bool = True) -> tuple[Option, ...]:
    """Offered options with GC and prompt attributes; order CAR by depart, PT, WFH.

    With ``wtt`` (the default) the CAR options charged above the commuter's willingness to pay are
    left out (wtt_filter); wtt=False gives every feasible option (for fee_faced and the diagnostics).
    The filter changes no option that stays."""
    a = persona.vot / 60.0
    cc = cfg.costs
    standing = memory.standing_option_id
    k = params.kappa_h * (cfg.traits.kappa_h_disc_factor if discontinuity else 1.0)
    modes = feasible_modes(persona, today, cfg)
    fees = today.fee_by_minute
    c_fee = 0.0 if persona.company_car else 1.0
    phi_s = params.phi * persona.sched_mult

    def habit(oid: str) -> float:
        return 0.0 if standing is None or oid == standing else float(k)

    out: list[Option] = []
    for d in car_departures(car_reference_depart(persona, memory, cfg, today), cfg, persona, today):
        oid = option_id_for("CAR", d)
        R = expected_road_delay(persona, today, d, cfg)      # 0.0 with roads off
        g = d + persona.fftt_to_gate_min + math.floor(R + 0.5)
        d_pub = expected_public_delay(today.public_delay, persona.corridor_id, g, cc.delay_bin_min)
        D = d_pub * memory.delay_ratio_ema
        x = g + _round_half_away(D)
        arr = x + persona.fftt_gate_to_dest_min
        start, is_early, early, late, sched = effective_start(arr, persona, params, cfg)
        f = float(fees[min(max(x, 0), len(fees) - 1)])
        parts = _parts(
            time=a * (persona.fftt_total_min + R + D),
            schedule=sched,
            fee=c_fee * (f + params.eta * max(0.0, f - memory.ref_fee)),
            parking=persona.parking_cost,
            fuel=persona.fuel_cost,
            habit=habit(oid),
        )
        out.append(Option(
            option_id=oid, mode="CAR", depart_min=d, expected_gate_arrive_min=g,
            expected_delay_min=D, expected_gate_exit_min=x,
            expected_travel_min=float(persona.fftt_total_min + R + D), expected_arrive_min=arr,
            early_min=early, late_min=late, fee=f, parking=float(persona.parking_cost),
            pt_time_min=None, pt_fare=None, is_standing=(oid == standing),
            gc=_gc(parts), gc_parts=parts, expected_public_delay_min=d_pub,
            fuel=float(persona.fuel_cost), start_used_min=start, early_shift=is_early,
            expected_road_delay_min=R,
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
    return wtt_filter(persona, out) if wtt else tuple(out)


def wtt_filter(persona: Persona, options: Sequence[Option]) -> tuple[Option, ...]:
    """The options left once the willingness to pay is applied (2026-10-09).

    A CAR option whose levied charge ``Option.fee`` (at its expected gate exit) is above
    ``persona.wtp_fee`` is removed; a charge equal to it stays. Nothing is removed for a company car
    (the employer pays the charge), for a commuter with no PT or WFH option (an essential trip: the
    must-drive trades, or no PT where WFH is not allowed) or when wtp_fee is infinite (wtt.beta0 = 0).
    Order and every other option are unchanged."""
    if persona.company_car or math.isinf(persona.wtp_fee) or all(o.mode == "CAR" for o in options):
        return tuple(options)
    return tuple(o for o in options if o.mode != "CAR" or o.fee <= persona.wtp_fee)


def car_outcome(persona: Persona, engine_row: Mapping[str, object], option_id: str | None = None,
                start_min: int | None = None) -> dict:
    """outcomes.csv row for a car agent from one engine outcome row (OUTCOME_COLUMNS).

    Early and late minutes are measured against ``start_min`` (the chosen option's
    ``start_used_min``; None = the usual start t*). Unserved cars (gate_exit_min == -1) keep the -1
    sentinels with travel/early/late empty. road_delay_min comes from the engine row (0 when the row
    has none: free-flow roads); it is known for unserved cars too.
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
        "road_delay_min": int(engine_row.get("road_delay_min", 0)),  # type: ignore[arg-type]
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
    """outcomes.csv row for PT/WFH (car-only fields None).

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


def fee_faced(persona: Persona, memory: AgentMemory, options: Sequence[Option], cfg: Config,
              today: TodayInfo | None = None) -> float:
    """Charge the agent faces today at its car reference departure (v3 5.2 ``fee-faced``).

    The reference departure is the centre of today's car grid (standing car departure, else the
    last car day, else the day-1 rule; ``car_reference_depart``), and the fee is the levied charge
    ``Option.fee`` of that CAR option (at its expected gate exit). 0 for company-car agents (the
    employer pays) and when that CAR option is not among ``options``. Call it with today's options
    built with wtt=False, so a reference departure removed by the willingness to pay still gives the
    charge the commuter faces, and with the TodayInfo they were built with (the day-1 rule uses its
    public road delays), before the standing option is updated.
    """
    if persona.company_car:
        return 0.0
    d0 = _floor_to_grid(car_reference_depart(persona, memory, cfg, today), cfg)
    for o in options:
        if o.mode == "CAR" and o.depart_min == d0:
            return float(o.fee)
    return 0.0
