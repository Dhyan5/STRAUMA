"""Ingest pipeline: interaction -> analyses -> SVI -> recommendation -> queue.

Keeping this orchestration in one service (rather than inside route handlers)
means the intake paths - chat, voice upload, IVRS - cannot drift apart, and the
test suite can drive the whole chain without HTTP.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from config import DISCLAIMER, SLA_HOURS, settings
from engine import behavioral, recommendations as rec_engine, svi as svi_engine
from models import (
    AuditLog,
    Case,
    CaseAction,
    CaseAssignment,
    Interaction,
    NotificationOutbox,
    Recommendation,
    SVIScore,
    TextAnalysis,
    User,
)
from nlp import text_analyzer
from nlp.audio_analyzer import analyze_audio_file
from utils import dumps, loads, utcnow

log = logging.getLogger(__name__)


def _recontact_count(db: Session, case: Case) -> int:
    """Interactions that re-opened an already-touched case inside the window."""
    window_start = utcnow() - dt.timedelta(hours=behavioral.RECONTACT_WINDOW_HOURS)
    total = db.query(Interaction).filter(
        Interaction.case_id == case.id, Interaction.created_at >= window_start
    ).count()
    return max(0, total - 1)


def _latest_self_report(db: Session, case: Case) -> Optional[Dict[str, Any]]:
    interaction = (
        db.query(Interaction)
        .filter(Interaction.case_id == case.id, Interaction.self_report.isnot(None))
        .order_by(Interaction.created_at.desc())
        .first()
    )
    if not interaction:
        return None
    return loads(interaction.self_report, None)


def _critical_occurrences(db: Session, case: Case) -> List[str]:
    """Critical-tier flags across the whole case, one entry per occurrence.

    This is the only input the Critical Override consumes, so the tier filter
    has to be exact: a `high`-tier flag (threat language, child-safety concern)
    must never be able to force the top band on its own. Tiers come from the
    lexicon `flag_details` that were stored with the analysis, not from a
    hard-coded list here, so the rule stays in one place.
    """
    from nlp.lexicons import TIER_CRITICAL

    analyses = (
        db.query(TextAnalysis)
        .join(Interaction, TextAnalysis.interaction_id == Interaction.id)
        .filter(Interaction.case_id == case.id)
        .all()
    )
    occurrences: List[str] = []
    for analysis in analyses:
        markers = loads(analysis.markers, {}) or {}
        for detail in markers.get("flag_details", []) or []:
            if str(detail.get("tier", "")).lower() == TIER_CRITICAL:
                occurrences.append(str(detail.get("flag")))
    return occurrences


def _text_risk_rollup(db: Session, case: Case) -> Tuple[float, List[str], List[Dict[str, Any]], float]:
    """**Peak** text score across the case, plus every flag ever seen.

    Peak, not mean and not latest. Averaging would let a later calm message
    dilute an earlier serious one, and taking only the latest would let someone
    who opens with a crisis statement and then says "sorry, never mind" drop
    out of the queue. A distress signal that was expressed is expressed.
    Every flag is retained regardless, because the Critical Override is
    deliberately even more conservative: it latches on any critical-tier flag
    ever seen on the case.
    """
    analyses = (
        db.query(TextAnalysis)
        .join(Interaction, TextAnalysis.interaction_id == Interaction.id)
        .filter(Interaction.case_id == case.id)
        .all()
    )
    if not analyses:
        return 0.0, [], [], 0.2

    peak = max(analyses, key=lambda a: (a.text_risk_score or 0.0, a.created_at))
    all_flags: List[str] = []
    all_details: List[Dict[str, Any]] = []
    for analysis in analyses:
        all_flags.extend(loads(analysis.risk_flags, []))
        all_details.extend((loads(analysis.markers, {}) or {}).get("flag_details", []) or [])

    return (
        float(peak.text_risk_score),
        list(dict.fromkeys(all_flags)),
        all_details,
        float(peak.confidence),
    )


def _vocal_rollup(db: Session, case: Case) -> Tuple[Optional[float], bool, str]:
    """Mean vocal stress across the case's audio turns, if any exist."""
    rows = (
        db.query(Interaction)
        .join(Interaction.audio_analysis)
        .filter(Interaction.case_id == case.id)
        .all()
    )
    scores = [i.audio_analysis.vocal_stress_score for i in rows if i.audio_analysis and i.audio_analysis.vocal_stress_score is not None]
    if not scores:
        return None, False, "no-audio"
    method = rows[0].audio_analysis.method if rows[0].audio_analysis else "heuristic-demo"
    return round(sum(scores) / len(scores), 2), True, method


