"""Segment reporting géographique (.txt Bloc I, point 70).

XBRL stocke ces ventilations en dimensions (StatementGeographicalAxis), absentes
de companyfacts en facts plats. v1 : on tente d'extraire un ratio US / non-US
depuis les frames si disponibles, sinon depuis yfinance.country. Limitation
documentée dans la note du JSON ; jamais d'invention.
"""
from __future__ import annotations
from edgar.xbrl_parser import CompanyData


def geographic_exposure(cd: CompanyData, yf_info: dict | None) -> dict:
    """Retourne {us_pct, non_us_pct, source, note}. Best-effort, dégradation propre.

    Stratégies par ordre de fiabilité :
      1. Tag XBRL natif companyfacts (rare mais fiable quand présent)
      2. yfinance country (proxy grossier : 100% si US-HQ, sinon non-US)
      3. N/D propre
    """
    # Stratégie 1 : tag XBRL natif si présent dans les séries parsées
    # (cf. extension TAG_MAP : us_revenue, foreign_revenue si on choisit de les ajouter)
    us_rev = cd.value("us_revenue")
    foreign_rev = cd.value("foreign_revenue")
    total_rev = cd.value("revenue")
    if us_rev is not None and total_rev:
        return {"us_pct": us_rev / total_rev,
                "non_us_pct": 1 - us_rev / total_rev,
                "source": "XBRL natif",
                "note": "valeurs extraites du companyfacts ; précision selon le tagging de l'émetteur"}

    # Stratégie 2 : proxy via yfinance country (grossier mais documenté)
    country = (yf_info or {}).get("country")
    if country:
        if country.upper() in ("UNITED STATES", "USA", "US"):
            return {"us_pct": None, "non_us_pct": None,
                    "source": "yfinance country (HQ)",
                    "country": country,
                    "note": "HQ US ; ventilation revenus géographiques non disponible "
                            "sans parsing dimensionnel XBRL (Phase 6) — voir 10-K Item 1"}
        return {"us_pct": None, "non_us_pct": None,
                "source": "yfinance country (HQ)",
                "country": country,
                "note": f"HQ {country} ; ventilation US/non-US indisponible en v1"}

    return {"us_pct": None, "non_us_pct": None, "source": None,
            "note": "Aucune source géographique disponible"}
