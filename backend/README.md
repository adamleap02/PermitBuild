# Construction Intel -- Backend

FastAPI backend for a database of US residential/commercial construction
permits, enriched with property data. Runs entirely locally and for free:
SQLite by default, no API keys required for the great majority of live
data sources used out of the box (a few enrichment features are richer
with one free Census API key -- see below), no paid billing/email/SMS
infra required to run.

Tested against **Python 3.14.3** on Windows.

## Setup

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### Optional: `.env` file

Copy `.env.example` to `.env` (gitignored) to set optional local
secrets -- everything in this repo runs without it, but a few things
unlock with it:

```bash
cp .env.example .env
```

- `CENSUS_API_KEY` -- free (https://api.census.gov/data/key_signup.html),
  unlocks real ACS demographic enrichment (median income/home value/
  population). Without it, Property enrichment still records the
  Census tract GEOID and FEMA flood zone (both fully keyless), just not
  the ACS numbers.
- `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` -- free Stripe TEST-mode
  keys, unlock the billing routes actually talking to Stripe. See
  `BLOCKERS.md` §8.
- `JWT_SECRET_KEY` -- set this for anything beyond a single local dev
  process (auto-generates a random one otherwise, with a warning).

## Run database migrations

Creates `backend/data/local.db` (SQLite) and applies the full schema:

```bash
alembic upgrade head
```

To point at Postgres later instead, set `DATABASE_URL` before running
migrations/the app -- no code changes needed:

```bash
export DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/construction_intel"
alembic upgrade head
```

## Ingest real, live demo data

**62 real, live-verified permit sources** are wired up out of the box
(no API key required for any of them), spanning **34 states/
territories** (genuine Northeast/Midwest/Southeast/Mountain West/
Pacific NW spread, not clustered), including 19 counties/parishes and
one statewide feed:

| key | jurisdiction | level | source system |
|---|---|---|---|
| `sf` | San Francisco, CA | city | Socrata |
| `chicago` | Chicago, IL | city | Socrata |
| `austin` | Austin, TX | city | Socrata |
| `seattle` | Seattle, WA | city | Socrata |
| `dallas` | Dallas, TX | city | Socrata |
| `nyc` | New York City, NY | city | Socrata |
| `tempe` | Tempe, AZ | city | ArcGIS |
| `denver` | Denver, CO | city | ArcGIS |
| `raleigh` | Raleigh, NC | city | ArcGIS |
| `dc` | Washington, DC | city | ArcGIS |
| `sonoma` | Sonoma County, CA | **county** | Socrata |
| `marin` | Marin County, CA | **county** | Socrata |
| `howard` | Howard County, MD | **county** | Socrata |
| `batonrouge` | East Baton Rouge Parish, LA | **county** | Socrata |
| `mesa` | Mesa, AZ | city | Socrata |
| `cincinnati` | Cincinnati, OH | city | Socrata |
| `gainesville` | Gainesville, FL | city | Socrata |
| `cook` | Cook County, IL | **county** | Socrata |
| `cambridge` | Cambridge, MA | city | Socrata |
| `framingham` | Framingham, MA | city | Socrata |
| `sandiego` | San Diego County, CA | **county** | Socrata |
| `nj` | New Jersey | **statewide** | Socrata |
| `neworleans` | New Orleans, LA | city | Socrata |
| `miamidade` | Miami-Dade County, FL | **county** | ArcGIS |
| `mecklenburg` | Mecklenburg County, NC (Charlotte) | **county** | ArcGIS |
| `annearundel` | Anne Arundel County, MD | **county** | **HTML scraper** |
| `minneapolis` | Minneapolis, MN | city | ArcGIS |
| `philadelphia` | Philadelphia, PA | city | ArcGIS |
| `honolulu` | Honolulu, HI | city | Socrata |
| `norfolk` | Norfolk, VA | city | Socrata |
| `kansascity` | Kansas City, MO | city | Socrata |
| `siouxfalls` | Sioux Falls, SD | city | ArcGIS |
| `montgomerycountymd` | Montgomery County, MD | **county** | Socrata |
| `nashville` | Nashville, TN | city | ArcGIS |
| `boise` | Boise, ID | city | ArcGIS |
| `atlanta` | Atlanta, GA | city | ArcGIS |
| `albuquerque` | Albuquerque, NM | city | ArcGIS |
| `portland` | Portland, OR | city | ArcGIS |
| `helena` | Helena, MT | city | ArcGIS |
| `tampa` | Tampa, FL | city | **HTML scraper** |
| `clarkcounty` | Clark County, NV (Las Vegas) | **county** | **HTML scraper** |
| `kingcounty` | King County, WA | **county** | **HTML scraper** |
| `fortworth` | Fort Worth, TX | city | ArcGIS |
| `columbus` | Columbus, OH | city | ArcGIS |
| `lasvegas` | Las Vegas, NV (city) | city | ArcGIS |
| `detroit` | Detroit, MI | city | ArcGIS |
| `louisville` | Louisville Metro, KY | **county** | ArcGIS |
| `tucson` | Tucson, AZ | city | ArcGIS |
| `sanantonio` | San Antonio, TX | city | **CKAN** |
| `milwaukee` | Milwaukee, WI | city | **HTML scraper** |
| `hartford` | Hartford, CT | city | **HTML scraper** |
| `oakland` | Oakland, CA | city | **HTML scraper** |
| `santabarbara` | Santa Barbara County, CA | **county** | **HTML scraper** |
| `polkcounty` | Polk County, FL | **county** | **HTML scraper** |
| `leecounty` | Lee County, FL | **county** | **HTML scraper** |
| `indianapolis` | Indianapolis, IN | city | **HTML scraper** |
| `charleston` | Charleston, SC | city | ArcGIS |
| `boston` | Boston, MA | city | **CKAN** |
| `orlando` | Orlando, FL | city | Socrata |
| `princegeorges` | Prince George's County, MD | **county** | Socrata |
| `somerville` | Somerville, MA | city | Socrata |
| `charlottecounty` | Charlotte County, FL | **county** | **HTML scraper** |

Exact dataset/layer URLs, and what was tried-and-skipped (LA's 403,
several aggregated-only ArcGIS feeds, Philadelphia's shifting ArcGIS
layer ID, Fulton County/Houston/Commerce City leads, etc.), are in
`BLOCKERS.md` §5.

Run the demo ingest script (creates the jurisdiction row if it doesn't
exist yet, pulls real permits over HTTPS, upserts them, writes
`PermitVersion` history, computes explainable scores, and runs free
property/parcel enrichment -- see below):

```bash
python scripts/run_ingest.py --jurisdiction sf --limit 25
python scripts/run_ingest.py --jurisdiction annearundel --limit 10
python scripts/run_ingest.py --all --limit 60   # ingest every demo jurisdiction in one run
```

Re-running the same command is safe/idempotent -- unchanged permits are
skipped, changed ones get a new `PermitVersion` row (old data is never
overwritten in place).

### Scaling up to real production volume

`--limit` caps records per source. Flags added for large real-world pulls:

```bash
# Pull the WHOLE feed for one source (0 or any value <= 0 means "no cap"):
python scripts/run_ingest.py --jurisdiction orlando --limit 0
# Fast bulk pull: skip per-address geocoding + per-property enrichment +
# scoring (recommended above a few thousand records so you don't hammer the
# free Census/FEMA services; backfill later with backfill_enrichment.py):
python scripts/run_ingest.py --jurisdiction boston --limit 100000 --no-geocode --no-enrich --no-score
# "Evergreen" incremental refresh -- only records dated in the last N days:
python scripts/run_ingest.py --all --since-days 60
```

The connectors page efficiently for volume: Socrata pulls up to 50,000
rows/request, CKAN 10,000/request, and ArcGIS pages on `resultOffset`
terminating on the server's own `exceededTransferLimit` flag (so it walks
a whole layer even when the FeatureServer caps each response at its
`maxRecordCount`). All three back off (respecting `Retry-After`) on HTTP
429/5xx rather than hammering the free public services.

