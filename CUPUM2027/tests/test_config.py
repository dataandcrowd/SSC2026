"""Tests for cordonlite.config."""

from __future__ import annotations

import tomllib

import pytest

from cordonlite.config import ConfigError, dump_toml, load_config, stream


def test_loads_default() -> None:
    cfg = load_config()
    assert cfg.run.n_agents == 950 and cfg.run.n_days == 10       # 10-day design since 2026-10-15; 5% of the 19,000 charged vehicles
    assert cfg.run.n_agents / cfg.engine.agents_represented == 0.05
    assert cfg.persona.n_twins == 95 == cfg.run.n_agents // 10      # twins stay 10% of the agents
    assert cfg.engine.min_capacity_vph == 950.0
    assert cfg.fees.fee_start_day == 6                       # 10-day design since 2026-10-15 (11 before)
    assert cfg.llm.mock.w_fee > 0
    assert cfg.resolve_path(cfg.prep.roads_gpkg).name == "tomtom_major_roads.gpkg"


def test_overrides_and_errors() -> None:
    cfg = load_config(overrides={"run.n_agents": 20, "llm.mock.noise_sigma": 0.0})
    assert cfg.run.n_agents == 20 and cfg.llm.mock.noise_sigma == 0.0
    with pytest.raises(ConfigError):
        load_config(overrides={"run.nope": 1})
    with pytest.raises(ConfigError):
        load_config(overrides={"run.arm": "X"})


def test_pt_disruption_day_takes_one_day_or_a_list() -> None:
    """events.pt_disruption_day is one day or a list of days (2026-10-13): disruption_days is the tuple,
    a list survives the config snapshot, and anything else is refused."""
    assert load_config().events.disruption_days == (0,)   # 0 = no disruption in the 10-day design (2026-10-15)
    one = load_config(overrides={"events.pt_disruption_day": 8})
    assert one.events.pt_disruption_day == 8 and one.events.disruption_days == (8,)
    two = load_config(overrides={"events.pt_disruption_day": [3, 8]})
    assert two.events.disruption_days == (3, 8)
    assert tomllib.loads(dump_toml(two))["events"]["pt_disruption_day"] == [3, 8]
    for bad in ([], [3.5], "3", [True]):
        with pytest.raises(ConfigError):
            load_config(overrides={"events.pt_disruption_day": bad})


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


def test_peak_fee_key() -> None:
    """fees.peak_fee (NZ$, 2026-10-09): 6.0 in config.toml and as the dataclass default; must be >= 0 (0 = no
    charge); fees.scale and fees.fee_flat are retired (overriding them is an error)."""
    import dataclasses

    from cordonlite.config import FeesConfig

    cfg = load_config()
    assert cfg.fees.peak_fee == 6.0 and not hasattr(cfg.fees, "scale") and not hasattr(cfg.fees, "fee_flat")
    assert {f.name: f.default for f in dataclasses.fields(FeesConfig)}["peak_fee"] == 6.0
    assert load_config(overrides={"fees.peak_fee": 12}).fees.peak_fee == 12.0      # an int is taken as a float
    assert load_config(overrides={"fees.peak_fee": 0}).fees.peak_fee == 0.0
    with pytest.raises(ConfigError, match="fees.peak_fee"):
        load_config(overrides={"fees.peak_fee": -1.0})
    for retired in ("fees.scale", "fees.fee_flat"):
        with pytest.raises(ConfigError, match=retired):
            load_config(overrides={retired: 2.0})
    with pytest.raises(ConfigError, match="tou_points"):
        load_config(overrides={"fees.tou_points": [[0.0, 0.0], [24.0, 0.0]]})


def _old_fees(text: str, extra: list[str], regime: str = "tou") -> str:
    """A config_snapshot.toml of an earlier version: no peak_fee, the [fees] lines in ``extra`` instead."""
    out = []
    for ln in text.splitlines():
        if ln.startswith("peak_fee = "):
            out += extra
        elif ln.startswith("regime = "):
            out.append(f'regime = "{regime}"')
        else:
            out.append(ln)
    return "\n".join(out) + "\n"


