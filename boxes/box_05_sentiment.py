"""
box_04_sentiment.py — Sentiment par secteur (MFI + OBV + DMA200).
"""

import sqlite3

# ══════════════════════════════════════════════════════════════
# ── 1. META
# ══════════════════════════════════════════════════════════════
META = {
    "id"         : "box_05_sentiment",
    "titre"      : {
        "EN": "Sentiment Analysis",
        "FR": "Analyse du Sentiment",
        "DE": "Stimmungsanalyse",
        "ES": "Análisis de Sentimiento",
        "ZH": "情绪分析",
        "RU": "Анализ настроений",
        "JA": "センチメント分析",
    },
    "description": "Composite sentiment score per sector (MFI 40% + OBV 30% + DMA200 30%).",
    "icone"      : "🧭",
    "largeur"    : "full",
}

# Filtre de région pour le sentiment affiché par défaut
# Modifie pour changer la région de référence (MONDE = benchmark global)
REGION_DEFAUT = "MONDE"

# Labels sentiment par score (doit correspondre à SENTIMENT_THRESHOLDS dans config.py)
LABELS_COLOR = {
    "Euphoric"     : "#C62828",   # rouge — surchauffe
    "Accumulation" : "#2E7D32",   # vert
    "Neutral"      : "#9E9E9E",   # gris
    "Caution"      : "#F57C00",   # orange
    "Bearish"      : "#C62828",   # rouge
    "Extreme Fear" : "#7B1FA2",   # violet
}


# ══════════════════════════════════════════════════════════════
# ── 2. QUERY
# ══════════════════════════════════════════════════════════════

def _fetch_sentiment(con: sqlite3.Connection, region: str) -> list[dict]:
    """
    Lit le sentiment pour tous les ETFs de la région donnée.
    Modifie `region` ou enlève le filtre WHERE pour changer la sélection.
    Modifie les colonnes SELECT pour ajouter MFI brut, OBV_dir, etc.
    """
    rows = con.execute(
        """
        SELECT
            ti.secteur,
            ti.ticker,
            ti.region,
            s.sentiment_score,
            s.sentiment_label,
            s.mfi,
            s.obv_dir,
            s.above_dma200,
            s.rvol,
            s.chg_pct,
            s.ts_update
        FROM snapshot s
        JOIN ticker_info ti ON ti.ticker = s.ticker
        WHERE ti.type    = 'etf_sector'
          AND ti.actif   = 1
          AND ti.region  = ?
        ORDER BY s.sentiment_score DESC NULLS LAST
        """,
        (region,),
    ).fetchall()

    cols = [
        "secteur", "ticker", "region",
        "sentiment_score", "sentiment_label",
        "mfi", "obv_dir", "above_dma200",
        "rvol", "chg_pct", "ts_update",
    ]
    return [dict(zip(cols, r)) for r in rows]


def _fetch_global_avg(con: sqlite3.Connection) -> float | None:
    """
    Moyenne du sentiment sur tous les ETFs MONDE → baromètre global.
    Modifie le filtre WHERE pour changer le périmètre du baromètre.
    """
    row = con.execute(
        """
        SELECT AVG(s.sentiment_score)
        FROM snapshot s
        JOIN ticker_info ti ON ti.ticker = s.ticker
        WHERE ti.type   = 'etf_sector'
          AND ti.region = 'MONDE'
          AND s.sentiment_score IS NOT NULL
        """,
    ).fetchone()
    return round(row[0], 4) if row and row[0] is not None else None


# ══════════════════════════════════════════════════════════════
# ── 3. FORMAT
# ══════════════════════════════════════════════════════════════

def render(con: sqlite3.Connection, lang: str = "EN", currency: str = "USD") -> dict:
    """
    Retourne :
    {
      "meta": META,
      "data": {
        "region"        : "MONDE",
        "global_avg"    : float (-1 à +1),
        "global_label"  : str,
        "secteurs"      : [
          {
            secteur, ticker, region,
            sentiment_score, sentiment_label, couleur,
            mfi, obv_dir, above_dma200,
            rvol, chg_pct
          },
          ...  (trié par score DESC)
        ]
      }
    }
    """
    region   = REGION_DEFAUT
    items    = _fetch_sentiment(con, region)
    avg      = _fetch_global_avg(con)

    # Label global basé sur la moyenne
    global_label = _score_to_label(avg) if avg is not None else "N/A"

    secteurs_out = []
    for item in items:
        secteurs_out.append({
            "secteur"        : item["secteur"],
            "ticker"         : item["ticker"],
            "region"         : item["region"],
            "sentiment_score": item["sentiment_score"],
            "sentiment_label": item["sentiment_label"] or "N/A",
            "couleur"        : LABELS_COLOR.get(item["sentiment_label"], "#9E9E9E"),
            "mfi"            : item["mfi"],
            "obv_dir"        : item["obv_dir"],
            "above_dma200"   : item["above_dma200"],
            "rvol"           : item["rvol"],
            "chg_pct"        : item["chg_pct"],
        })

    return {
        "meta": {**META, "titre": META["titre"].get(lang, META["titre"]["EN"])},
        "data": {
            "region"      : region,
            "global_avg"  : avg,
            "global_label": global_label,
            "secteurs"    : secteurs_out,
        },
    }


def _score_to_label(score: float) -> str:
    if score >= 0.6:  return "Euphoric"
    if score >= 0.1:  return "Accumulation"
    if score >= 0.0:  return "Neutral"
    if score >= -0.1: return "Caution"
    if score >= -0.6: return "Bearish"
    return "Extreme Fear"
