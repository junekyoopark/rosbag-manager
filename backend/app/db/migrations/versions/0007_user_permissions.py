"""add can_delete_own to users

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("can_delete_own", sa.Boolean(), nullable=False, server_default="false"))


def downgrade():
    op.drop_column("users", "can_delete_own")
