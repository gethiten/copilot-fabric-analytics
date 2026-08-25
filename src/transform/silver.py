"""Pure-Python Silver parsing helpers — the tested contract for bronze -> silver.

Notebook `04_transform_silver_gold.py` performs the same field mapping/typing at scale
with Spark `from_json`. These functions encode the identical schema so the logic can be
unit-tested without a Spark session. Keep the two in sync: the field names and types
here are the source of truth for the Silver layer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        # Tolerate numeric strings like "812.0".
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _to_date(value: Any) -> Optional[str]:
    """Return the date portion (YYYY-MM-DD) of an ISO date/datetime string."""
    if not value:
        return None
    return str(value)[:10]


def parse_github_cost(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw GitHub billing usage line-item to a typed Silver cost row.

    Mirrors `silver_github_copilot_cost` in notebook 04.
    """
    return {
        "usage_date": _to_date(payload.get("date")),
        "product": payload.get("product"),
        "sku": payload.get("sku"),
        "quantity": _to_float(payload.get("quantity")),          # premium requests
        "unit_type": payload.get("unitType"),
        "price_per_unit": _to_float(payload.get("pricePerUnit")),
        "gross_amount": _to_float(payload.get("grossAmount")),
        "discount_amount": _to_float(payload.get("discountAmount")),
        "net_amount": _to_float(payload.get("netAmount")),
        "org_name": payload.get("organizationName"),
        "repo_name": payload.get("repositoryName"),
    }


def parse_copilotstudio_token(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw App Insights token event to a typed Silver token-usage row.

    Mirrors `silver_copilotstudio_token_usage` in notebook 04.
    """
    ts = payload.get("timestamp")
    return {
        "event_time": ts,
        "usage_date": _to_date(ts),
        "conversation_id": payload.get("conversationId"),
        "agent_id": payload.get("agentId"),
        "model": payload.get("model"),
        "prompt_tokens": _to_int(payload.get("promptTokens")),
        "completion_tokens": _to_int(payload.get("completionTokens")),
        "total_tokens": _to_int(payload.get("totalTokens")),
    }


def cost_dedup_key(silver_row: Dict[str, Any]) -> tuple:
    """Business key used to de-duplicate GitHub cost rows in Silver (matches notebook 04)."""
    return (
        silver_row.get("usage_date"),
        silver_row.get("sku"),
        silver_row.get("org_name"),
        silver_row.get("repo_name"),
        silver_row.get("quantity"),
        silver_row.get("net_amount"),
    )


def audit_dedup_key(event: Dict[str, Any]) -> Optional[str]:
    """Stable unique key for a GitHub audit event (used by the idempotent bronze writer)."""
    key = event.get("_document_id")
    return None if key is None else str(key)


def dedup_by_key(rows: List[Dict[str, Any]], key_fn) -> List[Dict[str, Any]]:
    """Keep the first occurrence of each key. Rows whose key is None are dropped."""
    seen: set = set()
    result: List[Dict[str, Any]] = []
    for row in rows:
        key = key_fn(row)
        if key is None or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result
