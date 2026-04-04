# CLAUDE.md — SAINHE Project
> **CE FICHIER EST LE CONTEXTE PRINCIPAL DE CLAUDE CODE.**
> Lis-le intégralement avant d'écrire la moindre ligne de code.
> Toutes les décisions architecturales sont ici. Ne rien inventer, ne rien supposer.

---

## ⚡ QUICK START POUR CLAUDE CODE

```
Projet    : SAINHE — dashboard financier web (page HTML statique)
Dossier   : C:\SAINHE\
Langage   : Python 3.10+
DB        : SQLite → C:\SAINHE\db\sainhe.db
Output    : C:\SAINHE\output\index.html
```

### Ordre de build OBLIGATOIRE — ne pas dévier

```
1. db_init.py          → créer toutes les tables SQLite
2. fetch_prices.py     → yfinance : OHLCV quotidien + .info (PE, Beta, 52W)
3. fetch_indices.py    → yfinance : 13 indices globaux + ^TNX + ^IRX
4. fetch_fx.py         → Google Finance scraping : USD/EUR + USD/HKD
5. fetch_news.py       → feedparser RSS : 7 sources, rotation horaire
6. calc.py             → OBV, MFI, DMA, Momentum, RVOL, R-Perf, Sentiment
7. box_02_indices.py   → lire DB → générer HTML box 2
8. box_03_sectors.py   → lire DB → générer HTML box 3
9. box_04_sentiment.py → lire DB → générer HTML box 4
10. box_01_news.py     → lire cache JSON → générer HTML box 1
11. render_html.py     → assembler toutes les boxes → output/index.html
```

**Ne jamais coder une box avant que les données qu'elle consomme soient en base.**

---

## 🏗️ STRUCTURE DES DOSSIERS

```
C:\SAINHE\
├── CLAUDE.md                  ← ce fichier — contexte Claude Code
├── requirements.txt
├── main.py                    ← point d'entrée : lance tout dans l'ordre
├── config.py                  ← tickers watchlist, chemins, constantes
│
├── db\
│   └── sainhe.db              ← base SQLite unique
│
├── cache\
│   ├── news\                  ← news_YYYY-MM-DD.json (fenêtre 7 jours)
│   ├── events_today.json      ← TOP 3 events du jour (généré 08h00)
│   └── fx_rates.json          ← taux USD/EUR + USD/HKD du jour
│
├── scripts\
│   ├── db_init.py
│   ├── fetch_prices.py
│   ├── fetch_indices.py
│   ├── fetch_fx.py
│   ├── fetch_news.py
│   └── calc.py
│
├── boxes\
│   ├── box_01_news.py
│   ├── box_02_indices.py
│   ├── box_03_sectors.py
│   ├── box_04_sentiment.py
│   ├── box_05_macro.py        ← bandeau ERP + Yield Curve + VIX
│   └── box_06_portfolio.py
│
├── templates\
│   └── dashboard.html         ← template Jinja2 principal
│
└── output\
    └── index.html             ← page finale servie aux users
```

---

## 🗄️ SCHÉMA BASE DE DONNÉES SQLite

```sql
-- Série de prix par ticker (ETF sectoriels + indices)
CREATE TABLE prices (
    id          INTEGER PRIMARY KEY,
    ticker      TEXT NOT NULL,
    date        DATE NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,       -- adjusted close
    volume      INTEGER,
    UNIQUE(ticker, date)
);

-- Métriques calculées par ticker (mise à jour quotidienne)
CREATE TABLE metrics (
    ticker          TEXT NOT NULL,
    date            DATE NOT NULL,
    dma_50          REAL,
    dma_200         REAL,
    var_pct_j1      REAL,   -- (close_j1 - close_j2) / close_j2 * 100
    momentum_1m     REAL,
    momentum_3m     REAL,
    momentum_6m     REAL,
    momentum_1y     REAL,
    momentum_2y     REAL,
    rvol_20j        REAL,   -- volume_j1 / avg_volume_20j * 100
    obv             REAL,
    obv_delta_j1    REAL,
    obv_dir_20j     TEXT,   -- 'RISING' ou 'FALLING'
    rvol_dir        REAL,   -- obv_delta_j1 / avg_vol_20j * 100
    mfi_14          REAL,
    sentiment_score REAL,   -- -1.0 à +1.0
    sentiment_label TEXT,
    pos_52w_range   REAL,
    prix_vs_50dma   REAL,
    prix_vs_200dma  REAL,
    signal_dma      TEXT,   -- 'Golden Cross' ou 'Death Cross'
    PRIMARY KEY (ticker, date)
);

-- Métadonnées statiques par ticker (Beta, 52W, PE — refresh quotidien)
CREATE TABLE ticker_info (
    ticker          TEXT PRIMARY KEY,
    nom             TEXT,
    secteur_sainhe  TEXT,
    region          TEXT,
    devise_native   TEXT,
    beta_5y         REAL,
    high_52w        REAL,
    low_52w         REAL,
    pe_ratio        REAL,   -- ^GSPC uniquement pour ERP
    last_updated    DATE
);

-- Volume intraday horaire (Box 2 RVOL Speed)
CREATE TABLE intraday_volume (
    ticker          TEXT NOT NULL,
    datetime        DATETIME NOT NULL,
    volume_1h       INTEGER,
    vol_cumul_jour  INTEGER,
    heures_ecoulees REAL,
    rvol_speed      REAL,
    PRIMARY KEY (ticker, datetime)
);

-- Taux de change (stockés en J-1)
CREATE TABLE fx_rates (
    date            DATE NOT NULL,
    usd_eur         REAL,
    usd_hkd         REAL,
    PRIMARY KEY (date)
);

-- Macro bandeau Box 5
CREATE TABLE macro_bandeau (
    date            DATE PRIMARY KEY,
    tnx_yield       REAL,   -- ^TNX close = yield %
    irx_yield       REAL,   -- ^IRX close = 3M yield %
    yield_spread    REAL,   -- tnx - irx
    yield_signal    TEXT,   -- 'NORMALE' / 'INVERSÉE' / 'DÉSINVERSION'
    gspc_pe         REAL,   -- PE ratio S&P500
    earnings_yield  REAL,   -- 1 / pe
    erp             REAL,   -- earnings_yield - (tnx/100)
    erp_signal      TEXT,   -- 'ATTRACTIF' / 'CHER' / 'IRRATIONNEL'
    vix_close       REAL,
    vix_signal      TEXT    -- 'COMPLAISANCE' / 'NORMAL' / 'PANIQUE'
);

-- R-Perf sectorielle (Box 3)
CREATE TABLE rperf (
    ticker          TEXT NOT NULL,
    date            DATE NOT NULL,
    benchmark_monde TEXT,   -- ticker ETF monde du même secteur
    rperf_today     REAL,
    rperf_1m        REAL,
    rperf_3m        REAL,
    rperf_1y        REAL,
    rperf_2y        REAL,
    rf_check        INTEGER, -- 1 si momentum_1y > tnx_yield
    golden_alpha    INTEGER, -- 1 si rperf > 0 ET rf_check = 1
    PRIMARY KEY (ticker, date)
);
```

---

## 📦 REQUIREMENTS.TXT

```
yfinance>=0.2.36
pandas>=2.0
feedparser>=6.0
holidays>=0.46
requests>=2.31
beautifulsoup4>=4.12
jinja2>=3.1
```

---

## 🔑 RÈGLES ABSOLUES — NE JAMAIS VIOLER

```
❌ ZÉRO API avec clé (yfinance est une lib, pas une API)
❌ ZÉRO IA générative (pas de Gemini, pas d'OpenAI, rien)
❌ ZÉRO stockage en EUR ou HKD — tout en USD en base
❌ ZÉRO FMP — abandonné
❌ AUM / TER / Tracking Error — supprimés, ne pas les coder
✅ Toute conversion devise = à l'affichage uniquement (USD × taux)
✅ Adjusted Close partout — jamais le prix brut
✅ RVOL = 20J standard Bloomberg
✅ Sparkline = 7 jours calendaires sur Adjusted Close
✅ Si donnée manquante → afficher "DATA UNAVAILABLE", jamais extrapoler
```

---

## 🌐 TICKERS RÉFÉRENCE RAPIDE

### ETFs sectoriels (sheet "Tickers Sectoriels par region" dans Table_Tickers_SAINHE_v5.xlsx)
16 secteurs × 4 régions (Monde/USA/Europe/Asie) — lire l'Excel pour la liste complète.
Benchmark Monde par secteur = colonne "Monde (MSCI)" du même fichier.

