"""
Ingest pipeline: run a connector, upsert results into Permit rows, and
append PermitVersion history rows on any change. Permit rows are
NEVER overwritten silently -- every update writes a new immutable
PermitVersion snapshot first.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.connectors.arcgis import ARCGIS_SOURCES, ArcGISConnector
from app.connectors.base import NORMALIZED_PERMIT_FIELDS, PermitConnector
from app.connectors.ckan import CKAN_SOURCES, CKANConnector
from app.connectors.geocoder import CensusGeocoder
from app.connectors.html_scraper import ACCELA_SOURCES, AccelaCitizenAccessConnector
from app.connectors.normalizer import normalize_address
from app.connectors.socrata import SOCRATA_SOURCES, SocrataConnector
from app.enrichment.service import enrich_property
from app.models import Jurisdiction, Owner, Permit, PermitVersion, Property, SourceSystem

logger = logging.getLogger(__name__)

# Fields captured in each PermitVersion snapshot / compared for changes.
TRACKED_FIELDS = NORMALIZED_PERMIT_FIELDS[:-1]  # exclude raw_data from diffing (too noisy)


def build_connector(jurisdiction: Jurisdiction) -> PermitConnector:
    """Instantiate the right connector for a jurisdiction's source_config."""
    cfg = jurisdiction.source_config or {}
    mapping_key = cfg.get("mapping")

    if jurisdiction.source_system == SourceSystem.SOCRATA:
        source_cfg = SOCRATA_SOURCES.get(mapping_key)
        if source_cfg is None:
            raise ValueError(f"Unknown socrata mapping key: {mapping_key!r}")
        return SocrataConnector(source_cfg)

    if jurisdiction.source_system == SourceSystem.ARCGIS:
        source_cfg = ARCGIS_SOURCES.get(mapping_key)
        if source_cfg is None:
            raise ValueError(f"Unknown arcgis mapping key: {mapping_key!r}")
        return ArcGISConnector(source_cfg)

    if jurisdiction.source_system == SourceSystem.CKAN:
        source_cfg = CKAN_SOURCES.get(mapping_key)
        if source_cfg is None:
            raise ValueError(f"Unknown ckan mapping key: {mapping_key!r}")
        return CKANConnector(source_cfg)

    if jurisdiction.source_system == SourceSystem.HTML_SCRAPER:
        source_cfg = ACCELA_SOURCES.get(mapping_key)
        if source_cfg is None:
            raise ValueError(f"Unknown html_scraper mapping key: {mapping_key!r}")
        return AccelaCitizenAccessConnector(source_cfg)

    raise ValueError(f"No connector available for source_system={jurisdiction.source_system!r}")


@dataclass
class IngestStats:
    fetched: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: int = 0
    touched_permit_ids: list[int] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.touched_permit_ids is None:
            self.touched_permit_ids = []


def _canonical_dt(value: datetime) -> str:
    """Canonicalize a datetime to a stable naive-UTC ISO string for
    snapshotting/diffing.

    Some connectors (all ArcGIS epoch-date sources) yield timezone-AWARE
    UTC datetimes, but SQLite's DateTime columns store naive values, so a
    tz-aware datetime round-trips back as naive. Comparing the two directly
    made every ArcGIS re-ingest look "changed" purely on the timezone
    suffix (e.g. "2024-10-31T00:00:00" vs "2024-10-31T00:00:00+00:00"),
    silently inflating PermitVersion history on every `--all` run and
    breaking the documented idempotency. Normalizing both sides to naive
    UTC before comparison fixes it; naive datetimes (Socrata/CKAN parse to
    naive already) are treated as UTC and pass through unchanged.
    """
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.isoformat()


def _permit_snapshot(permit: Permit) -> dict:
    snapshot = {}
    for f in TRACKED_FIELDS:
        value = getattr(permit, f)
        if isinstance(value, datetime):
            value = _canonical_dt(value)
        snapshot[f] = value
    return snapshot


def _diff(old: dict, new: dict) -> dict:
    changed = {}
    for key in TRACKED_FIELDS:
        old_val = old.get(key)
        new_val = new.get(key)
        if isinstance(old_val, datetime):
            old_val = _canonical_dt(old_val)
        if isinstance(new_val, datetime):
            new_val = _canonical_dt(new_val)
        if old_val != new_val:
            changed[key] = {"old": old_val, "new": new_val}
    return changed


def _get_or_create_property(
    db: Session,
    address: Optional[str],
    lat: Optional[float],
    lon: Optional[float],
    parcel_number: Optional[str] = None,
) -> Optional[Property]:
    if not address:
        return None
    normalized = normalize_address(address)
    if not normalized:
        return None

    existing = db.query(Property).filter(Property.normalized_address == normalized).one_or_none()
    if existing:
        # Backfill lat/lon/parcel_number if we now have them and didn't before.
        if lat is not None and existing.latitude is None:
            existing.latitude = lat
        if lon is not None and existing.longitude is None:
            existing.longitude = lon
        if parcel_number and not existing.parcel_number:
            existing.parcel_number = parcel_number
        return existing

    prop = Property(
        address=address,
        normalized_address=normalized,
        latitude=lat,
        longitude=lon,
        parcel_number=parcel_number,
    )
    db.add(prop)
    db.flush()
    return prop


