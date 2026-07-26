from __future__ import annotations

from app.connectors.arcgis import ARCGIS_SOURCES, ArcGISConnector

# Shaped like a real record from the City of Tempe, AZ Building Permits
# FeatureServer (https://services.arcgis.com/lQySeXwbBg53XWDi/.../FeatureServer/0)
SAMPLE_TEMPE_ATTRS = {
    "PermitNum": "PV180038",
    "PermitTypeDesc": "Paving Permit",
    "StatusCurrent": "Closed",
    "AppliedDateDtm": 1516060800000,  # 2018-01-16T00:00:00Z
    "IssuedDateDtm": 1516665600000,
    "OriginalAddress1": "1245 N MILLER RD",
    "OriginalCity": "TEMPE",
    "OriginalState": "AZ",
    "OriginalZip": "85288",
    "EstProjectCost": 8500.0,
    "Fee": 125.5,
    "Description": "Repave parking lot",
    "PermitClass": "Commercial",
    "TotalSqFt": 5000,
    "HousingUnits": None,
    "ContractorCompanyName": "ABC Paving Co",
    "Latitude": 33.442974,
    "Longitude": -111.91789351,
}


def test_tempe_field_mapping_maps_core_fields():
    connector = ArcGISConnector(ARCGIS_SOURCES["tempe_az_building_permits"])
    normalized = connector._map_record(SAMPLE_TEMPE_ATTRS)

    assert normalized["permit_number"] == "PV180038"
    assert normalized["permit_type"] == "Paving Permit"
    assert normalized["status"] == "Closed"
    assert normalized["contractor"] == "ABC Paving Co"
    assert normalized["property_address"] == "1245 N MILLER RD, TEMPE AZ 85288"
    assert normalized["estimated_cost"] == 8500.0
    # valuation should reflect EstProjectCost (the real project value), NOT
    # Fee (a permit fee) -- regression test for the fee/valuation mapping
    # bug found during the field-completeness audit.
    assert normalized["valuation"] == 8500.0
    assert normalized["square_footage"] == 5000.0
    assert normalized["units"] is None
    assert normalized["source"].startswith("arcgis:")


def test_tempe_field_mapping_converts_esri_epoch_dates():
    connector = ArcGISConnector(ARCGIS_SOURCES["tempe_az_building_permits"])
    normalized = connector._map_record(SAMPLE_TEMPE_ATTRS)

    assert normalized["application_date"].year == 2018
    assert normalized["issue_date"].year == 2018


def test_tempe_field_mapping_lat_lon_direct_columns():
    connector = ArcGISConnector(ARCGIS_SOURCES["tempe_az_building_permits"])
    normalized = connector._map_record(SAMPLE_TEMPE_ATTRS)

    assert round(normalized["latitude"], 4) == round(33.442974, 4)
    assert round(normalized["longitude"], 4) == round(-111.91789351, 4)


def test_denver_valuation_not_mismapped_from_fee():
    """Regression test: Denver's VALUATION field must drive
    estimated_cost/valuation, never PERMIT_FEE (the fee-vs-valuation bug
    class found during the field-completeness audit)."""
    connector = ArcGISConnector(ARCGIS_SOURCES["denver_co_residential_permits"])
    normalized = connector._map_record(
        {"PERMIT_NUM": "2024-RESCON-001", "VALUATION": 50000.0, "PERMIT_FEE": 350.0}
    )
    assert normalized["estimated_cost"] == 50000.0
    assert normalized["valuation"] == 50000.0


SAMPLE_MIAMI_DADE_ATTRS = {
    "PermitNumber": "2024062245",
    "ApplicationTypeDescription": "DEMOLISH",
    "ApplicationDate": 1709182800000,
    "PermitIssuedDate": "2024-07-24",  # esriFieldTypeDateOnly -- plain string, not epoch millis
    "PropertyAddress": "4935 SW 117 AVE",
    "City": "MIAMI",
    "State": "FL",
    "FolioNumber": "3040190050450",
    "EstimatedValue": "75000",
    "ContractorName": "A-B REMODELING INC",
    "ArchitectName": "NOT LISTED",
    "OwnerName": "MIAMI-DADE COUNTY",
    "SquareFootage": "2600",
    "StructureUnits": "1",
}