### Indices globaux (sheet "tickers globaux")
```python
INDICES = {
    "^GSPC": {"nom": "SP500",      "region": "USA",    "devise": "USD", "volume": True},
    "^FCHI": {"nom": "CAC40",      "region": "EU",     "devise": "EUR", "volume": True},
    "^GDAXI":{"nom": "DAX",        "region": "EU",     "devise": "EUR", "volume": True},
    "^FTSE": {"nom": "FTSE 100",   "region": "EU",     "devise": "GBP", "volume": True},
    "^N225": {"nom": "Nikkei 225", "region": "ASIE",   "devise": "JPY", "volume": True},
    "^HSI":  {"nom": "Hang Seng",  "region": "ASIE",   "devise": "HKD", "volume": True},
    "000001.SS":{"nom":"Shanghai", "region": "ASIE",   "devise": "CNY", "volume": True},
    "^NSEI": {"nom": "Nifty 50",   "region": "ASIE",   "devise": "INR", "volume": True},
    "^GSPTSE":{"nom":"TSX",        "region": "USA",    "devise": "CAD", "volume": True},
    "^AXJO": {"nom": "ASX 200",    "region": "ASIE",   "devise": "AUD", "volume": True},
    "^SSMI": {"nom": "SMI",        "region": "EU",     "devise": "CHF", "volume": True},
    "^VIX":  {"nom": "VIX",        "region": "USA",    "devise": "USD", "volume": False},
    "DX-Y.NYB":{"nom":"DXY",       "region": "GLOBAL", "devise": "USD", "volume": False},
    "^TNX":  {"nom": "US 10Y",     "region": "USA",    "devise": "USD", "volume": False},
    "^IRX":  {"nom": "US 3M",      "region": "USA",    "devise": "USD", "volume": False},
}
# Note: ^TNX et ^IRX : close = yield en %. Ex: 4.31 = 4.31%
# Yield Curve Spread = ^TNX - ^IRX (proxy 10Y-3M, valide Fed recession model)
```

---

## 📡 SOURCES SCRAPING — URLS EXACTES

```python
# FX (Google Finance)
FX_SOURCES = {
    "USD_EUR": "https://www.google.com/finance/quote/USD-EUR",
    "USD_HKD": "https://www.google.com/finance/quote/USD-HKD",
}

# RSS News (feedparser)
RSS_SOURCES = {
    1: {"url": "https://feeds.reuters.com/reuters/businessNews",              "region": "GLOBAL", "lang": "EN"},
    2: {"url": "https://apnews.com/hub/financial-markets?format=rss",         "region": "USA",    "lang": "EN"},
    3: {"url": "https://feeds.marketwatch.com/marketwatch/topstories",        "region": "USA",    "lang": "EN"},
    4: {"url": "https://www.scmp.com/rss/91/feed",                            "region": "ASIE",   "lang": "EN"},
    5: {"url": "https://asia.nikkei.com/rss/feed/news",                       "region": "ASIE",   "lang": "EN"},
    6: {"url": "https://www.ft.com/rss/home/international",                   "region": "EU",     "lang": "EN"},
    7: {"url": "https://www.lesechos.fr/rss/rss_marches.xml",                 "region": "EU",     "lang": "FR"},
}

# Rotation horaire (Reuters #1 toujours inclus)
RSS_ROTATION = {
    8:[2,4], 9:[3,6], 10:[2,5], 11:[3,7], 12:[2,6], 13:[3,4],
    14:[2,5], 15:[3,6], 16:[2,7], 17:[3,4], 18:[2,6], 19:[3,5],
    20:[2,4], 21:[3,6], 22:[2,5], 23:[3,4],
}

# Calendar scraping (08h00 uniquement)
CALENDAR_SOURCES = {
    "macro":    "https://www.marketwatch.com/economy-politics/calendar",
    "earnings": "https://stockanalysis.com/earnings-calendar/",
}

# Macro officiel
MACRO_OFFICIAL = {
    "fed":  "https://www.federalreserve.gov/feeds/press_all.xml",
    "bls":  "https://www.bls.gov/feed/eag.rss",
    "ecb":  "https://www.ecb.europa.eu/rss/press.html",
}
```

---

## ⚙️ DÉPLOIEMENT AUTOMATIQUE — GitHub Actions + Cloudflare Pages

**Architecture complète (zéro serveur, zéro coût mensuel) :**
```
GitHub Actions → lance main.py selon cron → commit output/index.html + sainhe.db
Cloudflare Pages → détecte le commit → déploie index.html sur SAINHE.com
```

**Fichier `.github/workflows/sainhe.yml` :**
```yaml
name: SAINHE Auto-Update
on:
  schedule:
    - cron: '0 7-22 * * 1-5'  # news : 8h-23h CET (=7h-22h UTC) lun-ven
    - cron: '0 22 * * 1-5'    # data : 22h UTC = après clôture NYSE (18h EDT)
  workflow_dispatch:            # lancement manuel possible

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python main.py
      - name: Commit changes
        run: |
          git config user.name "SAINHE Bot"
          git config user.email "bot@sainhe.com"
          git add output/index.html db/sainhe.db cache/
          git commit -m "Auto-update $(date -u '+%Y-%m-%d %H:%M UTC')" || exit 0
          git push
```

**Logique dans main.py selon l'heure :**
```python
from datetime import datetime, timezone

def run():
    now = datetime.now(timezone.utc)
    hour = now.hour

    # Toujours : news + render
    fetch_news.run()
    render_html.run()

    # Seulement à 22h UTC (après clôture NYSE) : full data pipeline
    if hour == 22:
        fetch_prices.run()    # yfinance OHLCV
        fetch_indices.run()   # indices + ^TNX + ^IRX
        fetch_fx.run()        # taux USD/EUR + USD/HKD
        calc.run()            # OBV, MFI, DMA, Momentum, Sentiment, R-Perf
        render_html.run()     # re-render avec les nouvelles données
```

**Coûts finaux :**
| Service | Coût |
|---|---|
| GitHub (repo privé + Actions) | Gratuit |
| Cloudflare Pages | Gratuit |
| SAINHE.com (domaine) | ~10€/an |
| **Total mensuel** | **0€** |

---

## 📊 FORMULES CLÉS — COPIER-COLLER DIRECT

```python
# Var% J-1
var_j1 = (close[-1] - close[-2]) / close[-2] * 100

# RVOL 20J
avg_vol_20 = volume[-20:].mean()
rvol = volume[-1] / avg_vol_20 * 100

# OBV (cumulatif)
import numpy as np
direction = np.where(close > close.shift(1), 1, np.where(close < close.shift(1), -1, 0))
obv = (volume * direction).cumsum()

# OBV Delta J-1
obv_delta = volume[-1] if close[-1] > close[-2] else -volume[-1] if close[-1] < close[-2] else 0

# RVOL Directionnel (signal clé Box 4)
rvol_dir = obv_delta / avg_vol_20 * 100

# OBV Direction 20J
obv_dir = "RISING" if obv[-1] > obv[-20] else "FALLING"

# MFI 14J (ou pandas_ta.mfi())
tp = (high + low + close) / 3
mf = tp * volume
pos_mf = mf.where(tp > tp.shift(1), 0).rolling(14).sum()
neg_mf = mf.where(tp < tp.shift(1), 0).rolling(14).sum()
mfi = 100 - (100 / (1 + pos_mf / neg_mf))

# Sentiment Score (-1.0 à +1.0)
def sentiment(mfi, obv_dir, close, dma_200):
    if mfi > 70 and obv_dir == "RISING" and close > dma_200:
        return round(0.5 + (mfi - 70) / 60, 2)   # +0.5 à +1.0
    elif mfi < 30 and obv_dir == "FALLING" and close < dma_200:
        return round(-0.5 - (30 - mfi) / 60, 2)   # -0.5 à -1.0
    else:
        return round((mfi - 50) / 100, 2)           # interpolation neutre

# ERP
erp = (1 / pe_gspc) - (tnx_yield / 100)

# Yield Curve
yield_spread = tnx_yield - irx_yield
def yield_signal(spread, prev_spread):
    if spread < 0 and prev_spread >= 0: return "DÉSINVERSION"
    if spread < 0:                      return "INVERSÉE"
    return                              "NORMALE"

# R-Perf
rperf = momentum_region - momentum_monde  # même secteur, même période
golden_alpha = 1 if rperf > 0 and momentum_1y_region > tnx_yield else 0

# Conversion devise
valeur_affichee = valeur_usd * taux_fx_j1
```

---

## 🔄 LOGIQUE WEEKEND / JOURS FÉRIÉS

```python
import holidays
from datetime import datetime, timedelta

def is_market_day():
    today = datetime.now()
    if today.weekday() >= 5: return False
    if today.date() in holidays.country_holidays('US'): return False
    return True

# main.py vérifie is_market_day() avant chaque run
# FULL mode (lun-ven) : fetch toutes les heures 08h-23h
# WEEKEND mode : Reuters + FT uniquement, 1x/jour à 09h00
```

---

## 🗂️ SENTIMENT SCORE — TABLE DE VÉRITÉ

| Score | Label | MFI 14J | OBV Dir 20J | Prix vs 200DMA |
|---|---|---|---|---|
| +0.6 à +1.0 | Euphoric Bullish | > 70 | RISING | Au-dessus |
| +0.1 à +0.5 | Accumulation | 40-70 | RISING | Proche/Au-dessus |
| 0 | Neutral | 40-70 | Flat | ≈ 200DMA |
| -0.1 à -0.5 | Caution | 30-50 | FALLING | En-dessous |
| -0.6 à -1.0 | Extreme Bearish | < 30 | FALLING | En-dessous |

## 3 LOIS ETF BOX 4

| Loi | Condition | Signal |
|---|---|---|
| DMA CROSS | OBV FALLING + Prix > 200DMA | ⚠️ FALSE BREAKOUT |
| RVOL CONFIRM | RVOL Dir > +120% + OBV RISING + Prix > 200DMA | 🟢 INSTITUTIONAL CONFIRM |
| DIVERGENCE | Sentiment > +0.3 + R-Perf < -1% | 🟠 SECTOR DIVERGENCE |

---

# SAINHE — Notes de projet détaillées
> Ce qui suit est la documentation complète. Lire ci-dessus pour coder.

