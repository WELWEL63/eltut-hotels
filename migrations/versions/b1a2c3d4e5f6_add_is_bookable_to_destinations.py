"""Add is_bookable flag to destinations.

Revision ID: b1a2c3d4e5f6
Revises: 3e83e7b5d1ce
Create Date: 2026-10-16

Reversible. Customers only see packages whose destination has
is_bookable=True. Defaults to True so existing behaviour is unchanged
until an admin explicitly disables a destination.
"""
from alembic import op
import sqlalchemy as sa


revision = "b1a2c3d4e5f6"
down_revision = "3e83e7b5d1ce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "destinations",
        sa.Column(
            "is_bookable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("destinations", "is_bookable")