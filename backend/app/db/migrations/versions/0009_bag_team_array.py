"""change bags.team from string to text array

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("bags", "team")
    op.add_column("bags", sa.Column("team", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("bags", "team")
    op.add_column("bags", sa.Column("team", sa.String(64), nullable=True))