`scripts/scale_ingest.py` runs a curated, prioritized bulk plan in one
process (highest-record-count jurisdictions first -- Orlando, Fort Worth,
Columbus, Boston, Prince George's County, Las Vegas -- with per-source
caps, geocoding/enrichment/scoring off for speed, and single-page HTML
scrapers skipped):

```bash
python scripts/scale_ingest.py
```

### Real HTML scraping: 12 Accela Citizen Access agencies (no open-data API)

`annearundel`, `tampa`, `clarkcounty`, `kingcounty`, `milwaukee`,
`hartford`, `oakland`, `santabarbara`, `polkcounty`, `leecounty`,
`indianapolis`, and `charlottecounty` don't run through Socrata/ArcGIS --
they're real scraping (`app/connectors/html_scraper.py`, a generic
`AccelaCitizenAccessConnector`) against twelve different agencies' public
Accela Citizen Access permit search
(the most common "no open API" permit vendor nationally). It handles a
real ASP.NET WebForms `__doPostBack` search submission and Accela's
Referer/Origin CSRF check -- genuine scraping, not a simple GET -- and
parses each agency's results-grid header row dynamically at request
time, since the agencies checked each expose a genuinely different
column layout. Per-agency the only variable is the module name
(`Building`/`Permits`/`Permitting`), discovered live from each agency's
own home-page navigation. See `BLOCKERS.md` §5c/§5f/§5g for the
robots.txt check, legal reasoning, and rate-limiting approach (max 3
requests per run per agency, 1.5s delay between each, single page of
results only).

