const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE = API_BASE.replace('http', 'ws');

// 401 응답 시 호출되는 콜백 (App.jsx 에서 등록)
let _onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  _onUnauthorized = fn;
}

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    credentials: 'include',  // 세션 쿠키 전송
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (res.status === 401) {
    _onUnauthorized?.();
    const err = await res.json().catch(() => ({ detail: 'Unauthorized' }));
    throw new Error(err.detail || 'Unauthorized');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API Error ${res.status}`);
  }
  return res.json();
}

// ─── Auth ───
export const authApi = {
  me: () => request('/auth/me'),
  logout: () => request('/auth/logout', { method: 'POST' }),
  loginUrl: () => `${API_BASE}/auth/google/login`,
};

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
  // 수동 진료시간 입력 — 기존 source='manual' 행을 통째로 교체
  replaceManualSchedules: (doctorId, items) =>
    request(`/api/doctors/${doctorId}/schedules`, {
      method: 'POST',
      body: JSON.stringify(items),
    }),
  addDateSchedules: (doctorId, items) =>
    request(`/api/doctors/${doctorId}/date-schedules`, {
      method: 'POST',
      body: JSON.stringify(items),
    }),
  deleteSchedule: (doctorId, scheduleId) =>
    request(`/api/doctors/${doctorId}/schedules/${scheduleId}`, { method: 'DELETE' }),
};

// ─── Visits ───
export const visitApi = {
  list: (doctorId) => request(`/api/doctors/${doctorId}/visits`),
  create: (doctorId, data) => request(`/api/doctors/${doctorId}/visits`, { method: 'POST', body: JSON.stringify(data) }),
  update: (doctorId, visitId, data) =>
    request(`/api/doctors/${doctorId}/visits/${visitId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  remove: (doctorId, visitId) =>
    request(`/api/doctors/${doctorId}/visits/${visitId}`, { method: 'DELETE' }),
  createPersonal: (data) =>
    request('/api/visits/personal', { method: 'POST', body: JSON.stringify(data) }),
  createAnnouncement: (data) =>
    request('/api/visits/announcement', { method: 'POST', body: JSON.stringify(data) }),
  removeFlat: (visitId) =>
    request(`/api/visits/${visitId}`, { method: 'DELETE' }),
  updateFlat: (visitId, data) =>
    request(`/api/visits/${visitId}`, { method: 'PATCH', body: JSON.stringify(data) }),
  aiSummarize: (visitId, payload = {}) =>
    request(`/api/visits/${visitId}/ai-summarize`, { method: 'POST', body: JSON.stringify(payload) }),
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
  searchDoctors: (q) => request(`/api/crawl/search-doctors?q=${encodeURIComponent(q)}`),
  sync: (code, dept) => request(`/api/crawl/sync/${code}${dept ? '?department=' + encodeURIComponent(dept) : ''}`, { method: 'POST' }),
  runMyDoctors: () => request('/api/crawl/my-doctors', { method: 'POST' }),
  doctor: (code, staffId) => request(`/api/crawl/doctor/${code}/${encodeURIComponent(staffId)}`),
  registerDoctor: (data) => request('/api/crawl/register-doctor', { method: 'POST', body: JSON.stringify(data) }),
};

// ─── Dashboard ───
export const dashboardApi = {
  summary: () => request('/api/dashboard/'),
  myVisits: (year, month) => request(`/api/dashboard/my-visits?year=${year}&month=${month}`),
};

// ─── Scheduler ───
export const schedulerApi = {
  status: () => request('/api/scheduler/status'),
  run: (code) => request(`/api/scheduler/run/${code}`, { method: 'POST' }),
  runAll: () => request('/api/scheduler/run-all', { method: 'POST' }),
  task: (id) => request(`/api/scheduler/task/${id}`),
};

// ─── Academic (학회 일정) ───
export const academicApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/academic-events/${qs ? '?' + qs : ''}`);
  },
  upcoming: (department, months = 3, source) => {
    const params = new URLSearchParams({ months: String(months) });
    if (department) params.set('department', department);
    if (source) params.set('source', source);
    return request(`/api/academic-events/upcoming?${params.toString()}`);
  },
  unclassified: () => request('/api/academic-events/unclassified'),
  mySchedule: ({ start_date, end_date }) =>
    request(`/api/academic-events/my-schedule?start=${start_date}&end=${end_date}`),
  myLecturers: (months = 1) =>
    request(`/api/academic-events/my-lecturers?months=${months}`),
  eventsForDoctor: (doctorId, start, end) =>
    request(`/api/academic-events/for-doctor/${doctorId}?start=${start}&end=${end}`),
  getById: (id) => request(`/api/academic-events/${id}`),
  create: (data) => request('/api/academic-events', { method: 'POST', body: JSON.stringify(data) }),
  delete: (id) => request(`/api/academic-events/${id}`, { method: 'DELETE' }),
  pin: (id) => request(`/api/academic-events/${id}/pin`, { method: 'POST' }),
  unpin: (id) => request(`/api/academic-events/${id}/pin`, { method: 'DELETE' }),
  sync: () => request('/api/academic-events/sync', { method: 'POST' }),
  updateEventDepartments: (id, departments) =>
    request(`/api/academic-events/${id}/departments`, {
      method: 'PATCH',
      body: JSON.stringify({ departments }),
    }),
  organizers: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/academic-organizers/${qs ? '?' + qs : ''}`);
  },
  seedOrganizers: () => request('/api/academic-organizers/seed', { method: 'POST' }),
  updateOrganizerDepartments: (id, departments) =>
    request(`/api/academic-organizers/${id}/departments`, {
      method: 'PATCH',
      body: JSON.stringify({ departments }),
    }),
};

// ─── Memos (방문 메모 / 회의록) ───
export const memoApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.set(k, v);
    });
    const s = qs.toString();
    return request(`/api/memos${s ? '?' + s : ''}`);
  },
  get: (id) => request(`/api/memos/${id}`),
  create: (data) => request('/api/memos', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => request(`/api/memos/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  remove: (id) => request(`/api/memos/${id}`, { method: 'DELETE' }),
  summarize: (id, templateId) =>
    request(`/api/memos/${id}/summarize`, {
      method: 'POST',
      body: JSON.stringify({ template_id: templateId ?? null }),
    }),
  listByDoctor: (doctorId, limit = 20) =>
    request(`/api/doctors/${doctorId}/memos?limit=${limit}`),
};

export const memoTemplateApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString();
    return request(`/api/memo-templates${qs ? '?' + qs : ''}`);
  },
  create: (data) => request('/api/memo-templates', { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data) => request(`/api/memo-templates/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  remove: (id) => request(`/api/memo-templates/${id}`, { method: 'DELETE' }),
};

// ─── Reports (일일/주간 보고서) ───
export const reportApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ).toString();
    return request(`/api/reports${qs ? '?' + qs : ''}`);
  },
  get: (id) => request(`/api/reports/${id}`),
  create: (data) => request('/api/reports', { method: 'POST', body: JSON.stringify(data) }),
  regenerate: (id) => request(`/api/reports/${id}/regenerate`, { method: 'POST' }),
  remove: (id) => request(`/api/reports/${id}`, { method: 'DELETE' }),
  // docx 다운로드 URL — fetch + blob 으로 처리 가능
  docxUrl: (id) => `${API_BASE}/api/reports/${id}/docx`,
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
