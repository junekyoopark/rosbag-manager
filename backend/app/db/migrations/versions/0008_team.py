"""add team to users and bags

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "teams",
        sa.Column("name", sa.String(64), primary_key=True),
    )
    op.add_column("users", sa.Column("team", sa.String(64), nullable=True))
    op.add_column("bags", sa.Column("team", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("bags", "team")
    op.drop_column("users", "team")
    op.drop_table("teams")
