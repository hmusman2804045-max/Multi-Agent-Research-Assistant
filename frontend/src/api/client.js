/**
 * HTTP client for the research API.
 *
 * The backend returns a uniform error envelope ({error, message, ...}) and never
 * rewrites the messages raised by the core Python modules, so this layer surfaces
 * `message` verbatim and keeps the structured fields the UI needs to tell the
 * different failure modes apart.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(status, payload) {
    super(payload?.message || 'Request failed.');
    this.name = 'ApiError';
    this.status = status;
    this.code = payload?.error || 'unknown_error';
    this.retryAfterSeconds = payload?.retry_after_seconds ?? null;
    this.remainingLockoutSeconds = payload?.remaining_lockout_seconds ?? null;
    // 'personal' vs 'global' for daily quota failures — two different situations.
    this.capScope = payload?.cap_scope ?? null;
  }
}

async function parseBody(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}

async function request(path, { method = 'GET', body, token, signal } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (err.name === 'AbortError') throw err;
    throw new ApiError(0, { error: 'network_error', message: 'Could not reach the research service.' });
  }

  const payload = await parseBody(response);
  if (!response.ok) throw new ApiError(response.status, payload);
  return payload;
}

/* ===== Auth ================================================================= */

export const register = (username, password, email) =>
  request('/auth/register', { method: 'POST', body: { username, password, email: email || null } });

export const login = (username, password) =>
  request('/auth/login', { method: 'POST', body: { username, password } });

export const forgotPassword = (identifier) =>
  request('/auth/forgot-password', { method: 'POST', body: { identifier } });

export const resetPassword = (token, newPassword) =>
  request('/auth/reset-password', { method: 'POST', body: { token, new_password: newPassword } });

/* ===== Quota & history ====================================================== */

export const getQuota = ({ token, guestId, signal } = {}) => {
  const qs = !token && guestId ? `?session_id=${encodeURIComponent(guestId)}` : '';
  return request(`/quota${qs}`, { token, signal });
};

export const listHistory = (token, signal) => request('/history', { token, signal });

export const getHistoryItem = (token, sessionId, signal) =>
  request(`/history/${encodeURIComponent(sessionId)}`, { token, signal });

export const deleteHistoryItem = (token, sessionId) =>
  request(`/history/${encodeURIComponent(sessionId)}`, { method: 'DELETE', token });

export const getHealth = (signal) => request('/health', { signal });

/* ===== Research stream ====================================================== */

/**
 * Open the research SSE stream.
 *
 * `fetch` is used rather than `EventSource` for two reasons: EventSource cannot send
 * an Authorization header (the access token must never travel in a URL), and it cannot
 * surface the HTTP status of a rejected request — which is exactly how the backend
 * reports a spent quota or an invalid query before the stream opens.
 *
 * @param {object} args
 * @param {string} args.query       The research question.
 * @param {string} [args.token]     Bearer token for an authenticated run.
 * @param {string} [args.guestId]   Scoped guest id for an unauthenticated run.
 * @param {AbortSignal} [args.signal]
 * @param {(event: string, data: object) => void} args.onEvent
 */
export async function streamResearch({ query, token, guestId, signal, onEvent }) {
  const params = new URLSearchParams({ query });
  if (!token && guestId) params.set('session_id', guestId);

  const headers = { Accept: 'text/event-stream' };
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(`${BASE_URL}/research/stream?${params.toString()}`, { headers, signal });
  } catch (err) {
    if (err.name === 'AbortError') throw err;
    throw new ApiError(0, { error: 'network_error', message: 'Could not reach the research service.' });
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseBody(response));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const parsed = parseFrame(frame);
      if (parsed) onEvent(parsed.event, parsed.data);
    }
  }
}

function parseFrame(frame) {
  const trimmed = frame.trim();
  // ':' prefixed frames are keep-alive comments.
  if (!trimmed || trimmed.startsWith(':')) return null;

  let event = 'message';
  const dataLines = [];
  for (const line of trimmed.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;

  try {
    return { event, data: JSON.parse(dataLines.join('')) };
  } catch {
    return null;
  }
}
