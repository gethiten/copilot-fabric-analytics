# Fabric notebook source
# ==========================================================================
# 02_github_seats_audit — Copilot seat assignments/activity + audit log
# ==========================================================================
# Sources:
#   GET /orgs/{org}/copilot/billing/seats   (per-user seats + last_activity_at)
#   GET /orgs/{org}/audit-log?phrase=action:copilot   (admin events)
# --------------------------------------------------------------------------

# MAGIC %run ./00_common

# CELL ********************

cfg = load_config()
gh = cfg["github"]
kv = cfg["key_vault"]["name"]
bronze = cfg["lakehouse"]["bronze_prefix"]

token = get_secret(kv, gh["token_secret_name"])
headers = github_headers(token)
org = gh["org"]

# CELL ********************
# ---- Seats ----
seats_url = f'{gh["api_base"]}/orgs/{org}/copilot/billing/seats'
seats = list(github_paginate(seats_url, headers))
print(f"Seats: {len(seats)}")
write_delta(seats, f"{bronze}github_copilot_seats", mode="overwrite")  # current snapshot

# CELL ********************
# ---- Audit log (Copilot actions) ----
lookback = int(cfg["ingestion"]["lookback_days"])
since_ms = int((dt.datetime.utcnow() - dt.timedelta(days=lookback)).timestamp() * 1000)

audit_url = f'{gh["api_base"]}/orgs/{org}/audit-log'
audit_params = {"phrase": "action:copilot", "per_page": 100, "include": "all"}

audit_events: list[dict] = []
for ev in github_paginate(audit_url, headers, params=audit_params):
    if ev.get("@timestamp", since_ms) < since_ms:
        break
    audit_events.append(ev)

print(f"Copilot audit events: {len(audit_events)}")
# Idempotent: audit events carry a unique '_document_id'. Re-runs with an overlapping
# lookback window will NOT duplicate rows (Delta MERGE inserts only new keys).
upsert_delta(audit_events, f"{bronze}github_copilot_audit", key_field="_document_id")
