-- ==========================================================================
-- Power BI-ready views over the Lakehouse GOLD layer
-- Run against the Lakehouse SQL analytics endpoint (or a Fabric Warehouse).
-- These views give a clean, business-friendly surface for a Power BI model.
-- Adjust the schema/prefix if you changed lakehouse.*_prefix in settings.yaml.
-- ==========================================================================

-- --------------------------------------------------------------------------
-- 1. Unified daily cost & usage (one row per date + source)
-- --------------------------------------------------------------------------
CREATE OR ALTER VIEW vw_copilot_cost_daily AS
SELECT
    f.usage_date,
    f.source,                                  -- 'github_copilot' | 'copilot_studio'
    CASE f.source
        WHEN 'github_copilot' THEN 'Premium requests'
        WHEN 'copilot_studio' THEN 'Tokens'
        ELSE 'Units'
    END                              AS usage_unit_type,
    f.usage_units,
    f.net_cost_usd,
    f.gross_cost_usd,
    d.year,
    d.month,
    d.year_month,
    d.day_of_week
FROM gold_fact_copilot_cost AS f
LEFT JOIN gold_dim_date   AS d
    ON f.usage_date = d.usage_date;

-- --------------------------------------------------------------------------
-- 2. Monthly cost rollup (finance / chargeback)
-- --------------------------------------------------------------------------
CREATE OR ALTER VIEW vw_copilot_cost_monthly AS
SELECT
    d.year_month,
    f.source,
    SUM(f.usage_units)   AS usage_units,
    SUM(f.net_cost_usd)  AS net_cost_usd,
    SUM(f.gross_cost_usd) AS gross_cost_usd
FROM gold_fact_copilot_cost AS f
LEFT JOIN gold_dim_date   AS d
    ON f.usage_date = d.usage_date
GROUP BY d.year_month, f.source;

-- --------------------------------------------------------------------------
-- 3. GitHub Copilot cost by SKU / repo (drill-down detail from silver)
-- --------------------------------------------------------------------------
CREATE OR ALTER VIEW vw_github_copilot_cost_detail AS
SELECT
    usage_date,
    org_name,
    repo_name,
    sku,
    unit_type,
    quantity          AS premium_requests,
    price_per_unit,
    gross_amount,
    discount_amount,
    net_amount
FROM silver_github_copilot_cost;

-- --------------------------------------------------------------------------
-- 4. Copilot Studio token usage by model / agent (only if token telemetry exists)
-- --------------------------------------------------------------------------
CREATE OR ALTER VIEW vw_copilotstudio_token_usage AS
SELECT
    usage_date,
    agent_id,
    model,
    COUNT(DISTINCT conversation_id) AS conversations,
    SUM(prompt_tokens)              AS prompt_tokens,
    SUM(completion_tokens)          AS completion_tokens,
    SUM(total_tokens)               AS total_tokens
FROM silver_copilotstudio_token_usage
GROUP BY usage_date, agent_id, model;

-- --------------------------------------------------------------------------
-- 5. GitHub Copilot seat adoption (active vs assigned)
--    'active' = last activity within the trailing 30 days.
-- --------------------------------------------------------------------------
CREATE OR ALTER VIEW vw_github_copilot_adoption AS
WITH seats AS (
    SELECT
        JSON_VALUE(payload, '$.assignee.login')  AS user_login,
        JSON_VALUE(payload, '$.plan_type')       AS plan_type,
        TRY_CAST(JSON_VALUE(payload, '$.last_activity_at') AS datetime2) AS last_activity_at
    FROM bronze_github_copilot_seats
)
SELECT
    plan_type,
    COUNT(*)                                                              AS assigned_seats,
    SUM(CASE WHEN last_activity_at >= DATEADD(day, -30, SYSUTCDATETIME())
             THEN 1 ELSE 0 END)                                          AS active_seats_30d,
    CAST(100.0 * SUM(CASE WHEN last_activity_at >= DATEADD(day, -30, SYSUTCDATETIME())
             THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS decimal(5,1))   AS adoption_pct_30d
FROM seats
GROUP BY plan_type;
