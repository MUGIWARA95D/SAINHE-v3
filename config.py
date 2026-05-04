# ============================================================
#  SAINHE — config.py
#  Source unique de vérité.
#  Aucun calcul ici. Aucun secret ici.
#  BASE_DIR : répertoire du projet (résolu depuis ce fichier)
# ============================================================

from pathlib import Path

# ============================================================
#  1. CHEMINS
# ============================================================
BASE_DIR     = Path(__file__).resolve().parent
DB_PATH      = Path(r"G:\Mon Drive\PROJET SAINHE\SAINHE\SAINHE v2\db\sainhe.db")
CACHE_DIR    = BASE_DIR / "cache"
CACHE_NEWS   = BASE_DIR / "cache"  / "news"
OUTPUT_DIR   = BASE_DIR / "output"
TEMPLATE_DIR = BASE_DIR / "templates"

# ============================================================
#  2. TICKERS — ETFs sectoriels (4 régions × 16 secteurs)
#  Source : Table_Tickers_SAINHE_v6.xlsx
#  Clé    : secteur SAINHE → {MONDE, USA, EU, ASIE}
# ============================================================
SECTOR_TICKERS = {
    "Tech & Semis"         : {"MONDE": "IXN",     "USA": "XLK",   "EU": "EXV3.DE", "ASIE": "3191.HK"},
    "Robotics & MedTech"   : {"MONDE": "IRBO",    "USA": "ROBT",  "EU": "2B76.DE", "ASIE": "2807.HK"},
    "Healthcare & Pharma"  : {"MONDE": "IXJ",     "USA": "XLV",   "EU": "EXV4.DE", "ASIE": "2820.HK"},
    "Finance & Transac."   : {"MONDE": "IXG",     "USA": "XLF",   "EU": "EXV1.DE", "ASIE": "CHIX"},
    "Strategic Materials"  : {"MONDE": "MXI",     "USA": "IYM",   "EU": "EXV6.DE", "ASIE": "CHIM"},
    "Energy"               : {"MONDE": "IXC",     "USA": "XLE",   "EU": "EXH1.DE", "ASIE": "2809.HK"},
    "Defense & Aerospace"  : {"MONDE": "DFND",    "USA": "PPA",   "EU": "EDFS.DE", "ASIE": "PPA"},
    "EV & Clean Energy"    : {"MONDE": "ICLN",    "USA": "CNRG",  "EU": "SXR2.DE", "ASIE": "2845.HK"},
    "Space"                : {"MONDE": "UFO",     "USA": "ROKT",  "EU": "JEDI.DE", "ASIE": "UFO"},
    "Luxury"               : {"MONDE": "RXI",     "USA": "XLY",   "EU": "GLUX.DE", "ASIE": "2806.HK"},
    "Agriculture"          : {"MONDE": "VEGI",    "USA": "FTXG",  "EU": "MOOS.DE", "ASIE": "MOO"},
    "Infra & Water"        : {"MONDE": "IGF",     "USA": "PHO",   "EU": "EXV8.DE", "ASIE": "CHII"},
    "Consumer Staples"     : {"MONDE": "KXI",     "USA": "XLP",   "EU": "EXH3.DE", "ASIE": "CHIS"},
    "Digital Assets"       : {"MONDE": "IBIT",    "USA": "IBIT",  "EU": "IBIT",    "ASIE": "IBIT"},
    "Industrials"          : {"MONDE": "EXI",     "USA": "XLI",   "EU": None,      "ASIE": "3063.HK"},
    "Chemicals"            : {"MONDE": None,      "USA": "XLB",   "EU": "EXV7.DE", "ASIE": "CHIM"},
}

# Benchmark mondial par secteur — utilisé pour R-Perf
BENCHMARK_MONDE = {s: v["MONDE"] for s, v in SECTOR_TICKERS.items() if v["MONDE"]}

# Tous les ETFs uniques à fetcher (dédupliqués)
ALL_SECTOR_ETFS = list({
    t
    for region_dict in SECTOR_TICKERS.values()
    for t in region_dict.values()
    if t
})

