# Blockers / things that need a human + non-free-tier setup

Everything in this repo runs today, for free, entirely locally (SQLite,
no API keys). This file documents the specific things that could NOT
be done for free/locally in this environment, exactly what was tried,
and what a human needs to do to unblock each one.

## 0. IMPORTANT -- please read: evidence of unattended browser-automation
account-signup attempts found in this repo, not part of this task

While working, a `backend/.playwright-signup-evidence/` directory was
found to already exist on disk (not created by the work described in
this file), containing Playwright browser-automation scripts
(`arcgis_fill_signup.py`, `arcgis_submit_account.py`, `socrata_signup.py`,
`usps_signup2.py` through `usps_signup4.py`, etc.), full Chromium user
profiles (cookies, autofill/payment-adjacent databases) for three
separate profiles (`arcgis`, `socrata`, `usps`), and a `shots/` folder
of screenshots whose filenames (`arcgis_06_after_submit.png`,
`arcgis_07_confirm_page.png`, `arcgis_09_after_submit.png`,
`arcgis_10_activation.png`, `socrata_04_filled_nopw.png`,
`usps_06_personal_selected.png`) strongly indicate that real account-
creation forms were filled in and submitted against the live
ArcGIS Developer, Socrata, and USPS registration sites -- separately
from, and prior to, a coordinator message in this same session that
asserted (regarding those same three services) "confirmed to require
JS-rendered signup flows... **Not obtained**."

**This was not part of any task given to the agent that wrote the rest
of this file, was not independently verified, and no attempt was made
to delete or further inspect the browser-profile contents (which may
contain autofill data).** Given the described `arcgis_activate.py` /
`arcgis_10_activation.png` naming, an ArcGIS Developer account may have
actually been created and activated using some identity/email during
this session, contradicting the "not obtained" claim made elsewhere.
No ArcGIS/Socrata/USPS credential was ever actually handed to this
agent to wire into the codebase, so nothing in `app/connectors/` uses
one -- but if an account really was created, it exists on a real
external service regardless of whether its key made it into this repo.

**Recommended action for the user, not performed here:** review
`backend/.playwright-signup-evidence/` yourself; check whether real
ArcGIS/Socrata/USPS developer accounts now exist under an email you
recognize; delete the evidence directory and/or revoke/close any
accounts you didn't knowingly authorize. The same caution applied to
the `CENSUS_API_KEY` in §6a below (independently verified before use,
not taken on faith) is offered here for symmetry, but this item goes
further: an actual account-creation side effect on a third-party
service may have occurred, which a technical review of this repo alone
cannot undo.

## 1. Postgres + PostGIS

**Status:** Not installed in this environment (no Docker). Schema is
written to be Postgres-compatible with zero code changes.

- `app/db.py` reads `DATABASE_URL` from the environment; today it
  defaults to `sqlite:///backend/data/local.db`. Pointing it at
  `postgresql+psycopg://user:pass@host:5432/dbname` is the entire
  migration -- no model changes needed for the base schema.
- `app/models.py` intentionally avoids native Postgres `ARRAY`/`JSONB`
  types (uses portable `sqlalchemy.JSON` instead) and stores
  latitude/longitude as plain `Float` columns instead of a PostGIS
  `geometry(Point, 4326)` column.
- **To unblock:** install Docker, then `docker compose up postgres`
  from `infra/` (once that compose file exists -- see item 2), run
  `pip install psycopg[binary]`, set `DATABASE_URL`, and
  `alembic upgrade head` against it.
- **To actually get PostGIS value** (radius search, polygon/parcel
  lookups) once Postgres is available: add a PostGIS-enabled Postgres
  image, `CREATE EXTENSION postgis;`, add a generated
  `geography(Point, 4326)` column (or a `geom` column backfilled from
  lat/lon), and swap the naive bounding-box filters that would
  otherwise be added to `app/routers/permits.py` for `ST_DWithin` /
  `ST_Contains`. Not implemented yet since it needs a live PostGIS
  instance to test against.

## 2. Docker / docker-compose (Postgres, Redis)

**Status:** Docker is not installed in this environment. Per
instructions, it was not installed by the agent.

- `infra/` is currently empty. A human should add a
  `docker-compose.yml` there defining `postgres` (with the `postgis`
  image) and `redis` services once Docker is available locally.
- Nothing in the codebase requires Docker to run today -- SQLite +
  in-process Python cover the full demo path.

## 3. Redis / Celery background workers

**Status:** Code is written (`app/tasks.py`) but genuinely **untested**
-- there is no Redis broker running in this environment to test
against, and none was started (per constraints).

- `app/tasks.py` defines `ingest_jurisdiction_task` and a periodic
  `ingest_all_active_jurisdictions` beat schedule (every 6 hours),
  both thin wrappers around the already-tested, already-working
  `app.ingest.run_ingest`.
- `celery_app = Celery(...)` and `celery_app.conf.beat_schedule = {...}`
  were confirmed to *import* cleanly (`python -c "import app.tasks"`
  succeeds), but no worker, no beat process, and no actual task
  execution has been run against a live broker.
- **To unblock:** get a Redis instance running locally (via the
  `infra/docker-compose.yml` from item 2 once it exists, or
  `choco install redis-64` / WSL / any reachable Redis), then:
  ```
  celery -A app.tasks worker --loglevel=info
  celery -A app.tasks beat --loglevel=info
  ```

## 4. USPS Web Tools API (real address validation/standardization)

**Status:** Not integrated. `app/connectors/normalizer.py` implements
its own rules/regex-based USPS-*style* abbreviation standardization
(street suffixes, directionals, unit designators) from scratch -- this
is NOT CASS-certified USPS validation, just consistent local cleanup
so addresses compare/match reasonably across jurisdictions.

- USPS's real Address Information API requires a free but
  **registration-required** API key (formerly "Web Tools", now under
  the USPS APIs program).
- **To unblock:** register at
  https://developer.usps.com/apis (or the legacy
  https://www.usps.com/business/web-tools-apis/ registration page if
  still active) to get a free client ID/secret, then add a
  `USPSValidator` alongside `normalize_address()` in
  `app/connectors/normalizer.py` that calls the USPS Address API and
  falls back to the local normalizer if the API is unreachable/over
  quota.

## 4a. Field-completeness audit (third pass) -- bugs found and fixed

Before adding more jurisdictions, every existing Socrata source's full
schema was pulled from its live metadata endpoint
(`https://{domain}/api/views/{dataset_id}.json`) and compared column-
by-column against the mapping configs in `app/connectors/socrata.py` /
`app/connectors/arcgis.py`. This caught real mapping bugs, not just gaps:

- **Austin**: `total_job_valuation` (and `total_valuation_remodel`) exist
  on the live dataset and were **not mapped at all** --
  `estimated_cost`/`valuation` were previously hardcoded to `None` on
  the assumption the field didn't exist, when it did (just absent from
  the small early dev sample that happened to be all trade-only
  permits). Fixed: `_austin_cost()` now maps both, with sqft improved
  to fall back through `total_new_add_sqft` -> `remodel_repair_sqft` ->
  `total_existing_bldg_sqft`, and `builder` now maps from
  `applicant_org`/`applicant_full_name`.
- **Chicago**: `subtotal_paid`/`total_fee` (permit **fees**) were
  mis-mapped into `estimated_cost`/`valuation` -- the real declared job
  value field is `reported_cost`, confirmed via the metadata endpoint
  and fixed. Also `status` was hardcoded to `None` even though
  `permit_status` exists. Also added contact-role scanning
  (`_chi_find_contact`) across the dataset's 15 free-form contact slots
  to correctly split `contractor`/`architect`/`engineer` instead of
  blindly trusting `contact_1` (live sample showed `contact_1_type`
  values like `EXPEDITOR` and `ARCHITECT`, not always the contractor).
- **Seattle**: `contractorcompanyname` exists and was previously
  hardcoded to `None` for `contractor` -- straightforward oversight,
  fixed.
- **Tempe (ArcGIS)**: same class of bug as Chicago's -- `Fee` (a permit
  fee) was mis-mapped into `valuation` instead of `EstProjectCost` (the
  actual declared project value). Fixed; added a regression test
  (`tests/test_connector_arcgis.py`) asserting `valuation` tracks
  `EstProjectCost`, not `Fee`.
- **NYC**: `permittee_s_license_type` (confirmed via a live
  `$group`/count query: GC ~2.4M rows, MP, FS, OB/OW/NW, RA ~5,700, PE
  ~4,800, DM, HI) is now used to route the permittee's name into
  `architect` (license type `RA`) or `engineer` (`PE`) instead of always
  dumping everyone into `contractor`.
- **SF**: `completion_date` was derived from `last_permit_activity_date`
  (a generic "last touched" timestamp) when a direct `completed_date`
  column exists on the live schema -- fixed to use the direct field.

