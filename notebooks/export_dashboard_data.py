# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # Export dashboard snapshots
# MAGIC
# MAGIC Reads the monitoring views and writes one JSON file per panel into `data/`
# MAGIC inside this Git folder. Commit and push from the Databricks Git UI afterwards;
# MAGIC Vercel redeploys on push.

# COMMAND ----------

import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

# Panel id -> query. Ids must match the ones index.html asks for.
# Only the columns the charts need are selected, in a fixed order.
QUERIES = {
    "performance": """
        SELECT month, recall, precision, f1, tp, fp, fn
        FROM healthcare_fraud.ml.v_performance_drift
        ORDER BY month
    """,
    "prediction": """
        SELECT month, flagged_pct, n_scored, n_flagged, mean_probability, threshold
        FROM healthcare_fraud.ml.v_prediction_drift
        ORDER BY month
    """,
    "psi": """
        SELECT feature, psi, severity, n_current
        FROM healthcare_fraud.ml.feature_drift_psi
        WHERE month = (SELECT MAX(month) FROM healthcare_fraud.ml.feature_drift_psi)
        ORDER BY psi DESC
        LIMIT 15
    """,
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Business impact
# MAGIC
# MAGIC **Check the column names in `BASE` below against your own `fraud_predictions` table
# MAGIC before running.** Everything else is derived from it, so this is the only block to edit.

# COMMAND ----------

COST_PER_INVESTIGATION = 280

# The five things every business figure is derived from. Rename the left-hand
# expressions to match your table; keep the aliases exactly as they are.
BASE = """
    SELECT
        date_trunc('month', p.claim_submission_date) AS month,
        g.is_fraud                                   AS actual,
        p.predicted_label                            AS predicted,
        g.claim_amount                               AS amount
    FROM healthcare_fraud.ml.fraud_predictions p
    JOIN healthcare_fraud.gold.claim_features_gold g
      ON g.claim_id = p.claim_id
"""

QUERIES["business_kpis"] = f"""
    WITH base AS ({BASE})
    SELECT
        COUNT(*)                                                        AS claims_scored,
        SUM(CASE WHEN actual = 1 AND predicted = 1 THEN 1 ELSE 0 END)   AS fraud_caught,
        SUM(CASE WHEN actual = 1 AND predicted = 0 THEN 1 ELSE 0 END)   AS fraud_missed,
        SUM(CASE WHEN actual = 0 AND predicted = 1 THEN 1 ELSE 0 END)   AS false_alarms,
        ROUND(percentile_approx(amount, 0.5), 0)                        AS median_claim,
        ROUND(MAX(amount), 0)                                           AS max_claim,
        ROUND(SUM(CASE WHEN actual = 1 AND predicted = 1 THEN amount ELSE 0 END), 0) AS value_stopped,
        ROUND(SUM(CASE WHEN actual = 1 AND predicted = 0 THEN amount ELSE 0 END), 0) AS loss_missed,
        ROUND(SUM(CASE WHEN actual = 0 AND predicted = 1 THEN 1 ELSE 0 END)
              * {COST_PER_INVESTIGATION}, 0)                            AS cost_investigations
    FROM base
"""

QUERIES["business_monthly"] = f"""
    WITH base AS ({BASE})
    SELECT
        date_format(month, 'MMM yyyy')                                  AS month,
        SUM(CASE WHEN actual = 1 AND predicted = 1 THEN 1 ELSE 0 END)   AS fraud_caught,
        SUM(CASE WHEN actual = 1 AND predicted = 0 THEN 1 ELSE 0 END)   AS fraud_missed,
        ROUND(SUM(CASE WHEN actual = 1 AND predicted = 1 THEN amount ELSE 0 END), 0) AS value_stopped,
        ROUND(SUM(CASE WHEN actual = 1 AND predicted = 0 THEN amount ELSE 0 END)
              + SUM(CASE WHEN actual = 0 AND predicted = 1 THEN 1 ELSE 0 END)
                * {COST_PER_INVESTIGATION}, 0)                          AS total_cost
    FROM base
    GROUP BY month
    ORDER BY month
"""

# COMMAND ----------

# This notebook lives in <repo>/notebooks/, so the repo root is one level up.
NOTEBOOK_DIR = Path(
    dbutils.notebook.entry_point.getDbutils().notebook().getContext()
    .notebookPath().get()
).parent

REPO_ROOT = Path("/Workspace") / NOTEBOOK_DIR.relative_to("/").parent
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

print(f"Writing snapshots to {DATA_DIR}")

# COMMAND ----------

def to_jsonable(v):
    """Spark types that json.dumps cannot handle on its own."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (int, float, str, bool)):
        return v
    return str(v)


def export(panel_id, sql):
    sdf = spark.sql(sql)

    columns = [{"name": f.name, "type": f.dataType.simpleString()} for f in sdf.schema.fields]
    rows = [[to_jsonable(v) for v in row] for row in sdf.collect()]

    payload = {
        "columns": columns,
        "rows": rows,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
    }

    path = DATA_DIR / f"{panel_id}.json"
    path.write_text(json.dumps(payload, indent=2))

    print(f"{panel_id:18s} {len(rows):4d} rows, {len(columns)} columns -> {path.name}")
    return payload


snapshots = {}
failures = {}

for pid, sql in QUERIES.items():
    try:
        snapshots[pid] = export(pid, sql)
    except Exception as e:
        failures[pid] = str(e).split("\n")[0]
        print(f"{pid:18s} FAILED — {failures[pid][:120]}")

print(f"\n{len(snapshots)} exported, {len(failures)} failed")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Check what was exported

# COMMAND ----------

for pid, payload in snapshots.items():
    names = [c["name"] for c in payload["columns"]]
    print(f"{pid:12s} {len(payload['rows']):4d} rows  columns = {names}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Publish
# MAGIC
# MAGIC 1. Click the Git button at the top of this Git folder.
# MAGIC 2. Tick the three files under `data/`, add a message, then **Commit & Push**.
# MAGIC 3. Vercel redeploys within about a minute.