"""QUALITÉ DU BUSINESS — CADRE BUFFETT (.txt, métriques vérifiées uniquement).
Sources primaires : lettres Berkshire 1983-84 ($1 test), 1986 (Owner Earnings).
Sources secondaires labelées : LT Debt Payback (Mary Buffett & Clark), ROE consistency.
"""
from __future__ import annotations
import config
from edgar.xbrl_parser import CompanyData
from compute import metrics


def owner_earnings_series(cd: CompanyData, n: int = 10) -> dict[int, float]:
    """OE ≈ OCF − D&A − SBC (proxy maintenance capex = D&A, limitation affichée dans l'UI)."""
    out = {}
    for y in cd.years("ocf")[-n:]:
        v = metrics.derive(cd, y).get("owner_earnings")
        if v is not None:
            out[y] = v
    return out


def retained_earnings_dollar_test(cd: CompanyData, price_history: dict[int, float] | None,
                                  shares_history: dict[int, float] | None = None) -> dict:
    """$1 Test (Berkshire 1983-84) : ΔMarket Cap (5Y) / Σ Retained Earnings retenus (5Y).
    Retenus = Σ(NI − dividendes). Nécessite prix historiques (yfinance, ajustés splits).
    Sans prix → "N/D" avec note, jamais d'estimation."""
    years = cd.years("net_income")
    w = config.RETAINED_EARNINGS_TEST_WINDOW
    if len(years) < w + 1:
        return {"ratio": None, "note": f"moins de {w+1} ans de données"}
    y_end, y_start = years[-1], years[-1 - w]
    retained = 0.0
    for y in years[-w:]:
        ni = cd.value("net_income", y)
        div = cd.value("dividends_paid", y) or 0.0
        if ni is None:
            return {"ratio": None, "note": f"NI manquant {y}"}
        retained += ni - div
    if not price_history or y_end not in price_history or y_start not in price_history:
        return {"ratio": None, "note": "prix historiques indisponibles (brancher yfinance)",
                "retained_5y": retained}
    sh = shares_history or {}
    sh_end = sh.get(y_end) or cd.value("shares_diluted", y_end)
    sh_start = sh.get(y_start) or cd.value("shares_diluted", y_start)
    if None in (sh_end, sh_start):
        return {"ratio": None, "note": "shares manquants", "retained_5y": retained}
    delta_mcap = price_history[y_end] * sh_end - price_history[y_start] * sh_start
    ratio = delta_mcap / retained if retained > 0 else None
    return {"ratio": ratio, "retained_5y": retained, "delta_mcap": delta_mcap,
            "passes": (ratio is not None and ratio > config.RETAINED_EARNINGS_TEST_MIN),
            "window": (y_start, y_end)}


def lt_debt_payback(cd: CompanyData) -> dict:
    """LT Debt / NI < 3-4 ans (source secondaire, label obligatoire UI)."""
    fy = (cd.years("net_income") or [None])[-1]
    lt, ni = cd.value("lt_debt", fy), cd.value("net_income", fy)
    if None in (lt, ni) or ni <= 0:
        return {"years": None, "passes": None, "label": "source secondaire"}
    yrs = lt / ni
    return {"years": yrs, "passes": yrs < config.LT_DEBT_PAYBACK_MAX_YEARS,
            "label": "source secondaire"}


def roe_consistency(cd: CompanyData, n: int = 10) -> dict:
    """Moyenne 10Y > 20% ET aucune année < 15% (source secondaire)."""
    roes = {}
    for y in cd.years("net_income")[-n:]:
        r = metrics.derive(cd, y).get("roe")
        if r is not None:
            roes[y] = r
    if not roes:
        return {"available": False}
    vals = list(roes.values())
    avg, lo = sum(vals) / len(vals), min(vals)
    return {"available": True, "series": {y: round(v, 4) for y, v in roes.items()},
            "avg": avg, "min": lo,
            "passes": avg > config.ROE_AVG_MIN and lo > config.ROE_FLOOR_MIN}


def gross_margin_trend(cd: CompanyData, n: int = 10) -> dict:
    """Direction 10Y : expansion / stable / compression (proxy pricing power, label qualitatif)."""
    gms = {}
    for y in cd.years("revenue")[-n:]:
        g = metrics.derive(cd, y).get("gross_margin")
        if g is not None:
            gms[y] = g
    if len(gms) < 3:
        return {"direction": None, "series": gms}
    ys = sorted(gms)
    half = len(ys) // 2
    early = sum(gms[y] for y in ys[:half]) / half
    late = sum(gms[y] for y in ys[half:]) / (len(ys) - half)
    delta = late - early
    direction = "expansion" if delta > 0.01 else ("compression" if delta < -0.01 else "stable")
    return {"direction": direction, "delta": round(delta, 4),
            "series": {y: round(v, 4) for y, v in gms.items()},
            "label": "signal qualitatif — pas un seuil Buffett officiel"}
