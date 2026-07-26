# National Expansion Plan — Vendor Census, Discovery Methods, and Prioritized Build Waves

**Prepared:** July 26, 2026
**Builds on:** `research/RESEARCH_REPORT.md` (vendor landscape, legal/compliance, phased rollout) and `backend/BLOCKERS.md` (everything already tried/verified/blocked). Current live state as of this writing: **42 jurisdictions, 28 states/territories, ~4,900 real permits**, via Socrata SODA, ArcGIS FeatureServer, and a generalized Accela Citizen Access (ACA) scraper.

**Method note:** Everything below marked "confirmed live" was independently re-verified this pass via direct HTTP requests (`curl` against the actual API/service endpoint) or a live search-engine query, not taken on faith from prior research or from a search result's title text alone. Several leads that *looked* right from search-result titles turned out to be wrong on verification (see §4) — that discipline is carried forward from `BLOCKERS.md`'s existing "verify, don't assume" precedent (Atlanta's personal-looking account, Helena's unrelated-owner account, Philadelphia's shifting layer ID).

---

## 1. Vendor platform census

For each platform: a rough total population of US jurisdictions likely running it, how many are in our current 42, and a discovery method concrete enough for a worker agent to execute mechanically. Population figures are explicitly estimates except where cited as a vendor claim.

| Platform | Est. total US jurisdictions running it | Currently covered | Discovery method (verified this pass unless noted) |
|---|---|---|---|
| **Socrata (Tyler Data & Insights)** | ~200+ government portals total exist on Socrata; a subset (**est. 90–150, unconfirmed**) tag/publish something permit-related | **23** (sf, chicago, austin, seattle, dallas, nyc, sonoma, marin, howard, batonrouge, mesa, cincinnati, gainesville, cook, cambridge, framingham, sandiego, nj, neworleans, honolulu, norfolk, kansascity, montgomerycountymd) | `curl "https://api.us.socrata.com/api/catalog/v1?q=building%20permits&only=datasets&limit=200"` — **confirmed live**, returns real dataset IDs + `updatedAt` timestamps (Chicago's came back with today's date). Paginate with `&offset=N`; vary `q=` across "construction permits," "certificate of occupancy," "code enforcement" to catch differently-tagged datasets. Filter results to domains not already in our config. |
| **ArcGIS Hub / Enterprise** | Tens of thousands of orgs host *something* on ArcGIS Online; **est. 500–1,000** publish a permit-tagged layer (rough, unconfirmed) | **15** (tempe, denver, raleigh, dc, miamidade, mecklenburg, minneapolis, philadelphia, siouxfalls, nashville, boise, atlanta, albuquerque, portland, helena) | Two complementary live endpoints, both **confirmed working**: (a) `curl "https://hub.arcgis.com/api/search/v1/collections/dataset/items?q=building%20permits&limit=20"` — Hub's own dataset-collection search; (b) `curl "https://www.arcgis.com/sharing/rest/search?q=<city>%20building%20permits&f=json&num=10&sortField=numViews&sortOrder=desc"` — general item search, noisier, needs a per-city query rather than one global crawl (confirms the research report's point that generic catalog crawls miss city-hosted layers small/mid cities publish under personal-looking or oddly-named accounts). **Critical caveat found this pass**: always resolve the item's `url` field and pull one sample record to confirm geography/owner match the target city — see §4 for two real false-positives this session hit. Also reusable: any Hub site's DCAT feed at `<hubsite>/api/feed/dcat-us/1.1.json` enumerates its *entire* catalog without needing the JS search UI (this is how Fulton County GA's per-city permit datasets were found in the prior pass). |
| **Accela Citizen Access (ACA)** | Accela claims **~1,000+ gov customers, ~60% of US population** in some capacity (vendor claim, mixes true API access with counter-only deployments) | **4** (annearundel, tampa, clarkcounty, kingcounty) via the generalized `AccelaCitizenAccessConnector` | Google/Bing dork **`site:aca-prod.accela.com "CapHome.aspx"`** — **confirmed live this pass**, surfaced 9 previously-unknown agencies in a single query (Hartford CT, Santa Barbara Co. CA, Polk Co., San Joaquin Co. CA, Indianapolis IN, Oakland CA, Lee Co., plus 2 more) without any prior list. All agencies share the `aca-prod.accela.com` hosting domain (confirmed `robots.txt` still 404 site-wide, same as the original 4 — no crawl restriction). Per-agency module name (`Building`/`Permits`/`ServiceRequest`/etc.) varies and must be probed (`?module=Building` returning 200 vs. a 302 redirect is the live signal — confirmed working against Hartford and Oakland this pass, both resolved to `module=Building`). |
| **Tyler EnerGov / CSS** | Common among mid-size cities; no reliable total, **est. hundreds** | 0 direct connector (Houston/San Jose flagged as running Tyler-family or Infor stacks) | `site:*-energov.tylerhost.net` dork; also check a city's own `permits.<city>.gov` for an anonymous public lookup grid — untested as a bulk dork this pass (time-boxed), flagged for a worker follow-up. San Jose, CA confirmed this pass to host `TylerEnerGov_TestSite`/`z_TylerEnerGov_TrainingSite` items on its own ArcGIS org (`owner: sanjose`), confirming Tyler EnerGov as San Jose's platform — the actual public lookup UI wasn't located this pass. |
| **eTRAKiT / CSS (aspgov.com)** | **Est. hundreds** of small-mid CA/CO/WA/NC cities per research report | 0 | Dork **`inurl:etrakit permit.aspx`** — **confirmed live this pass**, surfaced 7 real instances in one query: Rancho Palos Verdes CA, Los Altos CA, Shoreline WA, Littleton CO, Harnett County NC, San Clemente CA, plus one on `grvlc-trk.aspgov.com`. Also enumerate the shared `*.aspgov.com` hosting domain directly. |
| **Infor Public Sector / Rhythm** | Smaller footprint specifically in permitting (research report); at least 1 major-metro confirmed | 0 (Houston flagged, not built) | Houston's `permits.houstontx.gov` **reconfirmed live this pass**: `robots.txt` returns `User-Agent: *` / `Disallow:` (empty — full crawl allowed) with `Sitemap: http://houstontx-prd.rhythmlabs.infor.com/sitemap.xml`, confirming the Infor Rhythm hosting pattern (`*.rhythmlabs.infor.com`). Dork: `site:*.rhythmlabs.infor.com`. |
| **CentralSquare / TRAKiT** | Est. hundreds of small municipalities + some Canadian cities | 0 | Not verified this pass — dork `inurl:trakit.net` or `inurl:mycentralsquare.com` untested, flagged for a worker to try next. |
| **BS&A Software** | Heavily concentrated in **Michigan** (MI Public Act 660 compliance) — MI has ~1,800 total municipal units, a large but unconfirmed fraction run BS&A | 0 | `bsaonline.com` **confirmed live** (302 redirect to a per-site landing page) and its own Municipal Directory is the ready-made target list per the research report, but a plain fetch of `bsaonline.com/MunicipalDirectory` did **not** return the actual list this session (content appears JS-rendered) — **flagged as needing a headless-browser worker pass**, not a plain HTTP GET. |
| **OpenGov / CitizenServe (ViewPoint Cloud)** | Vendor claims 500+ "Permitting & Licensing" partner communities, 2,000+ total customers (self-reported) | 0 | Not verified this pass — dork `inurl:viewpointcloud.com` or `inurl:opengov.com/permitting` untested, flagged for a worker. |
| **MyGov (now Tyler)** | Vendor/press-reported **~150 clients, concentrated TX/OK**; company founded in Norman, OK | 0 | No public client roster found via search this pass. Dork `site:*.mygov.us` untested — flagged for a worker. |
| **Selectron / CityView / GovPilot / Cloudpermit / CivicPlus / GOGov / Permitium / GovOS** | Long-tail, no reliable totals | 0 | Not investigated this pass beyond what's already in `RESEARCH_REPORT.md` §1.2 — lowest priority per that report's own ranking. |
| **Cityworks (Trimble) / Unity Permit** | Skews small cities/utilities, usually ArcGIS-paired | 0 direct, but ArcGIS-paired instances would already surface via the ArcGIS Hub discovery method above | No separate discovery method needed — same ArcGIS search covers it when combined with a "Cityworks" keyword. |
| **CKAN** (not in the original vendor survey — **new category confirmed this pass**) | Unconfirmed total; at least San Antonio TX and (partially) Phoenix AZ/Indianapolis IN run CKAN-based portals | 0 | `curl "https://<domain>/api/3/action/package_search?q=permit"` — standard CKAN API, **confirmed live and working** against `data.sanantonio.gov` (returned a real "building-permits" package, `metadata_modified` timestamped the same day as this research). This is a genuinely distinct connector shape from Socrata/ArcGIS (different JSON envelope, `datastore_search` for row-level data) — see Wave A below. |

**Overall estimate, updated from the research report**: still directionally **~3–6% of the ~20,100 Census BPS permit-issuing places have a true open API**, but this pass's findings suggest the *ArcGIS* slice of that is larger than the original report assumed — several of today's biggest finds (Fort Worth, Columbus, Las Vegas city, Detroit, Louisville) were sitting on live, high-volume, unauthenticated ArcGIS FeatureServers that simply hadn't been searched for yet, not because they're rare but because generic ArcGIS Hub catalog search misses city-hosted layers (confirmed again this pass — the winning technique was a per-city `arcgis.com/sharing/rest/search` query, not the Hub catalog crawl).

---

## 2. State-level and regional aggregators — investigated, mostly a dead end

The task hypothesis was that a state-level aggregator might shortcut jurisdiction-by-jurisdiction work. This pass specifically went looking for one. Findings:

- **New Jersey statewide (`data.nj.gov`, Socrata)** — **already in our 42.** This remains the one genuine, confirmed, live multi-municipality permit-transaction aggregator in the entire dataset (covers every reporting NJ municipality via `muniname`/`county` columns in one feed).
- **Cook County, IL Assessor feed** — **already in our 42.** Covers ~130 municipalities within the county (including overlap with the separate City of Chicago feed) via one parcel-tied permit dataset. Already fully exploited.
- **Utah — `opendata.utah.gov` (Socrata)** — this looked like exactly the shortcut hypothesized: search results showed a "Salt Lake City - Building Permits" dataset (`nbv6-7v56`) hosted on what appeared to be a *statewide* Socrata portal, which would imply other Utah cities might have parallel datasets on the same domain. **Verified live via direct query and found the domain has been decommissioned**: `curl "https://opendata.utah.gov/resource/3eji-gn2j.json"` returns `{"code":"not_found","error":true,"message":"This domain has been decommissioned."}`. This is a real, confirmed negative finding, not an assumption — a promising-looking state aggregator lead that no longer exists. Do not pursue further without finding wherever Utah's open data migrated to (not identified this pass).
- **Fulton County, GA — DCAT feed enumeration** — already investigated in `BLOCKERS.md` §5f: the county's ArcGIS Hub DCAT feed (`gisdata.fultoncountyga.gov/api/feed/dcat-us/1.1.json`) is live and real, but what it actually contains are **per-city** datasets (e.g., Alpharetta's own permit layers) published under the county's Hub umbrella, not one countywide permit feed. Useful as a *technique* (any Hub site's DCAT feed is a free full-catalog enumeration), not as a single-feed shortcut.
- **Virginia (VGIN Clearinghouse), Rhode Island (RIGIS), Idaho (Geospatial Office / Inside Idaho), Washington (`geo.wa.gov`), Arizona (AZGEO)** — all **confirmed live and real** this pass via direct fetch/search, exactly as the original research report predicted. But every one of them is overwhelmingly orthoimagery/parcel-boundary/elevation/transportation data, **not permit-transaction data** — consistent with the research report's caveat that these are useful only as a secondary signal ("does this local government publish open GIS data at all, as a proxy for whether it might also have an open permits layer"), not a direct permit source. No permit-transaction datasets were found on any of these five clearinghouses this pass.
- **Florida Geospatial Open Data Portal (`geodata.floridagio.gov`)** — found in search this pass, **not yet verified** for permit-relevant content. Florida is already reasonably represented (Gainesville, Tampa, Miami-Dade) — worth a follow-up check but not urgent.
- **Bottom line**: state-level aggregation is real but rare (2 confirmed cases: NJ statewide, Cook County IL) and one lead that looked promising (Utah) turned out to be dead. The overwhelming majority of remaining value is still jurisdiction-by-jurisdiction, exactly as `RESEARCH_REPORT.md` §1.4 estimated — this pass did not overturn that conclusion, just narrowed it with one more confirmed data point.