## FOIA / public-records email intake (received data, not scraped/pulled)

Some jurisdictions have **no** open-data API and no scrapable portal, so
the only way to get bulk permit data is a formal public-records / FOIA
request (see `BLOCKERS.md` §5d). Six such requests were filed
(LA County CA, Huntington WV, Pine Bluff AR, Bangor ME, Danville IL by
email; Rexburg ID by web form). Replies arrive over days/weeks as
CSV/XLSX/PDF attachments in wildly inconsistent per-agency formats.

`app/foia_intake/` is a real, working pipeline that turns those replies
into permit records, following the same `PermitConnector` conventions as
the API connectors but for *pushed* (received) data:

- **`gmail_client.py`** — read-only Gmail API wrapper using the saved
  OAuth token (`gmail_token.json`, `gmail.readonly` scope). Lists replies
  from the known FOIA senders, fetches messages, downloads attachments.
- **`parser.py`** — a **heuristic field-mapper**. Since column names are
  unpredictable per agency, it maps observed headers onto our canonical
  fields (`permit_number`, `property_address`, `estimated_cost`,
  `issue_date`, …) by fuzzy, case-insensitive keyword matching
  ("longest matching keyword wins"). Handles CSV (delimiter-sniffed),
  XLSX (openpyxl), and PDF tables (pdfplumber). **Every original column
  is preserved in `raw_data`** — nothing unmapped is discarded. PDF
  extraction is best-effort: a PDF with no clean table structure fails
  gracefully (flagged for manual review) rather than guessing at garbage.
- **`targets.py`** — the 6 target agencies and the `Jurisdiction` each
  maps to. Sender→target resolution matches the exact recipient address,
  then falls back to the agency email domain (records officers often
  reply from a personal named mailbox on the same domain).
- **`intake.py`** — orchestration. Ingests every parsed record through
  the **same** `upsert_permit` + `PermitVersion` history path every
  connector uses (`app/ingest.py`) — not a parallel path. Records are
  ingested under a `SourceSystem.FOIA_EMAIL` jurisdiction and flagged
  **`needs_review=True`** (a new `Permit` column) so heuristically-parsed
  data never silently masquerades as high-confidence API data.

**Idempotency**: every processed `(Gmail message id, attachment id)` is
recorded in the `processed_email_attachments` table, so re-running the
poll never re-downloads or re-ingests the same attachment.

### Run the poller manually

```bash
venv\Scripts\python.exe scripts\poll_foia_replies.py            # normal run
venv\Scripts\python.exe scripts\poll_foia_replies.py -v          # verbose
venv\Scripts\python.exe scripts\poll_foia_replies.py --no-enrich --no-geocode
```

Safe to run repeatedly. Exits 0 whether or not any reply had arrived;
exit 2 signals a hard failure (e.g. missing/invalid Gmail token — re-run
`scripts\gmail_oauth_setup.py`, which needs a human to click through the
browser consent screen once).

### Scheduling: Windows Task Scheduler (no broker needed)

There's no Celery/Redis broker running here (`BLOCKERS.md` §3), and this
must run independently of any Claude session, so scheduling is done with
Windows Task Scheduler running `scripts\run_foia_poll.cmd` (a wrapper
that `cd`s into `backend`, runs the poller, and appends to
`backend\logs\foia_poll.log`) every 6 hours. The task
**`ConstructionIntel-FOIA-Poll`** is already registered on this machine.

