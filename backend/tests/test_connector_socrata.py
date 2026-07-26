from __future__ import annotations

from app.connectors.socrata import SOCRATA_SOURCES, SocrataConnector

# A trimmed but real-shaped record captured live from
# https://data.sfgov.org/resource/i98e-djp9.json during development.
SAMPLE_SF_RECORD = {
    "permit_number": "201806293452",
    "permit_type": "3",
    "permit_type_definition": "additions alterations or repairs",
    "street_number": "930",
    "street_name": "Sutter",
    "street_suffix": "St",
    "description": "add 1 new accessory dwelling units, per ord 162-16.",
    "status": "expired",
    "filed_date": "2018-06-29T15:36:37.000",
    "issued_date": "2019-08-06T15:37:34.000",
    "last_permit_activity_date": "2020-07-01T12:04:05.000",
    "estimated_cost": "40000.0",
    "revised_cost": "76200.0",
    "proposed_units": "48.0",
    "block": "0280",
    "lot": "008",
    "location": {"type": "Point", "coordinates": [-122.415746391, 37.788599552]},
}


def test_sf_field_mapping_maps_core_fields():
    connector = SocrataConnector(SOCRATA_SOURCES["sf_building_permits"])
    normalized = connector._map_record(SAMPLE_SF_RECORD)

    assert normalized["permit_number"] == "201806293452"
    assert normalized["permit_type"] == "additions alterations or repairs"
    assert normalized["status"] == "expired"
    assert normalized["property_address"] == "930 Sutter St"
    assert normalized["parcel_number"] == "0280/008"
    assert normalized["estimated_cost"] == 40000.0
    assert normalized["valuation"] == 76200.0  # revised_cost preferred over estimated_cost
    assert normalized["units"] == 48
    assert normalized["source"] == "socrata:data.sfgov.org:i98e-djp9"
    assert normalized["raw_data"] == SAMPLE_SF_RECORD


def test_sf_field_mapping_extracts_lat_lon_from_nested_location():
    connector = SocrataConnector(SOCRATA_SOURCES["sf_building_permits"])
    normalized = connector._map_record(SAMPLE_SF_RECORD)

    assert round(normalized["latitude"], 4) == round(37.788599552, 4)
    assert round(normalized["longitude"], 4) == round(-122.415746391, 4)


def test_sf_field_mapping_parses_dates():
    connector = SocrataConnector(SOCRATA_SOURCES["sf_building_permits"])
    normalized = connector._map_record(SAMPLE_SF_RECORD)

    assert normalized["application_date"].year == 2018
    assert normalized["application_date"].month == 6
    assert normalized["issue_date"].year == 2019


def test_field_mapping_handles_missing_optional_fields_gracefully():
    connector = SocrataConnector(SOCRATA_SOURCES["sf_building_permits"])
    sparse_record = {"permit_number": "X-1"}
    normalized = connector._map_record(sparse_record)

    assert normalized["permit_number"] == "X-1"
    assert normalized["property_address"] is None
    assert normalized["estimated_cost"] is None
    assert normalized["latitude"] is None


def test_resource_url_is_built_from_domain_and_dataset_id():
    connector = SocrataConnector(SOCRATA_SOURCES["chicago_building_permits"])
    assert connector.resource_url == "https://data.cityofchicago.org/resource/ydr8-5enu.json"


def test_chicago_field_mapping_fixes_valuation_status_and_contact_roles():
    """Regression test for the fee-vs-valuation and contact-role bugs found
    during the field-completeness audit (BLOCKERS.md #4a)."""
    connector = SocrataConnector(SOCRATA_SOURCES["chicago_building_permits"])
    record = {
        "permit_": "100999999",
        "permit_type": "PERMIT - EASY PERMIT PROCESS",
        "permit_status": "ACTIVE",
        "reported_cost": "50000",
        "subtotal_paid": "75",  # a FEE -- must NOT end up in estimated_cost/valuation
        "total_fee": "75",
        "contact_1_type": "EXPEDITOR",
        "contact_1_name": "ON TIME EXPEDITING INC.",
        "contact_2_type": "ARCHITECT",
        "contact_2_name": "KOZIOL FREDERICK E",
        "contact_3_type": "GENERAL CONTRACTOR",
        "contact_3_name": "ACME BUILDERS LLC",
    }
    normalized = connector._map_record(record)

    assert normalized["status"] == "ACTIVE"
    assert normalized["estimated_cost"] == 50000.0
    assert normalized["valuation"] == 50000.0
    assert normalized["contractor"] == "ACME BUILDERS LLC"
    assert normalized["architect"] == "KOZIOL FREDERICK E"


