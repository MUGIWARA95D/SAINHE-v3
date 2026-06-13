"""Validation complète Stock Analysis + Portfolio Sim. Tout offline via fixtures.

Phase 1 (Stock Analysis fix) : peers branchés, segments geo, traceability par chiffre,
dispersion relative connectée.

Phase 2 (Portfolio Sim) : 5 tickers synthétiques avec
  - séries de prix incluant 2008/2020/2022 pour stress tests
  - corrélations contrôlées (2 clusters tech/value attendus)
  - poids déséquilibrés pour valider la concentration HRP
"""
from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

from edgar.xbrl_parser import parse_companyfacts
from compute import metrics, valuation, peer_batch
from output import report_builder
from portfolio import builder as port_builder
from tests.fixtures.testco import testco_companyfacts, badco_companyfacts

PASS, FAIL = 0, 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {name}")
    else:
        FAIL += 1; print(f"  ✗ {name} {detail}")


print("=" * 60)
print("STOCK ANALYSIS — Fix Phase 1 (4 trous comblés)")
print("=" * 60)

cd_a = parse_companyfacts("TICKA", 100001, testco_companyfacts())
cd_b = parse_companyfacts("TICKB", 100002, badco_companyfacts())
# Petit univers de peers pour valider le batch
cd_c = parse_companyfacts("TICKC", 100003, testco_companyfacts())
cd_d = parse_companyfacts("TICKD", 100004, testco_companyfacts())

bundles = []
for i, (cd, price) in enumerate([(cd_a, 18.0), (cd_b, 12.0), (cd_c, 22.0), (cd_d, 15.0)]):
    w = valuation.wacc(cd, price)
    shares = cd.value("shares_diluted") or cd.value("shares_outstanding")
    mcap = price * shares if (price and shares) else None
    bundles.append({"ticker": cd.ticker, "cd": cd, "price": price,
                     "market_cap": mcap, "wacc": w["wacc"], "sic": "3674",
                     "dispersion": [0.15, 0.30, 0.20, 0.18][i]})

peer_blocks = peer_batch.build_peer_blocks(bundles)

print("\n  Fix 1 — Batch peers (bloc F)")
for t, pb in peer_blocks.items():
    q = pb["quartiles"]
    check(f"{t} : quartiles présents", all(k in q for k in
          ["pe", "ev_ebitda", "p_fcf", "p_s", "roic", "roe", "spread_roic_wacc", "kd"]))
    check(f"{t} : kd_vs_peers calculé", pb["kd_vs_peers"]["peer_median_kd"] is not None)
    check(f"{t} : spread_rank défini", pb["spread_rank"]["rank"] is not None)
    check(f"{t} : dispersion relative branchée",
           pb["dispersion_relative"]["ratio"] is not None)

print("\n  Fix 2 — Segment geo (bloc I) + Fix 3 — Traceability par chiffre")
rep = report_builder.build_report(
    cd_a, price=18.0,
    yf_info={"targetMeanPrice": 20, "targetMedianPrice": 19.5, "targetHighPrice": 23,
             "targetLowPrice": 16, "numberOfAnalystOpinions": 12, "beta": 1.1,
             "sector": "Industrials", "country": "France"},
    edgar_meta={"nt_filing": {"triggered": False}, "restatement_2y": {"triggered": False}},
    peer_block=peer_blocks["TICKA"])

check("Bloc F peers BRANCHÉ (pas placeholder)",
       "quartiles" in rep["bloc_F_peers"] and "note" not in rep["bloc_F_peers"])
check("Bloc F : dispersion_relative présente",
       "dispersion_relative" in rep["bloc_F_peers"])
check("Bloc I : geographic_exposure présent",
       "geographic_exposure" in rep["bloc_I_macro"])
check("Bloc I : country détecté via yf_info",
       rep["bloc_I_macro"]["geographic_exposure"].get("country") == "France")
check("Drill-down : source_map_per_tag présent",
       "source_map_per_tag" in rep["drill_down"])
check("Drill-down : URL EDGAR par chiffre (revenue)",
       "edgar_filing_url" in rep["drill_down"]["source_map_per_tag"]["revenue"])
check("Drill-down : edgar_filings_index URL valide",
       rep["drill_down"]["edgar_filings_index"].startswith("https://www.sec.gov"))


print("\n" + "=" * 60)
print("PORTFOLIO SIM — 47 métriques sur 5 tickers synthétiques")
print("=" * 60)


# ----- Génère des séries de prix synthétiques 2007-2024 incluant les crises
def synth_prices(seed: int, n_days: int, mu_annual: float, sigma_annual: float,
                 crash_dates: list[tuple]) -> pd.Series:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2007-01-02", periods=n_days)
    mu_d, sigma_d = mu_annual / 252, sigma_annual / np.sqrt(252)
    rets = rng.normal(mu_d, sigma_d, n_days)
    # Injecter les crises
    for start, end, magnitude in crash_dates:
        mask = (dates >= start) & (dates <= end)
        n = mask.sum()
        if n > 0:
            crash_path = np.linspace(0, magnitude, n)
            rets[mask] += np.diff(np.concatenate([[0], crash_path])) / n * 50
    prices = 100 * np.exp(np.cumsum(rets))
    return pd.Series(prices, index=dates)