Recreate it (exact command used):

```powershell
schtasks /create /tn "ConstructionIntel-FOIA-Poll" ^
  /tr "C:\Users\schar\construction-intel\backend\scripts\run_foia_poll.cmd" ^
  /sc HOURLY /mo 6 /st 00:00 /f
```

Inspect / run-now / remove it:

```powershell
schtasks /query  /tn "ConstructionIntel-FOIA-Poll" /v /fo LIST   # status, next run
schtasks /run    /tn "ConstructionIntel-FOIA-Poll"               # trigger immediately
schtasks /delete /tn "ConstructionIntel-FOIA-Poll" /f            # stop/remove it
```

### Scheduling: daily "evergreen" full ingest (Windows Task Scheduler)

Per the product spec, the platform runs a full ingestion pass **once per
day** to discover new permits, detect modified permits (writing a new
immutable `PermitVersion` -- never overwriting data), and detect completed
projects. Like the FOIA poll (and for the same reason -- no Celery/Redis
broker here, and it must run independently of any Claude session), this is
a Windows Task Scheduler job running `scripts\run_daily_ingest.cmd` (a
wrapper that `cd`s into `backend`, runs
`run_ingest.py --all --since-days 60`, and appends to
`backend\logs\daily_ingest.log`). It uses a rolling 60-day incremental
window so the daily run stays bounded and polite to the free public APIs
(Socrata/ArcGIS filter server-side on their date field; other sources
re-scan and rely on idempotent upserts). The task
**`ConstructionIntel-Daily-Ingest`** is registered on this machine and runs
daily at 02:30. **It is a real, indefinite background task distinct from
the FOIA poll task.**

Recreate it (exact command used):

```powershell
schtasks /create /tn "ConstructionIntel-Daily-Ingest" ^
  /tr "C:\Users\schar\construction-intel\backend\scripts\run_daily_ingest.cmd" ^
  /sc DAILY /st 02:30 /f
```

Inspect / run-now / remove it:

```powershell
schtasks /query  /tn "ConstructionIntel-Daily-Ingest" /v /fo LIST  # status, next run
schtasks /run    /tn "ConstructionIntel-Daily-Ingest"              # trigger immediately
schtasks /delete /tn "ConstructionIntel-Daily-Ingest" /f           # stop/remove it
```

### What happens the moment a real reply arrives

1. Within ≤6 hours the scheduled task runs `poll_foia_replies.py`.
2. The Gmail search `from:(<the 5 addresses>) -in:sent` now returns the
   reply. `find_target_for_sender` maps its From address (exact or by
   domain) to the right FOIA target, and the `Jurisdiction` is
   get-or-created with `source_system=FOIA_EMAIL`.
3. Each new attachment is downloaded, its `(message id, attachment id)`
   checked against `processed_email_attachments` (skipped if already
   seen), then parsed. Headers are mapped heuristically; unmapped columns
   are preserved in `raw_data`.
4. Each record is upserted through the normal `upsert_permit` path — a
   new `Permit` (or a new `PermitVersion` if it changed), addresses
   geocoded and properties enriched exactly like any connector — with
   `needs_review=True`. Scores are computed for touched permits.
5. The attachment is recorded in `processed_email_attachments` with its
   outcome + counts. A PDF with no extractable table is recorded
   `status="unparseable"` for a human to review, not ingested as noise.
6. Everything is logged to `backend\logs\foia_poll.log`. The next run is
   a no-op for that attachment (idempotent).

**Limitations** (by design): PDF table extraction is best-effort; legacy
binary `.xls` is unsupported (only `.xlsx`); the heuristic mapper can
mis-guess an oddly-named column — which is exactly why `needs_review`
exists and the full `raw_data` is retained so any record can be
re-mapped later. Filter these out of high-trust views with
`needs_review = false`.

## Free property/parcel enrichment

Every ingest run automatically enriches each Property (idempotent --
skips sources already recorded, so re-ingesting doesn't re-hit external
APIs):

- **FEMA flood zone** (`app/enrichment/fema_flood.py`) -- free, keyless,
  live today. Point-in-polygon query against FEMA's National Flood
  Hazard Layer.
