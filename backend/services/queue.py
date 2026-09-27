"""Queue / session store with a Redis backend and an in-process fallback.

Redis is used for two things: the live counsellor queue ordering, and
transient intake session state. If Redis is unavailable the module degrades to
an in-process dictionary, logs a single warning, and the prototype stays fully
functional - a demo that refuses to start because a cache is missing is a worse
prototype.

Session state is intentionally *not* persisted to the relational DB: it holds
in-flight intake answers before consent is finalised.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from config import settings

log = logging.getLogger(__name__)

_lock = threading.Lock()
_redis = None
_redis_checked = False
_memory: Dict[str, Any] = {}
_fallback_warned = False


def _client():
    global _redis, _redis_checked
    if _redis_checked:
        return _redis
    with _lock:
        if _redis_checked:
            return _redis
        _redis_checked = True
        if not settings.redis_url:
            _log_fallback("REDIS_URL is not set")
            return None
        try:
            import redis  # type: ignore

            client = redis.from_url(settings.redis_url, socket_connect_timeout=1.0, socket_timeout=1.0)
            client.ping()
            _redis = client
            log.info("Queue backend: redis at %s", settings.redis_url)
        except Exception as exc:  # noqa: BLE001
            _log_fallback(f"{type(exc).__name__}: {exc}")
            _redis = None
    return _redis


def _log_fallback(reason: str) -> None:
    global _fallback_warned
    if not _fallback_warned:
        log.warning(
            "Queue backend: falling back to an in-process store (%s). The prototype "
            "is fully functional; Redis is only needed for multi-worker deployments.",
            reason,
        )
        _fallback_warned = True


def backend_name() -> str:
    return "redis" if _client() is not None else "in-memory"


# --------------------------------------------------------------------------
# Intake session state (ephemeral)
# --------------------------------------------------------------------------

def set_session(token: str, data: Dict[str, Any], ttl_seconds: int = 3600) -> None:
    client = _client()
    payload = json.dumps(data, ensure_ascii=False)
    if client is not None:
        try:
            client.setex(f"intake:{token}", ttl_seconds, payload)
            return
        except Exception as exc:  # noqa: BLE001
            _log_fallback(f"redis write failed: {type(exc).__name__}")
    with _lock:
        _memory[f"intake:{token}"] = (time.time() + ttl_seconds, payload)


def get_session(token: str) -> Optional[Dict[str, Any]]:
    client = _client()
    if client is not None:
        try:
            raw = client.get(f"intake:{token}")
            return json.loads(raw) if raw else None
        except Exception as exc:  # noqa: BLE001
            _log_fallback(f"redis read failed: {type(exc).__name__}")
    with _lock:
        entry = _memory.get(f"intake:{token}")
        if not entry:
            return None
        expires_at, payload = entry
        if expires_at < time.time():
            _memory.pop(f"intake:{token}", None)
            return None
        return json.loads(payload)


def drop_session(token: str) -> None:
    client = _client()
    if client is not None:
        try:
            client.delete(f"intake:{token}")
        except Exception:  # noqa: BLE001
            pass
    with _lock:
        _memory.pop(f"intake:{token}", None)


# --------------------------------------------------------------------------
# Live queue ordering
# --------------------------------------------------------------------------
# Priority is a plain integer so the ordering rule is inspectable from the
# Redis CLI during a demo: lower sorts first in the counsellor queue.

def priority_for(category: str, sla_state: str, critical_override: bool) -> int:
    base = {"Critical": 0, "High": 1000, "Moderate": 2000, "Low": 3000}.get(category, 4000)
    if critical_override:
        base -= 500          # overrides are always hoisted above their band
    if sla_state == "breached":
        base -= 200
    elif sla_state == "due_soon":
        base -= 100
    return max(0, base)


def publish_queue_entry(case_ref: str, category: str, sla_state_value: str, critical_override: bool) -> int:
    priority = priority_for(category, sla_state_value, critical_override)
    client = _client()
    if client is not None:
        try:
            client.zadd("queue:counsellor", {case_ref: priority})
            return priority
        except Exception:  # noqa: BLE001
            pass
    with _lock:
        _memory[f"queue:{case_ref}"] = priority
    return priority


def remove_queue_entry(case_ref: str) -> None:
    client = _client()
    if client is not None:
        try:
            client.zrem("queue:counsellor", case_ref)
        except Exception:  # noqa: BLE001
            pass
    with _lock:
        _memory.pop(f"queue:{case_ref}", None)


def read_queue() -> List[Dict[str, Any]]:
    client = _client()
    if client is not None:
        try:
            rows = client.zrange("queue:counsellor", 0, -1, withscores=True)
            return [{"case_ref": str(name), "priority": int(score)} for name, score in rows]
        except Exception:  # noqa: BLE001
            pass
    with _lock:
        return [
            {"case_ref": key.split(":", 1)[1], "priority": int(value)}
            for key, value in _memory.items()
            if key.startswith("queue:")
        ]


def status() -> Dict[str, Any]:
    return {
        "backend": backend_name(),
        "redis_url_configured": bool(settings.redis_url),
        "is_fallback": backend_name() != "redis",
        "note": (
            "Redis is optional for the demo. When absent, the in-process store keeps "
            "the queue ordered but does not survive a restart or span multiple workers."
        ),
    }
