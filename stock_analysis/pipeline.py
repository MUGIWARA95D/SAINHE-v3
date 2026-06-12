"""Pipeline SAINHE — orchestrateur (Fetch → Compute → Render).

Usage prod (sur la machine de Hugo, réseau ouvert) :
    python pipeline.py AAPL MSFT KO JPM XOM
    python pipeline.py --portfolio          # les tickers de config

Chaque ticker produit output/json/{TICKER}_report.json ;
l'agrégat Niveau 1 sort dans output/json/valuation_map.json.

yfinance est optionnel : sans lui, prix/consensus = N/D, le reste tourne (EDGAR only).
"""
from __future__ import annotations
import sys, os, json, logging

import config
from edgar.edgar_client import EdgarClient
from edgar.xbrl_parser import parse_companyfacts
from edgar.metadata_flags import metadata_flags
from output import report_builder

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
log = logging.getLogger("sainhe.pipeline")

OUT_DIR = "output/json"


def _yf_data(ticker: str):
    """Prix courant + info + prix historiques annuels (pour le $1 test). Optionnel."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        hist = t.history(period="10y")["Close"]
        price_history = {}
        if len(hist):
            yearly = hist.groupby(hist.index.year).last()
            price_history = {int(y): float(p) for y, p in yearly.items()}
        return price, info, price_history
    except Exception as e:  # réseau absent, ticker inconnu, etc.
        log.warning("yfinance indisponible pour %s (%s) — prix/consensus = N/D", ticker, e)
        return None, None, None


def run_ticker(client: EdgarClient, ticker: str) -> dict:
    cik = client.ticker_to_cik(ticker)
    facts = client.companyfacts(cik)
    subs = client.submissions(cik)
    cd = parse_companyfacts(ticker, cik, facts)
    meta = metadata_flags(subs)
    meta["_submissions_raw"] = subs

    price, info, price_history = _yf_data(ticker)
    report = report_builder.build_report(
        cd, price=price, yf_info=info, edgar_meta=meta,
        gics_sector=(info or {}).get("sector"),
        price_history=price_history,
    )
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{ticker}_report.json")
    report_builder.save(report, path)
    log.info("OK %s -> %s", ticker, path)
    return report


def main(tickers: list[str]):
    client = EdgarClient()
    reports = []
    for t in tickers:
        try:
            reports.append(run_ticker(client, t))
        except Exception as e:
            log.error("ECHEC %s : %s", t, e)
    if reports:
        vmap = report_builder.build_valuation_map(reports)
        report_builder.save(vmap, os.path.join(OUT_DIR, "valuation_map.json"))
        log.info("valuation_map.json : %d tickers", len(vmap["rows"]))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args == ["--portfolio"]:
        args = config.TEST_TICKERS
    main(args)
