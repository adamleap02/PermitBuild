"""
Real county assessor/parcel enrichment: Cook County, IL Assessor open
data, keyed by PIN (Property Index Number) -- the same PIN format our
Cook County permit connector (app/connectors/socrata.py,
COOK_COUNTY_PERMITS_MAPPING) maps into Permit.parcel_number, so permits
ingested from Cook County can be enriched by parcel automatically.

Two free, public, keyless Socrata datasets on datacatalog.cookcountyil.gov,
both confirmed live during development:
  - "Assessor - Single and Multi-Family Improvement Characteristics"
    (x54s-btds): year built, building/lot square footage, bed/bath count,
    construction quality, etc.
  - "Assessor - Assessed Values" (uzyt-m557): certified assessed value
    (building + land + total).

This is real county assessor data -- the actual authoritative source
municipalities use to set property tax bills -- not a paid third-party
aggregator (ATTOM/CoreLogic/Regrid), and it's free precisely because
it's a government open-records disclosure, same rationale as the
permit portals themselves (see BLOCKERS.md's FOIA/public-records note).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

CHARACTERISTICS_URL = "https://datacatalog.cookcountyil.gov/resource/x54s-btds.json"
ASSESSED_VALUES_URL = "https://datacatalog.cookcountyil.gov/resource/uzyt-m557.json"
DEFAULT_TIMEOUT = 15.0

# Cook County PINs are 14 digits (no dashes) in these datasets; permits
# feed may include formatting -- normalize before querying.
_PIN_MIN_LENGTH = 10


@dataclass
class CookCountyParcelData:
    pin: str
    year_built: Optional[int] = None
    building_sqft: Optional[float] = None
    land_sqft: Optional[float] = None
    bedrooms: Optional[float] = None
    full_baths: Optional[float] = None
    half_baths: Optional[float] = None
    stories_description: Optional[str] = None
    property_use: Optional[str] = None
    assessed_total: Optional[float] = None
    assessed_building: Optional[float] = None
    assessed_land: Optional[float] = None
    assessment_year: Optional[str] = None


def _clean_pin(pin: str) -> str:
    return "".join(ch for ch in pin if ch.isdigit())


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


def get_parcel_data(pin: str, timeout: float = DEFAULT_TIMEOUT) -> Optional[CookCountyParcelData]:
    """
    Look up Cook County Assessor characteristics + assessed value for a
    PIN. Returns None (never raises) if the PIN doesn't look like a Cook
    County PIN, has no match, or on any request failure.
    """
    clean_pin = _clean_pin(pin or "")
    if len(clean_pin) < _PIN_MIN_LENGTH:
        return None

    result = CookCountyParcelData(pin=clean_pin)
    found_anything = False

    try:
        char_resp = httpx.get(
            CHARACTERISTICS_URL,
            params={"pin": clean_pin, "$order": "year DESC", "$limit": 1},
            timeout=timeout,
        )
        char_resp.raise_for_status()
        char_rows = char_resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Cook County Assessor characteristics lookup failed for PIN %s: %s", clean_pin, exc)
        char_rows = []

    if char_rows:
        found_anything = True
        row = char_rows[0]
        result.year_built = _to_int(row.get("char_yrblt"))
        result.building_sqft = _to_float(row.get("char_bldg_sf"))
        result.land_sqft = _to_float(row.get("char_land_sf"))
        result.bedrooms = _to_float(row.get("char_beds"))
        result.full_baths = _to_float(row.get("char_fbath"))
        result.half_baths = _to_float(row.get("char_hbath"))
        result.stories_description = row.get("char_type_resd")
        result.property_use = row.get("char_use")

    try:
        val_resp = httpx.get(
            ASSESSED_VALUES_URL,
            params={"pin": clean_pin, "$order": "year DESC", "$limit": 1},
            timeout=timeout,
        )
        val_resp.raise_for_status()
        val_rows = val_resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Cook County Assessor value lookup failed for PIN %s: %s", clean_pin, exc)
        val_rows = []

    if val_rows:
        found_anything = True
        row = val_rows[0]
        result.assessed_total = _to_float(row.get("certified_tot")) or _to_float(row.get("mailed_tot"))
        result.assessed_building = _to_float(row.get("certified_bldg")) or _to_float(row.get("mailed_bldg"))
        result.assessed_land = _to_float(row.get("certified_land")) or _to_float(row.get("mailed_land"))
        result.assessment_year = row.get("year")

    return result if found_anything else None
