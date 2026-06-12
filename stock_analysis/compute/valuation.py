"""WACC + Valorisation intrinsèque (.txt Couche 3 : WACC, EPV, Reverse DCF, SGR,
RE Valuation statique, plage de confiance, sensibilité WACC, sensitivity matrix).
Aucune prédiction : seuls Reverse DCF (implied), SGR (data-driven) et plages historiques.
"""
from __future__ import annotations
import statistics
import config
from edgar.xbrl_parser import CompanyData
from compute import metrics
from compute.adjustments import adjust


# ------------------------------------------------------------------ WACC (.txt sous-module)
def wacc(cd: CompanyData, price: float | None, beta: float | None = None,
         rf: float | None = None, erp: float | None = None) -> dict:
    """Sources : Couche 2 (Kd, T, D) + Yahoo (E = shares × prix) + Macro SAINHE (Rf, ERP, β)."""
    rf = config.DEFAULT_RISK_FREE if rf is None else rf
    erp = config.DEFAULT_ERP if erp is None else erp
    beta = config.DEFAULT_BETA if beta is None else beta

    m = metrics.derive(cd)
    fy = m.get("fy")
    shares = cd.value("shares_diluted", fy) or cd.value("shares_outstanding", fy)
    ke = rf + beta * erp
    kd = m.get("kd")
    t = m.get("effective_tax_rate") or 0.0
    e = (shares * price) if (shares and price) else None
    d = metrics.financial_debt(cd, fy) or 0

    if e is None or (e + d) == 0:
        w = ke  # fallback all-equity, documenté dans l'output
        detail = "fallback all-equity (prix ou shares indisponible)"
    else:
        v = e + d
        w = ke * (e / v) + (kd or 0.0) * (1 - t) * (d / v)
        detail = "complet"
    return {"wacc": w, "ke": ke, "kd": kd, "tax_rate": t, "E": e, "D": d,
            "rf": rf, "erp": erp, "beta": beta, "mode": detail}


# ------------------------------------------------------------------ EPV (Greenwald)
def epv(cd: CompanyData, wacc_value: float, fy: int | None = None) -> dict:
    """EPV = Adjusted EBIT × (1−T) / WACC → enterprise ; equity = EPV − Net Debt ; /shares."""
    adj = adjust(cd, fy)
    fy = adj["fy"]
    t = metrics.derive(cd, fy).get("effective_tax_rate") or 0.0
    ebit_adj = adj["ebit_adj"]
    if ebit_adj is None or not wacc_value:
        return {"epv_ev": None, "epv_equity": None, "epv_per_share": None}
    ev = ebit_adj * (1 - t) / wacc_value
    nd = metrics.net_debt(cd, fy) or 0.0
    eq_val = ev - nd
    shares = cd.value("shares_diluted", fy) or cd.value("shares_outstanding", fy)
    return {"epv_ev": ev, "epv_equity": eq_val,
            "epv_per_share": (eq_val / shares) if shares else None,
            "inputs": {"ebit_adj": ebit_adj, "tax": t, "wacc": wacc_value, "net_debt": nd}}


# ------------------------------------------------------------------ Reverse DCF
def reverse_dcf(cd: CompanyData, price: float, wacc_value: float) -> dict:
    """Résout g implicite : EV_marché = FCF_adj × (1+g) / (WACC − g)  (Gordon inversé).
    g = (WACC×EV − FCF) / (EV + FCF). Flag si g > 15% (.txt)."""
    m = metrics.derive(cd)
    fy = m.get("fy")
    fcf = m.get("fcf_adj")
    shares = cd.value("shares_diluted", fy) or cd.value("shares_outstanding", fy)
    nd = m.get("net_debt") or 0.0
    if None in (fcf, shares) or price is None or fcf <= 0:
        return {"implied_g": None, "flag_unrealistic": False,
                "note": "FCF ajusté ≤ 0 ou inputs manquants"}
    ev = price * shares + nd
    g = (wacc_value * ev - fcf) / (ev + fcf)
    return {"implied_g": g, "flag_unrealistic": g > config.REVERSE_DCF_IMPLIED_G_FLAG,
            "inputs": {"ev": ev, "fcf_adj": fcf, "wacc": wacc_value}}


# ------------------------------------------------------------------ SGR
def sgr(cd: CompanyData, fy: int | None = None) -> dict:
    """SGR = ROIC × RR ; RR = (CapEx − D&A + ΔNWC) / NOPAT ; ΔNWC = Δ(AR + Inv − AP) YoY.
    100% XBRL, zéro hypothèse (.txt)."""
    m = metrics.derive(cd, fy)
    fy = m.get("fy")
    years = cd.years("ar")
    prev = max((y for y in years if y < fy), default=None) if fy else None
    if prev is None:
        return {"sgr": None, "rr": None, "note": "pas d'année précédente pour ΔNWC"}

    def nwc(y):
        ar, inv, ap = cd.value("ar", y), cd.value("inventory", y), cd.value("ap", y)
        if ar is None and inv is None and ap is None:
            return None
        return (ar or 0) + (inv or 0) - (ap or 0)

    nwc_now, nwc_prev = nwc(fy), nwc(prev)
    capex, da, nopat = cd.value("capex", fy), cd.value("dep_amort", fy), m.get("nopat")
    if None in (nwc_now, nwc_prev, capex, da) or nopat in (None, 0):
        return {"sgr": None, "rr": None, "note": "inputs manquants"}
    rr = (capex - da + (nwc_now - nwc_prev)) / nopat
    roic = m.get("roic")
    return {"sgr": (roic * rr) if roic is not None else None, "rr": rr, "roic": roic}


