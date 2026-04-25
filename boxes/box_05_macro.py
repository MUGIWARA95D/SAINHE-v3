"""
box_05_macro.py — Santé macro : VIX, Yield Curve, ERP, DXY.
"""

import sqlite3

# ══════════════════════════════════════════════════════════════
# ── 1. META
# ══════════════════════════════════════════════════════════════
META = {
    "id"         : "box_05_macro",
    "titre"      : {
        "EN": "Macro Health",
        "FR": "Santé Macro",
        "DE": "Makro-Gesundheit",
        "ES": "Salud Macro",
        "ZH": "宏观健康",
        "RU": "Макро-здоровье",
        "JA": "マクロ健全性",
    },
    "description": "ERP, yield curve inversion, VIX regime, DXY trend.",
    "icone"      : "🏛️",
    "largeur"    : "full",
}

# Seuils de régime — modifie ici pour changer les zones colorées
VIX_COMPLACENCY = 15
VIX_PANIC       = 30
ERP_ATTRACTIVE  = 0.02    # ERP > 2% → actions bon marché vs obligations
ERP_EXPENSIVE   = 0.01    # ERP < 1% → actions chères


# ══════════════════════════════════════════════════════════════
# ── 1b. YIELD CURVE — classifieur 4 régimes
#
#  Spread (10Y − 3M) en points de pourcentage
#  ─────────────────────────────────────────────────────────────
#  ≥  1.00  → "steep"             : pente saine, signal d'expansion
#     0.00  → "flat"              : aplatissement — aucun signal clair
#    -0.50  → "partial_inversion" : prudence — faux positifs fréquents
#   < -0.50 → "full_inversion"    : récession probable (≠ certaine)
#
#  Références historiques :
#    • 1998, 2019 : inversion partielle sans récession (faux positif)
#    • Lead time moyen avant récession : 6–24 mois (variable)
#    • ~70 % des inversions complètes précèdent une récession (1970–2023)
# ══════════════════════════════════════════════════════════════

def _yc_regime(spread: float | None) -> str | None:
    """
    Classifie le spread 10Y−3M en 4 régimes.
    Modifie les seuils ci-dessous pour changer la sensibilité.
    """
    if spread is None:
        return None
    if spread >= 1.00:
        return "steep"
    if spread >= 0.00:
        return "flat"
    if spread >= -0.50:
        return "partial_inversion"
    return "full_inversion"


# ══════════════════════════════════════════════════════════════
# ── 2. QUERY
# ══════════════════════════════════════════════════════════════

def _fetch_macro(con: sqlite3.Connection) -> dict:
    """
    Lit la dernière ligne de macro_bandeau.
    Modifie les colonnes SELECT pour ajouter des indicateurs macro.
    """
    row = con.execute(
        """
        SELECT ts, vix, us10y, us3m, dxy, erp, yield_curve, sp500_pe, sp500_earnings_yield
        FROM macro_bandeau
        ORDER BY ts DESC
        LIMIT 1
        """,
    ).fetchone()

    if not row:
        return {}

    cols = ["ts", "vix", "us10y", "us3m", "dxy", "erp", "yield_curve", "sp500_pe", "sp500_earnings_yield"]
    return dict(zip(cols, row))


def _fetch_index_snapshot(con: sqlite3.Connection, ticker: str) -> dict:
    """
    Lit close + chg_pct + sparkline pour un indice depuis snapshot.
    Utilisé pour afficher S&P500 et DXY en contexte macro.
    """
    row = con.execute(
        """
        SELECT close, chg_pct, ret_1m, ret_1y, sparkline_json
        FROM snapshot
        WHERE ticker = ?
        """,
        (ticker,),
    ).fetchone()

    if not row:
        return {}
    return {
        "close"         : row[0],
        "chg_pct"       : row[1],
        "ret_1m"        : row[2],
        "ret_1y"        : row[3],
        "sparkline_json": row[4],
    }


# ══════════════════════════════════════════════════════════════
# ── 3. FORMAT
# ══════════════════════════════════════════════════════════════

def render(con: sqlite3.Connection, lang: str = "EN", currency: str = "USD") -> dict:
    """
    Retourne :
    {
      "meta": META,
      "data": {
        "ts"           : str,
        "vix"          : { valeur, regime: "complacency"|"normal"|"fear"|"panic" },
        "yield_curve"  : { valeur, inverted: bool, us10y, us3m },
        "erp"          : { valeur, regime: "attractive"|"neutral"|"expensive", sp500_pe },
        "dxy"          : { valeur, chg_pct, ret_1m, sparkline },
        "sp500"        : { close, chg_pct, ret_1y, sparkline },
      }
    }
    """
    macro  = _fetch_macro(con)
    sp500  = _fetch_index_snapshot(con, "^GSPC")
    dxy    = _fetch_index_snapshot(con, "DX-Y.NYB")

    # ── Régimes ─────────────────────────────────────────────
    vix_val = macro.get("vix")
    if vix_val is not None:
        if vix_val < VIX_COMPLACENCY:
            vix_regime = "complacency"
        elif vix_val < 20:
            vix_regime = "normal"
        elif vix_val < VIX_PANIC:
            vix_regime = "fear"
        else:
            vix_regime = "panic"
    else:
        vix_regime = None

    erp_val = macro.get("erp")
    if erp_val is not None:
        if erp_val >= ERP_ATTRACTIVE:
            erp_regime = "attractive"
        elif erp_val >= ERP_EXPENSIVE:
            erp_regime = "neutral"
        else:
            erp_regime = "expensive"
    else:
        erp_regime = None

    yc_val   = macro.get("yield_curve")
    inverted = (yc_val < 0) if yc_val is not None else None
    yc_regime = _yc_regime(yc_val)

    return {
        "meta": {**META, "titre": META["titre"].get(lang, META["titre"]["EN"])},
        "data": {
            "ts"         : macro.get("ts"),
            "vix"        : {
                "valeur" : vix_val,
                "regime" : vix_regime,
            },
            "yield_curve": {
                "valeur"  : yc_val,
                "inverted": inverted,
                "regime"  : yc_regime,   # "steep"|"flat"|"partial_inversion"|"full_inversion"
                "us10y"   : macro.get("us10y"),
                "us3m"    : macro.get("us3m"),
            },
            "erp"        : {
                "valeur"  : erp_val,
                "regime"  : erp_regime,
                "sp500_pe": macro.get("sp500_pe"),
            },
            "dxy"        : {
                "valeur"  : dxy.get("close"),
                "chg_pct" : dxy.get("chg_pct"),
                "ret_1m"  : dxy.get("ret_1m"),
                "sparkline": dxy.get("sparkline_json"),
            },
            "sp500"      : {
                "close"   : sp500.get("close"),
                "chg_pct" : sp500.get("chg_pct"),
                "ret_1y"  : sp500.get("ret_1y"),
                "sparkline": sp500.get("sparkline_json"),
            },
        },
    }
