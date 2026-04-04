"""
calc.py — Calcule tous les indicateurs techniques depuis prices.
Écrit dans : metrics (historique), snapshot (dernière valeur par ticker), rperf.
Toutes les formules sont en pandas pur (pas de pandas-ta).

Lancement :
    python scripts/calc.py
"""

import json
import sqlite3
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    DB_PATH,
    SECTOR_TICKERS,
    BENCHMARK_MONDE,
    MOMENTUM_WINDOWS,
    SCORE_WEIGHTS,
    DMA_SHORT,
    DMA_LONG,
    MFI_PERIOD,
    OBV_DIR_WINDOW,
    RVOL_WINDOW,
    SPARKLINE_DAYS,
    SENTIMENT_THRESHOLDS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [calc] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
#  LOAD PRICES FROM DB
# ============================================================

def load_prices(con: sqlite3.Connection, ticker: str) -> pd.DataFrame:
    """
    Lit l'historique OHLCV pour un ticker depuis la table prices.
    Retourne un DataFrame indexé par date (plus ancien → plus récent).
    """
    df = pd.read_sql_query(
        """
        SELECT date, open, high, low, close, volume
        FROM prices
        WHERE ticker = ?
        ORDER BY date ASC
        """,
        con,
        params=(ticker,),
        parse_dates=["date"],
    )
    df = df.set_index("date")
    # Forcer les types numériques
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_all_tickers(con: sqlite3.Connection) -> list[str]:
    rows = con.execute(
        "SELECT ticker FROM ticker_info WHERE actif = 1"
    ).fetchall()
    return [r[0] for r in rows]


# ============================================================
#  INDICATEURS TECHNIQUES
# ============================================================

def calc_dma(df: pd.DataFrame) -> tuple:
    """Retourne (dma_50, dma_200, above_dma200) pour la dernière date."""
    close = df["close"]
    dma50  = close.rolling(DMA_SHORT).mean().iloc[-1]
    dma200 = close.rolling(DMA_LONG).mean().iloc[-1]
    above  = int(close.iloc[-1] > dma200) if not np.isnan(dma200) else None
    return _f(dma50), _f(dma200), above


def calc_momentum(df: pd.DataFrame) -> dict:
    """Retourne les returns pour chaque fenêtre (1M, 3M, 6M, 1Y, 2Y)."""
    close = df["close"]
    n     = len(close)
    result = {}
    for label, window in MOMENTUM_WINDOWS.items():
        if n > window:
            ret = (close.iloc[-1] / close.iloc[-(window + 1)] - 1)
            result[label] = _f(ret)
        else:
            result[label] = None
    return result


def calc_score(momentum: dict) -> float | None:
    """Score composite pondéré sur 1M/3M/6M/1Y."""
    total, weight_sum = 0.0, 0.0
    for label, w in SCORE_WEIGHTS.items():
        val = momentum.get(label)
        if val is not None:
            total      += val * w
            weight_sum += w
    return _f(total / weight_sum) if weight_sum > 0 else None


def calc_rvol(df: pd.DataFrame) -> tuple:
    """
    RVOL = volume J / moyenne volume 20j
    RVOL directionnel = signe(close - close[J-1]) × RVOL × 100
    """
    vol   = df["volume"].fillna(0)
    close = df["close"]
    if vol.iloc[-1] == 0 or len(vol) < RVOL_WINDOW + 1:
        return None, None

    avg_vol = vol.iloc[-(RVOL_WINDOW + 1):-1].mean()
    if avg_vol == 0:
        return None, None

    rvol = vol.iloc[-1] / avg_vol
    sign = np.sign(close.iloc[-1] - close.iloc[-2])
    rvol_dir = _f(sign * rvol * 100)
    return _f(rvol), rvol_dir


def calc_obv(df: pd.DataFrame) -> tuple:
    """
    OBV classique + direction sur OBV_DIR_WINDOW jours.
    direction : +1 hausse | -1 baisse | 0 flat
    """
    close = df["close"]
    vol   = df["volume"].fillna(0)

    delta    = close.diff()
    sign_vec = np.where(delta > 0, 1, np.where(delta < 0, -1, 0))
    obv_series = (sign_vec * vol).cumsum()

    obv_now = obv_series.iloc[-1]
    if len(obv_series) > OBV_DIR_WINDOW:
        obv_past = obv_series.iloc[-(OBV_DIR_WINDOW + 1)]
        diff     = obv_now - obv_past
        obv_dir  = 1 if diff > 0 else (-1 if diff < 0 else 0)
    else:
        obv_dir = 0

    return _f(obv_now), obv_dir


