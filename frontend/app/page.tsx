'use client';

import { useEffect, useState } from 'react';

type HealthResponse = {
  status?: string;
  project?: string;
  healthy?: boolean;
};

export default function Home() {
  const [data, setData] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  useEffect(() => {
    async function checkBackend() {
      if (!apiUrl) {
        setError('NEXT_PUBLIC_API_URL is not configured in Vercel.');
        return;
      }

      try {
        const response = await fetch(`${apiUrl}/health`);
        if (!response.ok) {
          throw new Error(`Backend returned ${response.status}`);
        }
        setData(await response.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unable to reach backend');
      }
    }

    checkBackend();
  }, [apiUrl]);

  return (
    <main className="page-shell">
      <section className="hero-card">
        <p className="eyebrow">Guiltless AI Prototype</p>
        <h1>Food Safety AI Agent</h1>
        <p className="subtitle">
          A nutrition assistant for meal planning, food recommendations,
          shopping lists, and product intelligence.
        </p>

        <div className="status-card">
          <span className={`status-dot ${data ? 'online' : error ? 'offline' : ''}`} />
          <div>
            <strong>Backend status</strong>
            <p>
              {data
                ? 'Connected to the FastAPI service on Render.'
                : error
                  ? error
                  : 'Checking Render backend...'}
            </p>
          </div>
        </div>

        {data && <pre>{JSON.stringify(data, null, 2)}</pre>}
      </section>
    </main>
  );
}
