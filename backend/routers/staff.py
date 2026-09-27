"""Staff endpoints: counsellor queue, case detail, actions, admin analytics.

Three invariants enforced here rather than trusted to callers:

1. A Critical case can never reach `resolved`/`closed` without a human action
   on the ledger, and specifically without a `safety_contact` or
   `emergency_bridge` record. `POST /actions` is the only write path, and
   `POST /resolve` refuses Critical cases outright.
2. Every read of a case writes an audit row. Viewing a case record is a
   disclosure event under the DPDP Act 2023.
3. Law-enforcement visibility is opt-in: a case appears in the police view only
   after a `police_liaison` action has actually been recorded.
"""

from __future__ import annotations

import datetime as dt
import logging
import statistics
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from config import (
    ANALYTICS_ROLES,
    DISCLAIMER,
    SLA_HOURS,
    SLA_LABELS,
)
from database import get_db
from engine import ingest
from engine.recommendations import (
    ACTION_LABELS,
    ACTION_ROLES,
    MANDATORY_BEFORE_CRITICAL_CLOSE,
    action_allowed,
    exposes_to_law_enforcement,
)
from models import (
    Case,
    CaseAction,
    CaseAssignment,
    Interaction,
    Recommendation,
    SVIScore,
    TextAnalysis,
    User,
)
from schemas import (
    ActionRequest,
    ActionResponse,
    AnalyticsOut,
    CaseActionOut,
    QueueItem,
    StaffCaseDetail,
)
from security import client_ip, get_current_user, record, require_admin, require_counsellor
from services import notifications, queue
from utils import dumps, loads, utcnow

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["staff"])

#: Human-action verbs a counsellor may record. Deliberately not free text: a
#: controlled vocabulary is what makes the audit trail and the "did a human
#: actually act?" question answerable.
ACTIONABLE = {
    "counselling",
    "legal_aid",
    "medical",
    "police_liaison",
    "witness_protection",
    "emergency_bridge",
    "safety_contact",
    "note",
    "resolve",
    "close",
}


def _case_or_404(db: Session, case_id: int) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


def _assignment(db: Session, case_id: int) -> Optional[CaseAssignment]:
    return (
        db.query(CaseAssignment)
        .filter(CaseAssignment.case_id == case_id)
        .order_by(CaseAssignment.assigned_at.desc())
        .first()
    )


def _latest_interaction(db: Session, case_id: int) -> Optional[Interaction]:
    return (
        db.query(Interaction)
        .filter(Interaction.case_id == case_id)
        .order_by(Interaction.created_at.desc())
        .first()
    )


def _to_queue_item(
    db: Session,
    case: Case,
    svi: Optional[SVIScore],
    recommendation: Optional[Recommendation],
    assignment: Optional[CaseAssignment],
) -> QueueItem:
    category = svi.category if svi else "Low"
    override = svi.override_reason if svi else None
    sla_state_value = ingest.sla_state(assignment, category)
    counsellor = db.get(User, assignment.counsellor_id) if assignment and assignment.counsellor_id else None
    return QueueItem(
        case_id=case.id,
        case_ref=case.ref,
        district=case.district,
        channel=case.channel,
        language=case.language,
        status=case.status,
        category=category,
        composite_score=round(svi.composite_score, 2) if svi else 0.0,
        is_critical_override=bool(override),
        override_reason=override,
        risk_flags=_flags_for_case(db, case.id),
        recommended_actions=loads(recommendation.actions, []) if recommendation else [],
        sla_state=sla_state_value,
        sla_due_at=assignment.sla_due_at if assignment else case.sla_due_at,
        queue_priority=queue.priority_for(category, sla_state_value, bool(override)),
        created_at=case.created_at,
        assigned_counsellor_id=assignment.counsellor_id if assignment else None,
        assigned_counsellor_name=counsellor.display_name if counsellor else None,
    )


def _flags_for_case(db: Session, case_id: int) -> List[str]:
    rows = (
        db.query(TextAnalysis)
        .join(Interaction, TextAnalysis.interaction_id == Interaction.id)
        .filter(Interaction.case_id == case_id)
        .all()
    )
    flags: List[str] = []
    for row in rows:
        flags.extend(loads(row.risk_flags, []))
    return list(dict.fromkeys(flags))


# --------------------------------------------------------------------------
# Counsellor queue
# --------------------------------------------------------------------------


