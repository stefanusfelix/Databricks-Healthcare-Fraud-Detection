# Healthcare Claims Fraud Detection — Monitoring Dashboard

A public dashboard for a fraud detection model built on Databricks. The page reads JSON
snapshots exported from Unity Catalog, so it needs no credentials and no backend.

```
Databricks notebook  →  data/*.json  →  git push  →  Vercel redeploy
```

## Files

| File | Purpose |
| --- | --- |
| `index.html` | The dashboard. No build step. |
| `data/*.json` | One snapshot per panel. Created by the notebook. |
| `notebooks/export_dashboard_data.py` | Queries the views and writes the snapshots. |

## Refreshing the data

1. In Databricks, open the Git folder connected to this repository.
2. Run `notebooks/export_dashboard_data.py`.
3. Click the branch name in the sidebar, then **Commit & Push**.

Vercel redeploys automatically on push.

## Adding a panel

1. Add an entry to `QUERIES` in the notebook.
2. Add a `<section class="panel">` block to `index.html` with matching `frame-` and
   `table-` ids.
3. Add the id to the `PANELS` array in `index.html`.

The page reads whatever columns the query returns: the first column becomes the x-axis
and the remaining numeric columns become series.

## Deploying

Import the repository at vercel.com. Framework preset **Other**, no build command, no
output directory, no environment variables.
