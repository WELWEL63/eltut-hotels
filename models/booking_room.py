"""
models/booking_room.py
──────────────────────
One room inside a multi-room hotel booking.

A hotel booking can now contain 1–3 rooms (Room 1 / Room 2 / Room 3).
Each row records which room was chosen, which rate window was used, how
many adults/children/infants sleep there, and the child ages as a JSON
snapshot. That is what lets a family of 4 adults + 2 children be split
across two rooms with different guest counts, and lets pricing be
computed per room instead of only for the whole booking.

DESIGN NOTES
    - `booking_id` REQUIRED; CASCADEs with the booking.
    - `room_id` REQUIRED; CASCADEs with the room (a deleted room cannot
      leave orphan room lines behind).
    - `room_index` is 1..3. Enforced by CHECK and by the service layer.
    - `rate_id` is OPTIONAL. Null means "use the room's base price /
      no matching seasonal window at booking time".
    - Guest counts are per-room, NOT per-booking. The booking-level
      travellers_* fields remain the headline totals (useful for
      reports) and are recomputed by the booking service.
    - `child_ages` stores a JSON list of integer ages, e.g. [5, 9].
      JSON keeps the schema simple and lets pricing/services read ages
      without a separate child table. Ages are snapshotted at booking
      time (same reasoning as BookingTraveller.age_at_booking).
    - `line_total` is a NUMERIC(12,2) snapshot of the room's price for
      this stay (rate * nights, plus per-room child/infant supplements
      as computed by hotel_pricing_service).
    - No TimestampMixin needed beyond created_at/updated_at? We DO use
      TimestampMixin for auditability (same as BookingItem).

WHY NO `booking` RELATIONSHIP HERE
    The reverse side is declared on Booking.rooms (backref="booking"),
    so SQLAlchemy creates `.booking` implicitly. Declaring it here too
    would collide.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, TimestampMixin


# ─── Constants ─────────────────────────────────────────────────────
ROOM_INDEX_MIN: int = 1
ROOM_INDEX_MAX: int = 3


class BookingRoom(Base, TimestampMixin):
    """
    One room inside a hotel booking.

    Columns
    -------
    id           : surrogate PK
    booking_id   : REQUIRED FK to bookings
    room_id      : REQUIRED FK to rooms
    rate_id      : optional FK to room_rates (which window was used)
    room_index   : 1..3 (which "Room 1/2/3" slot this is)
    adults       : adults assigned to this room
    children     : children (2..12) assigned to this room
    infants      : infants (< 2) assigned to this room (not counted
                   toward occupancy)
    child_ages   : JSON list of integer ages, or NULL when no children
    line_total   : NUMERIC(12,2) snapshot; total for this room for stay
    currency     : CHAR(3), snapshot
    created_at / updated_at : from TimestampMixin
    """

    __tablename__ = "booking_rooms"
    __table_args__ = (
        CheckConstraint(
            "room_index BETWEEN 1 AND 3",
            name="room_index_check",
        ),
        CheckConstraint("adults >= 0", name="adults_check"),
        CheckConstraint("children >= 0", name="children_check"),
        CheckConstraint("infants >= 0", name="infants_check"),
        CheckConstraint("line_total >= 0", name="line_total_check"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    rate_id: Mapped[int | None] = mapped_column(
        ForeignKey("room_rates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    room_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    adults: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    children: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    infants: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    child_ages: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)

    line_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        for key in ("currency",):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        if not kwargs.get("currency"):
            kwargs["currency"] = "USD"

        kwargs.setdefault("room_index", 1)
        kwargs.setdefault("adults", 1)
        kwargs.setdefault("children", 0)
        kwargs.setdefault("infants", 0)
        kwargs.setdefault("line_total", Decimal("0.00"))

        # Sanitise child_ages: keep only ints, drop non-int values.
        ages = kwargs.get("child_ages")
        if ages is not None:
            if not isinstance(ages, list):
                ages = [ages]
            cleaned: list[int] = []
            for a in ages:
                try:
                    cleaned.append(int(a))
                except (TypeError, ValueError):
                    continue
            kwargs["child_ages"] = cleaned

        super().__init__(**kwargs)

    # ── Convenience ───────────────────────────────────────────────
    @property
    def occupancy_bed_count(self) -> int:
        """Adults + children; infants excluded (cot, not a bed)."""
        return int(self.adults or 0) + int(self.children or 0)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<BookingRoom id={self.id} booking_id={self.booking_id} "
            f"room_id={self.room_id} idx={self.room_index} "
            f"a={self.adults} c={self.children} i={self.infants}>"
        )
