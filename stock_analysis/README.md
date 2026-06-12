# SAINHE Backend — Stock Analysis

Backend Python complet du module Stock Analysis. Source de vérité : `SAINHE_stock_analysis_plan.txt`.
**Zéro LLM, zéro prédiction, EDGAR direct gratuit, traçabilité totale.**

## Installation (sur ta machine / VM)

```bash
pip install pandas numpy requests yfinance
# 1. Mets ton email dans config.py → EDGAR_USER_AGENT (obligatoire SEC)
# 2. Lance sur les 5 tickers de validation :
python pipeline.py AAPL MSFT KO JPM XOM
# Sorties : output/json/{TICKER}_report.json + output/json/valuation_map.json
```

Sans yfinance/réseau Yahoo : prix, consensus, beta = "N/D", tout le reste (EDGAR) tourne.

## Structure

```
config.py                 tous les seuils (zéro valeur magique ailleurs)
pipeline.py               orchestrateur : ticker → EDGAR → compute → JSON
edgar/
  edgar_client.py         fetch + rate limit 10/s + cache SQLite + ticker→CIK
  xbrl_parser.py          tous les tags du plan, séries 10Y, restatements gérés,
                          transitions de tags (ASC 606, FASB 2024+), st_debt synthétique
  metadata_flags.py       NT filings, 10-K/A (flags metadata)
compute/
  metrics.py              métriques dérivées, reformulation Penman, Net Debt ASC 842
                          (financial_debt centralisée, garde anti double-comptage leases),
                          FCF ajusté SBC, Owner Earnings
  adjustments.py          earnings transitoires (Adjusted NI/EBIT) — preprocessing
  valuation.py            WACC, EPV, Reverse DCF, SGR, RE statique, plage de confiance,
                          sensibilité WACC, sensitivity matrix 5×5
  dupont.py               Advanced DuPont (RNOA, FLEV, NBC, SPREAD) + check cohérence
  buffett.py              Owner Earnings, $1 Test, LT Debt Payback, ROE consistency, GM trend
  scores.py               Altman Z, Beneish M (8 sous-ratios), ROIC trend,
                          flag composite Goodwill+ROIC, tous les flags
  external.py             consensus yfinance, dispersion relative, peers quartiles,
                          insiders (squelette), macro context GICS→indicateur
output/
  report_builder.py       JSON blocs A→I + score composite + valuation_map
tests/
  test_pipeline.py        62 assertions, formules vérifiées à la main — 62/62 ✓
  fixtures/testco.py      TESTCO (sain) + BADCO (tous les red flags)
```

## Validé

- **62/62 tests** sur fixture déterministe : Net Debt ASC 842, EBITDA, NOPAT, ROIC,
  FCF brut/ajusté, Owner Earnings, reformulation NOA/NFO (equity check = 0),
  DuPont (ROE dupont ≡ ROE direct), Ke/WACC, EPV, Reverse DCF, $1 Test, Altman Z, Beneish M.
  BADCO déclenche les 6 flags attendus.
- **Phase 1 validée sur les 5 tickers réels (live EDGAR)** :
  - Net Debt AAPL FY2025 = 63 953 M$ = 10-K **au million près** (écart 0.00 M$)
  - Net Debt KO FY2025 = 35 222 M$ = 10-K au million près (tags FASB 2024+)
  - JPM/XOM : EPV = N/D attendu (pas de tag OperatingIncomeLoss — banques/pétrolières)

## Reste à faire (Phases 5-6, documenté dans le code)

- **Portfolio Sim** (returns, beta, HRP riskfolio-lib, Monte Carlo, stress tests) — module séparé
- **Peers batch** : quartiles réels exigent l'univers SIC complet (boucle sur les 30 tickers)
- **Form 4 XML parsing** : détail buy/sell insiders (v1 = comptage filings)
- **Brancher Rf/ERP** sur le module Macro SAINHE existant (defaults dans config.py)
