"""Couche 4 — Output normalisé (.txt Couche 4 + contrat JSON du prompt).
Un JSON par ticker, structuré EXACTEMENT selon les blocs front A→I,
plus valuation_map.json agrégé (Niveau 1, les 30 tickers).
Chaque chiffre traçable ; tag manquant → "N/D".
"""
from __future__ import annotations
import json, datetime
import config
from edgar.xbrl_parser import CompanyData
from compute import metrics, valuation, dupont, buffett, scores, external
from compute.adjustments import adjust


def _nd(x):
    """None → 'N/D' pour le front (.txt garde-fous)."""
    if isinstance(x, dict):
        return {k: _nd(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_nd(v) for v in x]
    if isinstance(x, float):
        return round(x, 6)
    return "N/D" if x is None else x


def composite_score(blocks: dict) -> dict:
    """Score 0-100, pondérations config.SCORE_WEIGHTS AFFICHÉES (pas de black box, .txt).
    Chaque pilier noté 0-100 par règles simples et transparentes."""
    s = {}
    # valuation : EPV vs prix
    va = blocks["bloc_A_verdict"]
    price, epv_ps = va.get("prix"), va.get("EPV", {}).get("epv_per_share")
    if isinstance(price, (int, float)) and isinstance(epv_ps, (int, float)) and price > 0:
        upside = (epv_ps - price) / price
        s["valuation"] = max(0, min(100, 50 + upside * 200))   # +25% upside → 100
    else:
        s["valuation"] = 50
    # balance sheet health
    h = blocks["bloc_E_health"]
    pts = 50
    nde = h.get("net_debt_ebitda")
    if isinstance(nde, (int, float)):
        pts += 20 if nde < 1 else (10 if nde < 3 else (-20 if nde > 5 else 0))
    ic = h.get("interest_coverage")
    if isinstance(ic, (int, float)):
        pts += 15 if ic > 8 else (-15 if ic < 2 else 0)
    s["balance_sheet_health"] = max(0, min(100, pts))
    # earnings quality
    pts = 50
    ocfni = h.get("ocf_ni")
    if isinstance(ocfni, (int, float)):
        pts += 20 if ocfni > 1.1 else (-25 if ocfni < 0.7 else 0)
    flags = {f["id"] for f in blocks["bloc_B_flags"]}
    if "beneish_manipulation" in flags:
        pts -= 30
    s["earnings_quality"] = max(0, min(100, pts))
    # smart money (v1 neutre, Phase 6 affinera)
    s["smart_money"] = 50
    # momentum (rempli côté portfolio/yfinance ; neutre ici)
    s["momentum"] = 50

    total = sum(s[k] * w for k, w in config.SCORE_WEIGHTS.items())
    return {"value_0_100": round(total, 1), "pillars": s,
            "weights": config.SCORE_WEIGHTS,
            "note": "pondérations modifiables par l'utilisateur (.txt Couche 4)"}


def build_report(cd: CompanyData, price: float | None, yf_info: dict | None,
                 edgar_meta: dict, macro_signals: dict | None = None,
                 gics_sector: str | None = None,
                 price_history: dict[int, float] | None = None) -> dict:
    fy = (cd.years("revenue") or cd.years("net_income") or [None])[-1]
    m = metrics.derive(cd, fy)
    adj = adjust(cd, fy)
    shares = cd.value("shares_diluted", fy) or cd.value("shares_outstanding", fy)
    mcap = price * shares if (price and shares) else None
    beta = (yf_info or {}).get("beta")

    w = valuation.wacc(cd, price, beta=beta)
    epv_ = valuation.epv(cd, w["wacc"], fy)
    rdcf = valuation.reverse_dcf(cd, price, w["wacc"]) if price else {"implied_g": None}
    sgr_ = valuation.sgr(cd, fy)
    re_ = valuation.residual_earnings_static(cd, w["ke"], sgr_.get("sgr"))
    cons = external.consensus(yf_info)
    conf = valuation.confidence_range(cd, w["wacc"])
    wsens = valuation.wacc_sensitivity(cd, w["wacc"])
    flags = scores.all_flags(cd, edgar_meta, mcap)
    if adj["gap_flag"]:
        flags.append({"id": "transitory_items", "severity": "info",
                      "message": f"Écart NI brut vs ajusté = {adj['gap_pct']:.0%} (>10%) — "
                                 "earnings affectés par items one-time",
                      "details": {"adjustments": adj["adjustments"]}})

    impl_g, sgr_v = rdcf.get("implied_g"), sgr_.get("sgr")
    growth_unfinanceable = (isinstance(impl_g, float) and isinstance(sgr_v, float)
                            and impl_g > sgr_v)

    report = {
        "ticker": cd.ticker, "cik": cd.cik,
        "as_of": datetime.date.today().isoformat(),
        "fiscal_year": fy,
        "bloc_A_verdict": {
            "prix": price,
            "EPV": epv_, "EPV_confidence_range": conf, "EPV_wacc_sensitivity": wsens,
            "RE_valuation": re_,
            "consensus": cons,
            "reverse_dcf": rdcf,
            "SGR": sgr_,
            "flag_growth_unfinanceable": growth_unfinanceable,
        },
        "bloc_B_flags": flags,
        "bloc_C_dupont": dupont.advanced_dupont(cd, fy),
        "bloc_D_trends": {
            "roic_10y": scores.roic_trend(cd)["series"],
            "rnoa_10y": dupont.rnoa_trend(cd),
            "gross_margin_10y": buffett.gross_margin_trend(cd)["series"],
            "fcf_adj_10y": {y: metrics.derive(cd, y).get("fcf_adj")
                            for y in cd.years("ocf")[-10:]},
            "roe_10y": buffett.roe_consistency(cd).get("series", {}),
            "owner_earnings_10y": buffett.owner_earnings_series(cd),
            "revenue_10y": cd.history("revenue", 10),
        },
        "bloc_E_health": {
            "net_debt_ebitda": m.get("net_debt_ebitda"),
            "interest_coverage": m.get("interest_coverage"),
            "lt_debt_payback": buffett.lt_debt_payback(cd),
            "current_ratio": m.get("current_ratio"), "quick_ratio": m.get("quick_ratio"),
            "de_ratio": m.get("de_ratio"),
            "ccc": {"dso": m.get("dso"), "dio": m.get("dio"), "dpo": m.get("dpo"),
                    "ccc": m.get("ccc")},
            "ocf_ni": m.get("ocf_ni"), "accruals_pct_rev": m.get("accruals_pct_rev"),
            "retained_earnings_test": buffett.retained_earnings_dollar_test(cd, price_history),
        },
        "bloc_F_peers": {"note": "rempli par le batch peers (nécessite l'univers complet)"},
        "bloc_G_smart_money": external.insider_activity(
            edgar_meta.get("_submissions_raw", {})) if "_submissions_raw" in edgar_meta else
            {"note": "submissions non fournies"},
        "bloc_H_sensitivity": valuation.sensitivity_matrix(cd, w["ke"], sgr_.get("sgr")),
        "bloc_I_macro": external.macro_context(gics_sector, macro_signals),
        "drill_down": {
            "wacc_detail": w,
            "adjustments": adj,
            "reformulation": m.get("reformulation"),
            "three_statement_10y": {name: cd.history(name, 10)
                                    for name in cd.series},
            "edgar_links": {
                name: f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK="
                      f"{cd.cik:0>10}&type=10-K"
                for name in ("filings",)},
        },
    }
    report["score_composite"] = composite_score(report)
    return _nd(report)


def build_valuation_map(reports: list[dict]) -> dict:
    """Niveau 1 — JSON agrégé pour la Valuation Map (scatter + table triable)."""
    rows = []
    for r in reports:
        a = r["bloc_A_verdict"]
        epv_ps = a.get("EPV", {}).get("epv_per_share")
        price = a.get("prix")
        gap = None
        if isinstance(epv_ps, (int, float)) and isinstance(price, (int, float)) and price:
            gap = round((epv_ps - price) / price, 4)
        rows.append({
            "ticker": r["ticker"], "prix": price, "epv_per_share": epv_ps,
            "re_per_share": a.get("RE_valuation", {}).get("re_value_per_share"),
            "ecart_pct": gap if gap is not None else "N/D",
            "score": r["score_composite"]["value_0_100"],
            "n_flags": len(r["bloc_B_flags"]),
            "consensus_median": a.get("consensus", {}).get("target_median", "N/D"),
        })
    return {"as_of": datetime.date.today().isoformat(), "rows": rows}


def save(obj: dict, path: str):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
