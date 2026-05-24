"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2025-05-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("bag_format", sa.String(16), nullable=False),
        sa.Column("upload_path", sa.Text(), nullable=False),
        sa.Column("rrd_path", sa.Text()),
        sa.Column("rrd_url", sa.Text()),
        sa.Column("thumbnail_path", sa.Text()),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("rrd_size_bytes", sa.BigInteger()),
        sa.Column("duration_sec", sa.Float()),
        sa.Column("start_time_ns", sa.BigInteger()),
        sa.Column("end_time_ns", sa.BigInteger()),
        sa.Column("message_count", sa.BigInteger()),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_bags_status", "bags", ["status"])
    op.create_index("idx_bags_created_at", "bags", [sa.text("created_at DESC")])
    op.create_index("idx_bags_tags", "bags", ["tags"], postgresql_using="gin")

    op.create_table(
        "conversion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bag_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bags.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("celery_task_id", sa.String(255), unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("progress_pct", sa.SmallInteger(), server_default="0"),
        sa.Column("current_step", sa.String(128)),
        sa.Column("error_message", sa.Text()),
        sa.Column("worker_hostname", sa.String(255)),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_jobs_bag_id", "conversion_jobs", ["bag_id"])
    op.create_index("idx_jobs_status", "conversion_jobs", ["status"])

    op.create_table(
        "topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "bag_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bags.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("msg_type", sa.String(256), nullable=False),
        sa.Column("message_count", sa.BigInteger()),
        sa.Column("frequency_hz", sa.Float()),
        sa.Column("serialization_format", sa.String(32)),
    )
    op.create_index("idx_topics_bag_id", "topics", ["bag_id"])
    op.create_index("idx_topics_name", "topics", ["name"])
    op.create_index("idx_topics_msg_type", "topics", ["msg_type"])


def downgrade() -> None:
    op.drop_table("topics")
    op.drop_table("conversion_jobs")
    op.drop_table("bags")