---

## 🏗️ Projet en cours : Newsletter HTML quotidienne

### Décisions validées
- ~~**Données** : FMP MCP~~ → **ABANDONNÉ**
- **Gemini / toute IA générative** → **ABANDONNÉ** — remplacé par RSS scraping + templates Jinja2. Ne jamais l'intégrer.
- **Fetch prix/volumes** : `yfinance` lib Python — simple, fiable, maintenu
- **Stack** : Python + Jinja2 + Chart.js (CDN) — page HTML statique
- **Architecture** : Cache-first — HTML généré une fois, lu par tous les users
- **Scheduler** : GitHub Actions cron (gratuit) — pas de serveur, pas de VPS
- **Hosting** : Cloudflare Pages (gratuit) — connecté au repo GitHub, deploy auto à chaque commit
- **Langues** : EN (défaut) | FR | DE | ES | ZH | RU | JA — sélecteur dans le header
- **Devises affichées** : USD | EUR | HKD — taux Google Finance scraping J-1
- **Devise de base interne** : USD — conversion à l'affichage uniquement, jamais stocké en EUR/HKD
- **RVOL standard** : 20J partout — Bloomberg standard
- **Box 2 RVOL Speed** : collecte horaire pendant sessions de marché
- **Box 4** : Sentiment Score ETF sectoriels — 100% OHLCV calculé Python
- **Box 5** : Bandeau macro fixe — ERP + Yield Curve + VIX (3 chiffres, zéro box dédiée)
- **Box 1 news** : RSS scraping multi-sources + affichage headline brut style stockanalysis.com

---

## 🌐 INTERNATIONALISATION — Langues & Devises

### Langues (7)
| Code | Langue | Marché cible |
|---|---|---|
| EN | Anglais | Défaut — international |
| FR | Français | France, Suisse, Belgique |
| DE | Allemand | Allemagne, Autriche, Suisse |
| ES | Espagnol | Espagne, Amérique latine |
| ZH | Chinois simplifié | Chine, diaspora |
| RU | Russe | Russie, ex-URSS |
| JA | Japonais | Japon |

### Devises (3)
| Devise | Symbole | Usage | Taux source |
|---|---|---|---|
| USD | $ | Devise interne — toutes les données stockées en USD | — |
| EUR | € | Affichage Europe | Google Finance scraping (google.com/finance/quote/USD-EUR) |
| HKD | HK$ | Affichage Asie | Google Finance scraping (google.com/finance/quote/USD-HKD) |

**Règle d'or** : on ne stocke jamais EUR ni HKD en base.
Toute valeur en base = USD. La conversion se fait uniquement au moment du rendu HTML.
`valeur_affichée = valeur_USD × taux_BCE_J1`

---

## 🔄 PIPELINE FETCH — Structure de double vérification

```
FETCH PIPELINE — FULL YFINANCE SCRAPING
========================================

⚠️ RÈGLE ABSOLUE : ZÉRO API — FULL SCRAPING UNIQUEMENT
Aucune clé API. Aucun compte payant. Tout est scrapé depuis des pages web publiques.
Les données sont stockées dans sainhe.db — on ne dépend d'aucun fournisseur externe.

ÉTAPE 1 — FETCH PRIMAIRE (scraping Yahoo Finance HTML)
├── Source       : Yahoo Finance — pages HTML scraping (pas l'API yfinance)
├── URL pattern  : https://finance.yahoo.com/quote/{TICKER}/history/
├── Données      : AdjClose, Volume, High, Low, Open
├── Beta / 52W   : https://finance.yahoo.com/quote/{TICKER}/
├── Fréquence    : Quotidien après clôture marché (J-1)
├── Output       : fetch_primary_{YYYY-MM-DD}.json
└── Statut       : ✅ si données reçues / ❌ si timeout ou ticker manquant

ÉTAPE 2 — FETCH SECONDAIRE (cross-check scraping)
├── Source US/ETF  : stockanalysis.com — scraping HTML
├── Source EU .DE  : boerse-frankfurt.de — scraping HTML
├── Source HK .HK  : hkex.com.hk — scraping HTML
├── Données checkées : AdjClose uniquement (le plus critique)
├── Fréquence      : Même run que primaire
├── Output         : fetch_secondary_{YYYY-MM-DD}.json
└── Statut         : ✅ / ⚠️ / ❌ par ticker

ÉTAPE 3 — COMPARAISON & VALIDATION
├── Tolérance      : < 2%  → ✅ ACCEPTED  → écriture en base
│                   2–5%  → ⚠️ WARNING   → log + écriture en base
│                   > 5%  → ❌ REJECTED  → fallback J-2 + alerte
├── Log            : cache/validation_{YYYY-MM-DD}.json
└── Rapport        : 1 ligne par ticker (ticker | primary | secondary | delta | status)

ÉTAPE 4 — FETCH MACRO (quotidien — Box 1)
├── Source calendrier : investing.com/economic-calendar — scraping HTML
├── Source consensus  : investing.com même page (consensus affiché en clair)
├── Données           : Events High-Impact, Consensus, Valeur actuelle, Delta bps
├── Fréquence         : 08h00 pré-marché + 1x/heure si event dans la journée
└── Pas de double-check (source unique de référence pour le macro)

ÉTAPE 5 — FETCH TAUX DE CHANGE
├── Source      : Google Finance — scraping HTML
│               URL : https://www.google.com/finance/quote/USD-EUR
│               URL : https://www.google.com/finance/quote/USD-HKD
├── Paires      : USD/EUR, USD/HKD
├── Fréquence   : 1x/jour, même run que fetch primaire
├── Stockage    : taux en base table fx_rates (pas recalculé à chaque affichage)
└── Règle       : si scraping échoue → taux J-2 en cache, log alerte

ÉTAPE 6 — ÉCRITURE EN BASE (sainhe.db)
├── Condition   : uniquement si étape 3 = ✅ ou ⚠️
├── Devise      : USD uniquement en base — jamais EUR ni HKD stockés
├── Tables      : prices | macro_events | fx_rates
└── Trigger     : render_html.py lancé automatiquement après écriture

RÉSUMÉ FRÉQUENCES
├── Quotidien   : Toutes les étapes
├── Mensuel     : Aucun (étape méta ETF supprimée)
└── Archive     : fetch logs conservés 90 jours dans cache/archive/
```

---

## 📡 SOURCE MACRO — Calendrier économique (Option 3B)

investing.com abandonné (JS trop agressif, détection bot quasi-certaine).

### Trois alternatives scrapables sans Playwright

| Source | Scrapable ? | Données dispo | Fiabilité |
|---|---|---|---|
| **federalreserve.gov** | ✅ HTML statique | Calendrier Fed, minutes FOMC, décisions taux | ⭐⭐⭐ officiel |
| **bls.gov** (Bureau Labor Statistics) | ✅ HTML statique | CPI, NFP, unemployment — calendrier de release | ⭐⭐⭐ officiel |
| **ecb.europa.eu** | ✅ HTML statique | Décisions BCE, calendrier réunions | ⭐⭐⭐ officiel |
| **forexfactory.com** | ⚠️ JS partiel | Calendrier macro complet mondial, impact High/Med/Low | ⭐⭐ bon mais JS |
| **marketwatch.com/economy-politics/calendar** | ✅ HTML lisible | Calendrier US + consensus visible | ⭐⭐ bon |

### Recommandation retenue : sources officielles + marketwatch

```
MACRO PIPELINE
├── Fed/BCE/BoJ events   → scraping sites officiels (HTML statique, ultra stable)
├── CPI/NFP/PPI dates    → scraping bls.gov / eurostat.ec.europa.eu (HTML statique)
├── Consensus + résultat → scraping marketwatch.com/economy-politics/calendar
└── Fallback             → cache J-1 si scraping échoue
```

**Avantage décisif** : les sites gouvernementaux ne changeront jamais leur HTML agressivement — ce sont les sources les plus stables qui existent. marketwatch pour le consensus car affiché en HTML clair.

**Limite** : pas de couverture Asie-Pacifique aussi complète. Pour les events BOJ/PBOC, scraping de leur site officiel respectif.

---

## 📋 PAGE 2 — STOCK PICKING (Box 4 déplacée)

Box 4 (analyst recommendations, OBV, MFI, target price) est incompatible avec des ETFs.
Déplacée en Page 2 — appliquée aux **actions individuelles** de la watchlist.

### Sources Page 2 Stock Picking

| Donnée | Source |
|---|---|
| Financials (Revenue, EPS, marges) | EDGAR — SEC XBRL (HTML statique, gratuit, officiel) |
| Analyst recommendations | stockanalysis.com/stocks/{ticker}/ |
| Target price High/Low/Mean | stockanalysis.com/stocks/{ticker}/forecast/ |
| OBV / MFI / DMA | Calculé depuis série yfinance en base |
| Insider transactions | EDGAR Form 4 scraping |
| Beat/Miss historique 8Q | stockanalysis.com/stocks/{ticker}/financials/ |

