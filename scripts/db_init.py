"""
db_init.py — Initialise la base de données SQLite SAINHE.
Idempotent : safe à re-run à tout moment (CREATE TABLE IF NOT EXISTS).
"""

import sqlite3
import sys
from pathlib import Path

# Ajouter le dossier parent au path pour importer config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    DB_PATH,
    ALL_SECTOR_ETFS,
    ALL_INDEX_TICKERS,
    SECTOR_TICKERS,
    INDICES,
    WATCHLIST,
)

# ============================================================
#  DDL — 9 tables
# ============================================================

DDL = """

-- ── 1. PRICES ─────────────────────────────────────────────
-- OHLCV journalier brut. Une ligne par (ticker, date).
CREATE TABLE IF NOT EXISTS prices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL,
    date        TEXT    NOT NULL,          -- ISO 8601 : "2025-04-01"
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL    NOT NULL,
    adj_close   REAL,
    volume      INTEGER,
    UNIQUE(ticker, date)
);

-- ── 2. METRICS ────────────────────────────────────────────
-- Indicateurs calculés par ticker (un snapshot par jour).
-- INSERT OR REPLACE : écrase si recalculé.
CREATE TABLE IF NOT EXISTS metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL,
    date            TEXT    NOT NULL,          -- date de calcul
    -- Moyennes mobiles
    dma_50          REAL,
    dma_200         REAL,
    above_dma200    INTEGER,                   -- 1/0
    -- Momentum (returns)
    ret_1m          REAL,
    ret_3m          REAL,
    ret_6m          REAL,
    ret_1y          REAL,
    ret_2y          REAL,
    -- Score composite
    score           REAL,
    -- Volume
    rvol            REAL,                      -- RVOL 20j
    rvol_dir        REAL,                      -- RVOL directionnel
    -- Indicateurs techniques
    obv             REAL,
    obv_dir         INTEGER,                   -- +1 / 0 / -1
    mfi             REAL,                      -- Money Flow Index 14j
    -- Sentiment
    sentiment_score REAL,                      -- -1.0 à +1.0
    -- R-Perf vs benchmark monde
    rperf_1m        REAL,
    rperf_3m        REAL,
    rperf_6m        REAL,
    rperf_1y        REAL,
    UNIQUE(ticker, date)
);

-- ── 3. TICKER_INFO ────────────────────────────────────────
-- Métadonnées statiques par ticker (nom, région, secteur…).
-- Seed au démarrage depuis config.py.
CREATE TABLE IF NOT EXISTS ticker_info (
    ticker      TEXT    PRIMARY KEY,
    nom         TEXT,
    type        TEXT    NOT NULL,   -- 'etf_sector' | 'index' | 'watchlist'
    region      TEXT,               -- 'MONDE'|'USA'|'EU'|'ASIE'|'GLOBAL'
    secteur     TEXT,               -- secteur SAINHE (pour ETFs)
    devise      TEXT,               -- 'USD'|'EUR'|'HKD'…
    volume_flag INTEGER DEFAULT 1,  -- 0 = pas de volume (indices de taux…)
    actif       INTEGER DEFAULT 1
);

-- ── 4. INTRADAY_VOLUME ────────────────────────────────────
-- Volumes horaires pour RVOL intraday (optionnel — Box 02).
CREATE TABLE IF NOT EXISTS intraday_volume (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL,
    ts          TEXT    NOT NULL,   -- ISO 8601 avec heure : "2025-04-01T14:30:00"
    volume      INTEGER,
    UNIQUE(ticker, ts)
);

-- ── 5. FX_RATES ───────────────────────────────────────────
-- Taux de change scrappés (Google Finance).
CREATE TABLE IF NOT EXISTS fx_rates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pair        TEXT    NOT NULL,   -- 'USD_EUR' | 'USD_HKD'
    ts          TEXT    NOT NULL,   -- ISO 8601 avec heure
    rate        REAL    NOT NULL,
    UNIQUE(pair, ts)
);

-- ── 5b. FX_DAILY ──────────────────────────────────────────
-- Un taux par paire par jour — conservé sur 2 ans pour ajuster les returns.
-- Alimenté par fetch_fx.py + backfill Frankfurter historique.
CREATE TABLE IF NOT EXISTS fx_daily (
    pair  TEXT NOT NULL,
    date  TEXT NOT NULL,   -- YYYY-MM-DD
    rate  REAL NOT NULL,
    PRIMARY KEY (pair, date)
);

-- ── 6. MACRO_BANDEAU ──────────────────────────────────────
-- Dernières valeurs macro pour le bandeau (VIX, TNX, IRX, DXY, ERP…).
-- Un seul enregistrement actif, remplacé à chaque fetch.
CREATE TABLE IF NOT EXISTS macro_bandeau (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,
    vix             REAL,
    us10y           REAL,
    us3m            REAL,
    dxy             REAL,
    erp             REAL,           -- Earnings yield S&P - US10Y
    yield_curve     REAL,           -- US10Y - US3M
    sp500_pe        REAL,
    sp500_earnings_yield REAL
);

-- ── 7. RPERF ──────────────────────────────────────────────
-- Performance relative régionale vs benchmark MONDE.
-- Pré-calculé pour Box 03 sector rotation.
CREATE TABLE IF NOT EXISTS rperf (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    secteur     TEXT    NOT NULL,
    region      TEXT    NOT NULL,   -- 'USA'|'EU'|'ASIE'
    date        TEXT    NOT NULL,
    rperf_1m    REAL,
    rperf_3m    REAL,
    rperf_6m    REAL,
    rperf_1y    REAL,
    UNIQUE(secteur, region, date)
);

-- ── 8. SNAPSHOT ───────────────────────────────────────────
-- Dernières valeurs pré-calculées par ticker.
-- Zéro calcul au moment du rendu HTML — 1 SELECT * suffit.
-- INSERT OR REPLACE : toujours une seule ligne par ticker.
CREATE TABLE IF NOT EXISTS snapshot (
    ticker          TEXT    PRIMARY KEY,
    ts_update       TEXT,               -- horodatage du dernier calcul
    -- Prix
    close           REAL,
    close_prev      REAL,
    chg_pct         REAL,               -- variation % J vs J-1
    -- Moyennes mobiles
    dma_50          REAL,
    dma_200         REAL,
    above_dma200    INTEGER,
    -- Momentum
    ret_1m          REAL,
    ret_3m          REAL,
    ret_6m          REAL,
    ret_1y          REAL,
    ret_2y          REAL,
    -- Score
    score           REAL,
    -- Volume
    rvol            REAL,
    rvol_dir        REAL,
    -- Indicateurs
    obv_dir         INTEGER,
    mfi             REAL,
    -- Sentiment
    sentiment_score REAL,
    sentiment_label TEXT,
    -- R-Perf
    rperf_1m        REAL,
    rperf_3m        REAL,
    rperf_6m        REAL,
    rperf_1y        REAL,
    -- Sparkline (7 jours, JSON array)
    sparkline_json  TEXT
);

-- ── 9. MACRO_LIQUIDITY ────────────────────────────────────
-- Global macro liquidity snapshot — one row per fetch date.
-- Sources: FRED API, ECB SDW, yfinance, multpl.com
-- Columns are nullable — "N/A" shown in UI when data unavailable.
CREATE TABLE IF NOT EXISTS macro_liquidity (
    date                TEXT PRIMARY KEY,   -- YYYY-MM-DD (fetch date)
    ts                  TEXT,               -- ISO datetime of fetch

    -- ── Fed / US Plumbing ────────────────────────────────────
    fed_walcl_t         REAL,               -- Fed balance sheet, trillions USD
    fed_walcl_wk_pct    REAL,               -- WoW % change
    fed_walcl_date      TEXT,               -- FRED data as-of date
    rrp_b               REAL,               -- Reverse Repo, billions USD
    rrp_date            TEXT,
    tga_b               REAL,               -- Treasury General Account, billions USD
    tga_date            TEXT,

    -- ── ECB ──────────────────────────────────────────────────
    ecb_assets_t        REAL,               -- ECB total assets, trillions EUR
    ecb_assets_wk_pct   REAL,               -- WoW % change
    ecb_assets_date     TEXT,               -- ECB data as-of date

    -- ── M2 / Money Supply ────────────────────────────────────
    us_m2_yoy           REAL,               -- US M2 YoY %
    us_m2_date          TEXT,
    eu_m3_yoy           REAL,               -- EU M3 YoY %
    eu_m3_date          TEXT,
    china_m2_yoy        REAL,               -- China M2 YoY %
    china_m2_date       TEXT,

    -- ── Global CB Trend Signal ────────────────────────────────
    global_cb_trend     TEXT,               -- 'EXPANSION' | 'CONTRACTION' | 'MIXED'

    -- ── Yield Curves ─────────────────────────────────────────
    bund_10y            REAL,               -- German Bund 10Y proxy (ECB AAA EU), %
    bund_2y             REAL,               -- German Bund 2Y proxy, %
    bund_spread         REAL,               -- 10Y − 2Y
    bund_signal         TEXT,               -- steep | flat | partial_inversion | full_inversion
    bund_date           TEXT,
    jgb_10y             REAL,               -- JGB 10Y, % (monthly FRED)
    jgb_10y_date        TEXT,
    uk_10y              REAL,               -- UK Gilt 10Y, % (monthly FRED)
    uk_10y_date         TEXT,

    -- ── Credit Spreads ────────────────────────────────────────
    hy_oas_us           REAL,               -- US HY OAS, bps (FRED BAMLH0A0HYM2 × 100)
    hy_oas_us_date      TEXT,
    hy_oas_eu           REAL,               -- EU HY OAS, bps (FRED BAMLHE00EHY2Y × 100)
    hy_oas_eu_date      TEXT,

    -- ── Valuation ────────────────────────────────────────────
    cape_us             REAL,               -- Shiller CAPE US (multpl.com)
    cape_date           TEXT,
    pe_eu               REAL,               -- P/E EU proxy via VGK ETF
    pe_jp               REAL,               -- P/E JP proxy via EWJ ETF
    pe_em               REAL,               -- P/E EM proxy via EEM ETF

    -- ── Allocation Ratios ─────────────────────────────────────
    gold_stocks         REAL,               -- (GLD × 10) / ^GSPC — oz gold per S&P point
    cnh_usd             REAL                -- USD/CNH — yuan stress indicator
);

-- ── 10. NEWS ──────────────────────────────────────────────
-- Articles RSS. Dédupliqués par hash MD5 du titre.
CREATE TABLE IF NOT EXISTS news (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hash        TEXT    NOT NULL UNIQUE,   -- MD5(titre)
    source_id   INTEGER,                   -- clé RSS_SOURCES
    region      TEXT,
    lang        TEXT,
    titre       TEXT    NOT NULL,
    lien        TEXT,
    resume      TEXT,
    ts_pub      TEXT,                      -- date publication (ISO 8601)
    ts_fetch    TEXT    NOT NULL           -- date fetch
);

"""

