"""ASSEMBLEUR PORTFOLIO + CROISEMENT (.txt §4 + conv 'la boucle complète').

Sort portfolio_report.json structuré en 4 blocs (Performance → Risque → HRP → Simulation)
+ la TABLE CROISÉE par holding qui joint :
  poids | return contrib | beta contrib | cluster HRP | EPV vs prix | n_flags | score
C'est le différenciateur du plan : aucune banque privée ne croise fondamental et risque
portefeuille dans une seule vue.
"""
from __future__ import annotations
import json, datetime
import numpy as np
import pandas as pd

from portfolio import returns as ret_mod
from portfolio import risk as risk_mod
from portfolio import beta as beta_mod
from portfolio import hrp as hrp_mod
from portfolio import montecarlo as mc_mod
from portfolio import stress as stress_mod
from portfolio import exposure as exp_mod


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    s = sum(weights.values())
    return {t: w / s for t, w in weights.items()} if s else weights


def build_portfolio_report(
    prices: pd.DataFrame,                          # index=date, columns=tickers (devise réf)
    weights: dict[str, float],
    benchmarks: pd.DataFrame,                       # columns: 'SPY', 'ACWI'
    rf_annual: float,
    per_ticker_yield: dict[str, float] | None = None,
    sector_map: dict[str, str] | None = None,
    geo_map: dict[str, str] | None = None,
    currency_map: dict[str, str] | None = None,
    reference_currency: str = "USD",
    local_returns: pd.DataFrame | None = None,
    fx_returns: pd.DataFrame | None = None,
    benchmark_weights_spy: dict[str, float] | None = None,
    benchmark_weights_acwi: dict[str, float] | None = None,
    stock_analysis_reports: dict[str, dict] | None = None,    # ticker → report JSON
    n_mc_sims: int = 10_000,
    portfolio_currency: str = "USD",
) -> dict:
    """Assemble le JSON final 4 blocs + table croisée."""
    weights = _normalize_weights({t: w for t, w in weights.items() if t in prices.columns})

    # ---------------------------------------------------- BLOC 1 Performance
    spy = benchmarks["SPY"] if "SPY" in benchmarks else benchmarks.iloc[:, 0]
    bloc1 = {
        "returns_absolus": {
            **ret_mod.total_returns(prices, weights),
            "calendar_year_returns": ret_mod.calendar_year_returns(prices, weights),
            "aggregate_dividend_yield": (ret_mod.aggregate_dividend_yield(
                weights, per_ticker_yield or {}) if per_ticker_yield else None),
        },
        "cumulative_curves": ret_mod.cumulative_curves(prices, weights, benchmarks),
        "rolling_metrics": ret_mod.rolling_metrics(prices, weights, rf_annual),
        "attribution": ret_mod.attribution(prices, weights, sector_map, geo_map),
        "risk_adjusted_ratios": {
            "sharpe": ret_mod.sharpe(prices, weights, rf_annual),
            "sortino": ret_mod.sortino(prices, weights, rf_annual),
            "calmar": ret_mod.calmar(prices, weights),
            "rf_used": rf_annual,
            "rf_note": "3M T-bill réel (.txt §4 — PAS zéro)",
        },
        "returns_vs_benchmark_spy": ret_mod.jensen_alpha_tracking_ir(
            prices, weights, spy, rf_annual),
        "returns_vs_benchmark_acwi": (ret_mod.jensen_alpha_tracking_ir(
            prices, weights, benchmarks["ACWI"], rf_annual)
            if "ACWI" in benchmarks else None),
    }

    # ---------------------------------------------------- BLOC 2 Risque
    var_block = risk_mod.value_at_risk(prices, weights)
    bloc2_risk = {
        "volatility_annualized": risk_mod.annualized_volatility(prices, weights),
        "max_drawdown": risk_mod.max_drawdown(prices, weights),
        "underwater_curve": risk_mod.underwater_curve(prices, weights),
        "var_95": var_block,
        "cvar_95": risk_mod.conditional_var(prices, weights),
    }
    # Beta multi-fenêtres vs SPY ET ACWI (.txt point 23 — les deux affichés)
    bench_spy = benchmarks["SPY"] if "SPY" in benchmarks else None
    bench_acwi = benchmarks["ACWI"] if "ACWI" in benchmarks else None
    port_series = ret_mod._portfolio_series(prices, weights)
    beta_block = {}
    for name, b in [("SPY", bench_spy), ("ACWI", bench_acwi)]:
        if b is None:
            continue
        b_w_map = benchmark_weights_spy if name == "SPY" else benchmark_weights_acwi
        beta_block[name] = {
            "multi_window": beta_mod.beta_multi_window(port_series, b),
            "rolling_252d": beta_mod.rolling_beta(port_series, b),
            "contribution_by_holding": beta_mod.beta_contribution(
                prices, weights, b, benchmark_weights=b_w_map),
        }
    # Currency decomposition si fournie
    currency_decomp = None
    if local_returns is not None and fx_returns is not None and currency_map:
        currency_decomp = risk_mod.currency_decomposition(
            local_returns, fx_returns, weights, currency_map, reference_currency)

    bloc2 = {
        "risk_pure": bloc2_risk,
        "beta": beta_block,
        "currency_decomposition": currency_decomp,
        "exposures": {
            "sector": exp_mod.sector_exposure(weights, sector_map or {}),
            "geographic": exp_mod.geographic_exposure(weights, geo_map or {}),
            "currency": exp_mod.currency_exposure(weights, currency_map or {}),
        },
    }

    # ---------------------------------------------------- BLOC 3 HRP
    daily_rets = prices[list(weights)].pct_change().dropna()
    hrp_w = hrp_mod.hrp_weights(daily_rets)
    herc_w = hrp_mod.herc_weights(daily_rets)
    clusters = hrp_mod.cluster_assignments(daily_rets, n_clusters=4)
    # betas par holding (vs SPY pour cluster aggregation)
    if bench_spy is not None:
        betas_h = {t: beta_mod.beta_simple(prices[t], bench_spy) for t in weights}
        betas_h = {t: b for t, b in betas_h.items() if b is not None}
    else:
        betas_h = {}
    bloc3 = {
        "correlation_heatmap": hrp_mod.correlation_heatmap(daily_rets),
        "dendrogram": hrp_mod.dendrogram_data(daily_rets, weights, sector_map),
        "clusters": clusters,
        "cluster_beta_aggregation": hrp_mod.cluster_beta_aggregation(weights, betas_h, clusters),
        "bridge_assets": hrp_mod.bridge_assets(daily_rets, weights),
        "weights_comparison_hrp": hrp_mod.compare_weights(weights, hrp_w),
        "weights_comparison_herc": hrp_mod.compare_weights(weights, herc_w),
        "ux_note": ("Le dendrogramme remplace le bouton 'OK' du pré-mortem : friction "
                     "cognitive et visuelle, pas mécanique (.txt §4)"),
    }

    # ---------------------------------------------------- BLOC 4 Simulation
    bloc4 = {
        "monte_carlo_bootstrap": mc_mod.run(prices, weights, n_sims=n_mc_sims,
                                              method="bootstrap"),
        "monte_carlo_t_student": mc_mod.run(prices, weights, n_sims=n_mc_sims,
                                              method="t_student_df5"),
        "stress_tests_historical": stress_mod.run_all(prices, weights),
    }

    # ---------------------------------------------------- CROISEMENT (différenciateur)
    crossed = []
    by_holding_contrib = bloc1["attribution"]["by_holding"]
    beta_by_holding = (beta_block.get("SPY", {}).get("contribution_by_holding", {})
                       .get("by_holding", {}))
    for t, w in weights.items():
        sa = (stock_analysis_reports or {}).get(t, {})
        bloc_a = sa.get("bloc_A_verdict", {}) if isinstance(sa, dict) else {}
        epv_ps = (bloc_a.get("EPV", {}) or {}).get("epv_per_share")
        price = bloc_a.get("prix")
        ecart = None
        if isinstance(epv_ps, (int, float)) and isinstance(price, (int, float)) and price:
            ecart = (epv_ps - price) / price
        crossed.append({
            "ticker": t,
            "weight": w,
            "return_contribution": by_holding_contrib.get(t),
            "beta_contribution_spy": beta_by_holding.get(t, {}).get("contribution"),
            "hrp_cluster": clusters.get(t),
            "epv_vs_price_pct": ecart,
            "n_flags": len(sa.get("bloc_B_flags", [])) if isinstance(sa, dict) else None,
            "composite_score": (sa.get("score_composite", {}) or {}).get("value_0_100")
                                if isinstance(sa, dict) else None,
        })
    crossed.sort(key=lambda r: r["weight"], reverse=True)

    return {
        "as_of": datetime.date.today().isoformat(),
        "portfolio_currency": portfolio_currency,
        "n_holdings": len(weights),
        "weights": weights,
        "bloc_1_performance": bloc1,
        "bloc_2_risque": bloc2,
        "bloc_3_correlation_hrp": bloc3,
        "bloc_4_simulation": bloc4,
        "table_croisee_holdings": crossed,
        "differentiator_note": ("Croisement fondamental × risque portefeuille dans une seule "
                                 "vue : aucune banque privée ne le fait (equity research et "
                                 "risk management ne se parlent pas en interne)."),
    }


def save(obj: dict, path: str):
    def default(o):
        if isinstance(o, (np.floating, np.integer)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, pd.Timestamp):
            return o.strftime("%Y-%m-%d")
        return str(o)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=default, ensure_ascii=False)
