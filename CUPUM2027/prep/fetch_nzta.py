"""NZTA motorway traffic counts on the Auckland CBD approaches (run once; needs internet).

Owner: prep builder. Outputs into cordon_lite/data/nzta/ (described in data/nzta/README.md, which
this script writes).

    python -m prep.fetch_nzta [--out data/nzta] [--cache DIR] [--offline]

Source: New Zealand Transport Agency (NZTA Waka Kotahi) Traffic Monitoring System (TMS), NZTA Open
Data portal, licensed CC BY 4.0 (ATTRIBUTION). Only the 36 motorway count sites in SITES are kept:
the through lanes of SH1 on both CBD approaches (Harbour Bridge classifier included), SH16
eastbound, SH20 northbound, the two Waterview SH20 -> SH16 links and the CBD exit ramps of the
Central Motorway Junction. Exactly two downloads are made, nothing else:

1. DAILY counts, ArcGIS feature service TMS_Telemetry_Sites layer 0 (DAILY_URL). One query per site
   and calendar quarter of local dates DAILY_FIRST .. DAILY_LAST (a window is split in halves when
   the 2000-record page limit is reached), outFields startDate, classWeight, laneNumber,
   flowDirection, trafficCount, returnDistinctValues=true: since January 2026 the table holds most
   records up to ~40 times and the server-side DISTINCT drops the copies before they are sent.
   Responses are gzip-encoded. startDate is a UTC epoch in ms: 12:00 UTC of the previous day
   before 2024, 00:00 UTC of the day since, so local date = (UTC + 12 h).date() under both
   conventions (other times of day are counted and reported). Weekend days are dropped after the
   download (the service cannot filter by day of week). If two distinct records remain for the same
   site, date, direction, lane and class, the larger count is kept (n_conflicts in the summary).

2. QUARTER-HOURLY counts Feb 2022 - Jan 2025, ArcGIS item QH_ITEM: one 1.7 GB zip with one CSV per
   month. The zip is never downloaded: its central directory is read with a suffix Range request on
   the tail, then only the members QH_MEMBERS (May, Aug, Nov 2024, ~165 MB compressed) are fetched
   with Range requests (resumed from the last byte after a dropped connection), inflated on the fly
   (zlib raw deflate), filtered line by line to SITES and checked against the CRC-32 and size in
   the zip directory. Columns START_DATE, SITE_ALIAS, REGION_NAME, SITE_REFERENCE, CLASS_WEIGHT,
   SITE_DESCRIPTION, LANE_NUMBER, FLOW_DIRECTION, TRAFFIC_COUNT; fields are located by the header
   (fields left of SITE_DESCRIPTION from the left, the others from the right, so a comma inside a
   description cannot shift them). START_DATE is the local (NZ) start of the quarter hour
   (QH_LOCAL_TIME; checked on every run by check_qh_clock: the overnight trough of the summed
   weekday profile must fall between 01:00 and 05:00). Quarter hours with a zero count are absent
   from the source, and counts of x.5 vehicles are normal.

SiteRef: the 4th character is 1 = through lanes in the increasing direction, 2 = decreasing,
3/5 = on-ramp, 4/6 = off-ramp. flowDirection of through lanes is 1 = increasing (SH1 southbound,
SH16 westbound, SH20 northbound), 2 = decreasing; ramps and links carry the ramp codes 3..6, which
for off ramps is not the 4th SiteRef character (01N40430 is coded 6, 01N60427 4), so the code of a
ramp's counted direction is taken from the data (listed_codes). Every flow direction found for a
site is kept. The Harbour Bridge classifier's moveable barrier moves lanes between the directions
during the day, so a direction total is always the sum over all its lanes.

Outputs (LF line endings, sorted; a rerun on the same downloaded data writes identical files):
    tms_sites.csv              one row per site (SITES_COLUMNS), sorted by corridor and site_ref
    tms_daily_weekday.csv      site_ref, local_date, flow_direction, lane, class, count:
                               Mon-Fri DAILY_FIRST .. DAILY_LAST, one row per lane and class
    tms_15min_am_2024.csv      site_ref, local_date, time, flow_direction, lane, class, count:
                               Mon-Fri of May, Aug, Nov 2024, quarter hours starting 05:00 .. 10:45
    tms_15min_daily_2024.csv   site_ref, local_date, flow_direction, lane, class, count, n_qh:
                               full-day totals of the same quarter-hourly rows (Mon-Fri, all 96
                               quarter hours), for day validity checks and peak-hour shares
    README.md                  sources, licence and attribution, filters, row counts, coverage

--cache DIR keeps the downloaded pieces (daily responses per site and quarter, the site-filtered
lines of each quarter-hourly member, the zip directory): a rerun with the same DIR reads them
instead of downloading, and --offline forbids any network access (fails if a piece is missing).

Public API:
    flow_code(site_ref, direction) -> int                  # through lanes: 1 or 2
    listed_codes(*tables) -> dict[str, int]                # code of each site's counted direction
    local_date_from_ms(ms) -> dt.date
    Http(offline=False)                      .post_json, .range_tail, .range_chunks, .bytes
    quarter_windows(first, last) -> list[tuple[dt.date, dt.date]]
    daily_where(ref, a, b) -> str
    fetch_daily(http, refs, cache=None) -> tuple[list[tuple], dict]
    zip_directory(http, url, cache=None) -> tuple[int, dict[str, ZipEntry]]
    member_lines(http, url, entry) -> Iterator[bytes]
    QhLayout(header)                         .site(line), .parse(line)
    fetch_quarter_hourly(http, refs, cache=None) -> tuple[list[tuple], dict]
    check_qh_clock(qh_rows) -> int
    coverage(daily, am, codes) -> list[dict]
    partial_class_days(rows) -> int
    level_flags(qh, cov, codes, lo=0.67, hi=1.5) -> list[tuple[str, str, float, float]]
    outage_months(daily, min_share=0.5) -> list[tuple[str, int, int]]
    write_outputs(out_dir, daily, qh, stats) -> dict
    run_fetch(out_dir=None, cache=None, offline=False) -> dict
    main(argv=None) -> int
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import socket
import ssl
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from http.client import HTTPException
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "nzta"

DAILY_URL = ("https://services.arcgis.com/CXBb7LAjgIIdcsPt/arcgis/rest/services/"
             "TMS_Telemetry_Sites/FeatureServer/0")
DAILY_FIELDS = "startDate,classWeight,laneNumber,flowDirection,trafficCount"
DAILY_FIRST = dt.date(2025, 10, 1)
DAILY_LAST = dt.date(2026, 9, 30)
PAGE_LIMIT = 2000                       # maxRecordCount of the daily service

QH_ITEM = "39cdaa422dbd45c4b41e0e59b49e79e2"
QH_URL = f"https://www.arcgis.com/sharing/rest/content/items/{QH_ITEM}/data"
QH_MEMBERS = ("tms_2024_05.csv", "tms_2024_08.csv", "tms_2024_11.csv")
QH_LOCAL_TIME = True                    # START_DATE is NZ local time (see check_qh_clock)
AM_FIRST_MIN = 5 * 60                   # first quarter hour kept starts 05:00
AM_END_MIN = 11 * 60                    # last quarter hour kept ends 11:00

USER_AGENT = "cordon-lite-prep/1.0 (CUPUM2027 research; python urllib)"
ATTRIBUTION = ("Traffic counts sourced from the New Zealand Transport Agency (NZTA Waka Kotahi) "
               "Traffic Monitoring System via the NZTA Open Data portal, licensed for re-use under "
               "CC BY 4.0.")
UTC_TO_LOCAL_DATE = dt.timedelta(hours=12)

# Increasing-direction label per route (flowDirection 1); the other direction is flowDirection 2.
INC_DIRECTION = {"01N": "SB", "016": "WB", "020": "NB"}
# flowDirection of a ramp or link by the 4th SiteRef character, as found for every ramp and link
# in SITES with records (2025-26): on ramps 3 -> 3 and 5 -> 5, off ramps 4 -> 6 and 6 -> 4. Used
# only for the sites without any record.
RAMP_CODE = {"3": 3, "4": 6, "5": 5, "6": 4}

# site_ref, NZTA description, corridor, counted direction, kind, AM role towards the CBD, note,
# lat, lon (WGS84, from the NZTA TMS site catalogue). Curated 2026-10-08 from the Auckland
# motorway sites of the TMS catalogue: through lanes on the CBD approaches plus the CBD exit ramps.
SITES: tuple[tuple[str, str, str, str, str, str, str, float, float], ...] = (
    ("01N20440", "PANAMA RD - Telemetry Site 79 - NB", "SH1_south", "NB", "mainline", "CBD-bound",
     "Penrose/Panama Rd national telemetry site (gappy after the Sep 2022 handover)", -36.929173, 174.849607),
    ("01N20439", "SH1 Mt Wellington Hwy Interchange NB (S5)", "SH1_south", "NB", "mainline", "CBD-bound",
     "between the Mt Wellington Hwy ramps", -36.917958, 174.838139),
    ("01N20433", "SH1 Green Lane East Interchange NB (S3)", "SH1_south", "NB", "mainline", "CBD-bound",
     "Ellerslie/Greenlane", -36.888228, 174.795768),
    ("01N20431", "SH1 Gillies Ave On Ramp to Market Rd Off Ramp NB (S2)", "SH1_south", "NB", "mainline",
     "CBD-bound", "Newmarket viaduct (Market Rd-Gillies); best CBD approach site", -36.876031, 174.780755),
    ("01N20429", "SH1 Northwestern Off Ramp to Symonds/Wellesley/Port Off Ramp NB (S1)", "SH1_south", "NB",
     "mainline", "mixed", "inside the CMJ after the CBD exits; through traffic to the bridge",
     -36.864186, 174.766148),
    ("01N10417", "SH1 Tristram Ave Interchange SB (N7)", "SH1_north", "SB", "mainline", "CBD-bound",
     "Tristram Ave (upstream)", -36.77352, 174.743848),
    ("01N10419", "SH1 Northcote Rd Interchange SB (N6)", "SH1_north", "SB", "mainline", "CBD-bound",
     "Northcote", -36.78949, 174.75381),
    ("01N10420", "SH1 Esmonde Rd Interchange SB (N5)", "SH1_north", "SB", "mainline", "CBD-bound",
     "Esmonde", -36.800944, 174.761632),
    ("01N19424", "Auckland Harbour Bridge - Classifier Site No 1 - SB", "SH1_north", "SB", "mainline",
     "CBD-bound", "Harbour Bridge classifier; moveable barrier (5 SB lanes in the AM)", -36.825311, 174.749213),
    ("01N10425", "SH1 Shelly Beach Rd Off Ramp to Fanshawe St Off Ramp SB (N2)", "SH1_north", "SB",
     "mainline", "CBD-bound", "south end of the bridge (Shelly Beach-Fanshawe)", -36.838374, 174.741841),
    ("01620013", "SH16 Lincoln Rd Interchange EB", "SH16", "EB", "mainline", "CBD-bound",
     "Lincoln Rd (not in the 2022-25 quarter-hourly files since 2024)", -36.849478, 174.634246),
    ("01620011", "SH16 Te Atatu Sth On Ramp to Te Atatu Peninsula On Ramp EB", "SH16", "EB", "mainline",
     "CBD-bound", "Te Atatu", -36.858153, 174.65435),
    ("01620009", "SH16 Patiki Rd Off Ramp to Rosebank Rd On Ramp EB", "SH16", "EB", "mainline", "CBD-bound",
     "Causeway (Patiki-Rosebank)", -36.868444, 174.670627),
    ("01620008", "SH16 Great Nth Rd Interchange EB", "SH16", "EB", "mainline", "CBD-bound",
     "Great North Rd interchange (before the SH20 link merges)", -36.872228, 174.703778),
    ("01620006", "SH16 St Lukes Rd Interchange EB", "SH16", "EB", "mainline", "CBD-bound",
     "St Lukes/Western Springs (after the SH20 link)", -36.868637, 174.738161),
    ("01620002", "SH16 SH1 On Ramp to Wellesley St Off Ramp EB", "SH16", "EB", "mainline", "CBD-bound",
     "SH1 on ramp to Wellesley St off ramp (CBD end)", -36.857631, 174.767372),
    ("01659008", "SH16 Southwestern On Ramp EB (Link)", "SH20_to_SH16", "EB", "link", "CBD-bound",
     "Waterview link SH20 NB -> SH16 EB (CBD share of SH20)", -36.874549, 174.703477),
    ("01639008", "SH16 Southwestern On Ramp WB (Link)", "SH20_to_SH16", "WB", "link", "not CBD-bound",
     "Waterview link SH20 NB -> SH16 WB", -36.871958, 174.698667),
    ("02010015", "SH20 Neilson St On Ramp to Queenstown Rd Off Ramp NB", "SH20", "NB", "mainline",
     "partly CBD-bound", "Onehunga (Neilson-Queenstown)", -36.926281, 174.77685),
    ("02019015", "SH20 Queenstown Rd Off Ramp to Hillsborough Rd Off Ramp NB", "SH20", "NB", "mainline",
     "partly CBD-bound", "Queenstown-Hillsborough", -36.922075, 174.767885),
    ("02010017", "SH20 Hillsborough Rd On Ramp to Dominion Rd Off Ramp NB", "SH20", "NB", "mainline",
     "partly CBD-bound", "Hillsborough-Dominion", -36.914514, 174.748599),
    ("02010018", "SH20 Dominion Rd Interchange NB", "SH20", "NB", "mainline", "partly CBD-bound",
     "Dominion Rd (Mt Roskill)", -36.911382, 174.739473),
    ("02010020", "SH20 Maioro St Interchange NB", "SH20", "NB", "mainline", "partly CBD-bound",
     "Maioro St", -36.902083, 174.720396),
    ("02010021", "SH20 Waterview Tunnel NB", "SH20", "NB", "mainline", "partly CBD-bound",
     "Waterview Tunnel (splits to SH16 EB/WB)", -36.900364, 174.715719),
    ("01N40430", "SH1 Khyber Pass Off Ramp NB", "CBD_exit_SH1N", "NB", "ramp", "CBD exit",
     "Khyber Pass off ramp", -36.867614, 174.768154),
    ("01N45429", "SH1 Symonds St Off Ramp NB", "CBD_exit_SH1N", "NB", "ramp", "CBD exit",
     "Symonds St off ramp", -36.86294, 174.764086),
    ("01N47429", "SH1 Wellesley St Off Ramp NB", "CBD_exit_SH1N", "NB", "ramp", "CBD exit",
     "Wellesley St off ramp (catalogue gives the Symonds St coordinates)", -36.86294, 174.764086),
    ("01N46429", "SH1 Port Off Ramp NB (Link 01650002)", "CBD_exit_SH1N", "NB", "ramp", "CBD exit",
     "Port off ramp", -36.855843, 174.767618),
    ("01N40427", "SH1 Nelson St Off Ramp NB", "CBD_exit_SH1N", "NB", "ramp", "CBD exit",
     "Nelson St off ramp (non-continuous site)", -36.858474, 174.756121),
    ("01N60425", "SH1 Shelly Beach Rd Off Ramp SB", "CBD_exit_SH1S", "SB", "ramp", "CBD exit",
     "Shelly Beach Rd off ramp (non-continuous site)", -36.836901, 174.742095),
    ("01N60426", "SH1 Fanshawe St Off Ramp SB", "CBD_exit_SH1S", "SB", "ramp", "CBD exit",
     "Fanshawe St off ramp", -36.841675, 174.750592),
    ("01N60427", "SH1 Cook St Off Ramp SB", "CBD_exit_SH1S", "SB", "ramp", "CBD exit",
     "Cook St off ramp (non-continuous site)", -36.847992, 174.753937),
    ("01N69427", "SH1 Port / SH16 Off Ramp SB", "CBD_exit_SH1S", "SB", "ramp", "mixed",
     "Port/SH16 off ramp SB", -36.848029, 174.753859),
    ("01640002", "SH16 Wellesley St Off Ramp EB", "CBD_exit_SH16", "EB", "ramp", "CBD exit",
     "Wellesley St off ramp EB", -36.857622, 174.767371),
    ("01646004", "SH16 Northern / Nelson Off Ramp EB", "CBD_exit_SH16", "EB", "ramp", "mixed",
     "Northern/Nelson off ramp EB", -36.860543, 174.753616),
    ("01649004", "SH16 Newton Rd Off Ramp EB", "CBD_exit_SH16", "EB", "ramp", "CBD exit",
     "Newton Rd off ramp EB (non-continuous site)", -36.864726, 174.750828),
)
CORRIDOR_ORDER = ("SH1_north", "SH1_south", "SH16", "SH20", "SH20_to_SH16",
                  "CBD_exit_SH1N", "CBD_exit_SH1S", "CBD_exit_SH16")

SITES_COLUMNS: tuple[str, ...] = (
    "site_ref", "description", "corridor", "direction", "flow_direction", "kind", "cbd_bound",
    "cbd_role", "lanes", "lat", "lon", "x_nztm", "y_nztm", "note",
)
DAILY_COLUMNS: tuple[str, ...] = ("site_ref", "local_date", "flow_direction", "lane", "class", "count")
AM_COLUMNS: tuple[str, ...] = ("site_ref", "local_date", "time", "flow_direction", "lane", "class", "count")
QH_DAILY_COLUMNS: tuple[str, ...] = ("site_ref", "local_date", "flow_direction", "lane", "class",
                                     "count", "n_qh")

# A dropped connection, a timeout or a busy server is retried; anything else stops the run.
RETRYABLE = (urllib.error.URLError, HTTPException, ConnectionError, socket.timeout,
             TimeoutError, json.JSONDecodeError, zlib.error, EOFError, OSError)


# --------------------------------------------------------------------------- small helpers


def flow_code(site_ref: str, direction: str) -> int:
    """flowDirection code of a through-lane direction: 1 = increasing route position, 2 = decreasing."""
    return 1 if INC_DIRECTION[site_ref[:3]] == direction else 2


def listed_codes(*tables: Sequence[tuple]) -> dict[str, int]:
    """flowDirection code of each site's counted direction. Through lanes: flow_code. Ramps and
    links: the code with most rows in the given tables (rows start with site_ref, *, flow_direction),
    else RAMP_CODE[4th SiteRef character] for a site without any record."""
    n: dict[tuple[str, int], int] = defaultdict(int)
    for rows in tables:
        for r in rows:
            n[(r[0], r[2])] += 1
    out = {}
    for ref, _, _, dirn, kind, *_ in SITES:
        if kind == "mainline":
            out[ref] = flow_code(ref, dirn)
        else:
            seen = sorted(((c, fd) for (r, fd), c in n.items() if r == ref), reverse=True)
            out[ref] = seen[0][1] if seen else RAMP_CODE[ref[3]]
    return out


def local_date_from_ms(ms: float) -> dt.date:
    """Local (NZ) date of a daily startDate epoch (ms, UTC): (UTC + 12 h).date()."""
    return (dt.datetime(1970, 1, 1) + dt.timedelta(milliseconds=ms) + UTC_TO_LOCAL_DATE).date()


def utc_from_ms(ms: float) -> dt.datetime:
    """Naive UTC datetime of an epoch in ms."""
    return dt.datetime(1970, 1, 1) + dt.timedelta(milliseconds=ms)


def fmt_count(v: float) -> str:
    """Count with at most one decimal and no trailing '.0' (half vehicles occur in the source)."""
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def norm_class(value: str) -> str:
    """'Light'/'LIGHT' -> 'light', 'Heavy'/'HEAVY' -> 'heavy' (other labels lower-cased)."""
    return str(value).strip().strip('"').lower()


def ssl_context() -> ssl.SSLContext:
    """TLS context trusting the OS store (truststore) or certifi: NZTA's ArcGIS hub fails
    certificate checks against Python's bundled store on some machines."""
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        pass
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def write_csv(path: Path, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    """CSV with LF line endings and UTF-8, no index."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(columns)
        w.writerows(rows)


# --------------------------------------------------------------------------- HTTP


class ServerError(RuntimeError):
    """ArcGIS JSON error body ({"error": {...}})."""


class Http:
    """urllib with a trusted TLS context, retries with back-off and per-download byte counters.

    ``bytes[tag]`` counts bytes received on the wire (gzip-compressed for the daily queries, raw
    zip bytes for the Range reads), ``json_bytes[tag]`` the decompressed JSON, ``requests[tag]``
    the successful requests."""

    def __init__(self, offline: bool = False, retries: int = 6, timeout: float = 120.0) -> None:
        self.offline = offline
        self.retries = retries
        self.timeout = timeout
        self.ctx = ssl_context()
        self.bytes: dict[str, int] = defaultdict(int)
        self.json_bytes: dict[str, int] = defaultdict(int)
        self.requests: dict[str, int] = defaultdict(int)
        self.retried: dict[str, int] = defaultdict(int)

    def _open(self, req: urllib.request.Request) -> Any:
        if self.offline:
            raise RuntimeError(f"--offline: a download is needed ({req.full_url[:80]}); "
                               "rerun with the same --cache folder online")
        return urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx)

    def _backoff(self, tag: str, attempt: int, err: BaseException) -> None:
        if attempt + 1 >= self.retries:
            raise RuntimeError(f"{tag}: giving up after {self.retries} attempts: {err!r}") from err
        wait = min(60.0, 2.0 * 2 ** attempt)
        self.retried[tag] += 1
        print(f"  {tag}: {type(err).__name__}: {str(err)[:120]} - retry in {wait:.0f} s", flush=True)
        time.sleep(wait)

    def post_json(self, url: str, params: dict[str, str], tag: str) -> dict:
        """POST a form to an ArcGIS REST endpoint and return the JSON body (gzip accepted)."""
        body = urllib.parse.urlencode(params).encode()
        for attempt in range(self.retries):
            req = urllib.request.Request(url, data=body, headers={
                "User-Agent": USER_AGENT, "Accept-Encoding": "gzip",
                "Content-Type": "application/x-www-form-urlencoded"})
            try:
                with self._open(req) as r:
                    raw = r.read()
                    enc = (r.headers.get("Content-Encoding") or "").lower()
                self.bytes[tag] += len(raw)
                txt = gzip.decompress(raw) if enc == "gzip" else raw
                self.json_bytes[tag] += len(txt)
                j = json.loads(txt)
                if "error" in j:
                    code = int(j["error"].get("code") or 0)
                    if code in (429, 500, 502, 503, 504):
                        raise ConnectionError(f"server error {code}: {j['error'].get('message')}")
                    raise ServerError(f"{tag}: {j['error']}")
                self.requests[tag] += 1
                return j
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504):
                    raise
                self._backoff(tag, attempt, e)
            except RETRYABLE as e:
                self._backoff(tag, attempt, e)
        raise AssertionError("unreachable")

    def range_tail(self, url: str, n: int, tag: str) -> tuple[int, bytes]:
        """Last n bytes of a file (suffix Range request) and the total file size."""
        for attempt in range(self.retries):
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT, "Range": f"bytes=-{n}", "Accept-Encoding": "identity"})
            try:
                with self._open(req) as r:
                    if r.status != 206:
                        raise RuntimeError(f"{tag}: server ignored the Range header (HTTP {r.status})")
                    total = int(r.headers["Content-Range"].rsplit("/", 1)[1])
                    b = r.read()
                self.bytes[tag] += len(b)
                self.requests[tag] += 1
                return total, b
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504):
                    raise
                self._backoff(tag, attempt, e)
            except RETRYABLE as e:
                self._backoff(tag, attempt, e)
        raise AssertionError("unreachable")

    def range_chunks(self, url: str, start: int, end: int, tag: str,
                     chunk: int = 1 << 20) -> Iterator[bytes]:
        """Bytes start..end (inclusive) of a file in chunks; a dropped connection is resumed with
        a new Range request from the first byte not yet received."""
        pos, attempt = start, 0
        while pos <= end:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT, "Range": f"bytes={pos}-{end}", "Accept-Encoding": "identity"})
            try:
                with self._open(req) as r:
                    cr = r.headers.get("Content-Range") or ""
                    if r.status != 206 or not cr.startswith(f"bytes {pos}-"):
                        raise RuntimeError(f"{tag}: bad Range answer (HTTP {r.status}, {cr!r})")
                    self.requests[tag] += 1
                    while pos <= end:
                        b = r.read(min(chunk, end - pos + 1))
                        if not b:
                            raise ConnectionError(f"connection closed at byte {pos}")
                        pos += len(b)
                        self.bytes[tag] += len(b)
                        attempt = 0
                        yield b
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504):
                    raise
                self._backoff(tag, attempt, e)
                attempt += 1
            except RETRYABLE as e:
                self._backoff(tag, attempt, e)
                attempt += 1


# --------------------------------------------------------------------------- daily counts


def quarter_windows(first: dt.date, last: dt.date) -> list[tuple[dt.date, dt.date]]:
    """Calendar-quarter windows (first day, last day) covering first..last."""
    out, a = [], first
    while a <= last:
        q_end_month = ((a.month - 1) // 3) * 3 + 3
        nxt = dt.date(a.year + (q_end_month == 12), q_end_month % 12 + 1, 1)
        b = min(last, nxt - dt.timedelta(days=1))
        out.append((a, b))
        a = b + dt.timedelta(days=1)
    return out


def daily_where(ref: str, a: dt.date, b: dt.date) -> str:
    """WHERE clause for local dates a..b of one site. Local date D is stored as D 00:00 UTC (2024+)
    or (D - 1) 12:00 UTC (before 2024); [a - 1 12:00 UTC, b 12:00 UTC) holds both and adjacent
    windows never overlap."""
    lo = dt.datetime.combine(a, dt.time(12)) - dt.timedelta(days=1)
    hi = dt.datetime.combine(b, dt.time(12))
    return (f"SiteRef = '{ref}' AND startDate >= TIMESTAMP '{lo:%Y-%m-%d %H:%M:%S}' "
            f"AND startDate < TIMESTAMP '{hi:%Y-%m-%d %H:%M:%S}'")


def query_daily_window(http: Http, ref: str, a: dt.date, b: dt.date, stats: dict) -> list[dict]:
    """Distinct daily records of one site for local dates a..b; halves the window when a response
    reaches the page limit (or the server flags exceededTransferLimit)."""
    params = {"where": daily_where(ref, a, b), "outFields": DAILY_FIELDS,
              "returnDistinctValues": "true", "returnGeometry": "false",
              "orderByFields": "startDate,flowDirection,laneNumber,classWeight",
              "resultRecordCount": str(PAGE_LIMIT), "f": "json"}
    j = http.post_json(f"{DAILY_URL}/query", params, "daily")
    feats = [f["attributes"] for f in j.get("features", [])]
    if (j.get("exceededTransferLimit") or len(feats) >= PAGE_LIMIT) and a < b:
        stats["n_split"] += 1
        mid = a + (b - a) // 2
        return (query_daily_window(http, ref, a, mid, stats)
                + query_daily_window(http, ref, mid + dt.timedelta(days=1), b, stats))
    if j.get("exceededTransferLimit") or len(feats) >= PAGE_LIMIT:
        raise RuntimeError(f"daily {ref} {a}: more than {PAGE_LIMIT} records for one day")
    return feats


def fetch_daily(http: Http, refs: Sequence[str], cache: Path | None = None) -> tuple[list[tuple], dict]:
    """Weekday daily counts of the sites, one row (site_ref, local_date, flow_direction, lane,
    class, count) per lane and class, de-duplicated; plus fetch statistics."""
    stats: dict[str, Any] = defaultdict(int)
    utc_times: dict[str, int] = defaultdict(int)
    best: dict[tuple, float] = {}
    windows = quarter_windows(DAILY_FIRST, DAILY_LAST)
    for i, ref in enumerate(sorted(refs)):
        n_site = 0
        for a, b in windows:
            cfile = cache / "daily" / f"{ref}_{a:%Y%m%d}_{b:%Y%m%d}.json" if cache else None
            if cfile is not None and cfile.exists():
                feats = json.loads(cfile.read_text(encoding="utf-8"))
                stats["n_cached"] += 1
            else:
                feats = query_daily_window(http, ref, a, b, stats)
                if cfile is not None:
                    cfile.parent.mkdir(parents=True, exist_ok=True)
                    cfile.write_text(json.dumps(feats, separators=(",", ":")), encoding="utf-8")
            for f in feats:
                stats["n_records"] += 1
                ms, lane, fd, cnt = f.get("startDate"), f.get("laneNumber"), f.get("flowDirection"), f.get("trafficCount")
                if ms is None or lane is None or fd is None or cnt is None:
                    stats["n_null"] += 1
                    continue
                utc_times[f"{utc_from_ms(ms):%H:%M}"] += 1
                d = local_date_from_ms(ms)
                if not (a <= d <= b):
                    stats["n_outside"] += 1
                    continue
                if d.weekday() >= 5:
                    stats["n_weekend"] += 1
                    continue
                key = (ref, d.isoformat(), int(fd), int(lane), norm_class(f.get("classWeight")))
                if key in best:
                    stats["n_dupe"] += 1
                    if best[key] != float(cnt):
                        stats["n_conflicts"] += 1
                    best[key] = max(best[key], float(cnt))
                else:
                    best[key] = float(cnt)
                    n_site += 1
        print(f"  daily {i + 1:2d}/{len(refs)} {ref}: {n_site} weekday rows "
              f"({http.bytes['daily'] / 1e6:.2f} MB received so far)", flush=True)
    stats["utc_times"] = dict(sorted(utc_times.items()))
    rows = sorted((*k, v) for k, v in best.items())
    return rows, dict(stats)


# --------------------------------------------------------------------------- quarter-hourly zip


@dataclass(frozen=True)
class ZipEntry:
    """One member of the quarter-hourly zip (from its central directory)."""
    name: str
    method: int
    crc: int
    csize: int
    usize: int
    offset: int


def parse_central_directory(cd: bytes) -> dict[str, ZipEntry]:
    """Central-directory records (zip64 extra fields resolved)."""
    out: dict[str, ZipEntry] = {}
    p = 0
    while p < len(cd) and cd[p:p + 4] == b"PK\x01\x02":
        h = struct.unpack("<IHHHHHHIIIHHHHHII", cd[p:p + 46])
        method, crc, csize, usize = h[4], h[7], h[8], h[9]
        nl, el, cl, off = h[10], h[11], h[12], h[16]
        name = cd[p + 46:p + 46 + nl].decode("utf-8", "replace")
        extra = cd[p + 46 + nl:p + 46 + nl + el]
        q = 0
        while q + 4 <= len(extra):
            hid, hs = struct.unpack("<HH", extra[q:q + 4])
            body, k = extra[q + 4:q + 4 + hs], 0
            if hid == 1:                                   # zip64: only the saturated fields follow
                if usize == 0xFFFFFFFF:
                    usize = struct.unpack("<Q", body[k:k + 8])[0]; k += 8
                if csize == 0xFFFFFFFF:
                    csize = struct.unpack("<Q", body[k:k + 8])[0]; k += 8
                if off == 0xFFFFFFFF:
                    off = struct.unpack("<Q", body[k:k + 8])[0]; k += 8
            q += 4 + hs
        out[name] = ZipEntry(name, method, crc, csize, usize, off)
        p += 46 + nl + el + cl
    return out


def zip_directory(http: Http, url: str, cache: Path | None = None) -> tuple[int, dict[str, ZipEntry]]:
    """Total size and members of a remote zip, from the end-of-central-directory record and the
    central directory (read with Range requests on the tail of the file)."""
    cfile = cache / "qh" / "zip_directory.json" if cache else None
    if cfile is not None and cfile.exists():
        j = json.loads(cfile.read_text(encoding="utf-8"))
        return j["total"], {e["name"]: ZipEntry(**e) for e in j["entries"]}
    total, tail = http.range_tail(url, 70_000, "15min")
    i = tail.rfind(b"PK\x05\x06")
    if i < 0:
        raise RuntimeError("15min zip: end of central directory not found")
    _, _, _, _, n_tot, cd_size, cd_off, _ = struct.unpack("<IHHHHIIH", tail[i:i + 22])
    if cd_off == 0xFFFFFFFF or n_tot == 0xFFFF or cd_size == 0xFFFFFFFF:
        j = tail.rfind(b"PK\x06\x06")
        z = struct.unpack("<IQHHIIQQQQ", tail[j:j + 56])
        n_tot, cd_size, cd_off = z[7], z[8], z[9]
    tail_start = total - len(tail)
    if cd_off >= tail_start:
        cd = tail[cd_off - tail_start:cd_off - tail_start + cd_size]
    else:
        cd = b"".join(http.range_chunks(url, cd_off, cd_off + cd_size - 1, "15min"))
    entries = parse_central_directory(cd)
    if len(entries) != n_tot:
        raise RuntimeError(f"15min zip: {len(entries)} directory records, expected {n_tot}")
    if cfile is not None:
        cfile.parent.mkdir(parents=True, exist_ok=True)
        cfile.write_text(json.dumps({"total": total, "entries": [asdict(e) for e in entries.values()]},
                                    indent=1), encoding="utf-8")
    return total, entries


def member_lines(http: Http, url: str, entry: ZipEntry) -> Iterator[bytes]:
    """Lines (bytes, no line break) of one zip member, read with Range requests and inflated on
    the fly; the CRC-32 and the size are checked against the central directory at the end."""
    hdr = b"".join(http.range_chunks(url, entry.offset, entry.offset + 29, "15min"))
    sig, _, _, method, _, _, _, _, _, nl, el = struct.unpack("<IHHHHHIIIHH", hdr)
    if sig != 0x04034B50 or method not in (0, 8) or method != entry.method:
        raise RuntimeError(f"{entry.name}: unexpected local header (sig {sig:#x}, method {method})")
    start = entry.offset + 30 + nl + el
    d = zlib.decompressobj(-15) if method == 8 else None
    crc, n, rest = 0, 0, b""
    for chunk in http.range_chunks(url, start, start + entry.csize - 1, "15min"):
        out = d.decompress(chunk) if d is not None else chunk
        crc, n = zlib.crc32(out, crc), n + len(out)
        lines = (rest + out).split(b"\n")
        rest = lines.pop()
        yield from lines
    if d is not None:
        out = d.flush()
        crc, n = zlib.crc32(out, crc), n + len(out)
        lines = (rest + out).split(b"\n")
        rest = lines.pop()
        yield from lines
        if not d.eof:
            raise RuntimeError(f"{entry.name}: deflate stream not complete")
    if rest:
        yield rest
    if crc != entry.crc or n != entry.usize:
        raise RuntimeError(f"{entry.name}: CRC/size mismatch ({crc:#010x}/{n} vs "
                           f"{entry.crc:#010x}/{entry.usize})")


class QhLayout:
    """Field positions of a quarter-hourly CSV, from its header line. Fields left of
    SITE_DESCRIPTION are counted from the left, the others from the right."""

    NEED = ("START_DATE", "SITE_REFERENCE", "CLASS_WEIGHT", "LANE_NUMBER", "FLOW_DIRECTION",
            "TRAFFIC_COUNT")

    def __init__(self, header: bytes) -> None:
        cols = [c.strip().strip('"').upper() for c in header.decode("utf-8-sig").strip().split(",")]
        missing = [c for c in self.NEED if c not in cols]
        if missing:
            raise RuntimeError(f"quarter-hourly header lacks {missing}: {cols}")
        self.n = len(cols)
        self.desc = cols.index("SITE_DESCRIPTION") if "SITE_DESCRIPTION" in cols else self.n
        self.pos = {c: (cols.index(c) if cols.index(c) < self.desc else cols.index(c) - self.n)
                    for c in self.NEED}
        self.ref = self.pos["SITE_REFERENCE"]
        if not 0 <= self.ref < self.desc:
            raise RuntimeError("SITE_REFERENCE must come before SITE_DESCRIPTION")

    def site(self, line: bytes) -> bytes:
        """SITE_REFERENCE of a raw line (quotes stripped), cheap pre-filter."""
        parts = line.split(b",", self.ref + 1)
        return parts[self.ref].strip().strip(b'"') if len(parts) > self.ref else b""

    def parse(self, line: bytes) -> tuple[str, str, int, int, str, float]:
        """(site_ref, START_DATE, flow_direction, lane, class, count) of a raw line."""
        parts = [p.strip().strip('"') for p in line.decode("utf-8").rstrip("\r").split(",")]
        if len(parts) < self.n:
            raise ValueError(f"short line: {line[:120]!r}")
        g = {c: parts[i] for c, i in self.pos.items()}
        return (g["SITE_REFERENCE"], g["START_DATE"], int(float(g["FLOW_DIRECTION"])),
                int(float(g["LANE_NUMBER"])), norm_class(g["CLASS_WEIGHT"]), float(g["TRAFFIC_COUNT"]))


def qh_local(start: str) -> dt.datetime:
    """Local start of a quarter hour from START_DATE ('2024-05-01T07:15:00', or with a space)."""
    t = dt.datetime.fromisoformat(start.replace(" ", "T").rstrip("Z"))
    if QH_LOCAL_TIME:
        return t.replace(tzinfo=None)
    from zoneinfo import ZoneInfo
    return t.replace(tzinfo=dt.timezone.utc).astimezone(ZoneInfo("Pacific/Auckland")).replace(tzinfo=None)


def fetch_quarter_hourly(http: Http, refs: Sequence[str], cache: Path | None = None
                         ) -> tuple[list[tuple], dict]:
    """Quarter-hourly rows (site_ref, local datetime, flow_direction, lane, class, count) of the
    sites in QH_MEMBERS, all days and times; plus fetch statistics per member."""
    want = {r.encode() for r in refs}
    stats: dict[str, Any] = {"members": {}}
    rows: list[tuple] = []
    total, entries = zip_directory(http, QH_URL, cache)
    stats["zip_total_bytes"] = total
    stats["zip_members"] = len(entries)
    for name in QH_MEMBERS:
        if name not in entries:
            raise RuntimeError(f"{name} not in the quarter-hourly zip")
        e = entries[name]
        # cache: the header and the kept lines (gzip), and the member's line counts (json)
        cfile = cache / "qh" / f"{Path(name).stem}_sites.csv.gz" if cache else None
        mfile = cache / "qh" / f"{Path(name).stem}_sites.json" if cache else None
        mstat = {"csize": e.csize, "usize": e.usize, "crc": f"{e.crc:#010x}"}
        if cfile is not None and mfile is not None and cfile.exists() and mfile.exists():
            with gzip.open(cfile, "rb") as f:
                kept = f.read().split(b"\n")
            header, kept = kept[0], [k for k in kept[1:] if k]
            meta = json.loads(mfile.read_text(encoding="utf-8"))
            if meta["n_kept"] != len(kept):
                raise RuntimeError(f"{cfile}: {len(kept)} lines, expected {meta['n_kept']}")
            mstat.update(meta, cached=True)
        else:
            t0, b0 = time.time(), http.bytes["15min"]
            header, kept, n_lines, layout = b"", [], 0, None
            for line in member_lines(http, QH_URL, e):
                if layout is None:
                    if not line.strip():
                        continue
                    header, layout = line.rstrip(b"\r"), QhLayout(line)
                    continue
                n_lines += 1
                if layout.site(line) in want:
                    kept.append(line.rstrip(b"\r"))
            meta = {"n_lines": n_lines, "n_kept": len(kept), "crc_ok": True,
                    "bytes_received": http.bytes["15min"] - b0}
            mstat.update(meta, cached=False)
            print(f"  15min {name}: {n_lines:,} lines, {len(kept):,} kept, "
                  f"{meta['bytes_received'] / 1e6:.1f} MB in {time.time() - t0:.0f} s", flush=True)
            if cfile is not None and mfile is not None:
                cfile.parent.mkdir(parents=True, exist_ok=True)
                with gzip.GzipFile(cfile, "wb", mtime=0) as f:
                    f.write(b"\n".join([header, *kept]) + b"\n")
                mfile.write_text(json.dumps(meta, indent=1), encoding="utf-8")
        layout = QhLayout(header)
        bad = 0
        clock: dict[str, dt.datetime] = {}           # START_DATE text -> local datetime
        names: dict[str, str] = {}                   # one shared str per site_ref / class
        for line in kept:
            try:
                ref, start, fd, lane, cls, cnt = layout.parse(line)
            except ValueError:
                bad += 1
                continue
            t = clock.get(start)
            if t is None:
                t = clock[start] = qh_local(start)
            rows.append((names.setdefault(ref, ref), t, fd, lane, names.setdefault(cls, cls), cnt))
        mstat["n_unparsed"] = bad
        stats["members"][name] = mstat
    return rows, stats


def check_qh_clock(qh_rows: Sequence[tuple]) -> int:
    """Hour (0..23) of the overnight trough of all weekday quarter-hourly counts; raises when it is
    not between 01:00 and 05:00, i.e. when the START_DATE clock (QH_LOCAL_TIME) is wrong."""
    by_hour = [0.0] * 24
    for _, t, _, _, _, cnt in qh_rows:
        if t.weekday() < 5:
            by_hour[t.hour] += cnt
    trough = min(range(24), key=lambda h: by_hour[h])
    if not 1 <= trough <= 5:
        raise RuntimeError(f"quarter-hourly clock check failed: trough at {trough}:00 "
                           f"(hourly totals {[round(v) for v in by_hour]})")
    return trough


# --------------------------------------------------------------------------- outputs


def site_rows(daily: Sequence[tuple], qh: Sequence[tuple], codes: dict[str, int]) -> list[list[Any]]:
    """tms_sites.csv rows: catalogue + flow direction code, lanes seen, NZTM coordinates."""
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", "EPSG:2193", always_xy=True)
    lanes_d: dict[tuple[str, int], set[int]] = defaultdict(set)
    for ref, _, fd, lane, _, _ in daily:
        lanes_d[(ref, fd)].add(lane)
    lanes_q: dict[tuple[str, int], set[int]] = defaultdict(set)
    for ref, _, fd, lane, _, _ in qh:
        lanes_q[(ref, fd)].add(lane)
    out = []
    for ref, desc, corr, dirn, kind, role, note, lat, lon in SITES:
        fd = codes[ref]
        lanes = lanes_d.get((ref, fd)) or lanes_q.get((ref, fd)) or set()
        x, y = tr.transform(lon, lat)
        out.append([ref, desc, corr, dirn, fd, kind, int(role != "not CBD-bound"), role,
                    len(lanes) if lanes else "", f"{lat:.6f}", f"{lon:.6f}", f"{x:.1f}", f"{y:.1f}", note])
    order = {c: i for i, c in enumerate(CORRIDOR_ORDER)}
    return sorted(out, key=lambda r: (order[r[2]], r[0]))


def am_rows(qh: Sequence[tuple]) -> list[list[Any]]:
    """Weekday quarter hours starting AM_FIRST_MIN .. AM_END_MIN - 15, one row per lane and class
    (the source has one record per site, quarter hour, direction, lane and class)."""
    tot: dict[tuple, float] = defaultdict(float)
    for ref, t, fd, lane, cls, cnt in qh:
        m = t.hour * 60 + t.minute
        if t.weekday() >= 5 or not AM_FIRST_MIN <= m < AM_END_MIN:
            continue
        tot[(ref, t.date().isoformat(), f"{t:%H:%M}", fd, lane, cls)] += cnt
    return [[*k, fmt_count(tot[k])] for k in sorted(tot)]


def qh_daily_rows(qh: Sequence[tuple]) -> list[list[Any]]:
    """Weekday full-day totals per site, date, direction, lane and class, with the number of
    quarter hours present (a quarter hour with a zero count is absent from the source)."""
    tot: dict[tuple, float] = defaultdict(float)
    nq: dict[tuple, int] = defaultdict(int)
    for ref, t, fd, lane, cls, cnt in qh:
        if t.weekday() >= 5:
            continue
        k = (ref, t.date().isoformat(), fd, lane, cls)
        tot[k] += cnt
        nq[k] += 1
    return [[*k, fmt_count(tot[k]), nq[k]] for k in sorted(tot)]


def coverage(daily: Sequence[tuple], am: Sequence[tuple], codes: dict[str, int]) -> list[dict[str, Any]]:
    """Per site, counted direction: weekdays with daily data, core lanes (lanes on at least half of
    those days), complete days (every core lane present), median daily volume over the complete
    days (all lanes and classes), weekdays without a heavy record (the light count then holds all
    vehicles), weekdays with AM data."""
    day_tot: dict[tuple[str, str], float] = defaultdict(float)
    day_keys: dict[tuple[str, str], set] = defaultdict(set)
    for ref, d, fd, lane, cls, cnt in daily:
        if fd == codes[ref]:
            day_tot[(ref, d)] += cnt
            day_keys[(ref, d)].add((lane, cls))
    am_days: dict[str, set[str]] = defaultdict(set)
    for ref, d, _, fd, *_ in am:
        if fd == codes[ref]:
            am_days[ref].add(d)
    out = []
    for ref, _, corr, dirn, *_ in SITES:
        days = sorted(d for (r, d) in day_tot if r == ref)
        lane_days: dict[int, int] = defaultdict(int)
        for d in days:
            for lane in {ln for ln, _ in day_keys[(ref, d)]}:
                lane_days[lane] += 1
        core = {ln for ln, n in lane_days.items() if n >= 0.5 * len(days)}
        complete = [day_tot[(ref, d)] for d in days if core <= {ln for ln, _ in day_keys[(ref, d)]}]
        no_heavy = sum(not any(c == "heavy" for _, c in day_keys[(ref, d)]) for d in days)
        out.append({"site_ref": ref, "corridor": corr, "direction": dirn, "flow_direction": codes[ref],
                    "lanes": len(core), "days": len(days), "days_complete": len(complete),
                    "median": round(median(complete)) if complete else None, "no_heavy": no_heavy,
                    "am_days": len(am_days[ref])})
    return out


def partial_class_days(rows: Sequence[Sequence[Any]]) -> int:
    """Site-direction-days of a daily table (site_ref, local_date, flow_direction, lane, class, ...)
    with a heavy record on some but not all of their lanes."""
    lanes: dict[tuple, set[int]] = defaultdict(set)
    heavy: dict[tuple, set[int]] = defaultdict(set)
    for r in rows:
        k = (r[0], r[1], r[2])
        lanes[k].add(r[3])
        if r[4] == "heavy":
            heavy[k].add(r[3])
    return sum(0 < len(heavy[k]) < len(v) for k, v in lanes.items())


def level_flags(qh: Sequence[tuple], cov: list[dict[str, Any]], codes: dict[str, int],
                lo: float = 0.67, hi: float = 1.5) -> list[tuple[str, str, float, float]]:
    """Site-months of the quarter-hourly data whose median weekday total (counted direction, all
    lanes and classes) is outside lo..hi times the site's 2025-26 daily median (coverage): (site_ref,
    YYYY-MM, ratio, share of records with an even count; 1.0 means every count was doubled)."""
    tot: dict[tuple[str, str], float] = defaultdict(float)
    even: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for ref, t, fd, _, _, cnt in qh:
        if t.weekday() >= 5 or fd != codes[ref]:
            continue
        tot[(ref, t.date().isoformat())] += cnt
        e = even[(ref, f"{t:%Y-%m}")]
        e[0] += cnt % 2 == 0
        e[1] += 1
    by_month: dict[tuple[str, str], list[float]] = defaultdict(list)
    for (ref, d), v in tot.items():
        by_month[(ref, d[:7])].append(v)
    ref_med = {c["site_ref"]: c["median"] for c in cov if c["median"]}
    out = []
    for (ref, m), vals in sorted(by_month.items()):
        if ref in ref_med:
            r = median(vals) / ref_med[ref]
            if not lo <= r <= hi:
                out.append((ref, m, round(r, 2), round(even[(ref, m)][0] / even[(ref, m)][1], 2)))
    return out


def outage_months(daily: Sequence[tuple], min_share: float = 0.5) -> list[tuple[str, int, int]]:
    """Months in which at least min_share of the sites with daily data have no weekday record:
    (YYYY-MM, sites without data, sites with data in the window)."""
    have: dict[str, set[str]] = defaultdict(set)
    for ref, d, *_ in daily:
        have[d[:7]].add(ref)
    active = {r for refs in have.values() for r in refs}
    months, m = [], DAILY_FIRST.replace(day=1)
    while m <= DAILY_LAST:
        months.append(f"{m:%Y-%m}")
        m = (m + dt.timedelta(days=32)).replace(day=1)
    return [(k, len(active - have[k]), len(active)) for k in months
            if len(active - have[k]) >= min_share * len(active)]


def weekdays(first: dt.date, last: dt.date) -> int:
    """Number of Mon-Fri days in first..last."""
    return sum((first + dt.timedelta(days=i)).weekday() < 5 for i in range((last - first).days + 1))


def write_readme(path: Path, stats: dict, cov: list[dict[str, Any]], sizes: dict[str, int],
                 nrows: dict[str, int], outages: list[tuple[str, int, int]],
                 multi_dir: list[str], n_partial: int,
                 levels: list[tuple[str, str, float, float]]) -> None:
    """data/nzta/README.md: sources, licence, filters, row counts, coverage and known gaps."""
    qs, ds, tr = stats["qh"], stats["daily"], stats["transfer"]
    am_days = sum(weekdays(dt.date(2024, m, 1), dt.date(2024, m + 1, 1) - dt.timedelta(days=1))
                  for m in (5, 8, 11))
    n_wd = weekdays(DAILY_FIRST, DAILY_LAST)
    member_txt = "\n".join(
        f"| {n} | {m['csize']:,} | {m['usize']:,} | {m['n_lines']:,} | {m['n_kept']:,} | {m['crc']} |"
        for n, m in qs["members"].items())
    cov_txt = "\n".join(
        f"| {c['site_ref']} | {c['corridor']} | {c['direction']} | {c['flow_direction']} | "
        f"{c['lanes'] or ''} | {c['days']} | {c['days_complete']} | "
        f"{c['median'] if c['median'] is not None else ''} | {c['no_heavy']} | {c['am_days']} |"
        for c in cov)
    no_daily = [c["site_ref"] for c in cov if c["days"] == 0]
    few_daily = [f"{c['site_ref']} ({c['days']})" for c in cov if 0 < c["days"] < 0.5 * n_wd]
    no_am = [c["site_ref"] for c in cov if c["am_days"] == 0]
    heavy_gaps = [f"{c['site_ref']} ({c['no_heavy']} days)" for c in cov
                  if c["days"] and c["no_heavy"] >= 0.1 * c["days"]]
    out_txt = "; ".join(f"{m} ({n} of {a} sites)" for m, n, a in outages) or "none"
    times_txt = ", ".join(f"{k} UTC x{v:,}" for k, v in ds["utc_times"].items())
    level_txt = "; ".join(f"{r} {m} (x{x:.2f}, {e:.0%} of counts even)" for r, m, x, e in levels) or "none"
    partial_txt = ("in both daily files every site-direction-day has a heavy record on all its lanes "
                   "or on none." if n_partial == 0 else
                   f"{n_partial} site-direction-days (both daily files) have a heavy record on some "
                   "lanes only; every other day has one on all its lanes or on none.")
    total_kb = sum(sizes.values()) / 1e3
    text = f"""# NZTA motorway traffic counts, Auckland CBD approaches

