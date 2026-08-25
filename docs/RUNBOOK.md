# Operations Runbook — Fabric setup → Bronze/Silver/Gold → Analytics

End-to-end, do-this-then-that runbook. Covers **(1)** standing up Fabric, **(2)** ingesting
into Bronze, **(3)** building Silver and Gold, **(4)** verifying each layer, and
**(5)** pulling data back out for analytics. Pairs with
[architecture.md](architecture.md) (diagrams) and [WIRING.md](WIRING.md) (placeholder values).

---

## 1. Fabric setup (one-time)

| Step | Action | Where |
|------|--------|-------|
| 1.1 | Ensure a **Fabric capacity** is available (Trial, F-SKU, or P-SKU) | Fabric Admin portal |
| 1.2 | Create a **workspace** and assign it to that capacity | Fabric → Workspaces → New |
| 1.3 | Create a **Lakehouse** in the workspace (e.g. `CopilotAnalytics_LH`) | Workspace → New → Lakehouse |
| 1.4 | Note the Lakehouse **SQL analytics endpoint** and **name** (needed for Power BI) | Lakehouse → Settings → SQL endpoint |
| 1.5 | Create/identify an **Azure Key Vault**; add secret `ghcp-api-token` | Azure portal |
| 1.6 | Add the Key Vault as a **connection** in Fabric so notebooks can read secrets | Workspace → Manage connections |
| 1.7 | Upload `config/settings.yaml` into the Lakehouse **Files** area | Lakehouse → Files → Upload |
| 1.8 | Import `src/notebooks/*.py` as notebooks and **attach each to the Lakehouse** | Workspace → New → Import notebook |

> The workspace ID (from the URL `.../groups/<workspaceId>/...`) and each notebook ID are
> what you paste into the pipeline JSON — see [WIRING.md §D](WIRING.md).

---

## 2. Ingest into Bronze (raw)

Run the ingestion notebooks (manually the first time, then via the pipeline). Each lands
**raw JSON payloads** as Delta tables — schema-stable, append-friendly.

| Run order | Notebook | Bronze tables produced | Write mode |
|-----------|----------|------------------------|-----------|
| 1 | [01_github_cost_usage.py](../src/notebooks/01_github_cost_usage.py) | `bronze_github_copilot_cost`, `bronze_github_billing_usage_all` | append |
| 2 | [02_github_seats_audit.py](../src/notebooks/02_github_seats_audit.py) | `bronze_github_copilot_seats` (snapshot), `bronze_github_copilot_audit` | overwrite / append |
| 3 | [03_copilotstudio_appinsights_tokens.py](../src/notebooks/03_copilotstudio_appinsights_tokens.py) | `bronze_copilotstudio_token_usage` *(skipped while `enabled: false`)* | append |

**What happens:** notebooks read config from the Lakehouse Files `settings.yaml`, pull the
GitHub token from Key Vault, call the GitHub APIs for the last `lookback_days`, filter to
Copilot line-items, and write each raw record as a `payload` JSON column plus
`_ingested_at_utc`.

**Verify Bronze:**
```sql
SELECT COUNT(*) AS rows, MAX(_ingested_at_utc) AS last_load
FROM bronze_github_copilot_cost;
```

---

## 3. Build Silver + Gold (typed + modeled)

Run [04_transform_silver_gold.py](../src/notebooks/04_transform_silver_gold.py) **after**
the ingestion notebooks.

**Silver** — parse the JSON `payload` into typed, deduplicated columns:

| Table | Grain | Source |
|-------|-------|--------|
| `silver_github_copilot_cost` | one row per date/sku/org/repo | `bronze_github_copilot_cost` |
| `silver_copilotstudio_token_usage` | one row per token event *(if enabled)* | `bronze_copilotstudio_token_usage` |

**Gold** — business-ready star schema:

| Table | Grain | Notes |
|-------|-------|-------|
| `gold_fact_copilot_cost` | one row per `usage_date` + `source` | `usage_units`, `net_cost_usd`, `gross_cost_usd` |
| `gold_dim_date` | one row per date | year / month / year_month / day_of_week |

