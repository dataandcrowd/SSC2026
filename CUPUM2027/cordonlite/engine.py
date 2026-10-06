"""Gate-bottleneck engine interface (cars only).

Implementations (added by the engine builder in this module):
    PyEngine       Python reference implementation.
    NetLogoEngine  pynetlogo 0.5.2 + NetLogo 7.0.4 driving netlogo7/cordon_lite.nlogox via files.
    make_engine(kind: str, cfg: Config) -> Engine   kind in {"py", "netlogo"}.

Semantics (identical in both implementations). Per corridor, minute resolution:
  - A car with depart minute d joins its corridor queue at a = d + fftt_to_gate_min.
  - For each minute m ascending from sim_start_min: append arrivals with a == m to the back of
    the FIFO in ascending agent_id order; available = carry + c; n = min(len(queue),
    floor(available)); serve the first n (gate_exit_min = m); carry = available - n; if the queue
    is now empty, carry = min(carry, 1.0). carry starts at 0 each day.
  - The loop stops after the minute in which the last car is served, or at sim_end_cap_min.
    Cars still unserved at the cap get gate_exit_min = queue_delay_min = arrive_min = -1, fee 0.
  - queue_delay_min = gate_exit_min - a; arrive_min = gate_exit_min + fftt_gate_to_dest_min;
    fee_paid = fees.csv[gate_exit_min] if fee_active else 0.
  - Profile rows: every corridor x every minute from sim_start_min to the last minute processed,
    with arrivals, served and queue_len (after serving).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd

PLAN_COLUMNS: tuple[str, ...] = ("agent_id", "mode", "depart_min")
OUTCOME_COLUMNS: tuple[str, ...] = (
    "agent_id", "day", "corridor_id", "depart_min", "gate_arrive_min", "gate_exit_min",
    "queue_delay_min", "arrive_min", "fee_paid",
)
PROFILE_COLUMNS: tuple[str, ...] = ("day", "corridor_id", "minute", "arrivals", "served", "queue_len")

# Scenario files written by the orchestrator into the run directory.
CORRIDORS_FILE = "corridors.csv"   # corridor_id, name, capacity_per_min, x, y
AGENTS_FILE = "agents.csv"         # agent_id, corridor_id, fftt_to_gate_min, fftt_gate_to_dest_min, x, y
FEES_FILE = "fees.csv"             # minute, fee  (active regime, 1440 rows)
CORRIDORS_COLUMNS: tuple[str, ...] = ("corridor_id", "name", "capacity_per_min", "x", "y")
AGENTS_COLUMNS: tuple[str, ...] = ("agent_id", "corridor_id", "fftt_to_gate_min", "fftt_gate_to_dest_min", "x", "y")


def plans_file(day: int) -> str:
    """plans_dayNN.csv (NetLogoEngine file exchange)."""
    return f"plans_day{day:02d}.csv"


def outcomes_file(day: int) -> str:
    return f"outcomes_day{day:02d}.csv"


def profile_file(day: int) -> str:
    return f"profile_day{day:02d}.csv"


@dataclass
class DayResult:
    """Engine output for one day.

    outcomes: one row per CAR agent, columns OUTCOME_COLUMNS, sorted by agent_id,
              all integer columns int64 except fee_paid (float64).
    profile:  columns PROFILE_COLUMNS, sorted by corridor_id then minute, int64 except
              none (all integer).
    """

    outcomes: pd.DataFrame
    profile: pd.DataFrame


class Engine(Protocol):
    """Day-by-day gate-bottleneck simulator."""

    def load(self, scenario_dir: Path) -> None:
        """Read corridors.csv, agents.csv and fees.csv from scenario_dir."""
        ...

    def run_day(self, day: int, plans: pd.DataFrame, fee_active: bool) -> DayResult:
        """Simulate one morning. plans: agent_id (int), mode in {CAR, PT, WFH, SKIP},
        depart_min (int; ignored unless CAR). Every agent appears once."""
        ...

    def close(self) -> None:
        """Release resources (NetLogo workspace). Safe to call twice."""
        ...


# ---------------------------------------------------------------------------------------------
# Implementations (engine builder)
# ---------------------------------------------------------------------------------------------

import math  # noqa: E402
import os  # noqa: E402
import threading  # noqa: E402
from typing import TYPE_CHECKING, Any, Sequence  # noqa: E402

import numpy as np  # noqa: E402

from cordonlite.fees import read_fees_csv  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from cordonlite.config import Config

VALID_MODES: frozenset[str] = frozenset({"CAR", "PT", "WFH", "SKIP"})
_INT_OUTCOME_COLUMNS = tuple(c for c in OUTCOME_COLUMNS if c != "fee_paid")


@dataclass(frozen=True)
class Scenario:
    """Scenario files as read by the engines (corridors ordered by corridor_id)."""

    corridor_ids: tuple[int, ...]
    capacities: tuple[float, ...]
    names: tuple[str, ...]
    agent_corridor: dict[int, int]
    agent_fftt_to_gate: dict[int, int]
    agent_fftt_gate_to_dest: dict[int, int]
    fee_table: tuple[float, ...]


def read_scenario(scenario_dir: str | Path) -> Scenario:
    """Read corridors.csv, agents.csv and fees.csv (floats parsed round-trip exact)."""
    d = Path(scenario_dir)
    cor = pd.read_csv(d / CORRIDORS_FILE, float_precision="round_trip")
    ag = pd.read_csv(d / AGENTS_FILE, float_precision="round_trip")
    for cols, df, name in ((CORRIDORS_COLUMNS, cor, CORRIDORS_FILE), (AGENTS_COLUMNS, ag, AGENTS_FILE)):
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise ValueError(f"{name} lacks columns {missing}")
    cor = cor.sort_values("corridor_id", kind="stable")
    if cor["corridor_id"].duplicated().any():
        raise ValueError("duplicate corridor_id in corridors.csv")
    if ag["agent_id"].duplicated().any():
        raise ValueError("duplicate agent_id in agents.csv")
    caps = tuple(float(c) for c in cor["capacity_per_min"])
    if any(not (c > 0 and math.isfinite(c)) for c in caps):
        raise ValueError("capacity_per_min must be positive and finite")
    cids = tuple(int(c) for c in cor["corridor_id"])
    known = set(cids)
    a_cor = {int(a): int(c) for a, c in zip(ag["agent_id"], ag["corridor_id"])}
    if not set(a_cor.values()) <= known:
        raise ValueError("agents.csv refers to unknown corridor_id")
    for col in ("fftt_to_gate_min", "fftt_gate_to_dest_min"):
        v = ag[col].to_numpy(dtype=float)
        if np.any(v != np.round(v)) or np.any(v < 0):
            raise ValueError(f"agents.csv {col} must be non-negative integers")
    return Scenario(
        corridor_ids=cids,
        capacities=caps,
        names=tuple(str(n) for n in cor["name"]),
        agent_corridor=a_cor,
        agent_fftt_to_gate={int(a): int(v) for a, v in zip(ag["agent_id"], ag["fftt_to_gate_min"])},
        agent_fftt_gate_to_dest={int(a): int(v) for a, v in zip(ag["agent_id"], ag["fftt_gate_to_dest_min"])},
        fee_table=tuple(read_fees_csv(d / FEES_FILE)),
    )


def car_rows(plans: pd.DataFrame, scen: Scenario, sim_start_min: int) -> list[tuple[int, int, int, int]]:
    """Validate a plans frame and return CAR rows (agent_id, corridor_id, depart_min, gate_arrive_min)
    sorted by agent_id. Agents absent from plans are simply not simulated."""
    missing = [c for c in PLAN_COLUMNS if c not in plans.columns]
    if missing:
        raise ValueError(f"plans lacks columns {missing}")
    if plans["agent_id"].duplicated().any():
        raise ValueError("plans has duplicate agent_id")
    bad = set(plans["mode"].astype(str)) - VALID_MODES
    if bad:
        raise ValueError(f"plans has invalid modes {sorted(bad)}")
    car = plans[plans["mode"].astype(str) == "CAR"]
    out: list[tuple[int, int, int, int]] = []
    for aid, dep in zip(car["agent_id"], car["depart_min"]):
        aid = int(aid)
        if aid not in scen.agent_corridor:
            raise ValueError(f"plans: unknown agent_id {aid}")
        depf = float(dep)
        if not math.isfinite(depf) or depf != round(depf):
            raise ValueError(f"plans: CAR agent {aid} has non-integer depart_min {dep!r}")
        d = int(round(depf))
        a = d + scen.agent_fftt_to_gate[aid]
        if a < sim_start_min:
            raise ValueError(f"agent {aid} reaches its gate at minute {a}, before sim_start_min {sim_start_min}")
        out.append((aid, scen.agent_corridor[aid], d, a))
    out.sort()
    return out


def simulate_point_queues(
    cars: Sequence[tuple[int, int, int, int]],
    corridor_ids: Sequence[int],
    capacities: Sequence[float],
    sim_start_min: int,
    sim_end_cap_min: int,
) -> tuple[dict[int, int], list[tuple[int, int, int, int, int]], int]:
    """Vickrey point queues, one per corridor, minute resolution (reference algorithm).

    cars: (agent_id, corridor_id, depart_min, gate_arrive_min). Returns (exit minute by agent_id,
    profile rows (corridor_id, minute, arrivals, served, queue_len), last minute processed).
    Agents unserved at the cap are absent from the exit dict. The loop always processes at least
    sim_start_min, so a day without cars yields one profile row per corridor.
    """
    k_of = {c: k for k, c in enumerate(corridor_ids)}
    lanes: list[list[tuple[int, int]]] = [[] for _ in corridor_ids]
    for aid, cid, _d, a in cars:
        lanes[k_of[cid]].append((a, aid))
    for lane in lanes:
        lane.sort()  # by arrival minute, then agent_id: FIFO with ties in ascending agent_id
    n_k = len(lanes)
    arr_ptr = [0] * n_k
    srv_ptr = [0] * n_k
    carry = [0.0] * n_k
    exits: dict[int, int] = {}
    profile: list[tuple[int, int, int, int, int]] = []
    n_cars = len(cars)
    n_served = 0
    m = sim_start_min
    while True:
        for k in range(n_k):
            lane = lanes[k]
            ap = arr_ptr[k]
            n_arr = 0
            while ap < len(lane) and lane[ap][0] <= m:
                ap += 1
                n_arr += 1
            sp = srv_ptr[k]
            avail = carry[k] + capacities[k]
            n = min(ap - sp, math.floor(avail))
            for j in range(sp, sp + n):
                exits[lane[j][1]] = m
            sp += n
            cr = avail - n
            if sp == ap:
                cr = min(cr, 1.0)
            carry[k] = cr
            arr_ptr[k] = ap
            srv_ptr[k] = sp
            n_served += n
            profile.append((corridor_ids[k], m, n_arr, n, ap - sp))
        if n_served == n_cars or m >= sim_end_cap_min:
            break
        m += 1
    return exits, profile, m


def _empty_outcomes() -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype="int64") for c in OUTCOME_COLUMNS})
    df["fee_paid"] = df["fee_paid"].astype("float64")
    return df


def _typed_outcomes(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) == 0:
        return _empty_outcomes()
    df = df[list(OUTCOME_COLUMNS)].copy()
    for c in _INT_OUTCOME_COLUMNS:
        df[c] = df[c].astype("float64").round().astype("int64")
    df["fee_paid"] = df["fee_paid"].astype("float64")
    return df.sort_values("agent_id", kind="stable").reset_index(drop=True)


def _typed_profile(df: pd.DataFrame) -> pd.DataFrame:
    df = df[list(PROFILE_COLUMNS)].copy()
    for c in PROFILE_COLUMNS:
        df[c] = df[c].astype("float64").round().astype("int64")
    return df.sort_values(["corridor_id", "minute"], kind="stable").reset_index(drop=True)


class PyEngine:
    """Python reference implementation of the gate-bottleneck engine."""

    kind = "py"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.sim_start_min = int(cfg.time.sim_start_min)
        self.sim_end_cap_min = int(cfg.time.sim_end_cap_min)
        self.scenario: Scenario | None = None

    def load(self, scenario_dir: Path) -> None:
        self.scenario = read_scenario(scenario_dir)

    def run_day(self, day: int, plans: pd.DataFrame, fee_active: bool) -> DayResult:
        scen = self.scenario
        if scen is None:
            raise RuntimeError("PyEngine.load() must be called before run_day()")
        cars = car_rows(plans, scen, self.sim_start_min)
        exits, prof, _last = simulate_point_queues(
            cars, scen.corridor_ids, scen.capacities, self.sim_start_min, self.sim_end_cap_min)
        rows = []
        for aid, cid, d, a in cars:
            x = exits.get(aid, -1)
            if x < 0:
                rows.append((aid, day, cid, d, a, -1, -1, -1, 0.0))
            else:
                fee = scen.fee_table[x] if fee_active else 0.0
                rows.append((aid, day, cid, d, a, x, x - a, x + scen.agent_fftt_gate_to_dest[aid], float(fee)))
        outcomes = _typed_outcomes(pd.DataFrame(rows, columns=list(OUTCOME_COLUMNS))) if rows else _empty_outcomes()
        profile = _typed_profile(pd.DataFrame([(day, *r) for r in prof], columns=list(PROFILE_COLUMNS)))
        return DayResult(outcomes=outcomes, profile=profile)

    def close(self) -> None:
        self.scenario = None


# --------------------------------------------------------------------------- NetLogo

_LINK: Any = None
_LINK_LOCK = threading.Lock()


def get_netlogo_link(cfg: Config) -> Any:
    """One shared pynetlogo.NetLogoLink per process (the JVM can start only once)."""
    global _LINK
    with _LINK_LOCK:
        if _LINK is None:
            home = Path(cfg.engine.netlogo_home)
            if not (home.is_dir() and any(home.glob("**/netlogo-*.jar"))):
                raise RuntimeError(f"NetLogo 7.0.4 not found at {home}: install it or set "
                                   "[engine] netlogo_home in config.toml")
            import pynetlogo  # local import: optional dependency path, starts the JVM

            _LINK = pynetlogo.NetLogoLink(gui=bool(cfg.engine.gui), netlogo_home=cfg.engine.netlogo_home)
        return _LINK


def shutdown_netlogo_link(timeout_s: float = 5.0) -> bool:
    """Try kill_workspace on the shared link in a daemon thread; True if it returned in time.

    The JVM may still hang at interpreter exit: callers (CLI, test helpers) should finish with
    os._exit(code) after this.
    """
    global _LINK
    link = _LINK
    if link is None:
        return True
    done = threading.Event()

    def _kill() -> None:
        try:
            link.kill_workspace()
        except Exception:  # noqa: BLE001 - best effort during shutdown
            pass
        finally:
            done.set()

    threading.Thread(target=_kill, daemon=True).start()
    ok = done.wait(timeout_s)
    _LINK = None
    return ok


def _nl_string(s: str) -> str:
    """NetLogo string literal."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


