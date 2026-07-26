"""
FOIA / public-records email-intake pipeline.

Unlike the API connectors (app/connectors/), where we *pull* structured
data from a documented endpoint, this pipeline *receives* bulk permit
data pushed to us as email attachments (CSV / XLSX / PDF) in reply to
public-records / FOIA requests filed with jurisdictions that have no open
data API. There is no metadata to introspect and every agency names its
columns differently, so parsing is heuristic and best-effort -- every
record produced is flagged ``needs_review=True`` so it never masquerades
as vetted API data.

Modules:
  targets.py       -- the known FOIA target agencies (recipient addresses
                      + the Jurisdiction each maps to)
  gmail_client.py  -- thin wrapper over the Gmail API (saved OAuth token)
  parser.py        -- heuristic field-mapper: attachment/body -> normalized
                      permit dicts (same shape app/ingest.py expects)
  intake.py        -- orchestration: poll Gmail, parse, ingest through the
                      SAME upsert + PermitVersion path as every connector,
                      with per-attachment idempotency tracking
"""
from app.foia_intake.targets import FOIA_TARGETS, FoiaTarget

__all__ = ["FOIA_TARGETS", "FoiaTarget"]
