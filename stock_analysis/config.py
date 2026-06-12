"""SAINHE backend — configuration centrale.
Chaque seuil référence la section du plan (SAINHE_stock_analysis_plan.txt).
AUCUNE valeur magique ailleurs dans le code.
"""

# ---------------------------------------------------------------- EDGAR (.txt Couche 1)
EDGAR_USER_AGENT = "SAINHE research hugo12.waldmeyer@gmail.com"
EDGAR_RATE_LIMIT_PER_SEC = 10          # limite SEC officielle
EDGAR_BASE_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
EDGAR_BASE_COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"
EDGAR_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
CACHE_DB_PATH = "cache/edgar_cache.sqlite"

# Tickers de validation Phase 1 (.txt §8 / prompt)
TEST_TICKERS = ["AAPL", "MSFT", "KO", "JPM", "XOM"]

# ---------------------------------------------------------------- Seuils flags (.txt Couche 2/3)
GOODWILL_RED_FLAG_PCT_ASSETS = 0.30        # Goodwill > 30% assets → attention
GOODWILL_COMPOSITE_PCT_ASSETS = 0.50       # flag composite : >50% + ROIC déclinant
ROIC_DECLINE_YEARS = 3                     # contraction 3Y+ = érosion moat
SBC_FCF_FLAG = 0.15                        # SBC > 15% FCF brut
LEASE_HEAVY_PCT_LIABILITIES = 0.20         # OperatingLeaseLiability > 20% Total Liab
ADJUSTED_NI_GAP_FLAG = 0.10                # écart NI brut/ajusté > 10%
REVERSE_DCF_IMPLIED_G_FLAG = 0.15          # implied growth > 15% = peu réaliste
ANALYST_MIN_OPINIONS = 5                   # consensus < 5 analystes = warning
DISPERSION_HIGH_RATIO = 1.5                # dispute analystes
DISPERSION_LOW_RATIO = 0.8                 # consensus trop serré

# Altman Z (.txt SCORES DE RISQUE)
ALTMAN_DISTRESS = 1.81
ALTMAN_SAFE = 2.99
# Beneish M
BENEISH_MANIPULATION = -1.78

# Buffett (.txt QUALITÉ DU BUSINESS)
LT_DEBT_PAYBACK_MAX_YEARS = 4              # seuil 3-4 ans (source secondaire)
ROE_AVG_MIN = 0.20                         # moyenne 10Y > 20%
ROE_FLOOR_MIN = 0.15                       # aucune année < 15%
RETAINED_EARNINGS_TEST_WINDOW = 5          # rolling 5Y
RETAINED_EARNINGS_TEST_MIN = 1.0           # ratio > 1.0 = création de valeur

# ---------------------------------------------------------------- Valorisation (.txt Couche 3)
WACC_SENSITIVITY_BPS = 0.01                # EPV à WACC ±100bps
FCF_CONFIDENCE_PCTL = (25, 75)             # plage de confiance p25–p75
FCF_MIN_YEARS_FOR_PCTL = 4                 # fallback growth 0% si moins
RE_HORIZON_YEARS = 5                       # RE statique : 5Y + continuing value
SENSITIVITY_NOPAT_PCTL = (10, 25, 50, 75, 90)
SENSITIVITY_G_FACTORS = (0.5, 0.75, 1.0, 1.25, 1.5)   # × SGR

# Macro par défaut si le module Macro SAINHE est indisponible (override en prod)
DEFAULT_RISK_FREE = 0.042                  # 3M T-bill approx — à brancher sur Macro
DEFAULT_ERP = 0.050                        # ERP — à brancher sur Macro SAINHE
DEFAULT_BETA = 1.0                         # fallback si yfinance indisponible

# ---------------------------------------------------------------- Score composite (.txt §9, défaut)
SCORE_WEIGHTS = {
    "valuation": 0.30,           # EPV/RE vs prix
    "balance_sheet_health": 0.25,
    "earnings_quality": 0.20,
    "smart_money": 0.15,
    "momentum": 0.10,
}

# Peers (.txt §9 — tranché : SIC + market cap bucket)
PEER_MARKET_CAP_BUCKETS = [(0, 2e9), (2e9, 10e9), (10e9, 200e9), (200e9, float("inf"))]