class NetLogoEngine:
    """Drives netlogo7/cordon_lite.nlogox headless through pynetlogo, exchanging CSV files."""

    kind = "netlogo"

    def __init__(self, cfg: Config, link: object | None = None) -> None:
        self.cfg = cfg
        self.sim_start_min = int(cfg.time.sim_start_min)
        self.sim_end_cap_min = int(cfg.time.sim_end_cap_min)
        self.model_path = cfg.resolve_path(cfg.engine.model_path)
        self._link: Any = link
        self.scenario: Scenario | None = None
        self.scenario_dir: Path | None = None

    @property
    def link(self) -> Any:
        if self._link is None:
            self._link = get_netlogo_link(self.cfg)
        return self._link

    def load(self, scenario_dir: Path) -> None:
        d = Path(scenario_dir).resolve()
        self.scenario = read_scenario(d)  # Python-side validation of the same files
        self.scenario_dir = d
        link = self.link
        link.load_model(str(self.model_path))
        link.command(f"setup-from-dir {_nl_string(str(d))}")
        link.command(f"set-clock {self.sim_start_min} {self.sim_end_cap_min}")

    def run_day(self, day: int, plans: pd.DataFrame, fee_active: bool) -> DayResult:
        scen, d = self.scenario, self.scenario_dir
        if scen is None or d is None:
            raise RuntimeError("NetLogoEngine.load() must be called before run_day()")
        cars = car_rows(plans, scen, self.sim_start_min)  # same validation as PyEngine
        p = plans[list(PLAN_COLUMNS)].copy()
        dep = pd.to_numeric(p["depart_min"], errors="coerce").fillna(-1)
        p["depart_min"] = dep.round().astype("int64")
        p["agent_id"] = p["agent_id"].astype("int64")
        p["mode"] = p["mode"].astype(str)
        p = p.sort_values("agent_id", kind="stable")
        for f in (outcomes_file(day), profile_file(day)):
            (d / f).unlink(missing_ok=True)
        p.to_csv(d / plans_file(day), index=False, lineterminator="\n")
        self.link.command(f"run-day {int(day)} {_nl_string(str(d))} {'true' if fee_active else 'false'}")
        out = pd.read_csv(d / outcomes_file(day), float_precision="round_trip")
        prof = pd.read_csv(d / profile_file(day), float_precision="round_trip")
        if len(out) != len(cars):
            raise RuntimeError(f"NetLogo returned {len(out)} outcomes for {len(cars)} cars")
        return DayResult(outcomes=_typed_outcomes(out), profile=_typed_profile(prof))

    def close(self) -> None:
        """Forget the scenario; the shared JVM link stays up (see shutdown_netlogo_link)."""
        self.scenario = None
        self.scenario_dir = None


def make_engine(kind: str, cfg: Config) -> Engine:
    """kind in {"py", "netlogo"}."""
    if kind == "py":
        return PyEngine(cfg)
    if kind == "netlogo":
        return NetLogoEngine(cfg)
    raise ValueError(f"unknown engine kind {kind!r}")


def hard_exit(code: int = 0) -> None:
    """Flush stdio and leave the process without JVM shutdown (avoids the known hang)."""
    import sys

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
