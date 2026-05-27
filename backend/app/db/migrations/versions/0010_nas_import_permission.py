"""add can_import_from_nas to users

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("can_import_from_nas", sa.Boolean(), nullable=False, server_default="false"))


def downgrade():
    op.drop_column("users", "can_import_from_nas")