# ============================================================
#  3. INDICES GLOBAUX
#  Source : sheet "tickers globaux" — Table_Tickers_SAINHE_v6.xlsx
# ============================================================
INDICES = {
    "^GSPC"    : {"nom": "S&P 500",     "region": "USA",    "devise": "USD", "volume": True,  "heures_cet": "15:30-22:00"},
    "^FCHI"    : {"nom": "CAC 40",      "region": "EU",     "devise": "EUR", "volume": True,  "heures_cet": "09:00-17:30"},
    "^GDAXI"   : {"nom": "DAX",         "region": "EU",     "devise": "EUR", "volume": True,  "heures_cet": "09:00-17:30"},
    "^FTSE"    : {"nom": "FTSE 100",    "region": "EU",     "devise": "GBP", "volume": True,  "heures_cet": "09:00-17:30"},
    "^N225"    : {"nom": "Nikkei 225",  "region": "ASIE",   "devise": "JPY", "volume": True,  "heures_cet": "01:00-07:30"},
    "^HSI"     : {"nom": "Hang Seng",   "region": "ASIE",   "devise": "HKD", "volume": True,  "heures_cet": "03:30-10:00"},
    "000001.SS": {"nom": "Shanghai",    "region": "ASIE",   "devise": "CNY", "volume": True,  "heures_cet": "02:30-09:00"},
    "^NSEI"    : {"nom": "Nifty 50",    "region": "ASIE",   "devise": "INR", "volume": True,  "heures_cet": "04:45-11:00"},
    "^GSPTSE"  : {"nom": "TSX",         "region": "USA",    "devise": "CAD", "volume": True,  "heures_cet": "15:30-22:00"},
    "^AXJO"    : {"nom": "ASX 200",     "region": "ASIE",   "devise": "AUD", "volume": True,  "heures_cet": "01:00-07:00"},
    "^SSMI"    : {"nom": "SMI",         "region": "EU",     "devise": "CHF", "volume": True,  "heures_cet": "09:00-17:30"},
    "^VIX"     : {"nom": "VIX",         "region": "USA",    "devise": "USD", "volume": False, "heures_cet": "15:30-22:00"},
    "DX-Y.NYB" : {"nom": "DXY",         "region": "GLOBAL", "devise": "USD", "volume": False, "heures_cet": "24h/24"},
    "^TNX"     : {"nom": "US 10Y",      "region": "USA",    "devise": "USD", "volume": False, "heures_cet": "continu"},
    "^IRX"     : {"nom": "US 3M",       "region": "USA",    "devise": "USD", "volume": False, "heures_cet": "continu"},
}

ALL_INDEX_TICKERS = list(INDICES.keys())

