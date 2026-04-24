"""
box_02_indices.py — Indices boursiers globaux.
"""

import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import INDICES
from boxes._base import get_fx_rates, convert

# ══════════════════════════════════════════════════════════════
# ── 1. META
# ══════════════════════════════════════════════════════════════
META = {
    "id"         : "box_02_indices",
    "titre"      : {
        "EN": "Global Indices",
        "FR": "Indices Globaux",
        "DE": "Globale Indizes",
        "ES": "Índices Globales",
        "ZH": "全球指数",
        "RU": "Мировые индексы",
        "JA": "グローバル指数",
    },
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
          "USA":   [ {ticker, nom, close, chg_pct, ret_1m, ret_1y, sparkline_json, ...}, ... ],
          "EU":    [ ... ],
          "ASIE":  [ ... ],
          "GLOBAL":[ ... ],
        },
        "total": int,
      }
    }
    Note : close est converti dans la devise d'affichage (currency).
    Les indices de taux (^TNX, ^IRX) et VIX ne sont PAS convertis.
    """
    fx      = get_fx_rates(con)
    indices = _fetch_indices(con)

    # Tickers dont le close ne doit PAS être converti (taux / volatilité)
    NO_CONVERT = {"^TNX", "^IRX", "^VIX", "DX-Y.NYB"}

    par_region: dict[str, list] = {r: [] for r in REGIONS_ORDRE}

    for idx in indices:
        region = idx["region"]
        if region not in par_region:
            par_region[region] = []

        close = idx["close"]
        if idx["ticker"] not in NO_CONVERT:
            close = convert(close, currency, fx)

        par_region[region].append({
            "ticker"      : idx["ticker"],
            "nom"         : idx["nom"],
            "close"       : round(close, 2) if close is not None else None,
            "devise"      : currency if idx["ticker"] not in NO_CONVERT else idx["devise"],
            "chg_pct"     : idx["chg_pct"],
            "ret_1m"      : idx["ret_1m"],
            "ret_1y"      : idx["ret_1y"],
            "dma_200"     : idx["dma_200"],
            "above_dma200": idx["above_dma200"],
            "rvol"        : idx["rvol"],
            "sparkline"   : idx["sparkline_json"],
            "heures_cet"  : INDICES.get(idx["ticker"], {}).get("heures_cet"),
            "ts_update"   : idx["ts_update"],
        })

    return {
        "meta": {**META, "titre": META["titre"].get(lang, META["titre"]["EN"])},
        "data": {
            "par_region": par_region,
            "currency"  : currency,
            "total"     : len(indices),
        },
    }