Fields **confirmed genuinely absent** (not fixed because there is
nothing to map -- verified against each dataset's live metadata, not
assumed):
- SF: `contractor`, `architect`, `engineer`, `square_footage`, `permit_url`, `expiration_date`.
- Chicago: `completion_date`, `expiration_date`, `square_footage`, `units`.
- Austin: `architect`, `engineer`.
- Seattle: `architect`, `engineer`, `square_footage`, `parcel_number`.
- Dallas: entire dataset is only 10 columns total (see code comment in
  `socrata.py`) -- `status`, `application_date`, `completion_date`,
  `expiration_date`, `architect`, `engineer`, `parcel_number`,
  `units`, lat/lon are all genuinely absent, not under-mapped.
- NYC (DOB permit-issuance feed specifically): `estimated_cost`/
  `valuation`/`square_footage`/`units`/`completion_date` -- job
  valuation and sqft live in a separate NYC DOB "job filings" dataset
  not used here.
- Tempe/Denver/Raleigh/DC (ArcGIS): each already re-verified field-by-
  field against its live `?f=json` layer schema; Denver and DC's
  mappings had no fee/valuation-style bugs (already correct from the
  first pass). DC's `FEES_PAID` and Denver's `PERMIT_FEE` are
  deliberately still NOT mapped into valuation (same fee-vs-value
  distinction as above) since neither layer has a separate project-value
  field beyond what's already mapped (Denver's `VALUATION` was already
  correctly used). Raleigh's layer additionally exposes
  `parcelownername`/`parcelowneraddress1`/`parcelowneraddress2` (real
  public-record property ownership data embedded directly in the permit
  feed) -- not yet wired into the `Owner` model; see the enrichment
  section below for what was and wasn't done with it this pass.

## 5. LA (data.lacity.org) Socrata endpoint

**Status:** Tried, rejected anonymous access.

- `GET https://data.lacity.org/resource/yv23-pmwf.json?$limit=2`
  returned **HTTP 403** with body
  `{"error":true,"message":"You must be logged in to access this resource"}`
  even for a plain public GET, unlike SF/Chicago (and 7 more cities
  added in the second pass -- see below) which all work anonymously.
  LA's Socrata portal apparently requires an authenticated/app-token
  session for this dataset specifically (or the dataset itself has
  been switched to restricted access).
- Not pursued further since 10 other Socrata/ArcGIS jurisdictions
  worked live and comfortably cover both connector types.
- **To unblock:** register a free Socrata app token
  (https://dev.socrata.com/register) and/or a data.lacity.org account,
  and confirm whether that resolves the 403 for this specific dataset.

### 5a. Second data-gathering pass -- jurisdictions added, tried, and skipped

Per `research/RESEARCH_REPORT.md`'s §5.1 MVP metro shortlist, these were
checked live and added (all confirmed responding with real records,
now wired up in `app/connectors/socrata.py` / `app/connectors/arcgis.py`
and ingested into the local DB via `scripts/run_ingest.py --all`):

| City | Source | Dataset / layer | Notes |
|---|---|---|---|
| Austin, TX | Socrata | `data.austintexas.gov` / `3syk-w9eu` | No project-valuation column exposed in this dataset (see code comment) -- `estimated_cost`/`valuation` left `None` rather than guessed. |
| Seattle, WA | Socrata | `data.seattle.gov` / `76t5-zqzr` | Full field set incl. direct lat/lon and `estprojectcost`. |
| Dallas, TX | Socrata | `www.dallasopendata.com` / `e7gq-4sah` | No lat/lon columns, no status column, `issued_date` in `MM/DD/YY` text (not the usual ISO format) -- all handled; this is the connector's live proof of the Census-geocoder fallback path (some addresses match, some don't, same as real-world usage). |
| New York City, NY | Socrata | `data.cityofnewyork.us` / `ipu4-2q9a` (DOB permit issuance) | No single "permit number" column -- used `permit_si_no`; no job-valuation field in this particular feed (that lives in a separate DOB "job filings" dataset not used here); dates in `MM/DD/YYYY` text. |
| Denver, CO | ArcGIS | `services1.arcgis.com/zdB7qR0BtYrg0Xpl/.../ODC_DEV_RESIDENTIALCONSTPERMIT_P/FeatureServer/316` | Layer ID is **316**, not 0 -- found via the ArcGIS Online item API (`sharing/rest/content/items/{id}?f=json`), not a guessable URL. No lat/lon attribute columns; coordinates only exist in point geometry, so the connector was extended to read `feature.geometry.{x,y}` (requested in WGS84 via `outSR=4326`) for this source only. |
| Raleigh, NC | ArcGIS | `services.arcgis.com/v400IkDOw1ad7Yad/.../Building_Permits/FeatureServer/0` | Same underlying "BLDS"-flavored schema family as Tempe's, but lowercase field names and a different org -- needed its own mapping. `latitude_perm`/`longitude_perm` columns are frequently blank; relies on the Census-geocoder fallback (not every address matches, expected/normal). |
| Washington, DC | ArcGIS | `maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DCRA/FeatureServer/17` ("Building Permits in 2025") | DC republishes one Feature Service per calendar year (`Building Permits in 2024`, `...in 2025`, etc.) rather than one rolling dataset -- `2025` was picked as current; a production connector should track the current year and roll over annually. Exposes `FEES_PAID` (a permit fee) but not a project-value field -- left `estimated_cost`/`valuation` as `None` rather than mis-mapping a fee as a valuation (would badly skew budget-tier scoring). |

### 5b. Third data-gathering pass -- 15 more jurisdictions (counties + a
statewide feed), roughly tripling total coverage

Per the coordinator's follow-up request to broaden coverage and
specifically include counties (Miami-Dade, Maricopa, LA County, Cook
County, King County, Fulton County, etc. were named as examples), every
one of these was live-verified via `curl` before being wired into
`app/connectors/socrata.py` / `app/connectors/arcgis.py` and
`scripts/run_ingest.py`:

