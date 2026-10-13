"""Road congestion inputs (run once, after build_inputs): road sections, counts and capacity k.

Owner: prep builder. See INTERFACES.md and the road congestion design (2026-10-07). Outputs into
cordon_lite/data/.

    python -m prep.build_roads [--config config.toml] [--out-dir data]

The prep shortest paths are rebuilt with the build_inputs functions from the TomTom shapefile
(``prep.roads_shp``, field ``segment_id`` = TomTom ``newSegmentId``) and the cordon, and must
reproduce data/origins.csv exactly (coordinates, weight, gate_id, corridor_id, free-flow minutes,
path_km at the stored precision); otherwise the script stops. The pre-gate part of every origin's
path (origin node -> inside end of its gate segment, the edges whose minutes add up to
fftt_to_gate_min) is cut into road SECTIONS: maximal chains of consecutive graph edges used by the
same set of origins with the same frc, speed limit, normalised street name and count values.

Counts: every AT/NZTA count point (``prep.adt_geojson``) is matched to the nearest graph edge with
the same normalised street name within ``prep.adt_match_m`` (state-highway records by route to
the motorway names; bus-only ramp records are not used). An AT count is not used when a more
recent count of the same street within ``prep.adt_propagate_m`` is more than four times larger
(stale or misplaced counts, ``stale_counts``). A count holds along the same street up to
``prep.adt_propagate_m`` through the network (nearest source wins); other edges take the median
two-way ADT of matched edges of their frc and speed band. An AT count is a two-way total unless
its road_name names a direction (EASTBOUND, NORTH BOUND, ...); state-highway records count one
carriageway or one ramp. Per section: observed inbound peak-hour flow
``obs_peak_vph = road_inbound_share x peak_ratio x adt_twoway``, capacity ``cap_vph = k x adt_dir``
(adt_dir at least the ``prep.road_adt_floor_pct``-th percentile of adt_dir of its frc, SPEC4: a very
small or stale count does not give a near-zero capacity; ``adt_floors``, ``capacity_adt``),
the commuters' share ``phi`` of the counted 06:00-10:00 volume, background ``bg_peak_vph`` and the
commuter weight ``w_factor``. k is bisected so that the origin-weighted travel time index of
departures in ``prep.road_tti_window`` under usual traffic equals ``prep.road_tti_target`` (TomTom
Traffic Index, Auckland 2025), with the engines' speed factor (``speed_factor``).

Motorway flow breakdown (2026-10-08): a section is a motorway MAINLINE section (``mwy`` = 1) when
it is frc 0 or carries a motorway name (``is_motorway_name``: the word Motorway; TomTom gives the
Auckland Harbour Bridge stretch of the Northern Motorway frc 1 and 2), is not a ramp
(``is_ramp_name``: Entry/Exit/Ramp names) and is signed at least MWY_MIN_SPEED_KMH (Stanley Street,
a 50 km/h signalised part of SH16, and the 60 km/h part of George Bolt Memorial Drive are frc 0
but no motorway). Its breakdown window ``bd_on``, ``bd_off``
under usual traffic follows ``cordonlite.roads.breakdown_windows`` (road.mwy_breakdown_vc,
road.mwy_recover_vc); with road.mwy_breakdown the usual-traffic speeds use the engines' breakdown
rule, and with ``prep.road_tti_exclude_mwy`` the TTI target is matched on the non-motorway part
of each trip only (time on its mwy = 0 sections over their free-flow time).

NZTA motorway counts (SPEC3, 2026-10-08; data/nzta from prep/fetch_nzta.py, CC BY 4.0): the 2024
quarter-hourly counts of each CBD-bound through-lane site give its capacity (the pre-breakdown
maximum, scaled to 2025-26 daily volumes), its observed flow and time profile, and its breakdown
window and capacity drop (``nzta_sites``, ``site_breakdown``; SPEC4: a window also ends when the
flow rises back towards the pre-breakdown maximum). A motorway mainline section of a corridor with
sites (``MWY_NAME_CORRIDOR``) takes the values of the nearest site of its corridor at any distance
(SPEC4; SPEC3 had 6 km; adt_source 'nzta', profile_id, cap_drop); other sections keep k x max(ADT,
road-class floor), profile 0 (the default profile, prep.road_profile) and road.mwy_capacity_drop.
k is calibrated with those sections fixed.

Outputs (LF line endings; a rerun on the same inputs writes byte-identical files):
    road_sections.csv     one row per section (SECTIONS_COLUMNS), sorted by section_id
    origin_sections.csv   origin_id, seq, section_id (seq 0 at the origin)
    section_segments.csv  section_id, seq, segment_id (TomTom ids in travel order, for drawing)
    road_profile.csv      profile_id, minute, r (1440 rows per profile, r with 6 decimals; 0 = default,
                          1.. = NZTA sites, road_meta.json profiles.site_of)
    road_meta.json        parameters, k, TTI, matching counts, input files
    road_report.md        human-readable summary

Public API:
    norm_name(name) -> str
    parse_peak_hour(value) -> float                     # minutes after midnight or nan
    count_kind(road_name) -> tuple[str, str]            # (kind, SH route)
    has_direction_label(road_name) -> bool              # AT count of one direction ('... (EASTBOUND)')
    speed_band(speed_kmh) -> int
    load_roads_shp(cfg) -> gpd.GeoDataFrame
    load_cordon_any(cfg) -> tuple[BaseGeometry, Path]
    reproduce_prep(cfg, roads, cordon) -> dict
    check_origins(origins, ref) -> None
    edge_table(G, roads, cfg) -> pd.DataFrame
    pregate_routes(G, dest, origins, cordon, rule, eid) -> dict[int, list[tuple[int, Node]]]
    load_counts(cfg) -> tuple[pd.DataFrame, dict]
    stale_counts(counts, point_match, max_m) -> np.ndarray   # bool per point_match row
    match_counts(edges, counts, match_m, stale_m=None) -> tuple[pd.DataFrame, pd.DataFrame]
    direct_values(edges, counts, edge_match, cfg) -> pd.DataFrame
    propagate(edges, direct, max_m) -> pd.DataFrame
    edge_values(edges, counts, edge_match, cfg) -> pd.DataFrame
    build_sections(routes, key) -> tuple[list[list[int]], dict[int, list[int]]]
    road_profile(values, start_min) -> np.ndarray
    load_nzta(data_dir) -> dict; nzta_lane_days(df) -> pd.DataFrame
    site_breakdown(q, global_drop, onset_latest, recovery_from, recover_rise) -> dict
    site_profile(r_bins, values, start_min) -> np.ndarray
    nzta_sites(nz, cfg) -> tuple[pd.DataFrame, dict, dict]
    map_sections_to_sites(sec, sites, max_m=None) -> pd.DataFrame; apply_nzta(...) -> pd.DataFrame
    adt_floors(frc, adt_dir, pct) -> dict[int, float]; capacity_adt(frc, adt_dir, floors) -> np.ndarray
    section_profiles(profile_id, profiles) -> np.ndarray
    is_motorway_name(street_name) -> bool
    is_motorway(frc, speed_limit, street_name) -> bool
    MwyRule.from_config(road_cfg) -> MwyRule
    usual_breakdown(obs_peak, cap, r, mwy, rule) -> tuple[np.ndarray, np.ndarray, np.ndarray]
    speed_factor(v, cap, alpha, floor, broken=None, keep=1.0, jam=1.0) -> np.ndarray
    usual_speed_table(obs_peak, cap, r, alpha, floor, broken=None, rule=None) -> np.ndarray
    probe_elapsed(route_mat, ff, F, departures, mask=None) -> np.ndarray | tuple
    weighted_tti(el, ffsum, weights) -> float
    class_tti(el, el_mwy, ff_all, ff_mwy, weights) -> dict
    calibrate_k(...) -> tuple[float, float, list]
    run_build_roads(cfg, out_dir=None) -> dict
    main(argv=None) -> int
"""

from __future__ import annotations

import argparse
import dataclasses
import heapq
import json
import math
import os
import re
from collections.abc import Hashable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely
from shapely.geometry.base import BaseGeometry

from cordonlite.config import ROOT, Config, load_config
from cordonlite.roads import breakdown_windows
from prep import build_inputs as bi
from prep.fetch_nzta import ATTRIBUTION as NZTA_ATTRIBUTION

Node = tuple[float, float]

SECTIONS_COLUMNS: tuple[str, ...] = (
    "section_id", "n_seg", "ff_min", "km", "frc", "speed_limit", "street_name", "adt_twoway",
    "adt_dir", "adt_source", "peak_ratio", "cap_vph", "obs_peak_vph", "am_volume_veh",
    "expected_commuter_veh", "phi", "bg_peak_vph", "w_factor", "n_origins", "x_mid", "y_mid",
    "mwy", "bd_on", "bd_off", "profile_id", "cap_drop",
)
ORIGIN_SECTIONS_COLUMNS: tuple[str, ...] = ("origin_id", "seq", "section_id")
SECTION_SEGMENTS_COLUMNS: tuple[str, ...] = ("section_id", "seq", "segment_id")
PROFILE_COLUMNS: tuple[str, ...] = ("profile_id", "minute", "r")   # long format (2026-10-08); 0 = default
DEFAULT_PROFILE_ID = 0
OUTPUT_FILES: tuple[str, ...] = ("road_sections.csv", "origin_sections.csv", "section_segments.csv",
                                 "road_profile.csv", "road_meta.json", "road_report.md")
ADT_SOURCES: tuple[str, ...] = ("count", "propagated", "default", "nzta")

# SA3 polygons in the SSC2026 repository, used when prep.cordon_gpkg does not exist (relative to
# the cordon_lite folder); data/cordon.geojson is the last fallback.
SA3_FALLBACK = "../../SSC2026/netlogo/Data/roads/akl_CBD_SA3.gpkg"

PEAK_RATIO_CLIP: tuple[float, float] = (0.05, 0.20)   # peak-hour volume / ADT is clipped to this [A]
AM_PEAK_START: tuple[int, int] = (360, 585)           # a count's peak_hour start in 06:00-09:45 is an AM peak
AM_VOLUME_WINDOW: tuple[int, int] = (360, 600)        # observed morning volume, minutes [360, 600)
PROFILE_RAMP_FROM_MIN = 300                           # profile ramps from 0.15 x first value at 05:00
PROFILE_LOW = 0.15
N_MINUTES = 1440
DEFAULT_MIN_EDGES = 5          # a (frc, speed band) median needs at least this many matched edges [A]
SH_BEARING_MAX_DEG = 60.0      # SH carriageway counts hold only on edges within this bearing [SPEC]
K_ITERATIONS = 30              # bisection steps for k (fixed, so reruns are identical; bracket / 2^30 << 1e-6)
TTI_HOURS: tuple[tuple[str, int, int], ...] = (
    ("06-07", 360, 420), ("07-08", 420, 480), ("08-09", 480, 540), ("09-10", 540, 600))
TTI_PROBE_MIN = 450            # 07:30
TTI_PEAK: tuple[str, int, int] = ("07:30-08:29", 450, 510)   # AT's AM peak hour (Network Performance Report)
VC_PROBE_MIN: tuple[int, ...] = (450, 495)   # 07:30 and 08:15
LOW_CAP_VPH = 50.0             # report flag: sections with a capacity this small come from very small counts
MWY_MIN_SPEED_KMH = 70         # a motorway mainline section is signed at least this (frc 0 also holds 50-60 km/h streets) [A]
BREAKDOWN_PROBE_MIN: tuple[int, ...] = (420, 450, 480, 510, 540, 570, 600)   # 07:00 .. 10:00, report

# State-highway route -> normalised TomTom street names of its carriageways [SPEC 1.2]; the
# literal TomTom names of numbered state-highway links ("State Highway 16", "20") are added.
SH_ROUTE_NAMES: dict[str, frozenset[str]] = {
    "01N": frozenset({"NORTHERN", "SOUTHERN"}),
    "016": frozenset({"NORTHWESTERN", "STANLEY", "THE STRAND", "STATE HIGHWAY 16"}),
    "018": frozenset({"UPPER HARBOUR"}),
    "020": frozenset({"SOUTHWESTERN", "STATE HIGHWAY 20", "20"}),
    "20A": frozenset({"GEORGE BOLT MEMORIAL"}),
}
NAME_SUFFIXES: frozenset[str] = frozenset({
    "ROAD", "RD", "STREET", "ST", "AVENUE", "AVE", "AV", "DRIVE", "DR", "PLACE", "PL", "CRESCENT",
    "CRES", "TERRACE", "TCE", "PARADE", "PDE", "HIGHWAY", "HWY", "LANE", "LN", "WAY", "RISE", "MALL",
    "EXTENSION", "EXT", "XTN", "BOULEVARD", "BLVD", "GROVE", "GR", "CLOSE", "CL", "COURT", "CT",
    "SQUARE", "SQ", "QUAY", "ESPLANADE", "ESP", "MOTORWAY", "MWY", "BYPASS", "HILL", "EXPRESSWAY",
    "QUADRANT", "MILE", "CIRCLE", "LOOP", "RAMP",
})
DIRECTION_TOKENS: frozenset[str] = frozenset({"N", "S", "E", "W", "NORTH", "SOUTH", "EAST", "WEST"})
SPEED_BANDS: tuple[tuple[float, int], ...] = (
    (35.0, 35), (45.0, 40), (55.0, 50), (65.0, 60), (75.0, 70), (90.0, 80), (math.inf, 100))
_RAMP_RE = re.compile(r"^(ENTRY|EXIT)\b|\b(ENTRY|EXIT|RAMP)\b")
# a motorway route's street name (is_motorway_name). TomTom names a few state-highway links by
# number instead ('20', frc 0; 'State Highway 16', an 80 km/h frc 1 road past the end of the
# Northwestern Motorway): those count as motorway by their frc only [A]
_MWY_NAME_RE = re.compile(r"\bMOTORWAY\b")
_NUMBERED_NAME_RE = re.compile(r"^(STATE HIGHWAY\s*)?\d+[A-Z]?$")   # report only: numbered names
_PREFIX_RE = re.compile(r"^(ENTRY|EXIT)(\s+AND\s+(ENTRY|EXIT))?\s+\S+\s+")
# AT direction label in a count's road_name ('TI RAKAU DR (EASTBOUND)', 'PAKURANGA RD (EAST BOUND)',
# 'ORMISTON RD (EASTBOUND/FLAT BUSH)'; not BOUNDARY RD): the count covers one direction [A]. Whether
# the TomTom edge has a reversed twin says little about this: the carriageways of divided roads
# never twin, and AT counts there are still two-way totals.
_DIR_LABEL_RE = re.compile(r"\b(NORTH|SOUTH|EAST|WEST) ?BOUND\b")
# State-highway ramp records of bus-only ramps and busways count buses, not general traffic, and are
# not used [A]: start_name or end_name names a bus ramp, buses or a busway ('START OF BUS RAMP',
# 'ISLAND NOSE/BUSES ONLY', 'ONEWA SOUTHBOUND BUSWAY BRIDGE'), or cars are under BUS_RAMP_MAX_CAR_PCT
# of the record's traffic (pccar; the Northern Busway station ramps have 1-15%, other ramps 76-100%).
_BUS_RAMP_RE = re.compile(r"\bBUS(ES|WAY)?\b")
BUS_RAMP_MAX_CAR_PCT = 50.0
STALE_ADT_RATIO = 0.25   # an AT count below this share of a more recent same-street count nearby is not used [A]
EDGE_ADT_SOURCES: tuple[str, ...] = ("count", "propagated", "default")   # graph edges (ADT_SOURCES: sections)

# NZTA motorway counts (SPEC3, 2026-10-08): data/nzta, written by prep/fetch_nzta.py (see its README.md)
NZTA_SUBDIR = "nzta"                    # under run.data_dir
NZTA_SITES_FILE = "tms_sites.csv"
NZTA_DAILY_FILE = "tms_daily_weekday.csv"      # weekdays 2025-10 .. 2026-09, daily lane x class counts
NZTA_AM_FILE = "tms_15min_am_2024.csv"         # weekdays May, Aug, Nov 2024, quarter hours 05:00-10:45
NZTA_QH_DAILY_FILE = "tms_15min_daily_2024.csv"  # full-day totals of the same quarter-hourly records
NZTA_FILES: tuple[str, ...] = (NZTA_SITES_FILE, NZTA_DAILY_FILE, NZTA_AM_FILE, NZTA_QH_DAILY_FILE)
NZTA_LOW_LANE = 0.30            # a day with a core lane missing or below this x its median is a lane outage [A]
NZTA_LEVEL_BAND: tuple[float, float] = (0.67, 1.5)   # a 2024 site-month whose median day is outside this x the
#                                 2025-26 median is not used (doubled counts: 01N19424 May, 01N10420 May and Aug) [A]
NZTA_MIN_DAYS = 20              # valid 2024 weekdays a site needs [SPEC3]
NZTA_FIRST_BIN = 300            # 05:00, first quarter hour of the AM file
NZTA_BIN_MIN = 15
NZTA_N_BINS = 24                # 05:00 .. 10:45
NZTA_PLATEAU_GAP = 30           # the plateau starts 30 min after the maximum [SPEC3]
NZTA_PLATEAU_END = 570          # ... and ends at 09:30 (bins starting before 09:30) [SPEC3]
NZTA_BREAKDOWN_DELTA = 0.05     # a throughput drop of at least 5% is a breakdown [SPEC3]
NZTA_SAT_FRAC = 0.95            # saturated: at least 0.95 q_max ...
NZTA_SAT_MIN = 60               # ... for at least 60 consecutive minutes [SPEC3]
NZTA_RECOVER_FRAC = 0.95        # recovered once the flow stays below 0.95 x the plateau ...
NZTA_RECOVER_BINS = 2           # ... for two consecutive quarter hours [SPEC3]
NZTA_NO_RECOVERY_MIN = 660      # 11:00: no recovery within the data window [SPEC3]
# Two amendments to the SPEC3 rule (2026-10-08, build), so that the rule gives the reading of the data
# that SPEC3 states (SH20, the SH16 CBD end and the Waterview link: no breakdown; SH1 and SH16: a plateau
# to about 09:30-10:15). None restores the literal rule (reported alongside, site_breakdown).
#   NZTA_ONSET_LATEST_MIN: a drop (or a saturated run) counts only when the maximum (the run) starts by
#     07:00, i.e. with a plateau of at least two hours before 09:30; after a later maximum (SH20 at 08:00)
#     the counts cannot tell a capacity drop from the end of the demand peak [A]
#   NZTA_RECOVERY_FROM_MIN: recovery is looked for from the end of the plateau (09:30) on; a dip below
#     0.95 x the plateau inside it (SH16, SH1 south upstream sites at 07:15-08:30) is still congested
#     flow [A]
NZTA_ONSET_LATEST_MIN: int | None = 420
NZTA_RECOVERY_FROM_MIN: int | None = 570
# SPEC4 (2026-10-08): the second way a jam ends. The downstream bottleneck clears, the queue drains and
# throughput rises back towards its pre-breakdown level: recovery is also two consecutive quarter hours
# above plateau + NZTA_RECOVER_RISE x (q_max - plateau) (each of the two bins below 0.95 x plateau or
# above this level). None: recovery only by a fall in flow (SPEC3).
NZTA_RECOVER_RISE: float | None = 0.5
# a motorway mainline section of a corridor with valid sites takes the nearest valid site of its corridor
# within this distance (m); None = at any distance [SPEC4] (SPEC3: 6000)
NZTA_MAP_M: float | None = None
NZTA_MAP_M_SPEC3 = 6000.0       # report only: sections mapped beyond the SPEC3 limit
NZTA_FARTHEST_N = 10            # report: the farthest mapped sections listed
# street name of a motorway mainline section -> NZTA corridor of its CBD-bound counts (None: no site on
# that route; the section keeps the k x ADT rule). A motorway name missing here stops the prep [SPEC3]
MWY_NAME_CORRIDOR: dict[str, str | None] = {
    "Northern Motorway": "SH1_north",        # incl. the Harbour Bridge (frc 1-2, motorway by name)
    "Southern Motorway": "SH1_south",
    "Northwestern Motorway": "SH16",
    "Southwestern Motorway": "SH20",
    "20": "SH20",                            # TomTom names the SH20 -> SH16 Waterview link by its route number
    "Upper Harbour Motorway": None,          # SH18: no site
    "Airport Motorway": None,                # SH20A: no site
    "George Bolt Memorial Drive": None,      # SH20A: no site
}
# Weekday holidays 2025-10 .. 2026-09 left out of the 2025-26 median day (the 2024 months hold none):
# NZ public holidays (Auckland) and school holidays (Ministry of Education term dates; summer taken as
# 18 Dec - 6 Feb) [A]
NZTA_PUBLIC_HOLIDAYS: frozenset[str] = frozenset({
    "2025-10-27", "2025-12-25", "2025-12-26", "2026-01-01", "2026-01-02", "2026-01-26", "2026-02-06",
    "2026-04-03", "2026-04-06", "2026-04-27", "2026-06-01", "2026-07-10"})
