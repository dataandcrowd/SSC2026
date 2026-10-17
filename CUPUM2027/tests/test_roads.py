"""Road congestion (SPEC 1.4, 1.5): hand-computed traversals, window and floor rules, free-flow
identity, order independence, the probe tables agents see, scenario files, PyEngine integration."""

from __future__ import annotations

import dataclasses
import json
import math
import random
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cordonlite import fees
from cordonlite import roads as R
from cordonlite.engine import (
    AGENTS_FILE, CORRIDORS_FILE, FEES_FILE, OUTCOME_COLUMNS, ROAD_COLUMNS, PyEngine,
)
from tests.conftest import write_tiny_road_data


def road_dir(d: Path, sections: list[tuple], routes: dict[int, list[int]], r: float | list[float] = 1.0,
             alpha: float = 1.0, floor: float = 0.18, window: int = 15, vpa: float = 0.0) -> Path:
    """Write the four road files. sections: (section_id, ff_min, cap_vph, bg_peak_vph, obs_peak_vph,
    w_factor); routes: agent_id -> section ids; r: one value for every minute or 1440 values."""
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(sections, columns=list(R.ROAD_SECTIONS_COLUMNS)).to_csv(d / R.ROAD_SECTIONS_FILE, index=False)
    pd.DataFrame([(a, k, s) for a, rt in sorted(routes.items()) for k, s in enumerate(rt)],
                 columns=list(R.AGENT_ROUTES_COLUMNS)).to_csv(d / R.AGENT_ROUTES_FILE, index=False)
    rr = [float(r)] * 1440 if np.isscalar(r) else list(r)
    pd.DataFrame({"minute": range(1440), "r": rr}).to_csv(d / R.ROAD_PROFILE_FILE, index=False)
    (d / R.ROAD_PARAMS_FILE).write_text(
        f"key,value\nbpr_alpha,{alpha!r}\nbpr_beta,4\nspeed_floor,{floor!r}\nflow_window_min,{window}\n"
        f"vehicles_per_agent,{vpa!r}\n")
    return d


def load(d: Path, *a: object, **k: object) -> R.RoadScenario:
    road = R.read_road_scenario(road_dir(d, *a, **k))
    assert road is not None
    return road


def cfg_with(cfg, **road: object):
    """The config with [road] values replaced."""
    return dataclasses.replace(cfg, road=dataclasses.replace(cfg.road, **road))


MWY_RULE = {"vc": 1.0, "rec": 0.95, "drop": 0.1, "jam": 0.45}


def mwy_load(d: Path, sections: list[tuple], routes: dict[int, list[int]], mwy: dict[int, tuple[int, int, int]],
             on: bool = True, rule: dict | None = None, **k: object) -> R.RoadScenario:
    """road_dir plus motorway breakdown (add_mwy)."""
    road_dir(d, sections, routes, **k)
    return add_mwy(d, mwy, on, rule)


def add_mwy(d: Path, mwy: dict[int, tuple[int, int, int]], on: bool = True, rule: dict | None = None) -> R.RoadScenario:
    """Add motorway breakdown to the road files in d: mwy maps section_id -> (mwy, bd_on, bd_off)
    (others 0, -1, -1); on writes mwy_breakdown 1 and the rule keys (MWY_RULE unless given), off
    writes mwy_breakdown 0."""
    sec = pd.read_csv(d / R.ROAD_SECTIONS_FILE, float_precision="round_trip")
    vals = [mwy.get(int(s), (0, -1, -1)) for s in sec["section_id"]]
    for j, c in enumerate(R.MWY_COLUMNS):
        sec[c] = [v[j] for v in vals]
    sec.to_csv(d / R.ROAD_SECTIONS_FILE, index=False)
    ru = {**MWY_RULE, **(rule or {})}
    with open(d / R.ROAD_PARAMS_FILE, "a") as fh:
        fh.write(f"mwy_breakdown,{int(on)}\nmwy_breakdown_vc,{ru['vc']!r}\nmwy_recover_vc,{ru['rec']!r}\n"
                 f"mwy_capacity_drop,{ru['drop']!r}\nmwy_jam_speed,{ru['jam']!r}\n")
    road = R.read_road_scenario(d)
    assert road is not None
    return road


def bpr(x: float, alpha: float) -> float:
    return 1 / (1 + alpha * ((x * x) * (x * x)))


def profile(base: float = 1.0, **at: float) -> list[float]:
    """1440 values of base, with r[m] = v for keyword m<minute>=v."""
    r = [base] * 1440
    for k, v in at.items():
        r[int(k[1:])] = v
    return r


# ----------------------------------------------------------------- hand-computed traversals

def test_one_section_rounds_half_up(tmp_path):
    # x = 1000 / 1000 = 1, f = 1 / (1 + 1 * 1) = 0.5, el = 2.5 / 0.5 = 5.0, extra = 2.5
    # road_delay = floor(2.5 + 0.5) = 3 (Python round(2.5) would give 2)
    road = load(tmp_path / "r", [(7, 2.5, 1000.0, 1000.0, 1000.0, 0.0)], {0: [7]})
    day = R.simulate_roads([(0, 400)], road)
    assert day.extra_min == {0: 2.5} and day.delay_min == {0: 3}
    assert day.entries == [(7, 400, 1)]


def test_two_sections_use_the_entry_minute(tmp_path):
    secs = [(0, 0.75, 1000.0, 1000.0, 1000.0, 0.0), (1, 1.5, 1000.0, 1000.0, 1000.0, 0.0)]
    # r = 1 everywhere: A at 400 (f 0.5, el 1.5), B at 401 (f 0.5, el 4.5); extra 2.25 -> 2
    day = R.simulate_roads([(0, 400)], load(tmp_path / "a", secs, {0: [0, 1]}))
    assert day.extra_min[0] == 2.25 and day.delay_min[0] == 2
    assert day.entries == [(0, 400, 1), (1, 401, 1)]
    # r[401] = 0: B is entered at 401 at free flow: el = 1.5 + 1.5, extra 0.75 -> 1
    day = R.simulate_roads([(0, 400)], load(tmp_path / "b", secs, {0: [0, 1]}, r=profile(m401=0.0)))
    assert day.extra_min[0] == 0.75 and day.delay_min[0] == 1
    # r[400] = 0: A ends at 0.75 < 1, so B is entered in the same minute 400, also at free flow
    day = R.simulate_roads([(0, 400)], load(tmp_path / "c", secs, {0: [0, 1]}, r=profile(m400=0.0)))
    assert day.extra_min[0] == 0.0 and day.delay_min[0] == 0
    assert day.entries == [(0, 400, 1), (1, 400, 1)]


def test_flow_window_counts_entries_strictly_before_the_minute(tmp_path):
    # fpe = ((25 * 1) * 60) / 15 = 100 veh/h per entry; cap 100, no background, alpha 1, ff 1:
    # one earlier entry in the window -> x = 1, f = 0.5, el = 2, delay floor(1.5) = 1
    road = load(tmp_path / "r", [(0, 1.0, 100.0, 0.0, 0.0, 1.0)], {0: [0], 1: [0]}, vpa=25.0)
    assert road.fpe == (100.0,)
    expect = {400: 0, 401: 1, 408: 1, 415: 1, 416: 0}   # car 0 enters at 400; window m-15 .. m-1
    for t, exp in expect.items():
        day = R.simulate_roads([(0, 400), (1, t)], road)
        assert day.delay_min[1] == exp, t
        assert day.delay_min[0] == 0


def test_speed_floor(tmp_path):
    # x = 2: f = 1 / (1 + 16) < 0.18 -> f = 0.18
    road = load(tmp_path / "a", [(0, 1.8, 1000.0, 2000.0, 2000.0, 0.0)], {0: [0]})
    day = R.simulate_roads([(0, 400)], road)
    assert day.extra_min[0] == 1.8 / 0.18 - 1.8
    assert day.delay_min[0] == math.floor(1.8 / 0.18 - 1.8 + 0.5) == 8
    road = load(tmp_path / "b", [(0, 1.8, 1000.0, 2000.0, 2000.0, 0.0)], {0: [0]}, floor=0.01)
    assert R.simulate_roads([(0, 400)], road).extra_min[0] == 1.8 / (1 / (1 + 1.0 * 16.0)) - 1.8


