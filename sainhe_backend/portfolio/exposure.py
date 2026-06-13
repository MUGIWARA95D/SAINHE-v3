"""Expositions (.txt §4 points 29-30) — sector GICS, geographic HQ, currency.
Simple agrégation pondérée des metadata par holding.
"""
from __future__ import annotations


def sector_exposure(weights: dict[str, float], sector_map: dict[str, str]) -> dict:
    """Σ w_i par GICS sector (.txt point 29)."""
    out = {}
    for t, w in weights.items():
        s = sector_map.get(t, "Unknown")
        out[s] = out.get(s, 0.0) + w
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def geographic_exposure(weights: dict[str, float], geo_map: dict[str, str]) -> dict:
    """Σ w_i par HQ country/region (.txt point 30)."""
    out = {}
    for t, w in weights.items():
        g = geo_map.get(t, "Unknown")
        out[g] = out.get(g, 0.0) + w
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def currency_exposure(weights: dict[str, float], currency_map: dict[str, str]) -> dict:
    """Σ w_i par devise du listing (input pour la décomposition vol locale vs FX)."""
    out = {}
    for t, w in weights.items():
        c = currency_map.get(t, "USD")
        out[c] = out.get(c, 0.0) + w
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
