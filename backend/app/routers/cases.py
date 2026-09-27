"""
Cases router — queue management, case details, status updates.
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, case as sql_case

from app.db import get_db
from app.models.database import (
    Case, Assessment, User, AuditLog, RiskCategory, CaseStatus
)
from app.models.schemas import (
    CaseSummary, CaseDetail, CaseStatusUpdate, DashboardStats, AuditEntry
)

router = APIRouter(prefix="/cases", tags=["Cases"])


@router.get("/", response_model=list[CaseSummary])
def list_cases(
    status: str | None = None,
    risk: str | None = None,
    sort_by: str = "svi",
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    List cases sorted by SVI (highest risk first) — the counsellor's triage queue.
    """
    # Subquery: get latest assessment per case
    latest_assessment = (
        db.query(
            Assessment.case_id,
            func.max(Assessment.created_at).label("latest_at")
        )
        .group_by(Assessment.case_id)
        .subquery()
    )

    query = (
        db.query(Case, Assessment)
        .outerjoin(latest_assessment, Case.id == latest_assessment.c.case_id)
        .outerjoin(
            Assessment,
            (Assessment.case_id == Case.id) &
            (Assessment.created_at == latest_assessment.c.latest_at)
        )
        .options(joinedload(Case.assignee))
    )

    # Filters
    if status:
        query = query.filter(Case.status == status)
    if risk:
        query = query.filter(Assessment.risk_category == risk)

    # Sort by SVI descending (highest risk first)
    if sort_by == "svi":
        query = query.order_by(desc(Assessment.svi_score).nulls_last())
    elif sort_by == "date":
        query = query.order_by(desc(Case.created_at))
    else:
        query = query.order_by(desc(Assessment.svi_score).nulls_last())

    results = query.offset(offset).limit(limit).all()

    summaries = []
    for case_obj, assessment in results:
        summaries.append(CaseSummary(
            id=case_obj.id,
            created_at=case_obj.created_at,
            channel=case_obj.channel.value if case_obj.channel else "chat",
            language_detected=case_obj.language_detected or "en",
            status=case_obj.status.value if hasattr(case_obj.status, 'value') else str(case_obj.status),
            svi_score=assessment.svi_score if assessment else None,
            risk_category=assessment.risk_category.value if assessment else None,
            assigned_to=case_obj.assigned_to,
            assignee_name=case_obj.assignee.full_name if case_obj.assignee else None,
            hard_override=assessment.hard_override if assessment else False,
        ))

    return summaries


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db)):
    """
    Dashboard aggregate statistics.
    """
    total = db.query(func.count(Case.id)).scalar() or 0

    # Count by risk category (from latest assessment)
    risk_counts = {}
    for risk in RiskCategory:
        count = (
            db.query(func.count(Assessment.id))
            .filter(Assessment.risk_category == risk)
            .scalar() or 0
        )
        risk_counts[risk.value] = count

    unassigned = (
        db.query(func.count(Case.id))
        .filter(Case.assigned_to.is_(None))
        .filter(Case.status != CaseStatus.CLOSED)
        .scalar() or 0
    )

    avg_svi = db.query(func.avg(Assessment.svi_score)).scalar() or 0.0

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
    cases_today = (
        db.query(func.count(Case.id))
        .filter(Case.created_at >= today_start)
        .scalar() or 0
    )

    # Risk distribution for chart
    risk_distribution = [
        {"category": risk.value, "count": risk_counts.get(risk.value, 0), "color": _risk_color(risk.value)}
        for risk in RiskCategory
    ]

    # Trend: cases per day for last 7 days
    recent_trend = []
    for days_ago in range(6, -1, -1):
        day = datetime.now(timezone.utc).date() - timedelta(days=days_ago)
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        count = (
            db.query(func.count(Case.id))
            .filter(Case.created_at >= day_start, Case.created_at < day_end)
            .scalar() or 0
        )
        recent_trend.append({"date": day.isoformat(), "cases": count})

    return DashboardStats(
        total_cases=total,
        critical_count=risk_counts.get("critical", 0),
        high_count=risk_counts.get("high", 0),
        moderate_count=risk_counts.get("moderate", 0),
        low_count=risk_counts.get("low", 0),
        unassigned_count=unassigned,
        avg_svi=round(avg_svi, 1),
        cases_today=cases_today,
        risk_distribution=risk_distribution,
        recent_trend=recent_trend,
    )


