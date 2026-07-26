"""
Production-scale bulk ingest driver.

Pulls a genuinely large volume from the open-API sources (Socrata / ArcGIS
/ CKAN), prioritizing the highest-record-count jurisdictions, to move the
local DB from a small dev sample (~6K rows) to real production-scale
volume (hundreds of thousands+).

Design choices (see BLOCKERS.md / README "scale-up"):
  * Geocoding and enrichment are OFF by default here. Synchronously
    geocoding/enriching hundreds of thousands of addresses would hammer the
    free Census/FEMA services and dominate runtime. Sources that publish
    lat/lon directly keep it; address-only sources can be backfilled later
    with scripts/backfill_enrichment.py. Scoring is also skipped for speed.
  * HTML-scraper (Accela) and FOIA sources are skipped: they are
    single-page / rate-limited by design (~10 rows) and don't scale.
  * Back-off/paging for 429s and large pages lives in the connectors.

Per-source caps below are tuned so one run finishes in a sane time while
still producing large real datasets. `None` means "pull the whole feed".

Usage:
    python scripts/scale_ingest.py                 # run the curated plan
    python scripts/scale_ingest.py --default-cap 3000
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.models import SourceSystem
from scripts.run_ingest import DEMO_JURISDICTIONS, ingest_one

# Per-source record caps. Highest-population / highest-record-count sources
# first (live-verified available volumes in comments). None => whole feed.
CAPS: dict[str, int | None] = {
    # --- priority big sources ---
    "orlando": 150000,       # 1.1M available
    "fortworth": 120000,     # 756K
    "columbus": 120000,      # 675K
    "boston": 120000,        # 657K
    "princegeorges": 120000,  # 461K
    "lasvegas": 100000,      # 435K
    # --- large, pull (near-)fully ---
    "sanantonio": None,      # ~130K
    "cook": 60000,           # 711K but only ~1% has an address
    "somerville": None,      # ~64K
    "detroit": None,         # ~46K
    "louisville": None,      # ~23K
    "tucson": None,          # ~19K
    "charleston": None,      # ~14K
    "nashville": 40000,
    "minneapolis": 40000,
}

# Any other open-API jurisdiction not listed above gets this cap (grows the
# older small-sample sources from ~60 to a few thousand real records each).
DEFAULT_CAP = 5000

# Source systems that don't scale (single-page scrapers / pushed FOIA data).
SKIP_SYSTEMS = {SourceSystem.HTML_SCRAPER, SourceSystem.FOIA_EMAIL, SourceSystem.MANUAL}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--default-cap", type=int, default=DEFAULT_CAP)
    parser.add_argument("--only", nargs="*", help="Restrict to these jurisdiction keys")
    args = parser.parse_args()

    keys = args.only or [
        k for k, cfg in DEMO_JURISDICTIONS.items() if cfg["source_system"] not in SKIP_SYSTEMS
    ]
    # Order: curated priority keys first (in CAPS order), then the rest.
    ordered = [k for k in CAPS if k in keys] + [k for k in keys if k not in CAPS]

    db = SessionLocal()
    overall_start = time.time()
    try:
        for i, key in enumerate(ordered, 1):
            cap = CAPS.get(key, args.default_cap)
            print(f"[{i}/{len(ordered)}] === {key} (cap={cap}) ===", flush=True)
            ingest_one(db, key, cap, score=False, geocode=False, enrich=False)
    finally:
        db.close()
    print(f"ALL DONE in {(time.time() - overall_start) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
