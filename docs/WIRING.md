# Wiring Guide — fill in these values when you're ready to deploy

Everything in this repo is **code-complete and documented**, but intentionally left
**un-wired** (placeholders only). This is the single checklist of every value you must
supply, where it lives, and how to get it. Nothing here contains secrets — real secrets
only ever go into **Azure Key Vault**.

Validate any time with:

```powershell
python scripts/validate_config.py
```

---

## Placeholder inventory (everything you must replace)

| # | Placeholder | File | How to obtain |
|---|-------------|------|---------------|
| 1 | `<your-github-org>` | [config/settings.yaml](../config/settings.yaml) | Your GitHub **org login** (org/enterprise Copilot plan required) |
| 2 | `ghcp-api-token` (secret name) | [config/settings.yaml](../config/settings.yaml) | Name of the Key Vault secret holding your GitHub token |
| 3 | `kv-copilot-analytics` | [config/settings.yaml](../config/settings.yaml) | Your Azure Key Vault name + URI |
| 4 | `app_id` `00000000-…` | [config/settings.yaml](../config/settings.yaml) | App Insights **Application ID** *(only if enabling Copilot Studio)* |
| 5 | `tenant_id` `00000000-…` | [config/settings.yaml](../config/settings.yaml) | Entra **tenant ID** *(only if enabling Copilot Studio)* |
| 6 | `<REPLACE_WITH_NOTEBOOK_ID_01..04>` | [pipelines/pl_copilot_analytics_daily.json](../pipelines/pl_copilot_analytics_daily.json) | Fabric notebook IDs after import |
| 7 | `<REPLACE_WITH_WORKSPACE_ID>` | [pipelines/pl_copilot_analytics_daily.json](../pipelines/pl_copilot_analytics_daily.json) | Fabric **workspace ID** (from the workspace URL) |
| 8 | `REPLACE-WITH-LAKEHOUSE-SQL-ENDPOINT` | [powerbi/.../ServerEndpoint.tmdl](../powerbi/CopilotAnalytics.SemanticModel/definition/tables/ServerEndpoint.tmdl) | Lakehouse **SQL analytics endpoint** |
| 9 | `REPLACE-WITH-LAKEHOUSE-NAME` | [powerbi/.../DatabaseName.tmdl](../powerbi/CopilotAnalytics.SemanticModel/definition/tables/DatabaseName.tmdl) | Lakehouse / Warehouse name hosting the gold views |

---

## A. GitHub Copilot access (items 1–2)

1. **Create credentials** — as an Org Owner, create a **GitHub App** (preferred) or a
   **fine-grained PAT** with **read** on: *Copilot Business*, *Administration*,
   *Members*, and *audit log*.
2. **Store the token in Key Vault** as a secret named exactly **`ghcp-api-token`**
   (or change `github.token_secret_name` to match your chosen name).
3. **Set the org** — in `config/settings.yaml`, replace `<your-github-org>` with your
   org login. If you use an enterprise plan, set `scope: "enterprise"` and fill
   `enterprise:`.

> The token value never goes in the repo — only its **Key Vault secret name** does.

## B. Azure Key Vault (item 3)

1. Create/identify the vault and note its **name** and **URI**
   (`https://<name>.vault.azure.net/`).
2. Update `key_vault.name` and `key_vault.uri` in `config/settings.yaml`.
3. In the **Fabric workspace**, add the vault as a **connection** so
   `notebookutils.credentials.getSecret(...)` can resolve secrets at runtime.

## C. Copilot Studio token telemetry (items 4–5) — *optional, deferred*

Currently `copilot_studio.enabled: false`, so notebook `03` skips and no App Insights
values are needed. When you're ready:

1. Emit custom token events from the agent — see
   [token_telemetry_setup.md](token_telemetry_setup.md).
2. Register an Entra **service principal**, grant **Reader** on the App Insights resource,
   and store its client id/secret in Key Vault
   (`appinsights-client-id`, `appinsights-client-secret`).
3. In `config/settings.yaml`: set `copilot_studio.enabled: true`, and fill
   `app_insights.app_id` and `app_insights.tenant_id`.
4. Re-run `python scripts/validate_config.py` — it now enforces these fields.

## D. Fabric notebooks + pipeline (items 6–7)

1. Import `src/notebooks/*.py` as Fabric notebooks and **attach each to the Lakehouse**.
2. Import [pipelines/pl_copilot_analytics_daily.json](../pipelines/pl_copilot_analytics_daily.json)
   into Data Factory.
3. Replace in the pipeline JSON:
   - `<REPLACE_WITH_WORKSPACE_ID>` → your Fabric workspace ID (found in the workspace URL:
     `.../groups/<workspaceId>/...`).
   - `<REPLACE_WITH_NOTEBOOK_ID_01>` → the imported **01** notebook's ID (repeat for 02–04).
     Get each ID from the notebook's URL or Settings pane.
4. Attach [pipelines/trg_copilot_analytics_daily.json](../pipelines/trg_copilot_analytics_daily.json)
   for the daily **06:00 UTC** schedule.

## E. Reporting views + Power BI (items 8–9)

1. Run [sql/gold_views.sql](../sql/gold_views.sql) against the Lakehouse **SQL analytics endpoint**.
2. Open [powerbi/CopilotAnalytics.pbip](../powerbi/CopilotAnalytics.pbip) in Power BI Desktop.
3. Set the two parameters (either in Desktop or by editing the TMDL files):
   - **ServerEndpoint** → `xxxxxxxx.datawarehouse.fabric.microsoft.com`
   - **DatabaseName** → the Lakehouse/Warehouse name hosting the gold views.
4. Refresh.

---

## Readiness checklist

- [ ] GitHub token stored in Key Vault (`ghcp-api-token`)
- [ ] `github.org` set in `settings.yaml`
- [ ] Key Vault name/URI set + added as a Fabric connection
- [ ] `python scripts/validate_config.py` passes (exit 0)
- [ ] Notebooks 01–04 imported and attached to Lakehouse
- [ ] `settings.yaml` uploaded to Lakehouse Files
- [ ] Pipeline notebook/workspace IDs replaced
- [ ] Daily trigger attached
- [ ] `gold_views.sql` executed on SQL endpoint
- [ ] Power BI parameters set and model refreshed
- [ ] *(optional)* Copilot Studio telemetry enabled

> **Nothing above is wired yet** — this repo ships ready-to-configure. Work top to bottom
> and re-run the validator after editing `settings.yaml`.
