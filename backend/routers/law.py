"""Restricted law-enforcement view.

Design constraints, all deliberate:

* A case appears here **only** after a staff member has recorded a
  `police_liaison` action on it. There is no implicit "Critical means police
  see it" shortcut, because over-sharing with a third party is itself a harm.
* The projection is minimal: a case reference, the district, the reason a
  human made the referral, and where to send the person. No message text, no
  transcript, no audio, no risk score, no SVI breakdown, no identity.
* Every list and detail read writes an audit row, so the disclosure is visible
  to an administrator afterwards.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import DISCLAIMER
from database import get_db
from engine import ingest
from models import Case, CaseAction, User
from schemas import LawEnforcementItem
from security import record, require_law_enforcement
from utils import utcnow

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/law-enforcement", tags=["law-enforcement"])

POLICE_CONTACT = "District nodal officer, NHAA coordination cell"


def _referred_cases(db: Session) -> List[tuple]:
    """Cases with a recorded police-liaison action, newest referral first."""
    referrals = (
        db.query(CaseAction)
        .filter(CaseAction.action == "police_liaison")
        .order_by(CaseAction.created_at.desc())
        .all()
    )
    seen: set = set()
    out: List[tuple] = []
    for referral in referrals:
        if referral.case_id in seen:
            continue
        seen.add(referral.case_id)
        case = db.get(Case, referral.case_id)
        if case is None or case.status in ("resolved", "closed"):
            continue
        out.append((case, referral))
    return out


@router.get("/cases", response_model=List[LawEnforcementItem])
def referred_cases(
    user: User = Depends(require_law_enforcement),
    db: Session = Depends(get_db),
) -> List[LawEnforcementItem]:
    record(db, user, "view_law_enforcement_cases", "case", None)
    db.commit()
    return [_project(db, case, referral) for case, referral in _referred_cases(db)]


@router.get("/cases/{case_ref}", response_model=LawEnforcementItem)
def referred_case(
    case_ref: str,
    user: User = Depends(require_law_enforcement),
    db: Session = Depends(get_db),
) -> LawEnforcementItem:
    case = db.query(Case).filter(Case.ref == case_ref).first()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such case reference")
    referral = (
        db.query(CaseAction)
        .filter(CaseAction.case_id == case.id, CaseAction.action == "police_liaison")
        .order_by(CaseAction.created_at.desc())
        .first()
    )
    if referral is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No police-liaison referral is on record for this case.",
        )
    record(db, user, "view_law_enforcement_case", "case", case.ref)
    db.commit()
    return _project(db, case, referral)


def _project(db: Session, case: Case, referral: CaseAction) -> LawEnforcementItem:
    svi = ingest.current_svi(db, case.id)
    # The reason shown is the human referral note, not the model's internal
    # override text: the police view is a human-to-human handover.
    return LawEnforcementItem(
        case_ref=case.ref,
        district=case.district,
        category=svi.category if svi else "Low",
        override_reason=(referral.note or "Police liaison referral recorded by staff."),
        immediate_action_required=(
            "Contact the district nodal officer for assessment of mandatory-reporting duties "
            "and, where applicable, an immediate response."
        ),
        contact_via=POLICE_CONTACT,
        recorded_by_role=referral.actor.role if referral.actor else None,
        recorded_at=referral.created_at,
        disclaimer=DISCLAIMER,
    )


@router.get("/policy")
def policy(user: User = Depends(require_law_enforcement)) -> Dict[str, Any]:
    """State the disclosure rules in the UI, not only in a design document."""
    return {
        "visibility_rule": (
            "A case is visible here only after a counsellor, district admin or state admin "
            "has recorded an explicit police-liaison referral on it."
        ),
        "excluded_fields": [
            "raw message text",
            "transcripts",
            "audio recordings",
            "SVI / composite score and sub-scores",
            "complainant identity or contact details",
            "psychological or medical detail beyond the referral reason",
        ],
        "audit_note": "Every read from this view is written to the audit log with your user id.",
        "generated_at": utcnow().isoformat(),
        "disclaimer": DISCLAIMER,
    }
