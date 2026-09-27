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
  ActionResponse,
  Analytics,
  AuditRow,
  ConsentStatus,
  CrisisResource,
  CurrentUser,
  EngineStatus,
  LanguageCatalogue,
  LawCase,
  LawPolicy,
  NotificationOutbox,
  PortalConfig,
  QueueItem,
  RulesResponse,
  SelfReportItem,
  Session,
  StaffCaseDetail,
  StringBundle,
  TurnResult,
  VictimTranscript,
  VictimView,
  CaseOut,
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
  config: () => request<PortalConfig>("/api/portal/config"),
  health: () => request<{ status: string; disclaimer: string }>("/api/health"),
  /** Keyed by resource id, not a list. */
  crisisResources: () =>
    request<{ resources: Record<string, Omit<CrisisResource, "id">>; disclaimer: string; verification_note: string }>(
      "/api/crisis-resources",
    ),
  languages: () => request<LanguageCatalogue>("/api/i18n/languages"),
  strings: (language: string) =>
    request<StringBundle>(`/api/i18n/strings?language=${encodeURIComponent(language)}`),
  engines: () => request<EngineStatus>("/api/engines/status"),
  selfReportSchema: () => request<SelfReportItem[]>("/api/self-report/schema"),
};

export const authApi = {
  register: (body: { role: string; language_pref?: string; display_name?: string; district?: string; password?: string }) =>
    request<Session>("/api/auth/register", { method: "POST", body }),
  /** JSON body with `pseudonym_id`. Not OAuth2 form encoding. */
  login: (body: { pseudonym_id: string; password: string }) =>
    request<Session>("/api/auth/token", { method: "POST", body }),
  me: () => request<CurrentUser>("/api/auth/me", { auth: true }),
};

export const consentApi = {
  status: () => request<ConsentStatus>("/api/consent/status", { auth: true }),
  grant: (body: { version: string; channel: string }) =>
    request<ConsentStatus>("/api/consent", { method: "POST", body, auth: true }),
  withdraw: () => request<ConsentStatus>("/api/consent/status", { method: "DELETE", auth: true }),
};

export const victimApi = {
  createCase: (body: { channel: string; language: string }) =>
    request<CaseOut>("/api/cases", { method: "POST", body, auth: true }),
  submitTurn: (body: {
    case_id: number;
    channel: string;
    text?: string;
    transcribed_text?: string;
    keypad_presses?: string;
    response_latency_ms?: number;
    self_report?: Record<string, number>;
  }) => request<TurnResult>("/api/interactions", { method: "POST", body, auth: true }),
  /**
   * Synthetic practice clip. Sent as form data because the endpoint declares
   * `Form(...)` parameters; a query string returns 422.
   */
  demoVoice: (caseId: number, stressed: boolean, transcript: string, responseLatencyMs = 30000) => {
    const form = new FormData();
    form.set("case_id", String(caseId));
    form.set("channel", "voice");
    form.set("stressed", String(stressed));
    form.set("transcript", transcript);
    form.set("response_latency_ms", String(responseLatencyMs));
    return request<TurnResult>("/api/interactions/demo-voice", { method: "POST", auth: true, raw: form });
  },
  status: (caseId: number) => request<VictimView>(`/api/cases/${caseId}/status`, { auth: true }),
  history: (caseId: number) => request<VictimTranscript>(`/api/cases/${caseId}/interactions`, { auth: true }),
  confirmations: (caseId: number) => request<ActionResponse>(`/api/cases/${caseId}/confirmations`, { auth: true }),
  /** Withdraws the case: the person asked to stop. */
  stop: (caseId: number) => request<ActionResponse>(`/api/cases/${caseId}/stop`, { method: "POST", auth: true }),
};

/* ---------------------------------------------------------------- */
/* Staff / admin / law enforcement                                    */
/* ---------------------------------------------------------------- */

export const staffApi = {
  queue: () => request<QueueItem[]>("/api/counsellor/queue", { auth: true }),
  /** Takes the numeric `case_id`, not the human-quotable `case_ref`. */
  caseDetail: (caseId: number) => request<StaffCaseDetail>(`/api/counsellor/queue/${caseId}`, { auth: true }),
  act: (caseId: number, body: { action: string; note?: string }) =>
    request<ActionResponse>(`/api/counsellor/cases/${caseId}/actions`, { method: "POST", body, auth: true }),
  assign: (caseId: number, body: { counsellor_id?: number; note?: string }) =>
    request<ActionResponse>(`/api/counsellor/cases/${caseId}/assign`, { method: "POST", body, auth: true }),
  /** Closure. The endpoint is `resolve`; it returns 409 while actions are missing. */
  close: (caseId: number, note?: string) =>
    request<ActionResponse>(`/api/counsellor/cases/${caseId}/resolve`, { method: "POST", body: { note }, auth: true }),
  catalogue: () => request<ActionCatalogue>("/api/counsellor/actions/catalogue", { auth: true }),
  analytics: () => request<Analytics>("/api/admin/analytics", { auth: true }),
  audit: () => request<AuditRow[]>("/api/admin/audit", { auth: true }),
  rules: () => request<RulesResponse>("/api/admin/rules", { auth: true }),
  notifications: () => request<NotificationOutbox>("/api/admin/notifications", { auth: true }),
};

export const lawApi = {
  cases: () => request<LawCase[]>("/api/law-enforcement/cases", { auth: true }),
  caseDetail: (caseRef: string) =>
    request<LawCase>(`/api/law-enforcement/cases/${encodeURIComponent(caseRef)}`, { auth: true }),
  policy: () => request<LawPolicy>("/api/law-enforcement/policy", { auth: true }),
};
