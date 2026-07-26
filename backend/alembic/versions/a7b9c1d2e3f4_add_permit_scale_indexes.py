"""add scale indexes on permits (issue_date, latitude, longitude, property_id)

Revision ID: a7b9c1d2e3f4
Revises: f1a2b3c4d5e6
Create Date: 2026-07-26 12:00:00.000000

Adds secondary indexes needed for the platform to stay responsive as the
permits table grows from a small dev sample (~6K rows) to real
production-scale volume (hundreds of thousands+):

  * ix_permits_issue_date   -- /permits and /export filter/sort by date
  * ix_permits_latitude     -- bounding-box / map viewport spatial filters
  * ix_permits_longitude       (the naive pre-PostGIS path -- BLOCKERS.md §1)
  * ix_permits_property_id  -- permit -> property joins

The hot ingest-upsert lookup (jurisdiction_id, permit_number) is already
covered by the existing uq_permit_jurisdiction_number unique index, and
the version-history lookup by uq_permit_version_number, so no new index is
needed for those.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a7b9c1d2e3f4"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_permits_issue_date", "permits", ["issue_date"], unique=False)
    op.create_index("ix_permits_latitude", "permits", ["latitude"], unique=False)
    op.create_index("ix_permits_longitude", "permits", ["longitude"], unique=False)
    op.create_index("ix_permits_property_id", "permits", ["property_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_permits_property_id", table_name="permits")
    op.drop_index("ix_permits_longitude", table_name="permits")
    op.drop_index("ix_permits_latitude", table_name="permits")
    op.drop_index("ix_permits_issue_date", table_name="permits")
