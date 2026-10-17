"""Road congestion on the way to the cordon gate (SPEC 1.4 engine dynamics, 1.5 public information).

Each car drives its route section by section. A section's speed factor at minute m follows a BPR
curve of its volume: background traffic from the counts plus the commuter cars that entered it in
the last flow_window_min minutes. The extra time over free flow, rounded to whole minutes, is the
car's road_delay_min; its gate arrival is depart + fftt_to_gate_min + road_delay_min.

Scenario files (written into the run directory by write_road_scenario, only when road.enabled;
without them both engines use free-flow roads):
    road_sections.csv  section_id, ff_min, cap_vph, bg_peak_vph, obs_peak_vph, w_factor
                       (+ mwy, bd_on, bd_off with road.mwy_breakdown)
                       (+ profile_id, and cap_drop with road.mwy_breakdown, from data with NZTA sites)
    agent_routes.csv   agent_id, seq, section_id      (seq 0.. from the origin; pre-gate part only)
    road_profile.csv   minute, r                      (1440 rows: one profile, profile 0)
                       or profile_id, minute, r       (1440 rows per profile; with profile_id above)
    road_params.csv    key, value: bpr_alpha, bpr_beta, speed_floor, flow_window_min, vehicles_per_agent
                       (+ mwy_breakdown, mwy_breakdown_vc, mwy_recover_vc, mwy_capacity_drop,
                       mwy_jam_speed with road.mwy_breakdown)

Motorway flow breakdown (2026-10-08, road.mwy_breakdown): a motorway mainline section (mwy = 1) is
broken down at minute m when m is in its usual-traffic breakdown window [bd_on, bd_off) or its V/C
x reaches mwy_breakdown_vc with today's traffic; broken-down flow runs on the BPR curve of x / (1 -
mwy_capacity_drop) and at most mwy_jam_speed of free-flow speed (speed_factor). Without the mwy
columns and keys (road.mwy_breakdown = false, older run folders) the files are exactly those of
2026-10-07 and every section follows the plain BPR curve.

NZTA motorway counts (2026-10-08, SPEC3): each section has a time profile (profile_id; background
= bg_peak_vph x r[profile_id][m]) and a capacity drop cap_drop (broken-down flow runs on the BPR
curve of x / (1 - cap_drop)); the divisor 1 - cap_drop is computed once per section at load
(RoadScenario.sec_keep, NetLogo sec-keep). Without the columns every section has profile 0 and
cap_drop = mwy_capacity_drop, which gives exactly the results of the one-profile files.

simulate_roads is the reference for the NetLogo port (road-arrivals in netlogo7/cordon_lite.nlogox):
it uses only + - * / and floor in a fixed order, so both engines produce the same doubles.
speed_table and route_delays (what agents are told) are numpy-vectorised; they compute the same
per-element operations in the same order, so a table built from a day's entries reproduces every
car's traversal of that day exactly.

Public API:
    read_road_scenario(scenario_dir) -> RoadScenario | None
    write_road_scenario(run_dir, personas, cfg, data_dir=None) -> None
    speed_factor(road, i, m, c) -> float                  # section index i, minute m, window count c
    broken_down(road, i, m, x) -> bool                     # motorway breakdown at minute m with V/C x
    breakdown_windows(x, breakdown_vc, recover_vc) -> (bd_on, bd_off)   # usual-traffic windows
    simulate_roads(cars, road) -> RoadDay                  # cars: (agent_id, depart_min)
    entries_frame(day, rows) -> pd.DataFrame               # DayResult.road / road_entries.csv rows
    speed_table(road, entries, minutes) -> SpeedTable
    route_delays(road, table, routes, departures) -> dict[agent_id, np.ndarray]
    road_delay_at(public_road, agent_id, depart_min, start_min) -> float
    road_settings(cfg) -> dict; road_settings_diff(recorded, current) -> list[str]

V/C ratio and Level of Service (2026-10-08, SPEC4 B; the one place these are defined):
    traffic_table(road, entries, minutes) -> TrafficTable      # v, V/C x, speed factor f, broken by section/minute
    los_grade(vc, mwy, broken=None) -> np.ndarray               # 0..5 = A..F (HCM 1994 bands as SSC2026)
    speed_los_grade(f, broken=None) -> np.ndarray               # 0..5 = A..F from the speed factor (HCM 2010)
    los_section_info(road, data_dir) -> pd.DataFrame            # street_name, frc, mwy, corridor, km of each section
    los_at_minute(table, info, m) -> dict                       # grades and E/F shares at one minute (GUI check)
    los_outputs(road, entries, info, days) -> LosOutputs         # road_los.csv, los_summary.csv, summary.json keys
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
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
ROAD_PROFILE_COLUMNS: tuple[str, ...] = ("minute", "r")                  # one profile (profile 0)
ROAD_PROFILE_LONG_COLUMNS: tuple[str, ...] = ("profile_id", "minute", "r")  # several profiles (2026-10-08)
DEFAULT_PROFILE_ID = 0
# NZTA motorway counts (2026-10-08): per-section time profile and capacity drop (road_sections.csv)
PROFILE_COLUMNS_SEC: tuple[str, ...] = ("profile_id", "cap_drop")
ROAD_PARAMS_KEYS: tuple[str, ...] = ("bpr_alpha", "bpr_beta", "speed_floor", "flow_window_min", "vehicles_per_agent")
# motorway flow breakdown (road.mwy_breakdown): extra road_sections.csv columns and road_params.csv keys
MWY_COLUMNS: tuple[str, ...] = ("mwy", "bd_on", "bd_off")
MWY_PARAMS_KEYS: tuple[str, ...] = ("mwy_breakdown", "mwy_breakdown_vc", "mwy_recover_vc", "mwy_capacity_drop",
                                    "mwy_jam_speed")
N_PROFILE_MINUTES = 1440

# Engine output: commuter entries per section and minute (only non-zero rows)
ROAD_ENTRIES_COLUMNS: tuple[str, ...] = ("day", "section_id", "minute", "entries")
ROAD_ENTRIES_FILE = "road_entries.csv"    # run output: all days concatenated
ROAD_ENTRIES_GZ = ROAD_ENTRIES_FILE + ".gz"   # the same, gzip-compressed, when larger than run.compress_csv_over_mb

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
    # motorway flow breakdown (road_params.csv mwy_* keys; off without them). Per section: mwy 1 =
    # motorway mainline; [bd_on, bd_off) = breakdown window under usual traffic (-1, -1 = none)
    mwy: tuple[int, ...] = ()
    bd_on: tuple[int, ...] = ()
    bd_off: tuple[int, ...] = ()
    mwy_breakdown: bool = False
    mwy_breakdown_vc: float = 1.0
    mwy_recover_vc: float = 1.0
    mwy_capacity_drop: float = 0.0
    mwy_jam_speed: float = 1.0
    mwy_keep: float = 1.0              # 1 - mwy_capacity_drop, computed once (NetLogo: mwy-keep)
    # NZTA motorway counts (2026-10-08): per section its time profile and capacity drop. Defaults
    # (empty / None): every section on profile 0 = r, cap_drop = mwy_capacity_drop
    profile_id: tuple[int, ...] = ()
    profiles: Mapping[int, tuple[float, ...]] | None = None   # profile_id -> 1440 values by minute
    cap_drop: tuple[float, ...] = ()
    # derived once (__post_init__): the profile of each section, 1 - cap_drop of each section
    # (NetLogo sec-r, sec-keep), and arrays for speed_table
    sec_r: tuple[tuple[float, ...], ...] = field(init=False, repr=False, compare=False)
    sec_keep: tuple[float, ...] = field(init=False, repr=False, compare=False)
    _prof_mat: np.ndarray = field(init=False, repr=False, compare=False)
    _prof_row: np.ndarray = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        n = len(self.section_ids)
        pid = tuple(int(p) for p in self.profile_id) if self.profile_id else (DEFAULT_PROFILE_ID,) * n
        profs = dict(self.profiles) if self.profiles is not None else {DEFAULT_PROFILE_ID: tuple(self.r)}
        drop = tuple(float(d) for d in self.cap_drop) if self.cap_drop else (float(self.mwy_capacity_drop),) * n
        if len(pid) != n or len(drop) != n:
            raise ValueError("profile_id and cap_drop need one value per section")
        missing = sorted({p for p in pid if p not in profs})
        if missing:
            raise ValueError(f"sections use profiles {missing} that are not in the profile table")
        object.__setattr__(self, "profile_id", pid)
        object.__setattr__(self, "profiles", profs)
        object.__setattr__(self, "cap_drop", drop)
        object.__setattr__(self, "sec_r", tuple(profs[p] for p in pid))
        object.__setattr__(self, "sec_keep", tuple(1 - d for d in drop))
        ids = sorted(profs)
        object.__setattr__(self, "_prof_mat", np.array([profs[p] for p in ids], dtype=float).reshape(len(ids), -1))
        row = {p: i for i, p in enumerate(ids)}
        object.__setattr__(self, "_prof_row", np.array([row[p] for p in pid], dtype=np.int64))

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
    profiles = read_profiles(prof, ROAD_PROFILE_FILE)
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

    pid, drop = _read_section_profiles(sec, profiles)

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
    mwy_kw = _read_mwy(sec, p)
    r = profiles[DEFAULT_PROFILE_ID] if DEFAULT_PROFILE_ID in profiles else profiles[min(profiles)]
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
        **mwy_kw,
        profile_id=pid,
        profiles=profiles,
        cap_drop=drop,
    )


def read_profiles(prof: pd.DataFrame, name: str = ROAD_PROFILE_FILE) -> dict[int, tuple[float, ...]]:
    """Time profiles of a road_profile.csv frame: columns minute, r (one profile: profile 0) or
    profile_id, minute, r (several); each profile must have minutes 0..1439 and r >= 0, finite."""
    if "profile_id" in prof.columns:
        groups = [(int(k), g) for k, g in prof.groupby("profile_id", sort=True)]
    else:
        groups = [(DEFAULT_PROFILE_ID, prof)]
    out: dict[int, tuple[float, ...]] = {}
    for k, g in groups:
        g = g.sort_values("minute", kind="stable")
        if [int(m) for m in g["minute"]] != list(range(N_PROFILE_MINUTES)):
            raise ValueError(f"{name}: profile {k} must have minutes 0..{N_PROFILE_MINUTES - 1}")
        r = tuple(float(x) for x in g["r"])
        if any(not (math.isfinite(x) and x >= 0) for x in r):
            raise ValueError(f"{name}: r must be non-negative and finite")
        out[k] = r
    if not out:
        raise ValueError(f"{name} holds no profile")
    return out


def _read_section_profiles(sec: pd.DataFrame, profiles: Mapping[int, tuple[float, ...]]
                           ) -> tuple[tuple[int, ...], tuple[float, ...]]:
    """profile_id (default 0) and cap_drop (default: () = mwy_capacity_drop) of each section of
    road_sections.csv (sorted by section_id)."""
    n = len(sec)
    if "profile_id" in sec.columns:
        v = sec["profile_id"].to_numpy(dtype=float)
        if np.any(v != np.round(v)):
            raise ValueError(f"{ROAD_SECTIONS_FILE}: profile_id must be integers")
        pid = tuple(int(x) for x in v)
    else:
        pid = (DEFAULT_PROFILE_ID,) * n
    unknown = sorted({p for p in pid if p not in profiles})
    if unknown:
        raise ValueError(f"{ROAD_SECTIONS_FILE}: profile_id {unknown[:10]} not in {ROAD_PROFILE_FILE}")
    drop: tuple[float, ...] = ()
    if "cap_drop" in sec.columns:
        d = sec["cap_drop"].to_numpy(dtype=float)
        if np.any(~np.isfinite(d)) or np.any(d < 0) or np.any(d >= 1):
            raise ValueError(f"{ROAD_SECTIONS_FILE}: cap_drop must be in [0, 1)")
        drop = tuple(float(x) for x in d)
    return pid, drop


def _read_mwy(sec: pd.DataFrame, p: Mapping[str, float]) -> dict:
    """Motorway breakdown fields of RoadScenario from road_sections.csv (sorted by section_id) and
    road_params.csv. Without the mwy_breakdown key the rule is off (a run folder of 2026-10-07 or
    road.mwy_breakdown = false); with it set to 1 the other keys and the mwy columns must exist.
    Sections without the columns are no motorway (mwy 0, window -1, -1)."""
    n = len(sec)
    on = "mwy_breakdown" in p and p["mwy_breakdown"] != 0
    if "mwy_breakdown" in p and p["mwy_breakdown"] not in (0, 1):
        raise ValueError(f"{ROAD_PARAMS_FILE}: mwy_breakdown must be 0 or 1")
    have = [c for c in MWY_COLUMNS if c in sec.columns]
    if on:
        missing = [k for k in MWY_PARAMS_KEYS if k not in p] + [c for c in MWY_COLUMNS if c not in have]
        if missing:
            raise ValueError(f"motorway breakdown is on ({ROAD_PARAMS_FILE}) but {missing} are missing")
    if have and len(have) < len(MWY_COLUMNS):
        raise ValueError(f"{ROAD_SECTIONS_FILE} has only {have} of the columns {list(MWY_COLUMNS)}")
    if have:
        cols = {c: sec[c].to_numpy(dtype=float) for c in MWY_COLUMNS}
        for c, v in cols.items():
            if np.any(v != np.round(v)):
                raise ValueError(f"{ROAD_SECTIONS_FILE}: {c} must be integers")
        mwy, bd_on, bd_off = (tuple(int(x) for x in cols[c]) for c in MWY_COLUMNS)
        if any(x not in (0, 1) for x in mwy):
            raise ValueError(f"{ROAD_SECTIONS_FILE}: mwy must be 0 or 1")
        for a, b in zip(bd_on, bd_off):
            if not ((a == -1 and b == -1) or 0 <= a < b <= N_PROFILE_MINUTES):
                raise ValueError(f"{ROAD_SECTIONS_FILE}: bd_on, bd_off must be -1, -1 or 0 <= bd_on < bd_off <= 1440")
    else:
        mwy, bd_on, bd_off = (0,) * n, (-1,) * n, (-1,) * n
    out: dict = {"mwy": mwy, "bd_on": bd_on, "bd_off": bd_off, "mwy_breakdown": bool(on)}
    if on:
        vc, rec, drop, jam = (float(p[k]) for k in MWY_PARAMS_KEYS[1:])
        if not (0 < rec <= vc and 0 <= drop < 1 and 0 < jam <= 1):
            raise ValueError(f"{ROAD_PARAMS_FILE}: need 0 < mwy_recover_vc <= mwy_breakdown_vc, "
                             "0 <= mwy_capacity_drop < 1, 0 < mwy_jam_speed <= 1")
        out.update(mwy_breakdown_vc=vc, mwy_recover_vc=rec, mwy_capacity_drop=drop, mwy_jam_speed=jam,
                   mwy_keep=1 - drop)
    return out


def _data_dir(cfg: Config, data_dir: str | Path | None) -> Path:
    return Path(data_dir) if data_dir is not None else cfg.resolve_path(cfg.run.data_dir)


def write_road_scenario(run_dir: Path, personas: Sequence[Persona], cfg: Config,
                        data_dir: str | Path | None = None) -> None:
    """Write road_sections.csv, agent_routes.csv, road_profile.csv and road_params.csv into run_dir.

    Routes come from data/origin_sections.csv through each persona's origin_id; only the sections
    used by this run's agents are written. vehicles_per_agent = agents_represented / n_agents is
    written with Python repr so both engines read the same double.

    With road.mwy_breakdown the sections also get mwy (from the prep column; a data folder without
    it may have no frc-0 section) and their usual-traffic breakdown window bd_on, bd_off, computed
    here (breakdown_windows) with the run's road.mwy_breakdown_vc and mwy_recover_vc from the same
    obs_peak_vph, cap_vph and profile (equal to the prep columns for the same thresholds), and
    road_params.csv gets the mwy_* keys. Without it the files are those of 2026-10-07.

    Data with NZTA sites (SPEC3: road_sections.csv with profile_id and cap_drop, road_profile.csv
    in long format): the sections also get profile_id and, with road.mwy_breakdown, cap_drop;
    road_profile.csv holds the profiles they use (profile_id, minute, r). Sections from a site
    (adt_source 'nzta') keep the site's window and capacity drop from the data; every other
    section gets the window computed here and road.mwy_capacity_drop. Data without those columns
    (one profile) give the files of the one-profile model."""
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

    # time profiles: one (minute, r: profile 0) or several (profile_id, minute, r; data with NZTA
    # sites, whose road_sections.csv also has profile_id and cap_drop) [SPEC3]
    profiles = read_profiles(prof, str(d / DATA_PROFILE_FILE))
    have = [c for c in PROFILE_COLUMNS_SEC if c in sec.columns]
    if have and len(have) < len(PROFILE_COLUMNS_SEC):
        raise ValueError(f"{d / DATA_SECTIONS_FILE} has only {have} of the columns {list(PROFILE_COLUMNS_SEC)}")
    multi = bool(have)
    if multi:
        pid = sec.loc[used, "profile_id"].to_numpy(dtype=np.int64)
        unknown_p = sorted({int(x) for x in pid} - set(profiles))
        if unknown_p:
            raise ValueError(f"{d / DATA_SECTIONS_FILE}: profile_id {unknown_p[:10]} not in {DATA_PROFILE_FILE}")
        # NZTA site sections keep their measured window and capacity drop; the others take the run's
        site = ((sec.loc[used, "adt_source"].astype(str) == "nzta").to_numpy() if "adt_source" in sec.columns
                else pid != DEFAULT_PROFILE_ID)
        prof_ids = sorted({int(x) for x in pid})
        prof = pd.DataFrame({"profile_id": np.repeat(np.array(prof_ids, dtype=np.int64), N_PROFILE_MINUTES),
                             "minute": np.tile(np.arange(N_PROFILE_MINUTES, dtype=np.int64), len(prof_ids)),
                             "r": np.concatenate([np.asarray(profiles[k], dtype=float) for k in prof_ids])})
        R = np.vstack([np.asarray(profiles[k], dtype=float) for k in prof_ids])[
            np.searchsorted(np.array(prof_ids), pid)]
    else:
        if DEFAULT_PROFILE_ID not in profiles or len(profiles) != 1:
            raise ValueError(f"{d / DATA_PROFILE_FILE} holds several profiles but {DATA_SECTIONS_FILE} has no "
                             "profile_id column: run `python -m prep.build_roads` first")
        pid = np.zeros(len(used), dtype=np.int64)
        site = np.zeros(len(used), dtype=bool)
        prof = pd.DataFrame({"minute": np.arange(N_PROFILE_MINUTES, dtype=np.int64),
                             "r": np.asarray(profiles[DEFAULT_PROFILE_ID], dtype=float)})
        R = prof["r"].to_numpy()[None, :]

    rc = cfg.road
    vpa = float(cfg.engine.agents_represented) / len(personas)
    params = (("bpr_alpha", repr(float(rc.bpr_alpha))), ("bpr_beta", str(int(rc.bpr_beta))),
              ("speed_floor", repr(float(rc.speed_floor))), ("flow_window_min", str(int(rc.flow_window_min))),
              ("vehicles_per_agent", repr(vpa)))
    columns = list(ROAD_SECTIONS_COLUMNS)
    if rc.mwy_breakdown:
        if "mwy" in sec.columns:
            mwy = sec.loc[used, "mwy"].to_numpy(dtype=np.int64)
        elif "frc" in sec.columns and bool((sec.loc[used, "frc"] == 0).any()):
            raise ValueError(f"road.mwy_breakdown is true but {d / DATA_SECTIONS_FILE} has no mwy column: run "
                             "`python -m prep.build_roads` first, or set road.mwy_breakdown = false")
        else:
            mwy = np.zeros(len(used), dtype=np.int64)
        x = (out["obs_peak_vph"].to_numpy()[:, None] * R) / out["cap_vph"].to_numpy()[:, None]
        on, off = breakdown_windows(x, rc.mwy_breakdown_vc, rc.mwy_recover_vc)
        if site.any():
            on = np.where(site, sec.loc[used, "bd_on"].to_numpy(dtype=np.int64), on)
            off = np.where(site, sec.loc[used, "bd_off"].to_numpy(dtype=np.int64), off)
        out["mwy"] = mwy
        out["bd_on"] = np.where(mwy == 1, on, -1)
        out["bd_off"] = np.where(mwy == 1, off, -1)
        columns += list(MWY_COLUMNS)
        params += (("mwy_breakdown", "1"), ("mwy_breakdown_vc", repr(float(rc.mwy_breakdown_vc))),
                   ("mwy_recover_vc", repr(float(rc.mwy_recover_vc))),
                   ("mwy_capacity_drop", repr(float(rc.mwy_capacity_drop))),
                   ("mwy_jam_speed", repr(float(rc.mwy_jam_speed))))
    if multi:
        out["profile_id"] = pid
        columns.append("profile_id")
        if rc.mwy_breakdown:
            out["cap_drop"] = np.where(site, sec.loc[used, "cap_drop"].to_numpy(dtype=float),
                                       float(rc.mwy_capacity_drop))
            columns.append("cap_drop")

    run_dir.mkdir(parents=True, exist_ok=True)
    out[columns].to_csv(run_dir / ROAD_SECTIONS_FILE, index=False, lineterminator="\n")
    routes.to_csv(run_dir / AGENT_ROUTES_FILE, index=False, lineterminator="\n")
    prof.to_csv(run_dir / ROAD_PROFILE_FILE, index=False, lineterminator="\n")
    (run_dir / ROAD_PARAMS_FILE).write_text(
        "key,value\n" + "".join(f"{k},{v}\n" for k, v in params), encoding="utf-8", newline="\n")


def remove_road_scenario(run_dir: Path) -> None:
    """Delete road scenario files from run_dir (roads off: the engines then use free flow)."""
    for f in ROAD_SCENARIO_FILES:
        (Path(run_dir) / f).unlink(missing_ok=True)


# --------------------------------------------------------------------------- engine dynamics (SPEC 1.4)


def broken_down(road: RoadScenario, i: int, m: int, x: float) -> bool:
    """True when the section at index i is a motorway in broken-down flow at minute m with V/C x:
    the rule is on, the section is a motorway mainline (mwy = 1) and m is in its usual-traffic
    breakdown window [bd_on, bd_off) or x >= mwy_breakdown_vc (today's traffic starts one)."""
    return (road.mwy_breakdown and road.mwy[i] == 1
            and ((road.bd_on[i] <= m and m < road.bd_off[i]) or x >= road.mwy_breakdown_vc))


def speed_factor(road: RoadScenario, i: int, m: int, c: int) -> float:
    """Speed factor of section index i at integer minute m with c commuter entries in m-W..m-1.

    SPEC 1.4 and the motorway breakdown rule (2026-10-08), in this exact operation order (NetLogo
    port road-speed-factor: same order, no ^):
        v  = bg_peak_vph * r[profile_id][m] + c * fpe
        x  = v / cap_vph
        broken down (broken_down):  y = x / (1 - cap_drop) (sec_keep, computed once per section),
                                    y4 = (y * y) * (y * y), f = 1 / (1 + alpha * y4), at most mwy_jam_speed
        otherwise:                  x4 = (x * x) * (x * x), f = 1 / (1 + alpha * x4)
        f at least speed_floor
    The profile has minutes 0..1439; a later minute uses r[1439] (not reached in practice)."""
    fpe = ((road.vehicles_per_agent * road.w_factor[i]) * 60) / road.flow_window_min
    rr = road.sec_r[i]
    rm = rr[m] if m < N_PROFILE_MINUTES else rr[N_PROFILE_MINUTES - 1]
    v = road.bg_peak_vph[i] * rm + c * fpe
    x = v / road.cap_vph[i]
    if road.mwy_breakdown and road.mwy[i] == 1 and (       # broken_down, inlined (called per entry)
            (road.bd_on[i] <= m and m < road.bd_off[i]) or x >= road.mwy_breakdown_vc):
        y = x / road.sec_keep[i]
        y4 = (y * y) * (y * y)
        f = 1 / (1 + road.bpr_alpha * y4)
        if f > road.mwy_jam_speed:
            f = road.mwy_jam_speed
    else:
        x4 = (x * x) * (x * x)
        f = 1 / (1 + road.bpr_alpha * x4)
    if f < road.speed_floor:
        f = road.speed_floor
    return f


def breakdown_windows(x: np.ndarray, breakdown_vc: float, recover_vc: float) -> tuple[np.ndarray, np.ndarray]:
    """Breakdown window of each row of x (V/C by minute 0..n-1 under usual traffic) with hysteresis.

    Scanning the minutes in order, a row is broken down from the first minute with x >=
    breakdown_vc (bd_on) until the first later minute with x < recover_vc (bd_off; n if never).
    One window per row; (-1, -1) when x never reaches breakdown_vc. Returns int64 arrays."""
    x = np.atleast_2d(np.asarray(x, dtype=float))
    n_rows, n_m = x.shape
    on = np.full(n_rows, -1, dtype=np.int64)
    off = np.full(n_rows, -1, dtype=np.int64)
    hit = x >= breakdown_vc
    first = hit.argmax(axis=1)
    for i in np.flatnonzero(hit.any(axis=1)):
        a = int(first[i])
        rec = np.flatnonzero(x[i, a + 1:] < recover_vc)
        on[i] = a
        off[i] = a + 1 + int(rec[0]) if len(rec) else n_m
    return on, off


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


def road_entries_path(run_dir: Path) -> Path:
    """A run's road entries: road_entries.csv, or road_entries.csv.gz when the run wrote it compressed."""
    gz = Path(run_dir) / ROAD_ENTRIES_GZ
    return gz if gz.exists() else Path(run_dir) / ROAD_ENTRIES_FILE


def read_road_entries(run_dir: Path) -> pd.DataFrame:
    """road_entries.csv or road_entries.csv.gz of a run folder (pandas reads either)."""
    return pd.read_csv(road_entries_path(run_dir))


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
    """Speed factors f[i, m - start_min] for every section index i and minute m in the table;
    broken[i, m - start_min] marks motorway sections in broken-down flow (None: rule off or no
    motorway section)."""

    start_min: int
    f: np.ndarray
    broken: np.ndarray | None = None

    @property
    def end_min(self) -> int:
        """Last minute in the table."""
        return self.start_min + self.f.shape[1] - 1


def speed_table(road: RoadScenario, entries: pd.DataFrame | None, minutes: range) -> SpeedTable:
    """Speed factor of every section at every minute in ``minutes`` (a contiguous range).

    entries None = USUAL traffic: v = obs_peak_vph * r[m] (what the counts say: background plus the
    usual commuters). With a day's entries (DayResult.road or road_entries.csv rows of one day):
    v = bg_peak_vph * r[m] + window count * fpe, exactly the engine's day (r = the section's
    profile). Then, as speed_factor: x = v / cap, x4 = (x * x) * (x * x), f = 1 / (1 + alpha * x4);
    on broken-down motorway sections (broken_down) y = x / (1 - cap_drop) (sec_keep), f = 1 / (1 +
    alpha * (y * y) * (y * y)) at most mwy_jam_speed; f at least speed_floor."""
    if minutes.step != 1 or len(minutes) == 0:
        raise ValueError("minutes must be a non-empty contiguous range")
    start, n_m = int(minutes.start), len(minutes)
    W = road.flow_window_min
    mins = np.arange(start, start + n_m)
    cols = np.minimum(mins, N_PROFILE_MINUTES - 1)
    P = road._prof_mat[:, cols]                 # each profile at the table's minutes
    if P.shape[0] == 1:
        r = P                                   # one profile, shared by every section (broadcast)
    else:
        r = P[road._prof_row]                   # r[i, j] = profile of section i at minute start + j
    cap = np.asarray(road.cap_vph, dtype=float)[:, None]
    if entries is None:
        v = np.asarray(road.obs_peak_vph, dtype=float)[:, None] * r
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
        v = np.asarray(road.bg_peak_vph, dtype=float)[:, None] * r + c * fpe
    x = v / cap
    x4 = (x * x) * (x * x)
    f = 1 / (1 + road.bpr_alpha * x4)
    broken = None
    rows = np.flatnonzero(np.asarray(road.mwy, dtype=np.int64) == 1) if road.mwy_breakdown else np.zeros(0, int)
    if len(rows):
        xb = x[rows]
        on = np.asarray(road.bd_on, dtype=np.int64)[rows][:, None]
        off = np.asarray(road.bd_off, dtype=np.int64)[rows][:, None]
        bk = ((on <= mins[None, :]) & (mins[None, :] < off)) | (xb >= road.mwy_breakdown_vc)
        y = xb / np.asarray(road.sec_keep, dtype=float)[rows][:, None]
        y4 = (y * y) * (y * y)
        fb = 1 / (1 + road.bpr_alpha * y4)
        fb = np.where(fb > road.mwy_jam_speed, road.mwy_jam_speed, fb)
        f[rows] = np.where(bk, fb, f[rows])
        broken = np.zeros(f.shape, dtype=bool)
        broken[rows] = bk
    f = np.where(f < road.speed_floor, road.speed_floor, f)
    return SpeedTable(start_min=start, f=f, broken=broken)


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


# --------------------------------------------------------------------------- V/C and Level of Service (SPEC4 B)
#
# Definitions (identical everywhere: run outputs, analysis, the NetLogo GUI's monitors and plot):
#   V/C of section s at minute m: x = v / cap_vph with v the engine's volume, bg_peak_vph x
#   r[profile][m] + (commuter entries at m-W .. m-1) x fpe (a day's traffic), or obs_peak_vph x
#   r[profile][m] (usual traffic).
#   LoS grade from x: HCM 1994 bands as used by SSC2026 (The Congestion Question WS1 "Defining
#   congestion", Feb 2019, Table 1; SSC2026 netlogo/LOS_IMPLEMENTATION.md): motorway mainline (mwy = 1)
#   A < 0.30, B < 0.48, C < 0.70, D < 0.90, E < 1.0, F >= 1.0; other roads A < 0.26, B < 0.43, C < 0.62,
#   D < 0.82, E < 1.0, F >= 1.0. A motorway section in flow breakdown at that minute (its window or
#   the trigger, broken_down) is F.
#   "% of traffic at LoS E/F" of a group of sections over some minutes = sum of v x km over its
#   section-minutes at E or F / sum of v x km (vehicle-km weighted, as SSC2026's flow-weighted share);
#   its mean V/C and mean speed factor are the vehicle-km weighted means of x and f.
#   Groups: motorway (mwy = 1), other roads (mwy = 0), all, and each corridor (the corridor with the
#   most origin weight, data/origins.csv weight, among the prep origins whose path uses the section;
#   ties: the lowest corridor_id).
#   Speed-based LoS (2026-10-08, next to the V/C grade, which stays as above for SSC2026 comparability:
#   capacity here is an effective BPR parameter calibrated to TomTom's travel-time index, peak V/C about
#   1.4, so the V/C grade is E/F almost everywhere at the peak): the grade of the speed factor f (speed /
#   free-flow speed; the engine's f, speed_factor) in the HCM 2010 urban street segment bands on travel
#   speed as a share of base free-flow speed: A f > 0.85, B f > 0.67,
#   C f > 0.50, D f > 0.40, E f > 0.30, F f <= 0.30 (a bound belongs to the worse grade), the same bands
#   on every road; a motorway section in flow breakdown is F. "% of traffic at speed LoS E/F" =
#   vehicle-km weighted share of section-minutes at E or F (f <= 0.40, or broken down).
#   Congested (Auckland Transport): average speed below 50% of the posted limit (AT's LoS D-F); here f <
#   0.5, the speed factor alone ("% of traffic congested (AT)" = vehicle-km weighted share of
#   section-minutes with f < 0.5; a broken-down motorway runs at most mwy_jam_speed, 0.45 by default,
#   so it counts as congested).
# The motorway flag of a section for its bands is the prep column mwy of data/road_sections.csv (also
# when road.mwy_breakdown is off and the run's road_sections.csv has no mwy column); km comes from the
# same file (a data folder without km, e.g. a test fixture, weights by ff_min instead: km is then
# empty in road_los.csv).

ROAD_LOS_FILE = "road_los.csv"          # run output: one row per section x period x bin
LOS_SUMMARY_FILE = "los_summary.csv"    # run output: one row per day x bin x group
LOS_GRADES: tuple[str, ...] = ("A", "B", "C", "D", "E", "F")
LOS_BANDS_MWY: tuple[float, ...] = (0.30, 0.48, 0.70, 0.90, 1.0)     # upper bounds of A..E, motorway mainline
LOS_BANDS_OTHER: tuple[float, ...] = (0.26, 0.43, 0.62, 0.82, 1.0)   # upper bounds of A..E, other roads
LOS_E = 4                               # grade index of E: E/F = grade >= LOS_E
LOS_F = 5
# speed-based LoS: lower bounds (exclusive) of the speed factor for A..E, HCM 2010 urban street segments
SPEED_LOS_BANDS: tuple[float, ...] = (0.85, 0.67, 0.50, 0.40, 0.30)
SPEED_LOS_E_FROM = SPEED_LOS_BANDS[LOS_E - 1]     # E/F by speed: f <= 0.40 (or a broken-down motorway)
AT_CONGESTED_BELOW = 0.5                # Auckland Transport congested: f < 0.5
LOS_PEAK_BIN = "07:00-09:00"
# (label, first minute, end minute): four hours and the 07:00-09:00 peak
LOS_BINS: tuple[tuple[str, int, int], ...] = (("06:00-07:00", 360, 420), ("07:00-08:00", 420, 480),
                                              ("08:00-09:00", 480, 540), ("09:00-10:00", 540, 600),
                                              (LOS_PEAK_BIN, 420, 540))
LOS_FIRST_MIN, LOS_END_MIN = 360, 600
# (label, first day, last day): a run has a period when it has all its days; without any, "all" days
LOS_PERIODS: tuple[tuple[str, int, int], ...] = (("d2-5", 2, 5), ("d6-10", 6, 10), ("d21-30", 21, 30))   # d2-5 added 2026-10-15: the uncharged days of the 10-day design
LOS_ALL_PERIOD = "all"
LOS_GROUPS_FIXED: tuple[str, ...] = ("motorway", "other", "all")
ROAD_LOS_COLUMNS: tuple[str, ...] = (
    "section_id", "street_name", "frc", "mwy", "corridor", "km", "period", "bin", "vc_mean", "vc_max",
    "speed_factor_mean", "share_EF", "los", "commuter_veh", "usual_vc_mean",
    "speed_los", "share_EF_speed", "share_congested_AT")
LOS_SUMMARY_COLUMNS: tuple[str, ...] = ("day", "bin", "group", "share_EF", "vc_mean", "speed_factor_mean", "veh_km",
                                        "share_EF_speed", "share_congested_AT")
# summary.json per-day keys (the 07:00-09:00 peak): E/F shares (by V/C, by speed), mean V/C and the AT
# congested share of motorways and other roads
LOS_DAY_KEYS: tuple[str, ...] = ("los_ef_share_mwy", "los_ef_share_other", "vc_mean_mwy", "vc_mean_other",
                                 "los_ef_speed_share_mwy", "los_ef_speed_share_other",
                                 "congested_at_share_mwy", "congested_at_share_other")
LOS_DP = 4

# Regions of the GUI's LoS plots (2026-10-10; the GUI only: no run output uses them): the plots of the
# LoS E/F share and of the mean V/C have one pen per region instead of one for motorways and one for
# other roads. A section belongs to the first rule that fits (NetLogo: region-of, the same rules):
#   SH1, SH16, SH20: by the street_name of the motorway (data/road_sections.csv),
#   North Shore: north of the Harbour Bridge (y_mid above LOS_NORTH_SHORE_MIN_Y) and east of
#   LOS_NORTH_SHORE_MIN_X (NZTM metres, of the section's mid point),
#   New Lynn, Green Lane: within the radius of LOS_REGION_DISCS of the centre, mid point,
#   Other roads: all the rest (the other motorways, and sections without street name or position).
LOS_REGIONS: tuple[str, ...] = ("SH1", "SH16", "SH20", "North Shore", "New Lynn", "Green Lane", "Other roads")
LOS_REGION_STREETS: tuple[tuple[str, ...], ...] = (
    ("Northern Motorway", "Southern Motorway"), ("Northwestern Motorway",), ("Southwestern Motorway", "20"))
LOS_NORTH_SHORE_MIN_Y = 5922500.0
LOS_NORTH_SHORE_MIN_X = 1753000.0
LOS_REGION_DISCS: tuple[tuple[str, float, float, float], ...] = (       # (region, centre x, centre y, radius m)
    ("New Lynn", 1750199.0, 5913928.0, 2500.0), ("Green Lane", 1759012.0, 5915788.0, 1500.0))


def los_region_of(street_name: str, x: float, y: float) -> int:
    """Index in LOS_REGIONS of the section with this street name and mid point (NZTM x, y; NaN = unknown)."""
    for k, names in enumerate(LOS_REGION_STREETS):
        if street_name in names:
            return k
    if y > LOS_NORTH_SHORE_MIN_Y and x > LOS_NORTH_SHORE_MIN_X:
        return LOS_REGIONS.index("North Shore")
    for name, cx, cy, radius in LOS_REGION_DISCS:
        dx, dy = x - cx, y - cy
        if dx * dx + dy * dy <= radius * radius:
            return LOS_REGIONS.index(name)
    return len(LOS_REGIONS) - 1


def corridor_group(corridor_id: int) -> str:
    """los_summary.csv group name of a corridor."""
    return f"corridor {int(corridor_id)}"


@dataclass(frozen=True)
class TrafficTable:
    """Per section index i and minute m - start_min: volume v (veh/h), V/C x = v / cap_vph, the speed
    factor f (speed_table's) and broken (motorway in flow breakdown; all False when the rule is off)."""

    start_min: int
    v: np.ndarray
    x: np.ndarray
    f: np.ndarray
    broken: np.ndarray


@dataclass(frozen=True)
class _TrafficConsts:
    """Per-section arrays of a road scenario used by traffic_table (built once per run)."""

    pos: dict[int, int]
    ids: np.ndarray            # section_ids (ascending): position of a section id by searchsorted
    cap: np.ndarray
    bg: np.ndarray
    obs: np.ndarray
    fpe: np.ndarray
    rows: np.ndarray           # motorway rows of the breakdown rule (empty when it is off)
    on: np.ndarray
    off: np.ndarray
    keep: np.ndarray
    r_cache: dict = field(default_factory=dict)   # (start, n_m) -> profile of each section at those minutes


def _traffic_consts(road: RoadScenario) -> _TrafficConsts:
    rows = np.flatnonzero(np.asarray(road.mwy, dtype=np.int64) == 1) if road.mwy_breakdown else np.zeros(0, int)
    return _TrafficConsts(
        pos=road.index, ids=np.asarray(road.section_ids, dtype=np.int64), cap=np.asarray(road.cap_vph, dtype=float)[:, None],
        bg=np.asarray(road.bg_peak_vph, dtype=float)[:, None], obs=np.asarray(road.obs_peak_vph, dtype=float)[:, None],
        fpe=np.asarray(road.fpe, dtype=float)[:, None], rows=rows,
        on=np.asarray(road.bd_on, dtype=np.int64)[rows][:, None] if len(rows) else np.zeros((0, 1), np.int64),
        off=np.asarray(road.bd_off, dtype=np.int64)[rows][:, None] if len(rows) else np.zeros((0, 1), np.int64),
        keep=np.asarray(road.sec_keep, dtype=float)[rows][:, None] if len(rows) else np.zeros((0, 1)))


def _section_pos(k: _TrafficConsts, sid: np.ndarray) -> np.ndarray:
    """Positions of section ids in the scenario (all must be known)."""
    i = np.searchsorted(k.ids, sid)
    if len(sid) and (np.any(i >= len(k.ids)) or np.any(k.ids[np.minimum(i, len(k.ids) - 1)] != sid)):
        raise ValueError("road entries refer to a section_id that is not in the road scenario")
    return i


def traffic_table(road: RoadScenario, entries: pd.DataFrame | None, minutes: range,
                  consts: _TrafficConsts | None = None) -> TrafficTable:
    """Volume, V/C, speed factor and breakdown of every section at every minute in ``minutes``.

    v is computed with the engine's operations (speed_factor): bg_peak_vph * r[m] + c * fpe for a day's
    entries (c = entries at m-W .. m-1), obs_peak_vph * r[m] for entries None (usual traffic); x = v /
    cap_vph; f and broken follow with the operations of speed_table (the same doubles: tested), so the
    V/C here is the one the speed factor and the breakdown rule saw. consts: _traffic_consts(road),
    passed when many tables of one scenario are built."""
    if minutes.step != 1 or len(minutes) == 0:
        raise ValueError("minutes must be a non-empty contiguous range")
    k = consts if consts is not None else _traffic_consts(road)
    start, n_m = int(minutes.start), len(minutes)
    W = road.flow_window_min
    mins = np.arange(start, start + n_m)
    r = k.r_cache.get((start, n_m))
    if r is None:
        P = road._prof_mat[:, np.minimum(mins, N_PROFILE_MINUTES - 1)]
        r = k.r_cache[(start, n_m)] = P if P.shape[0] == 1 else P[road._prof_row]
    n_s = len(road.section_ids)
    if entries is None:
        v = k.obs * r
    else:
        E = np.zeros((n_s, n_m + W), dtype=np.int64)
        if len(entries):
            mm = entries["minute"].to_numpy(dtype=np.int64) - (start - W)
            ok = (mm >= 0) & (mm < n_m + W)
            si = _section_pos(k, entries["section_id"].to_numpy(dtype=np.int64)[ok])
            E = np.bincount(si * (n_m + W) + mm[ok], weights=entries["entries"].to_numpy(dtype=np.int64)[ok],
                            minlength=n_s * (n_m + W)).astype(np.int64).reshape(n_s, n_m + W)
        S = np.zeros((n_s, n_m + W + 1), dtype=np.int64)
        np.cumsum(E, axis=1, out=S[:, 1:])
        c = S[:, W:W + n_m] - S[:, 0:n_m]       # entries at minutes m-W .. m-1
        v = k.bg * r
        v += c * k.fpe                          # bg * r + c * fpe
    v = np.broadcast_to(v, (n_s, n_m))
    x = v / k.cap
    # speed factor and breakdown: speed_table's operations, in its order (in place: the same doubles)
    f = x * x
    np.multiply(f, f, out=f)                    # x4 = (x * x) * (x * x)
    np.multiply(f, road.bpr_alpha, out=f)       # alpha * x4
    np.add(f, 1, out=f)                         # 1 + alpha * x4
    np.divide(1, f, out=f)                      # f = 1 / (1 + alpha * x4)
    broken = np.zeros((n_s, n_m), dtype=bool)
    if len(k.rows):
        xb = x[k.rows]
        bk = ((k.on <= mins[None, :]) & (mins[None, :] < k.off)) | (xb >= road.mwy_breakdown_vc)
        y = xb / k.keep
        y4 = (y * y) * (y * y)
        fb = 1 / (1 + road.bpr_alpha * y4)
        fb = np.where(fb > road.mwy_jam_speed, road.mwy_jam_speed, fb)
        f[k.rows] = np.where(bk, fb, f[k.rows])
        broken[k.rows] = bk
    np.putmask(f, f < road.speed_floor, road.speed_floor)
    return TrafficTable(start_min=start, v=v, x=x, f=f, broken=broken)


def los_grade(vc: np.ndarray | float, mwy: np.ndarray | int, broken: np.ndarray | bool | None = None) -> np.ndarray:
    """LoS grade index (0..5 = A..F) of V/C ``vc`` on a motorway mainline (mwy 1) or another road
    (mwy 0), broadcasting vc against mwy (e.g. vc of shape (sections, minutes), mwy (sections, 1)); F
    wherever ``broken`` (a motorway in flow breakdown). The grade is the number of band bounds <= vc:
    vc = 0.30 on a motorway is B, vc = 1.0 is F."""
    x = np.asarray(vc, dtype=float)
    on_mwy = np.asarray(mwy) == 1
    g = np.zeros(np.broadcast(x, on_mwy).shape, dtype=np.int64)
    for b_mwy, b_other in zip(LOS_BANDS_MWY, LOS_BANDS_OTHER):
        g += x >= np.where(on_mwy, b_mwy, b_other)
    if broken is not None:
        g = np.where(np.asarray(broken, dtype=bool), LOS_F, g)
    return g


def speed_los_grade(f: np.ndarray | float, broken: np.ndarray | bool | None = None) -> np.ndarray:
    """Speed-based LoS grade index (0..5 = A..F) of the speed factor ``f`` (speed / free-flow speed):
    HCM 2010 urban street bands SPEED_LOS_BANDS on every road, F wherever ``broken`` (a motorway in flow
    breakdown). The grade is the number of band bounds >= f: f = 0.85 is B, f = 0.30 is F."""
    s = np.asarray(f, dtype=float)
    g = np.zeros(s.shape, dtype=np.int64)
    for b in SPEED_LOS_BANDS:
        g += s <= b
    if broken is not None:
        g = np.where(np.asarray(broken, dtype=bool), LOS_F, g)
    return g


def los_section_info(road: RoadScenario, data_dir: str | Path) -> pd.DataFrame:
    """Descriptive columns of the run's sections (road.section_ids order) for the LoS outputs:
    section_id, street_name, frc, mwy (LoS bands: the prep column; the run's mwy without it), corridor
    (most origin weight through the section, -1 if no origin uses it), km (NaN without the column),
    weight_km (km, or ff_min when the data has no km column: the vehicle-km weight), x_mid, y_mid (NaN
    without the columns) and region (index in LOS_REGIONS, from street_name and the mid point)."""
    d = Path(data_dir)
    want = {"section_id", "street_name", "frc", "mwy", "km", "x_mid", "y_mid"}
    sec = (pd.read_csv(d / DATA_SECTIONS_FILE, usecols=lambda c: c in want)
           .drop_duplicates("section_id").set_index("section_id"))
    ids = list(road.section_ids)
    out = pd.DataFrame({"section_id": np.array(ids, dtype=np.int64)})
    known = sec.reindex(ids)
    out["street_name"] = (known["street_name"].fillna("").astype(str).to_numpy()
                          if "street_name" in sec.columns else "")
    out["frc"] = (known["frc"].fillna(-1).astype(np.int64).to_numpy() if "frc" in sec.columns
                  else np.full(len(ids), -1, dtype=np.int64))
    if "mwy" in sec.columns:
        out["mwy"] = known["mwy"].fillna(0).astype(np.int64).to_numpy()
    else:
        out["mwy"] = np.asarray(road.mwy if road.mwy else (0,) * len(ids), dtype=np.int64)
    corridor = np.full(len(ids), -1, dtype=np.int64)
    osec_p, orig_p = d / DATA_ORIGIN_SECTIONS_FILE, d / "origins.csv"
    if osec_p.exists() and orig_p.exists():
        osec = pd.read_csv(osec_p, usecols=["origin_id", "section_id"]).drop_duplicates()
        orig = pd.read_csv(orig_p, usecols=["origin_id", "weight", "corridor_id"])
        w = osec.merge(orig, on="origin_id", how="inner")
        g = w.groupby(["section_id", "corridor_id"], sort=True)["weight"].sum().reset_index()
        g = g.sort_values(["section_id", "weight", "corridor_id"], ascending=[True, False, True], kind="stable")
        best = g.drop_duplicates("section_id").set_index("section_id")["corridor_id"]
        corridor = best.reindex(ids).fillna(-1).astype(np.int64).to_numpy()
    out["corridor"] = corridor
    if "km" in sec.columns:
        out["km"] = known["km"].astype(float).to_numpy()
        out["weight_km"] = out["km"].fillna(0.0)
    else:
        out["km"] = np.nan
        out["weight_km"] = np.asarray(road.ff_min, dtype=float)
    for c in ("x_mid", "y_mid"):
        out[c] = known[c].astype(float).to_numpy() if c in sec.columns else np.nan
    out["region"] = np.array([los_region_of(str(n), float(x), float(y)) for n, x, y
                              in zip(out["street_name"], out["x_mid"], out["y_mid"])], dtype=np.int64)
    return out


def _group_masks(info: pd.DataFrame) -> dict[str, np.ndarray]:
    """Section masks of the LoS groups, in output order: motorway, other, all, corridor 0, 1, ..."""
    mwy = info["mwy"].to_numpy() == 1
    out = {"motorway": mwy, "other": ~mwy, "all": np.ones(len(info), dtype=bool)}
    for c in sorted(int(x) for x in set(info["corridor"].tolist()) if int(x) >= 0):
        out[corridor_group(c)] = info["corridor"].to_numpy() == c
    return out


def _share(num: float, den: float) -> float:
    return float(num / den) if den > 0 else float("nan")


def los_at_minute(table: TrafficTable, info: pd.DataFrame, m: int) -> dict:
    """LoS at one minute m of a traffic table: per section the V/C grade (los_grade, F when broken)
    and the speed grade (speed_los_grade), and for motorways and other roads the share of traffic (v x
    km) at E/F by V/C and by speed, the AT congested share (f < 0.5), the mean V/C and the vehicle-km
    weight (v x km) - the values the NetLogo GUI shows at its 5-minute marks."""
    j = m - table.start_min
    x, v, f, b = table.x[:, j], table.v[:, j], table.f[:, j], table.broken[:, j]
    mwy = info["mwy"].to_numpy()
    g = los_grade(x, mwy, b)
    gs = speed_los_grade(f, b)
    w = v * info["weight_km"].to_numpy(dtype=float)
    ef, efs, cong = g >= LOS_E, gs >= LOS_E, f < AT_CONGESTED_BELOW
    out: dict = {"grades": g.tolist(), "speed_grades": gs.tolist()}
    for name, mask in (("mwy", mwy == 1), ("other", mwy != 1)):
        wm = float(w[mask].sum())
        out[f"ef_share_{name}"] = _share(float(w[mask & ef].sum()), wm)
        out[f"vc_mean_{name}"] = _share(float((w * x)[mask].sum()), wm)
        out[f"ef_speed_share_{name}"] = _share(float(w[mask & efs].sum()), wm)
        out[f"congested_at_share_{name}"] = _share(float(w[mask & cong].sum()), wm)
        out[f"vkm_{name}"] = wm
    if "region" in info.columns:     # the GUI's LoS plots, by region of LOS_REGIONS (NaN: no traffic)
        reg = info["region"].to_numpy()
        masks = [reg == k for k in range(len(LOS_REGIONS))]
        out["region_ef_share"] = [_share(float(w[m_ & ef].sum()), float(w[m_].sum())) for m_ in masks]
        out["region_vc_mean"] = [_share(float((w * x)[m_].sum()), float(w[m_].sum())) for m_ in masks]
    return out


@dataclass(frozen=True)
class LosOutputs:
    """los_outputs result: road_los.csv and los_summary.csv frames and the summary.json keys by day."""

    road_los: pd.DataFrame
    summary: pd.DataFrame
    day_keys: dict[int, dict[str, float | None]]


def empty_los_outputs(days: Sequence[int] = ()) -> LosOutputs:
    """Header-only frames and None day keys (roads off: the run folder holds the same files)."""
    return LosOutputs(pd.DataFrame(columns=list(ROAD_LOS_COLUMNS)), pd.DataFrame(columns=list(LOS_SUMMARY_COLUMNS)),
                      {int(d): {k: None for k in LOS_DAY_KEYS} for d in days})


def los_periods(days: Sequence[int]) -> list[tuple[str, list[int]]]:
    """Periods of a run with these days: each of LOS_PERIODS whose days are all in the run, else 'all'."""
    have = set(int(d) for d in days)
    out = [(lab, list(range(a, b + 1))) for lab, a, b in LOS_PERIODS if all(d in have for d in range(a, b + 1))]
    return out or [(LOS_ALL_PERIOD, sorted(have))]


def _round(x: float | None) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), LOS_DP)