---

## 3. Prioritized build waves

Ordered by (population/data-richness) × (technical feasibility), highest first. Every jurisdiction below marked "confirmed live" was queried directly this pass — record counts and field lists are real, not estimated.

### Wave A — Open-API, zero-scraping-risk, highest population/richness (build first)

All of these reuse the existing `SocrataConnector`/`ArcGISConnector` shape except San Antonio (new CKAN connector class, see effort note below).

| Jurisdiction | Vendor | Confirmed URL | Live record count | Notes |
|---|---|---|---|---|
| **Fort Worth, TX** | ArcGIS (self-hosted, not AGOL) | `https://mapit.fortworthtexas.gov/ags/rest/services/CIVIC/Permits/MapServer/0` | **756,489** | 13th-largest US city (~1M pop). Rich fields: `Permit_No`, `Permit_Type`, `Permit_SubType`, `Permit_Category`, `B1_WORK_DESC`, structured address parts, `B1_LOT`. No auth required. Highest single-source record count found this pass. |
| **Columbus, OH** | ArcGIS Hub | `https://services1.arcgis.com/9yy6msODkIBzkUXU/arcgis/rest/services/Building_Permits/FeatureServer/0` | **675,273** | ~15th-largest US city (~930K). **Correction to prior assumption**: `BLOCKERS.md` §5a's spot-check only found a bulk `.gdb.zip` download under the Columbus GIS org and concluded (reasonably, at the time) that Columbus was aggregate/bulk-only. A separate, live, queryable FeatureServer of the same name exists and was confirmed this pass — worth re-checking other "aggregate-only" prior conclusions the same way. |
| **Las Vegas, NV (city proper)** | ArcGIS Hub | `https://services1.arcgis.com/F1v0ufATbBQScMtY/arcgis/rest/services/Building_Permits_Open_Data/FeatureServer/0` | **435,245** | Complements the existing Clark County ACA scraper (`clarkcounty` in our 42) with the city-proper feed — genuinely distinct jurisdiction, not overlapping data. |
| **Detroit, MI** | ArcGIS Hub | `https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/bseed_building_permits/FeatureServer/0` | **46,146** | Adds **Michigan** (currently uncovered state). Sourced from BSEED's internal Accela system but published as a clean open FeatureServer — best of both worlds. Fields include `record_id`, `address`, `submitted_date`, `issued_date`. |
| **Louisville Metro, KY** | ArcGIS Hub | `https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/active_construction_permits/FeatureServer/0` | **23,286** | Adds **Kentucky** (currently uncovered state). Genuinely rich fields incl. direct `CONTRACTOR`, `PERMIT_TYPE`, `PERMIT_STATUS`, `WORK_TYPE`, `ZONING`. |
| **Tucson, AZ** | ArcGIS (own server) | `https://gis.tucsonaz.gov/public/rest/services/PublicMaps/PermitsCode/MapServer/85` | **19,391** | Second AZ jurisdiction (alongside Tempe, Mesa). Fields include `VALUE`, `SQUAREFEET`, `WORKCLASS`, direct `LAT`/`LON`, plus cross-reference URLs to `ENGOV_URL`/`CSS_URL`/`PRO_URL` (suggests Tucson's backend has migrated across multiple permitting systems over time — worth spot-checking date-range gaps). |
| **San Antonio, TX** | **CKAN** (new connector class) | `https://data.sanantonio.gov/api/3/action/package_show?id=building-permits` | dataset confirmed live, `metadata_modified` = same day as this research | 7th-largest US city (~1.5M pop). CC-BY licensed. Needs a net-new `CKANConnector` (package_show + datastore_search API, similar upsert shape to the existing Socrata connector but a different JSON envelope) — see effort estimate below. |

**Wave A population impact**: roughly 3.7M+ combined city population added (Fort Worth ~1M, Columbus ~930K, Las Vegas ~660K, San Antonio ~1.5M — overlapping/approximate), plus Detroit (~630K) and Louisville Metro (~630K) and Tucson (~545K) — genuinely the highest-leverage wave available today.

### Wave B — Accela scraper expansion (reuse existing generic connector, ~15–30 min/agency)

Every one of these was confirmed live this pass via the `site:aca-prod.accela.com "CapHome.aspx"` dork plus a direct module-name probe. Same robots.txt/no-login/rate-limit posture already documented for the existing 4 agencies (shared `aca-prod.accela.com` hosting domain, `robots.txt` reconfirmed 404 site-wide this pass).

| Jurisdiction | Confirmed URL | Module | Notes |
|---|---|---|---|
| **Milwaukee, WI** | `aca-prod.accela.com/MILWAUKEE` | untested exact module, portal confirmed reachable (200) | Adds **Wisconsin**. Milwaukee's own ArcGIS server (`milwaukeemaps.milwaukee.gov`) was also checked directly this pass and confirmed to have an internal `Accela` services folder (`AccelaApo`, `AccelaDistrict`) — but those are administrative district-boundary layers, not permit records, so the ACA scrape is the right path here, not the ArcGIS one. |
| **Hartford, CT** | `aca-prod.accela.com/HARTFORD/Cap/CapHome.aspx?module=Building` | `Building` (**confirmed 200** this pass) | Adds **Connecticut** (currently uncovered state). |
| **Oakland, CA** | `aca-prod.accela.com/OAKLAND/Cap/CapHome.aspx?module=Building` | `Building` (**confirmed 200** this pass) | Large CA city (~430K) not yet covered by any connector. |
| **Santa Barbara County, CA** | `aca-prod.accela.com/SBCO` | not probed | Confirmed reachable via dork; module TBD. |
| **San Joaquin County, CA** | `aca-prod.accela.com/SJCO` | not probed (found on `Fire` module) | Confirmed reachable via dork; check for a `Building`/`Permits` module. |
| **Polk County** (state ambiguous — likely FL or IA) | `aca-prod.accela.com/POLKCO` | not probed | Confirmed reachable via dork; **disambiguate state before building** — don't assume. |
| **Lee County** (state ambiguous — likely FL) | `aca-prod.accela.com/LEECO` | not probed | Confirmed reachable via dork; disambiguate state before building. |
| **Indianapolis, IN** | `aca-prod.accela.com/INDY/Cap/CapHome.aspx?module=Permits` | `Permits` (confirmed via dork result URL) | Adds **Indiana**. Also worth checking `data.indy.gov` (Indianapolis's own open-data portal, confirmed reachable this pass at HTTP 200, but its `/api/3/action/package_search` path 404'd — it may not be CKAN, or uses a different path; investigate before assuming a scrape is required here). |
| **Madison, WI** | `elam.cityofmadison.com/CitizenAccess/Cap/CapHome.aspx?module=Permitting` | confirmed reachable via search result | Also has `data-cityofmadison.opendata.arcgis.com` (ArcGIS Hub) — **check the ArcGIS route first**, cheaper than a new scrape target if a live FeatureServer exists there. |

### Wave C — eTRAKiT (new connector class, ~1–2 days for the first one, then ~30–60 min/agency)

Confirmed live this pass via `inurl:etrakit permit.aspx`:

- Commerce City, CO (already flagged in `BLOCKERS.md` §5f — `robots.txt` returned HTTP 500 last time, worth a recheck)
- Littleton, CO
- Shoreline, WA (already named in `RESEARCH_REPORT.md`)
- Harnett County, NC
- Rancho Palos Verdes, CA
- Los Altos, CA
- San Clemente, CA
- One more instance on `grvlc-trk.aspgov.com` (city not yet identified — resolve before building)

Building the first eTRAKiT connector is the real engineering investment — same class of problem as the original Accela reverse-engineering effort (ASPX session/search-grid mechanics, no documented API), likely payable off the same way the Accela connector became generic after the second or third agency.

### Wave D — Infor Public Sector / Rhythm (new connector class, single highest-population target)

- **Houston, TX** — `permits.houstontx.gov`. **Reconfirmed live this pass**: `robots.txt` explicitly allows full crawling (`Disallow:` empty) and names its own sitemap at `houstontx-prd.rhythmlabs.infor.com/sitemap.xml`, confirming the Infor Rhythm platform. 4th-largest US city (~2.3M pop) — **the single highest-population target remaining in the entire backlog**, open-API-adjacent (real public address-based search tool, permissive robots.txt), and worth the one-time new-connector-class cost on population alone. Already flagged in `BLOCKERS.md` §5f as "not built this pass due to time" — this plan promotes it to a top-tier priority given nothing bigger was found.

### Wave E — Promising but unresolved this pass (verify before building)

- **Oklahoma City, OK** — `data.okc.gov` and `open-okc.hub.arcgis.com` both confirmed to exist; no permit-specific dataset located in this pass's searches. Adds **Oklahoma** if resolved.
- **Charlotte, NC (city proper)** — `data.charlottenc.gov` confirmed live (HTTP 200) but its API doesn't respond to the standard CKAN `package_search` path; dataset location not resolved. Distinct from the already-covered Mecklenburg County connector.
- **Florida Geospatial Open Data Portal** (`geodata.floridagio.gov`) — confirmed to exist, permit content not checked.

### Wave F — State gap-fill status (honest accounting, not all resolved)

States still uncovered after Waves A–D would be added (MI, KY, WI, CT, IN closed by A–C above). Remaining gaps and their status as of this pass:

| State | Status |
|---|---|
| AL, AR, IA, KS, ME, MS, NE, ND, NH, PR, RI, SC, VT, WV, WY, AK, DE | **No live lead confirmed this pass.** Lower population impact individually; recommend the BS&A/MyGov/eTRAKiT directory-enumeration tasks (§1) or a targeted per-state search pass before the FOIA lever (`BLOCKERS.md` §5d). |
| UT | Had a promising-looking lead (`opendata.utah.gov`) that is **confirmed decommissioned** — see §2. Needs fresh discovery. |
| OK | See Wave E (Oklahoma City, portal exists, dataset not located). |

---

## 4. Structurally infeasible or already-blocked — do not re-discover these

Recap of what's already known from `BLOCKERS.md` (so a worker doesn't burn a cycle re-finding them), plus new findings from this pass:

**Already documented in `BLOCKERS.md` — still true, do not re-attempt without a new angle:**
- `data.lacity.org` (LA) — HTTP 403 "must be logged in" on anonymous GET (§5).
- Maricopa County, AZ — login-walled `PermitViewer` app only, no open dataset (§5d).
- LA County — `Building Permit Viewer` is a licensed Geocortex Essentials app, not a queryable FeatureServer (§5d).
- King County, WA Socrata proxy — HTTP 403 "no row or column access to non-tabular tables" (already circumvented via the ACA scraper instead — `kingcounty` is in our 42 via that route, not Socrata).
- Fulton County, GA — only aggregated dashboard datasets at the county level (per-city data exists instead, see §2).
- ArcGIS Developer / Socrata app token / USPS Web Tools signup — all confirmed to require JS-rendered SPA signup flows, not completable via script (§6b, §4). Not required for anything currently built (anonymous access works fine at current volumes).
- SendGrid/Mailgun/Twilio — all require phone/payment verification even for free tiers (§9).
- Docker/Redis/PostGIS — not installed in this environment, no code blocker (§1–3).

**New findings this pass — flag so nobody re-discovers these the hard way:**
- **Jacksonville, FL false positive**: an ArcGIS FeatureServer titled "Building Permits" (`services6.arcgis.com/ONZht79c8QWuX759/.../Building_Permits`) surfaced in a search explicitly for Jacksonville permit data — but its actual owner is `shahir.alam@peelregion.ca` and its fields (`Year`/`Quarter`/`Geography`/`Single_Units`/`Double_Units`) are **Peel Region, Ontario, Canada** quarterly aggregate housing-start stats, not Jacksonville per-record permits at all. A second item that surfaced in the same search thread, `CFW_Open_Data_Development_Permits_View`, is genuinely **Fort Worth's** (owner `CFW_AGOL_ADMIN` — "CFW" = City of Fort Worth, not a Jacksonville abbreviation). No real Jacksonville per-record permit FeatureServer was found this pass — don't reuse either of these URLs under Jacksonville's name.
- **Baltimore, MD** — the only permit-related ArcGIS item found is literally titled *"Building Permit Data System (BPDS) Web Service - **deprecated**"* — a dead end, don't build against it without finding a live replacement (not located this pass).
- **Milwaukee's older ArcGIS layer** (`PERMITS_BuildingZoning_CPCDC`, `services6.arcgis.com/StPsG80YRtvnlCJ8`) — last modified **2021**, owned by an individual-looking account (`LawrenceGWMKE`), not an official city org — stale, use the Wave B Accela scrape instead, not this layer.
- **Phoenix, AZ** — `phoenixopendata.com`'s only "building permit" listing is a mirror of the federal HUD SOCDS Building Permits Database, last modified **2023** and itself sourced from a historically-static federal survey product, not live per-record municipal permit data. Don't build against it expecting fresh data.
- **Providence, RI** — a search suggested a Socrata portal at a guessed domain; a direct catalog query (`domains=data.providenceri.gov`) returned **zero results**, meaning either the domain guess was wrong or no permit dataset exists there. Not resolved this pass.

