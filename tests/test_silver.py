"""Unit tests for the Silver parsing contract (src/transform/silver.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from transform.silver import (  # noqa: E402
    audit_dedup_key,
    cost_dedup_key,
    dedup_by_key,
    parse_copilotstudio_token,
    parse_github_cost,
)


# --------------------------------------------------------------------------
# GitHub cost parsing
# --------------------------------------------------------------------------
def test_parse_github_cost_typed_fields():
    payload = {
        "date": "2026-08-24T00:00:00Z",
        "product": "Copilot",
        "sku": "copilot_premium_request",
        "quantity": "12",
        "unitType": "premium_request",
        "pricePerUnit": "0.04",
        "grossAmount": "0.48",
        "discountAmount": "0.00",
        "netAmount": "0.48",
        "organizationName": "contoso",
        "repositoryName": "contoso/app",
    }
    row = parse_github_cost(payload)
    assert row["usage_date"] == "2026-08-24"           # date-only, truncated from datetime
    assert row["sku"] == "copilot_premium_request"
    assert row["quantity"] == 12.0 and isinstance(row["quantity"], float)
    assert row["price_per_unit"] == 0.04
    assert row["net_amount"] == 0.48
    assert row["org_name"] == "contoso"
    assert row["repo_name"] == "contoso/app"


def test_parse_github_cost_handles_missing_and_blank():
    row = parse_github_cost({"date": "2026-08-24", "sku": "x"})
    assert row["usage_date"] == "2026-08-24"
    assert row["quantity"] is None            # missing numeric -> None, not crash
    assert row["net_amount"] is None
    assert row["org_name"] is None


def test_parse_github_cost_bad_numeric_is_none():
    row = parse_github_cost({"date": "2026-08-24", "netAmount": "N/A"})
    assert row["net_amount"] is None


# --------------------------------------------------------------------------
# Copilot Studio token parsing
# --------------------------------------------------------------------------
def test_parse_token_usage_typed_ints():
    payload = {
        "timestamp": "2026-08-24T10:15:30.123Z",
        "conversationId": "abc-123",
        "agentId": "hr-bot",
        "model": "gpt-4o",
        "promptTokens": "812",
        "completionTokens": "240",
        "totalTokens": "1052",
    }
    row = parse_copilotstudio_token(payload)
    assert row["usage_date"] == "2026-08-24"
    assert row["event_time"] == "2026-08-24T10:15:30.123Z"
    assert row["conversation_id"] == "abc-123"
    assert row["prompt_tokens"] == 812 and isinstance(row["prompt_tokens"], int)
    assert row["completion_tokens"] == 240
    assert row["total_tokens"] == 1052


def test_parse_token_usage_float_string_ints():
    row = parse_copilotstudio_token({"timestamp": "2026-08-24", "totalTokens": "1052.0"})
    assert row["total_tokens"] == 1052


# --------------------------------------------------------------------------
# De-duplication (idempotency contract)
# --------------------------------------------------------------------------
def test_audit_dedup_key():
    assert audit_dedup_key({"_document_id": "evt-1"}) == "evt-1"
    assert audit_dedup_key({"_document_id": 999}) == "999"
    assert audit_dedup_key({}) is None


def test_dedup_by_key_removes_duplicate_audit_events():
    events = [
        {"_document_id": "a", "action": "copilot.enabled"},
        {"_document_id": "b", "action": "copilot.disabled"},
        {"_document_id": "a", "action": "copilot.enabled"},   # duplicate re-run
        {"action": "no-id"},                                  # dropped (no key)
    ]
    out = dedup_by_key(events, audit_dedup_key)
    assert [e["_document_id"] for e in out] == ["a", "b"]


def test_cost_dedup_key_matches_silver_grain():
    row = parse_github_cost({
        "date": "2026-08-24", "sku": "s1", "organizationName": "o1",
        "repositoryName": "r1", "quantity": "3", "netAmount": "1.20",
    })
    assert cost_dedup_key(row) == ("2026-08-24", "s1", "o1", "r1", 3.0, 1.20)
