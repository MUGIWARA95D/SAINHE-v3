"""Flags metadata EDGAR (.txt SCORES DE RISQUE — 4 signaux binaires).

Tirés du submissions JSON, zéro token :
  - NT 10-K / NT 10-Q déposé              → incapacité à filer à temps
  - 10-K/A ou 10-Q/A sur 2 dernières années → restatement
  - going concern : tag XBRL (lu en Couche 2, combiné ici)
  - GoodwillImpairmentLoss > 0 (lu en Couche 2, combiné ici)
"""
from __future__ import annotations
from datetime import datetime, timedelta


def metadata_flags(submissions_json: dict, lookback_years: int = 2) -> dict:
    recent = submissions_json.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    cutoff = (datetime.now() - timedelta(days=365 * lookback_years)).strftime("%Y-%m-%d")

    nt_filed, amendments = [], []
    for form, date in zip(forms, dates):
        if date < cutoff:
            continue
        if form in ("NT 10-K", "NT 10-Q"):
            nt_filed.append({"form": form, "date": date})
        if form in ("10-K/A", "10-Q/A"):
            amendments.append({"form": form, "date": date})

    return {
        "nt_filing": {"triggered": bool(nt_filed), "details": nt_filed},
        "restatement_2y": {"triggered": bool(amendments), "details": amendments},
    }
