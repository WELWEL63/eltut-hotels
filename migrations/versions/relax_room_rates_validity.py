"""Manual migration: relax ck_room_rates_validity_check.

Alembic autogenerate does not detect CHECK constraint text changes, so
this migration is written by hand.

NAMING NOTE
    Because Base.metadata applies a naming convention
    (ck_%(table_name)s_%(constraint_name)s), the constraint name passed
    here is the SUFFIX only ("validity_check"). Alembic adds the
    "ck_room_rates_" prefix, producing the physical name
    ck_room_rates_validity_check.
"""

from alembic import op
import sqlalchemy as sa


revision = "relax_room_rates_validity"
down_revision = "6063bba994dc"
branch_labels = None
depends_on = None


def upgrade():
    # Suffix-only name — naming convention adds "ck_room_rates_"
    op.drop_constraint("validity_check", "room_rates", type_="check")
    op.create_check_constraint(
        "validity_check",
        "room_rates",
        "valid_to IS NULL OR valid_from IS NULL "
        "OR valid_to >= valid_from "
        "OR (valid_from - valid_to) <= 180",
    )


def downgrade():
    op.drop_constraint("validity_check", "room_rates", type_="check")
    op.create_check_constraint(
        "validity_check",
        "room_rates",
        "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
    )
