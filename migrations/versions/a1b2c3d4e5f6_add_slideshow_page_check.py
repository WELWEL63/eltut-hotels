"""add slideshow to site_content page check

Revision ID: a1b2c3d4e5f6
Revises: 3656e6880fd2
Create Date: 2026-10-10

WHY THIS MIGRATION IS HAND-WRITTEN
    Alembic does not autogenerate changes to CHECK constraint text.
    The `page IN (...)` list only exists as a constraint expression in
    the DB, so changing it means dropping + recreating the constraint
    manually. Same pattern used for the room_rates validity check in
    Step 11.5.

CONSTRAINT NAMING
    We pass the suffix-only name `page_check` to
    op.create_check_constraint(). The naming_convention applied at
    metadata level prepends `ck_site_content_`, producing the final
    DB name `ck_site_content_page_check`. Matching that convention
    keeps autogenerate honest in the future.
"""

from __future__ import annotations

from alembic import op


revision = "a1b2c3d4e5f6"
down_revision = "3656e6880fd2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SUFFIX-ONLY name — naming_convention adds ck_site_content_ prefix.
    # Passing the full prefixed name would double-prefix and fail.
    op.drop_constraint(
        "page_check",
        "site_content",
        type_="check",
    )
    op.create_check_constraint(
        "page_check",
        "site_content",
        "page IN ('home','about','contact','footer','global','slideshow')",
    )


def downgrade() -> None:
    # SUFFIX-ONLY name — naming_convention adds ck_site_content_ prefix.
    # Passing the full prefixed name would double-prefix and fail.
    op.drop_constraint(
        "page_check",
        "site_content",
        type_="check",
    )
    op.create_check_constraint(
        "page_check",
        "site_content",
        "page IN ('home','about','contact','footer','global')",
    )
