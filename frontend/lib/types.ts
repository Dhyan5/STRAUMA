/**
 * Types mirroring the backend response contracts.
 *
 * These were rewritten field-by-field against a live server dump rather than
 * written from the schema, because the first version of this file was
 * hand-derived and almost every name in it was wrong: `reference` where the
 * server sends `ref`, `helplines` where it sends `crisis_resources`, a flat
 * case detail where the server nests the case. TypeScript compiled happily
 * against those guesses and the pages would have rendered `undefined` at run
 * time, which is the failure mode a build check cannot catch.
 *
 * The victim-facing half is the part that matters most, because it encodes what
 * a complainant is *allowed* to see. `VictimView` has no score, no band, no
 * flag name. If you add a field here, the backend leak detector will not catch
 * it, so `/api/strings/leakage-check` and the guardrail tests remain the
 * backstop.
 */

export type Role =
  | "complainant"
  | "counsellor"
  | "district_admin"
  | "state_admin"
  | "law_enforcement";

export type Band = "Low" | "Moderate" | "High" | "Critical";

/** A crisis line. `numbers` is a list because Tele MANAS has two. */
export interface CrisisResource {
  id: string;
  name: string;
  numbers: string[];
  description: string;
}

/* ------------------------------------------------------------------ */
/* Public configuration                                                */
/* ------------------------------------------------------------------ */

export interface PortalChannel {
  id: "chat" | "voice" | "ivrs";
  label_key: string;
}

export interface SelfReportOption {
  value: number;
  i18n_key: string;
}

export interface SelfReportItem {
  key: string;
  /** Present on `portal/config.self_report_items`; absent on the standalone
   *  `/api/self-report/schema` list, which is why the portal reads the former. */
  i18n_key?: string;
  options: SelfReportOption[];
}

export interface PortalLanguage {
  code: string;
  label: string;
  native_name: string;
  /** Serialised as a string, not a boolean. Truthy check with `=== "true"`. */
  curated_ui: string;
}

export interface PortalConfig {
  disclaimer: string;
  languages: PortalLanguage[];
  consent_version: string;
  quick_exit_url: string;
  crisis_resources: CrisisResource[];
  self_report_items: SelfReportItem[];
  channels: PortalChannel[];
  strings: Record<string, Record<string, string>>;
}

export interface LanguageCatalogue {
  consent_version: string;
  lexicon_version: string;
  languages: {
    code: string;
    display_name: string;
    native_name: string;
    curation_status: string;
  }[];
  ui_strings_curated_for: string[];
  translation: { translation_provider: string; languages: string[] }[];
  note: string;
}

export interface StringBundle {
  language: string;
  requested_language: string;
  curated: boolean;
  fallback: boolean;
  /** Human-readable reason, shown to the person. Never silent. */
  fallback_reason: string | null;
  strings: Record<string, string>;
}

export interface EngineStatus {
  sentiment: {
    backend: string;
    note: string;
    model_id: string;
    method_label: string;
    coverage_caveat: string;
  };
  /** Note: no `backend` key here. The audio engine reports `method_label`. */
  audio: { method_label: string; note: string };
  scoring: { bands: { category: Band; min: number; max: number; sla_hours: number; colour_token: string }[] };
  lexicons: Record<string, { curation_status: string; flags: number; patterns: number; requires_professional_signoff: boolean }>;
  lexicon_version: string;
  queue: { backend: string; redis_url_configured: boolean; is_fallback: boolean; note: string };
  notifications: { provider: string; transmits_anything: boolean; channels: Record<string, string>; note: string };
  translation_provider: string;
  guardrails: {
    complainants_never_see_scores: boolean;
    critical_cases_never_auto_close: boolean;
    law_enforcement_visibility_is_opt_in: boolean;
    all_endpoints_enforce_rbac_server_side: boolean;
  };
}

/* ------------------------------------------------------------------ */
/* Identity and consent                                                */
/* ------------------------------------------------------------------ */

