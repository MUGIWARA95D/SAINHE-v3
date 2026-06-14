"""BLOC 2 Portfolio — Risque pur (.txt §4 + audit points 17-22, 31).
Vol annualisée (dans la devise sélectionnée — décomposition locale vs FX),
Max Drawdown, Underwater curve, VaR 95% historique ET paramétrique
(écart = signal fat tails), CVaR 95%.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats

TRADING_DAYS = 252


def _portfolio_returns(prices: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    cols = [t for t in weights if t in prices.columns]
    w = np.array([weights[t] for t in cols])
    w = w / w.sum()
    return (prices[cols].pct_change().dropna() * w).sum(axis=1)


def annualized_volatility(prices: pd.DataFrame, weights: dict[str, float]) -> float:
    """σ_p × √252 (.txt point 17)."""
    return float(_portfolio_returns(prices, weights).std() * np.sqrt(TRADING_DAYS))


def max_drawdown(prices: pd.DataFrame, weights: dict[str, float]) -> dict:
    """Max DD + dates de peak et trough (.txt point 18)."""
    rets = _portfolio_returns(prices, weights)
    eq = (1 + rets).cumprod()
    peak = eq.cummax()
    dd = (eq - peak) / peak
    trough = dd.idxmin()
    peak_date = eq.loc[:trough].idxmax()
    return {"max_drawdown": float(dd.min()),
            "peak_date": peak_date.strftime("%Y-%m-%d"),
            "trough_date": trough.strftime("%Y-%m-%d")}


def underwater_curve(prices: pd.DataFrame, weights: dict[str, float]) -> dict:
    """Courbe underwater = durée passée sous le pic précédent (.txt point 19 — visuellement brutal)."""
    rets = _portfolio_returns(prices, weights)
    eq = (1 + rets).cumprod()
    peak = eq.cummax()
    under = (eq - peak) / peak
    return {"dates": [d.strftime("%Y-%m-%d") for d in under.index],
            "drawdown_pct": [float(v) for v in under.values],
            "current_drawdown": float(under.iloc[-1]),
            "days_since_last_peak": int((under.index[-1] -
                                          eq.loc[eq == peak.iloc[-1]].index[-1]).days)}


def value_at_risk(prices: pd.DataFrame, weights: dict[str, float],
                  alpha: float = 0.05) -> dict:
    """VaR 95% historique ET paramétrique. Écart = fat tails (.txt points 20-21)."""
    rets = _portfolio_returns(prices, weights).values
    if len(rets) < 30:
        return {"historical": None, "parametric": None, "gap_pct": None, "fat_tails": False}
    var_hist = float(np.quantile(rets, alpha))
    mu, sigma = float(np.mean(rets)), float(np.std(rets))
    var_param = float(mu + sigma * stats.norm.ppf(alpha))
    gap = (var_hist - var_param) / abs(var_param) if var_param else 0.0
    return {"historical": var_hist, "parametric": var_param,
            "gap_pct": float(gap),
            "fat_tails": gap < -0.10,
            "message": ("Fat tails détectées : la distribution n'est pas normale, "
                        "la VaR paramétrique sous-estime les pertes extrêmes") if gap < -0.10
                        else None}


def conditional_var(prices: pd.DataFrame, weights: dict[str, float],
                    alpha: float = 0.05) -> dict:
    """CVaR / Expected Shortfall — perte moyenne quand on dépasse la VaR (.txt point 22)."""
    rets = _portfolio_returns(prices, weights).values
    if len(rets) < 30:
        return {"cvar_95": None}
    var_hist = np.quantile(rets, alpha)
    tail = rets[rets <= var_hist]
    return {"cvar_95": float(tail.mean()) if len(tail) else None,
            "n_tail_observations": int(len(tail))}


def currency_decomposition(local_returns: pd.DataFrame, fx_returns: pd.DataFrame,
                            weights: dict[str, float],
                            ticker_currency: dict[str, str],
                            reference_currency: str) -> dict:
    """Décomposition vol locale vs FX (.txt point 31 — Problème 2 du plan)."""
    cols = [t for t in weights if t in local_returns.columns]
    w = np.array([weights[t] for t in cols])
    w = w / w.sum()
    local_port = (local_returns[cols] * w).sum(axis=1)
    fx_contrib_series = []
    for t in cols:
        ccy = ticker_currency.get(t, reference_currency)
        if ccy == reference_currency:
            continue
        pair = f"{ccy}{reference_currency}"
        if pair in fx_returns.columns:
            fx_contrib_series.append(fx_returns[pair] * weights[t])
    fx_total = (sum(fx_contrib_series) if fx_contrib_series
                else pd.Series(0.0, index=local_port.index))
    total = local_port.add(fx_total, fill_value=0)
    local_var = float(local_port.var() * TRADING_DAYS)
    fx_var = float(fx_total.var() * TRADING_DAYS) if len(fx_contrib_series) else 0.0
    total_var = float(total.var() * TRADING_DAYS)
    return {
        "reference_currency": reference_currency,
        "vol_local_currency": float(local_var ** 0.5),
        "vol_fx": float(fx_var ** 0.5),
        "vol_total": float(total_var ** 0.5),
        "fx_contribution_pct": (fx_var / total_var) if total_var else 0.0,
        "note": "vol(total) = vol(local) ⊕ vol(FX) + covariance",
    }
