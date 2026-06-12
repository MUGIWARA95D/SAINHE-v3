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
    # st_debt est SYNTHÉTISÉ après parsing (voir _build_st_debt) : DebtCurrent
    # (englobant) prioritaire, sinon somme des composantes — Apple p.ex. répartit
    # sa dette CT entre CommercialPaper et LongTermDebtCurrent (vérif Phase 1).
    "_st_debt_umbrella": ["DebtCurrent"],
    "_st_borrowings": ["ShortTermBorrowings", "NotesAndLoansPayable"],
    "_commercial_paper": ["CommercialPaper"],
    "_lt_debt_current": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    # NB : LongTermDebtAndCapitalLeaseObligations INCLUT les finance leases —
    # metrics.financial_debt() le détecte via DataPoint.tag pour ne pas les recompter.
    "lt_debt": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations", "LongTermDebt"],
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
}


@dataclass
class DataPoint:
    value: float
    fy: int                # fiscal year
    end: str               # date de fin de période
    accn: str              # accession number = filing source (traçabilité .txt Couche 4)
    form: str = "10-K"
    tag: str = ""          # tag US-GAAP source (traçabilité + gardes anti double-comptage)


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
        dp = self.point(name, fy)
        return dp.value if dp else None

    def point(self, name: str, fy: int | None = None) -> DataPoint | None:
        """DataPoint complet (valeur + tag source) ou None."""
        s = self.series.get(name)
        if not s:
            return None
        if fy is None:
            fy = max(s)
        return s.get(fy)

    def years(self, name: str) -> list[int]:
        return sorted(self.series.get(name, {}))

    def history(self, name: str, n: int = 10) -> dict[int, float]:
        s = self.series.get(name, {})
        return {y: s[y].value for y in sorted(s)[-n:]}


def parse_companyfacts(ticker: str, cik: int, facts_json: dict) -> CompanyData:
    """Construit les séries annuelles depuis le JSON companyfacts EDGAR.

    Règles :
    - on retient les points avec form 10-K et fp == 'FY' (annuels) ;
    - une valeur par fiscal year — pour un même fy, le point avec la date de
      fin la plus récente gagne (un 10-K contient les périodes comparatives
      N-1/N-2 sous le même fy), puis l'accession la plus récente (restatements) ;
    - entre tags candidats, le PRIMAIRE est celui dont les données vont le plus
      loin dans le temps (gère les transitions de tags type ASC 606 : Apple a
      cessé 'Revenues' en 2018 pour 'RevenueFromContractWithCustomer…'), les
      autres candidats ne servent qu'à backfiller les années manquantes.
    """
    cd = CompanyData(ticker=ticker, cik=cik)
    gaap = facts_json.get("facts", {}).get("us-gaap", {})
    dei = facts_json.get("facts", {}).get("dei", {})

    def _parse_tag(tag_name, node) -> dict[int, DataPoint]:
        units = node.get("units", {})
        # USD pour les montants, shares/pure pour le reste — on prend la 1re unité dispo
        unit_key = next((u for u in ("USD", "USD/shares", "shares", "pure") if u in units),
                        next(iter(units), None))
        if not unit_key:
            return {}
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
                    if (int(end[:4]) - int(start[:4])) not in (0, 1):
                        continue  # garde : cumuls multi-année tagués par certains émetteurs
                except ValueError:
                    pass
            dp = DataPoint(value=float(val), fy=int(fy), end=end or "",
                           accn=item.get("accn", ""), form="10-K", tag=tag_name)
            # même fy : end max gagne (période courante > comparatif N-1 du même filing),
            # puis accn max (le filing le plus récent écrase = restatement pris en compte)
            prev = picked.get(dp.fy)
            if prev is None or (dp.end, dp.accn) >= (prev.end, prev.accn):
                picked[dp.fy] = dp
        return picked

    for internal_name, candidates in TAG_MAP.items():
        parsed = []
        for tag in candidates:
            node = gaap.get(tag) or dei.get(tag)
            if not node:
                continue
            picked = _parse_tag(tag, node)
            if picked:
                parsed.append(picked)
        if not parsed:
            continue
        # primaire = série la plus récente (tie-break : ordre de préférence TAG_MAP)
        primary = max(parsed, key=lambda s: max(s))
        # backfill : années absentes du primaire, dans l'ordre de préférence
        for other in parsed:
            if other is primary:
                continue
            for fy, dp in other.items():
                if fy not in primary:
                    primary[fy] = dp
        cd.series[internal_name] = primary

    _build_st_debt(cd)
    return cd


def _build_st_debt(cd: CompanyData) -> None:
    """Série synthétique st_debt (dette financière courante complète).

    Par année : DebtCurrent (tag englobant) si présent ; sinon
    base courte (ShortTermBorrowings, qui inclut généralement le commercial
    paper — sinon CommercialPaper seul) + portion courante de la dette LT.
    Évite le double comptage ShortTermBorrowings/CommercialPaper.
    """
    umbrella = cd.series.pop("_st_debt_umbrella", {})
    stb      = cd.series.pop("_st_borrowings", {})
    cp       = cd.series.pop("_commercial_paper", {})
    ltc      = cd.series.pop("_lt_debt_current", {})

    years = set(umbrella) | set(stb) | set(cp) | set(ltc)
    if not years:
        return
    out: dict[int, DataPoint] = {}
    for fy in years:
        if fy in umbrella:
            out[fy] = umbrella[fy]
            continue
        base = stb.get(fy) or cp.get(fy)
        parts = [p for p in (base, ltc.get(fy)) if p is not None]
        if not parts:
            continue
        ref = max(parts, key=lambda p: (p.end, p.accn))
        out[fy] = DataPoint(value=sum(p.value for p in parts), fy=fy,
                            end=ref.end, accn=ref.accn, form=ref.form,
                            tag="+".join(p.tag for p in parts))
    if out:
        cd.series["st_debt"] = out
