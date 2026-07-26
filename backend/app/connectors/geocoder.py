"""
Geocoding via the US Census Bureau's free, keyless Geocoding API
(https://geocoding.geo.census.gov). No signup, no API key, no rate-limit
tier to pay for -- this is a genuinely free federal government service,
which is why it's the default/primary geocoder here.

Live-verified against real permit addresses pulled from SF (Socrata)
and Tempe, AZ (ArcGIS) during development -- see
tests/test_geocoder.py::test_census_geocoder_live_integration
(marked @pytest.mark.integration).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
DEFAULT_BENCHMARK = "Public_AR_Current"
DEFAULT_TIMEOUT = 10.0


@dataclass
class GeocodeResult:
    latitude: float
    longitude: float
    matched_address: str
    source: str = "census"
    # Census doesn't return a numeric confidence; "exact" for a direct
    # match, "tigerline_interpolated" is the norm for this benchmark.
    confidence: float = 1.0


class CensusGeocoder:
    """Thin client around the Census Bureau's onelineaddress endpoint."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT, benchmark: str = DEFAULT_BENCHMARK):
        self.timeout = timeout
        self.benchmark = benchmark

    def geocode(self, address: str) -> Optional[GeocodeResult]:
        """
        Look up a single address. Returns None (never raises for a
        not-found address) if the Census API has no match, so callers
        can degrade gracefully (e.g. fall back to permit lat/lon if the
        source already supplied one).
        """
        if not address or not address.strip():
            return None

        params = {
            "address": address,
            "benchmark": self.benchmark,
            "format": "json",
        }
        try:
            resp = httpx.get(CENSUS_GEOCODER_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Census geocoder request failed for %r: %s", address, exc)
            return None

        data = resp.json()
        matches = data.get("result", {}).get("addressMatches", [])
        if not matches:
            return None

        best = matches[0]
        coords = best.get("coordinates", {})
        if "x" not in coords or "y" not in coords:
            return None

        return GeocodeResult(
            latitude=float(coords["y"]),
            longitude=float(coords["x"]),
            matched_address=best.get("matchedAddress", address),
        )

    def geocode_batch(self, addresses: list[str]) -> dict[str, Optional[GeocodeResult]]:
        """Sequentially geocode a list of addresses (Census also offers a
        true batch file-upload endpoint for large volumes; not needed
        at MVP scale -- see BLOCKERS.md)."""
        return {addr: self.geocode(addr) for addr in addresses}
