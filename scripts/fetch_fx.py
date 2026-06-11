"""
fetch_fx.py — Récupère les taux de change USD/XXX pour toutes les paires de FX_SOURCES.
Source principale : api.frankfurter.app (BCE, gratuit, zéro API key, zéro rate limit).
Fallback         : yfinance (USDXXX=X).
Stocke dans :
  - fx_rates  : historique 7 jours (2 fetches/jour), pour SAINHE_FX côté client
  - fx_daily  : 1 taux par paire par jour, conservé 2 ans, pour ajuster les returns

Paires couvertes : USD/EUR, USD/HKD (affichage) + USD/JPY, USD/CHF, USD/GBP,
                   USD/CNY, USD/ILS, USD/SAR (conversion prix portefeuille).

Lancement :
    python scripts/fetch_fx.py                    # fetch + insert du jour
    python scripts/fetch_fx.py --backfill         # remplit fx_daily sur 2 ans (Frankfurter)
    python scripts/fetch_fx.py --backfill --years 1   # backfill sur 1 an
"""

import argparse
import sqlite3
import sys
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
import yfinance as yf

import db
from config import FX_SOURCES

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
#  INSERT — fx_rates (7 jours) + fx_daily (2 ans)
# ============================================================

def insert_rates(con: sqlite3.Connection, rates: dict[str, float], ts: str):
    """Insère dans fx_rates (horodaté) et fx_daily (1 par jour)."""
    today = ts[:10]   # "YYYY-MM-DD"

    for pair, rate in rates.items():
        # fx_rates — historique court (SAINHE_FX côté client)
        con.execute(
            "INSERT OR IGNORE INTO fx_rates (pair, ts, rate) VALUES (?, ?, ?)",
            (pair, ts, rate),
        )
        # fx_daily — historique long (ajustement returns calc.py).
        # OR REPLACE so the noon refetch can correct a stale morning value
        # (Frankfurter sometimes returns yesterday's value on a holiday).
        con.execute(
            "INSERT OR REPLACE INTO fx_daily (pair, date, rate) VALUES (?, ?, ?)",
            (pair, today, rate),
        )

    # Purge fx_rates : garde 7 jours glissants seulement
    con.execute("DELETE FROM fx_rates WHERE ts < datetime('now', '-7 days')")
    con.commit()


# ============================================================
#  BACKFILL — historique Frankfurter (2 ans)
# ============================================================

def backfill_fx_daily(con: sqlite3.Connection, years: int = 2):
    """
    Remplit fx_daily avec les taux historiques Frankfurter sur `years` ans.
    Utilise l'API range : api.frankfurter.app/START..END?from=USD&to=XXX,YYY
    Cibles : toutes les devises de FX_SOURCES supportées par Frankfurter (pas SAR).
    INSERT OR IGNORE — safe à relancer, ne réécrit pas l'existant.
    """
    end   = datetime.now(timezone.utc).date()
    start = end - timedelta(days=years * 365)

    # Frankfurter ne supporte pas toutes les devises — exclure SAR
    # On teste sur les targets de FX_SOURCES
    targets = [k.split("_")[1] for k in FX_SOURCES]
    url = (
        f"https://api.frankfurter.app/{start}..{end}"
        f"?from=USD&to={','.join(targets)}"
    )
    log.info("Backfill fx_daily %s → %s (%d cibles)…", start, end, len(targets))

    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error("Backfill Frankfurter échec : %s", e)
        return

    daily_rates = data.get("rates", {})   # {"2024-05-08": {"EUR": 0.915, "JPY": 154.2, ...}, ...}
    inserted = 0

    for date_str, rate_map in daily_rates.items():
        for pair in FX_SOURCES:
            target = pair.split("_")[1]
            if target in rate_map:
                con.execute(
                    "INSERT OR IGNORE INTO fx_daily (pair, date, rate) VALUES (?, ?, ?)",
                    (pair, date_str, float(rate_map[target])),
                )
                inserted += 1

    con.commit()
    log.info("Backfill terminé — %d lignes insérées dans fx_daily.", inserted)


# ============================================================
#  MAIN
# ============================================================

def main(backfill: bool = False, backfill_years: int = 2):
    con = db.connect()

    if backfill:
        backfill_fx_daily(con, years=backfill_years)
        con.close()
        return

    rates = fetch_rates()

    if not rates:
        log.error("Aucun taux récupéré.")
        con.close()
        sys.exit(1)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    insert_rates(con, rates, ts)
    con.close()

    log.info("Terminé — %d/%d paires insérées (ts=%s)", len(rates), len(FX_SOURCES), ts)

    missing = [p for p in FX_SOURCES if p not in rates]
    if missing:
        log.warning("Paires manquantes (affichage badge natif): %s", ", ".join(missing))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch FX rates (Frankfurter / yfinance)")
    parser.add_argument("--backfill", action="store_true",
                        help="Remplit fx_daily avec 2 ans d'historique Frankfurter")
    parser.add_argument("--years", type=int, default=2,
                        help="Nombre d'années à backfiller (défaut: 2)")
    args = parser.parse_args()
    main(backfill=args.backfill, backfill_years=args.years)
