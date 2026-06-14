"""SAINHE backend — configuration centrale.
Chaque seuil référence la section du plan (SAINHE_stock_analysis_plan.txt).
AUCUNE valeur magique ailleurs dans le code.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 CE QUE TU DOIS CONFIGURER AVANT D'UTILISER LES VRAIES DONNÉES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 1. EDGAR_USER_AGENT : mets TON email (obligatoire — la SEC bloque sans ça)
    → EDGAR_USER_AGENT = "SAINHE research TON_EMAIL@domaine.com"

 2. Installer les dépendances :
    pip install pandas numpy scipy requests yfinance

 3. Lancer le backend (depuis le dossier sainhe_backend/) :
    python pipeline.py AAPL MSFT KO JPM XOM

 4. Pour générer les données de démo SANS internet :
    python run_demo.py

 Les JSON de sortie vont dans ../output/data/stock/
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os

# ---------------------------------------------------------------- EDGAR (.txt Couche 1)
# ⚠️  OBLIGATOIRE : la SEC exige un User-Agent avec email valide
EDGAR_USER_AGENT = "SAINHE research hugo24.waldmeyer@gmail.com"
EDGAR_RATE_LIMIT_PER_SEC = 10
EDGAR_BASE_SUBMISSIONS   = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
EDGAR_BASE_COMPANYFACTS  = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"
EDGAR_TICKER_MAP_URL     = "https://www.sec.gov/files/company_tickers.json"

# Chemins — relatifs au dossier sainhe_backend/
CACHE_DB_PATH = os.path.join(os.path.dirname(__file__), "cache", "edgar_cache.sqlite")
OUTPUT_DIR    = os.path.join(os.path.dirname(__file__), "..", "output", "data", "stock")

# TTL du cache EDGAR (jours). Les fondamentaux ne bougent qu'au dépôt d'un 10-K (annuel)
# ou 10-Q (trimestriel) → inutile de re-fetcher la SEC plus de ~4×/an. 90 j couvre le
# cycle trimestriel tout en évitant le matraquage de data.sec.gov.
EDGAR_CACHE_DAYS_COMPANYFACTS = 90
EDGAR_CACHE_DAYS_SUBMISSIONS  = 90
EDGAR_CACHE_DAYS_TICKER_MAP   = 30

# ════════════════════════════════════════════════════════════════
#  PORTFOLIO SAINHE — 31 tickers exacts du dashboard (box_06_portfolio)
# ════════════════════════════════════════════════════════════════
# EDGAR (SEC) ne couvre QUE les déposants US (10-K). Les ADR étrangers
# déposent en 20-F (parsing différent), les valeurs purement étrangères /
# ETF / crypto n'ont AUCUN companyfacts EDGAR → le pipeline les saute
# proprement (log ECHEC) et continue.
#
#   ✓ EDGAR_OK      : US filers, données complètes
#   ~ ADR (20-F)    : déposent à la SEC mais format 20-F (couverture partielle)
#   ✗ NO_EDGAR      : étranger pur / ETF / crypto → pas de fondamentaux SEC

PORTFOLIO_TICKERS = [
    # ✓ US filers (10-K) — Stock Analysis complet
    "NVDA", "AAPL", "MSFT", "ISRG", "ZTS", "XOM", "LMT", "TSLA",
    "GEV", "DE", "CTVA", "ECL", "KO", "CAT",
    # ~ ADR déposant 20-F à la SEC (couverture partielle)
    "ASML", "TSM", "RACE",
    # ✗ Pas de données EDGAR (étranger pur / ETF / crypto) — sautés par le pipeline
    "6954.T", "ROG.SW", "2222.SR", "SAF.PA", "RHM.DE", "LDO.MI",
    "RMS.PA", "GEBN.SW", "NESN.SW", "COA.L", "600111.SS",
    "GLD", "KAP.L", "BTC-USD",
]

# Sous-ensemble exploitable par EDGAR (US 10-K) — sert de défaut sûr au pipeline
EDGAR_TICKERS = [
    "NVDA", "AAPL", "MSFT", "ISRG", "ZTS", "XOM", "LMT", "TSLA",
    "GEV", "DE", "CTVA", "ECL", "KO", "CAT",
]

# Tickers de validation Phase 1 (.txt §8 / prompt)
TEST_TICKERS = ["AAPL", "MSFT", "KO", "JPM", "XOM"]

# ---------------------------------------------------------------- Seuils flags (.txt Couche 2/3)
GOODWILL_RED_FLAG_PCT_ASSETS = 0.30
GOODWILL_COMPOSITE_PCT_ASSETS = 0.50
ROIC_DECLINE_YEARS = 3
SBC_FCF_FLAG = 0.15
LEASE_HEAVY_PCT_LIABILITIES = 0.20
ADJUSTED_NI_GAP_FLAG = 0.10
REVERSE_DCF_IMPLIED_G_FLAG = 0.15
ANALYST_MIN_OPINIONS = 5
DISPERSION_HIGH_RATIO = 1.5
DISPERSION_LOW_RATIO = 0.8

# Altman Z
ALTMAN_DISTRESS = 1.81
ALTMAN_SAFE = 2.99
# Beneish M
BENEISH_MANIPULATION = -1.78

# Buffett
LT_DEBT_PAYBACK_MAX_YEARS = 4
ROE_AVG_MIN = 0.20
ROE_FLOOR_MIN = 0.15
RETAINED_EARNINGS_TEST_WINDOW = 5
RETAINED_EARNINGS_TEST_MIN = 1.0

# ---------------------------------------------------------------- Valorisation
WACC_SENSITIVITY_BPS = 0.01
FCF_CONFIDENCE_PCTL = (25, 75)
FCF_MIN_YEARS_FOR_PCTL = 4
RE_HORIZON_YEARS = 5
SENSITIVITY_NOPAT_PCTL = (10, 25, 50, 75, 90)
SENSITIVITY_G_FACTORS = (0.5, 0.75, 1.0, 1.25, 1.5)

# Macro par défaut (override en prod via module Macro SAINHE)
DEFAULT_RISK_FREE = 0.042
DEFAULT_ERP = 0.050
DEFAULT_BETA = 1.0

# ---------------------------------------------------------------- Score composite
SCORE_WEIGHTS = {
    "valuation":          0.30,
    "balance_sheet_health": 0.25,
    "earnings_quality":   0.20,
    "smart_money":        0.15,
    "momentum":           0.10,
}

# Peers
PEER_MARKET_CAP_BUCKETS = [(0, 2e9), (2e9, 10e9), (10e9, 200e9), (200e9, float("inf"))]
