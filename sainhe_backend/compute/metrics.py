"""Couche 2 — Métriques dérivées + reformulation du bilan (.txt MÉTRIQUES STANDARD,
REFORMULATION DU BILAN, NOTE ASC 842, FCF AJUSTÉ SBC).

Toutes les fonctions retournent None si un input manque ("N/D" propagé, jamais d'imputation).
"""
from __future__ import annotations
import config
from edgar.xbrl_parser import CompanyData


def _nz(x, default=0.0):
    """None → default (uniquement pour les composants OPTIONNELS, ex: leases absents pré-2019)."""
    return default if x is None else x


def _div(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b


# ------------------------------------------------------------------ Net Debt ASC 842
def net_debt(cd: CompanyData, fy: int | None = None):
    """Net Debt = LT Debt + ST Debt + FinanceLeaseLiability − Cash  (.txt NOTE ASC 842).
    OperatingLeaseLiability est EXCLU (obligation opérationnelle, pas dette financière).
    """
    lt, st, cash = cd.value("lt_debt", fy), cd.value("st_debt", fy), cd.value("cash", fy)
    if lt is None and st is None:
        return None
    return _nz(lt) + _nz(st) + _nz(cd.value("finance_lease_liab", fy)) - _nz(cash)


# ------------------------------------------------------------------ Reformulation Penman
def reformulate(cd: CompanyData, fy: int | None = None) -> dict:
    """OA/FA/OO/FO → NOA, NFO (.txt REFORMULATION DU BILAN).
    Proxy par défaut : FA = Cash + ST investments ; OA = Total Assets − FA.
    OO = Total Liabilities − FO ; FO = dettes financières + finance leases.
    OperatingLeaseLiability reste dans OO (ASC 842).
    """
    ta, tl = cd.value("total_assets", fy), cd.value("total_liabilities", fy)
    if ta is None or tl is None:
        return {"NOA": None, "NFO": None, "OA": None, "FA": None, "OO": None, "FO": None,
                "equity_check": None}
    fa = _nz(cd.value("cash", fy)) + _nz(cd.value("st_investments", fy))
    fo = _nz(cd.value("lt_debt", fy)) + _nz(cd.value("st_debt", fy)) \
        + _nz(cd.value("finance_lease_liab", fy))
    oa, oo = ta - fa, tl - fo
    noa, nfo = oa - oo, fo - fa
    eq = cd.value("equity", fy)
    return {"OA": oa, "FA": fa, "OO": oo, "FO": fo, "NOA": noa, "NFO": nfo,
            "equity_check": (None if eq is None else round(noa - nfo - eq, 2))}


# ------------------------------------------------------------------ Bloc métriques annuelles
def derive(cd: CompanyData, fy: int | None = None) -> dict:
    """Toutes les métriques dérivées du .txt pour une année donnée."""
    fys = cd.years("revenue") or cd.years("net_income")
    if not fys:
        return {}
    fy = fy or fys[-1]

    rev = cd.value("revenue", fy)
    ebit = cd.value("ebit", fy)
    da = cd.value("dep_amort", fy)
    ni = cd.value("net_income", fy)
    ocf = cd.value("ocf", fy)
    capex = cd.value("capex", fy)
    sbc = cd.value("sbc", fy)
    tax, pretax = cd.value("tax_expense", fy), cd.value("pretax_income", fy)
    t_eff = _div(tax, pretax)
    nd = net_debt(cd, fy)
    eq = cd.value("equity", fy)
    interest = cd.value("interest_expense", fy)

    ebitda = None if (ebit is None or da is None) else ebit + da
    nopat = None if (ebit is None or t_eff is None) else ebit * (1 - t_eff)
    invested = None if (eq is None or nd is None) else eq + nd
    fcf_brut = None if (ocf is None or capex is None) else ocf - capex
    # FCF AJUSTÉ SBC — valorisations basées sur celui-ci UNIQUEMENT (.txt)
    fcf_adj = None if fcf_brut is None else fcf_brut - _nz(sbc)
    # Owner Earnings = OCF − D&A(proxy maintenance capex) − SBC (.txt Buffett + SBC)
    owner_earnings = None if (ocf is None or da is None) else ocf - da - _nz(sbc)

    ca, cl = cd.value("current_assets", fy), cd.value("current_liabilities", fy)
    inv, ar, ap = cd.value("inventory", fy), cd.value("ar", fy), cd.value("ap", fy)
    cogs = cd.value("cogs", fy)
    gp = cd.value("gross_profit", fy)
    if gp is None and rev is not None and cogs is not None:
        gp = rev - cogs

    dso = _div(ar, rev) and _div(ar, rev) * 365
    dio = _div(inv, cogs) and _div(inv, cogs) * 365
    dpo = _div(ap, cogs) and _div(ap, cogs) * 365

    total_debt = _nz(cd.value("lt_debt", fy)) + _nz(cd.value("st_debt", fy)) or None

    out = {
        "fy": fy,
        "ebitda": ebitda,
        "net_debt": nd,
        "nopat": nopat,
        "effective_tax_rate": t_eff,
        "invested_capital": invested,
        "roic": _div(nopat, invested),
        "kd": _div(interest, total_debt),
        "interest_coverage": _div(ebit, interest),
        "gross_margin": _div(gp, rev),
        "op_margin": _div(ebit, rev),
        "nopat_margin": _div(nopat, rev),
        "fcf_brut": fcf_brut,
        "fcf_adj": fcf_adj,
        "sbc": sbc,
        "sbc_pct_fcf": _div(sbc, fcf_brut),
        "owner_earnings": owner_earnings,
        "fcf_margin": _div(fcf_adj, rev),
        "asset_turnover": _div(rev, cd.value("total_assets", fy)),
        "current_ratio": _div(ca, cl),
        "quick_ratio": _div(None if ca is None else ca - _nz(inv), cl),
        "de_ratio": _div(total_debt, eq),
        "net_debt_ebitda": _div(nd, ebitda),
        "dso": dso, "dio": dio, "dpo": dpo,
        "ccc": (dso + dio - dpo) if None not in (dso, dio, dpo) else None,
        "ocf_ni": _div(ocf, ni),
        "accruals": None if (ni is None or ocf is None) else ni - ocf,
        "accruals_pct_rev": _div(None if (ni is None or ocf is None) else ni - ocf, rev),
        "roe": _div(ni, eq),
        "reformulation": reformulate(cd, fy),
    }
    return out


def derive_history(cd: CompanyData, n: int = 10) -> dict[int, dict]:
    years = cd.years("revenue")[-n:] or cd.years("net_income")[-n:]
    return {y: derive(cd, y) for y in years}