def _upsert_owner_from_normalized(db: Session, prop: Optional[Property], normalized: dict) -> None:
    """
    A few connectors surface real, public-record property-owner-of-record
    data directly on the permit feed (e.g. Miami-Dade's `OwnerName`,
    Mecklenburg County's `ownname`) via the non-schema `_owner_name`
    bonus key in their normalized dict (see app/connectors/arcgis.py).
    When present, upsert a minimal Owner row tied to the resolved
    Property -- name only, no fabricated contact info, matching the
    Owner model's "public-record-safe" design intent.
    """
    if prop is None:
        return
    owner_name = normalized.get("_owner_name")
    if not owner_name or not str(owner_name).strip():
        return
    owner_name = str(owner_name).strip()

    existing_owner = (
        db.query(Owner)
        .filter(Owner.property_id == prop.id, Owner.name == owner_name)
        .one_or_none()
    )
    if existing_owner is not None:
        return  # already recorded for this property; owners are append-only-ish, not versioned

    db.add(Owner(property_id=prop.id, name=owner_name, owner_type="unknown"))


def upsert_permit(
    db: Session,
    jurisdiction: Jurisdiction,
    normalized: dict,
    geocoder: Optional[CensusGeocoder] = None,
    enrich: bool = True,
    version_numbers: Optional[dict[int, int]] = None,
) -> tuple[str, int]:
    """
    Upsert a single normalized permit dict. Returns ("created"|"updated"|
    "unchanged", permit_id). Writes a PermitVersion row for every
    create/update.

    ``version_numbers`` is an optional per-run, in-memory
    ``{permit_id: last_assigned_version_number}`` map. It exists to make
    the next-version-number computation robust when the SAME
    ``permit_number`` appears more than once within a single ingest batch
    (common on non-unique-permit-number feeds -- Cook County, San Antonio,
    Howard, etc.). The session runs with ``autoflush=False`` (see
    app/db.py), so a plain ``max(version_number)`` DB query does NOT see a
    PermitVersion added earlier in the same uncommitted batch; two
    occurrences of one permit would then both compute the same "next"
    number and collide on the ``(permit_id, version_number)`` UNIQUE
    constraint at ``commit()`` time -- historically failing the WHOLE
    jurisdiction's commit (SF, Cincinnati) or a per-record insert (Marin,
    Howard, Minneapolis, Nashville, Fort Worth). We defend against this
    two ways (belt and suspenders): (1) consult/maintain this tracker so
    the number is monotonic across the batch without re-querying, and (2)
    ``db.flush()`` each new PermitVersion immediately so even a caller that
    passes no tracker has the row visible to a subsequent DB lookup.
    """
    permit_number = normalized.get("permit_number")
    if not permit_number:
        raise ValueError("normalized permit dict missing required 'permit_number'")

    existing = (
        db.query(Permit)
        .filter(Permit.jurisdiction_id == jurisdiction.id, Permit.permit_number == permit_number)
        .one_or_none()
    )

    lat = normalized.get("latitude")
    lon = normalized.get("longitude")
    address = normalized.get("property_address")

    # Geocode if the source didn't give us coordinates but did give an address.
    if (lat is None or lon is None) and address and geocoder is not None:
        result = geocoder.geocode(address)
        if result:
            lat = lat if lat is not None else result.latitude
            lon = lon if lon is not None else result.longitude

    prop = _get_or_create_property(db, address, lat, lon, parcel_number=normalized.get("parcel_number"))
    _upsert_owner_from_normalized(db, prop, normalized)

    # Free property/parcel enrichment (Census ACS by tract, FEMA flood
    # zone, Cook County Assessor by PIN) -- idempotent, skips sources
    # already recorded on this Property, so repeat ingests of the same
    # address don't re-hit external APIs. See app/enrichment/service.py.
    if enrich and prop is not None:
        try:
            enrich_property(db, prop)
        except Exception:
            logger.exception("Enrichment failed for property_id=%s (continuing without it)", prop.id)

    # `needs_review` is not one of NORMALIZED_PERMIT_FIELDS (so it is never
    # diffed/versioned and no API connector ever sets it), but the
    # FOIA-email intake pipeline (app/foia_intake/) passes it through on the
    # normalized dict to mark heuristically-parsed, lower-confidence records.
    needs_review = bool(normalized.get("needs_review", False))

    if existing is None:
        permit = Permit(jurisdiction_id=jurisdiction.id, permit_number=permit_number)
        for f in TRACKED_FIELDS:
            setattr(permit, f, normalized.get(f))
        permit.latitude = lat
        permit.longitude = lon
        permit.needs_review = needs_review
        permit.raw_data = normalized.get("raw_data") or {}
        permit.property_id = prop.id if prop else None
        db.add(permit)
        db.flush()

        version = PermitVersion(
            permit_id=permit.id,
            version_number=1,
            snapshot=_permit_snapshot(permit),
            changed_fields={},
        )
        db.add(version)
        if version_numbers is not None:
            # The tracker (threaded from run_ingest) makes version numbers
            # monotonic across the batch without needing this row flushed --
            # so skip the per-record flush on the hot bulk-ingest path.
            version_numbers[permit.id] = 1
        else:
            # Tracker-less caller (e.g. FOIA intake): flush so a repeat of
            # this permit_number later in its batch sees the row and can't
            # recompute the same version_number and collide.
            db.flush()
        return "created", permit.id

    new_values = dict(normalized)
    new_values["latitude"] = lat
    new_values["longitude"] = lon
    old_snapshot = _permit_snapshot(existing)
    changed = _diff(old_snapshot, new_values)

    if not changed:
        return "unchanged", existing.id

    for f in TRACKED_FIELDS:
        if f in new_values:
            setattr(existing, f, new_values.get(f))
    if prop is not None:
        existing.property_id = prop.id
    # Only touch needs_review when the caller actually supplied it (the
    # FOIA pipeline does; API connectors never do), so re-ingesting an
    # API permit can't accidentally clear/set the flag.
    if "needs_review" in normalized:
        existing.needs_review = needs_review
    existing.raw_data = normalized.get("raw_data") or existing.raw_data

    # Prefer the per-run tracker (robust against duplicates within one
    # uncommitted batch under autoflush=False); fall back to the DB for a
    # permit first touched this run (its latest version lives only in the DB
    # from a prior run). Take the max of both so we can never regress.
    db_last = 0
    if version_numbers is None or existing.id not in version_numbers:
        last_version = (
            db.query(PermitVersion)
            .filter(PermitVersion.permit_id == existing.id)
            .order_by(PermitVersion.version_number.desc())
            .first()
        )
        db_last = last_version.version_number if last_version else 0
    tracked_last = version_numbers.get(existing.id, 0) if version_numbers is not None else 0
    next_version_number = max(db_last, tracked_last) + 1

    version = PermitVersion(
        permit_id=existing.id,
        version_number=next_version_number,
        snapshot=_permit_snapshot(existing),
        changed_fields=changed,
    )
    db.add(version)
    if version_numbers is not None:
        # Record the assigned number so a repeat of this permit_number later
        # in the batch continues monotonically (no flush needed -- the
        # tracker, not a DB re-query, is the source of truth this run).
        version_numbers[existing.id] = next_version_number
    else:
        # Tracker-less caller: flush so a later duplicate in its batch sees
        # this version and doesn't recompute the same number.
        db.flush()
    return "updated", existing.id


