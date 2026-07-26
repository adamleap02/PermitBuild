from __future__ import annotations

import httpx
import pytest

from app.enrichment import census_acs, cook_county_assessor, fema_flood
from app.enrichment.service import _looks_like_cook_county_pin, enrich_property
from app.models import Property


def _fake_response(json_body, status_code=200):
    request = httpx.Request("GET", "https://example.test")
    return httpx.Response(status_code, json=json_body, request=request)


# --- FEMA flood zone -------------------------------------------------------


def test_fema_flood_zone_parses_real_shaped_response(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        assert "NFHL/MapServer/28/query" in url
        return _fake_response(
            {"features": [{"attributes": {"FLD_ZONE": "AE", "ZONE_SUBTY": "FLOODWAY", "SFHA_TF": "T"}}]}
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    result = fema_flood.get_flood_zone(37.7, -122.4)

    assert result.flood_zone == "AE"
    assert result.zone_subtype == "FLOODWAY"
    assert result.is_special_flood_hazard_area is True


def test_fema_flood_zone_no_match_returns_none(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _fake_response({"features": []}))
    assert fema_flood.get_flood_zone(0.0, 0.0) is None


def test_fema_flood_zone_request_error_returns_none(monkeypatch):
    def fake_get(*a, **k):
        raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(httpx, "get", fake_get)
    assert fema_flood.get_flood_zone(37.7, -122.4) is None


@pytest.mark.integration
def test_fema_flood_zone_live_integration():
    """Hits the real, live, free FEMA NFHL ArcGIS service."""
    result = fema_flood.get_flood_zone(37.788599, -122.415746)  # a real SF permit location
    assert result is not None
    assert result.flood_zone


# --- Census ACS tract lookup (keyless) + demographics (requires a key) ----


def test_get_tract_for_point_parses_real_shaped_response(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        assert "geographies/coordinates" in url
        return _fake_response(
            {
                "result": {
                    "geographies": {
                        "Census Tracts": [
                            {"STATE": "06", "COUNTY": "075", "TRACT": "012001", "NAME": "Census Tract 120.01"}
                        ]
                    }
                }
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    tract = census_acs.get_tract_for_point(37.788599, -122.415746)

    assert tract.geoid == "06075012001"
    assert tract.state_fips == "06"


def test_get_tract_for_point_no_match_returns_none(monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: _fake_response({"result": {"geographies": {"Census Tracts": []}}})
    )
    assert census_acs.get_tract_for_point(0.0, 0.0) is None


def test_acs_demographics_skips_without_api_key(monkeypatch):
    monkeypatch.setattr(census_acs, "CENSUS_API_KEY", None)
    assert census_acs.is_configured() is False
    tract = census_acs.CensusTract(state_fips="06", county_fips="075", tract_code="012001", geoid="06075012001")
    # Must return None WITHOUT making any HTTP request when unconfigured.
    result = census_acs.get_acs_demographics(tract)
    assert result is None


def test_acs_demographics_parses_response_when_configured(monkeypatch):
    monkeypatch.setattr(census_acs, "CENSUS_API_KEY", "fake-test-key")

    def fake_get(url, params=None, timeout=None):
        assert params["key"] == "fake-test-key"
        return _fake_response([["NAME", "B19013_001E", "B25077_001E", "B01003_001E", "state", "county", "tract"],
                                ["Census Tract 120.01", "125000", "950000", "3200", "06", "075", "012001"]])

    monkeypatch.setattr(httpx, "get", fake_get)
    tract = census_acs.CensusTract(state_fips="06", county_fips="075", tract_code="012001", geoid="06075012001")
    result = census_acs.get_acs_demographics(tract)

    assert result.median_household_income == 125000
    assert result.median_home_value == 950000
    assert result.population == 3200


@pytest.mark.integration
def test_get_tract_for_point_live_integration():
    """Hits the real, live, free (keyless) Census geographies endpoint."""
    tract = census_acs.get_tract_for_point(37.788599, -122.415746)
    assert tract is not None
    assert tract.state_fips == "06"
    assert tract.county_fips == "075"


# --- Cook County Assessor ---------------------------------------------------


def test_looks_like_cook_county_pin():
    assert _looks_like_cook_county_pin("01011000040000") is True
    assert _looks_like_cook_county_pin("01-01-100-004-0000") is True  # dashes stripped (14 digits)
    assert _looks_like_cook_county_pin("1448/004") is False  # SF-style block/lot, too short
    assert _looks_like_cook_county_pin(None) is False


def test_cook_county_assessor_parses_real_shaped_response(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        if "x54s-btds" in url:
            return _fake_response([{"char_yrblt": "1955", "char_bldg_sf": "1400", "char_land_sf": "5000",
                                     "char_beds": "3", "char_fbath": "2", "char_hbath": "0",
                                     "char_use": "Single-Family"}])
        return _fake_response([{"certified_tot": "85000", "certified_bldg": "60000", "certified_land": "25000",
                                 "year": "2023"}])

    monkeypatch.setattr(httpx, "get", fake_get)
    result = cook_county_assessor.get_parcel_data("01011000040000")

    assert result.year_built == 1955
    assert result.building_sqft == 1400.0
    assert result.assessed_total == 85000.0
    assert result.property_use == "Single-Family"


def test_cook_county_assessor_returns_none_for_non_cook_pin():
    assert cook_county_assessor.get_parcel_data("1448/004") is None


@pytest.mark.integration
def test_cook_county_assessor_live_integration():
    """Hits the real, live, free Cook County Assessor Socrata datasets."""
    # A real PIN pulled live during development (see BLOCKERS.md).
    result = cook_county_assessor.get_parcel_data("01011010301055")
    # Not asserting a match (individual PINs can be delisted/reclassified
    # over time) -- asserting the live call completes without raising and
    # returns either None or a well-formed result.
    assert result is None or isinstance(result.pin, str)


# --- Orchestration service ---------------------------------------------------


def test_enrich_property_is_idempotent_and_uses_dedicated_columns(db_session, monkeypatch):
    monkeypatch.setattr(
        fema_flood, "get_flood_zone",
        lambda lat, lon, timeout=15.0: fema_flood.FloodZoneResult("X", "AREA OF MINIMAL FLOOD HAZARD", False),
    )
    monkeypatch.setattr(
        census_acs, "get_tract_for_point",
        lambda lat, lon, timeout=10.0: census_acs.CensusTract("06", "075", "012001", "06075012001"),
    )
    monkeypatch.setattr(census_acs, "is_configured", lambda: False)
    monkeypatch.setattr(
        cook_county_assessor, "get_parcel_data",
        lambda pin, timeout=15.0: cook_county_assessor.CookCountyParcelData(
            pin=pin, year_built=1955, building_sqft=1400.0, land_sqft=5000.0,
            bedrooms=3.0, full_baths=2.0, half_baths=0.0, property_use="Single-Family",
            assessed_total=85000.0,
        ),
    )

    prop = Property(
        address="123 Test St",
        normalized_address="123 TEST ST",
        latitude=37.7,
        longitude=-122.4,
        parcel_number="01011000040000",
    )
    db_session.add(prop)
    db_session.commit()
    db_session.refresh(prop)

    summary = enrich_property(db_session, prop)
    db_session.commit()

    assert summary["fema_flood_zone"] == "X"
    assert summary["census_tract"] == "06075012001"
    assert summary["cook_county_assessor"] is True
    assert prop.year_built == 1955
    assert prop.building_size_sqft == 1400.0
    assert prop.bathrooms == 2.0
    assert prop.enrichment["fema_flood_zone"]["flood_zone"] == "X"

    # Second call should be a no-op (idempotent) -- flip the mocks to
    # raise if called again, then confirm nothing errors/changes.
    def _boom(*a, **k):
        raise AssertionError("should not re-fetch an already-enriched source")

    monkeypatch.setattr(fema_flood, "get_flood_zone", _boom)
    monkeypatch.setattr(census_acs, "get_tract_for_point", _boom)
    monkeypatch.setattr(cook_county_assessor, "get_parcel_data", _boom)

    second_summary = enrich_property(db_session, prop)
    assert second_summary == {}


def test_enrich_property_handles_no_lat_lon_or_parcel(db_session):
    prop = Property(address="456 No Data Way", normalized_address="456 NO DATA WAY")
    db_session.add(prop)
    db_session.commit()
    db_session.refresh(prop)

    summary = enrich_property(db_session, prop)
    assert summary == {}
