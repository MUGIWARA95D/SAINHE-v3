# Handoff

## State
Site is stable at commit `2c80168` on branch `dev`. `sainhe.pages.dev` = localhost, both running DB from 2026-05-05.
Infra fixed: DB lives on Google Drive (`18LcHZ2jPHBiqwtc82gZmVZZL03e4xpMj`), CI downloads it instead of re-fetching from scratch.
All UI changes shipped: no section numbers, centered hero, full-width chips, Finance Mindmap on learn page.

## Next
- Mindmap node pills still need to stretch full width (user asked, not done — see `_head.html` `.mm-type-nodes`)
- No other open items

## Context
- Local fetch workflow: run `scripts/fetch_*.py` + `calc.py` + `render_html.py` → Drive DB auto-updates → push to deploy
- Secrets on GitHub: `GDRIVE_SA_KEY`, `GDRIVE_FILE_ID`, `CF_API_TOKEN`, `CF_ACCOUNT_ID`
- CI always deploys with `branch: main` to hit production on CF Pages (not a preview)
- gdrive_sync.py strips UTF-8 BOM from env vars (PowerShell quirk)
