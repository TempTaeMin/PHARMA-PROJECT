const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE = API_BASE.replace('http', 'ws');

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API Error ${res.status}`);
  }
  return res.json();
}

// ─── Hospitals ───
export const hospitalApi = {
  list: () => request('/api/hospitals/'),
  get: (id) => request(`/api/hospitals/${id}`),
  create: (data) => request('/api/hospitals/', { method: 'POST', body: JSON.stringify(data) }),
};

// ─── Doctors ───
export const doctorApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/doctors/${qs ? '?' + qs : ''}`);
  },
  get: (id) => request(`/api/doctors/${id}`),
  create: (data) => request('/api/doctors/', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => request(`/api/doctors/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
};

// ─── Visits ───
export const visitApi = {
  list: (doctorId) => request(`/api/doctors/${doctorId}/visits`),
  create: (doctorId, data) => request(`/api/doctors/${doctorId}/visits`, { method: 'POST', body: JSON.stringify(data) }),
};

// ─── Crawling ───
export const crawlApi = {
  hospitals: () => request('/api/crawl/hospitals'),
  departments: (code) => request(`/api/crawl/departments/${code}`),
  browse: (code, search = '', dept = '') => {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    if (dept) params.set('department', dept);
    const qs = params.toString();
    return request(`/api/crawl/browse/${code}${qs ? '?' + qs : ''}`);
  },
  sync: (code, dept) => request(`/api/crawl/sync/${code}${dept ? '?department=' + encodeURIComponent(dept) : ''}`, { method: 'POST' }),
  runMyDoctors: () => request('/api/crawl/my-doctors', { method: 'POST' }),
  doctor: (code, staffId) => request(`/api/crawl/doctor/${code}/${staffId}`),
  registerDoctor: (data) => request('/api/crawl/register-doctor', { method: 'POST', body: JSON.stringify(data) }),
};

// ─── Scheduler ───
export const schedulerApi = {
  status: () => request('/api/scheduler/status'),
  run: (code) => request(`/api/scheduler/run/${code}`, { method: 'POST' }),
  runAll: () => request('/api/scheduler/run-all', { method: 'POST' }),
  task: (id) => request(`/api/scheduler/task/${id}`),
};

// ─── Notifications ───
export const notificationApi = {
  list: (limit = 20, unreadOnly = false) =>
    request(`/api/notifications/?limit=${limit}&unread_only=${unreadOnly}`),
  markRead: (id) => request(`/api/notifications/${id}/read`, { method: 'POST' }),
  markAllRead: () => request('/api/notifications/read-all', { method: 'POST' }),
  status: () => request('/api/notifications/status'),
  test: (msg) => request(`/api/notifications/test?message=${encodeURIComponent(msg)}`, { method: 'POST' }),
};

// ─── WebSocket ───
export function connectWebSocket(userId = 'default', onMessage, onClose) {
  const url = `${WS_BASE}/api/notifications/ws?user_id=${userId}`;
  const ws = new WebSocket(url);

  ws.onopen = () => console.log('[WS] Connected');
  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onMessage?.(data);
    } catch (err) {
      console.error('[WS] Parse error:', err);
    }
  };
  ws.onclose = () => { console.log('[WS] Disconnected'); onClose?.(); };
  ws.onerror = (e) => console.error('[WS] Error:', e);

  return {
    send: (msg) => ws.send(JSON.stringify(msg)),
    close: () => ws.close(),
    ping: () => ws.send(JSON.stringify({ action: 'ping' })),
    markRead: (id) => ws.send(JSON.stringify({ action: 'mark_read', notification_id: id })),
    markAllRead: () => ws.send(JSON.stringify({ action: 'mark_all_read' })),
    getHistory: (limit = 20) => ws.send(JSON.stringify({ action: 'get_history', limit })),
  };
}
