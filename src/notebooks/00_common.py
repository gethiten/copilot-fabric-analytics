# Fabric notebook source
# ==========================================================================
# 00_common — shared helpers (run this via %run or import into other notebooks)
# ==========================================================================
# Provides: load config, read Key Vault secrets, get GitHub headers,
# get an Entra token for Log Analytics/App Insights, and a Delta writer.
# --------------------------------------------------------------------------

# CELL ********************

import json
import time
import datetime as dt
from typing import Any, Dict, Iterable, List, Optional

import requests

try:
    import yaml  # available in Fabric Spark runtime
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml"])
    import yaml


# CELL ********************

def load_config(path: str = "config/settings.yaml") -> Dict[str, Any]:
    """Load the pipeline configuration from a YAML file in the Lakehouse Files area."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_secret(kv_name: str, secret_name: str) -> str:
    """Read a secret from the Fabric-linked Key Vault."""
    # notebookutils is injected in the Fabric runtime.
    return notebookutils.credentials.getSecret(kv_name, secret_name)  # noqa: F821


# CELL ********************

def github_headers(token: str) -> Dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_get(url: str, headers: Dict[str, str], params: Optional[dict] = None) -> requests.Response:
    """GET with basic rate-limit handling."""
    for attempt in range(5):
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
            reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            time.sleep(max(reset - time.time(), 1))
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


def github_paginate(url: str, headers: Dict[str, str], params: Optional[dict] = None) -> Iterable[dict]:
    """Yield items across Link-header paginated GitHub endpoints."""
    params = dict(params or {})
    params.setdefault("per_page", 100)
    next_url: Optional[str] = url
    while next_url:
        resp = github_get(next_url, headers, params=params if next_url == url else None)
        payload = resp.json()
        items = payload if isinstance(payload, list) else payload.get("seats") or payload.get("usageItems") or []
        for item in items:
            yield item
        next_url = resp.links.get("next", {}).get("url")


# CELL ********************

def entra_token(tenant_id: str, client_id: str, client_secret: str, scope: str) -> str:
    """Client-credentials token for App Insights / Log Analytics APIs."""
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
    }
    resp = requests.post(url, data=data, timeout=60)
    resp.raise_for_status()
    return resp.json()["access_token"]


# CELL ********************

def write_delta(rows: List[dict], table_name: str, mode: str = "append") -> int:
    """Write a list of dict rows to a Lakehouse Delta table. Returns row count."""
    if not rows:
        print(f"[write_delta] no rows for {table_name}")
        return 0
    ingest_ts = dt.datetime.utcnow().isoformat()
    for r in rows:
        r.setdefault("_ingested_at_utc", ingest_ts)
    # Store the raw payload as a JSON string column to keep bronze schema-stable.
    normalized = [{"_ingested_at_utc": r["_ingested_at_utc"], "payload": json.dumps(r, default=str)} for r in rows]
    df = spark.createDataFrame(normalized)  # noqa: F821
    (df.write.format("delta").mode(mode).option("mergeSchema", "true").saveAsTable(table_name))
    print(f"[write_delta] wrote {len(rows)} rows -> {table_name}")
    return len(rows)
