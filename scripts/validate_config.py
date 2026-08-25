#!/usr/bin/env python3
"""Validate config/settings.yaml before deploying to Fabric.

Checks structure, required keys, placeholder values still needing replacement,
and cross-field consistency (e.g. Copilot Studio required fields when enabled).
Run locally: python scripts/validate_config.py
Exit code 0 = OK, 1 = problems found.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"

PLACEHOLDERS = {"<your-github-org>", "00000000-0000-0000-0000-000000000000"}


def _require(cfg: dict, dotted: str, errors: list[str]) -> object:
    node: object = cfg
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            errors.append(f"missing required key: {dotted}")
            return None
        node = node[key]
    return node


def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"[FAIL] {CONFIG_PATH} not found. Copy config/settings.example.yaml first.")
        return 1

    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    errors: list[str] = []
    warnings: list[str] = []

    # Required across all deployments.
    for key in (
        "github.scope",
        "github.org",
        "github.api_base",
        "github.token_secret_name",
        "key_vault.name",
        "lakehouse.bronze_prefix",
        "lakehouse.silver_prefix",
        "lakehouse.gold_prefix",
        "ingestion.lookback_days",
    ):
        _require(cfg, key, errors)

    scope = (cfg.get("github") or {}).get("scope")
    if scope not in (None, "org", "enterprise"):
        errors.append(f"github.scope must be 'org' or 'enterprise', got: {scope!r}")
    if scope == "enterprise" and not (cfg.get("github") or {}).get("enterprise"):
        errors.append("github.scope is 'enterprise' but github.enterprise is empty")

    org = (cfg.get("github") or {}).get("org")
    if org in PLACEHOLDERS:
        errors.append("github.org is still a placeholder — set your real org login")

    lookback = (cfg.get("ingestion") or {}).get("lookback_days")
    if isinstance(lookback, int) and not (1 <= lookback <= 365):
        warnings.append(f"ingestion.lookback_days={lookback} is outside 1..365")

    # Copilot Studio: only enforce when enabled.
    cs = cfg.get("copilot_studio") or {}
    if cs.get("enabled"):
        ai = cs.get("app_insights") or {}
        for key in ("app_id", "tenant_id", "client_id_secret_name", "client_secret_secret_name"):
            if not ai.get(key):
                errors.append(f"copilot_studio enabled but app_insights.{key} is missing")
            elif ai.get(key) in PLACEHOLDERS:
                errors.append(f"copilot_studio enabled but app_insights.{key} is a placeholder")
    else:
        warnings.append("copilot_studio.enabled = false (token telemetry deferred; notebook 03 will skip)")

    for w in warnings:
        print(f"[WARN] {w}")
    for e in errors:
        print(f"[FAIL] {e}")

    if errors:
        print(f"\n{len(errors)} error(s) found — fix before deploying.")
        return 1
    print("\n[OK] settings.yaml looks valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
