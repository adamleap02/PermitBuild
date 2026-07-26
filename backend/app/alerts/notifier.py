"""
Alert delivery interface -- STUBBED, no real email/SMS provider wired
up (that would require a paid or signup-gated third-party service; see
BLOCKERS.md for free-tier options to integrate later).

Every "send" here just formats the message and writes an
AlertNotificationLog row with status="stubbed" -- a durable, inspectable
record of exactly what *would* have gone out, to whom, and why (which
permits matched), without actually dispatching anything externally.

Swapping in a real provider later (e.g. Resend/SendGrid free tier for
email, Twilio trial for SMS) means writing a new class that implements
NotificationChannel.send() and calling real API in there instead of
just logging -- the rest of app/routers/alerts.py doesn't change.
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Alert, AlertNotificationLog, Permit

logger = logging.getLogger(__name__)


@dataclass
class NotificationResult:
    status: str  # "stubbed" | "sent" | "failed"
    log_id: int
    detail: str


class NotificationChannel(abc.ABC):
    """Abstract interface a real email/SMS provider would implement."""

    channel_name: str = "unknown"

    @abc.abstractmethod
    def send(self, db: Session, alert: Alert, permits: list[Permit]) -> NotificationResult:
        raise NotImplementedError


def _format_message(alert: Alert, permits: list[Permit]) -> tuple[str, str]:
    saved_search = alert.saved_search
    subject = f"[Construction Intel] {len(permits)} new permit(s) matching '{saved_search.name}'"
    lines = [
        f"Saved search: {saved_search.name}",
        f"Filters: {saved_search.filters}",
        f"{len(permits)} matching permit(s):",
        "",
    ]
    for p in permits[:25]:
        lines.append(
            f"- #{p.permit_number} ({p.permit_type or 'unknown type'}) at "
            f"{p.property_address or 'unknown address'} -- "
            f"${(p.valuation or p.estimated_cost or 0):,.0f}"
        )
    if len(permits) > 25:
        lines.append(f"... and {len(permits) - 25} more.")
    body = "\n".join(lines)
    return subject, body


class _StubChannel(NotificationChannel):
    """Shared stub behavior for both email and SMS -- logs + persists an
    AlertNotificationLog row instead of actually sending anything."""

    def send(self, db: Session, alert: Alert, permits: list[Permit]) -> NotificationResult:
        subject, body = _format_message(alert, permits)
        logger.info(
            "[STUB %s] Would notify %s: %s (%d permit(s))",
            self.channel_name.upper(),
            alert.recipient,
            subject,
            len(permits),
        )
        log_row = AlertNotificationLog(
            alert_id=alert.id,
            channel=self.channel_name,
            recipient=alert.recipient,
            subject=subject if self.channel_name == "email" else None,
            body=body,
            matched_permit_ids=[p.id for p in permits],
            status="stubbed",
        )
        db.add(log_row)
        db.flush()
        return NotificationResult(
            status="stubbed",
            log_id=log_row.id,
            detail=f"No real {self.channel_name} provider configured -- logged only. See BLOCKERS.md.",
        )


class StubEmailChannel(_StubChannel):
    channel_name = "email"


class StubSMSChannel(_StubChannel):
    channel_name = "sms"


_CHANNELS: dict[str, NotificationChannel] = {
    "email": StubEmailChannel(),
    "sms": StubSMSChannel(),
}


def get_channel(channel_name: str) -> NotificationChannel:
    channel = _CHANNELS.get(channel_name)
    if channel is None:
        raise ValueError(f"Unknown alert channel: {channel_name!r}")
    return channel
