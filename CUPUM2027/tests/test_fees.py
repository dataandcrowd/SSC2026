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
    assert fees.fee_at(500, "flat", peak_fee=7.5) == 7.5
    assert fees.fee_at(500, "flat") == 6.0                                   # the points' peak
    assert fees.fee_at(500, "none") == 0.0
    assert set(fees.fee_table("none")) == {0.0}
    assert set(fees.fee_table("flat", peak_fee=3.0)) == {3.0}


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
    assert fees.fee_table_from_config(cfg, "flat") == [cfg.fees.peak_fee] * 1440 == [6.0] * 1440


def test_fee_active_and_change() -> None:
    assert not fees.fee_active(10, "tou", 11)
    assert fees.fee_active(11, "tou", 11)
    assert not fees.fee_active(20, "none", 11)
    # peak_fee 0 levies nothing: the regime actually levied is "none"
    assert fees.levied_regime("tou", 0.0) == fees.levied_regime("flat", 0) == "none"
    assert fees.levied_regime("tou", 3.0) == "tou" and fees.levied_regime("none", 6.0) == "none"
    assert not fees.fee_active(20, fees.levied_regime("tou", 0.0), 11)
    assert fees.max_table_change(fees.fee_table("none"), fees.fee_table("tou")) == 6.0


def test_describe_schedule() -> None:
    sched = fees.describe_schedule(fees.fee_table("tou"), 360, 600, 60)
    assert sched == [(360, 4.0), (420, 4.0), (480, 6.0), (540, 6.0), (600, 4.0)]


def test_peak_fee_scales_the_schedule() -> None:
    """fees.peak_fee is the schedule's highest charge: every ToU charge is multiplied by peak_fee / 6 before
    the table is built (rounding as for the points as given); NZ$6 gives the SSC2026 schedule unchanged and
    NZ$12, 18, 30 the tables of the retired multiplier 2, 3, 5; 0 gives a table of zeros."""
    six = fees.fee_table_from_config(load_config())
    assert six == fees.fee_table("tou") == fees.fee_table("tou", peak_fee=6.0)
    assert fees.peak_points(fees.TOU_POINTS, 6.0) == fees.TOU_POINTS and fees.schedule_peak(fees.TOU_POINTS) == 6.0
    twelve = fees.fee_table_from_config(load_config(overrides={"fees.peak_fee": 12.0}))
    assert all(abs(b - 2.0 * a) <= 1e-4 + 1e-12 for a, b in zip(six, twelve, strict=True))
    assert max(twelve) == 12.0 and min(twelve) == 4.0
    assert twelve == fees.fee_table("tou", points=[(h, 2.0 * f) for h, f in fees.TOU_POINTS])
    assert all(twelve[m] == fees.fee_at(m, "tou", peak_fee=12.0) for m in range(0, 1440, 7))
    three = fees.fee_table_from_config(load_config(overrides={"fees.peak_fee": 3}))   # an int is taken as NZ$
    assert max(three) == 3.0 and min(three) == 1.0 and three[480] == 3.0
    thirty = load_config(overrides={"fees.peak_fee": 30})
    assert max(fees.fee_table_from_config(thirty)) == 30.0                    # about London's daily charge
    assert fees.fee_table_from_config(thirty, "flat") == [30.0] * 1440
    assert set(fees.fee_table_from_config(thirty, "none")) == {0.0}
    zero = load_config(overrides={"fees.peak_fee": 0.0})
    assert fees.fee_table_from_config(zero) == fees.fee_table("none") == fees.fee_table_from_config(zero, "flat")
    # points with another peak are scaled to peak_fee as well; None keeps them as given
    pts = [(0.0, 2.0), (12.0, 8.0), (24.0, 2.0)]
    assert fees.fee_at(720, "tou", points=pts) == 8.0 and fees.fee_at(720, "tou", peak_fee=4.0, points=pts) == 4.0
    with pytest.raises(ValueError):
        fees.peak_points([(0.0, 0.0), (24.0, 0.0)], 6.0)
