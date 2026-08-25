# Fabric notebook source
# ==========================================================================
# 03_copilotstudio_appinsights_tokens — token-level telemetry from App Insights
# ==========================================================================
# Copilot Studio meters generative AI in "messages/credits", not tokens.
# To get REAL token counts you must emit custom telemetry when the model is
# called (see docs/token_telemetry_setup.md). This notebook reads those
# custom events back out of Application Insights via the REST query API.
#
# Expected custom event shape (customDimensions):
#   promptTokens, completionTokens, totalTokens, model, conversationId, agentId
# --------------------------------------------------------------------------

# MAGIC %run ./00_common

# CELL ********************

cfg = load_config()
kv = cfg["key_vault"]["name"]
bronze = cfg["lakehouse"]["bronze_prefix"]

# Skip cleanly when Copilot Studio token telemetry is not enabled yet.
# The daily pipeline uses a "Completed" dependency so 04 still runs after this exits.
if not cfg.get("copilot_studio", {}).get("enabled", False):
    print("[03] copilot_studio.enabled = false -> skipping token telemetry ingestion.")
    try:
        notebookutils.notebook.exit("skipped: copilot_studio disabled")  # noqa: F821
    except Exception:
        pass
    raise SystemExit(0)

ai = cfg["copilot_studio"]["app_insights"]

client_id = get_secret(kv, ai["client_id_secret_name"])
client_secret = get_secret(kv, ai["client_secret_secret_name"])

access_token = entra_token(
    tenant_id=ai["tenant_id"],
    client_id=client_id,
    client_secret=client_secret,
    scope="https://api.applicationinsights.io/.default",
)

# CELL ********************

lookback = int(cfg["ingestion"]["lookback_days"])

# KQL: pull custom token-usage events emitted by the agent.
kql = f"""
customEvents
| where timestamp > ago({lookback}d)
| where name in ("TokenUsage", "GenAITokenUsage")
| extend d = customDimensions
| project
    timestamp,
    conversationId = tostring(d.conversationId),
    agentId        = tostring(d.agentId),
    model          = tostring(d.model),
    promptTokens   = toint(d.promptTokens),
    completionTokens = toint(d.completionTokens),
    totalTokens    = toint(d.totalTokens),
    operation_Id
"""

query_url = f'{ai["api_base"]}/{ai["app_id"]}/query'
resp = requests.post(
    query_url,
    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
    json={"query": kql},
    timeout=120,
)
resp.raise_for_status()
result = resp.json()

# CELL ********************

# Flatten the App Insights tabular response into row dicts.
rows: list[dict] = []
for table in result.get("tables", []):
    cols = [c["name"] for c in table["columns"]]
    for values in table["rows"]:
        rows.append(dict(zip(cols, values)))

print(f"Token telemetry rows: {len(rows)}")
write_delta(rows, f"{bronze}copilotstudio_token_usage", mode="append")