def test_ties_and_order_within_a_minute(tmp_path):
    secs = [(0, 0.6, 300.0, 100.0, 150.0, 1.0), (1, 2.2, 250.0, 120.0, 150.0, 0.5),
            (2, 1.3, 400.0, 50.0, 80.0, 1.0)]
    routes = {a: ([0, 1, 2] if a % 2 == 0 else [1, 2]) for a in range(12)}
    road = load(tmp_path / "r", secs, routes, r=profile(0.8), vpa=20.0)
    cars = [(a, 400 + (a // 4)) for a in range(12)]
    ref = R.simulate_roads(cars, road)
    # same departure and route -> same delay (entries of a minute are not read in that minute)
    assert ref.delay_min[0] == ref.delay_min[2] and ref.delay_min[1] == ref.delay_min[3]
    assert ref.extra_min[4] == ref.extra_min[6]
    assert sum(n for _s, _m, n in ref.entries) == sum(len(routes[a]) for a, _ in cars)
    assert max(ref.delay_min.values()) > 0
    rng = random.Random(5)
    for _ in range(5):
        shuffled = cars[:]
        rng.shuffle(shuffled)
        got = R.simulate_roads(shuffled, road)
        assert got.extra_min == ref.extra_min and got.delay_min == ref.delay_min
        assert got.entries == ref.entries


def test_free_flow_identity(tmp_path):
    # background 0 and vehicles_per_agent 0: v = 0, f = 1 exactly, el == ffsum, delay 0
    rng = np.random.default_rng(3)
    secs = [(s, float(rng.uniform(0.01, 3.0)), float(rng.uniform(50, 900)), 0.0, 500.0,
             float(rng.uniform(0, 1))) for s in range(20)]
    routes = {a: [int(x) for x in rng.choice(20, size=int(rng.integers(1, 12)), replace=False)] for a in range(40)}
    road = load(tmp_path / "r", secs, routes, r=list(rng.uniform(0, 1.2, 1440)), vpa=0.0)
    cars = [(a, int(rng.integers(360, 600))) for a in range(40)]
    day = R.simulate_roads(cars, road)
    assert set(day.delay_min.values()) == {0} and set(day.extra_min.values()) == {0.0}


def test_agents_without_route_and_no_scenario(tmp_path):
    road = load(tmp_path / "r", [(0, 2.5, 1000.0, 1000.0, 1000.0, 0.0)], {0: [0]})
    day = R.simulate_roads([(5, 400), (0, 401)], road)
    assert day.delay_min == {5: 0, 0: 3} and day.extra_min[5] == 0.0
    assert day.entries == [(0, 401, 1)]
    none = R.simulate_roads([(5, 400), (0, 401)], None)
    assert none.delay_min == {5: 0, 0: 0} and none.entries == []
    assert R.simulate_roads([], road).entries == []


# ----------------------------------------------------------------- motorway flow breakdown (2026-10-08)

def test_mwy_threshold_capacity_drop_jam_cap_and_floor(tmp_path):
    # one motorway section without a window, V/C x = background / capacity (r = 1, no commuters)
    a = 0.15

    def road_at(bg: float, tag: str, **rule: float) -> R.RoadScenario:
        return mwy_load(tmp_path / tag, [(0, 1.0, 1000.0, bg, bg, 1.0)], {0: [0]}, {0: (1, -1, -1)},
                        alpha=a, rule=rule)

    road = road_at(990.0, "below")
    assert not R.broken_down(road, 0, 400, 0.99) and R.speed_factor(road, 0, 400, 0) == bpr(0.99, a)
    road = road_at(1000.0, "at")          # at the threshold: y = 1 / 0.9 gives 0.81, capped at 0.45
    assert road.mwy_keep == 1 - 0.1 and R.broken_down(road, 0, 400, 1.0)
    assert R.speed_factor(road, 0, 400, 0) == 0.45 < bpr(1 / 0.9, a)
    road = road_at(1300.0, "drop", jam=1.0)   # no jam cap: the capacity drop alone
    y = 1.3 / (1 - 0.1)
    assert R.speed_factor(road, 0, 400, 0) == 1 / (1 + a * ((y * y) * (y * y))) < bpr(1.3, a)
    road = road_at(1800.0, "heavy")       # below the cap already: BPR of x / 0.9
    y = 1.8 / (1 - 0.1)
    assert R.speed_factor(road, 0, 400, 0) == 1 / (1 + a * ((y * y) * (y * y))) < 0.45
    road = road_at(3000.0, "floor")       # never below the speed floor
    assert R.speed_factor(road, 0, 400, 0) == 0.18
    road = road_at(1000.0, "vc", vc=1.1, rec=1.05)   # another threshold
    assert R.speed_factor(road, 0, 400, 0) == bpr(1.0, a)


def test_mwy_window_and_dynamic_trigger(tmp_path):
    a = 0.15
    secs = [(0, 1.0, 1000.0, 500.0, 500.0, 1.0), (1, 1.0, 1000.0, 500.0, 500.0, 1.0)]
    # V/C 0.5: section 0 (motorway) is broken down only inside its window [410, 430); section 1 has
    # the same window but mwy = 0 and never breaks down
    road = mwy_load(tmp_path / "w", secs, {0: [0], 1: [1]}, {0: (1, 410, 430), 1: (0, 410, 430)}, alpha=a)
    for m, inside in ((409, False), (410, True), (429, True), (430, False)):
        assert R.broken_down(road, 0, m, 0.5) is inside
        assert R.speed_factor(road, 0, m, 0) == (0.45 if inside else bpr(0.5, a))
        assert not R.broken_down(road, 1, m, 0.5) and R.speed_factor(road, 1, m, 0) == bpr(0.5, a)
    # today's commuters start a breakdown: fpe = ((125 * 1) * 60) / 15 = 500 veh/h per entry, so the
    # second car (one entry in the window) sees V/C 1.0 at 401, outside the window
    road = mwy_load(tmp_path / "d", secs, {0: [0], 1: [0]}, {0: (1, -1, -1)}, alpha=a, vpa=125.0)
    day = R.simulate_roads([(0, 400), (1, 401)], road)
    assert day.extra_min == {0: 1 / bpr(0.5, a) - 1.0, 1: 1 / 0.45 - 1.0} and day.delay_min == {0: 0, 1: 1}
    plain = load(tmp_path / "p", secs, {0: [0], 1: [0]}, alpha=a, vpa=125.0)
    assert R.simulate_roads([(0, 400), (1, 401)], plain).extra_min[1] == 1 / bpr(1.0, a) - 1.0


def test_breakdown_windows_hysteresis():
    x = np.array([[0.5, 1.0, 0.97, 0.96, 0.95, 0.94, 1.2, 1.3],    # on at 1, off at the first x < 0.95
                  [0.5, 0.99, 0.9, 0.99, 0.5, 0.5, 0.5, 0.5],       # never reaches 1
                  [0.5, 0.5, 1.1, 1.0, 0.96, 0.95, 0.95, 0.95]])    # never recovers: off = 8
    on, off = R.breakdown_windows(x, 1.0, 0.95)
    assert on.tolist() == [1, -1, 2] and off.tolist() == [5, -1, 8]
    on, off = R.breakdown_windows(x[0], 0.96, 0.96)                   # one row; no hysteresis band
    assert (on.tolist(), off.tolist()) == ([1], [4])


def mwy_random_road(d: Path, seed: int = 1, on: bool = True) -> R.RoadScenario:
    """random_road with a third of the sections motorways, half of those with a window 07:10-09:50."""
    road = random_road(d, seed=seed)
    mw = {s: (1, 430, 590) if s % 6 == 0 else (1, -1, -1) for s in road.section_ids if s % 3 == 0}
    return add_mwy(d, mw, on=on)


def test_mwy_off_switch_is_identical(tmp_path):
    plain = random_road(tmp_path / "plain", seed=4)
    off = mwy_random_road(tmp_path / "off", seed=4, on=False)
    on = mwy_random_road(tmp_path / "on", seed=4, on=True)
    assert not off.mwy_breakdown and on.mwy_breakdown and sum(on.mwy) > 0
    cars = [(a, 400 + (a * 3) % 90) for a in plain.routes]
    ref = R.simulate_roads(cars, plain)
    got = R.simulate_roads(cars, off)
    assert got.extra_min == ref.extra_min and got.delay_min == ref.delay_min and got.entries == ref.entries
    ent = R.entries_frame(1, ref.entries)
    for e in (None, ent):
        t0, t1 = R.speed_table(plain, e, range(330, 1021)), R.speed_table(off, e, range(330, 1021))
        assert np.array_equal(t0.f, t1.f) and t1.broken is None
    # on: motorways in their window or at V/C >= 1 are slower (cars spread out, so not every car)
    mod = R.simulate_roads(cars, on)
    assert sum(mod.extra_min.values()) > sum(ref.extra_min.values())
    assert sum(mod.delay_min.values()) > sum(ref.delay_min.values())


def test_mwy_speed_table_and_route_delays_match_the_engine(tmp_path):
    road = mwy_random_road(tmp_path / "r", seed=2)
    cars = [(a, 380 + (a * 7) % 150) for a in road.routes]
    day = R.simulate_roads(cars, road)
    ent = R.entries_frame(1, day.entries)
    minutes = range(330, 1021)
    t = R.speed_table(road, ent, minutes)
    counts: dict[tuple[int, int], int] = {(s, m): n for s, m, n in day.entries}
    pos = road.index
    seen = {"window": 0, "dynamic": 0, "plain": 0}
    for s in road.section_ids:
        i = pos[s]
        for m in range(400, 620, 3):
            c = sum(counts.get((s, j), 0) for j in range(m - road.flow_window_min, m))
            assert t.f[i, m - minutes.start] == R.speed_factor(road, i, m, c)
            fpe = ((road.vehicles_per_agent * road.w_factor[i]) * 60) / road.flow_window_min
            x = (road.bg_peak_vph[i] * road.r[m] + c * fpe) / road.cap_vph[i]
            b = R.broken_down(road, i, m, x)
            assert bool(t.broken[i, m - minutes.start]) is b
            if b:
                seen["window" if road.bd_on[i] <= m < road.bd_off[i] else "dynamic"] += 1
            elif road.mwy[i]:
                seen["plain"] += 1
    assert min(seen.values()) > 0, seen
    got = R.route_delays(road, t, road.routes, range(330, 586))
    for aid, d in cars:
        assert got[aid][d - 330] == day.extra_min[aid]
    usual = R.speed_table(road, None, minutes)   # usual traffic: the same rule on v = obs_peak_vph x r
    i = road.mwy.index(1)
    for m in (400, 431, 500, 589, 590, 700):
        x = road.obs_peak_vph[i] * road.r[m] / road.cap_vph[i]
        assert usual.f[i, m - 330] == R.speed_factor(dataclasses.replace(road, bg_peak_vph=road.obs_peak_vph), i, m, 0)
        assert bool(usual.broken[i, m - 330]) is R.broken_down(road, i, m, x)


def test_read_scenario_mwy_validation(tmp_path):
    secs = [(0, 1.0, 1000.0, 500.0, 500.0, 1.0)]
    d = road_dir(tmp_path / "a", secs, {0: [0]})
    with open(d / R.ROAD_PARAMS_FILE, "a") as fh:
        fh.write("mwy_breakdown,1\nmwy_breakdown_vc,1.0\nmwy_recover_vc,0.95\nmwy_capacity_drop,0.1\nmwy_jam_speed,0.45\n")
    with pytest.raises(ValueError, match="missing"):
        R.read_road_scenario(d)       # on without the mwy columns
    with pytest.raises(ValueError, match="bd_on"):
        mwy_load(tmp_path / "b", secs, {0: [0]}, {0: (1, 500, 450)})
    road = mwy_load(tmp_path / "c", secs, {0: [0]}, {0: (1, 450, 500)}, on=False)
    assert not road.mwy_breakdown and road.mwy == (1,) and road.mwy_keep == 1.0


# ----------------------------------------------------------------- NZTA profiles and capacity drops (SPEC3)

def add_profiles(d: Path, profiles: dict[int, list[float]], pid: dict[int, int], drop: dict[int, float] | None = None
                 ) -> R.RoadScenario:
    """Write road_profile.csv in the long format (profile_id, minute, r; rows shuffled) and add the
    profile_id (pid: section_id -> id, others 0) and, with drop (section_id -> cap_drop, others
    0.1), cap_drop columns to road_sections.csv."""
    long = pd.concat([pd.DataFrame({"profile_id": k, "minute": range(1440), "r": v}) for k, v in profiles.items()],
                     ignore_index=True).sample(frac=1.0, random_state=1)
    long.to_csv(d / R.ROAD_PROFILE_FILE, index=False)
    sec = pd.read_csv(d / R.ROAD_SECTIONS_FILE, float_precision="round_trip")
    sec["profile_id"] = [pid.get(int(s), 0) for s in sec["section_id"]]
    if drop is not None:
        sec["cap_drop"] = [drop.get(int(s), 0.1) for s in sec["section_id"]]
    sec.to_csv(d / R.ROAD_SECTIONS_FILE, index=False)
    road = R.read_road_scenario(d)
    assert road is not None
    return road


def test_profile_lookup_and_per_section_capacity_drop(tmp_path):
    a = 0.15
    secs = [(s, 1.0, 1000.0, 900.0, 900.0, 1.0) for s in range(4)]
    early = profile(0.5, m400=1.2, m401=0.9)
    late = profile(0.7, m400=0.3, m401=1.25)
    road_dir(tmp_path / "p", secs, {0: [0, 1, 2, 3]}, alpha=a)
    add_mwy(tmp_path / "p", {0: (1, -1, -1), 1: (1, -1, -1), 2: (1, 450, 460), 3: (0, -1, -1)}, rule={"jam": 1.0})
    road = add_profiles(tmp_path / "p", {0: profile(1.0), 1: early, 2: late}, {0: 1, 1: 2, 2: 1},
                        {0: 0.25, 1: 0.05, 2: 0.3})
    assert road.profile_id == (1, 2, 1, 0) and road.cap_drop == (0.25, 0.05, 0.3, 0.1)
    assert road.sec_r[0] == tuple(early) and road.sec_r[1] == tuple(late) and road.sec_r[3] == road.r
    assert road.sec_keep == (1 - 0.25, 1 - 0.05, 1 - 0.3, 1 - 0.1) and road.mwy_keep == 1 - 0.1
    # background = bg x the section's own profile; V/C >= 1 breaks a motorway down: y = x / (1 - cap_drop)
    for i, m, rr in ((0, 400, 1.2), (0, 401, 0.9), (1, 400, 0.3), (1, 401, 1.25), (3, 400, 1.0)):
        x = 900.0 * rr / 1000.0
        if road.mwy[i] == 1 and x >= 1.0:
            y = x / road.sec_keep[i]
            want = 1 / (1 + a * ((y * y) * (y * y)))
        else:
            want = bpr(x, a)
        assert R.speed_factor(road, i, m, 0) == want, (i, m)
    # the same V/C 1.08 on two motorways with different drops: the larger drop is slower
    assert R.speed_factor(road, 0, 400, 0) < R.speed_factor(dataclasses.replace(road, cap_drop=(0.05, 0.05, 0.3, 0.1)),
                                                            0, 400, 0)
    # inside its window section 2 runs on x / 0.7 (profile 1 at 455: 0.5 -> x 0.45)
    y = 0.45 / (1 - 0.3)
    assert R.speed_factor(road, 2, 455, 0) == 1 / (1 + a * ((y * y) * (y * y)))
    # the tables agents see follow the same values
    usual = R.speed_table(road, None, range(330, 1021))
    road_obs = dataclasses.replace(road, bg_peak_vph=road.obs_peak_vph)
    for i in range(4):
        for m in (399, 400, 401, 455, 700):
            assert usual.f[i, m - 330] == R.speed_factor(road_obs, i, m, 0)


def test_nzta_columns_speed_table_and_route_delays_match_the_engine(tmp_path):
    road = mwy_random_road(tmp_path / "r", seed=5)
    rng = np.random.default_rng(7)
    m = np.arange(1440)
    profs = {0: list(road.r), 3: list(np.clip(1.15 - np.abs(m - 380) / 120.0, 0.2, 1.15).round(6)),
             7: list(np.clip(1.2 - np.abs(m - 500) / 90.0, 0.1, 1.2).round(6))}
    pid = {s: int(rng.choice([0, 3, 7])) for s in road.section_ids}
    drop = {s: float(rng.choice([0.05, 0.1, 0.18, 0.27])) for s in road.section_ids}
    road = add_profiles(tmp_path / "r", profs, pid, drop)
    assert set(road.profile_id) == {0, 3, 7} and len(set(road.cap_drop)) == 4
    cars = [(a, 370 + (a * 11) % 160) for a in road.routes]
    day = R.simulate_roads(cars, road)
    t = R.speed_table(road, R.entries_frame(1, day.entries), range(330, 1021))
    counts = {(s, mm): n for s, mm, n in day.entries}
    pos = road.index
    n_own = 0
    for s in road.section_ids:
        i = pos[s]
        for mm in range(380, 640, 4):
            c = sum(counts.get((s, j), 0) for j in range(mm - road.flow_window_min, mm))
            assert t.f[i, mm - 330] == R.speed_factor(road, i, mm, c)
            n_own += int(bool(t.broken[i, mm - 330]) and road.cap_drop[i] != 0.1)
    assert n_own > 0
    got = R.route_delays(road, t, road.routes, range(330, 586))
    for aid, d in cars:
        assert got[aid][d - 330] == day.extra_min[aid]


def test_profile_0_with_the_global_drop_is_identical(tmp_path):
    """Every section on profile 0 with cap_drop = mwy_capacity_drop (long file, also with an unused
    profile) gives exactly the results of the one-profile files."""
    old = mwy_random_road(tmp_path / "old", seed=4)
    new = mwy_random_road(tmp_path / "new", seed=4)
    new = add_profiles(tmp_path / "new", {0: list(old.r), 5: [0.3] * 1440}, {}, {s: 0.1 for s in old.section_ids})
    assert set(new.profile_id) == {0} and new.cap_drop == old.cap_drop and new.sec_keep == old.sec_keep
    cars = [(a, 380 + (a * 7) % 150) for a in old.routes]
    a, b = R.simulate_roads(cars, old), R.simulate_roads(cars, new)
    assert a.extra_min == b.extra_min and a.delay_min == b.delay_min and a.entries == b.entries
    assert max(a.delay_min.values()) > 0
    ent = R.entries_frame(1, a.entries)
    for e in (None, ent):
        t0, t1 = R.speed_table(old, e, range(330, 1021)), R.speed_table(new, e, range(330, 1021))
        assert np.array_equal(t0.f, t1.f) and np.array_equal(t0.broken, t1.broken)
        r0 = R.route_delays(old, t0, old.routes, range(330, 586))
        r1 = R.route_delays(new, t1, new.routes, range(330, 586))
        assert all(np.array_equal(r0[k], r1[k]) for k in r0)


def test_read_scenario_profile_validation(tmp_path):
    secs = [(0, 1.0, 1000.0, 500.0, 500.0, 1.0), (1, 1.0, 1000.0, 500.0, 500.0, 1.0)]
    road_dir(tmp_path / "a", secs, {0: [0, 1]})
    with pytest.raises(ValueError, match="profile_id"):
        add_profiles(tmp_path / "a", {0: [1.0] * 1440}, {1: 4})           # profile 4 not in the file
    road_dir(tmp_path / "b", secs, {0: [0, 1]})
    with pytest.raises(ValueError, match="cap_drop"):
        add_profiles(tmp_path / "b", {0: [1.0] * 1440}, {}, {0: 1.0})
    d = road_dir(tmp_path / "c", secs, {0: [0, 1]})
    pd.DataFrame({"profile_id": [0] * 1440 + [2] * 1439, "minute": list(range(1440)) + list(range(1439)),
                  "r": 1.0}).to_csv(d / R.ROAD_PROFILE_FILE, index=False)    # profile 2 lacks minute 1439
    with pytest.raises(ValueError, match="minutes"):
        R.read_road_scenario(d)
    # without the columns: profile 0 and the global drop (rule off: 0)
    road = R.read_road_scenario(road_dir(tmp_path / "d", secs, {0: [0, 1]}))
    assert road.profile_id == (0, 0) and road.cap_drop == (0.0, 0.0) and road.sec_keep == (1.0, 1.0)
    assert road.profiles == {0: road.r}


def test_write_road_scenario_nzta_data(tmp_path, tiny_cfg, tiny_origins, tiny_personas):
    """Data with NZTA sites (profile_id, cap_drop, long profile): site sections keep their window and
    capacity drop, the others get the run's window and road.mwy_capacity_drop; only the profiles the
    run's sections use are written. With the rule off: profile_id but no mwy columns or cap_drop."""
    data = tmp_path / "data"
    data.mkdir()
    write_tiny_road_data(data, tiny_origins)
    sec = pd.read_csv(data / R.DATA_SECTIONS_FILE)
    shared = sec["section_id"] >= 1000
    sec["frc"] = np.where(shared, 0, 2)
    sec["mwy"] = shared.astype(int)
    sec["adt_source"] = np.where(sec["section_id"] == 1000, "nzta", "count")
    sec["bd_on"] = np.where(sec["section_id"] == 1000, 400, -1)
    sec["bd_off"] = np.where(sec["section_id"] == 1000, 455, -1)
    sec["profile_id"] = np.where(sec["section_id"] == 1000, 2, 0)
    sec["cap_drop"] = np.where(sec["section_id"] == 1000, 0.217, 0.1)
    sec.to_csv(data / R.DATA_SECTIONS_FILE, index=False)
    prof = pd.read_csv(data / R.DATA_PROFILE_FILE)
    m = np.arange(1440)
    long = pd.concat([prof.assign(profile_id=0), pd.DataFrame({"minute": m, "r": 0.5, "profile_id": 2}),
                      pd.DataFrame({"minute": m, "r": 0.9, "profile_id": 9})])[["profile_id", "minute", "r"]]
    long.to_csv(data / R.DATA_PROFILE_FILE, index=False)
    cfg = cfg_with(tiny_cfg, mwy_capacity_drop=0.12)
    run = tmp_path / "run"
    R.write_road_scenario(run, tiny_personas, cfg, data)
    cols = list(pd.read_csv(run / R.ROAD_SECTIONS_FILE).columns)
    assert cols == list(R.ROAD_SECTIONS_COLUMNS + R.MWY_COLUMNS) + ["profile_id", "cap_drop"]
    road = R.read_road_scenario(run)
    assert set(road.profiles) == {0, 2}          # profile 9 is used by no section
    out = pd.read_csv(run / R.ROAD_PROFILE_FILE)
    assert list(out.columns) == list(R.ROAD_PROFILE_LONG_COLUMNS) and len(out) == 2 * 1440
    pos = road.index
    i = pos[1000]
    assert (road.profile_id[i], road.cap_drop[i], road.bd_on[i], road.bd_off[i]) == (2, 0.217, 400, 455)
    assert road.sec_r[i] == (0.5,) * 1440
    j = pos[1001]                                 # motorway without a site: window from usual traffic, run's drop
    x = np.array([road.obs_peak_vph[j] * r / road.cap_vph[j] for r in road.r])
    on, off = R.breakdown_windows(x, cfg.road.mwy_breakdown_vc, cfg.road.mwy_recover_vc)
    assert (road.bd_on[j], road.bd_off[j], road.cap_drop[j], road.profile_id[j]) == (on[0], off[0], 0.12, 0)
    assert all(road.cap_drop[pos[s]] == 0.12 for s in road.section_ids if s != 1000)
    # rule off: profile_id stays (the background needs it), no motorway columns, no cap_drop
    off_dir = tmp_path / "off"
    R.write_road_scenario(off_dir, tiny_personas, cfg_with(cfg, mwy_breakdown=False), data)
    assert list(pd.read_csv(off_dir / R.ROAD_SECTIONS_FILE).columns) == list(R.ROAD_SECTIONS_COLUMNS) + ["profile_id"]
    road_off = R.read_road_scenario(off_dir)
    assert not road_off.mwy_breakdown and road_off.profile_id[road_off.index[1000]] == 2
    assert (off_dir / R.ROAD_PROFILE_FILE).read_bytes() == (run / R.ROAD_PROFILE_FILE).read_bytes()
    # half the columns is an error
    sec.drop(columns="cap_drop").to_csv(data / R.DATA_SECTIONS_FILE, index=False)
    with pytest.raises(ValueError, match="only"):
        R.write_road_scenario(tmp_path / "bad", tiny_personas, cfg, data)


# ----------------------------------------------------------------- what agents are told (SPEC 1.5)

def random_road(d: Path, seed: int = 1, n_sec: int = 25, n_agents: int = 60, vpa: float = 40.0) -> R.RoadScenario:
    rng = np.random.default_rng(seed)
    secs = [(s, float(rng.uniform(0.05, 2.5)), float(rng.uniform(300, 1500)), float(rng.uniform(100, 900)),
             float(rng.uniform(300, 1200)), float(rng.uniform(0.2, 1.0))) for s in range(n_sec)]
    routes = {a: [int(x) for x in rng.choice(n_sec, size=int(rng.integers(1, 9)), replace=False)]
              for a in range(n_agents)}
    r = list(np.clip(1.1 - np.abs(np.arange(1440) - 470) / 150.0, 0.15, 1.1).round(6))
    return load(d, secs, routes, r=r, vpa=vpa, alpha=0.15)


def test_speed_table_matches_scalar_reference(tmp_path):
    road = random_road(tmp_path / "r")
    cars = [(a, 360 + (a * 7) % 120) for a in road.routes]
    day = R.simulate_roads(cars, road)
    ent = R.entries_frame(1, day.entries)
    minutes = range(380, 520)
    t = R.speed_table(road, ent, minutes)
    counts: dict[tuple[int, int], int] = {(s, m): n for s, m, n in day.entries}
    pos = road.index
    for s in road.section_ids[::3]:
        for m in minutes[::7]:
            c = sum(counts.get((s, j), 0) for j in range(m - road.flow_window_min, m))
            assert t.f[pos[s], m - minutes.start] == R.speed_factor(road, pos[s], m, c)
    usual = R.speed_table(road, None, minutes)
    for s in road.section_ids[::4]:
        i = pos[s]
        for m in minutes[::11]:
            x = road.obs_peak_vph[i] * road.r[m] / road.cap_vph[i]
            f = max(road.speed_floor, 1 / (1 + road.bpr_alpha * ((x * x) * (x * x))))
            assert usual.f[i, m - minutes.start] == f


def test_route_delays_reproduce_every_car_of_a_day(tmp_path):
    # A table built from the day's entries has, at each (section, entry minute), the same window
    # count the engine used, so the probe traversal reproduces each car's float extra exactly.
    road = random_road(tmp_path / "r", seed=2)
    cars = [(a, 400 + (a * 5) % 60) for a in road.routes]
    day = R.simulate_roads(cars, road)
    assert max(day.delay_min.values()) > 0
    table = R.speed_table(road, R.entries_frame(1, day.entries), range(330, 1021))
    deps = range(330, 586)
    got = R.route_delays(road, table, road.routes, deps)
    for aid, d in cars:
        assert got[aid][d - 330] == day.extra_min[aid]


def test_route_delays_single_probe_and_usual_traffic(tmp_path):
    secs = [(0, 0.75, 1000.0, 1000.0, 1000.0, 1.0), (1, 1.5, 800.0, 400.0, 400.0, 1.0),
            (2, 3.1, 900.0, 300.0, 300.0, 0.3)]
    routes = {0: [0, 1, 2], 1: [2], 2: []}
    road = load(tmp_path / "r", secs, routes, r=profile(0.9, m401=0.2), vpa=50.0)
    for d in (395, 400, 401, 410):
        day = R.simulate_roads([(0, d)], road)
        table = R.speed_table(road, R.entries_frame(1, day.entries), range(330, 1021))
        assert R.route_delays(road, table, {0: routes[0]}, [d])[0][0] == day.extra_min[0]
    # usual traffic (obs = bg here) equals a lone car of the engine when commuters add nothing
    road0 = load(tmp_path / "z", secs, routes, r=profile(0.9, m401=0.2), vpa=0.0)
    usual = R.speed_table(road0, None, range(330, 1021))
    got = R.route_delays(road0, usual, routes, range(390, 420))
    for i, d in enumerate(range(390, 420)):
        day = R.simulate_roads([(0, d), (1, d)], road0)
        assert got[0][i] == day.extra_min[0] and got[1][i] == day.extra_min[1]
    assert (got[2] == 0.0).all() and len(got[2]) == 30


def test_road_delay_at():
    pub = {3: (0.0, 1.25, 2.5)}
    assert R.road_delay_at(pub, 3, 331, 330) == 1.25
    assert R.road_delay_at(pub, 3, 340, 330) == 0.0 and R.road_delay_at(pub, 4, 331, 330) == 0.0
    assert R.road_delay_at({}, 3, 331, 330) == 0.0


# ----------------------------------------------------------------- files

def test_read_scenario_absent_partial_and_invalid(tmp_path):
    assert R.read_road_scenario(tmp_path) is None
    d = road_dir(tmp_path / "a", [(0, 1.0, 100.0, 0.0, 0.0, 1.0)], {0: [0]})
    (d / R.ROAD_PARAMS_FILE).unlink()
    with pytest.raises(ValueError, match="incomplete"):
        R.read_road_scenario(d)
    d = road_dir(tmp_path / "b", [(0, 1.0, 0.0, 0.0, 0.0, 1.0)], {0: [0]})
    with pytest.raises(ValueError, match="cap_vph"):
        R.read_road_scenario(d)
    d = road_dir(tmp_path / "c", [(0, 1.0, 100.0, 0.0, 0.0, 1.0)], {0: [5]})
    with pytest.raises(ValueError, match="unknown section_id"):
        R.read_road_scenario(d)


def test_write_road_scenario_from_prep_files(tmp_path, tiny_cfg, tiny_origins, tiny_personas):
    data = tmp_path / "data"
    data.mkdir()
    with pytest.raises(FileNotFoundError, match="prep.build_roads"):
        R.write_road_scenario(tmp_path / "run0", tiny_personas, tiny_cfg, data)
    write_tiny_road_data(data, tiny_origins)
    run = tmp_path / "run"
    R.write_road_scenario(run, tiny_personas, tiny_cfg, data)
    road = R.read_road_scenario(run)
    assert road is not None
    vpa = tiny_cfg.engine.agents_represented / len(tiny_personas)
    assert road.vehicles_per_agent == vpa
    params = pd.read_csv(run / R.ROAD_PARAMS_FILE, dtype=str).set_index("key")["value"]
    assert params["vehicles_per_agent"] == repr(vpa) and params["bpr_beta"] == "4"
    osec = pd.read_csv(data / R.DATA_ORIGIN_SECTIONS_FILE)
    used = set()
    for p in tiny_personas:
        exp = tuple(osec[osec["origin_id"] == p.origin_id].sort_values("seq")["section_id"])
        assert road.routes[p.agent_id] == exp
        used |= set(exp)
    assert road.section_ids == tuple(sorted(used))
    sec = pd.read_csv(data / R.DATA_SECTIONS_FILE, float_precision="round_trip").set_index("section_id")
    pos = road.index
    for s in road.section_ids:   # values pass through exactly
        assert road.ff_min[pos[s]] == sec.loc[s, "ff_min"] and road.cap_vph[pos[s]] == sec.loc[s, "cap_vph"]
    # motorway breakdown on (the config default): the mwy columns and keys are written; the tiny data
    # has no mwy column and no frc-0 section, so no section is a motorway
    assert tiny_cfg.road.mwy_breakdown
    assert list(pd.read_csv(run / R.ROAD_SECTIONS_FILE).columns) == list(R.ROAD_SECTIONS_COLUMNS + R.MWY_COLUMNS)
    assert road.mwy_breakdown and set(road.mwy) == {0} and set(road.bd_on) == set(road.bd_off) == {-1}
    assert params["mwy_breakdown"] == "1" and params["mwy_capacity_drop"] == repr(tiny_cfg.road.mwy_capacity_drop)
    assert len(road.r) == 1440
    # off: the files of 2026-10-07
    off = tmp_path / "run_off"
    R.write_road_scenario(off, tiny_personas, cfg_with(tiny_cfg, mwy_breakdown=False), data)
    assert list(pd.read_csv(off / R.ROAD_SECTIONS_FILE).columns) == list(R.ROAD_SECTIONS_COLUMNS)
    assert list(pd.read_csv(off / R.ROAD_PARAMS_FILE)["key"]) == list(R.ROAD_PARAMS_KEYS)
    assert not R.read_road_scenario(off).mwy_breakdown
    for f in (R.AGENT_ROUTES_FILE, R.ROAD_PROFILE_FILE):
        assert (off / f).read_bytes() == (run / f).read_bytes()


def test_write_road_scenario_motorway_windows(tmp_path, tiny_cfg, tiny_origins, tiny_personas):
    """The run's windows come from the data's obs_peak_vph, cap_vph and profile with the run's thresholds."""
    data = tmp_path / "data"
    data.mkdir()
    write_tiny_road_data(data, tiny_origins)      # obs 85% of capacity at the 08:00 peak (r = 1)
    sec = pd.read_csv(data / R.DATA_SECTIONS_FILE)
    sec["frc"] = np.where(sec["section_id"] >= 1000, 0, 2)   # the corridors' shared sections: frc 0
    sec.to_csv(data / R.DATA_SECTIONS_FILE, index=False)
    with pytest.raises(ValueError, match="no mwy column"):
        R.write_road_scenario(tmp_path / "r0", tiny_personas, tiny_cfg, data)
    sec["mwy"] = (sec["section_id"] >= 1000).astype(int)
    sec["bd_on"], sec["bd_off"] = -1, -1          # recomputed for the run
    sec.to_csv(data / R.DATA_SECTIONS_FILE, index=False)
    cfg = cfg_with(tiny_cfg, mwy_breakdown_vc=0.8, mwy_recover_vc=0.7)
    run = tmp_path / "run"
    R.write_road_scenario(run, tiny_personas, cfg, data)
    road = R.read_road_scenario(run)
    assert road.mwy_breakdown and road.mwy_breakdown_vc == 0.8 and road.mwy_recover_vc == 0.7
    # x = 0.85 r(m), r = 1 - |m - 480| / 180: x >= 0.8 from 07:50 (r 0.944444), x < 0.7 from 08:32
    for i, s in enumerate(road.section_ids):
        want = (1, 470, 512) if s >= 1000 else (0, -1, -1)
        assert (road.mwy[i], road.bd_on[i], road.bd_off[i]) == want
    x = np.array([road.obs_peak_vph[0] * r / road.cap_vph[0] for r in road.r])
    assert R.breakdown_windows(x, 0.8, 0.7)[0][0] == 470
    # cars on the motorways at 08:00 are slower than without the rule
    cars = [(p.agent_id, 470) for p in tiny_personas]
    on = R.simulate_roads(cars, road)
    R.write_road_scenario(tmp_path / "off", tiny_personas, cfg_with(cfg, mwy_breakdown=False), data)
    off = R.simulate_roads(cars, R.read_road_scenario(tmp_path / "off"))
    assert all(on.extra_min[a] > off.extra_min[a] for a, _ in cars)


def test_road_settings_diff(tmp_path):
    on = {"enabled": True, "bpr_alpha": 0.15, "bpr_beta": 4, "speed_floor": 0.18, "flow_window_min": 15, "k": 0.1}
    assert R.road_settings_diff(None, {"enabled": False}) == []
    assert R.road_settings_diff({"enabled": False, "k": 3}, {"enabled": False, "k": None}) == []
    assert "road.enabled False" in R.road_settings_diff(None, on)[0]
    assert R.road_settings_diff(on, on) == []
    assert R.road_settings_diff({**on, "k": 0.12}, on) == ["road k 0.12 (this run 0.1)"]
    mwy = {**on, "mwy_breakdown": True, "mwy_breakdown_vc": 1.0, "mwy_recover_vc": 0.95,
           "mwy_capacity_drop": 0.1, "mwy_jam_speed": 0.45}
    assert R.road_settings_diff(mwy, mwy) == []
    assert R.road_settings_diff(on, mwy) == ["road mwy_breakdown False (this run True)"]
    assert R.road_settings_diff(mwy, on) == ["road mwy_breakdown True (this run False)"]
    assert R.road_settings_diff({**mwy, "mwy_capacity_drop": 0.15}, mwy) == [
        "road mwy_capacity_drop 0.15 (this run 0.1)"]


def test_road_k_reads_meta(tmp_path, tiny_cfg):
    assert R.road_k(tiny_cfg, tmp_path) is None
    (tmp_path / R.DATA_META_FILE).write_text(json.dumps({"k": 0.0731}))
    assert R.road_k(tiny_cfg, tmp_path) == 0.0731


# ----------------------------------------------------------------- PyEngine with roads

def engine_dir(tmp_path: Path, agents: list[tuple[int, int, int, int]], caps: list[float]) -> Path:
    d = tmp_path / "s"
    d.mkdir()
    pd.DataFrame({"corridor_id": range(len(caps)), "name": [f"C{k}" for k in range(len(caps))],
                  "capacity_per_min": caps, "x": 0.0, "y": 0.0}).to_csv(d / CORRIDORS_FILE, index=False)
    pd.DataFrame([{"agent_id": a, "corridor_id": c, "fftt_to_gate_min": g, "fftt_gate_to_dest_min": t,
                   "x": 0.0, "y": 0.0} for a, c, g, t in agents]).to_csv(d / AGENTS_FILE, index=False)
    fees.write_fees_csv(d / FEES_FILE, fees.fee_table("tou"))
    return d


def test_engine_gate_arrival_includes_road_delay(tiny_cfg, tmp_path):
    d = engine_dir(tmp_path, [(0, 0, 3, 2), (1, 0, 3, 2), (2, 0, 7, 1)], [1.0])
    road_dir(d, [(7, 2.5, 1000.0, 1000.0, 1000.0, 0.0)], {0: [7], 1: [7]})
    e = PyEngine(tiny_cfg)
    e.load(d)
    plans = pd.DataFrame({"agent_id": [0, 1, 2], "mode": ["CAR", "CAR", "PT"], "depart_min": [400, 401, -1]})
    r = e.run_day(4, plans, False)
    o = r.outcomes
    assert list(o.columns) == list(OUTCOME_COLUMNS) and str(o["road_delay_min"].dtype) == "int64"
    assert o["road_delay_min"].tolist() == [3, 3]
    assert o["gate_arrive_min"].tolist() == [406, 407]      # d + fftt_to_gate (3) + road delay (3)
    assert o["arrive_min"].tolist() == [408, 409]
    assert list(r.road.columns) == list(ROAD_COLUMNS) and all(str(r.road[c].dtype) == "int64" for c in ROAD_COLUMNS)
    assert r.road.values.tolist() == [[4, 7, 400, 1], [4, 7, 401, 1]]


def test_engine_free_flow_road_files_change_nothing(tiny_cfg, tiny_scenario_dir, tiny_plans, tmp_path):
    ref = PyEngine(tiny_cfg)
    ref.load(tiny_scenario_dir)
    a = ref.run_day(3, tiny_plans, True)
    assert a.road.empty and list(a.road.columns) == list(ROAD_COLUMNS)
    assert (a.outcomes["road_delay_min"] == 0).all()
    # bg = 0, vehicles_per_agent = 0: a = d + fftt_to_gate exactly, but entries are recorded
    road_dir(tiny_scenario_dir, [(s, 0.37 * (s + 1), 500.0, 0.0, 900.0, 1.0) for s in range(6)],
             {i: [i % 6, (i + 1) % 6, (i + 3) % 6] for i in range(20)}, vpa=0.0)
    ff = PyEngine(tiny_cfg)
    ff.load(tiny_scenario_dir)
    b = ff.run_day(3, tiny_plans, True)
    pd.testing.assert_frame_equal(a.outcomes, b.outcomes, check_exact=True)
    pd.testing.assert_frame_equal(a.profile, b.profile, check_exact=True)
    assert int(b.road["entries"].sum()) == 3 * int((tiny_plans["mode"] == "CAR").sum())


def test_engine_congestion_is_deterministic_and_order_invariant(tiny_cfg, tiny_scenario_dir, tiny_plans):
    road_dir(tiny_scenario_dir, [(s, 0.8 + 0.3 * s, 300.0, 300.0, 330.0, 0.5) for s in range(6)],
             {i: [i % 6, (i + 1) % 6, (i + 3) % 6] for i in range(20)}, vpa=60.0, alpha=1.0,
             r=list(np.clip(1.05 - np.abs(np.arange(1440) - 470) / 150.0, 0.15, 1.05)))
    e = PyEngine(tiny_cfg)
    e.load(tiny_scenario_dir)
    a = e.run_day(3, tiny_plans, True)
    b = e.run_day(3, tiny_plans.sample(frac=1.0, random_state=2), True)
    pd.testing.assert_frame_equal(a.outcomes, b.outcomes, check_exact=True)
    pd.testing.assert_frame_equal(a.road, b.road, check_exact=True)
    o = a.outcomes
    fg = pd.read_csv(tiny_scenario_dir / AGENTS_FILE).set_index("agent_id")["fftt_to_gate_min"]
    assert (o["gate_arrive_min"] == o["depart_min"] + o["agent_id"].map(fg) + o["road_delay_min"]).all()
    assert o["road_delay_min"].max() > 0 and (o["road_delay_min"] >= 0).all()
    assert a.road.equals(a.road.sort_values(["section_id", "minute"]).reset_index(drop=True))
    assert (a.road["entries"] > 0).all()


# ----------------------------------------------------------------- V/C and Level of Service (SPEC4 B)

def test_los_grade_bands_and_breakdown():
    """HCM 1994 bands as SSC2026: a bound belongs to the worse grade; the same V/C grades worse on an
    arterial than on a motorway; a motorway in flow breakdown is F whatever its V/C."""
    mwy = [0.0, 0.2999, 0.30, 0.4799, 0.48, 0.6999, 0.70, 0.8999, 0.90, 0.9999, 1.0, 2.5]
    other = [0.0, 0.2599, 0.26, 0.4299, 0.43, 0.6199, 0.62, 0.8199, 0.82, 0.9999, 1.0, 2.5]
    want = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    assert R.los_grade(mwy, 1).tolist() == want
    assert R.los_grade(other, 0).tolist() == want
    assert [R.LOS_GRADES[g] for g in R.los_grade([0.85, 0.85], [1, 0])] == ["D", "E"]
    # broadcasting: V/C by section x minute, mwy by section; broken -> F
    x = np.array([[0.1, 0.95], [0.1, 0.95]])
    assert R.los_grade(x, np.array([[1], [0]])).tolist() == [[0, 4], [0, 4]]
    b = np.array([[True, False], [False, False]])
    assert R.los_grade(x, np.array([[1], [0]]), b).tolist() == [[5, 4], [0, 4]]
    assert R.LOS_BANDS_MWY[R.LOS_E - 1] == 0.90 and R.LOS_BANDS_OTHER[R.LOS_E - 1] == 0.82


def test_los_periods_and_bins():
    assert R.los_periods(range(1, 2)) == [("all", [1])]
    assert R.los_periods(range(1, 6)) == [("d2-5", [2, 3, 4, 5])]       # d2-5 since 2026-10-15 (10-day design)
    assert R.los_periods(range(1, 13)) == [("d2-5", [2, 3, 4, 5]), ("d6-10", [6, 7, 8, 9, 10])]
    assert R.los_periods(range(1, 31)) == [("d2-5", [2, 3, 4, 5]), ("d6-10", list(range(6, 11))),
                                           ("d21-30", list(range(21, 31)))]
    assert [b[0] for b in R.LOS_BINS] == ["06:00-07:00", "07:00-08:00", "08:00-09:00", "09:00-10:00",
                                          "07:00-09:00"]
    assert [(a, b) for _l, a, b in R.LOS_BINS] == [(360, 420), (420, 480), (480, 540), (540, 600), (420, 540)]


def test_traffic_table_matches_the_engine(tmp_path):
    """V/C, speed factor and breakdown of traffic_table are the engine's doubles (speed_factor,
    speed_table), for a day's entries and for usual traffic, with motorways, windows, NZTA profiles
    and per-section capacity drops."""
    road = mwy_random_road(tmp_path / "r", seed=5)
    m = np.arange(1440)
    profs = {0: list(road.r), 3: list(np.clip(1.15 - np.abs(m - 380) / 120.0, 0.2, 1.15).round(6))}
    rng = np.random.default_rng(3)
    road = add_profiles(tmp_path / "r", profs, {s: int(rng.choice([0, 3])) for s in road.section_ids},
                        {s: float(rng.choice([0.05, 0.1, 0.2])) for s in road.section_ids})
    day = R.simulate_roads([(a, 370 + (a * 11) % 160) for a in road.routes], road)
    ent = R.entries_frame(1, day.entries)
    minutes = range(330, 700)
    for e in (ent, None):
        t, st = R.traffic_table(road, e, minutes), R.speed_table(road, e, minutes)
        assert np.array_equal(t.f, st.f) and np.array_equal(t.broken, st.broken)
        assert t.broken.any() and (~t.broken).any()
    t = R.traffic_table(road, ent, minutes)
    counts = {(s, mm): n for s, mm, n in day.entries}
    for s in road.section_ids[::2]:
        i = road.index[s]
        for mm in range(360, 600, 9):
            c = sum(counts.get((s, j), 0) for j in range(mm - road.flow_window_min, mm))
            fpe = ((road.vehicles_per_agent * road.w_factor[i]) * 60) / road.flow_window_min
            v = road.bg_peak_vph[i] * road.sec_r[i][mm] + c * fpe
            assert t.v[i, mm - 330] == v and t.x[i, mm - 330] == v / road.cap_vph[i]
            assert bool(t.broken[i, mm - 330]) is R.broken_down(road, i, mm, v / road.cap_vph[i])
    u = R.traffic_table(road, None, minutes)
    i = 3
    assert u.x[i, 480 - 330] == road.obs_peak_vph[i] * road.sec_r[i][480] / road.cap_vph[i]


def los_toy(d: Path, km: bool = True) -> tuple[R.RoadScenario, Path]:
    """Three sections, r = 1 at every minute, vehicles_per_agent 10 (fpe 40 veh/h per entry, W 15):
    s0 motorway 2 km at V/C 0.95 (E), s1 motorway 1 km at V/C 0.5 (C) broken down 07:00-08:00 (its
    window), s2 other road 3 km at V/C 0.7 (D). Data folder: road_sections.csv (street_name, frc, km,
    mwy), origins.csv and origin_sections.csv (s0 -> corridor 0; s1 -> corridor 1; s2 used by
    corridor 0 with weight 1 + 2 and corridor 1 with weight 3: a tie, the lowest id wins)."""
    secs = [(0, 1.0, 1000.0, 950.0, 950.0, 1.0), (1, 1.0, 1000.0, 500.0, 500.0, 1.0),
            (2, 1.0, 1000.0, 700.0, 700.0, 1.0)]
    road_dir(d / "run", secs, {0: [0, 2], 1: [1, 2]}, r=1.0, alpha=0.15, vpa=10.0)
    road = add_mwy(d / "run", {0: (1, -1, -1), 1: (1, 420, 480)})
    data = d / "data"
    data.mkdir(parents=True, exist_ok=True)
    sec = pd.DataFrame({"section_id": [0, 1, 2],
                        "street_name": ["Northern Motorway", "Northern Motorway", "Dominion Road"],
                        "frc": [0, 0, 2], "mwy": [1, 1, 0]})
    if km:
        sec["km"] = [2.0, 1.0, 3.0]
    sec.to_csv(data / R.DATA_SECTIONS_FILE, index=False)
    pd.DataFrame({"origin_id": [0, 1, 2], "weight": [1.0, 3.0, 2.0], "corridor_id": [0, 1, 0]}).to_csv(
        data / "origins.csv", index=False)
    pd.DataFrame([(0, 0, 0), (0, 1, 2), (1, 0, 1), (1, 1, 2), (2, 0, 2)],
                 columns=["origin_id", "seq", "section_id"]).to_csv(data / R.DATA_ORIGIN_SECTIONS_FILE, index=False)
    return road, data


def test_los_section_info(tmp_path):
    road, data = los_toy(tmp_path)
    info = R.los_section_info(road, data)
    assert info["corridor"].tolist() == [0, 1, 0]          # s2: corridors 0 and 1 both weigh 3 -> 0
    assert info["mwy"].tolist() == [1, 1, 0] and info["km"].tolist() == [2.0, 1.0, 3.0]
    assert info["street_name"].tolist()[2] == "Dominion Road" and info["frc"].tolist() == [0, 0, 2]
    # without km in the data the vehicle-km weight is the free-flow minutes (km left empty)
    road2, data2 = los_toy(tmp_path / "nokm", km=False)
    info2 = R.los_section_info(road2, data2)
    assert info2["km"].isna().all() and info2["weight_km"].tolist() == list(road2.ff_min)


def test_los_outputs_hand_computed(tmp_path):
    """Vehicle-km weighting, breakdown = F, bins and periods, commuter vehicles, usual traffic and the
    summary.json keys on the toy network (los_toy)."""
    road, data = los_toy(tmp_path)
    info = R.los_section_info(road, data)
    # day 2: 3 commuter entries into s2 at 06:40 -> minutes 06:41-06:55 carry 700 + 3 x 40 = 820 veh/h,
    # V/C 0.82: E on an arterial (its lower bound)
    ent = pd.DataFrame({"day": [2], "section_id": [2], "minute": [400], "entries": [3]})
    out = R.los_outputs(road, ent, info, [1, 2, 3])
    rl, sm = out.road_los, out.summary
    assert list(rl.columns) == list(R.ROAD_LOS_COLUMNS) and list(sm.columns) == list(R.LOS_SUMMARY_COLUMNS)
    assert len(rl) == 3 * 1 * 5 and set(rl["period"]) == {"all"}
    assert rl["section_id"].tolist() == sorted(rl["section_id"].tolist())
    assert rl[rl["section_id"] == 0]["bin"].tolist() == [b[0] for b in R.LOS_BINS]
    r = rl.set_index(["section_id", "bin"])
    # s1 (V/C 0.5, C) is broken down 07:00-08:00: F there, and in the peak (half of its minutes)
    assert r.loc[(1, "07:00-08:00"), "los"] == "F" and r.loc[(1, "07:00-08:00"), "share_EF"] == 1.0
    assert r.loc[(1, "07:00-09:00"), "los"] == "F" and r.loc[(1, "07:00-09:00"), "share_EF"] == 0.5
    assert r.loc[(1, "08:00-09:00"), "los"] == "C" and r.loc[(1, "08:00-09:00"), "vc_mean"] == 0.5
    assert r.loc[(1, "07:00-08:00"), "speed_factor_mean"] < r.loc[(1, "08:00-09:00"), "speed_factor_mean"]
    assert r.loc[(0, "08:00-09:00"), "los"] == "E" and r.loc[(2, "08:00-09:00"), "los"] == "D"
    # s2, 06:00-07:00: 15 of 3 x 60 minutes at E; the commuters: 3 entries x 10 vehicles / 3 days
    s2 = r.loc[(2, "06:00-07:00")]
    assert s2["share_EF"] == pytest.approx(15 / 180) and s2["commuter_veh"] == pytest.approx(10.0)
    assert s2["vc_max"] == pytest.approx(0.82) and s2["vc_mean"] == pytest.approx((165 * 0.7 + 15 * 0.82) / 180)
    assert s2["los"] == "D" and s2["usual_vc_mean"] == pytest.approx(0.7)
    assert r.loc[(2, "07:00-08:00"), "commuter_veh"] == 0.0
    # los_summary: vehicle-km weighted (s0 950 veh/h x 2 km, s1 500 x 1 km)
    q = sm.set_index(["day", "bin", "group"])
    assert q.loc[(1, "08:00-09:00", "motorway"), "share_EF"] == pytest.approx(1900 / 2400)
    assert q.loc[(1, "07:00-08:00", "motorway"), "share_EF"] == pytest.approx(1.0)
    assert q.loc[(1, "07:00-09:00", "motorway"), "share_EF"] == pytest.approx((2400 + 1900) / 4800)
    assert q.loc[(1, "08:00-09:00", "motorway"), "vc_mean"] == pytest.approx((1900 * 0.95 + 500 * 0.5) / 2400)
    assert q.loc[(1, "08:00-09:00", "motorway"), "veh_km"] == pytest.approx(2400 * 60 / 60)
    w = 3 * (45 * 700 + 15 * 820)
    assert q.loc[(2, "06:00-07:00", "other"), "share_EF"] == pytest.approx(3 * 15 * 820 / w)
    assert q.loc[(2, "06:00-07:00", "other"), "vc_mean"] == pytest.approx(3 * (45 * 700 * 0.7 + 15 * 820 * 0.82) / w)
    assert q.loc[(1, "06:00-07:00", "other"), "share_EF"] == 0.0
    assert q.loc[(1, "08:00-09:00", "all"), "share_EF"] == pytest.approx(1900 / (2400 + 2100))
    # corridor groups: s0 and s2 -> corridor 0, s1 -> corridor 1
    assert set(sm["group"]) == {"motorway", "other", "all", "corridor 0", "corridor 1"}
    assert q.loc[(1, "07:00-08:00", "corridor 1"), "share_EF"] == 1.0
    assert q.loc[(1, "08:00-09:00", "corridor 0"), "share_EF"] == pytest.approx(1900 / (1900 + 2100))
    # summary.json keys: the 07:00-09:00 peak, 4 dp
    k = out.day_keys[1]
    assert set(k) == set(R.LOS_DAY_KEYS)
    assert k["los_ef_share_mwy"] == round((2400 + 1900) / 4800, 4) and k["los_ef_share_other"] == 0.0
    assert k["vc_mean_other"] == 0.7 and k["vc_mean_mwy"] == pytest.approx((1900 * 0.95 + 500 * 0.5) / 2400, abs=1e-4)
    # periods: 12 days -> days 2-5 and 6-10
    out12 = R.los_outputs(road, ent, info, list(range(1, 13)))
    assert set(out12.road_los["period"]) == {"d2-5", "d6-10"} and len(out12.summary) == 12 * 5 * 5


def test_los_at_minute_matches_los_outputs(tmp_path):
    """The per-minute values (the NetLogo GUI's) add up to los_summary's bins: summed over a bin's
    minutes with their vehicle-km weights they give its share and mean V/C."""
    road = mwy_random_road(tmp_path / "r", seed=6)
    day = R.simulate_roads([(a, 380 + (a * 13) % 150) for a in road.routes], road)
    ent = R.entries_frame(1, day.entries)
    data = tmp_path / "data"
    data.mkdir()
    n = len(road.section_ids)
    pd.DataFrame({"section_id": list(road.section_ids), "km": np.linspace(0.2, 3.0, n).round(4),
                  "mwy": list(road.mwy), "frc": [0 if x else 2 for x in road.mwy],
                  "street_name": ["s"] * n}).to_csv(data / R.DATA_SECTIONS_FILE, index=False)
    info = R.los_section_info(road, data)
    assert (info["corridor"] == -1).all()                     # no origin files: no corridor groups
    out = R.los_outputs(road, ent, info, [1])
    assert set(out.summary["group"]) == {"motorway", "other", "all"}
    q = out.summary.set_index(["bin", "group"])
    t = R.traffic_table(road, ent, range(330, 700))
    for lab, a, b in R.LOS_BINS:
        at = [R.los_at_minute(t, info, m) for m in range(a, b)]
        for name, grp in (("mwy", "motorway"), ("other", "other")):
            wsum = sum(x[f"vkm_{name}"] for x in at)
            ef = sum(x[f"ef_share_{name}"] * x[f"vkm_{name}"] for x in at) / wsum
            vc = sum(x[f"vc_mean_{name}"] * x[f"vkm_{name}"] for x in at) / wsum
            assert q.loc[(lab, grp), "share_EF"] == pytest.approx(ef, rel=1e-12, abs=1e-12)
            assert q.loc[(lab, grp), "vc_mean"] == pytest.approx(vc, rel=1e-12)
            for key, col in (("ef_speed_share", "share_EF_speed"), ("congested_at_share", "share_congested_AT")):
                want = sum(x[f"{key}_{name}"] * x[f"vkm_{name}"] for x in at) / wsum
                assert q.loc[(lab, grp), col] == pytest.approx(want, rel=1e-12, abs=1e-12), (lab, grp, col)
    g = R.los_at_minute(t, info, 480)["grades"]
    assert g == R.los_grade(t.x[:, 150], info["mwy"].to_numpy(), t.broken[:, 150]).tolist()
    assert 0 < sum(x >= R.LOS_E for x in g) < n
    gs = R.los_at_minute(t, info, 480)["speed_grades"]
    assert gs == R.speed_los_grade(t.f[:, 150], t.broken[:, 150]).tolist()
    # E/F per minute inside los_outputs (x >= the E bound, or broken) is los_grade >= E
    e_from = np.where(info["mwy"].to_numpy()[:, None] == 1, 0.90, 0.82)
    mw = info["mwy"].to_numpy()[:, None]
    assert np.array_equal((t.x >= e_from) | t.broken, R.los_grade(t.x, mw, t.broken) >= R.LOS_E)
    # and by speed (f <= 0.40, or broken) is speed_los_grade >= E
    assert np.array_equal((t.f <= 0.40) | t.broken, R.speed_los_grade(t.f, t.broken) >= R.LOS_E)


def test_los_region_rules():
    """The regions of the GUI's LoS plots (LOS_REGIONS): the motorways SH1, SH16 and SH20 by street name,
    then North Shore (north of the Harbour Bridge and east of its line), the New Lynn and Green Lane
    discs (a point on the circle belongs to the disc), else Other roads (also a section without position)."""
    region = lambda name, x=1750000.0, y=5900000.0: R.LOS_REGIONS[R.los_region_of(name, x, y)]  # noqa: E731
    assert [region(n) for n in ("Northern Motorway", "Southern Motorway", "Northwestern Motorway",
                                "Southwestern Motorway", "20")] == ["SH1", "SH1", "SH16", "SH20", "SH20"]
    assert region("Upper Harbour Motorway") == "Other roads" and region("Great North Road") == "Other roads"
    # the motorway name wins over the place: SH1 north of the bridge is SH1, not North Shore
    assert region("Northern Motorway", 1755000.0, 5930000.0) == "SH1"
    assert region("Lake Road", 1758290.0, 5927288.0) == "North Shore"
    assert region("Lake Road", 1753000.0, 5927288.0) == "Other roads"       # x on the line: not east of it
    assert region("Lake Road", 1758290.0, 5922500.0) == "Other roads"       # y on the line: not north of it
    new_lynn, green_lane = R.LOS_REGION_DISCS
    assert region("Great North Road", new_lynn[1], new_lynn[2]) == "New Lynn"
    assert region("x", new_lynn[1] + new_lynn[3], new_lynn[2]) == "New Lynn"
    assert region("x", new_lynn[1] + new_lynn[3] + 1, new_lynn[2]) == "Other roads"
    assert region("Green Lane E", green_lane[1], green_lane[2]) == "Green Lane"
    assert region("x", green_lane[1], green_lane[2] + green_lane[3] + 1) == "Other roads"
    assert region("x", float("nan"), float("nan")) == "Other roads" and region("") == "Other roads"
    assert R.LOS_REGIONS[-1] == "Other roads" and len(set(R.LOS_REGIONS)) == len(R.LOS_REGIONS)


def test_los_section_info_regions_and_region_values(tmp_path):
    """los_section_info gives each section its region from data/road_sections.csv (street_name, x_mid,
    y_mid); los_at_minute reports the E/F share and mean V/C of each region as the vehicle-km weighted
    values of its sections (NaN for a region without sections)."""
    road = mwy_random_road(tmp_path / "r", seed=6)
    n = len(road.section_ids)
    names = ["Northern Motorway", "Northwestern Motorway", "Great North Road", "Green Lane E", "Lake Road"]
    spots = [(1755000.0, 5930000.0), (1745000.0, 5918000.0), (1750199.0, 5913928.0), (1759012.0, 5915788.0),
             (1758290.0, 5927288.0)]
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame({"section_id": list(road.section_ids), "km": np.linspace(0.2, 3.0, n).round(4),
                  "mwy": list(road.mwy), "frc": [0 if x else 2 for x in road.mwy],
                  "street_name": [names[i % 5] for i in range(n)],
                  "x_mid": [spots[i % 5][0] for i in range(n)],
                  "y_mid": [spots[i % 5][1] for i in range(n)]}).to_csv(data / R.DATA_SECTIONS_FILE, index=False)
    info = R.los_section_info(road, data)
    want_regions = [R.LOS_REGIONS.index(x) for x in ("SH1", "SH16", "New Lynn", "Green Lane", "North Shore")]
    assert info["region"].tolist() == [want_regions[i % 5] for i in range(n)]
    day = R.simulate_roads([(a, 380 + (a * 13) % 150) for a in road.routes], road)
    t = R.traffic_table(road, R.entries_frame(1, day.entries), range(330, 700))
    at = R.los_at_minute(t, info, 480)
    j = 480 - t.start_min
    w = t.v[:, j] * info["weight_km"].to_numpy(dtype=float)
    ef = R.los_grade(t.x[:, j], info["mwy"].to_numpy(), t.broken[:, j]) >= R.LOS_E
    for k, name in enumerate(R.LOS_REGIONS):
        mask = info["region"].to_numpy() == k
        if not mask.any():
            assert name in ("SH20", "Other roads"), name         # the five names above leave these two empty
            assert math.isnan(at["region_ef_share"][k]) and math.isnan(at["region_vc_mean"][k])
            continue
        assert at["region_ef_share"][k] == pytest.approx(w[mask & ef].sum() / w[mask].sum(), rel=1e-12)
        assert at["region_vc_mean"][k] == pytest.approx((w * t.x[:, j])[mask].sum() / w[mask].sum(), rel=1e-12)
    # a data folder without positions or street names: every section is Other roads
    data2 = tmp_path / "data2"
    data2.mkdir()
    pd.DataFrame({"section_id": list(road.section_ids), "km": 1.0, "mwy": list(road.mwy)}).to_csv(
        data2 / R.DATA_SECTIONS_FILE, index=False)
    assert (R.los_section_info(road, data2)["region"] == len(R.LOS_REGIONS) - 1).all()


def test_speed_los_grade_bands_and_breakdown():
    """HCM 2010 urban street bands on the speed factor (speed / free-flow speed), the same on every road:
    A > 0.85, B > 0.67, C > 0.50, D > 0.40, E > 0.30, F <= 0.30; a bound belongs to the worse grade; a
    motorway in flow breakdown is F whatever its speed. AT congested is below 0.5 (strictly)."""
    f = [1.0, 0.8501, 0.85, 0.6701, 0.67, 0.5001, 0.50, 0.4001, 0.40, 0.3001, 0.30, 0.18, 0.0]
    want = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 5]
    assert R.speed_los_grade(f).tolist() == want
    assert R.speed_los_grade(np.array(f).reshape(1, -1)).tolist() == [want]
    assert R.speed_los_grade([0.95, 0.95, 0.2], [True, False, False]).tolist() == [5, 0, 5]
    assert R.SPEED_LOS_BANDS == (0.85, 0.67, 0.50, 0.40, 0.30)
    assert R.SPEED_LOS_E_FROM == 0.40 and R.AT_CONGESTED_BELOW == 0.5
    assert [R.LOS_GRADES[g] for g in R.speed_los_grade([0.5, 0.45, 0.4])] == ["D", "D", "E"]


def speed_toy(d: Path) -> tuple[R.RoadScenario, pd.DataFrame]:
    """alpha 1 (f = 1 / (1 + x^4)), r = 1: s0 motorway 2 km at V/C 0.95 (f 0.551: E by V/C, C by speed);
    s1 motorway 1 km at V/C 0.5 broken down 07:00-08:00 (f at most mwy_jam_speed 0.45 there: F by speed,
    AT congested; else f 0.941, A); s2 other 3 km at V/C 1.0 (f = 0.5 exactly: D, not congested); s3
    other 1 km at V/C 1.2 (f 0.325, E); s4 other 2 km at V/C 1.5 (f 0.165 -> floor 0.18, F); s5 other 1
    km at V/C 1.1 (f 0.406, D, congested). Every other road is F by V/C."""
    secs = [(0, 1.0, 1000.0, 950.0, 950.0, 1.0), (1, 1.0, 1000.0, 500.0, 500.0, 1.0),
            (2, 1.0, 1000.0, 1000.0, 1000.0, 1.0), (3, 1.0, 1000.0, 1200.0, 1200.0, 1.0),
            (4, 1.0, 1000.0, 1500.0, 1500.0, 1.0), (5, 1.0, 1000.0, 1100.0, 1100.0, 1.0)]
    road_dir(d / "run", secs, {0: [0, 2, 3], 1: [1, 4, 5]}, r=1.0, alpha=1.0, vpa=10.0)
    road = add_mwy(d / "run", {0: (1, -1, -1), 1: (1, 420, 480)})
    data = d / "data"
    data.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"section_id": range(6), "street_name": ["m"] * 2 + ["o"] * 4, "frc": [0, 0, 2, 2, 3, 4],
                  "mwy": [1, 1, 0, 0, 0, 0], "km": [2.0, 1.0, 3.0, 1.0, 2.0, 1.0]}).to_csv(
        data / R.DATA_SECTIONS_FILE, index=False)
    return road, R.los_section_info(road, data)


