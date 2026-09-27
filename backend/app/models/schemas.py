"""
Pydantic schemas for API request/response validation.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ─── Intake ──────────────────────────────────────────────────────────────────

class IntakeRequest(BaseModel):
    """Victim submits text (and optionally audio) for assessment."""
    text: Optional[str] = Field(None, description="Raw text input from victim")
    channel: str = Field("chat", description="Source channel: chat, voice, ivrs, portal")
    consent_given: bool = Field(..., description="Explicit consent to process data")
    language: Optional[str] = Field(None, description="Language code if known; auto-detected otherwise")


class IntakeResponse(BaseModel):
    case_id: str
    message: str
    language_detected: str


# ─── Assessment ──────────────────────────────────────────────────────────────

class AssessmentResult(BaseModel):
    case_id: str
    svi_score: float = Field(..., ge=0, le=100)
    risk_category: str
    hard_override: bool = False
    override_reason: Optional[str] = None

    # Sub-scores for transparency
    text_sentiment_score: float
    keyword_density_score: float
    voice_prosody_score: Optional[float] = None
    interaction_pattern_score: float

    triggered_keywords: list[dict] = []
    sub_score_details: dict = {}


class AssessRequest(BaseModel):
    case_id: str


# ─── Cases ───────────────────────────────────────────────────────────────────

class CaseSummary(BaseModel):
    id: str
    created_at: datetime
    channel: str
    language_detected: str
    status: str
    svi_score: Optional[float] = None
    risk_category: Optional[str] = None
    assigned_to: Optional[str] = None
    assignee_name: Optional[str] = None
    hard_override: bool = False

    class Config:
        from_attributes = True


class CaseDetail(CaseSummary):
    raw_text: Optional[str] = None
    transcript: Optional[str] = None
    consent_given: bool
    consent_timestamp: Optional[datetime] = None
    assessments: list[AssessmentResult] = []
    recommendations: list[str] = []


class CaseStatusUpdate(BaseModel):
    status: str
    assigned_to: Optional[str] = None


# ─── Recommendations ────────────────────────────────────────────────────────

class RecommendationRuleSchema(BaseModel):
    risk_category: str
    actions: list[str]
    response_window: Optional[str] = None
    notify_roles: list[str] = []


class RecommendationResponse(BaseModel):
    risk_category: str
    actions: list[str]
    response_window: Optional[str] = None
    notify_roles: list[str] = []


# ─── Auth ────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: str = "counsellor"
    district: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    username: str
    full_name: str
    role: str
    district: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ─── Audit ───────────────────────────────────────────────────────────────────

class AuditEntry(BaseModel):
    id: int
    timestamp: datetime
    user_id: Optional[str] = None
    case_id: Optional[str] = None
    action: str
    details: Optional[dict] = None

    class Config:
        from_attributes = True


# ─── Dashboard Stats ────────────────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_cases: int
    critical_count: int
    high_count: int
    moderate_count: int
    low_count: int
    unassigned_count: int
    avg_svi: float
    cases_today: int
    risk_distribution: list[dict]
    recent_trend: list[dict]
