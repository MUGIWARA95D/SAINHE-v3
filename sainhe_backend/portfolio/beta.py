"""BLOC 2 Portfolio — Beta complet (.txt §4 Beta + Problème 1 = instabilité).
Couvre points 23-28 :
  - Beta vs SPY ET ACWI (les deux affichés, jamais un seul)
  - Beta 1Y / 3Y / 5Y (instabilité)
  - Rolling beta 252j en sparkline (dérive visible)
  - Beta contribution par holding : w_i × β_i (3-5 tickers font 70% du beta)
  - Flag contamination si holding > 2% du benchmark + correction Dimson
  - Choix benchmark par défaut : ACWI ; SPY secondaire (.txt §4 critères benchmark)
"""
from __future__ import annotations
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def _pair_returns(asset: pd.Series, bench: pd.Series):
    """Returns alignés sur dates communes."""
    a = asset.pct_change().dropna()
    b = bench.pct_change().dropna()
    common = a.index.intersection(b.index)
    return a.loc[common], b.loc[common]


def beta_simple(asset: pd.Series, bench: pd.Series) -> float | None:
    a, b = _pair_returns(asset, bench)
    if len(a) < 30 or b.var() == 0:
        return None
    return float(np.cov(a, b, ddof=0)[0, 1] / b.var())


def beta_dimson(asset: pd.Series, bench: pd.Series) -> float | None:
    """Correction Dimson : β = β(t-1) + β(t) + β(t+1) — réduit le biais de synchronisation
    quand le ticker est gros constituant du benchmark (.txt point 27)."""
    a, b = _pair_returns(asset, bench)
    if len(a) < 60:
        return None
    df = pd.DataFrame({"a": a, "b": b, "b_lag": b.shift(1), "b_lead": b.shift(-1)}).dropna()
    if df["b"].var() == 0:
        return None
    # Régression multivariée a = α + β₋₁·b_lag + β₀·b + β₊₁·b_lead
    X = df[["b_lag", "b", "b_lead"]].values
    y = df["a"].values
    X_ = np.column_stack([np.ones(len(X)), X])
    coefs, *_ = np.linalg.lstsq(X_, y, rcond=None)
    return float(coefs[1] + coefs[2] + coefs[3])


def beta_multi_window(asset: pd.Series, bench: pd.Series) -> dict:
    """1Y / 3Y / 5Y — jamais 'le beta est X', toujours les 3 (.txt point 24, Problème 1)."""
    out = {}
    for years, key in [(1, "1Y"), (3, "3Y"), (5, "5Y")]:
        days = years * TRADING_DAYS
        if len(asset) > days:
            sub_a = asset.iloc[-days:]
            sub_b = bench.reindex(sub_a.index).ffill()
            out[key] = beta_simple(sub_a, sub_b)
        else:
            out[key] = None
    return out


def rolling_beta(asset: pd.Series, bench: pd.Series, window: int = TRADING_DAYS) -> dict:
    """Sparkline rolling 252j (.txt point 25 — la dérive du beta visible)."""
    a, b = _pair_returns(asset, bench)
    if len(a) < window:
        return {}
    cov = a.rolling(window).cov(b)
    var = b.rolling(window).var()
    rb = (cov / var).dropna()
    return {d.strftime("%Y-%m-%d"): float(v) for d, v in rb.tail(window).items()}


def contamination_check(ticker: str, benchmark_weights: dict[str, float] | None) -> dict:
    """Si ticker > 2% du benchmark → beta biaisé par circularité (.txt point 27)."""
    threshold = 0.02
    if not benchmark_weights or ticker not in benchmark_weights:
        return {"weight_in_benchmark": None, "contaminated": False, "applied_dimson": False}
    w = benchmark_weights[ticker]
    return {"weight_in_benchmark": w, "contaminated": w > threshold,
            "applied_dimson": w > threshold,
            "message": (f"{ticker} = {w:.1%} du benchmark — beta lissé via correction Dimson"
                        if w > threshold else None)}


def beta_contribution(prices: pd.DataFrame, weights: dict[str, float],
                      bench: pd.Series,
                      benchmark_weights: dict[str, float] | None = None) -> dict:
    """w_i × β_i par holding + identification top contributors qui font 70% du beta total.
    (.txt point 26 — le visuel le plus actionnable du bloc.)"""
    contribs = {}
    for t in weights:
        if t not in prices.columns:
            continue
        cont = contamination_check(t, benchmark_weights)
        # Dimson si contaminé, sinon simple
        b = (beta_dimson(prices[t], bench) if cont["contaminated"]
             else beta_simple(prices[t], bench))
        if b is None:
            continue
        contribs[t] = {"beta": b, "weight": weights[t],
                       "contribution": weights[t] * b, **cont}
    sorted_by_abs = sorted(contribs.items(),
                            key=lambda kv: abs(kv[1]["contribution"]), reverse=True)
    total_beta = sum(v["contribution"] for v in contribs.values())
    cum = 0.0
    top_70 = []
    for t, v in sorted_by_abs:
        cum += abs(v["contribution"])
        top_70.append(t)
        if total_beta and cum / abs(total_beta) >= 0.70:
            break
    return {"by_holding": contribs,
            "portfolio_beta": total_beta,
            "top_drivers_70pct": top_70,
            "note": f"{len(top_70)} tickers concentrent ≥70% du beta du portefeuille"}


def benchmark_selection(ticker_yf_info: dict, ticker_in_spy: float | None,
                        ticker_in_acwi: float | None) -> dict:
    """Critères de choix (.txt §4 Beta — contamination + alignement géo).
    Par défaut ACWI ; SPY si revenus ≤ 40% non-US ET contamination ACWI > SPY."""
    pct_non_us = None
    info = ticker_yf_info or {}
    if info.get("country") and info["country"].upper() not in ("UNITED STATES", "USA", "US"):
        pct_non_us = 0.50  # proxy quand le HQ n'est pas US
    notes = []
    if ticker_in_spy and ticker_in_spy > 0.02:
        notes.append(f"contamination SPY = {ticker_in_spy:.1%}")
    if ticker_in_acwi and ticker_in_acwi > 0.02:
        notes.append(f"contamination ACWI = {ticker_in_acwi:.1%}")
    default = "ACWI"
    if pct_non_us is None or pct_non_us < 0.40:
        if (ticker_in_acwi or 0) > (ticker_in_spy or 0) * 1.5:
            default = "SPY"
    return {"default_benchmark": default, "secondary_benchmark":
            "SPY" if default == "ACWI" else "ACWI",
            "rule": ("ACWI par défaut (couverture globale, contamination ~4% max) ; "
                     "SPY affiché en secondaire"),
            "notes": notes}
