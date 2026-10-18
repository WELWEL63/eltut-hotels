"""add multi-room support

Adds:
  - rooms.max_adults / rooms.max_children (nullable; split occupancy)
  - room_rates.infant_price (NOT NULL, default 0.00)
  - bookings.travellers_infants (NOT NULL, default 0)
  - booking_rooms table (multi-room hotel bookings, max 3 per booking)

Downstream logic lives in:
  - services/hotel_pricing_service.py  (age-aware per-room pricing)
  - services/hotel_capacity_service.py ("you need N rooms")
  - blueprints/public/hotel_routes.py  (multi-room UI)

Revision ID: add_multi_room_support
Revises:    b1a2c3d4e5f6  (add_is_bookable_to_destinations)
"""

from alembic import op
import sqlalchemy as sa


revision = "add_multi_room_support"
down_revision = "b1a2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── rooms: adult/child caps ─────────────────────────────────
    op.add_column("rooms", sa.Column("max_adults", sa.Integer(), nullable=True))
    op.add_column("rooms", sa.Column("max_children", sa.Integer(), nullable=True))

    # Backfill max_adults from max_occupancy (legacy fallback rule);
    # max_children stays NULL until an admin sets it (service layer
    # treats NULL as 0).
    op.execute(
        "UPDATE rooms SET max_adults = max_occupancy "
        "WHERE max_adults IS NULL"
    )

    # ── room_rates: infant price ────────────────────────────────
    op.add_column(
        "room_rates",
        sa.Column(
            "infant_price",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="0.00",
        ),
    )

    # ── bookings: infant count ──────────────────────────────────
    op.add_column(
        "bookings",
        sa.Column(
            "travellers_infants",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # ── booking_rooms: new table ────────────────────────────────
    op.create_table(
        "booking_rooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "booking_id",
            sa.Integer(),
            sa.ForeignKey("bookings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "room_id",
            sa.Integer(),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rate_id",
            sa.Integer(),
            sa.ForeignKey("room_rates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "room_index", sa.Integer(), nullable=False, server_default="1",
        ),
        sa.Column(
            "adults", sa.Integer(), nullable=False, server_default="1",
        ),
        sa.Column(
            "children", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column(
            "infants", sa.Integer(), nullable=False, server_default="0",
        ),
        sa.Column("child_ages", sa.JSON(), nullable=True),
        sa.Column(
            "line_total",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "currency", sa.String(3), nullable=False, server_default="USD",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "room_index BETWEEN 1 AND 3", name="ck_booking_rooms_room_index_check",
        ),
        sa.CheckConstraint(
            "adults >= 0", name="ck_booking_rooms_adults_check",
        ),
        sa.CheckConstraint(
            "children >= 0", name="ck_booking_rooms_children_check",
        ),
        sa.CheckConstraint(
            "infants >= 0", name="ck_booking_rooms_infants_check",
        ),
        sa.CheckConstraint(
            "line_total >= 0", name="ck_booking_rooms_line_total_check",
        ),
    )
    op.create_index(
        "ix_booking_rooms_booking_id", "booking_rooms", ["booking_id"],
    )
    op.create_index(
        "ix_booking_rooms_room_id", "booking_rooms", ["room_id"],
    )
    op.create_index(
        "ix_booking_rooms_rate_id", "booking_rooms", ["rate_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_booking_rooms_rate_id", table_name="booking_rooms")
    op.drop_index("ix_booking_rooms_room_id", table_name="booking_rooms")
    op.drop_index("ix_booking_rooms_booking_id", table_name="booking_rooms")
    op.drop_table("booking_rooms")

    op.drop_column("bookings", "travellers_infants")
    op.drop_column("room_rates", "infant_price")

    op.drop_column("rooms", "max_children")
    op.drop_column("rooms", "max_adults")
