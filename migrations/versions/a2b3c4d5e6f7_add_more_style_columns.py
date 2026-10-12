"""add more site_content style columns

Revision ID: a2b3c4d5e6f7
Revises: f1e2d3c4b5a6
Create Date: 2026-10-12

Adds 4 more nullable style columns to site_content: letter_spacing,
line_height, text_shadow, text_transform. Enables the full signature-
preset system for the CMS.

All columns are nullable - existing rows and templates are untouched.
"""

from alembic import op
import sqlalchemy as sa


revision = "a2b3c4d5e6f7"
down_revision = "f1e2d3c4b5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("site_content", sa.Column("letter_spacing", sa.String(length=16), nullable=True))
    op.add_column("site_content", sa.Column("line_height",    sa.String(length=8),  nullable=True))
    op.add_column("site_content", sa.Column("text_shadow",    sa.String(length=32), nullable=True))
    op.add_column("site_content", sa.Column("text_transform", sa.String(length=16), nullable=True))


def downgrade():
    op.drop_column("site_content", "text_transform")
    op.drop_column("site_content", "text_shadow")
    op.drop_column("site_content", "line_height")
    op.drop_column("site_content", "letter_spacing")