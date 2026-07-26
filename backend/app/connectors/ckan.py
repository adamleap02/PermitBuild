"""
Generic connector for any CKAN DataStore open-data permit dataset.

CKAN (https://ckan.org/) is a widely-used open-data portal platform,
distinct from Socrata/ArcGIS. Its Action API is free and keyless for
public datasets. This connector uses two endpoints:

  * `/api/3/action/package_show?id=<slug>` -- dataset metadata: lists
    the dataset's resources (individual data files/tables) and which of
    them are `datastore_active` (i.e. queryable row-by-row rather than
    just a bulk CSV download).
  * `/api/3/action/datastore_search?resource_id=<uuid>` -- paginated
    row-level access to a datastore-active resource (limit/offset), the
    CKAN analogue of Socrata's SODA `/resource/<id>.json` endpoint.

Verified live this pass against San Antonio, TX
(`data.sanantonio.gov`): `package_show?id=building-permits` returned a
real "Building Permits" package whose "PERMITS ISSUED" resource is
`datastore_active` with 130k+ rows and columns incl. `PERMIT #`,
`DECLARED VALUATION`, `PRIMARY CONTACT`, `X_COORD`/`Y_COORD`, `DATE
ISSUED`. See research/EXPANSION_PLAN.md Wave A and BLOCKERS.md.

Structurally similar to the Socrata connector (a domain + a resource id
+ a per-source field-mapping config), but a genuinely different JSON
envelope: rows live under `result.records`, the schema under
`result.fields`, and CKAN column ids frequently contain spaces and
punctuation (e.g. "PERMIT #", "AREA (SF)"), so mappings reference those
literal keys.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Iterable, Optional, Union

import httpx

from app.connectors.base import ConnectorInfo, PermitConnector

logger = logging.getLogger(__name__)

FieldMapValue = Union[str, Callable[[dict[str, Any]], Any]]

DEFAULT_TIMEOUT = 60.0
# CKAN's datastore_search accepts a large limit with offset paging; 10,000
# per request keeps big feeds (Boston 657K, San Antonio 130K) to a modest
# number of round-trips while staying well within typical CKAN caps.
DEFAULT_PAGE_SIZE = 10000


def _request_with_backoff(
    url: str,
    *,
    params: dict[str, Any],
    timeout: float = DEFAULT_TIMEOUT,
    max_retries: int = 5,
) -> httpx.Response:
    """GET with exponential back-off on HTTP 429 / transient 5xx, respecting
    Retry-After -- polite to the free CKAN datastore endpoint on big pulls."""
    import time

    delay = 2.0
    for attempt in range(max_retries):
        resp = httpx.get(url, params=params, timeout=timeout)
        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt == max_retries - 1:
                resp.raise_for_status()
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if (retry_after and retry_after.isdigit()) else delay
            logger.warning("CKAN %s on %s; backing off %.1fs (attempt %d)", resp.status_code, url, wait, attempt + 1)
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


def _first_not_none(*values: Any) -> Any:
    for v in values:
        if v is not None:
            return v
    return None


def _to_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
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
        logger.debug("Could not parse CKAN datetime value: %r", value)
        return None


# ---------------------------------------------------------------------------
# Per-source field mapping configs
# ---------------------------------------------------------------------------


def _san_antonio_valuation(rec: dict[str, Any]) -> Optional[float]:
    return _to_float(rec.get("DECLARED VALUATION"))


def _san_antonio_lat(rec: dict[str, Any]) -> Optional[float]:
    # LIVE-VERIFIED data-quality finding: this feed MIXES coordinate systems --
    # most rows carry WGS84 (Y_COORD ~29.x, X_COORD ~-98.x), but a meaningful
    # fraction instead carry Texas State Plane FEET (e.g. Y_COORD "13708187.9",
    # X_COORD "2076498.5"), which would be stored as a nonsensical latitude of
    # 13 million. Guard by range; out-of-range values fall through to the
    # Census-geocoder fallback on ADDRESS (which every row has).
    lat = _to_float(rec.get("Y_COORD"))
    return lat if lat is not None and -90.0 <= lat <= 90.0 else None


def _san_antonio_lon(rec: dict[str, Any]) -> Optional[float]:
    lon = _to_float(rec.get("X_COORD"))
    return lon if lon is not None and -180.0 <= lon <= 180.0 else None


def _san_antonio_permit_number(rec: dict[str, Any]) -> Optional[str]:
    # LIVE-VERIFIED data-quality finding: "PERMIT #" is NOT unique -- a single
    # master permit (e.g. "COM-BLG-PMT24-40200788") appears on multiple rows,
    # one per trade sub-permit (Building/Electrical/Mechanical/Plumbing), which
    # would violate our (jurisdiction_id, permit_number) uniqueness constraint.
    # CKAN's per-row `_id` is the datastore's own guaranteed-unique key, so
    # disambiguate by appending it (keeping the human-readable master number as
    # the prefix) -- same disambiguation strategy as the Cook County connector.
    base = rec.get("PERMIT #")
    if not base or not str(base).strip():
        return None
    row_id = rec.get("_id")
    return f"{str(base).strip()}-{row_id}" if row_id is not None else str(base).strip()


# City of San Antonio, TX (7th-largest US city) -- CKAN portal, CC-BY. The
# "PERMITS ISSUED" resource is the rolling current feed (a separate "PERMITS
# ISSUED 2020-2024" resource holds history). X_COORD is longitude, Y_COORD is
# latitude (both text, and mixed coordinate systems -- see the lat/lon helpers).
# "DECLARED VALUATION" is the declared project value; there is no separate
# permit-fee column to confuse it with. "PRIMARY CONTACT" is the applicant/
# contact of record.
SAN_ANTONIO_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": _san_antonio_permit_number,
    "permit_type": "PERMIT TYPE",
    "status": lambda r: None,  # confirmed absent -- the ISSUED feed carries no status column
    "application_date": lambda r: _to_datetime(r.get("DATE SUBMITTED")),
    "issue_date": lambda r: _to_datetime(r.get("DATE ISSUED")),
    "completion_date": lambda r: None,
    "expiration_date": lambda r: None,
    "contractor": "PRIMARY CONTACT",
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": "ADDRESS",  # already a full "street, City of San Antonio, TX zip" string
    "parcel_number": lambda r: None,  # confirmed absent
    "estimated_cost": _san_antonio_valuation,
    "valuation": _san_antonio_valuation,
    "description": lambda r: r.get("PROJECT NAME") or r.get("WORK TYPE"),
    "work_category": "WORK TYPE",
    "square_footage": lambda r: _to_float(r.get("AREA (SF)")),
    "units": lambda r: None,
    "latitude": _san_antonio_lat,
    "longitude": _san_antonio_lon,
    "permit_url": lambda r: None,
}


# ---------------------------------------------------------------------------
# Sixth data-gathering pass -- Boston, MA (CKAN, like San Antonio). Boston runs
# a CKAN portal at data.boston.gov; its "approved-building-permits" package
# exposes a datastore-active resource with 657k+ rows. Verified live this pass
# (column list + sample rows). CC-licensed public data.
# ---------------------------------------------------------------------------


def _parse_currency(value: Any) -> Optional[float]:
    # Boston stores money as formatted strings like "$36,500.00" / "$390.00".
    if value in (None, ""):
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    return _to_float(text)


def _boston_valuation(rec: dict[str, Any]) -> Optional[float]:
    # IMPORTANT fee-vs-valuation distinction (live-verified): `declared_valuation`
    # is the declared construction value; `total_fees` is the permit fee charged.
    # Map declared_valuation -- mapping total_fees here would badly skew
    # budget-tier scoring (same class of bug caught for Chicago/Tempe/Detroit).
    return _parse_currency(rec.get("declared_valuation"))


def _boston_address(rec: dict[str, Any]) -> Optional[str]:
    street = (rec.get("address") or "").strip()
    if not street:
        return None
    parts = [street]
    city = (rec.get("city") or "").strip()
    state = (rec.get("state") or "").strip()
    tail = ", ".join(p for p in (city, state) if p)
    if tail:
        parts.append(tail)
    full = ", ".join(parts)
    zip_code = (rec.get("zip") or "").strip()
    if zip_code:
        full = f"{full} {zip_code}"
    return full


def _boston_lat(rec: dict[str, Any]) -> Optional[float]:
    # y_latitude/x_longitude are direct WGS84 decimals; the gpsx/gpsy columns
    # are State Plane feet (unusable directly) -- use the WGS84 pair.
    lat = _to_float(rec.get("y_latitude"))
    return lat if lat is not None and -90.0 <= lat <= 90.0 and lat != 0 else None


def _boston_lon(rec: dict[str, Any]) -> Optional[float]:
    lon = _to_float(rec.get("x_longitude"))
    return lon if lon is not None and -180.0 <= lon <= 180.0 and lon != 0 else None


def _boston_permit_number(rec: dict[str, Any]) -> Optional[str]:
    base = rec.get("permitnumber")
    if not base or not str(base).strip():
        # A few rows lack a permitnumber -- fall back to the datastore _id so the
        # (jurisdiction_id, permit_number) constraint still holds.
        rid = rec.get("_id")
        return f"BOS-{rid}" if rid is not None else None
    return str(base).strip()


# City of Boston, MA -- CKAN "Approved Building Permits". declared_valuation is
# the value (total_fees is the fee -- see _boston_valuation). occupancytype and
# worktype describe use/work class. Direct WGS84 lat/lon in y_latitude/x_longitude.
BOSTON_PERMITS_MAPPING: dict[str, FieldMapValue] = {
    "permit_number": _boston_permit_number,
    "permit_type": "permittypedescr",
    "status": "status",
    "application_date": lambda r: None,  # confirmed absent -- only issued/expiration dates
    "issue_date": lambda r: _to_datetime(r.get("issued_date")),
    "completion_date": lambda r: None,
    "expiration_date": lambda r: _to_datetime(r.get("expiration_date")),
    "contractor": lambda r: None,  # `applicant` is the filer, not necessarily the contractor
    "builder": lambda r: None,
    "architect": lambda r: None,
    "engineer": lambda r: None,
    "property_address": _boston_address,
    "parcel_number": lambda r: (str(r.get("parcel_id")).strip() if r.get("parcel_id") not in (None, "") else None),
    "estimated_cost": _boston_valuation,
    "valuation": _boston_valuation,
    "description": lambda r: r.get("description") or r.get("comments"),
    "work_category": lambda r: r.get("worktype") or r.get("occupancytype"),
    "square_footage": lambda r: _to_float(r.get("sq_feet")),
    "units": lambda r: None,
    "latitude": _boston_lat,
    "longitude": _boston_lon,
    "permit_url": lambda r: None,
    # No property-owner column exists (the `applicant` field is the permit
    # filer, not the owner of record) -- not mapped to _owner_name to avoid
    # mislabeling a filer as an owner.
}


class CKANSourceConfig:
    def __init__(
        self,
        key: str,
        domain: str,
        display_name: str,
        field_map: dict[str, FieldMapValue],
        resource_id: Optional[str] = None,
        package_id: Optional[str] = None,
        resource_name_contains: Optional[str] = None,
    ):
        """
        Either pin a concrete `resource_id` (a datastore-active resource
        UUID -- stable and preferred), or give a `package_id` plus a
        `resource_name_contains` hint so discover()/fetch can resolve the
        right resource from the package's resource list at runtime.
        """
        self.key = key
        self.domain = domain
        self.display_name = display_name
        self.field_map = field_map
        self.resource_id = resource_id
        self.package_id = package_id
        self.resource_name_contains = resource_name_contains


CKAN_SOURCES: dict[str, CKANSourceConfig] = {
    "san_antonio_permits": CKANSourceConfig(
        key="san_antonio_permits",
        domain="data.sanantonio.gov",
        display_name="San Antonio, TX Building Permits",
        field_map=SAN_ANTONIO_PERMITS_MAPPING,
        # Pinned to the rolling "PERMITS ISSUED" datastore resource (verified
        # datastore_active live this pass); package_id/name kept as a
        # self-healing fallback if the resource UUID ever changes.
        resource_id="c21106f9-3ef5-4f3a-8604-f992b4db7512",
        package_id="building-permits",
        resource_name_contains="PERMITS ISSUED",
    ),
    "boston_permits": CKANSourceConfig(
        key="boston_permits",
        domain="data.boston.gov",
        display_name="Boston, MA Approved Building Permits",
        field_map=BOSTON_PERMITS_MAPPING,
        # Pinned to the datastore-active "Approved Building Permits" resource
        # (verified live this pass); package_id kept as a self-healing fallback.
        resource_id="6ddcd912-32a0-43df-9908-63574f8c7e77",
        package_id="approved-building-permits",
        resource_name_contains="Approved Building Permits",
    ),
}


class CKANConnector(PermitConnector):
    source_system = "ckan"

    def __init__(self, config: CKANSourceConfig, timeout: float = DEFAULT_TIMEOUT):
        self.config = config
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        return f"https://{self.config.domain}/api/3/action"

    def _resolve_resource_id(self) -> str:
        """Return the pinned resource id, or resolve one from the package's
        resource list by name hint (preferring datastore-active resources)."""
        if self.config.resource_id:
            return self.config.resource_id
        if not self.config.package_id:
            raise ValueError(f"CKAN source {self.config.key!r} has neither resource_id nor package_id")

        resp = httpx.get(
            f"{self.base_url}/package_show",
            params={"id": self.config.package_id},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        result = resp.json().get("result", {})
        resources = [r for r in result.get("resources", []) if r.get("datastore_active")]
        if not resources:
            raise RuntimeError(f"CKAN package {self.config.package_id!r} has no datastore-active resources")

        hint = (self.config.resource_name_contains or "").lower()
        if hint:
            for r in resources:
                if hint in (r.get("name") or "").lower():
                    return r["id"]
        return resources[0]["id"]

    def discover(self) -> ConnectorInfo:
        resource_id = self._resolve_resource_id()
        resp = httpx.get(
            f"{self.base_url}/datastore_search",
            params={"resource_id": resource_id, "limit": 1},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        result = resp.json().get("result", {})
        fields = [f.get("id") for f in result.get("fields", []) if f.get("id") != "_id"]
        return ConnectorInfo(
            source_system=self.source_system,
            identifier=f"{self.config.domain}/{resource_id}",
            display_name=self.config.display_name,
            record_count=result.get("total"),
            fields=fields,
            extra={"resource_id": resource_id},
        )

    def fetch_permits(self, since: Optional[datetime] = None, limit: Optional[int] = None) -> Iterable[dict]:
        resource_id = self._resolve_resource_id()
        remaining = limit
        offset = 0
        while True:
            page_size = DEFAULT_PAGE_SIZE if remaining is None else min(DEFAULT_PAGE_SIZE, remaining)
            if page_size <= 0:
                break

            resp = _request_with_backoff(
                f"{self.base_url}/datastore_search",
                params={"resource_id": resource_id, "limit": page_size, "offset": offset},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
            if not payload.get("success", False):
                raise RuntimeError(f"CKAN datastore_search error: {payload.get('error')}")
            records = payload.get("result", {}).get("records", [])
            if not records:
                break

            for raw in records:
                yield self._map_record(raw, resource_id)

            offset += len(records)
            if remaining is not None:
                remaining -= len(records)
            if len(records) < page_size:
                break

    def _map_record(self, raw: dict[str, Any], resource_id: str) -> dict:
        normalized = self.normalized_stub()
        for field_name, mapper in self.config.field_map.items():
            if callable(mapper):
                normalized[field_name] = mapper(raw)
            else:
                normalized[field_name] = raw.get(mapper)
        normalized["source"] = f"ckan:{self.config.domain}:{resource_id}"
        normalized["raw_data"] = raw
        return normalized
