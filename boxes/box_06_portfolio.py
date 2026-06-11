"""
box_06_portfolio.py — Scanner watchlist personnelle.
"""

import sqlite3

# ════════════════════════════════════════════════════════════
# ── 1. META
# ════════════════════════════════════════════════════════════
META = {
    "id"         : "box_06_portfolio",
    "titre"      : "Portfolio Scanner",
    "description": "Technical scan of your personal watchlist.",
    "icone"      : "🔍",
    "largeur"    : "full",
}

# Tri par défaut de la watchlist
# Modifie pour changer le critère : "ret_3m" | "ret_6m" | "ret_1y" | "chg_pct"
# (Le composite 'score' a été retiré pour des raisons de rigueur.)
TRI_DEFAUT      = "ret_3m"
TRI_DESCENDANT  = True


# ════════════════════════════════════════════════════════════
# ── 2. QUERY
# ════════════════════════════════════════════════════════════

def _fetch_watchlist(con: sqlite3.Connection) -> list[dict]:
    """
    Lit toutes les données de snapshot pour les tickers de type 'watchlist'.
    Modifie les colonnes SELECT pour ajouter/retirer des indicateurs.
    """
    rows = con.execute(
        """
        SELECT
            ti.ticker,
            ti.nom,
            ti.secteur,
            ti.devise,
            s.close,
            s.chg_pct,
            s.ret_1m,
            s.ret_3m,
            s.ret_6m,
            s.ret_1y,
            s.dma_50,
            s.dma_200,
            s.above_dma200,
            s.rvol,
            s.rvol_dir,
            s.mfi,
            s.obv_dir,
            s.sparkline_json,
            s.ts_update
        FROM ticker_info ti
        LEFT JOIN snapshot s ON s.ticker = ti.ticker
        WHERE ti.type  = 'watchlist'
          AND ti.actif = 1
        """,
    ).fetchall()

    # Portfolio surfaces only documented, defensible signals:
    #   - explicit returns (1M/3M/6M/1Y, raw price math)
    #   - DMA200 above/below (classical 200-day MA cross)
    #   - RVOL (volume vs 20-day average — standard liquidity gauge)
    #   - MFI 50d + OBV 90d direction (Quong-Soudack '89, Granville '63)
    # No composite scores — retired entirely from this box.
    cols = [
        "ticker", "nom", "secteur", "devise",
        "close", "chg_pct",
        "ret_1m", "ret_3m", "ret_6m", "ret_1y",
        "dma_50", "dma_200", "above_dma200",
        "rvol", "rvol_dir",
        "mfi", "obv_dir",
        "sparkline_json", "ts_update",
    ]
    return [dict(zip(cols, r)) for r in rows]


# ════════════════════════════════════════════════════════════
# ── 3. FORMAT
# ════════════════════════════════════════════════════════════

def render(con: sqlite3.Connection, lang: str = "EN", currency: str = "USD") -> dict:
    """
    Retourne :
    {
      "meta": META,
      "data": {
        "currency": str,
        "tickers": [
          {
            ticker, nom, secteur,
            close (converti), chg_pct,
            ret_1m, ret_3m, ret_6m, ret_1y,
            dma_50, dma_200, above_dma200,
            rvol, rvol_dir,
            mfi, obv_dir,
            signal,           ← synthèse : "BUY" | "WATCH" | "AVOID"
            sparkline_json,
            ts_update,
          },
          ...  (trié par ret_3m DESC par défaut)
        ],
        "total": int,
      }
    }
    """
    items = _fetch_watchlist(con)

    # Tri
    items_sorted = sorted(
        items,
        key=lambda x: (x[TRI_DEFAUT] is None, x[TRI_DEFAUT] or 0),
        reverse=TRI_DESCENDANT,
    )

    tickers_out = []
    for item in items_sorted:
        signal = _compute_signal(item)

        tickers_out.append({
            "ticker"         : item["ticker"],
            "nom"            : item["nom"],
            "secteur"        : item["secteur"],
            "native_devise"  : item["devise"] or "USD",  # devise native pour fxFmt côté client
            "close"          : round(item["close"], 2)   if item["close"]   is not None else None,
            "dma_50"         : round(item["dma_50"], 2)  if item["dma_50"]  is not None else None,
            "dma_200"        : round(item["dma_200"], 2) if item["dma_200"] is not None else None,
            "chg_pct"        : item["chg_pct"],
            "ret_1m"         : item["ret_1m"],
            "ret_3m"         : item["ret_3m"],
            "ret_6m"         : item["ret_6m"],
            "ret_1y"         : item["ret_1y"],
            "above_dma200"   : item["above_dma200"],
            "rvol"           : item["rvol"],
            "rvol_dir"       : item["rvol_dir"],
            "mfi"            : item["mfi"],
            "obv_dir"        : item["obv_dir"],
            "signal"         : signal,
            "evidence"       : _build_evidence(item),
            "sparkline"      : item["sparkline_json"],
            "ts_update"      : item["ts_update"],
        })

    return {
        "meta": META,
        "data": {
            "currency": currency,
            "tickers" : tickers_out,
            "total"   : len(tickers_out),
        },
    }


def _build_evidence(item: dict) -> str:
    """
    Texte lisible résumant les signaux clés du ticker.
    Only documented signals — no composite score.
    """
    parts = []
    r3 = item.get("ret_3m")
    if r3 is not None:
        parts.append(f"3M: {r3*100:+.1f}%")
    if item.get("above_dma200") is not None:
        parts.append("DMA200: " + ("↑" if item["above_dma200"] else "↓"))
    obv = item.get("obv_dir")
    if obv is not None:
        if obv == 1:    parts.append("OBV: acc")
        elif obv == -1: parts.append("OBV: dist")
    mfi = item.get("mfi")
    if mfi is not None:
        parts.append(f"MFI: {mfi:.0f}")
    rv = item.get("rvol")
    if rv is not None:
        parts.append(f"RVOL: {rv:.2f}")
    return " · ".join(parts) if parts else "—"


def _compute_signal(item: dict) -> str:
    """
    Synthetic BUY/WATCH/AVOID built from independent documented signals
    (no composite score):

      BUY   : 3M return > +5%  AND  DMA200 above  AND  OBV not distributing
      AVOID : 3M return < −5%  OR  (DMA200 below AND OBV distributing)
      WATCH : otherwise

    3M return is the trader's de-facto medium-term trend (cf. AQR Momentum
    12-1 month signal — same family, shorter horizon).
    """
    r3    = item.get("ret_3m")
    above = item.get("above_dma200")
    obv   = item.get("obv_dir")

    if r3 is None:
        return "N/A"

    distributing = (obv == -1)

    if r3 > 0.05 and above == 1 and not distributing:
        return "BUY"
    if r3 < -0.05 or (above == 0 and distributing):
        return "AVOID"
    return "WATCH"
