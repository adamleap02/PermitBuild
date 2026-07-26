import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.models import Jurisdiction, Permit

db = SessionLocal()
for j in db.query(Jurisdiction).order_by(Jurisdiction.id).all():
    permits = db.query(Permit).filter(Permit.jurisdiction_id == j.id).order_by(Permit.id.desc()).limit(2).all()
    print(f"\n=== {j.name}, {j.state} ({j.source_system}) — {len(permits)} shown, total in DB: "
          f"{db.query(Permit).filter(Permit.jurisdiction_id == j.id).count()} ===")
    for p in permits:
        print(f"  #{p.permit_number} | type={p.permit_type!r} | addr={p.property_address!r} | "
              f"cost={p.estimated_cost} | lat/lon=({p.latitude}, {p.longitude}) | status={p.status!r}")

db.close()
