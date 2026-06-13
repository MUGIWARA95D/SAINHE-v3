"""BLOC 1 Portfolio — Performance (.txt §4 + conv "rendement→risque→structure→futur").
Couvre les 16 premières métriques validées dans l'audit :
  Returns absolus (total, CAGR, calendaires, dividend yield)
  Attribution (holding / secteur GICS / géographie)
  Returns relatifs (Alpha Jensen, Tracking Error, Information Ratio)
  Risk-adjusted (Sharpe avec rf réel, Sortino, Calmar)
  Visualisation temporelle (cumulative vs bench, rolling 1Y, rolling Sharpe 252j)
"""
from __future__ import annotations
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _portfolio_series(prices: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Série de prix synthétique du portefeuille (rebal quotidienne implicite).
    prices : DataFrame index=date, columns=tickers ; weights : dict normalisé."""
    cols = [t for t in weights if t in prices.columns]
    w = np.array([weights[t] for t in cols])
    w = w / w.sum()
    rets = prices[cols].pct_change().dropna()
    port_rets = (rets * w).sum(axis=1)
    return (1 + port_rets).cumprod() * 100.0


def total_returns(prices: pd.DataFrame, weights: dict[str, float]) -> dict:
    """Returns cumulés 1Y/3Y/5Y + CAGR (.txt 4.1)."""
    p = _portfolio_series(prices, weights)
    out = {"cumulative": {}, "cagr": {}}
    for years in (1, 3, 5):
        days = years * TRADING_DAYS
        if len(p) > days:
            ret = p.iloc[-1] / p.iloc[-days] - 1
            out["cumulative"][f"{years}Y"] = float(ret)
            out["cagr"][f"{years}Y"] = float((1 + ret) ** (1 / years) - 1)
    return out


def calendar_year_returns(prices: pd.DataFrame, weights: dict[str, float]) -> dict[int, float]:
    """Returns par année calendaire (.txt point 6 — éviter le lissage CAGR qui cache un -40%)."""
    p = _portfolio_series(prices, weights)
    yearly = p.groupby(p.index.year).agg(["first", "last"])
    return {int(y): float(row["last"] / row["first"] - 1) for y, row in yearly.iterrows()}


def aggregate_dividend_yield(weights: dict[str, float],
                              per_ticker_yield: dict[str, float]) -> float | None:
    """Σ wᵢ × yieldᵢ (.txt point 6 — dividends souvent oubliés sur value/REITs)."""
    s, tot_w = 0.0, 0.0
    for t, w in weights.items():
        y = per_ticker_yield.get(t)
        if y is not None:
            s += w * y
            tot_w += w
    return (s / tot_w) if tot_w else None


def cumulative_curves(prices: pd.DataFrame, weights: dict[str, float],
                       benchmarks: pd.DataFrame) -> dict:
    """Courbe cumulative portefeuille vs benchmarks (SPY, ACWI superposés, point 5)."""
    p = _portfolio_series(prices, weights)
    p = p / p.iloc[0] * 100.0
    benches = {}
    for b in benchmarks.columns:
        bs = benchmarks[b].dropna()
        bs = bs.reindex(p.index, method="pad").dropna()
        if len(bs):
            benches[b] = (bs / bs.iloc[0] * 100.0).tolist()
    return {"dates": [d.strftime("%Y-%m-%d") for d in p.index],
            "portfolio": p.tolist(), "benchmarks": benches}


def rolling_metrics(prices: pd.DataFrame, weights: dict[str, float],
                    rf_annual: float) -> dict:
    """Rolling 1Y return + rolling Sharpe 252j (.txt points 7-8)."""
    p = _portfolio_series(prices, weights)
    daily = p.pct_change().dropna()
    rolling_ret = (p / p.shift(TRADING_DAYS) - 1).dropna()
    rf_daily = rf_annual / TRADING_DAYS
    excess = daily - rf_daily
    rolling_sharpe = (excess.rolling(TRADING_DAYS).mean() /
                      excess.rolling(TRADING_DAYS).std() * np.sqrt(TRADING_DAYS)).dropna()
    return {
        "rolling_return_1y": {d.strftime("%Y-%m-%d"): float(v)
                              for d, v in rolling_ret.tail(TRADING_DAYS).items()},
        "rolling_sharpe_252d": {d.strftime("%Y-%m-%d"): float(v)
                                for d, v in rolling_sharpe.tail(TRADING_DAYS).items()},
    }


def attribution(prices: pd.DataFrame, weights: dict[str, float],
                sector_map: dict[str, str] | None = None,
                geo_map: dict[str, str] | None = None,
                period_days: int = TRADING_DAYS) -> dict:
    """Attribution wᵢ × rᵢ (.txt points 9-11) par holding / secteur / géographie."""
    cols = [t for t in weights if t in prices.columns]
    rets = {}
    for t in cols:
        s = prices[t].dropna()
        if len(s) > period_days:
            rets[t] = float(s.iloc[-1] / s.iloc[-period_days] - 1)
        else:
            rets[t] = float(s.iloc[-1] / s.iloc[0] - 1) if len(s) > 1 else 0.0
    by_holding = {t: weights[t] * rets[t] for t in cols if t in rets}

    def _group(mapping):
        if not mapping:
            return {}
        agg = {}
        for t, c in by_holding.items():
            k = mapping.get(t, "Unknown")
            agg[k] = agg.get(k, 0.0) + c
        return agg

    return {"by_holding": by_holding,
            "by_sector": _group(sector_map),
            "by_geography": _group(geo_map)}


# ---------------------------------------------------------------- Risk-adjusted ratios (12-16)
def _excess_returns(prices_port: pd.Series, rf_annual: float) -> pd.Series:
    return prices_port.pct_change().dropna() - rf_annual / TRADING_DAYS


def sharpe(prices: pd.DataFrame, weights: dict[str, float], rf_annual: float) -> float:
    """Sharpe avec rf réel = 3M T-bill (.txt point 12 — PAS zéro)."""
    p = _portfolio_series(prices, weights)
    ex = _excess_returns(p, rf_annual)
    return float(ex.mean() / ex.std() * np.sqrt(TRADING_DAYS)) if ex.std() else 0.0


def sortino(prices: pd.DataFrame, weights: dict[str, float], rf_annual: float) -> float:
    """Sortino downside-only (.txt point 13)."""
    p = _portfolio_series(prices, weights)
    ex = _excess_returns(p, rf_annual)
    downside = ex[ex < 0]
    dd = downside.std() if len(downside) > 1 else None
    return float(ex.mean() / dd * np.sqrt(TRADING_DAYS)) if dd else 0.0


def calmar(prices: pd.DataFrame, weights: dict[str, float]) -> float:
    """Calmar = CAGR / Max Drawdown (.txt point 14 — le plus parlant non-quant)."""
    p = _portfolio_series(prices, weights)
    if len(p) < 2:
        return 0.0
    yrs = (p.index[-1] - p.index[0]).days / 365.25
    cagr = (p.iloc[-1] / p.iloc[0]) ** (1 / max(yrs, 1e-6)) - 1
    rolling_max = p.cummax()
    mdd = float(((p - rolling_max) / rolling_max).min())
    return float(cagr / abs(mdd)) if mdd else 0.0


def jensen_alpha_tracking_ir(prices: pd.DataFrame, weights: dict[str, float],
                              benchmark: pd.Series, rf_annual: float) -> dict:
    """Alpha Jensen, Tracking Error, Information Ratio (.txt points 15-16).
    Alpha = Rp - [Rf + β(Rm - Rf)] → "surperformance nettoyée de l'exposition marché"."""
    p = _portfolio_series(prices, weights).pct_change().dropna()
    b = benchmark.reindex(p.index).pct_change().dropna()
    common = p.index.intersection(b.index)
    p, b = p.loc[common], b.loc[common]
    rf_d = rf_annual / TRADING_DAYS
    if b.var() == 0:
        return {"alpha_annual": None, "tracking_error": None, "information_ratio": None}
    beta = float(np.cov(p, b, ddof=0)[0, 1] / b.var())
    alpha_daily = (p - rf_d).mean() - beta * (b - rf_d).mean()
    alpha_annual = float(alpha_daily * TRADING_DAYS)
    active = p - b
    te = float(active.std() * np.sqrt(TRADING_DAYS))
    ir = float(active.mean() * TRADING_DAYS / te) if te else None
    msg_ir = None
    if ir is not None and ir < 0:
        msg_ir = "IR négatif : un ETF passif aurait fait mieux"
    return {"alpha_annual": alpha_annual, "tracking_error": te,
            "information_ratio": ir, "ir_message": msg_ir, "beta_vs_bench": beta}
