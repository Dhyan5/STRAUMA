"""Small shared helpers."""

from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any, Optional


def utcnow() -> dt.datetime:
    """Timezone-naive UTC now (SQLite friendly, no deprecation warnings)."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def new_case_ref() -> str:
    """Pseudonymous, non-sequential case reference shown to staff.

    The integer primary key stays internal; this is the only identifier that
    appears on screen, on paper forms, and in notifications.
    """
    return "NHAA-" + uuid.uuid4().hex[:6].upper()


def new_pseudonym() -> str:
    return "anon-" + uuid.uuid4().hex[:8]


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads(value: Optional[str], default: Any = None) -> Any:
    if not value:
        return default if default is not None else []
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default if default is not None else []


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))
