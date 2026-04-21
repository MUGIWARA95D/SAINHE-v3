"""
fetch_fundamentals.py — Fetch ^GSPC trailingPE via Yahoo quoteSummary v10
                       puis met à jour macro_bandeau (VIX, yields, DXY, PE, ERP).

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
from config import DB_PATH

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
#  MACRO BANDEAU
# ============================================================

def _latest_close(con: sqlite3.Connection, ticker: str) -> float | None:
    row = con.execute(
        "SELECT close FROM prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
        (ticker,),
    ).fetchone()
    return row[0] if row else None


def update_macro_bandeau(con: sqlite3.Connection, sp500_pe: float | None):
    vix   = _latest_close(con, "^VIX")
    us10y = _latest_close(con, "^TNX")
    us3m  = _latest_close(con, "^IRX")
    dxy   = _latest_close(con, "DX-Y.NYB")

    yield_curve = None
    if us10y is not None and us3m is not None:
        yield_curve = round(us10y - us3m, 4)

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
        "macro_bandeau — VIX=%.2f | US10Y=%.2f%% | US3M=%.2f%% | DXY=%.2f | curve=%s | PE=%s | EY=%s | ERP=%s",
        vix or 0, us10y or 0, us3m or 0, dxy or 0,
        f"{yield_curve:+.4f}" if yield_curve is not None else "N/A",
        f"{sp500_pe:.2f}"      if sp500_pe      is not None else "N/A",
        f"{earnings_yld:.4%}"  if earnings_yld  is not None else "N/A",
        f"{erp:+.4%}"          if erp           is not None else "N/A",
    )


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

    con = sqlite3.connect(DB_PATH)
    update_macro_bandeau(con, pe)
    con.close()
    log.info("Terminé.")


if __name__ == "__main__":
    main()