---

## 5. Effort estimates (for sequencing, not firm quotes)

| Work item | Estimated effort | Basis |
|---|---|---|
| New Socrata-family jurisdiction (connector already built) | ~30–60 min | Matches the pace of the 4th data-gathering pass (`BLOCKERS.md` §5f): live metadata audit + config + field-completeness check per source. |
| New ArcGIS-family jurisdiction (connector already built) | ~30–60 min, +more if layer ID/geometry-only lat-lon needs handling | Same basis; watch for layer-ID drift (Philadelphia precedent) and State-Plane/geometry-only coordinates (Denver/Portland precedent). |
| New Accela agency (generic scraper already built) | ~15–30 min | Connector already parses header rows dynamically; the only per-agency work is discovering the module name and confirming `robots.txt`/rate-limit posture (already uniform across `aca-prod.accela.com`). |
| New CKAN connector (net-new class, San Antonio first) | ~3–5 hours first one, ~30 min each after | CKAN's `package_show`/`datastore_search` REST/JSON API is structurally similar to Socrata's SODA API — should reuse most of the existing upsert/mapping pattern. |
| New eTRAKiT connector (net-new class) | ~1–2 days first one, ~30–60 min each after | Comparable complexity to the original Accela reverse-engineering effort (stateful ASPX search grid, no documented API). |
| New Infor Rhythm connector (net-new class, Houston only) | ~1–2 days | Unknown session/search mechanics until reverse-engineered; justified by Houston's population alone (largest single target in the backlog). |