def test_snapshot_without_added_keys_loads(tmp_path) -> None:
    """A config_snapshot.toml written before 2026-10-09 lacks run.compress_csv_over_mb and fees.peak_fee and
    has fees.fee_flat: it loads with the default and with peak_fee = the peak it charged (fee_flat for regime
    "flat", else the highest tou_points charge), and can be overridden; any other missing key is an error.
    One of the same day's charge multiplier (fees.scale) loads with peak_fee = scale x that peak."""
    text = dump_toml(load_config())
    assert "peak_fee = 6.0" in text and "fee_flat" not in text and "\nscale = " not in text
    old = _old_fees("\n".join(ln for ln in text.splitlines() if not ln.startswith("compress_csv_over_mb = ")),
                    ["fee_flat = 6.0"])
    assert old != text and "peak_fee" not in old
    p = tmp_path / "config_snapshot.toml"
    p.write_text(old, encoding="utf-8")
    cfg = load_config(p)
    assert cfg.fees.peak_fee == 6.0 and cfg.run.compress_csv_over_mb == 100.0
    assert cfg.to_dict() == load_config().to_dict()
    assert load_config(p, overrides={"fees.peak_fee": 12.0}).fees.peak_fee == 12.0
    with pytest.raises(ConfigError, match="fees.scale"):
        load_config(p, overrides={"fees.scale": 2.0})
    for extra, regime, peak in ((["fee_flat = 6.0", "scale = 3.0"], "tou", 18.0),
                                (["fee_flat = 6.0", "scale = 5.0"], "tou", 30.0),
                                (["fee_flat = 7.5", "scale = 2.0"], "flat", 15.0),
                                (["fee_flat = 7.5"], "flat", 7.5),
                                (["fee_flat = 6.0", "scale = 1.0"], "none", 6.0)):
        p.write_text(_old_fees(text, extra, regime), encoding="utf-8")
        c = load_config(p)
        assert (c.fees.peak_fee, c.fees.regime) == (peak, regime), extra
    p.write_text("\n".join(ln for ln in old.splitlines() if not ln.startswith("round_dp = ")), encoding="utf-8")
    with pytest.raises(ConfigError, match=r"\[fees\] missing keys: \['round_dp'\]"):
        load_config(p)
    p.write_text("\n".join(ln for ln in text.splitlines() if not ln.startswith("peak_fee = ")), encoding="utf-8")
    with pytest.raises(ConfigError, match=r"\[fees\] missing keys: \['peak_fee'\]"):
        load_config(p)        # the current file format: peak_fee is required


def test_snapshot_before_skip_removal_and_wtt_loads(tmp_path) -> None:
    """2026-10-09: a config_snapshot.toml written before SKIP was removed still has costs.skip_cost,
    costs.skip_vot_hours and llm.mock.w_skip (dropped on loading), has no [wtt] section (loaded with the
    defaults: beta0 0, no willingness-to-pay limit) and names template cl-v2 (accepted for loading; the
    LLM decider renders cl-v3 only). Overriding a retired key is an error."""
    import dataclasses

    from cordonlite import llm
    from cordonlite.config import TEMPLATE_ID, WttConfig

    cur = load_config()
    assert TEMPLATE_ID == "cl-v3" == cur.llm.template_id
    assert not any(hasattr(cur.costs, k) for k in ("skip_cost", "skip_vot_hours"))
    assert not hasattr(cur.llm.mock, "w_skip")
    old = []
    for ln in dump_toml(cur).splitlines():
        if ln == "[wtt]" or ln.startswith(("beta0 = ", "beta_clip = ", "vot_ref = ")):
            continue
        old.append(ln.replace('"cl-v3"', '"cl-v2"'))
        if ln.startswith("wfh_cost = "):
            old += ["skip_cost = 30.0", "skip_vot_hours = 1.0"]
        if ln.startswith("w_wfh = "):
            old.append("w_skip = 1.0")
    text = "\n".join(old) + "\n"
    assert "[wtt]" not in text and "skip_cost = 30.0" in text and "w_skip = 1.0" in text
    p = tmp_path / "config_snapshot.toml"
    p.write_text(text, encoding="utf-8")
    cfg = load_config(p)
    assert cfg.wtt == WttConfig() and cfg.wtt.beta0 == 0.0 and cfg.llm.template_id == "cl-v2"
    assert dataclasses.replace(cfg, wtt=cur.wtt, llm=cur.llm).to_dict() == cur.to_dict()
    assert load_config(p, overrides={"wtt.beta0": 0.8}).wtt.beta0 == 0.8
    with pytest.raises(ConfigError, match="costs.skip_cost"):
        load_config(p, overrides={"costs.skip_cost": 25.0})
    with pytest.raises(ValueError, match="cl-v3"):
        llm.LLMDecider(cfg, llm.MockLLM(cfg), None, tmp_path / "llm_calls.jsonl", None)  # type: ignore[arg-type]
    with pytest.raises(ConfigError, match="template_id"):
        load_config(overrides={"llm.template_id": "cl-v9"})
