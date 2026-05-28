"""add live_config table

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "live_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scan_subnet", sa.String(64), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO live_config (id, scan_subnet) VALUES (1, '')")


def downgrade():
    op.drop_table("live_config")
