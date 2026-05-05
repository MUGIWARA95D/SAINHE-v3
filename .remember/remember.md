# Handoff

## State
Stable at commit `a2bdbf9` on branch `dev`. sainhe.pages.dev = localhost ✅
Finance Mindmap rebuilt as D3.js v7 force-directed graph (165 nodes, 164 links from Kumu JSON).
Dashboard data fresh May 05. No open items.

## Next
- No open items — site is clean and fully deployed

## Context
- Mindmap generator: `C:\Users\hugo1\Desktop\SAINHE\gen_mindmap.py` (outside repo) — run to rebuild mindmap section in `templates/learn.html`, then `render_html.py`
- Kumu JSON: `G:\Mon Drive\PROJET SAINHE\SAINHE\Mindmap\kumu-ipon28-sainhe-finance.json`
- Mindmap params: arc k=0.13 (bezier quadratic bidirectionnel), leaf repulsion -220, collide radius +22 ×4 iter, auto-fit 10s one-shot
- Push to dev → CI downloads DB from Drive → renders → deploys to sainhe.pages.dev
- GDRIVE_FILE_ID: 18LcHZ2jPHBiqwtc82gZmVZZL03e4xpMj / service account: sainhe-ci@sainhe.iam.gserviceaccount.com
