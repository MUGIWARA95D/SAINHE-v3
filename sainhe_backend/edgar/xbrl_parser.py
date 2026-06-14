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

    Règles (corrigées) :
      - Une série est indexée par l'ANNÉE DE LA PÉRIODE (end[:4]), jamais par le
        champ `fy` du datapoint — ce dernier est l'exercice DU DÉPÔT 10-K, pas la
        période de la donnée (un 10-K FY2025 contient aussi les comparatifs 2024/2023).
      - Flux (start→end) : on ne garde que les durées ~annuelles (11-13 mois) pour
        écarter trimestres et cumuls partiels. Stocks de bilan (sans `start`) : instant.
      - Restatement : à période égale, le dépôt le plus récent (accn max) gagne.
      - Changement de tag US-GAAP dans le temps (ex. `Revenues` →
        `RevenueFromContractWithCustomerExcludingAssessedTax`) : le tag préféré
        couvre ses années, les tags suivants ne COMBLENT que les années manquantes.
        (Avant : `break` au 1er tag non vide → séries figées à l'ancien tag.)
    """
    cd = CompanyData(ticker=ticker, cik=cik)
    gaap = facts_json.get("facts", {}).get("us-gaap", {})
    dei = facts_json.get("facts", {}).get("dei", {})

    for internal_name, candidates in TAG_MAP.items():
        merged: dict[int, DataPoint] = {}
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
            per_tag: dict[int, DataPoint] = {}
            for item in units[unit_key]:
                if item.get("form") != "10-K":
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
                               accn=accn, form="10-K")
                # à période égale, le dépôt le plus récent (accn max) écrase = restatement
                cur = per_tag.get(period_year)
                if cur is None or accn >= cur.accn:
                    per_tag[period_year] = dp
            # le tag préféré garde ses années ; les suivants comblent les trous seulement
            for y, dp in per_tag.items():
                merged.setdefault(y, dp)
        if merged:
            cd.series[internal_name] = merged
    return cd
