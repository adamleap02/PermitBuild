"""
SQLAlchemy ORM models for the construction-intel backend.

Design notes / Postgres+PostGIS upgrade path
---------------------------------------------
This schema is written to run unchanged against SQLite (today, local,
free) and Postgres (later, once Docker/Postgres is available):

- No native Postgres ARRAY / JSONB types are used. Generic
  ``sqlalchemy.JSON`` is used everywhere a flexible/nested field is
  needed; SQLAlchemy stores it as TEXT on SQLite and native JSON/JSONB
  on Postgres automatically, so no code changes are required.
- Latitude/longitude are stored as plain ``Float`` columns rather than
  a PostGIS ``Geometry(Point)`` column. When Postgres+PostGIS is
  available, add a generated ``geography(Point, 4326)`` column (or a
  separate ``geom`` column maintained by a trigger/backfill) and swap
  spatial queries (radius search, polygon lookups) over to PostGIS
  ``ST_DWithin`` / ``ST_Contains`` instead of the naive bounding-box
  math used in the API layer today. See BLOCKERS.md.
- All primary keys are surrogate integers; ``id`` is portable across
  both backends.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def gen_uuid() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Multi-tenant auth scaffold
# ---------------------------------------------------------------------------


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="organization")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="organization")
    saved_searches: Mapped[list["SavedSearch"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="users")
    saved_searches: Mapped[list["SavedSearch"]] = relationship(back_populates="user")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Store only a hash of the key, never the plaintext.
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="api_keys")


# ---------------------------------------------------------------------------
# Jurisdictions / connector configuration
# ---------------------------------------------------------------------------


class SourceSystem(str, enum.Enum):
    SOCRATA = "socrata"
    ARCGIS = "arcgis"
    CKAN = "ckan"
    HTML_SCRAPER = "html_scraper"
    MANUAL = "manual"
    # Bulk permit data received as an email attachment (CSV/XLSX/PDF) in
    # reply to a public-records/FOIA request, parsed heuristically by
    # app/foia_intake/. Inherently lower-confidence than a structured API
    # feed (unpredictable per-agency columns, best-effort PDF extraction),
    # so every Permit ingested this way is flagged needs_review=True.
    FOIA_EMAIL = "foia_email"


class Jurisdiction(Base):
    """A city/county whose permit data we ingest, plus its connector config."""

    __tablename__ = "jurisdictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    level: Mapped[str] = mapped_column(String(32), default="city", nullable=False)  # city|county
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    source_system: Mapped[SourceSystem] = mapped_column(
        Enum(SourceSystem, native_enum=False, length=32), nullable=False
    )
    # Free-form connector config, e.g. {"domain": "data.sfgov.org", "dataset_id": "i98e-djp9",
    # "mapping": "sf_building_permits"} for Socrata, or {"service_url": "...", "mapping": "tempe_az"}
    # for ArcGIS. Stored as JSON so no schema migration is needed to add new source configs.
    source_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    permits: Mapped[list["Permit"]] = relationship(back_populates="jurisdiction")

    __table_args__ = (UniqueConstraint("name", "state", name="uq_jurisdiction_name_state"),)


# ---------------------------------------------------------------------------
# Core permit / property data
# ---------------------------------------------------------------------------


class Permit(Base):
    __tablename__ = "permits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jurisdiction_id: Mapped[int] = mapped_column(ForeignKey("jurisdictions.id"), nullable=False)
    # Indexed for permit->property joins, which become common at scale.
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"), nullable=True, index=True)

    permit_number: Mapped[str] = mapped_column(String(128), nullable=False)
    permit_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(128), nullable=True)

    application_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Indexed: /permits and /export filter and sort on issue_date heavily.
    issue_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completion_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expiration_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    contractor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    builder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    architect: Mapped[str | None] = mapped_column(String(255), nullable=True)
    engineer: Mapped[str | None] = mapped_column(String(255), nullable=True)

    property_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parcel_number: Mapped[str | None] = mapped_column(String(128), nullable=True)  # APN

    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    valuation: Mapped[float | None] = mapped_column(Float, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_category: Mapped[str | None] = mapped_column(String(128), nullable=True)

    square_footage: Mapped[float | None] = mapped_column(Float, nullable=True)
    units: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Indexed for bounding-box / map viewport queries against lat/lon
    # (the naive pre-PostGIS spatial filter path -- see BLOCKERS.md §1).
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)

    permit_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)  # e.g. "socrata:data.sfgov.org"

    # True for records that were extracted heuristically from a less
    # reliable source (FOIA-email CSV/XLSX/PDF attachments -- see
    # app/foia_intake/) rather than a structured API. Lets the API/UI keep
    # these visibly distinct from high-confidence API-sourced permits
    # instead of letting them silently masquerade as vetted data. Defaults
    # False, so every existing API connector is unaffected.
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Full raw record from the source, preserved for debugging/re-mapping.
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    jurisdiction: Mapped["Jurisdiction"] = relationship(back_populates="permits")
    property: Mapped["Property | None"] = relationship(back_populates="permits")
    versions: Mapped[list["PermitVersion"]] = relationship(
        back_populates="permit", order_by="PermitVersion.version_number", cascade="all, delete-orphan"
    )
    scores: Mapped[list["Score"]] = relationship(back_populates="permit", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("jurisdiction_id", "permit_number", name="uq_permit_jurisdiction_number"),
    )


class PermitVersion(Base):
    """
    Append-only version history for a Permit.

    Every time an ingest run detects a change to an existing Permit row,
    a new PermitVersion is written BEFORE the Permit row is updated in
    place. The Permit table always reflects "latest known state"; this
    table is the immutable audit trail. Rows here are never updated or
    deleted.
    """

    __tablename__ = "permit_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    permit_id: Mapped[int] = mapped_column(ForeignKey("permits.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Full snapshot of the permit's mapped fields at this point in time.
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Dict of {field_name: {"old": ..., "new": ...}} for fields that changed
    # since the previous version (empty for the first/initial version).
    changed_fields: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    permit: Mapped["Permit"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("permit_id", "version_number", name="uq_permit_version_number"),
    )


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    address: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_address: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    parcel_number: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geocode_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    geocode_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    property_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lot_size_sqft: Mapped[float | None] = mapped_column(Float, nullable=True)
    building_size_sqft: Mapped[float | None] = mapped_column(Float, nullable=True)
    bedrooms: Mapped[float | None] = mapped_column(Float, nullable=True)
    bathrooms: Mapped[float | None] = mapped_column(Float, nullable=True)
    stories: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Free-form bucket for future enrichment providers (assessor data,
    # sales history, etc.) so we don't need a migration per new field.
    enrichment: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    permits: Mapped[list["Permit"]] = relationship(back_populates="property")
    owners: Mapped[list["Owner"]] = relationship(back_populates="property", cascade="all, delete-orphan")


class Owner(Base):
    """
    Minimal, public-record-safe ownership info.

    Intentionally excludes anything not derivable from public county
    assessor / recorder records (no fabricated contact info, no scraped
    personal data). mailing_address here means the assessor-of-record
    mailing address, which is itself public record in essentially every
    US county.
    """

    __tablename__ = "owners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), nullable=False)

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_type: Mapped[str | None] = mapped_column(String(64), nullable=True)  # individual|llc|trust|gov|unknown
    mailing_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_owner_occupied: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    property: Mapped["Property"] = relationship(back_populates="owners")


class Score(Base):
    """
    Output of app.scoring.engine for a single Permit at a point in time.

    Every numeric score is paired with a plain-English explanation
    field so the rules-based reasoning is always auditable in the API
    response -- no black-box ML here.
    """

    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    permit_id: Mapped[int] = mapped_column(ForeignKey("permits.id"), nullable=False)

    project_size_score: Mapped[float] = mapped_column(Float, nullable=False)
    project_size_explanation: Mapped[str] = mapped_column(Text, nullable=False)

    budget_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    budget_tier_explanation: Mapped[str] = mapped_column(Text, nullable=False)

    urgency_score: Mapped[float] = mapped_column(Float, nullable=False)
    urgency_explanation: Mapped[str] = mapped_column(Text, nullable=False)

    luxury_likelihood: Mapped[float] = mapped_column(Float, nullable=False)
    luxury_explanation: Mapped[str] = mapped_column(Text, nullable=False)

    remodel_vs_repair: Mapped[str] = mapped_column(String(32), nullable=False)
    remodel_vs_repair_explanation: Mapped[str] = mapped_column(Text, nullable=False)

    investment_property_likelihood: Mapped[float] = mapped_column(Float, nullable=False)
    investment_property_explanation: Mapped[str] = mapped_column(Text, nullable=False)

    lead_score: Mapped[float] = mapped_column(Float, nullable=False)
    lead_score_explanation: Mapped[str] = mapped_column(Text, nullable=False)

    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_explanation: Mapped[str] = mapped_column(Text, nullable=False)

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    permit: Mapped["Permit"] = relationship(back_populates="scores")


# ---------------------------------------------------------------------------
# Billing (Stripe scaffold -- see app/billing.py and BLOCKERS.md)
# ---------------------------------------------------------------------------


class SubscriptionStatus(str, enum.Enum):
    NONE = "none"
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    INCOMPLETE = "incomplete"


class Subscription(Base):
    """
    One row per organization tracking its Stripe subscription state.
    Populated/updated by app/routers/billing.py's webhook handler when
    STRIPE_SECRET_KEY/STRIPE_WEBHOOK_SECRET are configured; entirely
    inert (never created) when they're not -- see BLOCKERS.md.
    """

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)

    plan: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, native_enum=False, length=32), default=SubscriptionStatus.NONE, nullable=False
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Full raw Stripe object from the most recent webhook event, kept for
    # debugging/audit without needing a schema change per new Stripe field.
    raw_stripe_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    organization: Mapped["Organization"] = relationship(back_populates="subscriptions")


# ---------------------------------------------------------------------------
# Saved searches + alerts
# ---------------------------------------------------------------------------


class SavedSearch(Base):
    """A named, reusable /permits filter set, owned by a user within an org."""

    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Same filter keys accepted by GET /permits (jurisdiction_id, permit_type,
    # status, date_from, date_to, min_value, max_value, keyword), stored as
    # JSON so new filter fields don't require a migration.
    filters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    organization: Mapped["Organization"] = relationship(back_populates="saved_searches")
    user: Mapped["User"] = relationship(back_populates="saved_searches")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="saved_search", cascade="all, delete-orphan")


class AlertChannel(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"


class AlertFrequency(str, enum.Enum):
    INSTANT = "instant"
    DAILY = "daily"
    WEEKLY = "weekly"


class Alert(Base):
    """
    A subscription to be notified (via a stubbed delivery channel --
    see app/alerts/notifier.py and BLOCKERS.md) when new/changed permits
    match a SavedSearch's filters.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    saved_search_id: Mapped[int] = mapped_column(ForeignKey("saved_searches.id"), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    channel: Mapped[AlertChannel] = mapped_column(Enum(AlertChannel, native_enum=False, length=16), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)  # email address or phone number
    frequency: Mapped[AlertFrequency] = mapped_column(
        Enum(AlertFrequency, native_enum=False, length=16), default=AlertFrequency.DAILY, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    saved_search: Mapped["SavedSearch"] = relationship(back_populates="alerts")
    notification_logs: Mapped[list["AlertNotificationLog"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )


class AlertNotificationLog(Base):
    """
    Append-only audit log of what an alert WOULD HAVE sent. Real
    email/SMS delivery is stubbed (app/alerts/notifier.py) -- this table
    is where "what would have gone out" is actually recorded/inspectable
    even though nothing left the building. See BLOCKERS.md for the
    free-tier transactional-email provider that would replace the stub.
    """

    __tablename__ = "alert_notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), nullable=False)

    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    matched_permit_ids: Mapped[dict] = mapped_column(JSON, default=list, nullable=False)
    # "stubbed" today (no real provider wired up); would become "sent" /
    # "failed" once a real provider from BLOCKERS.md is integrated.
    status: Mapped[str] = mapped_column(String(32), default="stubbed", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    alert: Mapped["Alert"] = relationship(back_populates="notification_logs")


# ---------------------------------------------------------------------------
# FOIA / public-records email intake (see app/foia_intake/)
# ---------------------------------------------------------------------------


class ProcessedEmailAttachment(Base):
    """
    Idempotency ledger for the FOIA-reply email-intake pipeline
    (app/foia_intake/, scripts/poll_foia_replies.py).

    One row per (Gmail message id, attachment part id) the poller has
    already handled, so re-running the poll on a 6-hour schedule never
    re-downloads or re-ingests the same attachment twice. The email body
    of a message is tracked as a synthetic part id ("body") so a data
    table pasted inline in the reply is also processed exactly once.

    `status` records the outcome ("ingested" / "no_records" /
    "unsupported" / "unparseable" / "error") and the counts capture what
    the run did with that specific attachment, so the ledger doubles as an
    inspectable audit trail of every reply the pipeline has seen.
    """

    __tablename__ = "processed_email_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Gmail attachment/part id, or the sentinel "body" for an inline
    # (message-body) data table.
    attachment_id: Mapped[str] = mapped_column(String(512), nullable=False)

    # Which FOIA target (jurisdiction) this reply belongs to, e.g.
    # "huntington_wv" -- see app/foia_intake/targets.py.
    target_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    from_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    records_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_unchanged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_flagged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", "attachment_id", name="uq_processed_email_attachment"),
    )
