"""Couche 2 — Parsing structuré XBRL (.txt §3 Couche 2). Zéro LLM.

Extrait les tags US-GAAP du plan depuis companyfacts, en séries ANNUELLES (10-K, forme FY),
chaque point portant : valeur, fiscal year, end date, accession (filing source).
Tag absent → absent du dict (propagé "N/D" en aval, jamais d'imputation).
"""
from __future__ import annotations
from dataclasses import dataclass, field

# Mapping nom interne -> liste de tags US-GAAP candidats (ordre de préférence).
# Les entreprises varient dans leurs tags ; on prend le premier disponible.
TAG_MAP: dict[str, list[str]] = {
    # ---------------- INCOME STATEMENT
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "SalesRevenueNet"],
    "cogs": ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"],
    "gross_profit": ["GrossProfit"],
    "opex": ["OperatingExpenses"],
    "sga": ["SellingGeneralAndAdministrativeExpense"],
    "rnd": ["ResearchAndDevelopmentExpense"],
    "ebit": ["OperatingIncomeLoss"],
    "dep_amort": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                  "DepreciationAmortizationAndAccretionNet"],
    "interest_expense": ["InterestExpense", "InterestExpenseDebt",
                         "InterestExpenseNonoperating", "InterestAndDebtExpense"],
    "tax_expense": ["IncomeTaxExpenseBenefit"],
    "pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
                      "ExtraordinaryItemsNoncontrollingInterest",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
                      "MinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "net_income": ["NetIncomeLoss"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "shares_diluted": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "shares_outstanding": ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"],
    # ---------------- BALANCE SHEET
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "st_investments": ["ShortTermInvestments", "MarketableSecuritiesCurrent"],
    "ar": ["AccountsReceivableNetCurrent"],
    "inventory": ["InventoryNet"],
    "current_assets": ["AssetsCurrent"],
    "total_assets": ["Assets"],
    "ppe_net": ["PropertyPlantAndEquipmentNet"],
    # ASC 842 (.txt NOTE ASC 842 — critique retail/airlines/restaurants)
    "rou_asset": ["OperatingLeaseRightOfUseAsset"],
    "operating_lease_liab": ["OperatingLeaseLiability"],
    "finance_lease_liab": ["FinanceLeaseLiability"],
    "goodwill": ["Goodwill"],
    "intangibles": ["IntangibleAssetsNetExcludingGoodwill",
                    "FiniteLivedIntangibleAssetsNet"],
    "ap": ["AccountsPayableCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "st_debt": ["ShortTermBorrowings", "DebtCurrent", "LongTermDebtCurrent"],
    "lt_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "total_liabilities": ["Liabilities"],
    "equity": ["StockholdersEquity",
               "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "retained_earnings": ["RetainedEarningsAccumulatedDeficit"],
    # ---------------- CASH FLOW
    "ocf": ["NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment",
              "PaymentsToAcquireProductiveAssets"],
    "sbc": ["ShareBasedCompensation"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "dividends_paid": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
    "debt_issued": ["ProceedsFromIssuanceOfLongTermDebt"],
    "debt_repaid": ["RepaymentsOfLongTermDebt"],
    # ---------------- ITEMS TRANSITOIRES (.txt AJUSTEMENT DES EARNINGS)
    "goodwill_impairment": ["GoodwillImpairmentLoss", "GoodwillAndIntangibleAssetImpairment"],
    "restructuring": ["RestructuringCharges", "RestructuringCostsAndAssetImpairmentCharges"],
    "asset_disposal_gain": ["GainLossOnDispositionOfAssets",
                            "GainLossOnSaleOfPropertyPlantEquipment"],
    "acquisition_costs": ["BusinessCombinationAcquisitionRelatedCosts"],
    # ---------------- FLAGS XBRL natifs
    "going_concern": ["SubstantialDoubtAboutGoingConcernExistence"],
    # ---------------- SEGMENT GEO (.txt Bloc I point 70 — best-effort, souvent dimensionnel)
    "us_revenue": ["RevenueFromContractWithCustomerExcludingAssessedTaxUnitedStates",
                   "RevenuesUnitedStates"],
    "foreign_revenue": ["RevenuesForeign", "ForeignCountryMember"],
}


@dataclass
class DataPoint:
    value: float
    fy: int                # fiscal year
    end: str               # date de fin de période
    accn: str              # accession number = filing source (traçabilité .txt Couche 4)
    form: str = "10-K"


@dataclass
class CompanyData:
    ticker: str
    cik: int
    series: dict[str, dict[int, DataPoint]] = field(default_factory=dict)

    def latest(self, name: str) -> DataPoint | None:
        s = self.series.get(name)
        return s[max(s)] if s else None

    def value(self, name: str, fy: int | None = None):
        """Valeur ou None ('N/D' en aval). fy=None → dernière année."""
        s = self.series.get(name)
        if not s:
            return None
        if fy is None:
            fy = max(s)
        return s[fy].value if fy in s else None

    def years(self, name: str) -> list[int]:
        return sorted(self.series.get(name, {}))

    def history(self, name: str, n: int = 10) -> dict[int, float]:
        s = self.series.get(name, {})
        return {y: s[y].value for y in sorted(s)[-n:]}


def parse_companyfacts(ticker: str, cik: int, facts_json: dict) -> CompanyData:
    """Construit les séries annuelles depuis le JSON companyfacts EDGAR.

    Règle : on retient les points avec form 10-K et fp == 'FY' (annuels),
    une valeur par fiscal year (la plus récemment filée gagne — gère les restatements).
    """
    cd = CompanyData(ticker=ticker, cik=cik)
    gaap = facts_json.get("facts", {}).get("us-gaap", {})
    dei = facts_json.get("facts", {}).get("dei", {})

    for internal_name, candidates in TAG_MAP.items():
        for tag in candidates:
            node = gaap.get(tag) or dei.get(tag)
            if not node:
                continue
            units = node.get("units", {})
            # USD pour les montants, shares/pure pour le reste — on prend la 1re unité dispo
            unit_key = next((u for u in ("USD", "USD/shares", "shares", "pure") if u in units),
                            next(iter(units), None))
            if not unit_key:
                continue
            picked: dict[int, DataPoint] = {}
            for item in units[unit_key]:
                if item.get("form") != "10-K":
                    continue
                if item.get("fp") not in (None, "FY"):
                    continue
                fy = item.get("fy")
                val = item.get("val")
                if fy is None or val is None:
                    continue
                # durée annuelle pour les flux : start→end ≈ 1 an ; les stocks n'ont pas de start
                start, end = item.get("start"), item.get("end")
                if start and end:
                    try:
                        y0, y1 = int(start[:4]), int(end[:4])
                        if (y1 - y0) > 1 or (y1 - y0) == 0 and start[5:7] == end[5:7]:
                            pass  # garde : certains émetteurs taguent des cumuls multi-année
                        if (y1 - y0) not in (0, 1):
                            continue
                    except ValueError:
                        pass
                dp = DataPoint(value=float(val), fy=int(fy), end=end or "",
                               accn=item.get("accn", ""), form="10-K")
                # le filing le plus récent (accn max ~ chronologique) écrase = restatement pris en compte
                if fy not in picked or dp.accn >= picked[fy].accn:
                    picked[fy] = dp
            if picked:
                cd.series[internal_name] = picked
                break  # premier tag candidat trouvé suffit
    return cd
