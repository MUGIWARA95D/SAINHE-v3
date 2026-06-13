"""BLOC 4 Portfolio — Stress tests historiques (.txt §4 + audit points 43-47).
Rejouer le portefeuille ACTUEL sur les régimes de stress passés :
  GFC 2008 / COVID mars 2020 / Taper Tantrum 2013 / Volmageddon fév 2018 / hike cycle 2022.
Output : drawdown rejoué + durée de récupération par scénario.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

SCENARIOS = {
    "GFC_2008":         ("2008-09-01", "2009-03-31"),
    "COVID_2020":       ("2020-02-19", "2020-04-30"),
    "Taper_Tantrum_2013": ("2013-05-22", "2013-09-30"),
    "Volmageddon_2018": ("2018-02-01", "2018-02-15"),
    "Hike_Cycle_2022":  ("2022-01-01", "2022-10-31"),
}


def _portfolio_returns(prices: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    cols = [t for t in weights if t in prices.columns]
    w = np.array([weights[t] for t in cols])
    w = w / w.sum()
    return (prices[cols].pct_change().dropna() * w).sum(axis=1)


def replay_scenario(prices: pd.DataFrame, weights: dict[str, float],
                    start: str, end: str) -> dict:
    """Cumule les returns du portefeuille actuel sur la fenêtre du scénario."""
    rets = _portfolio_returns(prices, weights)
    win = rets.loc[start:end]
    if win.empty:
        return {"available": False, "note": f"pas de données entre {start} et {end}"}
    eq = (1 + win).cumprod()
    peak = eq.cummax()
    dd = ((eq - peak) / peak).min()
    final = eq.iloc[-1] - 1
    # Durée de récupération : combien de jours après end pour revenir au peak ?
    after = rets.loc[end:]
    recovery_days = None
    if len(after) > 1:
        eq_after = (1 + after).cumprod() * eq.iloc[-1]
        target = peak.iloc[-1] if len(peak) else 1.0
        recovered = eq_after[eq_after >= target]
        if len(recovered):
            recovery_days = int((recovered.index[0] - pd.Timestamp(end)).days)
    return {"available": True, "start": start, "end": end,
            "scenario_return": float(final),
            "max_drawdown_during": float(dd),
            "recovery_days_after": recovery_days,
            "n_days": int(len(win))}


def run_all(prices: pd.DataFrame, weights: dict[str, float]) -> dict:
    """Tous les scénarios. Format : 5 cartes horizontales pour le front (.txt §4)."""
    return {name: replay_scenario(prices, weights, s, e)
            for name, (s, e) in SCENARIOS.items()}