# ============================================================
#  INDEXES — performances read-heavy
# ============================================================

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_prices_ticker_date   ON prices  (ticker, date DESC);",
    "CREATE INDEX IF NOT EXISTS idx_metrics_ticker_date  ON metrics (ticker, date DESC);",
    "CREATE INDEX IF NOT EXISTS idx_intraday_ticker_ts   ON intraday_volume (ticker, ts DESC);",
    "CREATE INDEX IF NOT EXISTS idx_fx_pair_ts           ON fx_rates (pair, ts DESC);",
    "CREATE INDEX IF NOT EXISTS idx_rperf_secteur_date   ON rperf (secteur, region, date DESC);",
    "CREATE INDEX IF NOT EXISTS idx_news_ts_pub          ON news (ts_pub DESC);",
    "CREATE INDEX IF NOT EXISTS idx_news_region          ON news (region, ts_pub DESC);",
    "CREATE INDEX IF NOT EXISTS idx_fx_daily_pair_date ON fx_daily (pair, date DESC);",
    "CREATE INDEX IF NOT EXISTS idx_macro_liq_date      ON macro_liquidity (date DESC);",
]

# ============================================================
#  SEED — ticker_info depuis config.py
# ============================================================

# Devise native par région — EU ETFs trade en EUR, ASIE ETFs en HKD
# fetch_prices.py corrigera automatiquement via meta.currency Yahoo si différent
_REGION_DEVISE = {"MONDE": "USD", "USA": "USD", "EU": "EUR", "ASIE": "HKD"}