def test_miami_dade_field_mapping_parses_date_only_field():
    connector = ArcGISConnector(ARCGIS_SOURCES["miami_dade_permits"])
    normalized = connector._map_record(SAMPLE_MIAMI_DADE_ATTRS)

    assert normalized["issue_date"].year == 2024
    assert normalized["issue_date"].month == 7
    assert normalized["issue_date"].day == 24
    assert normalized["application_date"].year == 2024


def test_miami_dade_field_mapping_strips_placeholder_values():
    """Regression test: literal "NOT LISTED" placeholder text must not
    leak into the architect field."""
    connector = ArcGISConnector(ARCGIS_SOURCES["miami_dade_permits"])
    normalized = connector._map_record(SAMPLE_MIAMI_DADE_ATTRS)

    assert normalized["architect"] is None
    assert normalized["contractor"] == "A-B REMODELING INC"


def test_miami_dade_owner_name_bonus_key_present():
    connector = ArcGISConnector(ARCGIS_SOURCES["miami_dade_permits"])
    normalized = connector._map_record(SAMPLE_MIAMI_DADE_ATTRS)
    assert normalized["_owner_name"] == "MIAMI-DADE COUNTY"


def test_mecklenburg_field_mapping_reads_geometry_and_owner():
    connector = ArcGISConnector(ARCGIS_SOURCES["mecklenburg_county_permits"])
    attrs = {
        "permitnum": "B0583946",
        "permittype": "One/Two Family",
        "permitstat": "Complete",
        "projadd": "9600 VERONICA DR",
        "parcelnum": "11144234",
        "bldgcost": 100100.0,
        "totalsqft": 2527,
        "numunits": 1,
        "ownname": "THE BRADFORDT CO.",
        "_geometry": {"x": -80.781, "y": 35.059},
    }
    normalized = connector._map_record(attrs)

    assert normalized["property_address"] == "9600 VERONICA DR"
    assert normalized["estimated_cost"] == 100100.0
    assert round(normalized["latitude"], 3) == 35.059
    assert round(normalized["longitude"], 3) == -80.781
    assert normalized["_owner_name"] == "THE BRADFORDT CO."


def test_query_url_appends_query_segment():
    connector = ArcGISConnector(ARCGIS_SOURCES["tempe_az_building_permits"])
    assert connector.query_url.endswith("/FeatureServer/0/query")


def test_philadelphia_field_mapping_confirms_real_provenance_and_owner():
    """This ArcGIS item is titled/owned as if it were Milwaukee data, but the
    real field values (opa_accoun, opa_owner, PA zip codes) confirm it is
    genuinely Philadelphia -- regression test for that verification."""
    connector = ArcGISConnector(ARCGIS_SOURCES["philadelphia_permits"])
    normalized = connector._map_record(
        {
            "permitnumb": "2020123456",
            "permittype": "ZONING",
            "status": "ISSUED",
            "address": "1724 MEMORIAL AVE",
            "zip": "19104-1018",
            "opa_accoun": "062273800",
            "opa_owner": "PHILLY METROPOLITAN LLC",
            "contractor": "GAOFENG ZHENG",
            "typeofwork": "CHANGE OF USE",
            "_geometry": {"x": -75.19, "y": 39.97},
        }
    )
    assert normalized["property_address"] == "1724 MEMORIAL AVE, Philadelphia, PA 19104-1018"
    assert normalized["parcel_number"] == "062273800"
    assert normalized["_owner_name"] == "PHILLY METROPOLITAN LLC"
    assert normalized["contractor"] == "GAOFENG ZHENG"
    assert normalized["estimated_cost"] is None  # confirmed absent from this layer


