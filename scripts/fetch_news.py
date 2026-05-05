"""
fetch_news.py — Scrape les flux RSS et stocke dans news (dédupliqué par hash MD5).
Reuters (#1) toujours inclus. Les autres sources tournent selon RSS_ROTATION.
Purge automatique des articles > NEWS_RETENTION_DAYS.

Lancement :
    python scripts/fetch_news.py
"""

import hashlib
import sqlite3
import sys
import time
import logging
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import feedparser
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    DB_PATH,
    RSS_SOURCES,
    RSS_ROTATION,
    NEWS_RETENTION_DAYS,
    CACHE_NEWS,
)

# ============================================================
#  CONFIG
# ============================================================

TIMEOUT      = 15    # secondes par requête RSS
SLEEP_SOURCE = 1.5   # secondes entre sources
MAX_ARTICLES = 30    # articles max par source (limite mémoire)
MAX_RETRIES  = 2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SAINHEbot/1.0; +https://sainhe.com)"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [fetch_news] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ============================================================
#  ROTATION — sources actives à l'heure courante
# ============================================================

def active_sources(hour: int | None = None) -> list[int]:
    """
    Retourne tous les IDs sources — toutes les régions à chaque run.
    La rotation horaire est désactivée : on a besoin de USA/EU/ASIE à tout moment
    pour que les tabs de la dashboard news soient toujours peuplés.
    """
    return sorted(RSS_SOURCES.keys())


# ============================================================
#  PARSING RSS
# ============================================================

def _parse_date(entry) -> str | None:
    """Tente d'extraire une date ISO 8601 depuis un entry feedparser."""
    for field in ("published", "updated", "created"):
        raw = entry.get(field)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass
    return None


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def fetch_feed(source_id: int) -> list[dict]:
    """
    Fetch + parse un flux RSS. Retourne une liste d'articles normalisés.
    """
    src  = RSS_SOURCES[source_id]
    url  = src["url"]
    region = src["region"]
    lang   = src["lang"]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except requests.exceptions.RequestException as e:
            log.warning("Source %d — réseau : %s (tentative %d)", source_id, e, attempt)
            if attempt < MAX_RETRIES:
                time.sleep(SLEEP_SOURCE)
            continue
        except Exception as e:
            log.warning("Source %d — parse : %s (tentative %d)", source_id, e, attempt)
            if attempt < MAX_RETRIES:
                time.sleep(SLEEP_SOURCE)
            continue

        articles = []
        for entry in feed.entries[:MAX_ARTICLES]:
            titre = (entry.get("title") or "").strip()
            if not titre:
                continue

            lien   = entry.get("link", "").strip()
            resume = (entry.get("summary") or entry.get("description") or "").strip()
            # Tronque le résumé à 500 chars pour éviter de stocker du HTML long
            if len(resume) > 500:
                resume = resume[:497] + "…"

            articles.append({
                "hash"      : _md5(titre),
                "source_id" : source_id,
                "region"    : region,
                "lang"      : lang,
                "titre"     : titre,
                "lien"      : lien,
                "resume"    : resume,
                "ts_pub"    : _parse_date(entry),
                "ts_fetch"  : datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        log.info("Source %d (%s) — %d articles parsés", source_id, region, len(articles))
        return articles

    log.error("Source %d — abandon après %d tentatives.", source_id, MAX_RETRIES)
    return []


# ============================================================
#  INSERT + PURGE
# ============================================================

def insert_articles(con: sqlite3.Connection, articles: list[dict]) -> int:
    """INSERT OR IGNORE — dédupliqué par hash MD5. Retourne le nb inséré."""
    if not articles:
        return 0

    cur = con.cursor()
    cur.executemany(
        """
        INSERT OR IGNORE INTO news
            (hash, source_id, region, lang, titre, lien, resume, ts_pub, ts_fetch)
        VALUES
            (:hash, :source_id, :region, :lang, :titre, :lien, :resume, :ts_pub, :ts_fetch)
        """,
        articles,
    )
    con.commit()
    return cur.rowcount


def purge_old_news(con: sqlite3.Connection):
    """Supprime les articles plus vieux que NEWS_RETENTION_DAYS."""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=NEWS_RETENTION_DAYS)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    cur = con.cursor()
    cur.execute("DELETE FROM news WHERE ts_fetch < ?", (cutoff,))
    deleted = cur.rowcount
    con.commit()

    if deleted:
        log.info("Purge — %d articles supprimés (> %d jours)", deleted, NEWS_RETENTION_DAYS)


# ============================================================
#  MAIN
# ============================================================

def main():
    hour      = datetime.now(timezone.utc).hour
    src_ids   = active_sources(hour)
    log.info("Heure UTC=%dh — sources actives : %s", hour, src_ids)

    con           = sqlite3.connect(DB_PATH)
    total_fetched = 0
    total_new     = 0

    for i, src_id in enumerate(src_ids):
        if i > 0:
            time.sleep(SLEEP_SOURCE)

        articles = fetch_feed(src_id)
        total_fetched += len(articles)

        n = insert_articles(con, articles)
        total_new += n
        log.info("Source %d — %d nouveaux sur %d", src_id, n, len(articles))

    purge_old_news(con)
    con.close()

    log.info(
        "Terminé — %d articles fetchés, %d nouveaux insérés.",
        total_fetched, total_new,
    )


if __name__ == "__main__":
    main()
