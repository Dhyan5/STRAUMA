"""FastAPI dependencies for authentication and server-side role enforcement.

Guardrail #1 from the specification: RBAC is enforced here, on the server, on
every route - the dashboard UI hiding a menu item is presentation only and is
never the control.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Iterable, Optional, Sequence

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from auth import decode_access_token
from config import ROLES
from database import get_db
from models import AuditLog, Case, User
from utils import dumps, utcnow

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=True)

#: Pseudonymous case id prefix used for audit target ids.
CASE_TARGET = "case"


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(token)
    if not payload or payload.get("typ") != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session subject")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account unavailable")
    # The role claim is a hint; the database is the source of truth.
    return user


def require_roles(*allowed: str) -> Callable[..., User]:
    """Dependency factory: only the listed roles may call the route."""
    allowed_set = set(allowed)

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not permitted to access this resource",
            )
        return user

    return _guard


require_staff = require_roles("counsellor", "district_admin", "state_admin")
require_admin = require_roles("district_admin", "state_admin")
require_counsellor = require_roles("counsellor", "district_admin", "state_admin")
require_law_enforcement = require_roles("law_enforcement")


def record(
    db: Session,
    actor: Optional[User],
    action: str,
    target_type: str,
    target_id: Optional[Any],
    detail: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Write an audit row. Called from every mutating and every case-reading
    endpoint - a case view is itself a disclosure event under DPDP Act 2023."""
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_role=actor.role if actor else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=dumps(detail) if detail else None,
    )
    db.add(entry)
    return entry


def can_access_case(user: User, case: Case) -> bool:
    """Ownership + role visibility rules for a single case.

    * complainant      -> own cases only
    * law_enforcement  -> only cases the rules engine explicitly flagged for
      police intervention (enforced further in the router)
    * staff            -> all, subject to district scoping
    """
    if user.role == "complainant":
        return case.user_id == user.id
    if user.role == "law_enforcement":
        return False
    if user.role == "district_admin" and user.district:
        return case.district == user.district
    return True


def enforce_case_access(user: User, case: Case) -> None:
    if not can_access_case(user, case):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorised to view this case record",
        )


def visible_case_ids(db: Session, user: User) -> Optional[Sequence[int]]:
    """Case ids this user may see, or None meaning 'no pre-filter'."""
    query = db.query(Case.id)
    if user.role == "complainant":
        return [row[0] for row in query.filter(Case.user_id == user.id).all()]
    if user.role == "district_admin" and user.district:
        return [row[0] for row in query.filter(Case.district == user.district).all()]
    return None


def client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def audit_json_safe(value: Any) -> str:
    try:
        json.dumps(value)
        return dumps(value)
    except TypeError:
        return json.dumps(str(value))


__all__ = [
    "get_current_user",
    "require_roles",
    "require_staff",
    "require_admin",
    "require_counsellor",
    "require_law_enforcement",
    "record",
    "can_access_case",
    "enforce_case_access",
    "visible_case_ids",
    "ROLES",
    "utcnow",
]
