"""BLOC 4 Portfolio — Monte Carlo (.txt §4 + audit points 38-42).
10 000 simulations, horizons 1Y et 5Y, bootstrap historique par défaut (fat tails),
option t-Student df=5. Distribution P&L, proba perte > X%, time-to-recovery.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats

TRADING_DAYS = 252


def _portfolio_returns_series(prices: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    cols = [t for t in weights if t in prices.columns]
    w = np.array([weights[t] for t in cols])
    w = w / w.sum()
    return (prices[cols].pct_change().dropna() * w).sum(axis=1)


def _simulate_bootstrap(historical: np.ndarray, n_sims: int, horizon_days: int,
                         rng: np.random.Generator) -> np.ndarray:
    """Bootstrap historique : tire des returns observés (fat tails préservées)."""
    idx = rng.integers(0, len(historical), size=(n_sims, horizon_days))
    sampled = historical[idx]
    return np.cumprod(1 + sampled, axis=1)


def _simulate_t_student(historical: np.ndarray, n_sims: int, horizon_days: int,
                        df: int, rng: np.random.Generator) -> np.ndarray:
    """t-Student df=5 calibré sur μ et σ historiques (alternative paramétrique fat-tail)."""
    mu, sigma = float(np.mean(historical)), float(np.std(historical))
    samples = stats.t.rvs(df=df, loc=mu, scale=sigma, size=(n_sims, horizon_days),
                          random_state=rng.integers(2**31))
    return np.cumprod(1 + samples, axis=1)


def run(prices: pd.DataFrame, weights: dict[str, float],
        n_sims: int = 10_000, horizons_years: tuple = (1, 5),
        method: str = "bootstrap", seed: int = 42) -> dict:
    """Lance la simulation. method ∈ {'bootstrap', 't_student_df5'} (.txt anti-naïveté)."""
    rets = _portfolio_returns_series(prices, weights).values
    if len(rets) < 100:
        return {"available": False, "note": "moins de 100 jours de prix"}
    rng = np.random.default_rng(seed)
    out = {"available": True, "method": method, "n_sims": n_sims, "horizons": {}}
    for years in horizons_years:
        h = years * TRADING_DAYS
        if method == "bootstrap":
            paths = _simulate_bootstrap(rets, n_sims, h, rng)
        else:
            paths = _simulate_t_student(rets, n_sims, h, df=5, rng=rng)
        finals = paths[:, -1] - 1
        out["horizons"][f"{years}Y"] = {
            "percentiles": {f"p{p}": float(np.percentile(finals, p))
                            for p in (5, 25, 50, 75, 95)},
            "prob_loss_gt_10pct": float((finals < -0.10).mean()),
            "prob_loss_gt_20pct": float((finals < -0.20).mean()),
            "prob_loss_gt_30pct": float((finals < -0.30).mean()),
            "prob_loss_gt_50pct": float((finals < -0.50).mean()),
            "mean_final_return": float(finals.mean()),
            "time_to_recovery_distribution": _time_to_recovery(paths),
        }
    return out


def _time_to_recovery(paths: np.ndarray) -> dict:
    recovery_days = []
    for path in paths:
        peak_idx = np.argmax(path)
        peak_val = path[peak_idx]
        if peak_idx == len(path) - 1:
            continue
        post = path[peak_idx:]
        below = np.where(post < peak_val * 0.9)[0]
        if len(below) == 0:
            continue
        first_drop = below[0]
        after_drop = post[first_drop:]
        recovered = np.where(after_drop >= peak_val)[0]
        if len(recovered):
            recovery_days.append(int(first_drop + recovered[0]))
    if not recovery_days:
        return {"available": False}
    arr = np.array(recovery_days)
    return {"available": True, "n_paths_recovered": len(recovery_days),
            "p25_days": int(np.percentile(arr, 25)),
            "median_days": int(np.percentile(arr, 50)),
            "p75_days": int(np.percentile(arr, 75)),
            "max_days": int(arr.max())}
