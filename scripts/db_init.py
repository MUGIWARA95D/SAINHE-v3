"""
db_init.py — Initialise la base de données SQLite SAINHE.
Idempotent : safe à re-run à tout moment (CREATE TABLE IF NOT EXISTS).
"""

import sqlite3
from pathlib import Path

import db
from config import (
    DB_PATH,
    ALL_SECTOR_ETFS,
    ALL_INDEX_TICKERS,
    SECTOR_TICKERS,
    INDICES,
    WATCHLIST,
)

DDL = """

CREATE TABLE IF NOT EXISTS prices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL    NOT NULL,
    adj_close   REAL,
    volume      INTEGER,
    UNIQUE(ticker, date)
);

CREATE TABLE IF NOT EXISTS metrics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT    NOT NULL,
    date            TEXT    NOT NULL,
    dma_50          REAL,
    dma_200         REAL,
    above_dma200    INTEGER,
    ret_1m          REAL,
    ret_3m          REAL,
    ret_6m          REAL,
    ret_1y          REAL,
    ret_2y          REAL,
    score           REAL,
    rvol            REAL,
    rvol_dir        REAL,
    obv             REAL,
    obv_dir         INTEGER,
    mfi             REAL,
    sentiment_score REAL,
    rperf_1m        REAL,
    rperf_3m        REAL,
    rperf_6m        REAL,
    rperf_1y        REAL,
    UNIQUE(ticker, date)
);

CREATE TABLE IF NOT EXISTS ticker_info (
    ticker      TEXT    PRIMARY KEY,
    nom         TEXT,
    type        TEXT    NOT NULL,
    region      TEXT,
    secteur     TEXT,
    devise      TEXT,
    volume_flag INTEGER DEFAULT 1,
    actif       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS intraday_volume (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker      TEXT    NOT NULL,
    ts          TEXT    NOT NULL,
    volume      INTEGER,
    UNIQUE(ticker, ts)
);

CREATE TABLE IF NOT EXISTS fx_rates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pair        TEXT    NOT NULL,
    ts          TEXT    NOT NULL,
    rate        REAL    NOT NULL,
    UNIQUE(pair, ts)
);

CREATE TABLE IF NOT EXISTS fx_daily (
    pair  TEXT NOT NULL,
    date  TEXT NOT NULL,
    rate  REAL NOT NULL,
    PRIMARY KEY (pair, date)
);

CREATE TABLE IF NOT EXISTS macro_bandeau (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT    NOT NULL,
    vix             REAL,
    us10y           REAL,
    us3m            REAL,
    dxy             REAL,
    erp             REAL,
    yield_curve     REAL,
    sp500_pe        REAL,
    sp500_earnings_yield REAL
);

CREATE TABLE IF NOT EXISTS rperf (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    secteur     TEXT    NOT NULL,
    region      TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    rperf_1m    REAL,
    rperf_3m    REAL,
    rperf_6m    REAL,
    rperf_1y    REAL,
    UNIQUE(secteur, region, date)
);

CREATE TABLE IF NOT EXISTS snapshot (
    ticker          TEXT    PRIMARY KEY,
    ts_update       TEXT,
    close           REAL,
    close_prev      REAL,
    chg_pct         REAL,
    dma_50          REAL,
    dma_200         REAL,
    above_dma200    INTEGER,
    ret_1m          REAL,
    ret_3m          REAL,
    ret_6m          REAL,
    ret_1y          REAL,
    ret_2y          REAL,
    score           REAL,
    rvol            REAL,
    rvol_dir        REAL,
    obv_dir         INTEGER,
    mfi             REAL,
    sentiment_score REAL,
    sentiment_label TEXT,
    rperf_1m        REAL,
    rperf_3m        REAL,
    rperf_6m        REAL,
    rperf_1y        REAL,
    sparkline_json  TEXT
);

CREATE TABLE IF NOT EXISTS macro_liquidity (
    date                TEXT PRIMARY KEY,
    ts                  TEXT,
    fed_walcl_t         REAL,
    fed_walcl_wk_pct    REAL,
    fed_walcl_date      TEXT,
    rrp_b               REAL,
    rrp_date            TEXT,
    tga_b               REAL,
    tga_date            TEXT,
    ecb_assets_t        REAL,
    ecb_assets_wk_pct   REAL,
    ecb_assets_date     TEXT,
    us_m2_yoy           REAL,
    us_m2_date          TEXT,
    eu_m3_yoy           REAL,
    eu_m3_date          TEXT,
    china_m2_yoy        REAL,
    china_m2_date       TEXT,
    global_cb_trend     TEXT,
    bund_10y            REAL,
    bund_2y             REAL,
    bund_spread         REAL,
    bund_signal         TEXT,
    bund_date           TEXT,
    jgb_10y             REAL,
    jgb_10y_date        TEXT,
    uk_10y              REAL,
    uk_10y_date         TEXT,
    hy_oas_us           REAL,
    hy_oas_us_date      TEXT,
    hy_oas_eu           REAL,
    hy_oas_eu_date      TEXT,
    hy_oas_em           REAL,
    hy_oas_em_date      TEXT,
    cape_us             REAL,
    cape_date           TEXT,
    pe_eu               REAL,
    pe_jp               REAL,
    pe_em               REAL,
    pe_cn               REAL,
    japan_m2_yoy        REAL,
    japan_m2_date       TEXT,
    gold_stocks         REAL,
    cnh_usd             REAL,
    us_tips_10y         REAL,
    us_tips_date        TEXT,
    us_breakeven_10y    REAL,
    us_breakeven_date   TEXT,
    jgb_2y              REAL,
    jgb_spread          REAL,
    jgb_signal          TEXT,
    cgb_10y             REAL,
    cgb_2y              REAL,
    cgb_spread          REAL,
    cgb_signal          TEXT,
    cgb_date            TEXT,
    copper_price        REAL,
    copper_gold_ratio   REAL,
    jpy_usd             REAL
);

CREATE TABLE IF NOT EXISTS news (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hash        TEXT    NOT NULL UNIQUE,
    source_id   INTEGER,
    region      TEXT,
    lang        TEXT,
    titre       TEXT    NOT NULL,
    lien        TEXT,
    resume      TEXT,
    ts_pub      TEXT,
    ts_fetch    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sentiment_history (
    ticker      TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    score       REAL,
    label       TEXT,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS app_state (
    key   TEXT PRIMARY KEY,
    value TEXT,
    ts    TEXT
);

"""

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
    "CREATE INDEX IF NOT EXISTS idx_sent_hist_ticker_date ON sentiment_history (ticker, date DESC);",
]

