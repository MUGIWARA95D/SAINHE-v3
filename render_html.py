"""
render_html.py — Single EN build (static site) + agent-facing JSON data layer.

Generates:
  - 4 HTML pages (EN): index, stock-analysis, learn, contact
  - output/data/*.json   : machine-readable data layer for AI agents
  - output/data/index.json : discovery manifest
  - output/llms.txt      : agent entry point

Run:
    python render_html.py
"""

import json
import sqlite3
import importlib
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (
    DB_PATH,
    OUTPUT_DIR,
    TEMPLATE_DIR,
    BOX_REGISTRY,
    CURRENCIES,
    DEFAULT_CURRENCY,
    SITE_NAME,
    SITE_SLOGAN,
    COLORS,
)
import schema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [render] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


# ============================================================
#  BOX AUTO-DÉCOUVERTE
# ============================================================

def load_boxes(con: sqlite3.Connection, currency: str) -> list[dict]:
    boxes_out = []
    registry  = sorted([b for b in BOX_REGISTRY if b["actif"]], key=lambda b: b["ordre"])
    for box_cfg in registry:
        box_id = box_cfg["id"]
        try:
            module = importlib.import_module(f"boxes.{box_id}")
            result = module.render(con, lang="EN", currency=currency)
            result["largeur"] = box_cfg["largeur"]
            boxes_out.append(result)
            log.info("Box %s OK", box_id)
        except Exception as e:
            log.error("Box %s ERREUR : %s", box_id, e)
            boxes_out.append({
                "meta"   : {"id": box_id, "titre": box_id, "icone": "⚠️"},
                "data"   : {"error": str(e)},
                "largeur": box_cfg["largeur"],
            })
    return boxes_out


# ============================================================
#  HELPERS
# ============================================================

def _get_fx_rates(con: sqlite3.Connection) -> dict:
    """
    Retourne un dict {DEVISE: taux_USD} utilisé côté JS dans fxConvert.
    USD = 1.0 (base), EUR/HKD avec fallback hardcodé, autres paires dynamiquement.
    Structure : {"USD": 1.0, "EUR": 0.92, "HKD": 7.82, "JPY": 145.0, ...}
    """
    rows = con.execute("SELECT pair, rate FROM fx_rates ORDER BY ts DESC").fetchall()
    seen: dict[str, float] = {}
    for pair, rate in rows:
        if pair not in seen:
            seen[pair] = rate          # garde la valeur la plus récente par paire

    # Base toujours présente (USD = 1.0, EUR/HKD avec fallback si DB vide)
    result: dict[str, float] = {
        "USD": 1.0,
        "EUR": round(seen.get("USD_EUR", 0.9200), 6),
        "HKD": round(seen.get("USD_HKD", 7.8200), 6),
    }
    # Toutes les autres paires stockées (JPY, CHF, GBP, CNY, ILS, SAR…)
    for pair, rate in seen.items():
        if "_" in pair:
            target = pair.split("_")[1]   # "USD_JPY" → "JPY"
            if target not in result:
                result[target] = round(rate, 6)

    return result


