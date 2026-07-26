from __future__ import annotations

from datetime import datetime

import pytest
from bs4 import BeautifulSoup

from app.connectors.html_scraper import (
    ACCELA_SOURCES,
    AccelaCitizenAccessConnector,
    _build_column_index,
    _looks_like_header_row,
    _to_datetime,
)


def test_to_datetime_parses_mm_dd_yyyy():
    dt = _to_datetime("12/31/2024")
    assert dt is not None
    assert (dt.year, dt.month, dt.day) == (2024, 12, 31)


def test_to_datetime_handles_blank_and_none():
    assert _to_datetime("") is None
    assert _to_datetime(None) is None


# Real-shaped header rows captured live from each of the three agencies
# during development -- confirms each agency genuinely uses a DIFFERENT
# column layout, which is why header parsing (not fixed positions) is
# used.
ANNE_ARUNDEL_HEADER = ["", "Application Date", "Record Number", "Revision Number", "Record Type", "Status", "Address", "Description", "Action", "Expiration Date"]
TAMPA_HEADER = ["", "Date", "Record Number", "Record Type", "Address", "Status", "Action", "Expiration Date", "Short Notes", ""]
CLARK_COUNTY_HEADER = ["", "Date", "Permit Number", "Permit Type", "Description", "Project Name", "Status", "Action", "Short Notes", ""]


@pytest.mark.parametrize(
    "header",
    [ANNE_ARUNDEL_HEADER, TAMPA_HEADER, CLARK_COUNTY_HEADER],
    ids=["anne_arundel", "tampa", "clark_county"],
)
def test_looks_like_header_row_detects_all_three_real_layouts(header):
    assert _looks_like_header_row(header) is True


def test_looks_like_header_row_rejects_data_row():
    data_row = ["", "12/31/2024", "B02433064", "A", "Residential Single Family Dwelling Permit", "Active", "127 BONNIE VIEW RD", "INTERIOR ALTERATIONS", "", ""]
    assert _looks_like_header_row(data_row) is False


def test_build_column_index_anne_arundel():
    idx = _build_column_index(ANNE_ARUNDEL_HEADER)
    assert idx["number"] == 2
    assert idx["type"] == 4
    assert idx["status"] == 5
    assert idx["date"] == 1
    assert idx["expiration"] == 9


def test_build_column_index_tampa_differs_from_anne_arundel():
    idx = _build_column_index(TAMPA_HEADER)
    # Confirms the two agencies genuinely have different layouts --
    # regression test against ever hardcoding fixed positions again.
    assert idx["number"] == 2
    assert idx["type"] == 3
    assert idx["status"] == 5
    assert idx["expiration"] == 7


def test_build_column_index_clark_county_uses_permit_number_label():
    idx = _build_column_index(CLARK_COUNTY_HEADER)
    assert idx["number"] == 2  # "Permit Number", not "Record Number" -- still matched via "number"
    assert idx["type"] == 3  # "Permit Type"
    assert idx["status"] == 6


def test_all_agencies_registered():
    # Original 4 (Anne Arundel, Tampa, Clark County, King County), the 7
    # EXPANSION_PLAN.md Wave B agencies, plus Charlotte County FL (sixth pass,
    # BOCC). Each agency's module name was discovered/confirmed live (see
    # html_scraper.py). San Joaquin County (SJCO) was on the plan but returned
    # HTTP 503 all session and is intentionally NOT registered -- see BLOCKERS.md.
    assert set(ACCELA_SOURCES.keys()) == {
        "anne_arundel_county_aca",
        "tampa_fl_aca",
        "clark_county_nv_aca",
        "king_county_wa_aca",
        "milwaukee_wi_aca",
        "hartford_ct_aca",
        "charlotte_county_fl_aca",
        "oakland_ca_aca",
        "santa_barbara_county_ca_aca",
        "polk_county_fl_aca",
        "lee_county_fl_aca",
        "indianapolis_in_aca",
    }
    # Lee County uses the "Permitting" module and Indianapolis "Permits" --
    # not the more common "Building" -- confirmed via each agency's own nav.
    assert ACCELA_SOURCES["lee_county_fl_aca"].module == "Permitting"
    assert ACCELA_SOURCES["indianapolis_in_aca"].module == "Permits"
    assert ACCELA_SOURCES["milwaukee_wi_aca"].module == "Building"


