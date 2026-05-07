"""
render_html.py — Single EN build. Translations handled client-side via localStorage.

Génère 4 pages HTML (EN) + copie locales/*.json → output/locales/
Les traductions sont chargées côté client au runtime (voir _head.html i18n system).

Lancement :
    python render_html.py
"""

import json
import shutil
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
    LANGUAGES,
    DEFAULT_LANGUAGE,
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

LOCALES_DIR = Path(__file__).resolve().parent / "locales"

MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


# ============================================================
#  TRANSLATIONS — EN only (JS handles all other languages)
# ============================================================

def load_translations() -> dict:
    """Charge locales/en.json."""
    path = LOCALES_DIR / "en.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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
    rows = con.execute("SELECT pair, rate FROM fx_rates ORDER BY ts DESC").fetchall()
    seen: dict[str, float] = {}
    for pair, rate in rows:
        if pair not in seen:
            seen[pair] = rate
    return {
        "USD": 1.0,
        "EUR": round(seen.get("USD_EUR", 0.9200), 6),
        "HKD": round(seen.get("USD_HKD", 7.8200), 6),
    }


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


def build_page_navs(t: dict) -> dict:
    """Nav links with i18n key + EN label fallback."""
    return {
        "dashboard": [
            {"href": "#nav-macro",     "key": "nav_macro",      "label": t.get("nav_macro",      "Macro")},
            {"href": "#nav-indices",   "key": "nav_indices",    "label": t.get("nav_indices",    "Indices")},
            {"href": "#nav-news",      "key": "nav_news",       "label": t.get("nav_news",       "News")},
            {"href": "#nav-sectors",   "key": "nav_sectors",    "label": t.get("nav_sectors",    "Sectors")},
            {"href": "#nav-sentiment", "key": "nav_sentiment",  "label": t.get("nav_sentiment",  "Sentiment")},
            {"href": "#nav-portfolio", "key": "nav_portfolio",  "label": t.get("nav_portfolio",  "Portfolio")},
        ],
        "stock-analysis": [
            {"href": "#oracle",        "key": "nav_the_oracle",    "label": t.get("nav_the_oracle",    "The Oracle")},
            {"href": "#forge",         "key": "nav_the_forge",     "label": t.get("nav_the_forge",     "The Forge")},
            {"href": "#discernement",  "key": "nav_discernment",   "label": t.get("nav_discernment",   "Discernment")},
            {"href": "#equilibre",     "key": "nav_the_balance",   "label": t.get("nav_the_balance",   "The Balance")},
            {"href": "#marees",        "key": "nav_the_tides",     "label": t.get("nav_the_tides",     "The Tides")},
            {"href": "#comparaison",   "key": "nav_comparison",    "label": t.get("nav_comparison",    "Comparison")},
        ],
        "learn": [
            {"href": "#learn-whyfinance",    "key": "nav_why_finance",    "label": t.get("nav_why_finance",    "Why Finance")},
            {"href": "#learn-mindmap",       "key": "nav_mindmap",        "label": t.get("nav_mindmap",        "Mindmap")},
            {"href": "#learn-dashboard",     "key": "nav_dashboard",      "label": t.get("nav_dashboard",      "Dashboard")},
            {"href": "#learn-stockanalysis", "key": "nav_stock_analysis", "label": t.get("nav_stock_analysis", "Stock Analysis")},
        ],
        "contact": [
            {"href": "#contact-form", "key": "nav_contact", "label": t.get("nav_contact", "Get in Touch")},
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

    # ── Copy locales → output/locales/ ──────────────────────
    out_locales = OUTPUT_DIR / "locales"
    out_locales.mkdir(exist_ok=True)
    locale_files = list(LOCALES_DIR.glob("*.json"))
    for f in locale_files:
        shutil.copy2(f, out_locales / f.name)
    log.info("Locales → output/locales/ (%d fichiers)", len(locale_files))

    con       = sqlite3.connect(DB_PATH)
    t         = load_translations()
    boxes     = load_boxes(con, currency)
    fx_rates  = _get_fx_rates(con)
    ts_map    = _box_timestamps(con)
    ts_render = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    page_navs = build_page_navs(t)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)

    boxes_by_id = {b["meta"]["id"]: b for b in boxes}
    def _data(bid): return boxes_by_id.get(bid, {}).get("data", {})
    def _meta(bid): return boxes_by_id.get(bid, {}).get("meta", {})

    # Shared context (no i18n_json / locale_js / lang_urls — client-side now)
    base_ctx = {
        "site_name"   : SITE_NAME,
        "site_slogan" : SITE_SLOGAN,
        "colors"      : COLORS,
        "lang"        : "en",
        "currency"    : currency,
        "languages"   : LANGUAGES,
        "currencies"  : CURRENCIES,
        "ts_render"   : ts_render,
        "fx_rates_js" : fx_rates,
        "t"           : t,
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
    log.info("Render complet — 4 pages EN + %d locales", len(locale_files))


# ============================================================
#  MAIN
# ============================================================

if __name__ == "__main__":
    render()
