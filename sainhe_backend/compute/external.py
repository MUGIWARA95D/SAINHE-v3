"""Modules à dépendances externes (.txt Couche 3 : consensus, peers, smart money, macro).
Tous dégradent proprement en "N/D" si la source est indisponible — jamais d'invention.

- consensus  : yfinance .info (targetMeanPrice etc.)
- peers      : univers SIC + market cap bucket ; quartiles ; dispersion relative
- smart_money: 13F + Forms 3/4/5 (EDGAR submissions des fonds — v1 = squelette branché)
- macro      : mapping GICS → leading indicator, lit les signaux Macro SAINHE existants
"""
from __future__ import annotations
import statistics
import config


# ------------------------------------------------------------------ Consensus (yfinance)
def consensus(yf_info: dict | None) -> dict:
    """yf_info = yfinance.Ticker(t).info (passé par l'appelant pour rester testable offline)."""
    if not yf_info:
        return {"available": False, "note": "yfinance indisponible"}
    n = yf_info.get("numberOfAnalystOpinions")
    out = {
        "available": True,
        "target_mean": yf_info.get("targetMeanPrice"),
        "target_median": yf_info.get("targetMedianPrice"),
        "target_high": yf_info.get("targetHighPrice"),
        "target_low": yf_info.get("targetLowPrice"),
        "n_analysts": n,
        "warning_few_analysts": (n is not None and n < config.ANALYST_MIN_OPINIONS),
    }
    th, tl, tm = out["target_high"], out["target_low"], out["target_mean"]
    out["dispersion"] = ((th - tl) / tm) if None not in (th, tl, tm) and tm else None
    return out


def dispersion_relative(ticker_disp: float | None, peer_disps: list[float]) -> dict:
    """Dispersion(ticker) / médiane(peers). Seuils 1.5 / 0.8 (.txt). Jamais de seuil absolu."""
    if ticker_disp is None or not peer_disps:
        return {"ratio": None}
    med = statistics.median(peer_disps)
    if not med:
        return {"ratio": None}
    r = ticker_disp / med
    msg = None
    if r > config.DISPERSION_HIGH_RATIO:
        msg = "Les analystes se disputent plus que d'habitude sur ce titre → ton analyse propre a plus de valeur"
    elif r < config.DISPERSION_LOW_RATIO:
        msg = "Consensus fort, tout le monde modélise pareil → information edge faible"
    return {"ratio": r, "message": msg, "peer_median_dispersion": med}


# ------------------------------------------------------------------ Peers
def peer_quartiles(ticker_metrics: dict, peer_metrics: list[dict]) -> dict:
    """Quartile du ticker vs pairs pour P/E, EV/EBITDA, P/FCF, P/S, ROIC, ROE + spread rank.
    Univers attendu : même SIC + même market cap bucket (config), construit par l'appelant."""
    KEYS = ["pe", "ev_ebitda", "p_fcf", "p_s", "roic", "roe", "spread_roic_wacc", "kd"]
    out = {}
    for k in KEYS:
        tv = ticker_metrics.get(k)
        vals = sorted(v[k] for v in peer_metrics if v.get(k) is not None)
        if tv is None or len(vals) < 3:
            out[k] = {"value": tv, "quartile": None, "n_peers": len(vals)}
            continue
        below = sum(1 for v in vals if v <= tv)
        q = min(4, 1 + int(4 * below / (len(vals) + 1)))
        out[k] = {"value": tv, "quartile": q, "n_peers": len(vals)}
    return out


def market_cap_bucket(mcap: float | None) -> int | None:
    if mcap is None:
        return None
    for i, (lo, hi) in enumerate(config.PEER_MARKET_CAP_BUCKETS):
        if lo <= mcap < hi:
            return i
    return None


# ------------------------------------------------------------------ Smart money (squelette branché)
def insider_activity(submissions_json: dict, lookback_days: int = 180) -> dict:
    """Forms 3/4/5 dans les submissions du TICKER : volume de filings insiders récents.
    v1 : compte + dates (le détail buy/sell exige le parsing des form 4 XML — Phase 6)."""
    from datetime import datetime, timedelta
    recent = submissions_json.get("filings", {}).get("recent", {})
    cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    hits = [{"form": f, "date": d} for f, d in zip(forms, dates)
            if f in ("3", "4", "5") and d >= cutoff]
    return {"n_insider_filings_6m": len(hits), "recent": hits[:20],
            "note": "détail buy/sell = Phase 6 (parsing Form 4 XML)"}


# ------------------------------------------------------------------ Macro context
GICS_TO_INDICATOR = {
    "Information Technology": "PMI Manufacturing",
    "Industrials": "PMI Manufacturing",
    "Materials": "PMI Manufacturing",
    "Energy": "PMI Manufacturing",
    "Consumer Discretionary": "Consumer Confidence",
    "Consumer Staples": "Consumer Confidence",
    "Financials": "Yield Curve (2s10s)",
    "Real Estate": "Yield Curve (2s10s)",
    "Communication Services": "PMI Services",
    "Health Care": "PMI Services",
    "Utilities": "Yield Curve (2s10s)",
}


def macro_context(gics_sector: str | None, macro_signals: dict | None,
                  pct_revenue_non_us: float | None = None) -> dict:
    """Mapping secteur → leading indicator + lecture du signal Macro SAINHE.
    Label OBLIGATOIRE : 'contexte macro — indicateur avancé, PAS une prédiction' (.txt)."""
    indicator = GICS_TO_INDICATOR.get(gics_sector or "", "PMI Manufacturing")
    value = (macro_signals or {}).get(indicator)
    out = {"indicator": indicator, "value": value,
           "label": "contexte macro — indicateur avancé, pas une prédiction"}
    if pct_revenue_non_us is not None and pct_revenue_non_us > 0.40:
        out["dxy_warning"] = ("Plus de 40% des revenus hors-US : sensibilité au dollar (DXY) — "
                              "voir signal DXY de la page Macro")
    return out
