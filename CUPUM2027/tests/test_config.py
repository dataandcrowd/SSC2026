"""Tests for cordonlite.config."""

from __future__ import annotations

import tomllib

import pytest

from cordonlite.config import ConfigError, dump_toml, load_config, stream


def test_loads_default() -> None:
    cfg = load_config()
    assert cfg.run.n_agents == 300 and cfg.run.n_days == 30
    assert cfg.fees.fee_start_day == 11
    assert cfg.llm.mock.w_fee > 0
    assert cfg.resolve_path(cfg.prep.roads_gpkg).name == "tomtom_major_roads.gpkg"


def test_overrides_and_errors() -> None:
    cfg = load_config(overrides={"run.n_agents": 20, "llm.mock.noise_sigma": 0.0})
    assert cfg.run.n_agents == 20 and cfg.llm.mock.noise_sigma == 0.0
    with pytest.raises(ConfigError):
        load_config(overrides={"run.nope": 1})
    with pytest.raises(ConfigError):
        load_config(overrides={"run.arm": "X"})


def test_frozen() -> None:
    cfg = load_config()
    with pytest.raises(Exception):
        cfg.run.seed = 1  # type: ignore[misc]


def test_dump_round_trip() -> None:
    cfg = load_config(overrides={"run.seed": 5})
    again = tomllib.loads(dump_toml(cfg))
    assert again == cfg.to_dict()


def test_streams_deterministic_and_distinct() -> None:
    a1 = stream(11, "A").random(3)
    a2 = stream(11, "A").random(3)
    b = stream(11, "B").random(3)
    r = stream(11, "rule", 4, 12).random(3)
    r2 = stream(11, "rule", 4, 13).random(3)
    assert (a1 == a2).all()
    assert not (a1 == b).any()
    assert not (r == r2).any()


def test_fuel_cost_key() -> None:
    cfg = load_config(overrides={"costs.fuel_cost_per_km": 0.0})
    assert cfg.costs.fuel_cost_per_km == 0.0 and cfg.llm.mock.w_fuel == load_config().llm.mock.w_fuel
    with pytest.raises(ConfigError):
        load_config(overrides={"costs.fuel_cost_per_km": -0.1})
