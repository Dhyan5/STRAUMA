/**
 * Thin fetch wrapper around the FastAPI backend.
 *
 * Two rules live here rather than in each component:
 *
 * 1. Tokens are kept in `sessionStorage`, never `localStorage`. A token that
 *    survives the tab closing is a token left behind on a shared machine, and
 *    this portal may well be used on one.
 * 2. `ApiError` carries the backend's `detail` through unchanged, because the
 *    close-gate refusal names the missing action and the UI should show that
 *    sentence rather than invent one.
 */

import type {
  ActionCatalogue,
  Analytics,
  AuditRow,
  Band,
  ConsentStatus,
  EngineStatus,
  LawCase,
  QueueItem,
  Resource,
  RulesResponse,
  SelfReportItem,
  StaffCaseDetail,
  VictimCase,
  VictimStatus,
} from "./types";

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"
).replace(/\/$/, "");

const TOKEN_KEY = "nhaa14566.token";
const ROLE_KEY = "nhaa14566.role";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown, message?: string) {
    super(message ?? `API ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/* ---------------------------------------------------------------- */
/* Token storage                                                      */
/* ---------------------------------------------------------------- */

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(TOKEN_KEY);
}

export function getRole(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(ROLE_KEY);
}

export function setSession(token: string, role: string): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(TOKEN_KEY, token);
  window.sessionStorage.setItem(ROLE_KEY, role);
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(TOKEN_KEY);
  window.sessionStorage.removeItem(ROLE_KEY);
}

/* ---------------------------------------------------------------- */
/* Core request helper                                                */
/* ---------------------------------------------------------------- */

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; auth?: boolean; raw?: FormData } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined && !options.raw) headers["Content-Type"] = "application/json";

  if (options.auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.raw ? options.raw : options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError(0, null, "We could not reach the service. Check that the backend is running.");
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in (payload as Record<string, unknown>)
        ? (payload as Record<string, unknown>).detail
        : payload;
    throw new ApiError(response.status, detail, typeof detail === "string" ? detail : `Request failed (${response.status})`);
  }

  return payload as T;
}

/* ---------------------------------------------------------------- */
/* Public / victim                                                    */
/* ---------------------------------------------------------------- */

export const publicApi = {
  config: () => request<{ disclaimer: string; helplines: Resource[]; sla_hours: Record<Band, number> }>("/api/portal/config"),
  health: () => request<{ status: string; disclaimer: string }>("/api/health"),
  crisisResources: () => request<{ resources: Resource[]; disclaimer: string }>("/api/crisis-resources"),
  languages: () => request<{ languages: { code: string; display_name: string; native_name: string }[]; consent_version: string }>("/api/i18n/languages"),
  strings: (language: string) =>
    request<{ language: string; requested_language: string; curated: boolean; fallback: boolean; strings: Record<string, string> }>(
      `/api/i18n/strings?language=${encodeURIComponent(language)}`,
    ),
  engines: () => request<EngineStatus>("/api/engines/status"),
  selfReportSchema: () => request<SelfReportItem[]>("/api/self-report/schema"),
};

export const authApi = {
  register: (body: { role: string; language_pref?: string; display_name?: string; district?: string; password?: string }) =>
    request<{ access_token: string; pseudonym_id: string; role: string; disclaimer: string }>("/api/auth/register", {
      method: "POST",
      body,
    }),
  login: (body: { pseudonym_id: string; password: string }) =>
    request<{ access_token: string; pseudonym_id: string; role: string }>("/api/auth/login", { method: "POST", body }),
  me: () => request<{ pseudonym_id: string; role: string; district: string | null; disclaimer: string }>("/api/auth/me", { auth: true }),
};

export const consentApi = {
  status: () => request<ConsentStatus>("/api/consent/status", { auth: true }),
  grant: (body: { version: string; channel: string }) =>
    request<ConsentStatus>("/api/consent", { method: "POST", body, auth: true }),
  withdraw: () => request<ConsentStatus>("/api/consent/status", { method: "DELETE", auth: true }),
};

export const victimApi = {
  createCase: (body: { channel: string; language: string }) =>
    request<VictimCase>("/api/cases", { method: "POST", body, auth: true }),
  submitTurn: (body: { case_id: number; channel: string; text?: string; transcribed_text?: string; keypad_presses?: string; response_latency_ms?: number; self_report?: Record<string, number> }) =>
    request<{ reference: string; view: VictimStatus }>("/api/interactions", { method: "POST", body, auth: true }),
  demoVoice: (caseId: number, stressed: boolean, transcript: string) =>
    request<{ reference: string; view: VictimStatus }>(
      `/api/interactions/demo-voice?case_id=${caseId}&stressed=${stressed}&transcript=${encodeURIComponent(transcript)}`,
      { method: "POST", auth: true },
    ),
  status: (caseId: number) => request<VictimStatus>(`/api/cases/${caseId}/status`, { auth: true }),
  history: (caseId: number) =>
    request<{ interactions: { id: number; channel: string; created_at: string; text: string | null }[]; disclaimer: string }>(
      `/api/cases/${caseId}/interactions`,
      { auth: true },
    ),
  cases: () => request<{ cases: VictimCase[]; disclaimer: string }>("/api/cases", { auth: true }),
};

/* ---------------------------------------------------------------- */
/* Staff / admin / law enforcement                                    */
/* ---------------------------------------------------------------- */

export const staffApi = {
  queue: () => request<QueueItem[]>("/api/counsellor/queue", { auth: true }),
  caseDetail: (ref: string) => request<StaffCaseDetail>(`/api/counsellor/queue/${ref}`, { auth: true }),
  act: (ref: string, body: { action: string; note?: string }) =>
    request<{ recorded: string[]; can_close: boolean; mandatory_before_critical_close: string[]; detail?: string }>(
      `/api/counsellor/cases/${ref}/actions`,
      { method: "POST", body, auth: true },
    ),
  close: (ref: string) =>
    request<{ status: string; detail: string }>(`/api/counsellor/cases/${ref}/close`, { method: "POST", auth: true }),
  catalogue: () => request<ActionCatalogue>("/api/counsellor/actions/catalogue", { auth: true }),
  analytics: () => request<Analytics>("/api/admin/analytics", { auth: true }),
  audit: () => request<AuditRow[]>("/api/admin/audit", { auth: true }),
  rules: () => request<RulesResponse>("/api/admin/rules", { auth: true }),
  notifications: () => request<{ notifications: { id: number; kind: string; payload: string; created_at: string }[]; disclaimer: string }>(
    "/api/admin/notifications",
    { auth: true },
  ),
};

export const lawApi = {
  cases: () => request<LawCase[]>("/api/law-enforcement/cases", { auth: true }),
  policy: () =>
    request<{ policy: Record<string, unknown>; disclaimer: string }>("/api/law-enforcement/policy", { auth: true }),
};
