"""Pydantic request/response models.

Two response shapes matter for the safety design:

* `StaffCaseDetail` includes the SVI breakdown. Only staff roles ever receive it.
* `VictimCaseView` is the complainant's view. It carries no score, no band and
  no flag vocabulary at all - see `engine/victim_copy.py`.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --------------------------------------------------------------------------
# JSON-in-a-text-column bridge
# --------------------------------------------------------------------------
#
# Several columns hold JSON as Text (`risk_flags`, `weights`, `actions`,
# `self_report`). Handing the raw string to a `List`/`Dict` field fails
# validation, and pre-parsing everywhere in the routers would scatter the same
# defensive code across the codebase. These helpers make "text column, typed
# field" work automatically: a real dict/list passes straight through, a JSON
# string is decoded, and anything unparseable degrades to the documented default
# rather than 500-ing a counsellor dashboard.


def _coerce_json(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    if isinstance(raw, str):
        import json

        try:
            return json.loads(raw)
        except ValueError:
            return default
    return default


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    role: str = "complainant"
    language_pref: str = "en"
    district: Optional[str] = None
    display_name: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=200)

    @field_validator("role")
    @classmethod
    def _known_role(cls, value: str) -> str:
        from config import ROLES

        if value not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        return value

    @field_validator("language_pref")
    @classmethod
    def _known_lang(cls, value: str) -> str:
        value = (value or "en").lower()
        from nlp.lexicons import supported_languages

        if value not in {entry["code"] for entry in supported_languages()}:
            raise ValueError("unsupported language")
        return value


class LoginRequest(BaseModel):
    pseudonym_id: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    pseudonym_id: str
    language_pref: str
    district: Optional[str] = None
    display_name: Optional[str] = None
    created_at: dt.datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    pseudonym_id: str
    disclaimer: str


class RegisterOut(TokenOut):
    """Registration returns a usable session, not just a user row.

    A complainant has no password by design, so `/api/auth/login` can never
    authenticate them. If registration did not hand back a token, the victim
    portal would have no way to obtain credentials at all and the whole flow
    would be unreachable.
    """

    user: UserOut


# --------------------------------------------------------------------------
# Consent
# --------------------------------------------------------------------------


class ConsentRequest(BaseModel):
    version: str
    channel: str = Field(default="chat", pattern="^(chat|voice|ivrs)$")


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    version: str
    channel: str
    granted_at: dt.datetime
    withdrawn_at: Optional[dt.datetime] = None

    @property
    def is_active(self) -> bool:
        return self.withdrawn_at is None


# --------------------------------------------------------------------------
# Intake
# --------------------------------------------------------------------------


class CaseCreateRequest(BaseModel):
    district: Optional[str] = None
    channel: str = Field(default="chat", pattern="^(chat|voice|ivrs)$")
    language: str = "en"


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ref: str
    district: Optional[str] = None
    channel: str
    language: str
    status: str
    consent_version: str
    sla_due_at: Optional[dt.datetime] = None
    created_at: dt.datetime
    updated_at: dt.datetime


class InteractionCreateRequest(BaseModel):
    case_id: int
    channel: str = Field(pattern="^(chat|voice|ivrs)$")
    text: Optional[str] = Field(default=None, max_length=8000)
    transcribed_text: Optional[str] = Field(default=None, max_length=8000)
    keypad_presses: Optional[str] = Field(default=None, max_length=64)
    response_latency_ms: Optional[int] = Field(default=None, ge=0, le=3_600_000)
    self_report: Optional[Dict[str, Any]] = None
    language: Optional[str] = None


class SelfReportItem(BaseModel):
    key: str
    options: List[Dict[str, Any]] = Field(default_factory=list)


class TextAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sentiment: str
    sentiment_score: Optional[float] = None
    risk_flags: List[str]
    text_risk_score: float
    method: str
    confidence: float
    lexicon_version: str
    created_at: dt.datetime

    @field_validator("risk_flags", mode="before")
    @classmethod
    def _parse_risk_flags(cls, value: Any) -> Any:
        # Staff-only field. Decoded from the JSON text column, never shown to a
        # complainant: `routers/complainant.py` uses `InteractionEchoOut`, which
        # has no analysis objects on it at all.
        return _coerce_json(value, [])


class AudioAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pitch_mean: Optional[float] = None
    pitch_var: Optional[float] = None
    jitter_proxy: Optional[float] = None
    pause_count: Optional[int] = None
    pause_ratio: Optional[float] = None
    speaking_rate: Optional[float] = None
    energy_rms: Optional[float] = None
    duration_sec: Optional[float] = None
    vocal_stress_score: Optional[float] = None
    method: str
    confidence: float
    notes: Optional[str] = None
    created_at: dt.datetime


class InteractionOut(BaseModel):
    """Full interaction record including analysis. **Staff endpoints only.**

    Never return this to a complainant: it carries `text_analysis` and
    `audio_analysis`, and therefore numeric scores. The complainant-facing
    counterpart is `InteractionEchoOut`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    channel: str
    raw_text: Optional[str] = None
    transcribed_text: Optional[str] = None
    keypad_presses: Optional[str] = None
    response_latency_ms: Optional[int] = None
    self_report: Optional[Dict[str, Any]] = None
    created_at: dt.datetime
    text_analysis: Optional[TextAnalysisOut] = None
    audio_analysis: Optional[AudioAnalysisOut] = None

    @field_validator("self_report", mode="before")
    @classmethod
    def _parse_self_report(cls, value: Any) -> Any:
        return _coerce_json(value, None)


