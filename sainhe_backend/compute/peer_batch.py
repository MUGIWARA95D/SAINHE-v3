"""BLOC F — Peer benchmarking branché (.txt §3 Couche 3, points 58-65).

Tourne sur l'univers complet (les 30 tickers SAINHE). Pour chaque ticker :
  - Groupe : même SIC + même market cap bucket (config.PEER_MARKET_CAP_BUCKETS)
  - Calcule multiples (P/E, EV/EBITDA, P/FCF, P/S), ROIC, ROE, Kd, spread ROIC-WACC
  - Quartiles du ticker dans son groupe (1=bas, 4=haut)
  - Dispersion relative analystes vs médiane peers
  - Rang du ticker sur le spread ROIC-WACC

Inputs : liste de bundles {cd, price, yf_info, sic, wacc, dispersion} déjà produits
par le pipeline. Output : dict ticker → bloc_F prêt à intégrer dans le JSON.
"""
from __future__ import annotations
import config, statistics
from edgar.xbrl_parser import CompanyData
from compute import metrics, valuation
from compute.external import dispersion_relative, market_cap_bucket


def _peer_metric_set(cd: CompanyData, price: float | None, market_cap: float | None,
                     wacc_value: float | None) -> dict:
    """Calcule les multiples nécessaires au benchmarking pour UN ticker."""
    fy = (cd.years("revenue") or [None])[-1]
    m = metrics.derive(cd, fy)
    ni = cd.value("net_income", fy)
    rev = cd.value("revenue", fy)
    ebitda = m.get("ebitda")
    fcf = m.get("fcf_adj")
    nd = m.get("net_debt") or 0.0
    ev = (market_cap + nd) if market_cap is not None else None
    roic = m.get("roic")
    spread = (roic - wacc_value) if (roic is not None and wacc_value is not None) else None
    return {
        "pe": (market_cap / ni) if (market_cap and ni and ni > 0) else None,
        "ev_ebitda": (ev / ebitda) if (ev and ebitda and ebitda > 0) else None,
        "p_fcf": (market_cap / fcf) if (market_cap and fcf and fcf > 0) else None,
        "p_s": (market_cap / rev) if (market_cap and rev) else None,
        "roic": roic,
        "roe": m.get("roe"),
        "spread_roic_wacc": spread,
        "kd": m.get("kd"),
    }


def _quartile(value: float | None, sorted_vals: list[float], higher_is_better: bool) -> int | None:
    """Quartile 1..4. higher_is_better=True : Q4 = meilleur (ex: ROIC).
    higher_is_better=False : Q4 = meilleur signifie Q4 = plus bas (ex: P/E low = cheap)."""
    if value is None or len(sorted_vals) < 3:
        return None
    below = sum(1 for v in sorted_vals if v <= value)
    raw_q = min(4, max(1, 1 + int(4 * below / (len(sorted_vals) + 1))))
    return raw_q if higher_is_better else (5 - raw_q)


# higher_is_better par métrique : valuations bas = bon, profitabilité haut = bon
HIGHER_IS_BETTER = {
    "pe": False, "ev_ebitda": False, "p_fcf": False, "p_s": False,
    "roic": True, "roe": True, "spread_roic_wacc": True, "kd": False,
}


def build_peer_blocks(bundles: list[dict]) -> dict[str, dict]:
    """bundles : [{ticker, cd, price, market_cap, wacc, sic, dispersion}].
    Retourne : ticker → bloc_F_peers complet."""
    # 1. Calculer les métriques de chacun
    for b in bundles:
        b["metrics"] = _peer_metric_set(b["cd"], b.get("price"),
                                         b.get("market_cap"), b.get("wacc"))
        b["mcap_bucket"] = market_cap_bucket(b.get("market_cap"))

    # 2. Grouper par (SIC, bucket)
    groups: dict[tuple, list[dict]] = {}
    for b in bundles:
        key = (b.get("sic"), b["mcap_bucket"])
        groups.setdefault(key, []).append(b)

    out: dict[str, dict] = {}
    for b in bundles:
        peers = [p for p in groups.get((b.get("sic"), b["mcap_bucket"]), []) if p is not b]
        peer_metrics = [p["metrics"] for p in peers]
        peer_tickers = [p["ticker"] for p in peers]

        # Quartiles par métrique
        quartiles = {}
        for key, higher_better in HIGHER_IS_BETTER.items():
            tv = b["metrics"].get(key)
            vals = sorted(p[key] for p in peer_metrics if p.get(key) is not None)
            quartiles[key] = {
                "value": tv,
                "quartile": _quartile(tv, vals, higher_better),
                "peer_median": statistics.median(vals) if vals else None,
                "n_peers": len(vals),
                "higher_is_better": higher_better,
            }

        # Rang spread ROIC-WACC (1 = meilleur)
        spread_vals = sorted(((p["metrics"].get("spread_roic_wacc"), p["ticker"])
                              for p in peers if p["metrics"].get("spread_roic_wacc") is not None),
                             reverse=True)
        my_spread = b["metrics"].get("spread_roic_wacc")
        spread_rank = None
        if my_spread is not None and spread_vals:
            spread_rank = 1 + sum(1 for v, _ in spread_vals if v > my_spread)

        # Kd vs pairs (objectif, lu dans les filings — zéro hypothèse)
        kd_vals = [pm.get("kd") for pm in peer_metrics if pm.get("kd") is not None]
        kd_block = {
            "ticker_kd": b["metrics"].get("kd"),
            "peer_median_kd": statistics.median(kd_vals) if kd_vals else None,
            "n_peers": len(kd_vals),
        }

        # Dispersion relative analystes (branchement final de la fonction qui dormait)
        peer_disps = [p.get("dispersion") for p in peers if p.get("dispersion") is not None]
        disp_rel = dispersion_relative(b.get("dispersion"), peer_disps)

        out[b["ticker"]] = {
            "peer_universe": {
                "sic": b.get("sic"),
                "market_cap_bucket": b["mcap_bucket"],
                "peer_tickers": peer_tickers,
                "n_peers": len(peers),
            },
            "quartiles": quartiles,
            "kd_vs_peers": kd_block,
            "spread_rank": {"rank": spread_rank, "of_total": len(peers) + 1,
                            "ticker_spread": my_spread},
            "dispersion_relative": disp_rel,
        }
    return out
