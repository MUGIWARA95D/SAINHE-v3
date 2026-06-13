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
EDGAR_USER_AGENT = "SAINHE research contact@sainhe.com"   # ← CHANGE TON EMAIL ICI
EDGAR_RATE_LIMIT_PER_SEC = 10
EDGAR_BASE_SUBMISSIONS   = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
EDGAR_BASE_COMPANYFACTS  = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"
EDGAR_TICKER_MAP_URL     = "https://www.sec.gov/files/company_tickers.json"

# Chemins — relatifs au dossier sainhe_backend/
CACHE_DB_PATH = os.path.join(os.path.dirname(__file__), "cache", "edgar_cache.sqlite")
OUTPUT_DIR    = os.path.join(os.path.dirname(__file__), "..", "output", "data", "stock")

# Tickers de validation Phase 1 (.txt §8 / prompt)
TEST_TICKERS = ["AAPL", "MSFT", "KO", "JPM", "XOM"]

# Tickers SAINHE complets (portfolio) — à compléter
PORTFOLIO_TICKERS = ["AAPL", "MSFT", "KO", "JPM", "XOM"]

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

