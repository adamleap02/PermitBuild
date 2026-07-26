# Building a US Construction Project Database — Market & Data Research Report

**Prepared:** July 25, 2026
**Purpose:** Ground-truth research to inform the data acquisition strategy, legal posture, and MVP scope for a SaaS product that identifies and enriches actively-permitted residential and commercial construction projects across the US, for sale to contractors, suppliers, lenders, insurers, and investors.

**A note on confidence:** Vendor market-share figures, pricing, and coverage percentages below are frequently not publicly disclosed by the companies involved. Where a number is a public claim from the vendor, it's cited as such. Where no hard number exists, it is explicitly marked **"estimated"** or **"unconfirmed"** based on triangulating searches, and should be re-verified before it appears in any investor deck or customer-facing claim.

---

## 1. The US Permit Data Landscape

### 1.1 How permit data is issued and by whom

The US Census Bureau's Building Permits Survey (BPS) mails to **~20,100 permit-issuing places** (mostly municipalities, plus counties, townships, and New England-style towns) — this is the closest thing to an authoritative count of the total addressable universe of permitting jurisdictions. Not all of these issue *digitally accessible* permits; many are small townships still running paper processes.

Permitting software is fragmented across a handful of vendors, each with very different data-exposure models.

### 1.2 Vendor-by-vendor breakdown

