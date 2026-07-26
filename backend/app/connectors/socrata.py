"""
Generic connector for any Socrata (SODA API) open-data permit dataset.

Socrata's API (https://dev.socrata.com/) is free and public -- no key
required for reasonable/demo-scale use. An app token is optional (free
to register at https://data.<domain>/profile/app_tokens or via
https://dev.socrata.com/register) and only raises your throttling
ceiling; pass it via SOCRATA_APP_TOKEN if you have one.

This connector is intentionally domain/dataset-agnostic: give it a
domain, a dataset id, and a per-source field-mapping config (because
every city names its columns differently) and it works against any
Socrata permit dataset. Two real, live-verified configs are included
below as working examples:

  * SOCRATA_SOURCES["sf_building_permits"]     -- data.sfgov.org / i98e-djp9
  * SOCRATA_SOURCES["chicago_building_permits"] -- data.cityofchicago.org / ydr8-5enu

Both were confirmed live (HTTP 200, real records) during development.
LA's Socrata endpoint (data.lacity.org) was also tried and rejected
requests with "You must be logged in to access this resource" (HTTP
403) even for anonymous/public GET -- see BLOCKERS.md.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Callable, Iterable, Optional, Union

import httpx

from app.connectors.base import ConnectorInfo, PermitConnector

logger = logging.getLogger(__name__)

FieldMapValue = Union[str, Callable[[dict[str, Any]], Any]]

DEFAULT_TIMEOUT = 60.0
# Socrata's SODA API accepts a large $limit (documented ceiling 50,000 rows
# per request); pulling big pages is dramatically fewer round-trips than the
# old 1,000 default when ingesting real production-scale volume from large
# feeds (Orlando 1.1M, Prince George's 461K, Boston, etc.).
DEFAULT_PAGE_SIZE = 50000


def _request_with_backoff(
    url: str,
    *,
    params: dict[str, Any],
    headers: Optional[dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = 5,
) -> httpx.Response:
    """GET with polite exponential back-off on HTTP 429 (rate limited) and
    transient 5xx. Respects a ``Retry-After`` header when the free Socrata
    tier sends one, so a big multi-page pull backs off instead of hammering
    the public service."""
    import time

    delay = 2.0
    for attempt in range(max_retries):
        resp = httpx.get(url, params=params, headers=headers or {}, timeout=timeout)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == max_retries - 1:
                resp.raise_for_status()
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if (retry_after and retry_after.isdigit()) else delay
            logger.warning("Socrata %s on %s; backing off %.1fs (attempt %d)", resp.status_code, url, wait, attempt + 1)
            time.sleep(wait)
            delay = min(delay * 2, 60.0)
            continue
        return resp
    return resp  # pragma: no cover - loop always returns/raises above


def _row_id_permit_number(base_key: str):
    """Factory: disambiguate a non-unique permit number by suffixing Socrata's
    ":id" system row key (requires the source config to set select="*, :id").
    Guaranteed unique per row -- same disambiguation pattern already used for
    Cook County (PIN) and San Antonio (CKAN _id). See BLOCKERS.md §5i."""
    def _fn(rec: dict[str, Any]) -> Optional[str]:
        base = rec.get(base_key)
        if not base or not str(base).strip():
            return None
        row_id = rec.get(":id")
        return f"{str(base).strip()}-{row_id}" if row_id not in (None, "") else str(base).strip()
    return _fn


def _get(record: dict[str, Any], key: str) -> Any:
    """Dotted-path getter, e.g. 'location.coordinates.0'."""
    cur: Any = record
    for part in key.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, (list, tuple)):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def _to_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    f = _to_float(value)
    return int(f) if f is not None else None


def _first_not_none(*values: Any) -> Any:
    """Like `a or b or c`, but zero-safe: a genuine 0/0.0 value is kept
    instead of falling through to the next fallback (plain `or` treats
    0.0 as falsy, which silently discarded real "$0 valuation" values
    during the field-completeness audit -- see BLOCKERS.md)."""
    for v in values:
        if v is not None:
            return v
    return None


def _to_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    # Socrata floating_timestamp values look like "2018-06-29T00:00:00.000"
    # (SF/Chicago/Austin/Seattle); some portals (Dallas, NYC) instead export
    # plain US-style date strings like "03/13/20" or "06/17/2020".
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        logger.debug("Could not parse Socrata datetime value: %r", value)
        return None


# ---------------------------------------------------------------------------
# Per-source field mapping configs
# ---------------------------------------------------------------------------
# Each mapping maps NORMALIZED field name -> either a dotted source
# column path (string) or a callable(record) -> value for anything that
# needs light transformation (dates, lat/lon extraction, concatenated
# addresses, unit/value coercion).

def _sf_permit_number(rec: dict[str, Any]) -> Optional[str]:
    # LIVE-VERIFIED: `permit_number` is NOT unique on this dataset -- the same
    # permit_number appears on genuinely-distinct rows (confirmed: identical
    # mapped fields but different `record_id`, e.g. record_id 1410625418857 vs
    # 1410626418858 for permit 201601288220). `record_id` is a natural,
    # per-row unique column present in the default response, so suffix it --
    # same disambiguation pattern as Cook County (PIN) / San Antonio (_id).
    base = rec.get("permit_number")
    if not base or not str(base).strip():
        return None
    rid = rec.get("record_id")
    return f"{str(base).strip()}-{rid}" if rid not in (None, "") else str(base).strip()


def _sf_full_address(rec: dict[str, Any]) -> Optional[str]:
    parts = [rec.get("street_number"), rec.get("street_name"), rec.get("street_suffix")]
    addr = " ".join(p for p in parts if p)
    return addr or None


def _sf_lat(rec: dict[str, Any]) -> Optional[float]:
    coords = _get(rec, "location.coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) == 2:
        return _to_float(coords[1])
    return None


def _sf_lon(rec: dict[str, Any]) -> Optional[float]:
    coords = _get(rec, "location.coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) == 2:
        return _to_float(coords[0])
    return None


def _sf_valuation(rec: dict[str, Any]) -> Optional[float]:
    # revised_cost is the post-review valuation; fall back to estimated_cost.
    # Zero-safe (see _first_not_none) so a genuine $0 revised_cost isn't
    # silently discarded in favor of estimated_cost.
    return _first_not_none(_to_float(rec.get("revised_cost")), _to_float(rec.get("estimated_cost")))


# Field-completeness audit (against the live metadata endpoint
# https://data.sfgov.org/api/views/i98e-djp9.json) confirmed this dataset
# genuinely has NO contractor/architect/engineer/square-footage/permit-URL
# columns at all -- those stay None below, not a mapping gap. It DOES have
# a `completed_date` column that was previously missed (completion_date
# was wrongly derived from `last_permit_activity_date`, a proxy field, when
# a direct one exists) -- fixed here.
SF_BUILDING_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": _sf_permit_number,
    "permit_type": "permit_type_definition",
    "status": "status",
    "application_date": lambda r: _to_datetime(r.get("filed_date")),
    "issue_date": lambda r: _to_datetime(r.get("issued_date")),
    "completion_date": lambda r: _to_datetime(r.get("completed_date")),
    "expiration_date": lambda r: None,  # confirmed absent from this dataset's schema
    "contractor": lambda r: None,  # confirmed absent from this dataset's schema
    "builder": lambda r: None,
    "architect": lambda r: None,  # confirmed absent
    "engineer": lambda r: None,  # confirmed absent
    "property_address": _sf_full_address,
    "parcel_number": lambda r: f"{r.get('block', '')}/{r.get('lot', '')}".strip("/") or None,
    "estimated_cost": lambda r: _to_float(r.get("estimated_cost")),
    "valuation": _sf_valuation,
    "description": "description",
    "work_category": "permit_type_definition",
    "square_footage": lambda r: None,  # confirmed absent
    "units": lambda r: _to_int(r.get("proposed_units")),
    "latitude": _sf_lat,
    "longitude": _sf_lon,
    "permit_url": lambda r: None,  # confirmed absent
}


def _chi_full_address(rec: dict[str, Any]) -> Optional[str]:
    parts = [rec.get("street_number"), rec.get("street_direction"), rec.get("street_name")]
    addr = " ".join(p for p in parts if p)
    return addr or None


# Chicago's dataset carries up to 15 free-form "contact" slots
# (contact_1_type/contact_1_name .. contact_15_type/contact_15_name) rather
# than dedicated contractor/architect/engineer columns. contact_*_type is
# a free-text role label (confirmed live values include "CONTRACTOR-
# ELECTRICAL", "ARCHITECT", "OWNER AS GENERAL CONTRACTOR", "EXPEDITOR",
# "MASONRY CONTRACTOR", etc.) -- scan all slots for the best role match
# instead of blindly trusting contact_1 (which is often an expediter or
# a trade sub, not the general contractor).
def _chi_find_contact(rec: dict[str, Any], keywords: tuple[str, ...]) -> Optional[str]:
    for i in range(1, 16):
        role = (rec.get(f"contact_{i}_type") or "").upper()
        if any(kw in role for kw in keywords):
            name = rec.get(f"contact_{i}_name")
            if name:
                return name
    return None


def _chi_contractor(rec: dict[str, Any]) -> Optional[str]:
    return (
        _chi_find_contact(rec, ("GENERAL CONTRACTOR",))
        or _chi_find_contact(rec, ("CONTRACTOR",))
        or rec.get("contact_1_name")
    )


def _chi_architect(rec: dict[str, Any]) -> Optional[str]:
    return _chi_find_contact(rec, ("ARCHITECT",))


def _chi_engineer(rec: dict[str, Any]) -> Optional[str]:
    return _chi_find_contact(rec, ("ENGINEER",))


CHICAGO_BUILDING_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permit_",
    "permit_type": "permit_type",
    # permit_status genuinely exists (previously missed -- was hardcoded
    # to None even though the live metadata endpoint shows this column).
    "status": "permit_status",
    "application_date": lambda r: _to_datetime(r.get("application_start_date")),
    "issue_date": lambda r: _to_datetime(r.get("issue_date")),
    "completion_date": lambda r: None,  # confirmed absent from this dataset's schema
    "expiration_date": lambda r: None,  # confirmed absent
    "contractor": _chi_contractor,
    "builder": lambda r: None,
    "architect": _chi_architect,
    "engineer": _chi_engineer,
    "property_address": _chi_full_address,
    "parcel_number": lambda r: None,  # PIN_LIST exists but is often multi-valued/free-text; not a clean single APN
    # Previously mis-mapped: subtotal_paid/total_fee are permit FEES, not
    # project valuation -- reported_cost is the actual declared job value
    # (confirmed via the live metadata endpoint) and is what both
    # estimated_cost/valuation should reflect (Chicago exposes only one
    # cost figure, no separate "revised" number).
    "estimated_cost": lambda r: _to_float(r.get("reported_cost")),
    "valuation": lambda r: _to_float(r.get("reported_cost")),
    "description": "work_description",
    "work_category": "review_type",
    "square_footage": lambda r: None,  # confirmed absent
    "units": lambda r: None,  # confirmed absent
    "latitude": lambda r: _to_float(_get(r, "latitude")),
    "longitude": lambda r: _to_float(_get(r, "longitude")),
    "permit_url": lambda r: None,
}


def _austin_contractor(rec: dict[str, Any]) -> Optional[str]:
    return rec.get("contractor_company_name") or rec.get("contractor_full_name")


def _austin_builder(rec: dict[str, Any]) -> Optional[str]:
    # "Applicant" on an Austin permit is very often the property
    # owner/builder submitting the job (distinct from the contractor doing
    # the work), when present.
    return rec.get("applicant_org") or rec.get("applicant_full_name")


def _austin_cost(rec: dict[str, Any]) -> Optional[float]:
    # total_job_valuation is the declared overall project value; it was
    # missing from the earlier mapping entirely (an oversight -- the field
    # genuinely exists per the live metadata endpoint at
    # https://data.austintexas.gov/api/views/3syk-w9eu.json, it just isn't
    # populated on every permit type, e.g. some trade-only permits like the
    # irrigation-permit sample pulled during initial development). Falls
    # back to total_valuation_remodel for remodel-only jobs that report a
    # remodel-specific figure instead of an overall one. Zero-safe: many
    # real Austin permits genuinely report "0" total_job_valuation (e.g.
    # some sub-permit types where the city doesn't require a declared
    # value) -- a plain `or` chain would wrongly treat that 0 as "missing"
    # and fall through to total_valuation_remodel instead of reporting the
    # real $0.
    return _first_not_none(_to_float(rec.get("total_job_valuation")), _to_float(rec.get("total_valuation_remodel")))


def _austin_sqft(rec: dict[str, Any]) -> Optional[float]:
    # Prefer new/added sqft (what most permits report); fall back to
    # remodel-only sqft, then existing-building sqft, for permit types
    # (pure remodels/repairs) that don't add new square footage. Zero-safe
    # for the same reason as _austin_cost above.
    return _first_not_none(
        _to_float(rec.get("total_new_add_sqft")),
        _to_float(rec.get("remodel_repair_sqft")),
        _to_float(rec.get("total_existing_bldg_sqft")),
    )


def _austin_full_address(rec: dict[str, Any]) -> Optional[str]:
    parts = [rec.get("original_address1"), rec.get("original_city"), rec.get("original_state")]
    addr = " ".join(p for p in parts if p)
    if rec.get("original_zip"):
        addr = f"{addr} {rec['original_zip']}"
    return addr or rec.get("permit_location")


AUSTIN_BUILDING_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permit_number",
    "permit_type": "permit_type_desc",
    "status": "status_current",
    "application_date": lambda r: _to_datetime(r.get("applieddate")),
    "issue_date": lambda r: _to_datetime(r.get("issue_date")),
    "completion_date": lambda r: _to_datetime(r.get("completed_date")),
    "expiration_date": lambda r: _to_datetime(r.get("expiresdate")),
    "contractor": _austin_contractor,
    "builder": _austin_builder,
    "architect": lambda r: None,  # confirmed absent from this dataset's schema
    "engineer": lambda r: None,  # confirmed absent
    "property_address": _austin_full_address,
    "parcel_number": "tcad_id",
    "estimated_cost": _austin_cost,
    "valuation": _austin_cost,
    "description": "description",
    "work_category": "work_class",
    "square_footage": _austin_sqft,
    "units": lambda r: _to_int(r.get("housing_units")),
    "latitude": lambda r: _to_float(r.get("latitude")),
    "longitude": lambda r: _to_float(r.get("longitude")),
    "permit_url": lambda r: _get(r, "link.url"),
}


def _seattle_full_address(rec: dict[str, Any]) -> Optional[str]:
    parts = [rec.get("originaladdress1"), rec.get("originalcity"), rec.get("originalstate")]
    addr = " ".join(p for p in parts if p)
    if rec.get("originalzip"):
        addr = f"{addr} {rec['originalzip']}"
    return addr or None


SEATTLE_BUILDING_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permitnum",
    "permit_type": "permittypedesc",
    "status": "statuscurrent",
    "application_date": lambda r: _to_datetime(r.get("applieddate")),
    "issue_date": lambda r: _to_datetime(r.get("issueddate")),
    "completion_date": lambda r: _to_datetime(r.get("completeddate")),
    "expiration_date": lambda r: _to_datetime(r.get("expiresdate")),
    # Bug fix: contractorcompanyname genuinely exists on this dataset (per
    # the live metadata endpoint) -- was previously hardcoded to None.
    "contractor": "contractorcompanyname",
    "builder": lambda r: None,
    "architect": lambda r: None,  # confirmed absent from this dataset's schema
    "engineer": lambda r: None,  # confirmed absent
    "property_address": _seattle_full_address,
    "parcel_number": lambda r: None,
    "estimated_cost": lambda r: _to_float(r.get("estprojectcost")),
    "valuation": lambda r: _to_float(r.get("estprojectcost")),
    "description": "description",
    "work_category": "permitclassmapped",
    "square_footage": lambda r: None,  # confirmed absent from this dataset's schema
    "units": lambda r: _first_not_none(_to_int(r.get("housingunitsadded")), _to_int(r.get("housingunits"))),
    "latitude": lambda r: _to_float(r.get("latitude")),
    "longitude": lambda r: _to_float(r.get("longitude")),
    "permit_url": lambda r: _get(r, "link.url"),
}


def _dallas_full_address(rec: dict[str, Any]) -> Optional[str]:
    # Dallas's dataset gives only a bare street_address column (no
    # city/state/zip fields split out); Dallas is a single-city dataset so
    # "Dallas, TX" + the dataset's own zip_code column is appended to give
    # the Census geocoder fallback (app/ingest.py) enough to match against.
    street = rec.get("street_address")
    if not street:
        return None
    full = f"{street}, Dallas, TX"
    if rec.get("zip_code"):
        full = f"{full} {rec['zip_code']}"
    return full


# Field-completeness audit against the live metadata endpoint
# (https://www.dallasopendata.com/api/views/e7gq-4sah.json) confirms this
# dataset genuinely has only 10 columns total: permit_number, permit_type,
# issued_date, mapsco, contractor, value, area, work_description, land_use,
# street_address, zip_code. Every field below is either mapped or confirmed
# absent -- this is a genuinely minimal dataset, not an under-mapped one.
DALLAS_BUILDING_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permit_number",
    "permit_type": "permit_type",
    "status": lambda r: None,
    # No application/filed-date column either -- only issued_date.
    "application_date": lambda r: None,
    "issue_date": lambda r: _to_datetime(r.get("issued_date")),
    "completion_date": lambda r: None,
    "expiration_date": lambda r: None,
    # Dallas embeds the full contractor name+address+phone as one free-text
    # field rather than separate columns; stored as-is.
    "contractor": "contractor",
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": _dallas_full_address,
    "parcel_number": lambda r: None,
    "estimated_cost": lambda r: _to_float(r.get("value")),
    "valuation": lambda r: _to_float(r.get("value")),
    "description": "work_description",
    "work_category": "land_use",
    "square_footage": lambda r: _to_float(r.get("area")),
    "units": lambda r: None,
    # No lat/lon columns in this dataset -- deliberately left None so the
    # ingest pipeline's Census-geocoder fallback (app/ingest.py) kicks in
    # using street_address + zip_code. Good live proof of that fallback path.
    "latitude": lambda r: None,
    "longitude": lambda r: None,
    "permit_url": lambda r: None,
}


def _nyc_full_address(rec: dict[str, Any]) -> Optional[str]:
    parts = [rec.get("house__"), rec.get("street_name")]
    street = " ".join(p for p in parts if p)
    tail = " ".join(p for p in (rec.get("borough"), "NY") if p)
    full = street
    if tail:
        full = f"{full}, {tail}"
    if rec.get("zip_code"):
        full = f"{full} {rec['zip_code']}"
    return full or None


def _nyc_permittee_name(rec: dict[str, Any]) -> Optional[str]:
    business = rec.get("permittee_s_business_name")
    if business and business != "N/A":
        return business
    parts = [rec.get("permittee_s_first_name"), rec.get("permittee_s_last_name")]
    name = " ".join(p for p in parts if p)
    return name or None


# permittee_s_license_type is a real, confirmed-live signal for role: a
# distinct-value count against the live dataset showed GC (General
# Contractor, ~2.4M rows), MP (Master Plumber), FS (Fire Suppression), OB/
# OW/NW (owner variants), RA (Registered Architect, ~5,700 rows), PE
# (Professional Engineer, ~4,800 rows), DM, HI. Route RA -> architect, PE
# -> engineer, everything else (GC and all trade-license types) -> the
# contractor field, since they're still the permittee performing/
# overseeing the permitted work.
def _nyc_contractor(rec: dict[str, Any]) -> Optional[str]:
    license_type = (rec.get("permittee_s_license_type") or "").upper()
    if license_type in ("RA", "PE"):
        return None
    return _nyc_permittee_name(rec)


def _nyc_architect(rec: dict[str, Any]) -> Optional[str]:
    if (rec.get("permittee_s_license_type") or "").upper() == "RA":
        return _nyc_permittee_name(rec)
    return None


def _nyc_engineer(rec: dict[str, Any]) -> Optional[str]:
    if (rec.get("permittee_s_license_type") or "").upper() == "PE":
        return _nyc_permittee_name(rec)
    return None


NYC_DOB_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    # DOB NOW permit-issuance records don't have one single "permit number"
    # column -- permit_si_no (permit sequence identifier) is the closest
    # thing to a unique per-permit key in this feed.
    "permit_number": "permit_si_no",
    "permit_type": "permit_type",
    "status": "permit_status",
    "application_date": lambda r: _to_datetime(r.get("filing_date")),
    "issue_date": lambda r: _to_datetime(r.get("issuance_date")),
    "completion_date": lambda r: None,  # confirmed absent from this feed (permit issuance events, not job completion)
    "expiration_date": lambda r: _to_datetime(r.get("expiration_date")),
    "contractor": _nyc_contractor,
    "builder": lambda r: None,
    "architect": _nyc_architect,
    "engineer": _nyc_engineer,
    "property_address": _nyc_full_address,
    "parcel_number": lambda r: f"{r.get('block', '')}/{r.get('lot', '')}".strip("/") or None,
    # This feed (permit issuance events) does not carry job valuation --
    # that lives in a separate NYC DOB "job filings" dataset not used here.
    "estimated_cost": lambda r: None,
    "valuation": lambda r: None,
    "description": lambda r: " ".join(p for p in (r.get("job_type"), r.get("work_type")) if p) or None,
    "work_category": "work_type",
    "square_footage": lambda r: None,
    "units": lambda r: None,
    "latitude": lambda r: _to_float(r.get("gis_latitude")),
    "longitude": lambda r: _to_float(r.get("gis_longitude")),
    "permit_url": lambda r: None,
}


# ---------------------------------------------------------------------------
# Second data-gathering pass -- 13 more real, live-verified Socrata sources
# (7 counties + a statewide feed + 5 more cities), added to broaden
# geographic coverage per research/RESEARCH_REPORT.md and beyond it. Each
# was hit live and confirmed responding with real records before being
# wired in here -- see BLOCKERS.md for the ones that were tried and
# rejected/skipped (403s, moved domains, aggregated-only data).
# ---------------------------------------------------------------------------


def _sonoma_address(rec: dict[str, Any]) -> Optional[str]:
    addr = rec.get("address")
    if not addr:
        return None
    return f"{addr}, CA"  # dataset has no city/state columns; county is single-state


SONOMA_COUNTY_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "file_number",
    "permit_type": "application_type",
    "status": "status",
    "application_date": lambda r: _to_datetime(r.get("started")),
    "issue_date": lambda r: _to_datetime(r.get("issued")),
    "completion_date": lambda r: None,  # confirmed absent
    "expiration_date": lambda r: None,  # confirmed absent
    "contractor": lambda r: None,  # confirmed absent
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": _sonoma_address,
    "parcel_number": "assessors_parcel_number",
    # `value` is the declared project value; `totfee` is a fee, not mapped
    # into cost/valuation (same fee-vs-value distinction as elsewhere).
    "estimated_cost": lambda r: _to_float(r.get("value")),
    "valuation": lambda r: _to_float(r.get("value")),
    "description": "description",
    "work_category": "application_type",
    "square_footage": lambda r: None,  # confirmed absent
    "units": lambda r: None,  # confirmed absent
    "latitude": lambda r: None,  # confirmed absent -- Census geocoder fallback applies
    "longitude": lambda r: None,
    "permit_url": lambda r: None,
}


def _marin_permit_number(rec: dict[str, Any]) -> Optional[str]:
    # LIVE-VERIFIED: `permit_number` is NOT unique per row; `unique_id` is a
    # natural per-row unique column (2000/2000 distinct in a live sample), so
    # suffix it -- same pattern as Cook County / San Antonio. A slice of rows
    # (~2.6%) also have a blank permit_number; fall back to unique_id alone so
    # those real records still ingest (same idea as Boston's BOS-<id>).
    uid = rec.get("unique_id")
    base = rec.get("permit_number")
    if not base or not str(base).strip():
        return f"MARIN-{uid}" if uid not in (None, "") else None
    return f"{str(base).strip()}-{uid}" if uid not in (None, "") else str(base).strip()


MARIN_COUNTY_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": _marin_permit_number,
    "permit_type": "type_permit",
    "status": lambda r: None,  # confirmed absent from this dataset's schema
    "application_date": lambda r: _to_datetime(r.get("received_date")),
    "issue_date": lambda r: _to_datetime(r.get("issued_date")),
    "completion_date": lambda r: None,
    "expiration_date": lambda r: None,
    "contractor": "contractor",
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": "address",  # already a full "street, city, CA zip" string
    "parcel_number": "parcel_number",
    "estimated_cost": lambda r: _to_float(r.get("construction_value")),
    "valuation": lambda r: _to_float(r.get("construction_value")),
    "description": "description",
    "work_category": "permit_work_class",
    "square_footage": lambda r: None,  # confirmed absent
    "units": lambda r: None,  # confirmed absent
    "latitude": lambda r: _to_float(r.get("latitude")),
    "longitude": lambda r: _to_float(r.get("longitude")),
    "permit_url": lambda r: None,
}


# Howard County's public feed is genuinely minimal: no street-level address
# column at all (only city/zip), no valuation, no contractor. Confirmed via
# the live metadata endpoint, not an under-mapping -- Property/geocoding
# will simply not attach for these permits (property_address stays None).
# Still wired in because it's real, live, county-level data that adds
# Maryland to our footprint; see BLOCKERS.md for the limitation.
HOWARD_COUNTY_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": _row_id_permit_number("permit_number"),
    "permit_type": "permit_type",
    "status": lambda r: None,  # confirmed absent
    "application_date": lambda r: _to_datetime(r.get("file_date")),
    "issue_date": lambda r: _to_datetime(r.get("issue_date")),
    "completion_date": lambda r: None,
    "expiration_date": lambda r: None,
    "contractor": lambda r: None,  # confirmed absent
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": lambda r: None,  # confirmed absent -- only city/zip, no street address
    "parcel_number": lambda r: None,
    "estimated_cost": lambda r: None,  # confirmed absent
    "valuation": lambda r: None,
    "description": lambda r: " ".join(p for p in (r.get("category"), r.get("type")) if p) or None,
    "work_category": "category",
    "square_footage": lambda r: None,
    "units": lambda r: None,
    "latitude": lambda r: None,
    "longitude": lambda r: None,
    "permit_url": lambda r: None,
}


BATON_ROUGE_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permitnumber",
    "permit_type": "permittype",
    "status": lambda r: None,  # confirmed absent (designation is a residential/commercial flag, not a status)
    "application_date": lambda r: _to_datetime(r.get("creationdate")),
    "issue_date": lambda r: _to_datetime(r.get("issueddate")),
    "completion_date": lambda r: None,
    "expiration_date": lambda r: None,
    "contractor": "contractorname",
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": "address",  # already a full "street, city, LA zip" string
    "parcel_number": lambda r: None,  # lotnumber/subdivision exist but aren't a proper APN; kept in raw_data
    "estimated_cost": lambda r: _to_float(r.get("projectvalue")),
    "valuation": lambda r: _to_float(r.get("projectvalue")),
    "description": "projectdescription",
    "work_category": "designation",
    "square_footage": lambda r: _to_float(r.get("squarefootage")),
    "units": lambda r: None,
    "latitude": lambda r: _to_float(r.get("lat")),
    "longitude": lambda r: _to_float(r.get("long")),
    "permit_url": lambda r: None,
}


def _mesa_valuation(rec: dict[str, Any]) -> Optional[float]:
    return _first_not_none(_to_float(rec.get("total_valuation")), _to_float(rec.get("job_value")))


def _mesa_units(rec: dict[str, Any]) -> Optional[int]:
    return _first_not_none(_to_int(rec.get("number_of_dwelling_units")), _to_int(rec.get("number_of_dwellings")))


MESA_AZ_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permit_number",
    "permit_type": "permit_type",
    "status": "status",
    "application_date": lambda r: _to_datetime(r.get("opened_date")),
    "issue_date": lambda r: _to_datetime(r.get("issued_date")),
    "completion_date": lambda r: _to_datetime(r.get("finaled_date")),
    "expiration_date": lambda r: None,  # confirmed absent
    "contractor": "contractor_name",
    "builder": "applicant",
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": "property_address",  # already a full street address
    "parcel_number": "parcel_number",
    "estimated_cost": _mesa_valuation,
    "valuation": _mesa_valuation,
    "description": "description_of_work",
    "work_category": "type_of_work",
    "square_footage": lambda r: _to_float(r.get("total_square_feet")),
    "units": _mesa_units,
    "latitude": lambda r: _to_float(r.get("latitude")),
    "longitude": lambda r: _to_float(r.get("longitude")),
    "permit_url": lambda r: None,
}


def _cincinnati_address(rec: dict[str, Any]) -> Optional[str]:
    parts = [rec.get("originaladdress1"), rec.get("originalcity"), rec.get("originalstate")]
    addr = " ".join(p for p in parts if p)
    if rec.get("originalzip"):
        addr = f"{addr} {rec['originalzip']}"
    return addr or None


CINCINNATI_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": _row_id_permit_number("permitnum"),
    "permit_type": "permittypemapped",
    "status": "statuscurrentmapped",
    "application_date": lambda r: _to_datetime(r.get("applieddate")),
    "issue_date": lambda r: _to_datetime(r.get("issueddate")),
    "completion_date": lambda r: _to_datetime(r.get("completeddate")),
    "expiration_date": lambda r: _to_datetime(r.get("expiresdate")),
    "contractor": "companyname",
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": _cincinnati_address,
    "parcel_number": "pin",
    "estimated_cost": lambda r: _to_float(r.get("estprojectcostdec")),
    "valuation": lambda r: _to_float(r.get("estprojectcostdec")),
    "description": "description",
    "work_category": "workclassmapped",
    "square_footage": lambda r: _to_float(r.get("totalsqft")),
    "units": lambda r: _to_int(r.get("units")),
    "latitude": lambda r: _to_float(r.get("latitude")),
    "longitude": lambda r: _to_float(r.get("longitude")),
    "permit_url": "link",
}


def _gainesville_contractor(rec: dict[str, Any]) -> Optional[str]:
    return rec.get("business") or rec.get("contractor")


def _gainesville_address(rec: dict[str, Any]) -> Optional[str]:
    parts = [rec.get("address"), rec.get("city"), rec.get("state")]
    addr = " ".join(p for p in parts if p)
    return addr or None


GAINESVILLE_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permit",
    "permit_type": "type",
    "status": lambda r: None,  # confirmed absent
    "application_date": lambda r: _to_datetime(r.get("submit")),
    "issue_date": lambda r: _to_datetime(r.get("issue")),
    "completion_date": lambda r: None,
    "expiration_date": lambda r: None,
    "contractor": _gainesville_contractor,
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": _gainesville_address,
    "parcel_number": "parcel",
    "estimated_cost": lambda r: None,  # confirmed absent -- no value/cost column on this dataset
    "valuation": lambda r: None,
    "description": lambda r: " ".join(p for p in (r.get("classification"), r.get("subtype")) if p) or None,
    "work_category": "classification",
    "square_footage": lambda r: None,
    "units": lambda r: None,
    "latitude": lambda r: _to_float(r.get("latitude")),
    "longitude": lambda r: _to_float(r.get("longitude")),
    "permit_url": lambda r: None,
}


def _cook_county_address(rec: dict[str, Any]) -> Optional[str]:
    # A meaningful fraction of this dataset's property_address values are
    # literal placeholder junk ("..", "...") rather than null -- confirmed
    # live via a sample pull during development. Filter those out rather
    # than storing garbage addresses (which would also poison Property
    # dedup-by-normalized-address).
    addr = (rec.get("property_address") or "").strip()
    if not addr or addr.strip(".") == "":
        return None
    return addr


def _cook_county_permit_number(rec: dict[str, Any]) -> Optional[str]:
    # IMPORTANT, live-verified data-quality finding: this dataset's
    # `permit_number` is NOT reliably unique -- the same permit_number
    # value can appear on multiple genuinely-distinct rows (different
    # PIN/date_issued/work_description/etc), which caused real
    # UNIQUE-constraint failures against our (jurisdiction_id,
    # permit_number) schema during development at scale. Cook County's
    # own `row_id` column is the dataset's actual unique key (a
    # concatenation of pin+year+permit_number+local_permit_number+
    # date_issued), so disambiguate by appending the PIN, which is
    # cheap and keeps the human-readable permit number as a prefix.
    base = rec.get("permit_number") or rec.get("local_permit_number")
    if not base:
        return None
    pin = rec.get("pin")
    return f"{base}-{pin}" if pin else base


COOK_COUNTY_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    # This is Cook County ASSESSOR's permit feed (property-improvement
    # permits tied to a parcel PIN, reported by ~130 municipalities within
    # the county), not one city's building department -- `municipality`
    # varies per row and is preserved in raw_data.
    "permit_number": _cook_county_permit_number,
    "permit_type": "job_code_primary",
    "status": "status",
    "application_date": lambda r: None,  # confirmed absent -- only date_issued exists
    "issue_date": lambda r: _to_datetime(r.get("date_issued")),
    # estimated_date_of_completion is explicitly an ESTIMATE per its own
    # column name, not a confirmed actual completion -- deliberately not
    # mapped into completion_date to avoid presenting an estimate as fact.
    "completion_date": lambda r: None,
    "expiration_date": lambda r: None,
    "contractor": lambda r: None,  # confirmed absent -- only applicant_name (mapped to builder below)
    "builder": "applicant_name",
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": _cook_county_address,
    # `pin` is the Cook County Assessor's Property Index Number -- a
    # genuine, high-quality parcel identifier (this is assessor data).
    "parcel_number": "pin",
    "estimated_cost": lambda r: _to_float(r.get("amount")),
    "valuation": lambda r: _to_float(r.get("amount")),
    "description": "work_description",
    "work_category": "job_code_primary",
    "square_footage": lambda r: None,  # confirmed absent
    "units": lambda r: None,  # confirmed absent
    "latitude": lambda r: None,  # confirmed absent -- Census geocoder fallback applies
    "longitude": lambda r: None,
    "permit_url": lambda r: None,
}


def _cambridge_cost(rec: dict[str, Any]) -> Optional[float]:
    return _first_not_none(_to_float(rec.get("total_cost_of_construction")), _to_float(rec.get("building_cost")))


CAMBRIDGE_NEW_CONSTRUCTION_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "id",
    "permit_type": "permit_type",
    "status": "status",
    "application_date": lambda r: _to_datetime(r.get("applicant_submit_date")),
    "issue_date": lambda r: _to_datetime(r.get("issue_date")),
    "completion_date": lambda r: None,  # confirmed absent from this dataset's schema
    "expiration_date": lambda r: None,
    # "Licensed Construction Supervisor" is the closest field to a general
    # contractor of record on this dataset.
    "contractor": "licensed_name",
    "builder": "applicant_name",
    # Cambridge is one of the few sources in this codebase with genuine,
    # direct architect/engineer-of-record columns -- no inference needed.
    "architect": "architect_name",
    "engineer": "engineer_name",
    "property_address": "full_address",
    "parcel_number": "mbl",  # Massachusetts "Map-Block-Lot" parcel ID convention
    "estimated_cost": _cambridge_cost,
    "valuation": _cambridge_cost,
    "description": "description_of_work",
    "work_category": "proposed_building_use",
    "square_footage": lambda r: _to_float(r.get("gross_square_footage")),
    "units": lambda r: _to_int(r.get("proposed_count_of_dwelling")),
    "latitude": lambda r: _to_float(r.get("latitude")),
    "longitude": lambda r: _to_float(r.get("longitude")),
    "permit_url": lambda r: None,
}


def _framingham_address(rec: dict[str, Any]) -> Optional[str]:
    parts = [rec.get("street_number"), rec.get("street_name")]
    street = " ".join(str(p) for p in parts if p)
    if not street:
        return None
    return f"{street}, Framingham, MA"


FRAMINGHAM_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permit",
    "permit_type": "type",
    "status": lambda r: None,  # confirmed absent
    "application_date": lambda r: _to_datetime(r.get("applied")),
    # Genuinely odd but confirmed via the live metadata endpoint: this
    # dataset has an "applied" date column and no "issued" date column at
    # all -- issue_date stays None rather than reusing applied's value
    # (which would misrepresent an application date as an issuance date).
    "issue_date": lambda r: None,
    "completion_date": lambda r: None,
    "expiration_date": lambda r: None,
    "contractor": lambda r: None,  # confirmed absent
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": _framingham_address,
    "parcel_number": lambda r: None,
    "estimated_cost": lambda r: _to_float(r.get("estimated_job_cost")),
    "valuation": lambda r: _to_float(r.get("estimated_job_cost")),
    "description": "description",
    "work_category": lambda r: r.get("category") or r.get("sub_type"),
    "square_footage": lambda r: None,
    "units": lambda r: None,
    "latitude": lambda r: _to_float(_get(r, "location_1.latitude")),
    "longitude": lambda r: _to_float(_get(r, "location_1.longitude")),
    "permit_url": lambda r: None,
}


SAN_DIEGO_COUNTY_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "record_id",
    "permit_type": "record_type",
    "status": "record_status",
    "application_date": lambda r: _to_datetime(r.get("open_date")),
    "issue_date": lambda r: _to_datetime(r.get("issued_date")),
    "completion_date": lambda r: None,  # confirmed absent
    "expiration_date": lambda r: None,
    "contractor": "contractor_name",
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": "full_address",
    "parcel_number": "parcel_number",
    # This dataset has a genuinely-named `valuation` column (rare -- most
    # sources call it estimated_cost/job_value/total_job_valuation/etc).
    "estimated_cost": lambda r: _to_float(r.get("valuation")),
    "valuation": lambda r: _to_float(r.get("valuation")),
    "description": "use",
    "work_category": "record_category",
    "square_footage": lambda r: _to_float(r.get("floor_area")),
    "units": lambda r: None,
    "latitude": lambda r: _to_float(_get(r, "geocoded_column.latitude")),
    "longitude": lambda r: _to_float(_get(r, "geocoded_column.longitude")),
    "permit_url": lambda r: None,
}


def _nj_units(rec: dict[str, Any]) -> Optional[int]:
    return _first_not_none(_to_int(rec.get("salegained")), _to_int(rec.get("rentgained")))


# New Jersey's statewide construction-permit feed covers every reporting
# municipality in the state via one dataset (comu/muniname/county columns
# per row) rather than one city -- represented as a single "New Jersey
# (statewide)" Jurisdiction (level="state") rather than one row per town.
# Genuinely has NO street-address column at all (only municipality name +
# block/lot), so Property/geocoding will not attach for these permits --
# confirmed via the live metadata endpoint, not a mapping gap.
NJ_STATEWIDE_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permitno",
    "permit_type": lambda r: r.get("permittypedesc") or r.get("permittype"),
    "status": lambda r: r.get("permitstatusdesc") or r.get("status"),
    "application_date": lambda r: None,
    "issue_date": lambda r: _to_datetime(r.get("permitdate")),
    "completion_date": lambda r: _to_datetime(r.get("certdate")),
    "expiration_date": lambda r: None,
    "contractor": lambda r: None,  # confirmed absent
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": lambda r: None,  # confirmed absent -- see note above
    "parcel_number": lambda r: (
        f"{r.get('muniname', '')}-{r.get('block', '')}/{r.get('lot', '')}".strip("-/") or None
    ),
    "estimated_cost": lambda r: _to_float(r.get("constcost")),
    "valuation": lambda r: _to_float(r.get("constcost")),
    "description": lambda r: r.get("usegroupdesc") or r.get("censusdesc"),
    "work_category": "permittypedesc",
    "square_footage": lambda r: _to_float(r.get("squarefeet")),
    "units": _nj_units,
    "latitude": lambda r: None,  # confirmed absent
    "longitude": lambda r: None,
    "permit_url": lambda r: None,
}


def _neworleans_lat(rec: dict[str, Any]) -> Optional[float]:
    coords = _get(rec, "the_geom.coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) == 2:
        return _to_float(coords[1])
    return None


def _neworleans_lon(rec: dict[str, Any]) -> Optional[float]:
    coords = _get(rec, "the_geom.coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) == 2:
        return _to_float(coords[0])
    return None


NEW_ORLEANS_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": lambda r: r.get("numstring") or r.get("prmtid"),
    "permit_type": "permittype",
    "status": lambda r: None,  # confirmed absent
    "application_date": lambda r: None,  # confirmed absent -- only an issue date exists
    "issue_date": lambda r: _to_datetime(r.get("issuedate")),
    "completion_date": lambda r: None,
    "expiration_date": lambda r: None,
    "contractor": lambda r: None,  # confirmed absent
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": lambda r: f"{r['address']}, New Orleans, LA" if r.get("address") else None,
    "parcel_number": lambda r: None,  # confirmed absent
    "estimated_cost": lambda r: _to_float(r.get("constructionval")),
    "valuation": lambda r: _to_float(r.get("constructionval")),
    "description": "descr",
    "work_category": "landuse",
    "square_footage": lambda r: None,
    "units": lambda r: None,
    "latitude": _neworleans_lat,
    "longitude": _neworleans_lon,
    "permit_url": lambda r: None,
}


# ---------------------------------------------------------------------------
# Fourth data-gathering pass -- national-breadth expansion (Northeast,
# Midwest, Southeast, Mountain West, Pacific NW): 4 more real, live-verified
# Socrata sources, found partly via the central Socrata catalog and partly
# by checking each jurisdiction's OWN .gov site directly (per the
# coordinator's guidance that the central catalogs miss real datasets
# smaller/mid-size cities publish on their own domains).
# ---------------------------------------------------------------------------


def _honolulu_cost(rec: dict[str, Any]) -> Optional[float]:
    return _first_not_none(_to_float(rec.get("acceptedvalue")), _to_float(rec.get("estimatedvalueofwork")))


# Honolulu's permit extract genuinely has NO street-address column at all
# (confirmed via the live metadata endpoint) -- Hawaii identifies parcels by
# TMK (Tax Map Key) rather than a standard address field in this particular
# resource. property_address stays None; geocoding cannot attach for this
# source. location_1 carries a GeoJSON-style nested point for lat/lon.
def _honolulu_latlon(rec: dict[str, Any], axis: int) -> Optional[float]:
    coords = _get(rec, "location_1.coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) == 2:
        return _to_float(coords[axis])
    return None


HONOLULU_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "buildingpermitno",
    "permit_type": "buildingpermittype",
    "status": "statusdescription",
    "application_date": lambda r: _to_datetime(r.get("createddate")),
    "issue_date": lambda r: _to_datetime(r.get("issuedate")),
    "completion_date": lambda r: _to_datetime(r.get("completeddate")),
    "expiration_date": lambda r: None,  # confirmed absent
    "contractor": "contractor",
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": lambda r: None,  # confirmed absent -- see note above (TMK-based, no street address column)
    "parcel_number": "tmk",
    "estimated_cost": _honolulu_cost,
    "valuation": _honolulu_cost,
    "description": lambda r: r.get("proposeduse") or r.get("otherwork"),
    "work_category": "buildingpermittype",
    "square_footage": lambda r: _to_float(r.get("totalfloorarea")),
    "units": lambda r: None,
    "latitude": lambda r: _honolulu_latlon(r, 1),
    "longitude": lambda r: _honolulu_latlon(r, 0),
    "permit_url": lambda r: None,
}


NORFOLK_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permit_number",
    "permit_type": "type",
    "status": "status",
    "application_date": lambda r: _to_datetime(r.get("application_date")),
    "issue_date": lambda r: _to_datetime(r.get("issue_date")),
    "completion_date": lambda r: _to_datetime(r.get("finaled_date")),
    "expiration_date": lambda r: _to_datetime(r.get("expiration_date")),
    "contractor": lambda r: None,  # confirmed absent -- no contractor column on this dataset
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": "address",
    "parcel_number": "gpin",
    "estimated_cost": lambda r: _to_float(r.get("project_cost")),
    "valuation": lambda r: _to_float(r.get("project_cost")),
    "description": lambda r: r.get("work_type") or r.get("use_type"),
    "work_category": "use_group",
    "square_footage": lambda r: _to_float(r.get("square_footage")),
    "units": lambda r: None,
    "latitude": lambda r: _to_float(r.get("latitude")),
    "longitude": lambda r: _to_float(r.get("longitude")),
    "permit_url": lambda r: None,
}


def _kcmo_address(rec: dict[str, Any]) -> Optional[str]:
    parts = [rec.get("originaladdress1"), rec.get("originalcity"), rec.get("originalstate")]
    addr = " ".join(p for p in parts if p)
    if rec.get("originalzip"):
        addr = f"{addr} {rec['originalzip']}"
    return addr or None


KANSAS_CITY_MO_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permitnum",
    "permit_type": "permittypemapped",
    "status": "statuscurrent",
    "application_date": lambda r: _to_datetime(r.get("applieddate")),
    "issue_date": lambda r: _to_datetime(r.get("issueddate")),
    "completion_date": lambda r: _to_datetime(r.get("completeddate")),
    "expiration_date": lambda r: _to_datetime(r.get("expiresdate")),
    "contractor": "contractorcompanyname",
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": _kcmo_address,
    "parcel_number": "pin",
    "estimated_cost": lambda r: _to_float(r.get("estprojectcost")),
    "valuation": lambda r: _to_float(r.get("estprojectcost")),
    "description": "description",
    "work_category": "workclassmapped",
    "square_footage": lambda r: _to_float(r.get("totalsqft")),
    "units": lambda r: _to_int(r.get("housingunits")),
    "latitude": lambda r: _to_float(r.get("latitude")),
    "longitude": lambda r: _to_float(r.get("longitude")),
    "permit_url": "link",
}


def _montgomery_county_address(rec: dict[str, Any]) -> Optional[str]:
    parts = [
        rec.get("stno"),
        rec.get("predir"),
        rec.get("stname"),
        rec.get("suffix"),
        rec.get("postdir"),
    ]
    street = " ".join(p for p in parts if p)
    tail = " ".join(p for p in (rec.get("city"), rec.get("state")) if p)
    full = street
    if tail:
        full = f"{full}, {tail}"
    if rec.get("zip"):
        full = f"{full} {rec['zip']}"
    return full or None


# Montgomery County, MD's residential-permit feed genuinely has no
# contractor, expiration-date, or lat/lon columns (confirmed via the live
# metadata endpoint) -- a third Maryland county in this codebase (alongside
# Howard and Anne Arundel), each with a distinct real schema.
MONTGOMERY_COUNTY_MD_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permitno",
    "permit_type": "applicationtype",
    "status": "status",
    "application_date": lambda r: _to_datetime(r.get("addeddate")),
    "issue_date": lambda r: _to_datetime(r.get("issueddate")),
    "completion_date": lambda r: _to_datetime(r.get("finaleddate")),
    "expiration_date": lambda r: None,  # confirmed absent
    "contractor": lambda r: None,  # confirmed absent
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": _montgomery_county_address,
    "parcel_number": lambda r: None,  # confirmed absent
    "estimated_cost": lambda r: _to_float(r.get("declaredvaluation")),
    "valuation": lambda r: _to_float(r.get("declaredvaluation")),
    "description": "description",
    "work_category": "worktype",
    "square_footage": lambda r: _to_float(r.get("buildingarea")),
    "units": lambda r: None,
    "latitude": lambda r: None,  # confirmed absent -- Census geocoder fallback applies
    "longitude": lambda r: None,
    "permit_url": lambda r: None,
}


# ---------------------------------------------------------------------------
# Sixth data-gathering pass -- population-driven expansion beyond
# EXPANSION_PLAN.md's original list. Each source below was queried live via
# direct HTTP this pass (column list + a couple of sample rows) before wiring;
# confirmed-absent fields and fee-vs-valuation findings are noted per source.
# ---------------------------------------------------------------------------


def _orlando_point(rec: dict[str, Any], idx: int) -> Optional[float]:
    # `geocoded_column` is a Socrata Point ({"type":"Point","coordinates":[lon,lat]}).
    # NOTE: the separate `location` column is a free-text label ("Carports 22 23"),
    # NOT coordinates -- do not use it for lat/lon.
    coords = _get(rec, "geocoded_column.coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) == 2:
        return _to_float(coords[idx])
    return None


def _orlando_address(rec: dict[str, Any]) -> Optional[str]:
    street = (rec.get("permit_address") or "").strip()
    if not street:
        return None
    return f"{street}, Orlando, FL"


# City of Orlando, FL (distinct from the county-level Miami-Dade feed and from
# Gainesville/Tampa). 1.1M+ rows. `estimated_cost` is the declared construction
# value (no permit-fee column exists on this dataset to confuse it with;
# collect_permit_fees_date is only a date). `application_type` is a coarse
# category ("Building Permit") while `worktype` (New/Alteration) is the work
# class. Two contractor-ish columns: `contractor_name` (company) and
# `contractor` ("PERSON (COMPANY)") -- prefer the fuller `contractor`, fall back
# to contractor_name. No clean "applied" date column (only downstream workflow
# timestamps), so application_date is left None rather than mislabeling one.
ORLANDO_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permit_number",
    "permit_type": "application_type",
    "status": "application_status",
    "application_date": lambda r: None,  # no clean applied-date column (only workflow timestamps)
    "issue_date": lambda r: _to_datetime(r.get("issue_permit_date")),
    "completion_date": lambda r: None,
    "expiration_date": lambda r: None,
    "contractor": lambda r: r.get("contractor") or r.get("contractor_name"),
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": _orlando_address,
    "parcel_number": "parcel_number",
    "estimated_cost": lambda r: _to_float(r.get("estimated_cost")),
    "valuation": lambda r: _to_float(r.get("estimated_cost")),
    "description": lambda r: r.get("project_name") or r.get("worktype"),
    "work_category": "worktype",
    "square_footage": lambda r: _to_float(r.get("square_footage")),
    "units": lambda r: None,  # confirmed absent
    "latitude": lambda r: _orlando_point(r, 1),
    "longitude": lambda r: _orlando_point(r, 0),
    "permit_url": lambda r: None,
    # property_owner_name has a leading space in the raw feed -- strip it.
    "_owner_name": lambda r: (r.get("property_owner_name") or r.get("parcel_owner_name") or "").strip() or None,
}


def _pg_county_address(rec: dict[str, Any]) -> Optional[str]:
    street = (rec.get("street_address") or "").strip()
    if not street:
        return None
    city = (rec.get("city") or "").strip()
    full = f"{street}, {city}, MD" if city else f"{street}, MD"
    zip_code = (rec.get("zip_code") or "").strip()
    if zip_code:
        full = f"{full} {zip_code}"
    return full


# Prince George's County, MD (~950k pop) -- a new Maryland county (alongside
# Howard, Anne Arundel, Montgomery). 461k+ rows. `expected_construction_cost` is
# the declared project value (no fee column present). No contractor and no
# status column (confirmed). `location` is a text address, not coordinates, and
# there are no lat/lon columns -- Census-geocoder fallback supplies coordinates.
PRINCE_GEORGES_COUNTY_MD_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permit_case_id",
    "permit_type": "permit_type",
    "status": lambda r: None,  # confirmed absent -- no permit-status column
    "application_date": lambda r: None,  # confirmed absent -- only an issuance date exists
    "issue_date": lambda r: _to_datetime(r.get("permit_issuance_date")),
    "completion_date": lambda r: None,
    "expiration_date": lambda r: None,
    "contractor": lambda r: None,  # confirmed absent
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": _pg_county_address,
    "parcel_number": lambda r: None,  # confirmed absent
    "estimated_cost": lambda r: _to_float(r.get("expected_construction_cost")),
    "valuation": lambda r: _to_float(r.get("expected_construction_cost")),
    "description": lambda r: r.get("case_name"),
    "work_category": "permit_category",
    "square_footage": lambda r: None,  # confirmed absent
    "units": lambda r: None,
    "latitude": lambda r: None,  # no coordinate columns -- geocoder fallback
    "longitude": lambda r: None,
    "permit_url": lambda r: None,
}


# City of Somerville, MA (dense inner-core Boston-area city, ~80k pop).
# IMPORTANT fee-vs-valuation finding (live-verified): the `amount` column is the
# permit FEE, not a construction valuation -- sample rows show $278 for a
# roof re-cover and $76 for kitchen cabinets, i.e. fee schedule amounts, not
# job values. This dataset carries NO declared-value column, so
# estimated_cost/valuation are left None rather than mis-mapping the fee (which
# would badly skew budget-tier scoring -- the same class of bug caught for
# Chicago/Tempe/Detroit/Louisville). Direct latitude/longitude columns present.
SOMERVILLE_MA_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "id",
    "permit_type": "type",
    "status": "status",
    "application_date": lambda r: _to_datetime(r.get("application_date")),
    "issue_date": lambda r: _to_datetime(r.get("issue_date")),
    "completion_date": lambda r: None,
    "expiration_date": lambda r: None,
    "contractor": lambda r: None,  # confirmed absent
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": lambda r: (f"{r.get('address').strip()}, Somerville, MA" if r.get("address") else None),
    "parcel_number": lambda r: None,  # confirmed absent
    "estimated_cost": lambda r: None,  # `amount` is a FEE, not a valuation -- see note above
    "valuation": lambda r: None,
    "description": "work",
    "work_category": "type",
    "square_footage": lambda r: None,  # confirmed absent
    "units": lambda r: None,
    "latitude": lambda r: _to_float(r.get("latitude")),
    "longitude": lambda r: _to_float(r.get("longitude")),
    "permit_url": lambda r: None,
}


class SocrataSourceConfig:
    def __init__(
        self,
        key: str,
        domain: str,
        dataset_id: str,
        display_name: str,
        field_map: dict[str, FieldMapValue],
        incremental_date_field: Optional[str] = None,
        select: Optional[str] = None,
    ):
        self.key = key
        self.domain = domain
        self.dataset_id = dataset_id
        self.display_name = display_name
        self.field_map = field_map
        self.incremental_date_field = incremental_date_field
        # Optional explicit SoQL $select. Used by sources whose permit_number
        # is NOT unique per row and which have no natural unique column, so
        # they disambiguate on Socrata's ":id" system row key -- e.g.
        # `"*, :id"`. Left None for the vast majority (default column set).
        # NOTE: `$select=*` drops Socrata *computed* columns (e.g. a geocoding
        # column), so only opt sources in here when `*` still yields every
        # field their mapping reads.
        self.select = select


SOCRATA_SOURCES: dict[str, SocrataSourceConfig] = {
    "sf_building_permits": SocrataSourceConfig(
        key="sf_building_permits",
        domain="data.sfgov.org",
        dataset_id="i98e-djp9",
        display_name="San Francisco Building Permits",
        field_map=SF_BUILDING_PERMITS_MAPPING,
        incremental_date_field="filed_date",
    ),
    "chicago_building_permits": SocrataSourceConfig(
        key="chicago_building_permits",
        domain="data.cityofchicago.org",
        dataset_id="ydr8-5enu",
        display_name="Chicago Building Permits",
        field_map=CHICAGO_BUILDING_PERMITS_MAPPING,
        incremental_date_field="application_start_date",
    ),
    "austin_building_permits": SocrataSourceConfig(
        key="austin_building_permits",
        domain="data.austintexas.gov",
        dataset_id="3syk-w9eu",
        display_name="Austin Issued Construction Permits",
        field_map=AUSTIN_BUILDING_PERMITS_MAPPING,
        incremental_date_field="issue_date",
    ),
    "seattle_building_permits": SocrataSourceConfig(
        key="seattle_building_permits",
        domain="data.seattle.gov",
        dataset_id="76t5-zqzr",
        display_name="Seattle Building Permits",
        field_map=SEATTLE_BUILDING_PERMITS_MAPPING,
        incremental_date_field="issueddate",
    ),
    "dallas_building_permits": SocrataSourceConfig(
        key="dallas_building_permits",
        domain="www.dallasopendata.com",
        dataset_id="e7gq-4sah",
        display_name="Dallas Building Permits",
        field_map=DALLAS_BUILDING_PERMITS_MAPPING,
        incremental_date_field=None,  # issued_date is MM/DD/YY text, not SoQL-filterable as a date
    ),
    "nyc_dob_permits": SocrataSourceConfig(
        key="nyc_dob_permits",
        domain="data.cityofnewyork.us",
        dataset_id="ipu4-2q9a",
        display_name="NYC DOB Issued Permits",
        field_map=NYC_DOB_PERMITS_MAPPING,
        incremental_date_field=None,  # issuance_date is MM/DD/YYYY text, not SoQL-filterable as a date
    ),
    "sonoma_county_permits": SocrataSourceConfig(
        key="sonoma_county_permits",
        domain="data.sonomacounty.ca.gov",
        dataset_id="88ms-k5e7",
        display_name="Sonoma County Construction Permits",
        field_map=SONOMA_COUNTY_PERMITS_MAPPING,
        incremental_date_field="issued",
    ),
    "marin_county_permits": SocrataSourceConfig(
        key="marin_county_permits",
        domain="data.marincounty.gov",
        dataset_id="mkbn-caye",
        display_name="Marin County Building Permits",
        field_map=MARIN_COUNTY_PERMITS_MAPPING,
        incremental_date_field="issued_date",
    ),
    "howard_county_permits": SocrataSourceConfig(
        key="howard_county_permits",
        domain="opendata.howardcountymd.gov",
        dataset_id="kvz2-j5cj",
        display_name="Howard County, MD Permits",
        field_map=HOWARD_COUNTY_PERMITS_MAPPING,
        incremental_date_field="issue_date",
        # permit_number is NOT unique per row and this minimal dataset has no
        # natural unique column, so disambiguate on Socrata's ":id". This
        # dataset has no lat/lon columns anyway, so `$select=*, :id` drops
        # nothing the mapping reads. See BLOCKERS §5i.
        select="*, :id",
    ),
    "baton_rouge_permits": SocrataSourceConfig(
        key="baton_rouge_permits",
        domain="data.brla.gov",
        dataset_id="7fq7-8j7r",
        display_name="East Baton Rouge Parish Building Permits",
        field_map=BATON_ROUGE_PERMITS_MAPPING,
        incremental_date_field="issueddate",
    ),
    "mesa_az_permits": SocrataSourceConfig(
        key="mesa_az_permits",
        domain="citydata.mesaaz.gov",
        dataset_id="dzpk-hxfb",
        display_name="Mesa, AZ Building Permits",
        field_map=MESA_AZ_PERMITS_MAPPING,
        incremental_date_field="issued_date",
    ),
    "cincinnati_permits": SocrataSourceConfig(
        key="cincinnati_permits",
        domain="data.cincinnati-oh.gov",
        dataset_id="uhjb-xac9",
        display_name="Cincinnati Building Permits",
        field_map=CINCINNATI_PERMITS_MAPPING,
        incremental_date_field="issueddate",
        # permitnum is NOT unique (distinct sub-permits -- Wrecking vs
        # Excavation, etc. -- share one number) and this dataset has no
        # natural unique column, so disambiguate on Socrata's ":id".
        # Tradeoff: `$select=*, :id` drops this dataset's *computed* lat/lon
        # columns, so coordinates come from the address geocoder fallback on
        # normal runs (Cincinnati carries street addresses). See BLOCKERS §5i.
        select="*, :id",
    ),
    "gainesville_permits": SocrataSourceConfig(
        key="gainesville_permits",
        domain="data.cityofgainesville.org",
        dataset_id="p798-x3nx",
        display_name="Gainesville, FL Building Permits",
        field_map=GAINESVILLE_PERMITS_MAPPING,
        incremental_date_field="issue",
    ),
    "cook_county_permits": SocrataSourceConfig(
        key="cook_county_permits",
        domain="datacatalog.cookcountyil.gov",
        dataset_id="6yjf-dfxs",
        display_name="Cook County Assessor Permits",
        field_map=COOK_COUNTY_PERMITS_MAPPING,
        incremental_date_field="date_issued",
    ),
    "cambridge_new_construction_permits": SocrataSourceConfig(
        key="cambridge_new_construction_permits",
        domain="data.cambridgema.gov",
        dataset_id="9qm7-wbdc",
        display_name="Cambridge, MA New Construction Building Permits",
        field_map=CAMBRIDGE_NEW_CONSTRUCTION_MAPPING,
        incremental_date_field="issue_date",
    ),
    "framingham_permits": SocrataSourceConfig(
        key="framingham_permits",
        domain="data.framinghamma.gov",
        dataset_id="2vzw-yean",
        display_name="Framingham, MA Building Permits",
        field_map=FRAMINGHAM_PERMITS_MAPPING,
        incremental_date_field=None,  # no issued-date column to filter on (see mapping note)
    ),
    "san_diego_county_permits": SocrataSourceConfig(
        key="san_diego_county_permits",
        domain="internal-sandiegocounty.data.socrata.com",
        dataset_id="dyzh-7eat",
        display_name="San Diego County Construction Permits",
        field_map=SAN_DIEGO_COUNTY_PERMITS_MAPPING,
        incremental_date_field="issued_date",
    ),
    "nj_statewide_permits": SocrataSourceConfig(
        key="nj_statewide_permits",
        domain="data.nj.gov",
        dataset_id="w9se-dmra",
        display_name="New Jersey Statewide Construction Permits",
        field_map=NJ_STATEWIDE_PERMITS_MAPPING,
        incremental_date_field=None,  # permitdate field type isn't reliably SoQL-comparable across the whole feed
    ),
    "new_orleans_permits": SocrataSourceConfig(
        key="new_orleans_permits",
        domain="data.nola.gov",
        dataset_id="nbcf-m6c2",
        display_name="New Orleans Building Permits",
        field_map=NEW_ORLEANS_PERMITS_MAPPING,
        incremental_date_field=None,  # issuedate format not consistently SoQL-filterable
    ),
    "honolulu_permits": SocrataSourceConfig(
        key="honolulu_permits",
        domain="data.honolulu.gov",
        dataset_id="3fr8-2hnx",
        display_name="Honolulu Building Permits (2010-2016)",
        field_map=HONOLULU_PERMITS_MAPPING,
        incremental_date_field="issuedate",
    ),
    "norfolk_permits": SocrataSourceConfig(
        key="norfolk_permits",
        domain="data.norfolk.gov",
        dataset_id="fahm-yuh4",
        display_name="Norfolk, VA Permits",
        field_map=NORFOLK_PERMITS_MAPPING,
        incremental_date_field="issue_date",
    ),
    "kansas_city_mo_permits": SocrataSourceConfig(
        key="kansas_city_mo_permits",
        domain="data.kcmo.org",
        dataset_id="ntw8-aacc",
        display_name="Kansas City, MO Permits",
        field_map=KANSAS_CITY_MO_PERMITS_MAPPING,
        incremental_date_field="issueddate",
    ),
    "montgomery_county_md_permits": SocrataSourceConfig(
        key="montgomery_county_md_permits",
        domain="data.montgomerycountymd.gov",
        dataset_id="xfxj-qszi",
        display_name="Montgomery County, MD Residential Permits",
        field_map=MONTGOMERY_COUNTY_MD_PERMITS_MAPPING,
        incremental_date_field="issueddate",
    ),
    # --- Sixth pass: population-driven expansion (verified live this pass) ---
    "orlando_permits": SocrataSourceConfig(
        key="orlando_permits",
        domain="data.cityoforlando.net",
        dataset_id="ryhf-m453",
        display_name="Orlando, FL Permit Applications",
        field_map=ORLANDO_PERMITS_MAPPING,
        incremental_date_field="issue_permit_date",
    ),
    "prince_georges_county_md_permits": SocrataSourceConfig(
        key="prince_georges_county_md_permits",
        domain="data.princegeorgescountymd.gov",
        dataset_id="weik-ttee",
        display_name="Prince George's County, MD Permits",
        field_map=PRINCE_GEORGES_COUNTY_MD_PERMITS_MAPPING,
        incremental_date_field="permit_issuance_date",
    ),
    "somerville_ma_permits": SocrataSourceConfig(
        key="somerville_ma_permits",
        domain="data.somervillema.gov",
        dataset_id="vxgw-vmky",
        display_name="Somerville, MA Permits",
        field_map=SOMERVILLE_MA_PERMITS_MAPPING,
        incremental_date_field="issue_date",
    ),
}


class SocrataConnector(PermitConnector):
    source_system = "socrata"

    def __init__(self, config: SocrataSourceConfig, app_token: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT):
        self.config = config
        self.app_token = app_token or os.environ.get("SOCRATA_APP_TOKEN")
        self.timeout = timeout

    @property
    def resource_url(self) -> str:
        return f"https://{self.config.domain}/resource/{self.config.dataset_id}.json"

    def _headers(self) -> dict[str, str]:
        headers = {}
        if self.app_token:
            headers["X-App-Token"] = self.app_token
        return headers

    def discover(self) -> ConnectorInfo:
        resp = httpx.get(
            self.resource_url,
            params={"$limit": 1},
            headers=self._headers(),
            timeout=self.timeout,
        )
        resp.raise_for_status()
        records = resp.json()
        fields = sorted(records[0].keys()) if records else []
        return ConnectorInfo(
            source_system=self.source_system,
            identifier=f"{self.config.domain}/{self.config.dataset_id}",
            display_name=self.config.display_name,
            record_count=None,
            fields=fields,
            extra={"resource_url": self.resource_url},
        )

    def fetch_permits(self, since: Optional[datetime] = None, limit: Optional[int] = None) -> Iterable[dict]:
        remaining = limit
        offset = 0
        while True:
            page_size = DEFAULT_PAGE_SIZE if remaining is None else min(DEFAULT_PAGE_SIZE, remaining)
            if page_size <= 0:
                break

            params: dict[str, Any] = {"$limit": page_size, "$offset": offset, "$order": ":id"}
            if self.config.select:
                params["$select"] = self.config.select
            if since is not None and self.config.incremental_date_field:
                iso = since.strftime("%Y-%m-%dT%H:%M:%S")
                params["$where"] = f"{self.config.incremental_date_field} >= '{iso}'"

            resp = _request_with_backoff(
                self.resource_url, params=params, headers=self._headers(), timeout=self.timeout
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break

            for raw in batch:
                yield self._map_record(raw)

            offset += len(batch)
            if remaining is not None:
                remaining -= len(batch)
            if len(batch) < page_size:
                break

    def _map_record(self, raw: dict[str, Any]) -> dict:
        normalized = self.normalized_stub()
        for field_name, mapper in self.config.field_map.items():
            if callable(mapper):
                normalized[field_name] = mapper(raw)
            else:
                normalized[field_name] = raw.get(mapper)
        normalized["source"] = f"socrata:{self.config.domain}:{self.config.dataset_id}"
        normalized["raw_data"] = raw
        return normalized