Written by `prep/fetch_nzta.py` from data retrieved on {stats['retrieved']}. Do not edit by hand;
rerun the script (last section).

## Source and licence

New Zealand Transport Agency (NZTA Waka Kotahi), Traffic Monitoring System (TMS), published on the
NZTA Open Data portal (https://opendata-nzta.opendata.arcgis.com) under CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/). Attribution to show with any use:

> {ATTRIBUTION}

1. Daily counts: ArcGIS feature service `TMS_Telemetry_Sites`, layer 0,
   {DAILY_URL}, REST `query` with `returnDistinctValues=true`.
2. Quarter-hourly counts February 2022 to January 2025: ArcGIS item `{QH_ITEM}`,
   {QH_URL}: a {qs['zip_total_bytes']:,}-byte zip with one CSV per month ({qs['zip_members']}
   members). Only the three members below were read, with HTTP Range requests (plus a 70 kB read of
   the zip directory at the end of the file); the zip itself was never downloaded.

| member | compressed bytes | uncompressed bytes | lines | lines kept ({len(SITES)} sites) | CRC-32 (checked) |
|---|---|---|---|---|---|
{member_txt}

Site coordinates (WGS84) are from the NZTA TMS site catalogue; x_nztm, y_nztm (NZTM2000,
EPSG:2193) are projected from them with pyproj.

## Files ({total_kb:,.0f} kB in total)

| file | rows | bytes | content |
|---|---|---|---|
| tms_sites.csv | {nrows['tms_sites.csv']} | {sizes['tms_sites.csv']:,} | one row per site: site_ref, NZTA description, corridor, direction (NB/SB/EB/WB counted), flow_direction (its code in the count files), kind (mainline, link, ramp), cbd_bound (1 = the counted direction heads towards the CBD in the AM peak), cbd_role, lanes (lanes of the counted direction in the 2025-26 daily data, else in 2024), lat, lon, x_nztm, y_nztm, note |
| tms_daily_weekday.csv | {nrows['tms_daily_weekday.csv']:,} | {sizes['tms_daily_weekday.csv']:,} | site_ref, local_date, flow_direction, lane, class (light/heavy), count = vehicles per day; Mon-Fri {DAILY_FIRST} to {DAILY_LAST} |
| tms_15min_am_2024.csv | {nrows['tms_15min_am_2024.csv']:,} | {sizes['tms_15min_am_2024.csv']:,} | site_ref, local_date, time (HH:MM, NZ local start of the quarter hour), flow_direction, lane, class, count = vehicles per quarter hour; Mon-Fri of May, Aug and Nov 2024, quarter hours 05:00 to 11:00 |
| tms_15min_daily_2024.csv | {nrows['tms_15min_daily_2024.csv']:,} | {sizes['tms_15min_daily_2024.csv']:,} | site_ref, local_date, flow_direction, lane, class, count, n_qh: full-day totals of the same quarter-hourly records (Mon-Fri, all 96 quarter hours), n_qh = quarter hours present; for day validity checks and peak-hour shares |

Counts are vehicles; x.5 values are part of the source. flow_direction is the TMS code: through
lanes 1 = increasing route position (SH1 southbound, SH16 westbound, SH20 northbound) and 2 =
decreasing (SH1 northbound, SH16 eastbound); ramps and links carry the ramp codes 3 to 6 (see
tms_sites.csv). All flow directions found for a site are kept; sites with more than one:
{', '.join(multi_dir) or 'none'}. A direction total is the sum over all its lanes and both classes.

## Filters

* Sites: the {len(SITES)} SiteRefs in `SITES` (prep/fetch_nzta.py): SH1 through lanes on both CBD
  approaches including the Harbour Bridge classifier, SH16 eastbound, SH20 northbound, the two
  Waterview SH20 -> SH16 links and the CBD exit ramps of the Central Motorway Junction.
* Daily: local dates {DAILY_FIRST} to {DAILY_LAST}, Monday to Friday ({n_wd} weekdays; public and
  school holidays are included). One query per site and calendar quarter ({ds['n_requests']}
  requests, outFields startDate, classWeight, laneNumber, flowDirection, trafficCount);
  {ds['n_records']:,} distinct records received, {ds.get('n_weekend', 0):,} weekend records dropped,
  {ds.get('n_dupe', 0)} duplicates left after DISTINCT ({ds.get('n_conflicts', 0)} with differing
  counts; the larger is kept). startDate values seen: {times_txt}.
* Quarter-hourly: Monday to Friday of May, August and November 2024 ({am_days} weekdays; no public
  or school holiday falls on them); quarter hours starting 05:00 to 10:45 in the AM file, all 96 in
  the daily totals. START_DATE is NZ local time: the overnight minimum of the summed weekday counts
  is at {qs['trough_hour']:02d}:00.

## Coverage per site (counted direction)

days = weekdays with a daily record 2025-26 (of {n_wd}); lanes = lanes present on at least half of
those days; complete = days with every such lane; median = median daily volume (all lanes and
classes) over the complete days, holidays included, no check for low lanes; no heavy = days
without any heavy record; AM days = weekdays with quarter-hourly AM records in 2024 (of {am_days}).

| site_ref | corridor | dir | flow_direction | lanes | days | complete | median | no heavy | AM days |
|---|---|---|---|---|---|---|---|---|---|
{cov_txt}

## Known gaps and caveats

* No daily record 2025-26: {', '.join(no_daily) or 'none'}. Fewer than half of the weekdays:
  {', '.join(few_daily) or 'none'}.
* Months in which at least half of the sites report nothing: {out_txt}.
* Quarter-hourly site-months whose median weekday total is outside 0.67 to 1.5 times the site's
  2025-26 daily median (do not use their volumes): {level_txt}. About a quarter to a half of the
  counts are even in a normal month; 100 % even means every count was doubled.
* No AM record in the three 2024 quarter-hourly members read: {', '.join(no_am) or 'none'}.
  None of the CBD exit ramps appears in these months, so the 2024 AM profiles cover through lanes
  and links only.
* Unclassified days: {partial_txt} Without one, the light count holds all vehicles (median
  totals of such days match those of classified days at the same site), so use light + heavy as
  the volume and do not read a class split from those days. Sites with no heavy record on 10 % or
  more of their days: {', '.join(heavy_gaps) or 'none'}.
* 01N20440 (Panama Rd national telemetry site) has been gappy since its September 2022 handover;
  the Nelson St, Cook St, Shelly Beach Rd and Newton Rd off ramps are non-continuous sites.
* Since January 2026 the daily table holds most records up to ~40 times; the server-side DISTINCT
  removes the copies. Daily startDate is 12:00 UTC of the previous day before 2024 and 00:00 UTC of
  the day since; local date = (UTC + 12 h).date().
* Quarter hours with zero vehicles are absent from the quarter-hourly source, so a missing quarter
  hour means zero or no data. Lane outages show as low or missing lanes: check the lane totals in
  tms_15min_daily_2024.csv (and n_qh) or tms_daily_weekday.csv before using a day.
* Harbour Bridge (01N19424): the moveable barrier moves lanes between the directions during the
  day; always sum all lanes of a direction.
* 01N47429 (Wellesley St off ramp NB) has the Symonds St off ramp coordinates in the catalogue.
* The quarter-hourly zip also holds a stray member `tms_2025_01.csv.csv` (10 kB) and a metadata
  text file; neither was read.

## Re-run

    cd cordon_lite
    .venv\\Scripts\\python.exe -m prep.fetch_nzta --out data/nzta --cache <folder>

The download is {tr['daily_requests']} daily queries ({tr['daily_bytes']:,} bytes of gzip-encoded
JSON, {tr['daily_json_bytes']:,} bytes decompressed) and {tr['qh_requests']} Range requests on the
quarter-hourly zip ({tr['qh_bytes']:,} bytes). With `--cache` the downloaded pieces are kept, and a
rerun with the same folder (add `--offline` to forbid network access) rebuilds identical files
without downloading. The daily service is live, so a fresh download later may return revised
counts.
"""
    path.write_text(text, encoding="utf-8", newline="\n")


def write_outputs(out_dir: Path, daily: Sequence[tuple], qh: Sequence[tuple], stats: dict) -> dict:
    """Write the four CSV files and README.md; returns row counts, sizes and coverage."""
    out_dir.mkdir(parents=True, exist_ok=True)
    codes = listed_codes(daily, qh)
    am = am_rows(qh)
    files: dict[str, tuple[Sequence[str], list]] = {
        "tms_sites.csv": (SITES_COLUMNS, site_rows(daily, qh, codes)),
        "tms_daily_weekday.csv": (DAILY_COLUMNS, [[r, d, fd, ln, c, fmt_count(v)]
                                                  for r, d, fd, ln, c, v in daily]),
        "tms_15min_am_2024.csv": (AM_COLUMNS, am),
        "tms_15min_daily_2024.csv": (QH_DAILY_COLUMNS, qh_daily_rows(qh)),
    }
    nrows, sizes = {}, {}
    for name, (cols, rows) in files.items():
        write_csv(out_dir / name, cols, rows)
        nrows[name], sizes[name] = len(rows), (out_dir / name).stat().st_size
    cov = coverage(daily, am, codes)
    dirs: dict[str, set[int]] = defaultdict(set)
    for r in (*daily, *qh):
        dirs[r[0]].add(r[2])
    multi = [f"{ref} ({'/'.join(map(str, sorted(fds)))})" for ref, fds in sorted(dirs.items())
             if len(fds) > 1]
    n_partial = partial_class_days(daily) + partial_class_days(files["tms_15min_daily_2024.csv"][1])
    levels = level_flags(qh, cov, codes)
    write_readme(out_dir / "README.md", stats, cov, sizes, nrows, outage_months(daily), multi,
                 n_partial, levels)
    sizes["README.md"] = (out_dir / "README.md").stat().st_size
    return {"nrows": nrows, "sizes": sizes, "coverage": cov}


# --------------------------------------------------------------------------- driver


def transfer_totals(http: Http, cache: Path | None) -> dict[str, int]:
    """Requests and bytes of the downloads behind the outputs: this run's, plus those of the
    cached pieces (cache/transfer.json, updated here), so a rebuild from the cache reports the
    original download."""
    now = {"daily_requests": http.requests["daily"], "daily_bytes": http.bytes["daily"],
           "daily_json_bytes": http.json_bytes["daily"], "qh_requests": http.requests["15min"],
           "qh_bytes": http.bytes["15min"]}
    if cache is None:
        return now
    f = cache / "transfer.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    tot = {k: int(old.get(k, 0)) + v for k, v in now.items()}
    if any(now.values()):
        f.write_text(json.dumps(tot, indent=1) + "\n", encoding="utf-8")
    return tot


def run_fetch(out_dir: Path | None = None, cache: Path | None = None, offline: bool = False) -> dict:
    """Both downloads, filtering and outputs; returns statistics."""
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT
    http = Http(offline=offline)
    refs = [s[0] for s in SITES]
    if len(set(refs)) != len(refs):
        raise RuntimeError("duplicate site_ref in SITES")
    retrieved = dt.date.today().isoformat()
    if cache is not None:
        cache.mkdir(parents=True, exist_ok=True)
        meta = cache / "retrieved.txt"
        if meta.exists():
            retrieved = meta.read_text(encoding="utf-8").strip()
        else:
            meta.write_text(retrieved + "\n", encoding="utf-8")
    print(f"daily counts {DAILY_FIRST} .. {DAILY_LAST}, {len(refs)} sites", flush=True)
    daily, dstats = fetch_daily(http, refs, cache)
    dstats["n_requests"] = http.requests["daily"] + dstats.get("n_cached", 0)
    print(f"quarter-hourly counts {', '.join(QH_MEMBERS)}", flush=True)
    qh, qstats = fetch_quarter_hourly(http, refs, cache)
    qstats["trough_hour"] = check_qh_clock(qh)
    stats = {"retrieved": retrieved, "daily": dstats, "qh": qstats,
             "bytes": dict(http.bytes), "json_bytes": dict(http.json_bytes),
             "requests": dict(http.requests), "retried": dict(http.retried),
             "transfer": transfer_totals(http, cache)}
    stats.update(write_outputs(out_dir, daily, qh, stats))
    stats["out_dir"] = out_dir
    return stats


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description="NZTA TMS motorway counts for the Auckland CBD approaches")
    ap.add_argument("--out", default=None, help="output folder (default: data/nzta)")
    ap.add_argument("--cache", default=None, help="folder that keeps the downloaded pieces for reruns")
    ap.add_argument("--offline", action="store_true", help="no network access: rebuild from --cache only")
    args = ap.parse_args(argv)
    if args.offline and not args.cache:
        ap.error("--offline needs --cache")
    st = run_fetch(Path(args.out) if args.out else None, Path(args.cache) if args.cache else None,
                   args.offline)
    for tag in ("daily", "15min"):
        print(f"{tag}: {st['requests'].get(tag, 0)} requests, {st['bytes'].get(tag, 0):,} bytes received"
              + (f" ({st['json_bytes'][tag]:,} bytes of JSON)" if tag in st["json_bytes"] else "")
              + (f", {st['retried'][tag]} retries" if st["retried"].get(tag) else ""))
    for name, n in st["nrows"].items():
        print(f"{name}: {n:,} rows, {st['sizes'][name]:,} bytes")
    print(f"total {sum(st['sizes'].values()) / 1e6:.2f} MB in {st['out_dir']}")
    print(f"quarter-hourly overnight trough at {st['qh']['trough_hour']:02d}:00 local")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