def _box_timestamps(con: sqlite3.Connection) -> dict:
    cur = con.cursor()

    def q(sql):
        try:
            row = cur.execute(sql).fetchone()
            raw = row[0] if row else None
            if not raw:
                return "—"
            from datetime import datetime as _dt
            try:
                d = _dt.strptime(raw[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
                return f"{MONTH_ABBR[d.month-1]} {d.day:02d}; {d:%H:%M}"
            except Exception:
                try:
                    d = _dt.strptime(raw[:10], "%Y-%m-%d")
                    return f"{MONTH_ABBR[d.month-1]} {d.day:02d}"
                except Exception:
                    return raw[:10]
        except Exception:
            return "—"

    return {
        "box_01_macro"     : q("SELECT MAX(ts)        FROM macro_bandeau"),
        "box_02_indices"   : q("SELECT MAX(ts_update) FROM snapshot"),
        "box_03_news"      : q("SELECT MAX(ts_fetch)  FROM news"),
        "box_04_sectors"   : q("SELECT MAX(ts_update) FROM snapshot"),
        "box_05_sentiment" : q("SELECT MAX(ts_update) FROM snapshot"),
        "box_06_portfolio" : q("SELECT MAX(ts_update) FROM snapshot"),
    }


def build_page_navs() -> dict:
    """Nav links (href + EN label) per page."""
    return {
        "dashboard": [
            {"href": "#nav-macro",     "label": "Macro"},
            {"href": "#nav-indices",   "label": "Indices"},
            {"href": "#nav-news",      "label": "News"},
            {"href": "#nav-sectors",   "label": "Valuation"},
            {"href": "#nav-rotation",  "label": "Rotation"},
            {"href": "#nav-portfolio", "label": "Portfolio"},
        ],
        "stock-analysis": [
            {"href": "#oracle",       "label": "The Oracle"},
            {"href": "#forge",        "label": "The Forge"},
            {"href": "#discernement", "label": "Discernment"},
            {"href": "#equilibre",    "label": "The Balance"},
            {"href": "#marees",       "label": "The Tides"},
            {"href": "#comparaison",  "label": "Comparison"},
        ],
        "learn": [
            {"href": "#learn-whyfinance",  "label": "Why Finance"},
            {"href": "#learn-guidelines",  "label": "Guidelines"},
            {"href": "#learn-mindmap",     "label": "Mindmap"},
            {"href": "#learn-dashboard",   "label": "Dashboard"},
            {"href": "#learn-stockanalysis","label": "Stock Analysis"},
        ],
        "contact": [
            {"href": "#ct-about",   "label": "About"},
            {"href": "#ct-story",   "label": "Story"},
            {"href": "#ct-reach",   "label": "Reach"},
            {"href": "#ct-roadmap", "label": "Roadmap"},
        ],
    }


# ============================================================
#  DATA LAYER — agent-facing JSON (/data/*.json)
# ============================================================

def _dig(d: dict, path: tuple):
    """Safely walk a nested dict by a tuple path; return None if any hop missing."""
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _round_floats(obj):
    """Recursively round floats to kill float32 storage noise (99.01999664 -> 99.02).
    Magnitude-aware: 4 decimals for |x|>=1 (rates, indices, P/E), 6 for |x|<1
    (small ratios like ERP). bool is left untouched (it's an int subclass)."""
    if isinstance(obj, float):
        return round(obj, 4 if abs(obj) >= 1 else 6)
    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v) for v in obj]
    return obj


def _build_macro_dataset(macro_data: dict, ts_render: str) -> dict:
    """Rich per-field macro dataset: each metric carries value, unit, thresholds, regime."""
    fields = {}
    for m in schema.MACRO_METRICS:
        obj = {"value": _dig(macro_data, m["path"]), "unit": m["unit"]}
        if m.get("thresholds"):
            obj["thresholds"] = m["thresholds"]
        regime_path = schema.MACRO_REGIME_PATHS.get(m["key"])
        if regime_path:
            reg = _dig(macro_data, regime_path)
            if reg is not None:
                obj["regime"] = reg
        fields[m["key"]] = obj
    return {
        "dataset": "macro",
        "as_of":   macro_data.get("ts") or ts_render,
        "source":  schema.SOURCES["macro"],
        "data":    fields,
    }


def _envelope(name: str, box_data: dict, units: dict, ts_render: str) -> dict:
    """Collection dataset: flat records + a field→unit map (token-efficient)."""
    return {
        "dataset": name,
        "as_of":   ts_render,
        "source":  schema.SOURCES.get(name, ""),
        "units":   units,
        "data":    box_data,
    }


