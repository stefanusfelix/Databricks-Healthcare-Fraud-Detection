# Databricks notebook source
# MAGIC %md
# MAGIC # Export dashboard snapshots
# MAGIC
# MAGIC Reads the monitoring views and writes one JSON file per panel into `data/`
# MAGIC inside this Git folder. Commit and push from the Databricks Git UI afterwards;
# MAGIC Vercel redeploys on push.

# COMMAND ----------

import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

# Panel id -> query. The ids must match the PANELS array in index.html.
QUERIES = {
    "prediction":  "SELECT * FROM healthcare_fraud.ml.v_prediction_drift ORDER BY 1",
    "performance": "SELECT * FROM healthcare_fraud.ml.v_performance_drift ORDER BY 1",
    "psi":         "SELECT * FROM healthcare_fraud.ml.feature_drift_psi ORDER BY 2 DESC",
}

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
        "fetchedAt": datetime.utcnow().isoformat() + "Z",
    }

    path = DATA_DIR / f"{panel_id}.json"
    path.write_text(json.dumps(payload, indent=2))

    print(f"{panel_id:12s} {len(rows):4d} rows, {len(columns)} columns -> {path.name}")
    return payload


snapshots = {pid: export(pid, sql) for pid, sql in QUERIES.items()}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Check the shape
# MAGIC
# MAGIC The page uses the first column as the x-axis and every other numeric column as a
# MAGIC series. If a chart looks wrong, reorder the columns in the SELECT above.

# COMMAND ----------

for pid, payload in snapshots.items():
    names = [c["name"] for c in payload["columns"]]
    print(f"{pid}: x-axis = {names[0]!r}, series = {names[1:]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Publish
# MAGIC
# MAGIC 1. Open the Git folder in the sidebar and click the branch name.
# MAGIC 2. The three files under `data/` appear as changes. Add a message and **Commit & Push**.
# MAGIC 3. Vercel picks up the push and redeploys within about a minute.
# MAGIC
# MAGIC To refresh on a schedule, attach this notebook to a Job. Note that a Job can write
# MAGIC the files but cannot push them, so scheduled runs still need a manual push unless you
# MAGIC add a Git push step of your own.
