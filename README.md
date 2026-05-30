# SAINHE — Fundamental Intelligence

An independent financial-intelligence platform that aggregates macro signals,
decodes market structure, and explains it in plain language — so you can think
for yourself and act with conviction.

🔗 **Live:** [sainhe.pages.dev](https://sainhe.pages.dev)

---

## What it does

SAINHE turns raw market data into a single, legible dashboard:

- **Macro Health** — VIX, yield curve, ERP, DXY, central-bank liquidity, credit
  spreads, real rates, sovereign curves, valuation (CAPE / regional P/E), and
  cross-asset signals, each with interpretation thresholds.
- **Indices** — real-time snapshot of major global indices.
- **News** — curated financial headlines by region.
- **Sectors** — momentum and relative performance across 16 sectors × 4 regions.
- **Sentiment** — composite score per sector (MFI + OBV + 200-DMA).
- **Portfolio** — technical scan of a personal watchlist.

Every metric carries a small `(i)` that links to a *Learn* page explaining how
to read it.

## Architecture

```
 fetch_*.py ──► SQLite (sainhe.db, stored on Google Drive)
                     │
                 calc.py            indicators (DMA, MFI, OBV, momentum, score)
                     │
                 boxes/*.py         each box = render(con) -> {meta, data}
                     │
                render_html.py      Jinja2 -> static HTML  +  JSON data layer
                     │
              Cloudflare Pages      static hosting (sainhe.pages.dev)
```

- **Stateless & static.** No server at runtime — just static files on a CDN.
- **The database lives on Google Drive.** GitHub Actions downloads it at the
  start of each job, refreshes it, and uploads it back. No DB is committed.
- **Single source of truth.** Each box exposes one `render(con)` dict that feeds
  *both* the HTML and the JSON data layer — no duplicated computation.

## Data layer (built for AI agents)

Beyond the HTML, SAINHE publishes a machine-readable layer so agents read ~4 KB
of JSON instead of ~200 KB of markup:

| Resource | Description |
|---|---|
| [`/data/index.json`](https://sainhe.pages.dev/data/index.json) | Discovery manifest + units legend |
| [`/data/macro.json`](https://sainhe.pages.dev/data/macro.json) | Rich per-field: `value`, `unit`, `thresholds`, `regime` |
| `/data/{indices,sectors,sentiment,portfolio,news}.json` | Collections with a units map |
| [`/llms.txt`](https://sainhe.pages.dev/llms.txt) | Entry point for LLM agents |

Units and thresholds are defined once in [`schema.py`](./schema.py).

## Automation

GitHub Actions ([`.github/workflows/sainhe.yml`](./.github/workflows/sainhe.yml))
keeps everything fresh with no manual steps:

| Job | Cadence (Paris) |
|---|---|
| News + macro liquidity | 4h, 10h, 14h, 18h, 22h |
| FX rates | 12h, 23h |
| Full pipeline (prices + everything) | weeknights |

## Tech stack

Python · SQLite · pandas / statsmodels · Jinja2 · Chart.js · Cloudflare Pages ·
GitHub Actions

Data sources (all free): FRED, ECB SDW, MoF Japan, ChinaBond CCDC, stooq,
multpl.com, Yahoo Finance, and public RSS feeds.

## Repository layout

```
config.py            single source of truth (tickers, thresholds, sources)
schema.py            data-layer contract (units + thresholds)
render_html.py       Jinja2 render + JSON data layer
boxes/               one module per dashboard box
scripts/             fetchers, calc, DB init, Google Drive sync
templates/           HTML/CSS/JS (Jinja2)
projects/            academic / side projects (see below)
.github/workflows/   the automation pipeline
```

## Local development

```bash
pip install -r requirements.txt
cp .env.example .env          # then add your free API keys
python render_html.py         # build into output/
python serve.py               # serve output/ at http://localhost:7723
```

> No secrets are committed. All keys are read from environment variables / `.env`
> (gitignored). See [`.env.example`](./.env.example).

---

## Projects

Standalone work kept alongside the platform:

### [Oil Market Volatility → U.S. Financial Market Volatility](./projects/oil-vix-volatility/)
*Financial Econometrics — semester project.* Does oil-market volatility (OVX)
predict U.S. equity volatility (VIX)? Daily FRED data, OLS with HAC standard
errors, interaction/quadratic terms, and a PE test selecting a log-linear
specification. → [paper + code](./projects/oil-vix-volatility/)