### Pourquoi EDGAR est une mine d'or
- Données officielles déposées à la SEC — zéro risque légal
- HTML/XBRL statique — scraping trivial, jamais bloqué
- Revenue, EPS, Free Cash Flow, Debt — tout y est
- Insider buying/selling (Form 4) — signal smart money direct
- Fonctionne pour toutes les sociétés cotées US (y compris les holdings des ETFs)
├── config.py
├── db_init.py          ← CREATE TABLEs + INSERT 13 tickers de test
├── fetch_yahoo.py
├── fetch_edgarfiles.py
├── db/
│   └── sainhe.db
├── cache/
├── calc.py
├── generate_news.py
├── Mainpage - dashboard/
│   ├── box_01_news.py
│   ├── box_02_indices.py
│   ├── box_03_sectors.py
│   ├── box_04_analysis.py
│   ├── box_05_macro.py
│   └── box_06_portfolio.py
├── Stock analysis/
├── valueivestorsclub/
├── Timetable + lexique/
├── render_html.py
└── main.py

output/
├── index.html
└── assets/
    ├── style.css
    ├── main.js
    └── charts.js




-------------------------------------------------------------------------------------------------------------------------------------------------------
PAGE 1:

### Design validé
- Style crème/beige luxe (inspiré Financial Times / Apple)
- Mode sombre toggle (bouton dans le header)
- Mini graphiques dans les boxes sectorielles
- Sélecteur de langue dans le header : **EN par défaut**, FR DE ES ZH RU JA

#################################### Contenu page principale (à coder)##################################


**BOX 1 — Fil d'actualité marché (style stockanalysis.com)**
================================================================================
SAINHE - BLUEPRINT OFFICIEL : BOX 1 (NEWS FEED RSS + CALENDAR SCRAPING)
================================================================================

CONCEPT :
Agrégateur de news financières scrapées depuis des flux RSS publics.
Zéro IA, zéro réécriture. Headline brut + source + temps + badge région/ticker.
1 fetch par heure, 8h00–23h00 lun-ven. Purge automatique à 7 jours glissants.

--------------------------------------------------------------------------------
1. LES 7 SOURCES — CLASSÉES PAR FIABILITÉ RSS
--------------------------------------------------------------------------------

RÈGLE : toutes ces sources ont un flux RSS public stable, parseable avec
feedparser sans authentification, et sans rendu JavaScript requis.

┌────┬──────────────────┬─────────────────────────────────────────────────────┬────────┬──────────┐
│ #  │ Source           │ URL RSS                                             │ Région │ Langue   │
├────┼──────────────────┼─────────────────────────────────────────────────────┼────────┼──────────┤
│ 1  │ Reuters Business │ feeds.reuters.com/reuters/businessNews              │ GLOBAL │ EN       │
│ 2  │ AP News Business │ apnews.com/hub/financial-markets?format=rss         │ USA    │ EN       │
│ 3  │ MarketWatch      │ feeds.marketwatch.com/marketwatch/topstories        │ USA    │ EN       │
│ 4  │ South China MP   │ scmp.com/rss/91/feed                                │ ASIE   │ EN       │
│ 5  │ Nikkei Asia      │ asia.nikkei.com/rss/feed/news                       │ ASIE   │ EN       │
│ 6  │ Financial Times  │ ft.com/rss/home/international                       │ EUROPE │ EN       │
│ 7  │ Les Echos        │ lesechos.fr/rss/rss_marches.xml                     │ EUROPE │ FR       │
└────┴──────────────────┴─────────────────────────────────────────────────────┴────────┴──────────┘

Notes techniques par source :
- Reuters #1 : le plus fiable. Feed bien structuré, items complets, fréquence élevée.
- AP #2 : headlines propres, pas de contenu tronqué, couverture US solide.
- MarketWatch #3 : focus US marchés, très réactif sur earnings et macro.
- SCMP #4 : meilleure source Asie/HK anglophone avec RSS stable.
- Nikkei #5 : Japon + Asie, parfois 1-2h de délai vs événement réel.
- FT #6 : contenu tronqué pour abonnés mais headline + lead toujours présents.
- Les Echos #7 : en français — à utiliser pour la version FR de la page uniquement.

--------------------------------------------------------------------------------
2. ROTATION HORAIRE PAR RÉGION — LOGIQUE DE FETCH
--------------------------------------------------------------------------------

