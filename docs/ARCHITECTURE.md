# Architecture

This is a forward-looking design document for the target system. It
describes what construction-intel is meant to become, not what is currently
implemented - check `backend/`, `frontend/`, and each workstream's
`BLOCKERS.md` for actual current state. Treat this as the design the team is
building toward, and update it as real implementation decisions diverge from
it.

## 1. Why this design

The core constraint on this business is that construction-permit and
property data lives across an estimated ~20,100 US permit-issuing
jurisdictions (per the US Census Bureau's Building Permits Survey mailing
list), spread across a fragmented set of permitting-software vendors
(Accela, Tyler EnerGov/MyGov, OpenGov, Socrata, ArcGIS Hub, BS&A, and dozens
of smaller/regional systems - see `research/RESEARCH_REPORT.md` §1.2 for the
full vendor breakdown), each exposing data in its own shape, if at all.

A small engineering team cannot hand-write and hand-maintain thousands of
bespoke scrapers. The system is therefore designed around two ideas:

1. **A connector plug-in architecture** so that adding a new jurisdiction is
   a bounded, mostly-declarative task (a mapping config + a thin adapter),
   not a bespoke engineering project each time.
2. **An AI-driven ingestion pipeline** - an orchestrator that plans and
   schedules ingestion/enrichment work, and a fleet of independent AI
   workers that do the actual scraping, parsing, matching, and scoring -
   so that the *rate* at which new sources and new enrichment capabilities
   get added is bounded by orchestration/review capacity, not by
   engineer-hours writing one-off integration code.

## 2. Ingestion architecture: Fable orchestrator + Opus workers

### 2.1 Roles

**Orchestrator ("Fable")** - a long-running planning/supervisory process,
not itself doing scraping or parsing:

- Maintains the registry of known jurisdictions/connectors and their
  schedules (e.g., "poll Chicago's Socrata permit dataset every 6 hours,"
  "re-crawl this Accela ACA portal nightly").
- Decides *what* work needs to happen next: new-jurisdiction discovery runs
  (see §3.3), scheduled re-fetches of known sources, re-runs of enrichment
  jobs when a new enrichment provider/model version is added, and targeted
  backfills.
- Dispatches units of work to worker processes as discrete jobs with a
  clear input contract (e.g., "fetch permits from connector X updated since
  timestamp T") and an expected output contract (a batch of normalized
  records, or a structured failure/quality report).
- **Monitors quality**, not just completion: tracks per-connector success
  rate, schema-drift signals (e.g., a source's field names/shape changed
  and normalization confidence dropped), duplicate/conflict rates from
  entity resolution, and geocoding match-rate trends. Flags regressions for
  human review rather than silently degrading.
- Owns retry/backoff policy and dead-letter handling for jobs that keep
  failing (surfaced via CloudWatch alarms in production - see
  `infra/terraform/modules/cloudwatch`).

**Workers (Claude Opus-driven)** - stateless, independently-scaled processes
that each do one class of task and know nothing about the overall schedule:

- **Scraping / connector execution** - runs a specific connector's
  `fetch_permits()` (see `backend/app/connectors/base.py` for the current
  interface shape) against a live source and returns raw + provisionally
  normalized records.
- **Permit parsing** - for sources that return semi-structured text/PDF/HTML
  rather than clean JSON (common for Accela ACA and Tyler CSS portal
  scrapes), extracts structured fields (permit number, type, status, dates,
  valuation, description) from messy source material. This is the task
  class most likely to benefit from an LLM rather than brittle regex/XPath,
  since source markup varies per-jurisdiction and changes without notice.
- **Address normalization** - resolves a permit's raw address string into a
  canonical, parseable form (street number/direction/name/suffix/unit,
  city, state, ZIP+4) as a precursor to parcel/property matching.
- **Property enrichment** - attaches property-level attributes (lot
  size, year built, assessed value, prior permit history) from whatever
  property-data source is configured (see `research/RESEARCH_REPORT.md` for
  the vendor landscape - ATTOM, Regrid, county assessor open data, etc.).
- **Owner / entity resolution** - matches permit "owner"/"contractor"/
  "applicant" name strings to a canonical owner-entity record, including
  distinguishing individuals from LLCs/corporations, handling name
  variants, and linking an entity across multiple properties/permits it
  appears on.
- **Duplicate detection** - identifies when two records (possibly from two
  different source connectors, or a re-scrape of the same source) describe
  the same underlying permit or property, so they get merged/versioned
  rather than double-counted.
- **Geocoding** - resolves a normalized address to lat/lon and a parcel
  boundary where available, with a confidence score.
