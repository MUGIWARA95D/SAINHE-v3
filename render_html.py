"""
render_html.py — Assemble les 6 boxes et génère les pages HTML via Jinja2.
Génère une version par langue : EN → output/, FR → output/fr/, etc.

Pages générées :
    output/index.html          → Dashboard (EN)
    output/fr/index.html       → Dashboard (FR)
    output/{lang}/index.html   → Dashboard (autres langues)
    (idem pour learn, contact, stock-analysis)

Lancement :
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

# ============================================================
#  I18N — chargement des fichiers de traduction
# ============================================================

LOCALES_DIR = Path(__file__).resolve().parent / "locales"

# Mapping langue → locale JS (pour toLocaleString)
LOCALE_JS = {
    "EN": "en-US",
    "FR": "fr-FR",
    "DE": "de-DE",
    "ES": "es-ES",
    "ZH": "zh-CN",
    "RU": "ru-RU",
    "JA": "ja-JP",
}

# Abréviations de mois par langue (pour les timestamps des boxes)
MONTH_ABBR = {
    "EN": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
    "FR": ["jan.","fév.","mars","avr.","mai","juin","juil.","août","sep.","oct.","nov.","déc."],
    "DE": ["Jan","Feb","Mär","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"],
    "ES": ["ene.","feb.","mar.","abr.","may.","jun.","jul.","ago.","sep.","oct.","nov.","dic."],
    "ZH": ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"],
    "RU": ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"],
    "JA": ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"],
}

def load_translations(lang: str) -> dict:
    """Charge le fichier locales/{lang}.json. Fallback vers EN si absent."""
    path = LOCALES_DIR / f"{lang.lower()}.json"
    if not path.exists():
        path = LOCALES_DIR / "en.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ============================================================
#  BOX AUTO-DÉCOUVERTE
# ============================================================

def load_boxes(con: sqlite3.Connection, lang: str, currency: str) -> list[dict]:
    """
    Charge chaque box active depuis BOX_REGISTRY.
    Importe dynamiquement boxes/<id>.py → appelle render(con, lang, currency).
    """
    boxes_out = []
    registry  = sorted([b for b in BOX_REGISTRY if b["actif"]], key=lambda b: b["ordre"])

    for box_cfg in registry:
        box_id = box_cfg["id"]
        try:
            module = importlib.import_module(f"boxes.{box_id}")
            result = module.render(con, lang=lang, currency=currency)
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
#  RENDER
# ============================================================

def _get_fx_rates(con: sqlite3.Connection) -> dict:
    """Retourne {USD:1.0, EUR:rate, HKD:rate} pour injection JS côté client."""
    rows = con.execute(
        "SELECT pair, rate FROM fx_rates ORDER BY ts DESC"
    ).fetchall()
    seen: dict[str, float] = {}
    for pair, rate in rows:
        if pair not in seen:
            seen[pair] = rate
    return {
        "USD": 1.0,
        "EUR": round(seen.get("USD_EUR", 0.9200), 6),
        "HKD": round(seen.get("USD_HKD", 7.8200), 6),
    }


def _box_timestamps(con: sqlite3.Connection, lang: str = "EN") -> dict:
    """Retourne le dernier timestamp de mise à jour pour chaque box (localisé)."""
    cur = con.cursor()
    months = MONTH_ABBR.get(lang, MONTH_ABBR["EN"])

    def q(sql):
        try:
            row = cur.execute(sql).fetchone()
            raw = row[0] if row else None
            if not raw:
                return "—"
            from datetime import datetime as _dt
            try:
                clean = raw[:19].replace("T", " ")
                d = _dt.strptime(clean, "%Y-%m-%d %H:%M:%S")
                m = months[d.month - 1]
                return f"{m} {d.day:02d}; {d:%H:%M}"
            except Exception:
                try:
                    d = _dt.strptime(raw[:10], "%Y-%m-%d")
                    m = months[d.month - 1]
                    return f"{m} {d.day:02d}"
                except Exception:
                    return raw[:10]
        except Exception:
            return "—"

    ts_snap  = q("SELECT MAX(ts_update) FROM snapshot")
    ts_news  = q("SELECT MAX(ts_fetch)  FROM news")
    ts_macro = q("SELECT MAX(ts)        FROM macro_bandeau")

    return {
        "box_01_macro"     : ts_macro,
        "box_02_indices"   : ts_snap,
        "box_03_news"      : ts_news,
        "box_04_sectors"   : ts_snap,
        "box_05_sentiment" : ts_snap,
        "box_06_portfolio" : ts_snap,
    }


# ============================================================
#  PAGE NAVIGATION — uses translations
# ============================================================

def build_page_navs(t: dict) -> dict:
    """Construit les liens de navigation par page à partir du dict de traductions."""
    return {
        "dashboard": [
            {"href": "#nav-macro",     "label": t.get("nav_macro",      "Macro")},
            {"href": "#nav-indices",   "label": t.get("nav_indices",    "Indices")},
            {"href": "#nav-news",      "label": t.get("nav_news",       "News")},
            {"href": "#nav-sectors",   "label": t.get("nav_sectors",    "Sectors")},
            {"href": "#nav-sentiment", "label": t.get("nav_sentiment",  "Sentiment")},
            {"href": "#nav-portfolio", "label": t.get("nav_portfolio",  "Portfolio")},
        ],
        "stock-analysis": [
            {"href": "#oracle",        "label": t.get("nav_the_oracle",    "The Oracle")},
            {"href": "#forge",         "label": t.get("nav_the_forge",     "The Forge")},
            {"href": "#discernement",  "label": t.get("nav_discernment",   "Discernment")},
            {"href": "#equilibre",     "label": t.get("nav_the_balance",   "The Balance")},
            {"href": "#marees",        "label": t.get("nav_the_tides",     "The Tides")},
            {"href": "#comparaison",   "label": t.get("nav_comparison",    "Comparison")},
        ],
        "learn": [
            {"href": "#learn-whyfinance",    "label": t.get("nav_why_finance",    "Why Finance")},
            {"href": "#learn-mindmap",       "label": t.get("nav_mindmap",        "Mindmap")},
            {"href": "#learn-dashboard",     "label": t.get("nav_dashboard",      "Dashboard")},
            {"href": "#learn-stockanalysis", "label": t.get("nav_stock_analysis", "Stock Analysis")},
        ],
        "contact": [
            {"href": "#contact-form", "label": t.get("nav_contact", "Get in Touch")},
        ],
    }


# Mapping page → nom de fichier HTML
PAGE_FILES = {
    "dashboard":      "index.html",
    "stock-analysis": "stock-analysis.html",
    "learn":          "learn.html",
    "contact":        "contact.html",
}


def build_lang_urls(current_page: str, languages: list) -> dict:
    """
    Retourne un dict {lang_code: url} pour le switcher de langue.
    EN → /index.html (racine), FR → /fr/index.html, etc.
    URLs root-relatives pour fonctionner avec python -m http.server et Cloudflare Pages.
    """
    filename = PAGE_FILES.get(current_page, "index.html")
    urls = {}
    for lang in languages:
        if lang == "EN":
            urls[lang] = f"/{filename}"
        else:
            urls[lang] = f"/{lang.lower()}/{filename}"
    return urls


# ============================================================
#  RENDER — une langue
# ============================================================

def render_lang(lang: str, currency: str, con: sqlite3.Connection,
                boxes_cache: dict, env: Environment):
    """Génère les 4 pages pour une langue donnée."""
    t          = load_translations(lang)
    i18n_json  = json.dumps(t, ensure_ascii=False)
    locale_js  = LOCALE_JS.get(lang, "en-US")
    page_navs  = build_page_navs(t)
    ts_map     = _box_timestamps(con, lang)
    ts_render  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Répertoire de sortie : EN → output/, autres → output/{lang}/
    if lang == DEFAULT_LANGUAGE:
        out_dir = OUTPUT_DIR
    else:
        out_dir = OUTPUT_DIR / lang.lower()
    out_dir.mkdir(parents=True, exist_ok=True)

    boxes       = boxes_cache
    boxes_by_id = {b["meta"]["id"]: b for b in boxes}
    def _data(box_id): return boxes_by_id.get(box_id, {}).get("data", {})
    def _meta(box_id): return boxes_by_id.get(box_id, {}).get("meta", {})

    # Contexte commun
    base_ctx = {
        "site_name"   : SITE_NAME,
        "site_slogan" : SITE_SLOGAN,
        "colors"      : COLORS,
        "lang"        : lang,
        "currency"    : currency,
        "languages"   : LANGUAGES,
        "currencies"  : CURRENCIES,
        "ts_render"   : ts_render,
        "fx_rates_js" : boxes_cache[0] if not isinstance(boxes_cache, list) else None,
        "t"           : t,
        "i18n_json"   : i18n_json,
        "locale_js"   : locale_js,
    }
    # fx_rates injecté séparément
    base_ctx.pop("fx_rates_js", None)

    # ── 1. Dashboard ────────────────────────────────────────
    lang_urls = build_lang_urls("dashboard", LANGUAGES)
    dashboard_ctx = {
        **base_ctx,
        "current_page" : "dashboard",
        "page_nav"     : page_navs["dashboard"],
        "lang_urls"    : lang_urls,
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
        "ts_sentiment" : ts_map["box_05_sentiment"],
        "ts_portfolio" : ts_map["box_06_portfolio"],
    }
    _render_page(env, "dashboard.html", out_dir / "index.html", dashboard_ctx)

    # ── 2. Stock Analysis ────────────────────────────────────
    _render_page(env, "stock-analysis.html", out_dir / "stock-analysis.html", {
        **base_ctx,
        "current_page" : "stock-analysis",
        "page_nav"     : page_navs["stock-analysis"],
        "lang_urls"    : build_lang_urls("stock-analysis", LANGUAGES),
    })

    # ── 3. Learn ─────────────────────────────────────────────
    _render_page(env, "learn.html", out_dir / "learn.html", {
        **base_ctx,
        "current_page" : "learn",
        "page_nav"     : page_navs["learn"],
        "lang_urls"    : build_lang_urls("learn", LANGUAGES),
    })

    # ── 4. Contact ───────────────────────────────────────────
    _render_page(env, "contact.html", out_dir / "contact.html", {
        **base_ctx,
        "current_page" : "contact",
        "page_nav"     : page_navs["contact"],
        "lang_urls"    : build_lang_urls("contact", LANGUAGES),
    })

    log.info("Langue %s → %s/ OK", lang, out_dir.name if lang != DEFAULT_LANGUAGE else "output")


def _render_page(env, template_name: str, out_path: Path, ctx: dict):
    """Render a single Jinja2 template and write to out_path."""
    template = env.get_template(template_name)
    html     = template.render(**ctx)
    out_path.write_text(html, encoding="utf-8")
    log.info("HTML généré : %s (%d octets)", out_path, len(html))


# ============================================================
#  RENDER — toutes les langues
# ============================================================

def render(lang: str = DEFAULT_LANGUAGE, currency: str = DEFAULT_CURRENCY):
    """
    Point d'entrée principal.
    Si lang == DEFAULT_LANGUAGE, génère toutes les langues.
    Sinon, génère seulement la langue demandée (pour les tests).
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

    con        = sqlite3.connect(DB_PATH)
    # Les boxes sont chargées une seule fois (même données pour toutes les langues)
    boxes      = load_boxes(con, DEFAULT_LANGUAGE, currency)
    fx_rates   = _get_fx_rates(con)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)

    # Injecter fx_rates dans le contexte global (pas dans les boxes)
    # On passe par une variable de module accessible dans les templates via base_ctx
    langs_to_render = LANGUAGES if lang == DEFAULT_LANGUAGE else [lang]

    for l in langs_to_render:
        # Recréer le contexte boxes avec fx_rates_js
        t_boxes = list(boxes)  # même référence
        # Passer fx_rates via une variable dédiée dans render_lang
        _render_lang_with_fx(l, currency, con, t_boxes, fx_rates, env)

    con.close()


