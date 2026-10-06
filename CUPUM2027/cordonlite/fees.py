"""Cordon charge schedules.

The time-of-use (ToU) schedule is copied from the SSC2026 NetLogo model
(akl_pricing.nls, ``get-tou-fee``): piecewise linear in hours between fixed points,
evaluated here at minute resolution. The charge applies at the gate-exit minute
(cordon crossing time). Values are rounded to ``round_dp`` decimals so that the
table written to fees.csv and ``fee_at`` agree exactly (both engines read fees.csv).

Regimes: "tou" (piecewise linear), "flat" (``fee_flat`` all day), "none" (zero).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence

MINUTES_PER_DAY: int = 1440

TOU_POINTS: tuple[tuple[float, float], ...] = (
    (0.0, 2.0), (5.5, 2.0), (6.0, 4.0), (7.5, 4.0), (8.0, 6.0), (9.0, 6.0), (9.5, 4.0),
    (15.5, 4.0), (16.0, 6.0), (18.0, 6.0), (18.5, 4.0), (20.5, 4.0), (21.0, 2.0), (24.0, 2.0),
)
DEFAULT_FLAT: float = 6.0
DEFAULT_ROUND_DP: int = 4
REGIMES: tuple[str, ...] = ("tou", "flat", "none")


def _tou_hours(t: float, points: Sequence[Sequence[float]]) -> float:
    """SSC2026 get-tou-fee at decimal hour t (same loop, same fallback of the last point)."""
    for (t1, f1), (t2, f2) in zip(points[:-1], points[1:]):
        if t1 <= t < t2:
            if t2 == t1:
                return float(f1)
            return float(f1) + ((t - t1) / (t2 - t1)) * (float(f2) - float(f1))
    return float(points[-1][1])


def fee_at(minute: float, regime: str = "tou", *, fee_flat: float = DEFAULT_FLAT,
           points: Sequence[Sequence[float]] = TOU_POINTS,
           round_dp: int = DEFAULT_ROUND_DP) -> float:
    """Charge (NZ$) for a cordon crossing at ``minute`` since midnight under ``regime``.

    Minutes outside 0..1439 wrap around the day. Does not know about fee_start_day:
    callers decide whether the charge is active today.
    """
    if regime == "none":
        return 0.0
    if regime == "flat":
        return round(float(fee_flat), round_dp)
    if regime != "tou":
        raise ValueError(f"unknown fee regime: {regime!r}")
    m = float(minute) % MINUTES_PER_DAY
    return round(_tou_hours(m / 60.0, points), round_dp)


def fee_table(regime: str = "tou", *, fee_flat: float = DEFAULT_FLAT,
              points: Sequence[Sequence[float]] = TOU_POINTS,
              round_dp: int = DEFAULT_ROUND_DP) -> list[float]:
    """Fees for integer minutes 0..1439 (index = minute)."""
    return [fee_at(m, regime, fee_flat=fee_flat, points=points, round_dp=round_dp)
            for m in range(MINUTES_PER_DAY)]


def fee_table_from_config(cfg, regime: str | None = None) -> list[float]:
    """fee_table using a Config's [fees] section (regime defaults to cfg.fees.regime)."""
    f = cfg.fees
    return fee_table(regime or f.regime, fee_flat=f.fee_flat, points=f.tou_points, round_dp=f.round_dp)


def fee_active(day: int, regime: str, fee_start_day: int) -> bool:
    """True when a charge is levied on ``day`` (1-based)."""
    return regime != "none" and day >= fee_start_day


def write_fees_csv(path: str | Path, table: Sequence[float], round_dp: int = DEFAULT_ROUND_DP) -> Path:
    """Write fees.csv with columns minute, fee (fixed decimals, exact round-trip)."""
    path = Path(path)
    if len(table) != MINUTES_PER_DAY:
        raise ValueError("fee table must have 1440 entries")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["minute", "fee"])
        for m, v in enumerate(table):
            w.writerow([m, f"{v:.{round_dp}f}"])
    return path


def read_fees_csv(path: str | Path) -> list[float]:
    """Read fees.csv back into a 1440-entry list."""
    out = [0.0] * MINUTES_PER_DAY
    seen = 0
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            out[int(row["minute"])] = float(row["fee"])
            seen += 1
    if seen != MINUTES_PER_DAY:
        raise ValueError(f"fees.csv has {seen} rows, expected 1440")
    return out


def max_table_change(a: Sequence[float], b: Sequence[float]) -> float:
    """Largest absolute per-minute difference between two fee tables (for trigger T2)."""
    return max(abs(x - y) for x, y in zip(a, b, strict=True))


def describe_schedule(table: Sequence[float], start_min: int, end_min: int,
                      step_min: int = 15) -> list[tuple[int, float]]:
    """(minute, fee) pairs on a grid, e.g. for showing the charge by crossing time in prompts."""
    return [(m, float(table[m])) for m in range(start_min, end_min + 1, step_min)]
