"""
Assessment router — runs the SVI scoring pipeline on a case.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.database import Case, Assessment, RiskCategory, AuditLog
from app.models.schemas import AssessRequest, AssessmentResult
from app.services.scoring_engine import compute_svi

router = APIRouter(prefix="/assess", tags=["Assessment"])


@router.post("/", response_model=AssessmentResult)
def assess_case(req: AssessRequest, db: Session = Depends(get_db)):
    """
    Run the SVI scoring pipeline on a case.
    Returns full sub-scores, triggered keywords, and risk category.
    """
    case = db.query(Case).filter(Case.id == req.case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if not case.consent_given:
        raise HTTPException(
            status_code=403,
            detail="Cannot assess case without victim consent"
        )

    # Get text to analyze (raw text or transcript from audio)
    text = case.raw_text or case.transcript or ""
    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="No text content available for assessment"
        )

    # Run the scoring pipeline
    result = compute_svi(
        text=text,
        language=case.language_detected or "en",
        audio_features=None,  # Would come from voice pipeline
        interaction_metadata=None,
    )

    # Map string risk to enum
    risk_enum = RiskCategory(result.risk_category)

    # Persist assessment
    assessment = Assessment(
        case_id=case.id,
        text_sentiment_score=result.text_sentiment_score,
        keyword_density_score=result.keyword_density_score,
        voice_prosody_score=result.voice_prosody_score,
        interaction_pattern_score=result.interaction_pattern_score,
        svi_score=result.svi_score,
        risk_category=risk_enum,
        hard_override=result.hard_override,
        override_reason=result.override_reason,
        triggered_keywords=[kw.to_dict() for kw in result.triggered_keywords],
        sub_score_details=result.sub_score_details,
    )
    db.add(assessment)

    # Update case status
    case.status = "assigned" if risk_enum in (RiskCategory.HIGH, RiskCategory.CRITICAL) else "new"

    # Audit log
    audit = AuditLog(
        case_id=case.id,
        action="ASSESSMENT_COMPLETED",
        details={
            "svi_score": result.svi_score,
            "risk_category": result.risk_category,
            "hard_override": result.hard_override,
            "keyword_count": len(result.triggered_keywords),
        }
    )
    db.add(audit)
    db.commit()

    return AssessmentResult(
        case_id=case.id,
        svi_score=result.svi_score,
        risk_category=result.risk_category,
        hard_override=result.hard_override,
        override_reason=result.override_reason,
        text_sentiment_score=result.text_sentiment_score,
        keyword_density_score=result.keyword_density_score,
        voice_prosody_score=result.voice_prosody_score,
        interaction_pattern_score=result.interaction_pattern_score,
        triggered_keywords=[kw.to_dict() for kw in result.triggered_keywords],
        sub_score_details=result.sub_score_details,
    )


@router.post("/quick")
def quick_assess(text: str, language: str = "auto", db: Session = Depends(get_db)):
    """
    Quick assessment without creating a case — for demo/testing.
    Runs the pipeline on raw text and returns results immediately.
    """
    from app.services.language_detection import detect_language

    if language == "auto":
        language = detect_language(text)

    result = compute_svi(text=text, language=language)

    return {
        "svi_score": result.svi_score,
        "risk_category": result.risk_category,
        "hard_override": result.hard_override,
        "override_reason": result.override_reason,
        "text_sentiment_score": result.text_sentiment_score,
        "keyword_density_score": result.keyword_density_score,
        "interaction_pattern_score": result.interaction_pattern_score,
        "triggered_keywords": [kw.to_dict() for kw in result.triggered_keywords],
        "language_detected": language,
    }
