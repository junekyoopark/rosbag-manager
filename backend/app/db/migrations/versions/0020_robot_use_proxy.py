"""Add use_proxy to robots table

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('robots', sa.Column('use_proxy', sa.Boolean(), nullable=False, server_default='true'))


def downgrade():
    op.drop_column('robots', 'use_proxy')