# ============================================================
#  4. WATCHLIST PERSONNELLE — Box 06 Portfolio Scanner
#  ⚠️ À COMPLÉTER PAR L'UTILISATEUR
#  Format : {"TICKER": {"nom": "...", "secteur": "..."}}
# ============================================================
WATCHLIST = {
    # ── Tech & Semis ──────────────────────────────────────────
    "NVDA"      : {"nom": "NVIDIA",             "secteur": "Tech & Semis"},
    "AAPL"      : {"nom": "Apple",              "secteur": "Tech & Semis"},
    "MSFT"      : {"nom": "Microsoft",          "secteur": "Tech & Semis"},
    "ASML"      : {"nom": "ASML Holding",       "secteur": "Tech & Semis"},
    "TSM"       : {"nom": "Taiwan Semi (TSMC)", "secteur": "Tech & Semis"},

    # ── Robotics & MedTech ────────────────────────────────────
    "6954.T"    : {"nom": "Fanuc",              "secteur": "Robotics & MedTech"},
    "ISRG"      : {"nom": "Intuitive Surgical", "secteur": "Robotics & MedTech"},

    # ── Healthcare & Pharma ───────────────────────────────────
    "ROG.SW"    : {"nom": "Roche",              "secteur": "Healthcare & Pharma"},
    "ZTS"       : {"nom": "Zoetis",             "secteur": "Healthcare & Pharma"},

    # ── Energy ────────────────────────────────────────────────
    "2222.SR"   : {"nom": "Saudi Aramco",       "secteur": "Energy"},
    "XOM"       : {"nom": "ExxonMobil",         "secteur": "Energy"},

    # ── Defense & Aerospace ───────────────────────────────────
    "LMT"       : {"nom": "Lockheed Martin",    "secteur": "Defense & Aerospace"},
    "SAF.PA"    : {"nom": "Safran",             "secteur": "Defense & Aerospace"},
    "RHM.DE"    : {"nom": "Rheinmetall",        "secteur": "Defense & Aerospace"},
    "KAP.IL"    : {"nom": "Elbit Systems",      "secteur": "Defense & Aerospace"},

    # ── EV & Clean Energy ─────────────────────────────────────
    "TSLA"      : {"nom": "Tesla",              "secteur": "EV & Clean Energy"},
    "GEV"       : {"nom": "GE Vernova",         "secteur": "EV & Clean Energy"},

    # ── Space ─────────────────────────────────────────────────
    # SpaceX non coté — placeholder pour quand les données seront dispo
    # "SPACEX"  : {"nom": "SpaceX",             "secteur": "Space", "actif": False},

    # ── Luxury ────────────────────────────────────────────────
    "RACE"      : {"nom": "Ferrari",            "secteur": "Luxury"},
    "RMS.PA"    : {"nom": "Hermès",             "secteur": "Luxury"},

    # ── Agriculture ───────────────────────────────────────────
    "DE"        : {"nom": "John Deere",         "secteur": "Agriculture"},
    "CTVA"      : {"nom": "Corteva",            "secteur": "Agriculture"},

    # ── Infra & Water ─────────────────────────────────────────
    "GEBN.SW"   : {"nom": "Geberit",            "secteur": "Infra & Water"},
    "ECL"       : {"nom": "Ecolab",             "secteur": "Infra & Water"},

    # ── Consumer Staples ──────────────────────────────────────
    "NESN.SW"   : {"nom": "Nestlé",             "secteur": "Consumer Staples"},
    "KO"        : {"nom": "Coca-Cola",          "secteur": "Consumer Staples"},

    # ── Industrials ───────────────────────────────────────────
    "COA.L"     : {"nom": "Coats Group",        "secteur": "Industrials"},

    # ── Strategic Materials ───────────────────────────────────
    "600111.SS" : {"nom": "Northern Rare Earth", "secteur": "Strategic Materials"},
    "GLD"       : {"nom": "SPDR Gold ETF",        "secteur": "Strategic Materials"},

    # ── Digital Assets ────────────────────────────────────────
    "BTC-USD"   : {"nom": "Bitcoin",             "secteur": "Digital Assets"},

    # ── Non cotés / données indisponibles ─────────────────────
    # SpaceX  : privé, pas de données marchés
    # Gazprom : sanctions, données inaccessibles depuis 2022
    # Décommenter quand les données seront disponibles :
    # "GAZP.ME" : {"nom": "Gazprom",            "secteur": "Energy",  "actif": False},
}

# ============================================================
#  5. CONSTANTES DE CALCUL
#  Source : sheet "colonnes à fetch.calculer" — v6.xlsx
# ============================================================
RVOL_WINDOW          = 20     # jours — standard Bloomberg
DMA_SHORT            = 50     # 50-DMA
DMA_LONG             = 200    # 200-DMA
MFI_PERIOD           = 14     # Money Flow Index
OBV_DIR_WINDOW       = 20     # jours pour direction OBV
MOMENTUM_WINDOWS     = {      # (jours trading → label)
    "1M" : 21,
    "3M" : 63,
    "6M" : 126,
    "1Y" : 252,
    "2Y" : 504,
}
SCORE_WEIGHTS        = {      # Pondération score composite
    "1M": 0.20,
    "3M": 0.30,
    "6M": 0.30,
    "1Y": 0.20,
}
SPARKLINE_DAYS       = 7      # jours calendaires pour mini-graphique
YFINANCE_HISTORY     = "2y"   # historique fetch (2 ans = assez pour tous les calculs)

# Seuils RVOL directionnel
RVOL_DIR_THRESHOLDS = {
    "strong_buy"  :  120,
    "mild_buy"    :   20,
    "neutral_low" :  -20,
    "mild_sell"   : -120,
}

# Seuils Sentiment Score
SENTIMENT_THRESHOLDS = {
    "euphoric"  :  0.6,
    "accum"     :  0.1,
    "neutral"   :  0.0,
    "caution"   : -0.1,
    "bearish"   : -0.6,
}

