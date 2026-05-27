"""add frame_count to bags

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("bags", sa.Column("frame_count", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("bags", "frame_count")
