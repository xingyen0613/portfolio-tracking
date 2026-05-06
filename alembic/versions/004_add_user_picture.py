"""add picture column to users

Revision ID: 004
Revises: 003
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('picture', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('users', 'picture')
