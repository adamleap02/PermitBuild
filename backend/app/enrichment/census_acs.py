"""
US Census Bureau ACS (American Community Survey) neighborhood
demographics enrichment, by Census tract.

Two-step process:
  1. Reverse-geocode a lat/lon to a Census tract GEOID (state/county/tract)
     via the Census Geocoder's free, keyless `/geographies/coordinates`
     endpoint (same geocoding.geo.census.gov host used for address
     geocoding in app/connectors/geocoder.py -- confirmed live and
     keyless during development).
  2. Look up ACS 5-year estimates for that tract (median household
     income, median home value, population) via the separate Census
     **Data** API (api.census.gov/data/...).

IMPORTANT, live-verified finding: as of this development pass, the
Census Data API (api.census.gov/data/*) returns HTTP 200 with an HTML
"Missing Key" error page for EVERY request, including the most basic
ones, with no API key -- this is a change from the historical behavior
described in research/RESEARCH_REPORT.md (which characterized it as
"free, generous but rate-limited" with no key needed). Confirmed by
testing multiple ACS vintages (2021, 2022) and even the 2020 decennial
Census endpoint -- all require a key now. The key itself is still free
and instant to obtain (https://api.census.gov/data/key_signup.html,
just an email address, no payment/billing), so this degrades exactly
like the Stripe billing integration: fully written, but inert until a
human sets CENSUS_API_KEY. See BLOCKERS.md.

The reverse-geocode-to-tract step, by contrast, IS still free/keyless
and works today -- confirmed live, so a tract GEOID is always available
even when the ACS numbers themselves are not.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CENSUS_GEOGRAPHIES_URL = "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
CENSUS_ACS_BASE_URL = "https://api.census.gov/data/{year}/acs/acs5"
DEFAULT_ACS_YEAR = 2022
DEFAULT_TIMEOUT = 10.0

CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY")

# ACS 5-year detail table variables -- median household income, median
# owner-occupied home value, and total population, respectively.
ACS_VARIABLES = {
    "median_household_income": "B19013_001E",
    "median_home_value": "B25077_001E",
    "population": "B01003_001E",
}


@dataclass
class CensusTract:
    state_fips: str
    county_fips: str
    tract_code: str
    geoid: str
    name: Optional[str] = None


@dataclass
class AcsDemographics:
    tract: CensusTract
    median_household_income: Optional[int]
    median_home_value: Optional[int]
    population: Optional[int]


def get_tract_for_point(lat: float, lon: float, timeout: float = DEFAULT_TIMEOUT) -> Optional[CensusTract]:
    """Reverse-geocode a lat/lon to its Census Tract. Free, keyless,
    confirmed live. Returns None on no match or any request failure
    (never raises) so callers can degrade gracefully."""
    params = {
        "x": lon,
        "y": lat,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "layers": "Census Tracts",
        "format": "json",
    }
    try:
        resp = httpx.get(CENSUS_GEOGRAPHIES_URL, params=params, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Census geographies lookup failed for (%s, %s): %s", lat, lon, exc)
        return None

    data = resp.json()
    tracts = data.get("result", {}).get("geographies", {}).get("Census Tracts", [])
    if not tracts:
        return None
    tract = tracts[0]
    state = tract.get("STATE")
    county = tract.get("COUNTY")
    tract_code = tract.get("TRACT")
    if not (state and county and tract_code):
        return None
    return CensusTract(
        state_fips=state,
        county_fips=county,
        tract_code=tract_code,
        geoid=f"{state}{county}{tract_code}",
        name=tract.get("NAME"),
    )


def is_configured() -> bool:
    return bool(CENSUS_API_KEY)


def get_acs_demographics(
    tract: CensusTract, year: int = DEFAULT_ACS_YEAR, timeout: float = DEFAULT_TIMEOUT
) -> Optional[AcsDemographics]:
    """
    Look up ACS 5-year demographics for a Census tract. Requires
    CENSUS_API_KEY (free, human must register -- see module docstring
    and BLOCKERS.md); returns None immediately without making a request
    if unset, matching the rest of this codebase's "not configured"
    degrade-gracefully pattern (see app/billing.py).
    """
    if not CENSUS_API_KEY:
        logger.debug("CENSUS_API_KEY not set -- skipping ACS demographics lookup")
        return None

    variables = ",".join(["NAME"] + list(ACS_VARIABLES.values()))
    params = {
        "get": variables,
        "for": f"tract:{tract.tract_code}",
        "in": f"state:{tract.state_fips} county:{tract.county_fips}",
        "key": CENSUS_API_KEY,
    }
    url = CENSUS_ACS_BASE_URL.format(year=year)
    try:
        resp = httpx.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("ACS lookup failed for tract %s: %s", tract.geoid, exc)
        return None

    try:
        rows = resp.json()
    except ValueError:
        logger.warning("ACS lookup for tract %s returned non-JSON (likely a key/quota error)", tract.geoid)
        return None
    if len(rows) < 2:
        return None

    header, values = rows[0], rows[1]
    record = dict(zip(header, values))

    def _int_or_none(key: str) -> Optional[int]:
        raw = record.get(key)
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None  # ACS uses negative sentinel codes for suppressed/N/A values

    return AcsDemographics(
        tract=tract,
        median_household_income=_int_or_none(ACS_VARIABLES["median_household_income"]),
        median_home_value=_int_or_none(ACS_VARIABLES["median_home_value"]),
        population=_int_or_none(ACS_VARIABLES["population"]),
    )
