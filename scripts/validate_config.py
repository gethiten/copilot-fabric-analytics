#!/usr/bin/env python3
"""Validate config/settings.yaml before deploying to Fabric.

Checks structure, required keys, placeholder values still needing replacement,
and cross-field consistency (e.g. Copilot Studio required fields when enabled).
Run locally:      python scripts/validate_config.py
Validate example: python scripts/validate_config.py config/settings.example.yaml --structure-only
Exit code 0 = OK, 1 = problems found.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "settings.yaml"

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
    parser = argparse.ArgumentParser(description="Validate a Copilot-Fabric settings YAML.")
    parser.add_argument("path", nargs="?", default=str(DEFAULT_CONFIG_PATH),
                        help="Path to the settings YAML (default: config/settings.yaml).")
    parser.add_argument("--structure-only", action="store_true",
                        help="Only check structure/keys; treat placeholders as warnings (for CI on the example).")
    args = parser.parse_args()
    config_path = Path(args.path)
    structure_only = args.structure_only

    if not config_path.exists():
        print(f"[FAIL] {config_path} not found. Copy config/settings.example.yaml first.")
        return 1

    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    errors: list[str] = []
    warnings: list[str] = []

    def placeholder_issue(msg: str) -> None:
        (warnings if structure_only else errors).append(msg)

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
        placeholder_issue("github.org is still a placeholder — set your real org login")

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
                placeholder_issue(f"copilot_studio enabled but app_insights.{key} is a placeholder")
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
