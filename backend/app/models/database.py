"""
NHAA Real-Time Stress & Trauma Assessment Module
Database models — SQLAlchemy ORM
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Text, Boolean, DateTime,
    ForeignKey, JSON, Enum as SAEnum, Index
)
from sqlalchemy.orm import relationship, DeclarativeBase
import enum


class Base(DeclarativeBase):
    pass


# ─── Enums ───────────────────────────────────────────────────────────────────

class RiskCategory(str, enum.Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class CaseStatus(str, enum.Enum):
    NEW = "new"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    FOLLOW_UP = "follow_up"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ChannelSource(str, enum.Enum):
    CHAT = "chat"
    VOICE = "voice"
    IVRS = "ivrs"
    PORTAL = "portal"


class UserRole(str, enum.Enum):
    COUNSELLOR = "counsellor"
    DISTRICT_ADMIN = "district_admin"
    SUPER_ADMIN = "super_admin"


# ─── Models ──────────────────────────────────────────────────────────────────

class Case(Base):
    """Core case record — one per victim interaction."""
    __tablename__ = "cases"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Channel metadata
    channel = Column(SAEnum(ChannelSource), nullable=False)
    language_detected = Column(String(10), default="en")

    # Consent
    consent_given = Column(Boolean, default=False, nullable=False)
    consent_timestamp = Column(DateTime, nullable=True)

    # Content
    raw_text = Column(Text, nullable=True)
    transcript = Column(Text, nullable=True)
    audio_path = Column(String(500), nullable=True)
    audio_uploaded_at = Column(DateTime, nullable=True)

    # Status & assignment
    status = Column(SAEnum(CaseStatus), default=CaseStatus.NEW, nullable=False)
    assigned_to = Column(String, ForeignKey("users.id"), nullable=True)

    # Relationships
    assessments = relationship("Assessment", back_populates="case", order_by="Assessment.created_at.desc()")
    audit_entries = relationship("AuditLog", back_populates="case")
    assignee = relationship("User", back_populates="assigned_cases")

    __table_args__ = (
        Index("ix_cases_status", "status"),
        Index("ix_cases_created_at", "created_at"),
    )


class Assessment(Base):
    """SVI assessment — one per scoring run (a case may be re-assessed)."""
    __tablename__ = "assessments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String, ForeignKey("cases.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Sub-scores (each 0.0–1.0)
    text_sentiment_score = Column(Float, default=0.0)
    keyword_density_score = Column(Float, default=0.0)
    voice_prosody_score = Column(Float, nullable=True)  # null if no audio
    interaction_pattern_score = Column(Float, default=0.0)

    # Fusion
    svi_score = Column(Float, nullable=False)  # 0–100
    risk_category = Column(SAEnum(RiskCategory), nullable=False)
    hard_override = Column(Boolean, default=False)
    override_reason = Column(String(500), nullable=True)

    # Explainability
    triggered_keywords = Column(JSON, default=list)   # list of {term, language, category}
    sub_score_details = Column(JSON, default=dict)     # full breakdown for audit

    # Relationship
    case = relationship("Case", back_populates="assessments")

    __table_args__ = (
        Index("ix_assessments_svi", "svi_score"),
        Index("ix_assessments_risk", "risk_category"),
    )


class RecommendationRule(Base):
    """Admin-editable rule table: risk category → actions."""
    __tablename__ = "recommendation_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    risk_category = Column(SAEnum(RiskCategory), nullable=False, unique=True)
    actions = Column(JSON, nullable=False)         # list of action strings
    response_window = Column(String(50), nullable=True)   # e.g. "24 hours"
    notify_roles = Column(JSON, default=list)      # roles to alert
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    updated_by = Column(String, nullable=True)


class User(Base):
    """System user — counsellors, admins."""
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    full_name = Column(String(200), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False)
    district = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    assigned_cases = relationship("Case", back_populates="assignee")


class AuditLog(Base):
    """Immutable audit trail — who viewed/modified what."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    case_id = Column(String, ForeignKey("cases.id"), nullable=True)
    action = Column(String(100), nullable=False)  # VIEW, ASSIGN, SCORE, STATUS_CHANGE, etc.
    details = Column(JSON, nullable=True)

    case = relationship("Case", back_populates="audit_entries")

    __table_args__ = (
        Index("ix_audit_timestamp", "timestamp"),
        Index("ix_audit_case", "case_id"),
    )
