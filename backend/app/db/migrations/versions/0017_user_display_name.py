"""add display_name to users

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("display_name", sa.String(128), nullable=True))


def downgrade():
    op.drop_column("users", "display_name")
