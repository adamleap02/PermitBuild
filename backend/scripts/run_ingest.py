"""
Runnable demo script: ensures the demo jurisdictions exist, then runs a
live ingest against real public data (SF Socrata by default, or Tempe
AZ ArcGIS with --jurisdiction tempe), upserts permits, writes
PermitVersion history, and computes explainable scores.

Usage:
    python scripts/run_ingest.py                 # SF, 25 records
    python scripts/run_ingest.py --jurisdiction tempe --limit 50
    python scripts/run_ingest.py --jurisdiction chicago --limit 50
    python scripts/run_ingest.py --all --limit 25   # ingest every demo jurisdiction
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.ingest import run_ingest
from app.models import Jurisdiction, SourceSystem
from app.scoring.service import compute_scores_for_permit_ids

DEMO_JURISDICTIONS = {
    "sf": dict(
        name="San Francisco",
        state="CA",
        level="city",
        timezone="America/Los_Angeles",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.sfgov.org", "dataset_id": "i98e-djp9", "mapping": "sf_building_permits"},
    ),
    "chicago": dict(
        name="Chicago",
        state="IL",
        level="city",
        timezone="America/Chicago",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.cityofchicago.org", "dataset_id": "ydr8-5enu", "mapping": "chicago_building_permits"},
    ),
    "tempe": dict(
        name="Tempe",
        state="AZ",
        level="city",
        timezone="America/Phoenix",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services.arcgis.com/lQySeXwbBg53XWDi/arcgis/rest/services/building_permits/FeatureServer/0",
            "mapping": "tempe_az_building_permits",
        },
    ),
    "austin": dict(
        name="Austin",
        state="TX",
        level="city",
        timezone="America/Chicago",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.austintexas.gov", "dataset_id": "3syk-w9eu", "mapping": "austin_building_permits"},
    ),
    "seattle": dict(
        name="Seattle",
        state="WA",
        level="city",
        timezone="America/Los_Angeles",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.seattle.gov", "dataset_id": "76t5-zqzr", "mapping": "seattle_building_permits"},
    ),
    "dallas": dict(
        name="Dallas",
        state="TX",
        level="city",
        timezone="America/Chicago",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "www.dallasopendata.com", "dataset_id": "e7gq-4sah", "mapping": "dallas_building_permits"},
    ),
    "nyc": dict(
        name="New York City",
        state="NY",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.cityofnewyork.us", "dataset_id": "ipu4-2q9a", "mapping": "nyc_dob_permits"},
    ),
    "denver": dict(
        name="Denver",
        state="CO",
        level="city",
        timezone="America/Denver",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/ODC_DEV_RESIDENTIALCONSTPERMIT_P/FeatureServer/316",
            "mapping": "denver_co_residential_permits",
        },
    ),
    "raleigh": dict(
        name="Raleigh",
        state="NC",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services.arcgis.com/v400IkDOw1ad7Yad/arcgis/rest/services/Building_Permits/FeatureServer/0",
            "mapping": "raleigh_nc_building_permits",
        },
    ),
    "dc": dict(
        name="Washington",
        state="DC",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DCRA/FeatureServer/17",
            "mapping": "washington_dc_building_permits",
        },
    ),
    # --- Second data-gathering pass: 15 more jurisdictions (7 counties, 1
    # statewide feed, 7 more cities) -- see BLOCKERS.md for what was tried
    # and skipped (403s, moved domains, aggregated-only data). ---
    "sonoma": dict(
        name="Sonoma County",
        state="CA",
        level="county",
        timezone="America/Los_Angeles",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.sonomacounty.ca.gov", "dataset_id": "88ms-k5e7", "mapping": "sonoma_county_permits"},
    ),
    "marin": dict(
        name="Marin County",
        state="CA",
        level="county",
        timezone="America/Los_Angeles",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.marincounty.gov", "dataset_id": "mkbn-caye", "mapping": "marin_county_permits"},
    ),
    "howard": dict(
        name="Howard County",
        state="MD",
        level="county",
        timezone="America/New_York",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "opendata.howardcountymd.gov", "dataset_id": "kvz2-j5cj", "mapping": "howard_county_permits"},
    ),
    "batonrouge": dict(
        name="East Baton Rouge Parish",
        state="LA",
        level="county",
        timezone="America/Chicago",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.brla.gov", "dataset_id": "7fq7-8j7r", "mapping": "baton_rouge_permits"},
    ),
    "mesa": dict(
        name="Mesa",
        state="AZ",
        level="city",
        timezone="America/Phoenix",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "citydata.mesaaz.gov", "dataset_id": "dzpk-hxfb", "mapping": "mesa_az_permits"},
    ),
    "cincinnati": dict(
        name="Cincinnati",
        state="OH",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.cincinnati-oh.gov", "dataset_id": "uhjb-xac9", "mapping": "cincinnati_permits"},
    ),
    "gainesville": dict(
        name="Gainesville",
        state="FL",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.cityofgainesville.org", "dataset_id": "p798-x3nx", "mapping": "gainesville_permits"},
    ),
    "cook": dict(
        name="Cook County",
        state="IL",
        level="county",
        timezone="America/Chicago",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "datacatalog.cookcountyil.gov", "dataset_id": "6yjf-dfxs", "mapping": "cook_county_permits"},
    ),
    "cambridge": dict(
        name="Cambridge",
        state="MA",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.cambridgema.gov", "dataset_id": "9qm7-wbdc", "mapping": "cambridge_new_construction_permits"},
    ),
    "framingham": dict(
        name="Framingham",
        state="MA",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.framinghamma.gov", "dataset_id": "2vzw-yean", "mapping": "framingham_permits"},
    ),
    "sandiego": dict(
        name="San Diego County",
        state="CA",
        level="county",
        timezone="America/Los_Angeles",
        source_system=SourceSystem.SOCRATA,
        source_config={
            "domain": "internal-sandiegocounty.data.socrata.com",
            "dataset_id": "dyzh-7eat",
            "mapping": "san_diego_county_permits",
        },
    ),
    "nj": dict(
        name="New Jersey (statewide)",
        state="NJ",
        level="state",
        timezone="America/New_York",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.nj.gov", "dataset_id": "w9se-dmra", "mapping": "nj_statewide_permits"},
    ),
    "neworleans": dict(
        name="New Orleans",
        state="LA",
        level="city",
        timezone="America/Chicago",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.nola.gov", "dataset_id": "nbcf-m6c2", "mapping": "new_orleans_permits"},
    ),
    "miamidade": dict(
        name="Miami-Dade County",
        state="FL",
        level="county",
        timezone="America/New_York",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/miamidade_permit_data/FeatureServer/0",
            "mapping": "miami_dade_permits",
        },
    ),
    "mecklenburg": dict(
        name="Mecklenburg County",
        state="NC",
        level="county",
        timezone="America/New_York",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://meckgis.mecklenburgcountync.gov/server/rest/services/BuildingPermits/FeatureServer/0",
            "mapping": "mecklenburg_county_permits",
        },
    ),
    # Real HTML-scraping connector (no open-data API exists for this
    # jurisdiction) -- see app/connectors/html_scraper.py and BLOCKERS.md
    # for the legality/robots.txt/rate-limiting writeup.
    "annearundel": dict(
        name="Anne Arundel County",
        state="MD",
        level="county",
        timezone="America/New_York",
        source_system=SourceSystem.HTML_SCRAPER,
        source_config={"mapping": "anne_arundel_county_aca"},
    ),
    # --- Fourth data-gathering pass: national-breadth expansion (13 more
    # ArcGIS/Socrata jurisdictions across 12 new states + 3 more Accela
    # scraper agencies) -- see BLOCKERS.md for how each was found/verified. ---
    "minneapolis": dict(
        name="Minneapolis",
        state="MN",
        level="city",
        timezone="America/Chicago",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services.arcgis.com/afSMGVsC7QlRK1kZ/arcgis/rest/services/CCS_Permits/FeatureServer/0",
            "mapping": "minneapolis_permits",
        },
    ),
    "philadelphia": dict(
        name="Philadelphia",
        state="PA",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services6.arcgis.com/StPsG80YRtvnlCJ8/arcgis/rest/services/PERMITS_BuildingZoning_CPCDC/FeatureServer/66",
            "mapping": "philadelphia_permits",
        },
    ),
    "honolulu": dict(
        name="Honolulu",
        state="HI",
        level="city",
        timezone="Pacific/Honolulu",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.honolulu.gov", "dataset_id": "3fr8-2hnx", "mapping": "honolulu_permits"},
    ),
    "norfolk": dict(
        name="Norfolk",
        state="VA",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.norfolk.gov", "dataset_id": "fahm-yuh4", "mapping": "norfolk_permits"},
    ),
    "kansascity": dict(
        name="Kansas City",
        state="MO",
        level="city",
        timezone="America/Chicago",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.kcmo.org", "dataset_id": "ntw8-aacc", "mapping": "kansas_city_mo_permits"},
    ),
    "siouxfalls": dict(
        name="Sioux Falls",
        state="SD",
        level="city",
        timezone="America/Chicago",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://gis.siouxfalls.gov/arcgis/rest/services/Data/Community/MapServer/3",
            "mapping": "sioux_falls_permits",
        },
    ),
    "montgomerycountymd": dict(
        name="Montgomery County",
        state="MD",
        level="county",
        timezone="America/New_York",
        source_system=SourceSystem.SOCRATA,
        source_config={
            "domain": "data.montgomerycountymd.gov",
            "dataset_id": "xfxj-qszi",
            "mapping": "montgomery_county_md_permits",
        },
    ),
    "nashville": dict(
        name="Nashville",
        state="TN",
        level="city",
        timezone="America/Chicago",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services2.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services/Building_Permits_Issued_2/FeatureServer/0",
            "mapping": "nashville_permits",
        },
    ),
    "boise": dict(
        name="Boise",
        state="ID",
        level="city",
        timezone="America/Denver",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/Housing_OpenData/FeatureServer/0",
            "mapping": "boise_permits",
        },
    ),
    "atlanta": dict(
        name="Atlanta",
        state="GA",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services5.arcgis.com/5RxyIIJ9boPdptdo/arcgis/rest/services/AMS_BuildingPermits/FeatureServer/66",
            "mapping": "atlanta_permits",
        },
    ),
    "albuquerque": dict(
        name="Albuquerque",
        state="NM",
        level="city",
        timezone="America/Denver",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://coageo.cabq.gov/cabqgeo/rest/services/agis/City_Building_Permits/FeatureServer/0",
            "mapping": "albuquerque_permits",
        },
    ),
    "portland": dict(
        name="Portland",
        state="OR",
        level="city",
        timezone="America/Los_Angeles",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://www.portlandmaps.com/od/rest/services/COP_OpenData_PlanningDevelopment/MapServer/89",
            "mapping": "portland_permits",
        },
    ),
    "helena": dict(
        name="Helena",
        state="MT",
        level="city",
        timezone="America/Denver",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services1.arcgis.com/zy02xMI7T6QrPvfO/arcgis/rest/services/All_Building_Permits_Jan2019_Present/FeatureServer/9",
            "mapping": "helena_mt_permits",
        },
    ),
    "tampa": dict(
        name="Tampa",
        state="FL",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.HTML_SCRAPER,
        source_config={"mapping": "tampa_fl_aca"},
    ),
    "clarkcounty": dict(
        name="Clark County",
        state="NV",
        level="county",
        timezone="America/Los_Angeles",
        source_system=SourceSystem.HTML_SCRAPER,
        source_config={"mapping": "clark_county_nv_aca"},
    ),
    "kingcounty": dict(
        name="King County",
        state="WA",
        level="county",
        timezone="America/Los_Angeles",
        source_system=SourceSystem.HTML_SCRAPER,
        source_config={"mapping": "king_county_wa_aca"},
    ),
    # --- Fifth data-gathering pass: EXPANSION_PLAN.md Wave A (6 ArcGIS + 1
    # CKAN, all open-API) and Wave B (7 Accela agencies). Adds MI, KY, WI, CT,
    # IN as new states. Each source was queried live this pass before wiring;
    # see BLOCKERS.md §5g. ---
    "fortworth": dict(
        name="Fort Worth",
        state="TX",
        level="city",
        timezone="America/Chicago",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://mapit.fortworthtexas.gov/ags/rest/services/CIVIC/Permits/MapServer/0",
            "mapping": "fort_worth_permits",
        },
    ),
    "columbus": dict(
        name="Columbus",
        state="OH",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services1.arcgis.com/9yy6msODkIBzkUXU/arcgis/rest/services/Building_Permits/FeatureServer/0",
            "mapping": "columbus_permits",
        },
    ),
    "lasvegas": dict(
        name="Las Vegas",
        state="NV",
        level="city",
        timezone="America/Los_Angeles",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services1.arcgis.com/F1v0ufATbBQScMtY/arcgis/rest/services/OpenData_Building_Permits_/FeatureServer/0",
            "mapping": "las_vegas_permits",
        },
    ),
    "detroit": dict(
        name="Detroit",
        state="MI",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/bseed_building_permits/FeatureServer/0",
            "mapping": "detroit_permits",
        },
    ),
    "louisville": dict(
        name="Louisville Metro",
        state="KY",
        level="county",
        timezone="America/New_York",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://services1.arcgis.com/79kfd2K6fskCAkyg/arcgis/rest/services/active_construction_permits/FeatureServer/0",
            "mapping": "louisville_permits",
        },
    ),
    "tucson": dict(
        name="Tucson",
        state="AZ",
        level="city",
        timezone="America/Phoenix",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": "https://gis.tucsonaz.gov/public/rest/services/PublicMaps/PermitsCode/MapServer/85",
            "mapping": "tucson_permits",
        },
    ),
    "sanantonio": dict(
        name="San Antonio",
        state="TX",
        level="city",
        timezone="America/Chicago",
        source_system=SourceSystem.CKAN,
        source_config={"domain": "data.sanantonio.gov", "mapping": "san_antonio_permits"},
    ),
    # Wave B -- Accela Citizen Access agencies (reuse the generic scraper)
    "milwaukee": dict(
        name="Milwaukee",
        state="WI",
        level="city",
        timezone="America/Chicago",
        source_system=SourceSystem.HTML_SCRAPER,
        source_config={"mapping": "milwaukee_wi_aca"},
    ),
    "hartford": dict(
        name="Hartford",
        state="CT",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.HTML_SCRAPER,
        source_config={"mapping": "hartford_ct_aca"},
    ),
    "oakland": dict(
        name="Oakland",
        state="CA",
        level="city",
        timezone="America/Los_Angeles",
        source_system=SourceSystem.HTML_SCRAPER,
        source_config={"mapping": "oakland_ca_aca"},
    ),
    "santabarbara": dict(
        name="Santa Barbara County",
        state="CA",
        level="county",
        timezone="America/Los_Angeles",
        source_system=SourceSystem.HTML_SCRAPER,
        source_config={"mapping": "santa_barbara_county_ca_aca"},
    ),
    "polkcounty": dict(
        name="Polk County",
        state="FL",
        level="county",
        timezone="America/New_York",
        source_system=SourceSystem.HTML_SCRAPER,
        source_config={"mapping": "polk_county_fl_aca"},
    ),
    "leecounty": dict(
        name="Lee County",
        state="FL",
        level="county",
        timezone="America/New_York",
        source_system=SourceSystem.HTML_SCRAPER,
        source_config={"mapping": "lee_county_fl_aca"},
    ),
    "indianapolis": dict(
        name="Indianapolis",
        state="IN",
        level="city",
        timezone="America/Indiana/Indianapolis",
        source_system=SourceSystem.HTML_SCRAPER,
        source_config={"mapping": "indianapolis_in_aca"},
    ),
    # --- Sixth data-gathering pass: population-driven expansion beyond
    # EXPANSION_PLAN.md's original list. Adds South Carolina (Charleston) as a
    # new state; the rest are high-population cities/counties in already-covered
    # states (Boston, Orlando, Prince George's County MD). Each source was
    # queried live this pass before wiring (columns + sample rows); see
    # BLOCKERS.md §5h. San Joaquin County (SJCO) re-checked and still HTTP 503. ---
    "charleston": dict(
        name="Charleston",
        state="SC",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.ARCGIS,
        source_config={
            "service_url": (
                "https://services2.arcgis.com/tQaXW7Zb1Vphzvgd/arcgis/rest/services/"
                "New_Construction_Permits/FeatureServer/0"
            ),
            "mapping": "charleston_sc_permits",
        },
    ),
    "boston": dict(
        name="Boston",
        state="MA",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.CKAN,
        source_config={"domain": "data.boston.gov", "mapping": "boston_permits"},
    ),
    "orlando": dict(
        name="Orlando",
        state="FL",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.cityoforlando.net", "dataset_id": "ryhf-m453", "mapping": "orlando_permits"},
    ),
    "princegeorges": dict(
        name="Prince George's County",
        state="MD",
        level="county",
        timezone="America/New_York",
        source_system=SourceSystem.SOCRATA,
        source_config={
            "domain": "data.princegeorgescountymd.gov",
            "dataset_id": "weik-ttee",
            "mapping": "prince_georges_county_md_permits",
        },
    ),
    "somerville": dict(
        name="Somerville",
        state="MA",
        level="city",
        timezone="America/New_York",
        source_system=SourceSystem.SOCRATA,
        source_config={"domain": "data.somervillema.gov", "dataset_id": "vxgw-vmky", "mapping": "somerville_ma_permits"},
    ),
    "charlottecounty": dict(
        name="Charlotte County",
        state="FL",
        level="county",
        timezone="America/New_York",
        source_system=SourceSystem.HTML_SCRAPER,
        source_config={"mapping": "charlotte_county_fl_aca"},
    ),
}


def get_or_create_jurisdiction(db, key: str) -> Jurisdiction:
    cfg = DEMO_JURISDICTIONS[key]
    existing = db.query(Jurisdiction).filter(Jurisdiction.name == cfg["name"], Jurisdiction.state == cfg["state"]).one_or_none()
    if existing:
        return existing
    jurisdiction = Jurisdiction(**cfg)
    db.add(jurisdiction)
    db.commit()
    db.refresh(jurisdiction)
    return jurisdiction


def ingest_one(db, key: str, limit, score: bool, geocode: bool = True, enrich: bool = True, since=None) -> None:
    jurisdiction = get_or_create_jurisdiction(db, key)
    print(f"Ingesting live data for jurisdiction: {jurisdiction.name}, {jurisdiction.state} "
          f"(source_system={jurisdiction.source_system}, config={jurisdiction.source_config}, limit={limit})",
          flush=True)
    started = time.time()
    try:
        stats = run_ingest(db, jurisdiction, limit=limit, geocode_missing=geocode, enrich=enrich, since=since)
    except Exception as exc:
        print(f"  FAILED: {exc}", flush=True)
        # Same class of bug fixed in app/ingest.py's per-record loop:
        # without this, a failed commit for one jurisdiction leaves the
        # session in a "pending rollback" state that poisons every
        # subsequent jurisdiction in the same --all run.
        db.rollback()
        return
    elapsed = time.time() - started
    print(f"  Fetched={stats.fetched} Created={stats.created} Updated={stats.updated} "
          f"Unchanged={stats.unchanged} Errors={stats.errors} ({elapsed:.0f}s)", flush=True)
    if score:
        scored = compute_scores_for_permit_ids(db, stats.touched_permit_ids)
        print(f"  Computed scores for {scored} permit(s).", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jurisdiction", default="sf", choices=list(DEMO_JURISDICTIONS.keys()))
    parser.add_argument("--all", action="store_true", help="Ingest every demo jurisdiction in one run")
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Max records per source. Use 0 (or any value <= 0) for NO limit -- pull the whole feed.",
    )
    parser.add_argument("--no-score", action="store_true")
    parser.add_argument(
        "--no-geocode",
        action="store_true",
        help="Skip the per-address Census geocoder fallback (much faster; avoids hammering the free "
        "geocoder on large bulk pulls -- lat/lon still stored for sources that provide it directly).",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip per-property enrichment (FEMA/Census/assessor). Recommended for large bulk pulls to "
        "avoid hitting free external enrichment APIs tens of thousands of times; backfill later with "
        "scripts/backfill_enrichment.py.",
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Only fetch records dated within the last N days (the 'evergreen' daily-refresh mode). "
        "Socrata/ArcGIS filter server-side on their incremental date field; CKAN and sources without "
        "such a field re-scan and rely on idempotent upserts. Used by the daily Task Scheduler job.",
    )
    args = parser.parse_args()

    # A non-positive --limit means "no cap": the connectors treat limit=None
    # as "page until the feed is exhausted".
    limit = args.limit if args.limit and args.limit > 0 else None

    since = None
    if args.since_days and args.since_days > 0:
        since = datetime.now(timezone.utc) - timedelta(days=args.since_days)
        print(f"Incremental mode: only records since {since.isoformat()} (last {args.since_days} days)", flush=True)

    db = SessionLocal()
    try:
        keys = list(DEMO_JURISDICTIONS.keys()) if args.all else [args.jurisdiction]
        for key in keys:
            ingest_one(
                db,
                key,
                limit,
                score=not args.no_score,
                geocode=not args.no_geocode,
                enrich=not args.no_enrich,
                since=since,
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
