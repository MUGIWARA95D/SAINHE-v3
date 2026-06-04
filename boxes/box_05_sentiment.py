"""
box_05_sentiment.py — Sector Map: 16 sectors × 4 regions rotation matrix.

Replaces the previous single-region Sentiment Analysis box with a richer,
decision-oriented heatmap. Per cell:
  - Color = relative alpha vs MONDE benchmark at the selected timeframe
  - 3 micro signals: DMA200, MFI, OBV
  - Click-to-zoom reveals the full detail view (12 points)

Two overlays on top of the matrix:
  - Market Breadth: % of sector ETFs above DMA200 (Healthy/Narrowing/Risk-off)
  - Macro Regime: classified from VIX + yield curve + HY OAS (Risk-on/Neutral/Risk-off)

All data is read from existing tables (snapshot, macro_bandeau, macro_liquidity).
No new fetcher required.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import SECTOR_TICKERS


# ══════════════════════════════════════════════════════════════
# META
# ══════════════════════════════════════════════════════════════
META = {
    "id"         : "box_05_sentiment",   # ID kept for BOX_REGISTRY stability
    "titre"      : {
        "EN": "Rotation",
        "FR": "Rotation",
        "DE": "Rotation",
        "ES": "Rotación",
        "ZH": "板块轮动",
        "RU": "Ротация",
        "JA": "ローテーション",
    },
    "description": "Volume-driven sector rotation — DMA · MFI · OBV signals across 16 sectors × 4 regions.",
    "icone"      : "🗺️",
    "largeur"    : "full",
}

REGIONS = ["MONDE", "USA", "EU", "ASIE"]
SECTORS = list(SECTOR_TICKERS.keys())  # 16 sectors, fixed order from config

# Compact labels for the 1×1 recto (4–7 chars max)
SECTOR_ABBREV = {
    "Tech & Semis"        : "Tech",
    "Robotics & MedTech"  : "Robot",
    "Healthcare & Pharma" : "Health",
    "Finance & Transac."  : "Finance",
    "Strategic Materials" : "Mater",
    "Energy"              : "Energy",
    "Defense & Aerospace" : "Defens",
    "EV & Clean Energy"   : "Clean",
    "Space"               : "Space",
    "Luxury"              : "Luxury",
    "Agriculture"         : "Agri",
    "Infra & Water"       : "Infra",
    "Consumer Staples"    : "Staple",
    "Digital Assets"      : "Crypto",
    "Industrials"         : "Indus",
    "Chemicals"           : "Chem",
}


# ══════════════════════════════════════════════════════════════
# 1. Sector grid — snapshot JOIN ticker_info for every (sector, region)
# ══════════════════════════════════════════════════════════════

def _fetch_rperf_latest(con: sqlite3.Connection) -> dict:
    """
    Returns {(secteur, region): {rperf_1m, rperf_3m, rperf_6m, rperf_1y}}
    for the LATEST row per (secteur, region) in the rperf table.

    rperf is computed by calc.calc_rperf_for_sector and written to its own
    table by upsert_rperf — the snapshot table's rperf_* columns are NOT
    populated by calc.py's main loop, so reading rperf here is mandatory.
    Note: MONDE is the benchmark itself, so no row exists for it (its
    'alpha' is 0 by definition — kept as null and shown as neutral cream).
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
        """
    ).fetchall()
    return {(r[0], r[1]): {"1m": r[2], "3m": r[3], "6m": r[4], "1y": r[5]} for r in rows}


def _fetch_indicator_history(con: sqlite3.Connection, tickers: list) -> dict:
    """
    Returns {ticker: {obv_cur, mfi_50d, obv_90d}} — raw MFI and OBV values
    from the metrics table at three horizons so the verso can show the user
    the actual numbers to compare against today:
      obv_cur  — latest raw OBV (snapshot only stores the obv_dir flag)
      mfi_50d  — MFI value closest to 50 calendar days ago
      obv_90d  — raw OBV value closest to 90 calendar days ago
    """
    if not tickers:
        return {}
    ph = ",".join("?" * len(tickers))

    cur_rows = con.execute(f"""
        SELECT ticker, obv FROM (
            SELECT ticker, obv,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
            FROM metrics WHERE ticker IN ({ph})
        ) WHERE rn = 1
    """, tickers).fetchall()

    mfi_rows = con.execute(f"""
        SELECT ticker, mfi FROM (
            SELECT ticker, mfi,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
            FROM metrics
            WHERE ticker IN ({ph}) AND date <= date('now', '-50 days')
        ) WHERE rn = 1
    """, tickers).fetchall()

    obv_rows = con.execute(f"""
        SELECT ticker, obv FROM (
            SELECT ticker, obv,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
            FROM metrics
            WHERE ticker IN ({ph}) AND date <= date('now', '-90 days')
        ) WHERE rn = 1
    """, tickers).fetchall()

    result = {t: {"obv_cur": None, "mfi_50d": None, "obv_90d": None} for t in tickers}
    for ticker, obv in cur_rows:
        if ticker in result:
            result[ticker]["obv_cur"] = obv
    for ticker, mfi in mfi_rows:
        if ticker in result:
            result[ticker]["mfi_50d"] = mfi
    for ticker, obv in obv_rows:
        if ticker in result:
            result[ticker]["obv_90d"] = obv
    return result


def _fetch_grid(con: sqlite3.Connection) -> dict:
    """
    Returns {region: {sector: cell_dict}}. Cells with no ETF coverage (e.g.
    Industrials/EU, Chemicals/MONDE) carry coverage=False; the template renders
    them as muted, non-clickable cells.
    """
    rperf_map = _fetch_rperf_latest(con)
    # Pro standards only: alphas (rperf), absolute returns, and the 3 independent
    # signals (DMA200 / MFI / OBV). No composite score, no labels.
    rows = con.execute("""
        SELECT ti.ticker, ti.secteur, ti.region, ti.nom,
               s.mfi, s.obv_dir, s.above_dma200,
               s.dma_50, s.dma_200, s.close, s.chg_pct,
               s.ret_1m, s.ret_3m, s.ret_6m, s.ret_1y,
               s.rperf_1m, s.rperf_3m, s.rperf_6m, s.rperf_1y,
               s.rvol, s.rvol_dir,
               s.ts_update
        FROM snapshot s
        JOIN ticker_info ti ON ti.ticker = s.ticker
        WHERE ti.type = 'etf_sector' AND ti.actif = 1
    """).fetchall()

    cols = ["ticker", "secteur", "region", "nom",
            "mfi", "obv_dir", "above_dma200",
            "dma_50", "dma_200", "close", "chg_pct",
            "ret_1m", "ret_3m", "ret_6m", "ret_1y",
            "rperf_1m", "rperf_3m", "rperf_6m", "rperf_1y",
            "rvol", "rvol_dir",
            "ts_update"]
    snap_by_ticker = {r[0]: dict(zip(cols, r)) for r in rows}

    # Raw historical values for MFI/OBV comparison displayed in the 3×3 verso
    hist = _fetch_indicator_history(con, list(snap_by_ticker.keys()))

    grid = {r: {} for r in REGIONS}
    for sector in SECTORS:
        for region in REGIONS:
            ticker = SECTOR_TICKERS[sector].get(region)
            if not ticker:
                grid[region][sector] = {"coverage": False, "ticker": None}
                continue
            snap = snap_by_ticker.get(ticker)
            if not snap:
                grid[region][sector] = {"coverage": False, "ticker": ticker}
                continue

            # DMA200 signal (long-term trend)
            if snap.get("above_dma200") == 1:
                dma_sig = "above"
            elif snap.get("above_dma200") == 0:
                dma_sig = "below"
            else:
                dma_sig = "na"

            # MFI signal (momentum extremes)
            mfi = snap.get("mfi")
            if mfi is None:
                mfi_sig = "na"
            elif mfi >= 70:
                mfi_sig = "overbought"
            elif mfi <= 30:
                mfi_sig = "oversold"
            else:
                mfi_sig = "neutral"

            # OBV signal (smart money flow)
            obv_d = snap.get("obv_dir")
            if obv_d == 1:
                obv_sig = "accumulation"
            elif obv_d == -1:
                obv_sig = "distribution"
            elif obv_d == 0:
                obv_sig = "neutral"
            else:
                obv_sig = "na"

            # Alpha vs MONDE comes from the dedicated rperf table (snapshot's
            # rperf_* columns are not populated by calc.main). For MONDE itself
            # the benchmark is itself, so no rperf row exists — keep nulls.
            rp = rperf_map.get((sector, region), {})
            grid[region][sector] = {
                "coverage": True,
                "ticker"  : ticker,
                "nom"     : snap.get("nom") or ticker,
                # Relative alpha vs MONDE benchmark at 4 timeframes (decimals)
                "alpha_1m": rp.get("1m"),
                "alpha_3m": rp.get("3m"),
                "alpha_6m": rp.get("6m"),
                "alpha_1y": rp.get("1y"),
                # Absolute returns for the verso table
                "ret_1m"  : snap.get("ret_1m"),
                "ret_3m"  : snap.get("ret_3m"),
                "ret_6m"  : snap.get("ret_6m"),
                "ret_1y"  : snap.get("ret_1y"),
                # Three independent signals (documented standards: Granville '63,
                # Quong-Soudack '89, classical 200-day moving average)
                "dma_signal" : dma_sig,
                "mfi_value"  : mfi,
                "mfi_signal" : mfi_sig,
                "obv_signal" : obv_sig,
                # Price context for the verso
                "close"  : snap.get("close"),
                "chg_pct": snap.get("chg_pct"),
                "dma_50" : snap.get("dma_50"),
                "dma_200": snap.get("dma_200"),
                # RVOL — relative volume vs 20-day average (standard liquidity gauge)
                "rvol"     : snap.get("rvol"),
                "rvol_dir" : snap.get("rvol_dir"),
                # Raw historical values for the verso comparison rows
                "mfi_50d"  : hist.get(ticker, {}).get("mfi_50d"),
                "obv_cur"  : hist.get(ticker, {}).get("obv_cur"),
                "obv_90d"  : hist.get(ticker, {}).get("obv_90d"),
                "ts_update": snap.get("ts_update"),
            }
    return grid


# ══════════════════════════════════════════════════════════════
# 2. Market breadth — % of sector ETFs above DMA200
# ══════════════════════════════════════════════════════════════

def _fetch_breadth(con: sqlite3.Connection) -> dict:
    """
    Breadth = the share of all active sector ETFs (across regions) trading
    above their 200-day moving average. Classic participation indicator —
    when it falls below 50% during a rally, it typically warns of a top.
    """
    row = con.execute("""
        SELECT
          SUM(CASE WHEN s.above_dma200 = 1 THEN 1 ELSE 0 END) AS count_above,
          SUM(CASE WHEN s.above_dma200 IS NOT NULL THEN 1 ELSE 0 END) AS count_total
        FROM snapshot s
        JOIN ticker_info ti ON ti.ticker = s.ticker
        WHERE ti.type = 'etf_sector' AND ti.actif = 1
    """).fetchone()

    count_above = int(row[0]) if row and row[0] is not None else 0
    count_total = int(row[1]) if row and row[1] is not None else 0
    pct = (count_above / count_total * 100) if count_total else None

    if pct is None:
        label = "n/a"
    elif pct >= 60:
        label = "Healthy"
    elif pct >= 40:
        label = "Narrowing"
    else:
        label = "Risk-off"

    return {
        "count_above": count_above,
        "count_total": count_total,
        "pct"        : round(pct, 1) if pct is not None else None,
        "label"      : label,
    }


# ══════════════════════════════════════════════════════════════
# 3. Macro regime — VIX + yield curve + HY OAS classification
# ══════════════════════════════════════════════════════════════

def _fetch_regime(con: sqlite3.Connection) -> dict:
    """
    Three-bucket classification:
      RISK-ON  : VIX<20 AND curve>0 AND HY OAS<400 bps
      RISK-OFF : VIX>30 OR HY OAS>600 bps
      NEUTRAL  : everything else
    """
    bandeau = con.execute("""
        SELECT vix, yield_curve
        FROM macro_bandeau
        ORDER BY ts DESC
        LIMIT 1
    """).fetchone()
    liq = con.execute("""
        SELECT hy_oas_us
        FROM macro_liquidity
        ORDER BY date DESC
        LIMIT 1
    """).fetchone()

    vix   = bandeau[0] if bandeau else None
    curve = bandeau[1] if bandeau else None
    hy    = liq[0]     if liq     else None

    label = "NEUTRAL"
    if vix is not None and curve is not None and hy is not None:
        if vix < 20 and curve > 0 and hy < 400:
            label = "RISK-ON"
        elif vix > 30 or hy > 600:
            label = "RISK-OFF"
        else:
            label = "NEUTRAL"

    return {
        "label" : label,
        "vix"   : round(vix, 2)   if vix   is not None else None,
        "curve" : round(curve, 2) if curve is not None else None,
        "hy_oas": round(hy, 0)    if hy    is not None else None,
    }


# ══════════════════════════════════════════════════════════════
# render
# ══════════════════════════════════════════════════════════════

def render(con: sqlite3.Connection, lang: str = "EN", currency: str = "USD") -> dict:
    grid    = _fetch_grid(con)
    breadth = _fetch_breadth(con)
    regime  = _fetch_regime(con)

    return {
        "meta": {**META, "titre": META["titre"].get(lang, META["titre"]["EN"])},
        "data": {
            "regions": REGIONS,
            "sectors": SECTORS,
            "abbrevs": SECTOR_ABBREV,
            "grid"   : grid,
            "breadth": breadth,
            "regime" : regime,
        },
    }
