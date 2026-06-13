"""Tests de validation — chaque formule vérifiée contre les valeurs calculées à la main
(cf. docstring de tests/fixtures/testco.py). Règle Phase 1 du prompt :
'le Net Debt doit matcher au million près' → ici au centime, fixture déterministe.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edgar.xbrl_parser import parse_companyfacts
from compute import metrics, valuation, dupont, buffett, scores
from compute.adjustments import adjust
from output import report_builder
from tests.fixtures.testco import testco_companyfacts, badco_companyfacts

PASS, FAIL = 0, 0


def check(name, got, expected, tol=1e-2):
    global PASS, FAIL
    ok = (got is not None and expected is not None and abs(got - expected) <= tol)
    if ok:
        PASS += 1
        print(f"  ✓ {name}: {got:.4f}")
    else:
        FAIL += 1
        print(f"  ✗ {name}: got={got} expected={expected}")


def check_true(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  ✓ {name}")
    else:
        FAIL += 1; print(f"  ✗ {name}")


print("=" * 60)
print("TESTCO — formules de base")
print("=" * 60)
cd = parse_companyfacts("TESTCO", 999999, testco_companyfacts())
m = metrics.derive(cd, 2023)

check("Net Debt ASC842 (300+30+15-100)", m["net_debt"], 245.0)
check("EBITDA (250+50)", m["ebitda"], 300.0)
check("Effective tax (46/230)", m["effective_tax_rate"], 0.20)
check("NOPAT (250×0.8)", m["nopat"], 200.0)
check("Invested Capital (700+245)", m["invested_capital"], 945.0)
check("ROIC (200/945)", m["roic"], 200.0 / 945.0, tol=1e-4)
check("FCF brut (260-70)", m["fcf_brut"], 190.0)
check("FCF ajusté SBC (190-25)", m["fcf_adj"], 165.0)
check("Owner Earnings (260-50-25)", m["owner_earnings"], 185.0)
check("Gross Margin (400/1000)", m["gross_margin"], 0.40, tol=1e-4)
check("Interest Coverage (250/20)", m["interest_coverage"], 12.5)
check("OCF/NI (260/184)", m["ocf_ni"], 260.0 / 184.0, tol=1e-4)
check("DSO (120/1000×365)", m["dso"], 43.8)
check("CCC (43.8+48.67-54.75)", m["ccc"], 43.8 + 80/600*365 - 90/600*365, tol=0.1)

print("\nReformulation Penman")
ref = m["reformulation"]
check("FA (100+20)", ref["FA"], 120.0)
check("FO (300+30+15)", ref["FO"], 345.0)
check("NOA (1380-455)", ref["NOA"], 925.0)
check("NFO (345-120)", ref["NFO"], 225.0)
check("Equity check (NOA-NFO-Equity=0)", ref["equity_check"], 0.0)

print("\nAdvanced DuPont")
d = dupont.advanced_dupont(cd, 2023)
check("RNOA (200/925)", d["RNOA"], 200.0 / 925.0, tol=1e-4)
check("FLEV (225/700)", d["FLEV"], 225.0 / 700.0, tol=1e-4)
check("NBC (20×0.8/225)", d["NBC"], 16.0 / 225.0, tol=1e-4)
check("ROE dupont ≈ ROE direct", d["coherence_gap"], 0.0, tol=1e-3)

print("\nValorisation")
w = valuation.wacc(cd, price=15.0)
# Ke = 0.042 + 1.0×0.05 = 0.092 ; E=1500, D=345, V=1845
# WACC = 0.092×(1500/1845) + (20/330)×0.8×(345/1845)
exp_wacc = 0.092 * (1500/1845) + (20/330) * 0.8 * (345/1845)
check("Ke (rf+β×ERP)", w["ke"], 0.092, tol=1e-4)
check("WACC complet", w["wacc"], exp_wacc, tol=1e-4)

e = valuation.epv(cd, w["wacc"], 2023)
# EPV_EV = 250×0.8/wacc ; equity = EV-245 ; /100 shares
exp_ev = 200.0 / w["wacc"]
check("EPV enterprise", e["epv_ev"], exp_ev, tol=0.5)
check("EPV per share", e["epv_per_share"], (exp_ev - 245.0) / 100.0, tol=0.05)

r = valuation.reverse_dcf(cd, price=15.0, wacc_value=w["wacc"])
# EV = 15×100+245 = 1745 ; g = (wacc×1745-165)/(1745+165)
exp_g = (w["wacc"] * 1745 - 165.0) / (1745.0 + 165.0)
check("Reverse DCF implied g", r["implied_g"], exp_g, tol=1e-4)

s = valuation.sgr(cd, 2023)
check_true("SGR calculé (non-None)", s["sgr"] is not None)

re_ = valuation.residual_earnings_static(cd, w["ke"], s["sgr"])
check_true("RE valuation per share > 0", isinstance(re_["re_value_per_share"], float)
           and re_["re_value_per_share"] > 0)

sm = valuation.sensitivity_matrix(cd, w["ke"], s["sgr"])
check_true("Sensitivity matrix 5×5", sm["matrix"] is not None and len(sm["matrix"]) == 5
           and len(sm["matrix"][0]) == 5)

print("\nBuffett")
lt = buffett.lt_debt_payback(cd)
check("LT Debt payback (300/184)", lt["years"], 300.0 / 184.0, tol=1e-3)
gm = buffett.gross_margin_trend(cd)
check_true("GM trend = expansion", gm["direction"] == "expansion")
roe_c = buffett.roe_consistency(cd)
check_true("ROE consistency disponible", roe_c["available"])
re_test = buffett.retained_earnings_dollar_test(
    cd, price_history={2018: 9.0, 2023: 15.0})
check_true("$1 Test calculé avec prix fournis", isinstance(re_test["ratio"], float))

print("\nScores TESTCO (sain — flags minimaux)")
z = scores.altman_z(cd, market_cap=1500.0, fy=2023)
check_true(f"Altman Z = {z['z']:.2f} en zone safe/grey", z["zone"] in ("safe", "grey"))
b = scores.beneish_m(cd, 2023)
check_true(f"Beneish M = {b['m']:.2f} sous le seuil", b["flag"] is False)
flags = scores.all_flags(cd, {"nt_filing": {"triggered": False},
                              "restatement_2y": {"triggered": False}}, 1500.0)
ids = {f["id"] for f in flags}
check_true("TESTCO : pas de flag composite goodwill", "goodwill_roic_composite" not in ids)
check_true("TESTCO : pas de flag SBC", "sbc_15pct_fcf" not in ids)

print("\n" + "=" * 60)
print("BADCO — tous les drapeaux rouges doivent tirer")
print("=" * 60)
bad = parse_companyfacts("BADCO", 999998, badco_companyfacts())
rt = scores.roic_trend(bad)
check_true("ROIC déclinant 3Y+ détecté", rt["declining_3y_plus"])
bflags = scores.all_flags(bad, {"nt_filing": {"triggered": True, "details": []},
                                "restatement_2y": {"triggered": False}}, 1200.0)
bids = {f["id"] for f in bflags}
for expected_flag in ["goodwill_30pct", "goodwill_roic_composite", "sbc_15pct_fcf",
                      "lease_heavy", "goodwill_impairment", "nt_filing"]:
    check_true(f"flag {expected_flag} tiré", expected_flag in bids)
badj = adjust(bad, 2023)
check_true("Impairment dans les ajustements transitoires",
           any(a["item"] == "goodwill_impairment" for a in badj["adjustments"]))
check_true("NI ajusté > NI brut (addback impairment)",
           badj["ni_adj"] > badj["ni_brut"])

print("\nRapport complet end-to-end")
rep = report_builder.build_report(
    cd, price=15.0, yf_info={"targetMeanPrice": 16.0, "targetMedianPrice": 15.5,
                             "targetHighPrice": 18.0, "targetLowPrice": 13.0,
                             "numberOfAnalystOpinions": 8, "beta": 1.1,
                             "sector": "Industrials"},
    edgar_meta={"nt_filing": {"triggered": False}, "restatement_2y": {"triggered": False}},
    price_history={2018: 9.0, 2023: 15.0})
for bloc in ["bloc_A_verdict", "bloc_B_flags", "bloc_C_dupont", "bloc_D_trends",
             "bloc_E_health", "bloc_F_peers", "bloc_G_smart_money",
             "bloc_H_sensitivity", "bloc_I_macro", "score_composite", "drill_down"]:
    check_true(f"bloc présent : {bloc}", bloc in rep)
check_true("score composite 0-100",
           0 <= rep["score_composite"]["value_0_100"] <= 100)
check_true("consensus dispersion calculée",
           isinstance(rep["bloc_A_verdict"]["consensus"]["dispersion"], float))
vmap = report_builder.build_valuation_map([rep])
check_true("valuation map 1 ligne", len(vmap["rows"]) == 1)

report_builder.save(rep, "/home/claude/sainhe_backend/tests/TESTCO_report_sample.json")
print(f"\n{'='*60}\nRÉSULTAT : {PASS} ✓ / {FAIL} ✗")
sys.exit(1 if FAIL else 0)
