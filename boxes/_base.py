"""
_base.py — Utilitaires partagés entre toutes les boxes.
Import : from boxes._base import get_fx_rate, fmt_currency, fmt_pct
"""

import sqlite3


def get_fx_rate(con: sqlite3.Connection, pair: str) -> float:
    """
    Retourne le dernier taux de change pour une paire (ex: 'USD_EUR').
    Retourne 1.0 si non trouvé (affichage USD par défaut).
    """
    row = con.execute(
        "SELECT rate FROM fx_rates WHERE pair = ? ORDER BY ts DESC LIMIT 1",
        (pair,),
    ).fetchone()
    return row[0] if row else 1.0


def get_fx_rates(con: sqlite3.Connection) -> dict[str, float]:
    """Retourne tous les taux FX disponibles : {pair: rate}."""
    rows = con.execute(
        "SELECT pair, rate FROM fx_rates ORDER BY ts DESC"
    ).fetchall()
    seen = {}
    for pair, rate in rows:
        if pair not in seen:
            seen[pair] = rate
    return seen


def convert(amount: float | None, currency: str, fx: dict[str, float]) -> float | None:
    """
    Convertit un montant USD vers la devise cible.
    Tout est stocké en USD — conversion à l'affichage uniquement.
    """
    if amount is None:
        return None
    if currency == "USD":
        return amount
    if currency == "EUR":
        return amount * fx.get("USD_EUR", 1.0)
    if currency == "HKD":
        return amount * fx.get("USD_HKD", 1.0)
    return amount


def fmt_pct(value: float | None, decimals: int = 2) -> str | None:
    """Formate un float en pourcentage lisible (ex: +2.34%)."""
    if value is None:
        return None
    return f"{value * 100:+.{decimals}f}%"


def fmt_number(value: float | None, decimals: int = 2) -> str | None:
    if value is None:
        return None
    return f"{value:,.{decimals}f}"
