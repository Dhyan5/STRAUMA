"""
Recommendation router — maps risk category → suggested actions.
Rule-table based, editable by admins without code deploy.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.database import RecommendationRule, RiskCategory, AuditLog
from app.models.schemas import RecommendationRuleSchema, RecommendationResponse

router = APIRouter(prefix="/recommend", tags=["Recommendations"])


@router.get("/{risk_category}", response_model=RecommendationResponse)
def get_recommendation(risk_category: str, db: Session = Depends(get_db)):
    """Get recommended actions for a risk category."""
    try:
        risk_enum = RiskCategory(risk_category)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid risk category. Must be one of: {[r.value for r in RiskCategory]}"
        )

    rule = db.query(RecommendationRule).filter(
        RecommendationRule.risk_category == risk_enum
    ).first()

    if not rule:
        raise HTTPException(status_code=404, detail="No rule found for this risk category")

    return RecommendationResponse(
        risk_category=risk_category,
        actions=rule.actions,
        response_window=rule.response_window,
        notify_roles=rule.notify_roles,
    )


@router.get("/", response_model=list[RecommendationResponse])
def get_all_recommendations(db: Session = Depends(get_db)):
    """Get all recommendation rules."""
    rules = db.query(RecommendationRule).all()
    return [
        RecommendationResponse(
            risk_category=r.risk_category.value,
            actions=r.actions,
            response_window=r.response_window,
            notify_roles=r.notify_roles,
        )
        for r in rules
    ]


@router.put("/{risk_category}", response_model=RecommendationResponse)
def update_recommendation(
    risk_category: str,
    update: RecommendationRuleSchema,
    db: Session = Depends(get_db),
):
    """
    Update recommendation rule — designed to be editable by admins
    without a code deploy, as these need tuning by mental health professionals.
    """
    try:
        risk_enum = RiskCategory(risk_category)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid risk category")

    rule = db.query(RecommendationRule).filter(
        RecommendationRule.risk_category == risk_enum
    ).first()

    if not rule:
        raise HTTPException(status_code=404, detail="No rule found")

    rule.actions = update.actions
    rule.response_window = update.response_window
    rule.notify_roles = update.notify_roles

    audit = AuditLog(
        action="RECOMMENDATION_UPDATED",
        details={
            "risk_category": risk_category,
            "new_actions": update.actions,
        }
    )
    db.add(audit)
    db.commit()

    return RecommendationResponse(
        risk_category=risk_category,
        actions=rule.actions,
        response_window=rule.response_window,
        notify_roles=rule.notify_roles,
    )
