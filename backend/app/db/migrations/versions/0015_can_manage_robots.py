"""add can_manage_robots to users

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("can_manage_robots", sa.Boolean(), nullable=False, server_default="false"))


def downgrade():
    op.drop_column("users", "can_manage_robots")
