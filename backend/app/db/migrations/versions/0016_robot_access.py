"""add robot_access table and added_by_id to robots

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("robots", sa.Column("added_by_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_robots_added_by_id", "robots", "users", ["added_by_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "robot_access",
        sa.Column("robot_id", sa.Integer(), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("granted_by_id", UUID(as_uuid=True), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["robot_id"], ["robots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("robot_id", "user_id"),
    )


def downgrade():
    op.drop_table("robot_access")
    op.drop_constraint("fk_robots_added_by_id", "robots", type_="foreignkey")
    op.drop_column("robots", "added_by_id")