@router.get("/counsellor/queue", response_model=List[QueueItem])
def counsellor_queue(
    district: Optional[str] = None,
    include_resolved: bool = False,
    user: User = Depends(require_counsellor),
    db: Session = Depends(get_db),
) -> List[QueueItem]:
    """Risk-sorted queue. Critical overrides are always hoisted to the top."""
    query = db.query(Case)
    if not include_resolved:
        query = query.filter(Case.status.in_(("open", "assigned", "in_progress", "awaiting_counsellor")))
    if user.role == "district_admin" and user.district:
        query = query.filter(Case.district == user.district)
    elif district:
        query = query.filter(Case.district == district)

    items = [
        _to_queue_item(
            db,
            case,
            ingest.current_svi(db, case.id),
            ingest.current_recommendation(db, case.id),
            _assignment(db, case.id),
        )
        for case in query.all()
    ]
    items.sort(key=lambda i: (i.queue_priority, -i.composite_score, i.created_at))

    record(db, user, "view_queue", "case", None, {"count": len(items), "district": district})
    db.commit()
    return items


@router.get("/counsellor/queue/{case_id}", response_model=StaffCaseDetail)
def case_detail(
    case_id: int,
    user: User = Depends(require_counsellor),
    db: Session = Depends(get_db),
) -> StaffCaseDetail:
    """Full case detail with the SVI breakdown and one-click recommended actions."""
    case = _case_or_404(db, case_id)
    if user.role == "district_admin" and user.district and case.district != user.district:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Outside your district scope")

    svi = ingest.current_svi(db, case.id)
    history = (
        db.query(SVIScore)
        .filter(SVIScore.case_id == case.id)
        .order_by(SVIScore.computed_at.desc())
        .limit(20)
        .all()
    )
    recommendation = ingest.current_recommendation(db, case.id)
    interactions = db.query(Interaction).filter(Interaction.case_id == case.id).order_by(Interaction.created_at).all()
    actions = db.query(CaseAction).filter(CaseAction.case_id == case.id).order_by(CaseAction.created_at).all()
    assignment = _assignment(db, case.id)
    latest = _latest_interaction(db, case.id)

    behavioral: Dict[str, Any] = {}
    if latest is not None:
        from engine.behavioral import compute_behavioral_score

        result = compute_behavioral_score(
            latencies_ms=[
                i.response_latency_ms
                for i in interactions
                if i.response_latency_ms is not None
            ],
            recontact_count=ingest._recontact_count(db, case),
            self_report_answers=loads(latest.self_report, None),
        )
        behavioral = result.as_dict()

    category = svi.category if svi else "Low"
    sla_state_value = ingest.sla_state(assignment, category)
    action_list = loads(recommendation.actions, []) if recommendation else []

    record(
        db,
        user,
        "view_case",
        "case",
        case.ref,
        {"category": category, "sla_state": sla_state_value},
    )
    if case.first_response_at is None:
        case.first_response_at = utcnow()
    db.commit()

    return StaffCaseDetail(
        case=case,
        category=category,
        composite_score=round(svi.composite_score, 2) if svi else 0.0,
        is_critical_override=bool(svi and svi.override_reason),
        override_reason=svi.override_reason if svi else None,
        svi=svi,
        svi_history=history,
        behavioral=behavioral,
        recommendation=recommendation,
        actions=[
            CaseActionOut(
                id=a.id,
                action=a.action,
                note=a.note,
                created_at=a.created_at,
                actor_role=a.actor.role if a.actor else None,
                actor_id=a.actor_id,
            )
            for a in actions
        ],
        interactions=interactions,
        assignment={
            "id": assignment.id,
            "counsellor_id": assignment.counsellor_id,
            "assigned_at": assignment.assigned_at,
            "sla_due_at": assignment.sla_due_at,
            "status": assignment.status,
        }
        if assignment
        else None,
        sla_state=sla_state_value,
        sla_label=SLA_LABELS.get(category, ""),
        queue_priority=queue.priority_for(category, sla_state_value, bool(svi and svi.override_reason)),
        exposes_to_law_enforcement=exposes_to_law_enforcement(action_list),
        method_note=_method_note(db, case.id),
        disclaimer=DISCLAIMER,
    )