- **Census tract + ACS demographics** (`app/enrichment/census_acs.py`)
  -- tract lookup is free/keyless; median income/home value/population
  requires a free `CENSUS_API_KEY` (see `.env` section above) since the
  Census Data API now requires one for every request (a change from
  historically-keyless access -- see `BLOCKERS.md` §6).
- **Cook County Assessor** (`app/enrichment/cook_county_assessor.py`)
  -- free, keyless, real assessor data (year built, building/lot sqft,
  bed/bath count, assessed value) keyed by PIN, populated automatically
  for Cook County permits (and anything else with a Cook-shaped 14-digit
  parcel number).

To backfill enrichment for properties ingested before this existed (or
to force a refresh):

```bash
python scripts/backfill_enrichment.py                # only un-enriched properties
python scripts/backfill_enrichment.py --force         # re-enrich everything
python scripts/backfill_enrichment.py --limit 50      # cap how many to process
```

## Run the API

```bash
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000/docs for interactive OpenAPI docs, or:

**Public data endpoints** (no auth required):
- `GET /permits?jurisdiction_id=1&keyword=remodel&min_value=10000` -- search/filter/paginate
- `GET /permits/{id}` -- detail + full version history + latest score
- `GET /properties/{id}` -- property detail (incl. enrichment JSON: flood zone, census tract/ACS, assessor data)
- `GET /export?jurisdiction_id=1` -- CSV export of filtered permits
- `POST /ingest/run` -- `{"jurisdiction_id": 1, "limit": 50}` triggers a live connector run (+ enrichment)
- `GET /jurisdictions`, `POST /jurisdictions` -- manage jurisdiction/connector configs

**Auth** (JWT, fully local/free -- `bcrypt` + `pyjwt`, no external provider):
- `POST /auth/signup` -- `{"email", "password", "organization_name", "full_name"?}` -> creates an Organization + User, returns a JWT
- `POST /auth/login` -- `{"email", "password"}` -> JWT
- `GET /auth/me` -- current user (send `Authorization: Bearer <token>`)

**Billing** (Stripe TEST-mode scaffold -- degrades gracefully with no key set):
- `GET /billing/status` -- current org's subscription status; returns `{"configured": false, ...}` when `STRIPE_SECRET_KEY` isn't set (the default here)
- `POST /billing/checkout-session` -- creates a Stripe Checkout session; returns 503 with a clear message if billing isn't configured
- `POST /billing/webhook` -- Stripe webhook receiver (signature-verified); updates the `Subscription` table
- See `BLOCKERS.md` §8 for how to turn this on with a free Stripe test account.

**Saved searches + alerts** (auth required):
- `POST/GET /saved-searches`, `GET/DELETE /saved-searches/{id}` -- save a reusable `/permits` filter set
- `POST/GET /alerts`, `DELETE /alerts/{id}` -- subscribe a saved search to email/SMS notification (both channels **stubbed** -- see below)
- `POST /alerts/{id}/run` -- manually run one alert's match+notify cycle (stand-in for the Celery beat schedule that would otherwise call this automatically once a broker exists)

Alert delivery is intentionally stubbed: `POST /alerts/{id}/run` finds
real matching permits and writes an `AlertNotificationLog` row
recording exactly what *would* have been emailed/texted and to whom --
nothing is actually sent externally. See `BLOCKERS.md` §9 for free-tier
email/SMS providers considered (SendGrid/Mailgun were checked and
rejected -- both now require phone/payment verification even for free
tiers).

## Run the tests

```bash
pytest
```

This runs **153 tests** including model tests, the address normalizer,
the ingest version-numbering regression tests (`tests/test_ingest.py` --
a repeated `permit_number` within one batch must not collide on the
`permit_versions` UNIQUE constraint; see `BLOCKERS.md` §5i) and the
non-unique-permit-number disambiguation tests (SF/Marin/Cincinnati/Howard/
Fort Worth),
the FOIA email-intake pipeline (heuristic field-mapping across varied CSV/
XLSX column names, sender→target resolution, and end-to-end intake +
idempotency against a mocked Gmail API),
the scoring engine, connector field-mapping logic across dozens of
cities/counties (against realistic sample records, no network) --
including regression tests for the CKAN connector (San Antonio's mixed
WGS84/State-Plane coordinates and non-unique permit numbers; Boston's
`$`-formatted declared-valuation parsed as the value, not the fee) and the
fee-vs-valuation mappings on the new ArcGIS/Socrata sources (Detroit,
Louisville, Charleston SC, and Somerville MA -- whose `amount` column is a
permit fee that is deliberately NOT mapped as a valuation)
-- the HTML scraper's header-parsing/payload-building logic, enrichment
module logic, auth, billing (not-configured degrade-gracefully paths),
saved searches + alerts, the rest of the API routes (SQLite, isolated
per-test DB), and several `@pytest.mark.integration` tests that hit
real, live, free APIs (Census geocoder + tract lookup, FEMA flood zone,
Cook County Assessor, and 4 Accela scraper agencies). To skip the
live integration tests (e.g. offline / CI without egress):

```bash
pytest -m "not integration"
```

## Project layout

```
app/
  main.py             FastAPI app, CORS, router mounting
  db.py               SQLAlchemy engine/session (SQLite by default, DATABASE_URL for Postgres later);
                       also loads backend/.env via python-dotenv at import time
  models.py           Jurisdiction, Permit (+needs_review), PermitVersion, Property, Owner, Score,
                       Organization/User/ApiKey, Subscription, SavedSearch/Alert/AlertNotificationLog,
                       ProcessedEmailAttachment (FOIA intake idempotency ledger)
  schemas.py          Pydantic request/response models
  ingest.py           Upsert + append-only version-history logic + enrichment hook
  security.py         Password hashing (bcrypt) + JWT issuance/verification
  billing.py          Stripe TEST-mode client wrapper, no-op/graceful when STRIPE_SECRET_KEY unset
  tasks.py            Celery task wrappers around ingest (untested -- no local Redis; see BLOCKERS.md)
  connectors/
    base.py            Abstract PermitConnector interface
    socrata.py          Generic Socrata (SODA API) connector + 26 jurisdiction mapping configs
    arcgis.py           Generic ArcGIS FeatureServer connector + 22 jurisdiction mapping configs
    ckan.py             Generic CKAN DataStore connector + 2 jurisdiction mapping configs (San Antonio, Boston)
    html_scraper.py      Generic Accela Citizen Access connector + 12 real agency configs
    normalizer.py       USPS-style address standardization (regex/rules, not USPS API)
    geocoder.py         US Census Bureau free geocoder client
  foia_intake/
    targets.py           The 6 FOIA target agencies + the Jurisdiction each maps to
    gmail_client.py      Read-only Gmail API wrapper (saved OAuth token)
    parser.py            Heuristic field-mapper: CSV/XLSX/PDF/body -> normalized permit dicts
    intake.py            Poll -> parse -> upsert (same ingest path) + idempotency ledger
  enrichment/
    census_acs.py        Census tract lookup (free) + ACS demographics (needs free CENSUS_API_KEY)
    fema_flood.py         FEMA NFHL flood zone lookup (free, keyless)
    cook_county_assessor.py  Cook County Assessor parcel data by PIN (free, keyless)
    service.py            Orchestrates all of the above onto a Property, idempotently
  scoring/
    engine.py           Rules-based, fully explainable scoring functions
    service.py          Persists scoring engine output as Score rows
  alerts/
    notifier.py          Stubbed email/SMS delivery + AlertNotificationLog audit trail
    service.py            Runs a single Alert's match+notify cycle
  routers/
    permits.py, properties.py, export.py, ingest.py, jurisdictions.py,
    auth.py, billing.py, saved_searches.py, alerts.py