_REGION_DEVISE = {"MONDE": "USD", "USA": "USD", "EU": "EUR", "ASIE": "HKD"}


def _build_seed_rows():
    rows = []
    ticker_meta = {}
    for secteur, regions in SECTOR_TICKERS.items():
        for region, ticker in regions.items():
            if ticker and ticker not in ticker_meta:
                ticker_meta[ticker] = {"secteur": secteur, "region": region}
    for ticker, meta in ticker_meta.items():
        rows.append((
            ticker, ticker, "etf_sector", meta["region"], meta["secteur"],
            _REGION_DEVISE.get(meta["region"], "USD"), 1, 1,
        ))
    for ticker, info in INDICES.items():
        rows.append((
            ticker, info["nom"], "index", info["region"], None,
            info["devise"], 1 if info["volume"] else 0, 1,
        ))
    for ticker, info in WATCHLIST.items():
        rows.append((
            ticker, info["nom"], "watchlist", None, info.get("secteur"),
            info.get("devise", "USD"), 1, 1,
        ))
    return rows


def _add_col_if_missing(cur, table: str, column: str, col_type: str):
    existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        print(f"[db_init] Migration: added {table}.{column} ({col_type})")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = db.connect()
    cur = con.cursor()
    cur.executescript("""
        PRAGMA journal_mode = WAL;
        PRAGMA cache_size   = -32000;
        PRAGMA synchronous  = NORMAL;
        PRAGMA temp_store   = MEMORY;
    """)
    cur.executescript(DDL)
    for idx in INDEXES:
        cur.execute(idx)
    seed_rows = _build_seed_rows()
    cur.executemany(
        """
        INSERT OR IGNORE INTO ticker_info
            (ticker, nom, type, region, secteur, devise, volume_flag, actif)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        seed_rows,
    )
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
    _add_col_if_missing(cur, "macro_liquidity", "hy_oas_em",           "REAL")
    _add_col_if_missing(cur, "macro_liquidity", "hy_oas_em_date",      "TEXT")
    _add_col_if_missing(cur, "macro_liquidity", "us_tips_10y",         "REAL")
    _add_col_if_missing(cur, "macro_liquidity", "us_tips_date",        "TEXT")
    _add_col_if_missing(cur, "macro_liquidity", "us_breakeven_10y",    "REAL")
    _add_col_if_missing(cur, "macro_liquidity", "us_breakeven_date",   "TEXT")
    _add_col_if_missing(cur, "macro_liquidity", "jgb_2y",              "REAL")
    _add_col_if_missing(cur, "macro_liquidity", "jgb_spread",          "REAL")
    _add_col_if_missing(cur, "macro_liquidity", "jgb_signal",          "TEXT")
    _add_col_if_missing(cur, "macro_liquidity", "cgb_10y",             "REAL")
    _add_col_if_missing(cur, "macro_liquidity", "cgb_2y",              "REAL")
    _add_col_if_missing(cur, "macro_liquidity", "cgb_spread",          "REAL")
    _add_col_if_missing(cur, "macro_liquidity", "cgb_signal",          "TEXT")
    _add_col_if_missing(cur, "macro_liquidity", "cgb_date",            "TEXT")
    _add_col_if_missing(cur, "macro_liquidity", "copper_price",        "REAL")
    _add_col_if_missing(cur, "macro_liquidity", "copper_gold_ratio",   "REAL")
    _add_col_if_missing(cur, "macro_liquidity", "jpy_usd",             "REAL")
    _add_col_if_missing(cur, "macro_liquidity", "pe_cn",               "REAL")
    _add_col_if_missing(cur, "macro_liquidity", "japan_m2_yoy",        "REAL")
    _add_col_if_missing(cur, "macro_liquidity", "japan_m2_date",       "TEXT")
    con.commit()
    con.close()
    print(f"[db_init] Base initialisée : {DB_PATH}")
    print(f"[db_init] {len(seed_rows)} tickers seedés dans ticker_info")


if __name__ == "__main__":
    init_db()
