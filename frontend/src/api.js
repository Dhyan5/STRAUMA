/**
 * API client for the NHAA backend.
 */
const API_BASE = 'http://localhost:8000/api';

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const config = {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  };

  const res = await fetch(url, config);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `API Error: ${res.status}`);
  }
  return res.json();
}

// ─── Intake ──────────────────────────────────────────────────────────────────
export function createCase(data) {
  return request('/intake/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ─── Assessment ──────────────────────────────────────────────────────────────
export function assessCase(caseId) {
  return request('/assess/', {
    method: 'POST',
    body: JSON.stringify({ case_id: caseId }),
  });
}

export function quickAssess(text, language = 'auto') {
  return request(`/assess/quick?text=${encodeURIComponent(text)}&language=${language}`, {
    method: 'POST',
  });
}

// ─── Cases ───────────────────────────────────────────────────────────────────
export function getCases(params = {}) {
  const query = new URLSearchParams();
  if (params.status) query.set('status', params.status);
  if (params.risk) query.set('risk', params.risk);
  if (params.sort_by) query.set('sort_by', params.sort_by);
  if (params.limit) query.set('limit', params.limit);
  const qs = query.toString();
  return request(`/cases/${qs ? '?' + qs : ''}`);
}

export function getCaseDetail(caseId) {
  return request(`/cases/${caseId}`);
}

export function getDashboardStats() {
  return request('/cases/stats');
}

export function updateCaseStatus(caseId, data) {
  return request(`/cases/${caseId}/status`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export function getCaseAudit(caseId) {
  return request(`/cases/${caseId}/audit`);
}

// ─── Recommendations ────────────────────────────────────────────────────────
export function getRecommendations(riskCategory) {
  return request(`/recommend/${riskCategory}`);
}

export function getAllRecommendations() {
  return request('/recommend/');
}

// ─── Auth ────────────────────────────────────────────────────────────────────
export function login(username, password) {
  return request(`/auth/login?username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`, {
    method: 'POST',
  });
}

export function getUsers() {
  return request('/auth/users');
}
