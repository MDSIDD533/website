const JSON_HEADERS = { 'Content-Type': 'application/json' };

const configuredApiBase = (import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '');
const configuredWsBase = (import.meta.env.VITE_WS_URL || '').trim().replace(/\/+$/, '');

export const API_BASE_URL = configuredApiBase;

export function apiUrl(path: string): string {
  if (!path) return API_BASE_URL || path;
  if (/^(?:https?:)?\/\//i.test(path) || path.startsWith('data:') || path.startsWith('blob:')) {
    return path;
  }
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return API_BASE_URL ? `${API_BASE_URL}${normalizedPath}` : normalizedPath;
}

function jobsWebSocketUrl(): string {
  if (configuredWsBase) return configuredWsBase;
  if (API_BASE_URL) {
    return `${API_BASE_URL.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:')}/ws/jobs`;
  }
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/ws/jobs`;
}

async function handleResp<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      msg = data.detail || data.message || msg;
    } catch {
      const txt = await res.text();
      if (txt) msg = txt;
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T = any>(path: string) => fetch(apiUrl(path)).then((r) => handleResp<T>(r)),
  post: <T = any>(path: string, body?: unknown) =>
    fetch(apiUrl(path), {
      method: 'POST',
      headers: JSON_HEADERS,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }).then((r) => handleResp<T>(r)),
  patch: <T = any>(path: string, body: unknown) =>
    fetch(apiUrl(path), {
      method: 'PATCH',
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }).then((r) => handleResp<T>(r)),
  del: <T = any>(path: string) =>
    fetch(apiUrl(path), { method: 'DELETE' }).then((r) => handleResp<T>(r)),
  uploadForm: <T = any>(path: string, form: FormData) =>
    fetch(apiUrl(path), { method: 'POST', body: form }).then((r) => handleResp<T>(r)),
};

export function createJobsWebSocket(onEvent: (data: any) => void, onStatus: (connected: boolean) => void) {
  let ws: WebSocket | null = null;
  let closedByApp = false;
  let retryTimer: number | undefined;

  const connect = () => {
    if (closedByApp) return;
    ws = new WebSocket(jobsWebSocketUrl());
    ws.onopen = () => onStatus(true);
    ws.onmessage = (ev) => {
      try {
        const parsed = JSON.parse(ev.data);
        onEvent(parsed);
      } catch {
        // ignore malformed frame
      }
    };
    ws.onclose = () => {
      onStatus(false);
      if (!closedByApp) {
        retryTimer = window.setTimeout(connect, 2500);
      }
    };
    ws.onerror = () => {
      ws?.close();
    };
  };

  connect();
  return () => {
    closedByApp = true;
    if (retryTimer) window.clearTimeout(retryTimer);
    ws?.close();
  };
}

export function basenameFromPath(p: string | undefined | null): string {
  if (!p) return '';
  const parts = p.split('/');
  return parts[parts.length - 1] || '';
}