Reuters (#1) est fetchée TOUTES les heures — c'est la colonne vertébrale globale.
Les 6 autres tournent selon un cycle fixe par heure (heure CET) :

```python
ROTATION = {
    # heure_CET : [source_index_a_fetcher_en_plus_de_reuters]
    8:  [2, 4],   # AP + SCMP   → ouverture EU, marchés Asie encore actifs
    9:  [3, 6],   # MarketWatch + FT → ouverture EU officielle
    10: [2, 5],   # AP + Nikkei
    11: [3, 7],   # MarketWatch + Les Echos
    12: [2, 6],   # AP + FT
    13: [3, 4],   # MarketWatch + SCMP
    14: [2, 5],   # AP + Nikkei → ouverture USA approche
    15: [3, 6],   # MarketWatch + FT → ouverture NYSE
    16: [2, 7],   # AP + Les Echos
    17: [3, 4],   # MarketWatch + SCMP → fermeture EU
    18: [2, 6],   # AP + FT
    19: [3, 5],   # MarketWatch + Nikkei
    20: [2, 4],   # AP + SCMP
    21: [3, 6],   # MarketWatch + FT → clôture NYSE approche
    22: [2, 5],   # AP + Nikkei → marchés Asie rouvrent
    23: [3, 4],   # MarketWatch + SCMP → post-marché US
}
# Reuters toujours ajouté automatiquement : sources_du_tour = [1] + ROTATION[heure]
```

Résultat : 3 sources fetchées par heure (Reuters + 2 régionales), couverture
équilibrée GLOBAL / USA / EUROPE / ASIE sur la journée complète.

--------------------------------------------------------------------------------
3. FORMAT D'AFFICHAGE — UNE LIGNE PAR ITEM
--------------------------------------------------------------------------------

Format exact pour le template Jinja2 :

  [HH:MM]  [BADGE]  Headline complet de l'article  (Source)

Exemples :
  10:32  🇺🇸 $NVDA   Nvidia beats Q1 EPS $5.98 vs $5.58 estimate  (Reuters)
  09:15  🌍 MACRO    US CPI March 3.4% — consensus 3.1%  (AP News)
  08:45  🇪🇺 $ASML   ASML raises 2026 guidance on strong bookings  (FT)
  08:00  🇨🇳 MACRO   PBOC holds LPR rate at 3.1%  (SCMP)

Règles badge :
- Si headline contient ticker watchlist → badge ticker  ($NVDA)
- Sinon → badge région selon source  (🌍 GLOBAL | 🇺🇸 USA | 🇪🇺 EU | 🇨🇳 ASIE)
- "MACRO" si mot-clé macro détecté (CPI, Fed, BCE, NFP, GDP, taux, rate, inflation)
- Lien cliquable vers article original, target="_blank"
- Heure = pubDate du flux RSS, pas heure de fetch

--------------------------------------------------------------------------------
4. SECTION FIXE — TOP 3 EVENTS DU JOUR (08h00 uniquement)
--------------------------------------------------------------------------------

Générée une seule fois à 08h00 depuis deux scrapes :

Source A : marketwatch.com/economy-politics/calendar
  → extraire les events du jour avec tag "High" importance
  → champs : heure | nom_event | valeur_consensus

Source B : stockanalysis.com/earnings-calendar/
  → extraire earnings du jour pour tickers de la watchlist uniquement
  → champs : heure | ticker | est_EPS | est_Revenue

Sélection : max 3 items, priorité Earnings watchlist > Macro High > autres
Statique jusqu'à 08h00 du lendemain

```
┌──────────────────────────────────────────────┐
│  ⚠️  EVENTS DU JOUR — 03/04/2026            │
│  14:30  MACRO  CPI US Mars (Est: 3.1%)      │
│  16:00  MACRO  Powell — Senate Testimony    │
│  22:00  $NVDA  Earnings (Est EPS: $5.58)    │
└──────────────────────────────────────────────┘
```

--------------------------------------------------------------------------------
5. STOCKAGE ET PURGE — FENÊTRE GLISSANTE 7 JOURS
--------------------------------------------------------------------------------

```
cache/news/
├── news_2026-04-03.json   ← aujourd'hui (append 1x/heure)
├── news_2026-04-02.json   ← J-1
├── news_2026-04-01.json   ← J-2
├── ...
└── news_2026-03-27.json   ← J-7 (supprimé au prochain run du 04/04)
```

Logique de purge à chaque run :
```python
# À exécuter en début de chaque fetch horaire
cutoff = today - timedelta(days=7)
for f in glob("cache/news/news_*.json"):
    file_date = date.fromisoformat(f.stem.replace("news_", ""))
    if file_date < cutoff:
        os.remove(f)
```

Structure d'un item JSON :
```json
{
  "published": "2026-04-03T10:32:00",
  "source": "Reuters",
  "region": "GLOBAL",
  "ticker": "NVDA",
  "badge": "$NVDA",
  "headline": "Nvidia beats Q1 EPS $5.98 vs $5.58 estimate",
  "url": "https://reuters.com/...",
  "fetched_at": "2026-04-03T10:35:00"
}
```

Deduplication : avant append, vérifier que `url` n'existe pas déjà dans
le fichier du jour. Si doublon → skip silencieux.

--------------------------------------------------------------------------------
5b. WEEKEND ET JOURS FÉRIÉS — MODE RÉDUIT
--------------------------------------------------------------------------------

En semaine  : fetch toutes les heures de 08h00 à 23h00 (15 fetches/jour)
Weekend     : fetch 1x/jour à 09h00 uniquement — Reuters + FT uniquement
Jours fériés: même logique que weekend

```python
from datetime import datetime
import holidays

EU_HOLIDAYS = holidays.country_holidays('US')  # adapter par marché cible

def is_market_day():
    today = datetime.now()
    if today.weekday() >= 5:   # samedi=5, dimanche=6
        return False
    if today.date() in EU_HOLIDAYS:
        return False
    return True

def get_fetch_mode():
    if is_market_day():
        return "FULL"    # rotation complète 7 sources, 1x/heure 08h-23h
    else:
        return "WEEKEND" # Reuters + FT uniquement, 1x/jour à 09h00

# Dans run() :
mode = get_fetch_mode()
if mode == "WEEKEND":
    now = datetime.now()
    if now.hour != 9 or now.minute > 5:
        return  # on n'est pas dans la fenêtre de fetch weekend → exit
    sources_du_tour = [1, 6]  # Reuters + FT uniquement
else:
    sources_du_tour = [1] + ROTATION[now.hour]
```

Comportement affiché côté utilisateur en mode WEEKEND :
- Le fil de news affiche les items existants du cache (J-1 à J-7)
- Un badge discret indique : `Mode weekend — prochaine mise à jour lundi 08h00`
- TOP 3 EVENTS non générée (aucun calendrier économique le weekend)
- La box n'est jamais vide grâce au cache 7 jours

```python
# Jours fériés à installer : pip install holidays
# Librairie 'holidays' couvre US, EU, FR, DE, UK, JP, HK, CN etc.
# Configurer selon les marchés couverts par SAINHE
```

--------------------------------------------------------------------------------
6. ARCHITECTURE FICHIER box_01_news.py
--------------------------------------------------------------------------------

```
box_01_news.py
│
├── SOURCES = { dict des 7 sources avec URL + région + langue }
├── ROTATION = { dict heure → [indices sources] }   ← jours ouvrés seulement
│
├── is_market_day()       ← weekday + holidays check
├── get_fetch_mode()      ← retourne "FULL" ou "WEEKEND"
│
├── fetch_rss(source_id)
│     └── feedparser.parse(url)
│     └── retourne liste de {published, headline, url, source, région}
│
├── match_ticker(headline, watchlist)
│     └── regex sur headline pour détecter tickers
│     └── retourne ticker ou None
│
├── classify_macro(headline)
│     └── keywords = ["CPI", "Fed", "BCE", "NFP", "GDP", "rate", "inflation", ...]
│     └── retourne True/False
│
├── dedup_and_append(items, date)
│     └── charge cache/news/news_{date}.json
│     └── filtre les urls déjà présentes
│     └── append + save
│
├── purge_old_files()
│     └── supprime fichiers > 7 jours
│
├── fetch_calendar_08h()
│     └── appelé seulement si mode FULL ET heure == 08h00
│     └── scrape marketwatch calendar + stockanalysis earnings
│     └── retourne top 3 events du jour
│     └── save cache/events_today.json
│
└── run()
      └── mode = get_fetch_mode()
      └── si WEEKEND → vérifier heure == 09h00, sources = [1, 6], exit sinon
      └── si FULL    → sources = [1] + ROTATION[heure_courante]
      └── pour chaque source → fetch_rss → match_ticker → classify
      └── dedup_and_append
      └── purge_old_files
      └── si FULL ET 08h00 → fetch_calendar_08h
```

--------------------------------------------------------------------------------
7. SÉCURITÉ
--------------------------------------------------------------------------------
- Si flux RSS indisponible → log warning, skip silencieux, continuer les autres sources
- Headline affiché mot pour mot — aucune modification, aucun résumé
- Source toujours citée et cliquable
- Aucune IA impliquée à aucune étape





**box 2: tableau indices mondiaux**

OBJECTIF : 
Déterminer la santé globale du marché (Top-Down). 
Identifier si les mouvements de prix sont soutenus par une réelle conviction 
institutionnelle ou s'il s'agit de manipulations de faible liquidité.

--------------------------------------------------------------------------------
INDICES À SURVEILLER (SOURCE : yfinance)
--------------------------------------------------------------------------------
Les 13 indices de la sheet Excel `tickers globaux` — liste définitive.

--------------------------------------------------------------------------------
STRUCTURE DU TABLEAU (COLONNES)
--------------------------------------------------------------------------------

COLONNE 1 : INDEX & TICKER
- Nom de l'indice + Sparkline Adjusted Close sur 7 jours calendaires.

COLONNE 2 : LAST PRICE & % DAY
- Adjusted Close J-1 (clôture veille) + Variation journalière J-1 vs J-2.
- ⚠️ PAS de temps réel — données J-1 post-clôture uniquement.

COLONNE 3 : 52-WEEK RANGE (PSYCHOLOGIE DE MARCHÉ)
- Visualisation : [L ---------|--------- H]
- Position du prix actuel par rapport aux extrêmes de l'année.
- Formule : (AdjClose - 52wLow) / (52wHigh - 52wLow) × 100
- Utilité : Détecter les essoufflements (proche du High) ou les capitulations (proche du Low).

COLONNE 4 : RVOL (RELATIVE VOLUME)
- Formule : Volume J-1 / Avg Volume 20J  ← standard Bloomberg 20J
- Seuil Alerte : Gras si RVOL > 1.2.
- Si volume_disponible = NON (VIX, DXY) : afficher "N/A"

COLONNE 5 : RVOL SPEED (URGENCE 1H)
- Formule : Volume heure courante / (Volume quotidien cumulé / heures écoulées depuis ouverture)
- Source : collecte horaire yfinance pendant sessions (voir archi 2B)
- Signal : ⚡ si volume dernière heure > 2x moyenne horaire du jour
- Si volume_disponible = NON : afficher "N/A"

COLONNE 6 : SMART MONEY BIAS (SYNTHÈSE FINALE)
Combinaison RVOL 20J + RVOL Speed + direction du prix :

- [🟢 INSTITUTIONAL BUY]  : Prix ↑ + RVOL(20j) > 1.2 + RVOL Speed ↑
  → Achat massif et coordonné

- [⚠️ WEAK RALLY]         : Prix ↑ + RVOL(20j) < 0.8
  → Hausse fragile, manque d'acheteurs

- [⚠️ SPECULATIVE SPIKE]  : Prix ↑ + RVOL(20j) < 0.8 + RVOL Speed > 2.0
  → Hausse soudaine sur faible volume global — feu de paille

- [🔴 DISTRIBUTION]       : Prix ↓ + RVOL(20j) > 1.2
  → Vente institutionnelle massive

- [🔴 PANIC EXIT]         : Prix ↓ + RVOL Speed > 2.5
  → Liquidation immédiate en cours

- [⚪ THIN SLIDE]         : Prix ↓ + RVOL(20j) < 0.8
  → Dérive baissière par manque d'intérêt

- [🟡 NEUTRAL]            : RVOL entre 0.8 et 1.2, pas de signal Speed
  → Activité normale

- [➖ NO DATA]            : volume_disponible = NON (VIX, DXY)
  → Afficher prix uniquement

--------------------------------------------------------------------------------
LE "SENTIMENT HUB" (PIED DE BOX)
--------------------------------------------------------------------------------
- VIX : Adjusted Close J-1 uniquement (pas de volume).
    * < 15 : Complaisance — vigilance.
    * 15-30 : Zone normale.
    * > 30 : Panique — opportunité potentielle.
- DXY : Adjusted Close J-1 uniquement (pas de volume — indice Forex 24h/24).
    * DXY ↑ : Pression baissière sur indices mondiaux.
    * DXY ↓ : Soutien haussier pour indices mondiaux.

--------------------------------------------------------------------------------
SÉCURITÉ ANTI-BIAIS
--------------------------------------------------------------------------------
- Si volume_disponible = NON → Smart Money Bias = "N/A", jamais estimé.
- Aucune adjectivation — les labels et couleurs suffisent.
- Si données yfinance manquantes pour un indice → afficher "DATA UNAVAILABLE".
================================================================================





**BOX 3 — Secteurs par zone géographique** ✅ VALIDÉ
  ================================================================================
SAINHE - BLUEPRINT OFFICIEL : BOX 3 (DYNAMIC REGIONAL SECTOR ROTATION)
================================================================================

CONCEPT : 
Analyse de la force relative des 16 secteurs SAINHE par zone géographique. 
Objectif : Identifier où l'argent circule réellement (Alpha) par rapport au 
marché mondial et au rendement sans risque (Risk-Free).
Si un secteur n'existe pas pour une région donnée → case vide, pas d'extrapolation.

--------------------------------------------------------------------------------
1. PROTOCOLE D'ACQUISITION DES DONNÉES (yfinance)
--------------------------------------------------------------------------------
- SOURCE : yfinance — AdjClose des ETFs de la sheet "Tickers Sectoriels par region"
- DATA POINTS REQUIS :
    * AdjClose série historique par ETF régional (Momentum 1M/3M/1Y/2Y calculés en base)
    * AdjClose série historique par ETF mondial MSCI (benchmark de référence)
    * Risk-Free Rate : ^TNX (US Treasury 10Y Yield) — yfinance, J-1

--------------------------------------------------------------------------------
2. LOGIQUE DE CALCUL ET ÉLIMINATION DES BIAIS
--------------------------------------------------------------------------------
Pour chaque secteur dans la zone sélectionnée (USA | Europe | Asie | Monde) :

A. PERFORMANCE RELATIVE (R-Perf) :
   Formule : Momentum_T_Région(Secteur) − Momentum_T_Monde(Secteur)
   Périodes T : Today (Var% J-1) | 1M | 3M | 1Y | 2Y
   → Colonne R-Perf définie dans sheet "colonnes à fetch.calculer"

B. VALIDATION RISK-FREE (RF-Check) :
   Condition : Momentum_1Y_Région(Secteur) > ^TNX Yield J-1
   → OUI = Golden Alpha possible | NON = secteur ne bat pas le cash

--------------------------------------------------------------------------------
3. RÈGLES D'AFFICHAGE ET TRI DYNAMIQUE
--------------------------------------------------------------------------------
- TRI AUTOMATIQUE : Secteurs classés par R-Perf décroissant sur la période sélectionnée.
- Si secteur absent pour une région → ligne vide, label "—", pas de calcul.

- CODES COULEURS :
    * Vert pastel : R-Perf > +0.1% (surperformance)
    * Orange pastel : R-Perf < -0.1% (sous-performance)
    * Gris : neutre (−0.1% ≤ R-Perf ≤ +0.1%)

- BORDURE DORÉE (GOLDEN ALPHA) :
    * Condition : R-Perf > 0 ET RF-Check = OUI
    * Signification : le secteur bat le monde ET bat le cash (^TNX)

--------------------------------------------------------------------------------
4. CONTENU VISUEL — SÉLECTEURS DYNAMIQUES
--------------------------------------------------------------------------------
┌─────────────────────────────────────────────────────┐
│  [  USA  ]  [ Europe ]  [  Asie  ]  [  Monde  ]    │
├─────────────────────────────────────────────────────┤
│  Tech & Semis                              ↑        │
│  Robotics & MedTech                                 │
│  Healthcare & Pharma                                │
│  Finance & Transac.                                 │
│  Strategic Materials                                │
│  Energy                                             │
│  Defense & Aerospace                                │
│  EV & Clean Energy                                  │
│  Space                                              │
│  Luxury                                             │
│  Agriculture                                        │
│  Infra & Water                                      │
│  Consumer Staples                                   │
│  Digital Assets                                     │
│  Industrials                               ↓        │
│  Chemicals                                          │
├─────────────────────────────────────────────────────┤
│  [Today] [1M] [3M] [1Y] [2Y]                        │
└─────────────────────────────────────────────────────┘
Box dynamique — clic sur zone géographique + période

--------------------------------------------------------------------------------
5. SÉCURITÉ ET INTÉGRITÉ
--------------------------------------------------------------------------------
- Si yfinance retourne vide pour un ETF/période → afficher "DATA UNAVAILABLE"
- Si secteur absent de la région → afficher "—" (pas d'extrapolation)
- Cache : généré 1x/heure, servi statiquement (cache-first)



**BOX 4 — Sentiment Sectoriel (Grille 16 secteurs × 4 régions)**
================================================================================
SAINHE - BLUEPRINT OFFICIEL : BOX 4 (SENTIMENT SCORE PAR SECTEUR × RÉGION)
================================================================================

CONCEPT :
Grille de jauges Sentiment (−1.0 → +1.0) pour chaque secteur SAINHE par région.
Calculé 100% depuis les données de marché (OHLCV) — zéro opinion, zéro analyst.
Si secteur absent dans une région → cellule vide "—".

--------------------------------------------------------------------------------
1. DONNÉES REQUISES (toutes calculées depuis yfinance OHLCV en base)
--------------------------------------------------------------------------------
- Close / High / Low / Volume → déjà en base ✅
- 200 DMA → calculé depuis Close série ✅
- OBV → cumulatif directionnel Close × Volume
- OBV Direction 20J → RISING si OBV_J1 > OBV_J-20, sinon FALLING
- OBV Delta J-1 → +Volume si Close↑, −Volume si Close↓
- ★ RVOL Directionnel → OBV_Delta_J1 / AvgVolume_20J × 100
- MFI 14J → Money Flow Index (pandas_ta)
- Sentiment Score → combinaison des 3 ci-dessus

--------------------------------------------------------------------------------
2. ★ RVOL DIRECTIONNEL — LE SIGNAL CLÉ
--------------------------------------------------------------------------------
Formule : OBV_Delta_J1 / AvgVolume_20J × 100

Ce champ est unique : il combine RVOL (intensité) et OBV (direction).
Il répond à : "Hier, quelle proportion du volume moyen a été engagée, et dans quel sens ?"

Seuils :
- > +120% : 🟢 STRONG BUY PRESSURE — conviction institutionnelle forte
- +20 à +120% : 🟡 MILD BUY PRESSURE
- −20 à +20% : ⚪ NEUTRAL FLOW
- −20 à −120% : 🟠 MILD SELL PRESSURE
- < −120% : 🔴 STRONG SELL PRESSURE — distribution active

--------------------------------------------------------------------------------
3. SENTIMENT SCORE (−1.0 → +1.0)
--------------------------------------------------------------------------------
| Score        | Label             | MFI 14J   | OBV Dir | Prix vs 200DMA |
|--------------|-------------------|-----------|---------|----------------|
| +0.6 à +1.0  | 🟢 Euphoric Bullish | MFI > 70  | RISING  | Prix > 200DMA  |
| +0.1 à +0.5  | 🟡 Accumulation    | MFI 40-70 | RISING  | Proche/Au-dessus |
| 0            | ⚪ Neutral         | MFI 40-70 | Flat    | Prix ≈ 200DMA  |
| −0.1 à −0.5  | 🟠 Caution         | MFI 30-50 | FALLING | Prix < 200DMA  |
| −0.6 à −1.0  | 🔴 Extreme Bearish | MFI < 30  | FALLING | Prix < 200DMA  |

--------------------------------------------------------------------------------
4. 3 LOIS DE VÉRIFICATION (adaptées ETFs — remplace analyst Street)
--------------------------------------------------------------------------------
1. DMA CROSS LAW :
   SI OBV Direction = FALLING ET Prix > 200DMA
   → ⚠️ FALSE BREAKOUT : hausse non confirmée par le flux

2. RVOL CONFIRM LAW :
   SI RVOL Dir > +120% ET OBV = RISING ET Prix > 200DMA
   → 🟢 INSTITUTIONAL CONFIRM : conviction maximale

3. DIVERGENCE LAW (pont avec Box 3) :
   SI Sentiment Score > +0.3 ET R-Perf < −1%
   → 🟠 SECTOR DIVERGENCE : fort en absolu mais sous-performe vs monde

--------------------------------------------------------------------------------
5. VISUEL — GRILLE 16 × 4
--------------------------------------------------------------------------------
                    MONDE    USA    EUROPE    ASIE
Tech & Semis         🟢      🟢      🟡       🔴
Robotics & MedTech   🟡      🟢      ⚪       🟠
Healthcare           ⚪      🟡      🟠       🟡
Finance & Transac.   🟢      🟢       —       🔴
...
Chemicals            ⚪       —      🟠        —

Clic sur cellule → détail : MFI | OBV Dir | RVOL Dir | 200DMA | Lois actives

--------------------------------------------------------------------------------
6. SÉCURITÉ
--------------------------------------------------------------------------------
- Si OHLCV manquant pour un ticker/période → "DATA UNAVAILABLE"
- Si secteur absent d'une région → "—" (pas d'extrapolation)
- Toutes les lois désactivées si données insuffisantes (<14J d'historique)



**BOX 5 — Bandeau Macro Fixe**
================================================================================
SAINHE - BLUEPRINT OFFICIEL : BOX 5 (MACRO HEALTH — 3 INDICATEURS PERMANENTS)
================================================================================

CONCEPT :
Bandeau horizontal fixe toujours visible — pas une box scrollable.
Répond à une seule question : "Est-ce que le marché actions a du sens vs les alternatives ?"
Zéro IA, zéro narrative. 3 chiffres + 3 signaux couleur calculés Python pur.

Format affiché (inline dans le header ou pied de page) :
  ERP : +1.8%  🟡 CHER  |  Yield Curve : −0.3%  ⚠️ INVERSÉE  |  VIX : 18.2  ⚪ NORMAL

--------------------------------------------------------------------------------
1. INPUTS REQUIS
--------------------------------------------------------------------------------

| Champ | Ticker | Source Python | Note |
|---|---|---|---|
| PE Ratio S&P500 | ^GSPC | `yfinance.Ticker("^GSPC").info["trailingPE"]` | Donnée .info — pas OHLCV |
| 10Y Yield | ^TNX | yfinance AdjClose J-1 | AdjClose = taux en % (ex: 4.31) |
| 3M T-Bill | ^IRX | yfinance AdjClose J-1 | Proxy court terme Yield Curve |
| VIX | ^VIX | yfinance AdjClose J-1 | Niveau volatilité implicite |

^TNX et ^VIX → déjà dans `tickers globaux` ✅
^IRX → ajouté dans `tickers globaux` v6 ✅
PE Ratio → via `.info`, pas série historique — fetchable sans colonne dédiée

--------------------------------------------------------------------------------
2. CHAMPS DÉRIVÉS ET SIGNAUX
--------------------------------------------------------------------------------

A. EQUITY RISK PREMIUM (ERP)
   Earnings_Yield = 1 / PE_GSPC
   ERP = Earnings_Yield − (^TNX / 100)

   Signaux :
   - ERP > 2%  → 🟢 ATTRACTIF    (actions bien rémunérées vs obligations)
   - 1% < ERP ≤ 2% → 🟡 CHER    (prime de risque faible)
   - ERP ≤ 0%  → 🔴 IRRATIONNEL  (obligations rapportent plus que les bénéfices actions)

B. YIELD CURVE (10Y − 3M)
   Spread = ^TNX − ^IRX

   Signaux :
   - Spread > 0   → 🟢 NORMALE      (expansion économique)
   - Spread < 0   → ⚠️ INVERSÉE    (alerte récession 12-18 mois)
   - Spread remonte vers 0 après inversion → 🔴 DÉSINVERSION (souvent début de crise)

   Désinversion détectée si : spread_J1 > spread_J2 ET spread_J2 < 0

C. VIX
   Seuils :
   - VIX < 15  → ⚪ COMPLAISANCE  (vigilance — marché trop serein)
   - 15 ≤ VIX < 30 → 🟡 NORMAL
   - VIX ≥ 30  → 🔴 PANIQUE      (opportunité potentielle de rentrée)

--------------------------------------------------------------------------------
3. ORDRE DE CALCUL Python — box_05_macro.py
--------------------------------------------------------------------------------

```python
pe     = yf.Ticker("^GSPC").info.get("trailingPE")
tnx    = db.get_latest_adjclose("^TNX")
irx    = db.get_latest_adjclose("^IRX")
vix    = db.get_latest_adjclose("^VIX")
tnx_j2 = db.get_adjclose("^TNX", days_ago=2)
irx_j2 = db.get_adjclose("^IRX", days_ago=2)

ey     = (1 / pe)           if pe            else None
erp    = ey - (tnx / 100)   if ey and tnx    else None
spread = tnx - irx          if tnx and irx   else None
spread_prev = tnx_j2 - irx_j2 if tnx_j2 and irx_j2 else None

# Signaux — règles Python pures, zéro IA
erp_signal   = "ATTRACTIF" if erp and erp>0.02 else ("CHER" if erp and erp>0 else "IRRATIONNEL")
curve_signal = ("DÉSINVERSION" if spread and spread_prev and spread>spread_prev and spread_prev<0
                else ("INVERSÉE" if spread and spread<0 else "NORMALE"))
vix_signal   = "COMPLAISANCE" if vix and vix<15 else ("PANIQUE" if vix and vix>=30 else "NORMAL")
```

--------------------------------------------------------------------------------
4. SÉCURITÉ — CAS LIMITES
--------------------------------------------------------------------------------
- PE indisponible → ERP = "N/A", afficher "—"
- ^IRX ne cote pas certains jours fériés US → fallback valeur J-2 depuis cache
- Désinversion non calculable si historique < 2J → afficher "—"
- VIX weekend → valeur vendredi J-1 avec label "(ven.)"
- Tous les signaux sont désactivés si donnée = None → jamais d'erreur affichée
================================================================================







BOX 6 (PORTFOLIO ALPHA & RISK SCANNER)


OBJECTIF : 
Analyse de conviction et de risque sur le portefeuille utilisateur. 
L'IA doit agir comme un auditeur de risques, pas comme un conseiller.

--------------------------------------------------------------------------------
1. CRITÈRES DE TRI MATHÉMATIQUES (STRICT DATA ONLY)
--------------------------------------------------------------------------------

TOP 3 HIGH CONVICTION (MÉTRIQUE DE FORCE) :
Ne peut être affiché que si le Sentiment Score est > +0.6.
- Condition 1 : Prix > 200-DMA (Tendance confirmée).
- Condition 2 : MFI > 70 (Pression acheteuse forte).
- Condition 3 : OBV en hausse sur les 20 dernières sessions.

TOP 3 RED FLAGS (MÉTRIQUE DE DANGER) :
Affiché si le Sentiment Score est < -0.5 ou si une loi de Box 4 est enfreinte.
- Condition 1 : Prix < 200-DMA (Tendance baissière).
- Condition 2 : MFI < 30 (Capitulation/Survendu) ou Divergence OBV.
- Condition 3 : Présence d'un flag "ANALYST DELUSION" ou "SMART MONEY EXIT".

--------------------------------------------------------------------------------
2. STRUCTURE DU TABLEAU OBLIGATOIRE
--------------------------------------------------------------------------------

| CATEGORY | TICKER (SECTOR) | SIGNAL | EVIDENCE (MATH-ONLY) |
| :--- | :--- | :--- | :--- |
| Conviction | $TICKER | [SCORE] Label | [DATA_POINTS] |
| Red Flag | $TICKER | [SCORE] Label | [DATA_POINTS] |

--------------------------------------------------------------------------------
3. PROTOCOLE D'ÉCRITURE DE LA COLONNE "EVIDENCE"
--------------------------------------------------------------------------------
Interdiction de rédiger des phrases narratives. Format de données brutes uniquement :

- EXEMPLE CONVICTION : "MFI: 74 | OBV: +12% (20j) | Price: +8.3% vs 200-DMA | Sentiment: +0.8"
- EXEMPLE RED FLAG : "MFI: 22 | OBV: Falling | Price: -15% vs 200-DMA | Flag: ANALYST DELUSION"

--------------------------------------------------------------------------------
4. CLAUSE ANTI-HALLUCINATION (INSTRUCTIONS IA)
--------------------------------------------------------------------------------
- "Si aucun ticker du portefeuille ne dépasse le score de +0.6, la section 'High Conviction' doit afficher : 'NO STRONG TECHNICAL SIGNAL'."
- "Si une donnée de prix ou de volume est manquante pour un ticker, exclure le ticker de l'analyse et noter : 'TICKER [NAME] EXCLUDED - INCOMPLETE DATA'."
- "Interdiction de citer une news pour justifier un signal. Seuls les indicateurs techniques (MFI, OBV, DMA) et le consensus (Target/Price) sont autorisés."

--------------------------------------------------------------------------------
5. MISE EN PAGE VISUELLE (UX)
--------------------------------------------------------------------------------
- Bordure de ligne Verte pour High Conviction.
- Bordure de ligne Rouge clignotante ou intense pour Red Flags.
- Colonne "Signal" : Utiliser les labels de l'échelle Sentiment Score (ex: Euphoric Bullish).
================================================================================




----------------------------------------------------------


## 🗂️ Sector Grouping (par zone géographique)
*Mêmes 14 groupes pour USA / Europe / Asie — contenu différent selon la zone*

| # | Groupe Sectoriel |
|---|---|
| 1 | Technology & Semiconductors |
| 2 | Industrial Robotics & MedTech |
| 3 | Healthcare & Pharma |
| 4 | Digital Assets |
| 5 | Strategic Materials |
| 6 | Energy |
| 7 | Defense & Aerospace |
| 8 | EV & Clean Energy |
| 9 | Space |
| 10 | Luxury |
| 11 | Industrials |
| 12 | Agriculture |
| 13 | Infrastructure & Water |
| 14 | Consumer Staples |

**À confirmer** : les ETF/tickers représentatifs pour chaque groupe × chaque zone (Hugo valide)

---

## 📊 Sentiment Score — Méthodologie (OBLIGATOIRE)

### Formule de calcul
Dérivé de 3 indicateurs réels combinés :

| Condition | Score |
|---|---|
| MFI > 70 + OBV en hausse + prix au-dessus 200DMA | **+0.5 à +1.0** (Bullish) |
| MFI 40-70 + OBV plat + prix proche des DMA | **-0.1 à +0.1** (Neutre) |
| MFI < 30 + OBV en baisse + prix sous 200DMA | **-0.5 à -1.0** (Bearish) |

### Échelle d'interprétation
| Score | Signal | Signification |
|---|---|---|
| -1.0 à -0.6 | 🔴 Extreme Bearish | Capitulation — panique des vendeurs |
| -0.5 à -0.1 | 🟠 Caution | Distribution — les gros vendent discrètement |
| 0 | ⚪ Neutral | Équilibre acheteurs/vendeurs |
| +0.1 à +0.5 | 🟡 Accumulation | Optimisme modéré — les gros achètent discrètement |
| +0.6 à +1.0 | 🟢 Euphoric Bullish | Euphorie — attention au retournement |

> **MFI** = Money Flow Index (pression achat/vente via volume + prix)
> **OBV** = On-Balance Volume (accumulation/distribution du volume)


**Règle d'affichage sur la page** : chaque secteur affiche son score sous forme de jauge visuelle (-1 → +1) 
avec le label de l'échelle. Couleur dynamique selon la valeur.

-------------------------------------------------------------------------------------------------------------------------------------------------------------------

PAGE 2
### Planning de génération (validé)
| Horaire | Fréquence | Contexte |
|---|---|---|
| 08h00 | 1x lun-ven | Pré-marché |
| 10h → 22h | 1x/heure lun-ven | Heures de marché |
| 23h00 | 1x lun-ven | Post-marché + archivage |
| 09h00 | 1x sam-dim | Récap hebdo |
mise a jour de la page a page et des tickers selon la meme frequence

---

## 🔧 État technique du projet

### Structure cible (remplace l'ancienne newsletter)
```
C:\SAINHE\
├── CLAUDE.md                  ✅ ce fichier
├── requirements.txt           ← à créer
├── main.py                    ← à créer
├── config.py                  ← à créer
├── .github/workflows/
│   └── sainhe.yml             ← GitHub Actions cron
├── scripts/
│   ├── db_init.py             ← à créer EN PREMIER
│   ├── fetch_prices.py        ← à créer
│   ├── fetch_indices.py       ← à créer
│   ├── fetch_fx.py            ← à créer
│   ├── fetch_news.py          ← à créer
│   └── calc.py                ← à créer
├── boxes/
│   ├── box_01_news.py         ← à créer
│   ├── box_02_indices.py      ← à créer
│   ├── box_03_sectors.py      ← à créer
│   ├── box_04_sentiment.py    ← à créer
│   └── box_05_macro.py        ← à créer
├── templates/
│   └── dashboard.html         ← à créer (design crème/beige Apple)
├── db/
│   └── sainhe.db              ← créé par db_init.py
├── cache/
│   └── news/                  ← créé par fetch_news.py
└── output/
    └── index.html             ← généré par render_html.py
```

### Problèmes connus
- yfinance peut être bloqué dans certains environnements VM/proxy → tester sur machine locale
- Google Finance scraping : sélecteurs CSS à valider après chaque mise à jour du site
- Tickers HK (.HK) : historique parfois tronqué avant 2018 sur yfinance → à vérifier

### Prochaines étapes (ordre strict)
- [ ] db_init.py → créer toutes les tables SQLite
- [ ] fetch_prices.py → remplir la base avec yfinance
- [ ] calc.py → calculer tous les indicateurs
- [ ] boxes/ → générer le HTML de chaque box
- [ ] dashboard.html → template Jinja2 design crème/beige
- [ ] GitHub repo + Actions → automatisation
- [ ] Cloudflare Pages → déploiement SAINHE.com

---

## 💡 Idées en vrac (brainstorming)

- Créer une "religion" autour des infos SAINHE — contenu addictif, design premium
- Vendre les prestations depuis le domaine SAINHE.com (Phase 2+)
- Scalabilité : Cloudflare Pages (Phase 2) → Cloudflare Workers + Redis (Phase 3)
- Penser à la monétisation dès la structure (abonnement, tiers premium ?)

---

## 🔐 Sécurité

- ⚠️ Ne jamais committer le fichier `.env`
- ⚠️ Ne jamais partager les clés API dans le chat


---
---
## 🔌 SOURCES DE DONNÉES — DÉCISIONS VALIDÉES (session du 03/04/2026)

### Stack de fetch — yfinance + RSS scraping, zéro API, zéro IA

| Donnée | Source | Fréquence | Statut |
|---|---|---|---|
| AdjClose / Volume / High / Low / Open | yfinance daily | Quotidien J-1 post-clôture | ✅ Validé |
| Beta / 52W High / 52W Low / PE Ratio | yfinance `.info` | Quotidien | ✅ Validé |
| Var% J-1 / DMA / Momentum / RVOL / OBV / MFI | Calculé Python depuis série en base | Quotidien | ✅ Validé |
| Volume 1H (intraday) + RVOL Speed | yfinance interval=1h pendant sessions | Horaire 10h-22h | ⚠️ À coder |
| News flux (Box 1) | feedparser — Reuters / MarketWatch / FT / Seeking Alpha RSS | 1x/heure | ⚠️ À coder |
| Calendrier macro + Consensus (Box 1) | marketwatch.com/economy-politics/calendar HTML | 08h00 quotidien | ⚠️ À coder |
| Earnings calendar (Box 1) | stockanalysis.com/earnings-calendar/ HTML | 08h00 quotidien | ⚠️ À coder |
| Fed events | federalreserve.gov/feeds/press_all.xml RSS | 08h00 quotidien | ⚠️ À coder |
| BCE events | ecb.europa.eu/rss RSS | 08h00 quotidien | ⚠️ À coder |
| Taux USD/EUR et USD/HKD | Google Finance HTML scraping | Quotidien | ⚠️ À coder |
| Tickers .HK | yfinance (à valider ticker par ticker) | — | ⚠️ À tester |
| Earnings Beat/Miss consensus | stockanalysis.com HTML (fill Yahoo) | Quotidien | ⚠️ À coder |
| Gemini / toute IA générative | ❌ ABANDONNÉ — remplacé par RSS + templates Jinja2 | — | ❌ |
| FMP | ❌ ABANDONNÉ | — | ❌ |
| Toute API avec clé | ❌ INTERDIT | — | ❌ |

---

## 🔍 VALIDATION DES DONNÉES — Cross-check scraping

### Principe
Comparer les valeurs scrapées depuis Yahoo Finance HTML contre un second site
pour détecter les anomalies avant qu'elles n'entrent en base. Zéro API, deux sources HTML indépendantes.

### Sources de validation par type de ticker

| Ticker | Source primaire | Source secondaire (cross-check) |
|---|---|---|
| US (XLK, MOO…) | Yahoo Finance HTML | stockanalysis.com HTML |
| EU .DE (EXV3.DE…) | Yahoo Finance HTML | boerse-frankfurt.de HTML |
| HK .HK (2845.HK…) | Yahoo Finance HTML | hkex.com.hk HTML |
| FX USD/EUR | Google Finance HTML | xe.com HTML |
| FX USD/HKD | Google Finance HTML | xe.com HTML |

### Règles de validation
| Seuil delta | Action |
|---|---|
| < 2% | ✅ ACCEPTED — écriture en base |
| 2–5% | ⚠️ WARNING — log + écriture en base quand même |
| > 5% | ❌ REJECTED — fallback J-2 depuis base + log alerte |

### Intégration dans le pipeline
```
main.py
  └── fetch_primary.py     ← scraping Yahoo Finance HTML
  └── fetch_secondary.py   ← scraping source alternative
  └── validate.py          ← comparaison + seuils
        └── si OK / WARNING → db_write.py → sainhe.db
        └── si REJECTED     → fallback J-2 + log
  └── render_html.py       ← triggered automatiquement après écriture
```

### Limites à surveiller
- Les sélecteurs HTML changent sans prévenir → maintenir une liste de sélecteurs avec date de dernière vérification
- Respecter 1–2s de délai entre chaque requête — jamais en boucle serrée
- Conserver les logs 90 jours dans `cache/archive/`

---

## 📊 HIÉRARCHIE DES SOURCES — Règle globale

```
PRIORITÉ 1 — Yahoo Finance HTML    → source primaire pour TOUT
PRIORITÉ 2 — Stockanalysis.com     → complète ce que Yahoo n'a pas
PRIORITÉ 3 — Base sainhe.db J-2    → fallback si les deux échouent
❌ Aucune API, aucune clé, jamais
```

| Donnée | Yahoo Finance | Stockanalysis | Fallback |
|---|---|---|---|
| AdjClose / Volume / OHLC | ✅ Primaire | — | sainhe.db J-2 |
| Beta / 52W High / Low | ✅ Primaire | — | sainhe.db J-2 |
| Earnings date + heure | ✅ Primaire | ✅ Complément si manquant | — |
| Revenue/EPS consensus | ⚠️ Partiel | ✅ Complément | — |
| Beat/Miss réel | ⚠️ Partiel | ✅ Complément | — |
| Historique surprises (8Q) | ❌ Absent | ✅ Complément | — |
| Calendrier macro | ❌ Absent | ❌ Absent | → investing.com |
| Taux FX | ❌ Absent | ❌ Absent | → Google Finance |



### Pourquoi c'est utile en complément de Yahoo
Stockanalysis affiche ce que Yahoo ne donne pas facilement :
- Le consensus analyst détaillé : Revenue estimé + EPS estimé
- Le résultat réel dès publication + beat/miss calculé automatiquement
- L'historique des surprises sur 8 trimestres

Ce que Yahoo donne déjà et qu'on ne re-scrape pas sur stockanalysis :
- AdjClose, Volume, OHLC → Yahoo uniquement
- Date d'earnings → Yahoo en primaire, stockanalysis en fallback si manquant

Format DATA ANCHOR Box 1 résultant :
`$AAPL : Revenue $94.2B | Est. $93.8B | Beat +0.4%` ← réel Yahoo + consensus stockanalysis
`$NVDA : Earnings Today 22h00 | Est. EPS $5.58 | Est. Revenue $38.0B` ← pré-marché

### Pages à scraper (uniquement si Yahoo ne couvre pas)

| Contenu | URL pattern |
|---|---|
| Calendrier earnings du jour (fallback) | stockanalysis.com/earnings-calendar/ |
| Forecast revenue + EPS par ticker | stockanalysis.com/stocks/{ticker}/forecast/ |
| Résultat réel + beat/miss | stockanalysis.com/stocks/{ticker}/financials/ |

### Données à extraire depuis stockanalysis

| Champ | Yahoo couvre ? | Stockanalysis role |
|---|---|---|
| Date + heure earnings | ✅ Primaire | Fallback si manquant |
| Revenue consensus (est.) | ⚠️ Partiel | ✅ Complément principal |
| EPS consensus (est.) | ⚠️ Partiel | ✅ Complément principal |
| Revenue réel | ✅ Primaire | Vérification |
| EPS réel | ✅ Primaire | Vérification |
| Beat/Miss % | Calculé | Calculé aussi — cross-check |
| Surprise historique (8Q) | ❌ Absent | ✅ Exclusif stockanalysis |

### Rôle dans le pipeline
- Source **complémentaire** — appelée uniquement si Yahoo retourne vide sur consensus/forecast
- Scraping 2x/jour : 08h00 + post-publication
- Stockage : table `earnings_events` dans sainhe.db
- Champ `source` dans la table : `yahoo` ou `stockanalysis` pour traçabilité

