"""Add layout_id to robots table

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-29

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "robots",
        sa.Column("layout_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_robots_layout_id",
        "robots",
        "lichtblick_layouts",
        ["layout_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_robots_layout_id", "robots", type_="foreignkey")
    op.drop_column("robots", "layout_id")