- **Scoring** - computes lead-quality / project-size / likelihood scores
  (feeding `backend/app/scoring/engine.py`) from the now-enriched record,
  for consumption by contractor/lender/investor-facing features.

Workers run **independently and in parallel** - there is no requirement that
scraping for jurisdiction A blocks scraping for jurisdiction B, or that
parsing finishes before geocoding starts for a different batch. The
orchestrator's job registry and the task queue (Redis/Celery locally; Redis
ElastiCache + optionally SQS in production - see
`infra/terraform/modules/redis` and `modules/sqs`) are what let many workers
run concurrently against different jobs without stepping on each other.

### 2.2 Why split orchestration from workers this way

- **Independent scaling**: a backlog of "new jurisdiction discovery" jobs
  shouldn't block or compete with time-sensitive "re-score permits after a
  data source updated" jobs - separate worker pools scale independently.
- **Safe rollout of new capability**: a new enrichment worker type (e.g., a
  new geocoding provider) can be introduced and run in shadow/comparison
  mode against a sample before the orchestrator starts routing production
  traffic to it, because workers only receive whatever job the orchestrator
  hands them - no worker has implicit assumptions about what upstream did.
- **Quality monitoring is centralized**: because every job result flows back
  through the orchestrator, it's the single place that can notice
  cross-cutting quality regressions (e.g., "geocoding confidence dropped
  10% starting this morning across all connectors" points at a shared
  dependency issue, not a single connector bug) - an individual worker
  can't see that pattern.
