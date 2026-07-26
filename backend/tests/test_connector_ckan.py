from __future__ import annotations

from app.connectors.ckan import CKAN_SOURCES, CKANConnector

# Shaped like real rows from San Antonio's CKAN "PERMITS ISSUED" datastore
# resource (data.sanantonio.gov). Two rows share one master "PERMIT #" (a
# multi-trade permit) and carry DIFFERENT coordinate systems -- both real,
# live-verified quirks the mapping must handle.
SAMPLE_WGS84_ROW = {
    "_id": 1,
    "PERMIT TYPE": "Comm New Building Permit",
    "PERMIT #": "COM-BLG-PMT24-40200788",
    "PROJECT NAME": "Taco Palenque",
    "WORK TYPE": "New",
    "ADDRESS": "8751 STATE HWY 151, City of San Antonio, TX 78245",
    "X_COORD": "-98.558092",
    "Y_COORD": "29.315051",
    "DATE SUBMITTED": "2024-08-02",
    "DATE ISSUED": "2025-01-01",
    "DECLARED VALUATION": "3500000",
    "AREA (SF)": "9110",
    "PRIMARY CONTACT": "Taco Palenque",
}

SAMPLE_STATEPLANE_ROW = {
    "_id": 2,
    "PERMIT TYPE": "Electrical General Permit",
    "PERMIT #": "COM-BLG-PMT24-40200788",  # same master number as row above
    "ADDRESS": "8751 STATE HWY 151, City of San Antonio, TX 78245",
    "X_COORD": "2076498.5",   # Texas State Plane feet, NOT lon
    "Y_COORD": "13708187.9",  # Texas State Plane feet, NOT lat
    "DATE ISSUED": "2025-01-01",
    "DECLARED VALUATION": None,
    "PRIMARY CONTACT": "Taco Palenque",
}


def _conn():
    return CKANConnector(CKAN_SOURCES["san_antonio_permits"])


def test_san_antonio_core_field_mapping():
    n = _conn()._map_record(SAMPLE_WGS84_ROW, "res-uuid")
    assert n["permit_type"] == "Comm New Building Permit"
    assert n["valuation"] == 3500000.0
    assert n["estimated_cost"] == 3500000.0
    assert n["contractor"] == "Taco Palenque"
    assert n["square_footage"] == 9110.0
    assert n["issue_date"].year == 2025
    assert n["application_date"].month == 8
    assert n["source"].startswith("ckan:data.sanantonio.gov")


def test_san_antonio_permit_number_disambiguated_by_row_id():
    """"PERMIT #" is not unique across rows (multi-trade sub-permits); the
    connector must append CKAN's unique `_id` so the two rows below don't
    collide on our (jurisdiction_id, permit_number) constraint."""
    a = _conn()._map_record(SAMPLE_WGS84_ROW, "res-uuid")["permit_number"]
    b = _conn()._map_record(SAMPLE_STATEPLANE_ROW, "res-uuid")["permit_number"]
    assert a == "COM-BLG-PMT24-40200788-1"
    assert b == "COM-BLG-PMT24-40200788-2"
    assert a != b


def test_san_antonio_accepts_valid_wgs84_coordinates():
    n = _conn()._map_record(SAMPLE_WGS84_ROW, "res-uuid")
    assert round(n["latitude"], 4) == 29.3151
    assert round(n["longitude"], 4) == -98.5581


def test_san_antonio_rejects_state_plane_coordinates():
    """Regression test: out-of-range State Plane values must be dropped to
    None (letting the geocoder fall back on ADDRESS), never stored as a
    latitude of 13 million."""
    n = _conn()._map_record(SAMPLE_STATEPLANE_ROW, "res-uuid")
    assert n["latitude"] is None
    assert n["longitude"] is None


# --- Sixth pass: Boston, MA (data.boston.gov CKAN) ---
# Shaped like real rows from Boston's "Approved Building Permits" datastore.
# declared_valuation is the job value; total_fees is the permit FEE (must NOT
# be mapped into valuation) -- both are $-formatted strings.
BOSTON_ROW = {
    "_id": 1,
    "permitnumber": "A1000569",
    "permittypedescr": "Amendment to a Long Form",
    "status": "Closed",
    "issued_date": "2021-01-28T16:29:26",
    "expiration_date": "2021-07-28T04:00:00",
    "declared_valuation": "$36,500.00",
    "total_fees": "$390.00",
    "sq_feet": "0",
    "occupancytype": "Mixed",
    "worktype": "INTEXT",
    "description": "Interior/Exterior Work",
    "address": "181-183 State ST",
    "city": "Boston",
    "state": "MA",
    "zip": "02109",
    "parcel_id": 303807000,
    "x_longitude": -71.05292400062602,
    "y_latitude": 42.35919000001041,
}


def _boston_conn():
    return CKANConnector(CKAN_SOURCES["boston_permits"])


def test_boston_declared_valuation_parsed_not_fee():
    """Regression test for the fee-vs-valuation discipline: the $-formatted
    declared_valuation must be parsed to a float and the permit fee
    (total_fees) must NOT leak into valuation/estimated_cost."""
    n = _boston_conn()._map_record(BOSTON_ROW, "res-uuid")
    assert n["valuation"] == 36500.0
    assert n["estimated_cost"] == 36500.0
    assert n["valuation"] != 390.0  # total_fees, never the value


def test_boston_core_field_mapping():
    n = _boston_conn()._map_record(BOSTON_ROW, "res-uuid")
    assert n["permit_number"] == "A1000569"
    assert n["permit_type"] == "Amendment to a Long Form"
    assert n["status"] == "Closed"
    assert n["issue_date"].year == 2021
    assert n["property_address"] == "181-183 State ST, Boston, MA 02109"
    assert round(n["latitude"], 4) == 42.3592
    assert round(n["longitude"], 4) == -71.0529
    assert n["source"].startswith("ckan:data.boston.gov")


def test_boston_missing_permitnumber_falls_back_to_row_id():
    row = dict(BOSTON_ROW, permitnumber="", _id=99)
    n = _boston_conn()._map_record(row, "res-uuid")
    assert n["permit_number"] == "BOS-99"