def test_austin_field_mapping_recovers_valuation_and_is_zero_safe():
    """Regression test for the missing total_job_valuation mapping and the
    zero-value fallback bug found during the field-completeness audit."""
    connector = SocrataConnector(SOCRATA_SOURCES["austin_building_permits"])

    populated = connector._map_record({"permit_number": "A-1", "total_job_valuation": "150000"})
    assert populated["estimated_cost"] == 150000.0

    genuinely_zero = connector._map_record(
        {"permit_number": "A-2", "total_job_valuation": "0", "total_valuation_remodel": "5000"}
    )
    # A real $0 total_job_valuation must be reported as 0.0, not silently
    # replaced by the remodel fallback (that was the zero-safety bug).
    assert genuinely_zero["estimated_cost"] == 0.0

    missing = connector._map_record({"permit_number": "A-3", "total_valuation_remodel": "8000"})
    assert missing["estimated_cost"] == 8000.0


def test_mesa_field_mapping():
    connector = SocrataConnector(SOCRATA_SOURCES["mesa_az_permits"])
    record = {
        "permit_number": "BLD2024-00123",
        "permit_type": "Residential",
        "status": "Issued",
        "property_address": "123 E MAIN ST",
        "job_value": "0",
        "total_valuation": "250000",
        "contractor_name": "Desert Homes Inc",
        "applicant": "Jane Homeowner",
        "total_square_feet": "2400",
        "number_of_dwelling_units": "1",
        "latitude": "33.42",
        "longitude": "-111.83",
    }
    normalized = connector._map_record(record)

    assert normalized["estimated_cost"] == 250000.0  # total_valuation preferred over job_value
    assert normalized["contractor"] == "Desert Homes Inc"
    assert normalized["builder"] == "Jane Homeowner"
    assert normalized["square_footage"] == 2400.0
    assert normalized["units"] == 1


def test_cambridge_field_mapping_captures_architect_and_engineer():
    connector = SocrataConnector(SOCRATA_SOURCES["cambridge_new_construction_permits"])
    record = {
        "id": "99001",
        "full_address": "10 Main St, Cambridge, MA 02139",
        "status": "Active",
        "permit type": "Building: New Construction",
        "architect_name": "Jane Architect",
        "engineer_name": "John Engineer",
        "licensed_name": "Bob Contractor",
        "total_cost_of_construction": "1200000",
        "gross_square_footage": "8000",
        "proposed_count_of_dwelling": "4",
        "latitude": "42.37",
        "longitude": "-71.10",
    }
    normalized = connector._map_record(record)

    assert normalized["architect"] == "Jane Architect"
    assert normalized["engineer"] == "John Engineer"
    assert normalized["contractor"] == "Bob Contractor"
    assert normalized["estimated_cost"] == 1200000.0
    assert normalized["units"] == 4


def test_howard_county_field_mapping_has_no_address_by_design():
    """Howard County's dataset genuinely has no street-address column --
    confirm the mapping reflects that honestly instead of guessing."""
    connector = SocrataConnector(SOCRATA_SOURCES["howard_county_permits"])
    normalized = connector._map_record(
        {"permit_number": "B25000001", "permit_type": "SOLAR EXPRESS", "city": "COLUMBIA", "zip": "21044"}
    )
    assert normalized["property_address"] is None
    assert normalized["estimated_cost"] is None


def test_norfolk_field_mapping():
    connector = SocrataConnector(SOCRATA_SOURCES["norfolk_permits"])
    record = {
        "permit_number": "B25-01234",
        "address": "243 W BUTE STREET",
        "gpin": "1427878551",
        "type": "Building",
        "status": "Issued",
        "application_date": "2025-06-06T00:00:00.000",
        "issue_date": "2025-06-10T00:00:00.000",
        "project_cost": "150000",
        "square_footage": "2000",
        "work_type": "New Construction",
    }
    normalized = connector._map_record(record)

    assert normalized["permit_number"] == "B25-01234"
    assert normalized["property_address"] == "243 W BUTE STREET"
    assert normalized["parcel_number"] == "1427878551"
    assert normalized["estimated_cost"] == 150000.0
    assert normalized["square_footage"] == 2000.0
    assert normalized["contractor"] is None  # confirmed absent from this dataset


