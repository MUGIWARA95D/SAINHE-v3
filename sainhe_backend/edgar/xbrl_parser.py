"""Couche 2 — Parsing structuré XBRL (.txt §3 Couche 2). Zéro LLM.

Extrait les tags US-GAAP (10-K) et IFRS (20-F) depuis companyfacts EDGAR, en séries
ANNUELLES, chaque point portant : valeur, fiscal year, end date, accession (filing source).
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
    "net_income": ["NetIncomeLoss", "ProfitLoss",
                   "NetIncomeLossAvailableToCommonStockholdersBasic"],
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

# Mapping IFRS (ifrs-full namespace) pour les déposants 20-F (ASML, TSM, RACE, etc.).
# Même noms internes que TAG_MAP → le résultat est fusionné dans le même CompanyData.
IFRS_TAG_MAP: dict[str, list[str]] = {
    # ---------------- INCOME STATEMENT
    "revenue": ["Revenue", "RevenueFromContractsWithCustomers"],
    "cogs": ["CostOfSales"],
    "gross_profit": ["GrossProfit"],
    "ebit": ["ProfitLossFromOperatingActivities", "OperatingProfit"],
    "dep_amort": ["DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLoss"
                  "RecognisedInProfitOrLoss",
                  "DepreciationAndAmortisationExpense"],
    "interest_expense": ["FinanceCosts", "InterestExpense"],
    "tax_expense": ["IncomeTaxExpenseContinuingOperations", "IncomeTaxExpense"],
    "pretax_income": ["ProfitLossBeforeTax"],
    "net_income": ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
    "eps_diluted": ["DilutedEarningsLossPerShare", "BasicEarningsLossPerShare"],
    "shares_diluted": ["WeightedAverageDilutedNumberOfOrdinarySharesOutstanding",
                       "WeightedAverageNumberOfSharesOutstandingBasic"],
    "shares_outstanding": ["NumberOfSharesOutstanding", "IssuedCapitalOrdinaryShares"],
    # ---------------- BALANCE SHEET
    "cash": ["CashAndCashEquivalents", "CashAndCashEquivalentsClassifiedAsPartOfDisposalGroup"],
    "ar": ["TradeAndOtherCurrentReceivables", "TradeAndOtherReceivables"],
    "inventory": ["Inventories"],
    "current_assets": ["CurrentAssets"],
    "total_assets": ["Assets"],
    "ppe_net": ["PropertyPlantAndEquipment"],
    "goodwill": ["Goodwill"],
    "intangibles": ["IntangibleAssetsOtherThanGoodwill"],
    "ap": ["TradeAndOtherCurrentPayables"],
    "current_liabilities": ["CurrentLiabilities"],
    "lt_debt": ["NoncurrentPortionOfLongtermBorrowings", "LongtermBorrowings",
                "NoncurrentBorrowings"],
    "total_liabilities": ["Liabilities"],
    "equity": ["EquityAttributableToOwnersOfParent", "Equity"],
    "retained_earnings": ["RetainedEarnings"],
    # ---------------- CASH FLOW
    "ocf": ["CashFlowsFromUsedInOperatingActivities"],
    "capex": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
              "AcquisitionOfPropertyPlantAndEquipment"],
    "sbc": ["ExpenseFromShareBasedPaymentTransactionsWithEmployees", "ShareBasedCompensation"],
    "buybacks": ["RepurchaseOfTreasuryShares", "PaymentsForRepurchaseOfOrdinaryShares"],
    "dividends_paid": ["DividendsPaidClassifiedAsFinancingActivities", "DividendsPaid"],
    # ---------------- ITEMS TRANSITOIRES
    "goodwill_impairment": ["ImpairmentLossRecognisedInProfitOrLossGoodwill"],
    "restructuring": ["RestructuringCosts"],
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


def _extract_series(node: dict, forms: frozenset[str]) -> dict[int, "DataPoint"]:
    """Extrait une série annuelle depuis un node companyfacts {units:{...:[...]}}"""
    units = node.get("units", {})
    unit_key = next((u for u in ("USD", "USD/shares", "shares", "pure") if u in units),
                    next(iter(units), None))
    if not unit_key:
        return {}
    per_tag: dict[int, DataPoint] = {}
    for item in units[unit_key]:
        if item.get("form") not in forms:
            continue
        val, end = item.get("val"), item.get("end")
        if val is None or not end:
            continue
        start = item.get("start")
        if start:  # flux : ne garder que les périodes ~annuelles
            try:
                months = (int(end[:4]) * 12 + int(end[5:7])) - \
                         (int(start[:4]) * 12 + int(start[5:7]))
            except (ValueError, IndexError):
                continue
            if not (11 <= months <= 13):
                continue
        try:
            period_year = int(end[:4])
        except ValueError:
            continue
        accn = item.get("accn", "")
        dp = DataPoint(value=float(val), fy=period_year, end=end,
                       accn=accn, form=item.get("form", ""))
        cur = per_tag.get(period_year)
        if cur is None or accn >= cur.accn:
            per_tag[period_year] = dp
    return per_tag


def parse_companyfacts(
    ticker: str,
    cik: int,
    facts_json: dict,
    forms: tuple[str, ...] = ("10-K",),
) -> "CompanyData":
    """Construit les séries annuelles depuis le JSON companyfacts EDGAR.

    Règles :
      - Indexée par l'ANNÉE DE LA PÉRIODE (end[:4]), jamais par item["fy"].
      - Flux (start→end) : durées ~annuelles (11-13 mois) seulement.
      - Restatement : à période égale, accn max gagne.
      - Tag migration : tags candidats MERGENT, pas break au premier.
      - forms=("20-F",) : cherche aussi dans ifrs-full (IFRS_TAG_MAP).
    """
    cd = CompanyData(ticker=ticker, cik=cik)
    facts = facts_json.get("facts", {})
    gaap = facts.get("us-gaap", {})
    dei = facts.get("dei", {})
    ifrs = facts.get("ifrs-full", {})

    allowed = frozenset(forms)

    for internal_name, candidates in TAG_MAP.items():
        merged: dict[int, DataPoint] = {}
        for tag in candidates:
            node = gaap.get(tag) or dei.get(tag)
            if not node:
                continue
            for y, dp in _extract_series(node, allowed).items():
                merged.setdefault(y, dp)
        # Pour les déposants 20-F : compléter avec IFRS quand le tag GAAP est absent
        if ifrs and "20-F" in allowed:
            for tag in IFRS_TAG_MAP.get(internal_name, []):
                node = ifrs.get(tag)
                if not node:
                    continue
                for y, dp in _extract_series(node, allowed).items():
                    merged.setdefault(y, dp)
        if merged:
            cd.series[internal_name] = merged
    return cd
