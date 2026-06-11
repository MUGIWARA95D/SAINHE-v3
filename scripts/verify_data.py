"""
verify_data.py — Audit de la DB prices pour détecter les rows partial intraday.

Critères de détection (red flags) :
  VOL_LOW        : volume < 30% de la médiane des 20 rows précédentes
  RANGE_NARROW   : range high-low / close < 0.3% (journée incomplète)
  TODAY_ROW      : une row avec date == aujourd'hui UTC existe en DB
  SNAPSHOT_STALE : la date de la row source du snapshot ≠ date EOD la plus récente
  SNAPSHOT_MIX   : tickers dans snapshot ont des dates source différentes

Exit code :
  0 = clean
  1 = anomalies détectées

Lancement :
    python scripts/verify_data.py
"""

import sqlite3
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import db


# ============================================================
#  AUDIT PAR TICKER
# ============================================================

def audit_ticker(con: sqlite3.Connection, ticker: str) -> list[tuple]:
    """Retourne liste de (level, message) pour un ticker."""
    rows = con.execute(
        """
        SELECT date, open, high, low, close, volume
        FROM prices WHERE ticker = ?
        ORDER BY date ASC
        """,
        (ticker,),
    ).fetchall()

    if len(rows) < 22:
        return [("INFO", f"only {len(rows)} rows")]

    flags  = []
    today  = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── 1. VOL_LOW — dernières 10 rows comparées à la médiane des 20 précédentes
    for i in range(max(0, len(rows) - 10), len(rows)):
        date, o, h, l, c, v = rows[i]
        if not v or v <= 0:
            continue
        window = [r[5] for r in rows[max(0, i - 20):i] if r[5] and r[5] > 0]
        if len(window) < 5:
            continue
        median_vol = statistics.median(window)
        if v < median_vol * 0.3:
            pct = v / median_vol * 100
            flags.append((
                "VOL_LOW",
                f"{date} vol={int(v):,} vs median={int(median_vol):,} ({pct:.0f}%)",
            ))

    # ── 2. RANGE_NARROW — range relatif trop étroit
    for r in rows[-10:]:
        date, o, h, l, c, v = r
        if h is None or l is None or c is None or c <= 0:
            continue
        range_pct = (h - l) / c
        if range_pct < 0.003:
            flags.append((
                "RANGE_NARROW",
                f"{date} range={range_pct * 100:.3f}% (h={h:.2f} l={l:.2f})",
            ))

    # ── 3. TODAY_ROW — row au jour même AVEC volume anormalement bas.
    # Pour les tickers EU/Asia, une row datée aujourd'hui UTC peut être un
    # EOD finalisé légitime (marché fermé avant le fetch matin). On ne flag
    # que si volume < 30% médiane (corroboration partial intraday).
    for r in rows[-3:]:
        if r[0] != today:
            continue
        vol_today = r[5]
        prior_vols = [x[5] for x in rows[-21:-1] if x[5] and x[5] > 0]
        if vol_today and vol_today > 0 and len(prior_vols) >= 5:
            median_vol = statistics.median(prior_vols)
            if vol_today < median_vol * 0.3:
                flags.append((
                    "TODAY_ROW",
                    f"{r[0]} close={r[4]:.2f} vol={int(vol_today):,} vs median={int(median_vol):,} (partial)",
                ))

    return flags


# ============================================================
#  AUDIT SNAPSHOT (cohérence dates)
# ============================================================

def audit_snapshot(con: sqlite3.Connection) -> list[tuple]:
    """
    Pour chaque ticker dans snapshot, trouve la date de la row prices qui
    correspond à la valeur close. Détecte les incohérences de dates.
    """
    flags = []

    # Dernière date EOD par ticker
    q = """
    SELECT s.ticker, s.close, s.ts_update,
           (SELECT MAX(date) FROM prices WHERE ticker = s.ticker) AS last_price_date
    FROM snapshot s
    """
    rows = con.execute(q).fetchall()
    if not rows:
        return [("INFO", "snapshot vide")]

    # Compte les dates "as of" pour voir si tous les tickers partagent la même date
    dates_counter = Counter(r[3] for r in rows if r[3])

    if len(dates_counter) > 1:
        top_date, top_count = dates_counter.most_common(1)[0]
        other_dates = [f"{d}:{n}" for d, n in dates_counter.items() if d != top_date]
        flags.append((
            "SNAPSHOT_MIX",
            f"majoritaire={top_date} ({top_count}), autres=[{', '.join(other_dates)}]",
        ))

    # Vérifie que snapshot.close correspond bien à la close de la dernière row prices
    mismatched = []
    for ticker, snap_close, ts_upd, last_date in rows:
        if not last_date or snap_close is None:
            continue
        row = con.execute(
            "SELECT close FROM prices WHERE ticker=? AND date=?",
            (ticker, last_date),
        ).fetchone()
        if not row:
            continue
        price_close = row[0]
        if price_close is None:
            continue
        diff_pct = abs(snap_close - price_close) / price_close * 100 if price_close > 0 else 0
        if diff_pct > 0.01:
            mismatched.append((ticker, snap_close, price_close, last_date, diff_pct))

    for t, sc, pc, d, pct in mismatched[:20]:
        flags.append((
            "SNAPSHOT_STALE",
            f"{t} snap={sc:.4f} vs prices[{d}]={pc:.4f} ({pct:.2f}%)",
        ))

    return flags


# ============================================================
#  MAIN
# ============================================================

def main():
    con = db.connect()

    tickers = [
        r[0] for r in con.execute(
            "SELECT DISTINCT ticker FROM prices ORDER BY ticker"
        ).fetchall()
    ]

    print(f"\n=== VERIFY_DATA — {len(tickers)} tickers ===\n")

    total_flags = 0
    flag_counter = Counter()

    for ticker in tickers:
        flags = audit_ticker(con, ticker)
        bad = [f for f in flags if f[0] != "INFO"]
        if bad:
            print(f"[{ticker}]")
            for level, msg in bad:
                print(f"  {level:14} {msg}")
                flag_counter[level] += 1
            total_flags += len(bad)

    # Audit snapshot
    print("\n--- SNAPSHOT ---")
    snap_flags = audit_snapshot(con)
    if snap_flags:
        for level, msg in snap_flags:
            print(f"  {level:14} {msg}")
            flag_counter[level] += 1
            if level != "INFO":
                total_flags += 1
    else:
        print("  (snapshot OK)")

    # Répartition par date EOD
    print("\n--- DATES EOD PAR TICKER ---")
    date_counts = con.execute("""
        SELECT MAX(date) AS last_date, COUNT(*) AS n
        FROM (SELECT ticker, date FROM prices)
        GROUP BY ticker
    """).fetchall()
    c = Counter()
    for d, n in date_counts:
        c[d] += 1
    for d, n in sorted(c.items(), reverse=True)[:5]:
        print(f"  {d}: {n} tickers")

    print(f"\n=== RÉSUMÉ ===")
    for level, n in flag_counter.most_common():
        print(f"  {level:14} {n}")
    print(f"  TOTAL: {total_flags} flags\n")

    con.close()

    if total_flags > 0:
        print("!  Anomalies detectees")
        sys.exit(1)
    print("OK Clean")
    sys.exit(0)


if __name__ == "__main__":
    main()
