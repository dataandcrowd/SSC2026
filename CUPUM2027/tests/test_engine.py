"""PyEngine: hand-computed point-queue cases, validation, outputs; NetLogoEngine file plumbing (fake link)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cordonlite import fees
from cordonlite.engine import (
    AGENTS_FILE, CORRIDORS_FILE, FEES_FILE, OUTCOME_COLUMNS, PROFILE_COLUMNS,
    NetLogoEngine, PyEngine, make_engine, outcomes_file, plans_file, profile_file,
    simulate_point_queues,
)

START = 330  # config default sim_start_min
CAP = 720


def scenario(tmp_path: Path, caps: list[float], agents: list[tuple[int, int, int, int]], name: str = "s") -> Path:
    """agents: (agent_id, corridor_id, fftt_to_gate_min, fftt_gate_to_dest_min)."""
    d = tmp_path / name
    d.mkdir()
    pd.DataFrame({"corridor_id": range(len(caps)), "name": [f"C{k}" for k in range(len(caps))],
                  "capacity_per_min": caps, "x": [0.0] * len(caps), "y": [0.0] * len(caps)}
                 ).to_csv(d / CORRIDORS_FILE, index=False)
    pd.DataFrame([{"agent_id": a, "corridor_id": c, "fftt_to_gate_min": g, "fftt_gate_to_dest_min": t,
                   "x": 0.0, "y": 0.0} for a, c, g, t in agents]).to_csv(d / AGENTS_FILE, index=False)
    fees.write_fees_csv(d / FEES_FILE, fees.fee_table("tou"))
    return d


def plans(rows: list[tuple[int, str, int]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["agent_id", "mode", "depart_min"])


def engine(tiny_cfg, d: Path) -> PyEngine:
    e = PyEngine(tiny_cfg)
    e.load(d)
    return e


def exits(res) -> dict[int, int]:
    return dict(zip(res.outcomes["agent_id"], res.outcomes["gate_exit_min"]))


# ----------------------------------------------------------------- hand-computed queues

def test_capacity_one_idle_carry_allows_burst(tiny_cfg, tmp_path):
    # Idle gate: carry grows to the 1.0 cap, so at 400 available = 2 -> two served, third at 401.
    d = scenario(tmp_path, [1.0], [(0, 0, 10, 3), (1, 0, 10, 3), (2, 0, 10, 3)])
    r = engine(tiny_cfg, d).run_day(1, plans([(0, "CAR", 390), (1, "CAR", 390), (2, "CAR", 390)]), False)
    assert exits(r) == {0: 400, 1: 400, 2: 401}
    assert r.outcomes["queue_delay_min"].tolist() == [0, 0, 1]
    assert r.outcomes["arrive_min"].tolist() == [403, 403, 404]
    assert r.outcomes["gate_arrive_min"].tolist() == [400, 400, 400]
    assert r.profile["minute"].max() == 401  # stops after the last car is served


def test_capacity_half(tiny_cfg, tmp_path):
    # c = 0.5, three cars at 400 after an idle period (carry 1.0):
    # 400: avail 1.5 -> 1 served, carry 0.5; 401: avail 1.0 -> 1, carry 0.0 (queue not empty);
    # 402: avail 0.5 -> 0; 403: avail 1.0 -> 1.
    d = scenario(tmp_path, [0.5], [(0, 0, 10, 0), (1, 0, 10, 0), (2, 0, 10, 0)])
    r = engine(tiny_cfg, d).run_day(1, plans([(2, "CAR", 390), (0, "CAR", 390), (1, "CAR", 390)]), False)
    assert exits(r) == {0: 400, 1: 401, 2: 403}
    prof = r.profile.set_index("minute")
    assert prof.loc[400, ["arrivals", "served", "queue_len"]].tolist() == [3, 1, 2]
    assert prof.loc[401, ["arrivals", "served", "queue_len"]].tolist() == [0, 1, 1]
    assert prof.loc[402, ["arrivals", "served", "queue_len"]].tolist() == [0, 0, 1]
    assert prof.loc[403, ["arrivals", "served", "queue_len"]].tolist() == [0, 1, 0]


def test_arrival_at_sim_start_has_no_carry(tiny_cfg, tmp_path):
    # carry starts at 0: c = 0.5 at minute 330 gives avail 0.5 -> wait one minute.
    d = scenario(tmp_path, [0.5], [(0, 0, 10, 0)])
    eng = engine(tiny_cfg, d)
    r = eng.run_day(1, plans([(0, "CAR", 320)]), False)
    assert exits(r) == {0: 331}
    assert r.outcomes["queue_delay_min"].tolist() == [1]


def test_carry_capped_at_one_when_queue_empties(tiny_cfg, tmp_path):
    # c = 2.6. Car 0 alone at 400 (avail 1.0 + 2.6 = 3.6, serve 1, carry 2.6 -> capped 1.0).
    # Five cars at 401: avail 3.6 -> 3 served, carry 0.6; 402: avail 3.2 -> 2 served.
    agents = [(i, 0, 10, 0) for i in range(6)]
    d = scenario(tmp_path, [2.6], agents)
    rows = [(0, "CAR", 390)] + [(i, "CAR", 391) for i in range(1, 6)]
    r = engine(tiny_cfg, d).run_day(1, plans(rows), False)
    assert exits(r) == {0: 400, 1: 401, 2: 401, 3: 401, 4: 402, 5: 402}


def test_fifo_by_arrival_then_agent_id(tiny_cfg, tmp_path):
    # Agent 5 arrives first (399), then 1 and 3 tie at 400 (ascending id), c = 0.25.
    d = scenario(tmp_path, [0.25], [(1, 0, 20, 0), (3, 0, 20, 0), (5, 0, 9, 0)])
    r = engine(tiny_cfg, d).run_day(1, plans([(3, "CAR", 380), (5, "CAR", 390), (1, "CAR", 380)]), False)
    # 399 avail 1.25 -> agent 5, carry .25 (queue empty, < 1); 400 .5; 401 .75; 402 1.0 -> agent 1;
    # 403 .25; 404 .5; 405 .75; 406 1.0 -> agent 3
    assert exits(r) == {5: 399, 1: 402, 3: 406}


def test_float_capacity_accumulates_in_ieee_doubles(tiny_cfg, tmp_path):
    # c = 1/3 does not sum to exactly 1 after three minutes: 0.333.. + 0.333.. + 0.333.. after a
    # subtraction is 0.9999999999999998, so service slips a minute. Both engines share this
    # (identical double arithmetic); it is documented rather than corrected.
    ex, _, _ = simulate_point_queues([(0, 0, 0, 400), (1, 0, 0, 400), (2, 0, 0, 400)], [0], [1 / 3], START, CAP)
    # exact arithmetic would give 400, 402, 405
    assert ex == {0: 400, 1: 403, 2: 406}


def test_corridors_are_independent_and_empty_corridor_profiled(tiny_cfg, tmp_path):
    d = scenario(tmp_path, [1.0, 1.0, 0.25], [(0, 0, 5, 1), (1, 1, 5, 1), (2, 0, 5, 1)])
    r = engine(tiny_cfg, d).run_day(2, plans([(0, "CAR", 400), (1, "CAR", 400), (2, "CAR", 400)]), True)
    assert exits(r) == {0: 405, 1: 405, 2: 405}
    p = r.profile
    assert sorted(p["corridor_id"].unique().tolist()) == [0, 1, 2]
    per = p.groupby("corridor_id")["minute"].agg(["min", "max", "count"])
    assert (per["min"] == START).all() and (per["max"] == 405).all() and (per["count"] == 405 - START + 1).all()
    assert p.loc[p.corridor_id == 2, ["arrivals", "served", "queue_len"]].to_numpy().sum() == 0
    assert (p["day"] == 2).all()


def test_fee_at_gate_exit_minute(tiny_cfg, tmp_path):
    d = scenario(tmp_path, [1.0], [(0, 0, 10, 4), (1, 0, 10, 4), (2, 0, 10, 4)])
    eng = engine(tiny_cfg, d)
    p = plans([(0, "CAR", 440), (1, "CAR", 440), (2, "CAR", 440)])  # gate 450 (07:30), exits 450, 450, 451
    on = eng.run_day(11, p, True).outcomes
    table = fees.fee_table("tou")
    assert on["fee_paid"].tolist() == [table[450], table[450], table[451]]
    assert table[451] > table[450]  # ToU ramp from NZ$4 at 07:30 to NZ$6 at 08:00
    off = eng.run_day(10, p, False).outcomes
    assert off["fee_paid"].tolist() == [0.0, 0.0, 0.0]


def test_all_skip_day(tiny_cfg, tiny_scenario_dir, tiny_plans):
    eng = engine(tiny_cfg, tiny_scenario_dir)
    p = tiny_plans.assign(mode="SKIP")
    r = eng.run_day(4, p, True)
    assert len(r.outcomes) == 0 and list(r.outcomes.columns) == list(OUTCOME_COLUMNS)
    assert r.profile["minute"].tolist() == [START] * 3
    assert r.profile[["arrivals", "served", "queue_len"]].to_numpy().sum() == 0


def test_cap_marks_unserved_and_late_arrivals(tmp_path):
    cars = [(0, 0, 700, 715), (1, 0, 700, 715), (2, 0, 700, 730)]
    ex, prof, last = simulate_point_queues(cars, [0], [0.05], START, 720)
    # carry 1.0 at 715 -> agent 0 served at 715; agent 1 needs carry 1.0 again: 0.05*20 = 1.0 at 735 > cap
    assert ex == {0: 715}
    assert last == 720
    assert prof[-1] == (0, 720, 0, 0, 1)


def test_unserved_outcome_sentinels(tiny_cfg, tmp_path):
    d = scenario(tmp_path, [0.25], [(0, 0, 300, 5)])
    eng = engine(tiny_cfg, d)
    eng.sim_end_cap_min = 600  # depart 360 + 300 = gate 660 > cap
    r = eng.run_day(1, plans([(0, "CAR", 360)]), True)
    row = r.outcomes.iloc[0]
    assert (row["gate_exit_min"], row["queue_delay_min"], row["arrive_min"], row["fee_paid"]) == (-1, -1, -1, 0.0)
    assert r.profile["minute"].max() == 600


# ----------------------------------------------------------------- outputs and validation

def test_output_schema_and_conservation(tiny_cfg, tiny_scenario_dir, tiny_plans):
    eng = engine(tiny_cfg, tiny_scenario_dir)
    r = eng.run_day(3, tiny_plans, True)
    o, p = r.outcomes, r.profile
    assert list(o.columns) == list(OUTCOME_COLUMNS) and list(p.columns) == list(PROFILE_COLUMNS)
    assert all(str(o[c].dtype) == "int64" for c in OUTCOME_COLUMNS if c != "fee_paid")
    assert str(o["fee_paid"].dtype) == "float64"
    assert all(str(p[c].dtype) == "int64" for c in PROFILE_COLUMNS)
    n_car = int((tiny_plans["mode"] == "CAR").sum())
    assert len(o) == n_car and o["agent_id"].is_monotonic_increasing
    assert p["arrivals"].sum() == n_car and p["served"].sum() == n_car
    assert p.equals(p.sort_values(["corridor_id", "minute"]).reset_index(drop=True))
    assert (o["queue_delay_min"] >= 0).all()
    assert (o["gate_exit_min"] - o["gate_arrive_min"] == o["queue_delay_min"]).all()
    # queue length identity per corridor: cumulative arrivals - cumulative served
    for _, g in p.groupby("corridor_id"):
        assert (g["arrivals"].cumsum() - g["served"].cumsum() == g["queue_len"]).all()


def test_deterministic_and_order_invariant(tiny_cfg, tiny_scenario_dir, tiny_plans):
    eng = engine(tiny_cfg, tiny_scenario_dir)
    a = eng.run_day(3, tiny_plans, True)
    b = eng.run_day(3, tiny_plans.sample(frac=1.0, random_state=1), True)
    pd.testing.assert_frame_equal(a.outcomes, b.outcomes, check_exact=True)
    pd.testing.assert_frame_equal(a.profile, b.profile, check_exact=True)


def test_non_car_depart_may_be_missing_and_agents_may_be_absent(tiny_cfg, tiny_scenario_dir, tiny_plans):
    eng = engine(tiny_cfg, tiny_scenario_dir)
    p = tiny_plans.copy()
    p["depart_min"] = p["depart_min"].astype(float)
    p.loc[p["mode"] != "CAR", "depart_min"] = np.nan
    a = eng.run_day(3, p, True)
    b = eng.run_day(3, tiny_plans, True)
    pd.testing.assert_frame_equal(a.outcomes, b.outcomes)
    sub = eng.run_day(3, tiny_plans.iloc[:5], True)
    assert set(sub.outcomes["agent_id"]) <= set(range(5))


@pytest.mark.parametrize("bad,match", [
    (plans([(0, "CAR", 400), (0, "PT", 400)]), "duplicate"),
    (plans([(0, "BUS", 400)]), "invalid modes"),
    (plans([(99, "CAR", 400)]), "unknown agent_id"),
    (plans([(0, "CAR", 400.5)]), "non-integer"),
    (plans([(0, "CAR", 300)]), "before sim_start_min"),
    (pd.DataFrame({"agent_id": [0], "mode": ["CAR"]}), "lacks columns"),
])
def test_plan_validation(tiny_cfg, tmp_path, bad, match):
    d = scenario(tmp_path, [1.0], [(0, 0, 10, 0)])
    with pytest.raises(ValueError, match=match):
        engine(tiny_cfg, d).run_day(1, bad, False)


def test_run_before_load_and_make_engine(tiny_cfg, tiny_plans):
    with pytest.raises(RuntimeError):
        PyEngine(tiny_cfg).run_day(1, tiny_plans, False)
    assert isinstance(make_engine("py", tiny_cfg), PyEngine)
    assert isinstance(make_engine("netlogo", tiny_cfg), NetLogoEngine)  # lazy: no JVM started
    with pytest.raises(ValueError):
        make_engine("sumo", tiny_cfg)


def test_bad_scenario_files(tiny_cfg, tmp_path):
    d = scenario(tmp_path, [0.0], [(0, 0, 10, 0)])
    with pytest.raises(ValueError, match="capacity"):
        PyEngine(tiny_cfg).load(d)


# ----------------------------------------------------------------- NetLogoEngine plumbing (no JVM)

class FakeLink:
    """Stands in for pynetlogo.NetLogoLink: answers run-day with PyEngine and NetLogo-style CSVs."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.commands: list[str] = []
        self.loaded: list[str] = []
        self.py = PyEngine(cfg)

    def load_model(self, path: str) -> None:
        self.loaded.append(path)

    def command(self, cmd: str) -> None:
        self.commands.append(cmd)
        if cmd.startswith("setup-from-dir "):
            self.py.load(Path(cmd.split(" ", 1)[1].strip('"')))
        elif cmd.startswith("run-day "):
            head, rest = cmd[len("run-day "):].split(" ", 1)
            day = int(head)
            d, fee = rest.rsplit(" ", 1)
            d = Path(d.strip('"'))
            p = pd.read_csv(d / plans_file(day))
            r = self.py.run_day(day, p, fee == "true")
            # NetLogo writes integral numbers without ".0"
            r.outcomes.to_csv(d / outcomes_file(day), index=False)
            r.profile.to_csv(d / profile_file(day), index=False)