def test_detroit_valuation_uses_contractor_cost_not_permit_fee():
    """Regression test (fee-vs-value): Detroit's amt_permit_cost is the permit
    FEE; amt_estimated_contractor_cost is the declared construction value --
    valuation must track the latter, never the fee."""
    connector = ArcGISConnector(ARCGIS_SOURCES["detroit_permits"])
    normalized = connector._map_record(
        {
            "record_id": "RES2024-01173",
            "permit_type": "Alteration",
            "address": "2225 Lakeview St",
            "zip_code": "48215",
            "submitted_date": "2024-04-01",  # esriFieldTypeDateOnly plain string
            "issued_date": "2024-04-02",
            "amt_permit_cost": 510.06,               # the FEE -- must NOT be the valuation
            "amt_estimated_contractor_cost": 8378,   # the declared value
            "num_units": 1,
            "parcel_id": "21052625-6",
            "latitude": 42.378714,
            "longitude": -82.953423,
        }
    )
    assert normalized["valuation"] == 8378.0
    assert normalized["estimated_cost"] == 8378.0
    assert normalized["property_address"] == "2225 Lakeview St, Detroit, MI 48215"
    assert normalized["issue_date"].day == 2
    assert normalized["status"] is None  # confirmed absent on this layer


def test_louisville_valuation_uses_project_costs_not_permit_fee():
    """Regression test (fee-vs-value): Louisville's PERMIT_FEE is the fee;
    PROJECT_COSTS is the declared project value."""
    connector = ArcGISConnector(ARCGIS_SOURCES["louisville_permits"])
    normalized = connector._map_record(
        {
            "PERMIT_NUMBER": "14BL3607",
            "PERMIT_TYPE": "Commercial New",
            "PERMIT_STATUS": "Issued",
            "CONTRACTOR": "PINNACLE PROPERTIES",
            "PERMIT_FEE": 806,           # the FEE
            "PROJECT_COSTS": 650000,     # the declared value
            "SQFT": 6200,
            "ADDRESS": "421 BENJAMIN LN",
            "CITY": "LYNDON",
            "STATE": "KY",
            "ZIPCODE": "40222",
            "LATITUDE": 38.256,
            "LONGITUDE": -85.608,
        }
    )
    assert normalized["valuation"] == 650000.0
    assert normalized["estimated_cost"] == 650000.0
    assert normalized["contractor"] == "PINNACLE PROPERTIES"
    assert normalized["property_address"] == "421 BENJAMIN LN, LYNDON KY 40222"


def test_las_vegas_valuation_prefers_declared_and_rejects_no_geometry():
    """Las Vegas is a Table (no geometry); DECLVLTN (declared) is preferred
    over CALCVLTN, zero-safe, and owner-of-record is captured."""
    connector = ArcGISConnector(ARCGIS_SOURCES["las_vegas_permits"])
    normalized = connector._map_record(
        {
            "APNO": "C24-01395",
            "APTYPE": "Com",
            "WORKTYPE": "New",
            "BLDGAPPLSTATUS": "Issued",
            "APPLICANT": "JC Companies LLC",
            "DECLVLTN": 200000,
            "CALCVLTN": 0,
            "ADDR1": "1700 PAVILION CENTER DR",
            "CITY": "LAS VEGAS",
            "STATE": "NV",
            "ZIP": "89135",
            "PRCLID": 12524403006,
            "NAME": "HOWARD HUGHES COMPANY L L C",
        }
    )
    assert normalized["valuation"] == 200000.0
    assert normalized["property_address"] == "1700 PAVILION CENTER DR, LAS VEGAS, NV 89135"
    assert normalized["parcel_number"] == "12524403006"
    assert normalized["_owner_name"] == "HOWARD HUGHES COMPANY L L C"
    assert normalized["latitude"] is None  # Table type -- geocoder fallback


def test_fort_worth_maps_owner_and_jobvalue():
    connector = ArcGISConnector(ARCGIS_SOURCES["fort_worth_permits"])
    normalized = connector._map_record(
        {
            "Permit_No": "PB16-00123",
            "Permit_Type": "Building",
            "Current_Status": "Issued",
            "File_Date": 1451692800000,
            "Address": "2925 BIG HORN BLUFF CT",
            "Zip_Code": "76179",
            "JobValue": 250000.0,
            "Owner_Full_Name": "JABEZ DEVELOPMENT LP",
            "SqFt": "3200",
            "Units": "1",
            "Latitude": 32.73,
            "Longitude": -97.51,
        }
    )
    assert normalized["valuation"] == 250000.0
    assert normalized["property_address"] == "2925 BIG HORN BLUFF CT, Fort Worth, TX 76179"
    assert normalized["_owner_name"] == "JABEZ DEVELOPMENT LP"
    assert normalized["square_footage"] == 3200.0
    assert normalized["units"] == 1
    assert normalized["issue_date"] is None  # confirmed absent -- only File_Date (application)