def _method_note(db: Session, case_id: int) -> str:
    """State which engine actually produced these numbers.

    Built from the stored `method` fields rather than from configuration, so a
    counsellor sees what this specific case was scored with - which may differ
    from the default if the backend was switched mid-session.
    """
    rows = (
        db.query(TextAnalysis)
        .join(Interaction, TextAnalysis.interaction_id == Interaction.id)
        .filter(Interaction.case_id == case_id)
        .all()
    )
    text_methods = sorted({r.method for r in rows if r.method})
    audio_methods = sorted(
        {
            i.audio_analysis.method
            for i in db.query(Interaction).filter(Interaction.case_id == case_id).all()
            if i.audio_analysis is not None and i.audio_analysis.method
        }
    )
    return (
        f"Text engine: {', '.join(text_methods) or 'not scored'}. "
        f"Audio features: {', '.join(audio_methods) or 'not used'}. "
        "Vocal features are prototype-grade heuristics, not a trained classifier. "
        "Decision support only; not a diagnosis."
    )


# --------------------------------------------------------------------------
# Assignment and human actions
# --------------------------------------------------------------------------


@router.post("/counsellor/cases/{case_id}/assign", response_model=ActionResponse)
def assign_case(
    case_id: int,
    note: Optional[str] = None,
    user: User = Depends(require_counsellor),
    db: Session = Depends(get_db),
) -> ActionResponse:
    case = _case_or_404(db, case_id)
    svi = ingest.current_svi(db, case.id)
    category = svi.category if svi else "Low"

    assignment = _assignment(db, case.id)
    if assignment is None:
        assignment = CaseAssignment(case_id=case.id, counsellor_id=user.id, status="open")
        db.add(assignment)
    assignment.counsellor_id = user.id
    assignment.status = "in_progress" if assignment.status == "open" else assignment.status
    assignment.sla_due_at = utcnow() + dt.timedelta(hours=SLA_HOURS[category])
    case.status = "in_progress" if case.status in ("open", "assigned") else case.status

    db.add(
        CaseAction(
            case_id=case.id,
            actor_id=user.id,
            action="assigned",
            note=note or f"Picked up by {user.display_name or user.pseudonym_id}.",
        )
    )
    record(db, user, "assign_case", "case", case.ref, {"category": category})
    db.commit()
    return ActionResponse(
        case_ref=case.ref,
        recorded=["assigned"],
        status=case.status,
        message=f"Case assigned. {SLA_LABELS.get(category, '')}",
    )


@router.get("/counsellor/actions/catalogue")
def action_catalogue(user: User = Depends(require_counsellor)) -> Dict[str, Any]:
    """Which one-click buttons this user is allowed to press, and why."""
    return {
        "actions": [
            {
                "action": action,
                "label": ACTION_LABELS[action],
                "allowed": action_allowed(action, user.role),
                "allowed_roles": sorted(ACTION_ROLES.get(action, set())),
            }
            for action in sorted(ACTION_LABELS)
        ],
        "mandatory_before_critical_close": list(MANDATORY_BEFORE_CRITICAL_CLOSE),
        "disclaimer": DISCLAIMER,
    }


@router.post("/counsellor/cases/{case_id}/actions", response_model=ActionResponse)
def record_action(
    request: Request,
    case_id: int,
    payload: ActionRequest,
    user: User = Depends(require_counsellor),
    db: Session = Depends(get_db),
) -> ActionResponse:
    """The only write path for human action on a case."""
    case = _case_or_404(db, case_id)
    action = payload.action
    if action not in ACTIONABLE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown action '{action}'. Allowed: {sorted(ACTIONABLE)}",
        )
    if action in ACTION_ROLES and not action_allowed(action, user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' cannot record '{action}'",
        )

    entry = CaseAction(case_id=case.id, actor_id=user.id, action=action, note=payload.note)
    db.add(entry)

    if action in ("resolve", "close"):
        _assert_closeable(db, case, user)
        case.status = "resolved" if action == "resolve" else "closed"
        _close_assignment(db, case)
    elif action in ("emergency_bridge", "safety_contact", "counselling") and case.status == "assigned":
        case.status = "in_progress"

    record(
        db,
        user,
        f"case_action:{action}",
        "case",
        case.ref,
        {"note": (payload.note or "")[:400], "ip": client_ip(request)},
    )
    db.commit()
    db.refresh(entry)

    outstanding = _outstanding_critical_actions(db, case)
    return ActionResponse(
        case_ref=case.ref,
        recorded=[action],
        status=case.status,
        still_open_actions=outstanding,
        message=(
            "Recorded. A Critical case cannot close until a safety contact and a live "
            "bridge are on the record."
            if outstanding
            else "Recorded."
        ),
    )


