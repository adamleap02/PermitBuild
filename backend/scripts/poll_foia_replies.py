"""
Entry point for the FOIA-reply email-intake pipeline -- the script the
Windows Task Scheduler job runs every 6 hours (see backend/README.md).

It polls the permitbuildadscharf@gmail.com mailbox for replies from the
known FOIA target agencies (app/foia_intake/targets.py), downloads and
heuristically parses any new CSV/XLSX/PDF attachments (or inline data
tables), and ingests the resulting permit records through the SAME
upsert + PermitVersion history path every connector uses -- flagging each
as needs_review=True.

Safe to run repeatedly: attachments already recorded in the
ProcessedEmailAttachment ledger are skipped, so nothing is ever
re-ingested. Exits cleanly (code 0) whether or not any reply had arrived.
Exit code 2 is reserved for a hard failure (e.g. missing/invalid Gmail
token) so the scheduled task's history surfaces it.

Usage:
    venv\\Scripts\\python.exe scripts\\poll_foia_replies.py
    venv\\Scripts\\python.exe scripts\\poll_foia_replies.py --no-enrich --no-geocode
    venv\\Scripts\\python.exe scripts\\poll_foia_replies.py --max-messages 50
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.foia_intake.gmail_client import GmailAuthError, GmailClient
from app.foia_intake.intake import poll_and_ingest
from app.scoring.service import compute_scores_for_permit_ids


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll Gmail for FOIA replies and ingest permit data.")
    parser.add_argument("--max-messages", type=int, default=100)
    parser.add_argument("--no-geocode", action="store_true", help="Skip Census geocoding of addresses.")
    parser.add_argument("--no-enrich", action="store_true", help="Skip property/parcel enrichment.")
    parser.add_argument("--no-score", action="store_true", help="Skip computing scores for touched permits.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    _configure_logging(args.verbose)
    log = logging.getLogger("poll_foia_replies")

    try:
        client = GmailClient()
        # Cheap, read-only connectivity check up front so a bad token fails
        # fast and loudly rather than mid-run.
        account = client.get_profile_email()
        log.info("Authenticated to Gmail as %s", account)
    except GmailAuthError as exc:
        log.error("Gmail auth failed: %s", exc)
        return 2
    except Exception:
        log.exception("Unexpected error establishing Gmail connection")
        return 2

    db = SessionLocal()
    try:
        stats = poll_and_ingest(
            db,
            client=client,
            max_messages=args.max_messages,
            geocode_missing=not args.no_geocode,
            enrich=not args.no_enrich,
        )
    except Exception:
        log.exception("FOIA intake run failed")
        db.rollback()
        db.close()
        return 2

    log.info("FOIA intake complete: %s", stats.summary())
    for entry in stats.per_attachment:
        log.info(
            "  [%s] %s -> %s (created=%d updated=%d unchanged=%d flagged=%d errors=%d) %s",
            entry["target"], entry["filename"], entry["status"],
            entry["created"], entry["updated"], entry["unchanged"], entry["flagged"], entry["errors"],
            (entry["note"] or ""),
        )

    if not args.no_score and stats.touched_permit_ids:
        scored = compute_scores_for_permit_ids(db, stats.touched_permit_ids)
        log.info("Computed scores for %d permit(s).", scored)

    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
