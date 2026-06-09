"""
box_02_indices.py — Indices boursiers globaux.
"""

import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import INDICES

# ══════════════════════════════════════════════════════════════
# ── 1. META
# ══════════════════════════════════════════════════════════════
META = {
    "id"         : "box_02_indices",
    "titre"      : "Global Indices",
    "description": "Real-time snapshot of major global indices.",
    "icone"      : "📈",
    "largeur"    : "full",
}

# Ordre d'affichage des régions dans le template
REGIONS_ORDRE = ["USA", "EU", "ASIE", "GLOBAL"]


# ══════════════════════════════════════════════════════════════
# ── 2. QUERY
# ══════════════════════════════════════════════════════════════

def _fetch_indices(con: sqlite3.Connection) -> list[dict]:
    """
    Lit snapshot + ticker_info pour tous les indices actifs.
    Modifie les colonnes SELECT pour ajouter/retirer des champs.
    """
    rows = con.execute(
        """
        SELECT
            s.ticker,
            ti.nom,
            ti.region,
            ti.devise,
            ti.volume_flag,
            s.close,
            s.chg_pct,
            s.ret_1m,
            s.ret_1y,
            s.dma_200,
            s.above_dma200,
            s.rvol,
            s.sparkline_json,
            s.ts_update
        FROM snapshot s
        JOIN ticker_info ti ON ti.ticker = s.ticker
        WHERE ti.type = 'index'
          AND ti.actif = 1
        ORDER BY ti.region, ti.nom
""",
    ).fetchall()

    cols = [
        "ticker", "nom", "region", "devise", "volume_flag",
        "close", "chg_pct", "ret_1m", "ret_1y",
        "dma_200", "above_dma200", "rvol", "sparkline_json", "ts_update",
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
        "par_region": {
          "USA":   [ {ticker, nom, close, native_devise, convertible, chg_pct, ...}, ... ],
          "EU":    [ ... ],
          "ASIE":  [ ... ],
          "GLOBAL":[ ... ],
        },
        "total": int,
      }
    }
    Note : pas de conversion server-side — le JS client utilise fxFmt(close, native_devise).
    Les tickers de taux/volatilité ont convertible=False (VIX, TNX, IRX, DXY).
    """
    indices = _fetch_indices(con)

    # Ces tickers sont des taux / indices dimensionnels — ne pas convertir côté client
    NO_CONVERT = {"^TNX", "^IRX", "^VIX", "DX-Y.NYB"}

    par_region: dict[str, list] = {r: [] for r in REGIONS_ORDRE}

    for idx in indices:
        region = idx["region"]
        if region not in par_region:
            par_region[region] = []

        par_region[region].append({
            "ticker"       : idx["ticker"],
            "nom"          : idx["nom"],
            "close"        : round(idx["close"], 2) if idx["close"] is not None else None,
            "native_devise": idx["devise"],                          # USD, EUR, JPY…
            "convertible"  : idx["ticker"] not in NO_CONVERT,       # False → afficher tel quel
            "chg_pct"      : idx["chg_pct"],
            "ret_1m"       : idx["ret_1m"],
            "ret_1y"       : idx["ret_1y"],
            "dma_200"      : idx["dma_200"],
            "above_dma200" : idx["above_dma200"],
            "rvol"         : idx["rvol"],
            "sparkline"    : idx["sparkline_json"],
            "heures_cet"   : INDICES.get(idx["ticker"], {}).get("heures_cet"),
            "ts_update"    : idx["ts_update"],
        })

    return {
        "meta": META,
        "data": {
            "par_region": par_region,
            "currency"  : currency,
            "total"     : len(indices),
        },
    }