**Verify Gold:**
```sql
SELECT source, SUM(usage_units) AS units, SUM(net_cost_usd) AS net_cost
FROM gold_fact_copilot_cost
GROUP BY source;
```

---

## 4. Orchestrate & schedule

1. Import [pipelines/pl_copilot_analytics_daily.json](../pipelines/pl_copilot_analytics_daily.json)
   into Data Factory; map notebook/workspace IDs ([WIRING.md §D](WIRING.md)).
2. The pipeline chains **01 → 02 → 03 → 04** with retries. `03` uses a
   `Succeeded, Completed` dependency so `04` still runs when token telemetry is skipped.
3. Attach [pipelines/trg_copilot_analytics_daily.json](../pipelines/trg_copilot_analytics_daily.json)
   for the daily **06:00 UTC** run.

---

## 5. Pull data OUT of Fabric for analytics

Once Gold exists and [sql/gold_views.sql](../sql/gold_views.sql) is executed against the
**SQL analytics endpoint**, consumers can read the data several ways:

### 5a. Power BI (recommended)
- Open [powerbi/CopilotAnalytics.pbip](../powerbi/CopilotAnalytics.pbip), set the
  **ServerEndpoint** + **DatabaseName** parameters, refresh.
- Prebuilt measures + Overview page (cost, adoption %, active seats, trend).
- For live data with no import, switch the model to **Direct Lake** on the Lakehouse.

### 5b. T-SQL via the SQL analytics endpoint
Query the Gold tables/views directly from any T-SQL client:
```sql
-- Daily unified cost/usage
SELECT * FROM vw_copilot_cost_daily ORDER BY usage_date DESC;

-- Monthly finance rollup
SELECT * FROM vw_copilot_cost_monthly ORDER BY year_month DESC;

-- Adoption
SELECT * FROM vw_github_copilot_adoption;
```

### 5c. Excel / SSMS / Azure Data Studio
- Connect to the Lakehouse **SQL analytics endpoint** (looks like
  `xxxx.datawarehouse.fabric.microsoft.com`) with Entra auth.
- In Excel: **Data → Get Data → From Azure → Azure SQL** using that endpoint; pick the
  `vw_*` views.

### 5d. Fabric / Spark notebooks
```python
df = spark.read.table("gold_fact_copilot_cost")
display(df.groupBy("source").sum("net_cost_usd"))
```

### 5e. Semantic model / XMLA (Analyze in Excel, Tabular Editor)
- Publish the `CopilotAnalytics` semantic model; connect via the workspace **XMLA endpoint**
  for pivot tables or external modeling tools.

### 5f. OneLake direct access
- Gold Delta tables live in **OneLake** and are reachable via the OneLake file/ABFS path
  or the OneLake APIs for custom downstream jobs.

**Reporting views reference:**

| View | Purpose |
|------|---------|
| `vw_copilot_cost_daily` | Unified daily cost/usage by source |
| `vw_copilot_cost_monthly` | Monthly rollup for finance / chargeback |
| `vw_github_copilot_cost_detail` | GitHub cost drill-down by SKU / repo |
| `vw_copilotstudio_token_usage` | Token usage by agent/model *(needs telemetry)* |
| `vw_github_copilot_adoption` | Assigned vs active seats + adoption % |

---

## 6. End-to-end checklist

- [ ] Capacity + workspace + Lakehouse created
- [ ] Key Vault connected; `settings.yaml` uploaded to Files
- [ ] Notebooks imported and attached
- [ ] **Bronze**: 01–03 run, tables verified
- [ ] **Silver + Gold**: 04 run, `gold_fact_copilot_cost` populated
- [ ] Pipeline mapped + daily trigger attached
- [ ] `gold_views.sql` executed on the SQL endpoint
- [ ] Analytics consumer connected (Power BI / T-SQL / Excel)
