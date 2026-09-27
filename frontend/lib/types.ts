/**
 * Types mirroring the backend response contracts.
 *
 * Deliberately hand-written rather than generated: the victim-facing types are
 * the important part, because they encode what a complainant is *allowed* to
 * see. `VictimStatus` has no score, no band, no flag names. If someone adds a
 * field here, the leak detector in the backend will not catch it, so the
 * frontend also asserts the absence of those keys at runtime.
 */

export type Role =
  | "complainant"
  | "counsellor"
  | "district_admin"
  | "state_admin"
  | "law_enforcement";

export type Band = "Low" | "Moderate" | "High" | "Critical";

/* ------------------------------------------------------------------ */
/* Victim-facing. No numeric assessment exists in any of these types.  */
/* ------------------------------------------------------------------ */

export interface Resource {
  key: string;
  label: string;
  number: string;
  note?: string;
}

/** A service commitment, not a judgement. This is the only status a person sees. */
export type VictimUrgency = "routine" | "soon" | "urgent";

export interface VictimStatus {
  reference: string;
  urgency: VictimUrgency;
  status: string;
  message_key: string;
  updated_at: string;
  next_steps_key: string;
  resources: Resource[];
  disclaimer: string;
}

export interface VictimInteractionEcho {
  id: number;
  channel: string;
  created_at: string;
  /** The person's own words. Never the analysis. */
  text?: string | null;
}

export interface VictimCase {
  id: number;
  reference: string;
  channel: string;
  language: string;
  consent_version: string;
  created_at: string;
  status: string;
  disclaimer: string;
}

export interface SelfReportItem {
  key: string;
  prompt_key: string;
  options: { value: number; label_key: string }[];
}

/* ------------------------------------------------------------------ */
/* Staff-facing. Scores live here and only here.                        */
/* ------------------------------------------------------------------ */

export interface QueueItem {
  case_ref: string;
  district: string;
  language: string;
  channel: string;
  category: Band;
  composite_score: number;
  override_reason: string | null;
  is_critical_override: boolean;
  sla_due_at: string | null;
  sla_state: string;
  assigned_counsellor: string | null;
  last_activity_at: string;
  risk_flag_count: number;
}

export interface SviBreakdown {
  composite_score: number;
  text_score: number;
  vocal_score: number | null;
  behavioral_score: number;
  category: Band;
  override_reason: string | null;
  weights: Record<string, number>;
  critical_override_applied: boolean;
  components?: Record<string, unknown>;
}

export interface Recommendation {
  summary: string;
  actions: string[];
  rationale: { id: string; note: string }[];
  mandatory_before_critical_close: string[];
}

export interface TextAnalysis {
  text_risk_score: number;
  risk_flags: string[];
  sentiment_score: number;
  method: string;
  lexicon_version: string;
  lexicon_status: string;
  critical_tier_hits: string[];
  flag_details: { flag: string; tier: string; label: string; weight: number }[];
}

export interface AudioAnalysis {
  vocal_stress_score: number;
  speech_rate: number;
  pause_ratio: number;
  pause_count: number;
  pitch_variability: number;
  method: string;
  notes: string | null;
  extractor?: string;
}

export interface BehavioralAnalysis {
  score: number;
  confidence: number;
  components: Record<string, unknown>;
  notes: string[];
}

export interface StaffInteraction {
  id: number;
  channel: string;
  created_at: string;
  text: string | null;
  response_latency_ms: number | null;
  keypad_presses: string | null;
  text_analysis: TextAnalysis | null;
  audio_analysis: AudioAnalysis | null;
  behavioral: BehavioralAnalysis | null;
}

export interface StaffCaseDetail {
  case_ref: string;
  district: string;
  language: string;
  channel: string;
  category: Band;
  composite_score: number;
  override_reason: string | null;
  is_critical_override: boolean;
  status: string;
  created_at: string;
  sla_due_at: string | null;
  sla_state: string;
  assigned_counsellor: string | null;
  interactions: StaffInteraction[];
  svi: SviBreakdown;
  behavioral: BehavioralAnalysis;
  recommendation: Recommendation;
  recorded_actions: { action: string; actor_role: string; created_at: string; note: string | null }[];
  mandatory_before_critical_close: string[];
  can_close: boolean;
  disclosure: string;
  disclaimer: string;
  method_note: string;
}

export interface ActionCatalogue {
  actions: { key: string; label: string; allowed: string[]; note: string }[];
  mandatory_before_critical_close: string[];
}

export interface Analytics {
  scope: string;
  total_cases: number;
  risk_distribution: Record<Band, number>;
  override_reasons: Record<string, number>;
  by_channel: Record<string, number>;
  by_language: Record<string, number>;
  avg_response_minutes?: Record<string, number>;
}

export interface AuditRow {
  id: number;
  actor_role: string;
  action: string;
  target_type: string;
  target_id: string | null;
  detail: string | null;
  created_at: string;
}

export interface LawCase {
  case_ref: string;
  district: string;
  category: Band;
  override_reason: string;
  immediate_action_required: boolean;
  contact_via: string;
  recorded_by_role: string;
  recorded_at: string;
  disclaimer: string;
}

export interface EngineStatus {
  sentiment: { backend: string; note: string; method_label: string; coverage_caveat: string };
  audio: { backend: string; note: string; method_label: string };
  lexicons: Record<string, { curation_status: string; requires_professional_signoff: boolean; flag_count: number }>;
}

export interface RulesResponse {
  svi_weights: { with_voice: Record<string, number>; text_only: Record<string, number> };
  bands: { low: string; moderate: string; high: string; critical: string };
  override_reasons: Record<string, string>;
  recommendation_rules: { id: string; when_category?: string; when_flags_any?: string[]; actions: string[]; note: string }[];
}

export interface ConsentStatus {
  version: string;
  channel: string;
  granted_at: string;
  withdrawn_at: string | null;
}