def _latencies(db: Session, case: Case) -> List[int]:
    rows = (
        db.query(Interaction.response_latency_ms)
        .filter(Interaction.case_id == case.id, Interaction.response_latency_ms.isnot(None))
        .all()
    )
    return [int(r[0]) for r in rows]


def recompute_svi(db: Session, case: Case, actor: Optional[User] = None) -> Dict[str, Any]:
    """Recompute the SVI for a case from all of its interactions so far."""
    text_score, risk_flags, flag_details, lexical_confidence = _text_risk_rollup(db, case)
    vocal_score, voice_present, _method = _vocal_rollup(db, case)
    behavioral_result = behavioral.compute_behavioral_score(
        latencies_ms=_latencies(db, case),
        recontact_count=_recontact_count(db, case),
        self_report_answers=_latest_self_report(db, case),
    )
    critical_flags = _critical_occurrences(db, case)

    result = svi_engine.compute_svi(
        text_score=text_score,
        vocal_score=vocal_score,
        behavioral_score=behavioral_result.score,
        risk_flags=risk_flags,
        flag_details=flag_details,
        critical_occurrences=critical_flags,
        lexical_confidence=lexical_confidence,
    )

    # Supersede the previous reading; keep history for audit.
    db.query(SVIScore).filter(SVIScore.case_id == case.id).update({"is_current": False})
    score_row = SVIScore(
        case_id=case.id,
        text_score=result.text_score,
        vocal_score=result.vocal_score,
        behavioral_score=result.behavioral_score,
        composite_score=result.composite_score,
        category=result.category,
        override_reason=result.override_reason,
        weights=dumps(result.weights),
        is_current=True,
    )
    db.add(score_row)

    rec_payload = rec_engine.generate_recommendations(
        category=result.category,
        flags=result.risk_flags,
        override_reason=result.override_reason,
        sla_hours=result.sla_hours,
    )
    rec_row = Recommendation(
        case_id=case.id,
        actions=dumps(rec_payload["actions"]),
        summary=rec_payload["summary"],
        ruleset_version=rec_payload["ruleset_version"],
    )
    db.add(rec_row)

    case.sla_due_at = utcnow() + dt.timedelta(hours=result.sla_hours)
    if case.status == "open" and result.category in ("High", "Critical"):
        case.status = "assigned"

    db.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            actor_role=actor.role if actor else None,
            action="svi_recomputed",
            target_type="case",
            target_id=str(case.id),
            detail=dumps(
                {
                    "category": result.category,
                    "composite": result.composite_score,
                    "override": bool(result.override_reason),
                    "weights": result.weights,
                }
            ),
        )
    )
    db.flush()
    return {**result.as_dict(), "behavioral": behavioral_result.as_dict(), "recommendation": rec_payload}


def current_svi(db: Session, case_id: int) -> Optional[SVIScore]:
    return (
        db.query(SVIScore)
        .filter(SVIScore.case_id == case_id, SVIScore.is_current.is_(True))
        .order_by(SVIScore.computed_at.desc())
        .first()
    )


def current_recommendation(db: Session, case_id: int) -> Optional[Recommendation]:
    return (
        db.query(Recommendation)
        .filter(Recommendation.case_id == case_id)
        .order_by(Recommendation.generated_at.desc())
        .first()
    )


def enqueue_notification(
    db: Session,
    case: Case,
    channel: str,
    payload: Dict[str, Any],
    recipient: Optional[str] = None,
) -> NotificationOutbox:
    row = NotificationOutbox(
        case_id=case.id,
        channel=channel,
        recipient=recipient,
        payload=dumps(payload),
        status="pending",
        provider=settings.notification_provider,
    )
    db.add(row)
    db.flush()
    return row


