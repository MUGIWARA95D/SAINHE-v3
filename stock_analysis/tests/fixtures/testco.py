"""Fixture TESTCO — entreprise synthétique au format companyfacts EDGAR exact.

Valeurs choisies pour vérifier les formules à la main :
FY2023 (dernière année) :
  Revenue 1000, COGS 600 (GM 40%), EBIT 250, D&A 50, Interest 20,
  Pretax 230, Tax 46 (T=20%), NI 184
  Cash 100, ST inv 20, AR 120, Inventory 80, CurAssets 350, TotalAssets 1500
  PP&E 400, Goodwill 200, ROU 60, OpLeaseLiab 65, FinLeaseLiab 15
  AP 90, CurLiab 200, ST debt 30, LT debt 300, TotalLiab 800, Equity 700, RE 350
  OCF 260, CapEx 70, SBC 25, Dividends 40, Buybacks 30

Vérifications attendues :
  Net Debt = 300+30+15-100 = 245
  EBITDA = 300 ; NOPAT = 250×0.8 = 200 ; Invested = 700+245 = 945 ; ROIC = 21.16%
  FCF brut = 190 ; FCF ajusté = 165 ; Owner Earnings = 260-50-25 = 185
  FA = 120 ; FO = 345 ; OA = 1380 ; OO = 455 ; NOA = 925 ; NFO = 225 ; NOA-NFO = 700 = Equity ✓
  RNOA = 200/925 = 21.62% ; FLEV = 225/700 = 0.3214 ; NBC = 16/225 = 7.11%
  SPREAD = 14.51% ; ROE_dupont = 21.62 + 0.3214×14.51 = 26.28%... vs ROE direct 184/700 = 26.29% ✓
Historique 2014-2023 : croissance régulière ~6%/an, ROIC stable, GM en légère expansion.
"""
from __future__ import annotations


def _annual(tag_values: dict[int, float], unit="USD", flow=False) -> dict:
    """Construit un node companyfacts {units:{USD:[...]}} annuel 10-K."""
    items = []
    for fy, val in sorted(tag_values.items()):
        item = {"fy": fy, "fp": "FY", "form": "10-K", "val": val,
                "end": f"{fy}-12-31", "accn": f"000{fy}-23-000001"}
        if flow:
            item["start"] = f"{fy}-01-01"
        items.append(item)
    return {"units": {unit: items}}


def _grow(base: float, years: range, g: float = 0.06) -> dict[int, float]:
    out, v = {}, base
    for y in years:
        out[y] = round(v, 2)
        v *= (1 + g)
    return out


