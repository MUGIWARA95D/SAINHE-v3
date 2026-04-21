"""
render_html.py — Assemble les 6 boxes et génère output/index.html via Jinja2.
Auto-découverte des boxes depuis BOX_REGISTRY (config.py).
Zéro calcul ici — tout vient des snapshots pré-calculés en DB.

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
#  BOX AUTO-DÉCOUVERTE
# ============================================================

def load_boxes(con: sqlite3.Connection, lang: str, currency: str) -> list[dict]:
    """
    Charge chaque box active depuis BOX_REGISTRY.
    Importe dynamiquement boxes/<id>.py → appelle render(con, lang, currency).
    Retourne une liste de dicts {meta, data} triée par ordre.
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
            # Box en erreur → placeholder vide (ne bloque pas le rendu)
            boxes_out.append({
                "meta"   : {"id": box_id, "titre": box_id, "icone": "⚠️"},
                "data"   : {"error": str(e)},
                "largeur": box_cfg["largeur"],
            })

    return boxes_out


# ============================================================
#  RENDER
# ============================================================

def _box_timestamps(con: sqlite3.Connection) -> dict:
    """Retourne le dernier timestamp de mise à jour pour chaque box."""
    cur = con.cursor()
    def q(sql):
        try:
            row = cur.execute(sql).fetchone()
            raw = row[0] if row else None
            if not raw:
                return "—"
            # Normalise ISO → "Apr 05; 08:41"
            from datetime import datetime as _dt
            try:
                clean = raw[:19].replace("T", " ")
                d = _dt.strptime(clean, "%Y-%m-%d %H:%M:%S")
                return d.strftime("%b %d; %H:%M")
            except Exception:
                try:
                    d = _dt.strptime(raw[:10], "%Y-%m-%d")
                    return d.strftime("%b %d")
                except Exception:
                    return raw[:10]
        except Exception:
            return "—"

    ts_snap  = q("SELECT MAX(ts_update) FROM snapshot")
    ts_news  = q("SELECT MAX(ts_fetch)  FROM news")
    ts_macro = q("SELECT MAX(ts)        FROM macro_bandeau")

    return {
        "box_01_news"      : ts_news,
        "box_02_indices"   : ts_snap,
        "box_03_sectors"   : ts_snap,
        "box_04_sentiment" : ts_snap,
        "box_05_macro"     : ts_macro,
        "box_06_portfolio" : ts_snap,
    }


def render(lang: str = DEFAULT_LANGUAGE, currency: str = DEFAULT_CURRENCY):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

    con   = sqlite3.connect(DB_PATH)
    boxes = load_boxes(con, lang, currency)
    ts_map = _box_timestamps(con)
    con.close()

    # Index par id pour accès direct dans le template
    boxes_by_id = {b["meta"]["id"]: b for b in boxes}
    def _data(box_id):  return boxes_by_id.get(box_id, {}).get("data", {})
    def _meta(box_id):  return boxes_by_id.get(box_id, {}).get("meta", {})

    # Contexte Jinja2
    ctx = {
        "site_name"   : SITE_NAME,
        "site_slogan" : SITE_SLOGAN,
        "colors"      : COLORS,
        "lang"        : lang,
        "currency"    : currency,
        "languages"   : LANGUAGES,
        "currencies"  : CURRENCIES,
        "boxes"       : boxes,
        "ts_render"   : datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        # ── Données par box (accès direct dans les partials) ──
        "box_news"            : _data("box_01_news"),
        "box_news_meta"       : _meta("box_01_news"),
        "box_indices"         : _data("box_02_indices"),
        "box_indices_meta"    : _meta("box_02_indices"),
        "box_sectors"         : _data("box_03_sectors"),
        "box_sectors_meta"    : _meta("box_03_sectors"),
        "box_sentiment"       : _data("box_04_sentiment"),
        "box_sentiment_meta"  : _meta("box_04_sentiment"),
        "box_macro"           : _data("box_05_macro"),
        "box_macro_meta"      : _meta("box_05_macro"),
        "box_portfolio"       : _data("box_06_portfolio"),
        "box_portfolio_meta"  : _meta("box_06_portfolio"),
        # ── Timestamps de dernière mise à jour par box ──
        "ts_news"      : ts_map["box_01_news"],
        "ts_indices"   : ts_map["box_02_indices"],
        "ts_sectors"   : ts_map["box_03_sectors"],
        "ts_sentiment" : ts_map["box_04_sentiment"],
        "ts_macro"     : ts_map["box_05_macro"],
        "ts_portfolio" : ts_map["box_06_portfolio"],
    }

    env      = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("dashboard.html")
    html     = template.render(**ctx)

    out_path = OUTPUT_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    log.info("HTML généré : %s (%d octets)", out_path, len(html))


# ============================================================
#  MAIN
# ============================================================

if __name__ == "__main__":
    render()