def escalate(db: Session, case: Case, result: Dict[str, Any], actor: Optional[User] = None) -> List[str]:
    """Create assignment + notification rows for a High/Critical case.

    Nothing is *sent* by this function. The mock notification provider only
    records intent into the outbox, so a judge can see exactly what would have
    gone out over SMS, email and WhatsApp.
    """
    created: List[str] = []
    category = str(result.get("category"))
    if category not in ("High", "Critical"):
        return created

    assignment = (
        db.query(CaseAssignment)
        .filter(CaseAssignment.case_id == case.id, CaseAssignment.status.in_(("open", "in_progress")))
        .order_by(CaseAssignment.assigned_at.desc())
        .first()
    )
    if assignment is None:
        assignment = CaseAssignment(
            case_id=case.id,
            counsellor_id=None,
            sla_due_at=utcnow() + dt.timedelta(hours=SLA_HOURS[category]),
            status="open",
        )
        db.add(assignment)
    else:
        assignment.sla_due_at = utcnow() + dt.timedelta(hours=SLA_HOURS[category])

    payload = {
        "case_ref": case.ref,
        "case_id": case.id,
        "district": case.district,
        "channel": case.channel,
        "category": category,
        "override_reason": result.get("override_reason"),
        "risk_flags": result.get("risk_flags", []),
        "recommended_actions": result.get("recommendation", {}).get("actions", []),
        "sla_label": result.get("recommendation", {}).get("sla_label", ""),
        "queued_at": utcnow().isoformat(),
        "disclaimer": DISCLAIMER,
        "requires_human_action": True,
    }

    for channel in ("sms", "email", "whatsapp", "dashboard_alert"):
        enqueue_notification(db, case, channel, payload)
        created.append(channel)

    db.add(
        CaseAction(
            case_id=case.id,
            actor_id=actor.id if actor else None,
            action="escalated",
            note=f"Auto-routed to {category} band by the SVI engine; awaiting a human action.",
        )
    )
    db.flush()
    return created


def sla_state(assignment: Optional[CaseAssignment], category: str) -> str:
    """ok | due_soon | breached | unassigned - for the staff queue."""
    if assignment is None:
        return "unassigned"
    if assignment.sla_due_at is None:
        return "unassigned"
    now = utcnow()
    if now <= assignment.sla_due_at:
        remaining = (assignment.sla_due_at - now).total_seconds()
        if category == "Critical" or remaining < 3600:
            return "due_soon"
        return "ok"
    return "breached"


def seed_analysis_for_interaction(
    db: Session,
    interaction: Interaction,
    language: str,
) -> Optional[TextAnalysis]:
    """Analyse an interaction's text and persist the result. Voice turns also
    get a transcript if one exists, so the text path still runs."""
    text = interaction.transcribed_text or interaction.raw_text
    if not text:
        return None
    result = text_analyzer.analyze_text(text, language=language)
    row = TextAnalysis(
        interaction_id=interaction.id,
        sentiment=result.sentiment,
        sentiment_score=result.sentiment_score,
        risk_flags=dumps(result.risk_flags),
        markers=dumps({**result.markers, "flag_details": result.flag_details}),
        text_risk_score=result.text_risk_score,
        method=result.method,
        confidence=result.confidence,
        lexicon_version=result.lexicon_version,
    )
    db.add(row)
    db.flush()
    return row


def persist_audio_analysis(
    db: Session,
    interaction: Interaction,
    audio_path: str,
    provenance: str = "real",
):
    from models import AudioAnalysis

    result = analyze_audio_file(audio_path, provenance=provenance)
    row = AudioAnalysis(
        interaction_id=interaction.id,
        pitch_mean=result.pitch_mean,
        pitch_var=result.pitch_var,
        jitter_proxy=result.jitter_proxy,
        pause_count=result.pause_count,
        pause_ratio=result.pause_ratio,
        speaking_rate=result.speaking_rate,
        energy_rms=result.energy_rms,
        vocal_stress_score=result.vocal_stress_score,
        duration_sec=result.duration_sec,
        method=result.method,
        confidence=result.confidence,
        notes=result.notes,
    )
    db.add(row)
    db.flush()
    return result, row


def language_fallbacks(language: str) -> Sequence[str]:
    """Extra lexicons to consult for a session language."""
    return [language, "en"] if language and language != "en" else ["en"]
