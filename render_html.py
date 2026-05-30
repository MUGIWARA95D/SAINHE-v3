"""
render_html.py — Single EN build. Translations handled client-side via localStorage.

Génère 4 pages HTML (EN) + copie locales/*.json → output/locales/
Les traductions sont chargées côté client au runtime (voir _head.html i18n system).

Lancement :
    python render_html.py
"""

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
            {"href": "#nav-sectors",   "label": "Sectors"},
            {"href": "#nav-sentiment", "label": "Sentiment"},
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
            {"href": "#learn-whyfinance",    "label": "Why Finance"},
            {"href": "#learn-mindmap",       "label": "Mindmap"},
            {"href": "#learn-dashboard",     "label": "Dashboard"},
            {"href": "#learn-stockanalysis", "label": "Stock Analysis"},
        ],
        "contact": [
            {"href": "#contact-form", "label": "Get in Touch"},
        ],
    }


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
        "current_page" : "dashboard",
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
        "current_page" : "stock-analysis",
        "page_nav"     : page_navs["stock-analysis"],
    })

    # ── 3. Learn ─────────────────────────────────────────────
    _render_page(env, "learn.html", OUTPUT_DIR / "learn.html", {
        **base_ctx,
        "current_page" : "learn",
        "page_nav"     : page_navs["learn"],
    })

    # ── 4. Contact ───────────────────────────────────────────
    _render_page(env, "contact.html", OUTPUT_DIR / "contact.html", {
        **base_ctx,
        "current_page" : "contact",
        "page_nav"     : page_navs["contact"],
    })

    con.close()
    log.info("Render complet — 4 pages (EN)")


# ============================================================
#  MAIN
# ============================================================

if __name__ == "__main__":
    render()