def test_speed_los_outputs_hand_computed(tmp_path):
    """road_los speed_los / share_EF_speed / share_congested_AT, los_summary and summary.json keys and
    los_at_minute on speed_toy: vehicle-km weighting, breakdown = F, the 0.5 bound (D, not congested),
    the floor, and speed_los F when broken down in at least half the minutes."""
    road, info = speed_toy(tmp_path)
    t = R.traffic_table(road, None, range(360, 600))
    j = 450 - 360
    assert t.f[2, j] == 0.5 and t.f[4, j] == 0.18 and t.f[1, j] == 0.45 and bool(t.broken[1, j])
    out = R.los_outputs(road, pd.DataFrame(columns=list(R.ROAD_ENTRIES_COLUMNS)), info, [1, 2])
    r = out.road_los.set_index(["section_id", "bin"])
    pk = "07:00-09:00"
    assert [r.loc[(s, "08:00-09:00"), "speed_los"] for s in range(6)] == ["C", "A", "D", "E", "F", "D"]
    assert [r.loc[(s, "08:00-09:00"), "los"] for s in range(6)] == ["E", "C", "F", "F", "F", "F"]
    assert r.loc[(1, "07:00-08:00"), "speed_los"] == "F" and r.loc[(1, "07:00-08:00"), "share_EF_speed"] == 1.0
    assert r.loc[(1, "07:00-08:00"), "share_congested_AT"] == 1.0
    # s1 over the peak: half the minutes broken down -> F, although its mean speed factor grades B
    f1 = bpr(0.5, 1.0)
    assert r.loc[(1, pk), "speed_factor_mean"] == pytest.approx((0.45 + f1) / 2)
    assert R.LOS_GRADES[int(R.speed_los_grade(r.loc[(1, pk), "speed_factor_mean"]))] == "B"
    assert r.loc[(1, pk), "speed_los"] == "F" and r.loc[(1, pk), "share_EF_speed"] == 0.5
    assert r.loc[(1, pk), "share_congested_AT"] == 0.5
    assert [r.loc[(s, pk), "share_EF_speed"] for s in range(6)] == [0.0, 0.5, 0.0, 1.0, 1.0, 0.0]
    assert [r.loc[(s, pk), "share_congested_AT"] for s in range(6)] == [0.0, 0.5, 0.0, 1.0, 1.0, 1.0]
    # los_summary: vehicle-km weighted (motorways 950 x 2 + 500 x 1; other 1000 x 3, 1200, 1500 x 2, 1100)
    q = out.summary.set_index(["day", "bin", "group"])
    assert q.loc[(1, "07:00-08:00", "motorway"), "share_EF_speed"] == pytest.approx(500 / 2400)
    assert q.loc[(1, "07:00-08:00", "motorway"), "share_congested_AT"] == pytest.approx(500 / 2400)
    assert q.loc[(1, "08:00-09:00", "motorway"), "share_EF_speed"] == 0.0
    assert q.loc[(1, "08:00-09:00", "motorway"), "share_EF"] == pytest.approx(1900 / 2400)
    assert q.loc[(2, "06:00-07:00", "other"), "share_EF_speed"] == pytest.approx(4200 / 8300)
    assert q.loc[(2, "06:00-07:00", "other"), "share_congested_AT"] == pytest.approx(5300 / 8300)
    assert q.loc[(2, "06:00-07:00", "other"), "share_EF"] == 1.0
    assert q.loc[(1, pk, "all"), "share_EF_speed"] == pytest.approx((500 + 2 * 4200) / (4800 + 2 * 8300))
    k = out.day_keys[1]
    assert k["los_ef_speed_share_mwy"] == round(500 / 4800, 4) == k["congested_at_share_mwy"]
    assert k["los_ef_speed_share_other"] == round(4200 / 8300, 4)
    assert k["congested_at_share_other"] == round(5300 / 8300, 4)
    assert k["los_ef_share_mwy"] == round((2400 + 1900) / 4800, 4) and k["los_ef_share_other"] == 1.0
    # one minute (the GUI's values)
    a = R.los_at_minute(t, info, 450)
    assert [R.LOS_GRADES[g] for g in a["speed_grades"]] == ["C", "F", "D", "E", "F", "D"]
    assert a["ef_speed_share_mwy"] == pytest.approx(500 / 2400)
    assert a["congested_at_share_mwy"] == pytest.approx(500 / 2400)
    assert a["ef_speed_share_other"] == pytest.approx(4200 / 8300)
    assert a["congested_at_share_other"] == pytest.approx(5300 / 8300)
    b = R.los_at_minute(t, info, 500)
    assert b["ef_speed_share_mwy"] == 0.0 and b["congested_at_share_mwy"] == 0.0


def test_write_los_outputs_and_empty(tmp_path):
    road, data = los_toy(tmp_path)
    out = R.los_outputs(road, pd.DataFrame(columns=list(R.ROAD_ENTRIES_COLUMNS)), R.los_section_info(road, data), [1])
    (tmp_path / "o").mkdir()
    R.write_los_outputs(tmp_path / "o", out)
    rl = pd.read_csv(tmp_path / "o" / R.ROAD_LOS_FILE)
    assert len(rl) == 15 and list(rl.columns) == list(R.ROAD_LOS_COLUMNS)
    assert (rl["vc_mean"] == rl["vc_mean"].round(4)).all()
    e = R.empty_los_outputs([1, 2])
    R.write_los_outputs(tmp_path, e)
    assert (tmp_path / R.ROAD_LOS_FILE).read_text() == ",".join(R.ROAD_LOS_COLUMNS) + "\n"
    assert (tmp_path / R.LOS_SUMMARY_FILE).read_text() == ",".join(R.LOS_SUMMARY_COLUMNS) + "\n"
    assert e.day_keys == {1: dict.fromkeys(R.LOS_DAY_KEYS), 2: dict.fromkeys(R.LOS_DAY_KEYS)}