| Vendor / Platform | Typical exposure | Connector requirements | Notes |
|---|---|---|---|
| **Accela (Civic Platform / Citizen Access, "ACA")** | Public web search UI (ACA) at `<agency>.accela.com` or custom subdomains (e.g. `access.okc.gov/aca`); a documented REST API (Accela Automation / Construct API) exists but is **licensed and permissioned per agency** — most agencies do not open it to third parties without a data-sharing agreement. | Auth: agency-specific OAuth app registration, usually requires the *agency's* sign-off, not just Accela's; pagination via `offset/limit`; JSON. Where no API access is granted, the practical path is scraping the public ACA search UI (session-based ASPX/JSP forms, CAPTCHA on some instances). | Accela claims **~1,000+ government customers**, serving an estimated **~60% of the US population** in some capacity (cited in Accela's own marketing) — this figure should be treated as a vendor claim, not independently verified. |
| **Tyler Technologies (EnerGov / Munis / "Enterprise Permitting & Licensing")** | Public self-service portal ("EnerGov Citizen Self Service" / "CSS") at pattern `*-energov.tylerhost.net` or `permits.<city>.gov`; anonymous record lookup is usually open to the public (no login) for basic status/address search. No general open API for third parties; Tyler's own integrations (e.g., SeeClickFix 311) are separately licensed. | No key needed for the public lookup UI, but it is a stateful web app (ASP.NET) requiring scraping with pagination through search-result grids; rate limiting is informal (IP-based) rather than documented. | Tyler acquired **MyGov** (Jan 2025) and **EnerGov** (via Sungard-era acquisitions), consolidating a large share of mid-size-city permitting. |
| **OpenGov (formerly ViewPoint Cloud / CitizenServe)** | Public-facing permit portal per agency; OpenGov acquired ViewPoint (2019), which was notable as the first vendor with a live ArcGIS link to permit records, meaning some OpenGov/ViewPoint cities publish permit layers directly as **ArcGIS map services** in addition to the citizen portal. OpenGov's own "Open Data" product (post Ontodia acquisition) is CKAN-based. | Where ArcGIS-linked, standard ArcGIS REST API access (see below). Otherwise, portal scraping. | OpenGov claims **500+ "Permitting & Licensing" partner communities** and 2,000+ total public-agency customers across its full suite (self-reported). |
| **CentralSquare / Superion (CSM, formerly TRAKiT / TRAKiT.Net)** | Agency-hosted web portal, typically no public API; TRAKiT.Net historically offered a lightweight public search page. | Scraping only, in most cases; forms-based ASP.NET UI similar to Tyler's. | CentralSquare serves 7,650+ public-sector organizations across its full product line (not permitting-specific); TRAKiT is a smaller share used mostly by small-to-mid municipalities and some Canadian cities. |
| **BS&A Software** | "BS&A Online" portal (`bsaonline.com` + per-municipality subdomain) — public records search covers permits, assessments, and utility billing; heavily concentrated in **Michigan** (used to comply with MI Public Act 660) with expansion into a few neighboring Midwest states. | Public search is unauthenticated HTML; each municipality is a separate "site" in the BS&A Municipal Directory, so a connector must enumerate that directory and scrape per-site. | Virtually every Michigan municipality appears in BS&A's own Municipal Directory — useful as a ready-made target list for that state. |
| **CSS / eTRAKiT** | Public portal at pattern `*.aspgov.com/etrakit` or `<agency-subdomain>` (e.g., `permits.shorelinewa.gov/etrakit`); anonymous permit/project lookup is standard. | Same scraping profile as Tyler CSS — session cookies, ASPX search grids, no documented public API. | Common among small-to-mid CA, CO, WA cities (Sausalito, Commerce City CO, Shoreline WA, Colton CA, Piedmont CA, Del Mar CA confirmed via search). |
| **Infor Public Sector** | Agency portal, generally no open API; smaller footprint in permitting specifically (Infor is stronger in ERP/utility billing for public sector). | Scraping where a public search exists; many Infor Public Sector permitting deployments are not public-facing at all. | Lower priority vendor for a connector strategy given smaller permitting footprint. |
| **Cityworks (Trimble)** — "Cityworks PLL / Public Access," being rebranded **Unity Permit** | Public Access portal for permitting, licensing, land (PLL module); GIS-centric, often paired with Esri ArcGIS. | Where paired with ArcGIS (common, since Cityworks is Esri-centric), the **ArcGIS REST API is the most reliable connector path**. | Adoption skews toward small-to-mid cities/utilities/public works agencies (e.g., Rexburg ID, Bonneville County ID) rather than major metros. |
| **Socrata (now "Tyler Data & Insights" after Tyler's 2018 acquisition)** | True **open-data API** (SODA — Socrata Open Data API). This is the best-case scenario for a connector. | REST/JSON, dataset IDs like `ydr8-5enu` (Chicago) via `/resource/{id}.json`; **Socrata Discovery API** (`api.us.socrata.com/api/catalog/v1`) lets you programmatically enumerate all public datasets tagged "building permits" across all ~200+ government Socrata portals — this is a strong "auto-discovery" mechanism (see 1.3). No auth needed for public data; app tokens recommended for higher rate limits. **Note:** SODA3 (rolling out through 2025–2026) changes some legacy SODA2 paths and pushes toward authenticated access — connectors should plan for token-based auth going forward. | Confirmed live building-permit Socrata datasets: **Chicago** (`data.cityofchicago.org`, dataset `ydr8-5enu`), **NYC** (`data.cityofnewyork.us`, multiple DOB NOW datasets), **San Francisco** (`data.sfgov.org`, dataset `i98e-djp9`, 1.3M+ records), **Austin** (`data.austintexas.gov`), **Seattle** (`data.seattle.gov`, dataset `76t5-zqzr`), **Los Angeles** (`data.lacity.org`, multiple building-permit datasets), plus **Dallas** (`dallasopendata.com`). |
| **ArcGIS Hub / Esri Open Data** | Open Data portals at pattern `<agency>.hub.arcgis.com` or `<agency>.opendata.arcgis.com`; datasets downloadable as CSV/GeoJSON/Shapefile/KML and queryable live via **ArcGIS REST "FeatureServer/MapServer" endpoints** (`.../MapServer/0/query?where=...&outFields=*&f=json`). | No auth for public layers; pagination via `resultOffset`/`resultRecordCount`; can be discovered via ArcGIS Hub's own search UI/API (`hub.arcgis.com/api/v3/datasets?...`) filtered by tag "building permits." | Confirmed instances: **Denver** (residential construction permits, `opendata-geospatialdenver.hub.arcgis.com`), **Columbus OH**, **Raleigh NC**, **Washington DC**, **Douglas County CO**, **Yucaipa CA**, plus many county GIS shops. |
| **MyGov** (acquired by Tyler, Jan 2025) | Public permit/inspection lookup portal; **~150 clients, concentrated in Texas and Oklahoma** (per vendor/press reporting). | Scraping; expect consolidation into Tyler's stack over the medium term. | Useful target list for small Texas/Oklahoma towns not otherwise covered. |
| **Permitium / GovOS** | Public permitting portal for smaller agencies; GovOS also sells short-term-rental and tax-compliance products bundled with permitting. | Scraping; no confirmed open API. | Smaller footprint; lower near-term priority. |
| **ProudCity** | Primarily a city *website/CMS* platform (not a permitting system per se) — some ProudCity sites embed or link out to a separate permitting vendor. | N/A as a direct permit source; useful mainly for locating which underlying permitting vendor a small city actually uses. | Lower priority — not itself a permit-data source. |
| **Selectron / CivicPlus / GOGov / CityView / Cloudpermit / GovPilot** | Smaller/regional permitting vendors, each with agency-hosted public portals of varying openness; no standardized API confirmed for any. | Scraping, case-by-case. | Long-tail vendors; relevant mainly in Phase 3 (see §4/§5). |
| **Custom in-house systems** | Highly variable — ranges from a PDF-only weekly "permits issued" report posted to a city clerk's page, to a bespoke searchable database. | No general connector; requires manual jurisdiction-by-jurisdiction assessment. | Common among the smallest jurisdictions and some large legacy cities (parts of NYC pre-DOB NOW, e.g.) that haven't migrated to a modern vendor. |

### 1.3 Strategy for discovering new jurisdictions over time

A durable connector-discovery pipeline should combine several automatable signals rather than relying on a static list:

1. **Socrata Discovery/Catalog API** — query `api.us.socrata.com/api/catalog/v1?q=building+permits&only=datasets` (and variants for "construction permits," "certificate of occupancy," etc.) on a recurring schedule; this surfaces new portals and new datasets on existing portals automatically. The **Open Data Network** (openness aggregator over Socrata) is a secondary crawl target.
2. **ArcGIS Hub search API** — `hub.arcgis.com`'s dataset search can be queried by tag/keyword ("permits," "building permits," "construction permits") across all public ArcGIS Hub/Open Data sites; combine with a scheduled crawl of known `*.opendata.arcgis.com` and `*.hub.arcgis.com` subdomain patterns (many follow `<citygis>.opendata.arcgis.com`, discoverable via `site:opendata.arcgis.com "building permits"` style search-engine dorking as a supplement).
3. **URL-pattern enumeration** against known vendor hostnames: `*.accela.com/citizenaccess`, `*-energov.tylerhost.net`, `*.aspgov.com/etrakit`, `bsaonline.com` municipal directory (BS&A publishes its own directory of every enrolled MI municipality — a ready-made scrape target), `*.mygov.us`, `*.citizenserve.com`, `*.viewpointcloud.com` / `*.opengov.com`.
4. **State open-data catalogs and GIS clearinghouses** as secondary aggregators: e.g., NY's statewide GIS Clearinghouse (`gis.ny.gov`) and Statewide Parcel Map Program, Washington's `geo.wa.gov`, Arizona's AZGEO Clearinghouse, Idaho's "Inside Idaho" / new statewide "Idaho's Map," Hawaii's statewide GIS program, Virginia's VGIN clearinghouse. These rarely host permit-transaction data directly but are useful for parcel/zoning context and for discovering which local governments publish *any* open GIS data (a decent proxy for "likely to also have an open permits layer").
5. **data.gov federal catalog** — search for "building permits" nets a long but incomplete list of harvested state/local datasets (confirmed hits for Chicago among others); useful as a supplementary discovery feed, not a primary source (data.gov often just mirrors metadata from the Socrata/ArcGIS source, with staleness risk).
6. **Manual/semi-manual fallback**: for the long tail (small towns, custom systems), periodic targeted search (`"<city name>" building permit search online`) remains necessary; this doesn't scale to full automation and should be budgeted as ongoing analyst/BD time, not pure engineering.

### 1.4 Rough coverage estimate (explicitly an estimate)

| Access tier | Estimated share of ~20,100 permit-issuing places | Estimated share of US population covered |
|---|---|---|
| Open API / open-data portal (Socrata, ArcGIS Hub, true REST API) | **~3–6%** of jurisdictions | **~25–35%** of population — because open-data-mature cities skew toward large, well-resourced metros (LA, NYC, Chicago, SF, Seattle, Austin, Denver, etc.) |
| Public search UI only, PDF/HTML, requires scraping (Accela ACA, Tyler CSS, eTRAKiT, BS&A, TRAKiT, MyGov, etc. without open API) | **~35–45%** of jurisdictions | **~35–45%** of population |
| No usable public digital access (paper process, phone/counter-only, or a portal requiring a login/paid account to see any record detail) | **~50–60%** of jurisdictions | **~20–30%** of population |

These bands are triangulated from Accela's self-reported "~60% of US population" customer footprint (which itself mixes true API access with counter-only portal deployments), the confirmed list of major-metro Socrata/ArcGIS portals, and the general shape of US municipal fragmentation (most of the 20,100 places are small towns). **Treat these percentages as directional, not audited** — a proper coverage model requires actually enumerating and testing each jurisdiction, which is itself a Phase 1 engineering deliverable.

### 1.5 Sample state/metro table (starting sample, not exhaustive)

| State / Metro | Jurisdiction | Vendor / Platform | Data access type |
|---|---|---|---|
| CA | Los Angeles | Custom / LA Dept. of Building & Safety | Socrata open data (`data.lacity.org`) |
| CA | San Francisco | DBI | Socrata open data (`data.sfgov.org`, `i98e-djp9`) |
| IL | Chicago | Custom | Socrata open data (`data.cityofchicago.org`, `ydr8-5enu`) |
| NY | New York City | DOB NOW | Socrata open data (`data.cityofnewyork.us`, multiple DOB NOW datasets) |
| TX | Austin | Custom | Socrata open data (`data.austintexas.gov`) |
| TX | Dallas | Custom | Socrata open data (`dallasopendata.com`) |
| WA | Seattle | Custom | Socrata open data (`data.seattle.gov`, `76t5-zqzr`) |
| CO | Denver | Custom / GIS | ArcGIS Hub (`opendata-geospatialdenver.hub.arcgis.com`) |
| OH | Columbus | Custom | ArcGIS Hub |
| NC | Raleigh | Custom | ArcGIS Hub (`data-ral.opendata.arcgis.com`) |
| DC | Washington | Custom | ArcGIS Hub (Open Data DC) |
| CO | Douglas County | Custom | ArcGIS Hub |
| MI | (all municipalities) | BS&A Software | Public search portal (`bsaonline.com`), no open API |
| OK, TX (~150 clients) | Various small cities | MyGov (now Tyler) | Public portal, no open API |
| CA | Sausalito, Colton, Piedmont, Del Mar | CSS eTRAKiT | Public search portal, no open API |
| CO | Commerce City | CSS eTRAKiT | Public search portal, no open API |
| WA | Shoreline | CSS eTRAKiT | Public search portal, no open API |
| FL | Cape Coral | Tyler EnerGov CSS | Public search portal, no open API |
| Many mid-size cities nationwide | — | Accela Citizen Access | Public search portal, licensed API rarely opened to 3rd parties |
| Many mid-size cities nationwide | — | Tyler EnerGov CSS | Public search portal, no general open API |
| ID (Rexburg, Bonneville Co.) | — | Trimble Cityworks PLL | Public Access portal, ArcGIS-paired where available |

*This table is a verified starting sample built from targeted searches during this research pass — it is not a comprehensive jurisdiction inventory and should be expanded systematically per §1.3.*

---

## 2. Commercial Property / Owner Enrichment Providers

### 2.1 Category framing

- **(a) Public-record / no-license-needed sources:** US Census Bureau (ACS, BPS), USPS address standards (the underlying ZIP+9/CASS reference data itself is public; only *certified software implementations* are gated), county assessor open-data portals, state GIS clearinghouses.
- **(b) Licensed commercial data requiring a paid contract:** ATTOM, CoreLogic, Melissa, Experian, Acxiom, LiveRamp, Regrid/Estated, BatchData, PropertyRadar, Datafiniti.
- **(c) Likely unavailable/restricted for this use case without specific compliance controls:** raw consumer credit attributes, anything requiring FCRA "permissible purpose" (employment, credit, insurance underwriting, tenant screening) when your product's actual use is marketing/lead-gen, and DMV-sourced driver data (not needed for this product — see §3).

### 2.2 Provider comparison

| Provider | Relevant data offered | Pricing model (best available info) | API | Free tier/trial | Licensing/legal notes |
|---|---|---|---|---|---|
| **ATTOM Data Solutions** | Property characteristics, valuations (AVM), ownership, tax assessment, foreclosure, deed/mortgage, ~9,000 attributes across 160M+ properties, 3,000+ counties aggregated. | API plans reportedly starting **~$499/yr** for low volume; realistic usable tiers run **hundreds to low-thousands $/mo**; bulk/enterprise is custom-quoted. | Yes — REST, JSON/XML, well-documented developer portal. | Developer trial/sandbox available (limited calls); no permanent free tier for production use. | Standard commercial data license; not FCRA-regulated for property-only use, but ATTOM does offer FCRA-compliant products (e.g., for background-check resellers) as a *separate* certified tier — don't conflate the two. |
| **CoreLogic** | Property, mortgage/lien, valuation (AVM), climate/hazard risk, MLS-adjacent (via Trestle marketplace). Very deep in mortgage/insurance-grade data. | Enterprise-only, contact sales; one reported real-world data point: **~$12,000/yr** for ~900 API calls in a Property Data API package (per-call ranged $0.005–$11.50 depending on endpoint). Skews toward large lenders/insurers as customers, so SMB pricing is not really a target segment for them. | Yes — but enterprise-gated, requires a sales relationship to provision keys. | No public free tier. | Contracts typically include strict resale/redistribution restrictions; CoreLogic data is often used *within* FCRA-regulated workflows (mortgage underwriting) so contract terms may impose FCRA-adjacent permissible-use language even where your use is non-FCRA. |
| **Melissa (Melissa Data)** | Address verification/standardization (CASS-certified), property append (property details, mortgage/deed, owner contact, absentee-owner flag), phone/email validation. | Pay-as-you-go, no long-term contract required; approx. **$0.01–$0.04/unit** cited for contact verification-type calls; **1,000 free credits** on signup. | Yes, REST API. | Yes — free credits on account creation (not a recurring monthly free tier, more of a one-time trial allotment). | Melissa explicitly separates its FCRA-regulated identity/background products from its non-regulated marketing/verification products — good vendor to model contract language after. |
| **Experian** | Consumer marketing data (245M+ consumers), expanded public-record data (property deeds, address history) beyond a standard credit file, B2B/business data (32M+ businesses). Also owns FCRA-certified specialty CRAs (Clarity Services, RentBureau). | Enterprise/contact-sales; typically multi-year contracts embedded into client data workflows. | Yes, but enterprise-provisioned, not self-serve signup. | No self-serve free tier. | Experian's marketing-data arm is explicitly positioned as **non-FCRA** for ad-targeting/marketing use; the FCRA-regulated products (Clarity, RentBureau, core credit file) are a **separate legal product line** — critical to keep the two contractually and technically separated if any Experian relationship is pursued. |
| **Acxiom (part of IPG / Interpublic, "Acxiom Marketing Solutions")** | Broad consumer marketing/identity data ("AMP" platform), covering an IPG-claimed "two-thirds of the world's population" in some form; strong in identity resolution and audience segments, not property-specific. | Enterprise-only, agency/brand-level contracts, typically via IPG Mediabrands relationships; not a self-serve product for a startup. | Limited/enterprise, generally accessed via IPG's platform rather than an open developer API. | No. | Consumer marketing data with permissible-use and opt-out obligations under state privacy laws (see §3); not FCRA-regulated by default, but resale/onward-transfer restrictions are typically heavy in Acxiom-class contracts. Likely a poor fit for an early-stage company (relationship-gated, agency-oriented). |
| **LiveRamp** | Not a data owner per se — an **identity resolution and data-collaboration/clean-room platform** plus a data marketplace connecting to thousands of third-party data segments. | No public pricing; unconfirmed reporting suggests implementation fees in the **$15K–$50K** range, annual identity-resolution licensing from **~$50K/yr** up to $250K+/yr for advanced features, plus usage fees (~$0.50–$2.50 per 1,000 matched profiles). | Yes, but enterprise-provisioned. | No. | Primarily relevant if/when this company needs to onboard its own first-party data into ad-tech ecosystems (e.g., matching permit-derived leads to ad audiences) — not a core property-data source. Overkill and likely premature for MVP. |
| **Regrid (formerly Estated is now folded in / Regrid acquired Estated's parcel assets)** | Nationwide parcel boundaries, ownership records, addresses, zoning, building footprints. Strong on **parcel geometry + ownership**, less deep than ATTOM/CoreLogic on transaction history/valuation. | Self-serve tiers (Starter/Pro/Team) plus a self-serve API plan; per-record pricing scales with volume/fields; enterprise custom quote available via email. | Yes, self-serve REST API — notably more accessible/self-serve than ATTOM or CoreLogic for a startup to start using immediately. | Free/low-cost entry tier reported for the web app; API self-serve plans start at modest volume. | Standard commercial license; parcel/ownership data is public-record-derived, generally lower legal risk than consumer marketing data. **Good MVP-stage candidate** given self-serve accessibility. |
| **BatchData** | Property + owner data, **skip-tracing** (phone/email/mailing address for a given owner), DNC/litigator scrubbing. | Skip-tracing: **$2,000/mo (100K traces)** up to **$20,000/mo (3M traces, Enterprise)**; also pay-as-you-go; Property Search API from **$500/mo (20K records)**; Contact Enrichment add-on **$5,000/mo**. | Yes, REST API, developer docs available. | Not confirmed — no clear free tier; likely a demo/sales-assisted trial. | Skip-tracing / contact-append data raises **TCPA** exposure once used for outbound calling/texting — BatchData explicitly markets DNC/litigator scrubbing to mitigate this, but the compliance burden remains on the buyer (this company), not BatchData. |
| **PropertyRadar** | Property + owner data, foreclosure/vacancy/absentee flags, 250+ search criteria, phone/email append, direct-mail integration. | Tiered SaaS: **Solo $119/mo, Team $249/mo, Business $599/mo** (API access included at Business tier); add-ons for dialers, SMS, direct mail, extra contacts. 5-day free trial. | Yes, at Business tier and above. | 5-day free trial (not a permanent free tier). | Marketed directly at real-estate investors/agents; likely the **cheapest entry point** for owner-contact enrichment and a plausible reseller/comparison benchmark, though probably a competitor-adjacent product rather than a good OEM/supply partner. |
| **Datafiniti** | Aggregated property, business, and people data assembled largely from public web sources; usage-based. | **Trial: 1,000 free records / 2 weeks**; paid from **$119/mo (1,000 records)** up to **$3,999/mo (1M records)**; Enterprise **~$60,000/yr**; 10% discount for annual prepay. | Yes, REST API. | Yes — genuine free trial (1,000 records, time-boxed). | Because Datafiniti's data is web-aggregated rather than licensed from primary record-holders, provenance and accuracy should be independently spot-checked before relying on it for a paid product; legal risk is generally lower (public web sources) but data freshness/quality risk is higher. |
| **US Census Bureau** | ACS demographic/housing/economic data, decennial Census, Building Permits Survey (BPS) aggregate stats. | **Free.** | Yes, free public API (`api.census.gov`), no cost, generous but rate-limited. | N/A — fully free. | No restrictions; public government statistical data, ideal as a baseline enrichment layer (neighborhood demographics, median income, housing stock age) at zero marginal cost. |
| **USPS** | Address standardization/validation (ZIP+4, delivery point, CASS). | The raw USPS **Address Validation API is free** but rate-limited to a low default (reported **60 requests/hour** on the new V3 platform) — usable for light validation, not bulk. Full CASS-certified bulk processing generally requires a **licensed third-party CASS-certified vendor** (e.g., Smarty, PostGrid, Melissa), typically **$0.01–$0.05/address** at modest volumes. | Yes (free, rate-limited) or via certified vendors (paid, bulk). | Yes — the free API itself is the "free tier," just heavily rate-limited. | No general restriction; standard USPS address-standardization is a compliance best-practice (improves match rates against permit addresses) rather than a legal risk. |

### 2.3 Bottom line for this product

- Property characteristics, ownership, and parcel/zoning data (ATTOM, CoreLogic, Regrid) sit comfortably in normal commercial-license territory — not FCRA-regulated as long as the use is not credit/employment/tenant-screening decisioning.
- Owner **contact append/skip-trace** (BatchData, PropertyRadar, Melissa's property-append) is where **TCPA** and (for some providers) FCRA-adjacent contractual language start to matter — see §3.
- Regrid, PropertyRadar, Datafiniti, and Melissa are the most **startup-accessible** (self-serve signup, published tiers) and are reasonable Phase 1/2 enrichment partners; ATTOM is accessible but pricier; CoreLogic, Experian, Acxiom, and LiveRamp are enterprise-relationship products that likely don't make sense until this company has revenue and a compliance program to point to.

---

## 3. Legal & Compliance Considerations

### 3.1 State comprehensive privacy laws

As of mid-2026, roughly **19–24 states** (count is actively growing; sources differ slightly by cutoff date) have comprehensive consumer privacy laws, including California (CCPA/CPRA), Virginia (VCDPA), Colorado (CPA), Connecticut (CTDPA), Utah (UCPA), and now a wave of additional states (Texas, Oregon, Montana, Florida, Iowa, Indiana, Kentucky, Tennessee, New Jersey, Delaware, Nebraska, New Hampshire, Minnesota, Maryland, Rhode Island, and others with staggered effective dates through 2026).

**Commonalities across these laws** relevant to this product:
- Rights to access, correct, delete, and opt out of "sale"/"sharing" and targeted advertising for **personal information about identifiable individuals**.
- Most exempt data that is purely about a **business or property** (not tied to an identifiable natural person) — meaning raw permit records (address, project type, valuation, contractor of record) are generally *not* "personal information" under these laws in the way that an *owner's name + phone + email* combination would be.
- Sensitive-data categories (health, precise geolocation, etc.) require opt-in consent in several states (VA, CT, CO, IN, KY, RI) — unlikely to be directly relevant here unless the product starts inferring things like homeowner financial distress.
- CCPA/CPRA is the most operationally demanding (private right of action for breaches, CPPA enforcement, and — critically — **California's "data broker" registry regime**, see below).

### 3.2 Data broker registration laws

If this company **sells or licenses personal information about consumers (property owners, homeowners) that it did not collect directly from them**, it likely qualifies as a "data broker" in several states and should plan to register:

| State | Requirement | Fee | Notes |
|---|---|---|---|
| **California** (Delete Act / CPPA) | Annual registration with CPPA via the **DROP** platform (Jan 1–31 each year) | **$6,000/yr** + processing fee | Also requires responding to consumer delete requests submitted via DROP within 45 days, starting Aug 2026; enforcement is active. |
| **Vermont** | Annual registration | $0 in 2024 rising to **$200/yr** thereafter | Also imposes encryption/breach-notification obligations on registered brokers. |
| **Texas** | Registration with the Secretary of State, annual renewal | Fee unconfirmed exactly but modeled after similar states; **civil penalties up to $10,000/12 months** for non-compliance | SB 2105 (2023). |
| **Oregon** | Annual registration with Dept. of Consumer & Business Services | **$600/yr** | Penalties up to $500/violation/day, capped at $10,000/yr. |

**Practical takeaway:** if the go-to-market model is "sell enriched owner-contact lists," data-broker registration in CA/VT/TX/OR (at minimum) should be budgeted as a compliance line item before commercial launch — this is inexpensive (~$7,000–8,000/yr combined) but **must not be skipped**, and EFF has publicly noted many brokers are non-compliant, i.e., this is an active enforcement area, not a paper tiger.

### 3.3 FCRA (Fair Credit Reporting Act)

FCRA applies when (a) information is used or expected to be used, in whole or in part, to make a decision about a consumer's eligibility for credit, insurance, employment, housing/tenancy, or similar, AND (b) that information is compiled by a "consumer reporting agency." **Selling permit/property data to contractors and suppliers for lead-generation/marketing purposes is generally not an FCRA consumer report use** — there's no "permissible purpose" requirement triggered by pure marketing.

However, FCRA risk appears if:
- A lender or insurer customer starts using the data (even indirectly) to make an underwriting/eligibility decision about a specific consumer — at that point, the *data* may become subject to FCRA "consumer report" treatment regardless of how this company itself uses it, and the company could be deemed a furnisher or a CRA depending on structure.
- The product later adds tenant-screening or contractor-vetting features that assess a person's creditworthiness or character — this would clearly cross into FCRA territory and require a specialty-CRA compliance program (adverse-action notices, dispute handling, accuracy procedures under FCRA §607(b)).

**Guidance:** keep the core product (permits + property/project data + business-contact info for contractors/suppliers) in the "non-FCRA, B2B marketing/lead" lane. If lender/insurer customers want to use the data for underwriting decisions, that use case needs a **separate, explicitly FCRA-compliant data product** (following the ATTOM/Experian pattern of segregating FCRA and non-FCRA product lines) — do not casually blend the two.

### 3.4 DPPA (Driver's Privacy Protection Act)

DPPA restricts DMV disclosure/use of personal info tied to **motor vehicle records** (driver's license, vehicle registration/title). **This is very likely inapplicable to this product** since the data model is property/permit-centric, not driver/vehicle-centric — there is no reason for this company to touch DMV data. Flagging it only because it was in scope: no action needed unless a future feature (e.g., verifying a contractor's commercial vehicle fleet) pulls in DMV-sourced data, at which point DPPA's 14 permissible-use categories would need review.

### 3.5 TCPA (Telephone Consumer Protection Act)

Directly relevant once the product supports **outbound calling or texting** to property owners or contractors using autodialers/pre-recorded messages, or texting mobile numbers for marketing:
- Prior express written consent is generally required for marketing calls/texts to mobile numbers, **including B2B contacts on a mobile number** — the informal "B2B exemption" mostly only protects manual (non-automated) dialing to landline business numbers, not automated texts to a cell phone.
- Statutory damages run **$500–$1,500 per violation**, and class actions are common — this is a real, well-litigated risk area, not theoretical.
- **Practical guidance:** if outbound SMS/robocall outreach to leads is part of the GTM plan, obtain and log documented consent (or use only manual, one-to-one outreach to established business contacts, or route the "contact" step to human sales reps at customer companies rather than doing it centrally).

### 3.6 CAN-SPAM and Do-Not-Call

- CAN-SPAM governs commercial email: requires accurate headers, a working opt-out/unsubscribe, and honoring opt-outs within 10 business days. Lower risk than TCPA but still enforceable (FTC).
- The National Do-Not-Call Registry applies to **telemarketing calls to individual consumers**, generally not to B2B calls to a business number about a business's own products/services — but if this company's "leads" are actually individual homeowners (not contractors), DNC scrubbing before any outbound calling program is required.

### 3.7 Web scraping legal considerations

- **hiQ Labs v. LinkedIn (9th Cir.):** the CFAA "without authorization" prong does **not** criminalize scraping of data that is publicly accessible without a login — reaffirmed on appeal in 2022. This is a favorable precedent for scraping open government permit portals (which require no login).
- **However**, the underlying *hiQ v. LinkedIn* dispute ultimately ended in a **private settlement (Dec 2022)** where hiQ was permanently enjoined from scraping LinkedIn and paid LinkedIn $500,000 — importantly, that later phase turned on **breach-of-contract / Terms-of-Service** claims, not CFAA. The lesson: even where scraping is not a *federal crime*, a website's Terms of Service can still create **civil contract liability** if you scrape a site that expressly prohibits it and you're deemed to have agreed to those terms.
- Practical implication for this product: (1) government permit portals are generally public-interest data with no meaningful "terms of service" barrier and strong public-policy support for access (many explicitly intend the data to be public); (2) still worth a light legal review of each portal's terms/robots.txt before large-scale scraping, especially for vendor-hosted portals (Accela, Tyler) where a commercial vendor (not just the government) might assert its own platform ToS against a scraper; (3) prefer official APIs/open-data feeds wherever they exist over scraping, both for reliability and for legal cleanliness; (4) respect robots.txt and reasonable rate limits as a matter of practice, which also reduces IP-ban/technical risk.

### 3.8 Summary: what's safe now vs. what needs a licensing/compliance gate

| Activity | Compliance posture |
|---|---|
| Ingesting public government permit records (address, permit type, valuation, dates, contractor-of-record) | **Generally safe today** — public records, minimal PII, strong public-interest rationale, favorable CFAA precedent for scraping public pages. |
| Enriching with Census/ACS demographics, USPS address standardization | **Safe, free, no license needed.** |
| Enriching with licensed property/ownership data (ATTOM, CoreLogic, Regrid) for internal matching/scoring | **Safe under standard commercial license** — not FCRA-triggered by mere possession, only by specific end-use. |
| Adding owner **contact info** (phone/email) via skip-trace providers (BatchData, PropertyRadar, Melissa) and using it for **outbound telemarketing/texting** | **Requires compliance build-out first**: TCPA consent workflow, DNC scrubbing, and likely **data-broker registration** (CA/VT/TX/OR) before commercial sale of contact lists. |
| Reselling/sublicensing consumer marketing data (Experian/Acxiom-class segments) to third parties | **Needs contract + compliance review before go-to-market** — resale restrictions are typically baked into these vendors' contracts, and this is the highest-risk category. |
| Any future underwriting/credit/tenant-screening use of the data by lender/insurer customers | **Out of scope until a dedicated FCRA-compliant product line is built** — do not let this bleed into the core marketing product without a deliberate legal decision. |

---

## 4. Coverage Estimates (Phased)

| Phase | Description | Example jurisdictions (verified access type via search) | Rough % of US population reachable |
|---|---|---|---|
| **Phase 1 — Open API metros** | Cities/counties with a live Socrata or ArcGIS Hub permit dataset; can be ingested with a clean, low-maintenance connector from day one. | Los Angeles (Socrata), Chicago (Socrata), New York City (Socrata, DOB NOW), San Francisco (Socrata), Austin (Socrata), Dallas (Socrata), Seattle (Socrata), Denver (ArcGIS Hub), Columbus OH (ArcGIS), Raleigh NC (ArcGIS), Washington DC (ArcGIS) | **Estimated ~20–25%** of US population once ~25–40 such metros are onboarded (these are disproportionately large, dense metros). |
| **Phase 2 — Scraped portals** | Expand into Accela ACA, Tyler EnerGov CSS, and eTRAKiT cities where no open API exists but a public, unauthenticated search portal does; requires building and maintaining per-vendor (not per-city) scrapers, since many cities share the same underlying vendor template. | Any mid-size city on Accela or Tyler EnerGov (very common nationally), all Michigan municipalities via BS&A, ~150 Texas/Oklahoma towns via MyGov, small CA/CO/WA cities on eTRAKiT (Sausalito, Commerce City, Shoreline, Colton, Piedmont, Del Mar), Cape Coral FL (EnerGov CSS) | **Additional estimated ~30–40%**, bringing cumulative coverage to roughly **half to two-thirds** of the population — because vendor-template scraping amortizes across hundreds of cities per vendor built. |
| **Phase 3 — Long tail** | Small towns/counties on PDF/HTML-only or paper/counter-only processes; custom in-house systems; jurisdictions requiring manual monitoring or direct government-relations outreach. | The bulk of the ~20,100 Census BPS permit-issuing places not captured above — mostly small townships and rural counties. | Remaining **~15–25%** of population, spread across a very large number of very small jurisdictions — low ROI per-jurisdiction; likely never fully automated, may instead be handled via periodic manual sampling, partnerships with regional data aggregators, or simply left uncovered in v1–v2. |

These bands should be treated as **planning estimates**, not verified totals — a real jurisdiction-by-jurisdiction inventory (per §1.3's discovery methods) is needed to convert this into an actual coverage map, and is itself recommended as an early Phase-1 engineering task.

---

## 5. Recommended MVP Scope & Phased Rollout

### 5.1 MVP jurisdiction selection (recommended starting set: ~12–15 metros)

Prioritize **Socrata/ArcGIS-confirmed, large-population metros** first, since they combine (a) lowest engineering cost (clean APIs, no scraping-fragility risk), (b) largest addressable contractor/supplier/lender market, and (c) fastest time-to-first-data:

1. Los Angeles, CA (Socrata)
2. Chicago, IL (Socrata)
3. New York City, NY (Socrata / DOB NOW)
4. San Francisco, CA (Socrata)
5. Austin, TX (Socrata)
6. Dallas, TX (Socrata)
7. Seattle, WA (Socrata)
8. Denver, CO (ArcGIS Hub)
9. Washington, DC (ArcGIS Hub)
10. Columbus, OH (ArcGIS Hub)
11. Raleigh, NC (ArcGIS Hub)
12. 2–4 additional Socrata/ArcGIS metros to be confirmed during Phase 0 discovery sweep (candidates to check next: Boston, Philadelphia, Miami-Dade, Phoenix, San Diego, Houston, Charlotte, Nashville, Sacramento, Portland — many of these are known in the industry to run Accela or Tyler rather than open-data portals, so each needs individual verification before being added to this "Tier 1" list).

### 5.2 Enrichment scope at launch (free/public only)

- US Census ACS (neighborhood demographics, housing stock age/value context) — free.
- USPS address standardization (free tier, rate-limited; upgrade to a certified vendor like Smarty/PostGrid once volume requires it) — cheap.
- Basic parcel/ownership overlay via **Regrid** (self-serve API, most startup-friendly of the licensed providers) to resolve permit addresses to parcel + owner-of-record where available.
- **Defer** until (a) revenue exists and (b) a compliance program (TCPA consent flow, data-broker registration) is in place: owner contact append/skip-trace (BatchData, PropertyRadar, Melissa property-append), and any Experian/Acxiom/CoreLogic enterprise relationship.

### 5.3 Three-phase roadmap

**Phase 1 (0–3 months): Prove the core data pipeline**
- Build connectors for the Socrata SODA API and ArcGIS REST API (two connector types cover the ~11-metro Tier 1 list above).
- Stand up the Socrata Discovery API + ArcGIS Hub search crawl as an ongoing jurisdiction-discovery job (don't hardcode the city list).
- Normalize permit records into a common schema (address, permit type, valuation, filing/issue date, status, contractor-of-record if present, parcel ID).
- Overlay free Census/ACS demographics and a self-serve Regrid parcel/ownership layer.
- Stand up basic search/alerting UI for design-partner customers (a handful of regional suppliers/contractors) to validate demand before spending on paid data licenses.
- Begin the CA/VT/TX/OR data-broker registration paperwork in parallel if the GTM model involves selling owner-contact data — this has lead time (annual registration windows) so start early even before revenue.

**Phase 2 (3–9 months): Scale jurisdiction count, layer in paid enrichment**
- Build scrapers for the highest-value non-API vendor templates (Accela ACA, Tyler EnerGov CSS, eTRAKiT) — because these are shared templates, each scraper investment unlocks many cities at once, not just one.
- Target BS&A (all of Michigan) and MyGov (Texas/Oklahoma small cities) as two large, template-driven wins.
- Sign a paid tier with ATTOM or Regrid's higher tier (or both, compared head-to-head) for deeper property valuation/characteristics once there's revenue to justify the ~$500–$1,500+/mo cost.
- If lead-gen/contact-enrichment is validated as a paid feature by customers, add BatchData or PropertyRadar contact append — but only after the TCPA consent workflow and data-broker registrations from Phase 1 are actually in place.
- Begin state-by-state legal review as new states are added (comprehensive privacy law obligations scale with jurisdiction count and data volume).

**Phase 3 (9–18 months): Long tail + enterprise data deals**
- Expand into Phase-3 long-tail jurisdictions selectively, prioritized by customer demand (i.e., "our contractor customers operate in X county, can you add it") rather than blanket coverage — this is the lowest-ROI tier and should be demand-pulled, not push-built.
- Evaluate enterprise relationships with CoreLogic and/or Experian only once ARR justifies enterprise minimums (likely six figures/year) and only for specific customer segments (e.g., lenders/insurers who need FCRA-adjacent or deeper valuation data) — keep this contractually and technically separate from the core marketing-data product per §3.3.
- Consider LiveRamp only if/when the GTM motion needs to plug permit-derived audiences into ad-tech/clean-room workflows for enterprise supplier customers — not a Phase 1/2 need.
- Reassess data-broker and state-privacy-law obligations annually as the company scales — this is a recurring compliance cost, not a one-time setup.

---

## Key Sources Consulted

- US Census Bureau, Building Permits Survey (census.gov/construction/bps)
- Socrata Discovery API docs (dev.socrata.com), Chicago/SF/Austin/Seattle/NYC/LA/Dallas open data portals
- ArcGIS Hub open data listings (Denver, Columbus, Raleigh, DC, Douglas County)
- Accela, Tyler Technologies (EnerGov, MyGov), OpenGov (ViewPoint/CitizenServe), CentralSquare (TRAKiT), BS&A Software, Trimble Cityworks vendor sites and product pages
- ATTOM, CoreLogic, Melissa, Regrid, BatchData, PropertyRadar, Datafiniti vendor pricing/docs pages; Datarade and PriceLevel third-party pricing aggregators
- California CPPA (privacy.ca.gov, cppa.ca.gov), state data-broker law summaries (WilmerHale, Davis+Gilbert, Tonkon Torp, EFF)
- CFPB and industry summaries on FCRA permissible purpose
- EFF, Fenwick, Ninth Circuit opinion (hiQ Labs v. LinkedIn)
- MultiState, Troutman Pepper, Byte Back state privacy law trackers (2026)
- ActiveProspect, Infobip TCPA/SMS compliance guides
