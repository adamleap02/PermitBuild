from __future__ import annotations

import httpx
import pytest

from app.connectors.geocoder import CensusGeocoder

FAKE_CENSUS_RESPONSE = {
    "result": {
        "input": {"address": {"address": "930 Sutter St, San Francisco, CA 94109"}},
        "addressMatches": [
            {
                "coordinates": {"x": -122.415725259501, "y": 37.788374431092},
                "matchedAddress": "930 SUTTER ST, SAN FRANCISCO, CA, 94109",
            }
        ],
    }
}

FAKE_CENSUS_NO_MATCH = {"result": {"input": {}, "addressMatches": []}}


def test_geocode_success_mocked(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        assert "onelineaddress" in url
        request = httpx.Request("GET", url)
        return httpx.Response(200, json=FAKE_CENSUS_RESPONSE, request=request)

    monkeypatch.setattr(httpx, "get", fake_get)

    geocoder = CensusGeocoder()
    result = geocoder.geocode("930 Sutter St, San Francisco, CA 94109")

    assert result is not None
    assert round(result.latitude, 4) == round(37.788374431092, 4)
    assert round(result.longitude, 4) == round(-122.415725259501, 4)
    assert result.source == "census"


def test_geocode_no_match_returns_none(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        request = httpx.Request("GET", url)
        return httpx.Response(200, json=FAKE_CENSUS_NO_MATCH, request=request)

    monkeypatch.setattr(httpx, "get", fake_get)

    geocoder = CensusGeocoder()
    result = geocoder.geocode("1 Nonexistent Way, Nowhere, ZZ 00000")
    assert result is None


def test_geocode_empty_address_returns_none():
    geocoder = CensusGeocoder()
    assert geocoder.geocode("") is None
    assert geocoder.geocode("   ") is None


def test_geocode_http_error_returns_none(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise httpx.ConnectTimeout("simulated timeout")

    monkeypatch.setattr(httpx, "get", fake_get)

    geocoder = CensusGeocoder()
    result = geocoder.geocode("930 Sutter St, San Francisco, CA 94109")
    assert result is None


@pytest.mark.integration
def test_census_geocoder_live_integration():
    """Hits the real, live, free US Census geocoder -- no key required."""
    geocoder = CensusGeocoder()
    result = geocoder.geocode("930 Sutter St, San Francisco, CA 94109")

    assert result is not None
    assert -123 < result.longitude < -122
    assert 37 < result.latitude < 38
    assert "SUTTER" in result.matched_address.upper()