def run_ingest(
    db: Session,
    jurisdiction: Jurisdiction,
    since: Optional[datetime] = None,
    limit: Optional[int] = None,
    geocode_missing: bool = True,
    enrich: bool = True,
) -> IngestStats:
    """Run a jurisdiction's connector end-to-end and upsert all results."""
    connector = build_connector(jurisdiction)
    geocoder = CensusGeocoder() if geocode_missing else None

    stats = IngestStats()
    # Per-run map of {permit_id: last assigned version_number}, threaded
    # through every upsert so duplicate permit_numbers within this batch
    # get monotonic version numbers instead of colliding (see upsert_permit).
    version_numbers: dict[int, int] = {}
    for normalized in connector.fetch_permits(since=since, limit=limit):
        stats.fetched += 1
        try:
            outcome, permit_id = upsert_permit(
                db, jurisdiction, normalized, geocoder=geocoder, enrich=enrich, version_numbers=version_numbers
            )
            if outcome == "created":
                stats.created += 1
                stats.touched_permit_ids.append(permit_id)
            elif outcome == "updated":
                stats.updated += 1
                stats.touched_permit_ids.append(permit_id)
            else:
                stats.unchanged += 1
        except Exception:
            # Critical: a DB-level error (e.g. an IntegrityError from a
            # flush) leaves the SQLAlchemy session in a "pending rollback"
            # state where every subsequent operation raises until
            # rollback() is called -- without this, one bad record
            # silently poisons and fails every remaining record in the
            # batch (found live against Cook County's permit feed, where
            # `permit_number` is occasionally reused across genuinely
            # distinct records -- see BLOCKERS.md).
            logger.exception("Failed to upsert permit %s", normalized.get("permit_number"))
            db.rollback()
            stats.errors += 1

    db.commit()
    return stats
