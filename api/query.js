// Proxies a fixed set of queries to the Databricks SQL Statement Execution API.
// The token never reaches the browser. Only queries listed below can run.

export const config = { maxDuration: 60 };

const QUERIES = {
  ping: `SELECT 1 AS ok`,
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

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function dbx(path, options) {
  const url = `https://${process.env.DBX_HOST}/api/2.0/sql/statements${path}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      Authorization: `Bearer ${process.env.DBX_TOKEN}`,
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
  });

  const text = await res.text();
  try {
    return { httpStatus: res.status, ...JSON.parse(text) };
  } catch {
    // Not JSON: usually an HTML login page, which means the host is wrong.
    return { httpStatus: res.status, raw: text.slice(0, 200) };
  }
}

export default async function handler(req, res) {
  const key = req.query.q;
  const statement = QUERIES[key];

  if (!statement) {
    return res.status(400).json({
      error: `Unknown query "${key}". Allowed: ${Object.keys(QUERIES).join(', ')}`,
    });
  }

  const missing = ['DBX_HOST', 'DBX_TOKEN', 'DBX_WAREHOUSE_ID'].filter((k) => !process.env[k]);
  if (missing.length) {
    return res.status(500).json({ error: `Missing environment variables: ${missing.join(', ')}` });
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

    // Databricks rejected the request before it ever became a statement.
    if (data.httpStatus >= 400 || (!data.statement_id && !data.status)) {
      return res.status(502).json({
        error: data.message || data.raw || `Databricks returned HTTP ${data.httpStatus}`,
        error_code: data.error_code,
        http_status: data.httpStatus,
      });
    }

    const id = data.statement_id;
    let waited = 0;
    while (['PENDING', 'RUNNING'].includes(data.status?.state) && waited < 20000) {
      await sleep(2000);
      waited += 2000;
      data = await dbx(`/${id}`, { method: 'GET' });
    }

    const state = data.status?.state;

    if (state !== 'SUCCEEDED') {
      const stillWaiting = state === 'PENDING' || state === 'RUNNING';
      return res.status(stillWaiting ? 504 : 502).json({
        error:
          data.status?.error?.message ||
          data.message ||
          `Statement ended in state ${state || 'UNKNOWN'}`,
        error_code: data.status?.error?.error_code || data.error_code,
        state,
        hint: stillWaiting ? 'The SQL warehouse is still starting. Refresh in a minute.' : undefined,
      });
    }

    const columns = (data.manifest?.schema?.columns || []).map((c) => ({
      name: c.name,
      type: c.type_name,
    }));

    res.setHeader('Cache-Control', 's-maxage=3600, stale-while-revalidate=86400');

    return res.status(200).json({
      columns,
      rows: data.result?.data_array || [],
      fetchedAt: new Date().toISOString(),
    });
  } catch (err) {
    return res.status(500).json({ error: `Proxy error: ${err.message}` });
  }
}
