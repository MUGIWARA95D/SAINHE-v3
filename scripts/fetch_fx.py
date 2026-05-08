"""
fetch_fx.py — Récupère les taux de change USD/XXX pour toutes les paires de FX_SOURCES.
Source principale : api.frankfurter.app (BCE, gratuit, zéro API key, zéro rate limit).
Fallback         : yfinance (USDXXX=X).
Stocke dans fx_rates (INSERT OR IGNORE, horodatage UTC).

Paires couvertes : USD/EUR, USD/HKD (affichage) + USD/JPY, USD/CHF, USD/GBP,
                   USD/CNY, USD/ILS, USD/SAR (conversion prix portefeuille).

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

# Currencies to fetch — derived from FX_SOURCES keys ("USD_EUR" → "EUR")
_FX_TARGETS      = [k.split("_")[1] for k in FX_SOURCES]
FRANKFURTER_URL  = f"https://api.frankfurter.app/latest?from=USD&to={','.join(_FX_TARGETS)}"
TIMEOUT          = 10
MAX_RETRIES      = 3
SLEEP_RETRY      = 10.0

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
    Appelle api.frankfurter.app → {"base":"USD","rates":{"EUR":0.867,"HKD":7.83,...}}
    Retourne {"USD_EUR": 0.867, "USD_HKD": 7.83, ...} pour toutes les paires disponibles.
    Note : Frankfurter (BCE) ne couvre pas toutes les devises (ex: SAR, ILS) — yfinance
           prend le relais pour les paires manquantes.
    """
    try:
        r = requests.get(FRANKFURTER_URL, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        rates = data.get("rates", {})
        result = {}
        for pair in FX_SOURCES:
            target = pair.split("_")[1]   # "USD_EUR" → "EUR"
            if target in rates:
                result[pair] = float(rates[target])
                log.info("  %s = %.6f  [frankfurter]", pair, result[pair])
        return result
    except Exception as e:
        log.warning("Frankfurter échec : %s", e)
        return {}


# ============================================================
#  SOURCE 2 — yfinance (fallback)
# ============================================================

def _fetch_yfinance() -> dict[str, float]:
    """
    Fallback : lit les taux FX depuis yfinance (USDXXX=X).
    Retourne {"USD_XXX": rate, ...} ou {} sur échec.
    Note : avec group_by='ticker', l'accès est raw[yf_ticker]['Close'],
           indépendamment du nombre de tickers.
    """
    tickers = list(FX_SOURCES.values())

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
                    series = raw[yf_ticker]["Close"]
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
    log.info("Tentative Frankfurter (BCE)… (%d paires demandées)", len(FX_SOURCES))
    rates = _fetch_frankfurter()

    if len(rates) == len(FX_SOURCES):
        return rates

    missing = [p for p in FX_SOURCES if p not in rates]
    log.warning("Frankfurter incomplet (%d/%d) — fallback yfinance pour : %s",
                len(rates), len(FX_SOURCES), ", ".join(missing))
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

    missing = [p for p in FX_SOURCES if p not in rates]
    if missing:
        # Certaines devises exotiques (SAR…) ne sont pas couvertes par Frankfurter/yfinance.
        # Ce n'est pas bloquant — les tickers concernés afficheront le badge devise natif.
        log.warning("Paires manquantes (affichage badge natif): %s", ", ".join(missing))
    # Ne pas sys.exit(1) pour des paires optionnelles — les 7/8 paires critiques suffisent.


if __name__ == "__main__":
    main()
