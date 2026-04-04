"""
box_03_sectors.py — Rotation sectorielle (16 secteurs × 4 régions).
"""

import sqlite3
from boxes._base import get_fx_rates

# ══════════════════════════════════════════════════════════════
# ── 1. META
# ══════════════════════════════════════════════════════════════
META = {
    "id"         : "box_03_sectors",
    "titre"      : {
        "EN": "Sector Rotation",
        "FR": "Rotation Sectorielle",
        "DE": "Sektorrotation",
        "ES": "Rotación Sectorial",
        "ZH": "板块轮动",
        "RU": "Ротация секторов",
        "JA": "セクターローテーション",
    },
    "description": "Momentum scores and relative performance across 16 sectors × 4 regions.",
    "icone"      : "🔄",
    "largeur"    : "full",
}

# Ordre d'affichage des secteurs (correspond à SECTOR_TICKERS dans config.py)
# Modifie cette liste pour changer l'ordre ou masquer des secteurs
SECTEURS_ORDRE = [
    "Tech & Semis", "Robotics & MedTech", "Healthcare & Pharma",
    "Finance & Transac.", "Strategic Materials", "Energy",
    "Defense & Aerospace", "EV & Clean Energy", "Space",
    "Luxury", "Agriculture", "Infra & Water",
    "Consumer Staples", "Digital Assets", "Industrials", "Chemicals",
]

REGIONS_ORDRE = ["MONDE", "USA", "EU", "ASIE"]


# ══════════════════════════════════════════════════════════════
# ── 2. QUERY
# ══════════════════════════════════════════════════════════════

def _fetch_etf_snapshots(con: sqlite3.Connection) -> dict[tuple, dict]:
    """
    Lit snapshot + ticker_info pour tous les ETFs sectoriels.
    Retourne un dict {(secteur, region): données}.
    Modifie les colonnes SELECT pour ajouter des indicateurs.
    """
    rows = con.execute(
        """
        SELECT
            ti.secteur,
            ti.region,
            ti.ticker,
            s.close,
            s.chg_pct,
            s.ret_1m,
            s.ret_3m,
            s.ret_6m,
            s.ret_1y,
            s.score,
            s.above_dma200,
            s.sparkline_json
        FROM snapshot s
        JOIN ticker_info ti ON ti.ticker = s.ticker
        WHERE ti.type = 'etf_sector'
          AND ti.actif = 1
        """,
    ).fetchall()

    cols = [
        "secteur", "region", "ticker", "close", "chg_pct",
        "ret_1m", "ret_3m", "ret_6m", "ret_1y",
        "score", "above_dma200", "sparkline_json",
    ]
    result = {}
    for r in rows:
        d = dict(zip(cols, r))
        result[(d["secteur"], d["region"])] = d
    return result


def _fetch_rperf(con: sqlite3.Connection) -> dict[tuple, dict]:
    """
    Lit la dernière R-Perf par (secteur, region).
    Modifie les fenêtres SELECT pour changer les colonnes R-Perf affichées.
    """
    rows = con.execute(
        """
        SELECT secteur, region, rperf_1m, rperf_3m, rperf_6m, rperf_1y
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY secteur, region
                       ORDER BY date DESC
                   ) AS rn
            FROM rperf
        )
        WHERE rn = 1
        """,
    ).fetchall()

    result = {}
    for r in rows:
        result[(r[0], r[1])] = {
            "rperf_1m": r[2],
            "rperf_3m": r[3],
            "rperf_6m": r[4],
            "rperf_1y": r[5],
        }
    return result


# ══════════════════════════════════════════════════════════════
# ── 3. FORMAT
# ══════════════════════════════════════════════════════════════

def render(con: sqlite3.Connection, lang: str = "EN", currency: str = "USD") -> dict:
    """
    Retourne :
    {
      "meta": META,
      "data": {
        "secteurs": [
          {
            "nom": "Tech & Semis",
            "regions": {
              "MONDE": { ticker, close, chg_pct, ret_1m..ret_1y, score, above_dma200, rperf_1m..rperf_1y, sparkline },
              "USA":   { ... },
              "EU":    { ... },
              "ASIE":  { ... },
            }
          },
          ...  (16 secteurs)
        ]
      }
    }
    """
    snaps  = _fetch_etf_snapshots(con)
    rperfs = _fetch_rperf(con)

    secteurs_out = []
    for secteur in SECTEURS_ORDRE:
        regions_out = {}
        for region in REGIONS_ORDRE:
            snap  = snaps.get((secteur, region), {})
            rperf = rperfs.get((secteur, region), {})

            if not snap:
                regions_out[region] = None
                continue

            regions_out[region] = {
                "ticker"      : snap.get("ticker"),
                "close"       : snap.get("close"),
                "chg_pct"     : snap.get("chg_pct"),
                "ret_1m"      : snap.get("ret_1m"),
                "ret_3m"      : snap.get("ret_3m"),
                "ret_6m"      : snap.get("ret_6m"),
                "ret_1y"      : snap.get("ret_1y"),
                "score"       : snap.get("score"),
                "above_dma200": snap.get("above_dma200"),
                "sparkline"   : snap.get("sparkline_json"),
                # R-Perf vs MONDE (absent pour MONDE lui-même)
                "rperf_1m"    : rperf.get("rperf_1m"),
                "rperf_3m"    : rperf.get("rperf_3m"),
                "rperf_6m"    : rperf.get("rperf_6m"),
                "rperf_1y"    : rperf.get("rperf_1y"),
            }

        secteurs_out.append({
            "nom"    : secteur,
            "regions": regions_out,
        })

    return {
        "meta": {**META, "titre": META["titre"].get(lang, META["titre"]["EN"])},
        "data": {
            "secteurs"      : secteurs_out,
            "regions_ordre" : REGIONS_ORDRE,
        },
    }
