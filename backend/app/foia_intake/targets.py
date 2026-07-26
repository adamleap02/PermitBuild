"""
The known FOIA / public-records request targets.

These are the exact agency mailboxes the outbound requests were sent to
(confirmed live against the permitbuildadscharf@gmail.com Sent folder),
each tied to the Jurisdiction its permit data should be ingested under.

The intake poller (app/foia_intake/intake.py) searches Gmail for replies
``from:`` any of these addresses. It also matches on the sending *domain*
as a fallback, because a records officer very often replies from their
own named mailbox (e.g. ``jane.doe@huntingtonwv.gov``) rather than the
generic intake address the request was sent to -- see `domain` below.

A 6th request (Rexburg, ID) was submitted through a web form, not email,
so there is no outbound address to key on; if Rexburg replies by email at
all it will come from some ``@rexburg.org`` address. It is included here
with ``email=None`` and only a domain, so a domain-match reply is still
routed to the right jurisdiction.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FoiaTarget:
    key: str  # stable machine key, also stored on ProcessedEmailAttachment.target_key
    email: Optional[str]  # address the request was sent to (None => web-form submission)
    domain: str  # agency email domain, for the from-domain fallback match
    # Jurisdiction identity (get-or-created by the intake pipeline).
    jurisdiction_name: str
    state: str
    level: str  # city | county
    timezone: str
    display_name: str

    def source_config(self) -> dict:
        return {"target": self.key, "foia_email": self.email, "domain": self.domain}


FOIA_TARGETS: list[FoiaTarget] = [
    FoiaTarget(
        key="la_county_ca",
        email="DPWPRRS@dpw.lacounty.gov",
        domain="dpw.lacounty.gov",
        jurisdiction_name="Los Angeles County (unincorporated)",
        state="CA",
        level="county",
        timezone="America/Los_Angeles",
        display_name="Los Angeles County, CA -- Public Works (FOIA/CPRA)",
    ),
    FoiaTarget(
        key="huntington_wv",
        email="permits@huntingtonwv.gov",
        domain="huntingtonwv.gov",
        jurisdiction_name="Huntington",
        state="WV",
        level="city",
        timezone="America/New_York",
        display_name="Huntington, WV -- Permits (FOIA)",
    ),
    FoiaTarget(
        key="pine_bluff_ar",
        email="inspectionandzoning@cityofpinebluff-ar.gov",
        domain="cityofpinebluff-ar.gov",
        jurisdiction_name="Pine Bluff",
        state="AR",
        level="city",
        timezone="America/Chicago",
        display_name="Pine Bluff, AR -- Inspection & Zoning (FOIA)",
    ),
    FoiaTarget(
        key="bangor_me",
        email="code.enf@bangormaine.gov",
        domain="bangormaine.gov",
        jurisdiction_name="Bangor",
        state="ME",
        level="city",
        timezone="America/New_York",
        display_name="Bangor, ME -- Code Enforcement (FOAA)",
    ),
    FoiaTarget(
        key="danville_il",
        email="cityclerk@cityofdanville.org",
        domain="cityofdanville.org",
        jurisdiction_name="Danville",
        state="IL",
        level="city",
        timezone="America/Chicago",
        display_name="Danville, IL -- City Clerk (FOIA)",
    ),
    # Submitted via web form (no outbound email address). Domain-only match.
    FoiaTarget(
        key="rexburg_id",
        email=None,
        domain="rexburg.org",
        jurisdiction_name="Rexburg",
        state="ID",
        level="city",
        timezone="America/Denver",
        display_name="Rexburg, ID -- Public Records (web form)",
    ),
]


def targets_with_email() -> list[FoiaTarget]:
    """Targets we actually emailed (have a From address to search on)."""
    return [t for t in FOIA_TARGETS if t.email]


def find_target_for_sender(from_address: str) -> Optional[FoiaTarget]:
    """
    Resolve which FOIA target a reply came from, given its From header.

    Matches the exact recipient address first, then falls back to the
    agency email domain (records officers frequently reply from a
    personal named mailbox on the same domain, not the generic intake
    address the request was sent to).
    """
    if not from_address:
        return None
    addr = _extract_email(from_address).lower()
    if not addr:
        return None
    for t in FOIA_TARGETS:
        if t.email and addr == t.email.lower():
            return t
    domain = addr.rsplit("@", 1)[-1]
    for t in FOIA_TARGETS:
        if domain == t.domain.lower():
            return t
    return None


def _extract_email(value: str) -> str:
    """Pull the bare address out of a From header like 'Name <a@b.com>'."""
    value = value.strip()
    if "<" in value and ">" in value:
        return value[value.index("<") + 1 : value.index(">")].strip()
    return value