N_DAYS = 252 * 17  # 2007 → 2024
crashes = [("2008-09-01", "2009-03-31", -0.35),
           ("2020-02-19", "2020-04-30", -0.30),
           ("2022-01-01", "2022-10-31", -0.20)]
# 5 tickers : 2 tech (corrélés), 2 value (corrélés), 1 défensif
np.random.seed(0)
common_tech = synth_prices(1, N_DAYS, 0.12, 0.25, crashes)
common_value = synth_prices(2, N_DAYS, 0.08, 0.18, crashes)
prices = pd.DataFrame({
    "TECH1": common_tech * (1 + 0.05 * np.random.randn(N_DAYS).cumsum() / 1000),
    "TECH2": common_tech * (1 + 0.05 * np.random.randn(N_DAYS).cumsum() / 1000),
    "VAL1":  common_value * (1 + 0.05 * np.random.randn(N_DAYS).cumsum() / 1000),
    "VAL2":  common_value * (1 + 0.05 * np.random.randn(N_DAYS).cumsum() / 1000),
    "DEF1":  synth_prices(5, N_DAYS, 0.06, 0.10, crashes),
})
# Benchmarks
benchmarks = pd.DataFrame({
    "SPY":  synth_prices(10, N_DAYS, 0.09, 0.16, crashes),
    "ACWI": synth_prices(11, N_DAYS, 0.08, 0.15, crashes),
})

weights = {"TECH1": 0.30, "TECH2": 0.20, "VAL1": 0.20, "VAL2": 0.15, "DEF1": 0.15}
sector_map = {"TECH1": "Tech", "TECH2": "Tech", "VAL1": "Financials",
               "VAL2": "Financials", "DEF1": "Consumer Staples"}
geo_map = {"TECH1": "US", "TECH2": "US", "VAL1": "Europe", "VAL2": "Europe", "DEF1": "US"}
ccy_map = {"TECH1": "USD", "TECH2": "USD", "VAL1": "EUR", "VAL2": "EUR", "DEF1": "USD"}

# Stock Analysis reports pour le croisement
stock_reports = {"TECH1": rep}  # un seul branché — suffit pour valider la jointure

report = port_builder.build_portfolio_report(
    prices=prices,
    weights=weights,
    benchmarks=benchmarks,
    rf_annual=0.042,
    per_ticker_yield={"TECH1": 0.005, "TECH2": 0.0, "VAL1": 0.035, "VAL2": 0.04, "DEF1": 0.025},
    sector_map=sector_map, geo_map=geo_map, currency_map=ccy_map,
    benchmark_weights_spy={"TECH1": 0.05},  # contamination test
    stock_analysis_reports=stock_reports,
    n_mc_sims=2_000,   # plus rapide pour le test
)

print("\n  BLOC 1 Performance (points 1-16)")
b1 = report["bloc_1_performance"]
check("1-2 returns cumulés + CAGR (1Y/3Y/5Y)",
       "1Y" in b1["returns_absolus"]["cumulative"] and "5Y" in b1["returns_absolus"]["cagr"])
check("6 calendar year returns",
       len(b1["returns_absolus"]["calendar_year_returns"]) >= 10)
check("4 dividend yield agrégé",
       b1["returns_absolus"]["aggregate_dividend_yield"] is not None)
check("5 cumulative curves vs benchmarks",
       "portfolio" in b1["cumulative_curves"] and len(b1["cumulative_curves"]["benchmarks"]) >= 2)
check("7-8 rolling_return_1y + rolling_sharpe_252d",
       "rolling_return_1y" in b1["rolling_metrics"]
       and "rolling_sharpe_252d" in b1["rolling_metrics"])
check("9-11 attribution holding/sector/geo",
       all(k in b1["attribution"] for k in ["by_holding", "by_sector", "by_geography"]))
check("12-14 Sharpe + Sortino + Calmar",
       all(k in b1["risk_adjusted_ratios"] for k in ["sharpe", "sortino", "calmar"]))
check("15-16 Alpha Jensen + Tracking + IR (vs SPY)",
       all(k in b1["returns_vs_benchmark_spy"]
            for k in ["alpha_annual", "tracking_error", "information_ratio"]))

print("\n  BLOC 2 Risque (points 17-31)")
b2 = report["bloc_2_risque"]
rp = b2["risk_pure"]
check("17 volatility annualized", isinstance(rp["volatility_annualized"], float))
check("18 max drawdown + peak/trough dates",
       "peak_date" in rp["max_drawdown"] and "trough_date" in rp["max_drawdown"])
check("19 underwater curve", len(rp["underwater_curve"]["dates"]) > 1000)
check("20-21 VaR historique ET paramétrique + flag fat tails",
       all(k in rp["var_95"] for k in ["historical", "parametric", "fat_tails"]))
