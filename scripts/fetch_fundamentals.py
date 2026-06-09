"""
fetch_fundamentals.py — Fetch S&P 500 trailing P/E and stash in app_state.

The pipeline runs this script before calc.py. We only store the PE here;
calc.py reads it from app_state and is the sole writer to macro_bandeau.

Utilise curl_cffi Chrome impersonation (résistant au rate-limit).

Lancement :
    python scripts/fetch_fundamentals.py
"""

import sqlite3
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests as cffi

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [fetch_fundamentals] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
#  QUOTE SUMMARY — trailingPE
# ============================================================

def _get_session_with_crumb() -> tuple[object, str | None]:
    """
    Crée une session curl_cffi avec cookies Yahoo + récupère un crumb.
    Nécessaire pour query2 quoteSummary (401 sans crumb).
    """
    sess = cffi.Session(impersonate="chrome110")
    # 1. Consent cookie
    try:
        sess.get("https://fc.yahoo.com", timeout=10)
    except Exception:
        pass
    # 2. Crumb
    try:
        r = sess.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=10)
        if r.status_code == 200 and r.text and "<" not in r.text:
            return sess, r.text.strip()
    except Exception as exc:
        log.warning("crumb fetch failed: %s", exc)
    return sess, None


def fetch_trailing_pe(ticker: str = "^GSPC") -> float | None:
    """
    Retourne trailingPE via quoteSummary v10.
    Fallback : forwardPE si trailingPE absent.
    """
    sess, crumb = _get_session_with_crumb()

    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
    params = {"modules": "summaryDetail,defaultKeyStatistics"}
    if crumb:
        params["crumb"] = crumb

    try:
        resp = sess.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            log.warning("%s — HTTP %d (crumb=%s)", ticker, resp.status_code, bool(crumb))
            # Fallback : quote v7 (souvent accessible sans crumb)
            return _fetch_pe_v7(sess, ticker)

        data   = resp.json()
        result = data.get("quoteSummary", {}).get("result")
        if not result:
            log.warning("%s — réponse vide", ticker)
            return _fetch_pe_v7(sess, ticker)

        summary = result[0].get("summaryDetail", {}) or {}
        keystat = result[0].get("defaultKeyStatistics", {}) or {}

        for node in (summary.get("trailingPE"),
                     keystat.get("trailingPE"),
                     summary.get("forwardPE"),
                     keystat.get("forwardPE")):
            if isinstance(node, dict) and node.get("raw") is not None:
                return float(node["raw"])

        log.warning("%s — aucun PE dans la réponse", ticker)
        return _fetch_pe_v7(sess, ticker)

    except Exception as exc:
        log.error("%s — erreur : %s", ticker, exc)
        return None


def _fetch_pe_v7(sess, ticker: str) -> float | None:
    """Fallback : /v7/finance/quote renvoie trailingPE directement."""
    try:
        url = "https://query1.finance.yahoo.com/v7/finance/quote"
        r = sess.get(url, params={"symbols": ticker}, timeout=15)
        if r.status_code != 200:
            log.warning("%s v7 — HTTP %d", ticker, r.status_code)
            return None
        res = r.json().get("quoteResponse", {}).get("result") or []
        if not res:
            return None
        for key in ("trailingPE", "forwardPE"):
            val = res[0].get(key)
            if val is not None:
                log.info("%s — PE via v7/%s = %.2f", ticker, key, float(val))
                return float(val)
        return None
    except Exception as exc:
        log.error("%s v7 fallback — %s", ticker, exc)
        return None


# ============================================================
#  MAIN
# ============================================================

def main():
    # ^GSPC est un indice → Yahoo ne renvoie pas trailingPE pour les indices.
    # On utilise SPY (ETF qui réplique le S&P 500, market-cap weighted)
    # dont le trailingPE est ≈ celui du S&P 500 (écart < 0.5%).
    log.info("Fetch SPY trailingPE (proxy ^GSPC)…")
    pe = fetch_trailing_pe("SPY")
    if pe is None:
        log.info("SPY échoué, fallback sur IVV…")
        pe = fetch_trailing_pe("IVV")
    if pe is None:
        log.info("IVV échoué, fallback sur VOO…")
        pe = fetch_trailing_pe("VOO")

    if pe is None:
        log.warning("Aucune source PE n'a abouti — calc.py utilisera la valeur précédente.")
        return

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    con = db.connect()
    con.execute(
        "INSERT OR REPLACE INTO app_state(key, value, ts) VALUES('sp500_pe', ?, ?)",
        (f"{pe:.6f}", ts),
    )
    con.commit()
    con.close()
    log.info("sp500_pe stocké dans app_state : %.4f", pe)


if __name__ == "__main__":
    main()
