"""add published flag to bags

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bags",
        sa.Column("published", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade():
    op.drop_column("bags", "published")