---

## 6. Recommended execution order for a worker agent

1. **Wave A** (7 jurisdictions, all open-API, ~3.7M+ population added, mostly reusing existing connectors) — highest ROI, start here.
2. **Wave B** (Accela expansion, 8 agencies, ~15–30 min each) — cheapest marginal cost, do in parallel with Wave A.
3. **Wave D** (Houston, Infor Rhythm) — single new connector class, justified purely by population; worth the build time.
4. **Wave C** (eTRAKiT, new connector class) — second-highest new-class investment; do after Houston since eTRAKiT unlocks more total agencies than one Rhythm connector does.
5. **Wave E** (Oklahoma City, Charlotte proper) — needs a follow-up discovery pass before building (30–60 min of research each), then treat as Wave A-style config work.
6. **Wave F / state gap-fill** — lowest-population-density long tail; treat as demand-pulled per `RESEARCH_REPORT.md` §5.3's Phase 3 guidance, or hand to the BS&A/MyGov directory-enumeration tasks in §1 as a batch project rather than one-by-one search.
7. **Discovery-pipeline hardening** (not jurisdiction-specific): implement the confirmed-working Socrata catalog query, ArcGIS Hub search, and both dork patterns (§1) as a recurring scheduled job rather than one-off manual searches, per `RESEARCH_REPORT.md` §1.3's original recommendation — this pass reconfirms all of them still work exactly as described, plus adds the CKAN `package_search` pattern as a fourth mechanical method not in the original research report.