def test_netlogo_engine_file_exchange_with_fake_link(tiny_cfg, tiny_scenario_dir, tiny_plans):
    link = FakeLink(tiny_cfg)
    nl = NetLogoEngine(tiny_cfg, link=link)
    nl.load(tiny_scenario_dir)
    assert link.loaded == [str(tiny_cfg.resolve_path(tiny_cfg.engine.model_path))]
    assert link.commands[0] == f'setup-from-dir "{tiny_scenario_dir.resolve()}"'
    assert link.commands[1] == f"set-clock {tiny_cfg.time.sim_start_min} {tiny_cfg.time.sim_end_cap_min}"
    shuffled = tiny_plans.sample(frac=1.0, random_state=3)
    r = nl.run_day(7, shuffled, True)
    assert link.commands[-1] == f'run-day 7 "{tiny_scenario_dir.resolve()}" true'
    written = pd.read_csv(tiny_scenario_dir / "plans_day07.csv")
    assert list(written.columns) == ["agent_id", "mode", "depart_min"]
    assert written["agent_id"].is_monotonic_increasing
    ref = engine(tiny_cfg, tiny_scenario_dir).run_day(7, tiny_plans, True)
    pd.testing.assert_frame_equal(r.outcomes, ref.outcomes, check_exact=True)
    pd.testing.assert_frame_equal(r.profile, ref.profile, check_exact=True)
    nl.close()
    nl.close()  # safe twice


def test_netlogo_engine_validates_before_calling_netlogo(tiny_cfg, tiny_scenario_dir):
    link = FakeLink(tiny_cfg)
    nl = NetLogoEngine(tiny_cfg, link=link)
    nl.load(tiny_scenario_dir)
    n = len(link.commands)
    with pytest.raises(ValueError):
        nl.run_day(1, plans([(0, "CAR", 100)]), False)
    assert len(link.commands) == n


def test_netlogo_string_escaping():
    from cordonlite.engine import _nl_string

    assert _nl_string('/a b/"c"\\d') == '"/a b/\\"c\\"\\\\d"'
