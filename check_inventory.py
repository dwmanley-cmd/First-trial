#!/usr/bin/env python3
"""Daily Costco warehouse inventory check for a single item.

Mirrors the Costco app's Warehouse page "search in-warehouse items" lookup:
it sets your home warehouse, looks up the item, and reports whether the
warehouse shows it as in stock.

Config (environment variables):
  ITEM_NUMBER       Costco item number (default 2113717)
  WAREHOUSE_NUMBER  Your local warehouse number (required), e.g. 1234
  ZIP_CODE          ZIP code near that warehouse (optional, helps the site pick it)

Exit codes: 0 = check ran (see result.json), 2 = could not determine status.
Writes result.json and, on failure, debug.png / debug.html for troubleshooting.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

ITEM = os.environ.get("ITEM_NUMBER", "2113717").strip()
WAREHOUSE = os.environ.get("WAREHOUSE_NUMBER", "").strip()
ZIP_CODE = os.environ.get("ZIP_CODE", "").strip()
BASE = "https://www.costco.com"

IN_STOCK = [r"in stock at", r"\bin stock\b", r"available in warehouse", r"limited stock"]
OUT_OF_STOCK = [r"out of stock", r"not available at", r"not sold in", r"unavailable", r"sold out"]


def classify(text: str) -> str:
    t = text.lower()
    # Check out-of-stock first: "not in stock" would otherwise match "in stock".
    if any(re.search(p, t) for p in OUT_OF_STOCK) or "not in stock" in t:
        return "OUT_OF_STOCK"
    if any(re.search(p, t) for p in IN_STOCK):
        return "IN_STOCK"
    return "UNKNOWN"


def try_inventory_api(page) -> dict | None:
    """Call the endpoint costco.com's product page uses for warehouse stock,
    from inside the browser so it carries the site's cookies."""
    if not WAREHOUSE:
        return None
    product_id = str(int(ITEM) - 1) if ITEM.isdigit() else ITEM
    url = (f"{BASE}/AjaxGetInventoryDetail?itemId={ITEM}&catalogId=10701"
           f"&productId={product_id}&WarehouseFormatted=&warehouseNumber={WAREHOUSE}")
    try:
        body = page.evaluate(
            "async (u) => { const r = await fetch(u, {credentials: 'include'});"
            " return r.ok ? await r.text() : null; }", url)
        return json.loads(body) if body else None
    except Exception:
        return None


def interpret_api(data: dict) -> str:
    blob = json.dumps(data).lower()
    for key in ("instock", "isinstock", "inventoryavailable", "available"):
        m = re.search(rf'"{key}"\s*:\s*"?(true|false|\d+)', blob)
        if m:
            v = m.group(1)
            return "IN_STOCK" if v in ("true",) or (v.isdigit() and int(v) > 0) else "OUT_OF_STOCK"
    return classify(blob)


def main() -> int:
    if not WAREHOUSE:
        print("WAREHOUSE_NUMBER is not set.", file=sys.stderr)
        return 2
    result = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "item": ITEM, "warehouse": WAREHOUSE, "status": "UNKNOWN",
              "source": None, "detail": None}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
            locale="en-US", viewport={"width": 1366, "height": 900})
        # Preferred-warehouse cookies the site reads to pick "my warehouse".
        cookies = [{"name": "STORELOCATION", "value": json.dumps({"storeLocation": {"zip": ZIP_CODE, "city": ""}}),
                    "domain": ".costco.com", "path": "/"},
                   {"name": "WAREHOUSEDELIVERY_WHS",
                    "value": json.dumps({"distributionCenters": [], "groceryCenters": [],
                                         "pickUpCenters": [WAREHOUSE]}),
                    "domain": ".costco.com", "path": "/"},
                   {"name": "invCheckPostalCode", "value": ZIP_CODE, "domain": ".costco.com", "path": "/"}]
        ctx.add_cookies([c for c in cookies if c["value"]])
        page = ctx.new_page()
        try:
            page.goto(f"{BASE}/.product.{ITEM}.html", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

            data = try_inventory_api(page)
            if data:
                result.update(status=interpret_api(data), source="AjaxGetInventoryDetail",
                              detail=json.dumps(data)[:500])

            if result["status"] == "UNKNOWN":
                text = page.inner_text("body")
                # Narrow to the warehouse availability area if present.
                m = re.search(r"(.{0,120}warehouse.{0,160})", text, re.I | re.S)
                snippet = m.group(1) if m else text[:400]
                result.update(status=classify(snippet), source="product page",
                              detail=" ".join(snippet.split())[:300])

            if result["status"] == "UNKNOWN":
                # Fall back to search, like the app's warehouse item search.
                page.goto(f"{BASE}/s?keyword={ITEM}", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(5000)
                text = page.inner_text("body")
                result.update(status=classify(text) if ITEM in text else "NOT_FOUND",
                              source="search", detail=" ".join(text.split())[:300])
        except Exception as e:  # network block, bot challenge, timeout...
            result["detail"] = f"error: {e}"
        if result["status"] == "UNKNOWN":
            try:
                page.screenshot(path="debug.png", full_page=True)
                open("debug.html", "w").write(page.content())
            except Exception:
                pass
        browser.close()

    with open("result.json", "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] != "UNKNOWN" else 2


if __name__ == "__main__":
    sys.exit(main())