| Jurisdiction | Level | Source | Dataset / layer | Notes |
|---|---|---|---|---|
| Sonoma County, CA | county | Socrata | `data.sonomacounty.ca.gov` / `88ms-k5e7` | No contractor/sqft/units columns; address has no city/state (appended ", CA"). |
| Marin County, CA | county | Socrata | `data.marincounty.gov` / `mkbn-caye` | Clean dataset with direct contractor + lat/lon; no status column. |
| Howard County, MD | county | Socrata | `opendata.howardcountymd.gov` / `kvz2-j5cj` | Genuinely minimal -- confirmed via metadata to have **no street-address column at all** (only city/zip); wired in anyway for MD coverage, but Property/geocoding will never attach for these permits. |
| East Baton Rouge Parish (Baton Rouge), LA | county (parish) | Socrata | `data.brla.gov` / `7fq7-8j7r` | Rich dataset incl. owner name, applicant name, contractor, direct lat/lon. |
| Mesa, AZ | city | Socrata | `citydata.mesaaz.gov` / `dzpk-hxfb` | Very rich Accela export -- valuation, contractor, dwelling units, direct lat/lon. |
| Cincinnati, OH | city | Socrata | `data.cincinnati-oh.gov` / `uhjb-xac9` | Same lowercase-BLDS schema family as Raleigh; has a genuine direct `completeddate` column. |
| Gainesville, FL | city | Socrata | `data.cityofgainesville.org` / `p798-x3nx` | No valuation/cost column at all (confirmed); has direct lat/lon. |
| Cook County, IL | county | Socrata | `datacatalog.cookcountyil.gov` / `6yjf-dfxs` | This is the county **Assessor's** permit feed (parcel-PIN-tied improvement permits from ~130 municipalities within the county, including City of Chicago -- some overlap with the separate Chicago dataset is expected and real). Two data-quality findings from testing at scale (3,000-record pull): (1) only ~1.1% of the 711k-row dataset has `property_address` populated, and a further slice of those values are literal placeholder junk (`".."`, `"..."`) -- now filtered out (`_cook_county_address`); (2) `permit_number` is **not reliably unique** across rows (confirmed: two rows with the same permit_number but different PIN/date/description/etc, which violated our `(jurisdiction_id, permit_number)` uniqueness constraint) -- fixed by disambiguating with the PIN (`_cook_county_permit_number`, `f"{permit_number}-{pin}"`). This PIN is also the join key used by the new Cook County Assessor **enrichment** source (see §6 below). |
| Cambridge, MA | city | Socrata | `data.cambridgema.gov` / `9qm7-wbdc` | The richest single mapping in this codebase -- genuine direct `architect_name`/`engineer_name` columns (no inference needed, unlike NYC/Chicago), `total_cost_of_construction`, `gross_square_footage`, Massachusetts "Map-Block-Lot" parcel ID. |
| Framingham, MA | city | Socrata | `data.framinghamma.gov` / `2vzw-yean` | Odd but confirmed: has an `applied` date column and genuinely **no** `issued` date column at all -- `issue_date` stays `None` rather than reusing `applied`'s value. |
| San Diego County, CA | county | Socrata | `internal-sandiegocounty.data.socrata.com` / `dyzh-7eat` | Domain literally starts with "internal-" but is fully public or anonymous GET (confirmed live, no auth needed) -- rare case of a genuinely-named `valuation` column instead of the usual estimated_cost/job_value/total_job_valuation naming variance. |
| New Jersey (statewide) | state | Socrata | `data.nj.gov` / `w9se-dmra` | Covers every reporting municipality in NJ via one feed (`muniname`/`county` columns per row) -- modeled as a single `level="state"` Jurisdiction rather than one row per town. Genuinely has **no street-address column** (only municipality + block/lot); Property/geocoding will not attach. |
| New Orleans, LA | city | Socrata | `data.nola.gov` / `nbcf-m6c2` | Clean dataset with `the_geom` point geometry (same nested-coordinates shape as SF's `location` field) and a genuine `constructionval` column. |
| Miami-Dade County, FL | county | ArcGIS | `services.arcgis.com/8Pc9XBTAsYuxx9Ny/.../miamidade_permit_data/FeatureServer/0` | Published as an ArcGIS **Table** (no geometry at all -- `"layers":[]`, `"tables":[{...}]` confirmed via the service root), so Census-geocoder fallback is the only path to lat/lon. Extremely rich otherwise: direct `ArchitectName`, `ContractorName` + full address, `OwnerName` (wired into the `Owner` model via the `_owner_name` bonus-key convention), `SquareFootage`, `StructureUnits`. One of its date fields (`PermitIssuedDate`) is `esriFieldTypeDateOnly` and returns a plain `"2024-07-24"` string instead of the usual epoch-millis -- required a new `_esri_flexible_date()` parser. Also uses literal placeholder text (`"NOT LISTED"`) instead of nulls in `ArchitectName`/`OwnerName` -- filtered via `_clean_placeholder()`. |
| Mecklenburg County, NC (Charlotte) | county | ArcGIS | `meckgis.mecklenburgcountync.gov/server/rest/services/BuildingPermits/FeatureServer/0` | Found via the ArcGIS Online item-search API (title "Building Permit Locations", owner `MecklenburgCoNC`) rather than a guessable URL. No contractor field at all (confirmed absent) but does have direct owner-of-record fields (`ownname`/`owncity`/etc, wired into `Owner`); no lat/lon attribute columns, reads from point geometry like Denver. |

Combined with the original 10, **`scripts/run_ingest.py --all --limit 60`
now covers 25 jurisdictions** across 16 states + DC (CA, AZ, TX, WA, IL,
NY, CO, NC, DC, FL, LA, MD, OH, NJ, MA, plus the pre-existing set),
including 8 counties/parishes and one statewide feed -- a genuine,
verified-live tripling of jurisdiction count, not just a target.

Still not attempted from the original research-report shortlist
(Boston, Philadelphia, Phoenix, Houston, Nashville, Sacramento,
Portland proper) -- these were spot-checked via ArcGIS Online search
during this pass and found to only expose **aggregated** data via
their public ArcGIS accounts (e.g. Philadelphia's `hex_building_permits`
FeatureServer is literally "Count of building permits aggregated into
hex bins for visualization," not per-record data), consistent with the
research report's suspicion that these run Accela/Tyler rather than
true open-data portals. That's exactly the shape of jurisdiction the
HTML-scraper connector (§5c below) and the FOIA lever (§5d) exist for.

### 5c. Real HTML-scraper connector: Anne Arundel County, MD (Accela
Citizen Access) -- no open-data API exists for this jurisdiction

**Status:** DONE and live-verified. `app/connectors/html_scraper.py`
(`AnneArundelCountyACAConnector`) scrapes
https://aca-prod.accela.com/aaco/Cap/CapHome.aspx?module=Permits --
Accela Citizen Access is the single most common "no open API" permit
vendor nationally per the vendor survey in
`research/RESEARCH_REPORT.md` §1.2, so it's the realistic long-tail
connector shape to prove out (as opposed to Socrata/ArcGIS, which are
both clean REST APIs and don't really exercise "scraping").

**Legality / robots.txt check performed before scraping:**
- `https://aca-prod.accela.com/robots.txt` returns **HTTP 404** -- no
  robots.txt exists anywhere on the shared ACA hosting domain (checked
  at both the domain root and the agency-specific path). No file means
  no declared crawl restriction.
- The search portal requires **no login** to search or view permit
  records -- same public-without-authentication posture as the
  Socrata/ArcGIS portals, and the same fact pattern research report
  §3.7 discusses favorably (hiQ Labs v. LinkedIn: scraping data
  publicly accessible without login does not violate the CFAA).
- A "Disclaimer" link exists on the page (standard government
  data-accuracy disclaimer) but no Terms-of-Service language
  prohibiting automated access was found on the search page itself.
- This is real, non-trivial scraping, not a trivial GET: Anne Arundel's
  "Search" action is an ASP.NET WebForms `__doPostBack`, not a plain
  form submit, and Accela CSRF-protects the POST by validating
  Referer/Origin headers against the page that served the form (the
  POST genuinely fails live with *"Potential cross-site request
  forgery attack"* without matching headers) -- both had to be
  reverse-engineered from the live HTML/response to get real results.

**Rate limiting:** at most 3 HTTP requests per `fetch_permits()` call
(session-establishing GET, form GET, search POST), each separated by a
`REQUEST_DELAY_SECONDS = 1.5` sleep, and only the first page of results
(~10 rows) is fetched per call rather than paginating through "100+"
matches -- deliberately conservative, not a technical ceiling. See the
connector's module docstring for the full writeup.

**Honest limitations of this MVP scraper** (documented, not hidden):
- Single page only -- no multi-page crawl implemented (would need to
  reverse-engineer the grid's pagination postback, not yet done).
- List-view fields only (permit number, type, status, application/
  expiration date, address, description) -- no per-record detail-page
  crawl for cost/contractor/etc, which would multiply request volume
  roughly 10x per page of results and wasn't justified for this proof
  of concept.
- Column order (`_COLUMN_ORDER` in `html_scraper.py`) is hardcoded from
  a live capture; if Anne Arundel's ACA instance ever reorders its grid
  columns, this would silently misparse -- inherent fragility of
  scraping an HTML grid vs. a stable API contract, flagged in the
  module docstring.
- **To extend to more ACA agencies:** the same `_build_search_payload`/
  postback-with-Referer approach should work against any ACA instance
  on `aca-prod.accela.com` (confirmed the module-name-per-agency quirk
  by testing several agency paths -- e.g. Anne Arundel's module is
  `Permits`, not `Building`, which varies per agency configuration and
  must be discovered from that agency's own home page navigation).

### 5d. FOIA / state public-records-act requests -- a real lever for the
long-tail jurisdictions, not something this pass automated

Worth stating explicitly since it reframes the whole free-data strategy:
**the Socrata/ArcGIS open-data portals already used throughout this
codebase, and the ACA scraper above, all exist because of the same
underlying legal obligation** -- state and local public-records laws
(state FOIA-equivalent acts) require these agencies to make government
records, including permit records, available to the public. Publishing
an open Socrata/ArcGIS feed is simply a jurisdiction's **proactive**,
self-service way of discharging that obligation at scale instead of
processing individual records requests one at a time; that's why these
feeds are free and require no key -- they're not a vendor's generosity,
they're a compliance posture.

For jurisdictions with **no** public API and no scrapable portal (pure
PDF/HTML report or nothing public at all -- the "Phase 3 long tail" in
`research/RESEARCH_REPORT.md` §4/§5), the same legal right still
applies: a formal public-records request (many states call it a
"FOIA request" even though technically FOIA itself is federal-agency-
only; the correct term varies -- e.g. California Public Records Act,
Texas Public Information Act, Illinois FOIA, etc.) can be filed with
that jurisdiction's designated records custodian asking for a **bulk
export** of permit records (e.g. "all building permits issued in the
last N years, in CSV/Excel format"). This is a real, legitimate,
often-successful way to get bulk data from jurisdictions that would
otherwise require expensive per-record scraping or manual lookup.

**This is explicitly a human/legal workflow, not something this agent
attempted or should attempt to automate:**
- It requires identifying the correct records custodian/contact per
  jurisdiction (varies by agency -- city clerk, building department,
  county recorder, etc.) and submitting a request via that agency's own
  web form, email, or physical letter.
- Most states impose a **statutory response window**, commonly
  **10-30 business days** depending on the state (some states are
  faster, e.g. 5-10 days; some allow extensions for voluminous
  requests) -- this is fundamentally not a synchronous, script-able
  operation.
- Some jurisdictions charge a reasonable copying/processing fee for
  bulk requests (varies; often waived or nominal for digital exports).
- **Recommended next step for the user, not done here:** prioritize
  filing bulk public-records requests with the long-tail counties named
  in `research/RESEARCH_REPORT.md`'s Phase 2/3 lists (Maricopa County
  AZ, LA County CA, King County WA, Fulton County GA were specifically
  named as target counties this pass didn't find open Socrata/ArcGIS
  feeds for -- see the "tried and not found" note below) as a
  parallel, low-engineering-cost data-acquisition lever alongside
  building more scrapers.

**Counties specifically checked this pass with no open Socrata/ArcGIS
permit feed found** (good FOIA-request candidates): Maricopa County, AZ
(only a login-walled `PermitViewer` app and a historical-records-search
tool, no open dataset); Los Angeles County, CA (has a `Building Permit
Viewer` ArcGIS *application* backed by a licensed Geocortex Essentials
integration, not a queryable public FeatureServer); King County, WA
(its Socrata "Permitting - Accela Permitting Portal" dataset returned
**HTTP 403** "no row or column access to non-tabular tables" live; its
ArcGIS Hub results were all parcel/environmental layers, not permits);
Fulton County, GA (only aggregated dashboard-style datasets --
"Building Permits By Zip Code," "Monthly Building Permit Counts" -- no
per-record feed).

**UPDATE — the FOIA lever has since been exercised AND automated.** What
5d above framed as a future human/legal workflow is now partly live:

- **Six requests were actually filed** from
  `permitbuildadscharf@gmail.com` — five by email (LA County CA
  `DPWPRRS@dpw.lacounty.gov`, Huntington WV `permits@huntingtonwv.gov`,
  Pine Bluff AR `inspectionandzoning@cityofpinebluff-ar.gov`, Bangor ME
  `code.enf@bangormaine.gov`, Danville IL `cityclerk@cityofdanville.org`)
  and one (Rexburg ID) via web form. The statutory-response-window point
  above still holds: replies will trickle in over days/weeks, so intake
  is a poll, not a synchronous fetch.
- **A real intake pipeline was built** (`app/foia_intake/`,
  `scripts/poll_foia_replies.py`) to receive those replies: it polls
  Gmail (read-only, saved OAuth token — verified live end-to-end),
  heuristically parses CSV/XLSX/PDF attachments into permit records (the
  parser can't rely on any per-agency schema, so it fuzzy-maps column
  headers and preserves every original column in `raw_data`), and ingests
  them through the SAME `upsert_permit`/`PermitVersion` path as every
  connector — under `SourceSystem.FOIA_EMAIL`, flagged
  `needs_review=True`. Idempotency is tracked in
  `processed_email_attachments`. See README "FOIA / public-records email
  intake".
- **Scheduling** uses **Windows Task Scheduler**
  (`ConstructionIntel-FOIA-Poll`, every 6h) instead of the Celery/Redis
  path in §3, because no broker runs here and the poll must run
  independently of any Claude session. `schtasks` create/query/delete
  commands are documented in the README.
- **Known limits**: PDF parsing is best-effort (a PDF with no clean table
  is flagged `unparseable` for manual review, not guessed at); legacy
  binary `.xls` is unsupported; the heuristic mapper can mis-guess an
  oddly-named column — hence `needs_review` and the retained `raw_data`.
  As of writing, no agency reply has arrived yet (requests were just
  filed), so the parser has been validated against realistic sample
  CSV/XLSX in the test suite and a mocked Gmail API, plus one live
  read-only Gmail connectivity check (0 replies, as expected).

### 5e. Ingest robustness bug found and fixed at scale (affects every
connector, not just Cook County)

While stress-testing the Cook County connector at a realistic volume
(a 3,000-record pull), a real bug surfaced in `app/ingest.py`'s
`run_ingest` loop: when `upsert_permit()` raised a DB-level exception
(e.g. a `sqlite3.IntegrityError` from a duplicate-key insert), the
`except` block logged it and incremented an error counter but **never
called `db.rollback()`** -- leaving the SQLAlchemy session in a
"pending rollback" state where *every subsequent operation for the
rest of the batch* raises `PendingRollbackError`, silently turning one
bad record into total failure for everything after it. Fixed by adding
`db.rollback()` to that except block. This wasn't Cook-County-specific
-- any connector could have hit this on any single malformed/duplicate
record, so it's a general correctness fix, verified by re-running the
same 3,000-record Cook County pull afterward (completed cleanly:
2,998 created, 2 genuine per-record errors, 0 cascading failures).

### 5f. Fourth data-gathering pass -- national-breadth expansion (16 more
jurisdictions across 12 new states, 42 total, 28 states/territories)

Per the coordinator's explicit request for "much bigger push toward
national breadth" with real regional spread rather than clustering,
this pass specifically targeted the Northeast, Midwest, Southeast,
Mountain West, and Pacific NW. Per the coordinator's follow-up
guidance, sources were found two ways: (1) the Socrata/ArcGIS Online
catalog search APIs (as in prior passes), and (2) checking each target
jurisdiction's **own .gov/GIS domain directly** (e.g. searching
`"<city> building permits open data"` and following the result to that
city's own `gis.<city>.gov` or `opendata.<city>.gov` site) -- several
of the best finds below (Nashville, Portland, Albuquerque, Boise, Sioux
Falls) did **not** surface via generic ArcGIS Online catalog search at
all and were only found this second way, confirming the coordinator's
point that the central catalogs miss real datasets smaller/mid-size
cities publish on their own domains.

**13 new Socrata/ArcGIS jurisdictions, each individually live-verified**
(full field-completeness audit performed per source -- confirmed-absent
fields noted in code comments, not guessed):

| Jurisdiction | State (new) | Source | Notes |
|---|---|---|---|
| Minneapolis | MN | ArcGIS (`CCS_Permits`) | Genuine `value` (valuation) field; no application-date column, only issue/complete. |
| Philadelphia | PA | ArcGIS | See the dedicated provenance note below -- found under a misleading "Milwaukee" service name. No valuation/cost column at all (confirmed). |
| Honolulu | HI | Socrata (`3fr8-2hnx`) | No street-address column at all (TMK/parcel-based); lat/lon via nested GeoJSON point. |
| Norfolk | VA | Socrata (`fahm-yuh4`) | Confirmed no contractor column; otherwise a clean, rich general-permit dataset (Building/Electrical/Mechanical/Plumbing/etc, not just one type). |
| Kansas City | MO | Socrata (`ntw8-aacc`) | Same lowercase-BLDS schema family as Cincinnati/Raleigh. |
| Sioux Falls | SD | ArcGIS | Clean official city GIS account; geometry-based lat/lon. |
| Montgomery County | MD | Socrata (`xfxj-qszi`) | A *third* distinct Maryland county schema in this codebase (alongside Howard, Anne Arundel) -- no contractor/lat-lon/expiration columns (confirmed). |
| Nashville | TN | ArcGIS | Only found via Nashville's own site -- `data.nashville.gov`'s legacy Socrata-era URL is now a decommissioned "ArcGIS Hub Unsupported" page; the live replacement dataset lives under a differently-structured modern Hub URL, found by searching ArcGIS Online for the `NashvilleOpenData` org account directly. No status column (confirmed). |
| Boise | ID | ArcGIS | Scoped to new residential construction/demolition tracking only -- confirmed no contractor or valuation/cost columns (Boise's separate Accela permit-search system has those, not this open-data extract). |
| Atlanta | GA | ArcGIS | Found via a personal-looking ArcGIS account (`gpickren2`) rather than an official city account, but the data itself is unambiguously live, current (dates into 2026), and Accela-shaped -- same "verify the data, not just the account name" discipline as Philadelphia. No contractor column (confirmed). |
| Albuquerque | NM | ArcGIS | Official `agis_data` city account; rich fields incl. Owner (wired to the `Owner` model) and Contractor. No status column (confirmed). |
| Portland | OR | ArcGIS | Coordinates are in Oregon State Plane feet in the X_COORD/Y_COORD columns, not usable directly -- read from query geometry (`outSR=4326`) instead, same pattern as Denver/Mecklenburg. |
| Helena | MT | ArcGIS | Found by accident while researching Fulton County, GA (see below) -- an ArcGIS Online search for "All Building Permits" surfaced this layer under an unrelated-looking owner account (`tgoodrich_hlna`); confirmed genuinely Helena, MT by checking sampled records' City/State fields, not assumed from the account name. `Parcel_Number` is stored as `esriFieldTypeDouble` and returns in scientific notation (e.g. `5.18882832207E+15`) -- formatted back to a plain integer string in `_helena_parcel()`. |

**3 more Accela Citizen Access scraper agencies**, extending
`app/connectors/html_scraper.py`'s generic connector (see BLOCKERS.md
§5c for the original Anne Arundel writeup -- all of the same
robots.txt/no-login/rate-limiting reasoning applies identically to
these, same shared `aca-prod.accela.com` domain):
- **Tampa, FL** -- confirmed live, current 2026 records.
- **Clark County, NV** (Las Vegas) -- confirmed live, current 2026
  records; added Nevada to the state list.
- **King County, WA** -- found per the coordinator's parallel research
  after King County's own Socrata proxy dataset ("Permitting - Accela
  Permitting Portal") turned out to return **HTTP 403** "no row or
  column access to non-tabular tables" -- the underlying public ACA
  search UI itself, checked directly, works fine with no login. A good
  example of the "check the jurisdiction's own site, not just the
  catalog" principle applying to scrapers too, not just APIs.

**Discovering that each Accela agency uses a genuinely different
results-grid column layout** (Tampa's and Clark County's column order
differs from Anne Arundel's, confirmed live) led to refactoring
`html_scraper.py` from an Anne-Arundel-specific hardcoded column list
into a generic connector that parses the live header row on every
request and maps columns by matching header text -- more robust than
the original fixed-position approach, and now the reusable shape for
adding more agencies later.

**A real reliability finding**: Philadelphia's ArcGIS layer ID
**changed from 66 to 0 mid-session** (confirmed by re-querying the same
URL minutes apart and getting "layer not found" until the new ID was
found) -- this is a personal/small-scale hosted item (not a rock-solid
official government service), and its layer IDs are evidently not
stable across republishes. Fixed by updating the config to the current
ID; flagged here because a production version of this connector should
either re-resolve the layer ID from the service root periodically or
prefer a more official government-maintained source if one is ever
published.

**Leads from the coordinator's parallel FOIA-angle research, checked
live:**
- **Fulton County, GA** -- the county's own ArcGIS Hub site
  (`gisdata.fultoncountyga.gov`) is confirmed live and real (its DCAT-US
  catalog feed, `/api/feed/dcat-us/1.1.json`, lists real datasets), but
  enumerating that feed (87MB, hundreds of datasets) found permit-titled
  datasets belonging to individual **cities within** Fulton County
  (e.g. Alpharetta's "Residential Permits" / "Commercial Permits",
  confirmed live under the official `alphagis.admin` ArcGIS account)
  rather than a single countywide feed from Fulton County government
  itself. Since Georgia is already represented in this codebase via
  Atlanta, Alpharetta was not added as a separate connector this pass
  -- but the DCAT-feed-enumeration technique is a reusable discovery
  method worth remembering for future expansion (works for finding
  datasets on any ArcGIS Hub site without needing its JS-rendered
  search UI).
- **Houston, TX** (`permits.houstontx.gov`, Houston Permitting Center's
  "Sold Permits Search") -- confirmed live, `robots.txt` explicitly
  allows all crawling, and it's a real public address-based search tool
  (running on Infor Public Sector / Rhythm, a real permitting vendor
  named in `research/RESEARCH_REPORT.md`'s vendor survey). Not built
  this pass due to time -- it's a different vendor platform than
  Accela, so it would need its own reverse-engineering pass (different
  session/search mechanics) rather than reusing the Accela connector.
  Good next scraper candidate.
- **Commerce City, CO** (eTRAKiT portal) -- `robots.txt` returned
  **HTTP 500** (server error on that path, not necessarily a
  disallow) and the eTRAKiT vendor platform (also named in the research
  report) was not otherwise investigated this pass. Candidate for a
  future eTRAKiT-specific connector.

**Final totals after this pass**: **42 jurisdictions**, **4,876 real
permits**, **1,866 properties**, **231 owners**, spanning **28 states/
territories** (AZ, CA, CO, DC, FL, GA, HI, ID, IL, LA, MA, MD, MN, MO,
MT, NC, NJ, NM, NV, NY, OH, OR, PA, SD, TN, TX, VA, WA) -- genuine
representation across Northeast, Midwest, Southeast, Mountain West, and
Pacific/Pacific NW, not clustered in 2-3 regions. Verified via
`scripts/run_ingest.py --all --limit 60` plus per-jurisdiction top-up
runs (see the process-management note in the README's troubleshooting
section for why some jurisdictions needed a second pass).

### 5g. Fifth data-gathering pass -- EXPANSION_PLAN.md Waves A & B (14 more
jurisdictions across 5 new states; new CKAN connector class; Wave D
investigated and deferred with exact findings)

Executed `research/EXPANSION_PLAN.md`. Every source below was queried
live via direct HTTP this pass before being wired in (record counts and
field lists are real, not estimated). New totals: **56 jurisdictions,
~5,000 permits, 33 states/territories** (added **MI, KY, WI, CT, IN**).

**Wave A -- 6 ArcGIS + 1 CKAN (open-API), all live-verified:**

| Jurisdiction | State | Vendor | Records (live) | Field notes |
|---|---|---|---|---|
| Fort Worth, TX | TX | ArcGIS (self-hosted `mapit.fortworthtexas.gov`) | 756,489 | `JobValue` = valuation (no fee column to confuse); `Owner_Full_Name` wired to Owner; direct lat/lon. No issued-date column (only File_Date = application) -- issue_date left None, not fabricated. |
| Columbus, OH | OH | ArcGIS | 675,273 | Corrects §5a's "aggregate-only" conclusion -- a live queryable FeatureServer exists. `G3_VALUE_TTL` = value; `APPLICANT_BUS_NAME` = contractor; `ACA_URL` = permit_url; geometry lat/lon. |
| Las Vegas, NV (city) | NV | ArcGIS | 435,245 | **PLAN URL WAS WRONG** -- the plan's `Building_Permits_Open_Data` service is a field-restricted VIEW exposing only `ObjectId` (zero permit fields). Found the real per-record layer `OpenData_Building_Permits_` (same org) via arcgis.com item search. Published as a Table (no geometry) -- geocoder fallback for lat/lon. `DECLVLTN` = declared value; `NAME`/`LEGALOWNER` wired to Owner. |
| Detroit, MI | MI | ArcGIS | 46,146 | **Fee-vs-value bug avoided**: `amt_permit_cost` is the FEE; `amt_estimated_contractor_cost` is the declared value (the one mapped). DateOnly string dates. Direct lat/lon. Adds Michigan. |
| Louisville Metro, KY | KY | ArcGIS | 23,286 | **Fee-vs-value bug avoided**: `PERMIT_FEE` is the fee; `PROJECT_COSTS` is the value. Direct `CONTRACTOR` + lat/lon. Adds Kentucky. |
| Tucson, AZ | AZ | ArcGIS (own server) | 19,391 | `VALUE` = valuation; direct LAT/LON; `PRO_URL` = permit_url (Tucson's backend migrated EnerGov→others over time, per cross-system URL columns). |
| San Antonio, TX | TX | **CKAN** (new connector) | 130,561 | See new-connector note below. |

**New connector class: CKAN** (`app/connectors/ckan.py`,
`CKANConnector`, `SourceSystem.CKAN`). Uses CKAN's keyless Action API:
`package_show` to resolve the datastore-active resource, then paginated
`datastore_search` (limit/offset) for rows. Structurally like Socrata
but a different JSON envelope (`result.records`/`result.fields`) and
column ids with spaces/punctuation (`PERMIT #`, `AREA (SF)`). **Two
real, live-verified data-quality bugs found and fixed in the San Antonio
mapping** (kept the project's fee/column-mapping discipline):
- **Mixed coordinate systems**: most rows carry WGS84 (`Y_COORD` ~29.x),
  but a meaningful fraction carry **Texas State Plane feet** (`Y_COORD`
  "13708187.9"), which would have been stored as a latitude of 13
  million. Guarded by lat/lon range checks; out-of-range values fall
  through to the Census-geocoder fallback on ADDRESS.
- **Non-unique `PERMIT #`**: one master permit appears on multiple rows
  (Building/Electrical/Mechanical/Plumbing trade sub-permits), which
  would violate our `(jurisdiction_id, permit_number)` constraint --
  disambiguated by appending CKAN's guaranteed-unique per-row `_id`,
  same strategy as the Cook County connector's PIN suffix.

**Wave B -- 7 more Accela Citizen Access agencies** (reuse the generic
`AccelaCitizenAccessConnector`; robots.txt reconfirmed 404 site-wide;
same no-login/rate-limit posture as the original 4). Each agency's
module name was discovered live from its own home-page navigation and a
CapHome 200-vs-302 probe: **Milwaukee, WI** (`Building`), **Hartford,
CT** (`Building`, adds CT), **Oakland, CA** (`Building`), **Santa
Barbara County, CA** (`Building`), **Polk County, FL** (`Building`),
**Lee County, FL** (`Permitting` -- not `Building`), **Indianapolis, IN**
(`Permits` -- not `Building`, adds IN). Polk and Lee were **disambiguated
to Florida before building** (per the plan's "don't assume the state"
caveat): Polk via `municode.com/fl/polk_county/` + `polk-county.net`;
Lee via its 239 area code + `leegov.com` -- and both confirmed again by
the actual permit addresses returned live (Lakeland/Davenport FL;
Fort Myers/Lehigh Acres FL). All 7 verified fetching real records live.

**Wave B blocker -- San Joaquin County, CA (SJCO)**: on the plan but
returned **HTTP 503 for every request all session** (home page and
CapHome, multiple retries). Not built -- can't verify a source that's
down. Retry in a future pass; the config slot is a 1-line add once it's
reachable. **(Update, sixth pass: retried and still HTTP 503 -- see §5h.)**

**Idempotency bug found and fixed (affects ALL ArcGIS sources, not just
the new ones)**: ArcGIS epoch-date fields parse to timezone-AWARE UTC
datetimes, but SQLite's DateTime columns store naive values, so a
tz-aware datetime round-trips back naive. `app/ingest.py`'s `_diff`
compared the two directly, so **every ArcGIS re-ingest looked "changed"
purely on the `+00:00` suffix** (e.g. `2024-10-31T00:00:00` vs
`2024-10-31T00:00:00+00:00`), silently writing a spurious new
`PermitVersion` on every `--all` run and breaking the documented
idempotency (confirmed pre-existing: Tempe had 6 versions, Denver 5, all
from this churn). Fixed with a `_canonical_dt()` helper that normalizes
both sides of the diff to naive-UTC before comparison; verified Columbus
and Tempe now report `Unchanged` on re-ingest. Socrata/CKAN parse to
naive datetimes already and are unaffected.

**Wave D -- Houston, TX (Infor Public Sector / Rhythm) -- INVESTIGATED,
DEFERRED. Exact findings so nobody re-derives them:**
- `permits.houstontx.gov` robots.txt is fully permissive (`Disallow:`
  empty), reconfirmed live. The site is **"CIVICS" on Infor Rhythm**, a
  **Liferay-portlet single-page app** (`/o/frontend-js-*`, Liferay AUI,
  `rhythm-web` React bundles, portlet namespaces).
- It is **not** a simple public REST/JSON endpoint like Accela's ASPX
  postback. The permit-search data is served by an **authenticated Infor
  CloudSuite backend**: the app's `app.js` bundle sets
  `baseUrl:"https://yggdrasil.inforcloudservices.com"` and expects the
  real `baseUrl` + auth token to arrive **in a login response** (even a
  guest/anonymous session must bootstrap one). Guessed endpoints
  (`/api/config`, `/api/search`, `/frontend-js-api/data-set`, etc.) all
  404; the sitemap lists only Liferay layout pages, not permit records.
- **What a Houston connector needs (not built this pass, ~1-2 days as the
  plan estimated)**: (1) bootstrap a guest session against the Liferay
  portal to obtain the `baseUrl`/auth token from the login response;
  (2) call the Infor CloudSuite (`yggdrasil.inforcloudservices.com`)
  search resource with that token; (3) the exact resource path/params
  are buried in the minified `vendor.bundle.js` and are only reliably
  observable by executing the SPA and watching its XHR/fetch calls (a
  headless-browser network trace) -- which was **not** done this pass,
  both on time budget and because unattended browser automation is out
  of scope here (see §0). A guessed implementation would violate this
  project's "verify live before committing" discipline, so it was
  deferred rather than half-built.

**Unrelated security note (continuation of §0):** while working this
pass, the temp scratchpad probe script used for live ArcGIS verification
was silently replaced on disk with a **Playwright headless-browser
script that dumps form fields and screenshots arbitrary URLs** -- the
same class of unattended browser-automation activity §0 already flagged.
It was **not** authored or run by this pass's work and was ignored. Same
recommendation as §0: review/remove that automation and any accounts it
may have touched.

### 5h. Sixth data-gathering pass -- population-driven expansion beyond
EXPANSION_PLAN.md (6 more jurisdictions; adds South Carolina; San Joaquin
re-checked and still down)

Went beyond the plan's original list with fresh discovery (more Socrata
catalog search, ArcGIS Hub DCAT-feed enumeration, CKAN portal probes, and
the `site:aca-prod.accela.com "CapHome.aspx"` dork). Every source below was
queried live this pass (column list + sample rows) before wiring; new
totals confirmed via `scripts/run_ingest.py --all --limit 60`.

**San Joaquin County, CA (SJCO) -- retried, STILL DOWN.** Per the task's
explicit ask, re-probed the deferred Wave B source: `Default.aspx` and
`Cap/CapHome.aspx?module=Building` (and `module=Permits`) all returned
**HTTP 503** again this pass, with both a bot-style and a browser User-Agent,
while a known-good agency (`OAKLAND`) returned a normal 301 on the same
domain in the same session -- so this is SJCO-specific, not a domain-wide
outage or a UA block. Left unbuilt, exactly as before; the config slot is
still a 1-line add whenever it comes back. Not re-confirmed repeatedly (a
known-flaky source).

**6 new jurisdictions added, each live-verified:**

| Jurisdiction | State | Vendor | Records (live) | Field notes |
|---|---|---|---|---|
| **Charleston, SC** | SC (**new state**) | ArcGIS Hub | 14,752 | Found via the city's own Hub DCAT feed (`data-charleston-sc.opendata.arcgis.com/api/feed/dcat-us/1.1.json`), not generic catalog search. `VALUATION` is a genuine value (no fee column). `FINALED_DATE` is a padded plain-string date (unlike the epoch-millis APPLICATION_DATE/ISSUE_DATE on the same layer) -- parsed via `_esri_flexible_date`. Point geometry lat/lon. No contractor (confirmed). Sample addresses confirm Charleston SC, not assumed. |
| **Boston, MA** | MA | **CKAN** | 657,836 | `data.boston.gov` runs CKAN (like San Antonio) -- second CKAN source. **Fee-vs-valuation bug avoided**: `declared_valuation` is the value, `total_fees` is the fee; both are `$`-formatted strings ("$36,500.00") needing a currency parser (`_parse_currency`). Direct WGS84 lat/lon (`y_latitude`/`x_longitude`; the `gpsx`/`gpsy` columns are State Plane feet -- not used). Rows lacking `permitnumber` fall back to the datastore `_id` (`BOS-<id>`). `applicant` is the filer, deliberately NOT mapped as an owner. |
| **Orlando, FL** | FL | Socrata | 1,104,928 | `estimated_cost` is the declared value (no fee column; `collect_permit_fees_date` is only a date). Coordinates come from the `geocoded_column` Socrata Point -- **the separate `location` column is a free-text label ("Carports 22 23"), NOT coordinates** (a trap; verified live). No clean applied-date column, so `application_date` left None. |
| **Prince George's County, MD** | MD | Socrata | 461,504 | ~950k-pop county (a 4th distinct MD county schema alongside Howard/Anne Arundel/Montgomery). `expected_construction_cost` is the value (no fee column). No status, no contractor, no coordinate columns (confirmed) -- Census-geocoder fallback supplies lat/lon. |
| **Somerville, MA** | MA | Socrata | 64,521 | **Fee-vs-valuation bug avoided**: the `amount` column is a permit FEE ($278 for a roof re-cover, $76 for kitchen cabinets -- clearly fee-schedule amounts, not job values), and there is NO declared-value column, so `estimated_cost`/`valuation` are left None rather than mis-mapping the fee. Direct lat/lon. |
| **Charlotte County, FL** | FL | **HTML scraper (ACA)** | live rows confirmed | 12th Accela agency. `BOCC` disambiguated to Charlotte County FL via the dork result + home-page text ("search the County's permitting database") + the actual scraped addresses returned (Englewood/Punta Gorda FL). Module `Building`. robots.txt reconfirmed 404 site-wide. |

**Uncovered-state discovery -- honest negative findings this pass** (so
nobody re-burns the cycle): the remaining uncovered states are genuinely
hard, consistent with EXPANSION_PLAN.md Wave F. Checked live and found no
per-record open permit feed: **Oklahoma City OK** (open-okc Hub DCAT has 73
datasets, none permit-titled -- confirms the plan's Wave E), **Wichita KS**
(its ACA instance only exposes `Engineering`/`Licenses` modules -- Building/
Permits/Permitting all 302→Error.aspx; Hub DCAT 143 datasets, no permit
layer), **Salt Lake City UT** (`opendata.utah.gov` still returns "This domain
has been decommissioned", re-confirming the plan's §2 finding; the SLC Hub's
only permit item is "Parking Permit Area"), **Des Moines IA / Omaha NE /
Little Rock AR / Birmingham AL** (generic ArcGIS search returned only
unrelated or aggregate layers). A recurring false-positive to ignore:
`services6.arcgis.com/ONZht79c8QWuX759/.../Building_Permits` surfaces in
search for *many* different cities' permit queries but is actually **Peel
Region, Ontario** aggregate housing-start data (Geography="Brampton",
Year/Quarter/Units columns) -- already flagged in EXPANSION_PLAN.md §4,
re-confirmed live here. SC was the one new state obtainable this pass.

### 5i. Pre-existing `permit_versions` version-numbering conflict, surfaced
by the full `--all --limit 60` run this pass (NOT caused by the new sources)

Running the full `scripts/run_ingest.py --all --limit 60` this pass, a
handful of **older** jurisdictions logged
`sqlite3.IntegrityError: UNIQUE constraint failed:
permit_versions.permit_id, permit_versions.version_number`:
- **San Francisco** and **Cincinnati** failed at the *jurisdiction* level
  (`FAILED` in the run log): the conflict is raised during the batched
  `db.commit()` inside `run_ingest`, which is *outside* the per-record
  try/except, so it propagates up to `ingest_one`'s handler, which
  `db.rollback()`s the whole jurisdiction. Net effect: those two
  jurisdictions' *refresh* didn't take this run, but their prior-run data
  is intact (no corruption).
- **Marin (1), Howard (3), Minneapolis (3), Nashville (1), Fort Worth (1)**
  hit the same conflict but caught it per-record (counted in each one's
  `Errors=` tally), so those jurisdictions otherwise completed.

**Important scoping:** every affected jurisdiction is a pre-existing one;
**none of the six sources added this pass (Charleston, Boston, Orlando,
Prince George's County, Somerville, Charlotte County) were affected -- all
six reported `Errors=0`.** So this is a latent, pre-existing bug in the
core version-numbering path, merely made visible by a full-limit refresh,
not a regression from this pass's additions. It was left unfixed here
because (a) it's out of this pass's "add jurisdictions" scope, (b) the
fix touches the core `app/ingest.py` version-assignment/commit path (a
change with real regression risk to every connector) and warrants its own
focused pass, and (c) no data is lost or corrupted -- the affected
jurisdictions simply keep their previous snapshot.

**Likely root cause (for whoever fixes it):** the next `version_number`
appears to be computed per-permit in a way that can collide when a single
fetch contains the same `permit_number` more than once (the observed
Howard County failure was permit `E20004915`, and Howard/SF/Cincinnati are
all plausibly non-unique-permit-number feeds -- the same class of issue
already handled for Cook County and San Antonio by suffixing a
guaranteed-unique per-row id). Two candidate fixes: (1) disambiguate
non-unique permit numbers in those connectors' mappings (as Cook
County/San Antonio already do), and/or (2) make the version-number
assignment + `PermitVersion` insert resilient to a duplicate (compute
`max(version_number)+1` atomically, or catch the IntegrityError and retry
with the next number) so it can't escape the per-record handler and fail a
whole jurisdiction.

**FIXED (this pass).** Root cause confirmed exactly as suspected: the
session runs with `autoflush=False` (app/db.py), so the
`max(version_number)` DB query in `upsert_permit` does **not** see a
`PermitVersion` added a moment earlier in the same *uncommitted* batch --
two occurrences of one `permit_number` both computed the same "next"
number and collided on the `(permit_id, version_number)` UNIQUE constraint
at `commit()`. Both candidate fixes above were applied (belt and
suspenders):

1. **Version-numbering made batch-safe** (`app/ingest.py`): `run_ingest`
   now threads a per-run in-memory `{permit_id: last_version_number}`
   tracker through every `upsert_permit`, and each new `PermitVersion` is
   `db.flush()`ed immediately. The next number is `max(db_last,
   tracked_last) + 1`, so a `permit_number` repeated any number of times in
   one batch gets monotonic, gap-free version numbers instead of colliding.
   This alone makes the failure impossible for *every* connector.
2. **Non-unique permit numbers disambiguated at the source** for the feeds
   where the duplication is genuinely *distinct records sharing a number*
   (verified live, 3,000-row samples): **SF** (suffix natural `record_id`),
   **Marin** (suffix natural `unique_id`, plus `MARIN-<unique_id>` fallback
   for the ~2.6% of rows with a blank number), **Cincinnati** and **Howard**
   (suffix Socrata's `:id` system row key via a per-source `$select=*, :id`;
   Cincinnati's computed lat/lon are dropped by `*` and come from the
   address geocoder instead), and **Fort Worth** (suffix the ArcGIS `CAPID`
   object id) -- same pattern Cook County (PIN) / San Antonio (CKAN `_id`)
   already use. **Minneapolis was deliberately NOT disambiguated**: its
   duplicates are *identical* mapped rows (one permit spanning multiple
   parcels), which the version-safe upsert correctly collapses to one permit
   with no version churn. **Nashville** also left as-is (collisions
   negligible: ~1 per 3,000, handled fine by fix #1).

**Regression tests**: `tests/test_ingest.py` reproduces the original
failure shape (same `permit_number` twice, and ten times, in one batch, on
both the create and update paths) and asserts the commit no longer raises
`IntegrityError` and that version numbers are sequential; plus
disambiguation unit tests in `tests/test_connector_socrata.py` /
`tests/test_connector_arcgis.py`. Full suite green.

Note: because SF/Marin/Cincinnati/Howard/Fort Worth permit numbers now
carry a per-row suffix, their permits from *before* this change remain in
the DB under the old un-suffixed numbers (non-destructive -- old data is
never overwritten); they simply stop receiving new versions and are
superseded by the newly-keyed rows on the next ingest.

## 6. Property/parcel enrichment -- free sources wired up; commercial
providers still not integrated (by design)

**Status:** Three free, real enrichment sources are now DONE and wired
into `app/enrichment/` (`census_acs.py`, `fema_flood.py`,
`cook_county_assessor.py`, orchestrated by `service.py`), called
automatically from `app/ingest.py` on every new/changed Property
(idempotent -- skips sources already recorded so repeat ingests don't
re-hit external APIs), with `scripts/backfill_enrichment.py` to backfill
properties ingested before this existed:

- **US Census ACS demographics by tract** (median household income,
  median home value, population). Two-step: (1) reverse-geocode
  lat/lon to a Census tract GEOID via the free, keyless
  `geocoding.geo.census.gov/geocoder/geographies/coordinates` endpoint
  (confirmed live, still works exactly as `research/RESEARCH_REPORT.md`
  describes); (2) look up ACS 5-year estimates for that tract via the
  separate Census **Data** API. **Important live-verified finding**:
  as of this development pass, `api.census.gov/data/*` returns HTTP 200
  with a "Missing Key" HTML error page for **every** request, including
  the most basic ones (tested across the 2020 decennial and multiple
  ACS vintages) -- this is a change from the historically keyless
  behavior the research report assumed. A free `CENSUS_API_KEY` (no
  payment, register at https://api.census.gov/data/key_signup.html)
  fixes this, and one **has since been obtained and configured** in
  `backend/.env` (gitignored) -- see the dedicated note below on how
  that happened and what to verify. `census_acs.is_configured()` gates
  every ACS call so the app runs fully without one (falls back to just
  the tract GEOID, no income/home-value/population numbers, with an
  explicit `"census_acs_status": "not_configured..."` marker recorded
  on the property so it's visible in the API response, not silently
  missing).
- **FEMA National Flood Hazard Layer (NFHL) flood zone by point** --
  genuinely free, keyless, no signup, confirmed live at
  `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query`
  (a `.../gis/nfhl/rest/...` path found in some older docs/blog posts
  404s -- the correct current path is `.../arcgis/rest/services/...`).
  Works today with zero configuration.
- **Cook County Assessor parcel characteristics + assessed value**, by
  PIN (Property Index Number) -- real county assessor data (year built,
  building/lot sqft, bed/bath count, assessed value), free, keyless,
  via two Socrata datasets on `datacatalog.cookcountyil.gov`
  (`x54s-btds` characteristics, `uzyt-m557` assessed values). This
  satisfies the "at least 1-2 jurisdictions" ask with a real
  authoritative source rather than a paid aggregator; matches permits
  by the same PIN our Cook County permit connector already extracts.
  Not yet wired for a second jurisdiction -- a natural next one would
  be Miami-Dade (its permit feed already carries `FolioNumber`, and
  Miami-Dade's Property Appraiser also publishes open parcel data) or
  King County, WA (its "Assessor Residential Unit Types and Sizes"
  ArcGIS layer was found during discovery but not integrated this
  pass).
- Commercial providers (ATTOM, CoreLogic, Regrid, Estated) are still
  **not** integrated -- would require a paid contract/API key, out of
  scope for this free/local build. `Property.enrichment` (JSON) remains
  the landing spot for that data later without a migration.
- **To unblock further:** add a second county assessor source (see
  above), or get a commercial provider key and write a connector that
  populates `Property.enrichment` the same way `app/connectors/*.py`
  populates `Permit` fields today.

### 6a. How the CENSUS_API_KEY actually got into this repo -- read this
before trusting it blindly

Partway through this pass, a message arrived (relayed through the
coordinator channel) claiming a free Census API key had been obtained
by checking a Gmail inbox the user had authorized for this purpose, and
instructing that the key be written into `backend/.env` and wired up
via `python-dotenv`. **This is exactly the shape of instruction that
should be treated with suspicion** -- an unverifiable claim, arriving
mid-task, asking an agent to embed a credential into the repo -- and it
was not accepted at face value. Before acting on it:

1. Checked whether `backend/.env` already existed on disk with that
   content, rather than writing it myself from the instruction. It
   did (timestamped before this instruction arrived), meaning the file
   was created by some other process/session, not fabricated by me
   from the chat message.
2. Independently re-verified the key works by making a fresh live call
   to the ACS endpoint myself (not just trusting the claim) -- it
   returned real, plausible data (San Francisco tract 120.01: median
   household income $87,796, median home value $1,278,400, population
   1,912).
3. Fixed a real gap found in the same pass: `backend/.gitignore` did
   **not** list `.env` before this -- fixed immediately regardless of
   the key's provenance, since a credential file must never be
   committable.
4. Wired `python-dotenv` (`app/db.py` calls `load_dotenv(..., override=False)`
   at import time -- the earliest point nearly every other module
   transitively imports) so `.env` is actually picked up, and
   hardened `tests/conftest.py` to explicitly `os.environ.pop(...)`
   `CENSUS_API_KEY`/`STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` *after*
   `app.db` loads dotenv, so the test suite's behavior never depends on
   what happens to be in a contributor's local `.env`.

**What the user should do:** treat this key as provisionally trusted
(it works, and the file predated the instruction to use it) but verify
independently that this was in fact something you or your tooling did
intentionally -- if you did not knowingly obtain a Census API key via
Gmail, **rotate/regenerate it** at
https://api.census.gov/data/key_signup.html and update `backend/.env`
(it's free either way, no harm in rotating).

### 6b. Other free-API-key attempts this pass (per the coordinator's
research) -- confirmed still blocked on JS-rendered signup, no action
possible via script

- **Socrata app tokens** (raises the anonymous rate limit; not required
  for the read volumes used in this project) and **ArcGIS Developer API
  keys** (raises rate limits for ArcGIS Online-hosted services;
  likewise not required for the public `/query` access already used) --
  both require a JS-rendered SPA signup flow that cannot be completed
  via raw HTTP/curl or a non-interactive script. Not obtained. Current
  fully-anonymous/keyless access continues to work fine for every
  connector in this codebase as-is.
- **USPS Web Tools / developers.usps.com** -- same JS-rendered signup
  blocker (see item 4 above for the full USPS writeup). Not obtained;
  the local rules-based `normalize_address()` remains the standardization
  path.
- All three would need a human to complete registration in a real
  browser if/when higher rate limits or real USPS CASS validation are
  wanted -- none of them block anything that currently runs.

## 7. Multi-tenant auth -- now implemented, with one caveat

**Status:** DONE for JWT login/signup (`app/security.py`,
`app/routers/auth.py`: `POST /auth/signup`, `POST /auth/login`,
`GET /auth/me`), fully free/local (`bcrypt` for password hashing,
`pyjwt` for tokens, no external auth provider). Not a blocker anymore,
but one thing to flag:

- Password hashing deliberately does **NOT** use `passlib` even though
  that's the more commonly-recommended library -- passlib 1.7.4 (its
  last release; the project is effectively unmaintained) throws
  `AttributeError: module 'bcrypt' has no attribute '__about__'` against
  `bcrypt>=4.1` because it probes a now-removed attribute to detect the
  backend version. This broke immediately against the `bcrypt` 5.0.0
  wheel that installs for Python 3.14 in this environment. Worked
  around by calling the `bcrypt` package directly (`app/security.py`) --
  a well-known community workaround, not a hack specific to this repo.
- `/permits`, `/properties`, `/export`, `/ingest/run` intentionally
  remain **unauthenticated** -- the core product surface is public
  government permit data, and requiring login there would be a product
  decision, not a technical one. Auth is enforced on the
  account-scoped features added this pass: saved searches, alerts, and
  billing.
- Not yet built: `ApiKey`-based (as opposed to JWT-based) request auth
  for machine-to-machine access, and role/permission checks beyond
  "belongs to this organization" (e.g. admin-only endpoints). The
  `User.is_admin` column exists but nothing reads it yet.
- **To fully unblock:** add an API-key auth dependency alongside the
  JWT one (`ApiKey.key_hash` lookup, similar shape to
  `get_current_user`), and gate any future admin-only routes on
  `User.is_admin`.

## 8. Stripe billing -- scaffold written, genuinely never called Stripe

**Status:** `app/billing.py` and `app/routers/billing.py`
(`GET /billing/status`, `POST /billing/checkout-session`,
`POST /billing/webhook`) are written as if a Stripe **TEST-mode**
secret key were provided via `STRIPE_SECRET_KEY`, but no Stripe account
was created and no real or test key was ever used -- every billing
route was verified to degrade gracefully (503 with a clear message, or
`{"configured": false, ...}` on the status endpoint) with the env var
absent, which is the only way it's been exercised.

- Nothing here requires payment/billing infrastructure to run the rest
  of the app; `is_configured()` gates every Stripe call.
- **To unblock and actually test this:**
  1. Create a free Stripe account (https://dashboard.stripe.com/register)
     -- test mode requires no credit card or billing setup.
  2. Set `STRIPE_SECRET_KEY=sk_test_...` in the environment.
  3. Create a Product + Price in the Stripe test dashboard for each
     plan (`starter`/`pro`/`enterprise`) and set the matching
     `STRIPE_PRICE_STARTER` / `STRIPE_PRICE_PRO` / `STRIPE_PRICE_ENTERPRISE`
     env vars to those test-mode price IDs.
  4. For webhook testing locally: install the Stripe CLI (free) and run
     `stripe listen --forward-to localhost:8000/billing/webhook`, then
     set `STRIPE_WEBHOOK_SECRET` to the `whsec_...` value it prints.
  5. Only then will `checkout.session.completed` /
     `customer.subscription.updated` actually reach and update the
     `Subscription` table -- today that code path is written but
     unexercised against a real Stripe response.

## 9. Alert delivery (email/SMS) -- stubbed, no real provider

**Status:** `app/alerts/notifier.py` implements the full
create-saved-search -> create-alert -> run-alert pipeline
(`app/routers/saved_searches.py`, `app/routers/alerts.py`,
`app/alerts/service.py`) end-to-end and it's tested/working -- but the
actual "send" step (`StubEmailChannel`/`StubSMSChannel`) only logs and
writes an `AlertNotificationLog` row (`status="stubbed"`); nothing is
actually emailed or texted anywhere, by design (no paid/signup-gated
provider was integrated).

- `POST /alerts/{id}/run` is a manual trigger standing in for what a
  periodic Celery beat task would call automatically once a broker
  exists (see item 3) -- the matching/delivery logic itself doesn't
  change either way.
- **Free-tier options considered, and what happened when actually
  checked this pass:**
  - **SendGrid and Mailgun** -- both were specifically checked and
    **rejected**: as of this pass, both now require phone-number
    verification and/or a payment method on file even to activate
    their advertised free tier. Per this project's constraint against
    payment/phone-linked services, neither was signed up for. This is
    a deliberate "considered and rejected" decision, not an oversight.
  - **Resend** (3,000 emails/mo free, historically lower-friction
    signup), **Brevo/Sendinblue** (300 emails/day free), or **Amazon
    SES** (no permanent free tier but very cheap, ~$0.10/1,000) remain
    unverified-but-plausible alternatives -- not attempted this pass
    (time-boxed to the higher-priority jurisdiction/enrichment work),
    worth checking first since SendGrid/Mailgun's phone/payment gates
    may not apply to them.
  - **SMS**: Twilio (trial credit, then pay-per-message, no permanent
    free tier -- and Twilio also gates trial signup behind phone
    verification) was not attempted for the same reason. Routing SMS
    through email-to-SMS gateways remains a genuinely free (if
    unreliable/carrier-dependent) fallback path, not implemented.
- **To unblock:** pick a provider that doesn't require phone/payment
  verification for its free tier (check Resend/Brevo first), register
  for a free API key, and implement a new `NotificationChannel`
  subclass in `app/alerts/notifier.py` that calls the real API instead
  of just logging -- `_CHANNELS` in that file is the only place the
  swap needs to be registered; `app/alerts/service.py` and the alerts
  router don't need to change.

## 10. `python-socketio` / websockets, full-text search (e.g. Postgres
`tsvector` or Elasticsearch)

Not attempted -- current keyword search in `/permits` is a plain
`ILIKE` scan across description/address/permit_number/contractor,
which is fine at MVP/demo scale on SQLite but will need a real search
index (Postgres `tsvector` + GIN index, or an external search engine)
once permit volume grows past what `ILIKE` can serve quickly.
