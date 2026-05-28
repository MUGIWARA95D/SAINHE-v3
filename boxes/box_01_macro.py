"""
box_01_macro.py — Santé macro : VIX, Yield Curve, ERP, DXY + Global Liquidity Strip.
"""

import sqlite3

# ══════════════════════════════════════════════════════════════
# ── 1. META
# ══════════════════════════════════════════════════════════════
META = {
    "id"         : "box_01_macro",
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
# ── 1c. PROFESSIONAL INFERENCE TEXT ENGINE
#
#  Tier 1 — Institutional published thresholds:
#    VIX    : CBOE VIX White Paper (regime bands)
#    ERP    : CAPM / Damodaran (1960–present dataset)
#    YC     : NY Fed recession probability model
#    CAPE   : Shiller / Yale CAPE (1881–present, long-run avg = 17)
#    HY OAS : ICE BofA HY index / Fed Financial Stability Report
#
#  Tier 2 — No official standard; historical percentile context:
#    M2/M3 YoY      : FRED / ECB SDW historical range (1990–present)
#    CNH/USD         : PBOC managed-float band (post-2015 reform)
#    Balance sheets  : CB WoW directional change
#    Gold/S&P ratio  : historical risk-on / risk-off context
#    DXY level       : 10-year average ~98 (1985 Plaza Accord era)
# ══════════════════════════════════════════════════════════════

# ── Tier 1 ──────────────────────────────────────────────────────────────────

def _vix_text(v):
    """CBOE VIX White Paper regime classification."""
    if v is None:
        return ""
    if v < 12:
        return (f"{v:.1f} — extreme complacency (CBOE <12). "
                f"Tail-risk structurally underpriced; vol spikes to >30 typically occur within 3–6 months of sub-12 readings.")
    if v < 15:
        return (f"{v:.1f} — complacency zone (CBOE <15). "
                f"Implied volatility below historical norm; out-of-the-money puts historically cheap at this level.")
    if v < 20:
        return (f"{v:.1f} — normal range (CBOE 15–20). "
                f"Orderly markets; no systemic stress. Long equity exposure appropriate without excess hedging premium.")
    if v < 30:
        return (f"{v:.1f} — elevated fear (CBOE 20–30). "
                f"Risk-off rotation developing; 1–2 standard deviation event. Consistent with sector rotation, not crisis.")
    return (f"{v:.1f} — panic zone (CBOE >30). "
            f"Consistent with crisis episodes (GFC 2008: 80, COVID 2020: 66). Historically a mean-reversion buy signal within 20–30 sessions.")


def _erp_text(erp, us10y, sp500_pe):
    """CAPM / Damodaran equity risk premium framework."""
    if erp is None:
        return ""
    erp_pct = erp * 100
    ey_pct  = (100.0 / sp500_pe) if sp500_pe else None
    y10_str = f"{us10y:.2f}%" if us10y is not None else "N/A"
    ey_str  = f"{ey_pct:.2f}%" if ey_pct is not None else "N/A"

    if erp < 0:
        return (f"Negative ERP ({erp_pct:+.2f}%): risk-free rate ({y10_str}) exceeds earnings yield ({ey_str}). "
                f"Historically rare — last observed 1997–2000 and 2006–2008 (Damodaran). "
                f"Bonds structurally outperform equities on a risk-adjusted basis at these levels.")
    if erp < ERP_EXPENSIVE:
        return (f"ERP at {erp_pct:.2f}% — below 1% CAPM threshold. "
                f"Near-zero equity premium vs bonds (earnings yield {ey_str} vs 10Y {y10_str}). "
                f"Risk-adjusted returns historically favour fixed income (Damodaran, 1960–present).")
    if erp < ERP_ATTRACTIVE:
        return (f"ERP at {erp_pct:.2f}% — below the 2% CAPM attractiveness threshold. "
                f"Equity premium modest vs bonds. Balanced allocation warranted; no strong directional signal (Damodaran).")
    return (f"ERP at {erp_pct:.2f}% — above 2% CAPM threshold. "
            f"Earnings yield ({ey_str}) meaningfully exceeds risk-free rate ({y10_str}). "
            f"Historically associated with above-average forward equity returns (Damodaran, 1960–present).")


def _yc_text(spread):
    """NY Fed yield curve recession model language."""
    if spread is None:
        return ""
    if spread >= 1.0:
        return (f"{spread:+.2f}% spread — expansionary slope. "
                f"NY Fed recession model: low probability when 10Y−3M >100bps. "
                f"Historically consistent with a sustained economic growth environment.")
    if spread >= 0.0:
        return (f"{spread:+.2f}% spread — flattening towards zero. "
                f"NY Fed: ambiguous signal; no confirmed recession indicator. "
                f"Historical lead time to full inversion: 12–18 months from this stage.")
    if spread >= -0.5:
        return (f"{spread:.2f}% — partial inversion. NY Fed: caution, not confirmation. "
                f"False positives documented: 1998 (LTCM), 2019 (Fed pivot). "
                f"Sustained full inversion required for elevated recession probability.")
    return (f"{spread:.2f}% — full inversion. NY Fed recession model at elevated probability. "
            f"Historical lead time to recession: 6–24 months (avg. 14 months, 1970–2023). "
            f"~70% of full inversions preceded a recession.")


def _cape_text(cape):
    """Shiller / Yale CAPE — long-run mean 17 (1881–present)."""
    CAPE_MEAN = 17.0
    if cape is None:
        return ""
    ratio = cape / CAPE_MEAN
    if cape <= 20:
        return (f"{cape:.1f} — near long-run mean of {CAPE_MEAN:.0f} (Shiller/Yale, 1881–present). "
                f"Forward 10-year real returns historically ~8–10% annualised from this level.")
    if cape <= 25:
        return (f"{cape:.1f} ({ratio:.1f}× long-run mean of {CAPE_MEAN:.0f}, Shiller/Yale, 1881–present). "
                f"Modest valuation premium. 10-year forward real returns historically 4–7% from this level.")
    if cape <= 34:
        return (f"{cape:.1f} ({ratio:.1f}× the long-run mean of {CAPE_MEAN:.0f}, Shiller/Yale, 1881–present). "
                f"Elevated valuation. 10-year forward real returns historically compressed to 0–4%.")
    return (f"{cape:.1f} ({ratio:.1f}× the long-run mean of {CAPE_MEAN:.0f}, Shiller/Yale, 1881–present). "
            f"Comparable to 1929 peak (33) and dot-com peak 2000 (44). "
            f"Forward 10-year real returns historically near-zero or negative at this level.")


def _hy_text(bps, variant="US"):
    """ICE BofA HY OAS — Fed Financial Stability Report framework."""
    if bps is None:
        return ""
    if variant == "US":
        avg, pre_gfc, label = 525, 240, "ICE BofA US HY"
    else:
        avg, pre_gfc, label = 600, 280, "ICE BofA EM HY"

    if bps < pre_gfc + 20:
        return (f"{bps:.0f}bps — approaching pre-GFC lows (~{pre_gfc}bps, mid-2007). "
                f"{label}: extreme compression. Credit risk structurally underpriced; late-cycle complacency signal.")
    if bps < 350:
        return (f"{bps:.0f}bps — well below {label} long-run avg (~{avg}bps). "
                f"Comparable to 2006–2007 pre-GFC and 2021 post-COVID troughs. Compressed spreads = underpriced credit risk.")
    if bps < 500:
        return (f"{bps:.0f}bps — below {label} long-run avg (~{avg}bps). "
                f"Orderly credit conditions. No systemic stress per Fed Financial Stability Report framework.")
    if bps < 700:
        return (f"{bps:.0f}bps — {label} stress zone (>500bps). "
                f"Consistent with Fed FSR 'elevated vulnerability' classification. Monitor for spread widening acceleration.")
    return (f"{bps:.0f}bps — {label} crisis level (>700bps). "
            f"Consistent with GFC peak (2000bps, 2008) and COVID spike (1100bps, 2020). Systemic stress signal.")


# ── New Tier 1 — Real rates, Cu/Au, CGB, JPY (all institutional data) ───────

def _tips_text(real_rate, breakeven=None):
    """
    FRED DFII10: 10Y TIPS real yield.
    >2.5% restrictive; 0.5–2.5% elevated; 0–0.5% neutral; <0% financial repression.
    """
    if real_rate is None:
        return ""
    bk_str = f" Breakeven: {breakeven:.2f}%." if breakeven is not None else ""
    if real_rate > 2.5:
        return (f"{real_rate:.2f}% — restrictive real rates (>2.5%). "
                f"Historically among the highest since GFC 2008. "
                f"Strong headwind for growth equities, PE multiples, and levered assets.{bk_str}")
    if real_rate > 0.5:
        return (f"{real_rate:.2f}% — elevated real rates (0.5–2.5%). "
                f"Above neutral; borrowing cost exceeds expected inflation. "
                f"Moderately restrictive for risk assets and credit.{bk_str}")
    if real_rate >= 0:
        return (f"{real_rate:.2f}% — near-neutral real rate. "
                f"Inflation broadly compensated by nominal yield. No strong directional signal.{bk_str}")
    if real_rate > -1.0:
        return (f"{real_rate:.2f}% — mildly negative real rate. "
                f"Financial repression: depositors earn below inflation. "
                f"Historically supportive for real assets (gold, real estate).{bk_str}")
    return (f"{real_rate:.2f}% — deep financial repression (<−1%). "
            f"Consistent with 2020–2022 QE peak (TIPS reached −1.7%, Nov 2021). "
            f"Strong tailwind for levered assets, real estate, and speculative growth.{bk_str}")


def _copper_text(price, cu_au_ratio):
    """
    Cu/Au ratio regime: >0.35 expansion, 0.25–0.35 mid-cycle, 0.18–0.25 risk-off, <0.18 stress.
    Copper/gold ratio is the best real-time PMI proxy outside official surveys.
    """
    if cu_au_ratio is None:
        return ""
    p_str = f" Copper at ${price:.4f}/lb." if price else ""
    if cu_au_ratio > 0.35:
        return (f"Cu/Au ratio {cu_au_ratio:.4f} — expansion signal (>0.35). "
                f"Copper demand dominant over safe-haven gold. "
                f"Historically consistent with global PMI >52 and industrial cycle acceleration.{p_str}")
    if cu_au_ratio > 0.25:
        return (f"Cu/Au ratio {cu_au_ratio:.4f} — mid-cycle neutral (0.25–0.35). "
                f"Industrial demand balanced against safe-haven flows. No strong directional signal.{p_str}")
    if cu_au_ratio > 0.18:
        return (f"Cu/Au ratio {cu_au_ratio:.4f} — risk-off territory (0.18–0.25). "
                f"Gold outperforming copper; consistent with global slowdown concerns, PMI contraction, or EM stress.{p_str}")
    return (f"Cu/Au ratio {cu_au_ratio:.4f} — cycle stress signal (<0.18). "
            f"Copper severely depressed relative to gold. "
            f"Consistent with recessionary episodes (2016 trough: ~0.16).{p_str}")


def _cgb_text(spread):
    """
    CGB 10Y−2Y curve — China Japanification risk signal.
    ≥0.5% normal; 0.1–0.5% flattening; ~0% Japanification warning; negative = strong signal.
    """
    if spread is None:
        return ""
    if spread >= 0.5:
        return (f"CGB spread {spread:+.2f}% — normal term structure. "
                f"Positive term premium; no deflation or Japanification risk signal.")
    if spread >= 0.1:
        return (f"CGB spread {spread:+.2f}% — curve flattening. "
                f"Reduced term premium. Watch for sustained move below 10bp — consistent with China's post-2021 property crisis deleveraging.")
    if spread >= 0.0:
        return (f"CGB spread {spread:+.2f}% — near-zero term premium. "
                f"Japanification signal: bond markets pricing prolonged low growth and deflation risk in China.")
    return (f"CGB spread {spread:+.2f}% — inverted. "
            f"Strong Japanification signal. Consistent with deflation concerns, PBOC rate cuts, or capital flight within domestic markets.")


def _jpy_text(rate):
    """
    JPY per USD (yfinance JPY=X). >155: extreme carry risk; >145: BOJ intervention; <115: yen strength.
    """
    if rate is None:
        return ""
    if rate > 155:
        return (f"¥{rate:.2f}/USD — historically weak yen (>155). "
                f"BOJ intervention risk extreme. Yen carry trade at maximum — rapid yen strengthening triggers "
                f"global deleveraging (Aug 2024: ¥161→¥142 in 3 weeks, −12% global equities).")
    if rate > 145:
        return (f"¥{rate:.2f}/USD — BOJ intervention risk elevated (>145). "
                f"PBOC and BOJ have historically defended near this level (2019: 145, 2022: 151). "
                f"Yen carry meaningful — monitor for sudden unwind.")
    if rate > 130:
        return (f"¥{rate:.2f}/USD — mildly weak yen (130–145). "
                f"Within post-2022 BOJ YCC adjustment range. No acute carry unwind risk.")
    if rate > 115:
        return (f"¥{rate:.2f}/USD — moderate yen (115–130). Near pre-2022 long-run range. "
                f"Carry trade small; limited systemic risk from potential reversal.")
    return (f"¥{rate:.2f}/USD — strong yen (<115). "
            f"Carry trade unwinding or BOJ hawkish pivot. "
            f"Historically associated with risk-off episodes and EM capital outflows (2008, 2011, 2016).")


def _eur_text(rate):
    """
    EUR/USD — ECB vs Fed policy divergence signal.
    >1.15: USD weak / ECB hawkish; <0.95: USD very strong / EUR stress.
    """
    if rate is None:
        return ""
    if rate > 1.20:
        return (f"{rate:.4f} EUR/USD — historically weak USD. "
                f"Dollar weakness typical of Fed easing cycles or fiscal concerns. Positive for EM and commodities.")
    if rate > 1.10:
        return (f"{rate:.4f} EUR/USD — USD mild weakness. "
                f"ECB and Fed broadly aligned; no major policy divergence signal.")
    if rate > 1.00:
        return (f"{rate:.4f} EUR/USD — near parity zone. "
                f"Reflects residual USD strength vs 2010–2020 avg (~1.18). "
                f"Fed/ECB rate differential compressing or euro area growth lagging.")
    if rate > 0.95:
        return (f"{rate:.4f} EUR/USD — strong USD (near 2022 parity crisis lows). "
                f"Euro area energy shock or ECB-Fed divergence. "
                f"Parity episodes historically brief — watch ECB response.")
    return (f"{rate:.4f} EUR/USD — extremely strong USD. "
            f"Below 2022 parity floor. Consistent with acute euro area stress or emergency USD demand.")


def _aud_text(rate):
    """
    AUD/USD — commodity cycle and China/EM risk appetite proxy.
    AUD is the 'risk currency': rises with global growth and China activity.
    >0.75: risk-on / China strong; <0.60: risk-off / commodity cycle trough.
    """
    if rate is None:
        return ""
    if rate > 0.75:
        return (f"{rate:.4f} AUD/USD — strong AUD (>0.75). "
                f"Risk-on regime; consistent with expanding China PMI, commodity demand, and EM growth acceleration.")
    if rate > 0.68:
        return (f"{rate:.4f} AUD/USD — neutral-to-positive range (0.68–0.75). "
                f"China activity broadly stable; no acute commodity cycle stress.")
    if rate > 0.60:
        return (f"{rate:.4f} AUD/USD — weak AUD (0.60–0.68). "
                f"China slowdown or commodity demand concerns. "
                f"Consistent with EM risk-off episodes and global manufacturing contraction.")
    return (f"{rate:.4f} AUD/USD — historically weak AUD (<0.60). "
            f"Consistent with commodity cycle troughs (GFC 2009: 0.60, COVID 2020: 0.57). "
            f"Strong risk-off signal for EM and commodity exporters.")


# ── Tier 2 ──────────────────────────────────────────────────────────────────

def _m2_text(yoy, region="US"):
    """M2/M3 YoY — historical context (FRED/ECB SDW, 1990–present). No official threshold."""
    if yoy is None:
        return ""
    if region == "US":
        avg, label = 6.0, "FRED M2, 1990–present avg ~6%"
    else:
        avg, label = 5.0, "ECB M3, 1990–present avg ~5%"

    if yoy < 0:
        return (f"{yoy:+.1f}% YoY — monetary contraction. "
                f"Below zero for the first time since the 1930s in the US; consistent with QT-driven deleveraging. "
                f"Historically precedes deflationary pressure by 12–18 months ({label}).")
    if yoy < 3:
        return (f"{yoy:+.1f}% YoY — subdued money growth, below historical avg of ~{avg:.0f}% ({label}). "
                f"Disinflationary. No excess liquidity risk; watch for demand contraction if sustained.")
    if yoy < avg + 2:
        return (f"{yoy:+.1f}% YoY — within normal historical range ({label}). "
                f"No excess liquidity signal. Consistent with trend GDP growth.")
    return (f"{yoy:+.1f}% YoY — above historical avg of ~{avg:.0f}% ({label}). "
            f"Excess money supply growth historically leads CPI inflation by 12–24 months (Friedman/Schwartz; ECB Working Papers).")


def _cnh_text(rate):
    """CNH/USD — PBOC managed-float context (post-2015 reform band: ~6.1–7.35)."""
    if rate is None:
        return ""
    if rate < 6.5:
        return (f"{rate:.4f} CNH/USD — strong yuan. "
                f"Consistent with PBOC appreciation bias or capital inflows. Positive for EM risk appetite.")
    if rate < 7.0:
        return (f"{rate:.4f} CNH/USD — within PBOC managed band (6.1–7.35). "
                f"No currency stress signal. FX reserve drawdown pressure absent.")
    if rate < 7.3:
        return (f"{rate:.4f} CNH/USD — approaching '7.3' psychological threshold. "
                f"PBOC historically intervenes near this level (2019: 7.19, 2022: 7.35). Watch FX reserves.")
    return (f"{rate:.4f} CNH/USD — above 7.3 threshold. "
            f"Consistent with yuan depreciation episodes (trade war 2019, 2022 selloff). "
            f"PBOC intervention risk elevated; negative for EM sentiment broadly.")


def _balance_sheet_text(wk_pct, label="Fed"):
    """Central bank balance sheet WoW change — Tier 2 directional context."""
    if wk_pct is None:
        return ""
    if abs(wk_pct) < 0.05:
        return f"Flat week-on-week (±0.05%). {label} balance sheet in maintenance phase; no net policy impulse."
    if wk_pct > 0.5:
        return (f"{wk_pct:+.2f}% w/w — meaningful expansion. "
                f"{label} adding reserves to the system; net loosening of financial conditions.")
    if wk_pct > 0:
        return f"{wk_pct:+.2f}% w/w — marginal expansion. {label} balance sheet growing modestly."
    if wk_pct > -0.5:
        return f"{wk_pct:+.2f}% w/w — measured contraction. {label} running QT at a gradual pace."
    return (f"{wk_pct:+.2f}% w/w — notable contraction. "
            f"{label} actively draining reserves via QT; tightening financial conditions.")


def _gold_ratio_text(ratio):
    """Gold/S&P 500 oz-per-index-point ratio — historical risk-on/off context."""
    if ratio is None:
        return ""
    # Context: 2019–2022 avg ~0.42–0.55; 2011 defensive peak ~1.73
    if ratio > 1.0:
        return (f"{ratio:.3f} oz/pt — elevated vs recent range (2019–2023 avg: ~0.42–0.55). "
                f"Gold meaningfully outperforming equities. Consistent with macro uncertainty peaks (2011: 1.73).")
    if ratio > 0.6:
        return (f"{ratio:.3f} oz/pt — above recent norm (2019–2022 avg: ~0.42–0.55). "
                f"Gold outperforming equities; mild defensive rotation underway.")
    if ratio > 0.42:
        return (f"{ratio:.3f} oz/pt — within recent historical range (2019–2023: 0.42–0.55). "
                f"Balanced allocation between risk assets and gold; no strong directional signal.")
    return (f"{ratio:.3f} oz/pt — below recent historical range. "
            f"Equities strongly outperforming gold; risk-on dominant regime.")


def _dxy_text(val):
    """DXY — historical level context (10-year avg ~98; Plaza Accord era range: 70–120)."""
    if val is None:
        return ""
    if val > 108:
        return (f"DXY at {val:.1f} — strong USD territory (10Y avg: ~98). "
                f"Historically headwind for USD-priced commodities, EM debt, and US multinational earnings.")
    if val > 102:
        return (f"DXY at {val:.1f} — above 10-year average (~98). "
                f"Mild USD strength; moderate drag on EM currencies and commodity indices.")
    if val > 95:
        return (f"DXY at {val:.1f} — near 10-year average (~98). "
                f"Neutral USD; balanced impact on global risk assets and commodities.")
    if val > 88:
        return (f"DXY at {val:.1f} — mild USD weakness vs 10-year avg (~98). "
                f"Historically supportive for commodities, gold, and EM equities.")
    return (f"DXY at {val:.1f} — historically weak USD (10Y avg: ~98). "
            f"Strong tailwind for gold, commodities, and USD-denominated EM debt service.")


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


def _fetch_fx_pair(con: sqlite3.Connection, pair: str) -> float | None:
    """
    Lit le dernier taux pour une paire FX depuis fx_rates.
    pair = 'USD_EUR' → retourne USD/EUR (e.g. 0.867)
    Appeler 1/rate pour obtenir EUR/USD.
    """
    try:
        row = con.execute(
            "SELECT rate FROM fx_rates WHERE pair=? ORDER BY ts DESC LIMIT 1",
            (pair,),
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _fetch_liquidity(con: sqlite3.Connection) -> dict:
    """
    Lit la dernière ligne de macro_liquidity.
    Retourne {} si la table est vide ou absente.
    """
    try:
        row = con.execute(
            "SELECT * FROM macro_liquidity ORDER BY date DESC LIMIT 1"
        ).fetchone()
    except Exception:
        return {}
    if not row:
        return {}
    cols = [d[0] for d in con.execute(
        "SELECT * FROM macro_liquidity LIMIT 0"
    ).description]
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
    liq    = _fetch_liquidity(con)
    # FX rates from fx_rates table (inverted to get CCY/USD convention)
    _usd_eur = _fetch_fx_pair(con, "USD_EUR")
    _usd_aud = _fetch_fx_pair(con, "USD_AUD")
    eur_usd  = round(1.0 / _usd_eur, 4) if _usd_eur else None
    aud_usd  = round(1.0 / _usd_aud, 4) if _usd_aud else None

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

    # ── Inference texts (generated in Python, displayed verbatim by JS) ──────
    vix_text    = _vix_text(vix_val)
    erp_text    = _erp_text(erp_val, macro.get("us10y"), macro.get("sp500_pe"))
    yc_text     = _yc_text(yc_val)
    dxy_text    = _dxy_text(dxy.get("close"))
    # Liq strip — Tier 1
    cape_text   = _cape_text(liq.get("cape_us"))
    hy_us_text  = _hy_text(liq.get("hy_oas_us"), "US")
    hy_eu_text  = _hy_text(liq.get("hy_oas_eu"), "EU")
    hy_em_text  = _hy_text(liq.get("hy_oas_em"), "EM")
    # Liq strip — new Tier 1 (real rates, Cu/Au, CGB, JPY)
    tips_text   = _tips_text(liq.get("us_tips_10y"), liq.get("us_breakeven_10y"))
    copper_text = _copper_text(liq.get("copper_price"), liq.get("copper_gold_ratio"))
    cgb_text    = _cgb_text(liq.get("cgb_spread"))
    jpy_text    = _jpy_text(liq.get("jpy_usd"))
    eur_text    = _eur_text(eur_usd)
    aud_text    = _aud_text(aud_usd)
    # Liq strip — Tier 2
    us_m2_text  = _m2_text(liq.get("us_m2_yoy"), "US")
    eu_m3_text  = _m2_text(liq.get("eu_m3_yoy"), "EU")
    cnh_text    = _cnh_text(liq.get("cnh_usd"))
    fed_bs_text = _balance_sheet_text(liq.get("fed_walcl_wk_pct"), "Fed")
    ecb_bs_text = _balance_sheet_text(liq.get("ecb_assets_wk_pct"), "ECB")
    gold_text   = _gold_ratio_text(liq.get("gold_stocks"))

    return {
        "meta": {**META, "titre": META["titre"].get(lang, META["titre"]["EN"])},
        "data": {
            "ts"         : macro.get("ts"),
            "vix"        : {
                "valeur" : vix_val,
                "regime" : vix_regime,
                "text"   : vix_text,
            },
            "yield_curve": {
                "valeur"  : yc_val,
                "inverted": inverted,
                "regime"  : yc_regime,   # "steep"|"flat"|"partial_inversion"|"full_inversion"
                "us10y"   : macro.get("us10y"),
                "us3m"    : macro.get("us3m"),
                "text"    : yc_text,
            },
            "erp"        : {
                "valeur"  : erp_val,
                "regime"  : erp_regime,
                "sp500_pe": macro.get("sp500_pe"),
                "text"    : erp_text,
            },
            "dxy"        : {
                "valeur"  : dxy.get("close"),
                "chg_pct" : dxy.get("chg_pct"),
                "ret_1m"  : dxy.get("ret_1m"),
                "sparkline": dxy.get("sparkline_json"),
                "text"    : dxy_text,
            },
            "sp500"      : {
                "close"   : sp500.get("close"),
                "chg_pct" : sp500.get("chg_pct"),
                "ret_1y"  : sp500.get("ret_1y"),
                "sparkline": sp500.get("sparkline_json"),
            },
            # ── Global Liquidity Strip (3 rows) ───────────────
            "liq"        : {
                # Row 1 — Central Bank Liquidity
                "fed_walcl_t"      : liq.get("fed_walcl_t"),
                "fed_walcl_wk_pct" : liq.get("fed_walcl_wk_pct"),
                "fed_walcl_date"   : liq.get("fed_walcl_date"),
                "fed_bs_text"      : fed_bs_text,
                "rrp_b"            : liq.get("rrp_b"),
                "rrp_date"         : liq.get("rrp_date"),
                "tga_b"            : liq.get("tga_b"),
                "tga_date"         : liq.get("tga_date"),
                "ecb_assets_t"     : liq.get("ecb_assets_t"),
                "ecb_assets_wk_pct": liq.get("ecb_assets_wk_pct"),
                "ecb_assets_date"  : liq.get("ecb_assets_date"),
                "ecb_bs_text"      : ecb_bs_text,
                "us_m2_yoy"        : liq.get("us_m2_yoy"),
                "us_m2_date"       : liq.get("us_m2_date"),
                "us_m2_text"       : us_m2_text,
                "eu_m3_yoy"        : liq.get("eu_m3_yoy"),
                "eu_m3_date"       : liq.get("eu_m3_date"),
                "eu_m3_text"       : eu_m3_text,
                "china_m2_yoy"     : liq.get("china_m2_yoy"),
                "china_m2_date"    : liq.get("china_m2_date"),
                "global_cb_trend"  : liq.get("global_cb_trend"),
                "hy_oas_us"        : liq.get("hy_oas_us"),
                "hy_oas_us_date"   : liq.get("hy_oas_us_date"),
                "hy_oas_us_text"   : hy_us_text,
                "hy_oas_eu"        : liq.get("hy_oas_eu"),
                "hy_oas_eu_date"   : liq.get("hy_oas_eu_date"),
                "hy_oas_eu_text"   : hy_eu_text,
                "hy_oas_em"        : liq.get("hy_oas_em"),
                "hy_oas_em_date"   : liq.get("hy_oas_em_date"),
                "hy_oas_em_text"   : hy_em_text,
                # Row 2 — Yield Curves
                "bund_10y"         : liq.get("bund_10y"),
                "bund_2y"          : liq.get("bund_2y"),
                "bund_spread"      : liq.get("bund_spread"),
                "bund_signal"      : liq.get("bund_signal"),
                "bund_date"        : liq.get("bund_date"),
                "jgb_10y"          : liq.get("jgb_10y"),
                "jgb_10y_date"     : liq.get("jgb_10y_date"),
                "jgb_2y"           : liq.get("jgb_2y"),
                "jgb_spread"       : liq.get("jgb_spread"),
                "jgb_signal"       : liq.get("jgb_signal"),
                "cgb_10y"          : liq.get("cgb_10y"),
                "cgb_2y"           : liq.get("cgb_2y"),
                "cgb_spread"       : liq.get("cgb_spread"),
                "cgb_signal"       : liq.get("cgb_signal"),
                "cgb_date"         : liq.get("cgb_date"),
                "cgb_text"         : cgb_text,
                "uk_10y"           : liq.get("uk_10y"),
                "uk_10y_date"      : liq.get("uk_10y_date"),
                # Row 3 — Real Rates & Inflation
                "us_tips_10y"      : liq.get("us_tips_10y"),
                "us_tips_date"     : liq.get("us_tips_date"),
                "us_tips_text"     : tips_text,
                "us_breakeven_10y" : liq.get("us_breakeven_10y"),
                "us_breakeven_date": liq.get("us_breakeven_date"),
                # Row 4 — Real Economy
                "copper_price"     : liq.get("copper_price"),
                "copper_gold_ratio": liq.get("copper_gold_ratio"),
                "copper_text"      : copper_text,
                "jpy_usd"          : liq.get("jpy_usd"),
                "jpy_text"         : jpy_text,
                # Row 5 — Valuation & Cross-Asset
                "cape_us"          : liq.get("cape_us"),
                "cape_date"        : liq.get("cape_date"),
                "cape_text"        : cape_text,
                "pe_eu"            : liq.get("pe_eu"),
                "pe_jp"            : liq.get("pe_jp"),
                "pe_em"            : liq.get("pe_em"),
                "gold_stocks"      : liq.get("gold_stocks"),
                "gold_text"        : gold_text,
                "cnh_usd"          : liq.get("cnh_usd"),
                "cnh_text"         : cnh_text,
                # Row 6 — Regional FX rates
                "eur_usd"          : eur_usd,
                "eur_text"         : eur_text,
                "aud_usd"          : aud_usd,
                "aud_text"         : aud_text,
                # Meta
                "ts"               : liq.get("ts"),
                "date"             : liq.get("date"),
            },
        },
    }
