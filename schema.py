"""
schema.py — Single source of truth for the /data/*.json layer.

Defines, per dataset:
  - which fields are exposed (the API contract)
  - their unit
  - their interpretation thresholds (regime boundaries)
  - their extraction path inside the box render() dict

Consumed by render_html.write_data_layer(). Keeping units + thresholds here
(not duplicated in box JS) means a threshold change happens in ONE place and
flows into both the rendered page logic and the agent-facing JSON.

Unit tokens (stable vocabulary for agents):
  index | pct | pct_points | bps | ratio | fx_per_usd | category
  trillion_usd | trillion_eur | billion_usd
"""

# ── MACRO — scalar economic indicators (rich per-field) ──────────────────────
# Each entry: key, path (tuple) into box_01_macro data dict, unit, thresholds|None
MACRO_METRICS = [
    # US signal cards
    {"key": "vix",                "path": ("vix", "valeur"),          "unit": "index",
     "thresholds": {"complacency": 15, "normal": 20, "panic": 30}},
    {"key": "erp",                "path": ("erp", "valeur"),          "unit": "ratio",
     "thresholds": {"expensive": 0.01, "attractive": 0.02}},
    {"key": "yield_curve_10y_3m", "path": ("yield_curve", "valeur"),  "unit": "pct_points",
     "thresholds": {"full_inversion": -0.5, "flat": 0.0, "steep": 1.0}},
    {"key": "us_10y",             "path": ("yield_curve", "us10y"),   "unit": "pct",  "thresholds": None},
    {"key": "us_3m",              "path": ("yield_curve", "us3m"),    "unit": "pct",  "thresholds": None},
    {"key": "dxy",                "path": ("dxy", "valeur"),          "unit": "index",
     "thresholds": {"weak": 95, "average": 98, "strong": 108}},
    {"key": "sp500_pe",           "path": ("erp", "sp500_pe"),        "unit": "ratio", "thresholds": None},

    # Central bank liquidity
    {"key": "fed_balance_sheet",      "path": ("liq", "fed_walcl_t"),       "unit": "trillion_usd", "thresholds": None},
    {"key": "fed_balance_sheet_wow",  "path": ("liq", "fed_walcl_wk_pct"),  "unit": "pct",          "thresholds": None},
    {"key": "ecb_balance_sheet",      "path": ("liq", "ecb_assets_t"),      "unit": "trillion_eur", "thresholds": None},
    {"key": "ecb_balance_sheet_wow",  "path": ("liq", "ecb_assets_wk_pct"), "unit": "pct",          "thresholds": None},
    {"key": "reverse_repo",           "path": ("liq", "rrp_b"),             "unit": "billion_usd",  "thresholds": None},
    {"key": "treasury_general_acct",  "path": ("liq", "tga_b"),             "unit": "billion_usd",  "thresholds": None},
    {"key": "global_cb_trend",        "path": ("liq", "global_cb_trend"),   "unit": "category",     "thresholds": None},

    # Money supply
    {"key": "us_m2_yoy",     "path": ("liq", "us_m2_yoy"),    "unit": "pct", "thresholds": {"subdued": 3, "elevated": 8}},
    {"key": "eu_m3_yoy",     "path": ("liq", "eu_m3_yoy"),    "unit": "pct", "thresholds": {"subdued": 3, "elevated": 7}},
    {"key": "china_m2_yoy",  "path": ("liq", "china_m2_yoy"), "unit": "pct", "thresholds": None},
    {"key": "japan_m2_yoy",  "path": ("liq", "japan_m2_yoy"), "unit": "pct", "thresholds": None},

    # Credit spreads
    {"key": "hy_oas_us", "path": ("liq", "hy_oas_us"), "unit": "bps",
     "thresholds": {"compression": 350, "average": 525, "stress": 700}},
    {"key": "hy_oas_eu", "path": ("liq", "hy_oas_eu"), "unit": "bps",
     "thresholds": {"compression": 350, "average": 525, "stress": 700}},
    {"key": "hy_oas_em", "path": ("liq", "hy_oas_em"), "unit": "bps",
     "thresholds": {"compression": 400, "average": 600, "stress": 800}},

    # Sovereign yields & curves
    {"key": "bund_10y", "path": ("liq", "bund_10y"), "unit": "pct", "thresholds": None},
    {"key": "bund_2y",  "path": ("liq", "bund_2y"),  "unit": "pct", "thresholds": None},
    {"key": "jgb_10y",  "path": ("liq", "jgb_10y"),  "unit": "pct", "thresholds": None},
    {"key": "jgb_2y",   "path": ("liq", "jgb_2y"),   "unit": "pct", "thresholds": None},
    {"key": "cgb_10y",  "path": ("liq", "cgb_10y"),  "unit": "pct", "thresholds": None},
    {"key": "uk_10y",   "path": ("liq", "uk_10y"),   "unit": "pct", "thresholds": None},

    # Real rates & inflation
    {"key": "us_tips_10y",     "path": ("liq", "us_tips_10y"),     "unit": "pct",
     "thresholds": {"repression": 0.0, "neutral": 0.5, "restrictive": 2.5}},
    {"key": "us_breakeven_10y", "path": ("liq", "us_breakeven_10y"), "unit": "pct", "thresholds": None},

    # Valuation
    {"key": "cape_us", "path": ("liq", "cape_us"), "unit": "ratio",
     "thresholds": {"mean": 17, "elevated": 25, "extreme": 34}},
    {"key": "pe_eu", "path": ("liq", "pe_eu"), "unit": "ratio", "thresholds": None},
    {"key": "pe_jp", "path": ("liq", "pe_jp"), "unit": "ratio", "thresholds": None},
    {"key": "pe_em", "path": ("liq", "pe_em"), "unit": "ratio", "thresholds": None},
    {"key": "pe_cn", "path": ("liq", "pe_cn"), "unit": "ratio", "thresholds": None},

    # Real economy & cross-asset
    {"key": "copper_gold_ratio", "path": ("liq", "copper_gold_ratio"), "unit": "ratio",
     "thresholds": {"stress": 0.18, "risk_off": 0.25, "expansion": 0.35}},
    {"key": "jpy_usd",     "path": ("liq", "jpy_usd"),     "unit": "fx_per_usd",
     "thresholds": {"strong": 115, "intervention": 145, "extreme": 155}},
    {"key": "cnh_usd",     "path": ("liq", "cnh_usd"),     "unit": "fx_per_usd",
     "thresholds": {"strong": 6.5, "psychological": 7.3}},
    {"key": "gold_stocks", "path": ("liq", "gold_stocks"), "unit": "ratio", "thresholds": None},
]

