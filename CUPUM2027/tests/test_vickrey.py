"""Vickrey (1969) bottleneck equilibrium: closed forms and internal consistency."""

from __future__ import annotations

import numpy as np
import pytest

from cordonlite.vickrey import (departure_rate, equilibrium, equilibrium_from_ratios, private_cost,
                               queue_delay, queue_length)


def test_textbook_values() -> None:
    # alpha 1, beta 0.5, gamma 2: delta = 1 / 2.5 = 0.4; N = 6000, s = 100/min -> N/s = 60
    r = equilibrium(6000, 100, 1.0, 0.5, 2.0, t_star=480.0)
    assert r.delta == pytest.approx(0.4)
    assert r.rush_len == pytest.approx(60.0)
    assert r.cost_per_commuter == pytest.approx(24.0)
    assert r.total_cost == pytest.approx(144000.0)
    assert r.t_first == pytest.approx(480 - 0.8 * 60)
    assert r.t_last == pytest.approx(480 + 0.2 * 60)
    assert r.rate_early == pytest.approx(200.0)
    assert r.rate_late == pytest.approx(100 / 3)
    assert r.max_delay == pytest.approx(24.0)
    assert r.t_tilde == pytest.approx(456.0)


def test_departures_sum_to_n_and_cost_constant() -> None:
    r = equilibrium_from_ratios(300, 5.0, 20.0, 0.61, 2.38, t_star=510.0)
    n = r.rate_early * (r.t_tilde - r.t_first) + r.rate_late * (r.t_last - r.t_tilde)
    assert n == pytest.approx(r.N)
    t = np.linspace(r.t_first, r.t_last, 401)
    c = private_cost(r, t)
    assert np.allclose(c, r.cost_per_commuter)
    # departing outside the rush hour costs more (pure schedule delay)
    assert private_cost(r, np.array([r.t_first - 5]))[0] > r.cost_per_commuter
    assert private_cost(r, np.array([r.t_last + 5]))[0] > r.cost_per_commuter


def test_queue_profile() -> None:
    r = equilibrium(6000, 100, 1.0, 0.5, 2.0, t_star=480.0)
    t = np.array([r.t_first - 1, r.t_first, r.t_tilde, r.t_last, r.t_last + 1])
    d = queue_delay(r, t)
    assert d.tolist() == pytest.approx([0.0, 0.0, r.max_delay, 0.0, 0.0])
    assert np.allclose(queue_length(r, t), r.s * d)
    grid = np.linspace(r.t_first, r.t_last, 1001)
    assert grid[np.argmax(queue_delay(r, grid))] == pytest.approx(r.t_tilde, abs=0.2)
    # the on-time departure arrives exactly at t_star
    assert r.t_tilde + r.max_delay == pytest.approx(r.t_star)


def test_fluid_queue_matches_analytic() -> None:
    """A fluid point queue fed with the equilibrium departure rates reproduces the queue profile."""
    r = equilibrium(6000, 100, 1.0, 0.5, 2.0, t_star=480.0)
    dt = 0.01
    t = np.arange(r.t_first, r.t_last, dt)
    q = 0.0
    qs = []
    for rate in departure_rate(r, t + dt / 2):
        q = max(0.0, q + (rate - r.s) * dt)
        qs.append(q)
    assert np.allclose(np.array(qs), queue_length(r, t + dt), atol=1.0)
    assert qs[-1] == pytest.approx(0.0, abs=1.0)


def test_from_ratios_uses_per_minute_alpha() -> None:
    r = equilibrium_from_ratios(100, 2.0, 60.0)
    assert r.alpha == pytest.approx(1.0) and r.beta == pytest.approx(0.61) and r.gamma == pytest.approx(2.38)
    assert r.cost_per_commuter == pytest.approx(0.61 * 2.38 / (0.61 + 2.38) * 50.0)


@pytest.mark.parametrize("args", [(0, 1, 1, 0.5, 2), (10, 0, 1, 0.5, 2), (10, 1, 1, 1.0, 2), (10, 1, 1, 0.5, 0)])
def test_invalid(args) -> None:
    with pytest.raises(ValueError):
        equilibrium(*args)
