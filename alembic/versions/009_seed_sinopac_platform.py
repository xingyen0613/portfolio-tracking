"""seed sinopac platform

Revision ID: 009
Revises: 008
Create Date: 2026-05-11
"""
from alembic import op


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO platforms (name, display_name) VALUES
            ('sinopac', '永豐證券')
        ON CONFLICT (name) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM platforms WHERE name = 'sinopac'")
