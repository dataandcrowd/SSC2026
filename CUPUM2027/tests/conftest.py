"""Shared fixtures: a tiny synthetic scenario (3 corridors, 20 agents) needing no prep data.

Fixtures
    tiny_cfg              Config with n_agents=20, n_days=6, fee_start_day=3, n_twins=4.
    tiny_corridors        engine corridors.csv frame (corridor_id, name, capacity_per_min, x, y).
    tiny_agents           engine agents.csv frame (agent_id, corridor_id, fftt_to_gate_min, fftt_gate_to_dest_min, x, y).
    tiny_scenario_dir     tmp dir holding corridors.csv, agents.csv, fees.csv (ToU).
    tiny_origins          prep origins.csv frame (60 origins over the 3 corridors).
    tiny_corridors_prep   prep corridors.csv frame.
    tiny_personas         20 hand-built Persona objects consistent with tiny_agents.
    tiny_plans            day plans frame (agent_id, mode, depart_min): mix of CAR/PT/WFH/SKIP.
    make_today            factory: make_today(day, fee_active=..., public_delay=None, disrupted=()) -> TodayInfo.

NetLogo tests: mark with @pytest.mark.netlogo. They are skipped unless pytest is run with
--run-netlogo or CORDONLITE_RUN_NETLOGO=1, and must run in their own pytest process because
the JVM can start only once per process and may hang on exit.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import pandas as pd
import pytest

from cordonlite import fees
from cordonlite.config import Config, load_config
from cordonlite.engine import AGENTS_COLUMNS, AGENTS_FILE, CORRIDORS_COLUMNS, CORRIDORS_FILE, FEES_FILE
from cordonlite.types import DelayProfile, Persona, TodayInfo

N_TINY_AGENTS = 20
N_TINY_CORRIDORS = 3


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--run-netlogo", action="store_true", default=False,
                     help="run tests marked netlogo (start the NetLogo JVM)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-netlogo") or os.environ.get("CORDONLITE_RUN_NETLOGO") == "1":
        return
    skip = pytest.mark.skip(reason="NetLogo test: use --run-netlogo in a separate pytest process")
    for item in items:
        if "netlogo" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def tiny_cfg() -> Config:
    return load_config(overrides={
        "run.n_agents": N_TINY_AGENTS,
        "run.n_days": 6,
        "fees.fee_start_day": 3,
        "persona.n_twins": 4,
        "events.pt_disruption_day": 5,
    })


@pytest.fixture
def tiny_corridors() -> pd.DataFrame:
    df = pd.DataFrame({
        "corridor_id": [0, 1, 2],
        "name": ["North (Harbour Bridge)", "West (Great North Rd)", "South (Khyber Pass Rd)"],
        "capacity_per_min": [0.5, 1.0, 1.5],
        "x": [1757000.0, 1755000.0, 1758500.0],
        "y": [5923000.0, 5920000.0, 5918000.0],
    })
    return df[list(CORRIDORS_COLUMNS)]


def _agent_rows() -> list[dict]:
    rows = []
    for i in range(N_TINY_AGENTS):
        c = i % N_TINY_CORRIDORS
        rows.append({
            "agent_id": i,
            "corridor_id": c,
            "fftt_to_gate_min": 10 + (i * 7) % 31,
            "fftt_gate_to_dest_min": 2 + i % 5,
            "x": 1750000.0 + 500.0 * i,
            "y": 5910000.0 + 300.0 * ((i * 3) % 20),
        })
    return rows


@pytest.fixture
def tiny_agents() -> pd.DataFrame:
    return pd.DataFrame(_agent_rows())[list(AGENTS_COLUMNS)]


@pytest.fixture
def tiny_scenario_dir(tmp_path: Path, tiny_corridors: pd.DataFrame, tiny_agents: pd.DataFrame) -> Path:
    d = tmp_path / "scenario"
    d.mkdir()
    tiny_corridors.to_csv(d / CORRIDORS_FILE, index=False)
    tiny_agents.to_csv(d / AGENTS_FILE, index=False)
    fees.write_fees_csv(d / FEES_FILE, fees.fee_table("tou"))
    return d


@pytest.fixture
def tiny_origins() -> pd.DataFrame:
    rng = np.random.default_rng(12345)
    n = 60
    corr = np.arange(n) % N_TINY_CORRIDORS
    to_gate = rng.uniform(8.0, 45.0, n).round(2)
    return pd.DataFrame({
        "origin_id": np.arange(n),
        "x_nztm": rng.uniform(1740000.0, 1775000.0, n).round(1),
        "y_nztm": rng.uniform(5900000.0, 5935000.0, n).round(1),
        "weight": rng.uniform(0.5, 3.0, n).round(3),
        "corridor_id": corr,
        "gate_id": corr * 2 + (np.arange(n) // N_TINY_CORRIDORS) % 2,
        "fftt_to_gate_min": to_gate,
        "fftt_gate_to_dest_min": rng.uniform(1.0, 6.0, n).round(2),
        "path_km": (to_gate * 0.8).round(2),
    })


@pytest.fixture
def tiny_corridors_prep() -> pd.DataFrame:
    return pd.DataFrame({
        "corridor_id": [0, 1, 2],
        "name": ["North (Harbour Bridge)", "West (Great North Rd)", "South (Khyber Pass Rd)"],
        "n_gates": [2, 2, 2],
        "capacity_vph_raw": [5000.0, 3000.0, 2400.0],
        "bearing_deg": [10.0, 260.0, 160.0],
        "x_nztm": [1757000.0, 1755000.0, 1758500.0],
        "y_nztm": [5923000.0, 5920000.0, 5918000.0],
        "main_streets": ["Harbour Bridge", "Great North Rd", "Khyber Pass Rd"],
    })


@pytest.fixture
def tiny_personas() -> list[Persona]:
    out: list[Persona] = []
    for r in _agent_rows():
        i = r["agent_id"]
        arch = 1 + i % 5
        total = r["fftt_to_gate_min"] + r["fftt_gate_to_dest_min"]
        out.append(Persona(
            agent_id=i, origin_id=i, corridor_id=r["corridor_id"],
            x_nztm=r["x"], y_nztm=r["y"],
            fftt_to_gate_min=r["fftt_to_gate_min"], fftt_gate_to_dest_min=r["fftt_gate_to_dest_min"],
            path_km=round(total * 0.8, 2),
            vot=8.0 + 2.0 * i, vot_quintile=1 + i // 4,
            archetype=arch, activity="study" if arch == 5 else "work",
            tstar_min=[525, 510, 450, 465, 555][arch - 1],
            fixed_start=arch in (2, 3), must_drive=arch == 4,
            sched_mult=[0.5, 1.0, 1.5, 0.75, 0.5][arch - 1],
            pt_allowed=arch != 4, wfh_allowed=arch == 1, company_car=(arch == 4 and i % 2 == 1),
            parking_cost=[8.0, 0.0, 8.0, 0.0, 6.0][arch - 1],
            pt_time_min=round(1.6 * total + 10.0, 2), pt_fare=7.0,
            H=1 + i % 5, F=1 + (i * 2) % 5, P=1 + (i * 3) % 5, S=1 + (i * 4) % 5,
        ))
    return out


@pytest.fixture
def tiny_plans() -> pd.DataFrame:
    modes = ["CAR", "CAR", "CAR", "PT", "CAR", "WFH", "CAR", "SKIP", "CAR", "CAR"] * 2
    departs = [360 + 15 * ((i * 5) % 16) for i in range(N_TINY_AGENTS)]
    return pd.DataFrame({
        "agent_id": np.arange(N_TINY_AGENTS, dtype=np.int64),
        "mode": modes,
        "depart_min": np.array(departs, dtype=np.int64),
    })


@pytest.fixture
def make_today() -> Callable[..., TodayInfo]:
    def _make(day: int, fee_active: bool = True, regime: str = "tou",
              public_delay: DelayProfile | None = None, disrupted: Iterable[int] = (),
              fee_changed_today: bool = False) -> TodayInfo:
        table = fees.fee_table(regime if fee_active else "none")
        return TodayInfo(
            day=day, fee_regime=regime, fee_active=fee_active, fee_by_minute=tuple(table),
            fee_changed_today=fee_changed_today,
            public_delay=public_delay if public_delay is not None else {c: () for c in range(N_TINY_CORRIDORS)},
            pt_disrupted_corridors=frozenset(disrupted), pt_disruption_announced=True,
            pt_disruption_time_mult=2.0,
        )
    return _make
