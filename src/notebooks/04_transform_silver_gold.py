# Fabric notebook source
# ==========================================================================
# 04_transform_silver_gold — shape bronze into Silver + Gold analytics tables
# ==========================================================================
# Builds:
#   silver_github_copilot_cost      (typed cost line-items)
#   silver_copilotstudio_token_usage(typed token telemetry)
#   gold_fact_copilot_cost          (unified daily cost + volume fact)
#   gold_dim_date                   (date dimension)
# --------------------------------------------------------------------------

# MAGIC %run ./00_common

# CELL ********************

from pyspark.sql import functions as F

cfg = load_config()
bronze = cfg["lakehouse"]["bronze_prefix"]
silver = cfg["lakehouse"]["silver_prefix"]
gold = cfg["lakehouse"]["gold_prefix"]

# CELL ********************
# ---- Silver: GitHub Copilot cost (parse JSON payload -> columns) ----
raw_cost = spark.read.table(f"{bronze}github_copilot_cost")  # noqa: F821

cost_schema = (
    "date STRING, product STRING, sku STRING, quantity DOUBLE, unitType STRING, "
    "pricePerUnit DOUBLE, grossAmount DOUBLE, discountAmount DOUBLE, netAmount DOUBLE, "
    "organizationName STRING, repositoryName STRING"
)

silver_cost = (
    raw_cost
    .withColumn("j", F.from_json("payload", cost_schema))
    .select(
        F.to_date("j.date").alias("usage_date"),
        F.col("j.product").alias("product"),
        F.col("j.sku").alias("sku"),
        F.col("j.quantity").alias("quantity"),          # premium requests for Copilot SKUs
        F.col("j.unitType").alias("unit_type"),
        F.col("j.pricePerUnit").alias("price_per_unit"),
        F.col("j.grossAmount").alias("gross_amount"),
        F.col("j.discountAmount").alias("discount_amount"),
        F.col("j.netAmount").alias("net_amount"),
        F.col("j.organizationName").alias("org_name"),
        F.col("j.repositoryName").alias("repo_name"),
        F.col("_ingested_at_utc"),
    )
    .dropDuplicates(["usage_date", "sku", "org_name", "repo_name", "quantity", "net_amount"])
)
silver_cost.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{silver}github_copilot_cost")

# CELL ********************
# ---- Silver: Copilot Studio token usage ----
token_schema = (
    "timestamp STRING, conversationId STRING, agentId STRING, model STRING, "
    "promptTokens LONG, completionTokens LONG, totalTokens LONG, operation_Id STRING"
)
try:
    raw_tok = spark.read.table(f"{bronze}copilotstudio_token_usage")  # noqa: F821
    silver_tok = (
        raw_tok
        .withColumn("j", F.from_json("payload", token_schema))
        .select(
            F.to_timestamp("j.timestamp").alias("event_time"),
            F.to_date(F.to_timestamp("j.timestamp")).alias("usage_date"),
            F.col("j.conversationId").alias("conversation_id"),
            F.col("j.agentId").alias("agent_id"),
            F.col("j.model").alias("model"),
            F.col("j.promptTokens").alias("prompt_tokens"),
            F.col("j.completionTokens").alias("completion_tokens"),
            F.col("j.totalTokens").alias("total_tokens"),
        )
    )
    silver_tok.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{silver}copilotstudio_token_usage")
    has_tokens = True
except Exception as e:
    print(f"[info] token usage table not available yet: {e}")
    has_tokens = False

# CELL ********************
# ---- Gold: unified daily cost/volume fact ----
gh_daily = (
    spark.read.table(f"{silver}github_copilot_cost")  # noqa: F821
    .groupBy("usage_date")
    .agg(
        F.lit("github_copilot").alias("source"),
        F.sum("quantity").alias("usage_units"),          # premium requests
        F.sum("net_amount").alias("net_cost_usd"),
        F.sum("gross_amount").alias("gross_cost_usd"),
    )
)

if has_tokens:
    cs_daily = (
        spark.read.table(f"{silver}copilotstudio_token_usage")  # noqa: F821
        .groupBy("usage_date")
        .agg(
            F.lit("copilot_studio").alias("source"),
            F.sum("total_tokens").cast("double").alias("usage_units"),  # tokens
            F.lit(None).cast("double").alias("net_cost_usd"),
            F.lit(None).cast("double").alias("gross_cost_usd"),
        )
    )
    fact = gh_daily.select("usage_date", "source", "usage_units", "net_cost_usd", "gross_cost_usd").unionByName(cs_daily)
else:
    fact = gh_daily.select("usage_date", "source", "usage_units", "net_cost_usd", "gross_cost_usd")

fact.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{gold}fact_copilot_cost")

# CELL ********************
# ---- Gold: date dimension ----
dates = fact.select("usage_date").distinct()
dim_date = (
    dates
    .withColumn("year", F.year("usage_date"))
    .withColumn("month", F.month("usage_date"))
    .withColumn("day", F.dayofmonth("usage_date"))
    .withColumn("day_of_week", F.dayofweek("usage_date"))
    .withColumn("year_month", F.date_format("usage_date", "yyyy-MM"))
)
dim_date.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{gold}dim_date")

print("Gold tables built: fact_copilot_cost, dim_date")