def calc_mfi(df: pd.DataFrame, period: int = MFI_PERIOD) -> float | None:
    """
    Money Flow Index (MFI) sur `period` jours.
    MFI = 100 - 100 / (1 + MF_ratio)
    """
    if len(df) < period + 1:
        return None

    high  = df["high"].fillna(df["close"])
    low   = df["low"].fillna(df["close"])
    close = df["close"]
    vol   = df["volume"].fillna(0)

    tp  = (high + low + close) / 3.0
    mf  = tp * vol

    pos = pd.Series(np.where(tp > tp.shift(1), mf, 0.0), index=df.index)
    neg = pd.Series(np.where(tp < tp.shift(1), mf, 0.0), index=df.index)

    pos_sum = pos.rolling(period).sum().iloc[-1]
    neg_sum = neg.rolling(period).sum().iloc[-1]

    if neg_sum == 0:
        return 100.0
    mfi_val = 100.0 - (100.0 / (1.0 + pos_sum / neg_sum))
    return _f(mfi_val)


def calc_sentiment(
    mfi: float | None,
    obv_dir: int | None,
    above_dma200: int | None,
) -> tuple[float | None, str | None]:
    """
    Sentiment Score composite : -1.0 à +1.0
    Composantes :
      - MFI normalisé : (MFI - 50) / 50  → [-1, +1]
      - OBV direction : +1 / 0 / -1
      - above_dma200  : +1 / 0 / -1
    Pondération : MFI 40%, OBV 30%, DMA200 30%
    """
    scores = []
    weights = []

    if mfi is not None:
        scores.append((mfi - 50.0) / 50.0)
        weights.append(0.40)

    if obv_dir is not None:
        scores.append(float(obv_dir))
        weights.append(0.30)

    if above_dma200 is not None:
        # 1 → +1, 0 → -1
        scores.append(1.0 if above_dma200 else -1.0)
        weights.append(0.30)

    if not scores:
        return None, None

    total  = sum(s * w for s, w in zip(scores, weights))
    w_sum  = sum(weights)
    score  = _f(total / w_sum)

    t = SENTIMENT_THRESHOLDS
    if score >= t["euphoric"]:
        label = "Euphoric"
    elif score >= t["accum"]:
        label = "Accumulation"
    elif score >= t["neutral"]:
        label = "Neutral"
    elif score >= t["caution"]:
        label = "Caution"
    elif score >= t["bearish"]:
        label = "Bearish"
    else:
        label = "Extreme Fear"

    return score, label


def calc_sparkline(df: pd.DataFrame, days: int = SPARKLINE_DAYS) -> str:
    """Retourne les N dernières closes sous forme de JSON array."""
    closes = df["close"].iloc[-days:].round(4).tolist()
    return json.dumps(closes)


# ============================================================
#  R-PERF (performance relative régionale vs MONDE)
# ============================================================

def calc_rperf_for_sector(
    con: sqlite3.Connection,
    secteur: str,
    benchmark_ticker: str,
) -> list[tuple]:
    """
    Pour un secteur, calcule R-Perf = ret_Nj(region) - ret_Nj(monde)
    pour chaque région disponible.
    Retourne une liste de tuples (secteur, region, date, rp_1m, rp_3m, rp_6m, rp_1y).
    """
    results = []
    ts_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Benchmark MONDE
    df_monde = load_prices(con, benchmark_ticker)
    if len(df_monde) < 22:
        return results
    mom_monde = calc_momentum(df_monde)

    for region, ticker in SECTOR_TICKERS[secteur].items():
        if region == "MONDE" or not ticker or ticker == benchmark_ticker:
            continue

        df = load_prices(con, ticker)
        if len(df) < 22:
            continue

        mom = calc_momentum(df)

        def diff(label):
            a = mom.get(label)
            b = mom_monde.get(label)
            return _f(a - b) if (a is not None and b is not None) else None

        results.append((
            secteur, region, ts_today,
            diff("1M"), diff("3M"), diff("6M"), diff("1Y"),
        ))

    return results


# ============================================================
#  WRITE TO DB
# ============================================================

def upsert_metrics(con: sqlite3.Connection, ticker: str, date: str, vals: dict):
    con.execute(
        """
        INSERT OR REPLACE INTO metrics (
            ticker, date,
            dma_50, dma_200, above_dma200,
            ret_1m, ret_3m, ret_6m, ret_1y, ret_2y,
            score,
            rvol, rvol_dir,
            obv, obv_dir, mfi,
            sentiment_score,
            rperf_1m, rperf_3m, rperf_6m, rperf_1y
        ) VALUES (
            :ticker, :date,
            :dma_50, :dma_200, :above_dma200,
            :ret_1m, :ret_3m, :ret_6m, :ret_1y, :ret_2y,
            :score,
            :rvol, :rvol_dir,
            :obv, :obv_dir, :mfi,
            :sentiment_score,
            :rperf_1m, :rperf_3m, :rperf_6m, :rperf_1y
        )
        """,
        {"ticker": ticker, "date": date, **vals},
    )


