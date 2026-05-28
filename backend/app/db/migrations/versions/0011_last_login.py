"""add last login fields to users

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("last_login_ip", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("last_login_ua", sa.String(512), nullable=True))


def downgrade():
    op.drop_column("users", "last_login_ua")
    op.drop_column("users", "last_login_ip")
    op.drop_column("users", "last_login_at")
