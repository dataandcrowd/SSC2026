"""Sanity checks on the shared tiny-scenario fixtures."""

from __future__ import annotations

import pandas as pd

from cordonlite.engine import AGENTS_COLUMNS, CORRIDORS_COLUMNS
from cordonlite.fees import read_fees_csv


def test_tiny_scenario_files(tiny_scenario_dir) -> None:
    c = pd.read_csv(tiny_scenario_dir / "corridors.csv")
    a = pd.read_csv(tiny_scenario_dir / "agents.csv")
    assert tuple(c.columns) == CORRIDORS_COLUMNS and len(c) == 3
    assert tuple(a.columns) == AGENTS_COLUMNS and len(a) == 20
    assert len(read_fees_csv(tiny_scenario_dir / "fees.csv")) == 1440


def test_tiny_personas_match_agents(tiny_personas, tiny_agents, tiny_plans, make_today) -> None:
    for p, (_, r) in zip(tiny_personas, tiny_agents.iterrows()):
        assert (p.agent_id, p.corridor_id, p.fftt_to_gate_min) == (r.agent_id, r.corridor_id, r.fftt_to_gate_min)
    assert set(tiny_plans["mode"]) == {"CAR", "PT", "WFH", "SKIP"}
    t = make_today(3, fee_active=True)
    assert t.fee_by_minute[480] == 6.0 and len(t.fee_by_minute) == 1440