@router.get("/{case_id}", response_model=CaseDetail)
def get_case_detail(case_id: str, db: Session = Depends(get_db)):
    """
    Full case detail with all assessments, sub-scores, and triggered keywords.
    """
    case_obj = (
        db.query(Case)
        .options(joinedload(Case.assessments), joinedload(Case.assignee))
        .filter(Case.id == case_id)
        .first()
    )
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")

    # Audit: log this view
    audit = AuditLog(case_id=case_id, action="CASE_VIEWED")
    db.add(audit)
    db.commit()

    # Get recommendations for this case's risk level
    latest_assessment = case_obj.assessments[0] if case_obj.assessments else None
    recommendations = []
    if latest_assessment:
        from app.models.database import RecommendationRule
        rule = (
            db.query(RecommendationRule)
            .filter(RecommendationRule.risk_category == latest_assessment.risk_category)
            .first()
        )
        if rule:
            recommendations = rule.actions

    assessments_data = []
    for a in case_obj.assessments:
        assessments_data.append(AssessmentResultFromDB(a))

    return CaseDetail(
        id=case_obj.id,
        created_at=case_obj.created_at,
        channel=case_obj.channel.value if case_obj.channel else "chat",
        language_detected=case_obj.language_detected or "en",
        status=case_obj.status.value if hasattr(case_obj.status, 'value') else str(case_obj.status),
        svi_score=latest_assessment.svi_score if latest_assessment else None,
        risk_category=latest_assessment.risk_category.value if latest_assessment else None,
        assigned_to=case_obj.assigned_to,
        assignee_name=case_obj.assignee.full_name if case_obj.assignee else None,
        hard_override=latest_assessment.hard_override if latest_assessment else False,
        raw_text=case_obj.raw_text,
        transcript=case_obj.transcript,
        consent_given=case_obj.consent_given,
        consent_timestamp=case_obj.consent_timestamp,
        assessments=assessments_data,
        recommendations=recommendations,
    )


@router.patch("/{case_id}/status")
def update_case_status(
    case_id: str, update: CaseStatusUpdate, db: Session = Depends(get_db)
):
    """Update case status and/or assignment."""
    case_obj = db.query(Case).filter(Case.id == case_id).first()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found")

    old_status = case_obj.status
    case_obj.status = update.status
    if update.assigned_to is not None:
        case_obj.assigned_to = update.assigned_to

    audit = AuditLog(
        case_id=case_id,
        action="STATUS_CHANGED",
        details={
            "old_status": str(old_status),
            "new_status": update.status,
            "assigned_to": update.assigned_to,
        }
    )
    db.add(audit)
    db.commit()

    return {"message": "Case updated", "case_id": case_id, "new_status": update.status}


@router.get("/{case_id}/audit", response_model=list[AuditEntry])
def get_case_audit_log(case_id: str, db: Session = Depends(get_db)):
    """Full audit trail for a case."""
    entries = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case_id)
        .order_by(desc(AuditLog.timestamp))
        .all()
    )
    return [AuditEntry.model_validate(e) for e in entries]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def AssessmentResultFromDB(a: Assessment) -> dict:
    """Convert DB assessment to response dict."""
    from app.models.schemas import AssessmentResult
    return AssessmentResult(
        case_id=a.case_id,
        svi_score=a.svi_score,
        risk_category=a.risk_category.value,
        hard_override=a.hard_override,
        override_reason=a.override_reason,
        text_sentiment_score=a.text_sentiment_score,
        keyword_density_score=a.keyword_density_score,
        voice_prosody_score=a.voice_prosody_score,
        interaction_pattern_score=a.interaction_pattern_score,
        triggered_keywords=a.triggered_keywords or [],
        sub_score_details=a.sub_score_details or {},
    )


def _risk_color(risk: str) -> str:
    return {
        "low": "#22c55e",
        "moderate": "#f59e0b",
        "high": "#f97316",
        "critical": "#ef4444",
    }.get(risk, "#6b7280")
