"""
FEMA National Flood Hazard Layer (NFHL) flood-zone enrichment.

Free, public, keyless ArcGIS REST FeatureServer/MapServer -- confirmed
live during development at
https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer
(layer 28, "Flood Hazard Zones"). Note the base path is
`.../arcgis/rest/services/...` -- an older `.../gis/nfhl/rest/...` path
found in some third-party docs/blog posts 404s; this module uses the
confirmed-live path.

Query is a simple point-in-polygon intersection: given a lat/lon, ask
which flood hazard zone polygon (if any) contains that point. No auth,
no key, updated monthly by FEMA.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

FEMA_NFHL_FLOOD_ZONES_QUERY_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
)
DEFAULT_TIMEOUT = 15.0


@dataclass
class FloodZoneResult:
    flood_zone: str  # e.g. "X", "AE", "A", "VE"
    zone_subtype: Optional[str]  # e.g. "AREA OF MINIMAL FLOOD HAZARD", "0.2 PCT ANNUAL CHANCE FLOOD HAZARD"
    is_special_flood_hazard_area: Optional[bool]  # SFHA_TF: "T"/"F"


def get_flood_zone(lat: float, lon: float, timeout: float = DEFAULT_TIMEOUT) -> Optional[FloodZoneResult]:
    """
    Look up the FEMA flood hazard zone for a point. Returns None (never
    raises) if the point isn't covered by any mapped flood zone polygon,
    or on any request failure -- so ingest/backfill can degrade
    gracefully rather than blocking on FEMA's availability.
    """
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF",
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        resp = httpx.get(FEMA_NFHL_FLOOD_ZONES_QUERY_URL, params=params, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("FEMA NFHL lookup failed for (%s, %s): %s", lat, lon, exc)
        return None

    data = resp.json()
    if "error" in data:
        logger.warning("FEMA NFHL query error for (%s, %s): %s", lat, lon, data["error"])
        return None

    features = data.get("features", [])
    if not features:
        return None

    attrs = features[0].get("attributes", {})
    flood_zone = attrs.get("FLD_ZONE")
    if not flood_zone:
        return None

    sfha_flag = attrs.get("SFHA_TF")
    return FloodZoneResult(
        flood_zone=flood_zone,
        zone_subtype=attrs.get("ZONE_SUBTY") or None,
        is_special_flood_hazard_area=(sfha_flag == "T") if sfha_flag in ("T", "F") else None,
    )