export interface Session {
  access_token: string;
  token_type: string;
  role: Role;
  pseudonym_id: string;
  disclaimer: string;
}

export interface CurrentUser {
  id: number;
  role: Role;
  pseudonym_id: string;
  language_pref: string;
  district: string | null;
  display_name: string | null;
  created_at: string;
}

export interface ConsentStatus {
  version: string;
  channel: string;
  granted_at: string;
  withdrawn_at: string | null;
}

/* ------------------------------------------------------------------ */
/* Victim-facing. No numeric assessment exists in any of these types.  */
/* ------------------------------------------------------------------ */

/**
 * A service commitment, never a judgement and never a band.
 * The server maps the internal band onto exactly one of these four words, so
 * the complainant learns how fast a person will come, not what they scored.
 */
export type VictimUrgency = "routine" | "soon" | "priority" | "immediate";

export interface VictimView {
  reference: string;
  /** Lifecycle label. Never the risk band. */
  stage: string;
  next_step_key: string;
  urgency: VictimUrgency;
  resources: CrisisResource[];
  disclaimer: string;
  /** String-table keys for the client to resolve. The server sends no prose. */
  i18n_keys: string[];
}

export interface CaseOut {
  id: number;
  /** The human-quotable reference. Named `ref` on the wire. */
  ref: string;
  district: string | null;
  channel: string;
  language: string;
  status: string;
  consent_version: string;
  sla_due_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TurnResult {
  interaction_id: number;
  reference: string;
  view: VictimView;
}

/** The person's own words. Never the analysis. */
export interface VictimInteractionEcho {
  id: number;
  channel: string;
  created_at: string;
  raw_text?: string | null;
  transcribed_text?: string | null;
}

export interface VictimTranscript {
  interactions: VictimInteractionEcho[];
  disclaimer: string;
}

/** The closure/confirmation view. `still_open_actions` is what blocks closure. */
export interface ActionResponse {
  case_ref: string;
  recorded: string[];
  status: string;
  still_open_actions: string[];
  message: string;
}

/* ------------------------------------------------------------------ */
/* Staff-facing. Scores live here and only here.                        */
/* ------------------------------------------------------------------ */

export interface QueueItem {
  case_id: number;
  case_ref: string;
  district: string | null;
  channel: string;
  language: string;
  status: string;
  category: Band;
  composite_score: number;
  is_critical_override: boolean;
  override_reason: string | null;
  risk_flags: string[];
  recommended_actions: string[];
  sla_state: string;
  sla_due_at: string | null;
  queue_priority: number;
  created_at: string;
  assigned_counsellor_id: number | null;
  assigned_counsellor_name: string | null;
}

export interface SviRecord {
  id: number;
  case_id: number;
  text_score: number;
  /** 0 when the turn had no audio, so a chat case never looks assessed. */
  vocal_score: number;
  behavioral_score: number;
  composite_score: number;
  category: Band;
  override_reason: string | null;
  weights: Record<string, number>;
  computed_at: string;
}

export interface BehavioralAnalysis {
  score: number;
  confidence: number;
  components: Record<string, number>;
  method: string;
  notes: string[];
}

export interface Recommendation {
  id: number;
  case_id: number;
  actions: string[];
  summary: string;
  ruleset_version: string;
  generated_at: string;
}

export interface TextAnalysis {
  sentiment: string;
  sentiment_score: number;
  risk_flags: string[];
  text_risk_score: number;
  method: string;
  confidence: number;
  lexicon_version: string;
  created_at: string;
}

export interface AudioAnalysis {
  pitch_mean: number;
  pitch_var: number;
  jitter_proxy: number;
  pause_count: number;
  pause_ratio: number;
  speaking_rate: number;
  energy_rms: number;
  duration_sec: number;
  vocal_stress_score: number;
  method: string;
  confidence: number;
  /** Provenance is carried here, which is how synthetic audio stays labelled. */
  notes: string;
  created_at: string;
}

export interface StaffInteraction {
  id: number;
  case_id: number;
  channel: string;
  raw_text: string | null;
  transcribed_text: string | null;
  keypad_presses: string | null;
  response_latency_ms: number | null;
  self_report: Record<string, number> | null;
  created_at: string;
  text_analysis: TextAnalysis | null;
  audio_analysis: AudioAnalysis | null;
}

export interface CaseActionRecord {
  id: number;
  action: string;
  note: string | null;
  created_at: string;
  actor_role: string;
  actor_id: number;
}

export interface StaffCaseDetail {
  /** Nested, unlike the flat shape this file used to claim. */
  case: CaseOut;
  category: Band;
  composite_score: number;
  is_critical_override: boolean;
  override_reason: string | null;
  svi: SviRecord;
  svi_history: SviRecord[];
  behavioral: BehavioralAnalysis;
  recommendation: Recommendation;
  actions: CaseActionRecord[];
  interactions: StaffInteraction[];
  assignment: { id: number; counsellor_id: number | null; assigned_at: string; sla_due_at: string | null; status: string };
  sla_state: string;
  sla_label: string;
  queue_priority: number;
  exposes_to_law_enforcement: boolean;
  method_note: string;
  disclaimer: string;
}

export interface ActionCatalogue {
  actions: { action: string; label: string; allowed: boolean; allowed_roles: string[] }[];
  mandatory_before_critical_close: string[];
  disclaimer: string;
}

/* ------------------------------------------------------------------ */
/* Admin                                                               */
/* ------------------------------------------------------------------ */

export interface Analytics {
  generated_at: string;
  scope: string;
  total_cases: number;
  open_cases: number;
  risk_distribution: Record<Band, number>;
  cases_by_district: Record<string, number>;
  cases_by_channel: Record<string, number>;
  cases_by_language: Record<string, number>;
  critical_override_count: number;
  override_reasons: Record<string, number>;
  flag_frequency: Record<string, number>;
  sla_compliance_pct: number;
  sla_state_counts: Record<string, number>;
  median_composite_by_band: Record<string, number>;
  actions_taken: Record<string, number>;
  engine_notes: Record<string, string>;
  disclaimer: string;
}

export interface AuditRow {
  id: number;
  actor_id: number;
  actor_role: string;
  action: string;
  target_type: string;
  target_id: string | null;
  /** A list, not a string. `[]` for actions with no extra detail. */
  detail: unknown[];
  created_at: string;
}

export interface RulesResponse {
  ruleset_version: string;
  svi_bands: { category: Band; min: number; max: number; sla_hours: number; colour_token: string }[];
  svi_weights: { with_voice: Record<string, number>; text_only: Record<string, number> };
  override_reasons: Record<string, string>;
  recommendation_rules: { id: string; when_category?: string; when_flags_any?: string[]; actions: string[]; note: string }[];
  lexicon_version: string;
  lexicons: Record<string, { curation_status: string; flags: number; patterns: number; requires_professional_signoff: boolean }>;
  disclaimer: string;
}

export interface NotificationOutbox {
  provider: { provider: string; transmits_anything: boolean; channels: Record<string, string>; note: string };
  entries: {
    id: number;
    case_id: number;
    channel: string;
    channel_note: string;
    recipient: string;
    status: string;
    provider: string;
    attempts: number;
    created_at: string;
    sent_at: string | null;
    payload: string;
    disclaimer: string;
  }[];
}

/* ------------------------------------------------------------------ */
/* Law enforcement. Minimal by construction.                           */
/* ------------------------------------------------------------------ */

export interface LawCase {
  case_ref: string;
  district: string | null;
  category: Band;
  /** The referring human's handover note, deliberately not the model lexicon
   *  text: the police view is a human-to-human handover, not a model output. */
  override_reason: string;
  immediate_action_required: string;
  contact_via: string;
  recorded_by_role: string | null;
  recorded_at: string;
  disclaimer: string;
}

export interface LawPolicy {
  visibility_rule: string;
  excluded_fields: string[];
  audit_note: string;
  generated_at: string;
  disclaimer: string;
}
