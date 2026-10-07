"""Road congestion on the way to the cordon gate (SPEC 1.4 engine dynamics, 1.5 public information).

Each car drives its route section by section. A section's speed factor at minute m follows a BPR
curve of its volume: background traffic from the counts plus the commuter cars that entered it in
the last flow_window_min minutes. The extra time over free flow, rounded to whole minutes, is the
car's road_delay_min; its gate arrival is depart + fftt_to_gate_min + road_delay_min.

Scenario files (written into the run directory by write_road_scenario, only when road.enabled;
without them both engines use free-flow roads):
    road_sections.csv  section_id, ff_min, cap_vph, bg_peak_vph, obs_peak_vph, w_factor
    agent_routes.csv   agent_id, seq, section_id      (seq 0.. from the origin; pre-gate part only)
    road_profile.csv   minute, r                      (1440 rows)
    road_params.csv    key, value: bpr_alpha, bpr_beta, speed_floor, flow_window_min, vehicles_per_agent

simulate_roads is the reference for the NetLogo port (road-arrivals in netlogo7/cordon_lite.nlogox):
it uses only + - * / and floor in a fixed order, so both engines produce the same doubles.
speed_table and route_delays (what agents are told) are numpy-vectorised; they compute the same
per-element operations in the same order, so a table built from a day's entries reproduces every
car's traversal of that day exactly.

Public API:
    read_road_scenario(scenario_dir) -> RoadScenario | None
    write_road_scenario(run_dir, personas, cfg, data_dir=None) -> None
    speed_factor(road, i, m, c) -> float                  # section index i, minute m, window count c
    simulate_roads(cars, road) -> RoadDay                  # cars: (agent_id, depart_min)
    entries_frame(day, rows) -> pd.DataFrame               # DayResult.road / road_entries.csv rows
    speed_table(road, entries, minutes) -> SpeedTable
    route_delays(road, table, routes, departures) -> dict[agent_id, np.ndarray]
    road_delay_at(public_road, agent_id, depart_min, start_min) -> float
    road_settings(cfg) -> dict; road_settings_diff(recorded, current) -> list[str]
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Mapping, Sequence

import numpy as np
import pandas as pd

if TYPE_CHECKING:  # pragma: no cover
    from cordonlite.config import Config
    from cordonlite.types import Persona

# Scenario files (run directory)
ROAD_SECTIONS_FILE = "road_sections.csv"
AGENT_ROUTES_FILE = "agent_routes.csv"
ROAD_PROFILE_FILE = "road_profile.csv"
ROAD_PARAMS_FILE = "road_params.csv"
ROAD_SCENARIO_FILES: tuple[str, ...] = (ROAD_SECTIONS_FILE, AGENT_ROUTES_FILE, ROAD_PROFILE_FILE, ROAD_PARAMS_FILE)
ROAD_SECTIONS_COLUMNS: tuple[str, ...] = ("section_id", "ff_min", "cap_vph", "bg_peak_vph", "obs_peak_vph", "w_factor")
AGENT_ROUTES_COLUMNS: tuple[str, ...] = ("agent_id", "seq", "section_id")
ROAD_PROFILE_COLUMNS: tuple[str, ...] = ("minute", "r")
ROAD_PARAMS_KEYS: tuple[str, ...] = ("bpr_alpha", "bpr_beta", "speed_floor", "flow_window_min", "vehicles_per_agent")
N_PROFILE_MINUTES = 1440

# Engine output: commuter entries per section and minute (only non-zero rows)
ROAD_ENTRIES_COLUMNS: tuple[str, ...] = ("day", "section_id", "minute", "entries")
ROAD_ENTRIES_FILE = "road_entries.csv"    # run output: all days concatenated

# Prep outputs (data/, python -m prep.build_roads)
DATA_SECTIONS_FILE = "road_sections.csv"
DATA_ORIGIN_SECTIONS_FILE = "origin_sections.csv"
DATA_PROFILE_FILE = "road_profile.csv"
DATA_META_FILE = "road_meta.json"

# speed_table covers departures and travel up to this many minutes after time.sim_end_cap_min
TABLE_TAIL_MIN = 300


@dataclass(frozen=True)
class RoadScenario:
    """Road scenario files as read by the engines.

    Section arrays are aligned with ``section_ids`` (ascending); ``routes`` maps agent_id to the
    section ids of its pre-gate route in seq order (agents without a route are absent: free flow)."""

    section_ids: tuple[int, ...]
    ff_min: tuple[float, ...]
    cap_vph: tuple[float, ...]
    bg_peak_vph: tuple[float, ...]
    obs_peak_vph: tuple[float, ...]
    w_factor: tuple[float, ...]
    routes: Mapping[int, tuple[int, ...]]
    r: tuple[float, ...]               # time profile, minute 0..1439
    bpr_alpha: float
    bpr_beta: int                      # always 4: x4 = (x * x) * (x * x)
    speed_floor: float
    flow_window_min: int
    vehicles_per_agent: float

    @property
    def index(self) -> dict[int, int]:
        """section_id -> position in the section arrays."""
        return {s: i for i, s in enumerate(self.section_ids)}

    @property
    def fpe(self) -> tuple[float, ...]:
        """Veh/h added to a section per commuter entry in the window: ((vpa * w_factor) * 60) / W."""
        return tuple(((self.vehicles_per_agent * w) * 60) / self.flow_window_min for w in self.w_factor)


# --------------------------------------------------------------------------- files


def _read_params(path: Path) -> dict[str, float]:
    df = pd.read_csv(path, dtype={"key": str, "value": str})
    if list(df.columns) != ["key", "value"]:
        raise ValueError(f"{path.name} must have columns key, value")
    vals = {str(k).strip(): float(v) for k, v in zip(df["key"], df["value"])}
    missing = [k for k in ROAD_PARAMS_KEYS if k not in vals]
    if missing:
        raise ValueError(f"{path.name} lacks keys {missing}")
    return vals


def read_road_scenario(scenario_dir: str | Path) -> RoadScenario | None:
    """Read the four road files (floats round-trip exact); None when none of them exists."""
    d = Path(scenario_dir)
    present = [f for f in ROAD_SCENARIO_FILES if (d / f).exists()]
    if not present:
        return None
    if len(present) < len(ROAD_SCENARIO_FILES):
        raise ValueError(f"incomplete road scenario in {d}: missing "
                         f"{[f for f in ROAD_SCENARIO_FILES if f not in present]}")
    sec = pd.read_csv(d / ROAD_SECTIONS_FILE, float_precision="round_trip")
    rt = pd.read_csv(d / AGENT_ROUTES_FILE, float_precision="round_trip")
    prof = pd.read_csv(d / ROAD_PROFILE_FILE, float_precision="round_trip")
    for cols, df, name in ((ROAD_SECTIONS_COLUMNS, sec, ROAD_SECTIONS_FILE),
                           (AGENT_ROUTES_COLUMNS, rt, AGENT_ROUTES_FILE),
                           (ROAD_PROFILE_COLUMNS, prof, ROAD_PROFILE_FILE)):
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"{name} lacks columns {missing}")
    sec = sec.sort_values("section_id", kind="stable")
    if sec["section_id"].duplicated().any():
        raise ValueError(f"duplicate section_id in {ROAD_SECTIONS_FILE}")
    cap = sec["cap_vph"].to_numpy(dtype=float)
    if np.any(~np.isfinite(cap)) or np.any(cap <= 0):
        raise ValueError(f"{ROAD_SECTIONS_FILE}: cap_vph must be positive and finite")
    for col in ("ff_min", "bg_peak_vph", "obs_peak_vph", "w_factor"):
        v = sec[col].to_numpy(dtype=float)
        if np.any(~np.isfinite(v)) or np.any(v < 0):
            raise ValueError(f"{ROAD_SECTIONS_FILE}: {col} must be non-negative and finite")
    sids = tuple(int(s) for s in sec["section_id"])
    known = set(sids)

    rt = rt.sort_values(["agent_id", "seq"], kind="stable")
    routes: dict[int, tuple[int, ...]] = {}
    for aid, g in rt.groupby("agent_id", sort=True):
        seq = [int(x) for x in g["seq"]]
        if seq != list(range(len(seq))):
            raise ValueError(f"{AGENT_ROUTES_FILE}: agent {aid} seq must be 0..n-1")
        route = tuple(int(s) for s in g["section_id"])
        if not set(route) <= known:
            raise ValueError(f"{AGENT_ROUTES_FILE}: agent {aid} uses unknown section_id")
        routes[int(aid)] = route

    prof = prof.sort_values("minute", kind="stable")
    if [int(m) for m in prof["minute"]] != list(range(N_PROFILE_MINUTES)):
        raise ValueError(f"{ROAD_PROFILE_FILE} must have minutes 0..{N_PROFILE_MINUTES - 1}")
    r = tuple(float(x) for x in prof["r"])
    if any(not (math.isfinite(x) and x >= 0) for x in r):
        raise ValueError(f"{ROAD_PROFILE_FILE}: r must be non-negative and finite")

    p = _read_params(d / ROAD_PARAMS_FILE)
    beta, window = p["bpr_beta"], p["flow_window_min"]
    if beta != 4:
        raise ValueError(f"{ROAD_PARAMS_FILE}: bpr_beta must be 4 (the engines compute (x*x)*(x*x))")
    if window != round(window) or window < 1:
        raise ValueError(f"{ROAD_PARAMS_FILE}: flow_window_min must be an integer >= 1")
    if not (0 < p["speed_floor"] <= 1):
        raise ValueError(f"{ROAD_PARAMS_FILE}: speed_floor must be in (0, 1]")
    if not (p["bpr_alpha"] >= 0 and p["vehicles_per_agent"] >= 0):
        raise ValueError(f"{ROAD_PARAMS_FILE}: bpr_alpha and vehicles_per_agent must be >= 0")
    return RoadScenario(
        section_ids=sids,
        ff_min=tuple(float(x) for x in sec["ff_min"]),
        cap_vph=tuple(float(x) for x in cap),
        bg_peak_vph=tuple(float(x) for x in sec["bg_peak_vph"]),
        obs_peak_vph=tuple(float(x) for x in sec["obs_peak_vph"]),
        w_factor=tuple(float(x) for x in sec["w_factor"]),
        routes=routes,
        r=r,
        bpr_alpha=float(p["bpr_alpha"]),
        bpr_beta=4,
        speed_floor=float(p["speed_floor"]),
        flow_window_min=int(window),
        vehicles_per_agent=float(p["vehicles_per_agent"]),
    )


def _data_dir(cfg: Config, data_dir: str | Path | None) -> Path:
    return Path(data_dir) if data_dir is not None else cfg.resolve_path(cfg.run.data_dir)


def write_road_scenario(run_dir: Path, personas: Sequence[Persona], cfg: Config,
                        data_dir: str | Path | None = None) -> None:
    """Write road_sections.csv, agent_routes.csv, road_profile.csv and road_params.csv into run_dir.

    Routes come from data/origin_sections.csv through each persona's origin_id; only the sections
    used by this run's agents are written. vehicles_per_agent = agents_represented / n_agents is
    written with Python repr so both engines read the same double."""
    d = _data_dir(cfg, data_dir)
    need = (DATA_SECTIONS_FILE, DATA_ORIGIN_SECTIONS_FILE, DATA_PROFILE_FILE)
    missing = [f for f in need if not (d / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"road.enabled is true but {', '.join(missing)} missing in {d}: run "
            "`python -m prep.build_roads` first, or set road.enabled = false (free-flow roads)")
    sec = pd.read_csv(d / DATA_SECTIONS_FILE, float_precision="round_trip")
    osec = pd.read_csv(d / DATA_ORIGIN_SECTIONS_FILE)
    prof = pd.read_csv(d / DATA_PROFILE_FILE, float_precision="round_trip")
    for cols, df, name in ((ROAD_SECTIONS_COLUMNS, sec, DATA_SECTIONS_FILE),
                           (("origin_id", "seq", "section_id"), osec, DATA_ORIGIN_SECTIONS_FILE),
                           (ROAD_PROFILE_COLUMNS, prof, DATA_PROFILE_FILE)):
        miss = [c for c in cols if c not in df.columns]
        if miss:
            raise ValueError(f"{d / name} lacks columns {miss}")

    osec = osec.sort_values(["origin_id", "seq"], kind="stable")
    by_origin = {int(o): [int(s) for s in g["section_id"]] for o, g in osec.groupby("origin_id", sort=True)}
    rows: list[tuple[int, int, int]] = []
    for p in sorted(personas, key=lambda q: q.agent_id):
        for k, s in enumerate(by_origin.get(int(p.origin_id), [])):
            rows.append((int(p.agent_id), k, s))
    routes = pd.DataFrame(rows, columns=list(AGENT_ROUTES_COLUMNS)).astype("int64")
    used = sorted(set(routes["section_id"].tolist()))
    sec = sec.drop_duplicates("section_id").set_index("section_id")
    unknown = [s for s in used if s not in sec.index]
    if unknown:
        raise ValueError(f"{DATA_ORIGIN_SECTIONS_FILE} refers to section_ids missing from "
                         f"{DATA_SECTIONS_FILE}: {unknown[:10]}")
    out = sec.loc[used, list(ROAD_SECTIONS_COLUMNS[1:])].astype("float64").reset_index()
    out["section_id"] = out["section_id"].astype("int64")

    prof = prof.sort_values("minute", kind="stable")[list(ROAD_PROFILE_COLUMNS)]
    if [int(m) for m in prof["minute"]] != list(range(N_PROFILE_MINUTES)):
        raise ValueError(f"{d / DATA_PROFILE_FILE} must have minutes 0..{N_PROFILE_MINUTES - 1}")
    prof = prof.assign(minute=prof["minute"].astype("int64"), r=prof["r"].astype("float64"))

    rc = cfg.road
    vpa = float(cfg.engine.agents_represented) / len(personas)
    params = (("bpr_alpha", repr(float(rc.bpr_alpha))), ("bpr_beta", str(int(rc.bpr_beta))),
              ("speed_floor", repr(float(rc.speed_floor))), ("flow_window_min", str(int(rc.flow_window_min))),
              ("vehicles_per_agent", repr(vpa)))

    run_dir.mkdir(parents=True, exist_ok=True)
    out[list(ROAD_SECTIONS_COLUMNS)].to_csv(run_dir / ROAD_SECTIONS_FILE, index=False, lineterminator="\n")
    routes.to_csv(run_dir / AGENT_ROUTES_FILE, index=False, lineterminator="\n")
    prof.to_csv(run_dir / ROAD_PROFILE_FILE, index=False, lineterminator="\n")
    (run_dir / ROAD_PARAMS_FILE).write_text(
        "key,value\n" + "".join(f"{k},{v}\n" for k, v in params), encoding="utf-8", newline="\n")


def remove_road_scenario(run_dir: Path) -> None:
    """Delete road scenario files from run_dir (roads off: the engines then use free flow)."""
    for f in ROAD_SCENARIO_FILES:
        (Path(run_dir) / f).unlink(missing_ok=True)


# --------------------------------------------------------------------------- engine dynamics (SPEC 1.4)


def speed_factor(road: RoadScenario, i: int, m: int, c: int) -> float:
    """Speed factor of section index i at integer minute m with c commuter entries in m-W..m-1.

    SPEC 1.4, in this exact operation order (NetLogo port: same order, no ^):
        v  = bg_peak_vph * r[m] + c * fpe
        x  = v / cap_vph
        x4 = (x * x) * (x * x)
        f  = 1 / (1 + alpha * x4), at least speed_floor
    The profile has minutes 0..1439; a later minute uses r[1439] (not reached in practice)."""
    fpe = ((road.vehicles_per_agent * road.w_factor[i]) * 60) / road.flow_window_min
    rm = road.r[m] if m < N_PROFILE_MINUTES else road.r[N_PROFILE_MINUTES - 1]
    v = road.bg_peak_vph[i] * rm + c * fpe
    x = v / road.cap_vph[i]
    x4 = (x * x) * (x * x)
    f = 1 / (1 + road.bpr_alpha * x4)
    if f < road.speed_floor:
        f = road.speed_floor
    return f


@dataclass(frozen=True)
class RoadDay:
    """simulate_roads result for one day.

    delay_min: road_delay_min by agent_id for every car passed in (0 without a route).
    extra_min: el - ffsum by agent_id (float, before rounding; 0.0 without a route).
    entries:   (section_id, minute, entries) for every non-zero count, sorted by section, minute.
    """

    delay_min: dict[int, int]
    extra_min: dict[int, float]
    entries: list[tuple[int, int, int]]


def simulate_roads(cars: Sequence[tuple[int, int]], road: RoadScenario | None) -> RoadDay:
    """Drive today's cars along their routes (SPEC 1.4); cars = (agent_id, depart_min).

    Reference algorithm, ported line by line to NetLogo:
      - each car: el = 0.0 (elapsed float minutes), k = 0 (next route position),
        ffsum = sum of ff_min over its route added left to right in seq order;
      - cars wait in minute buckets keyed by cur = d + floor(el);
      - for m = min(d) upwards while any car is unfinished: for the cars in bucket m in ascending
        agent_id, while the car is unfinished and d + floor(el) == m: enter section s = route[k]
        with the speed factor of minute m (window counts use entries strictly before m), record
        one entry of s at minute m, el = el + ff_min_s / f, k = k + 1; an unfinished car moves to
        bucket d + floor(el) (always a later minute);
      - extra = el - ffsum; road_delay_min = max(0, floor(extra + 0.5)).
    Entries recorded at minute m are never read at minute m, so the order of cars within a minute
    does not change the result. Cars without a route (or no road scenario) have delay 0."""
    delay: dict[int, int] = {int(aid): 0 for aid, _d in cars}
    extra: dict[int, float] = {int(aid): 0.0 for aid, _d in cars}
    if road is None:
        return RoadDay(delay, extra, [])
    pos = road.index
    W = road.flow_window_min
    # per car state (only cars with a route take part)
    dep: dict[int, int] = {}
    route: dict[int, list[int]] = {}
    el: dict[int, float] = {}
    k: dict[int, int] = {}
    ffsum: dict[int, float] = {}
    for aid, d in cars:
        aid, d = int(aid), int(d)
        rt = road.routes.get(aid, ())
        if len(rt) == 0:
            continue
        dep[aid] = d
        route[aid] = [pos[s] for s in rt]
        el[aid] = 0.0
        k[aid] = 0
        s_ff = 0.0
        for i in route[aid]:
            s_ff = s_ff + road.ff_min[i]
        ffsum[aid] = s_ff
    # entries[i] = {minute: count} for section index i
    entries: list[dict[int, int]] = [{} for _ in road.section_ids]
    buckets: dict[int, list[int]] = {}
    for aid, d in dep.items():
        buckets.setdefault(d, []).append(aid)
    unfinished = len(dep)
    m = min(dep.values()) if dep else 0
    while unfinished > 0:
        for aid in sorted(buckets.pop(m, [])):
            d, rt = dep[aid], route[aid]
            done = False
            while not done and d + math.floor(el[aid]) == m:
                i = rt[k[aid]]
                ent = entries[i]
                c = 0                                   # entries of i at minutes m-W .. m-1
                for j in range(m - W, m):
                    c = c + ent.get(j, 0)
                f = speed_factor(road, i, m, c)
                ent[m] = ent.get(m, 0) + 1              # one more entry of i at minute m
                el[aid] = el[aid] + road.ff_min[i] / f
                k[aid] = k[aid] + 1
                if k[aid] == len(rt):
                    done = True
            if done:
                unfinished -= 1
            else:
                buckets.setdefault(d + math.floor(el[aid]), []).append(aid)
        m += 1
    for aid in dep:
        x = el[aid] - ffsum[aid]
        extra[aid] = x
        delay[aid] = max(0, math.floor(x + 0.5))
    rows = [(road.section_ids[i], mm, n) for i in range(len(road.section_ids))
            for mm, n in sorted(entries[i].items()) if n != 0]
    return RoadDay(delay, extra, rows)


def entries_frame(day: int, rows: Sequence[tuple[int, int, int]]) -> pd.DataFrame:
    """DayResult.road frame: int64 columns ROAD_ENTRIES_COLUMNS sorted by section_id, minute."""
    df = pd.DataFrame([(int(day), *r) for r in rows], columns=list(ROAD_ENTRIES_COLUMNS))
    return typed_entries(df)


def typed_entries(df: pd.DataFrame) -> pd.DataFrame:
    """Cast to int64, keep non-zero rows, sort by section_id then minute."""
    if len(df) == 0:
        return pd.DataFrame({c: pd.Series(dtype="int64") for c in ROAD_ENTRIES_COLUMNS})
    df = df[list(ROAD_ENTRIES_COLUMNS)].copy()
    for c in ROAD_ENTRIES_COLUMNS:
        df[c] = df[c].astype("float64").round().astype("int64")
    df = df[df["entries"] != 0]
    return df.sort_values(["section_id", "minute"], kind="stable").reset_index(drop=True)


# --------------------------------------------------------------------------- public information (SPEC 1.5)


@dataclass(frozen=True)
class SpeedTable:
    """Speed factors f[i, m - start_min] for every section index i and minute m in the table."""

    start_min: int
    f: np.ndarray

    @property
    def end_min(self) -> int:
        """Last minute in the table."""
        return self.start_min + self.f.shape[1] - 1


def speed_table(road: RoadScenario, entries: pd.DataFrame | None, minutes: range) -> SpeedTable:
    """Speed factor of every section at every minute in ``minutes`` (a contiguous range).

    entries None = USUAL traffic: v = obs_peak_vph * r[m] (what the counts say: background plus the
    usual commuters). With a day's entries (DayResult.road or road_entries.csv rows of one day):
    v = bg_peak_vph * r[m] + window count * fpe, exactly the engine's day. Then, as speed_factor:
    x = v / cap, x4 = (x * x) * (x * x), f = 1 / (1 + alpha * x4), at least speed_floor."""
    if minutes.step != 1 or len(minutes) == 0:
        raise ValueError("minutes must be a non-empty contiguous range")
    start, n_m = int(minutes.start), len(minutes)
    W = road.flow_window_min
    mins = np.arange(start, start + n_m)
    r_all = np.asarray(road.r, dtype=float)
    r = r_all[np.minimum(mins, N_PROFILE_MINUTES - 1)]
    cap = np.asarray(road.cap_vph, dtype=float)[:, None]
    if entries is None:
        v = np.asarray(road.obs_peak_vph, dtype=float)[:, None] * r[None, :]
    else:
        n_s = len(road.section_ids)
        # E[i, j] = entries of section i at minute start - W + j
        E = np.zeros((n_s, n_m + W), dtype=np.int64)
        if len(entries):
            pos = road.index
            mm = entries["minute"].to_numpy(dtype=np.int64) - (start - W)
            ok = (mm >= 0) & (mm < n_m + W)
            si = np.array([pos[int(s)] for s in entries["section_id"].to_numpy()[ok]], dtype=np.int64)
            np.add.at(E, (si, mm[ok]), entries["entries"].to_numpy(dtype=np.int64)[ok])
        S = np.zeros((n_s, n_m + W + 1), dtype=np.int64)
        np.cumsum(E, axis=1, out=S[:, 1:])
        c = S[:, W:W + n_m] - S[:, 0:n_m]       # entries at minutes m-W .. m-1
        fpe = np.asarray(road.fpe, dtype=float)[:, None]
        v = np.asarray(road.bg_peak_vph, dtype=float)[:, None] * r[None, :] + c * fpe
    x = v / cap
    x4 = (x * x) * (x * x)
    f = 1 / (1 + road.bpr_alpha * x4)
    f = np.where(f < road.speed_floor, road.speed_floor, f)
    return SpeedTable(start_min=start, f=f)


def route_delays(road: RoadScenario, table: SpeedTable, routes: Mapping[int, Sequence[int]],
                 departures: Sequence[int]) -> dict[int, np.ndarray]:
    """Road delay (float minutes, el - ffsum) of a probe car on each agent's route for each departure.

    The probe adds no load and follows the engine's traversal rule: it enters each section at minute
    d + floor(el) with that minute's speed factor from ``table`` (a minute past the table's end uses
    the last minute). routes: agent_id -> section ids in seq order (empty = free flow, zeros).
    Vectorised over (route, departure) pairs; agents with the same route share the computation."""
    dep = np.asarray(list(departures), dtype=np.int64)
    n_d = len(dep)
    pos = road.index
    uniq: dict[tuple[int, ...], int] = {}
    for rt in routes.values():
        t = tuple(int(s) for s in rt)
        if t and t not in uniq:
            uniq[t] = len(uniq)
    out: dict[int, np.ndarray] = {}
    if uniq and n_d:
        keys = sorted(uniq, key=lambda t: -len(t))  # longest first: routes still driving form a prefix
        n_u = len(keys)
        lens = np.array([len(t) for t in keys], dtype=np.int64)
        P = np.zeros((n_u, int(lens[0])), dtype=np.int64)
        for u, t in enumerate(keys):
            P[u, :len(t)] = [pos[s] for s in t]
        ff = np.asarray(road.ff_min, dtype=float)
        fflat = table.f.ravel()
        n_cols = table.f.shape[1]
        dep_col = (dep - table.start_min)[None, :]
        el = np.zeros((n_u, n_d))                  # elapsed minutes, route x departure
        ffs = np.zeros(n_u)                        # ffsum per route, added in seq order
        for j in range(int(lens[0])):
            a = int(np.count_nonzero(lens > j))
            sj = P[:a, j]
            ffj = ff[sj]
            e = el[:a]
            col = dep_col + np.floor(e).astype(np.int64)      # entry minute - start_min
            np.clip(col, 0, n_cols - 1, out=col)
            f = fflat[(sj * n_cols)[:, None] + col]
            el[:a] = e + ffj[:, None] / f
            ffs[:a] = ffs[:a] + ffj
        res = el - ffs[:, None]
        by_route = {t: res[u] for u, t in enumerate(keys)}
    else:
        by_route = {}
    zero = np.zeros(n_d)
    for aid, rt in routes.items():
        t = tuple(int(s) for s in rt)
        out[int(aid)] = by_route[t].copy() if t in by_route else zero.copy()
    return out


def road_delay_at(public_road: Mapping[int, Sequence[float]], agent_id: int, depart_min: int,
                  start_min: int) -> float:
    """Public road delay of one agent for departure minute depart_min (TodayInfo.public_road holds
    one value per minute from start_min = time.sim_start_min); 0.0 without information."""
    seq = public_road.get(int(agent_id))
    i = int(depart_min) - int(start_min)
    if seq is None or i < 0 or i >= len(seq):
        return 0.0
    return float(seq[i])


# --------------------------------------------------------------------------- settings (calibration record)


def road_k(cfg: Config, data_dir: str | Path | None = None) -> float | None:
    """Capacity factor k from data/road_meta.json (None when the file or the key is missing)."""
    p = _data_dir(cfg, data_dir) / DATA_META_FILE
    if not p.exists():
        return None
    meta = json.loads(p.read_text(encoding="utf-8"))
    for src in (meta, meta.get("params", {}) if isinstance(meta.get("params"), dict) else {}):
        for key in ("k", "cap_k", "road_cap_k"):
            if key in src and src[key] is not None:
                return float(src[key])
    return None


def road_settings(cfg: Config) -> dict:
    """Road settings that a capacity calibration depends on (stored in calibration.json)."""
    rc = cfg.road
    return {"enabled": bool(rc.enabled), "bpr_alpha": float(rc.bpr_alpha), "bpr_beta": int(rc.bpr_beta),
            "speed_floor": float(rc.speed_floor), "flow_window_min": int(rc.flow_window_min),
            "k": road_k(cfg) if rc.enabled else None}


def road_settings_diff(recorded: Mapping[str, object] | None, current: Mapping[str, object]) -> list[str]:
    """Human-readable differences; a record without road settings was made with free-flow roads.
    With roads off on both sides nothing else matters."""
    rec = dict(recorded) if recorded else {"enabled": False}
    if bool(rec.get("enabled", False)) != bool(current.get("enabled", False)):
        return [f"road.enabled {bool(rec.get('enabled', False))} (this run {bool(current.get('enabled'))})"]
    if not current.get("enabled"):
        return []
    out = []
    for key in ("bpr_alpha", "bpr_beta", "speed_floor", "flow_window_min", "k"):
        if rec.get(key) != current.get(key):
            out.append(f"road {key} {rec.get(key)} (this run {current.get(key)})")
    return out