def _build_seed_rows():
    rows = []

    # 1) ETFs sectoriels (64 tickers, dédupliqués dans ALL_SECTOR_ETFS)
    # Construire un mapping ticker → {secteur, region} depuis SECTOR_TICKERS
    ticker_meta = {}
    for secteur, regions in SECTOR_TICKERS.items():
        for region, ticker in regions.items():
            if ticker and ticker not in ticker_meta:
                ticker_meta[ticker] = {"secteur": secteur, "region": region}
            # Si le même ticker apparaît pour plusieurs secteurs/régions,
            # on garde le premier rencontré (idem ALL_SECTOR_ETFS)

    for ticker, meta in ticker_meta.items():
        rows.append((
            ticker,
            ticker,                # nom = ticker par défaut (yfinance le mettra à jour)
            "etf_sector",
            meta["region"],
            meta["secteur"],
            _REGION_DEVISE.get(meta["region"], "USD"),  # devise native par région
            1,                     # volume_flag
            1,                     # actif
        ))

    # 2) Indices globaux
    for ticker, info in INDICES.items():
        rows.append((
            ticker,
            info["nom"],
            "index",
            info["region"],
            None,                  # pas de secteur SAINHE
            info["devise"],
            1 if info["volume"] else 0,
            1,
        ))

    # 3) Watchlist personnelle
    for ticker, info in WATCHLIST.items():
        rows.append((
            ticker,
            info["nom"],
            "watchlist",
            None,
            info.get("secteur"),
            info.get("devise", "USD"),   # devise native (JPY, CHF, GBP…) ou USD par défaut
            1,
            1,
        ))

    return rows


