"""
fetch_fx.py — Récupère les taux de change USD/EUR et USD/HKD.
Source principale : api.frankfurter.app (BCE, gratuit, zéro API key, zéro rate limit).
Fallback         : yfinance (USDEUR=X / USDHKD=X).
Stocke dans fx_rates (INSERT OR IGNORE, horodatage UTC).

Lancement :
    python scripts/fetch_fx.py
"""

import sqlite3
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DB_PATH, FX_SOURCES

# ============================================================
#  CONFIG
# ============================================================

FRANKFURTER_URL = "https://api.frankfurter.app/latest?from=USD&to=EUR,HKD"
TIMEOUT         = 10
MAX_RETRIES     = 3
SLEEP_RETRY     = 10.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [fetch_fx] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
#  SOURCE 1 — Frankfurter (BCE)
# ============================================================

def _fetch_frankfurter() -> dict[str, float]:
    """
    Appelle api.frankfurter.app → {"base":"USD","rates":{"EUR":0.867,"HKD":7.83}}
    Retourne {"USD_EUR": 0.867, "USD_HKD": 7.83} ou {} sur échec.
    """
    try:
        r = requests.get(FRANKFURTER_URL, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        rates = data.get("rates", {})
        result = {}
        if "EUR" in rates:
            result["USD_EUR"] = float(rates["EUR"])
        if "HKD" in rates:
            result["USD_HKD"] = float(rates["HKD"])
        return result
    except Exception as e:
        log.warning("Frankfurter échec : %s", e)
        return {}


# ============================================================
#  SOURCE 2 — yfinance (fallback)
# ============================================================

def _fetch_yfinance() -> dict[str, float]:
    """
    Fallback : lit les taux FX depuis yfinance (USDEUR=X, USDHKD=X).
    Retourne {"USD_EUR": ..., "USD_HKD": ...} ou {} sur échec.
    """
    tickers = list(FX_SOURCES.values())   # ["USDEUR=X", "USDHKD=X"]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = yf.download(
                tickers=" ".join(tickers),
                period="2d",
                interval="1d",
                auto_adjust=True,
                progress=False,
                group_by="ticker",
            )
            if raw.empty:
                time.sleep(SLEEP_RETRY)
                continue

            result = {}
            for pair, yf_ticker in FX_SOURCES.items():
                try:
                    if len(tickers) == 1:
                        series = raw["Close"]
                    else:
                        series = raw["Close"][yf_ticker]
                    rate = series.dropna().iloc[-1]
                    result[pair] = float(rate)
                except Exception as e:
                    log.warning("Impossible d'extraire %s : %s", pair, e)

            if result:
                return result

        except Exception as exc:
            msg = str(exc).lower()
            wait = SLEEP_RETRY if ("429" in msg or "rate" in msg) else 3.0
            log.warning("yfinance tentative %d/%d : %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                time.sleep(wait)

    return {}


# ============================================================
#  FETCH (primaire + fallback)
# ============================================================

def fetch_rates() -> dict[str, float]:
    log.info("Tentative Frankfurter (BCE)…")
    rates = _fetch_frankfurter()

    if len(rates) == len(FX_SOURCES):
        for pair, rate in rates.items():
            log.info("  %s = %.6f  [frankfurter]", pair, rate)
        return rates

    log.warning("Frankfurter incomplet (%d/%d) — fallback yfinance…", len(rates), len(FX_SOURCES))
    yf_rates = _fetch_yfinance()
    # Merge : yfinance complète les paires manquantes
    for pair, rate in yf_rates.items():
        if pair not in rates:
            rates[pair] = rate
            log.info("  %s = %.6f  [yfinance]", pair, rate)

    return rates


# ============================================================
#  INSERT
# ============================================================

def insert_rates(con: sqlite3.Connection, rates: dict[str, float], ts: str):
    for pair, rate in rates.items():
        con.execute(
            "INSERT OR IGNORE INTO fx_rates (pair, ts, rate) VALUES (?, ?, ?)",
            (pair, ts, rate),
        )
    con.commit()


# ============================================================
#  MAIN
# ============================================================

def main():
    rates = fetch_rates()

    if not rates:
        log.error("Aucun taux récupéré.")
        sys.exit(1)

    ts  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    con = sqlite3.connect(DB_PATH)
    insert_rates(con, rates, ts)
    con.close()

    log.info("Terminé — %d/%d paires insérées (ts=%s)", len(rates), len(FX_SOURCES), ts)

    if len(rates) < len(FX_SOURCES):
        sys.exit(1)


if __name__ == "__main__":
    main()
