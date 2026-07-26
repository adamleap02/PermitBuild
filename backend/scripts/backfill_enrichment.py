"""
Backfills free property/parcel enrichment (Census ACS tract lookup, FEMA
flood zone, Cook County Assessor by PIN) for every Property already in
the local database -- for permits ingested before app/enrichment/service.py
existed, or any time you want to (re-)run enrichment in bulk.

Going forward, new ingest runs enrich automatically (see app/ingest.py's
`enrich=True` default) -- this script is for one-time backfill of
already-ingested data plus periodic re-runs with --force if enrichment
logic changes.

Usage:
    python scripts/backfill_enrichment.py                # enrich everything not yet enriched
    python scripts/backfill_enrichment.py --force         # re-enrich everything, even if already done
    python scripts/backfill_enrichment.py --limit 50      # cap how many properties to process
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.enrichment.service import enrich_property
from app.models import Property


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-enrich properties even if already enriched")
    parser.add_argument("--limit", type=int, default=None, help="Max number of properties to process")
    parser.add_argument("--delay", type=float, default=0.2, help="Seconds to sleep between properties (be polite)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(Property)
        if not args.force:
            # Only properties with at least a coordinate or a parcel
            # number are candidates for any enrichment source at all.
            query = query.filter(
                (Property.latitude.isnot(None)) | (Property.parcel_number.isnot(None))
            )
        if args.limit:
            query = query.limit(args.limit)
        properties = query.all()

        print(f"Backfilling enrichment for {len(properties)} propert{'y' if len(properties) == 1 else 'ies'} "
              f"(force={args.force})...")

        counts = {"fema_flood_zone": 0, "census_tract": 0, "census_acs": 0, "cook_county_assessor": 0}
        for i, prop in enumerate(properties, 1):
            try:
                summary = enrich_property(db, prop, force=args.force)
            except Exception as exc:
                print(f"  [{i}/{len(properties)}] property_id={prop.id} FAILED: {exc}")
                continue
            for key in counts:
                if summary.get(key):
                    counts[key] += 1
            if i % 25 == 0 or i == len(properties):
                db.commit()
                print(f"  [{i}/{len(properties)}] committed. Running totals: {counts}")
            time.sleep(args.delay)

        db.commit()
        print(f"Done. Final totals: {counts}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
