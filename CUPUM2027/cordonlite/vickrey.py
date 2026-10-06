"""Analytical Vickrey (1969) single-bottleneck no-toll user equilibrium.

N identical commuters, bottleneck capacity s, value of time alpha, early penalty beta, late
penalty gamma (beta < alpha), desired arrival t_star, zero free-flow time (Vickrey 1969;
Arnott, de Palma and Lindsey 1990, 1993). With delta = beta * gamma / (beta + gamma):
    rush-hour length N / s, from t_first = t_star - gamma/(beta+gamma) * N/s
                             to   t_last  = t_star + beta/(beta+gamma)  * N/s
    equilibrium private cost per commuter delta * N / s
    departure rate s * alpha / (alpha - beta) before the on-time departure t_tilde,
                   s * alpha / (alpha + gamma) after it
    queueing delay D(t) = beta/(alpha-beta) (t - t_first) for t <= t_tilde,
                          gamma/(alpha+gamma) (t_last - t) for t >= t_tilde,
    peak delay D_max = delta * N / (alpha * s), t_tilde = t_star - D_max.
Units are consistent: if s is per minute and t in minutes, D is in minutes.

Public API:
    VickreyResult, equilibrium(N, s, alpha, beta, gamma, t_star=0.0),
    equilibrium_from_ratios(N, s, vot_per_h, beta_ratio, gamma_ratio, t_star=0.0)  # alpha per minute
    queue_delay(res, t), queue_length(res, t), departure_rate(res, t), private_cost(res, t)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class VickreyResult:
    N: float
    s: float
    alpha: float
    beta: float
    gamma: float
    t_star: float
    delta: float
    rush_len: float
    t_first: float
    t_last: float
    cost_per_commuter: float
    rate_early: float
    rate_late: float
    t_tilde: float = 0.0          # departure time of the commuter arriving exactly at t_star
    max_delay: float = 0.0        # queueing delay of that commuter

    @property
    def total_cost(self) -> float:
        return self.cost_per_commuter * self.N


def equilibrium(N: float, s: float, alpha: float, beta: float, gamma: float,
                t_star: float = 0.0) -> VickreyResult:
    """No-toll Vickrey equilibrium; requires N > 0, s > 0, 0 < beta < alpha, gamma > 0."""
    if not (N > 0 and s > 0 and alpha > 0 and gamma > 0 and 0 < beta < alpha):
        raise ValueError("need N > 0, s > 0, gamma > 0 and 0 < beta < alpha")
    delta = beta * gamma / (beta + gamma)
    rush = N / s
    t_first = t_star - gamma / (beta + gamma) * rush
    t_last = t_star + beta / (beta + gamma) * rush
    d_max = delta * rush / alpha
    return VickreyResult(
        N=float(N), s=float(s), alpha=float(alpha), beta=float(beta), gamma=float(gamma),
        t_star=float(t_star), delta=delta, rush_len=rush, t_first=t_first, t_last=t_last,
        cost_per_commuter=delta * rush, rate_early=s * alpha / (alpha - beta),
        rate_late=s * alpha / (alpha + gamma), t_tilde=t_star - d_max, max_delay=d_max,
    )


def equilibrium_from_ratios(N: float, s: float, vot_per_h: float, beta_ratio: float = 0.61,
                            gamma_ratio: float = 2.38, t_star: float = 0.0) -> VickreyResult:
    """Equilibrium with alpha = VoT per minute and Small (1982) ratios beta/alpha, gamma/alpha."""
    a = vot_per_h / 60.0
    return equilibrium(N, s, a, beta_ratio * a, gamma_ratio * a, t_star)


def queue_delay(res: VickreyResult, t: np.ndarray) -> np.ndarray:
    """Queueing delay for a departure at time t (0 outside the rush hour)."""
    t = np.asarray(t, dtype=float)
    early = res.beta / (res.alpha - res.beta) * (t - res.t_first)
    late = res.gamma / (res.alpha + res.gamma) * (res.t_last - t)
    d = np.where(t <= res.t_tilde, early, late)
    inside = (t >= res.t_first) & (t <= res.t_last)
    return np.where(inside, np.maximum(d, 0.0), 0.0)


def queue_length(res: VickreyResult, t: np.ndarray) -> np.ndarray:
    """Vehicles queued at departure time t (= s * queue_delay)."""
    return res.s * queue_delay(res, t)


def departure_rate(res: VickreyResult, t: np.ndarray) -> np.ndarray:
    """Equilibrium departure rate at time t."""
    t = np.asarray(t, dtype=float)
    r = np.where(t < res.t_tilde, res.rate_early, res.rate_late)
    return np.where((t >= res.t_first) & (t < res.t_last), r, 0.0)


def private_cost(res: VickreyResult, t: np.ndarray) -> np.ndarray:
    """Travel plus schedule-delay cost of departing at t (constant inside the rush hour)."""
    t = np.asarray(t, dtype=float)
    d = queue_delay(res, t)
    arr = t + d
    return (res.alpha * d + res.beta * np.maximum(0.0, res.t_star - arr)
            + res.gamma * np.maximum(0.0, arr - res.t_star))
