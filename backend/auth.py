"""Password hashing and JWT issuance.

Threat model notes:
* Complainant sessions are token-based and pseudonymous - there is no identity
  to steal unless the victim explicitly opted into identity disclosure.
* Staff tokens carry the role claim so that RBAC can be enforced without a
  database round-trip on every request, but `security.require_roles` still
  re-reads the user row, so a deactivated account loses access immediately.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
from typing import Any, Dict, Optional

import bcrypt
from jose import JWTError, jwt

from config import settings
from utils import utcnow

ALGORITHM = settings.jwt_algorithm
SECRET_KEY = settings.jwt_secret

#: bcrypt truncates silently at 72 bytes (or raises, depending on version).
#: We pre-hash with SHA-256 and base64, which is 44 bytes and length-stable, so
#: a long passphrase is never truncated and passlib's bcrypt 4.x
#: incompatibility is sidestepped entirely.
#:
#: NOTE: SHA-256 pre-hashing removes bcrypt's own per-algorithm salting limits
#: and means a very long passphrase has a *weaker* effective work factor than
#: a short one. For government staff accounts, prefer an identity provider over
#: local passwords; see the README's production requirements.
_BCRYPT_ROUNDS = 12
TOKEN_TYPE = "bearer"


def _prehash(plain: str) -> bytes:
    digest = hashlib.sha256(plain.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(_prehash(plain), salt).decode("utf-8")


def verify_password(plain: str, hashed: Optional[str]) -> bool:
    if not hashed:
        return False
    try:
        return hmac.compare_digest(bcrypt.hashpw(_prehash(plain), hashed.encode("utf-8")), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: Any, role: str, extra: Optional[Dict[str, Any]] = None) -> str:
    now = utcnow()
    expire = now + dt.timedelta(minutes=settings.access_token_expire_minutes)
    payload: Dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "typ": TOKEN_TYPE,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
