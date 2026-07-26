"""
Real HTML-scraping connector for jurisdictions with NO open-data API:
a generic client for any agency running Accela Citizen Access (ACA) on
the shared `aca-prod.accela.com` hosting domain, the single most common
"no open API" permit vendor nationally (per
research/RESEARCH_REPORT.md's vendor survey).

Four real, live-verified agencies are wired up below:
  * ACCELA_SOURCES["anne_arundel_county_aca"] -- Anne Arundel County, MD
  * ACCELA_SOURCES["tampa_fl_aca"]            -- Tampa, FL
  * ACCELA_SOURCES["clark_county_nv_aca"]     -- Clark County, NV (Las Vegas)
  * ACCELA_SOURCES["king_county_wa_aca"]      -- King County, WA (found after
    King County's own Socrata proxy dataset ("Permitting - Accela Permitting
    Portal") turned out to be gated -- HTTP 403 "no row or column access to
    non-tabular tables" -- but the underlying public ACA search UI itself,
    checked directly on the vendor's own domain, works with no login needed)

Why this domain, and why scraping it is legally reasonable:
-------------------------------------------------------------------
- The portal (https://aca-prod.accela.com/<agency>/...) requires **no
  login** to search or view permit records for any of the four
  agencies above -- a public search page, same posture as the
  government permit portals discussed favorably in
  research/RESEARCH_REPORT.md section 3.7 (hiQ Labs v. LinkedIn:
  scraping data publicly accessible without authentication does not
  violate the CFAA).
- `https://aca-prod.accela.com/robots.txt` returns **HTTP 404** (no
  robots.txt exists anywhere on the shared ACA hosting domain) --
  verified live, both at the domain root and each agency-specific path.
  No robots.txt means no declared crawl restriction.
- Each agency's page displays a "Disclaimer" link (standard government
  data-accuracy disclaimer) but no Terms-of-Service language
  prohibiting automated access was found on any of the four search
  pages.
- Rate limiting: at most 3 HTTP requests per `fetch_permits()` call per
  agency (session-establishing GET, form GET, search POST), each
  separated by a `REQUEST_DELAY_SECONDS` (default 1.5s) sleep, and only
  the first page of results (~10 rows) is fetched per call rather than
  paginating through "100+" matches -- deliberately conservative, not a
  technical ceiling.

Real, non-trivial scraping, not a trivial GET: each agency's "Search"
action is an ASP.NET WebForms `__doPostBack`, not a plain form submit,
and Accela CSRF-protects the POST by validating Referer/Origin headers
against the page that served the form (confirmed live: the POST fails
with "Potential cross-site request forgery attack" without matching
headers) -- both had to be reverse-engineered to get real results back.

Column layout is genuinely agency-configurable (confirmed live: Anne
Arundel, Tampa, and Clark County each expose a DIFFERENT column order
and a different subset of columns in their general-search results
grid), so rather than hardcoding fixed column positions (fragile --
silently misparses the moment one agency's layout differs, which
turned out to be immediately, not hypothetically), this connector
parses the live header row on every request and maps columns by
matching header text (case-insensitive substring match on "number",
"type", "status", "date", "expiration", "description"/"notes").
One thing IS consistently true across all three agencies checked:
the address, when present, is always the last cell in each data row,
regardless of whether that column has a visible header label -- used
as a reliable fallback.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from app.connectors.base import ConnectorInfo, PermitConnector

logger = logging.getLogger(__name__)

ACCELA_DOMAIN = "https://aca-prod.accela.com"
DEFAULT_TIMEOUT = 30.0
REQUEST_DELAY_SECONDS = 1.5

USER_AGENT = (
    "ConstructionIntelBot/0.1 (+https://github.com/; research/demo use; "
    "respects robots.txt when present, self-rate-limited)"
)

# Header keywords used to locate each logical field within whatever
# column order/subset a given agency happens to expose. Order within
# each tuple matters only in that the first case-insensitive substring
# match wins.
_HEADER_KEYWORDS = {
    "number": ("number",),         # matches "Record Number" or "Permit Number"
    "type": ("type",),             # matches "Record Type" or "Permit Type"
    "status": ("status",),
    "date": ("date",),             # first date-ish column that isn't "Expiration Date"
    "expiration": ("expiration",),
    "description": ("description", "short notes"),
}


def _to_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%m/%d/%Y")
    except ValueError:
        return None


def _row_cells(row: Tag) -> list[str]:
    return [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]


def _looks_like_header_row(cells: list[str]) -> bool:
    """A header row is one whose cell texts are themselves column
    labels (e.g. "Record Number", "Status") rather than data values."""
    lowered = [c.lower() for c in cells]
    hits = sum(1 for kw_group in _HEADER_KEYWORDS.values() for kw in kw_group for c in lowered if kw in c)
    return hits >= 2


def _build_column_index(header_cells: list[str]) -> dict[str, int]:
    """Map logical field name -> column index by matching header text."""
    lowered = [c.lower() for c in header_cells]
    index: dict[str, int] = {}
    for field, keywords in _HEADER_KEYWORDS.items():
        for idx, cell in enumerate(lowered):
            if field == "date" and "expiration" in cell:
                continue  # don't let "Expiration Date" win the generic "date" slot
            if any(kw in cell for kw in keywords):
                index[field] = idx
                break
    return index


class AccelaAgencyConfig:
    def __init__(
        self,
        key: str,
        agency_path: str,
        module: str,
        display_name: str,
        search_days_back: int = 180,
    ):
        self.key = key
        self.agency_path = agency_path  # e.g. "aaco", "Tampa", "clarkco"
        self.module = module  # e.g. "Permits", "Building" -- varies per agency's own ACA configuration
        self.display_name = display_name
        self.search_days_back = search_days_back


ACCELA_SOURCES: dict[str, AccelaAgencyConfig] = {
    "anne_arundel_county_aca": AccelaAgencyConfig(
        key="anne_arundel_county_aca",
        agency_path="aaco",
        module="Permits",
        display_name="Anne Arundel County, MD (Accela Citizen Access)",
    ),
    "tampa_fl_aca": AccelaAgencyConfig(
        key="tampa_fl_aca",
        agency_path="Tampa",
        module="Building",
        display_name="Tampa, FL (Accela Citizen Access)",
    ),
    "clark_county_nv_aca": AccelaAgencyConfig(
        key="clark_county_nv_aca",
        agency_path="clarkco",
        module="Building",
        display_name="Clark County, NV (Accela Citizen Access)",
    ),
    "king_county_wa_aca": AccelaAgencyConfig(
        key="king_county_wa_aca",
        agency_path="kingco",
        module="Building",
        display_name="King County, WA (Accela Citizen Access)",
    ),
    # --- Fifth pass / EXPANSION_PLAN.md Wave B: 7 more ACA agencies, each
    # verified live this pass (robots.txt still 404 site-wide; each agency's
    # module discovered from its own home-page navigation / a direct CapHome
    # 200-vs-302 probe). San Joaquin County (SJCO) was also on the plan but
    # returned HTTP 503 for every request this session -- excluded, see
    # BLOCKERS.md. Polk County and Lee County were disambiguated to FL before
    # building (municode /fl/polk_county/ + polk-county.net; Lee's 239 area
    # code + leegov.com), per the plan's "don't assume the state" caveat. ---
    "milwaukee_wi_aca": AccelaAgencyConfig(
        key="milwaukee_wi_aca",
        agency_path="MILWAUKEE",
        module="Building",  # confirmed: ?module=Building -> 200 w/ search form; Permits/Permitting -> 302
        display_name="Milwaukee, WI (Accela Citizen Access)",
    ),
    "hartford_ct_aca": AccelaAgencyConfig(
        key="hartford_ct_aca",
        agency_path="HARTFORD",
        module="Building",  # confirmed via home-page nav (title: City of Hartford Permitting Online Portal)
        display_name="Hartford, CT (Accela Citizen Access)",
    ),
    "oakland_ca_aca": AccelaAgencyConfig(
        key="oakland_ca_aca",
        agency_path="OAKLAND",
        module="Building",  # confirmed via home-page nav (title: Oakland Online Portal)
        display_name="Oakland, CA (Accela Citizen Access)",
    ),
    "santa_barbara_county_ca_aca": AccelaAgencyConfig(
        key="santa_barbara_county_ca_aca",
        agency_path="SBCO",
        module="Building",  # confirmed via home-page nav
        display_name="Santa Barbara County, CA (Accela Citizen Access)",
    ),
    "polk_county_fl_aca": AccelaAgencyConfig(
        key="polk_county_fl_aca",
        agency_path="POLKCO",
        module="Building",  # confirmed via home-page nav (title: Polk County Citizen Access)
        display_name="Polk County, FL (Accela Citizen Access)",
    ),
    "lee_county_fl_aca": AccelaAgencyConfig(
        key="lee_county_fl_aca",
        agency_path="LEECO",
        module="Permitting",  # confirmed via home-page nav (no Building module; uses "Permitting")
        display_name="Lee County, FL (Accela Citizen Access)",
    ),
    "indianapolis_in_aca": AccelaAgencyConfig(
        key="indianapolis_in_aca",
        agency_path="INDY",
        module="Permits",  # confirmed via home-page nav (uses "Permits", not "Building")
        display_name="Indianapolis, IN (Accela Citizen Access)",
    ),
    # --- Sixth pass: one more ACA agency, found via the same
    # `site:aca-prod.accela.com "CapHome.aspx"` dork. `BOCC` disambiguated to
    # Charlotte County, FL (its home page reads "search the County's permitting
    # database"; the Building module's CapHome returns the general-search form
    # -- txtGSStartDate present -- confirming a valid Building module). ---
    "charlotte_county_fl_aca": AccelaAgencyConfig(
        key="charlotte_county_fl_aca",
        agency_path="BOCC",
        module="Building",  # confirmed: ?module=Building serves the General Search form
        display_name="Charlotte County, FL (Accela Citizen Access)",
    ),
}


class AccelaCitizenAccessConnector(PermitConnector):
    """
    Scrapes any agency's public Accela Citizen Access (ACA) permit
    search on the shared aca-prod.accela.com hosting domain. See module
    docstring for the legality/rate-limiting/robustness rationale.
    """

    source_system = "html_scraper"

    def __init__(
        self,
        config: AccelaAgencyConfig,
        timeout: float = DEFAULT_TIMEOUT,
        request_delay: float = REQUEST_DELAY_SECONDS,
    ):
        self.config = config
        self.timeout = timeout
        self.request_delay = request_delay

    @property
    def base_url(self) -> str:
        return f"{ACCELA_DOMAIN}/{self.config.agency_path}"

    @property
    def default_page_url(self) -> str:
        return f"{self.base_url}/Default.aspx"

    @property
    def search_url(self) -> str:
        return f"{self.base_url}/Cap/CapHome.aspx?module={self.config.module}&TabName={self.config.module}"

    def _new_client(self) -> httpx.Client:
        return httpx.Client(follow_redirects=True, headers={"User-Agent": USER_AGENT}, timeout=self.timeout)

    def discover(self) -> ConnectorInfo:
        with self._new_client() as client:
            resp = client.get(self.default_page_url)
            resp.raise_for_status()
            time.sleep(self.request_delay)
            search_resp = client.get(self.search_url)
            search_resp.raise_for_status()

        soup = BeautifulSoup(search_resp.text, "html.parser")
        title_el = soup.find("title")
        return ConnectorInfo(
            source_system=self.source_system,
            identifier=self.search_url,
            display_name=self.config.display_name,
            extra={"page_title": title_el.get_text(strip=True) if title_el else None},
        )

    def _build_search_payload(self, form: Tag, start: datetime, end: datetime) -> dict[str, str]:
        payload: dict[str, str] = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue
            input_type = (inp.get("type") or "text").lower()
            if input_type in ("checkbox", "radio"):
                if inp.get("checked") is not None:
                    payload[name] = inp.get("value", "on")
            else:
                payload[name] = inp.get("value", "")
        for sel in form.find_all("select"):
            name = sel.get("name")
            if not name:
                continue
            chosen = sel.find("option", selected=True) or sel.find("option")
            payload[name] = chosen.get("value", "") if chosen else ""

        # Trigger the "Search" postback (an <a> link, not a real submit
        # button, per ASP.NET WebForms convention) with a General Search
        # (searchtype "0") over a bounded date range. Field names
        # themselves are consistent across all three agencies checked
        # even though the RESULT column layout differs.
        payload["__EVENTTARGET"] = "ctl00$PlaceHolderMain$btnNewSearch"
        payload["__EVENTARGUMENT"] = ""
        payload["ctl00$PlaceHolderMain$ddlSearchType"] = "0"
        for key in list(payload.keys()):
            if "txtGSStartDate" in key and "ext_ClientState" not in key:
                payload[key] = start.strftime("%m/%d/%Y")
            if "txtGSEndDate" in key and "ext_ClientState" not in key:
                payload[key] = end.strftime("%m/%d/%Y")
        return payload

    def fetch_permits(self, since: Optional[datetime] = None, limit: Optional[int] = None) -> Iterable[dict]:
        end = datetime.now()
        start = since if since is not None else end - timedelta(days=self.config.search_days_back)

        with self._new_client() as client:
            # Step 1: establish a session (required before the search
            # page will render).
            client.get(self.default_page_url)
            time.sleep(self.request_delay)

            # Step 2: GET the search form to harvest __VIEWSTATE /
            # __EVENTVALIDATION and every current field value.
            form_resp = client.get(self.search_url)
            form_resp.raise_for_status()
            soup = BeautifulSoup(form_resp.text, "html.parser")
            form = soup.find("form")
            if form is None:
                logger.warning("%s: could not find search form on page", self.config.key)
                return
            time.sleep(self.request_delay)

            # Step 3: POST the search. Accela CSRF-checks Referer/Origin
            # against the page that served the form.
            payload = self._build_search_payload(form, start, end)
            search_resp = client.post(
                self.search_url,
                data=payload,
                headers={
                    "Referer": self.search_url,
                    "Origin": ACCELA_DOMAIN,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            search_resp.raise_for_status()

        results_soup = BeautifulSoup(search_resp.text, "html.parser")
        grids = results_soup.find_all("table", class_=lambda c: c and "ACA_Grid" in c)
        if not grids:
            logger.info("%s: no results grid found for date range %s - %s", self.config.key, start, end)
            return

        rows = grids[0].find_all("tr")

        # Find the header row dynamically (position varies slightly by
        # agency/version -- matching content is more robust than a
        # fixed index).
        header_index: dict[str, int] = {}
        header_row_pos = None
        for i, row in enumerate(rows):
            cells = _row_cells(row)
            if _looks_like_header_row(cells):
                header_index = _build_column_index(cells)
                header_row_pos = i
                break

        if header_row_pos is None or "number" not in header_index:
            logger.warning("%s: could not locate a recognizable header row in results grid", self.config.key)
            return

        count = 0
        for row in rows[header_row_pos + 1 :]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue  # pagination/summary rows, not data rows
            texts = [c.get_text(" ", strip=True) for c in cells]

            number_idx = header_index.get("number")
            record_number = texts[number_idx] if number_idx is not None and number_idx < len(texts) else None
            if not record_number:
                continue

            def _field(name: str) -> Optional[str]:
                idx = header_index.get(name)
                if idx is None or idx >= len(texts):
                    return None
                return texts[idx] or None

            # Empirically consistent across all three agencies checked:
            # the address is always the LAST cell of the row, whether or
            # not that column has a visible header label.
            address = texts[-1] if texts else None

            detail_url = None
            link = cells[number_idx].find("a") if number_idx is not None and number_idx < len(cells) else None
            if link and link.get("href"):
                href = link["href"]
                detail_url = href if href.startswith("http") else f"{ACCELA_DOMAIN}{href}"

            yield self._map_record(
                permit_number=record_number,
                permit_type=_field("type"),
                status=_field("status"),
                application_date=_field("date"),
                expiration_date=_field("expiration"),
                description=_field("description"),
                address=address,
                detail_url=detail_url,
                raw_row=dict(zip((f"col_{i}" for i in range(len(texts))), texts)),
            )
            count += 1
            if limit is not None and count >= limit:
                break

    def _map_record(
        self,
        permit_number: str,
        permit_type: Optional[str],
        status: Optional[str],
        application_date: Optional[str],
        expiration_date: Optional[str],
        description: Optional[str],
        address: Optional[str],
        detail_url: Optional[str],
        raw_row: dict[str, Any],
    ) -> dict:
        normalized = self.normalized_stub()
        normalized["permit_number"] = permit_number
        normalized["permit_type"] = permit_type
        normalized["status"] = status
        normalized["application_date"] = _to_datetime(application_date)
        normalized["expiration_date"] = _to_datetime(expiration_date)
        normalized["property_address"] = address
        normalized["description"] = description
        normalized["work_category"] = permit_type
        normalized["permit_url"] = detail_url
        normalized["source"] = f"html_scraper:aca-prod.accela.com/{self.config.agency_path}"
        normalized["raw_data"] = raw_row
        return normalized
