"""
box_01_news.py — Fil d'actualités financières (RSS).
"""

import sqlite3
from boxes._base import get_fx_rates

# ══════════════════════════════════════════════════════════════
# ── 1. META
# ══════════════════════════════════════════════════════════════
META = {
    "id"         : "box_03_news",
    "titre"      : {
        "EN": "Market News",
        "FR": "Actualités Marchés",
        "DE": "Marktnachrichten",
        "ES": "Noticias de Mercado",
        "ZH": "市场新闻",
        "RU": "Новости рынка",
        "JA": "市場ニュース",
    },
    "description": "Latest financial news from global sources.",
    "icone"      : "📰",
    "largeur"    : "full",
}

# Nombre d'articles à afficher par région
ARTICLES_PAR_REGION = 5
REGIONS_ORDRE       = ["GLOBAL", "USA", "EU", "ASIE"]


# ══════════════════════════════════════════════════════════════
# ── 2. QUERY
# ══════════════════════════════════════════════════════════════

def _fetch_news(con: sqlite3.Connection) -> list[dict]:
    """
    Lit les N derniers articles par région.
    Modifie ARTICLES_PAR_REGION pour changer le volume affiché.
    Modifie ORDER BY pour changer le tri (ts_pub / ts_fetch).
    """
    rows = con.execute(
        """
        SELECT region, source_id, titre, lien, resume, ts_pub
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY region
                       ORDER BY ts_pub DESC NULLS LAST
                   ) AS rn
            FROM news
        )
        WHERE rn <= ?
        ORDER BY region, ts_pub DESC NULLS LAST
        """,
        (ARTICLES_PAR_REGION,),
    ).fetchall()

    return [
        {
            "region"   : r[0],
            "source_id": r[1],
            "titre"    : r[2],
            "lien"     : r[3],
            "resume"   : r[4],
            "ts_pub"   : r[5],
        }
        for r in rows
    ]


# ══════════════════════════════════════════════════════════════
# ── 3. FORMAT
# ══════════════════════════════════════════════════════════════

def render(con: sqlite3.Connection, lang: str = "EN", currency: str = "USD") -> dict:
    """
    Retourne :
    {
      "meta": META,
      "data": {
        "par_region": {
          "GLOBAL": [ {titre, lien, resume, ts_pub}, ... ],
          "USA":    [ ... ],
          "EU":     [ ... ],
          "ASIE":   [ ... ],
        },
        "total": int,
      }
    }
    """
    articles = _fetch_news(con)

    par_region: dict[str, list] = {r: [] for r in REGIONS_ORDRE}
    for a in articles:
        region = a["region"]
        if region not in par_region:
            par_region[region] = []
        par_region[region].append({
            "titre" : a["titre"],
            "lien"  : a["lien"],
            "resume": a["resume"],
            "ts_pub": a["ts_pub"],
        })

    return {
        "meta": {**META, "titre": META["titre"].get(lang, META["titre"]["EN"])},
        "data": {
            "par_region": par_region,
            "total"     : len(articles),
        },
    }
