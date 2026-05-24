"""add nas_config table and can_upload_to_nas user privilege

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "nas_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("dsm_url", sa.String(512), nullable=True),
        sa.Column("username", sa.String(128), nullable=True),
        sa.Column("encrypted_password", sa.Text(), nullable=True),
        sa.Column("upload_path", sa.String(512), nullable=False, server_default="/rosbags"),
        sa.Column("verify_ssl", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("can_upload_to_nas", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade():
    op.drop_column("users", "can_upload_to_nas")
    op.drop_table("nas_config")
