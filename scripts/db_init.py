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

-- ── 9. NEWS ───────────────────────────────────────────────
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
]

# ============================================================
#  SEED — ticker_info depuis config.py
# ============================================================

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
            "USD",                 # tout stocké en USD
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

    con = sqlite3.connect(DB_PATH)
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

    con.commit()
    con.close()

    print(f"[db_init] Base initialisée : {DB_PATH}")
    print(f"[db_init] {len(seed_rows)} tickers seedés dans ticker_info")


if __name__ == "__main__":
    init_db()
