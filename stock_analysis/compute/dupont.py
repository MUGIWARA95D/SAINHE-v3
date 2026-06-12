"""ADVANCED DUPONT (.txt — Markarian UNIL, source directe cours).
ROE = RNOA + FLEV × SPREAD
  RNOA  = NOPAT / NOA            performance opérationnelle pure
  FLEV  = NFO / Equity           levier financier net
  NBC   = Net Interest AT / NFO  coût net de la dette (RNFA si NFO<0, cas MSFT 2003)
  SPREAD = RNOA − NBC
Vérification de cohérence vs ROE = NI/Equity incluse.
"""
from __future__ import annotations
from edgar.xbrl_parser import CompanyData
from compute import metrics


def advanced_dupont(cd: CompanyData, fy: int | None = None) -> dict:
    m = metrics.derive(cd, fy)
    fy = m.get("fy")
    ref = m.get("reformulation", {})
    noa, nfo = ref.get("NOA"), ref.get("NFO")
    eq = cd.value("equity", fy)
    nopat = m.get("nopat")
    ni = cd.value("net_income", fy)
    t = m.get("effective_tax_rate") or 0.0
    interest = cd.value("interest_expense", fy)

    if None in (noa, nfo, eq, nopat) or eq == 0:
        return {"available": False}

    rnoa = nopat / noa if noa else None
    flev = nfo / eq
    # Net interest after tax / NFO ; si NFO ≤ 0 (net cash) → RNFA, même formule, signe géré
    net_int_at = (interest or 0.0) * (1 - t)
    nbc = (net_int_at / nfo) if nfo not in (0, None) else 0.0
    spread = None if rnoa is None else rnoa - nbc
    roe_dupont = None if (rnoa is None or spread is None) else rnoa + flev * spread
    roe_direct = (ni / eq) if ni is not None else None

    return {
        "available": True, "fy": fy,
        "RNOA": rnoa, "FLEV": flev, "NBC": nbc, "SPREAD": spread,
        "leverage_gain": None if spread is None else flev * spread,
        "ROE_dupont": roe_dupont, "ROE_direct": roe_direct,
        "coherence_gap": (None if None in (roe_dupont, roe_direct)
                          else round(roe_dupont - roe_direct, 4)),
        "net_cash_position": nfo < 0,   # cas Microsoft 2003 du cours
    }


def rnoa_trend(cd: CompanyData, n: int = 10) -> dict[int, float]:
    out = {}
    for y in (cd.years("revenue") or [])[-n:]:
        d = advanced_dupont(cd, y)
        if d.get("available") and d.get("RNOA") is not None:
            out[y] = round(d["RNOA"], 4)
    return out