- **Human review stays cheap**: the orchestrator is the natural place to
  surface a review queue ("this connector's output confidence dropped -
  approve or pause") rather than requiring a human to watch every worker.

## 3. Connector plug-in architecture

### 3.1 Current interface (backend/app/connectors/)

The backend already establishes the core abstraction: `PermitConnector`
(`backend/app/connectors/base.py`) is an abstract base with exactly two
methods a new connector must implement:

- `discover() -> ConnectorInfo` - probe the source's metadata endpoint,
  return basic info (record count, field list) for sanity-checking a new
  jurisdiction config before a full ingest run.
- `fetch_permits(since, limit) -> Iterable[dict]` - fetch and yield
  normalized records matching the fixed `NORMALIZED_PERMIT_FIELDS` shape
  (permit_number, permit_type, status, dates, contractor/builder/architect,
  property_address, parcel_number, valuation, lat/lon, source, raw_data,
  etc.) so nothing downstream (routers, scoring, storage) needs to know
  which source system produced a given record.

Concrete connectors (`socrata.py`, `arcgis.py` today) hold whatever
source-specific config they need (a Socrata domain + dataset ID, an ArcGIS
FeatureServer URL) plus a **field-mapping config** translating that source's
native column names into `NORMALIZED_PERMIT_FIELDS`. `raw_data` always
retains the untouched source record, so re-normalization (e.g., after a
mapping-config fix) never requires re-fetching from the source.

### 3.2 Target state: adding a new jurisdiction with minimal engineering

The goal is that onboarding a new jurisdiction on an already-supported
source system (e.g., "another Socrata city") is close to **pure
configuration**, not new code:

- A jurisdiction registry entry: source system, connection details
  (domain/dataset ID or service URL), polling schedule, and a field-mapping
  config (source column name -> `NORMALIZED_PERMIT_FIELDS` key, plus any
  per-field transform like date-format parsing or unit conversion).
- Only genuinely new *source systems* (not just new cities on an existing
  system) require writing a new `PermitConnector` subclass - and even that
  is bounded work because the interface is intentionally narrow (two
  methods).
- For messy/unstructured sources (portal scrapes rather than clean open
  data APIs), the "permit parsing" worker type (§2.1) absorbs most of the
  per-jurisdiction variability by using an LLM to extract fields from
  whatever markup/text that jurisdiction's portal returns, rather than
  requiring a hand-written parser per portal quirk.
- New jurisdictions get **discovered**, not just manually added, via the
  pipeline in §3.3 - the orchestrator can propose new jurisdiction registry
  entries for human approval rather than requiring an engineer to notice a
  new city exists.

### 3.3 Discovering new jurisdictions/sources over time

Per `research/RESEARCH_REPORT.md` §1.3, several automatable discovery
signals feed the orchestrator's jurisdiction registry:

1. **Socrata Discovery/Catalog API** (`api.us.socrata.com/api/catalog/v1`) -
   queryable by keyword ("building permits," "construction permits," etc.)
   across all public Socrata portals; run on a recurring schedule to catch
   new portals and new datasets on existing portals.
2. **ArcGIS Hub search API** - similarly queryable by tag across all public
   ArcGIS Hub/Open Data sites, plus scheduled crawling of known
   `*.opendata.arcgis.com` / `*.hub.arcgis.com` subdomain patterns.
3. **URL-pattern enumeration** against known vendor hostnames (Accela,
   Tyler EnerGov, eTRAKiT, BS&A's own published municipal directory, MyGov,
   etc.) to find newly-onboarded agencies on already-integrated vendor
   platforms.
4. **State GIS/open-data clearinghouses** as secondary aggregators.
5. **data.gov federal catalog** as a supplementary discovery feed (staleness
   risk - treat as a lead to verify, not a primary source).
6. **Manual/analyst fallback** for the long tail of small towns and custom
   systems - this doesn't scale to full automation and should be budgeted
   as ongoing analyst/BD time.

Each discovered candidate becomes a proposed jurisdiction registry entry
that a human approves (checking, e.g., ToS/scraping-permissibility per
`research/BLOCKERS.md` §2-3) before the orchestrator starts scheduling real
ingestion jobs against it.

### 3.4 Adding a new enrichment provider

The same plug-in philosophy applies to enrichment (geocoding, property data,
owner-contact data, etc.): each enrichment capability is a narrow interface
(similar in spirit to `PermitConnector`) with one or more provider
implementations behind it (e.g., a `Geocoder` interface with USPS/Census/
paid-vendor implementations). Swapping or adding a provider means writing
one adapter against a narrow interface and registering it - the
orchestrator can then run it in shadow mode against a sample before cutting
production traffic over (§2.2), and can run multiple providers side by side
per record if cross-checking improves match confidence.

## 4. Data model: permits, properties, owners, scores - versioned, never overwritten

### 4.1 Core entities

- **Property** - a physical parcel/address, the stable anchor most other
  data hangs off of. Identified primarily by parcel number where available,
  with normalized address as a fallback/secondary key.
- **Permit** - a single permit record from a single source, at a point in
  time. Many permits reference one property over its lifetime.
- **Owner** (entity) - a resolved individual or organization, which may be
  linked to many properties (as owner, contractor, applicant, architect,
  engineer, etc. depending on role) and to permits directly.
- **Score** - a derived value (lead-quality, project-size estimate, etc.)
  computed from a permit+property+owner combination as of a point in time.

### 4.2 Versioning principle: append, don't overwrite

Every one of the above is treated as an **append-only history**, not a
row that gets mutated in place:

- When a source re-publishes a permit with an updated status (e.g.,
  "issued" -> "finaled"), the system inserts a **new version** of that
  permit record linked to the same logical permit identity, rather than
  updating the existing row. The prior version remains queryable.
- When entity resolution changes its mind about which canonical Owner a
  name string maps to (e.g., a later, higher-confidence match merges two
  previously-separate Owner records), that merge is itself a recorded
  event - both the old and new mapping are visible in history, not silently
  replaced.
- When a scoring model changes (new model version, new feature, or a
  reprocessing run), a new Score row is written with a version
  reference to the model/config that produced it - previous scores for the
  same permit/property remain visible rather than being overwritten. This
  is what lets the orchestrator's quality monitoring (§2.1) detect when a
  new scoring version changed outcomes and by how much, and what lets any
  future retraining/backtesting compare model versions against each other.
- Raw source payloads (`raw_data` on permits, and equivalent for other
  enrichment inputs) are always retained alongside the normalized fields,
  so re-normalization after a mapping/parsing-logic fix never requires
  re-fetching from the original source.

### 4.3 Why this matters for this business specifically

- **Trust/auditability**: customers (especially lenders/insurers) need to
  be able to answer "what did we know about this property, and when" -
  overwriting history makes that unanswerable.
- **Duplicate/entity-resolution correction is expected, not exceptional**:
  because entity resolution and duplicate detection are AI-driven and
  running continuously (§2.1), the system *will* revise its own past
  conclusions as it sees more data or as models improve. An append-only
  model treats that as normal, recorded revision rather than data
  corruption.
- **Reprocessing is cheap**: because raw inputs are retained and outputs are
  versioned rather than mutated, backfilling with an improved connector,
  parser, or scoring model is a matter of running a new version through the
  pipeline and writing new versioned outputs - old outputs remain
  available for comparison/rollback, and nothing has to be "undone" first.

## 5. Where this document intentionally stops

This is a target-design document, not an implementation plan or a sprint
backlog. It deliberately does not commit to specific ORM schemas, specific
LLM prompts, specific queue message formats, or specific provider contracts
- those are implementation decisions for the backend/infra workstreams to
make (and revise) as they build, informed by this design's shape and by
`research/RESEARCH_REPORT.md`'s vendor/legal findings. Update this document
when a real implementation decision meaningfully diverges from what's
described here, so it stays a useful map rather than aspirational fiction.
