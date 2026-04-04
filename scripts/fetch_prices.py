"""
fetch_prices.py — Télécharge OHLCV via yfinance (batch 100 tickers/appel).
Stocke dans :
  - prices      : OHLCV journalier (INSERT OR IGNORE — jamais écrasé)
  - ticker_info : mise à jour du nom long si disponible

Tickers fetchés : ALL_SECTOR_ETFS + ALL_INDEX_TICKERS + WATCHLIST
Historique      : YFINANCE_HISTORY (2 ans)

Lancement :
    python scripts/fetch_prices.py            # full run
    python scripts/fetch_prices.py --mode update  # seulement les N derniers jours
"""

import sqlite3
import sys
import time
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    DB_PATH,
    ALL_SECTOR_ETFS,
    ALL_INDEX_TICKERS,
    WATCHLIST,
    YFINANCE_HISTORY,
)

# ============================================================
#  CONFIG
# ============================================================

BATCH_SIZE   = 100    # tickers par appel yfinance.download()
SLEEP_BATCH  = 2.0    # secondes entre batches (courtoisie)
SLEEP_429    = 60.0   # secondes d'attente sur rate-limit
MAX_RETRIES  = 3      # tentatives par batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [fetch_prices] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
#  HELPERS
# ============================================================

def _all_tickers() -> list[str]:
    """Déduplique les tickers : ETFs sectoriels + indices + watchlist."""
    seen = set()
    result = []
    for t in ALL_SECTOR_ETFS + ALL_INDEX_TICKERS + list(WATCHLIST.keys()):
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _batches(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def _period_for_mode(mode: str) -> str:
    """Retourne la période yfinance selon le mode."""
    if mode == "update":
        return "5d"   # 5 jours → couvre le dernier week-end
    return YFINANCE_HISTORY   # "2y"


# ============================================================
#  FETCH
# ============================================================

def fetch_batch(tickers: list[str], period: str) -> dict:
    """
    Télécharge un batch via yfinance.download().
    Retourne un dict {ticker: DataFrame(OHLCV)} ou {} sur échec.
    """
    ticker_str = " ".join(tickers)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = yf.download(
                tickers=ticker_str,
                period=period,
                interval="1d",
                group_by="ticker",
                auto_adjust=True,   # adj_close = close
                progress=False,
                threads=True,
            )
            if raw.empty:
                log.warning("Batch vide (tickers: %s…)", tickers[:3])
                return {}

            # yfinance : si 1 ticker → colonnes plates ; si N tickers → MultiIndex
            result = {}
            if len(tickers) == 1:
                df = raw.copy()
                df.columns = [c.lower() for c in df.columns]
                df = df.dropna(subset=["close"])
                result[tickers[0]] = df
            else:
                for t in tickers:
                    if t not in raw.columns.get_level_values(0):
                        continue
                    df = raw[t].copy()
                    df.columns = [c.lower() for c in df.columns]
                    df = df.dropna(subset=["close"])
                    if not df.empty:
                        result[t] = df

            return result

        except Exception as exc:
            msg = str(exc).lower()
            if "429" in msg or "rate" in msg or "too many" in msg:
                log.warning("429 rate-limit — attente %.0fs (tentative %d/%d)",
                            SLEEP_429, attempt, MAX_RETRIES)
                time.sleep(SLEEP_429)
            else:
                log.error("Erreur batch (tentative %d/%d) : %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(SLEEP_BATCH)

    log.error("Batch abandonné après %d tentatives.", MAX_RETRIES)
    return {}


# ============================================================
#  INSERT
# ============================================================

def insert_prices(con: sqlite3.Connection, ticker: str, df) -> int:
    """
    Insère les lignes OHLCV dans prices.
    INSERT OR IGNORE → ne touche pas les données existantes.
    Retourne le nombre de lignes insérées.
    """
    rows = []
    for date_idx, row in df.iterrows():
        date_str = date_idx.strftime("%Y-%m-%d")
        rows.append((
            ticker,
            date_str,
            float(row.get("open",  0) or 0) or None,
            float(row.get("high",  0) or 0) or None,
            float(row.get("low",   0) or 0) or None,
            float(row["close"]),
            float(row["close"]),    # auto_adjust=True → close == adj_close
            int(row.get("volume", 0) or 0) or None,
        ))

    cur = con.cursor()
    cur.executemany(
        """
        INSERT OR IGNORE INTO prices
            (ticker, date, open, high, low, close, adj_close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    con.commit()
    return cur.rowcount  # lignes réellement insérées


def update_ticker_names(con: sqlite3.Connection, tickers: list[str]):
    """
    Met à jour ticker_info.nom avec le longName yfinance (info par ticker).
    Appel individuel — fait seulement au full-run pour éviter 100 requêtes.
    """
    cur = con.cursor()
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).fast_info
            long_name = getattr(info, "exchange", None)   # fast_info minimal
            # On utilise Ticker.info pour le nom complet
            full_info = yf.Ticker(ticker).info
            name = full_info.get("longName") or full_info.get("shortName") or ticker
            cur.execute(
                "UPDATE ticker_info SET nom = ? WHERE ticker = ? AND nom = ?",
                (name, ticker, ticker),   # ne met à jour que si nom = ticker (valeur par défaut)
            )
            time.sleep(0.2)   # courtoisie
        except Exception as exc:
            log.debug("Impossible de récupérer le nom de %s : %s", ticker, exc)
    con.commit()


# ============================================================
#  MAIN
# ============================================================

def main(mode: str = "full"):
    period  = _period_for_mode(mode)
    tickers = _all_tickers()
    log.info("Mode=%s | période=%s | %d tickers à fetcher", mode, period, len(tickers))

    con = sqlite3.connect(DB_PATH)
    total_inserted = 0
    total_tickers  = 0

    for i, batch in enumerate(_batches(tickers, BATCH_SIZE), start=1):
        log.info("Batch %d — %d tickers (%s…)", i, len(batch), batch[:3])
        data = fetch_batch(batch, period)

        for ticker, df in data.items():
            n = insert_prices(con, ticker, df)
            total_inserted += n
            total_tickers  += 1

        if i > 1:   # pas de sleep avant le premier batch
            time.sleep(SLEEP_BATCH)

    con.close()

    log.info(
        "Terminé — %d tickers traités, %d nouvelles lignes insérées dans prices.",
        total_tickers, total_inserted,
    )

    # Mise à jour des noms seulement en full-run (économise les requêtes)
    if mode == "full":
        log.info("Mise à jour des noms longs dans ticker_info…")
        con2 = sqlite3.connect(DB_PATH)
        update_ticker_names(con2, tickers)
        con2.close()
        log.info("Noms mis à jour.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch OHLCV via yfinance")
    parser.add_argument(
        "--mode",
        choices=["full", "update"],
        default="full",
        help="full = 2 ans d'historique | update = 5 derniers jours",
    )
    args = parser.parse_args()
    main(mode=args.mode)
