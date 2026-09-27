"""Authentication and consent.

Complainants register pseudonymously: no name, no phone number, no email. A
staff account needs a password; a complainant does not get one, because a
password is a re-identification risk with no benefit to the victim. Their
session is the token itself.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import create_access_token, hash_password, verify_password
from config import CONSENT_VERSION, DISCLAIMER
from database import get_db
from models import ConsentRecord, User
from schemas import (
    ConsentOut,
    ConsentRequest,
    LoginRequest,
    RegisterOut,
    RegisterRequest,
    TokenOut,
    UserOut,
)
from security import get_current_user, record
from utils import new_pseudonym

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

STAFF_ROLES = ("counsellor", "district_admin", "state_admin", "law_enforcement")


@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Create a pseudonymous session user, or a staff account with a password.

    Returns a session token. This is the *only* way a complainant ever gets
    credentials: they have no password, so `/api/auth/login` is structurally
    unavailable to them. Staff also get a token here as a convenience, but they
    can additionally log in again later with their password.
    """
    is_staff = payload.role in STAFF_ROLES
    if is_staff and not payload.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A password is required for the '{payload.role}' role",
        )
    if not is_staff and payload.password:
        # Complainants never set a password: there is no identity to protect it.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Complainant accounts are password-less by design. Do not set a password.",
        )

    user = User(
        role=payload.role,
        pseudonym_id=new_pseudonym(),
        language_pref=payload.language_pref,
        district=payload.district,
        display_name=payload.display_name if is_staff else None,
        password_hash=hash_password(payload.password) if payload.password else None,
    )
    db.add(user)
    db.flush()
    record(db, user, "register", "user", user.id, {"role": user.role})
    db.commit()
    db.refresh(user)
    return {
        "access_token": create_access_token(user.id, user.role),
        "token_type": "bearer",
        "role": user.role,
        "pseudonym_id": user.pseudonym_id,
        "disclaimer": DISCLAIMER,
        "user": user,
    }


@router.post("/token", response_model=TokenOut)
@router.post("/login", response_model=TokenOut, include_in_schema=False)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    user = (
        db.query(User)
        .filter(User.pseudonym_id == payload.pseudonym_id, User.is_active.is_(True))
        .first()
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user.id, user.role)
    record(db, user, "login", "user", user.id)
    db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "pseudonym_id": user.pseudonym_id,
        "disclaimer": DISCLAIMER,
    }


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


# --------------------------------------------------------------------------
# Consent
# --------------------------------------------------------------------------

consent_router = APIRouter(prefix="/api/consent", tags=["consent"])


@consent_router.post("", response_model=ConsentOut, status_code=status.HTTP_201_CREATED)
def give_consent(
    payload: ConsentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsentRecord:
    """Capture consent. A case cannot be opened without a current consent row."""
    row = ConsentRecord(
        user_id=user.id,
        version=payload.version,
        channel=payload.channel,
    )
    db.add(row)
    db.flush()
    record(db, user, "consent_granted", "consent", row.id, {"version": row.version, "channel": row.channel})
    db.commit()
    db.refresh(row)
    return row


@consent_router.get("/status", response_model=ConsentOut)
def consent_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ConsentRecord:
    row = (
        db.query(ConsentRecord)
        .filter(ConsentRecord.user_id == user.id, ConsentRecord.withdrawn_at.is_(None))
        .order_by(ConsentRecord.granted_at.desc())
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active consent on record. The portal must show the consent screen for version {CONSENT_VERSION}.",
        )
    return row


@consent_router.delete("/status", response_model=ConsentOut)
def withdraw_consent(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConsentRecord:
    """Withdraw consent. Stops new analysis; retention of existing records is
    a legal question, so we mark the withdrawal rather than silently deleting."""
    from utils import utcnow

    row = (
        db.query(ConsentRecord)
        .filter(ConsentRecord.user_id == user.id, ConsentRecord.withdrawn_at.is_(None))
        .order_by(ConsentRecord.granted_at.desc())
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active consent to withdraw")
    row.withdrawn_at = utcnow()
    record(db, user, "consent_withdrawn", "consent", row.id)
    db.commit()
    db.refresh(row)
    return row
