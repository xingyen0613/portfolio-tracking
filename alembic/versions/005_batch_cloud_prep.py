"""batch cloud prep: add payload_json to raw_payloads, add user_connectors

Revision ID: 005
Revises: 004
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('raw_payloads',
        sa.Column('payload_json', postgresql.JSONB, nullable=True))


def downgrade():
    op.drop_column('raw_payloads', 'payload_json')
