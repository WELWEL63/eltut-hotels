"""add site_content style columns

Revision ID: f1e2d3c4b5a6
Revises: d1359aad31a6
Create Date: 2026-10-12

Adds 5 nullable style columns to site_content so the CMS can store
per-key font, size, weight, colour, and alignment overrides.

All columns are nullable - existing rows and templates are untouched.
"""

from alembic import op
import sqlalchemy as sa


revision = "f1e2d3c4b5a6"
down_revision = "d1359aad31a6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("site_content", sa.Column("font_family", sa.String(length=80), nullable=True))
    op.add_column("site_content", sa.Column("font_size",   sa.String(length=16), nullable=True))
    op.add_column("site_content", sa.Column("font_weight", sa.String(length=8),  nullable=True))
    op.add_column("site_content", sa.Column("color",       sa.String(length=16), nullable=True))
    op.add_column("site_content", sa.Column("align",       sa.String(length=12), nullable=True))


def downgrade():
    op.drop_column("site_content", "align")
    op.drop_column("site_content", "color")
    op.drop_column("site_content", "font_weight")
    op.drop_column("site_content", "font_size")
    op.drop_column("site_content", "font_family")