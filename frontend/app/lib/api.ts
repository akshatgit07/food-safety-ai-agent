/** Shared helpers for talking to the FastAPI backend. */

export function apiBase(apiUrl?: string): string {
  if (!apiUrl) throw new Error('NEXT_PUBLIC_API_URL is not configured.');
  return apiUrl.replace(/\/$/, '');
}

export async function readJson(response: Response): Promise<any> {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { detail: text || 'Non-JSON response from backend' };
  }
}

/**
 * FastAPI returns `detail` as a string for HTTPException but as an array of
 * validation objects for a 422. Interpolating that array straight into an Error
 * rendered "[object Object]" in the UI, hiding which field was rejected.
 */
export function errorMessage(payload: any, status: number): string {
  const detail = payload?.detail;

  if (typeof detail === 'string' && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const parts = detail
      .map((entry) => {
        if (typeof entry === 'string') return entry;
        const field = Array.isArray(entry?.loc)
          ? entry.loc.filter((part: unknown) => part !== 'body').join('.')
          : '';
        const message = entry?.msg ?? 'is invalid';
        return field ? `${field}: ${message}` : message;
      })
      .filter(Boolean);
    if (parts.length) return parts.join('; ');
  }

  if (detail && typeof detail === 'object') {
    const message = (detail as any).msg ?? (detail as any).message;
    if (typeof message === 'string' && message.trim()) return message;
  }

  return `Backend returned ${status}`;
}

/** fetch + parse + raise a readable error. */
export async function requestJson(apiUrl: string | undefined, path: string, options?: RequestInit): Promise<any> {
  const response = await fetch(`${apiBase(apiUrl)}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
  });
  const payload = await readJson(response);
  if (!response.ok) throw new Error(errorMessage(payload, response.status));
  return payload;
}