def test_helena_mt_field_mapping_formats_parcel_and_prefers_geocoded_address():
    connector = ArcGISConnector(ARCGIS_SOURCES["helena_mt_permits"])
    normalized = connector._map_record(
        {
            "Permit_Number": "RWSF18-00531",
            "Permit_Type": "Utility Water-Sewer",
            "Permit_Status": "Closed",
            "Match_addr": "951 Gibbon Street, #UNIT 1, Helena, MT, 59601",
            "Address": "951 GIBBON ST BOYCE ADDN Unit: UNIT 1\nHELENA, 59601",
            "Parcel_Number": 5.18882832207e15,
            "Permit_Valuation": 0,
            "_geometry": {"x": -112.03, "y": 46.6},
        }
    )
    assert normalized["property_address"] == "951 Gibbon Street, #UNIT 1, Helena, MT, 59601"
    # Must format as a plain integer string, not Python's scientific notation.
    assert normalized["parcel_number"] == "5188828322070000"
    assert normalized["estimated_cost"] == 0.0


# --- Sixth pass: Charleston, SC New Construction Permits ---
# Shaped like a real record from
# services2.arcgis.com/tQaXW7Zb1Vphzvgd/.../New_Construction_Permits/FeatureServer/0
SAMPLE_CHARLESTON_ATTRS = {
    "PERMIT_NUMBER": "BC2020-02070",
    "PERMIT_TYPE": "Building Commercial",
    "WORK_CLASS": "New",
    "PERMIT_STATUS": "Completed",
    "DESCRIPTION": "Constuction of new storage facility- 15,106 SF",
    "APPLICATION_DATE": 1591021830000,
    "ISSUE_DATE": 1599004800000,
    "FINALED_DATE": "04/12/2021                    ",  # plain string, padded
    "VALUATION": 800000.0,
    "MAIN_PARCEL_NUMBER": "B2750000179",
    "PARCELADDR_LINE1": "460 SEVEN FARMS DR",
    "PARCELADDR_LINE2": "Charleston, SC 29492",
    "_geometry": {"x": -79.92265863829984, "y": 32.8566110583242},
}


def test_charleston_field_mapping():
    n = ArcGISConnector(ARCGIS_SOURCES["charleston_sc_permits"])._map_record(SAMPLE_CHARLESTON_ATTRS)
    assert n["permit_number"] == "BC2020-02070"
    assert n["valuation"] == 800000.0
    assert n["estimated_cost"] == 800000.0
    assert n["property_address"] == "460 SEVEN FARMS DR, Charleston, SC 29492"
    assert n["parcel_number"] == "B2750000179"
    assert n["issue_date"].year == 2020
    # FINALED_DATE is a padded plain-string date, not epoch millis
    assert n["completion_date"].year == 2021
    assert round(n["latitude"], 4) == 32.8566
    assert round(n["longitude"], 4) == -79.9227


def test_fort_worth_disambiguates_permit_number_with_capid():
    from app.connectors.arcgis import ARCGIS_SOURCES, ArcGISConnector

    connector = ArcGISConnector(ARCGIS_SOURCES["fort_worth_permits"])
    a = connector._map_record({"Permit_No": "PE16-00020", "CAPID": "111", "Address": "3844 HEYWOOD AVE"})
    b = connector._map_record({"Permit_No": "PE16-00020", "CAPID": "222", "Address": "4128 ANITA AVE"})
    # Same base Permit_No at two different addresses => distinct permit numbers.
    assert a["permit_number"] == "PE16-00020-111"
    assert b["permit_number"] == "PE16-00020-222"
    assert a["permit_number"] != b["permit_number"]