def _count_blocks(b: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Number of True per row of the boolean array b in each block of columns starting at edges (an
    integer count, as np.add.reduceat(b, edges, axis=1) gives; summed as uint8 into int64, about
    twice as fast as summing the booleans as floats)."""
    return np.add.reduceat(b.view(np.uint8), edges, axis=1, dtype=np.int64)


def los_outputs(road: RoadScenario, entries: pd.DataFrame, info: pd.DataFrame, days: Sequence[int]) -> LosOutputs:
    """road_los.csv, los_summary.csv and the summary.json day keys of a run (definitions above).

    entries: road_entries.csv rows of all days (day, section_id, minute, entries); days: the run's
    days. Per day the traffic table of minutes 06:00-09:59 (traffic_table on that day's entries) is
    reduced to sums per section and bin; road_los averages them over the days of each period (vc_mean,
    speed_factor_mean, share_EF, share_EF_speed and share_congested_AT over section-minutes, vc_max the
    largest, commuter_veh the mean per day of entries x vehicles_per_agent, los the V/C grade of vc_mean
    and speed_los the speed grade of speed_factor_mean, each F when the section was broken down in at
    least half the minutes, usual_vc_mean the usual-traffic V/C of the bin); los_summary gives per day,
    bin and group the vehicle-km weighted shares and means and the vehicle-km (v x km / 60 summed over
    the minutes)."""
    days = [int(d) for d in days]
    minutes = range(LOS_FIRST_MIN, LOS_END_MIN)
    # V/C from which a section is at E (the upper bound of D) by its bands
    e_from = np.where(info["mwy"].to_numpy()[:, None] == 1, LOS_BANDS_MWY[LOS_E - 1], LOS_BANDS_OTHER[LOS_E - 1])
    wkm = info["weight_km"].to_numpy(dtype=float)[:, None]
    bins = [(lab, a - LOS_FIRST_MIN, b - LOS_FIRST_MIN) for lab, a, b in LOS_BINS]
    n_s, n_b = len(road.section_ids), len(bins)
    vpa = float(road.vehicles_per_agent)
    groups = _group_masks(info)
    G = np.vstack([m.astype(float) for m in groups.values()])          # groups x sections
    by_day = {int(k): g for k, g in entries.groupby("day", sort=True)} if len(entries) else {}
    empty = entries.iloc[0:0] if len(entries.columns) else pd.DataFrame(columns=list(ROAD_ENTRIES_COLUMNS))
    # per day, section and bin: sums of x, f, E/F minutes, broken minutes, entries, E/F minutes by
    # speed, AT-congested minutes (acc) and max x
    acc = np.zeros((7, len(days), n_s, n_b))
    vmax = np.zeros((len(days), n_s, n_b))
    summ_rows: list[tuple] = []
    day_keys: dict[int, dict[str, float | None]] = {}
    consts = _traffic_consts(road)
    n_m = LOS_END_MIN - LOS_FIRST_MIN
    edges = np.array(sorted({a for _l, a, _b in bins} | {b for _l, _a, b in bins if b < n_m}), dtype=np.int64)
    if len(edges) == 0 or edges[0] != 0:
        raise ValueError("LOS_BINS must start at LOS_FIRST_MIN")
    ends = np.append(edges[1:], n_m)
    bin_blocks = [np.flatnonzero((edges >= a) & (ends <= b)) for _l, a, b in bins]
    if [int((ends[c] - edges[c]).sum()) for c in bin_blocks] != [b - a for _l, a, b in bins]:
        raise ValueError("LOS_BINS edges do not tile the bins")    # each bin is a run of whole blocks
    n_k = len(edges)
    block_of = np.searchsorted(edges, np.arange(n_m), side="right") - 1      # block of each minute
    for di, d in enumerate(days):
        ent = by_day.get(d, empty)
        t = traffic_table(road, ent, minutes, consts)
        ef = (t.x >= e_from) | t.broken           # = los_grade(t.x, mwy, t.broken) >= LOS_E (tested)
        efs = (t.f <= SPEED_LOS_E_FROM) | t.broken    # = speed_los_grade(t.f, t.broken) >= LOS_E (tested)
        cong = t.f < AT_CONGESTED_BELOW
        w = t.v * wkm
        # one pass over the minutes: sums and max per block between bin edges, then each bin = its blocks
        # (x, f, E/F, broken, entries, E/F by speed, congested; w * E/F, w * x, w * f, w, w * E/F by
        # speed, w * congested)
        blk = np.empty((13, n_s, n_k))
        blk[0] = np.add.reduceat(t.x, edges, axis=1)
        blk[1] = np.add.reduceat(t.f, edges, axis=1)
        blk[2] = _count_blocks(ef, edges)          # minute counts (exact integers)
        blk[3] = _count_blocks(t.broken, edges)
        blk[4] = 0.0
        if len(ent):
            mm = ent["minute"].to_numpy(dtype=np.int64) - LOS_FIRST_MIN
            ok = (mm >= 0) & (mm < n_m)
            si = _section_pos(consts, ent["section_id"].to_numpy(dtype=np.int64)[ok])
            blk[4] = np.bincount(si * n_k + block_of[mm[ok]], weights=ent["entries"].to_numpy(dtype=float)[ok],
                                 minlength=n_s * n_k).reshape(n_s, n_k)
        blk[5] = _count_blocks(efs, edges)
        blk[6] = _count_blocks(cong, edges)
        blk[7] = np.add.reduceat(np.where(ef, w, 0.0), edges, axis=1)
        blk[8] = np.add.reduceat(w * t.x, edges, axis=1)
        blk[9] = np.add.reduceat(w * t.f, edges, axis=1)
        blk[10] = np.add.reduceat(w, edges, axis=1)
        blk[11] = np.add.reduceat(np.where(efs, w, 0.0), edges, axis=1)
        blk[12] = np.add.reduceat(np.where(cong, w, 0.0), edges, axis=1)
        bmax = np.maximum.reduceat(t.x, edges, axis=1)
        sums = np.empty((6, n_s, n_b))         # w, w*ef, w*x, w*f, w*ef speed, w*congested by section, bin
        for bi, cover in enumerate(bin_blocks):
            s = blk[:, :, cover[0]] if len(cover) == 1 else blk[:, :, cover].sum(axis=2)
            acc[:, di, :, bi] = s[0:7]
            sums[:, :, bi] = s[[10, 7, 8, 9, 11, 12]]
            vmax[di, :, bi] = bmax[:, cover].max(axis=1)
        gs = np.einsum("gs,ksb->kgb", G, sums)                             # by group and bin
        for bi, (lab, _a, _b) in enumerate(bins):
            for gi, name in enumerate(groups):
                W_ = gs[0, gi, bi]
                summ_rows.append((d, lab, name, _share(gs[1, gi, bi], W_), _share(gs[2, gi, bi], W_),
                                  _share(gs[3, gi, bi], W_), W_ / 60.0, _share(gs[4, gi, bi], W_),
                                  _share(gs[5, gi, bi], W_)))
        peak = [bi for bi, (lab, _a, _b) in enumerate(bins) if lab == LOS_PEAK_BIN][0]
        names = list(groups)
        im, io = names.index("motorway"), names.index("other")
        has_m, has_o = bool(groups["motorway"].any()), bool(groups["other"].any())
        day_keys[d] = {
            "los_ef_share_mwy": _round(_share(gs[1, im, peak], gs[0, im, peak])) if has_m else None,
            "los_ef_share_other": _round(_share(gs[1, io, peak], gs[0, io, peak])) if has_o else None,
            "vc_mean_mwy": _round(_share(gs[2, im, peak], gs[0, im, peak])) if has_m else None,
            "vc_mean_other": _round(_share(gs[2, io, peak], gs[0, io, peak])) if has_o else None,
            "los_ef_speed_share_mwy": _round(_share(gs[4, im, peak], gs[0, im, peak])) if has_m else None,
            "los_ef_speed_share_other": _round(_share(gs[4, io, peak], gs[0, io, peak])) if has_o else None,
            "congested_at_share_mwy": _round(_share(gs[5, im, peak], gs[0, im, peak])) if has_m else None,
            "congested_at_share_other": _round(_share(gs[5, io, peak], gs[0, io, peak])) if has_o else None,
        }
    summary = pd.DataFrame(summ_rows, columns=list(LOS_SUMMARY_COLUMNS))

    # usual traffic: V/C of each bin
    tu = traffic_table(road, None, minutes, consts)
    usual = np.stack([tu.x[:, a:b].mean(axis=1) for _lab, a, b in bins], axis=1)
    day_ix = {d: i for i, d in enumerate(days)}
    periods = los_periods(days)
    n_p = len(periods)
    cols: dict[str, list[np.ndarray]] = {c: [] for c in ("vc_mean", "vc_max", "speed_factor_mean", "share_EF",
                                                         "los", "commuter_veh", "speed_los", "share_EF_speed",
                                                         "share_congested_AT")}
    for plab, pdays in periods:
        ix = [day_ix[d] for d in pdays]
        n_min = np.array([b - a for _lab, a, b in bins], dtype=float)[None, :] * len(ix)
        tot = acc[:, ix].sum(axis=1)                                       # sums over the period's days
        vc_mean, sf_mean = tot[0] / n_min, tot[1] / n_min
        mostly_broken = tot[3] / n_min >= 0.5
        grade = los_grade(vc_mean, info["mwy"].to_numpy()[:, None], mostly_broken)
        cols["vc_mean"].append(vc_mean)
        cols["vc_max"].append(vmax[ix].max(axis=0))
        cols["speed_factor_mean"].append(sf_mean)
        cols["share_EF"].append(tot[2] / n_min)
        cols["los"].append(np.asarray(LOS_GRADES, dtype=object)[grade])
        cols["commuter_veh"].append(tot[4] * vpa / len(ix))
        cols["speed_los"].append(np.asarray(LOS_GRADES, dtype=object)[speed_los_grade(sf_mean, mostly_broken)])
        cols["share_EF_speed"].append(tot[5] / n_min)
        cols["share_congested_AT"].append(tot[6] / n_min)
    # rows: section (ascending section_id: road.section_ids order), then period, then bin
    rep = n_p * n_b
    rl = pd.DataFrame({
        "section_id": np.repeat(info["section_id"].to_numpy(), rep),
        "street_name": np.repeat(info["street_name"].to_numpy(), rep),
        "frc": np.repeat(info["frc"].to_numpy(), rep), "mwy": np.repeat(info["mwy"].to_numpy(), rep),
        "corridor": np.repeat(info["corridor"].to_numpy(), rep),
        "km": np.repeat(info["km"].to_numpy(dtype=float), rep),
        "period": np.tile(np.repeat(np.array([p for p, _d in periods], dtype=object), n_b), n_s),
        "bin": np.tile(np.array([b[0] for b in bins], dtype=object), n_s * n_p),
        **{c: np.stack(v, axis=1).reshape(-1) for c, v in cols.items()},      # (sections, periods, bins)
        "usual_vc_mean": np.repeat(usual[:, None, :], n_p, axis=1).reshape(-1),
    })[list(ROAD_LOS_COLUMNS)]
    return LosOutputs(road_los=rl, summary=summary, day_keys=day_keys)


def write_los_outputs(run_dir: Path, out: LosOutputs) -> None:
    """road_los.csv and los_summary.csv (floats rounded to 4 dp) into run_dir."""
    rl = out.road_los.copy()
    for c in ("km", "vc_mean", "vc_max", "speed_factor_mean", "share_EF", "commuter_veh", "usual_vc_mean",
              "share_EF_speed", "share_congested_AT"):
        if len(rl):
            rl[c] = rl[c].astype(float).round(LOS_DP)
    rl.to_csv(Path(run_dir) / ROAD_LOS_FILE, index=False, lineterminator="\n")
    sm = out.summary.copy()
    for c in ("share_EF", "vc_mean", "speed_factor_mean", "veh_km", "share_EF_speed", "share_congested_AT"):
        if len(sm):
            sm[c] = sm[c].astype(float).round(LOS_DP)
    sm.to_csv(Path(run_dir) / LOS_SUMMARY_FILE, index=False, lineterminator="\n")


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
    """Road settings that a capacity calibration depends on (stored in calibration.json). With roads
    and road.mwy_breakdown on, the motorway breakdown keys are added (MWY_PARAMS_KEYS); without the
    rule the record is that of 2026-10-07."""
    rc = cfg.road
    out = {"enabled": bool(rc.enabled), "bpr_alpha": float(rc.bpr_alpha), "bpr_beta": int(rc.bpr_beta),
           "speed_floor": float(rc.speed_floor), "flow_window_min": int(rc.flow_window_min),
           "k": road_k(cfg) if rc.enabled else None}
    if rc.enabled and rc.mwy_breakdown:
        out.update(mwy_breakdown=True, mwy_breakdown_vc=float(rc.mwy_breakdown_vc),
                   mwy_recover_vc=float(rc.mwy_recover_vc), mwy_capacity_drop=float(rc.mwy_capacity_drop),
                   mwy_jam_speed=float(rc.mwy_jam_speed))
    return out


def road_settings_diff(recorded: Mapping[str, object] | None, current: Mapping[str, object]) -> list[str]:
    """Human-readable differences; a record without road settings was made with free-flow roads,
    one without mwy_breakdown without the motorway breakdown rule. With roads off on both sides
    nothing else matters."""
    rec = dict(recorded) if recorded else {"enabled": False}
    if bool(rec.get("enabled", False)) != bool(current.get("enabled", False)):
        return [f"road.enabled {bool(rec.get('enabled', False))} (this run {bool(current.get('enabled'))})"]
    if not current.get("enabled"):
        return []
    out = []
    for key in ("bpr_alpha", "bpr_beta", "speed_floor", "flow_window_min", "k"):
        if rec.get(key) != current.get(key):
            out.append(f"road {key} {rec.get(key)} (this run {current.get(key)})")
    mwy = (bool(rec.get("mwy_breakdown", False)), bool(current.get("mwy_breakdown", False)))
    if mwy[0] != mwy[1]:
        out.append(f"road mwy_breakdown {mwy[0]} (this run {mwy[1]})")
    elif mwy[1]:
        for key in MWY_PARAMS_KEYS[1:]:
            if rec.get(key) != current.get(key):
                out.append(f"road {key} {rec.get(key)} (this run {current.get(key)})")
    return out
