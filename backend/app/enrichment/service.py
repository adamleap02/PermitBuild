"""
Orchestrates all free property/parcel enrichment sources for a single
Property row: US Census ACS demographics (by tract), FEMA flood zone,
and Cook County Assessor parcel characteristics (where the parcel looks
like a Cook County PIN). Populates Property's dedicated columns
(year_built, lot_size_sqft, etc.) where a real value is found, and
stashes the rest (tract GEOID, flood zone detail, raw assessor payload)
in Property.enrichment (JSON) so nothing is lost even where there's no
dedicated column.

Idempotent by default: skips a source if Property.enrichment already
has that source's key, so re-running ingest doesn't re-hit external
APIs for properties already enriched. Pass force=True to refresh.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Optional

from sqlalchemy.orm import Session

from app.enrichment import census_acs, cook_county_assessor, fema_flood
from app.models import Property

logger = logging.getLogger(__name__)

# Cook County PINs are 14 digits; used as a light heuristic to decide
# whether it's worth querying the Cook County Assessor for a given
# Property's parcel_number (works for Cook County AND City of Chicago
# permits, since Chicago is inside Cook County and Chicago-mapped parcel
# numbers -- when present -- follow the same PIN convention).
def _looks_like_cook_county_pin(parcel_number: Optional[str]) -> bool:
    if not parcel_number:
        return False
    digits = "".join(ch for ch in parcel_number if ch.isdigit())
    return len(digits) == 14


def enrich_property(db: Session, prop: Property, force: bool = False) -> dict:
    """Run every applicable enrichment source for `prop`, mutating it in
    place, and return a small summary dict of what was added/updated
    (for logging/backfill-script reporting)."""
    if prop is None:
        return {}

    enrichment = dict(prop.enrichment or {})
    summary: dict = {}

    if prop.latitude is not None and prop.longitude is not None:
        if force or "fema_flood_zone" not in enrichment:
            flood = fema_flood.get_flood_zone(prop.latitude, prop.longitude)
            if flood is not None:
                enrichment["fema_flood_zone"] = asdict(flood)
                summary["fema_flood_zone"] = flood.flood_zone
            else:
                enrichment["fema_flood_zone"] = None  # explicitly checked, no match

        tract: Optional[census_acs.CensusTract] = None
        if force or "census_tract" not in enrichment:
            tract = census_acs.get_tract_for_point(prop.latitude, prop.longitude)
            if tract is not None:
                enrichment["census_tract"] = {
                    "geoid": tract.geoid,
                    "state_fips": tract.state_fips,
                    "county_fips": tract.county_fips,
                    "tract_code": tract.tract_code,
                    "name": tract.name,
                }
                summary["census_tract"] = tract.geoid
            else:
                enrichment["census_tract"] = None
        elif enrichment.get("census_tract"):
            # Tract was already resolved in a prior run -- rehydrate it so
            # ACS demographics can still be fetched below even if
            # CENSUS_API_KEY wasn't configured back then (e.g. a human
            # adds the key after the fact; this makes that retroactive
            # without needing --force, which would also re-hit FEMA/
            # Cook County unnecessarily).
            cached = enrichment["census_tract"]
            tract = census_acs.CensusTract(
                state_fips=cached["state_fips"],
                county_fips=cached["county_fips"],
                tract_code=cached["tract_code"],
                geoid=cached["geoid"],
                name=cached.get("name"),
            )

        if tract is not None:
            if census_acs.is_configured() and (force or "census_acs" not in enrichment):
                demographics = census_acs.get_acs_demographics(tract)
                if demographics is not None:
                    enrichment["census_acs"] = {
                        "median_household_income": demographics.median_household_income,
                        "median_home_value": demographics.median_home_value,
                        "population": demographics.population,
                    }
                    summary["census_acs"] = enrichment["census_acs"]
                enrichment.pop("census_acs_status", None)
            elif not census_acs.is_configured() and "census_acs" not in enrichment:
                enrichment.setdefault(
                    "census_acs_status",
                    "not_configured: CENSUS_API_KEY unset -- see BLOCKERS.md",
                )
            else:
                enrichment["census_tract"] = None

    if _looks_like_cook_county_pin(prop.parcel_number) and (force or "cook_county_assessor" not in enrichment):
        parcel_data = cook_county_assessor.get_parcel_data(prop.parcel_number)
        if parcel_data is not None:
            enrichment["cook_county_assessor"] = {
                "year_built": parcel_data.year_built,
                "building_sqft": parcel_data.building_sqft,
                "land_sqft": parcel_data.land_sqft,
                "bedrooms": parcel_data.bedrooms,
                "full_baths": parcel_data.full_baths,
                "half_baths": parcel_data.half_baths,
                "stories_description": parcel_data.stories_description,
                "property_use": parcel_data.property_use,
                "assessed_total": parcel_data.assessed_total,
                "assessed_building": parcel_data.assessed_building,
                "assessed_land": parcel_data.assessed_land,
                "assessment_year": parcel_data.assessment_year,
            }
            summary["cook_county_assessor"] = True

            # Populate dedicated Property columns where we have a real
            # value and the column isn't already set (don't clobber
            # existing data, e.g. from a future commercial-provider
            # integration).
            if parcel_data.year_built and not prop.year_built:
                prop.year_built = parcel_data.year_built
            if parcel_data.building_sqft and not prop.building_size_sqft:
                prop.building_size_sqft = parcel_data.building_sqft
            if parcel_data.land_sqft and not prop.lot_size_sqft:
                prop.lot_size_sqft = parcel_data.land_sqft
            if parcel_data.bedrooms and not prop.bedrooms:
                prop.bedrooms = parcel_data.bedrooms
            if parcel_data.full_baths is not None and not prop.bathrooms:
                prop.bathrooms = (parcel_data.full_baths or 0) + 0.5 * (parcel_data.half_baths or 0)
            if parcel_data.property_use and not prop.property_type:
                prop.property_type = parcel_data.property_use
        else:
            enrichment["cook_county_assessor"] = None

    prop.enrichment = enrichment
    db.add(prop)
    return summary
