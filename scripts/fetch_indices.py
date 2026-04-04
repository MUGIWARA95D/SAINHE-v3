"""
fetch_indices.py — Fetch OHLCV pour les 15 indices globaux + màj macro_bandeau.
Différence avec fetch_prices.py : run plus fréquent possible (intraday),
et écrit dans macro_bandeau (VIX, yield curve, ERP approximatif).

Lancement :
    python scripts/fetch_indices.py
"""

import sqlite3
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    DB_PATH,
    ALL_INDEX_TICKERS,
    INDICES,
    YFINANCE_HISTORY,
)

# ============================================================
#  CONFIG
# ============================================================

SLEEP_RETRY  = 60.0
MAX_RETRIES  = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [fetch_indices] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
#  FETCH OHLCV INDICES
# ============================================================

def fetch_indices_ohlcv(period: str = "5d") -> dict:
    """
    Télécharge OHLCV pour tous les indices en un seul appel yfinance.
    Retourne {ticker: DataFrame}.
    """
    ticker_str = " ".join(ALL_INDEX_TICKERS)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = yf.download(
                tickers=ticker_str,
                period=period,
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if raw.empty:
                log.warning("Réponse yfinance vide (tentative %d)", attempt)
                time.sleep(SLEEP_RETRY)
                continue

            result = {}
            if len(ALL_INDEX_TICKERS) == 1:
                df = raw.copy()
                df.columns = [c.lower() for c in df.columns]
                result[ALL_INDEX_TICKERS[0]] = df.dropna(subset=["close"])
            else:
                for t in ALL_INDEX_TICKERS:
                    if t not in raw.columns.get_level_values(0):
                        continue
                    df = raw[t].copy()
                    df.columns = [c.lower() for c in df.columns]
                    df = df.dropna(subset=["close"])
                    if not df.empty:
                        result[t] = df

            log.info("%d indices fetchés", len(result))
            return result

        except Exception as exc:
            msg = str(exc).lower()
            wait = SLEEP_RETRY if ("429" in msg or "rate" in msg) else 5.0
            log.warning("Erreur (tentative %d/%d) : %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(wait)

    log.error("Abandon après %d tentatives.", MAX_RETRIES)
    return {}


# ============================================================
#  INSERT PRICES
# ============================================================

def insert_prices(con: sqlite3.Connection, data: dict) -> int:
    rows = []
    for ticker, df in data.items():
        for date_idx, row in df.iterrows():
            rows.append((
                ticker,
                date_idx.strftime("%Y-%m-%d"),
                float(row.get("open",  0) or 0) or None,
                float(row.get("high",  0) or 0) or None,
                float(row.get("low",   0) or 0) or None,
                float(row["close"]),
                float(row["close"]),
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
    return cur.rowcount


# ============================================================
#  MACRO BANDEAU
# ============================================================

def _latest_close(con: sqlite3.Connection, ticker: str) -> float | None:
    """Dernière valeur close connue pour un ticker."""
    row = con.execute(
        "SELECT close FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    return row[0] if row else None


def _sp500_pe(con: sqlite3.Connection) -> float | None:
    """
    P/E approximatif S&P 500 depuis les métriques si déjà calculé,
    sinon None (calc.py le remplira plus tard).
    """
    row = con.execute(
        "SELECT sp500_pe FROM macro_bandeau ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None


def update_macro_bandeau(con: sqlite3.Connection):
    """
    Calcule et insère une ligne dans macro_bandeau avec les dernières valeurs.
    """
    vix   = _latest_close(con, "^VIX")
    us10y = _latest_close(con, "^TNX")   # en % (ex: 4.32)
    us3m  = _latest_close(con, "^IRX")   # en % (ex: 5.25)
    dxy   = _latest_close(con, "DX-Y.NYB")

    # Yield curve = US10Y - US3M (négatif = inversé)
    yield_curve = None
    if us10y is not None and us3m is not None:
        yield_curve = round(us10y - us3m, 4)

    # ERP = earnings yield S&P 500 - US10Y (en décimal)
    # earnings yield = 1 / P/E  — P/E récupéré si déjà en base
    sp500_pe     = _sp500_pe(con)
    erp          = None
    earnings_yld = None
    if sp500_pe and us10y:
        earnings_yld = round(1.0 / sp500_pe, 6)
        erp          = round(earnings_yld - (us10y / 100), 6)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    con.execute(
        """
        INSERT INTO macro_bandeau
            (ts, vix, us10y, us3m, dxy, erp, yield_curve, sp500_pe, sp500_earnings_yield)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts, vix, us10y, us3m, dxy, erp, yield_curve, sp500_pe, earnings_yld),
    )
    con.commit()

    log.info(
        "macro_bandeau — VIX=%.2f | US10Y=%.2f%% | US3M=%.2f%% | DXY=%.2f | curve=%s",
        vix or 0, us10y or 0, us3m or 0, dxy or 0,
        f"{yield_curve:+.4f}" if yield_curve is not None else "N/A",
    )


# ============================================================
#  MAIN
# ============================================================

def main():
    con  = sqlite3.connect(DB_PATH)
    data = fetch_indices_ohlcv(period="5d")

    if data:
        n = insert_prices(con, data)
        log.info("%d nouvelles lignes dans prices", n)
    else:
        log.warning("Aucune donnée indices fetchée — macro_bandeau quand même mis à jour.")

    update_macro_bandeau(con)
    con.close()
    log.info("Terminé.")


if __name__ == "__main__":
    main()
