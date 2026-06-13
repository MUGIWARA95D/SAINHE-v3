"""run_demo.py — Génère les JSON Stock Analysis depuis des fixtures synthétiques.

Aucun réseau nécessaire, aucune clé API.
Les valeurs sont cohérentes (TESTCO = entreprise synthétique avec 10 ans d'historique).

Usage (depuis sainhe_backend/) :
    python run_demo.py

Résultat :
    ../output/data/stock/TESTCO_report.json    ← rapport complet
    ../output/data/stock/valuation_map.json    ← agrégat niveau 1 (front)

Pour remplacer par les vraies données :
    1. Mets ton email dans config.py → EDGAR_USER_AGENT
    2. pip install pandas numpy scipy requests yfinance
    3. python pipeline.py AAPL MSFT KO JPM XOM
"""
from __future__ import annotations
import os, sys, json, logging

# Assure-toi qu'on importe depuis ce dossier
sys.path.insert(0, os.path.dirname(__file__))

import config
from tests.fixtures.testco import testco_companyfacts, testco_submissions
from edgar.edgar_client import EdgarClient
from edgar.xbrl_parser import parse_companyfacts
from edgar.metadata_flags import metadata_flags
from output import report_builder

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("demo")

DEMO_TICKER = "TESTCO"
DEMO_CIK    = 9999999

# Prix de marché fictif (facilement remplaçable)
DEMO_PRICE  = 18.0
DEMO_YF_INFO = {
    "currentPrice": DEMO_PRICE,
    "targetMeanPrice": 20,
    "targetMedianPrice": 19.5,
    "targetHighPrice": 23,
    "targetLowPrice": 16,
    "numberOfAnalystOpinions": 12,
    "sector": "Technology",
    "beta": 1.15,
}
DEMO_PRICE_HISTORY = {y: 10.0 + (y - 2014) * 0.8 for y in range(2014, 2024)}


def main():
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    # Fixtures offline — aucun réseau
    facts      = testco_companyfacts()
    subs_raw   = testco_submissions()
    cd         = parse_companyfacts(DEMO_TICKER, DEMO_CIK, facts)
    meta       = metadata_flags(subs_raw)
    meta["_submissions_raw"] = subs_raw

    report = report_builder.build_report(
        cd,
        price=DEMO_PRICE,
        yf_info=DEMO_YF_INFO,
        edgar_meta=meta,
        gics_sector="Technology",
        price_history=DEMO_PRICE_HISTORY,
    )

    # Sauvegarde
    out_report = os.path.join(config.OUTPUT_DIR, f"{DEMO_TICKER}_report.json")
    report_builder.save(report, out_report)
    log.info("Rapport demo : %s", out_report)

    # Valuation map (niveau 1)
    vmap = report_builder.build_valuation_map([report])
    out_vmap = os.path.join(config.OUTPUT_DIR, "valuation_map.json")
    report_builder.save(vmap, out_vmap)
    log.info("Valuation map : %s", out_vmap)

    print("\n✓ Données démo générées dans output/data/stock/")
    print("  → Ouvre output/index.html pour voir le front.\n")


if __name__ == "__main__":
    main()
