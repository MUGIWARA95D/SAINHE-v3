"""SCORES DE RISQUE (.txt Couche 3) : Altman Z, Beneish M (8 sous-ratios exposés),
ROIC trend 10Y + direction moat, flag composite Goodwill>50% + ROIC déclinant 3Y,
flags SBC / lease-heavy / Goodwill 30% / going concern / impairment.
"""
from __future__ import annotations
import config
from edgar.xbrl_parser import CompanyData
from compute import metrics


# ------------------------------------------------------------------ Altman Z
def altman_z(cd: CompanyData, market_cap: float | None, fy: int | None = None) -> dict:
    """Z = 1.2·WC/TA + 1.4·RE/TA + 3.3·EBIT/TA + 0.6·MVE/TL + 1.0·Sales/TA (manuf. originale)."""
    fy = fy or (cd.years("total_assets") or [None])[-1]
    ta = cd.value("total_assets", fy)
    tl = cd.value("total_liabilities", fy)
    ca, cl = cd.value("current_assets", fy), cd.value("current_liabilities", fy)
    re = cd.value("retained_earnings", fy)
    ebit = cd.value("ebit", fy)
    rev = cd.value("revenue", fy)
    if None in (ta, tl, ca, cl, re, ebit, rev) or ta == 0 or tl == 0:
        return {"z": None, "zone": "N/D"}
    wc = ca - cl
    mve = market_cap
    if mve is None:
        return {"z": None, "zone": "N/D", "note": "market cap manquante (yfinance)"}
    z = 1.2 * wc / ta + 1.4 * re / ta + 3.3 * ebit / ta + 0.6 * mve / tl + 1.0 * rev / ta
    zone = ("distress" if z < config.ALTMAN_DISTRESS
            else "safe" if z > config.ALTMAN_SAFE else "grey")
    return {"z": z, "zone": zone,
            "components": {"WC/TA": wc / ta, "RE/TA": re / ta, "EBIT/TA": ebit / ta,
                           "MVE/TL": mve / tl, "Sales/TA": rev / ta}}


# ------------------------------------------------------------------ Beneish M
def beneish_m(cd: CompanyData, fy: int | None = None) -> dict:
    """M = −4.84 + 0.92·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI
            − 0.172·SGAI + 4.679·TATA − 0.327·LVGI.   M > −1.78 → manipulation likely.
    Sous-ratios exposés pour le drill-down (.txt)."""
    years = cd.years("revenue")
    if len(years) < 2:
        return {"m": None}
    fy = fy or years[-1]
    prev = max((y for y in years if y < fy), default=None)
    if prev is None:
        return {"m": None}

    def v(name, y):
        return cd.value(name, y)

    def ratio(a, b):
        return None if (a is None or b in (None, 0)) else a / b

    rev1, rev0 = v("revenue", fy), v("revenue", prev)
    ar1, ar0 = v("ar", fy), v("ar", prev)
    cogs1, cogs0 = v("cogs", fy), v("cogs", prev)
    ta1, ta0 = v("total_assets", fy), v("total_assets", prev)
    ca1, ca0 = v("current_assets", fy), v("current_assets", prev)
    ppe1, ppe0 = v("ppe_net", fy), v("ppe_net", prev)
    da1, da0 = v("dep_amort", fy), v("dep_amort", prev)
    sga1, sga0 = v("sga", fy), v("sga", prev)
    tl1, tl0 = v("total_liabilities", fy), v("total_liabilities", prev)
    ni1, ocf1 = v("net_income", fy), v("ocf", fy)

    gm1 = ratio((rev1 - cogs1) if None not in (rev1, cogs1) else None, rev1)
    gm0 = ratio((rev0 - cogs0) if None not in (rev0, cogs0) else None, rev0)

    dsri = ratio(ratio(ar1, rev1), ratio(ar0, rev0))
    gmi = ratio(gm0, gm1)
    aqi_1 = None if None in (ca1, ppe1, ta1) else 1 - (ca1 + ppe1) / ta1
    aqi_0 = None if None in (ca0, ppe0, ta0) else 1 - (ca0 + ppe0) / ta0
    aqi = ratio(aqi_1, aqi_0)
    sgi = ratio(rev1, rev0)
    depi = ratio(ratio(da0, (da0 + ppe0) if None not in (da0, ppe0) else None),
                 ratio(da1, (da1 + ppe1) if None not in (da1, ppe1) else None))
    sgai = ratio(ratio(sga1, rev1), ratio(sga0, rev0))
    tata = ratio((ni1 - ocf1) if None not in (ni1, ocf1) else None, ta1)
    lvgi = ratio(ratio(tl1, ta1), ratio(tl0, ta0))

    subs = {"DSRI": dsri, "GMI": gmi, "AQI": aqi, "SGI": sgi,
            "DEPI": depi, "SGAI": sgai, "TATA": tata, "LVGI": lvgi}
    # Beneish : sous-ratio manquant → neutre (1.0, ou 0 pour TATA), documenté
    neutral = {k: (0.0 if k == "TATA" else 1.0) for k in subs}
    filled = {k: (v_ if v_ is not None else neutral[k]) for k, v_ in subs.items()}
    m = (-4.84 + 0.92 * filled["DSRI"] + 0.528 * filled["GMI"] + 0.404 * filled["AQI"]
         + 0.892 * filled["SGI"] + 0.115 * filled["DEPI"] - 0.172 * filled["SGAI"]
         + 4.679 * filled["TATA"] - 0.327 * filled["LVGI"])
    return {"m": m, "flag": m > config.BENEISH_MANIPULATION,
            "sub_ratios": {k: (round(v_, 4) if v_ is not None else "N/D")
                           for k, v_ in subs.items()},
            "missing_filled_neutral": [k for k, v_ in subs.items() if v_ is None]}