def upsert_snapshot(con: sqlite3.Connection, ticker: str, df: pd.DataFrame, vals: dict):
    close_now  = df["close"].iloc[-1]
    close_prev = df["close"].iloc[-2] if len(df) >= 2 else None
    chg_pct    = _f((close_now / close_prev - 1)) if close_prev else None

    con.execute(
        """
        INSERT OR REPLACE INTO snapshot (
            ticker, ts_update,
            close, close_prev, chg_pct,
            dma_50, dma_200, above_dma200,
            ret_1m, ret_3m, ret_6m, ret_1y, ret_2y,
            score,
            rvol, rvol_dir,
            obv_dir, mfi,
            sentiment_score, sentiment_label,
            rperf_1m, rperf_3m, rperf_6m, rperf_1y,
            sparkline_json
        ) VALUES (
            :ticker, :ts_update,
            :close, :close_prev, :chg_pct,
            :dma_50, :dma_200, :above_dma200,
            :ret_1m, :ret_3m, :ret_6m, :ret_1y, :ret_2y,
            :score,
            :rvol, :rvol_dir,
            :obv_dir, :mfi,
            :sentiment_score, :sentiment_label,
            :rperf_1m, :rperf_3m, :rperf_6m, :rperf_1y,
            :sparkline_json
        )
        """,
        {
            "ticker"         : ticker,
            "ts_update"      : datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "close"          : _f(close_now),
            "close_prev"     : _f(close_prev),
            "chg_pct"        : chg_pct,
            "sparkline_json" : calc_sparkline(df),
            **vals,
        },
    )


def upsert_rperf(con: sqlite3.Connection, rows: list[tuple]):
    con.executemany(
        """
        INSERT OR REPLACE INTO rperf
            (secteur, region, date, rperf_1m, rperf_3m, rperf_6m, rperf_1y)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


# ============================================================
#  HELPERS
# ============================================================

def _f(x) -> float | None:
    """Convertit en float Python, None si NaN/Inf."""
    if x is None:
        return None
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


# ============================================================
#  MAIN
# ============================================================

def main():
    con     = sqlite3.connect(DB_PATH)
    tickers = load_all_tickers(con)
    ts_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    log.info("Calcul pour %d tickers (date=%s)", len(tickers), ts_date)
    ok = 0
    skipped = 0

    for ticker in tickers:
        df = load_prices(con, ticker)
        if len(df) < 22:   # minimum 1M de données
            log.debug("%s — données insuffisantes (%d jours)", ticker, len(df))
            skipped += 1
            continue

        # ── Calculs ──────────────────────────────────────
        dma50, dma200, above_dma200 = calc_dma(df)
        momentum                    = calc_momentum(df)
        score                       = calc_score(momentum)
        rvol, rvol_dir              = calc_rvol(df)
        obv, obv_dir                = calc_obv(df)
        mfi                         = calc_mfi(df)
        sentiment, sent_label       = calc_sentiment(mfi, obv_dir, above_dma200)

        vals = {
            "dma_50"         : dma50,
            "dma_200"        : dma200,
            "above_dma200"   : above_dma200,
            "ret_1m"         : momentum.get("1M"),
            "ret_3m"         : momentum.get("3M"),
            "ret_6m"         : momentum.get("6M"),
            "ret_1y"         : momentum.get("1Y"),
            "ret_2y"         : momentum.get("2Y"),
            "score"          : score,
            "rvol"           : rvol,
            "rvol_dir"       : rvol_dir,
            "obv"            : obv,
            "obv_dir"        : obv_dir,
            "mfi"            : mfi,
            "sentiment_score": sentiment,
            "sentiment_label": sent_label,
            # R-Perf rempli plus bas pour les ETFs sectoriels
            "rperf_1m"       : None,
            "rperf_3m"       : None,
            "rperf_6m"       : None,
            "rperf_1y"       : None,
        }

        upsert_metrics(con, ticker, ts_date, vals)
        upsert_snapshot(con, ticker, df, vals)
        ok += 1

    # ── R-Perf par secteur ────────────────────────────────
    rperf_rows = []
    for secteur, benchmark in BENCHMARK_MONDE.items():
        rows = calc_rperf_for_sector(con, secteur, benchmark)
        rperf_rows.extend(rows)

    if rperf_rows:
        upsert_rperf(con, rperf_rows)

    con.commit()
    con.close()

    log.info(
        "Terminé — %d tickers calculés, %d ignorés (données insuffisantes), %d rperf rows.",
        ok, skipped, len(rperf_rows),
    )


if __name__ == "__main__":
    main()