alembic/                Migrations (initial schema, then billing/alerts tables)
scripts/
  run_ingest.py          Runnable live-ingest demo, supports --all and 62 jurisdiction keys
  backfill_enrichment.py Backfills enrichment for properties ingested before it existed
  poll_foia_replies.py   FOIA email-intake entry point (run by Windows Task Scheduler every 6h)
  run_foia_poll.cmd      Task Scheduler wrapper (cd + run + append to logs/foia_poll.log)
  gmail_oauth_setup.py   One-time Gmail OAuth consent (creates gmail_token.json)
tests/                   pytest suite (see above)
research/RESEARCH_REPORT.md  Market/legal/vendor research that guided jurisdiction selection
BLOCKERS.md              What's not free/local-only yet, and how to unblock it -- read this
```

## Troubleshooting: `scripts/run_ingest.py --all` and concurrent processes

If you run `--all` more than once in close succession (e.g. from two
terminals, or a backgrounded run that's still finishing when you start
another), you may see occasional
`sqlite3.IntegrityError: UNIQUE constraint failed: permit_versions...`
in the log for a handful of records -- this happens when two processes
race to write the next `PermitVersion` for the same permit. As of this
pass, `app/ingest.py`'s per-record error handling calls `db.rollback()`
on any such failure, so this is now a **contained, logged, per-record
error** (counted in that jurisdiction's `Errors=` count) rather than a
cascading failure that silently corrupts the rest of the run -- but the
underlying advice is still: avoid running `--all` concurrently against
the same `local.db` file. A single `run_ingest.py --jurisdiction <key>`
call is unaffected either way.

## What's a scaffold vs. fully wired up

- JWT auth is fully wired up (`/auth/signup`, `/auth/login`, `/auth/me`)
  and enforced on saved searches/alerts/billing; the core `/permits`
  etc. data endpoints stay public by design (see `BLOCKERS.md` §7 for the
  one remaining gap: no API-key-based, as opposed to JWT-based, auth
  path yet).
- Stripe billing routes are fully written and exercised in their
  not-configured/graceful-degradation form; never actually called
  Stripe (no account/key used) -- see `BLOCKERS.md` §8 for how to turn it
  on with a free Stripe test account.
- Saved searches + alerts are fully working end-to-end including a
  persisted delivery audit log; the actual email/SMS "send" step is
  stubbed (logs + records only) -- see `BLOCKERS.md` §9 for free-tier
  providers considered.
- Celery/Redis background ingest scheduling is written but untested
  without a broker -- see `BLOCKERS.md` §3. The synchronous path
  (`scripts/run_ingest.py`, `POST /ingest/run`, `POST /alerts/{id}/run`)
  is fully working today.
- **FOIA email intake is fully wired up and running**: `app/foia_intake/`
  polls Gmail live (read connection verified end-to-end), parses
  attachments, and ingests through the normal upsert/version path with
  `needs_review=True`. Scheduled on this machine via Windows Task
  Scheduler (`ConstructionIntel-FOIA-Poll`, every 6h) rather than Celery,
  since no broker is available. See the "FOIA / public-records email
  intake" section above and `BLOCKERS.md` §5d.
- PostGIS spatial queries are not implemented; lat/lon are plain floats
  today with a documented upgrade path -- see `BLOCKERS.md` §1.
- Property/parcel enrichment: FEMA flood zone and Census tract lookup
  work with zero configuration; ACS demographics need a free
  `CENSUS_API_KEY`; Cook County Assessor data is real and free but only
  wired for one county so far -- see `BLOCKERS.md` §6.
- **Read `BLOCKERS.md` §6a before trusting the `CENSUS_API_KEY` checked
  into local `.env`** -- it documents exactly how that key's provenance
  was verified (independently, not just trusted) given it arrived via
  an unusual mid-task instruction.
- **Read `BLOCKERS.md` §0** for an unrelated but important flag: evidence
  of unattended browser-automation account-signup activity found in this
  repo (`.playwright-signup-evidence/`), not part of this codebase's own
  work.

## Current live dataset snapshot

As of the last full `--all` run: **62 jurisdictions**, **~5,930 real
permits**, **~2,780 properties**, **~482 owners**, spanning **34 US
states/territories** (added **SC** this pass, via Charleston). Re-run
`scripts/run_ingest.py --all --limit 60` at any time to refresh/grow
this -- it's fully idempotent (the ArcGIS timezone-diff idempotency bug
that used to inflate version history on every re-run was fixed in a prior
pass -- see `BLOCKERS.md` §5g). The per-jurisdiction record counts in
the demo DB are capped by `--limit`; the underlying sources are far
larger (Fort Worth alone exposes 756k+ live records; Orlando 1.1M+,
Boston 657k+, Prince George's County 461k+).

Note: a full `--all` run may report a couple of jurisdictions with a
handful of `permit_versions` UNIQUE-constraint errors (or, for two, a
whole-jurisdiction `FAILED`) -- this is the pre-existing version-numbering
edge documented in `BLOCKERS.md` §5i, affecting a few older jurisdictions
(SF, Cincinnati, Howard, Marin, Minneapolis, Nashville, Fort Worth), not
the sources added this pass (which ingest cleanly, Errors=0). No data is
corrupted -- affected jurisdictions retain their prior-run data.
