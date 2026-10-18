"""
models/room_rate.py
───────────────────
Seasonal rate windows for a room.

The source CSV (Egypt.csv) lists multiple price rows per room, each
valid over a date range. This table preserves that: one row per
(room, valid_from, valid_to) window, so the pricing service can pick
the correct price for any requested date.

MULTI-ROOM UPGRADE
    `infant_price` was added alongside adult/child so the pricing
    service can distinguish:
        infant (age < 2)       -> infant_price
        child  (2 <= age < 13) -> child_price
        adult  (age >= 13)     -> adult_price
    Infants do not count toward room occupancy (cot, not a bed).
    No CHECK on the new column (SQLite-safe ADD COLUMN).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base, TimestampMixin


class RoomRate(Base, TimestampMixin):
    """One seasonal price window for a room."""

    __tablename__ = "room_rates"
    __table_args__ = (
        CheckConstraint("adult_price >= 0", name="adult_price_check"),
        CheckConstraint("child_price >= 0", name="child_price_check"),
        # Accept either a normal window (valid_to >= valid_from) or a
        # year-end wrap of up to ~180 days. The source CSV has
        # Christmas -> New Year rates that cross the year boundary,
        # e.g. 2027-12-24 -> 2027-01-03, which are legitimate.
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL "
            "OR valid_to >= valid_from "
            "OR (valid_from - valid_to) <= 180",
            name="validity_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    adult_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    child_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    infant_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="GBP", server_default="GBP"
    )

    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    room: Mapped["Room"] = relationship(back_populates="rates")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RoomRate id={self.id} room_id={self.room_id} "
            f"{self.valid_from}->{self.valid_to} adult={self.adult_price}>"
        )