def write_data_layer(boxes_by_id: dict, ts_render: str) -> list[dict]:
    """
    Writes output/data/*.json + index.json manifest.
    Returns the manifest entries (for llms.txt / logging).
    """
    data_dir = OUTPUT_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    def _data(bid): return boxes_by_id.get(bid, {}).get("data", {})

    datasets = {
        "macro":     _build_macro_dataset(_data("box_01_macro"), ts_render),
        "indices":   _envelope("indices",   _data("box_02_indices"),   schema.INDICES_UNITS,   ts_render),
        "news":      _envelope("news",       _data("box_03_news"),      {},                     ts_render),
        "sectors":   _envelope("sectors",    _data("box_04_sectors"),   schema.SECTORS_UNITS,   ts_render),
        "sentiment": _envelope("sentiment",  _data("box_05_sentiment"), schema.SENTIMENT_UNITS, ts_render),
        "portfolio": _envelope("portfolio",  _data("box_06_portfolio"), schema.PORTFOLIO_UNITS, ts_render),
    }

    manifest_entries = []
    for name, payload in datasets.items():
        payload = _round_floats(payload)
        out = data_dir / f"{name}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest_entries.append({
            "dataset": name,
            "url":     f"/data/{name}.json",
            "as_of":   payload.get("as_of"),
            "source":  payload.get("source"),
        })
        log.info("Data → %s (%d octets)", out, out.stat().st_size)

    # Discovery manifest
    manifest = {
        "site":      SITE_NAME,
        "generated": ts_render,
        "datasets":  manifest_entries,
        "units_legend": {
            "index": "index level", "pct": "percent", "pct_points": "percentage points",
            "bps": "basis points", "ratio": "dimensionless ratio", "fx_per_usd": "units per 1 USD",
            "trillion_usd": "trillions USD", "trillion_eur": "trillions EUR",
            "billion_usd": "billions USD", "category": "categorical label",
            "native_ccy": "value in the instrument's native currency",
            "score_-1_to_1": "score from -1 to +1", "index_0_100": "index 0-100",
            "composite": "composite momentum score", "direction": "-1/0/+1",
            "shares": "number of shares (avg daily volume)",
        },
    }
    (data_dir / "index.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Data → %s/index.json (manifest, %d datasets)", data_dir, len(manifest_entries))

    # llms.txt — agent entry point
    lines = [
        f"# {SITE_NAME} — {SITE_SLOGAN}",
        "",
        "> Independent financial intelligence platform. Macro signals, global indices,",
        "> sector valuation, rotation heatmap, and a personal watchlist scan. All values in USD",
        "> unless a native_ccy unit is given.",
        "",
        "## Machine-readable data",
        "",
        f"All data is exposed as JSON. Start with the manifest: /data/index.json",
        "",
    ]
    for e in manifest_entries:
        lines.append(f"- [{e['dataset']}]({e['url']}): {e['source']}")
    lines += [
        "",
        "## Notes for agents",
        "",
        "- macro.json is rich per-field: each metric has value, unit, thresholds, regime.",
        "- Collection datasets (indices, sectors, rotation, portfolio) use a top-level",
        "  units map; records are flat. Missing values are null (never \"-\" or \"N/A\").",
        "- Dates are ISO 8601. Refresh cadence: news 5x/day, fx 2x/day, full pipeline nightly.",
        "",
        "## Signal thresholds — do not invent values; read from macro.json",
        "",
        "The exact live values are always in macro.json. The thresholds below define regimes:",
        "",
        "### VIX (CBOE Volatility Index) — unit: index level",
        "- < 12  : extreme complacency — tail risk structurally underpriced",
        "- 12–15 : complacency zone — implied vol below historical norm",
        "- 15–20 : normal range — orderly markets, no systemic stress",
        "- 20–30 : elevated fear — risk-off rotation developing",
        "- > 30  : panic zone — crisis consistent (GFC 2008 peak: 80, COVID 2020: 66)",
        "",
        "### ERP — Equity Risk Premium (unit: pct_points, e.g. 0.025 = 2.5%)",
        "  Formula: earnings yield (1/P·E S&P 500) minus US 10Y treasury yield",
        "- < 0%  : negative ERP — bonds outperform equities on risk-adjusted basis",
        "- 0–1%  : very expensive — near CAPM break-even (Damodaran threshold)",
        "- 1–2%  : modest premium — balanced allocation, no strong signal",
        "- > 2%  : attractive — historically above-average forward equity returns",
        "",
        "### Yield Curve (10Y − 3M spread, unit: pct_points)",
        "- ≥ +1.00 : steep — expansionary, low NY Fed recession probability",
        "- 0 to +1 : flat — ambiguous, no confirmed recession signal",
        "- −0.50 to 0 : partial inversion — caution; false positives exist (1998, 2019)",
        "- < −0.50 : full inversion — ~70% preceded recession (1970–2023), lead 6–24 months",
        "",
        "### HY OAS — High-Yield Option-Adjusted Spread (unit: bps)",
        "  US long-run average ~525bps; EM long-run average ~600bps",
        "- < 260 bps : extreme compression — approaching pre-GFC lows (mid-2007 ~240bps)",
        "- < 350 bps : tight — comparable to 2006–07, 2021 troughs; underpriced credit risk",
        "- 350–500 bps : orderly — no systemic stress per Fed FSR framework",
        "- 500–700 bps : stress — Fed FSR 'elevated vulnerability'",
        "- > 700 bps : crisis — GFC peak 2000bps (2008), COVID 1100bps (2020)",
        "",
        "### CAPE — Shiller/Yale Cyclically Adjusted P/E (unit: ratio)",
        "  Long-run mean: 17 (1881–present)",
        "- ≤ 20  : near mean — forward 10Y real returns historically 8–10%",
        "- 20–25 : modest premium — forward 10Y real returns 4–7%",
        "- 25–34 : elevated — forward 10Y real returns compressed 0–4%",
        "- > 34  : extreme — comparable to 1929 (33) and dot-com 2000 (44)",
        "",
        "### Portfolio signals (box_06)",
        "  BUY   : ret_3m > +5%  AND price > DMA200  AND OBV not distributing",
        "  AVOID : ret_3m < −5%  OR  (price < DMA200 AND OBV distributing)",
        "  WATCH : all other cases",
        "  MFI   : Money Flow Index (0–100); overbought > 60, oversold < 40",
        "  RVOL  : Relative Volume vs 90-day avg; highlighted in gold when > 1.20",
        "  OBV   : On-Balance Volume trend — accumulating / distributing / neutral",
        "",
    ]
    (OUTPUT_DIR / "llms.txt").write_text("\n".join(lines), encoding="utf-8")
    log.info("llms.txt written")

    # robots.txt — allow all crawlers, point AI agents to llms.txt
    robots = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "# AI agent entry point\n"
        "# Machine-readable data catalogue: /data/index.json\n"
        "# Signal thresholds and interpretation: /llms.txt\n"
    )
    (OUTPUT_DIR / "robots.txt").write_text(robots, encoding="utf-8")
    log.info("robots.txt written")

    return manifest_entries