def testco_companyfacts() -> dict:
    Y = range(2014, 2024)  # 10 ans
    rev = _grow(592.0, Y)                       # → ~1000 en 2023
    rev[2023] = 1000.0
    cogs = {y: round(rev[y] * (0.63 - 0.003 * (y - 2014)), 2) for y in Y}  # GM en expansion
    cogs[2023] = 600.0
    ebit = {y: round(rev[y] * 0.25, 2) for y in Y}
    ebit[2023] = 250.0
    da = {y: round(rev[y] * 0.05, 2) for y in Y}; da[2023] = 50.0
    interest = {y: 20.0 for y in Y}
    pretax = {y: round(ebit[y] - interest[y], 2) for y in Y}; pretax[2023] = 230.0
    tax = {y: round(pretax[y] * 0.20, 2) for y in Y}; tax[2023] = 46.0
    ni = {y: round(pretax[y] - tax[y], 2) for y in Y}; ni[2023] = 184.0
    ocf = {y: round(ni[y] + da[y] + 26.0, 2) for y in Y}; ocf[2023] = 260.0
    capex = {y: round(rev[y] * 0.07, 2) for y in Y}; capex[2023] = 70.0
    sbc = {y: round(rev[y] * 0.025, 2) for y in Y}; sbc[2023] = 25.0
    ar = {y: round(rev[y] * 0.12, 2) for y in Y}; ar[2023] = 120.0
    inv = {y: round(rev[y] * 0.08, 2) for y in Y}; inv[2023] = 80.0
    ap = {y: round(rev[y] * 0.09, 2) for y in Y}; ap[2023] = 90.0
    equity = _grow(420.0, Y); equity[2023] = 700.0
    ta = _grow(900.0, Y); ta[2023] = 1500.0
    re_ = _grow(210.0, Y); re_[2023] = 350.0

    gaap = {
        "Revenues": _annual(rev, flow=True),
        "CostOfGoodsAndServicesSold": _annual(cogs, flow=True),
        "OperatingIncomeLoss": _annual(ebit, flow=True),
        "DepreciationDepletionAndAmortization": _annual(da, flow=True),
        "InterestExpense": _annual(interest, flow=True),
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
        "ExtraordinaryItemsNoncontrollingInterest": _annual(pretax, flow=True),
        "IncomeTaxExpenseBenefit": _annual(tax, flow=True),
        "NetIncomeLoss": _annual(ni, flow=True),
        "EarningsPerShareDiluted": _annual({y: round(ni[y] / 100.0, 2) for y in Y},
                                           unit="USD/shares", flow=True),
        "WeightedAverageNumberOfDilutedSharesOutstanding": _annual(
            {y: 100.0 for y in Y}, unit="shares", flow=True),
        "CashAndCashEquivalentsAtCarryingValue": _annual({y: 100.0 for y in Y}),
        "ShortTermInvestments": _annual({y: 20.0 for y in Y}),
        "AccountsReceivableNetCurrent": _annual(ar),
        "InventoryNet": _annual(inv),
        "AssetsCurrent": _annual({y: 350.0 for y in Y}),
        "Assets": _annual(ta),
        "PropertyPlantAndEquipmentNet": _annual({y: 400.0 for y in Y}),
        "OperatingLeaseRightOfUseAsset": _annual({y: 60.0 for y in range(2019, 2024)}),
        "OperatingLeaseLiability": _annual({y: 65.0 for y in range(2019, 2024)}),
        "FinanceLeaseLiability": _annual({y: 15.0 for y in range(2019, 2024)}),
        "Goodwill": _annual({y: 200.0 for y in Y}),
        "IntangibleAssetsNetExcludingGoodwill": _annual({y: 50.0 for y in Y}),
        "AccountsPayableCurrent": _annual(ap),
        "LiabilitiesCurrent": _annual({y: 200.0 for y in Y}),
        "ShortTermBorrowings": _annual({y: 30.0 for y in Y}),
        "LongTermDebtNoncurrent": _annual({y: 300.0 for y in Y}),
        "Liabilities": _annual({y: 800.0 for y in Y}),
        "StockholdersEquity": _annual(equity),
        "RetainedEarningsAccumulatedDeficit": _annual(re_),
        "NetCashProvidedByUsedInOperatingActivities": _annual(ocf, flow=True),
        "PaymentsToAcquirePropertyPlantAndEquipment": _annual(capex, flow=True),
        "ShareBasedCompensation": _annual(sbc, flow=True),
        "PaymentsForRepurchaseOfCommonStock": _annual({y: 30.0 for y in Y}, flow=True),
        "PaymentsOfDividends": _annual({y: 40.0 for y in Y}, flow=True),
    }
    return {"cik": 999999, "entityName": "TESTCO INC", "facts": {"us-gaap": gaap}}


def badco_companyfacts() -> dict:
    """Entreprise à drapeaux rouges : Goodwill 55% des actifs, ROIC déclinant 4 ans,
    SBC 30% du FCF, leases 35% du passif, impairment, OCF/NI faible."""
    base = testco_companyfacts()
    g = base["facts"]["us-gaap"]
    Y = range(2014, 2024)
    g["Goodwill"] = _annual({y: 825.0 for y in Y})                       # 55% de 1500
    # ROIC déclinant : EBIT qui chute 2020→2023
    ebit = {y: 250.0 for y in Y}
    for i, y in enumerate([2020, 2021, 2022, 2023]):
        ebit[y] = 250.0 - 30.0 * (i + 1)                                  # 220,190,160,130
    g["OperatingIncomeLoss"] = _annual(ebit, flow=True)
    pretax = {y: ebit[y] - 20.0 for y in Y}
    g["IncomeLossFromContinuingOperationsBeforeIncomeTaxes" \
      "ExtraordinaryItemsNoncontrollingInterest"] = _annual(pretax, flow=True)
    g["IncomeTaxExpenseBenefit"] = _annual({y: round(pretax[y] * .2, 2) for y in Y}, flow=True)
    ni = {y: round(pretax[y] * .8, 2) for y in Y}
    g["NetIncomeLoss"] = _annual(ni, flow=True)
    g["NetCashProvidedByUsedInOperatingActivities"] = _annual(
        {y: round(ni[y] * 0.6, 2) for y in Y}, flow=True)                # OCF/NI = 0.6 < 0.7
    g["ShareBasedCompensation"] = _annual({y: 20.0 for y in Y}, flow=True)
    g["PaymentsToAcquirePropertyPlantAndEquipment"] = _annual({y: 10.0 for y in Y}, flow=True)
    g["OperatingLeaseLiability"] = _annual({y: 280.0 for y in range(2019, 2024)})  # 35% de 800
    g["GoodwillImpairmentLoss"] = _annual({2023: 50.0}, flow=True)
    return base