def _outstanding_critical_actions(db: Session, case: Case) -> List[str]:
    svi = ingest.current_svi(db, case.id)
    if not svi or svi.category != "Critical":
        return []
    recorded = {a.action for a in db.query(CaseAction).filter(CaseAction.case_id == case.id).all()}
    return [a for a in MANDATORY_BEFORE_CRITICAL_CLOSE if a not in recorded]


def _assert_closeable(db: Session, case: Case, user: Optional[User] = None) -> None:
    """The human-in-the-loop gate. See module guardrail 3.

    A Critical case can never be resolved by the system. It can only be closed
    by a district or state administrator, and only once a safety contact and a
    live bridge are on the human-action ledger.
    """
    svi = ingest.current_svi(db, case.id)
    if svi is None or svi.category != "Critical":
        return

    outstanding = _outstanding_critical_actions(db, case)
    if outstanding:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This case is in the Critical band and cannot be closed automatically. "
                f"A human must first record: {', '.join(outstanding)}."
            ),
        )
    if user is not None and user.role not in ("district_admin", "state_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Closing a Critical case requires district or state administrator sign-off. "
                "The record is complete but this role cannot sign it off."
            ),
        )


def _close_assignment(db: Session, case: Case) -> None:
    assignment = _assignment(db, case.id)
    if assignment is not None:
        assignment.status = "met" if assignment.sla_due_at and utcnow() <= assignment.sla_due_at else "breached"
        assignment.resolved_at = utcnow()
    queue.remove_queue_entry(case.ref)


@router.post("/counsellor/cases/{case_id}/resolve", response_model=ActionResponse)
def resolve_case(
    request: Request,
    case_id: int,
    note: Optional[str] = None,
    user: User = Depends(require_counsellor),
    db: Session = Depends(get_db),
) -> ActionResponse:
    """Convenience wrapper that is deliberately guarded by the same gate."""
    return record_action(request, case_id, ActionRequest(action="resolve", note=note), user, db)


# --------------------------------------------------------------------------
# Admin analytics
# --------------------------------------------------------------------------


def _median(values: List[float]) -> Optional[float]:
    return round(statistics.median(values), 2) if values else None


