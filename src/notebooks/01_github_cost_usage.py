# Fabric notebook source
# ==========================================================================
# 01_github_cost_usage — GitHub Copilot COST + premium-request (token proxy)
# ==========================================================================
# Source: Enhanced Billing Platform usage API
#   GET /organizations/{org}/settings/billing/usage
# Lands raw usage line-items into the bronze layer. Each item includes:
#   date, product, sku, quantity, unitType, pricePerUnit,
#   grossAmount, discountAmount, netAmount, organizationName, repositoryName
# NOTE: GitHub Copilot bills in "premium requests", not raw tokens.
#       'quantity' on Copilot SKUs = premium request count.
# --------------------------------------------------------------------------

# MAGIC %run ./00_common

# CELL ********************

cfg = load_config()
gh = cfg["github"]
kv = cfg["key_vault"]["name"]

token = get_secret(kv, gh["token_secret_name"])
headers = github_headers(token)

lookback = int(cfg["ingestion"]["lookback_days"])
today = dt.date.today()
start = today - dt.timedelta(days=lookback)

# CELL ********************

# The usage API supports year/month/day filters. Pull per-day for the window
# to keep payloads small and support incremental re-runs.
owner = gh["org"] if gh["scope"] == "org" else gh["enterprise"]
base = f'{gh["api_base"]}/organizations/{owner}/settings/billing/usage'

all_items: list[dict] = []
d = start
while d <= today:
    params = {"year": d.year, "month": d.month, "day": d.day}
    try:
        resp = github_get(base, headers, params=params)
        items = resp.json().get("usageItems", [])
        all_items.extend(items)
    except requests.HTTPError as e:
        print(f"[warn] {d} -> {e}")
    d += dt.timedelta(days=1)

# Keep only Copilot-related lines (product name contains 'copilot', case-insensitive).
copilot_items = [i for i in all_items if "copilot" in str(i.get("product", "")).lower()]
print(f"Total usage items: {len(all_items)} | Copilot items: {len(copilot_items)}")

# CELL ********************

write_delta(copilot_items, f'{cfg["lakehouse"]["bronze_prefix"]}github_copilot_cost', mode="append")

# Optional: keep the full usage feed too (all products) for finance reconciliation.
write_delta(all_items, f'{cfg["lakehouse"]["bronze_prefix"]}github_billing_usage_all', mode="append")
