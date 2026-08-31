// Proxies a fixed set of queries to the Databricks SQL Statement Execution API.
// The token never reaches the browser. Only queries listed below can run.

export const config = { maxDuration: 60 };

const QUERIES = {
  prediction: `
    SELECT *
    FROM healthcare_fraud.ml.v_prediction_drift
    ORDER BY 1
  `,
  performance: `
    SELECT *
    FROM healthcare_fraud.ml.v_performance_drift
    ORDER BY 1
  `,
  psi: `
    SELECT *
    FROM healthcare_fraud.ml.feature_drift_psi
    ORDER BY 2 DESC
  `,
};

const API = (host, path) => `https://${host}/api/2.0/sql/statements${path}`;

async function dbx(path, options) {
  const host = process.env.DBX_HOST;
  const res = await fetch(API(host, path), {
    ...options,
    headers: {
      Authorization: `Bearer ${process.env.DBX_TOKEN}`,
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
  });
  return res.json();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export default async function handler(req, res) {
  const key = req.query.q;
  const statement = QUERIES[key];

  if (!statement) {
    return res.status(400).json({ error: `Unknown query: ${key}` });
  }

  if (!process.env.DBX_HOST || !process.env.DBX_TOKEN || !process.env.DBX_WAREHOUSE_ID) {
    return res.status(500).json({ error: 'Missing DBX_HOST, DBX_TOKEN or DBX_WAREHOUSE_ID' });
  }

  try {
    let data = await dbx('', {
      method: 'POST',
      body: JSON.stringify({
        warehouse_id: process.env.DBX_WAREHOUSE_ID,
        statement: statement.trim(),
        wait_timeout: '30s',
        on_wait_timeout: 'CONTINUE',
        format: 'JSON_ARRAY',
        disposition: 'INLINE',
      }),
    });

    // The warehouse may be cold. Poll until it settles or we run out of budget.
    const id = data.statement_id;
    let waited = 0;
    while (['PENDING', 'RUNNING'].includes(data.status?.state) && waited < 20000) {
      await sleep(2000);
      waited += 2000;
      data = await dbx(`/${id}`, { method: 'GET' });
    }

    const state = data.status?.state;

    if (state !== 'SUCCEEDED') {
      const detail = data.status?.error?.message || `Query ${state || 'did not complete'}`;
      const code = state === 'PENDING' || state === 'RUNNING' ? 504 : 502;
      return res.status(code).json({
        error: detail,
        hint: code === 504 ? 'The SQL warehouse is starting up. Refresh in about a minute.' : undefined,
      });
    }

    const columns = (data.manifest?.schema?.columns || []).map((c) => ({
      name: c.name,
      type: c.type_name,
    }));

    // Cached at the edge so heavy traffic does not repeatedly wake the warehouse.
    res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate=86400');

    return res.status(200).json({
      columns,
      rows: data.result?.data_array || [],
      fetchedAt: new Date().toISOString(),
    });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
}
