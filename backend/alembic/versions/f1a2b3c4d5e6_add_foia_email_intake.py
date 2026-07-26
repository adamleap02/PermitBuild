"""add FOIA email intake: permits.needs_review + processed_email_attachments

Revision ID: f1a2b3c4d5e6
Revises: e083159d68d8
Create Date: 2026-07-26 09:30:00.000000

Adds the schema needed by the FOIA-reply email-intake pipeline
(app/foia_intake/):

  * permits.needs_review -- flags heuristically-parsed, lower-confidence
    records (from FOIA-email CSV/XLSX/PDF attachments) so they don't
    masquerade as vetted API data. Defaults False; every existing
    connector is unaffected.
  * processed_email_attachments -- idempotency ledger of every
    (Gmail message id, attachment part id) the poller has handled.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e083159d68d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("permits", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    op.create_table(
        "processed_email_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.String(length=128), nullable=False),
        sa.Column("attachment_id", sa.String(length=512), nullable=False),
        sa.Column("target_key", sa.String(length=64), nullable=True),
        sa.Column("from_address", sa.String(length=255), nullable=True),
        sa.Column("filename", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("records_created", sa.Integer(), nullable=False),
        sa.Column("records_updated", sa.Integer(), nullable=False),
        sa.Column("records_unchanged", sa.Integer(), nullable=False),
        sa.Column("records_flagged", sa.Integer(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "attachment_id", name="uq_processed_email_attachment"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("processed_email_attachments")
    with op.batch_alter_table("permits", schema=None) as batch_op:
        batch_op.drop_column("needs_review")