NZTA_SCHOOL_HOLIDAYS: tuple[tuple[str, str], ...] = (
    ("2024-04-13", "2024-04-28"), ("2024-07-06", "2024-07-21"), ("2024-09-28", "2024-10-13"),
    ("2024-12-18", "2025-01-31"), ("2025-09-27", "2025-10-12"), ("2025-12-18", "2026-02-06"),
    ("2026-04-03", "2026-04-19"), ("2026-07-04", "2026-07-19"), ("2026-09-26", "2026-10-11"))


# --------------------------------------------------------------------------- names and counts


def norm_name(name: Any) -> str:
    """Normalised street name for matching counts to TomTom segments.

    Upper case; ``(...)`` qualifiers dropped (also unclosed ones); TomTom ``Entry/Exit NNN``
    prefixes dropped; MOUNT -> MT, SAINT -> ST; punctuation removed; trailing direction tokens
    (N/S/E/W, NORTH, ...) and then street-type suffixes (RD/ROAD, ST/STREET, ...) dropped, always
    keeping the first word. 'Exit 429B Wellesley Street' -> 'WELLESLEY', 'MT EDEN RD (NORTH)' ->
    'MT EDEN'. TomTom's 'Terrace Atatu Road' is read as 'TE ATATU'.
    """
    if name is None or (isinstance(name, float) and math.isnan(name)):
        return ""
    s = str(name).upper().strip()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\(.*$", " ", s).strip()
    s = _PREFIX_RE.sub("", s)
    s = re.sub(r"^TERRACE ATATU\b", "TE ATATU", s)
    s = re.sub(r"[^A-Z0-9 ]", "", s.replace("-", " ").replace("/", " "))
    s = re.sub(r"\bMOUNT\b", "MT", s)
    s = re.sub(r"\bSAINT\b", "ST", s)
    t = s.split()
    while len(t) > 1 and t[-1] in DIRECTION_TOKENS:
        t.pop()
    while len(t) > 1 and t[-1] in NAME_SUFFIXES:
        t.pop()
    return " ".join(t)


def is_ramp_name(street_name: str) -> bool:
    """True for TomTom ramp names ('Exit 4A Northern Motorway', 'Northern Motorway Entry')."""
    return bool(_RAMP_RE.search(str(street_name).upper()))


def is_motorway_name(street_name: str) -> bool:
    """True for the street name of a motorway route: it holds the word Motorway (Northern, Southern,
    Northwestern, Southwestern, Upper Harbour, Airport Motorway; ramps are told apart by is_ramp_name)."""
    return bool(_MWY_NAME_RE.search(str(street_name).upper()))


def is_motorway(frc: int, speed_limit: float, street_name: str) -> bool:
    """Motorway MAINLINE (mwy = 1): frc 0 or a motorway name (is_motorway_name; TomTom gives some
    mainline links a lower frc, e.g. the Auckland Harbour Bridge: Northern Motorway frc 1 and 2),
    not a ramp (names starting with Entry/Exit/'Entry And Exit' or holding Entry, Exit, Ramp,
    On-Ramp, Off-Ramp) and signed at least MWY_MIN_SPEED_KMH."""
    if is_ramp_name(street_name) or float(speed_limit) < MWY_MIN_SPEED_KMH:
        return False
    return int(frc) == 0 or is_motorway_name(street_name)


def parse_peak_hour(value: Any) -> float:
    """Start of the count's peak hour in minutes after midnight ('800', '08:00', '16:'), else nan."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return math.nan
    s = str(value).strip()
    if ":" in s:
        h, _, mm = s.partition(":")
        h, mm = h.strip(), mm.strip() or "0"
        if not (h.isdigit() and mm.isdigit()):
            return math.nan
        return float(int(h) * 60 + int(mm))
    if not s.isdigit():
        return math.nan
    v = int(s)
    return float((v // 100) * 60 + v % 100)


def count_kind(road_name: Any) -> tuple[str, str]:
    """(kind, route) of a count record.

    kind: 'local' (AT count, two-way unless has_direction_label), 'sh_cway' (state-highway
    carriageway, road_name ending -I or -D), 'sh_ramp' (-R1, -R2, ...) or 'sh_other' (state-highway
    record without a direction suffix; not used). route: '01N', '016', ... for state highways.
    """
    s = "" if road_name is None or (isinstance(road_name, float) and math.isnan(road_name)) else str(road_name)
    m = re.match(r"^SH\s*(\w+)-", s)
    if not m:
        return "local", ""
    route = m.group(1)
    if re.search(r"-[ID]$", s):
        return "sh_cway", route
    if re.search(r"-R\d+$", s):
        return "sh_ramp", route
    return "sh_other", route


def has_direction_label(road_name: Any) -> bool:
    """True when an AT count's road_name names one direction ('TI RAKAU DR (EASTBOUND)', 'PAKURANGA
    RD (EAST BOUND)'): the count is directional. Other AT counts are two-way totals."""
    if road_name is None or (isinstance(road_name, float) and math.isnan(road_name)):
        return False
    return bool(_DIR_LABEL_RE.search(str(road_name).upper()))


def speed_band(speed_kmh: float) -> int:
    """Speed-limit band label used for default ADT medians (35, 40, 50, 60, 70, 80, 100)."""
    for upper, label in SPEED_BANDS:
        if float(speed_kmh) <= upper:
            return label
    return SPEED_BANDS[-1][1]


def clip_peak_ratio(x: float) -> float:
    lo, hi = PEAK_RATIO_CLIP
    return min(hi, max(lo, float(x)))


# --------------------------------------------------------------------------- loading


def load_roads_shp(cfg: Config) -> gpd.GeoDataFrame:
    """TomTom roads from ``prep.roads_shp`` through build_inputs.load_roads (field segment_id -> newSegmentId)."""
    shp = cfg.resolve_path(cfg.prep.roads_shp)
    if not shp.exists():
        raise FileNotFoundError(f"prep.roads_shp not found: {shp}")
    c2 = dataclasses.replace(cfg, prep=dataclasses.replace(cfg.prep, roads_gpkg=str(shp), roads_layer=shp.stem))
    roads = bi.load_roads(c2)
    if "newSegmentId" not in roads.columns:
        roads = roads.rename(columns={"segment_id": "newSegmentId"})
    return roads


def load_cordon_any(cfg: Config) -> tuple[BaseGeometry, Path]:
    """Cordon polygon: prep.cordon_gpkg if it exists, else the SSC2026 SA3 gpkg, else data/cordon.geojson."""
    for p in (cfg.prep.cordon_gpkg, SA3_FALLBACK):
        path = cfg.resolve_path(p)
        if path.exists():
            c2 = dataclasses.replace(cfg, prep=dataclasses.replace(cfg.prep, cordon_gpkg=str(path)))
            return bi.load_cordon(c2), path
    path = cfg.resolve_path(cfg.run.data_dir) / "cordon.geojson"
    gdf = gpd.read_file(path)
    if gdf.crs is not None and gdf.crs.to_epsg() != cfg.prep.crs_epsg:
        gdf = gdf.to_crs(epsg=cfg.prep.crs_epsg)
    return shapely.unary_union([shapely.make_valid(g) for g in gdf.geometry]).buffer(0), path


def load_counts(cfg: Config) -> tuple[pd.DataFrame, dict[str, int]]:
    """Count points with adt > 0 in the prep CRS, without the state-highway ramp records of bus-only
    ramps and busways (start_name or end_name names a bus ramp, buses or a busway, or pccar <
    BUS_RAMP_MAX_CAR_PCT; stats n_sh_ramp_bus).

    Columns: count_id (OBJECTID), road_name, kind, route, core (normalised road_name, local only),
    adt, peaktraffic, peak_min, count_date ('YYYY-MM-DD'), x, y.
    """
    path = cfg.resolve_path(cfg.prep.adt_geojson)
    g = gpd.read_file(path)
    if g.crs is None or g.crs.to_epsg() != cfg.prep.crs_epsg:
        g = g.set_crs(epsg=4326, allow_override=False) if g.crs is None else g
        g = g.to_crs(epsg=cfg.prep.crs_epsg)
    n_all = len(g)
    adt = pd.to_numeric(g["adt"], errors="coerce")
    g = g[(adt > 0) & g.geometry.notna() & ~g.geometry.is_empty].reset_index(drop=True)
    kinds = [count_kind(n) for n in g["road_name"]]
    xy = shapely.get_coordinates(g.geometry.values)
    dates = pd.to_datetime(g["count_date"], errors="coerce", utc=True)
    out = pd.DataFrame({
        "count_id": g["OBJECTID"].astype(int).to_numpy(),
        "road_name": g["road_name"].fillna("").astype(str).to_numpy(),
        "kind": [k for k, _ in kinds],
        "route": [r for _, r in kinds],
        "core": [norm_name(n) if k == "local" else "" for n, (k, _) in zip(g["road_name"], kinds)],
        "adt": pd.to_numeric(g["adt"], errors="coerce").to_numpy(dtype=float),
        "peaktraffic": pd.to_numeric(g["peaktraffic"], errors="coerce").to_numpy(dtype=float),
        "peak_min": [parse_peak_hour(v) for v in g["peak_hour"]],
        "count_date": dates.dt.strftime("%Y-%m-%d").fillna("").to_numpy(),
        "x": xy[:, 0], "y": xy[:, 1],
    })
    ends = [f"{a} {b}".upper() for a, b in zip(_text_col(g, "start_name"), _text_col(g, "end_name"))]
    pccar = (pd.to_numeric(g["pccar"], errors="coerce").to_numpy(dtype=float) if "pccar" in g.columns
             else np.full(len(g), np.nan))
    bus = (out["kind"] == "sh_ramp").to_numpy() & (
        np.array([bool(_BUS_RAMP_RE.search(e)) for e in ends], dtype=bool) | (pccar < BUS_RAMP_MAX_CAR_PCT))
    stats = {"n_points": int(n_all), "n_adt_positive": int(len(out)), "n_sh_ramp_bus": int(bus.sum())}
    out = out[~bus].reset_index(drop=True)
    for k in ("local", "sh_cway", "sh_ramp", "sh_other"):
        stats[f"n_{k}"] = int((out["kind"] == k).sum())
    return out, stats


def _text_col(g: pd.DataFrame, col: str) -> list[str]:
    """A text column as strings ('' for missing values or a missing column)."""
    if col not in g.columns:
        return [""] * len(g)
    return g[col].fillna("").astype(str).tolist()


# --------------------------------------------------------------------------- prep paths


def origins_frame(paths: pd.DataFrame, gates: pd.DataFrame) -> pd.DataFrame:
    """The origins.csv frame exactly as build_inputs.write_outputs builds it."""
    seg2gate = dict(zip(gates["segment_id"], gates["gate_id"]))
    seg2corr = dict(zip(gates["segment_id"], gates["corridor_id"]))
    return pd.DataFrame({
        "origin_id": paths["origin_id"].astype(int),
        "x_nztm": paths["x_nztm"].round(1),
        "y_nztm": paths["y_nztm"].round(1),
        "weight": paths["weight"].round(3),
        "corridor_id": paths["segment_id"].map(seg2corr).astype(int),
        "gate_id": paths["segment_id"].map(seg2gate).astype(int),
        "fftt_to_gate_min": paths["fftt_to_gate_min"].round(3),
        "fftt_gate_to_dest_min": paths["fftt_gate_to_dest_min"].round(3),
        "path_km": paths["path_km"].round(3),
    })[list(bi.ORIGINS_COLUMNS)]


def check_origins(origins: pd.DataFrame, ref: pd.DataFrame, atol: float = 5e-7) -> None:
    """Raise ValueError unless the rebuilt origins equal data/origins.csv column by column."""
    if len(origins) != len(ref):
        raise ValueError(f"rebuilt prep has {len(origins)} origins, data/origins.csv has {len(ref)}")
    bad = []
    for c in bi.ORIGINS_COLUMNS:
        if c not in ref.columns:
            bad.append(f"{c}: missing in data/origins.csv")
            continue
        a = origins[c].to_numpy(dtype=float)
        b = ref[c].to_numpy(dtype=float)
        n = int((~np.isclose(a, b, rtol=0.0, atol=atol)).sum())
        if n:
            bad.append(f"{c}: {n} rows differ (max abs diff {np.abs(a - b).max():.6g})")
    if bad:
        raise ValueError("the rebuilt prep does not reproduce data/origins.csv; road sections would not "
                         "match the run's origins:\n  " + "\n  ".join(bad))


def reproduce_prep(cfg: Config, roads: gpd.GeoDataFrame, cordon: BaseGeometry) -> dict[str, Any]:
    """Rebuild graph, destination, sampled origins, paths, gates and corridors as build_inputs does."""
    G = bi.build_graph(roads, cfg)
    dest = bi.destination_node(G, cordon)
    candidates = bi.candidate_origins(G, roads, cordon, cfg)
    origins = bi.sample_origins(candidates, cfg)
    paths = bi.trace_paths(G, dest, origins, cordon, cfg.prep.gate_rule)
    gates = bi.gate_table(paths, roads, cordon)
    gates, corridors = bi.group_corridors(gates, cordon, cfg)
    return {"G": G, "dest": dest, "origins": origins, "paths": paths, "gates": gates,
            "corridors": corridors, "origins_frame": origins_frame(paths, gates)}


def edge_table(G: nx.Graph, roads: gpd.GeoDataFrame, cfg: Config) -> pd.DataFrame:
    """One row per graph edge, ordered by its roads row (edge index = position).

    Columns: u, v (graph nodes), row, segment_id, minutes, distance_m, frc, speed_limit,
    street_name, core (norm_name), ramp, bearing (deg, from the segment's first to last vertex =
    travel direction), two_way (a segment in the reverse direction between the same rounded end
    points exists; otherwise a one-way carriageway or street), geometry.
    """
    r = cfg.prep.node_round_m
    geoms = roads.geometry.values
    p0 = shapely.get_coordinates(shapely.get_point(geoms, 0))
    p1 = shapely.get_coordinates(shapely.get_point(geoms, -1))
    x0, y0 = bi.round_xy(p0[:, 0], p0[:, 1], r)
    x1, y1 = bi.round_xy(p1[:, 0], p1[:, 1], r)
    directed = set(zip(zip(x0.tolist(), y0.tolist()), zip(x1.tolist(), y1.tolist())))
    edges = sorted(G.edges(data=True), key=lambda t: t[2]["row"])
    rows = []
    for u, v, d in edges:
        i = int(d["row"])
        a, b = (float(x0[i]), float(y0[i])), (float(x1[i]), float(y1[i]))
        rows.append({
            "u": u, "v": v, "row": i, "segment_id": d["segment_id"], "minutes": float(d["minutes"]),
            "distance_m": float(d["distance_m"]), "frc": int(d["frc"]),
            "speed_limit": int(round(d["speed_limit"])), "street_name": str(d["street_name"]),
            "core": norm_name(d["street_name"]), "ramp": is_ramp_name(d["street_name"]),
            "bearing": float(bi.bearing_deg(p0[i, 0], p0[i, 1], p1[i, 0], p1[i, 1])),
            "two_way": (b, a) in directed, "geometry": geoms[i],
        })
    return pd.DataFrame(rows)


def edge_index(edges: pd.DataFrame) -> dict[tuple[Node, Node], int]:
    """(u, v) and (v, u) -> edge index."""
    eid: dict[tuple[Node, Node], int] = {}
    for i, (u, v) in enumerate(zip(edges["u"], edges["v"])):
        eid[(u, v)] = i
        eid[(v, u)] = i
    return eid


def pregate_routes(G: nx.Graph, dest: Node, origins: pd.DataFrame, cordon: BaseGeometry, rule: str,
                   eid: dict[tuple[Node, Node], int]) -> dict[int, list[tuple[int, Node]]]:
    """origin_id -> [(edge index, node the edge is entered from)] from the origin to the gate's inside end.

    Same Dijkstra tree and gate rule as build_inputs.trace_paths; the gate edge is included.
    """
    _, paths = nx.single_source_dijkstra(G, dest, weight="minutes")
    nodes, xy = bi.node_array(G)
    ins = dict(zip(nodes, bi.inside_mask(cordon, xy).tolist()))
    out: dict[int, list[tuple[int, Node]]] = {}
    for o in origins.itertuples(index=False):
        path = list(reversed(paths[o.node]))
        i = bi.gate_index(path, ins, rule)
        out[int(o.origin_id)] = [(eid[(path[j], path[j + 1])], path[j]) for j in range(i)]
    return out


# --------------------------------------------------------------------------- count matching


def _name_ok(kind: str, route: str, core: str, e_core: str, e_ramp: bool, e_street: str) -> bool:
    if kind == "local":
        return core != "" and core == e_core
    if kind == "sh_cway":
        return e_core in SH_ROUTE_NAMES.get(route, frozenset())
    if kind == "sh_ramp":
        return e_ramp or e_street == ""
    return False


def stale_counts(counts: pd.DataFrame, point_match: pd.DataFrame, max_m: float) -> np.ndarray:
    """Stale AT counts among the matched points (bool per point_match row).

    A matched AT count is stale when a matched AT count of the same street (normalised name) whose
    point lies within max_m is more recent (later count_date) and its two-way ADT (2 x adt with a
    direction label) is below STALE_ADT_RATIO of that count's: an old count that newer counts of
    the street contradict, or a count placed on the wrong link (Wairau Rd: 64 vehicles a day in
    1999, 28 m from 19,798 in 2024; Queenstown Rd: 2,362 in 1990 next to 21,297 in 2025). The
    'most recent count_date' rule for counts on one edge, applied to the street's neighbourhood
    where the values disagree that much.
    """
    out = np.zeros(len(point_match), dtype=bool)
    if len(point_match) == 0:
        return out
    ci = point_match["ci"].to_numpy(dtype=int)
    loc = counts["kind"].to_numpy()[ci] == "local"
    core = counts["core"].to_numpy()[ci]
    date = counts["count_date"].to_numpy()[ci]
    x, y = counts["x"].to_numpy(dtype=float)[ci], counts["y"].to_numpy(dtype=float)[ci]
    twoway = np.array([float(a) * (2.0 if has_direction_label(n) else 1.0) for a, n in
                       zip(counts["adt"].to_numpy()[ci], counts["road_name"].to_numpy()[ci])])
    by_core: dict[str, list[int]] = {}
    for i in np.flatnonzero(loc & (core != "")):
        by_core.setdefault(str(core[i]), []).append(int(i))
    for rows in by_core.values():
        for i in rows:
            for j in rows:
                if (j != i and date[j] > date[i] and twoway[i] < STALE_ADT_RATIO * twoway[j]
                        and math.hypot(x[j] - x[i], y[j] - y[i]) <= max_m):
                    out[i] = True
                    break
    return out


def match_counts(edges: pd.DataFrame, counts: pd.DataFrame, match_m: float,
                 stale_m: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Name-checked nearest-edge match of every count point within match_m.

    Returns (point_match, edge_match). point_match: one row per matched count (ci = row in
    ``counts``, edge, dist_m, stale), nearest edge with an accepted name (ties: lower edge index);
    stale marks the AT counts that ``stale_counts`` drops with max_m = stale_m (none when stale_m
    is None). edge_match: one row per edge holding a count that is not stale; several counts on
    one edge keep the most recent count_date (ties: nearer, then lower count_id).
    """
    cols = ["ci", "edge", "dist_m"]
    if len(counts) == 0 or len(edges) == 0:
        return pd.DataFrame(columns=cols + ["stale"]), pd.DataFrame(columns=cols)
    geoms = np.asarray(edges["geometry"].to_list(), dtype=object)
    tree = shapely.STRtree(geoms)
    pts = shapely.points(counts["x"].to_numpy(dtype=float), counts["y"].to_numpy(dtype=float))
    pi, ei = tree.query(pts, predicate="dwithin", distance=float(match_m))
    if len(pi) == 0:
        return pd.DataFrame(columns=cols + ["stale"]), pd.DataFrame(columns=cols)
    d = shapely.distance(pts[pi], geoms[ei])
    kind, route, core = counts["kind"].to_numpy(), counts["route"].to_numpy(), counts["core"].to_numpy()
    e_core, e_ramp, e_st = edges["core"].to_numpy(), edges["ramp"].to_numpy(), edges["street_name"].to_numpy()
    ok = np.array([_name_ok(kind[p], route[p], core[p], e_core[e], bool(e_ramp[e]), e_st[e])
                   for p, e in zip(pi, ei)], dtype=bool)
    cand = pd.DataFrame({"ci": pi[ok].astype(int), "edge": ei[ok].astype(int), "dist_m": d[ok]})
    pm = (cand.sort_values(["ci", "dist_m", "edge"], kind="mergesort")
          .drop_duplicates("ci", keep="first").reset_index(drop=True))
    pm["stale"] = (stale_counts(counts, pm, float(stale_m)) if stale_m is not None
                   else np.zeros(len(pm), dtype=bool))
    pm2 = pm[~pm["stale"]]
    pm2 = pm2.assign(date=counts["count_date"].to_numpy()[pm2["ci"]],
                     cid=counts["count_id"].to_numpy()[pm2["ci"]])
    em = (pm2.sort_values(["edge", "date", "dist_m", "cid"], ascending=[True, False, True, True], kind="mergesort")
          .drop_duplicates("edge", keep="first")[cols].reset_index(drop=True))
    return pm[cols + ["stale"]], em


def direct_values(edges: pd.DataFrame, counts: pd.DataFrame, edge_match: pd.DataFrame,
                  cfg: Config) -> pd.DataFrame:
    """Values of the edges that hold a count (index = edge index).

    Directional convention [SPEC 1.3, direction from the count record]: a count of one carriageway
    or direction (SH -I/-D, SH ramp, or an AT count whose road_name names a direction,
    has_direction_label) is directional: adt_dir = adt, adt_twoway = 2 x adt; any other AT count
    is a two-way total: adt_twoway = adt, adt_dir = adt / 2. (An AT count on a TomTom edge without
    a reversed twin is not taken as directional: those edges are mostly carriageways of divided
    roads, and their AT counts are two-way totals like those of the same street elsewhere.)
    peak_ratio = peaktraffic / adt when the count's peak hour starts in 06:00-09:45, else
    prep.road_peak_ratio_default; clipped.
    """
    p = cfg.prep
    rows = []
    for e, ci in zip(edge_match["edge"].astype(int), edge_match["ci"].astype(int)):
        c = counts.iloc[ci]
        adt = float(c["adt"])
        directional = c["kind"] != "local" or has_direction_label(c["road_name"])
        twoway = 2.0 * adt if directional else adt
        pk, ptr = float(c["peak_min"]), float(c["peaktraffic"])
        am = (not math.isnan(pk)) and AM_PEAK_START[0] <= pk <= AM_PEAK_START[1] and ptr > 0
        ratio = clip_peak_ratio(ptr / adt if am else p.road_peak_ratio_default)
        rows.append({"edge": e, "count_id": int(c["count_id"]), "kind": c["kind"],
                     "adt_twoway": round(twoway, 3), "adt_dir": round(twoway / 2.0, 3),
                     "peak_ratio": round(ratio, 6), "count_peak": bool(am)})
    cols = ["edge", "count_id", "kind", "adt_twoway", "adt_dir", "peak_ratio", "count_peak"]
    return pd.DataFrame(rows, columns=cols).set_index("edge")


def _bearing_ok(b_src: float, b_tgt: float, axial: bool) -> bool:
    d = abs(((b_tgt - b_src) + 180.0) % 360.0 - 180.0)
    if axial:
        d = min(d, 180.0 - d)
    return d <= SH_BEARING_MAX_DEG


def propagate(edges: pd.DataFrame, direct: pd.DataFrame, max_m: float) -> pd.DataFrame:
    """Nearest count source along the same street for every edge without a count.

    The search runs through the edges with the same normalised name (midpoint to midpoint network
    distance, segment lengths ``distance_m``) up to ``max_m``. A source is accepted for a target
    edge when: both are not frc <= 1 / ramp edges, or their TomTom streetName is identical; and,
    for a state-highway carriageway count, the target's bearing is within 60 deg of the source
    edge's (compared as axes when either edge is two-way). Nearest accepted source wins (ties:
    lower source edge index). Returns a frame (index = edge index) with src_edge and dist_m.
    """
    n = len(edges)
    core = edges["core"].to_numpy()
    u, v = edges["u"].to_numpy(), edges["v"].to_numpy()
    length = edges["distance_m"].to_numpy(dtype=float)
    frc, ramp, street = edges["frc"].to_numpy(), edges["ramp"].to_numpy(), edges["street_name"].to_numpy()
    bearing, two_way = edges["bearing"].to_numpy(dtype=float), edges["two_way"].to_numpy()
    adj: dict[str, dict[Node, list[tuple[Node, float]]]] = {}
    node_edges: dict[str, dict[Node, list[int]]] = {}
    for i in range(n):
        if core[i] == "":
            continue
        a = adj.setdefault(core[i], {})
        a.setdefault(u[i], []).append((v[i], length[i]))
        a.setdefault(v[i], []).append((u[i], length[i]))
        ne = node_edges.setdefault(core[i], {})
        ne.setdefault(u[i], []).append(i)
        ne.setdefault(v[i], []).append(i)
    is_direct = np.zeros(n, dtype=bool)
    is_direct[direct.index.to_numpy(dtype=int)] = True
    best: dict[int, tuple[float, int]] = {}
    for s in sorted(int(x) for x in direct.index):
        c = core[s]
        if c == "":
            continue
        sh = direct.at[s, "kind"] == "sh_cway"
        strict_s = frc[s] <= 1 or bool(ramp[s])
        dist: dict[Node, float] = {}
        h0 = 0.5 * length[s]
        heap: list[tuple[float, int, Node]] = [(h0, 0, u[s]), (h0, 1, v[s])]
        tie = 2
        while heap:
            d0, _, x = heapq.heappop(heap)
            if x in dist:
                continue
            dist[x] = d0
            for y, w in adj[c].get(x, ()):
                nd = d0 + w
                if nd <= max_m and y not in dist:
                    heapq.heappush(heap, (nd, tie, y))
                    tie += 1
        for x, d0 in dist.items():
            for t in node_edges[c].get(x, ()):
                if is_direct[t]:
                    continue
                dt = d0 + 0.5 * length[t]
                if dt > max_m:
                    continue
                if (strict_s or frc[t] <= 1 or bool(ramp[t])) and street[s] != street[t]:
                    continue
                if sh and not _bearing_ok(bearing[s], bearing[t], bool(two_way[s] or two_way[t])):
                    continue
                cur = best.get(t)
                if cur is None or (dt, s) < cur:
                    best[t] = (dt, s)
    idx = sorted(best)
    return pd.DataFrame({"src_edge": [best[t][1] for t in idx], "dist_m": [best[t][0] for t in idx]},
                        index=pd.Index(idx, name="edge"))


def default_adt(edges: pd.DataFrame,
                direct: pd.DataFrame) -> tuple[dict[tuple[int, int], float], dict[int, float], float]:
    """Median two-way ADT of count edges by (frc, speed band) with >= DEFAULT_MIN_EDGES edges, by frc, overall."""
    d = edges.loc[direct.index, ["frc", "speed_limit"]].copy()
    d["band"] = [speed_band(s) for s in d["speed_limit"]]
    d["adt_twoway"] = direct["adt_twoway"].to_numpy(dtype=float)
    by_band = {(int(f), int(b)): float(g.median()) for (f, b), g in d.groupby(["frc", "band"])["adt_twoway"]
               if len(g) >= DEFAULT_MIN_EDGES}
    by_frc = {int(f): float(g.median()) for f, g in d.groupby("frc")["adt_twoway"]}
    overall = float(d["adt_twoway"].median()) if len(d) else math.nan
    return by_band, by_frc, overall


def edge_values(edges: pd.DataFrame, counts: pd.DataFrame, edge_match: pd.DataFrame,
                cfg: Config) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Per-edge adt_source, count_id, adt_twoway, adt_dir, peak_ratio (counts, propagation, defaults)."""
    p = cfg.prep
    direct = direct_values(edges, counts, edge_match, cfg)
    prop = propagate(edges, direct, float(p.adt_propagate_m))
    by_band, by_frc, overall = default_adt(edges, direct)
    n = len(edges)
    src = np.full(n, "default", dtype=object)
    cid = np.full(n, -1, dtype=int)
    twoway = np.full(n, np.nan)
    ratio = np.full(n, round(clip_peak_ratio(p.road_peak_ratio_default), 6))
    count_peak = np.zeros(n, dtype=bool)
    di = direct.index.to_numpy(dtype=int)
    src[di] = "count"
    cid[di] = direct["count_id"].to_numpy(dtype=int)
    twoway[di] = direct["adt_twoway"].to_numpy(dtype=float)
    ratio[di] = direct["peak_ratio"].to_numpy(dtype=float)
    count_peak[di] = direct["count_peak"].to_numpy(dtype=bool)
    if len(prop):
        pi = prop.index.to_numpy(dtype=int)
        se = prop["src_edge"].to_numpy(dtype=int)
        src[pi] = "propagated"
        cid[pi] = cid[se]
        twoway[pi] = twoway[se]
        ratio[pi] = ratio[se]
        count_peak[pi] = count_peak[se]
    frc, spd = edges["frc"].to_numpy(dtype=int), edges["speed_limit"].to_numpy(dtype=int)
    for i in np.flatnonzero(src == "default"):
        val = by_band.get((int(frc[i]), speed_band(spd[i])), by_frc.get(int(frc[i]), overall))
        if not np.isfinite(val):
            raise ValueError("no matched count to derive a default ADT from")
        twoway[i] = round(val, 3)
    out = pd.DataFrame({"adt_source": src, "count_id": cid, "adt_twoway": twoway,
                        "adt_dir": np.round(twoway / 2.0, 3), "peak_ratio": ratio, "count_peak": count_peak})
    info = {"defaults_by_band": {f"{f}/{b}": round(x, 1) for (f, b), x in sorted(by_band.items())},
            "defaults_by_frc": {str(f): round(x, 1) for f, x in sorted(by_frc.items())},
            "default_overall": round(overall, 1)}
    return out, info


# --------------------------------------------------------------------------- sections


def build_sections(routes: dict[int, Sequence[int]],
                   key: Sequence[Hashable]) -> tuple[list[list[int]], dict[int, list[int]]]:
    """Cut the routes into sections.

    ``routes``: origin_id -> edge indices in travel order (origin first); ``key[e]``: the edge's
    attributes that must agree within a section (frc, speed limit, name, count values). A section
    is a maximal run of consecutive edges with the same key and the same set of origins using
    them. Sections are numbered by first appearance walking origins in origin_id order, then seq.
    Returns (section edge lists in travel order, origin_id -> section ids in travel order).
    Raises ValueError if the result is not a consistent partition of every route.
    """
    users: dict[int, list[int]] = {}
    for oid in sorted(routes):
        for e in routes[oid]:
            users.setdefault(e, []).append(oid)
    set_ids: dict[tuple[int, ...], int] = {}
    eset = {e: set_ids.setdefault(tuple(o), len(set_ids)) for e, o in users.items()}
    sec_of: dict[int, int] = {}
    sections: list[list[int]] = []
    osec: dict[int, list[int]] = {}
    for oid in sorted(routes):
        seq: list[int] = []
        prev_key: Any = None
        prev_sec = -1
        for e in routes[oid]:
            k = (eset[e], key[e])
            if e in sec_of:
                s = sec_of[e]
            elif prev_sec >= 0 and k == prev_key:
                s = prev_sec
                sections[s].append(e)
            else:
                s = len(sections)
                sections.append([e])
            sec_of[e] = s
            if not seq or seq[-1] != s:
                seq.append(s)
            prev_key, prev_sec = k, s
        osec[oid] = seq
    for oid, seq in osec.items():
        flat = [e for s in seq for e in sections[s]]
        if flat != list(routes[oid]) or len(set(seq)) != len(seq):
            raise ValueError(f"sections are not a consistent partition of the route of origin {oid}")
    return sections, osec


def chain_midpoint(geoms: Sequence[BaseGeometry], starts: Sequence[Node]) -> tuple[float, float]:
    """Point at half the length of a chain of segments, each entered from ``starts[i]``."""
    lens = [float(g.length) for g in geoms]
    half = 0.5 * sum(lens)
    acc = 0.0
    for g, st, L in zip(geoms, starts, lens):
        if acc + L >= half or g is geoms[-1]:
            c = shapely.get_coordinates(g)
            fwd = math.hypot(c[0, 0] - st[0], c[0, 1] - st[1]) <= math.hypot(c[-1, 0] - st[0], c[-1, 1] - st[1])
            off = min(max(half - acc, 0.0), L)
            p = g.interpolate(off if fwd else L - off)
            return float(p.x), float(p.y)
        acc += L
    raise ValueError("empty chain")


# --------------------------------------------------------------------------- profile and speeds


def road_profile(values: Sequence[float], start_min: int, n: int = N_MINUTES) -> np.ndarray:
    """r(m) for every minute 0..n-1 (6 decimals) from 15-min bins starting at ``start_min``.

    Value at each bin centre (start + 7.5 + 15 i), linear between centres, constant after the last
    centre, a linear ramp from 0.15 x the first value at minute 300 (05:00) up to the first centre,
    and 0.15 x the first value before minute 300.
    """
    v = [float(x) for x in values]
    c0 = start_min + 7.5
    c_last = c0 + 15.0 * (len(v) - 1)
    low = PROFILE_LOW * v[0]
    out = np.empty(n)
    for m in range(n):
        if m >= c_last:
            r = v[-1]
        elif m >= c0:
            j = int((m - c0) // 15.0)
            t = (m - (c0 + 15.0 * j)) / 15.0
            r = v[j] + (v[j + 1] - v[j]) * t
        elif m >= PROFILE_RAMP_FROM_MIN:
            r = low + (v[0] - low) * (m - PROFILE_RAMP_FROM_MIN) / (c0 - PROFILE_RAMP_FROM_MIN)
        else:
            r = low
        out[m] = float(f"{r:.6f}")
    return out


@dataclasses.dataclass(frozen=True)
class MwyRule:
    """Motorway breakdown parameters (config [road] mwy_*); on = road.mwy_breakdown."""

    on: bool
    breakdown_vc: float
    recover_vc: float
    capacity_drop: float
    jam_speed: float

    @classmethod
    def from_config(cls, rd: Any) -> MwyRule:
        return cls(bool(rd.mwy_breakdown), float(rd.mwy_breakdown_vc), float(rd.mwy_recover_vc),
                   float(rd.mwy_capacity_drop), float(rd.mwy_jam_speed))

    @property
    def keep(self) -> float:
        """1 - capacity_drop, the same double as the engines' mwy_keep."""
        return 1 - self.capacity_drop


def profile_rows(r: Any, n: int) -> np.ndarray:
    """A time profile for n sections: r is one profile (1440 values, shared: shape (1, 1440)) or one
    row per section (shape (n, 1440), e.g. section_profiles)."""
    a = np.asarray(r, dtype=float)
    if a.ndim == 1:
        return a[None, :]
    if a.shape[0] != n:
        raise ValueError(f"profile has {a.shape[0]} rows for {n} sections")
    return a


def adt_floors(frc: Sequence[int], adt_dir: Sequence[float], pct: float) -> dict[int, float]:
    """Capacity floor per road class [SPEC4 A3]: the pct-th percentile of adt_dir over the sections
    of each frc (unweighted, numpy's linear interpolation, rounded to 3 decimals); {} (no floor) when
    pct <= 0 (prep.road_adt_floor_pct)."""
    if pct <= 0:
        return {}
    if pct > 100:
        raise ValueError(f"prep.road_adt_floor_pct must be at most 100, got {pct}")
    f = np.asarray(frc, dtype=np.int64)
    a = np.asarray(adt_dir, dtype=float)
    return {int(c): round(float(np.percentile(a[f == c], pct)), 3) for c in sorted(set(f.tolist()))}


def capacity_adt(frc: Sequence[int], adt_dir: Sequence[float], floors: dict[int, float]) -> np.ndarray:
    """The ADT the capacity uses (cap_vph = k x this): max(adt_dir, floors[frc]) per section, adt_dir
    where the class has no floor [SPEC4 A3]. Background and observed flows keep adt_dir (the counts)."""
    a = np.asarray(adt_dir, dtype=float)
    fl = np.array([floors.get(int(c), -math.inf) for c in frc], dtype=float)
    return np.where(a < fl, fl, a)


def section_profiles(profile_id: Sequence[int], profiles: dict[int, np.ndarray]) -> np.ndarray:
    """r[s, m]: the profile of each section (profile_id) by minute."""
    ids = sorted(profiles)
    P = np.vstack([np.asarray(profiles[p], dtype=float) for p in ids])
    pos = {p: i for i, p in enumerate(ids)}
    return P[np.array([pos[int(p)] for p in profile_id], dtype=np.int64)]


def usual_breakdown(obs_peak: np.ndarray, cap: np.ndarray, r: np.ndarray, mwy: np.ndarray,
                    rule: MwyRule, fixed: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Motorway breakdown under usual traffic (v = obs_peak_vph x r[m], x = v / cap_vph, minutes 0..1439).

    r: one shared profile or one row per section (profile_rows). Returns (broken[s, m], bd_on,
    bd_off): the window of each mwy = 1 section from cordonlite.roads.breakdown_windows (-1, -1 for
    other sections and when x never reaches the threshold) and, when the rule is on, the engines'
    state: in the window or x >= breakdown_vc. fixed = (mask, bd_on, bd_off): sections whose window
    is given (NZTA sites: the window the counts show) instead of the usual-traffic hysteresis."""
    obs = np.asarray(obs_peak, dtype=float)
    x = (obs[:, None] * profile_rows(r, len(obs))) / np.asarray(cap, dtype=float)[:, None]
    mw = np.asarray(mwy, dtype=np.int64) == 1
    on = np.full(len(obs), -1, dtype=np.int64)
    off = np.full(len(obs), -1, dtype=np.int64)
    calc = mw.copy()
    if fixed is not None:
        fm = np.asarray(fixed[0], dtype=bool) & mw
        on[fm] = np.asarray(fixed[1], dtype=np.int64)[fm]
        off[fm] = np.asarray(fixed[2], dtype=np.int64)[fm]
        calc &= ~fm
    if calc.any():
        on[calc], off[calc] = breakdown_windows(x[calc], rule.breakdown_vc, rule.recover_vc)
    broken = np.zeros(x.shape, dtype=bool)
    if rule.on and mw.any():
        m = np.arange(x.shape[1])[None, :]
        broken[mw] = ((on[mw][:, None] <= m) & (m < off[mw][:, None])) | (x[mw] >= rule.breakdown_vc)
    return broken, on, off


def speed_factor(v: Any, cap: Any, alpha: float, floor: float, broken: Any = None, keep: Any = 1.0,
                 jam: float = 1.0) -> np.ndarray:
    """Engine speed factor (SPEC 1.4): x = v / cap, f = 1 / (1 + alpha (x x)(x x)); where ``broken``
    (motorway breakdown, cordonlite.roads.speed_factor) y = x / keep, f = 1 / (1 + alpha (y y)(y y))
    at most jam; f at least floor. keep = 1 - capacity drop, one value or one per row (section)."""
    x = np.asarray(v, dtype=float) / np.asarray(cap, dtype=float)
    x4 = (x * x) * (x * x)
    f = 1.0 / (1.0 + alpha * x4)
    if broken is not None:
        y = x / keep
        y4 = (y * y) * (y * y)
        fb = 1.0 / (1.0 + alpha * y4)
        f = np.where(broken, np.where(fb > jam, jam, fb), f)
    return np.where(f < floor, floor, f)


def usual_speed_table(obs_peak: np.ndarray, cap: np.ndarray, r: np.ndarray, alpha: float,
                      floor: float, broken: np.ndarray | None = None, rule: MwyRule | None = None,
                      keep: np.ndarray | None = None) -> np.ndarray:
    """f[s, m] under usual traffic (v = obs_peak_vph x r[m]; r shared or per section) for every
    section and minute; broken (usual_breakdown) with its rule applies the motorway breakdown rule,
    with keep = 1 - cap_drop per section (default rule.keep for all)."""
    obs = np.asarray(obs_peak, dtype=float)
    v = obs[:, None] * profile_rows(r, len(obs))
    c = np.asarray(cap, dtype=float)[:, None]
    if broken is None or rule is None or not broken.any():
        return speed_factor(v, c, alpha, floor)
    kp = rule.keep if keep is None else np.asarray(keep, dtype=float)[:, None]
    return speed_factor(v, c, alpha, floor, broken, kp, rule.jam_speed)


def route_matrix(osec: dict[int, list[int]], origin_ids: Sequence[int]) -> np.ndarray:
    """Routes as an (n_origins, max_len) int array of section ids, padded with -1."""
    L = max((len(osec[o]) for o in origin_ids), default=0)
    mat = np.full((len(origin_ids), L), -1, dtype=np.int64)
    for i, o in enumerate(origin_ids):
        mat[i, :len(osec[o])] = osec[o]
    return mat


def route_ffsum(route_mat: np.ndarray, ff: np.ndarray) -> np.ndarray:
    """Sum of ff_min over each route, added left to right in seq order (as the engines do)."""
    s = np.zeros(route_mat.shape[0])
    for k in range(route_mat.shape[1]):
        sec = route_mat[:, k]
        act = sec >= 0
        s[act] = s[act] + ff[sec[act]]
    return s


def probe_elapsed(route_mat: np.ndarray, ff: np.ndarray, F: np.ndarray, departures: Sequence[int],
                  mask: np.ndarray | None = None) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    """Elapsed minutes to the gate of a probe car (adds no load) per (route, departure).

    Same traversal rule as the engines: entering section s at minute d + floor(el) uses the speed
    factor of that minute; el = el + ff_min_s / f. Minutes past the end of ``F`` use its last column.
    With ``mask`` (bool per section) also returns the minutes spent on the masked sections.
    """
    dep = np.asarray(departures, dtype=np.int64)[None, :]
    el = np.zeros((route_mat.shape[0], dep.shape[1]))
    el_m = np.zeros_like(el) if mask is not None else None
    last = F.shape[1] - 1
    for k in range(route_mat.shape[1]):
        sec = route_mat[:, k]
        act = sec >= 0
        if not act.any():
            break
        s = sec[act]
        e = el[act]
        m = np.minimum(dep + np.floor(e).astype(np.int64), last)
        f = F[s[:, None], m]
        dt = ff[s][:, None] / f
        el[act] = e + dt
        if el_m is not None:
            el_m[act] = el_m[act] + np.where(mask[s][:, None], dt, 0.0)
    return el if el_m is None else (el, el_m)


def weighted_tti(el: np.ndarray, ffsum: np.ndarray, weights: np.ndarray) -> float:
    """Origin-weighted mean over (origin, departure) of el / ffsum."""
    w = np.asarray(weights, dtype=float)
    tti = el / ffsum[:, None]
    return float((w[:, None] * tti).sum() / (w.sum() * el.shape[1]))


def class_tti(el: np.ndarray, el_mwy: np.ndarray, ff_all: np.ndarray, ff_mwy: np.ndarray,
              weights: np.ndarray) -> dict[str, float]:
    """weighted_tti of the whole trip ('all'), its motorway part ('motorway': time on mwy = 1 sections
    over their free-flow time, origins with such a part) and its other part ('non_motorway')."""
    w = np.asarray(weights, dtype=float)
    ff_non = ff_all - ff_mwy
    out = {"all": weighted_tti(el, ff_all, w)}
    for lab, num, den in (("motorway", el_mwy, ff_mwy), ("non_motorway", el - el_mwy, ff_non)):
        ok = den > 1e-9
        out[lab] = weighted_tti(num[ok], den[ok], w[ok]) if ok.any() else math.nan
    return out


def calibrate_k(route_mat: np.ndarray, ff: np.ndarray, weights: np.ndarray, obs_peak: np.ndarray,
                adt_dir: np.ndarray, r: np.ndarray, alpha: float, floor: float, target: float,
                window: tuple[int, int], bounds: tuple[float, float],
                n_iter: int = K_ITERATIONS, mwy: np.ndarray | None = None, rule: MwyRule | None = None,
                exclude_mwy: bool = False, cap_fixed: np.ndarray | None = None,
                win_fixed: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
                keep: np.ndarray | None = None) -> tuple[float, float, list[tuple[float, float]]]:
    """Bisect k (cap_vph = round(k x adt_dir, 3)) so the weighted TTI over departures in window equals target.

    adt_dir: the ADT the capacity uses (run_build_roads passes capacity_adt, adt_dir with the
    road-class floor [SPEC4]); obs_peak holds the flows.

    With ``mwy`` and ``rule`` the usual-traffic speeds follow the motorway breakdown rule (when
    rule.on; the windows depend on k through cap_vph); with ``exclude_mwy`` the TTI is that of the
    trips' non-motorway parts (class_tti 'non_motorway'). r: one shared profile or one per section.
    NZTA sections (SPEC3) do not depend on k: ``cap_fixed`` (nan = k x adt_dir) holds their capacity,
    ``win_fixed`` (usual_breakdown fixed) their windows and ``keep`` the per-section 1 - cap_drop.
    Returns (k rounded to 6 decimals, TTI at that k, [(k, TTI) probes]). Raises ValueError when the
    target is outside the TTI range of the bracket.
    """
    ffsum = route_ffsum(route_mat, ff)
    deps = list(range(int(window[0]), int(window[1])))
    hist: list[tuple[float, float]] = []
    mask = (np.asarray(mwy, dtype=np.int64) == 1) if mwy is not None else None
    ff_m = route_ffsum(route_mat, np.where(mask, ff, 0.0)) if exclude_mwy and mask is not None else None

    def tti(k: float) -> float:
        cap = np.round(k * adt_dir, 3)
        if cap_fixed is not None:
            cap = np.where(np.isnan(cap_fixed), cap, cap_fixed)
        broken = (usual_breakdown(obs_peak, cap, r, mwy, rule, win_fixed)[0]
                  if mwy is not None and rule is not None and rule.on else None)
        F = usual_speed_table(obs_peak, cap, r, alpha, floor, broken, rule, keep)
        if ff_m is not None:
            el, el_m = probe_elapsed(route_mat, ff, F, deps, mask)
            val = class_tti(el, el_m, ffsum, ff_m, weights)["non_motorway"]
        else:
            val = weighted_tti(probe_elapsed(route_mat, ff, F, deps), ffsum, weights)
        hist.append((k, val))
        return val

    lo, hi = float(bounds[0]), float(bounds[1])
    t_lo, t_hi = tti(lo), tti(hi)
    if not (t_hi <= target <= t_lo):
        raise ValueError(f"TTI target {target} outside the bracket: k={lo} gives {t_lo:.4f}, "
                         f"k={hi} gives {t_hi:.4f} (prep.road_cap_k_bounds)")
    for _ in range(n_iter):
        mid = 0.5 * (lo + hi)
        if tti(mid) > target:
            lo = mid
        else:
            hi = mid
    k = round(0.5 * (lo + hi), 6)
    return k, tti(k), hist


# --------------------------------------------------------------------------- NZTA motorway counts (SPEC3)


def nzta_holiday(dates: Sequence[str]) -> np.ndarray:
    """True for the dates (YYYY-MM-DD) in NZTA_PUBLIC_HOLIDAYS or an NZTA_SCHOOL_HOLIDAYS range."""
    out = np.zeros(len(dates), dtype=bool)
    for i, d in enumerate(dates):
        s = str(d)
        out[i] = s in NZTA_PUBLIC_HOLIDAYS or any(a <= s <= b for a, b in NZTA_SCHOOL_HOLIDAYS)
    return out


def load_nzta(data_dir: Path) -> dict[str, pd.DataFrame]:
    """The four NZTA files of data_dir/nzta (prep/fetch_nzta.py): sites, daily, am, qh_daily."""
    d = Path(data_dir) / NZTA_SUBDIR
    missing = [f for f in NZTA_FILES if not (d / f).exists()]
    if missing:
        raise FileNotFoundError(f"NZTA count files missing in {d}: {missing}; run `python -m prep.fetch_nzta "
                                "--out data/nzta` (see data/nzta/README.md)")
    txt = {"site_ref": str, "local_date": str, "time": str}
    sites = pd.read_csv(d / NZTA_SITES_FILE, dtype={"site_ref": str})
    out = {"sites": sites}
    for key, f in (("daily", NZTA_DAILY_FILE), ("am", NZTA_AM_FILE), ("qh_daily", NZTA_QH_DAILY_FILE)):
        df = pd.read_csv(d / f, dtype={c: t for c, t in txt.items()})
        out[key] = df
    return out


def nzta_lane_days(df: pd.DataFrame, low: float = NZTA_LOW_LANE) -> pd.DataFrame:
    """Per site_ref, flow_direction and local_date: total (all lanes and classes; a day without a
    heavy record is unclassified, its light count holds all vehicles) and low_lane: a core lane (one
    present on at least half of the direction's days) is missing or below ``low`` x its median day."""
    cols = ["site_ref", "flow_direction", "local_date", "total", "low_lane"]
    if len(df) == 0:
        return pd.DataFrame({c: [] for c in cols})
    lane = df.groupby(["site_ref", "flow_direction", "local_date", "lane"], sort=True)["count"].sum()
    parts = []
    for (s, fd), g in lane.groupby(level=["site_ref", "flow_direction"], sort=True):
        piv = g.droplevel(["site_ref", "flow_direction"]).unstack("lane")
        n = len(piv)
        core = [c for c in piv.columns if 2 * int(piv[c].notna().sum()) >= n]
        sub = piv[core]
        lowm = (sub.lt(low * sub.median(), axis=1) | sub.isna()).any(axis=1)
        parts.append(pd.DataFrame({"site_ref": str(s), "flow_direction": int(fd),
                                   "local_date": piv.index.astype(str).to_numpy(),
                                   "total": piv.sum(axis=1).to_numpy(dtype=float),
                                   "low_lane": lowm.to_numpy(dtype=bool)}))
    return pd.concat(parts, ignore_index=True)[cols]


def site_breakdown(q: Sequence[float], global_drop: float, onset_latest: int | None = NZTA_ONSET_LATEST_MIN,
                   recovery_from: int | None = NZTA_RECOVERY_FROM_MIN,
                   recover_rise: float | None = NZTA_RECOVER_RISE) -> dict[str, Any]:
    """Capacity, breakdown and capacity drop of one site from its mean weekday flow q (veh/h) in the
    quarter hours from NZTA_FIRST_BIN (05:00) [SPEC3 1].

    q_max = max q (t_max its first bin); plateau q_pl = median of q over the bins from t_max + 30 min
    to 09:30 (the bins after t_max when there are none); delta = 1 - q_pl / q_max. Saturated: q >=
    0.95 q_max for at least 60 consecutive minutes (the first such run). Breakdown when saturated
    (onset = start of the run, cap_drop = max(delta, global_drop): the drop cannot be measured at
    the bottleneck itself) or when delta >= 0.05 (onset = first bin after t_max with q <= q_max (1 -
    delta / 2), cap_drop = delta). Recovery bd_off = first bin after the onset from which, for two
    consecutive bins, q < 0.95 q_pl (demand fell) or, with recover_rise [SPEC4], q > q_pl +
    recover_rise (q_max - q_pl) (the downstream bottleneck cleared and throughput rose back);
    recovery_by 'fall', 'rise' or 'mixed' (one bin each); else NZTA_NO_RECOVERY_MIN (11:00,
    recovered False). Amendments (None = the literal rule): onset_latest = latest start of the
    maximum (drop) or of the saturated run; recovery_from = earliest recovery bin; recover_rise None
    = recovery by a fall only (SPEC3). Without a breakdown bd_on = bd_off = -1 and cap_drop =
    global_drop. Minutes are bin starts (integers)."""
    v = [float(x) for x in q]
    n = len(v)
    t = [NZTA_FIRST_BIN + NZTA_BIN_MIN * i for i in range(n)]
    j = 0
    for i in range(1, n):
        if v[i] > v[j]:
            j = i
    q_max, t_max = v[j], t[j]
    pl = [i for i in range(n) if t[i] >= t_max + NZTA_PLATEAU_GAP and t[i] < NZTA_PLATEAU_END]
    if not pl:
        pl = list(range(j + 1, n))
    q_pl = float(np.median([v[i] for i in pl])) if pl else q_max
    delta = 1.0 - q_pl / q_max if q_max > 0 else 0.0
    need = -(-NZTA_SAT_MIN // NZTA_BIN_MIN)
    sat_i, sat_len, i = -1, 0, 0
    while i < n:
        if v[i] >= NZTA_SAT_FRAC * q_max:
            k = i
            while k < n and v[k] >= NZTA_SAT_FRAC * q_max:
                k += 1
            if k - i >= need and (onset_latest is None or t[i] <= onset_latest):
                sat_i, sat_len = i, k - i
                break
            i = k
        else:
            i += 1
    drop = delta >= NZTA_BREAKDOWN_DELTA and (onset_latest is None or t_max <= onset_latest)
    out: dict[str, Any] = {"q_max": round(q_max, 3), "t_max": t_max, "q_plateau": round(q_pl, 3),
                           "plateau_bins": [t[pl[0]], t[pl[-1]]] if pl else [], "delta": round(delta, 6),
                           "sat_start": t[sat_i] if sat_i >= 0 else -1, "sat_min": sat_len * NZTA_BIN_MIN,
                           "saturated": sat_i >= 0, "breakdown": False, "bd_on": -1, "bd_off": -1,
                           "recovered": None, "recovery_by": None, "rise_level": None,
                           "cap_drop": float(global_drop)}
    if sat_i >= 0:
        on_i = sat_i
        out["cap_drop"] = round(max(delta, float(global_drop)), 6)
    elif drop:
        on_i = next((i for i in range(j + 1, n) if v[i] <= q_max * (1.0 - delta / 2.0)), -1)
        if on_i < 0:
            return out
        out["cap_drop"] = round(delta, 6)
    else:
        return out
    out.update(breakdown=True, bd_on=t[on_i], bd_off=NZTA_NO_RECOVERY_MIN, recovered=False)
    lim = NZTA_RECOVER_FRAC * q_pl
    hi = q_pl + recover_rise * (q_max - q_pl) if recover_rise is not None else math.inf
    out["rise_level"] = round(hi, 3) if math.isfinite(hi) else None
    first = on_i + 1
    while first < n and recovery_from is not None and t[first] < recovery_from:
        first += 1
    for i in range(first, n - NZTA_RECOVER_BINS + 1):
        w = [v[i + b] for b in range(NZTA_RECOVER_BINS)]
        if all(x < lim or x > hi for x in w):
            by = "fall" if all(x < lim for x in w) else ("rise" if all(x > hi for x in w) else "mixed")
            out.update(bd_off=t[i], recovered=True, recovery_by=by)
            break
    return out


def _default_profile_at(values: Sequence[float], start_min: int, t: float) -> float:
    """road_profile's formula (before rounding) at a real minute t."""
    v = [float(x) for x in values]
    c0 = start_min + 7.5
    c_last = c0 + 15.0 * (len(v) - 1)
    low = PROFILE_LOW * v[0]
    if t >= c_last:
        return v[-1]
    if t >= c0:
        j = int((t - c0) // 15.0)
        u = (t - (c0 + 15.0 * j)) / 15.0
        return v[j] + (v[j + 1] - v[j]) * u
    if t >= PROFILE_RAMP_FROM_MIN:
        return low + (v[0] - low) * (t - PROFILE_RAMP_FROM_MIN) / (c0 - PROFILE_RAMP_FROM_MIN)
    return low


def site_profile(r_bins: Sequence[float], values: Sequence[float], start_min: int, n: int = N_MINUTES) -> np.ndarray:
    """r(m) of an NZTA site for every minute 0..n-1 (6 decimals) [SPEC3 1]: its quarter-hour ratios
    r_bins (from 05:00) at the bin centres, linear between centres; before the first and after the
    last centre the shared default profile (prep.road_profile, road_profile) scaled to match there."""
    rb = [float(x) for x in r_bins]
    c0 = NZTA_FIRST_BIN + 7.5
    c_last = c0 + NZTA_BIN_MIN * (len(rb) - 1)
    a_lo = rb[0] / _default_profile_at(values, start_min, c0)
    a_hi = rb[-1] / _default_profile_at(values, start_min, c_last)
    out = np.empty(n)
    for m in range(n):
        if m < c0:
            r = a_lo * _default_profile_at(values, start_min, m)
        elif m > c_last:
            r = a_hi * _default_profile_at(values, start_min, m)
        else:
            j = min(int((m - c0) // NZTA_BIN_MIN), len(rb) - 2)
            u = (m - (c0 + NZTA_BIN_MIN * j)) / NZTA_BIN_MIN
            r = rb[j] + (rb[j + 1] - rb[j]) * u
        out[m] = float(f"{r:.6f}")
    return out


def nzta_sites(nz: dict[str, pd.DataFrame], cfg: Config) -> tuple[pd.DataFrame, dict[str, np.ndarray],
                                                                    dict[int, np.ndarray]]:
    """Site analysis of the NZTA counts [SPEC3 1].

    Valid 2024 weekdays of a site's counted (CBD-bound) direction: no lane outage in the full-day or
    the 05:00-11:00 totals (nzta_lane_days), all 24 quarter hours present, not in a site-month whose
    median day is outside NZTA_LEVEL_BAND x the site's 2025-26 median (doubled counts), not a holiday.
    A site is valid (used) when it is a through-lane (mainline) site counting the CBD-bound direction
    (cbd_bound 1, cbd_role not 'mixed') with at least NZTA_MIN_DAYS valid days. Per site: q (veh/h,
    mean of the valid days, all lanes and classes, 3 decimals) by quarter hour 05:00-10:45; the
    2024 -> 2025-26 scale = median weekday 2025-26 (no lane outage, no holiday) / median valid 2024
    day (else the corridor's median scale, else 1); capacity cap_vph = q_max x scale; obs_peak_vph =
    the peak-hour mean of q x scale; r_bins = q x scale / obs_peak_vph; breakdown (site_breakdown,
    with the literal SPEC3 rule as lit_* and the end of the window without the SPEC4 rise rule as
    fo_bd_off). Valid sites get profile ids 1.. in tms_sites.csv order.

    Returns (site table, q by site_ref, minute profile by profile_id)."""
    sites = nz["sites"]
    gdrop = float(cfg.road.mwy_capacity_drop)
    d25 = nzta_lane_days(nz["daily"])
    d24 = nzta_lane_days(nz["qh_daily"])
    a24 = nzta_lane_days(nz["am"]).rename(columns={"total": "am_total", "low_lane": "am_low_lane"})
    am = nz["am"]
    key = ["site_ref", "flow_direction", "local_date"]
    nqh = am.groupby(key, sort=True)["time"].nunique().rename("n_qh").reset_index()
    bins = [_hhmm(NZTA_FIRST_BIN + NZTA_BIN_MIN * i) for i in range(NZTA_N_BINS)]
    rows: list[dict[str, Any]] = []
    qs: dict[str, np.ndarray] = {}
    for s in sites.itertuples(index=False):
        ref, fd = str(s.site_ref), int(s.flow_direction)
        a = d25[(d25["site_ref"] == ref) & (d25["flow_direction"] == fd)]
        ok25 = ~a["low_lane"].to_numpy(dtype=bool) & ~nzta_holiday(a["local_date"].tolist())
        med25 = float(np.median(a["total"].to_numpy(dtype=float)[ok25])) if ok25.any() else math.nan
        b = d24[(d24["site_ref"] == ref) & (d24["flow_direction"] == fd)]
        b = (b.merge(a24[key + ["am_low_lane"]], on=key, how="left").merge(nqh, on=key, how="left")
             .sort_values("local_date", kind="mergesort").reset_index(drop=True))
        b["am_low_lane"] = b["am_low_lane"].astype(object).where(b["am_low_lane"].notna(), True).astype(bool)
        b["n_qh"] = b["n_qh"].fillna(0).astype(int)
        month = b["local_date"].str[:7]
        bad_months = []
        if math.isfinite(med25) and med25 > 0:
            for mo in sorted(set(month)):
                ratio = float(np.median(b.loc[month == mo, "total"].to_numpy(dtype=float))) / med25
                if not (NZTA_LEVEL_BAND[0] <= ratio <= NZTA_LEVEL_BAND[1]):
                    bad_months.append(f"{mo} (x{ratio:.2f})")
        bad = month.isin([x.split(" ")[0] for x in bad_months]).to_numpy()
        valid_day = (~b["low_lane"].to_numpy(dtype=bool) & ~b["am_low_lane"].to_numpy(dtype=bool)
                     & (b["n_qh"].to_numpy() == NZTA_N_BINS) & ~bad & ~nzta_holiday(b["local_date"].tolist()))
        days = b.loc[valid_day, "local_date"].tolist()
        med24 = float(np.median(b.loc[valid_day, "total"].to_numpy(dtype=float))) if days else math.nan
        q = np.full(NZTA_N_BINS, math.nan)
        if days:
            x = am[(am["site_ref"] == ref) & (am["flow_direction"] == fd) & am["local_date"].isin(set(days))]
            M = (x.groupby(["local_date", "time"], sort=True)["count"].sum().unstack("time")
                 .reindex(index=sorted(days), columns=bins).fillna(0.0).to_numpy(dtype=float))
            q = np.round(4.0 * M.mean(axis=0), 3)
            qs[ref] = q
        reason = ""
        if str(s.kind) != "mainline":
            reason = f"not a through-lane site ({s.kind})"
        elif int(s.cbd_bound) != 1 or str(s.cbd_role) == "mixed" or "CBD-bound" not in str(s.cbd_role):
            reason = f"not CBD-bound ({s.cbd_role})"
        elif len(days) < NZTA_MIN_DAYS:
            reason = f"{len(days)} valid 2024 weekdays (< {NZTA_MIN_DAYS})"
        rows.append({"site_ref": ref, "description": str(s.description), "corridor": str(s.corridor),
                     "direction": str(s.direction), "kind": str(s.kind), "cbd_role": str(s.cbd_role),
                     "x_nztm": float(s.x_nztm), "y_nztm": float(s.y_nztm),
                     "days_2024": int(len(b)), "valid_2024": int(len(days)), "level_flagged": "; ".join(bad_months),
                     "median_2024": med24, "median_2025_26": med25, "valid_2025_26": int(ok25.sum()),
                     "valid": reason == "", "reason": reason})
    tab = pd.DataFrame(rows)
    own = [r["median_2025_26"] / r["median_2024"] if (math.isfinite(r["median_2025_26"]) and
                                                      math.isfinite(r["median_2024"]) and r["median_2024"] > 0)
           else math.nan for r in rows]
    tab["scale"], tab["scale_source"] = math.nan, ""
    for i, r in tab.iterrows():
        if math.isfinite(own[i]):
            tab.at[i, "scale"], tab.at[i, "scale_source"] = round(own[i], 6), "site"
            continue
        corr = [own[k] for k in range(len(rows)) if rows[k]["corridor"] == r["corridor"] and math.isfinite(own[k])]
        if corr:
            tab.at[i, "scale"], tab.at[i, "scale_source"] = round(float(np.median(corr)), 6), "corridor"
        else:
            tab.at[i, "scale"], tab.at[i, "scale_source"] = 1.0, "none"
    p = cfg.prep
    profiles: dict[int, np.ndarray] = {}
    extra: list[dict[str, Any]] = []
    pid = 0
    for i, r in tab.iterrows():
        e: dict[str, Any] = {"profile_id": -1}
        ref = r["site_ref"]
        if ref in qs:
            q = qs[ref]
            lit = site_breakdown(q, gdrop, None, None, None)
            e.update({f"lit_{k}": lit[k] for k in ("breakdown", "bd_on", "bd_off", "cap_drop")})
        if bool(r["valid"]):
            pid += 1
            q = qs[ref]
            sc = float(r["scale"])
            bd = site_breakdown(q, gdrop)
            fo = site_breakdown(q, gdrop, recover_rise=None)     # recovery by a fall only (SPEC3 amended)
            e.update(fo_bd_off=fo["bd_off"])
            qsc = [float(x) * sc for x in q]
            ph_best, ph_start = -1.0, 0
            for k in range(NZTA_N_BINS - 3):
                mean4 = (qsc[k] + qsc[k + 1] + qsc[k + 2] + qsc[k + 3]) / 4.0
                if mean4 > ph_best:
                    ph_best, ph_start = mean4, NZTA_FIRST_BIN + NZTA_BIN_MIN * k
            obs = round(ph_best, 3)
            r_bins = [x / obs for x in qsc]
            profiles[pid] = site_profile(r_bins, p.road_profile, p.road_profile_start_min)
            e.update(profile_id=pid, cap_vph=round(bd["q_max"] * sc, 3), obs_peak_vph=obs,
                     peak_hour_start=ph_start, r_max=round(max(r_bins), 6), **bd)
        extra.append(e)
    tab = pd.concat([tab, pd.DataFrame(extra)], axis=1)
    return tab, qs, profiles


def map_sections_to_sites(sec: pd.DataFrame, sites: pd.DataFrame, max_m: float | None = NZTA_MAP_M) -> pd.DataFrame:
    """For every motorway mainline section (mwy = 1): its NZTA corridor (MWY_NAME_CORRIDOR by street
    name) and the nearest valid site of that corridor (distance from the section midpoint to the site
    point; ties: the first site in tms_sites.csv order), at any distance when max_m is None [SPEC4],
    else only within max_m (SPEC3: 6 km). Sections of a route without a corridor (None) or of a
    corridor without valid sites get none. Returns a frame aligned with sec: corridor ('' none),
    site_ref ('' none), dist_m (nan without a site). A motorway name missing from
    MWY_NAME_CORRIDOR raises ValueError."""
    is_m = sec["mwy"].to_numpy(dtype=np.int64) == 1
    names = sec["street_name"].astype(str).to_numpy()
    unknown = sorted({n for n, m in zip(names, is_m) if m and n not in MWY_NAME_CORRIDOR})
    if unknown:
        raise ValueError(f"motorway sections named {unknown} have no entry in MWY_NAME_CORRIDOR "
                         "(map each to an NZTA corridor or to None)")
    valid = sites[sites["valid"].astype(bool)]
    corr = np.full(len(sec), "", dtype=object)
    site = np.full(len(sec), "", dtype=object)
    dist = np.full(len(sec), math.nan)
    xm, ym = sec["x_mid"].to_numpy(dtype=float), sec["y_mid"].to_numpy(dtype=float)
    for i in np.flatnonzero(is_m):
        c = MWY_NAME_CORRIDOR[names[i]]
        if c is None:
            continue
        corr[i] = c
        cand = valid[valid["corridor"] == c]
        if cand.empty:
            continue
        d = np.hypot(cand["x_nztm"].to_numpy(dtype=float) - xm[i], cand["y_nztm"].to_numpy(dtype=float) - ym[i])
        j = int(np.argmin(d))
        if max_m is None or d[j] <= max_m:
            site[i], dist[i] = str(cand["site_ref"].iat[j]), round(float(d[j]), 1)
    return pd.DataFrame({"corridor": corr, "site_ref": site, "dist_m": dist}, index=sec.index)


def apply_nzta(sec: pd.DataFrame, site_map: pd.DataFrame, sites: pd.DataFrame, profiles: dict[int, np.ndarray],
               cfg: Config) -> pd.DataFrame:
    """Section values from the NZTA site of each mapped motorway section [SPEC3 2]: cap_vph = the
    site's capacity, obs_peak_vph and profile_id from the site, bd_on/bd_off = the site's window,
    cap_drop = its drop, adt_source 'nzta'; am_volume_veh, phi, bg_peak_vph and w_factor recomputed
    with the site profile (SPEC 1.3). Every other section: profile_id 0 (the default profile),
    cap_drop = road.mwy_capacity_drop (cap_vph, bd_on, bd_off set later from k)."""
    out = sec.copy()
    out["profile_id"] = DEFAULT_PROFILE_ID
    out["cap_drop"] = float(cfg.road.mwy_capacity_drop)
    by_ref = sites.set_index("site_ref")
    for i in np.flatnonzero(site_map["site_ref"].to_numpy() != ""):
        s = by_ref.loc[site_map["site_ref"].iat[i]]
        pid = int(s["profile_id"])
        rr = profiles[pid]
        r_am = 0.0
        for m in range(*AM_VOLUME_WINDOW):
            r_am += float(rr[m])
        obs = float(s["obs_peak_vph"])
        am_vol = round(obs * r_am / 60.0, 3)
        exp_c = float(out["expected_commuter_veh"].iat[i])
        phi = min(1.0, exp_c / am_vol) if am_vol > 0 else 1.0
        wf = min(1.0, am_vol / exp_c) if exp_c > 0 else 1.0
        idx = out.index[i]
        out.loc[idx, ["cap_vph", "obs_peak_vph", "am_volume_veh", "phi", "bg_peak_vph", "w_factor"]] = [
            float(s["cap_vph"]), obs, am_vol, round(phi, 6), round(obs * (1.0 - phi), 3), round(wf, 6)]
        out.loc[idx, ["profile_id", "bd_on", "bd_off"]] = [pid, int(s["bd_on"]), int(s["bd_off"])]
        out.loc[idx, "cap_drop"] = float(s["cap_drop"])
        out.loc[idx, "adt_source"] = "nzta"
    for c in ("profile_id", "bd_on", "bd_off"):
        out[c] = out[c].astype(np.int64)
    return out


def nzta_summary(sites: pd.DataFrame, sec: pd.DataFrame, site_map: pd.DataFrame, pre: pd.DataFrame, k: float,
                 trav: np.ndarray, corr_tti: dict[str, dict[str, float]],
                 nz: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """road_meta.json 'nzta': rule constants, per site (validity, q_max, plateau, delta, window, scale,
    capacity against the k x ADT capacity the mapped sections would have had), the section mapping and
    the motorway TTI by motorway corridor under usual traffic."""
    ff = sec["ff_min"].to_numpy(dtype=float)
    wt = trav * ff
    is_m = sec["mwy"].to_numpy(dtype=np.int64) == 1
    sm = site_map["site_ref"].to_numpy()
    old_cap = np.round(k * pre["adt_cap" if "adt_cap" in pre.columns else "adt_dir"].to_numpy(dtype=float), 3)
    old_obs = pre["obs_peak_vph"].to_numpy(dtype=float)

    def num(x: Any, nd: int = 3) -> Any:
        try:
            v = float(x)
        except (TypeError, ValueError):
            return None
        return None if not math.isfinite(v) else round(v, nd)

    site_rows = []
    for t in sites.itertuples(index=False):
        d = {"site_ref": t.site_ref, "corridor": t.corridor, "direction": t.direction, "kind": t.kind,
             "cbd_role": t.cbd_role, "valid": bool(t.valid), "reason": t.reason, "days_2024": int(t.days_2024),
             "valid_2024": int(t.valid_2024), "level_flagged": t.level_flagged,
             "median_2024": num(t.median_2024, 1), "median_2025_26": num(t.median_2025_26, 1),
             "valid_2025_26": int(t.valid_2025_26), "scale": num(t.scale, 6), "scale_source": t.scale_source}
        if pd.notna(getattr(t, "lit_breakdown", np.nan)):
            d["literal_rule"] = {"breakdown": bool(t.lit_breakdown), "bd_on": int(t.lit_bd_on),
                                 "bd_off": int(t.lit_bd_off), "cap_drop": num(t.lit_cap_drop, 6)}
        if bool(t.valid):
            mapped = sm == t.site_ref
            d.update({"profile_id": int(t.profile_id), "q_max": num(t.q_max), "t_max": _hhmm(int(t.t_max)),
                      "q_plateau": num(t.q_plateau), "plateau_bins": [_hhmm(int(x)) for x in t.plateau_bins],
                      "delta": num(t.delta, 6), "saturated_min": int(t.sat_min),
                      "saturated_from": _hhmm(int(t.sat_start)) if int(t.sat_start) >= 0 else None,
                      "breakdown": bool(t.breakdown), "bd_on": int(t.bd_on), "bd_off": int(t.bd_off),
                      "window": (f"{_hhmm(int(t.bd_on))}-{_hhmm(int(t.bd_off))}" if bool(t.breakdown) else "none"),
                      "recovered_by_1045": (None if not bool(t.breakdown) else bool(t.recovered)),
                      "recovery_by": (t.recovery_by if bool(t.breakdown) and bool(t.recovered) else None),
                      "rise_level": num(t.rise_level),
                      "window_fall_only": (f"{_hhmm(int(t.bd_on))}-{_hhmm(int(t.fo_bd_off))}" if bool(t.breakdown)
                                           else "none"),
                      "cap_drop": num(t.cap_drop, 6), "cap_vph": num(t.cap_vph), "obs_peak_vph": num(t.obs_peak_vph),
                      "peak_hour": f"{_hhmm(int(t.peak_hour_start))}-{_hhmm(int(t.peak_hour_start) + 60)}",
                      "r_max": num(t.r_max, 6),
                      "n_sections": int(mapped.sum()), "ff_min": round(float(ff[mapped].sum()), 3),
                      "old_cap_vph_min_median_max": ([num(np.min(old_cap[mapped])), num(np.median(old_cap[mapped])),
                                                      num(np.max(old_cap[mapped]))] if mapped.any() else []),
                      "old_obs_peak_vph_median": num(np.median(old_obs[mapped])) if mapped.any() else None})
        site_rows.append(d)
    names = sec["street_name"].astype(str).to_numpy()
    mapping = {}
    for n in sorted({str(x) for x in names[is_m]}):
        sel = is_m & (names == n)
        on = sel & (sm != "")
        mapping[n] = {"corridor": MWY_NAME_CORRIDOR[n], "sections": int(sel.sum()), "mapped": int(on.sum()),
                      "ff_min": round(float(ff[sel].sum()), 3), "ff_min_mapped": round(float(ff[on].sum()), 3),
                      "sites": {str(s): int((sm[sel] == s).sum()) for s in sorted(set(sm[on]))},
                      "max_dist_m": num(np.nanmax(site_map["dist_m"].to_numpy()[on]), 1) if on.any() else None}
    # distance from each mapped section's midpoint to its site [SPEC4 A2]
    dist = site_map["dist_m"].to_numpy(dtype=float)
    on_all = sm != ""
    corr_of = site_map["corridor"].to_numpy()
    far = on_all & (dist > NZTA_MAP_M_SPEC3)

    def dist_q(sel: np.ndarray) -> dict[str, Any]:
        d = dist[sel]
        q = {lab: num(np.quantile(d, x), 1) if len(d) else None
             for lab, x in (("min", 0.0), ("p10", 0.1), ("median", 0.5), ("p90", 0.9), ("max", 1.0))}
        return {"n": int(sel.sum()), **q, "n_beyond_6km": int((sel & far).sum()),
                "minutes_share_beyond_6km": round(float(wt[sel & far].sum() / wt[sel].sum()), 6)
                if wt[sel].sum() > 0 else None}

    sid = sec["section_id"].to_numpy(dtype=np.int64)
    order = sorted(np.flatnonzero(on_all).tolist(), key=lambda i: (-dist[i], int(sid[i])))
    farthest = [{"section_id": int(sid[i]), "street_name": str(names[i]), "site_ref": str(sm[i]),
                 "dist_m": num(dist[i], 1), "km": float(sec["km"].iat[i]), "ff_min": round(float(ff[i]), 4),
                 "n_origins": int(sec["n_origins"].iat[i]),
                 "window": (f"{_hhmm(int(sec['bd_on'].iat[i]))}-{_hhmm(int(sec['bd_off'].iat[i]))}"
                            if int(sec["bd_on"].iat[i]) >= 0 else "none")}
                for i in order[:NZTA_FARTHEST_N]]
    mapping_dist = {"all": dist_q(on_all),
                    **{c: dist_q(on_all & (corr_of == c)) for c in sorted({str(x) for x in corr_of[on_all]})}}
    return {
        "source": "data/nzta (prep/fetch_nzta.py; NZTA Traffic Monitoring System, CC BY 4.0)",
        "attribution": NZTA_ATTRIBUTION,
        "rule": {"min_valid_days": NZTA_MIN_DAYS, "low_lane": NZTA_LOW_LANE, "level_band": list(NZTA_LEVEL_BAND),
                 "plateau": f"median of the quarter hours from t_max + {NZTA_PLATEAU_GAP} min to "
                            f"{_hhmm(NZTA_PLATEAU_END)}", "breakdown_delta": NZTA_BREAKDOWN_DELTA,
                 "saturated": f">= {NZTA_SAT_FRAC} q_max for >= {NZTA_SAT_MIN} min",
                 "recovery": (f"< {NZTA_RECOVER_FRAC} x plateau" + (
                     f" or > plateau + {NZTA_RECOVER_RISE:g} x (q_max - plateau)" if NZTA_RECOVER_RISE is not None
                     else "") + f" for {NZTA_RECOVER_BINS} quarter hours"),
                 "recover_rise": NZTA_RECOVER_RISE,
                 "no_recovery_min": NZTA_NO_RECOVERY_MIN,
                 "onset_latest": _hhmm(NZTA_ONSET_LATEST_MIN) if NZTA_ONSET_LATEST_MIN is not None else None,
                 "recovery_from": _hhmm(NZTA_RECOVERY_FROM_MIN) if NZTA_RECOVERY_FROM_MIN is not None else None,
                 "map_m": NZTA_MAP_M},
        "n_sites": int(len(sites)), "n_valid": int(sites["valid"].sum()),
        "n_breakdown": int(sites.loc[sites["valid"], "breakdown"].astype(bool).sum()),
        "sites": site_rows,
        "mapping": mapping,
        "mapping_dist_m": mapping_dist,
        "farthest_sections": farthest,
        "dist_m_by_section": {str(int(sid[i])): num(dist[i], 1) for i in np.flatnonzero(on_all)},
        "n_sections_nzta": int((sec["adt_source"] == "nzta").sum()),
        "minutes_share_nzta": round(float(wt[(sec["adt_source"] == "nzta").to_numpy()].sum() / wt.sum()), 6)
        if wt.sum() > 0 else math.nan,
        "minutes_share_mwy_nzta": round(float(wt[(sec["adt_source"] == "nzta").to_numpy()].sum() / wt[is_m].sum()), 6)
        if wt[is_m].sum() > 0 else math.nan,
        "mwy_tti_by_corridor": corr_tti,
        "rows": {k_: int(len(v)) for k_, v in nz.items()},
    }


# --------------------------------------------------------------------------- tables


def section_table(edges: pd.DataFrame, vals: pd.DataFrame, sections: list[list[int]],
                  starts: list[list[Node]], osec: dict[int, list[int]], weights: dict[int, float],
                  r: np.ndarray, cfg: Config) -> pd.DataFrame:
    """road_sections rows without cap_vph (set once k is known)."""
    p = cfg.prep
    users: dict[int, list[int]] = {}
    for oid in sorted(osec):
        for s in osec[oid]:
            users.setdefault(s, []).append(oid)
    w_total = sum(weights[o] for o in sorted(weights))
    r_am = 0.0
    for m in range(*AM_VOLUME_WINDOW):
        r_am += float(r[m])
    agents_cars = float(cfg.engine.agents_represented) * float(p.road_commuter_car_share)
    mins = edges["minutes"].to_numpy(dtype=float)
    dist = edges["distance_m"].to_numpy(dtype=float)
    geoms = edges["geometry"].to_numpy()
    src = vals["adt_source"].to_numpy()
    rows = []
    for sid, es in enumerate(sections):
        e0 = es[0]
        ff = 0.0
        km = 0.0
        for e in es:
            ff += mins[e]
            km += dist[e]
        srcs = {src[e] for e in es}
        source = "count" if "count" in srcs else ("propagated" if "propagated" in srcs else "default")
        twoway = float(vals["adt_twoway"].iat[e0])
        ratio = float(vals["peak_ratio"].iat[e0])
        obs = round(p.road_inbound_share * ratio * twoway, 3)
        am_vol = round(obs * r_am / 60.0, 3)
        w_s = sum(weights[o] for o in users[sid])
        exp_c = round(agents_cars * w_s / w_total, 3)
        phi = min(1.0, exp_c / am_vol) if am_vol > 0 else 1.0
        wf = min(1.0, am_vol / exp_c) if exp_c > 0 else 1.0
        xm, ym = chain_midpoint([geoms[e] for e in es], starts[sid])
        frc, spd, name = int(edges["frc"].iat[e0]), int(edges["speed_limit"].iat[e0]), str(edges["street_name"].iat[e0])
        rows.append({
            "section_id": sid, "n_seg": len(es), "ff_min": ff, "km": round(km / 1000.0, 4),
            "frc": frc, "speed_limit": spd, "street_name": name, "adt_twoway": twoway,
            "adt_dir": float(vals["adt_dir"].iat[e0]), "adt_source": source, "peak_ratio": ratio,
            "cap_vph": math.nan, "obs_peak_vph": obs, "am_volume_veh": am_vol,
            "expected_commuter_veh": exp_c, "phi": round(phi, 6), "bg_peak_vph": round(obs * (1.0 - phi), 3),
            "w_factor": round(wf, 6), "n_origins": len(users[sid]),
            "x_mid": round(xm, 1), "y_mid": round(ym, 1),
            "mwy": int(is_motorway(frc, spd, name)), "bd_on": -1, "bd_off": -1,   # window set once k is known
        })
    return pd.DataFrame(rows, columns=list(SECTIONS_COLUMNS))


def floor_summary(frc: np.ndarray, adt_dir: np.ndarray, adt_cap: np.ndarray, floors: dict[int, float],
                  is_site: np.ndarray, k: float, wt: np.ndarray, pct: float) -> dict[str, Any]:
    """road_meta.json 'capacity_floor' [SPEC4 A3]: the floor per frc (ADT and k x ADT veh/h) and the
    sections whose capacity it raised (count, share of the origin-weighted pre-gate minutes wt);
    NZTA sections below the floor keep their measured capacity (counted separately)."""
    f = np.asarray(frc, dtype=np.int64)
    up = np.asarray(adt_cap, dtype=float) > np.asarray(adt_dir, dtype=float)
    raised = up & ~is_site
    tot = float(wt.sum())

    def share(sel: np.ndarray, den: float) -> float | None:
        return round(float(wt[sel].sum()) / den, 6) if den > 0 else None

    by = {}
    for c in sorted(floors):
        sel = f == c
        by[str(c)] = {"adt_floor": floors[c], "cap_floor_vph": round(k * floors[c], 3), "n_sections": int(sel.sum()),
                      "n_raised": int((sel & raised).sum()), "minutes_share_raised": share(sel & raised, tot),
                      "minutes_share_of_class_raised": share(sel & raised, float(wt[sel].sum())),
                      "n_nzta_below_floor": int((sel & up & is_site).sum())}
    return {"pct": pct, "rule": "cap_vph = k x max(adt_dir, adt_floor[frc]); adt_floor = the pct-th percentile of "
                                "adt_dir over the sections of the frc (unweighted); not on NZTA sections; flows "
                                "keep adt_dir",
            "by_frc": by, "n_raised": int(raised.sum()), "minutes_share_raised": share(raised, tot),
            "n_nzta_below_floor": int((up & is_site).sum())}


def trav_weights(osec: dict[int, list[int]], weights: dict[int, float], n_sections: int) -> np.ndarray:
    """Sum of the origin weights of the origins whose pre-gate route uses each section."""
    trav = np.zeros(n_sections)
    for o in sorted(osec):
        for s in osec[o]:
            trav[s] += weights[o]
    return trav


def motorway_summary(sec: pd.DataFrame, edges: pd.DataFrame, sections: list[list[int]], broken: np.ndarray,
                     rule: MwyRule, trav: np.ndarray, default_ratio: float) -> dict[str, Any]:
    """Motorway mainline sections, those that are motorway by name only (not frc 0), the frc-0 and
    motorway-named sections left out (ramps by name, low speed limits), the sections with numbered
    names, the usual-traffic breakdown windows and the share of motorway mainline minutes broken
    down at BREAKDOWN_PROBE_MIN (by free-flow minutes of the sections, and weighted by the origins
    using them)."""
    is_m = sec["mwy"].to_numpy(dtype=np.int64) == 1
    ff = sec["ff_min"].to_numpy(dtype=float)
    frc0 = sec[(sec["frc"] == 0) & ~is_m]
    is_r = np.array([is_ramp_name(n) for n in frc0["street_name"]], dtype=bool)
    ramp, slow = frc0.loc[is_r], frc0.loc[~is_r]
    named = np.array([is_motorway_name(n) for n in sec["street_name"]], dtype=bool)
    by_name = sec[is_m & (sec["frc"] != 0)]
    named_out = sec[named & ~is_m & (sec["frc"] != 0)]
    numbered = sec[np.array([bool(_NUMBERED_NAME_RE.match(str(n).upper().strip())) for n in sec["street_name"]],
                            dtype=bool)]
    ramp_e, names_e = edges["ramp"].to_numpy(), edges["street_name"].to_numpy()
    mixed = {f"{sid}": sorted({str(names_e[e]) for e in es if ramp_e[e]}) for sid, (es, m)
             in enumerate(zip(sections, is_m)) if m and bool(ramp_e[es].any())}
    win = sec[is_m & (sec["bd_on"] >= 0)]
    wt = trav * ff
    share = {}
    for mm in BREAKDOWN_PROBE_MIN:
        b = broken[:, mm] & is_m
        share[_hhmm(mm)] = {"network": round(float(ff[b].sum() / ff[is_m].sum()), 6) if is_m.any() else math.nan,
                            "weighted": round(float(wt[b].sum() / wt[is_m].sum()), 6) if is_m.any() else math.nan}

    def hm(v: pd.Series) -> list[str]:
        return [_hhmm(int(x)) for x in (v.min(), v.median(), v.max())] if len(v) else []

    return {
        "rule": {"mwy_breakdown": rule.on, "mwy_breakdown_vc": rule.breakdown_vc, "mwy_recover_vc": rule.recover_vc,
                 "mwy_capacity_drop": rule.capacity_drop, "mwy_jam_speed": rule.jam_speed,
                 "min_speed_kmh": MWY_MIN_SPEED_KMH,
                 "mainline": "frc 0 or a street name holding the word Motorway; not a ramp by name; "
                             "signed at least min_speed_kmh"},
        "n_sections": int(is_m.sum()), "km": round(float(sec.loc[is_m, "km"].sum()), 2),
        "ff_min": round(float(ff[is_m].sum()), 3),
        "minutes_share": round(float(wt[is_m].sum() / wt.sum()), 6) if wt.sum() > 0 else math.nan,
        "names": {str(n): int(c) for n, c in sec.loc[is_m, "street_name"].value_counts().sort_index().items()},
        "frc0_ramps_excluded": {str(n): int(c) for n, c in ramp["street_name"].value_counts().sort_index().items()},
        "frc0_slow_excluded": {f"{n} ({s} km/h)": int(c) for (n, s), c in
                               slow.groupby(["street_name", "speed_limit"]).size().sort_index().items()},
        "by_name_not_frc0": [
            {"section_id": int(r.section_id), "street_name": str(r.street_name), "frc": int(r.frc),
             "speed_limit": int(r.speed_limit), "km": float(r.km), "ff_min": round(float(r.ff_min), 4),
             "n_origins": int(r.n_origins),
             "window": f"{_hhmm(int(r.bd_on))}-{_hhmm(int(r.bd_off))}" if int(r.bd_on) >= 0 else "none"}
            for r in by_name.sort_values("section_id").itertuples()],
        "named_excluded_not_frc0": {f"{n} (frc {f}, {s} km/h)": int(c) for (n, f, s), c in
                                    named_out.groupby(["street_name", "frc", "speed_limit"]).size()
                                    .sort_index().items()},
        "numbered_names": {f"{n} (frc {f}, {s} km/h, mwy {m})": int(c) for (n, f, s, m), c in
                           numbered.groupby(["street_name", "frc", "speed_limit", "mwy"]).size()
                           .sort_index().items()},
        "sections_with_ramp_edges": mixed,
        "n_peak_ratio_from_count": int((sec.loc[is_m, "peak_ratio"] != round(clip_peak_ratio(default_ratio), 6)).sum()),
        "n_with_window": int(len(win)),
        "bd_on_min_median_max": hm(win["bd_on"]), "bd_off_min_median_max": hm(win["bd_off"]),
        "broken_share": share,
    }


def section_keys(edges: pd.DataFrame, vals: pd.DataFrame) -> list[Hashable]:
    """Per-edge section key: frc, speed limit, normalised name, count values, observed/default."""
    return [(int(f), int(s), c, float(a), float(d), float(pr), src == "default")
            for f, s, c, a, d, pr, src in zip(edges["frc"], edges["speed_limit"], edges["core"],
                                               vals["adt_twoway"], vals["adt_dir"], vals["peak_ratio"],
                                               vals["adt_source"])]


# --------------------------------------------------------------------------- outputs


def _write_text(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False, lineterminator="\n")


def _file_info(path: Path) -> dict[str, Any]:
    st = path.stat()
    try:
        rel = Path(os.path.relpath(path, ROOT)).as_posix()
    except ValueError:
        rel = path.as_posix()
    return {"path": rel, "bytes": int(st.st_size),
            "modified_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def _q(s: pd.Series | np.ndarray, qs: Sequence[float] = (0.0, 0.1, 0.5, 0.9, 1.0), fmt: str = "{:.3f}") -> str:
    a = np.asarray(s, dtype=float)
    return " | ".join(fmt.format(float(np.quantile(a, q))) for q in qs) if len(a) else " | ".join("-" for _ in qs)


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def nzta_report_lines(nzi: dict[str, Any]) -> list[str]:
    """'NZTA motorway counts' section of road_report.md from road_meta.json 'nzta' (nzta_summary)."""
    ru = nzi["rule"]
    L = ["## NZTA motorway counts", "",
         f"Source: {nzi['source']}. {nzi['attribution']}", "",
         f"- Valid 2024 weekday (May, Aug, Nov; counted CBD-bound direction): no lane outage (a core lane "
         f"missing or below {ru['low_lane']:g} x its median day, full day or 05:00-11:00), all 24 quarter hours "
         f"05:00-10:45, the site-month's median day within {ru['level_band'][0]:g}-{ru['level_band'][1]:g} x the "
         "site's 2025-26 median (doubled counts), no holiday. A site is used when it counts CBD-bound through "
         f"lanes (not a link, ramp or 'mixed' site) on at least {ru['min_valid_days']} valid days.",
         f"- Per site: q(t) = mean weekday 15-min flow (veh/h, all lanes and classes); q_max its maximum at "
         f"t_max; plateau = {ru['plateau']}; delta = 1 - plateau / q_max. Breakdown when delta >= "
         f"{ru['breakdown_delta']:g} (onset: first quarter hour after t_max at or below q_max (1 - delta / 2), "
         f"cap_drop = delta) or when saturated ({ru['saturated']}; onset: start of that run; cap_drop = "
         "max(delta, road.mwy_capacity_drop), as the drop cannot be measured at the bottleneck itself). "
         f"Recovery: first quarter hour from which q stays {ru['recovery']} (each of them; below: demand "
         "fell; above: the downstream bottleneck cleared, the queue drained and throughput rose back towards "
         f"its pre-breakdown level); {_hhmm(ru['no_recovery_min'])} when that never happens by 10:45.",
         "- Amendments to the SPEC3 rule (the literal rule's window is in the last column): a drop or a "
         f"saturated run counts only when it starts by {ru['onset_latest']} (a plateau of two hours or more "
         "before 09:30; after a later maximum the counts cannot tell a capacity drop from the end of the "
         f"demand peak), and recovery is looked for from {ru['recovery_from']} on (a dip inside the plateau "
         "is still congested flow)."
         if ru["onset_latest"] is not None or ru["recovery_from"] is not None else
         "- The literal SPEC3 rule (no amendments).",
         "- Capacity C = q_max x scale, observed flow = q(t) x scale (throughput as counted), scale = median "
         "weekday 2025-26 (no outage, no holiday) / median valid 2024 day of the same site. obs_peak_vph = the "
         "peak-hour mean of the scaled q; the site's time profile r(m) = scaled q / obs_peak_vph at the "
         "quarter-hour centres, linear between them, the default profile scaled to match before 05:07 and "
         "after 10:52.", "",
         "| site | corridor | valid days | q_max (veh/h) at | plateau | delta | saturated | window | cap_drop | "
         "scale 2024 -> 2025-26 | capacity | obs_peak_vph | sections | k x ADT cap of those (min / median / max) | "
         "literal SPEC3 window |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for d in nzi["sites"]:
        if not d["valid"]:
            continue
        lit = d.get("literal_rule", {})
        lw = (f"{_hhmm(lit['bd_on'])}-{_hhmm(lit['bd_off'])}" if lit.get("breakdown") else "none") if lit else "-"
        sat = f"{d['saturated_min']} min from {d['saturated_from']}" if d["saturated_from"] else "no"
        win = d["window"] + (" (no recovery by 10:45)" if d["recovered_by_1045"] is False else "")
        oc = d["old_cap_vph_min_median_max"]
        L.append(f"| {d['site_ref']} | {d['corridor']} | {d['valid_2024']} | {d['q_max']:.0f} at {d['t_max']} | "
                 f"{d['q_plateau']:.0f} | {d['delta']:.3f} | {sat} | {win} | {d['cap_drop']:.3f} | "
                 f"{d['median_2024']:.0f} -> {d['median_2025_26']:.0f} = {d['scale']:.4f} ({d['scale_source']}) | "
                 f"{d['cap_vph']:.0f} | {d['obs_peak_vph']:.0f} | {d['n_sections']} | "
                 + (" / ".join(f"{x:.0f}" for x in oc) if oc else "-") + f" | {lw} |")
    rose = [d for d in nzi["sites"] if d["valid"] and d.get("recovery_by") in ("rise", "mixed")]
    rise_line = ""
    if ru.get("recover_rise") is not None:
        rise_line = (f"Windows that end because the flow rose back above plateau + {ru['recover_rise']:g} x (q_max - "
                     "plateau): " + ("; ".join(f"{d['site_ref']} {d['window']} (by a fall in flow alone "
                                               f"{d['window_fall_only']})" for d in rose) or "none") + ".")
    L += [""] + ([rise_line, ""] if rise_line else []) + ["Sites not used: " + "; ".join(
        f"{d['site_ref']} ({d['corridor']}): {d['reason']}" for d in nzi["sites"] if not d["valid"]) + ".",
          "Doubled-count site-months left out: " + ("; ".join(
              f"{d['site_ref']} {d['level_flagged']}" for d in nzi["sites"] if d["level_flagged"]) or "none") + ".", "",
          "Motorway sections mapped to the nearest used site of their corridor "
          + ("at any distance" if ru["map_m"] is None else f"within {ru['map_m'] / 1000:g} km")
          + f" (midpoint to site): {nzi['n_sections_nzta']} sections, {nzi['minutes_share_mwy_nzta']:.1%} of the "
          "origin-weighted motorway minutes. Motorway sections of a route without a used site keep k x max(ADT, "
          "the road-class floor), the default profile, the usual-traffic window and road.mwy_capacity_drop.", "",
          "| street name | corridor | sections | mapped | free-flow min (mapped) | sites | farthest (m) |",
          "|---|---|---|---|---|---|---|"]
    for n, v in nzi["mapping"].items():
        L.append(f"| {n} | {v['corridor'] or 'none (no site)'} | {v['sections']} | {v['mapped']} | "
                 f"{v['ff_min']:.2f} ({v['ff_min_mapped']:.2f}) | "
                 + (", ".join(f"{s} {c}" for s, c in v["sites"].items()) or "-") + " | "
                 + (f"{v['max_dist_m']:.0f}" if v["max_dist_m"] is not None else "-") + " |")
    md = nzi.get("mapping_dist_m", {})
    if md:
        L += ["", "Distance from a mapped section's midpoint to its site (m), and the mapped sections beyond the "
              "6 km limit of SPEC3 (count, and their share of the corridor's origin-weighted mapped motorway "
              "minutes):", "",
              "| corridor | sections | min | p10 | median | p90 | max | beyond 6 km | minutes share beyond 6 km |",
              "|---|---|---|---|---|---|---|---|---|"]
        for c, v in md.items():
            L.append(f"| {c} | {v['n']} | " + " | ".join(f"{v[x]:.0f}" if v[x] is not None else "-"
                                                        for x in ("min", "p10", "median", "p90", "max"))
                     + f" | {v['n_beyond_6km']} | "
                     + (f"{v['minutes_share_beyond_6km']:.1%}" if v["minutes_share_beyond_6km"] is not None else "-")
                     + " |")
        L += ["", "Farthest mapped sections:", "",
              "| section | street name | site | distance (m) | km | free-flow min | origins | window |",
              "|---|---|---|---|---|---|---|---|"]
        for d in nzi.get("farthest_sections", []):
            L.append(f"| {d['section_id']} | {d['street_name']} | {d['site_ref']} | {d['dist_m']:.0f} | {d['km']:g} | "
                     f"{d['ff_min']:.2f} | {d['n_origins']} | {d['window']} |")
    ct = nzi["mwy_tti_by_corridor"]
    if ct:
        labs = list(next(iter(ct.values())))
        L += ["", "Motorway TTI by motorway corridor under usual traffic (time on that corridor's motorway "
              "sections over their free-flow time, origin-weighted, origins using them), by departure:", "",
              "| corridor | " + " | ".join(labs) + " |", "|---|" + "---|" * len(labs)]
        for c, v in ct.items():
            L.append(f"| {c} | " + " | ".join(f"{v[lab]:.3f}" for lab in labs) + " |")
    L.append("")
    return L


def no_site_motorway_text(sec: pd.DataFrame, floor_info: dict[str, Any], default_ratio: float) -> str:
    """road_report.md Assumptions: the motorway mainline sections without an NZTA site (mwy = 1, adt_source
    not 'nzta'), their capacity rule and usual-traffic windows (from bd_on, bd_off: 'break down together'
    only when those at k x ADT share one window). Those whose capacity the road-class floor raised [SPEC4
    A3] (adt_dir below floor_info by_frc adt_floor, as in capacity_adt) have a lower usual V/C, so their
    windows are listed apart. Returns '' when there are no such sections."""
    ns = sec[(sec["mwy"] == 1) & (sec["adt_source"] != "nzta")]
    if ns.empty:
        return ""
    ratio = (f"the default peak ratio {default_ratio}" if (ns["peak_ratio"] == default_ratio).all()
             else f"their count's peak ratio or the default {default_ratio}")
    fl = np.array([floor_info["by_frc"].get(str(int(c)), {}).get("adt_floor", -math.inf) for c in ns["frc"]],
                  dtype=float)
    up = ns["adt_dir"].to_numpy(dtype=float) < fl

    def windows(d: pd.DataFrame) -> list[tuple[str, int]]:
        cnt: dict[tuple[int, int], int] = {}
        for a, b in zip(d["bd_on"].astype(int), d["bd_off"].astype(int)):
            cnt[(a, b)] = cnt.get((a, b), 0) + 1
        return [("no window" if a < 0 else f"{_hhmm(a)}-{_hhmm(b)}", n) for (a, b), n in sorted(cnt.items())]

    parts = []
    plain, raised = ns[~up], ns[up]
    if len(plain):
        w = windows(plain)
        parts.append(f"the {len(plain)} at k x ADT break down together ({w[0][0]})" if len(w) == 1 and len(plain) > 1
                     else f"the {len(plain)} at k x ADT have the windows " + ", ".join(f"{s} ({n})" for s, n in w))
    if len(raised):
        dur = lambda d: (d["bd_off"] - d["bd_on"]).where(d["bd_on"] >= 0, 0)  # noqa: E731
        shorter = len(plain) > 0 and bool((dur(raised) < dur(plain).min()).all())
        parts.append(f"the {len(raised)} whose capacity the floor raised have a lower V/C and their own"
                     + (", shorter" if shorter else "") + " windows: "
                     + ", ".join(f"{s} ({n})" for s, n in windows(raised)))
    return (f"; the others (motorways without a site, {len(ns)} sections) keep {ratio} and capacity "
            "k x max(ADT, the road-class floor): " + "; ".join(parts))


def render_report(cfg: Config, sec: pd.DataFrame, osec: dict[int, list[int]], origins: pd.DataFrame,
                  meta: dict[str, Any], R: np.ndarray, tti_corr: dict[int, float],
                  corridors: pd.DataFrame) -> str:
    """Markdown road report: coverage, k, TTI, V/C, commuter shares, busiest sections, assumptions."""
    p, rd = cfg.prep, cfg.road
    w = dict(zip(origins["origin_id"].astype(int), origins["weight"].astype(float)))
    w_total = sum(w.values())
    # traversal minutes: section ff_min x origin weight of its users
    trav = np.zeros(len(sec))
    for oid, seq in osec.items():
        for s in seq:
            trav[s] += w[oid]
    trav_min = trav * sec["ff_min"].to_numpy(dtype=float)
    sec = sec.assign(trav_min=trav_min)
    L: list[str] = ["# Cordon-Lite road congestion inputs (prep.build_roads)", ""]
    m = meta
    L += ["## Summary", "",
          f"- Sections: {len(sec)} on the pre-gate parts of {len(osec)} origin paths "
          f"({int(sec['n_seg'].sum())} graph edges, {sec['km'].sum():.1f} km, "
          f"{sec['ff_min'].sum():.1f} free-flow minutes); {m['n_origin_section_rows']} origin-section rows, "
          f"{np.mean([len(s) for s in osec.values()]):.1f} sections per origin on average "
          f"(max {max(len(s) for s in osec.values())}).",
          f"- The rebuilt prep paths reproduce `data/origins.csv` exactly (gate_id, corridor_id, "
          f"free-flow minutes); per-origin sum of section ff_min minus fftt_to_gate_min: max abs "
          f"{m['checks']['max_abs_ffsum_minus_fftt_to_gate']:.2e} min.",
          f"- Capacity factor k = {m['k']:.6f} (cap_vph = k x max(adt_dir, the ADT floor of the section's frc); "
          "see 'Capacity floor by road class'), bisected in "
          f"{list(p.road_cap_k_bounds)} so that the origin-weighted travel time index of departures "
          f"{_hhmm(p.road_tti_window[0])}-{_hhmm(p.road_tti_window[1] - 1)} under usual traffic"
          + (" on the non-motorway part of each trip (time on its sections other than motorway mainline "
             "over their free-flow time; prep.road_tti_exclude_mwy)" if m["tti_match"] == "non_motorway" else "")
          + f" is {p.road_tti_target} (achieved {m['tti_achieved']:.4f}).",
          f"- Usual-traffic V/C is 2 x {p.road_inbound_share} x peak_ratio x r(m) / k on every section "
          f"except the {m['nzta']['n_sections_nzta']} motorway sections from an NZTA count site (there it is "
          f"the site's counted flow over its capacity, at most 1) and the {m['capacity_floor']['n_raised']} "
          "sections whose capacity the road-class floor raised (lower there); with the default peak ratio "
          f"{p.road_peak_ratio_default} that is {2 * p.road_inbound_share * p.road_peak_ratio_default / m['k']:.2f} "
          "x r(m).",
          ""]
    cf = m["capacity_floor"]
    L += ["## Capacity floor by road class", "",
          f"cap_vph = k x max(adt_dir, adt_floor[frc]), adt_floor = the {cf['pct']:g}th percentile of adt_dir "
          "over all sections of that frc (unweighted, before k; prep.road_adt_floor_pct), so very small or "
          "stale counts do not give near-zero capacity. The floor is inside the k calibration; it sets capacity "
          "only (observed and background flows stay from the counts); NZTA motorway sections keep their "
          f"measured capacity. {cf['n_raised']} sections raised, "
          + (f"{cf['minutes_share_raised']:.2%}" if cf["minutes_share_raised"] is not None else "-")
          + " of origin-weighted pre-gate minutes.", "",
          "| frc | sections | ADT floor (adt_dir) | capacity floor (veh/h) | sections raised | share of the class's "
          "minutes | share of all minutes | NZTA sections below the floor |",
          "|---|---|---|---|---|---|---|---|"]
    for c, v in cf["by_frc"].items():
        L.append(f"| {c} | {v['n_sections']} | {v['adt_floor']:.1f} | {v['cap_floor_vph']:.1f} | {v['n_raised']} | "
                 + (f"{v['minutes_share_of_class_raised']:.2%}" if v["minutes_share_of_class_raised"] is not None
                    else "-") + f" | {v['minutes_share_raised']:.3%} | {v['n_nzta_below_floor']} |")
    L.append("")
    mw = m["motorway"]
    tt, t0 = mw["tti"], mw["tti_without_breakdown"]
    L += ["## Travel time index under usual traffic", "",
          "Probe car on each origin's pre-gate route (adds no load), one departure per minute, "
          "origin-weighted mean of (time to the gate) / (free-flow time to the gate). Motorway and "
          "non-motorway: the same over the trip's motorway mainline part (time on those sections over "
          "their free-flow time; origins whose route has such a part) and over the rest. "
          + ("With" if mw["rule"]["mwy_breakdown"] else "Without") + " the motorway breakdown rule "
          "(road.mwy_breakdown); the last two columns show the plain BPR curve at the same k.", "",
          "| departures | all | motorway | non-motorway | all, no breakdown | motorway, no breakdown |",
          "|---|---|---|---|---|---|"]
    for lab, a, b in list(TTI_HOURS) + [TTI_PEAK]:
        L.append(f"| {_hhmm(a)}-{_hhmm(b - 1)} | {tt['all'][lab]:.3f} | {tt['motorway'][lab]:.3f} | "
                 f"{tt['non_motorway'][lab]:.3f} | {t0['all'][lab]:.3f} | {t0['motorway'][lab]:.3f} |")
    L.append(f"| {_hhmm(TTI_PROBE_MIN)} only | {tt['all']['07:30']:.3f} | {tt['motorway']['07:30']:.3f} | "
             f"{tt['non_motorway']['07:30']:.3f} | {t0['all']['07:30']:.3f} | {t0['motorway']['07:30']:.3f} |")
    L += ["", "By corridor (departures in the calibration window):", "",
          "| corridor | name | origins | TTI |", "|---|---|---|---|"]
    for c in corridors.itertuples():
        n = int((origins["corridor_id"] == c.corridor_id).sum())
        L.append(f"| {c.corridor_id} | {c.name} | {n} | {tti_corr.get(int(c.corridor_id), math.nan):.3f} |")
    L += ["", "## Count matching", "",
          f"- Count points: {m['counts']['n_points']} in `{p.adt_geojson}`, {m['counts']['n_adt_positive']} "
          f"with adt > 0 (local {m['counts']['n_local']}, SH carriageway {m['counts']['n_sh_cway']}, "
          f"SH ramp {m['counts']['n_sh_ramp']}, SH without direction {m['counts']['n_sh_other']}, not used; "
          f"{m['counts']['n_sh_ramp_bus']} SH ramp records of bus-only ramps or busways (named so, or under "
          f"{BUS_RAMP_MAX_CAR_PCT:g}% cars) are not used).",
          f"- Matched to a same-name graph edge within {p.adt_match_m:g} m and used: {m['counts']['n_matched']} "
          f"(local {m['counts']['matched_local']}, SH carriageway {m['counts']['matched_sh_cway']}, "
          f"SH ramp {m['counts']['matched_sh_ramp']}). Not used: {m['counts']['n_stale']} matched AT counts "
          f"below {STALE_ADT_RATIO:g} of a more recent count of the same street within {p.adt_propagate_m:g} m "
          "(stale or misplaced counts). Graph edges holding a count: "
          f"{m['edges']['count']}; propagated within {p.adt_propagate_m:g} m: {m['edges']['propagated']}; "
          f"default: {m['edges']['default']} (of {m['edges']['total']} graph edges).",
          "- Sections take adt_source 'count' when one of their edges holds a count, 'propagated' "
          "when their values come from a count on the same street, else 'default' (median two-way "
          "ADT of count edges with the same frc and speed band, else frc); motorway sections of a "
          "corridor with NZTA count sites take 'nzta' (their capacity, flow and time profile come from the "
          "nearest site of their corridor; see 'NZTA motorway counts' below).", ""]
    L += ["Coverage by frc (share of sections | share of origin-weighted pre-gate free-flow minutes):", "",
          "| frc | sections | " + " | ".join(ADT_SOURCES) + " | minutes share of all | "
          + " | ".join(ADT_SOURCES) + " |",
          "|---|---|" + "---|" * (2 * len(ADT_SOURCES) + 1)]
    tm_all = sec["trav_min"].sum()
    for f, g in sec.groupby("frc"):
        tm = g["trav_min"].sum()
        sh = [(g["adt_source"] == s).mean() for s in ADT_SOURCES]
        shm = [g.loc[g["adt_source"] == s, "trav_min"].sum() / tm for s in ADT_SOURCES]
        L.append(f"| {f} | {len(g)} | " + " | ".join(f"{x:.1%}" for x in sh) +
                 f" | {tm / tm_all:.1%} | " + " | ".join(f"{x:.1%}" for x in shm) + " |")
    sh = [(sec["adt_source"] == s).mean() for s in ADT_SOURCES]
    shm = [sec.loc[sec["adt_source"] == s, "trav_min"].sum() / tm_all for s in ADT_SOURCES]
    L.append(f"| all | {len(sec)} | " + " | ".join(f"{x:.1%}" for x in sh) + " | 100.0% | " +
             " | ".join(f"{x:.1%}" for x in shm) + " |")
    pk = m["peak_ratio"]
    L += ["", f"- AM peak ratio from a count with an AM peak hour (06:00-09:45): {pk['sections_from_count']} "
          f"sections ({pk['minutes_share_from_count']:.1%} of origin-weighted pre-gate minutes); the others "
          f"use {p.road_peak_ratio_default} (not used on 'nzta' sections). Peak ratio over sections "
          "(min | p10 | median | p90 | max): "
          f"{_q(sec['peak_ratio'])}.", ""]
    L += ["## V/C under usual traffic", "",
          "V/C = obs_peak_vph x r(m) / cap_vph (background plus usual commuters, what the counts say). "
          "Median over sections and origin-weighted mean over traversal minutes.", "",
          "| frc | sections | median 07:30 | median 08:15 | weighted 07:30 | weighted 08:15 |",
          "|---|---|---|---|---|---|"]
    for f, g in sec.groupby("frc"):
        vc = {mm: g["obs_peak_vph"] * R[g.index.to_numpy(), mm] / g["cap_vph"] for mm in VC_PROBE_MIN}
        wt = g["trav_min"]
        L.append(f"| {f} | {len(g)} | " + " | ".join(f"{vc[mm].median():.2f}" for mm in VC_PROBE_MIN) + " | " +
                 " | ".join(f"{(vc[mm] * wt).sum() / wt.sum():.2f}" for mm in VC_PROBE_MIN) + " |")
    L += ["", f"Speed factor f = 1 / (1 + {rd.bpr_alpha:g} (V/C)^{rd.bpr_beta}), at least {rd.speed_floor:g}; "
          f"time on a section = ff_min / f.", ""]
    ru = mw["rule"]
    nzi = m["nzta"]
    keep = 1 - ru["mwy_capacity_drop"]
    L += ["## Motorway flow breakdown", "",
          f"- Motorway mainline sections (mwy = 1): frc 0 or a street name holding 'Motorway', not a ramp "
          f"by name, signed at least {ru['min_speed_kmh']} km/h: {mw['n_sections']} sections, "
          f"{mw['km']:.1f} km, {mw['ff_min']:.1f} free-flow minutes, {mw['minutes_share']:.1%} of "
          "origin-weighted pre-gate minutes (sections by name: "
          + ", ".join(f"'{n}' {c}" for n, c in mw["names"].items()) + ").",
          "- Motorway by name, not frc 0 (TomTom gives some mainline links a lower frc, e.g. the Auckland "
          "Harbour Bridge stretch of the Northern Motorway; these sections had mwy = 0 under the frc-0-only "
          "rule before 2026-10-08): "
          + ("; ".join(f"section {d['section_id']} '{d['street_name']}' frc {d['frc']}, {d['speed_limit']} km/h, "
                       f"{d['km']:g} km, {d['ff_min']:.2f} min, {d['n_origins']} origins, window {d['window']}"
                       for d in mw["by_name_not_frc0"]) or "none")
          + (f" (in all {sum(d['ff_min'] for d in mw['by_name_not_frc0']):.2f} free-flow minutes and "
             f"{sum(d['n_origins'] for d in mw['by_name_not_frc0'])} origin passes)" if mw["by_name_not_frc0"] else "")
          + ". Sections with a motorway name left out (ramps or slower than "
          f"{ru['min_speed_kmh']} km/h, not frc 0): "
          + (", ".join(f"'{n}' {c}" for n, c in mw["named_excluded_not_frc0"].items()) or "none") + ".",
          "- Numbered names (TomTom names a few state-highway links by number; they count as motorway "
          "by frc only): " + (", ".join(f"'{n}' {c}" for n, c in mw["numbered_names"].items()) or "none")
          + "." + ("" if any(n.upper().startswith("STATE HIGHWAY") for n in mw["numbered_names"])
                   else " No section is named 'State Highway N'."),
          "- frc-0 ramps left out (name starts with or holds Entry, Exit, 'Entry And Exit', Ramp, On-Ramp, "
          "Off-Ramp; sections): " + (", ".join(f"'{n}' {c}" for n, c in mw["frc0_ramps_excluded"].items())
                                     or "none") + ".",
          f"- frc-0 sections signed below {ru['min_speed_kmh']} km/h left out (signalised streets, no "
          "motorway): " + (", ".join(f"'{n}' {c}" for n, c in mw["frc0_slow_excluded"].items()) or "none")
          + ". Motorway sections that also hold a ramp edge (same normalised name and count values, so "
          "joined to the mainline; the section takes its first edge's name): "
          + ("; ".join(f"section {s}: {', '.join(n)}" for s, n in mw["sections_with_ramp_edges"].items())
             or "none") + ".",
          f"- Breakdown window: a motorway section of a corridor with NZTA count sites (adt_source 'nzta', "
          f"{nzi['n_sections_nzta']} sections) takes its site's window (the counts' breakdown onset and recovery, "
          "see 'NZTA motorway counts'); every other motorway section the window under usual traffic (V/C = "
          "obs_peak_vph x r(m) / "
          f"cap_vph): from the first minute with V/C >= {ru['mwy_breakdown_vc']:g} until the first later "
          f"minute with V/C < {ru['mwy_recover_vc']:g} (hysteresis). {mw['n_with_window']} of "
          f"{mw['n_sections']} sections have one; start (min | median | max) "
          f"{' | '.join(mw['bd_on_min_median_max']) or '-'}, end {' | '.join(mw['bd_off_min_median_max']) or '-'}.",
          f"- Engine rule (road.mwy_breakdown = {str(ru['mwy_breakdown']).lower()}): a motorway section is "
          f"broken down at minute m inside its window or when today's V/C reaches "
          f"{ru['mwy_breakdown_vc']:g}; it then runs at f = 1 / (1 + {rd.bpr_alpha:g} (V/C / (1 - cap_drop))^4) "
          f"(capacity cap_drop lower: the site's measured drop on 'nzta' sections, {ru['mwy_capacity_drop']:.0%} "
          f"(road.mwy_capacity_drop, x / {keep:g}) elsewhere) and at most {ru['mwy_jam_speed']:g} of free-flow "
          f"speed (stop-and-go flow), at least {rd.speed_floor:g}. The charge cannot shorten the usual "
          "window: commuters are a few percent of motorway flow.", "",
          "Share of motorway mainline minutes broken down under usual traffic (by the sections' free-flow "
          "minutes | weighted by the origins using them):", "",
          "| clock | " + " | ".join(mw["broken_share"]) + " |", "|---|" + "---|" * len(mw["broken_share"]),
          "| network | " + " | ".join(f"{v['network']:.0%}" for v in mw["broken_share"].values()) + " |",
          "| weighted | " + " | ".join(f"{v['weighted']:.0%}" for v in mw["broken_share"].values()) + " |", ""]
    L += nzta_report_lines(nzi)
    low = sec["cap_vph"] < LOW_CAP_VPH
    low_names = ", ".join(sorted(set(sec.loc[low, "street_name"].astype(str)))[:5])
    L += ["## Commuter share of the counted volume", "",
          f"expected_commuter_veh = {cfg.engine.agents_represented:g} x {p.road_commuter_car_share:g} x "
          "(origin weight using the section) / (all origin weight); phi = min(1, expected / observed "
          "06:00-10:00 volume); bg_peak_vph = obs_peak_vph x (1 - phi); w_factor = min(1, observed / "
          "expected).", "",
          "| quantity | min | p10 | median | p90 | max |", "|---|---|---|---|---|---|",
          f"| phi | {_q(sec['phi'])} |", f"| w_factor | {_q(sec['w_factor'])} |",
          f"| expected_commuter_veh | {_q(sec['expected_commuter_veh'], fmt='{:.0f}')} |",
          f"| am_volume_veh | {_q(sec['am_volume_veh'], fmt='{:.0f}')} |", "",
          f"- Sections where the commuters reach the whole counted volume (phi = 1, w_factor < 1): "
          f"{int((sec['phi'] >= 1).sum())} ({(sec['phi'] >= 1).mean():.1%} of sections, "
          f"{sec.loc[sec['phi'] >= 1, 'trav_min'].sum() / tm_all:.1%} of origin-weighted pre-gate minutes).",
          f"- Origin-weighted mean phi over pre-gate minutes: {(sec['phi'] * sec['trav_min']).sum() / tm_all:.3f}.",
          f"- Data check: {int(low.sum())} sections have cap_vph below {LOW_CAP_VPH:g} veh/h (very small "
          f"counts, e.g. {low_names or 'none'}); {sec.loc[low, 'trav_min'].sum() / tm_all:.2%} of "
          "origin-weighted pre-gate minutes.", ""]
    L += ["## Sections used by the most origins", "",
          "| section | street | frc | speed | ff_min | origins | adt_twoway | source | peak_ratio | phi | w_factor | V/C 08:15 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    top = sec.sort_values(["n_origins", "section_id"], ascending=[False, True], kind="mergesort").head(10)
    for t in top.itertuples():
        vc = t.obs_peak_vph * R[t.Index, VC_PROBE_MIN[1]] / t.cap_vph
        L.append(f"| {t.section_id} | {t.street_name or '(unnamed)'} | {t.frc} | {t.speed_limit} | {t.ff_min:.2f} | "
                 f"{t.n_origins} | {t.adt_twoway:.0f} | {t.adt_source} | {t.peak_ratio:.3f} | {t.phi:.3f} | "
                 f"{t.w_factor:.3f} | {vc:.2f} |")
    L += ["", "## Assumptions", "",
          "- [SPEC] Routes are the prep shortest free-flow paths on the undirected graph (no rerouting); "
          "only the pre-gate part is congested; the gate-to-destination leg stays free flow.",
          f"- [DATA] Two-way ADT from the AT/NZTA count points (`{p.adt_geojson}`): 7-day averages of mixed "
          "vintage (motorway counts mostly 2016); AT counts are two-way totals unless the record's name "
          "carries a direction (EASTBOUND, EAST BOUND, ...); state-highway records count one carriageway or ramp.",
          f"- [A] A count matches the nearest graph edge with the same normalised street name within "
          f"{p.adt_match_m:g} m (state-highway carriageway records by route to the motorway names, ramp records "
          "to ramp or unnamed edges); several counts on one edge keep the most recent; SH records without a "
          "direction suffix and SH ramp records of bus-only ramps or busways (named so, or under "
          f"{BUS_RAMP_MAX_CAR_PCT:g}% cars) are not used; an AT count below "
          f"{STALE_ADT_RATIO:g} of a more recent count of the same street within {p.adt_propagate_m:g} m "
          "(straight line) is not used.",
          f"- [A] A count holds along the same street up to {p.adt_propagate_m:g} m through the network "
          "(motorway, frc 1 and ramp edges need the identical TomTom name; SH carriageway counts only on edges "
          f"within {SH_BEARING_MAX_DEG:g} deg of their bearing); nearest source wins. Other edges take the "
          f"median two-way ADT of count edges with the same frc and speed band (at least {DEFAULT_MIN_EDGES} "
          "edges), else frc.",
          "- [SPEC, A] Direction: a count of one carriageway or direction (SH -I/-D, SH ramp, AT count whose "
          "name carries a direction) is directional (adt_dir = adt, two-way equivalent 2 x adt); any other AT "
          "count is a two-way total (adt_dir = adt / 2), also on TomTom edges without a reversed twin, which "
          "are mostly carriageways of divided roads rather than one-way streets.",
          f"- [A] Inbound share of the two-way AM peak-hour flow {p.road_inbound_share}; AM peak ratio "
          f"peaktraffic / adt where the count's peak hour starts 06:00-09:45, else {p.road_peak_ratio_default} "
          f"[DATA]; clipped to {list(PEAK_RATIO_CLIP)}.",
          f"- [A] Time profile r(m): 15-min bins from {_hhmm(p.road_profile_start_min)} {list(p.road_profile)} "
          "(peak timing from the counts [DATA], shape assumed), linear between bin centres, ramp to "
          f"{PROFILE_LOW} x the first value at 05:00.",
          f"- [A] Capacity = k x directional ADT (SSC2026 rule) with k calibrated to the TomTom Traffic Index "
          f"[DATA]: Auckland 2025 morning rush-hour congestion level 71.4% => TTI {p.road_tti_target} "
          "(https://www.tomtom.com/traffic-index/auckland-traffic/). The ADT in the capacity is at least the "
          f"{cf['pct']:g}th percentile of the directional ADT of the section's road class (frc), so a very "
          "small or stale count does not give a near-zero capacity; the flows stay from the counts.",
          f"- [A] BPR alpha {rd.bpr_alpha:g}, beta {rd.bpr_beta}, speed floor {rd.speed_floor:g} (SSC2026); "
          f"commuter flow counts the cars that entered in the last {rd.flow_window_min} min.",
          f"- [A, L] Motorway flow breakdown (road.mwy_*): breakdown at V/C {ru['mwy_breakdown_vc']:g}, recovery "
          f"below {ru['mwy_recover_vc']:g} under usual traffic, {ru['mwy_capacity_drop']:.0%} capacity drop "
          f"(Cassidy and Bertini 1999; 3-18% in the literature), at most {ru['mwy_jam_speed']:g} of free-flow "
          "speed (bottleneck speeds of 25-35 km/h at SH20 in 2005, Brown et al.). The window is the usual "
          "traffic's (the counts), so a charge that removes commuter cars cannot shorten it; today's "
          "commuters can only start a breakdown earlier (V/C threshold). A motorway mainline section is "
          "frc 0 or carries a motorway name (TomTom's frc is lower on a few mainline links, such as the "
          "Harbour Bridge). "
          + (f"Motorway sections of a corridor with NZTA count sites ({nzi['minutes_share_mwy_nzta']:.0%} of the "
             "origin-weighted motorway minutes) take capacity, flow, time profile, window and capacity drop "
             "from the 2024 quarter-hourly counts (scaled to 2025-26 volumes) of the nearest site of their "
             "corridor" + (", at any distance" if nzi["rule"]["map_m"] is None else
                           f" within {nzi['rule']['map_m'] / 1000:g} km")
             + no_site_motorway_text(sec, m["capacity_floor"], p.road_peak_ratio_default) + ". ")
          + ("k is matched on the non-motorway part of the trips, so the TomTom index sets the arterial "
             "level and the motorway level follows from the breakdown rule." if m["tti_match"] == "non_motorway"
             else "k is matched on whole trips."),
          f"- [A] Commuters are netted out of the counts with car share {p.road_commuter_car_share:g} of "
          f"{cfg.engine.agents_represented:g} represented vehicles; where all-or-nothing routing puts more "
          "commuter cars on a section than counted, their weight w_factor is reduced instead.",
          "- [A] Routing is undirected: many motorway traversals follow the opposite carriageway's geometry; "
          "congestion uses the inbound flow at the location, so the values do not depend on which "
          "carriageway is drawn.", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------- main


def run_build_roads(cfg: Config, out_dir: Path | None = None) -> dict[str, Any]:
    """Run the road prep and write the six outputs; returns tables and summary numbers."""
    p, rd = cfg.prep, cfg.road
    data_dir = cfg.resolve_path(cfg.run.data_dir)
    out_dir = Path(out_dir) if out_dir is not None else data_dir
    ref_path = data_dir / "origins.csv"
    ref = pd.read_csv(ref_path)
    roads = load_roads_shp(cfg)
    cordon, cordon_path = load_cordon_any(cfg)
    prep = reproduce_prep(cfg, roads, cordon)
    check_origins(prep["origins_frame"], ref)
    G, dest, origins, paths = prep["G"], prep["dest"], prep["origins"], prep["paths"]

    edges = edge_table(G, roads, cfg)
    eid = edge_index(edges)
    routes_n = pregate_routes(G, dest, origins, cordon, p.gate_rule, eid)
    routes = {o: [e for e, _ in rt] for o, rt in routes_n.items()}
    counts, cstats = load_counts(cfg)
    point_match, edge_match = match_counts(edges, counts, p.adt_match_m, stale_m=p.adt_propagate_m)
    vals, dinfo = edge_values(edges, counts, edge_match, cfg)

    sections, osec = build_sections(routes, section_keys(edges, vals))
    start_of = {e: n for rt in routes_n.values() for e, n in rt}
    starts = [[start_of[e] for e in es] for es in sections]
    weights = dict(zip(ref["origin_id"].astype(int), ref["weight"].astype(float)))
    r = road_profile(p.road_profile, p.road_profile_start_min)
    sec = section_table(edges, vals, sections, starts, osec, weights, r, cfg)

    # check: per origin, sections add up to the unrounded free-flow time to the gate
    ff = sec["ff_min"].to_numpy(dtype=float)
    oids = sorted(osec)
    rmat = route_matrix(osec, oids)
    ffsum = route_ffsum(rmat, ff)
    fftt = paths.set_index("origin_id").loc[oids, "fftt_to_gate_min"].to_numpy(dtype=float)
    fftt_csv = ref.set_index("origin_id").loc[oids, "fftt_to_gate_min"].to_numpy(dtype=float)
    d_unr = float(np.abs(ffsum - fftt).max())
    d_csv = float(np.abs(ffsum - fftt_csv).max())
    if d_unr > 1e-3 or d_csv > 1e-3:
        raise ValueError(f"section free-flow minutes do not add up to fftt_to_gate_min "
                         f"(max diff {d_unr:.3g} unrounded, {d_csv:.3g} against origins.csv)")

    # NZTA motorway counts [SPEC3]: site analysis, then the motorway sections of a corridor with sites
    nz = load_nzta(data_dir)
    sites, site_q, site_prof = nzta_sites(nz, cfg)
    profiles: dict[int, np.ndarray] = {DEFAULT_PROFILE_ID: r, **site_prof}
    site_map = map_sections_to_sites(sec, sites)
    pre_nzta = sec[["obs_peak_vph", "adt_dir", "bg_peak_vph", "phi", "w_factor"]].copy()
    sec = apply_nzta(sec, site_map, sites, profiles, cfg)
    is_site = (sec["adt_source"] == "nzta").to_numpy()
    R = section_profiles(sec["profile_id"].to_numpy(dtype=np.int64), profiles)

    w_arr = np.array([weights[o] for o in oids])
    obs = sec["obs_peak_vph"].to_numpy(dtype=float)
    adt_dir = sec["adt_dir"].to_numpy(dtype=float)
    mwy = sec["mwy"].to_numpy(dtype=np.int64)
    rule = MwyRule.from_config(rd)
    cap_fixed = np.where(is_site, sec["cap_vph"].to_numpy(dtype=float), math.nan)
    win_fixed = (is_site, sec["bd_on"].to_numpy(dtype=np.int64), sec["bd_off"].to_numpy(dtype=np.int64))
    keep = 1 - sec["cap_drop"].to_numpy(dtype=float)
    # capacity floor by road class [SPEC4 A3]: cap_vph = k x max(adt_dir, floor[frc]) on every section
    # but the NZTA ones, inside the k calibration; the flows keep adt_dir
    frc_arr = sec["frc"].to_numpy(dtype=np.int64)
    floors = adt_floors(frc_arr, adt_dir, float(p.road_adt_floor_pct))
    adt_cap = capacity_adt(frc_arr, adt_dir, floors)
    pre_nzta["adt_cap"] = adt_cap
    k, tti_k, hist = calibrate_k(rmat, ff, w_arr, obs, adt_cap, R, rd.bpr_alpha, rd.speed_floor,
                                 p.road_tti_target, tuple(p.road_tti_window), tuple(p.road_cap_k_bounds),
                                 mwy=mwy, rule=rule, exclude_mwy=bool(p.road_tti_exclude_mwy),
                                 cap_fixed=cap_fixed, win_fixed=win_fixed, keep=keep)
    sec["cap_vph"] = np.where(is_site, cap_fixed, np.round(k * adt_cap, 3))
    cap = sec["cap_vph"].to_numpy(dtype=float)
    broken, bd_on, bd_off = usual_breakdown(obs, cap, R, mwy, rule, win_fixed)
    sec["bd_on"], sec["bd_off"] = bd_on, bd_off
    F = usual_speed_table(obs, cap, R, rd.bpr_alpha, rd.speed_floor, broken, rule, keep)
    deps = list(range(TTI_HOURS[0][1], TTI_HOURS[-1][2]))
    is_m = mwy == 1
    ff_m = route_ffsum(rmat, np.where(is_m, ff, 0.0))
    el, el_m = probe_elapsed(rmat, ff, F, deps, is_m)
    tti_hour = {lab: round(weighted_tti(el[:, a - deps[0]:b - deps[0]], ffsum, w_arr), 6) for lab, a, b in TTI_HOURS}
    tti_0730 = round(weighted_tti(el[:, [TTI_PROBE_MIN - deps[0]]], ffsum, w_arr), 6)
    win = slice(p.road_tti_window[0] - deps[0], p.road_tti_window[1] - deps[0])
    corr = ref.set_index("origin_id").loc[oids, "corridor_id"].to_numpy(dtype=int)
    tti_corr = {int(c): weighted_tti(el[corr == c, win], ffsum[corr == c], w_arr[corr == c])
                for c in sorted(set(corr.tolist()))}
    # by road class (motorway mainline / other / all), with the breakdown rule and without it
    F0 = usual_speed_table(obs, cap, R, rd.bpr_alpha, rd.speed_floor)
    el0, el0_m = probe_elapsed(rmat, ff, F0, deps, is_m)
    periods = [(lab, a, b) for lab, a, b in TTI_HOURS] + [TTI_PEAK, ("07:30", TTI_PROBE_MIN, TTI_PROBE_MIN + 1)]

    def by_class(e: np.ndarray, e_m: np.ndarray) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {"motorway": {}, "non_motorway": {}, "all": {}}
        for lab, a, b in periods:
            cut = slice(a - deps[0], b - deps[0])
            for cl, v in class_tti(e[:, cut], e_m[:, cut], ffsum, ff_m, w_arr).items():
                out[cl][lab] = round(v, 6)
        return out

    trav_w = trav_weights(osec, weights, len(sec))
    floor_info = floor_summary(frc_arr, adt_dir, adt_cap, floors, is_site, k, trav_w * ff,
                               float(p.road_adt_floor_pct))
    mwy_info = motorway_summary(sec, edges, sections, broken, rule, trav_w, p.road_peak_ratio_default)
    mwy_info["tti"] = by_class(el, el_m)
    mwy_info["tti_without_breakdown"] = by_class(el0, el0_m)
    # NZTA: sites, mapping, motorway TTI by motorway corridor (usual traffic, with the rule)
    corr_lab = np.array([MWY_NAME_CORRIDOR.get(str(n)) or "other" if m == 1 else "" for n, m in
                         zip(sec["street_name"], mwy)], dtype=object)
    corr_tti: dict[str, dict[str, float]] = {}
    for lab_c in [c for c in ("SH1_north", "SH1_south", "SH16", "SH20", "other") if (corr_lab == c).any()]:
        cm = corr_lab == lab_c
        ffc = route_ffsum(rmat, np.where(cm, ff, 0.0))
        _e, e_c = probe_elapsed(rmat, ff, F, deps, cm)
        ok = ffc > 1e-9
        corr_tti[lab_c] = {lab: round(weighted_tti(e_c[ok, a - deps[0]:b - deps[0]], ffc[ok], w_arr[ok]), 6)
                           for lab, a, b in periods}
    nzta_info = nzta_summary(sites, sec, site_map, pre_nzta, k, trav_w, corr_tti, nz)

    # tables
    os_rows = [(o, i, s) for o in oids for i, s in enumerate(osec[o])]
    origin_sections = pd.DataFrame(os_rows, columns=list(ORIGIN_SECTIONS_COLUMNS))
    seg_ids = edges["segment_id"].to_numpy()
    ss_rows = [(sid, i, seg_ids[e]) for sid, es in enumerate(sections) for i, e in enumerate(es)]
    section_segments = pd.DataFrame(ss_rows, columns=list(SECTION_SEGMENTS_COLUMNS))

    # meta
    on_route = sorted({e for es in sections for e in es})
    src_e = vals["adt_source"].to_numpy()
    trav = np.zeros(len(sec))
    for o in oids:
        for s in osec[o]:
            trav[s] += weights[o]
    trav_min = trav * ff
    from_count = (~sec["adt_source"].isin(["default", "nzta"])).to_numpy() & np.array(
        [bool(vals["count_peak"].iat[es[0]]) for es in sections])
    used = point_match[~point_match["stale"].astype(bool)]
    mk = counts["kind"].to_numpy()[used["ci"].to_numpy(dtype=int)] if len(used) else np.array([])
    meta: dict[str, Any] = {
        "created_by": "prep.build_roads",
        "k": k, "k_bounds": list(p.road_cap_k_bounds), "k_iterations": K_ITERATIONS,
        "road_adt_floor_pct": p.road_adt_floor_pct,
        "tti_target": p.road_tti_target, "tti_achieved": round(tti_k, 6), "tti_window": list(p.road_tti_window),
        "tti_match": "non_motorway" if p.road_tti_exclude_mwy else "all",
        "tti_by_hour": tti_hour, "tti_0730": tti_0730,
        "tti_by_corridor": {str(c): round(v, 6) for c, v in tti_corr.items()},
        "bpr_alpha": rd.bpr_alpha, "bpr_beta": rd.bpr_beta, "speed_floor": rd.speed_floor,
        "flow_window_min": rd.flow_window_min,
        "road_inbound_share": p.road_inbound_share, "road_peak_ratio_default": p.road_peak_ratio_default,
        "peak_ratio_clip": list(PEAK_RATIO_CLIP), "road_commuter_car_share": p.road_commuter_car_share,
        "agents_represented": cfg.engine.agents_represented,
        "adt_match_m": p.adt_match_m, "adt_propagate_m": p.adt_propagate_m,
        "road_profile_start_min": p.road_profile_start_min, "road_profile": list(p.road_profile),
        "n_sections": len(sec), "n_origins": len(oids), "n_origin_section_rows": len(origin_sections),
        "n_section_segments": len(section_segments),
        "sections_by_source": {s: int((sec["adt_source"] == s).sum()) for s in ADT_SOURCES},
        "pregate_edges_by_source": {s: int(sum(src_e[e] == s for e in on_route)) for s in EDGE_ADT_SOURCES},
        "edges": {"total": len(edges), **{s: int((src_e == s).sum()) for s in EDGE_ADT_SOURCES}},
        "counts": {**cstats, "n_matched": int(len(used)), "n_stale": int(len(point_match) - len(used)),
                   **{f"matched_{kd}": int((mk == kd).sum()) for kd in ("local", "sh_cway", "sh_ramp")}},
        "defaults_adt_twoway": dinfo,
        "peak_ratio": {"sections_from_count": int(from_count.sum()),
                       "minutes_share_from_count": round(float(trav_min[from_count].sum() / trav_min.sum()), 6)},
        "capacity_floor": floor_info,
        "motorway": mwy_info,
        "nzta": nzta_info,
        "profiles": {"default": DEFAULT_PROFILE_ID, "n": len(profiles),
                     "site_of": {str(int(t.profile_id)): str(t.site_ref) for t in sites.itertuples()
                                 if int(t.profile_id) > 0}},
        "checks": {"origins_reproduced": True,
                   "max_abs_ffsum_minus_fftt_to_gate": d_unr,
                   "max_abs_ffsum_minus_origins_csv": d_csv},
        "cordon_source": _file_info(cordon_path)["path"],
        "inputs": {
            "roads_shp": _file_info(cfg.resolve_path(p.roads_shp)),
            "roads_dbf": _file_info(cfg.resolve_path(p.roads_shp).with_suffix(".dbf")),
            "adt_geojson": _file_info(cfg.resolve_path(p.adt_geojson)),
            "cordon": _file_info(cordon_path),
            "origins_csv": _file_info(ref_path),
            **{f"nzta_{f.split('.')[0]}": _file_info(data_dir / NZTA_SUBDIR / f) for f in NZTA_FILES},
        },
        "k_probes": [[round(a, 9), round(b, 6)] for a, b in hist],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(out_dir / "road_sections.csv", sec[list(SECTIONS_COLUMNS)])
    _write_csv(out_dir / "origin_sections.csv", origin_sections)
    _write_csv(out_dir / "section_segments.csv", section_segments)
    _write_text(out_dir / "road_profile.csv",
                ",".join(PROFILE_COLUMNS) + "\n" + "".join(f"{pid},{m},{x:.6f}\n" for pid in sorted(profiles)
                                                         for m, x in enumerate(profiles[pid])))
    _write_text(out_dir / "road_meta.json", json.dumps(meta, indent=2) + "\n")
    _write_text(out_dir / "road_report.md",
                render_report(cfg, sec, osec, ref, meta, R, tti_corr, prep["corridors"]) + "\n")
    return {"sections": sec, "origin_sections": origin_sections, "section_segments": section_segments,
            "profile": r, "profiles": profiles, "sites": sites, "site_q": site_q, "site_map": site_map,
            "meta": meta, "edges": edges, "values": vals, "osec": osec, "floors": floors, "adt_cap": adt_cap}


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="Cordon-Lite road congestion inputs (sections, counts, k)")
    ap.add_argument("--config", default=None, help="path to config.toml")
    ap.add_argument("--out-dir", default=None, help="output folder (default: run.data_dir)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    out = Path(args.out_dir) if args.out_dir else None
    res = run_build_roads(cfg, out)
    m = res["meta"]
    print(f"sections {m['n_sections']}, origin-section rows {m['n_origin_section_rows']}, "
          f"segments {m['n_section_segments']}")
    print("sections by adt_source:", m["sections_by_source"])
    print(f"k {m['k']:.6f}, TTI {m['tti_achieved']:.4f} (target {m['tti_target']}, {m['tti_match']}), "
          f"by hour {m['tti_by_hour']}, 07:30 {m['tti_0730']}")
    mw = m["motorway"]
    print(f"motorway sections {mw['n_sections']} ({mw['n_with_window']} with a breakdown window, start "
          f"{mw['bd_on_min_median_max']}, end {mw['bd_off_min_median_max']}); TTI by class {mw['tti']}")
    nzi = m["nzta"]
    print(f"NZTA sites {nzi['n_valid']} used of {nzi['n_sites']} ({nzi['n_breakdown']} with breakdown); "
          f"{nzi['n_sections_nzta']} motorway sections from a site ({nzi['minutes_share_mwy_nzta']:.1%} of "
          "motorway minutes); windows " + ", ".join(f"{d['site_ref']} {d['window']}" for d in nzi["sites"]
                                                     if d["valid"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
