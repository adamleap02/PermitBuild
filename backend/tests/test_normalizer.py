from __future__ import annotations

from app.connectors.normalizer import (
    build_full_address,
    normalize_address,
    split_address_components,
)


def test_normalize_basic_street_suffix():
    assert normalize_address("930 sutter street") == "930 SUTTER ST"


def test_normalize_directional_and_unit():
    assert normalize_address("1245 North Miller Road, Apartment 4") == "1245 N MILLER RD APT 4"


def test_normalize_avenue_and_suite():
    assert normalize_address("100 Main Avenue Suite 200") == "100 MAIN AVE STE 200"


def test_normalize_handles_none_and_empty():
    assert normalize_address(None) is None
    assert normalize_address("   ") is None


def test_normalize_is_idempotent():
    once = normalize_address("760 East University Drive")
    twice = normalize_address(once)
    assert once == twice == "760 E UNIVERSITY DR"


def test_split_address_components_with_full_string():
    parts = split_address_components("930 Sutter St, San Francisco, CA 94109")
    assert parts["street"] == "930 Sutter St"
    assert parts["city"] == "San Francisco"
    assert parts["state"] == "CA"
    assert parts["zip_code"] == "94109"


def test_split_address_components_missing_parts():
    parts = split_address_components("930 Sutter St")
    assert parts["street"] == "930 Sutter St"
    assert parts["city"] is None
    assert parts["state"] is None
    assert parts["zip_code"] is None


def test_build_full_address_from_components():
    result = build_full_address(
        street_number="1245",
        street_direction="N",
        street_name="Miller",
        street_suffix="Rd",
        city="Tempe",
        state="AZ",
        zip_code="85281",
    )
    assert result == "1245 N MILLER RD TEMPE AZ 85281"


def test_build_full_address_returns_none_without_street():
    assert build_full_address(None, None, None, None) is None