# Seuils macro
VIX_THRESHOLDS = {"complacency": 15, "panic": 30}
ERP_THRESHOLDS = {"attractive": 0.02, "expensive": 0.01}

# ============================================================
#  6. SOURCES RSS — fetch_news.py
#  Reuters #1 toujours inclus
# ============================================================
RSS_SOURCES = {
    1: {"url": "https://feeds.bloomberg.com/markets/news.rss",           "region": "GLOBAL", "lang": "EN"},
    2: {"url": "https://apnews.com/hub/financial-markets?format=rss",    "region": "USA",    "lang": "EN"},
    3: {"url": "https://feeds.marketwatch.com/marketwatch/topstories",   "region": "USA",    "lang": "EN"},
    4: {"url": "https://www.scmp.com/rss/91/feed",                       "region": "ASIE",   "lang": "EN"},
    5: {"url": "https://asia.nikkei.com/rss/feed/news",                  "region": "ASIE",   "lang": "EN"},
    6: {"url": "https://www.ft.com/rss/home/international",              "region": "EU",     "lang": "EN"},
    7: {"url": "https://www.lesechos.fr/rss/rss_marches.xml",            "region": "EU",     "lang": "FR"},
}

# Rotation horaire (Reuters #1 toujours inclus)
RSS_ROTATION = {
     8: [2, 4],  9: [3, 6], 10: [2, 5], 11: [3, 7],
    12: [2, 6], 13: [3, 4], 14: [2, 5], 15: [3, 6],
    16: [2, 7], 17: [3, 4], 18: [2, 6], 19: [3, 5],
    20: [2, 4], 21: [3, 6], 22: [2, 5], 23: [3, 4],
}

NEWS_RETENTION_DAYS  = 3     # purge auto — keep last 3 days
LOG_RETENTION_DAYS   = 90    # logs fetch conservés N jours

# Sources calendrier macro (scraping 08h00)
CALENDAR_SOURCES = {
    "macro"   : "https://www.marketwatch.com/economy-politics/calendar",
    "earnings": "https://stockanalysis.com/earnings-calendar/",
    "fed"     : "https://www.federalreserve.gov/feeds/press_all.xml",
    "bls"     : "https://www.bls.gov/feed/eag.rss",
    "ecb"     : "https://www.ecb.europa.eu/rss/press.html",
}

# ============================================================
#  7. TAUX DE CHANGE — fetch_fx.py (yfinance)
# ============================================================
FX_SOURCES = {
    "USD_EUR": "USDEUR=X",
    "USD_HKD": "USDHKD=X",
}

# ============================================================
#  8. LANGUES & DEVISES
# ============================================================
LANGUAGES        = ["EN", "FR", "DE", "ES", "ZH", "RU", "JA"]
DEFAULT_LANGUAGE = "EN"

CURRENCIES       = ["USD", "EUR", "HKD"]
DEFAULT_CURRENCY = "USD"
# Règle : tout stocké en USD — conversion à l'affichage uniquement

# ============================================================
#  9. DESIGN
# ============================================================
SITE_NAME   = "SAINHE"
SITE_SLOGAN = "Fundamental Intelligence"

COLORS = {
    "bg_light"  : "#FAF7F2",
    "bg_dark"   : "#1A1A1A",
    "gold"      : "#C9A84C",
    "text_light": "#2C2C2C",
    "text_dark" : "#F0EDE8",
    "positive"  : "#2E7D32",
    "negative"  : "#C62828",
    "neutral"   : "#9E9E9E",
    "warning"   : "#F57C00",
}

# ============================================================
#  10. BOX REGISTRY — render_html.py auto-découvre les boxes
#  actif=False → box ignorée au rendu
# ============================================================
BOX_REGISTRY = [
    {"id": "box_01_news",      "ordre": 1, "largeur": "full",  "actif": True},
    {"id": "box_02_indices",   "ordre": 2, "largeur": "full",  "actif": True},
    {"id": "box_03_sectors",   "ordre": 3, "largeur": "full",  "actif": True},
    {"id": "box_04_sentiment", "ordre": 4, "largeur": "full",  "actif": True},
    {"id": "box_05_macro",     "ordre": 5, "largeur": "full",  "actif": True},
    {"id": "box_06_portfolio", "ordre": 6, "largeur": "full",  "actif": True},
]