def test_kansas_city_mo_field_mapping_builds_address_and_maps_valuation():
    connector = SocrataConnector(SOCRATA_SOURCES["kansas_city_mo_permits"])
    record = {
        "permitnum": "2024-BP-001",
        "permittypemapped": "Building",
        "statuscurrent": "Issued",
        "contractorcompanyname": "ACME Construction",
        "originaladdress1": "123 MAIN ST",
        "originalcity": "KANSAS CITY",
        "originalstate": "MO",
        "originalzip": "64106",
        "estprojectcost": "75000",
        "totalsqft": "1800",
        "housingunits": "1",
    }
    normalized = connector._map_record(record)

    assert normalized["contractor"] == "ACME Construction"
    assert normalized["property_address"] == "123 MAIN ST KANSAS CITY MO 64106"
    assert normalized["estimated_cost"] == 75000.0
    assert normalized["units"] == 1


# --- Sixth pass: Somerville, MA (data.somervillema.gov) ---
# The `amount` column is a permit FEE, not a construction valuation -- the
# mapping must leave estimated_cost/valuation None rather than mis-mapping it.
SAMPLE_SOMERVILLE_RECORD = {
    "id": "B14-001277",
    "type": "Residential Building",
    "status": "Issued",
    "application_date": "2014-11-07T00:00:00.000",
    "issue_date": "2014-11-12T00:00:00.000",
    "address": "84 Washington St 610",
    "amount": "278.00",  # a FEE, not a valuation
    "work": "Remove and replace 1500 sf of roofing.",
    "latitude": "42.381492614746094",
    "longitude": "-71.084541320800781",
}


def test_somerville_fee_not_mapped_as_valuation():
    """Regression test: Somerville's `amount` is a permit fee. It must NOT be
    mapped into valuation/estimated_cost (which would skew budget scoring)."""
    n = SocrataConnector(SOCRATA_SOURCES["somerville_ma_permits"])._map_record(SAMPLE_SOMERVILLE_RECORD)
    assert n["valuation"] is None
    assert n["estimated_cost"] is None
    assert n["permit_number"] == "B14-001277"
    assert n["property_address"] == "84 Washington St 610, Somerville, MA"
    assert round(n["latitude"], 3) == 42.381
    assert n["issue_date"].year == 2014


# ---------------------------------------------------------------------------
# Non-unique-permit-number disambiguation (BLOCKERS.md §5i). Several sources
# reuse one permit_number across genuinely-distinct rows; each suffixes a
# guaranteed-unique per-row key so they don't collapse/collide.
# ---------------------------------------------------------------------------


def test_sf_disambiguates_permit_number_with_record_id():
    connector = SocrataConnector(SOCRATA_SOURCES["sf_building_permits"])
    a = connector._map_record({**SAMPLE_SF_RECORD, "record_id": "1410625418857"})
    b = connector._map_record({**SAMPLE_SF_RECORD, "record_id": "1410626418858"})
    # Same base permit_number, different record_id => distinct permit numbers.
    assert a["permit_number"] == "201806293452-1410625418857"
    assert b["permit_number"] == "201806293452-1410626418858"
    assert a["permit_number"] != b["permit_number"]


def test_cincinnati_disambiguates_permit_number_with_row_id():
    connector = SocrataConnector(SOCRATA_SOURCES["cincinnati_permits"])
    base = {"permitnum": "2013P06831", "issueddate": "2013-09-20T00:00:00.000"}
    a = connector._map_record({**base, "permittypemapped": "Wrecking", ":id": "row-aaaa"})
    b = connector._map_record({**base, "permittypemapped": "Excavation/Fill", ":id": "row-bbbb"})
    assert a["permit_number"] == "2013P06831-row-aaaa"
    assert b["permit_number"] == "2013P06831-row-bbbb"


def test_marin_falls_back_to_unique_id_when_permit_number_blank():
    connector = SocrataConnector(SOCRATA_SOURCES["marin_county_permits"])
    got = connector._map_record({"permit_number": "", "unique_id": "abc-123"})
    assert got["permit_number"] == "MARIN-abc-123"
    got2 = connector._map_record({"permit_number": "B12-9", "unique_id": "abc-123"})
    assert got2["permit_number"] == "B12-9-abc-123"
