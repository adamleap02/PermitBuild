"""
Generic connector for ArcGIS REST FeatureServer/MapServer layers.

The ArcGIS REST `/query` endpoint (with `f=json`) is free and public
for any layer an agency has published without auth -- no key required.
This connector works against any such layer given its service URL plus
a per-source field-mapping config (ArcGIS/Accela-style schemas vary
layer to layer just like Socrata datasets vary column to column).

Live-verified example wired up below:

  * ARCGIS_SOURCES["tempe_az_building_permits"] -- City of Tempe, AZ
    Building Permits layer (Accela Civic Platform export via ArcGIS
    Hub): https://services.arcgis.com/lQySeXwbBg53XWDi/arcgis/rest/services/building_permits/FeatureServer/0

Two other ArcGIS FeatureServer permit layers were also probed and
responded live (services6.arcgis.com/.../Building_Permits and
services.arcgis.com/v400IkDOw1ad7Yad/.../Building_Permits_Pending);
Tempe's was chosen as the primary example because it exposes clean,
directly-typed Latitude/Longitude/EstProjectCost fields. See
BLOCKERS.md for notes on the others.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional, Union

import httpx

from app.connectors.base import ConnectorInfo, PermitConnector

logger = logging.getLogger(__name__)

FieldMapValue = Union[str, Callable[[dict[str, Any]], Any]]

DEFAULT_TIMEOUT = 60.0
# ArcGIS FeatureServers cap each query at the layer's maxRecordCount
# (commonly 1,000-2,000). Requesting 2,000 and paging on resultOffset --
# terminating on the server's own `exceededTransferLimit` flag rather than a
# naive "short page" heuristic -- correctly walks the entire layer even when
# the server silently truncates a larger requested page.
DEFAULT_PAGE_SIZE = 2000


def _request_with_backoff(
    url: str,
    *,
    params: dict[str, Any],
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = 5,
) -> httpx.Response:
    """GET with exponential back-off on HTTP 429 / transient 5xx, respecting
    Retry-After -- polite to free public ArcGIS services on big pulls."""
    import time

    delay = 2.0
    for attempt in range(max_retries):
        resp = httpx.get(url, params=params, timeout=timeout)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == max_retries - 1:
                resp.raise_for_status()
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if (retry_after and retry_after.isdigit()) else delay
            logger.warning("ArcGIS %s on %s; backing off %.1fs (attempt %d)", resp.status_code, url, wait, attempt + 1)
            time.sleep(wait)
            delay = min(delay * 2, 60.0)
            continue
        return resp
    return resp  # pragma: no cover


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


def _esri_epoch_to_datetime(value: Any) -> Optional[datetime]:
    """ArcGIS date fields are epoch milliseconds (UTC) when returned as f=json."""
    if value in (None, ""):
        return None
    try:
        millis = float(value)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def _esri_flexible_date(value: Any) -> Optional[datetime]:
    """
    Most ArcGIS date fields are epoch-millis (see above), but some layers
    (e.g. Miami-Dade's `esriFieldTypeDateOnly` columns) return a plain
    "YYYY-MM-DD" string instead, and a few "date-ish" fields are typed as
    plain esriFieldTypeString and may be blank or oddly formatted. Try
    epoch first, then a couple of plain-string formats, else give up
    quietly rather than raising -- confirmed necessary by hitting
    Miami-Dade's live layer during development (PermitIssuedDate came back
    as "2024-07-24", not an epoch number).
    """
    if value in (None, ""):
        return None
    epoch_result = _esri_epoch_to_datetime(value)
    if epoch_result is not None:
        return epoch_result
    text = str(value)
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _first_not_none(*values: Any) -> Any:
    """Zero-safe fallback chain -- see the identical helper (and the bug it
    fixes) in app/connectors/socrata.py."""
    for v in values:
        if v is not None:
            return v
    return None


def _tempe_address(attrs: dict[str, Any]) -> Optional[str]:
    parts = [attrs.get("OriginalAddress1"), attrs.get("OriginalAddress2")]
    street = " ".join(p for p in parts if p)
    tail = " ".join(p for p in (attrs.get("OriginalCity"), attrs.get("OriginalState")) if p)
    full = street
    if tail:
        full = f"{full}, {tail}"
    if attrs.get("OriginalZip"):
        full = f"{full} {attrs['OriginalZip']}"
    return full or None


TEMPE_AZ_BUILDING_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "PermitNum",
    "permit_type": "PermitTypeDesc",
    "status": "StatusCurrent",
    "application_date": lambda a: _esri_epoch_to_datetime(a.get("AppliedDateDtm")),
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("IssuedDateDtm")),
    "completion_date": lambda a: _esri_epoch_to_datetime(a.get("CompletedDateDtm")),
    "expiration_date": lambda a: _esri_epoch_to_datetime(a.get("ExpiresDateDtm")),
    "contractor": "ContractorCompanyName",
    "builder": lambda a: None,
    "architect": lambda a: None,  # confirmed absent from this layer's field list
    "engineer": lambda a: None,  # confirmed absent
    "property_address": _tempe_address,
    "parcel_number": lambda a: None,  # confirmed absent (no APN/parcel column on this layer)
    "estimated_cost": lambda a: _to_float(a.get("EstProjectCost")),
    # Bug fix: `Fee` is the permit FEE (what the city charged), not the
    # project valuation -- was previously mis-mapped here, same class of
    # bug found in Chicago's original mapping. EstProjectCost is the
    # correct declared-value field; there's no separate "revised" cost on
    # this layer so both estimated_cost/valuation use it.
    "valuation": lambda a: _to_float(a.get("EstProjectCost")),
    "description": "Description",
    "work_category": "PermitClass",
    "square_footage": lambda a: _to_float(a.get("TotalSqFt")),
    "units": lambda a: _to_int(a.get("HousingUnits")),
    "latitude": lambda a: _to_float(a.get("Latitude")),
    "longitude": lambda a: _to_float(a.get("Longitude")),
    "permit_url": lambda a: None,  # confirmed absent
}


def _geometry_lat(attrs: dict[str, Any]) -> Optional[float]:
    geom = attrs.get("_geometry") or {}
    return _to_float(geom.get("y"))


def _geometry_lon(attrs: dict[str, Any]) -> Optional[float]:
    geom = attrs.get("_geometry") or {}
    return _to_float(geom.get("x"))


def _raleigh_address(attrs: dict[str, Any]) -> Optional[str]:
    parts = [
        attrs.get("streetnum"),
        attrs.get("streetdirectionprefix"),
        attrs.get("streetname"),
        attrs.get("streettype"),
    ]
    street = " ".join(p.strip() for p in parts if p and str(p).strip())
    if not street:
        return None
    # originalcity/originalstate are frequently blank in this layer even
    # though every record is a City of Raleigh, NC permit -- fall back to
    # the known jurisdiction so the Census-geocoder fallback in
    # app/ingest.py has a fighting chance at a match.
    city = (attrs.get("originalcity") or "RALEIGH").strip() or "RALEIGH"
    state = (attrs.get("originalstate") or "NC").strip() or "NC"
    full = f"{street}, {city}, {state}"
    zip_code = (attrs.get("originalzip") or "").strip()
    if zip_code:
        full = f"{full} {zip_code}"
    return full


# Raleigh, NC publishes via the same "Building and Land Development
# Specification (BLDS)"-flavored schema as several other Esri-centric cities
# (lowercase field names), distinct from Tempe's PascalCase Accela export --
# same underlying idea (national permit data standard), different casing per
# city's ETL, so each still needs its own mapping config.
RALEIGH_NC_BUILDING_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permitnum",
    "permit_type": "permittypemapped",
    "status": "statuscurrentmapped",
    "application_date": lambda a: _esri_epoch_to_datetime(a.get("applieddate")),
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("issueddate")),
    "completion_date": lambda a: _esri_epoch_to_datetime(a.get("cocissueddate")),
    "expiration_date": lambda a: _esri_epoch_to_datetime(a.get("expiresdate")),
    "contractor": "contractorcompanyname",
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _raleigh_address,
    "parcel_number": "pin",
    "estimated_cost": lambda a: _to_float(a.get("estprojectcost")),
    "valuation": lambda a: _to_float(a.get("estprojectcost")),
    "description": lambda a: a.get("description") or a.get("proposedworkdescription"),
    "work_category": lambda a: a.get("workclassmapped") or a.get("permitclassmapped"),
    "square_footage": lambda a: _to_float(a.get("totalsqft")),
    "units": lambda a: _to_int(a.get("housingunitstotal")),
    # This layer's latitude_perm/longitude_perm columns are frequently blank
    # (see sample records pulled live) -- left as direct-column lookups so
    # the ingest pipeline's Census-geocoder fallback fills gaps from
    # property_address, same live-fallback path exercised by Dallas.
    "latitude": lambda a: _to_float(a.get("latitude_perm")),
    "longitude": lambda a: _to_float(a.get("longitude_perm")),
    "permit_url": lambda a: None,
}


def _denver_status(attrs: dict[str, Any]) -> Optional[str]:
    if attrs.get("CANCEL"):
        return "cancelled"
    if attrs.get("FINAL_DATE"):
        return "finaled"
    return "issued"


# City & County of Denver's residential construction permits layer uses its
# own bespoke (non-BLDS) schema exported from Denver's Accela instance, and
# -- unlike Tempe/Raleigh -- carries no direct latitude/longitude attribute
# columns at all; coordinates only exist in the feature's geometry, so this
# mapping reads from the "_geometry" key the connector injects (see
# ArcGISConnector.fetch_permits below).
DENVER_RESIDENTIAL_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "PERMIT_NUM",
    "permit_type": "CLASS",
    "status": _denver_status,
    "application_date": lambda a: _esri_epoch_to_datetime(a.get("DATE_RECEIVED")),
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("DATE_ISSUED")),
    "completion_date": lambda a: _esri_epoch_to_datetime(a.get("FINAL_DATE")),
    "expiration_date": lambda a: None,
    "contractor": "CONTRACTOR_NAME",
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": lambda a: (a.get("ADDRESS") or "").strip() or None,
    "parcel_number": "SCHEDNUM",
    "estimated_cost": lambda a: _to_float(a.get("VALUATION")),
    "valuation": lambda a: _to_float(a.get("VALUATION")),
    "description": "CLASS",
    "work_category": "CLASS",
    "square_footage": lambda a: None,
    "units": lambda a: _to_int(a.get("UNITS")),
    "latitude": _geometry_lat,
    "longitude": _geometry_lon,
    "permit_url": lambda a: None,
}


DC_BUILDING_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "PERMIT_ID",
    "permit_type": lambda a: a.get("PERMIT_SUBTYPE_NAME") or a.get("PERMIT_TYPE_NAME"),
    "status": "APPLICATION_STATUS_NAME",
    "application_date": lambda a: None,
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("ISSUE_DATE")),
    "completion_date": lambda a: None,
    "expiration_date": lambda a: None,
    "contractor": "PERMIT_APPLICANT",
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": "FULL_ADDRESS",
    "parcel_number": "SSL",
    # DC's public permit-issuance feed exposes FEES_PAID (a permit fee) but
    # not a project valuation/cost figure -- deliberately NOT mapped into
    # estimated_cost/valuation since a permit fee is not a project value and
    # would badly mislead the budget-tier scoring (fees are a tiny fraction
    # of project cost). Left None rather than fabricating a number.
    "estimated_cost": lambda a: None,
    "valuation": lambda a: None,
    "description": "DESC_OF_WORK",
    "work_category": lambda a: a.get("PERMIT_CATEGORY_NAME") or a.get("PERMIT_TYPE_NAME"),
    "square_footage": lambda a: None,
    "units": lambda a: None,
    "latitude": lambda a: _to_float(a.get("LATITUDE")),
    "longitude": lambda a: _to_float(a.get("LONGITUDE")),
    "permit_url": lambda a: None,
}


# ---------------------------------------------------------------------------
# Second data-gathering pass -- 2 more real, live-verified ArcGIS sources
# (both counties), added alongside the 13 new Socrata sources above.
# ---------------------------------------------------------------------------


_PLACEHOLDER_VALUES = {"not listed", "n/a", "na", "none", "unknown", "tbd", ""}


def _clean_placeholder(value: Any) -> Optional[str]:
    """Miami-Dade's feed uses literal placeholder text like "NOT LISTED"
    instead of leaving fields null -- strip those out rather than storing
    junk strings in contractor/architect/owner fields."""
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _PLACEHOLDER_VALUES:
        return None
    return text


def _miami_dade_address(attrs: dict[str, Any]) -> Optional[str]:
    parts = [attrs.get("PropertyAddress"), attrs.get("City"), attrs.get("State")]
    addr = " ".join(p for p in parts if p)
    return addr or None


# Miami-Dade's permit feed is published as an ArcGIS "Table" (no geometry
# at all, confirmed via the live service root -- `"tables":[...]`, empty
# `"layers":[]`), so there is no lat/lon to read even indirectly from
# geometry; the Census-geocoder fallback in app/ingest.py is the only path
# to coordinates for this source. Also note: this feed is genuinely rich
# with OwnerName -- see `owner_name` handling in the connector class below
# and app/ingest.py's `_owner_name` convention.
MIAMI_DADE_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "PermitNumber",
    "permit_type": lambda a: a.get("ApplicationTypeDescription") or a.get("PermitType"),
    "status": lambda a: None,  # confirmed absent -- no status column on this table
    "application_date": lambda a: _esri_flexible_date(a.get("ApplicationDate")),
    "issue_date": lambda a: _esri_flexible_date(a.get("PermitIssuedDate")),
    "completion_date": lambda a: _esri_flexible_date(a.get("CoCcDate")),
    "expiration_date": lambda a: None,  # confirmed absent
    "contractor": lambda a: _clean_placeholder(a.get("ContractorName")),
    "builder": lambda a: None,
    "architect": lambda a: _clean_placeholder(a.get("ArchitectName")),
    "engineer": lambda a: None,
    "property_address": _miami_dade_address,
    "parcel_number": "FolioNumber",
    "estimated_cost": lambda a: _to_float(a.get("EstimatedValue")),
    "valuation": lambda a: _to_float(a.get("EstimatedValue")),
    "description": lambda a: a.get("DetailDescriptionComments") or a.get("ProposedUseDescription"),
    "work_category": "ProposedUseDescription",
    "square_footage": lambda a: _to_float(a.get("SquareFootage")),
    "units": lambda a: _to_int(a.get("StructureUnits")),
    "latitude": lambda a: None,  # confirmed absent (Table type, no geometry) -- geocoder fallback applies
    "longitude": lambda a: None,
    "permit_url": lambda a: None,
    # Bonus (non-schema) key: consumed by app/ingest.py to populate the
    # Owner model, tied to the resolved Property, when present.
    "_owner_name": lambda a: _clean_placeholder(a.get("OwnerName")),
}


def _mecklenburg_owner_name(attrs: dict[str, Any]) -> Optional[str]:
    return attrs.get("ownname")


MECKLENBURG_COUNTY_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permitnum",
    "permit_type": "permittype",
    "status": "permitstat",
    "application_date": lambda a: None,  # confirmed absent -- no received/applied date field on this layer
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("issuedate")),
    "completion_date": lambda a: _esri_epoch_to_datetime(a.get("compldate")),
    "expiration_date": lambda a: None,  # confirmed absent
    "contractor": lambda a: None,  # confirmed absent -- only owner-of-record fields exist, not a contractor
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": "projadd",
    "parcel_number": "parcelnum",
    "estimated_cost": lambda a: _to_float(a.get("bldgcost")),
    "valuation": lambda a: _to_float(a.get("bldgcost")),
    "description": lambda a: a.get("workdesc") or a.get("projdesc"),
    "work_category": "worktype",
    "square_footage": lambda a: _to_float(a.get("totalsqft")),
    "units": lambda a: _to_int(a.get("numunits")),
    "latitude": _geometry_lat,
    "longitude": _geometry_lon,
    "permit_url": lambda a: None,
    "_owner_name": _mecklenburg_owner_name,
}


# ---------------------------------------------------------------------------
# Fourth data-gathering pass -- national-breadth expansion. 8 more real,
# live-verified ArcGIS sources found via a mix of the ArcGIS Online search
# API and checking each jurisdiction's OWN .gov site directly (several of
# these -- Nashville, Portland, Albuquerque, Boise -- did NOT surface via
# generic "building permits <city>" ArcGIS searches and were only found by
# following each city's own open-data/GIS site).
# ---------------------------------------------------------------------------


def _minneapolis_address(attrs: dict[str, Any]) -> Optional[str]:
    display = attrs.get("Display")
    if not display:
        return None
    return f"{display}, Minneapolis, MN"


MINNEAPOLIS_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permitNumber",
    "permit_type": "permitType",
    "status": "status",
    "application_date": lambda a: None,  # confirmed absent -- only issueDate/completeDate exist
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("issueDate")),
    "completion_date": lambda a: _esri_epoch_to_datetime(a.get("completeDate")),
    "expiration_date": lambda a: None,
    "contractor": "applicantName",
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _minneapolis_address,
    "parcel_number": "APN",
    "estimated_cost": lambda a: _to_float(a.get("value")),
    "valuation": lambda a: _to_float(a.get("value")),
    "description": lambda a: a.get("comments") or a.get("workType"),
    "work_category": "workType",
    "square_footage": lambda a: None,
    "units": lambda a: _to_int(a.get("dwellingUnitsNew")),
    "latitude": lambda a: _to_float(a.get("Latitude")),
    "longitude": lambda a: _to_float(a.get("Longitude")),
    "permit_url": lambda a: None,
}


def _philadelphia_address(attrs: dict[str, Any]) -> Optional[str]:
    addr = attrs.get("address")
    if not addr:
        return None
    full = f"{addr}, Philadelphia, PA"
    if attrs.get("zip"):
        full = f"{full} {attrs['zip']}"
    return full


# NOTE on provenance: this ArcGIS item is titled "PERMITS_BuildingZoning_CPCDC"
# and owned by an account suggesting Milwaukee (found while searching for
# Milwaukee permit data) -- but the field names (`opa_accoun`, `opa_owner` --
# OPA is Philadelphia's Office of Property Assessment) and every sampled
# record's address/zip/council-district are unambiguously Philadelphia, PA,
# confirmed by pulling multiple pages of live records (all 191xx zips, real
# Philly streets). Labeled correctly as Philadelphia here rather than trusting
# the misleading service name -- exactly the live-data-verification discipline
# this project has followed throughout. This is also a genuine, real,
# per-record permit dataset for Philadelphia, which earlier in this project's
# research only turned up an aggregated hex-bin dataset for the same city.
PHILADELPHIA_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "permitnumb",
    "permit_type": "permittype",
    "status": "status",
    "application_date": lambda a: None,  # confirmed absent -- only an issue-ish date and a "most recent" date exist
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("permitissu")),
    "completion_date": lambda a: None,
    "expiration_date": lambda a: None,
    "contractor": "contractor",
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _philadelphia_address,
    "parcel_number": "opa_accoun",
    "estimated_cost": lambda a: None,  # confirmed absent -- no valuation/cost column on this layer
    "valuation": lambda a: None,
    "description": lambda a: a.get("permitdesc") or a.get("typeofwork"),
    "work_category": "typeofwork",
    "square_footage": lambda a: None,
    "units": lambda a: None,
    "latitude": _geometry_lat,
    "longitude": _geometry_lon,
    "permit_url": lambda a: None,
    "_owner_name": "opa_owner",
}


SIOUX_FALLS_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "PERMITNUMBER",
    "permit_type": "PERMITTYPE",
    "status": "PERMITSTATUS",
    "application_date": lambda a: _esri_epoch_to_datetime(a.get("APPLYDATE")),
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("ISSUEDATE")),
    "completion_date": lambda a: _esri_epoch_to_datetime(a.get("FINALIZEDATE")),
    "expiration_date": lambda a: None,
    "contractor": "contractor_name",
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": "MAINADDRESS",  # already a full "street, city, state zip" string
    "parcel_number": lambda a: None,  # confirmed absent
    "estimated_cost": lambda a: _to_float(a.get("VALUATION")),
    "valuation": lambda a: _to_float(a.get("VALUATION")),
    "description": "WORKCLASS",
    "work_category": "WORKCLASS",
    "square_footage": lambda a: None,
    "units": lambda a: _to_int(a.get("DwellingUnits")),
    "latitude": _geometry_lat,
    "longitude": _geometry_lon,
    "permit_url": lambda a: None,
}


def _nashville_address(attrs: dict[str, Any]) -> Optional[str]:
    parts = [attrs.get("Address"), attrs.get("City"), attrs.get("State")]
    addr = " ".join(p for p in parts if p)
    if attrs.get("ZIP"):
        addr = f"{addr} {attrs['ZIP']}"
    return addr or None


NASHVILLE_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "Permit__",
    "permit_type": "Permit_Type_Description",
    # Confirmed absent: no distinct status column on this layer -- Nashville's
    # own permit-status concept isn't exposed here, only open/entered dates.
    "status": lambda a: None,
    "application_date": lambda a: _esri_epoch_to_datetime(a.get("Date_Entered")),
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("Date_Issued")),
    "completion_date": lambda a: None,
    "expiration_date": lambda a: None,
    "contractor": "Contact",
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _nashville_address,
    "parcel_number": "Parcel",
    "estimated_cost": lambda a: _to_float(a.get("Const_Cost")),
    "valuation": lambda a: _to_float(a.get("Const_Cost")),
    "description": "Purpose",
    "work_category": "Permit_Subtype_Description",
    "square_footage": lambda a: None,
    "units": lambda a: None,
    "latitude": lambda a: _to_float(a.get("Lat")),
    "longitude": lambda a: _to_float(a.get("Lon")),
    "permit_url": lambda a: None,
}


def _boise_address(attrs: dict[str, Any]) -> Optional[str]:
    parts = [attrs.get("PropertyAddress"), attrs.get("PropertyCityStateZip")]
    addr = " ".join(p for p in parts if p)
    return addr or None


# Boise's open dataset is scoped to new residential construction/demolition
# tracking specifically -- confirmed via live metadata that it carries no
# contractor or valuation/cost columns at all (those live in Boise's separate
# Accela permit-search system, not this open-data extract).
BOISE_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "RecordID",
    "permit_type": lambda a: a.get("ResidentialType") or a.get("ResidentialSubtype"),
    "status": "PermitStatus",
    "application_date": lambda a: _esri_flexible_date(a.get("ReceiveDate")),
    "issue_date": lambda a: _esri_flexible_date(a.get("IssuedDate")),
    "completion_date": lambda a: _esri_flexible_date(a.get("FinaledDate")),
    "expiration_date": lambda a: None,
    "contractor": lambda a: None,  # confirmed absent
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _boise_address,
    "parcel_number": lambda a: None,  # confirmed absent
    "estimated_cost": lambda a: None,  # confirmed absent
    "valuation": lambda a: None,
    "description": "RecordName",
    "work_category": "ResidentialSubtype",
    "square_footage": lambda a: None,
    "units": lambda a: _to_int(a.get("Units")),
    "latitude": _geometry_lat,
    "longitude": _geometry_lon,
    "permit_url": lambda a: None,
}


ATLANTA_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "RECORD_ID",
    "permit_type": "RECORD_TYPE",
    "status": "STATUS",
    # DATE_OPENED_ORIGINAL/DATE_OPENED are the closest fields to
    # application/issue dates on this layer -- Atlanta's own permit
    # lifecycle doesn't expose a cleanly separate "issued" date here, so
    # this pairing is a best-effort approximation, not a confirmed
    # application-vs-issuance distinction.
    "application_date": lambda a: _esri_flexible_date(a.get("DATE_OPENED_ORIGINAL")),
    "issue_date": lambda a: _esri_flexible_date(a.get("DATE_OPENED")),
    "completion_date": lambda a: None,
    "expiration_date": lambda a: None,
    "contractor": lambda a: None,  # confirmed absent
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": "ADDR_FULL_LINE",  # already a full "street, city, state zip" string
    "parcel_number": "PARCEL_NBR",
    "estimated_cost": lambda a: _to_float(a.get("JOB_VALUE")),
    "valuation": lambda a: _to_float(a.get("JOB_VALUE")),
    "description": "RECORD_NAME",
    "work_category": lambda a: a.get("RECORD_TYPE_GROUP") or a.get("RECORD_TYPE_TYPE"),
    "square_footage": lambda a: None,
    "units": lambda a: None,
    "latitude": lambda a: _to_float(a.get("Latitude")),
    "longitude": lambda a: _to_float(a.get("Longitude")),
    "permit_url": lambda a: None,
}


ALBUQUERQUE_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "PermitNumber",
    "permit_type": lambda a: a.get("GeneralCategory") or a.get("TypeofWork"),
    "status": lambda a: None,  # confirmed absent -- no status column on this layer
    "application_date": lambda a: _esri_epoch_to_datetime(a.get("DateEntered")),
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("DateIssued")),
    "completion_date": lambda a: None,
    "expiration_date": lambda a: None,
    "contractor": "Contractor",
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": lambda a: a.get("CalculatedAddress") or a.get("FreeFormAddress"),
    "parcel_number": lambda a: None,  # confirmed absent
    "estimated_cost": lambda a: _to_float(a.get("Valuation")),
    "valuation": lambda a: _to_float(a.get("Valuation")),
    "description": "WorkDescription",
    "work_category": "TypeofWork",
    "square_footage": lambda a: _to_float(a.get("SquareFootage")),
    "units": lambda a: _to_int(a.get("NumberofUnits")),
    "latitude": _geometry_lat,
    "longitude": _geometry_lon,
    "permit_url": lambda a: None,
    "_owner_name": "Owner",
}


def _portland_address(attrs: dict[str, Any]) -> Optional[str]:
    addr = attrs.get("PROP_ADDRE")
    if not addr:
        return None
    return f"{addr}, Portland, OR"


# Portland's X_COORD/Y_COORD columns are in Oregon State Plane feet, not
# WGS84 lat/lon -- coordinates are read from the query's geometry (requested
# in WGS84 via outSR=4326, same as Denver/Mecklenburg/Philadelphia) instead.
PORTLAND_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "FOLDERNUMB",
    "permit_type": lambda a: a.get("NEWTYPE") or a.get("NEWCLASS"),
    "status": "STATUS",
    "application_date": lambda a: _esri_epoch_to_datetime(a.get("INDATE")),
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("ISSUEDATE")),
    "completion_date": lambda a: None,
    "expiration_date": lambda a: None,
    "contractor": lambda a: None,  # confirmed absent
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _portland_address,
    "parcel_number": "PROPGISID1",
    "estimated_cost": lambda a: _to_float(a.get("VALUATION")),
    "valuation": lambda a: _to_float(a.get("VALUATION")),
    "description": lambda a: a.get("FOLDER_DES") or a.get("WORKDESC"),
    "work_category": "NEWCLASS",
    "square_footage": lambda a: _to_float(a.get("SQFT")),
    "units": lambda a: _to_int(a.get("NEW_UNITS")),
    "latitude": _geometry_lat,
    "longitude": _geometry_lon,
    "permit_url": lambda a: None,
}


def _helena_parcel(attrs: dict[str, Any]) -> Optional[str]:
    # Stored as esriFieldTypeDouble (e.g. 5.18882832207E+15) -- format as a
    # plain integer string rather than scientific notation.
    raw = attrs.get("Parcel_Number")
    if raw in (None, ""):
        return None
    try:
        return str(int(float(raw)))
    except (TypeError, ValueError):
        return str(raw)


def _helena_address(attrs: dict[str, Any]) -> Optional[str]:
    # Match_addr is the geocoder-cleaned "street, city, state, zip" version;
    # prefer it over the raw multi-line Address field.
    return attrs.get("Match_addr") or attrs.get("Address")


# Found via a Fulton County, GA GIS research detour (searching ArcGIS Online
# for "All Building Permits" surfaced this Helena, MT layer under an
# unrelated-looking owner account "tgoodrich_hlna") -- confirmed live by
# checking the actual sampled records' City/State fields (HELENA, MT), not
# assumed from the owner name alone.
HELENA_MT_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "Permit_Number",
    "permit_type": "Permit_Type",
    "status": "Permit_Status",
    "application_date": lambda a: _esri_epoch_to_datetime(a.get("Permit_Application_Date")),
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("Permit_Issue_Date")),
    "completion_date": lambda a: _esri_epoch_to_datetime(a.get("Permit_Finaled_Date")),
    "expiration_date": lambda a: None,  # confirmed absent
    "contractor": lambda a: None,  # confirmed absent
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _helena_address,
    "parcel_number": _helena_parcel,
    "estimated_cost": lambda a: _to_float(a.get("Permit_Valuation")),
    "valuation": lambda a: _to_float(a.get("Permit_Valuation")),
    "description": "Permit_Work_Class",
    "work_category": "Permit_Work_Class",
    "square_footage": lambda a: None,
    "units": lambda a: None,
    "latitude": _geometry_lat,
    "longitude": _geometry_lon,
    "permit_url": lambda a: None,
}


# ---------------------------------------------------------------------------
# Fifth data-gathering pass -- Wave A of research/EXPANSION_PLAN.md: six more
# real, live-verified ArcGIS sources, each queried directly this pass (field
# lists + record counts below are real, not estimated). Adds MI and KY as new
# states and materially raises total population coverage (Fort Worth, Columbus,
# Las Vegas city, Detroit, Louisville Metro, Tucson).
# ---------------------------------------------------------------------------


def _fort_worth_address(attrs: dict[str, Any]) -> Optional[str]:
    # `Address` is a bare street ("2925 BIG HORN BLUFF CT") -- Fort Worth is a
    # single city, so append city/state and the dataset's own Zip_Code to give
    # the Census-geocoder fallback enough to match against.
    street = (attrs.get("Address") or "").strip()
    if not street:
        return None
    full = f"{street}, Fort Worth, TX"
    zip_code = (attrs.get("Zip_Code") or "").strip()
    if zip_code:
        full = f"{full} {zip_code}"
    return full


def _fort_worth_work_category(attrs: dict[str, Any]) -> Optional[str]:
    # Use_Type/Specific_Use describe the building use; Permit_Category is often
    # the literal string "NA". Prefer the real use, fall back to sub-type.
    return attrs.get("Use_Type") or attrs.get("Specific_Use") or attrs.get("Permit_SubType")


# City of Fort Worth, TX -- self-hosted ArcGIS (mapit.fortworthtexas.gov), the
# highest single-source record count found this pass (756k). JobValue is the
# declared project value; the dataset carries no separate permit-fee column to
# confuse it with. Owner_Full_Name is real public-record owner-of-record data
# (wired to the Owner model via the _owner_name bonus key). Direct
# Latitude/Longitude columns present.
def _fort_worth_permit_number(attrs: dict[str, Any]) -> Optional[str]:
    # LIVE-VERIFIED: `Permit_No` is NOT unique per row -- the same value
    # appears on genuinely-distinct rows (e.g. PE16-00020 at two different
    # addresses: 3844 HEYWOOD AVE and 4128 ANITA AVE). CAPID is the layer's
    # unique object id (1000/1000 distinct, never null in a live sample), so
    # suffix it -- same pattern as Cook County (PIN) / San Antonio (_id).
    base = attrs.get("Permit_No")
    if not base or not str(base).strip():
        return None
    capid = attrs.get("CAPID")
    return f"{str(base).strip()}-{capid}" if capid not in (None, "") else str(base).strip()


FORT_WORTH_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": _fort_worth_permit_number,
    "permit_type": "Permit_Type",
    "status": "Current_Status",
    # File_Date is the filing/application date; this feed has no distinct
    # "issued" date column (only File_Date and a generic Status_Date), so
    # issue_date is left None rather than mis-labeling the status-change date.
    "application_date": lambda a: _esri_epoch_to_datetime(a.get("File_Date")),
    "issue_date": lambda a: None,  # confirmed absent -- no dedicated issued-date column
    "completion_date": lambda a: None,
    "expiration_date": lambda a: None,
    "contractor": lambda a: None,  # confirmed absent -- only owner-of-record, no contractor column
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _fort_worth_address,
    "parcel_number": lambda a: None,  # confirmed absent -- only lot/block/tract + legal desc, no APN
    "estimated_cost": lambda a: _to_float(a.get("JobValue")),
    "valuation": lambda a: _to_float(a.get("JobValue")),
    "description": lambda a: a.get("B1_WORK_DESC") or a.get("B1_SPECIAL_TEXT"),
    "work_category": _fort_worth_work_category,
    "square_footage": lambda a: _to_float(a.get("SqFt")),
    "units": lambda a: _to_int(a.get("Units")),
    "latitude": lambda a: _to_float(a.get("Latitude")),
    "longitude": lambda a: _to_float(a.get("Longitude")),
    "permit_url": lambda a: None,
    "_owner_name": "Owner_Full_Name",
}


def _columbus_address(attrs: dict[str, Any]) -> Optional[str]:
    street = (attrs.get("SITE_ADDRESS") or "").strip()
    if not street:
        return None
    full = f"{street}, Columbus, OH"
    zip_code = (attrs.get("B1_SITUS_ZIP") or "").strip()
    if zip_code:
        full = f"{full} {zip_code}"
    return full


# City of Columbus, OH -- live, queryable FeatureServer (correcting BLOCKERS.md
# §5a's prior "aggregate/bulk-only" conclusion; see EXPANSION_PLAN.md Wave A).
# G3_VALUE_TTL is the declared job value (no separate fee column). Coordinates
# come from point geometry (no direct lat/lon columns).
COLUMBUS_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "B1_ALT_ID",
    "permit_type": lambda a: a.get("B1_PER_TYPE") or a.get("B1_PER_GROUP"),
    "status": lambda a: a.get("PERMIT_STATUS") or a.get("B1_APPL_STATUS"),
    "application_date": lambda a: None,  # confirmed absent -- only issued/last-status dates exist
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("ISSUED_DT")),
    "completion_date": lambda a: None,
    "expiration_date": lambda a: None,
    "contractor": lambda a: a.get("APPLICANT_BUS_NAME") or a.get("APPLICANT_FULL_NAME"),
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _columbus_address,
    "parcel_number": lambda a: (a.get("B1_PARCEL_NBR") or "").strip() or None,
    "estimated_cost": lambda a: _to_float(a.get("G3_VALUE_TTL")),
    "valuation": lambda a: _to_float(a.get("G3_VALUE_TTL")),
    "description": lambda a: a.get("VALUE_DESC") or a.get("GENERAL_TYPE"),
    "work_category": lambda a: a.get("GENERAL_TYPE") or a.get("B1_PER_CATEGORY"),
    "square_footage": lambda a: _to_float(a.get("SQFT")),
    "units": lambda a: _to_int(a.get("UNITS")),
    "latitude": _geometry_lat,
    "longitude": _geometry_lon,
    "permit_url": "ACA_URL",
}


def _las_vegas_address(attrs: dict[str, Any]) -> Optional[str]:
    parts = [attrs.get("ADDR1"), attrs.get("CITY"), attrs.get("STATE")]
    street = attrs.get("ADDR1")
    if not street or not str(street).strip():
        return None
    tail = ", ".join(p for p in (attrs.get("CITY"), attrs.get("STATE")) if p)
    full = str(street).strip()
    if tail:
        full = f"{full}, {tail}"
    if attrs.get("ZIP"):
        full = f"{full} {attrs['ZIP']}"
    return full


def _las_vegas_valuation(attrs: dict[str, Any]) -> Optional[float]:
    # DECLVLTN = declared valuation, CALCVLTN = calculated valuation. Prefer
    # the declared value; fall back to calculated. Zero-safe (see
    # _first_not_none) so a genuine $0 declared value isn't discarded.
    return _first_not_none(_to_float(attrs.get("DECLVLTN")), _to_float(attrs.get("CALCVLTN")))


def _las_vegas_parcel(attrs: dict[str, Any]) -> Optional[str]:
    raw = attrs.get("PRCLID")
    if raw in (None, ""):
        return None
    try:
        return str(int(raw))
    except (TypeError, ValueError):
        return str(raw)


# City of Las Vegas, NV (city proper) -- distinct from the existing Clark County
# ACA scraper. NOTE (provenance): EXPANSION_PLAN.md pointed at the
# `Building_Permits_Open_Data` service, which on live verification this pass was
# a field-restricted VIEW exposing only ObjectId (zero permit fields). The real
# per-record layer is `OpenData_Building_Permits_` (same org, 435k records,
# resolved via arcgis.com item search) -- used here instead. Published as an
# ArcGIS Table (no geometry), so the Census-geocoder fallback supplies lat/lon.
LAS_VEGAS_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "APNO",
    "permit_type": "APTYPE",
    "status": "BLDGAPPLSTATUS",
    "application_date": lambda a: None,  # confirmed absent -- only an issue datetime exists
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("ISSDTTM")),
    "completion_date": lambda a: None,
    "expiration_date": lambda a: None,
    "contractor": "APPLICANT",
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _las_vegas_address,
    "parcel_number": _las_vegas_parcel,
    "estimated_cost": _las_vegas_valuation,
    "valuation": _las_vegas_valuation,
    "description": lambda a: None,  # no clean free-text description column (WORKTYPE used as category)
    "work_category": lambda a: a.get("WORKTYPE") or a.get("APTYPE"),
    "square_footage": lambda a: None,  # confirmed absent
    "units": lambda a: None,  # confirmed absent
    "latitude": lambda a: None,  # Table type, no geometry -- geocoder fallback applies
    "longitude": lambda a: None,
    "permit_url": lambda a: None,
    "_owner_name": lambda a: a.get("NAME") or a.get("LEGALOWNER"),
}


def _detroit_address(attrs: dict[str, Any]) -> Optional[str]:
    street = (attrs.get("address") or "").strip()
    if not street:
        return None
    full = f"{street}, Detroit, MI"
    zip_code = (attrs.get("zip_code") or "").strip()
    if zip_code:
        full = f"{full} {zip_code}"
    return full


# City of Detroit, MI (BSEED) -- adds Michigan. Sourced from Detroit's internal
# Accela but published as a clean open FeatureServer with direct lat/lon.
# IMPORTANT fee-vs-value distinction: amt_permit_cost is the permit FEE charged
# by the city; amt_estimated_contractor_cost is the declared construction value
# -- the latter is what drives estimated_cost/valuation (mapping the fee here
# would badly skew budget-tier scoring). Dates are esriFieldTypeDateOnly plain
# "YYYY-MM-DD" strings, parsed via _esri_flexible_date.
DETROIT_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "record_id",
    "permit_type": "permit_type",
    "status": lambda a: None,  # confirmed absent -- no permit-status column on this layer
    "application_date": lambda a: _esri_flexible_date(a.get("submitted_date")),
    "issue_date": lambda a: _esri_flexible_date(a.get("issued_date")),
    "completion_date": lambda a: None,
    "expiration_date": lambda a: None,
    "contractor": lambda a: None,  # confirmed absent -- no contractor name column
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _detroit_address,
    "parcel_number": "parcel_id",
    "estimated_cost": lambda a: _to_float(a.get("amt_estimated_contractor_cost")),
    "valuation": lambda a: _to_float(a.get("amt_estimated_contractor_cost")),
    "description": "work_description",
    "work_category": lambda a: a.get("use_group") or a.get("permit_type"),
    "square_footage": lambda a: None,  # confirmed absent (num_stories exists, not sqft)
    "units": lambda a: _to_int(a.get("num_units")),
    "latitude": lambda a: _to_float(a.get("latitude")),
    "longitude": lambda a: _to_float(a.get("longitude")),
    "permit_url": lambda a: None,
}


def _louisville_address(attrs: dict[str, Any]) -> Optional[str]:
    street = (attrs.get("ADDRESS") or "").strip()
    if not street:
        return None
    tail = " ".join(p for p in (attrs.get("CITY"), attrs.get("STATE")) if p)
    full = street
    if tail:
        full = f"{full}, {tail}"
    zip_code = (attrs.get("ZIPCODE") or "").strip()
    if zip_code:
        full = f"{full} {zip_code}"
    return full


# Louisville Metro, KY -- adds Kentucky. Rich fields incl. a direct CONTRACTOR
# column. Fee-vs-value: PERMIT_FEE is the fee, PROJECT_COSTS is the declared
# project value -- PROJECT_COSTS drives estimated_cost/valuation.
LOUISVILLE_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "PERMIT_NUMBER",
    "permit_type": "PERMIT_TYPE",
    "status": "PERMIT_STATUS",
    "application_date": lambda a: None,  # confirmed absent -- only ISSUE_DATE exists
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("ISSUE_DATE")),
    "completion_date": lambda a: None,
    "expiration_date": lambda a: None,
    "contractor": "CONTRACTOR",
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _louisville_address,
    "parcel_number": lambda a: None,  # confirmed absent
    "estimated_cost": lambda a: _to_float(a.get("PROJECT_COSTS")),
    "valuation": lambda a: _to_float(a.get("PROJECT_COSTS")),
    "description": lambda a: a.get("WORK_TYPE") or a.get("CATEGORY_NAME"),
    "work_category": lambda a: a.get("WORK_TYPE") or a.get("CATEGORY_NAME"),
    "square_footage": lambda a: _to_float(a.get("SQFT")),
    "units": lambda a: None,
    "latitude": lambda a: _to_float(a.get("LATITUDE")),
    "longitude": lambda a: _to_float(a.get("LONGITUDE")),
    "permit_url": lambda a: None,
}


def _tucson_address(attrs: dict[str, Any]) -> Optional[str]:
    street = (attrs.get("ADDRESS") or "").strip()
    if not street:
        return None
    unit = (attrs.get("UNITORSUITE") or "").strip()
    if unit:
        street = f"{street} {unit}"
    return f"{street}, Tucson, AZ"


# City of Tucson, AZ (second AZ jurisdiction beyond Tempe/Mesa) -- own ArcGIS
# server. VALUE is the declared valuation; direct LAT/LON columns. Cross-system
# URLs (CSS_URL/ENGOV_URL/PRO_URL) confirm Tucson's backend migrated across
# permitting systems over time; PRO_URL is the stable public-facing record link.
TUCSON_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "NUMBER",
    "permit_type": "TYPE",
    "status": "STATUS",
    "application_date": lambda a: _esri_epoch_to_datetime(a.get("APPLYDATE")),
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("ISSUEDATE")),
    "completion_date": lambda a: _esri_epoch_to_datetime(a.get("COMPLETEDATE")),
    "expiration_date": lambda a: _esri_epoch_to_datetime(a.get("EXPIREDATE")),
    "contractor": lambda a: None,  # confirmed absent -- no contractor column on this layer
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _tucson_address,
    "parcel_number": "PARCEL",
    "estimated_cost": lambda a: _to_float(a.get("VALUE")),
    "valuation": lambda a: _to_float(a.get("VALUE")),
    "description": "DESCRIPTION",
    "work_category": "WORKCLASS",
    "square_footage": lambda a: _to_float(a.get("SQUAREFEET")),
    "units": lambda a: None,
    "latitude": lambda a: _to_float(a.get("LAT")),
    "longitude": lambda a: _to_float(a.get("LON")),
    "permit_url": lambda a: a.get("PRO_URL") or a.get("CSS_URL"),
}


# ---------------------------------------------------------------------------
# Sixth data-gathering pass -- adds South Carolina (a previously-uncovered
# state). Charleston, SC "New Construction Permits" FeatureServer, found via the
# city's own ArcGIS Hub DCAT feed (data-charleston-sc.opendata.arcgis.com) and
# verified live this pass (14.7k real per-record permits; sample addresses
# confirm Charleston, SC -- not assumed from the account name).
# ---------------------------------------------------------------------------


def _charleston_finaled_date(attrs: dict[str, Any]) -> Optional[datetime]:
    # FINALED_DATE is a plain string ("04/12/2021" with trailing whitespace),
    # unlike the epoch-millis APPLICATION_DATE/ISSUE_DATE fields on the same
    # layer -- parse flexibly and tolerate the padding.
    raw = attrs.get("FINALED_DATE")
    if raw in (None, ""):
        return None
    return _esri_flexible_date(str(raw).strip())


def _charleston_address(attrs: dict[str, Any]) -> Optional[str]:
    line1 = (attrs.get("PARCELADDR_LINE1") or "").strip()
    if not line1:
        return None
    line2 = (attrs.get("PARCELADDR_LINE2") or "").strip()  # e.g. "Charleston, SC 29492"
    return f"{line1}, {line2}" if line2 else f"{line1}, Charleston, SC"


# City of Charleston, SC New Construction Permits. VALUATION is a genuine
# declared value (esriFieldTypeDouble, no separate fee column on this layer).
# Point geometry supplies lat/lon (requested in WGS84 via outSR=4326). No
# contractor column (confirmed absent).
CHARLESTON_SC_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": "PERMIT_NUMBER",
    "permit_type": "PERMIT_TYPE",
    "status": "PERMIT_STATUS",
    "application_date": lambda a: _esri_epoch_to_datetime(a.get("APPLICATION_DATE")),
    "issue_date": lambda a: _esri_epoch_to_datetime(a.get("ISSUE_DATE")),
    "completion_date": _charleston_finaled_date,
    "expiration_date": lambda a: None,  # confirmed absent
    "contractor": lambda a: None,  # confirmed absent
    "builder": lambda a: None,
    "architect": lambda a: None,
    "engineer": lambda a: None,
    "property_address": _charleston_address,
    "parcel_number": "MAIN_PARCEL_NUMBER",
    "estimated_cost": lambda a: _to_float(a.get("VALUATION")),
    "valuation": lambda a: _to_float(a.get("VALUATION")),
    "description": "DESCRIPTION",
    "work_category": lambda a: a.get("WORK_CLASS") or a.get("PERMIT_TYPE"),
    "square_footage": lambda a: None,  # confirmed absent
    "units": lambda a: None,
    "latitude": _geometry_lat,
    "longitude": _geometry_lon,
    "permit_url": lambda a: None,
}


class ArcGISSourceConfig:
    def __init__(
        self,
        key: str,
        service_url: str,
        display_name: str,
        field_map: dict[str, FieldMapValue],
        incremental_date_field: Optional[str] = None,
        object_id_field: str = "OBJECTID",
    ):
        self.key = key
        # service_url should point at a specific layer, e.g. ".../FeatureServer/0"
        self.service_url = service_url.rstrip("/")
        self.display_name = display_name
        self.field_map = field_map
        self.incremental_date_field = incremental_date_field
        self.object_id_field = object_id_field


ARCGIS_SOURCES: dict[str, ArcGISSourceConfig] = {
    "tempe_az_building_permits": ArcGISSourceConfig(
        key="tempe_az_building_permits",
        service_url=(
            "https://services.arcgis.com/lQySeXwbBg53XWDi/arcgis/rest/services/"
            "building_permits/FeatureServer/0"
        ),
        display_name="City of Tempe, AZ Building Permits",
        field_map=TEMPE_AZ_BUILDING_PERMITS_MAPPING,
        incremental_date_field="AppliedDateDtm",
        object_id_field="OBJECTID",
    ),
    "raleigh_nc_building_permits": ArcGISSourceConfig(
        key="raleigh_nc_building_permits",
        service_url=(
            "https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/"
            "Building_Permits/FeatureServer/0"
        ),
        display_name="City of Raleigh, NC Building Permits",
        field_map=RALEIGH_NC_BUILDING_PERMITS_MAPPING,
        incremental_date_field="issueddate",
        object_id_field="OBJECTID",
    ),
    "denver_co_residential_permits": ArcGISSourceConfig(
        key="denver_co_residential_permits",
        service_url=(
            "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/"
            "ODC_DEV_RESIDENTIALCONSTPERMIT_P/FeatureServer/316"
        ),
        display_name="City & County of Denver, CO Residential Construction Permits",
        field_map=DENVER_RESIDENTIAL_PERMITS_MAPPING,
        incremental_date_field="DATE_ISSUED",
        object_id_field="OBJECTID",
    ),
    "washington_dc_building_permits": ArcGISSourceConfig(
        key="washington_dc_building_permits",
        service_url="https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DCRA/FeatureServer/17",
        display_name="Washington, DC Building Permits (2025)",
        field_map=DC_BUILDING_PERMITS_MAPPING,
        incremental_date_field="ISSUE_DATE",
        object_id_field="OBJECTID",
    ),
    "miami_dade_permits": ArcGISSourceConfig(
        key="miami_dade_permits",
        service_url=(
            "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/"
            "miamidade_permit_data/FeatureServer/0"
        ),
        display_name="Miami-Dade County Building Permits",
        field_map=MIAMI_DADE_PERMITS_MAPPING,
        incremental_date_field="ApplicationDate",
        object_id_field="ObjectId",
    ),
    "mecklenburg_county_permits": ArcGISSourceConfig(
        key="mecklenburg_county_permits",
        service_url="https://meckgis.mecklenburgcountync.gov/server/rest/services/BuildingPermits/FeatureServer/0",
        display_name="Mecklenburg County, NC (Charlotte) Building Permits",
        field_map=MECKLENBURG_COUNTY_PERMITS_MAPPING,
        incremental_date_field="issuedate",
        object_id_field="objectid",
    ),
    "minneapolis_permits": ArcGISSourceConfig(
        key="minneapolis_permits",
        service_url="https://services.arcgis.com/afSMGVsC7QlRK1kZ/arcgis/rest/services/CCS_Permits/FeatureServer/0",
        display_name="Minneapolis, MN Building Permits",
        field_map=MINNEAPOLIS_PERMITS_MAPPING,
        incremental_date_field="issueDate",
        object_id_field="OBJECTID",
    ),
    "philadelphia_permits": ArcGISSourceConfig(
        key="philadelphia_permits",
        service_url=(
            "https://services6.arcgis.com/StPsG80YRtvnlCJ8/arcgis/rest/services/"
            "PERMITS_BuildingZoning_CPCDC/FeatureServer/0"
        ),
        display_name="Philadelphia, PA Building Permits",
        field_map=PHILADELPHIA_PERMITS_MAPPING,
        incremental_date_field="permitissu",
        object_id_field="OBJECTID_1",
    ),
    "sioux_falls_permits": ArcGISSourceConfig(
        key="sioux_falls_permits",
        service_url="https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/3",
        display_name="Sioux Falls, SD Building Permits",
        field_map=SIOUX_FALLS_PERMITS_MAPPING,
        incremental_date_field="ISSUEDATE",
        object_id_field="OBJECTID",
    ),
    "nashville_permits": ArcGISSourceConfig(
        key="nashville_permits",
        service_url=(
            "https://services2.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services/"
            "Building_Permits_Issued_2/FeatureServer/0"
        ),
        display_name="Nashville, TN Building Permits Issued",
        field_map=NASHVILLE_PERMITS_MAPPING,
        incremental_date_field="Date_Issued",
        object_id_field="ObjectId",
    ),
    "boise_permits": ArcGISSourceConfig(
        key="boise_permits",
        service_url="https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Housing_OpenData/FeatureServer/0",
        display_name="Boise, ID New Residential Permits",
        field_map=BOISE_PERMITS_MAPPING,
        incremental_date_field="IssuedDate",
        object_id_field="OBJECTID",
    ),
    "atlanta_permits": ArcGISSourceConfig(
        key="atlanta_permits",
        service_url="https://services5.arcgis.com/5RxyIIJ9boPdptdo/arcgis/rest/services/AMS_BuildingPermits/FeatureServer/66",
        display_name="Atlanta, GA Building Permits",
        field_map=ATLANTA_PERMITS_MAPPING,
        incremental_date_field="DATE_OPENED",
        object_id_field="OBJECTID",
    ),
    "albuquerque_permits": ArcGISSourceConfig(
        key="albuquerque_permits",
        service_url="https://coageo.cabq.gov/cabqgeo/rest/services/agis/City_Building_Permits/FeatureServer/0",
        display_name="Albuquerque, NM City Building Permits",
        field_map=ALBUQUERQUE_PERMITS_MAPPING,
        incremental_date_field="DateIssued",
        object_id_field="OBJECTID",
    ),
    "portland_permits": ArcGISSourceConfig(
        key="portland_permits",
        service_url="https://www.portlandmaps.com/od/rest/services/COP_OpenData_PlanningDevelopment/MapServer/89",
        display_name="Portland, OR Residential Building Permits",
        field_map=PORTLAND_PERMITS_MAPPING,
        incremental_date_field="ISSUEDATE",
        object_id_field="OBJECTID",
    ),
    "helena_mt_permits": ArcGISSourceConfig(
        key="helena_mt_permits",
        service_url=(
            "https://services1.arcgis.com/zy02xMI7T6QrPvfO/arcgis/rest/services/"
            "All_Building_Permits_Jan2019_Present/FeatureServer/9"
        ),
        display_name="Helena, MT Building Permits",
        field_map=HELENA_MT_PERMITS_MAPPING,
        incremental_date_field="Permit_Issue_Date",
        object_id_field="OBJECTID",
    ),
    # --- Fifth pass / EXPANSION_PLAN.md Wave A ---
    "fort_worth_permits": ArcGISSourceConfig(
        key="fort_worth_permits",
        service_url="https://mapit.fortworthtexas.gov/ags/rest/services/CIVIC/Permits/MapServer/0",
        display_name="Fort Worth, TX Permits",
        field_map=FORT_WORTH_PERMITS_MAPPING,
        incremental_date_field="File_Date",
        object_id_field="CAPID",
    ),
    "columbus_permits": ArcGISSourceConfig(
        key="columbus_permits",
        service_url=(
            "https://services1.arcgis.com/9yy6msODkIBzkUXU/arcgis/rest/services/"
            "Building_Permits/FeatureServer/0"
        ),
        display_name="Columbus, OH Building Permits",
        field_map=COLUMBUS_PERMITS_MAPPING,
        incremental_date_field="ISSUED_DT",
        object_id_field="OBJECTID",
    ),
    "las_vegas_permits": ArcGISSourceConfig(
        key="las_vegas_permits",
        service_url=(
            "https://services1.arcgis.com/F1v0ufATbBQScMtY/arcgis/rest/services/"
            "OpenData_Building_Permits_/FeatureServer/0"
        ),
        display_name="Las Vegas, NV (city) Building Permits",
        field_map=LAS_VEGAS_PERMITS_MAPPING,
        incremental_date_field="ISSDTTM",
        object_id_field="ObjectId",
    ),
    "detroit_permits": ArcGISSourceConfig(
        key="detroit_permits",
        service_url=(
            "https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/"
            "bseed_building_permits/FeatureServer/0"
        ),
        display_name="Detroit, MI Building Permits",
        field_map=DETROIT_PERMITS_MAPPING,
        incremental_date_field=None,  # issued_date is esriFieldTypeDateOnly text, not epoch-millis filterable
        object_id_field="ObjectId",
    ),
    "louisville_permits": ArcGISSourceConfig(
        key="louisville_permits",
        service_url=(
            "https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/"
            "active_construction_permits/FeatureServer/0"
        ),
        display_name="Louisville Metro, KY Construction Permits",
        field_map=LOUISVILLE_PERMITS_MAPPING,
        incremental_date_field="ISSUE_DATE",
        object_id_field="ObjectId",
    ),
    "tucson_permits": ArcGISSourceConfig(
        key="tucson_permits",
        service_url="https://gis.tucsonaz.gov/public/rest/services/PublicMaps/PermitsCode/MapServer/85",
        display_name="Tucson, AZ Residential Building Permits",
        field_map=TUCSON_PERMITS_MAPPING,
        incremental_date_field="ISSUEDATE",
        object_id_field="OBJECTID",
    ),
    # --- Sixth pass: adds South Carolina ---
    "charleston_sc_permits": ArcGISSourceConfig(
        key="charleston_sc_permits",
        service_url=(
            "https://services2.arcgis.com/tQaXW7Zb1Vphzvgd/arcgis/rest/services/"
            "New_Construction_Permits/FeatureServer/0"
        ),
        display_name="Charleston, SC New Construction Permits",
        field_map=CHARLESTON_SC_PERMITS_MAPPING,
        incremental_date_field="ISSUE_DATE",
        object_id_field="OBJECTID",
    ),
}


class ArcGISConnector(PermitConnector):
    source_system = "arcgis"

    def __init__(self, config: ArcGISSourceConfig, timeout: float = DEFAULT_TIMEOUT):
        self.config = config
        self.timeout = timeout

    @property
    def query_url(self) -> str:
        return f"{self.config.service_url}/query"

    def discover(self) -> ConnectorInfo:
        resp = httpx.get(f"{self.config.service_url}", params={"f": "json"}, timeout=self.timeout)
        resp.raise_for_status()
        meta = resp.json()
        fields = [f["name"] for f in meta.get("fields", [])]

        count_resp = httpx.get(
            self.query_url,
            params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
            timeout=self.timeout,
        )
        count = None
        if count_resp.status_code == 200:
            count = count_resp.json().get("count")

        return ConnectorInfo(
            source_system=self.source_system,
            identifier=self.config.service_url,
            display_name=self.config.display_name,
            record_count=count,
            fields=fields,
            extra={"name": meta.get("name"), "geometry_type": meta.get("geometryType")},
        )

    def fetch_permits(self, since: Optional[datetime] = None, limit: Optional[int] = None) -> Iterable[dict]:
        remaining = limit
        offset = 0
        while True:
            page_size = DEFAULT_PAGE_SIZE if remaining is None else min(DEFAULT_PAGE_SIZE, remaining)
            if page_size <= 0:
                break

            where = "1=1"
            if since is not None and self.config.incremental_date_field:
                epoch_millis = int(since.replace(tzinfo=since.tzinfo or timezone.utc).timestamp() * 1000)
                where = f"{self.config.incremental_date_field} >= {epoch_millis}"

            params = {
                "where": where,
                "outFields": "*",
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "orderByFields": self.config.object_id_field,
                # Request WGS84 lat/lon explicitly -- some layers (e.g.
                # Denver's) carry no direct latitude/longitude attribute
                # columns, only point geometry, and the server's native
                # spatial reference isn't guaranteed to be 4326 otherwise.
                "outSR": "4326",
            }
            resp = _request_with_backoff(self.query_url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"ArcGIS query error: {data['error']}")

            features = data.get("features", [])
            if not features:
                break

            for feature in features:
                attrs = dict(feature.get("attributes", {}))
                # Merge point geometry (if any) into the attrs dict under a
                # reserved "_geometry" key so field-mapping lambdas can pull
                # lat/lon from it for layers with no direct lat/lon columns
                # (e.g. Denver) -- see _geometry_lat/_geometry_lon above.
                geometry = feature.get("geometry")
                if geometry:
                    attrs["_geometry"] = geometry
                yield self._map_record(attrs)

            offset += len(features)
            if remaining is not None:
                remaining -= len(features)
                if remaining <= 0:
                    break
            # Terminate on the server's own truncation signal rather than a
            # "short page" heuristic: a layer whose maxRecordCount is below
            # our requested page_size returns fewer rows than asked but sets
            # exceededTransferLimit=True to say "there's more" -- so keep
            # paging until it's absent/false and we've drained the layer.
            exceeded = data.get("exceededTransferLimit")
            if not exceeded and len(features) < page_size:
                break

    def _map_record(self, attrs: dict[str, Any]) -> dict:
        normalized = self.normalized_stub()
        for field_name, mapper in self.config.field_map.items():
            if callable(mapper):
                normalized[field_name] = mapper(attrs)
            else:
                normalized[field_name] = attrs.get(mapper)
        normalized["source"] = f"arcgis:{self.config.service_url}"
        # Keep raw_data as the true raw attributes only (no injected
        # "_geometry" key) so it faithfully reflects what the source sent.
        raw = {k: v for k, v in attrs.items() if k != "_geometry"}
        normalized["raw_data"] = raw
        return normalized