class InteractionEchoOut(BaseModel):
    """What a complainant may see about their own turns.

    Deliberately narrower than `InteractionOut`: the person sees their own words
    back, and nothing the engine derived from them. No `text_analysis`, no
    `audio_analysis`, no latency. Adding a scored field here would be a safety
    regression, so the test suite asserts this shape has no such fields.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    channel: str
    created_at: dt.datetime
    raw_text: Optional[str] = None
    transcribed_text: Optional[str] = None


# --------------------------------------------------------------------------
# Assessment (staff only)
# --------------------------------------------------------------------------


class SVIOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    text_score: float
    vocal_score: float
    behavioral_score: float
    composite_score: float
    category: str
    override_reason: Optional[str] = None
    weights: Dict[str, float]
    computed_at: dt.datetime

    @field_validator("weights", mode="before")
    @classmethod
    def _parse_weights(cls, value: Any) -> Any:
        return _coerce_json(value, {})

    @property
    def is_critical_override(self) -> bool:
        return self.category == "Critical" and bool(self.override_reason)


class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: int
    actions: List[str]
    summary: str
    ruleset_version: str
    generated_at: dt.datetime

    @field_validator("actions", mode="before")
    @classmethod
    def _parse_actions(cls, value: Any) -> Any:
        return _coerce_json(value, [])


class CaseActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    note: Optional[str] = None
    created_at: dt.datetime
    actor_role: Optional[str] = None
    actor_id: Optional[int] = None


class StaffCaseDetail(BaseModel):
    """Full counsellor view. SVI visible. Never sent to a complainant."""

    case: CaseOut
    category: str
    composite_score: float
    is_critical_override: bool
    override_reason: Optional[str] = None
    svi: Optional[SVIOut] = None
    svi_history: List[SVIOut] = Field(default_factory=list)
    behavioral: Dict[str, Any] = Field(default_factory=dict)
    recommendation: Optional[RecommendationOut] = None
    actions: List[CaseActionOut] = Field(default_factory=list)
    interactions: List[InteractionOut] = Field(default_factory=list)
    assignment: Optional[Dict[str, Any]] = None
    sla_state: str = "unassigned"
    sla_label: str = ""
    queue_priority: Optional[int] = None
    exposes_to_law_enforcement: bool = False
    method_note: str = "Decision support only. Not a diagnosis."
    disclaimer: str


class QueueItem(BaseModel):
    case_id: int
    case_ref: str
    district: Optional[str] = None
    channel: str
    language: str
    status: str
    category: str
    composite_score: float
    is_critical_override: bool
    override_reason: Optional[str] = None
    risk_flags: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)
    sla_state: str = "unassigned"
    sla_due_at: Optional[dt.datetime] = None
    queue_priority: int = 4000
    created_at: dt.datetime
    assigned_counsellor_id: Optional[int] = None
    assigned_counsellor_name: Optional[str] = None


class LawEnforcementItem(BaseModel):
    """Minimal-PII projection for the restricted police view."""

    case_ref: str
    district: Optional[str] = None
    category: str
    override_reason: Optional[str] = None
    immediate_action_required: str
    contact_via: str
    recorded_by_role: Optional[str] = None
    recorded_at: Optional[dt.datetime] = None
    disclaimer: str


# --------------------------------------------------------------------------
# Victim view
# --------------------------------------------------------------------------


class VictimCaseView(BaseModel):
    """Deliberately minimal. No scores, no categories, no flags."""

    reference: str
    stage: str
    next_step_key: str
    urgency: str
    #: `List[Dict[str, Any]]` rather than `List[Dict[str, str]]` because each
    #: resource carries a list of numbers, not a single string.
    resources: List[Dict[str, Any]]
    disclaimer: str
    i18n_keys: List[str]


class ActionRequest(BaseModel):
    action: str
    note: Optional[str] = Field(default=None, max_length=2000)


class ActionResponse(BaseModel):
    #: A set, not a single verb: `/confirmations` reports everything recorded on
    #: a case, while a single action records one entry. Callers that record one
    #: action pass a one-element list rather than a bare string, so the shape
    #: does not change with the endpoint.
    case_ref: str
    recorded: List[str]
    status: str
    still_open_actions: List[str] = Field(default_factory=list)
    message: str


class AnalyticsOut(BaseModel):
    generated_at: dt.datetime
    scope: str
    total_cases: int
    open_cases: int
    risk_distribution: Dict[str, int]
    cases_by_district: Dict[str, int]
    cases_by_channel: Dict[str, int]
    cases_by_language: Dict[str, int]
    critical_override_count: int
    override_reasons: Dict[str, int]
    flag_frequency: Dict[str, int]
    sla_compliance_pct: float
    sla_state_counts: Dict[str, int]
    median_composite_by_band: Dict[str, float]
    actions_taken: Dict[str, int]
    engine_notes: Dict[str, str]
    disclaimer: str
