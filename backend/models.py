"""SQLAlchemy models for the NHAA 14566 Stress & Trauma Assessment module.

Design notes that matter for review:

* **Data minimization.** A complainant is a `User` with a random
  `pseudonym_id` and *no* identity columns. Optional identity, if a victim
  explicitly consents to share it, is stored separately in
  `IdentityDisclosure` and is Fernet-encrypted at rest (see `config.get_fernet`).
* **Human-in-the-loop.** `Case.status` has no value that can be reached
  without a `CaseAction` row, and `resolve_case` refuses Critical cases.
* **Auditability.** Every mutating endpoint calls `services.audit.record`.
"""

from __future__ import annotations

import datetime as dt
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from utils import new_case_ref, new_pseudonym, utcnow

CASE_STATUSES = ("open", "assigned", "in_progress", "awaiting_counsellor", "resolved", "closed")
OPEN_CASE_STATUSES = ("open", "assigned", "in_progress", "awaiting_counsellor")
RISK_CATEGORIES = ("Low", "Moderate", "High", "Critical")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(32), default="complainant", index=True)
    pseudonym_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=new_pseudonym)
    language_pref: Mapped[str] = mapped_column(String(8), default="en")
    district: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    cases: Mapped[List["Case"]] = relationship(back_populates="user")


class IdentityDisclosure(Base):
    """Optional, separately encrypted identity for a complainant.

    Never joined automatically into case responses. An operator must request
    disclosure explicitly, and doing so writes an AuditLog row.
    """

    __tablename__ = "identity_disclosures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    captured_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    captured_via: Mapped[str] = mapped_column(String(32), default="complainant_opt_in")


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(16))
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    withdrawn_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)

    @property
    def is_active(self) -> bool:
        return self.withdrawn_at is None


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: Pseudonymous, non-sequential reference. The only case id shown to staff.
    ref: Mapped[str] = mapped_column(String(32), unique=True, index=True, default=new_case_ref)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    district: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    #: Channel the case arrived on: chat | voice | ivrs
    channel: Mapped[str] = mapped_column(String(16), default="chat")
    language: Mapped[str] = mapped_column(String(8), default="en")
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    consent_version: Mapped[str] = mapped_column(String(64), default="")
    sla_due_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True, index=True)
    first_response_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="cases")
    interactions: Mapped[List["Interaction"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="Interaction.created_at"
    )
    actions: Mapped[List["CaseAction"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseAction.created_at"
    )

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_CASE_STATUSES


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16), index=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audio_ref: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    transcribed_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    #: IVRS keypad presses as a compact string, e.g. "1,1,2". Kept so the
    #: IVRS channel is auditable rather than a pure UI skin over chat.
    keypad_presses: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    #: Client-side time-to-type, in ms. Feeds the BehavioralScore.
    response_latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    #: Plain-language self-report answers (never a clinical instrument).
    self_report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)

    case: Mapped[Case] = relationship(back_populates="interactions")
    text_analysis: Mapped[Optional["TextAnalysis"]] = relationship(
        back_populates="interaction", cascade="all, delete-orphan", uselist=False
    )
    audio_analysis: Mapped[Optional["AudioAnalysis"]] = relationship(
        back_populates="interaction", cascade="all, delete-orphan", uselist=False
    )


class TextAnalysis(Base):
    __tablename__ = "text_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interaction_id: Mapped[int] = mapped_column(ForeignKey("interactions.id"), unique=True, index=True)
    sentiment: Mapped[str] = mapped_column(String(24), default="neutral")
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    #: JSON list of flag tokens, e.g. ["hopelessness", "isolation"]
    risk_flags: Mapped[str] = mapped_column(Text, default="[]")
    #: JSON dict of linguistic markers (absolutist terms, negation density, ...)
    markers: Mapped[str] = mapped_column(Text, default="{}")
    text_risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    #: "ml-model" | "heuristic" | "mixed" - never hidden from the caller.
    method: Mapped[str] = mapped_column(String(24), default="heuristic")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    lexicon_version: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    interaction: Mapped[Interaction] = relationship(back_populates="text_analysis")


class AudioAnalysis(Base):
    __tablename__ = "audio_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interaction_id: Mapped[int] = mapped_column(ForeignKey("interactions.id"), unique=True, index=True)
    pitch_mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pitch_var: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    jitter_proxy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pause_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pause_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speaking_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    energy_rms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vocal_stress_score: Mapped[float] = mapped_column(Float, default=0.0)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    #: "heuristic-demo" or "ml-model" - surfaced verbatim in the UI.
    method: Mapped[str] = mapped_column(String(24), default="heuristic-demo")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    interaction: Mapped[Interaction] = relationship(back_populates="audio_analysis")


class SVIScore(Base):
    __tablename__ = "svi_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    text_score: Mapped[float] = mapped_column(Float, default=0.0)
    vocal_score: Mapped[float] = mapped_column(Float, default=0.0)
    behavioral_score: Mapped[float] = mapped_column(Float, default=0.0)
    composite_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    category: Mapped[str] = mapped_column(String(16), default="Low", index=True)
    #: Set when the Critical Override fired, e.g. "suicidal_ideation_lexicon".
    override_reason: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    weights: Mapped[str] = mapped_column(Text, default="{}")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    computed_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)

    @property
    def is_critical_override(self) -> bool:
        return self.category == "Critical" and bool(self.override_reason)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    #: JSON list of machine action tokens, e.g. ["counselling", "legal_aid"]
    actions: Mapped[str] = mapped_column(Text, default="[]")
    #: Plain-language summary rendered for the counsellor, e.g.
    #: "Recommended: priority counsellor callback + legal aid referral"
    summary: Mapped[str] = mapped_column(Text, default="")
    ruleset_version: Mapped[str] = mapped_column(String(32), default="v1")
    generated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)


class CaseAction(Base):
    """Human-in-the-loop ledger.

    A case may only reach `resolved`/`closed` if a staff member wrote a
    `CaseAction` row, and Critical cases additionally require an action
    containing a safety contact. This table is what makes the "never
    auto-close a Critical case" rule auditable rather than aspirational.
    """

    __tablename__ = "case_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    #: assign | start | note | counselling | legal_aid | medical | police_liaison
    #: | witness_protection | emergency_bridge | safety_contact | resolve | close
    action: Mapped[str] = mapped_column(String(32), index=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)

    case: Mapped[Case] = relationship(back_populates="actions")
    actor: Mapped[Optional[User]] = relationship()


class CaseAssignment(Base):
    __tablename__ = "case_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    counsellor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    sla_due_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    #: open | in_progress | met | breached
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    resolved_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(48), index=True)
    target_type: Mapped[str] = mapped_column(String(32), index=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cases.id"), nullable=True, index=True)
    channel: Mapped[str] = mapped_column(String(24), index=True)
    recipient: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    payload: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)
    sent_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


Index("ix_cases_status_created", Case.status, Case.created_at)
Index("ix_svi_case_current", SVIScore.case_id, SVIScore.is_current)
