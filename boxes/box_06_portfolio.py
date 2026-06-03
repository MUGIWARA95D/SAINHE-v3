"""
box_06_portfolio.py — Scanner watchlist personnelle.
"""

import sqlite3

# ══════════════════════════════════════════════════════════════
# ── 1. META
# ══════════════════════════════════════════════════════════════
META = {
    "id"         : "box_06_portfolio",
    "titre"      : {
        "EN": "Portfolio Scanner",
        "FR": "Scanner Portefeuille",
        "DE": "Portfolio-Scanner",
        "ES": "Escáner de Cartera",
        "ZH": "投资组合扫描",
        "RU": "Сканер портфеля",
        "JA": "ポートフォリオスキャナー",
    },
    "description": "Technical scan of your personal watchlist.",
    "icone"      : "🔍",
    "largeur"    : "full",
}

# Tri par défaut de la watchlist
# Modifie pour changer le critère : "score" | "chg_pct" | "ret_1y" | "ret_3m"
TRI_DEFAUT      = "score"
TRI_DESCENDANT  = True


# ══════════════════════════════════════════════════════════════
# ── 2. QUERY
# ══════════════════════════════════════════════════════════════

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
            s.score,
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

    # No sentiment_score / sentiment_label — the composite was retired (it had
    # no academic validation). Portfolio relies on the momentum score (a
    # weighted blend of returns over 4 timeframes) + the same independent
    # signals exposed in Rotation (DMA200 / MFI / OBV).
    cols = [
        "ticker", "nom", "secteur", "devise",
        "close", "chg_pct",
        "ret_1m", "ret_3m", "ret_6m", "ret_1y",
        "score",
        "dma_50", "dma_200", "above_dma200",
        "rvol", "rvol_dir",
        "mfi", "obv_dir",
        "sparkline_json", "ts_update",
    ]
    return [dict(zip(cols, r)) for r in rows]


# ══════════════════════════════════════════════════════════════
# ── 3. FORMAT
# ══════════════════════════════════════════════════════════════

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
            score,
            dma_50, dma_200, above_dma200,
            rvol, rvol_dir,
            mfi, obv_dir,
            signal,           ← synthèse : "BUY" | "WATCH" | "AVOID"
            sparkline_json,
            ts_update,
          },
          ...  (trié par score DESC par défaut)
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
            "score"          : item["score"],
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
        "meta": {**META, "titre": META["titre"].get(lang, META["titre"]["EN"])},
        "data": {
            "currency": currency,
            "tickers" : tickers_out,
            "total"   : len(tickers_out),
        },
    }


def _build_evidence(item: dict) -> str:
    """
    Texte lisible résumant les signaux clés du ticker.
    Modifie ici pour changer les champs affichés dans la colonne Evidence.
    """
    parts = []
    sc = item.get("score")
    if sc is not None:
        parts.append(f"Score: {sc:+.2f}")
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
    Synthetic signal based on momentum score + DMA200 + OBV direction.
    Modify thresholds here to tweak the logic.
      BUY   : momentum > 0.05  AND DMA200 above  AND OBV not distributing
      AVOID : momentum < -0.05  OR  DMA200 below + OBV distributing
      WATCH : otherwise
    The previous version also required a positive 'sentiment_score' (composite
    MFI/OBV/DMA200). That composite has been retired — the same information now
    enters via DMA + OBV explicitly, no arbitrary 40/30/30 weighting.
    """
    score = item.get("score")
    above = item.get("above_dma200")
    obv   = item.get("obv_dir")

    if score is None:
        return "N/A"

    distributing = (obv == -1)
    accumulating = (obv == 1)

    if score > 0.05 and above == 1 and not distributing:
        return "BUY"
    if score < -0.05 or (above == 0 and distributing):
        return "AVOID"
    return "WATCH"
