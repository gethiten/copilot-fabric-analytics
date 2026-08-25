# Copilot Fabric Analytics

Extract **GitHub Copilot** and **Copilot Studio** usage, cost, and token telemetry into a
**Microsoft Fabric Lakehouse** (medallion: bronze → silver → gold) for Power BI analytics.

## What this delivers
- **Cost & consumption** for both Copilots (this is fully available today).
- **Token-level telemetry** for Copilot Studio (requires custom instrumentation — see
  [docs/token_telemetry_setup.md](docs/token_telemetry_setup.md)).
- A unified **`gold_fact_copilot_cost`** table + **`gold_dim_date`** ready for Power BI.

> **Status: code-complete, not yet wired.** All notebooks, pipeline, SQL, and Power BI
> assets are ready with placeholders only. See the architecture and the step-by-step
> wiring checklist before deploying:
> - **Architecture & build steps:** [docs/architecture.md](docs/architecture.md)
> - **Operations runbook (Fabric setup → Bronze/Silver/Gold → analytics):** [docs/RUNBOOK.md](docs/RUNBOOK.md)
> - **Wiring checklist (every value to fill):** [docs/WIRING.md](docs/WIRING.md)
> - **Validate config locally:** `pip install -r requirements.txt` then `python scripts/validate_config.py`

## Layout
```
config/settings.example.yaml   # copy to settings.yaml, fill values (no secrets)
src/notebooks/
  00_common.py                 # shared helpers (config, Key Vault, HTTP, Delta writer)
  01_github_cost_usage.py      # GitHub Copilot cost + premium requests -> bronze
  02_github_seats_audit.py     # seats/activity + Copilot audit events -> bronze
  03_copilotstudio_appinsights_tokens.py  # token telemetry from App Insights -> bronze
  04_transform_silver_gold.py  # typed silver + unified gold fact/dim
pipelines/
  pl_copilot_analytics_daily.json  # Data Factory pipeline: 01 -> 02 -> 03 -> 04
  trg_copilot_analytics_daily.json # daily 06:00 UTC schedule trigger
sql/
  gold_views.sql               # Power BI-ready views over the gold/silver tables
powerbi/
  CopilotAnalytics.pbip        # Power BI project (open in Power BI Desktop)
  CopilotAnalytics.SemanticModel/  # TMDL model: tables, relationships, measures
  CopilotAnalytics.Report/     # Overview report page (cards + trend + by-source)
docs/token_telemetry_setup.md  # how to emit real token counts from Copilot Studio
```

## One-time auth setup
1. **GitHub** — Org Owner creates a **GitHub App** (or fine-grained PAT) with read on:
   *Copilot Business*, *Administration*, *Members*, and *audit log*. Store the token in
   Key Vault as `ghcp-api-token`.
2. **Copilot Studio / App Insights** — Register an **Entra app** (service principal),
   grant it **Reader** on the App Insights resource. Store its client id/secret in Key Vault.
3. **Key Vault** — Create/identify the vault, add the secrets above, and add it as a
   **connection** in your Fabric workspace.

> Data model note: GitHub Copilot bills in **premium requests** and Copilot Studio in
> **messages/credits** — neither exposes raw tokens by default. Token counts require the
> custom telemetry in `docs/token_telemetry_setup.md`.

## Run order (in Fabric)
1. Upload `config/settings.yaml` to the Lakehouse **Files** area.
2. Import the `src/notebooks/*.py` files as Fabric notebooks (attach to the Lakehouse).
3. Run `01`, `02`, `03` (ingest) → then `04` (transform).
4. Orchestrate with the **Data Factory pipeline** in `pipelines/`: import
   `pl_copilot_analytics_daily.json`, replace the `<REPLACE_WITH_*>` notebook/workspace
   IDs, then attach `trg_copilot_analytics_daily.json` for a daily 06:00 UTC run.
5. Create the reporting views: run `sql/gold_views.sql` against the Lakehouse SQL
   analytics endpoint.
6. Build Power BI reports on the views (start with `vw_copilot_cost_daily`,
   `vw_copilot_cost_monthly`, `vw_github_copilot_adoption`).

## Reporting views (`sql/gold_views.sql`)
| View | Use |
| ---- | --- |
| `vw_copilot_cost_daily` | Unified daily cost/usage by source |
| `vw_copilot_cost_monthly` | Monthly rollup for finance / chargeback |
| `vw_github_copilot_cost_detail` | GitHub cost drill-down by SKU/repo |
| `vw_copilotstudio_token_usage` | Token usage by agent/model (needs telemetry) |
| `vw_github_copilot_adoption` | Assigned vs active seats + adoption % |

## Power BI starter (`powerbi/`)
A ready-to-open **PBIP** project with a full TMDL semantic model and an Overview report.

1. Open `powerbi/CopilotAnalytics.pbip` in **Power BI Desktop** (enable the
   *Power BI Project (.pbip)* preview if prompted).
2. On first refresh, set the two parameters:
   - **ServerEndpoint** → your Lakehouse **SQL analytics endpoint**
     (e.g. `xxxx.datawarehouse.fabric.microsoft.com`)
   - **DatabaseName** → the Lakehouse/Warehouse name that hosts the gold views.
3. Refresh. The model imports the views from `sql/gold_views.sql`.

**Included measures:** `Total Net Cost`, `Total Gross Cost`, `GitHub Copilot Cost`,
`Total Usage Units`, `Assigned Seats`, `Active Seats (30d)`, `Adoption % (30d)`,
`Cost per Active User`, `Total Tokens`, `Prompt Tokens`, `Completion Tokens`.

**Overview page:** KPI cards (total cost, GitHub cost, active seats, adoption %),
a cost-over-time line chart, and cost-by-source column chart.

## Dataverse (transcripts / CSAT / KPIs)
Use Fabric's **Link Dataverse to Microsoft Fabric** (zero-copy) to shortcut the
`ConversationTranscript` and analytics tables directly into the Lakehouse — no code needed.
Join them to the gold fact tables in your Power BI model.