# ============================================================
#  MAIN
# ============================================================

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(DB_PATH, timeout=30)
    cur = con.cursor()

    # Pragmas performance
    cur.executescript("""
        PRAGMA journal_mode = WAL;
        PRAGMA cache_size   = -32000;   -- 32 MB
        PRAGMA synchronous  = NORMAL;
        PRAGMA temp_store   = MEMORY;
    """)

    # Tables
    cur.executescript(DDL)

    # Indexes
    for idx in INDEXES:
        cur.execute(idx)

    # Seed ticker_info (INSERT OR IGNORE — ne touche pas les lignes existantes)
    seed_rows = _build_seed_rows()
    cur.executemany(
        """
        INSERT OR IGNORE INTO ticker_info
            (ticker, nom, type, region, secteur, devise, volume_flag, actif)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        seed_rows,
    )

    # Migration : met à jour la devise des tickers watchlist dont le config.py
    # définit explicitement une devise non-USD (les lignes existantes ont "USD" hardcodé).
    watchlist_devises = [
        (info["devise"], ticker)
        for ticker, info in WATCHLIST.items()
        if "devise" in info
    ]
    if watchlist_devises:
        cur.executemany(
            "UPDATE ticker_info SET devise = ? WHERE ticker = ? AND type = 'watchlist'",
            watchlist_devises,
        )
        print(f"[db_init] {len(watchlist_devises)} devises watchlist mises à jour")

    # Migration : met à jour la devise des ETFs sectoriels EU/ASIE (étaient tous "USD")
    ticker_meta = {}
    for secteur, regions in SECTOR_TICKERS.items():
        for region, ticker in regions.items():
            if ticker and ticker not in ticker_meta:
                ticker_meta[ticker] = {"secteur": secteur, "region": region}
    etf_devises = [
        (_REGION_DEVISE.get(meta["region"], "USD"), ticker)
        for ticker, meta in ticker_meta.items()
        if _REGION_DEVISE.get(meta["region"], "USD") != "USD"
    ]
    if etf_devises:
        cur.executemany(
            "UPDATE ticker_info SET devise = ? WHERE ticker = ? AND type = 'etf_sector'",
            etf_devises,
        )
        print(f"[db_init] {len(etf_devises)} devises etf_sector mises à jour")

    con.commit()
    con.close()

    print(f"[db_init] Base initialisée : {DB_PATH}")
    print(f"[db_init] {len(seed_rows)} tickers seedés dans ticker_info")


if __name__ == "__main__":
    init_db()
