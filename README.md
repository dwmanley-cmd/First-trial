# Costco warehouse inventory checker

Checks once a day whether Costco item **2113717** is in stock at your local
warehouse (the same lookup as the app's Warehouse page), using GitHub Actions.

## Setup
1. In the repo on GitHub: **Settings → Secrets and variables → Actions → Variables**, add:
   - `WAREHOUSE_NUMBER` — your warehouse number (on the app's Warehouse page or your receipt)
   - `ZIP_CODE` — your ZIP code (optional)
   - `ITEM_NUMBER` — optional, defaults to `2113717`
2. Merge this into the default branch (scheduled workflows only run from there).
3. **Actions → Costco warehouse inventory check → Run workflow** to test it now.

## What you get
- Each run's result (`IN_STOCK`, `OUT_OF_STOCK`, `NOT_FOUND`) in the run summary.
- When it's in stock, an issue is opened, and GitHub emails you about it.
- A run fails (and GitHub emails you) when the status couldn't be read, e.g. if
  Costco blocks the request or changes its page; `debug.png`/`debug.html` are
  attached to the run.

Run locally: `pip install playwright && playwright install chromium && WAREHOUSE_NUMBER=123 python check_inventory.py`