# ------------------------------------------------------------------ ROIC trend + flag composite
def roic_trend(cd: CompanyData, n: int = 10) -> dict:
    series = {}
    for y in cd.years("revenue")[-n:]:
        r = metrics.derive(cd, y).get("roic")
        if r is not None:
            series[y] = round(r, 4)
    ys = sorted(series)
    declining_3y = (len(ys) >= config.ROIC_DECLINE_YEARS + 1 and
                    all(series[ys[-i]] < series[ys[-i - 1]]
                        for i in range(1, config.ROIC_DECLINE_YEARS + 1)))
    direction = None
    if len(ys) >= 3:
        direction = "contraction" if declining_3y else (
            "expansion" if series[ys[-1]] > series[ys[0]] else "stable")
    return {"series": series, "declining_3y_plus": declining_3y, "direction": direction}


def all_flags(cd: CompanyData, edgar_meta: dict, market_cap: float | None) -> list[dict]:
    """Assemble TOUS les flags du plan en une liste uniforme pour le bloc B du front."""
    fy = (cd.years("total_assets") or [None])[-1]
    m = metrics.derive(cd, fy)
    flags = []

    def add(fid, triggered, severity, message, details=None):
        if triggered:
            flags.append({"id": fid, "severity": severity, "message": message,
                          "details": details or {}})

    # EDGAR metadata
    add("nt_filing", edgar_meta.get("nt_filing", {}).get("triggered", False), "high",
        "NT 10-K/10-Q déposé : incapacité à filer à temps — red flag majeur",
        edgar_meta.get("nt_filing"))
    add("restatement_2y", edgar_meta.get("restatement_2y", {}).get("triggered", False), "high",
        "Restatement (10-K/A ou 10-Q/A) sur les 2 dernières années — chiffres passés révisés",
        edgar_meta.get("restatement_2y"))
    gc = cd.value("going_concern", fy)
    add("going_concern", bool(gc), "critical",
        "Going concern : doute substantiel déclaré dans le filing (tag XBRL natif)")
    gwi = cd.value("goodwill_impairment", fy)
    add("goodwill_impairment", bool(gwi), "medium",
        "Goodwill impairment comptabilisé : le management a reconnu un mauvais deal",
        {"amount": gwi})

    # Goodwill simple + composite (.txt FLAG COMPOSITE — value trap detector)
    gw, ta = cd.value("goodwill", fy), cd.value("total_assets", fy)
    gw_pct = (gw / ta) if (gw and ta) else None
    add("goodwill_30pct", bool(gw_pct and gw_pct > config.GOODWILL_RED_FLAG_PCT_ASSETS),
        "medium", f"Goodwill = {gw_pct:.0%} des actifs (>30%) : acquisitions agressives"
        if gw_pct else "", {"goodwill_pct_assets": gw_pct})
    rt = roic_trend(cd)
    add("goodwill_roic_composite",
        bool(gw_pct and gw_pct > config.GOODWILL_COMPOSITE_PCT_ASSETS
             and rt["declining_3y_plus"]),
        "critical",
        "Bilan dominé par Goodwill (>50% actifs) avec ROIC en érosion 3Y+. "
        "Les acquisitions historiques n'ont pas créé de valeur mesurable. "
        "Risque d'impairment matériel à surveiller. (Cas type : Kraft Heinz 2019, GE 2018)",
        {"goodwill_pct_assets": gw_pct, "roic_trend": rt["series"]})

    # SBC (.txt)
    sbc_pct = m.get("sbc_pct_fcf")
    add("sbc_15pct_fcf", bool(sbc_pct and sbc_pct > config.SBC_FCF_FLAG), "medium",
        f"SBC = {sbc_pct:.0%} du FCF brut (>15%) : FCF brut significativement surestiمé"
        if sbc_pct else "", {"sbc_pct_fcf": sbc_pct})

    # Lease-heavy ASC 842 (.txt)
    oll, tlb = cd.value("operating_lease_liab", fy), cd.value("total_liabilities", fy)
    lease_pct = (oll / tlb) if (oll and tlb) else None
    add("lease_heavy", bool(lease_pct and lease_pct > config.LEASE_HEAVY_PCT_LIABILITIES),
        "info", f"Operating leases = {lease_pct:.0%} du passif : secteur lease-heavy, "
        "ratios de dette à lire avec la décomposition ASC 842" if lease_pct else "",
        {"operating_lease_pct_liabilities": lease_pct})

    # Scores
    z = altman_z(cd, market_cap, fy)
    add("altman_distress", z.get("zone") == "distress", "high",
        f"Altman Z = {z['z']:.2f} < 1.81 : zone de détresse financière" if z.get("z") else "",
        z)
    b = beneish_m(cd, fy)
    add("beneish_manipulation", bool(b.get("flag")), "high",
        f"Beneish M = {b['m']:.2f} > −1.78 : profil statistique de manipulation des earnings"
        if b.get("m") is not None else "", {"m": b.get("m")})

    return flags
