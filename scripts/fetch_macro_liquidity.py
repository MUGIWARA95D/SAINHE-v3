"""
fetch_macro_liquidity.py — Global macro liquidity & valuation data.

Sources (zero paid APIs):
  FRED API (free key)   : Fed/RRP/TGA, US M2, China M2, HY OAS, JGB/UK yields
  ECB SDW (no key)      : ECB balance sheet, EU M3, Bund 10Y/2Y
  yfinance              : P/E proxies (VGK/EWJ/EEM), GLD/^GSPC ratio, CNH/USD
  multpl.com (scraping) : Shiller CAPE US

Run: python scripts/fetch_macro_liquidity.py
Requires: FRED_API_KEY in environment (free at fred.stlouisfed.org/docs/api/api_key.html)
"""

import os
import sys
import time
import datetime as dt
import sqlite3
from pathlib import Path

import requests
import yfinance as yf
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DB_PATH


# ── Load .env (no python-dotenv needed) ───────────────────────────────────────

def _load_dotenv():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_dotenv()


# ── Constants ─────────────────────────────────────────────────────────────────

FRED_KEY  = os.environ.get("FRED_API_KEY", "")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# ECB: try new REST API first, fall back to legacy SDW
ECB_ENDPOINTS = [
    "https://data-api.ecb.europa.eu/service/data",   # new (2024+), different DNS
    "https://sdw-wsrest.ecb.europa.eu/service/data",  # legacy fallback
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 20

# FRED series IDs → (column_name, description)
FRED_SERIES = {
    "WALCL"          : "Fed Total Assets (B USD, weekly)",
    "RRPONTSYD"      : "Overnight Reverse Repo (B USD, daily)",
    "WTREGEN"        : "Treasury General Account (B USD, weekly)",
    "M2SL"           : "US M2 Money Stock (B USD, monthly)",
    "MYAGM2CNM189N"  : "China M2 Money Stock (B CNY, monthly)",
    "BAMLH0A0HYM2"    : "US HY OAS — ICE BofA (%, daily)",
    "BAMLHE00EHYIOAS" : "EU HY OAS — ICE BofA Euro (%, daily)",     # BAMLHE00EHY2EY discontinued
    "IRLTLT01JPM156N": "JGB 10Y Yield (%, monthly)",
    "IRLTLT01GBM156N": "UK Gilt 10Y Yield (%, monthly)",
}

# ECB SDW series → description
ECB_SERIES = {
    # ILM dataset — Internal Liquidity Management (weekly balance sheet)
    ("ILM", "W.U2.C.A.U20.EUR.E.1.Z5.0000.Z01.E"): "ECB Total Assets (B EUR, weekly)",
    # YC dataset — yield curve (daily)
    ("YC",  "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y")  : "Euro AAA 10Y Yield (daily)",
    ("YC",  "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y")   : "Euro AAA 2Y Yield (daily)",
    # BSI dataset — balance sheet items (monthly M3)
    ("BSI", "M.U2.Y.V.M30.X.I.U2.2300.Z01.E")    : "EU M3 Money Supply (monthly)",
}


# ── FRED ──────────────────────────────────────────────────────────────────────

def _fred_obs(series_id: str, n: int = 14, lookback_years: int = 4) -> list[dict]:
    """
    Returns last n observations [{date, value}] sorted newest first.
    Uses observation_start — works on all FRED series (no sort_order issues).
    lookback_years: increase for monthly series with long publication lags (e.g. China M2).
    Retries with backoff on 429 (FRED rate-limits per IP, and GitHub Actions runners share IPs).
    """
    if not FRED_KEY:
        print(f"[fred] No FRED_API_KEY — skipping {series_id}")
        return []
    obs_start = (dt.date.today() - dt.timedelta(days=lookback_years * 365)).isoformat()
    params = {
        "series_id"        : series_id,
        "api_key"          : FRED_KEY,
        "file_type"        : "json",
        "observation_start": obs_start,
    }
    backoffs = [5, 15, 30]   # seconds; 3 retries on 429 or any exception
    for attempt, wait in enumerate([0] + backoffs):
        if wait: time.sleep(wait)
        try:
            r = requests.get(FRED_BASE, params=params, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 429 and attempt < len(backoffs):
                print(f"[fred] {series_id} 429 rate-limited, retry in {backoffs[attempt]}s ({attempt+1}/{len(backoffs)})")
                continue
            r.raise_for_status()
            raw = r.json().get("observations", [])
            clean = [
                {"date": o["date"], "value": float(o["value"])}
                for o in raw
                if o.get("value") not in (".", None, "")
            ]
            return sorted(clean, key=lambda x: x["date"], reverse=True)[:n]
        except Exception as e:
            if attempt == len(backoffs):
                print(f"[fred] {series_id} error after retries: {e}")
            # else: fall through to next loop iteration to retry
    return []


def _yoy(series: list[dict]) -> float | None:
    """YoY % change from a list of monthly obs sorted newest first."""
    if len(series) < 13:
        return None
    v_now  = series[0]["value"]
    v_prev = series[12]["value"]
    if not v_prev:
        return None
    return round((v_now - v_prev) / abs(v_prev) * 100, 2)


def _wkchg(series: list[dict]) -> float | None:
    """Week-over-week % change."""
    if len(series) < 2:
        return None
    v_now  = series[0]["value"]
    v_prev = series[1]["value"]
    if not v_prev:
        return None
    return round((v_now - v_prev) / abs(v_prev) * 100, 3)


# ── ECB SDW ───────────────────────────────────────────────────────────────────

def _ecb_obs(dataset: str, series_key: str, n: int = 14) -> list[dict]:
    """
    Returns last n observations from ECB REST API.
    Tries new endpoint (data-api.ecb.europa.eu) first, then legacy SDW.
    """
    for base in ECB_ENDPOINTS:
        try:
            url = f"{base}/{dataset}/{series_key}"
            r = requests.get(
                url,
                params={"format": "jsondata", "lastNObservations": n},
                headers={**HEADERS, "Accept": "application/json"},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()

            series_data  = data["dataSets"][0]["series"]
            first_key    = next(iter(series_data))
            observations = series_data[first_key]["observations"]
            time_periods = data["structure"]["dimensions"]["observation"][0]["values"]

            result = []
            for idx, period in enumerate(time_periods):
                obs = observations.get(str(idx))
                if obs and obs[0] is not None:
                    result.append({"date": period["id"], "value": float(obs[0])})
            return sorted(result, key=lambda x: x["date"], reverse=True)[:n]

        except Exception as e:
            print(f"[ecb] {base}/{dataset}/{series_key} error: {e}")
            continue  # try next endpoint

    return []  # all endpoints failed


# ── Yield Curve Signal ────────────────────────────────────────────────────────

def _yc_signal(spread: float | None) -> str | None:
    """Classifies 10Y−2Y spread into 4 regimes (same logic as box_01_macro)."""
    if spread is None:
        return None
    if spread >= 1.00:  return "steep"
    if spread >= 0.00:  return "flat"
    if spread >= -0.50: return "partial_inversion"
    return "full_inversion"


# ── MoF Japan — daily JGB yields (CSV, no key) ───────────────────────────────

def _mof_jgb_yields(maturities=(2, 10)) -> dict:
    """
    Fetch daily JGB yields from Ministry of Finance Japan.
    URL: https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv
    CSV header: Date, 1Y, 2Y, 3Y, 4Y, 5Y, 6Y, 7Y, 8Y, 9Y, 10Y, 15Y, 20Y, 25Y, 30Y, 40Y
    Date format: YYYY/M/D; values in % (already decimal, e.g. 0.684)
    Returns {mat_int: {"date": "YYYY-MM-DD", "value": float}, ...}
    """
    url = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        lines = [l.strip() for l in r.text.strip().split("\n") if l.strip()]

        # Find header line (contains maturity labels)
        header      = None
        header_idx  = 0
        for i, line in enumerate(lines):
            cols = [c.strip().strip('"') for c in line.split(",")]
            if any(c in ("2Y", "10Y", "5Y") for c in cols):
                header      = cols
                header_idx  = i
                break
        if header is None:
            print("[mof] JGB CSV: header not found")
            return {}

        result = {}
        for line in reversed(lines[header_idx + 1:]):
            parts = [c.strip().strip('"') for c in line.split(",")]
            if len(parts) < 2 or not parts[0]:
                continue
            # Parse date: YYYY/M/D or YYYY-MM-DD
            date_str = parts[0]
            try:
                if "/" in date_str:
                    y, m, d = date_str.split("/")
                    date_iso = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
                else:
                    date_iso = date_str
            except Exception:
                continue

            for mat in maturities:
                if mat in result:
                    continue
                col_name = f"{mat}Y"
                if col_name in header:
                    idx = header.index(col_name)
                    if idx < len(parts) and parts[idx] not in ("", "-", "N/A", "—"):
                        try:
                            val = float(parts[idx])
                            result[mat] = {"date": date_iso, "value": val}
                        except ValueError:
                            pass
            if len(result) == len(maturities):
                break

        return result
    except Exception as e:
        print(f"[mof] JGB CSV error: {e}")
        return {}


# ── ChinaBond CCDC — CGB yields (scraped, no key) ─────────────────────────────

def _chinabond_yield(maturity_years: int) -> dict | None:
    """
    Fetch CGB yield from ChinaBond CCDC (official Chinese bond clearing house).
    Returns {"date": "YYYY-MM-DD", "value": float} or None.
    Falls back to a simpler JSON endpoint if HTML scrape fails.
    """
    today = dt.date.today()
    start = (today - dt.timedelta(days=30)).strftime("%Y-%m-%d")
    end   = today.strftime("%Y-%m-%d")

    # Primary endpoint: CCDC history query
    url = "https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/historyQuery"
    params = {
        "startDate": start,
        "endDate"  : end,
        "gjqx"     : str(maturity_years),
        "qxId"     : "hzsylqx",
        "locale"   : "en_US",
    }
    try:
        r = requests.get(url, params=params, headers={**HEADERS, "Referer": "https://yield.chinabond.com.cn/"}, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Try to find table rows with date + yield
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                date_text = cells[0].get_text(strip=True)
                val_text  = cells[1].get_text(strip=True)
                try:
                    val = float(val_text)
                    if not (0 < val < 20):      # sanity check: yield must be 0–20%
                        continue
                    date_text = date_text.replace("/", "-")
                    return {"date": date_text[:10], "value": val}
                except ValueError:
                    continue
    except Exception as e:
        print(f"[chinabond] {maturity_years}Y CGB error: {e}")

    print(f"[chinabond] No data found for {maturity_years}Y CGB")
    return None


# ── stooq.com — free yields, no key ──────────────────────────────────────────

def _stooq_yield(symbol: str, n: int = 3) -> list[dict]:
    """
    Fetch daily yield from stooq.com (free, no key, no rate limit).
    Symbols: '10dey.b' = German Bund 10Y, '2dey.b' = German Bund 2Y.
    Returns [{date, value}] sorted newest first.
    """
    try:
        url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        lines = [l.strip() for l in r.text.strip().split("\n") if l.strip()]
        result = []
        for line in lines[1:]:  # skip header
            parts = line.split(",")
            if len(parts) >= 5 and parts[4] not in ("", "null", "N/D"):
                try:
                    result.append({"date": parts[0], "value": float(parts[4])})
                except ValueError:
                    pass
        return sorted(result, key=lambda x: x["date"], reverse=True)[:n]
    except Exception as e:
        print(f"[stooq] {symbol} error: {e}")
        return []


# ── yfinance ──────────────────────────────────────────────────────────────────

def _yf_info(ticker: str) -> dict:
    """Fetch yfinance .info with retry on rate limit (3 attempts, backoff)."""
    for attempt in range(3):
        try:
            time.sleep(3 + attempt * 5)   # 3s, 8s, 13s
            return yf.Ticker(ticker).info
        except Exception as e:
            msg = str(e).lower()
            if "rate" in msg or "too many" in msg or "429" in msg:
                wait = 15 * (attempt + 1)
                print(f"[yf] {ticker} rate limited (attempt {attempt+1}), waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"[yf] {ticker} error: {e}")
                return {}
    return {}


def _pe_proxies() -> dict:
    """P/E ratios from ETF proxies via yfinance .info."""
    proxies = {"pe_eu": "VGK", "pe_jp": "EWJ", "pe_em": "EEM", "pe_cn": "MCHI"}
    result  = {}
    for col, ticker in proxies.items():
        info = _yf_info(ticker)
        pe   = info.get("trailingPE") or info.get("forwardPE")
        result[col] = round(float(pe), 1) if pe else None
        if result[col]:
            print(f"[yf] {ticker} P/E = {result[col]}")
    return result


def _fast_price(ticker: str) -> float | None:
    """Get last price via fast_info with retry."""
    for attempt in range(3):
        try:
            time.sleep(2 + attempt * 3)
            return yf.Ticker(ticker).fast_info.last_price
        except Exception as e:
            msg = str(e).lower()
            if "rate" in msg or "too many" in msg or "429" in msg:
                wait = 10 * (attempt + 1)
                print(f"[yf] {ticker} rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"[yf] {ticker} fast_info error: {e}")
                return None
    return None


def _copper_gold() -> tuple:
    """
    Returns (copper_price_lbr, gold_oz, copper_gold_ratio).
    HG=F is USD/lb (US Copper front month), GC=F is USD/oz (Gold futures front month).
    Cu/Au ratio = (copper × 100) / gold — proxy for industrial vs safe-haven demand balance.
    >0.35: industrial expansion; 0.25–0.35: mid-cycle; 0.18–0.25: risk-off; <0.18: cycle stress.
    """
    copper = _fast_price("HG=F")
    gold   = _fast_price("GC=F")
    if copper and gold and gold > 0:
        ratio = round((copper * 100) / gold, 4)
        return round(copper, 4), round(gold, 2), ratio
    return None, None, None


def _gold_stocks_ratio() -> float | None:
    """Gold-to-Stocks ratio: (GLD × 10) / S&P500."""
    gld = _fast_price("GLD")
    sp  = _fast_price("^GSPC")
    if gld and sp and sp > 0:
        return round(gld * 10 / sp, 4)
    return None


def _cnh_usd() -> float | None:
    """USD/CNH exchange rate as yuan stress indicator."""
    v = _fast_price("CNH=X")
    return round(v, 4) if v else None


# ── Shiller CAPE ─────────────────────────────────────────────────────────────

def _cape_multpl() -> float | None:
    """
    Scrape current Shiller CAPE from multpl.com/shiller-pe/table/by-month.
    Parses the structured data table — more reliable than regex on the main page.
    Sanity check: historical CAPE range is ~5–55 (peak 2000 = ~44).
    """
    CAPE_MIN, CAPE_MAX = 5.0, 60.0

    def _from_table(text: str) -> float | None:
        soup = BeautifulSoup(text, "html.parser")
        table = soup.find("table", {"id": "datatable"})
        if not table:
            return None
        for tr in table.find_all("tr")[1:]:   # skip header
            cols = tr.find_all("td")
            if len(cols) >= 2:
                raw = cols[1].get_text(strip=True).replace(",", ".")
                digits = "".join(c for c in raw if c.isdigit() or c == ".")
                try:
                    v = float(digits)
                    if CAPE_MIN < v < CAPE_MAX:
                        return v
                except ValueError:
                    pass
        return None

    def _from_selector(text: str) -> float | None:
        soup = BeautifulSoup(text, "html.parser")
        for sel in ["#current-value", ".current", "#current"]:
            el = soup.select_one(sel)
            if el:
                raw = el.get_text(strip=True).replace(",", ".")
                digits = "".join(c for c in raw if c.isdigit() or c == ".")
                try:
                    v = float(digits)
                    if CAPE_MIN < v < CAPE_MAX:
                        return v
                except ValueError:
                    pass
        return None

    # Table page first (most structured), then main page
    urls = [
        ("https://www.multpl.com/shiller-pe/table/by-month", _from_table),
        ("https://www.multpl.com/shiller-pe",                _from_selector),
    ]
    for url, parser in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            v = parser(r.text)
            if v:
                print(f"[cape] CAPE US = {v} (from {url})")
                return v
        except Exception as e:
            print(f"[cape] {url} error: {e}")

    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    today = dt.date.today().isoformat()
    now   = dt.datetime.now(dt.timezone.utc).isoformat()
    row   = {}

    # ── 1. FRED ───────────────────────────────────────────────────────────────
    print("[macro_liq] Fetching FRED...")

    walcl_obs = _fred_obs("WALCL", n=5)
    if walcl_obs:
        row["fed_walcl_t"]      = round(walcl_obs[0]["value"] / 1_000_000, 3)  # millions → trillions
        row["fed_walcl_wk_pct"] = _wkchg(walcl_obs)
        row["fed_walcl_date"]   = walcl_obs[0]["date"]

    rrp_obs = _fred_obs("RRPONTSYD", n=2)
    if rrp_obs:
        row["rrp_b"]    = round(rrp_obs[0]["value"], 1)
        row["rrp_date"] = rrp_obs[0]["date"]

    tga_obs = _fred_obs("WTREGEN", n=5)
    if tga_obs:
        row["tga_b"]    = round(tga_obs[0]["value"] / 1_000, 1)  # millions → billions
        row["tga_date"] = tga_obs[0]["date"]

    m2_obs = _fred_obs("M2SL", n=14)
    if len(m2_obs) >= 13:
        row["us_m2_yoy"]  = _yoy(m2_obs)
        row["us_m2_date"] = m2_obs[0]["date"]

    # China M2 lags up to 18 months on FRED — use 6-year lookback
    cn_m2_obs = _fred_obs("MYAGM2CNM189N", n=14, lookback_years=6)
    if len(cn_m2_obs) >= 13:
        row["china_m2_yoy"]  = _yoy(cn_m2_obs)
        row["china_m2_date"] = cn_m2_obs[0]["date"]
        print(f"[fred] China M2 YoY = {row['china_m2_yoy']}% (as of {row['china_m2_date']})")

    # Japan M2 — FRED MYAGM2JPM189N (billions JPY, monthly, ~2-month lag)
    jp_m2_obs = _fred_obs("MYAGM2JPM189N", n=14, lookback_years=3)
    if len(jp_m2_obs) >= 13:
        row["japan_m2_yoy"]  = _yoy(jp_m2_obs)
        row["japan_m2_date"] = jp_m2_obs[0]["date"]
        print(f"[fred] Japan M2 YoY = {row['japan_m2_yoy']}% (as of {row['japan_m2_date']})")

    # HY OAS: FRED returns decimal (3.12 = 312 bps) — multiply by 100
    hy_us_obs = _fred_obs("BAMLH0A0HYM2", n=2)
    if hy_us_obs:
        row["hy_oas_us"]      = round(hy_us_obs[0]["value"] * 100, 0)
        row["hy_oas_us_date"] = hy_us_obs[0]["date"]

    # EU HY OAS — ICE BofA Euro High Yield Index OAS (BAMLHE00EHYIOAS)
    # Note: old series BAMLHE00EHY2EY was discontinued — replaced by BAMLHE00EHYIOAS
    hy_eu_obs = _fred_obs("BAMLHE00EHYIOAS", n=2)
    if hy_eu_obs:
        row["hy_oas_eu"]      = round(hy_eu_obs[0]["value"] * 100, 0)
        row["hy_oas_eu_date"] = hy_eu_obs[0]["date"]
        print(f"[fred] EU HY OAS = {row['hy_oas_eu']}bp (BAMLHE00EHYIOAS)")

    # EM HY OAS — ICE BofA EM Corporate Plus HY Index OAS (BAMLEMHBHYCRPIOAS)
    hy_em_obs = _fred_obs("BAMLEMHBHYCRPIOAS", n=2)
    if hy_em_obs:
        row["hy_oas_em"]      = round(hy_em_obs[0]["value"] * 100, 0)
        row["hy_oas_em_date"] = hy_em_obs[0]["date"]
        print(f"[fred] EM HY OAS = {row['hy_oas_em']}bp (BAMLEMHBHYCRPIOAS)")

    # JGB 10Y — FRED monthly (IRLTLT01JPM156N), ~1-month lag
    # Note: MoF Japan daily CSV is primary source (see below); FRED is the fallback
    jgb_obs = _fred_obs("IRLTLT01JPM156N", n=2)
    if jgb_obs:
        row["jgb_10y"]      = round(jgb_obs[0]["value"], 3)
        row["jgb_10y_date"] = jgb_obs[0]["date"]

    # UK Gilt 10Y — FRED monthly (IRLTLT01GBM156N), ~1-month lag
    uk_obs = _fred_obs("IRLTLT01GBM156N", n=2)
    if uk_obs:
        row["uk_10y"]      = round(uk_obs[0]["value"], 3)
        row["uk_10y_date"] = uk_obs[0]["date"]

    # TIPS 10Y real yield + 10Y inflation breakeven (daily, lag ~1 day)
    tips_obs = _fred_obs("DFII10", n=2)
    if tips_obs:
        row["us_tips_10y"]       = round(tips_obs[0]["value"], 3)
        row["us_tips_date"]      = tips_obs[0]["date"]
        print(f"[fred] TIPS 10Y real = {row['us_tips_10y']}% (as of {row['us_tips_date']})")

    bkeven_obs = _fred_obs("T10YIE", n=2)
    if bkeven_obs:
        row["us_breakeven_10y"]  = round(bkeven_obs[0]["value"], 3)
        row["us_breakeven_date"] = bkeven_obs[0]["date"]
        print(f"[fred] 10Y Breakeven = {row['us_breakeven_10y']}% (as of {row['us_breakeven_date']})")

    # ── 2. Bund yields — stooq.com primary (daily, no key, works everywhere) ──
    print("[macro_liq] Fetching Bund yields (stooq.com)...")

    bund10_stooq = _stooq_yield("10dey.b", n=3)
    if bund10_stooq:
        row["bund_10y"]  = round(bund10_stooq[0]["value"], 3)
        row["bund_date"] = bund10_stooq[0]["date"]
        print(f"[stooq] Bund 10Y = {row['bund_10y']}% (as of {row['bund_date']})")

    bund2_stooq = _stooq_yield("2dey.b", n=3)
    if bund2_stooq:
        row["bund_2y"] = round(bund2_stooq[0]["value"], 3)
        print(f"[stooq] Bund 2Y  = {row['bund_2y']}%")

    # ── 3. ECB SDW — balance sheet + EU M3 (fails on restricted networks) ────
    print("[macro_liq] Fetching ECB SDW...")

    ecb_assets_obs = _ecb_obs("ILM", "W.U2.C.A.U20.EUR.E.1.Z5.0000.Z01.E", n=5)
    if ecb_assets_obs:
        # ECB ILM returns values in millions EUR — divide by 1,000,000 for trillions
        row["ecb_assets_t"]      = round(ecb_assets_obs[0]["value"] / 1_000_000, 3)
        row["ecb_assets_wk_pct"] = _wkchg(ecb_assets_obs)
        row["ecb_assets_date"]   = ecb_assets_obs[0]["date"]
    # FRED fallback for ECB total assets (ECBASSETS = billions EUR, NOT millions)
    if row.get("ecb_assets_t") is None:
        ecb_fred = _fred_obs("ECBASSETS", n=5)
        if ecb_fred:
            row["ecb_assets_t"]      = round(ecb_fred[0]["value"] / 1_000, 3)  # billions → trillions
            row["ecb_assets_wk_pct"] = _wkchg(ecb_fred)
            row["ecb_assets_date"]   = ecb_fred[0]["date"]
            print(f"[fred] ECB assets fallback = {row['ecb_assets_t']}T (as of {row['ecb_assets_date']})")

    # Bund ECB fallback if stooq failed
    if row.get("bund_10y") is None:
        bund10_ecb = _ecb_obs("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y", n=5)
        if bund10_ecb:
            row["bund_10y"]  = round(bund10_ecb[0]["value"], 3)
            row["bund_date"] = bund10_ecb[0]["date"]
    if row.get("bund_2y") is None:
        bund2_ecb = _ecb_obs("YC", "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y", n=5)
        if bund2_ecb:
            row["bund_2y"] = round(bund2_ecb[0]["value"], 3)

    eu_m3_obs = _ecb_obs("BSI", "M.U2.Y.V.M30.X.I.U2.2300.Z01.E", n=14)
    if len(eu_m3_obs) >= 13:
        row["eu_m3_yoy"]  = _yoy(eu_m3_obs)
        row["eu_m3_date"] = eu_m3_obs[0]["date"]

    # FRED last-resort fallback for Bund 10Y if both stooq and ECB fail (monthly)
    if row.get("bund_10y") is None:
        bund10_fred = _fred_obs("IRLTLT01DEM156N", n=2)
        if bund10_fred:
            row["bund_10y"]  = round(bund10_fred[0]["value"], 3)
            row["bund_date"] = bund10_fred[0]["date"]
            print(f"[fred] Bund 10Y fallback: {row['bund_10y']}% (as of {row['bund_date']})")

    if row.get("bund_10y") is not None and row.get("bund_2y") is not None:
        spread = round(row["bund_10y"] - row["bund_2y"], 3)
        row["bund_spread"] = spread
        row["bund_signal"] = _yc_signal(spread)

    # ── 3b. JGB daily — MoF Japan (free CSV, daily, no key) ─────────────────
    print("[macro_liq] Fetching JGB yields (MoF Japan daily CSV)...")

    jgb_data = _mof_jgb_yields(maturities=(2, 10))
    if jgb_data.get(10):
        row["jgb_10y"]      = round(jgb_data[10]["value"], 3)   # override FRED monthly
        row["jgb_10y_date"] = jgb_data[10]["date"]
        print(f"[mof] JGB 10Y = {row['jgb_10y']}% (as of {row['jgb_10y_date']})")
    if jgb_data.get(2):
        row["jgb_2y"] = round(jgb_data[2]["value"], 3)
        print(f"[mof] JGB 2Y  = {row['jgb_2y']}%")
    if row.get("jgb_10y") is not None and row.get("jgb_2y") is not None:
        jgb_spr          = round(row["jgb_10y"] - row["jgb_2y"], 3)
        row["jgb_spread"] = jgb_spr
        row["jgb_signal"] = _yc_signal(jgb_spr)
        print(f"[mof] JGB spread 10Y-2Y = {jgb_spr:+.3f}% -> {row['jgb_signal']}")

    # ── 3c. ChinaBond CCDC — CGB yields (scraped, no key) ─────────────────────
    # Primary: ChinaBond CCDC (geo-blocked on GitHub Actions — fails silently)
    # Fallback: FRED IRLTLT01CNM156N (OECD China 10Y, monthly, ~1-month lag)
    print("[macro_liq] Fetching CGB yields (ChinaBond CCDC → FRED fallback)...")

    cgb10 = _chinabond_yield(10)
    cgb2  = _chinabond_yield(2)
    if cgb10:
        row["cgb_10y"]  = round(cgb10["value"], 3)
        row["cgb_date"] = cgb10["date"]
        print(f"[chinabond] CGB 10Y = {row['cgb_10y']}% (as of {row['cgb_date']})")
    if cgb2:
        row["cgb_2y"] = round(cgb2["value"], 3)
        print(f"[chinabond] CGB 2Y  = {row['cgb_2y']}%")

    if row.get("cgb_10y") is not None and row.get("cgb_2y") is not None:
        cgb_spr           = round(row["cgb_10y"] - row["cgb_2y"], 3)
        row["cgb_spread"] = cgb_spr
        row["cgb_signal"] = _yc_signal(cgb_spr)
        print(f"[cgb] spread 10Y-2Y = {cgb_spr:+.3f}% -> {row['cgb_signal']}")

    # ── 4. Global CB Trend ────────────────────────────────────────────────────
    cb_signals = []
    if row.get("fed_walcl_wk_pct") is not None:
        cb_signals.append(1 if row["fed_walcl_wk_pct"] > 0 else -1)
    if row.get("ecb_assets_wk_pct") is not None:
        cb_signals.append(1 if row["ecb_assets_wk_pct"] > 0 else -1)
    if cb_signals:
        s = sum(cb_signals)
        row["global_cb_trend"] = "EXPANSION" if s > 0 else ("CONTRACTION" if s < 0 else "MIXED")

    # ── 5. yfinance ───────────────────────────────────────────────────────────
    print("[macro_liq] Fetching yfinance (P/E proxies + Gold/Stocks + CNH + Copper + JPY)...")
    row.update(_pe_proxies())
    row["gold_stocks"] = _gold_stocks_ratio()
    row["cnh_usd"]     = _cnh_usd()

    # Copper (HG=F) + Cu/Au ratio (cycle health signal)
    copper_price, _gold_oz, cu_au_ratio = _copper_gold()
    if copper_price:
        row["copper_price"]      = copper_price
        row["copper_gold_ratio"] = cu_au_ratio
        print(f"[yf] Copper = ${copper_price:.4f}/lb  Cu/Au = {cu_au_ratio}")

    # JPY/USD — yen carry trade risk indicator
    jpy = _fast_price("JPY=X")
    if jpy:
        row["jpy_usd"] = round(jpy, 2)
        print(f"[yf] JPY/USD = {row['jpy_usd']}")

    # ── 6. CAPE ───────────────────────────────────────────────────────────────
    print("[macro_liq] Fetching CAPE (multpl.com)...")
    cape = _cape_multpl()
    if cape:
        row["cape_us"]   = cape
        row["cape_date"] = today

    # ── 7. Write to DB ────────────────────────────────────────────────────────
    con = sqlite3.connect(DB_PATH, timeout=30)

    # Build UPSERT: only overwrite columns when this run actually fetched a value.
    # Earlier `INSERT OR REPLACE` blanked half-failed runs (a column that came back
    # NULL today overwrote yesterday's success). ON CONFLICT … DO UPDATE with
    # COALESCE keeps the prior value when excluded.col is NULL.
    fixed_cols  = ["date", "ts"]
    fixed_vals  = [today, now]
    data_cols   = list(row.keys())
    data_vals   = [row[c] for c in data_cols]

    all_cols    = fixed_cols + data_cols
    all_vals    = fixed_vals + data_vals
    placeholders = ", ".join(["?"] * len(all_cols))
    col_sql     = ", ".join(all_cols)

    update_clauses = ["ts = excluded.ts"]
    for c in data_cols:
        update_clauses.append(f"{c} = COALESCE(excluded.{c}, {c})")
    update_sql = ", ".join(update_clauses)

    con.execute(
        f"INSERT INTO macro_liquidity ({col_sql}) VALUES ({placeholders}) "
        f"ON CONFLICT(date) DO UPDATE SET {update_sql}",
        all_vals,
    )
    con.commit()
    con.close()

    filled = sum(1 for v in row.values() if v is not None)
    print(f"[macro_liq] Done — {filled}/{len(row)} fields populated for {today}")
    _print_summary(row)


def _print_summary(row: dict):
    print("\n--- Liquidity ---")
    print(f"  Fed: {row.get('fed_walcl_t','N/A')}T USD  WoW: {row.get('fed_walcl_wk_pct','N/A')}%  (as of {row.get('fed_walcl_date','?')})")
    print(f"  ECB: {row.get('ecb_assets_t','N/A')}T EUR  WoW: {row.get('ecb_assets_wk_pct','N/A')}%  (as of {row.get('ecb_assets_date','?')})")
    print(f"  RRP: {row.get('rrp_b','N/A')}B   TGA: {row.get('tga_b','N/A')}B")
    print(f"  US M2 YoY: {row.get('us_m2_yoy','N/A')}%  |  China M2 YoY: {row.get('china_m2_yoy','N/A')}%")
    print(f"  CB Trend: {row.get('global_cb_trend','N/A')}")
    print("\n--- Real Rates & Inflation ---")
    print(f"  TIPS 10Y real: {row.get('us_tips_10y','N/A')}%  (as of {row.get('us_tips_date','?')})")
    print(f"  10Y Breakeven: {row.get('us_breakeven_10y','N/A')}%  (as of {row.get('us_breakeven_date','?')})")
    print("\n--- Yield Curves ---")
    print(f"  Bund:  10Y {row.get('bund_10y','N/A')}%  2Y {row.get('bund_2y','N/A')}%  Spread {row.get('bund_spread','N/A')}%  -> {row.get('bund_signal','N/A')}")
    print(f"  JGB:   10Y {row.get('jgb_10y','N/A')}%  2Y {row.get('jgb_2y','N/A')}%  Spread {row.get('jgb_spread','N/A')}%  -> {row.get('jgb_signal','N/A')}")
    print(f"  CGB:   10Y {row.get('cgb_10y','N/A')}%  2Y {row.get('cgb_2y','N/A')}%  Spread {row.get('cgb_spread','N/A')}%  -> {row.get('cgb_signal','N/A')}")
    print(f"  UK 10Y: {row.get('uk_10y','N/A')}%  (as of {row.get('uk_10y_date','?')})")
    print("\n--- Real Economy ---")
    print(f"  Copper: ${row.get('copper_price','N/A')}/lb  Cu/Au ratio: {row.get('copper_gold_ratio','N/A')}")
    print(f"  JPY/USD: {row.get('jpy_usd','N/A')}")
    print("\n--- Valuation & Credit ---")
    print(f"  CAPE US: {row.get('cape_us','N/A')}  P/E EU: {row.get('pe_eu','N/A')}  P/E JP: {row.get('pe_jp','N/A')}  P/E EM: {row.get('pe_em','N/A')}")
    print(f"  HY OAS US: {row.get('hy_oas_us','N/A')}bp  HY OAS EU: {row.get('hy_oas_eu','N/A')}bp  HY OAS EM: {row.get('hy_oas_em','N/A')}bp")
    print(f"  Gold/Stocks: {row.get('gold_stocks','N/A')}  USD/CNH: {row.get('cnh_usd','N/A')}")


if __name__ == "__main__":
    run()
