"""Notification providers.

The prototype ships a **mock** provider. It never opens a socket; it only
marks outbox rows as `sent` and records what would have been transmitted. That
is the correct behaviour for a demo *and* for any environment where nobody has
procured a government-approved SMS gateway, which is the honest state of this
project today.

Swapping in a real gateway means implementing `NotificationProvider.send` and
registering it in `provider()`. Nothing in the escalation path changes: the
engine has already written the outbox rows, so a real provider can drain the
queue later without re-running any scoring.
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from config import DISCLAIMER, settings
from models import AuditLog, NotificationOutbox
from utils import loads, utcnow

log = logging.getLogger(__name__)

#: Channels the prototype knows about, with what each would be used for.
CHANNEL_NOTES: Dict[str, str] = {
    "sms": "Short plain-text alert to the district nodal officer.",
    "email": "Structured alert with the case reference and recommended actions.",
    "whatsapp": "Low-bandwidth alert for field staff.",
    "dashboard_alert": "In-app banner on the counsellor queue. No external send.",
}


@dataclass
class SendResult:
    channel: str
    status: str
    detail: str


class NotificationProvider(abc.ABC):
    name = "abstract"

    @abc.abstractmethod
    def send(self, channel: str, recipient: Optional[str], payload: Dict[str, Any]) -> SendResult:
        ...


class MockProvider(NotificationProvider):
    """Records intent only. Never transmits anything."""

    name = "mock"

    def send(self, channel: str, recipient: Optional[str], payload: Dict[str, Any]) -> SendResult:
        log.info(
            "[mock-notification] channel=%s recipient=%s case=%s actions=%s",
            channel,
            recipient or "-",
            payload.get("case_ref"),
            payload.get("recommended_actions"),
        )
        return SendResult(
            channel=channel,
            status="logged",
            detail="Mock provider: payload recorded in notification_outbox, nothing transmitted.",
        )


_PROVIDER: Optional[NotificationProvider] = None


def provider() -> NotificationProvider:
    global _PROVIDER
    if _PROVIDER is None:
        if settings.notification_provider == "mock":
            _PROVIDER = MockProvider()
        else:
            # Unknown provider name: fall back to mock rather than pretending.
            log.warning(
                "NOTIFICATION_PROVIDER='%s' is not implemented; using the mock provider.",
                settings.notification_provider,
            )
            _PROVIDER = MockProvider()
    return _PROVIDER


def drain_outbox(db: Session, limit: int = 50) -> List[Dict[str, Any]]:
    """Process pending outbox rows. In the demo this just logs and marks sent."""
    impl = provider()
    rows = (
        db.query(NotificationOutbox)
        .filter(NotificationOutbox.status == "pending")
        .order_by(NotificationOutbox.created_at.asc())
        .limit(limit)
        .all()
    )
    processed: List[Dict[str, Any]] = []
    for row in rows:
        payload = loads(row.payload, {})
        result = impl.send(row.channel, row.recipient, payload)
        row.status = "sent" if result.status in ("sent", "logged") else "failed"
        row.sent_at = utcnow()
        row.attempts += 1
        processed.append(
            {
                "id": row.id,
                "channel": row.channel,
                "status": row.status,
                "provider": row.provider,
                "detail": result.detail,
            }
        )
    if processed:
        db.add(
            AuditLog(
                actor_id=None,
                actor_role="system",
                action="outbox_drained",
                target_type="notification",
                target_id=str(len(processed)),
                detail=f"provider={impl.name}",
            )
        )
        db.commit()
    return processed


def preview(row: NotificationOutbox) -> Dict[str, Any]:
    return {
        "id": row.id,
        "case_id": row.case_id,
        "channel": row.channel,
        "channel_note": CHANNEL_NOTES.get(row.channel, "Unrecognised channel."),
        "recipient": row.recipient,
        "status": row.status,
        "provider": row.provider,
        "attempts": row.attempts,
        "created_at": row.created_at.isoformat(),
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "payload": loads(row.payload, {}),
        "disclaimer": DISCLAIMER,
    }


def provider_status() -> Dict[str, Any]:
    impl = provider()
    return {
        "provider": impl.name,
        "transmits_anything": impl.name != "mock",
        "channels": CHANNEL_NOTES,
        "note": (
            "The prototype uses a mock provider by design. No SMS, email or WhatsApp "
            "message leaves this process. A real deployment needs an empanelled gateway."
        ),
    }


_ = Sequence