# ------------------------------------------------------------------ RE statique
def residual_earnings_static(cd: CompanyData, ke: float, g: float | None) -> dict:
    """V₀ = B₀ + Σ_{t=1..5} RE/(1+ke)^t + CV ; RE = Adjusted NI − ke×B₀ constant (statique).
    CV = RE×(1+g)/(ke−g) actualisé. g = min(SGR, ke−50bps) pour éviter la divergence (.txt)."""
    adj = adjust(cd)
    fy = adj["fy"]
    b0 = cd.value("equity", fy)
    ni_adj = adj["ni_adj"]
    shares = cd.value("shares_diluted", fy) or cd.value("shares_outstanding", fy)
    if None in (b0, ni_adj) or not ke:
        return {"re_value_per_share": None}
    g = 0.0 if g is None else min(g, ke - 0.005)
    g = max(g, 0.0)
    re = ni_adj - ke * b0
    pv = sum(re / (1 + ke) ** t for t in range(1, config.RE_HORIZON_YEARS + 1))
    cv = (re * (1 + g) / (ke - g)) / (1 + ke) ** config.RE_HORIZON_YEARS
    v0 = b0 + pv + cv
    return {"re_value_equity": v0,
            "re_value_per_share": (v0 / shares) if shares else None,
            "inputs": {"B0": b0, "RE": re, "ke": ke, "g": g}}


# ------------------------------------------------------------------ Plage de confiance + sensibilité
def confidence_range(cd: CompanyData, wacc_value: float) -> dict:
    """EPV recalculé au FCF p25 / p75 historique 5-10Y. Fallback <4 ans : growth 0% = EPV central.
    Implémentation : on scale l'EBIT ajusté par le ratio FCF_pctl / FCF_actuel (proxy stable)."""
    hist = [v for v in (metrics.derive(cd, y).get("fcf_adj")
            for y in cd.years("ocf")[-10:]) if v is not None]
    base = epv(cd, wacc_value)
    if len(hist) < config.FCF_MIN_YEARS_FOR_PCTL or not base["epv_per_share"]:
        return {"low": base["epv_per_share"], "high": base["epv_per_share"],
                "fallback": "moins de 4 ans de FCF → plage = EPV central (growth 0%)"}
    cur = hist[-1] or 1.0
    qs = statistics.quantiles(hist, n=4)  # [p25, p50, p75]
    p25, p75 = qs[0], qs[2]
    return {"low": base["epv_per_share"] * (p25 / cur) if cur else None,
            "high": base["epv_per_share"] * (p75 / cur) if cur else None,
            "fcf_p25": p25, "fcf_p75": p75}


def wacc_sensitivity(cd: CompanyData, wacc_value: float) -> dict:
    """EPV à WACC ±100bps (.txt Sensibilité WACC)."""
    bp = config.WACC_SENSITIVITY_BPS
    return {"minus_100bps": epv(cd, wacc_value - bp)["epv_per_share"],
            "central": epv(cd, wacc_value)["epv_per_share"],
            "plus_100bps": epv(cd, wacc_value + bp)["epv_per_share"]}


# ------------------------------------------------------------------ Sensitivity matrix
def sensitivity_matrix(cd: CompanyData, ke: float, sgr_value: float | None) -> dict:
    """Grille NOPAT margin (percentiles historiques) × terminal growth (fractions de SGR),
    valeur par cellule via RE statique avec NI recalculé à la marge testée (.txt Couche 4)."""
    fy = (cd.years("revenue") or [None])[-1]
    rev = cd.value("revenue", fy)
    b0 = cd.value("equity", fy)
    shares = cd.value("shares_diluted", fy) or cd.value("shares_outstanding", fy)
    margins_hist = [m for m in (metrics.derive(cd, y).get("nopat_margin")
                    for y in cd.years("revenue")[-10:]) if m is not None]
    if None in (rev, b0, shares) or len(margins_hist) < 3 or not ke:
        return {"matrix": None, "note": "données insuffisantes"}
    qs = statistics.quantiles(margins_hist, n=10)  # déciles
    margin_axis = [qs[0], qs[1], statistics.median(margins_hist), qs[6], qs[8]]  # ~p10..p90
    base_g = sgr_value if (sgr_value and sgr_value > 0) else 0.02
    g_axis = [min(base_g * f, ke - 0.005) for f in config.SENSITIVITY_G_FACTORS]

    rows = []
    for m_ in margin_axis:
        row = []
        for g in g_axis:
            ni = rev * m_
            re = ni - ke * b0
            pv = sum(re / (1 + ke) ** t for t in range(1, config.RE_HORIZON_YEARS + 1))
            cv = (re * (1 + max(g, 0)) / (ke - max(g, 0))) / (1 + ke) ** config.RE_HORIZON_YEARS
            row.append(round((b0 + pv + cv) / shares, 2))
        rows.append(row)
    return {"margin_axis": [round(m_, 4) for m_ in margin_axis],
            "g_axis": [round(g, 4) for g in g_axis], "matrix": rows}