# Regime labels already computed by the box (compact, high-value classification)
MACRO_REGIME_PATHS = {
    "vix":                ("vix", "regime"),
    "erp":                ("erp", "regime"),
    "yield_curve_10y_3m": ("yield_curve", "regime"),
}

# ── COLLECTIONS — field→unit maps (records stay flat to save tokens) ─────────
INDICES_UNITS = {
    "close": "native_ccy", "chg_pct": "pct", "ret_1m": "pct", "ret_1y": "pct",
    "rvol": "ratio",
}
SECTORS_UNITS = {
    "close": "usd", "chg_pct": "pct", "score": "composite",
    "ret_1m": "pct", "ret_3m": "pct", "ret_6m": "pct", "ret_1y": "pct",
    "rperf_1m": "pct", "rperf_3m": "pct", "rperf_6m": "pct", "rperf_1y": "pct",
}
SENTIMENT_UNITS = {
    "sentiment_score": "score_-1_to_1", "mfi": "index_0_100",
    "obv_dir": "direction", "rvol": "ratio", "chg_pct": "pct",
}
PORTFOLIO_UNITS = {
    "close": "native_ccy", "chg_pct": "pct", "score": "composite",
    "rvol": "ratio", "mfi": "index_0_100", "sentiment_score": "score_-1_to_1",
}

# ── Per-dataset provenance (shown in JSON envelope) ──────────────────────────
SOURCES = {
    "macro":     "FRED, ECB SDW, MoF Japan, ChinaBond CCDC, stooq, multpl.com, yfinance",
    "indices":   "Yahoo Finance (curl_cffi)",
    "news":      "RSS: Bloomberg, AP, MarketWatch, SCMP, FT",
    "sectors":   "Yahoo Finance (curl_cffi)",
    "sentiment": "Yahoo Finance (curl_cffi) — MFI/OBV/DMA200 composite",
    "portfolio": "Yahoo Finance (curl_cffi)",
}
