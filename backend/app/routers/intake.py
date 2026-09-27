"""
Intake router — accepts victim text/audio, creates case records.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.database import Case, ChannelSource, AuditLog
from app.models.schemas import IntakeRequest, IntakeResponse
from app.services.language_detection import detect_language

router = APIRouter(prefix="/intake", tags=["Intake"])


@router.post("/", response_model=IntakeResponse)
def create_case(req: IntakeRequest, db: Session = Depends(get_db)):
    """
    Create a new case from victim input.
    Requires explicit consent before processing.
    """
    # Consent gate — no processing without it
    if not req.consent_given:
        raise HTTPException(
            status_code=400,
            detail="Consent is required before any data can be processed. "
                   "Please review the consent information and try again."
        )

    # Validate channel
    try:
        channel = ChannelSource(req.channel)
    except ValueError:
        channel = ChannelSource.CHAT

    # Auto-detect language
    lang = req.language if req.language else detect_language(req.text or "")

    # Create case record
    case = Case(
        channel=channel,
        language_detected=lang,
        consent_given=True,
        consent_timestamp=datetime.now(timezone.utc),
        raw_text=req.text,
        status="new",
    )
    db.add(case)
    db.flush()

    # Audit log
    audit = AuditLog(
        case_id=case.id,
        action="CASE_CREATED",
        details={
            "channel": req.channel,
            "language_detected": lang,
            "text_length": len(req.text) if req.text else 0,
        }
    )
    db.add(audit)
    db.commit()
    db.refresh(case)

    return IntakeResponse(
        case_id=case.id,
        message="Case created successfully. Assessment pending.",
        language_detected=lang,
    )