def _render_lang_with_fx(lang: str, currency: str, con: sqlite3.Connection,
                         boxes: list, fx_rates_js: dict, env: Environment):
    """Génère les 4 pages pour une langue (avec fx_rates_js injecté)."""
    t          = load_translations(lang)
    i18n_json  = json.dumps(t, ensure_ascii=False)
    locale_js  = LOCALE_JS.get(lang, "en-US")
    page_navs  = build_page_navs(t)
    ts_map     = _box_timestamps(con, lang)
    ts_render  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if lang == DEFAULT_LANGUAGE:
        out_dir = OUTPUT_DIR
    else:
        out_dir = OUTPUT_DIR / lang.lower()
    out_dir.mkdir(parents=True, exist_ok=True)

    boxes_by_id = {b["meta"]["id"]: b for b in boxes}
    def _data(bid): return boxes_by_id.get(bid, {}).get("data", {})
    def _meta(bid): return boxes_by_id.get(bid, {}).get("meta", {})

    base_ctx = {
        "site_name"   : SITE_NAME,
        "site_slogan" : SITE_SLOGAN,
        "colors"      : COLORS,
        "lang"        : lang,
        "currency"    : currency,
        "languages"   : LANGUAGES,
        "currencies"  : CURRENCIES,
        "ts_render"   : ts_render,
        "fx_rates_js" : fx_rates_js,
        "t"           : t,
        "i18n_json"   : i18n_json,
        "locale_js"   : locale_js,
    }

    # ── 1. Dashboard ──────────────────────────────────────────
    _render_page(env, "dashboard.html", out_dir / "index.html", {
        **base_ctx,
        "current_page" : "dashboard",
        "page_nav"     : page_navs["dashboard"],
        "lang_urls"    : build_lang_urls("dashboard", LANGUAGES),
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

    # ── 2. Stock Analysis ─────────────────────────────────────
    _render_page(env, "stock-analysis.html", out_dir / "stock-analysis.html", {
        **base_ctx,
        "current_page" : "stock-analysis",
        "page_nav"     : page_navs["stock-analysis"],
        "lang_urls"    : build_lang_urls("stock-analysis", LANGUAGES),
    })

    # ── 3. Learn ──────────────────────────────────────────────
    _render_page(env, "learn.html", out_dir / "learn.html", {
        **base_ctx,
        "current_page" : "learn",
        "page_nav"     : page_navs["learn"],
        "lang_urls"    : build_lang_urls("learn", LANGUAGES),
    })

    # ── 4. Contact ────────────────────────────────────────────
    _render_page(env, "contact.html", out_dir / "contact.html", {
        **base_ctx,
        "current_page" : "contact",
        "page_nav"     : page_navs["contact"],
        "lang_urls"    : build_lang_urls("contact", LANGUAGES),
    })

    log.info("Langue %s → %s OK", lang, out_dir.name if lang != DEFAULT_LANGUAGE else "output/")


# ============================================================
#  MAIN
# ============================================================

if __name__ == "__main__":
    render()
