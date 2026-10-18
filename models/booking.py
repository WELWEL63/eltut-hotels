"""models/booking.py - reservations."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base, TimestampMixin


# ─── Product types ──────────────────────────────────────────────────
PRODUCT_TYPE_ACTIVITY = "activity"
PRODUCT_TYPE_HOTEL = "hotel"
PRODUCT_TYPE_PACKAGE = "package"
PRODUCT_TYPE_FLIGHT = "flight"

VALID_PRODUCT_TYPES = (
    PRODUCT_TYPE_ACTIVITY,
    PRODUCT_TYPE_HOTEL,
    PRODUCT_TYPE_PACKAGE,
)


# ─── Booking status values ──────────────────────────────────────────
STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
STATUS_CANCELLED = "cancelled"
STATUS_COMPLETED = "completed"
STATUS_REFUNDED = "refunded"

VALID_BOOKING_STATUSES = (
    STATUS_PENDING,
    STATUS_CONFIRMED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_REFUNDED,
)

DEFAULT_BOOKING_STATUS = STATUS_PENDING


class Booking(Base, TimestampMixin):
    """A single reservation of a product.

    MULTI-ROOM UPGRADE (hotel bookings only)
        `travellers_infants` records the infant count (age < 2) so the
        booking headline matches the new age-band rules. Infants do NOT
        count toward room occupancy.
        `rooms` exposes the BookingRoom child rows (max 3 per booking).
        For hotel bookings, `product_id` continues to hold the FIRST
        room id for backward compatibility; `booking.rooms` is the
        source of truth when present.
    """

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    guest_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    guest_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    guest_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)

    product_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DEFAULT_BOOKING_STATUS, index=True
    )

    check_in_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    check_out_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    travellers_adults: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    travellers_children: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    travellers_infants: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    special_requests: Mapped[str | None] = mapped_column(Text, nullable=True)

    how_heard: Mapped[str | None] = mapped_column(String(60), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(40), nullable=True)

    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notification_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    notification_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    items: Mapped[list["BookingItem"]] = relationship(  # noqa: F821
        "BookingItem", backref="booking",
        cascade="all, delete-orphan", order_by="BookingItem.id",
    )
    travellers: Mapped[list["BookingTraveller"]] = relationship(  # noqa: F821
        "BookingTraveller", backref="booking",
        cascade="all, delete-orphan", order_by="BookingTraveller.sort_order",
    )
    rooms: Mapped[list["BookingRoom"]] = relationship(  # noqa: F821
        "BookingRoom", backref="booking",
        cascade="all, delete-orphan", order_by="BookingRoom.room_index",
    )
    status_history: Mapped[list["BookingStatusHistory"]] = relationship(  # noqa: F821
        "BookingStatusHistory", backref="booking",
        cascade="all, delete-orphan", order_by="BookingStatusHistory.created_at",
    )