def test_map_record_produces_normalized_permit_shape():
    connector = AccelaCitizenAccessConnector(ACCELA_SOURCES["anne_arundel_county_aca"])
    normalized = connector._map_record(
        permit_number="B02433064",
        permit_type="Residential Single Family Dwelling Permit",
        status="Active",
        application_date="12/31/2024",
        expiration_date="",
        description="INTERIOR ALTERATIONS",
        address="127 BONNIE VIEW RD, GLEN BURNIE 21060",
        detail_url="https://aca-prod.accela.com/AACO/Cap/CapDetail.aspx?capID1=25CAP",
        raw_row={"col_0": "B02433064"},
    )

    assert normalized["permit_number"] == "B02433064"
    assert normalized["permit_type"] == "Residential Single Family Dwelling Permit"
    assert normalized["status"] == "Active"
    assert normalized["property_address"] == "127 BONNIE VIEW RD, GLEN BURNIE 21060"
    assert normalized["description"] == "INTERIOR ALTERATIONS"
    assert normalized["application_date"].year == 2024
    assert normalized["expiration_date"] is None
    assert normalized["permit_url"].startswith("https://aca-prod.accela.com")
    assert normalized["source"] == "html_scraper:aca-prod.accela.com/aaco"


def test_build_search_payload_sets_postback_and_date_range():
    html = """
    <form>
        <input type="hidden" name="__VIEWSTATE" value="abc123" />
        <input type="text" name="ctl00$PlaceHolderMain$generalSearchForm$txtGSStartDate" value="" />
        <select name="ctl00$PlaceHolderMain$ddlSearchType">
            <option value="0" selected="selected">General Search</option>
            <option value="1">Search by Address</option>
        </select>
    </form>
    """
    form = BeautifulSoup(html, "html.parser").find("form")
    connector = AccelaCitizenAccessConnector(ACCELA_SOURCES["tampa_fl_aca"])

    start = datetime(2024, 1, 1)
    end = datetime(2024, 12, 31)
    payload = connector._build_search_payload(form, start, end)

    assert payload["__VIEWSTATE"] == "abc123"
    assert payload["__EVENTTARGET"] == "ctl00$PlaceHolderMain$btnNewSearch"
    assert payload["ctl00$PlaceHolderMain$ddlSearchType"] == "0"
    assert payload["ctl00$PlaceHolderMain$generalSearchForm$txtGSStartDate"] == "01/01/2024"


def test_search_url_uses_agency_specific_module():
    aaco = AccelaCitizenAccessConnector(ACCELA_SOURCES["anne_arundel_county_aca"])
    tampa = AccelaCitizenAccessConnector(ACCELA_SOURCES["tampa_fl_aca"])
    assert "module=Permits" in aaco.search_url
    assert "aaco" in aaco.search_url
    assert "module=Building" in tampa.search_url
    assert "Tampa" in tampa.search_url


@pytest.mark.integration
@pytest.mark.parametrize("key", list(ACCELA_SOURCES.keys()))
def test_accela_scraper_live_integration(key):
    """
    Hits each real, live, public Accela Citizen Access permit search --
    no API, no key, genuinely scraped HTML. Confirmed live during
    development to return real permit records for all three agencies;
    see BLOCKERS.md for the robots.txt/legality/rate-limiting notes.
    """
    connector = AccelaCitizenAccessConnector(ACCELA_SOURCES[key])
    permits = list(connector.fetch_permits(limit=3))

    assert len(permits) > 0
    for permit in permits:
        assert permit["permit_number"]
        assert permit["source"].startswith("html_scraper:aca-prod.accela.com/")
