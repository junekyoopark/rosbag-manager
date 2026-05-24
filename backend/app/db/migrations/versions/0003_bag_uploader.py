"""add uploaded_by_id to bags

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bags",
        sa.Column("uploaded_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade():
    op.drop_column("bags", "uploaded_by_id")
