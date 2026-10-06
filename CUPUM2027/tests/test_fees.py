"""Tests for cordonlite.fees."""

from __future__ import annotations

import pytest

from cordonlite import fees
from cordonlite.config import load_config


@pytest.mark.parametrize(
    "minute, expected",
    [
        (0, 2.0), (329, 2.0), (330, 2.0), (345, 3.0), (360, 4.0), (420, 4.0), (450, 4.0),
        (465, 5.0), (480, 6.0), (510, 6.0), (539, 6.0), (540, 6.0), (555, 5.0), (570, 4.0),
        (930, 4.0), (945, 5.0), (960, 6.0), (1080, 6.0), (1110, 4.0), (1260, 2.0), (1439, 2.0),
    ],
)
def test_tou_known_points(minute: int, expected: float) -> None:
    assert fees.fee_at(minute, "tou") == pytest.approx(expected, abs=1e-9)


def test_tou_linear_ramp_is_monotone_and_rounded() -> None:
    ramp = [fees.fee_at(m, "tou") for m in range(450, 481)]
    assert ramp == sorted(ramp)
    assert fees.fee_at(451, "tou") == round(4.0 + 2.0 / 30.0, 4)


def test_wraps_day() -> None:
    assert fees.fee_at(1440 + 480, "tou") == fees.fee_at(480, "tou")


def test_flat_and_none() -> None:
    assert fees.fee_at(500, "flat", fee_flat=7.5) == 7.5
    assert fees.fee_at(500, "none") == 0.0
    assert set(fees.fee_table("none")) == {0.0}
    assert set(fees.fee_table("flat", fee_flat=3.0)) == {3.0}


def test_unknown_regime() -> None:
    with pytest.raises(ValueError):
        fees.fee_at(500, "cordon")


def test_table_shape_matches_fee_at() -> None:
    t = fees.fee_table("tou")
    assert len(t) == 1440
    assert all(t[m] == fees.fee_at(m, "tou") for m in range(0, 1440, 7))


def test_csv_round_trip_exact(tmp_path) -> None:
    t = fees.fee_table("tou")
    p = fees.write_fees_csv(tmp_path / "fees.csv", t)
    assert fees.read_fees_csv(p) == t
    head = p.read_text().splitlines()[:2]
    assert head == ["minute,fee", "0,2.0000"]


def test_config_table_equals_default() -> None:
    cfg = load_config()
    assert tuple(tuple(p) for p in cfg.fees.tou_points) == fees.TOU_POINTS
    assert fees.fee_table_from_config(cfg) == fees.fee_table("tou")
    assert fees.fee_table_from_config(cfg, "flat") == [cfg.fees.fee_flat] * 1440


def test_fee_active_and_change() -> None:
    assert not fees.fee_active(10, "tou", 11)
    assert fees.fee_active(11, "tou", 11)
    assert not fees.fee_active(20, "none", 11)
    assert fees.max_table_change(fees.fee_table("none"), fees.fee_table("tou")) == 6.0


def test_describe_schedule() -> None:
    sched = fees.describe_schedule(fees.fee_table("tou"), 360, 600, 60)
    assert sched == [(360, 4.0), (420, 4.0), (480, 6.0), (540, 6.0), (600, 4.0)]
