"""
Orchestration for the FOIA-reply email-intake pipeline.

Ties the pieces together:
  1. search Gmail for replies from the known FOIA target agencies
  2. for each new attachment (and inline data table), parse it into
     normalized permit dicts
  3. ingest each record through the SAME upsert_permit + PermitVersion
     path every API connector uses (app/ingest.py) -- NOT a parallel path
  4. record every processed attachment in ProcessedEmailAttachment so
     re-running the poll never re-ingests the same data

The whole thing is idempotent and safe to run on a schedule: already-seen
(message_id, attachment_id) pairs are skipped, and a failure on one
attachment is contained (rolled back, logged, counted) without poisoning
the rest of the run.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.connectors.geocoder import CensusGeocoder
from app.foia_intake.gmail_client import GmailClient, build_foia_search_query
from app.foia_intake.parser import ParseResult, parse_attachment, parse_email_body
from app.foia_intake.targets import FoiaTarget, find_target_for_sender, targets_with_email
from app.ingest import upsert_permit
from app.models import Jurisdiction, ProcessedEmailAttachment, SourceSystem

logger = logging.getLogger(__name__)

BODY_PART_ID = "body"  # sentinel attachment_id for an inline (email-body) data table


@dataclass
class IntakeStats:
    messages_seen: int = 0
    attachments_processed: int = 0
    attachments_skipped: int = 0  # already processed on a prior run
    records_created: int = 0
    records_updated: int = 0
    records_unchanged: int = 0
    records_flagged: int = 0
    errors: int = 0
    touched_permit_ids: list[int] = field(default_factory=list)
    per_attachment: list[dict] = field(default_factory=list)  # human-readable log entries

    def summary(self) -> str:
        return (
            f"messages={self.messages_seen} attachments={self.attachments_processed} "
            f"(skipped {self.attachments_skipped}) created={self.records_created} "
            f"updated={self.records_updated} unchanged={self.records_unchanged} "
            f"flagged_for_review={self.records_flagged} errors={self.errors}"
        )


def get_or_create_foia_jurisdiction(db: Session, target: FoiaTarget) -> Jurisdiction:
    existing = (
        db.query(Jurisdiction)
        .filter(Jurisdiction.name == target.jurisdiction_name, Jurisdiction.state == target.state)
        .one_or_none()
    )
    if existing:
        return existing
    jurisdiction = Jurisdiction(
        name=target.jurisdiction_name,
        state=target.state,
        level=target.level,
        timezone=target.timezone,
        source_system=SourceSystem.FOIA_EMAIL,
        source_config=target.source_config(),
    )
    db.add(jurisdiction)
    db.commit()
    db.refresh(jurisdiction)
    return jurisdiction


def _already_processed(db: Session, message_id: str, attachment_id: str) -> bool:
    return (
        db.query(ProcessedEmailAttachment)
        .filter(
            ProcessedEmailAttachment.message_id == message_id,
            ProcessedEmailAttachment.attachment_id == attachment_id,
        )
        .first()
        is not None
    )


def _ingest_records(
    db: Session,
    jurisdiction: Jurisdiction,
    result: ParseResult,
    geocoder: Optional[CensusGeocoder],
    enrich: bool,
    stats: IntakeStats,
) -> dict:
    """Upsert every parsed record; returns per-attachment counts."""
    counts = {"created": 0, "updated": 0, "unchanged": 0, "flagged": 0, "errors": 0}
    for normalized in result.records:
        try:
            outcome, permit_id = upsert_permit(db, jurisdiction, normalized, geocoder=geocoder, enrich=enrich)
            if outcome == "created":
                counts["created"] += 1
                stats.touched_permit_ids.append(permit_id)
            elif outcome == "updated":
                counts["updated"] += 1
                stats.touched_permit_ids.append(permit_id)
            else:
                counts["unchanged"] += 1
            if normalized.get("needs_review"):
                counts["flagged"] += 1
        except Exception:
            # Mirror app/ingest.py's per-record safety: roll back so one bad
            # row can't poison the rest of the session, log, and count it.
            logger.exception("FOIA intake: failed to upsert permit %s", normalized.get("permit_number"))
            db.rollback()
            counts["errors"] += 1
    return counts


def _record_processed(
    db: Session,
    message_id: str,
    attachment_id: str,
    target: Optional[FoiaTarget],
    from_address: str,
    filename: Optional[str],
    result: ParseResult,
    counts: dict,
) -> None:
    db.add(
        ProcessedEmailAttachment(
            message_id=message_id,
            attachment_id=attachment_id,
            target_key=target.key if target else None,
            from_address=from_address,
            filename=filename,
            status=("error" if counts.get("errors") else result.status),
            note=(result.note or None),
            records_created=counts.get("created", 0),
            records_updated=counts.get("updated", 0),
            records_unchanged=counts.get("unchanged", 0),
            records_flagged=counts.get("flagged", 0),
        )
    )
    db.commit()


def poll_and_ingest(
    db: Session,
    client: Optional[GmailClient] = None,
    max_messages: int = 100,
    geocode_missing: bool = True,
    enrich: bool = True,
) -> IntakeStats:
    """
    Poll Gmail for FOIA replies and ingest any new attachments/data tables.

    Safe to run repeatedly; anything already recorded in
    ProcessedEmailAttachment is skipped.
    """
    client = client or GmailClient()
    geocoder = CensusGeocoder() if geocode_missing else None
    stats = IntakeStats()

    query = build_foia_search_query([t.email for t in targets_with_email()])
    logger.info("FOIA intake: Gmail search query: %s", query)
    message_ids = client.list_message_ids(query, max_results=max_messages)
    logger.info("FOIA intake: %d candidate message(s) matched", len(message_ids))

    for message_id in message_ids:
        message = client.get_message(message_id)
        stats.messages_seen += 1
        target = find_target_for_sender(message.from_address)
        if target is None:
            # Matched the search but not a known target (e.g. a domain-only
            # near-miss) -- skip rather than guess a jurisdiction.
            logger.info("FOIA intake: message %s from %r matched no target; skipping",
                        message_id, message.from_address)
            continue
        jurisdiction = get_or_create_foia_jurisdiction(db, target)

        # --- file attachments ---
        for att in message.attachments:
            if _already_processed(db, message_id, att.attachment_id):
                stats.attachments_skipped += 1
                continue
            try:
                data = client.download_attachment(message_id, att.attachment_id)
                result = parse_attachment(att.filename, data, source_label=_source_label(target, message_id))
            except Exception as exc:
                logger.exception("FOIA intake: failed to download/parse %s", att.filename)
                result = ParseResult(status="error", note=f"download/parse error: {exc}")
            counts = (
                _ingest_records(db, jurisdiction, result, geocoder, enrich, stats)
                if result.records
                else {"created": 0, "updated": 0, "unchanged": 0, "flagged": 0, "errors": 0}
            )
            _record_processed(db, message_id, att.attachment_id, target, message.from_address, att.filename, result, counts)
            _roll_up(stats, counts, att.filename, target, result)

        # --- inline body data table (tracked once per message) ---
        if not _already_processed(db, message_id, BODY_PART_ID):
            result = parse_email_body(message.body_text, source_label=_source_label(target, message_id))
            counts = (
                _ingest_records(db, jurisdiction, result, geocoder, enrich, stats)
                if result.records
                else {"created": 0, "updated": 0, "unchanged": 0, "flagged": 0, "errors": 0}
            )
            # Only bother recording the body row when it actually yielded
            # data OR errored; a plain-prose reply (no_records) is left
            # unrecorded so a later attachment-bearing reply on the same
            # thread can still be picked up without special-casing.
            if result.records or result.status == "error":
                _record_processed(db, message_id, BODY_PART_ID, target, message.from_address, "(email body)", result, counts)
                _roll_up(stats, counts, "(email body)", target, result)
        else:
            stats.attachments_skipped += 1

    return stats


def _source_label(target: FoiaTarget, message_id: str) -> str:
    return f"foia_email:{target.key}:{message_id}"


def _roll_up(stats: IntakeStats, counts: dict, filename: str, target: FoiaTarget, result: ParseResult) -> None:
    stats.attachments_processed += 1
    stats.records_created += counts.get("created", 0)
    stats.records_updated += counts.get("updated", 0)
    stats.records_unchanged += counts.get("unchanged", 0)
    stats.records_flagged += counts.get("flagged", 0)
    stats.errors += counts.get("errors", 0)
    stats.per_attachment.append(
        {
            "target": target.key,
            "filename": filename,
            "status": result.status,
            "note": result.note,
            "created": counts.get("created", 0),
            "updated": counts.get("updated", 0),
            "unchanged": counts.get("unchanged", 0),
            "flagged": counts.get("flagged", 0),
            "errors": counts.get("errors", 0),
            "field_mapping": result.field_mapping,
        }
    )