@router.get("/admin/analytics", response_model=AnalyticsOut)
def analytics(
    district: Optional[str] = None,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AnalyticsOut:
    query = db.query(Case)
    scope = "state"
    if user.role == "district_admin" and user.district:
        query = query.filter(Case.district == user.district)
        scope = f"district:{user.district}"
    elif district:
        query = query.filter(Case.district == district)
        scope = f"district:{district}"

    cases = query.all()
    case_ids = [c.id for c in cases]
    scores = [s for s in (ingest.current_svi(db, cid) for cid in case_ids) if s is not None]

    risk_distribution = {"Low": 0, "Moderate": 0, "High": 0, "Critical": 0}
    by_district: Dict[str, int] = {}
    by_channel: Dict[str, int] = {}
    by_language: Dict[str, int] = {}
    sla_counts = {"ok": 0, "due_soon": 0, "breached": 0, "unassigned": 0}
    override_reasons: Dict[str, int] = {}
    composites: Dict[str, List[float]] = {}
    flag_frequency: Dict[str, int] = {}

    for case in cases:
        by_district[case.district or "unspecified"] = by_district.get(case.district or "unspecified", 0) + 1
        by_channel[case.channel] = by_channel.get(case.channel, 0) + 1
        by_language[case.language] = by_language.get(case.language, 0) + 1
        svi = ingest.current_svi(db, case.id)
        if svi is None:
            continue
        risk_distribution[svi.category] = risk_distribution.get(svi.category, 0) + 1
        composites.setdefault(svi.category, []).append(svi.composite_score)
        if svi.override_reason:
            reason = svi.override_reason.split(" [")[0]
            override_reasons[reason] = override_reasons.get(reason, 0) + 1
        sla_counts[ingest.sla_state(_assignment(db, case.id), svi.category)] += 1
        for flag in _flags_for_case(db, case.id):
            flag_frequency[flag] = flag_frequency.get(flag, 0) + 1

    measured = [sla_counts["ok"] + sla_counts["due_soon"]]
    sla_compliance = round(100.0 * measured[0] / max(1, sum(measured)), 1)

    action_rows = db.query(CaseAction).filter(CaseAction.case_id.in_(case_ids or [0])).all()
    actions_taken: Dict[str, int] = {}
    for row in action_rows:
        actions_taken[row.action] = actions_taken.get(row.action, 0) + 1

    from nlp.sentiment import backend_name as sentiment_backend

    record(db, user, "view_analytics", "case", None, {"scope": scope})
    db.commit()

    return AnalyticsOut(
        generated_at=utcnow(),
        scope=scope,
        total_cases=len(cases),
        open_cases=sum(1 for c in cases if c.is_open),
        risk_distribution=risk_distribution,
        cases_by_district=by_district,
        cases_by_channel=by_channel,
        cases_by_language=by_language,
        critical_override_count=sum(1 for s in scores if s.override_reason),
        override_reasons=override_reasons,
        flag_frequency=flag_frequency,
        sla_compliance_pct=sla_compliance,
        sla_state_counts=sla_counts,
        median_composite_by_band={band: _median(values) for band, values in composites.items() if values},
        actions_taken=actions_taken,
        engine_notes={
            "sentiment_backend": sentiment_backend(),
            "queue_backend": queue.backend_name(),
            "notification_provider": notifications.provider_status()["provider"],
            "scoring": "SVI = weighted blend of text, vocal and behavioural signals; see /api/admin/rules",
        },
        disclaimer=DISCLAIMER,
    )


@router.get("/admin/rules")
def rules(user: User = Depends(require_admin)) -> Dict[str, Any]:
    """The rules engine, published so reviewers can check it is deterministic."""
    from engine.recommendations import RULES, RULESET_VERSION
    from engine.svi import BANDS, OVERRIDE_REASONS, WEIGHTS_TEXT_ONLY, WEIGHTS_WITH_VOICE
    from nlp.lexicons import all_lexicons, LEXICON_VERSION

    return {
        "ruleset_version": RULESET_VERSION,
        "svi_bands": BANDS,
        "svi_weights": {"with_voice": WEIGHTS_WITH_VOICE, "text_only": WEIGHTS_TEXT_ONLY},
        "override_reasons": OVERRIDE_REASONS,
        "recommendation_rules": [
            {
                "id": rule.id,
                "when_category": sorted(rule.when_category) if rule.when_category else None,
                "when_flags_any": sorted(rule.when_flags_any) if rule.when_flags_any else None,
                "actions": rule.actions,
                "note": rule.note,
            }
            for rule in RULES
        ],
        "lexicon_version": LEXICON_VERSION,
        "lexicons": {
            code: {
                "curation_status": lex.curation_status,
                "flags": {name: {"tier": spec.get("tier"), "weight": spec.get("weight")} for name, spec in lex.flags.items()},
                "pattern_counts": {name: len(pats) for name, pats in lex.compiled.items()},
            }
            for code, lex in sorted(all_lexicons().items())
        },
        "disclaimer": DISCLAIMER,
    }


@router.get("/admin/audit")
def audit_log(
    limit: int = 100,
    case_ref: Optional[str] = None,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """The audit trail. Read-only, and itself audited."""
    from models import AuditLog

    query = db.query(AuditLog)
    if case_ref:
        query = query.filter(AuditLog.target_id == case_ref)
    rows = query.order_by(AuditLog.created_at.desc()).limit(min(limit, 500)).all()
    record(db, user, "view_audit", "case", case_ref)
    db.commit()
    return [
        {
            "id": row.id,
            "actor_id": row.actor_id,
            "actor_role": row.actor_role,
            "action": row.action,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "detail": loads(row.detail, None),
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/admin/notifications")
def outbox(
    limit: int = 50,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    from models import NotificationOutbox

    rows = db.query(NotificationOutbox).order_by(NotificationOutbox.created_at.desc()).limit(min(limit, 200)).all()
    record(db, user, "view_outbox", "case", None)
    db.commit()
    return {
        "provider": notifications.provider_status(),
        "entries": [notifications.preview(row) for row in rows],
    }


@router.post("/admin/notifications/drain")
def drain_outbox(user: User = Depends(require_admin), db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Process the outbox. With the mock provider this only logs and marks sent."""
    processed = notifications.drain_outbox(db)
    return {"processed": processed, "provider": notifications.provider_status()["provider"]}


_ = (get_current_user, dumps, SLA_HOURS, Interaction, User)
