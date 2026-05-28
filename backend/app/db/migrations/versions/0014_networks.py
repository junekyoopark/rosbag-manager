"""add networks table, network_id on robots, drop live_config

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "networks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("scan_subnet", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.add_column("robots", sa.Column("network_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_robots_network_id", "robots", "networks", ["network_id"], ["id"],
        ondelete="SET NULL",
    )
    op.drop_table("live_config")


def downgrade():
    op.drop_constraint("fk_robots_network_id", "robots", type_="foreignkey")
    op.drop_column("robots", "network_id")
    op.drop_table("networks")
    op.create_table(
        "live_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scan_subnet", sa.String(64), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