check("22 CVaR 95%", rp["cvar_95"]["cvar_95"] is not None)
check("23-26 Beta vs SPY ET ACWI, multi-fenêtres + rolling + contribution",
       "SPY" in b2["beta"] and "ACWI" in b2["beta"]
       and "multi_window" in b2["beta"]["SPY"]
       and "rolling_252d" in b2["beta"]["SPY"]
       and "contribution_by_holding" in b2["beta"]["SPY"])
check("27 Beta multi-fenêtres présent (1Y/3Y/5Y)",
       all(k in b2["beta"]["SPY"]["multi_window"] for k in ["1Y", "3Y", "5Y"]))
check("27bis contamination + Dimson",
       b2["beta"]["SPY"]["contribution_by_holding"]["by_holding"]
        .get("TECH1", {}).get("contaminated") is True)
check("28 top 70% beta drivers",
       len(b2["beta"]["SPY"]["contribution_by_holding"]["top_drivers_70pct"]) >= 1)
check("29-30 sector + geographic exposure",
       "Tech" in b2["exposures"]["sector"] and "Europe" in b2["exposures"]["geographic"])
check("31 currency exposure", "EUR" in b2["exposures"]["currency"])

print("\n  BLOC 3 Corrélation HRP (points 32-37)")
b3 = report["bloc_3_correlation_hrp"]
check("32 correlation heatmap", "matrix" in b3["correlation_heatmap"])
check("33 dendrogramme (leaves_order + nodes)",
       len(b3["dendrogram"]["leaves_order"]) == 5 and len(b3["dendrogram"]["nodes"]) == 5)
check("34 cluster beta aggregation",
       len(b3["cluster_beta_aggregation"]) >= 1)
check("35 bridge assets identifiés",
       isinstance(b3["bridge_assets"], list) and len(b3["bridge_assets"]) > 0)
check("36 weights comparison HRP",
       len(b3["weights_comparison_hrp"]) == 5
       and "current_weight" in b3["weights_comparison_hrp"][0]
       and "hrp_suggested" in b3["weights_comparison_hrp"][0])
check("37 weights comparison HERC", len(b3["weights_comparison_herc"]) == 5)
check("HRP poids ≈ 1.0",
       abs(sum(r["hrp_suggested"] for r in b3["weights_comparison_hrp"]) - 1.0) < 0.05,
       detail=f"sum={sum(r['hrp_suggested'] for r in b3['weights_comparison_hrp']):.3f}")

print("\n  BLOC 4 Simulation (points 38-47)")
b4 = report["bloc_4_simulation"]
mcb = b4["monte_carlo_bootstrap"]
check("38 Monte Carlo bootstrap lancé", mcb.get("available"))
check("39 percentiles 5/25/50/75/95 sur 1Y",
       all(f"p{p}" in mcb["horizons"]["1Y"]["percentiles"] for p in [5, 25, 50, 75, 95]))
check("39bis horizons 1Y et 5Y", "1Y" in mcb["horizons"] and "5Y" in mcb["horizons"])
check("40 prob_loss_gt_30pct présent",
       isinstance(mcb["horizons"]["1Y"]["prob_loss_gt_30pct"], float))
check("41 time_to_recovery_distribution",
       "time_to_recovery_distribution" in mcb["horizons"]["5Y"])
check("42 alternative t-Student fournie",
       b4["monte_carlo_t_student"]["method"] == "t_student_df5")
st = b4["stress_tests_historical"]
check("43-47 5 scénarios historiques",
       all(s in st for s in ["GFC_2008", "COVID_2020", "Taper_Tantrum_2013",
                                "Volmageddon_2018", "Hike_Cycle_2022"]))
check("Stress test GFC : drawdown négatif détecté",
       st["GFC_2008"]["available"] and st["GFC_2008"]["max_drawdown_during"] < 0)

print("\n  CROISEMENT Stock Analysis × Portfolio (différenciateur)")
crossed = report["table_croisee_holdings"]
check("Table croisée sur tous les holdings", len(crossed) == 5)
check("Holding avec Stock Analysis : EPV vs prix présent",
       any(r.get("epv_vs_price_pct") is not None for r in crossed))
check("Holding avec Stock Analysis : score + flags croisés",
       any(r.get("composite_score") is not None for r in crossed))
check("Toutes les colonnes du contrat conv présentes",
       all(set(["ticker", "weight", "return_contribution", "beta_contribution_spy",
                 "hrp_cluster", "epv_vs_price_pct", "n_flags", "composite_score"])
            <= set(r.keys()) for r in crossed))

# Sauvegarde
os.makedirs("tests/out", exist_ok=True)
port_builder.save(report, "tests/out/portfolio_sample.json")
report_builder.save(rep, "tests/out/TICKA_report_sample.json")

print(f"\n{'='*60}\nRÉSULTAT : {PASS} ✓ / {FAIL} ✗")
sys.exit(1 if FAIL else 0)
