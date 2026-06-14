"""Couche 1 — Ingestion EDGAR (.txt §3 Couche 1).

- submissions JSON  : data.sec.gov/submissions/CIK{xxx}.json
- companyfacts XBRL : data.sec.gov/api/xbrl/companyfacts/CIK{xxx}.json
- Rate limit 10 req/s, User-Agent obligatoire, cache SQLite idempotent par CIK+endpoint.
- Chaque fetch est loggé (URL, status, cache hit/miss).
"""
from __future__ import annotations
import json, sqlite3, time, logging, os
import requests

import config

log = logging.getLogger("sainhe.edgar")


class EdgarClient:
    def __init__(self, cache_path: str = config.CACHE_DB_PATH, offline_fixtures: dict | None = None):
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        self._db = sqlite3.connect(cache_path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS edgar_cache ("
            " key TEXT PRIMARY KEY, fetched_at REAL, payload TEXT)"
        )
        self._last_request_t = 0.0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": config.EDGAR_USER_AGENT})
        # offline_fixtures: {key -> dict} pour tests sans réseau
        self._fixtures = offline_fixtures or {}

    # ------------------------------------------------------------------ HTTP
    def _throttle(self):
        min_interval = 1.0 / config.EDGAR_RATE_LIMIT_PER_SEC
        elapsed = time.time() - self._last_request_t
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_t = time.time()

    def _get_json(self, url: str, key: str, max_age_days: float = 1.0) -> dict:
        # 1. fixtures (tests offline)
        if key in self._fixtures:
            log.info("FIXTURE hit %s", key)
            return self._fixtures[key]
        # 2. cache SQLite
        row = self._db.execute(
            "SELECT fetched_at, payload FROM edgar_cache WHERE key=?", (key,)
        ).fetchone()
        if row and (time.time() - row[0]) < max_age_days * 86400:
            log.info("CACHE hit %s", key)
            return json.loads(row[1])
        # 3. réseau
        self._throttle()
        log.info("FETCH %s", url)
        resp = self._session.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        self._db.execute(
            "INSERT OR REPLACE INTO edgar_cache (key, fetched_at, payload) VALUES (?,?,?)",
            (key, time.time(), json.dumps(data)),
        )
        self._db.commit()
        return data

    # ------------------------------------------------------------------ API publique
    def ticker_to_cik(self, ticker: str) -> int:
        data = self._get_json(config.EDGAR_TICKER_MAP_URL, "ticker_map",
                              max_age_days=config.EDGAR_CACHE_DAYS_TICKER_MAP)
        t = ticker.upper()
        for entry in data.values():
            if entry["ticker"].upper() == t:
                return int(entry["cik_str"])
        raise KeyError(f"Ticker {ticker} introuvable dans company_tickers.json")

    def submissions(self, cik: int) -> dict:
        url = config.EDGAR_BASE_SUBMISSIONS.format(cik=cik)
        return self._get_json(url, f"submissions:{cik}",
                              max_age_days=config.EDGAR_CACHE_DAYS_SUBMISSIONS)

    def companyfacts(self, cik: int) -> dict:
        url = config.EDGAR_BASE_COMPANYFACTS.format(cik=cik)
        return self._get_json(url, f"companyfacts:{cik}",
                              max_age_days=config.EDGAR_CACHE_DAYS_COMPANYFACTS)
