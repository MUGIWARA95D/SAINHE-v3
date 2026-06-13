"""AJUSTEMENT DES EARNINGS — preprocessing obligatoire avant toute valorisation
(.txt Couche 3, premier bloc). Cas de référence : ADI 2018, NI brut $1.49B vs ajusté $2.01B.

Items transitoires retirés (tags XBRL, .txt liste) :
  goodwill_impairment, restructuring, asset_disposal_gain (signe inversé), acquisition_costs.
Taxes one-time : non détectables par tag fiable → hors périmètre v1, documenté.
"""
from __future__ import annotations
import config
from edgar.xbrl_parser import CompanyData

TRANSITORY_ADDBACK = ["goodwill_impairment", "restructuring", "acquisition_costs"]
TRANSITORY_DEDUCT = ["asset_disposal_gain"]  # un gain one-time GONFLE les earnings → on le retire


def adjust(cd: CompanyData, fy: int | None = None) -> dict:
    fy = fy or (cd.years("net_income") or [None])[-1]
    if fy is None:
        return {"fy": None, "ni_brut": None, "ni_adj": None, "ebit_adj": None,
                "adjustments": [], "gap_flag": False}

    ni = cd.value("net_income", fy)
    ebit = cd.value("ebit", fy)
    tax = cd.value("tax_expense", fy)
    pretax = cd.value("pretax_income", fy)
    t = (tax / pretax) if (tax is not None and pretax not in (None, 0)) else 0.0

    adjustments, pretax_addback = [], 0.0
    for name in TRANSITORY_ADDBACK:
        v = cd.value(name, fy)
        if v:
            pretax_addback += v
            dp = cd.series[name][fy]
            adjustments.append({"item": name, "amount": v, "direction": "addback",
                                "source_accn": dp.accn, "end": dp.end})
    for name in TRANSITORY_DEDUCT:
        v = cd.value(name, fy)
        if v:
            pretax_addback -= v
            dp = cd.series[name][fy]
            adjustments.append({"item": name, "amount": v, "direction": "deduct",
                                "source_accn": dp.accn, "end": dp.end})

    ebit_adj = None if ebit is None else ebit + pretax_addback
    ni_adj = None if ni is None else ni + pretax_addback * (1 - t)
    gap = (abs(ni_adj - ni) / abs(ni)) if (ni not in (None, 0) and ni_adj is not None) else 0.0

    return {
        "fy": fy, "ni_brut": ni, "ni_adj": ni_adj, "ebit_brut": ebit, "ebit_adj": ebit_adj,
        "adjustments": adjustments,
        "gap_pct": gap,
        "gap_flag": gap > config.ADJUSTED_NI_GAP_FLAG,  # écart >10% → afficher les deux (.txt)
    }
