# SAINHE Backend v2 — Stock Analysis + Portfolio Simulation

Backend Python complet. Source de vérité : `SAINHE_stock_analysis_plan.txt`.
**Zéro LLM, zéro prédiction, EDGAR direct gratuit, traçabilité totale.**

## Installation

```bash
pip install pandas numpy scipy requests yfinance
# Mets ton email dans config.py → EDGAR_USER_AGENT (SEC l'exige)
python pipeline.py AAPL MSFT KO JPM XOM           # Stock Analysis 5 tickers
# Portfolio Sim : voir tests/test_full.py pour l'API build_portfolio_report()
```

## Couverture vs plan (audit final)

### Stock Analysis : 74/75 (98.7%)
- Niveau 1 Valuation Map (1-12) : 12/12 ✓
- Bloc A Verdict (13-25) : 13/13 ✓ (dispersion relative branchée via peer_batch)
- Bloc B Flags (26-35) : 10/10 ✓
- Bloc C DuPont (36-41) : 6/6 ✓
- Bloc D Sparklines (42-48) : 7/7 ✓
- Bloc E Santé (49-57) : 9/9 ✓
- Bloc F Peers (58-65) : 8/8 ✓ ← Fix Phase 2
- Bloc G Smart Money (66-67) : 1.5/2 (Form 4 XML détail = Phase 6 documentée)
- Bloc H Sensitivity (68) : 1/1 ✓
- Bloc I Macro (69-70) : 2/2 ✓ ← Fix Phase 2
- Drill-down (71-75) : 5/5 ✓ ← Fix Phase 2 (accession par chiffre)

### Portfolio Sim : 47/47 (100%)
- Bloc 1 Performance (1-16) : returns/CAGR, calendrier, yield, courbes vs SPY/ACWI, rolling, attribution, Sharpe/Sortino/Calmar, Alpha Jensen/TE/IR
- Bloc 2 Risque (17-31) : vol, MaxDD, underwater, VaR hist+param + fat tails, CVaR, Beta vs SPY ET ACWI × 1Y/3Y/5Y + rolling + contribution + Dimson, expositions
- Bloc 3 HRP (32-37) : matrice + dendrogramme Lopez de Prado, clusters, beta cluster, ponts, HRP vs actuel, HERC
- Bloc 4 Simulation (38-47) : MC bootstrap + t-Student, 1Y/5Y, percentiles, prob loss, time-to-recovery, 5 scénarios (GFC, COVID, Taper Tantrum, Volmageddon, Hike Cycle)

### Croisement final (différenciateur conv)
Table par holding : poids | return contrib | beta contrib | cluster HRP | EPV vs prix | n_flags | score. Aucune banque privée ne fait ça.

## Validation

```bash
python tests/test_pipeline.py   # → 62/62 ✓
python tests/test_full.py       # → 61/61 ✓
# Total : 123/123 assertions sur fixtures déterministes
```

## Reste à faire (documenté inline)

1. Brancher Rf/ERP sur le module Macro SAINHE existant (defaults dans config.py)
2. Form 4 XML parsing pour détail insider buy/sell (Phase 6 — v1 = comptage)
3. Validation sur tickers réels : Net Debt Apple vs 10-K au million près
4. Univers peers complet : le batch tourne dès qu'on lance les 30 tickers
