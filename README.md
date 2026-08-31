# Healthcare Claims Fraud Detection — Live Dashboard

A public dashboard that queries Databricks live. The browser calls a serverless function;
the function holds the token and calls the Databricks SQL Statement Execution API.

```
Browser  →  /api/query  →  Databricks SQL warehouse  →  Unity Catalog
             (Vercel)        (token lives here)
```

## Files

| File | Purpose |
| --- | --- |
| `index.html` | The dashboard. No build step. |
| `api/query.js` | Serverless proxy. Holds the whitelist of allowed queries. |
| `package.json` | Marks the API file as an ES module. |
| `.env.example` | Names of the three secrets. |

## What you need

Three values, all of which you already have:

- `DBX_HOST` — workspace hostname, no `https://`, e.g. `dbc-a1b2c3d4-e5f6.cloud.databricks.com`
- `DBX_TOKEN` — the personal access token with the `sql` scope
- `DBX_WAREHOUSE_ID` — the part after `/sql/1.0/warehouses/` in the warehouse HTTP path

## Deploy

1. Create a GitHub repository and upload these files.
2. Sign in at vercel.com with GitHub.
3. Add New → Project → import the repository.
4. Framework preset: **Other**. Leave build and output settings empty.
5. Expand **Environment Variables** and add the three values above.
6. Deploy.

## Changing what is displayed

The queries live in the `QUERIES` object at the top of `api/query.js`. Edit the SQL there.
The front end reads whatever columns come back: the first column becomes the x-axis and the
remaining numeric columns become series, so no front-end change is needed when the shape
of a view changes.

To add a panel: add an entry to `QUERIES`, add a `<section class="panel">` block to
`index.html` with matching `frame-` and `table-` ids, and add the id to the `PANELS` array.

## Caching

Responses cache at the edge for one hour (`s-maxage=3600`). This exists to protect the
Databricks Free Edition compute quota — without it, every page view would wake the
warehouse. The Refresh button bypasses the cache.

## Token expiry

The token expires on the lifetime you chose when generating it. When it does, every panel
will show an error. Generate a new token in Databricks, update `DBX_TOKEN` in Vercel's
project settings, and redeploy.