# ============================================================
#  RENDER
# ============================================================

def _render_page(env: Environment, template_name: str, out_path: Path, ctx: dict):
    template = env.get_template(template_name)
    html     = template.render(**ctx)
    out_path.write_text(html, encoding="utf-8")
    log.info("HTML généré : %s (%d octets)", out_path, len(html))


def render(currency: str = DEFAULT_CURRENCY):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Write _headers (Cloudflare Pages cache policy) ───────
    headers_content = (
        "/*.html\n"
        "  Cache-Control: no-cache, must-revalidate\n\n"
        "/data/*.json\n"
        "  Cache-Control: no-cache, must-revalidate\n"
    )
    (OUTPUT_DIR / "_headers").write_text(headers_content, encoding="utf-8")
    log.info("_headers written")

    con       = sqlite3.connect(DB_PATH, timeout=30)
    boxes     = load_boxes(con, currency)
    fx_rates  = _get_fx_rates(con)
    ts_map    = _box_timestamps(con)
    ts_render = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    page_navs = build_page_navs()

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)

    boxes_by_id = {b["meta"]["id"]: b for b in boxes}
    def _data(bid): return boxes_by_id.get(bid, {}).get("data", {})
    def _meta(bid): return boxes_by_id.get(bid, {}).get("meta", {})

    # ── Agent-facing JSON data layer (/data/*.json + llms.txt) ──
    write_data_layer(boxes_by_id, ts_render)

    # Shared base context (EN-only build)
    base_ctx = {
        "site_name"   : SITE_NAME,
        "site_slogan" : SITE_SLOGAN,
        "colors"      : COLORS,
        "lang"        : "en",
        "currency"    : currency,
        "currencies"  : CURRENCIES,
        "ts_render"   : ts_render,
        "fx_rates_js" : fx_rates,
    }

    # ── 1. Dashboard ────────────────────────────────────────
    _render_page(env, "dashboard.html", OUTPUT_DIR / "index.html", {
        **base_ctx,
        "current_page"    : "dashboard",
        "page_title"      : f"{SITE_NAME} — {SITE_SLOGAN}",
        "page_description": "Live macro signals, global indices, sector rotation, sentiment and portfolio scan. VIX, ERP, yield curve, HY OAS, CAPE and more.",
        "page_nav"     : page_navs["dashboard"],
        "boxes"        : boxes,
        "box_macro"           : _data("box_01_macro"),
        "box_macro_meta"      : _meta("box_01_macro"),
        "box_indices"         : _data("box_02_indices"),
        "box_indices_meta"    : _meta("box_02_indices"),
        "box_news"            : _data("box_03_news"),
        "box_news_meta"       : _meta("box_03_news"),
        "box_sectors"         : _data("box_04_sectors"),
        "box_sectors_meta"    : _meta("box_04_sectors"),
        "box_sentiment"       : _data("box_05_sentiment"),
        "box_sentiment_meta"  : _meta("box_05_sentiment"),
        "box_portfolio"       : _data("box_06_portfolio"),
        "box_portfolio_meta"  : _meta("box_06_portfolio"),
        "ts_macro"     : ts_map["box_01_macro"],
        "ts_indices"   : ts_map["box_02_indices"],
        "ts_news"      : ts_map["box_03_news"],
        "ts_sectors"   : ts_map["box_04_sectors"],
        "ts_sentiment" : ts_map.get("box_05_sentiment", "—"),
        "ts_portfolio" : ts_map["box_06_portfolio"],
    })

    # ── 2. Stock Analysis ────────────────────────────────────
    _render_page(env, "stock-analysis.html", OUTPUT_DIR / "stock-analysis.html", {
        **base_ctx,
        "current_page"    : "stock-analysis",
        "page_nav"        : page_navs["stock-analysis"],
        "page_title"      : f"Stock Analysis — {SITE_NAME}",
        "page_description": "Deep-dive stock analysis: fundamentals, technicals, and valuation context.",
    })

    # ── 3. Learn ─────────────────────────────────────────────
    _render_page(env, "learn.html", OUTPUT_DIR / "learn.html", {
        **base_ctx,
        "current_page"    : "learn",
        "page_nav"        : page_navs["learn"],
        "page_title"      : f"Learn — {SITE_NAME}",
        "page_description": "How to read the dashboard: signal thresholds, column definitions, and interpretation guides for all 6 data boxes.",
    })

    # ── 4. Contact ───────────────────────────────────────────
    _render_page(env, "contact.html", OUTPUT_DIR / "contact.html", {
        **base_ctx,
        "current_page"    : "contact",
        "page_nav"        : page_navs["contact"],
        "page_title"      : f"Contact — {SITE_NAME}",
        "page_description": f"Contact {SITE_NAME} — feedback, data corrections, and partnership inquiries.",
    })

    con.close()
    log.info("Render complet — 4 pages (EN) + data layer (6 datasets + manifest)")


# ============================================================
#  MAIN
# ============================================================

if __name__ == "__main__":
    render()
