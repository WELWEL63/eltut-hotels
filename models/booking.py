"""
models/booking.py
─────────────────
The bookings table — the transactional heart of the platform.

One row per reservation, regardless of product type. The product is
identified polymorphically:

    product_type  IN ('activity', 'hotel', 'package')
    product_id    INTEGER

There is deliberately NO foreign key on product_id: SQL cannot FK a
column whose target table varies by row. Integrity is enforced by:
    1. A CHECK constraint on product_type.
    2. A service-layer guard that verifies the product exists at booking
       time.
    3. The convention that products are never hard-deleted — every
       product table carries an `is_active` flag for soft-disable.

DESIGN NOTES
    - `reference` is UNIQUE and human-friendly. Used in emails and URLs.
    - `user_id` is NULLABLE — guest checkout is supported.
    - Dates live HERE, never on products. Hotel/package use
      check_in_date / check_out_date; activities use activity_date.
    - `total_amount` is snapshotted at booking time.
    - Bookings are never deleted. Cancellation sets status + cancelled_at
      + cancellation_reason.

RELATIONSHIPS
    - `items` uses backref="booking" so BookingItem.booking exists too.
    - `travellers` uses backref="booking" so BookingTraveller.booking
      exists too.
    - Neither relationship uses order_by referencing another class, so
      SQLAlchemy never needs BookingItem/BookingTraveller to be imported
      first just to configure this mapper. Ordering is done in the
      service layer where needed.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base, TimestampMixin


# ─── Constants ─────────────────────────────────────────────────────
PRODUCT_TYPE_ACTIVITY: str = "activity"
PRODUCT_TYPE_HOTEL: str = "hotel"
PRODUCT_TYPE_PACKAGE: str = "package"

VALID_PRODUCT_TYPES: tuple[str, ...] = (
    PRODUCT_TYPE_ACTIVITY,
    PRODUCT_TYPE_HOTEL,
    PRODUCT_TYPE_PACKAGE,
)

STATUS_PENDING: str = "pending"
STATUS_CONFIRMED: str = "confirmed"
STATUS_CANCELLED: str = "cancelled"
STATUS_COMPLETED: str = "completed"
STATUS_REFUNDED: str = "refunded"

VALID_BOOKING_STATUSES: tuple[str, ...] = (
    STATUS_PENDING,
    STATUS_CONFIRMED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_REFUNDED,
)
DEFAULT_BOOKING_STATUS: str = STATUS_PENDING


class Booking(Base, TimestampMixin):
    """A reservation — see module docstring for design notes."""

    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(
            "product_type IN ('activity','hotel','package')",
            name="product_type_check",
        ),
        CheckConstraint(
            "status IN ('pending','confirmed','cancelled','completed','refunded')",
            name="status_check",
        ),
        CheckConstraint("travellers_adults >= 0", name="adults_check"),
        CheckConstraint("travellers_children >= 0", name="children_check"),
        CheckConstraint("total_amount >= 0", name="total_amount_check"),
        CheckConstraint(
            "check_out_date IS NULL OR check_in_date IS NULL "
            "OR check_out_date >= check_in_date",
            name="stay_range_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    reference: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False, index=True
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    guest_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    guest_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    guest_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)

    product_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_BOOKING_STATUS,
        server_default=DEFAULT_BOOKING_STATUS,
        index=True,
    )

    check_in_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    check_out_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    activity_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    travellers_adults: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    travellers_children: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )

    special_requests: Mapped[str | None] = mapped_column(Text, nullable=True)

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── Relationships ─────────────────────────────────────────────
    # No order_by, no string expressions that would require the child
    # classes to already be imported. Service layer handles ordering.
    items: Mapped[list["BookingItem"]] = relationship(  # noqa: F821
        "BookingItem",
        backref="booking",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    travellers: Mapped[list["BookingTraveller"]] = relationship(  # noqa: F821
        "BookingTraveller",
        backref="booking",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        for key in (
            "reference", "guest_email", "guest_name", "guest_phone",
            "product_type", "status", "currency",
        ):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        email = kwargs.get("guest_email")
        if isinstance(email, str) and email:
            kwargs["guest_email"] = email.lower()

        if not kwargs.get("status"):
            kwargs["status"] = DEFAULT_BOOKING_STATUS
        if not kwargs.get("currency"):
            kwargs["currency"] = "USD"

        kwargs.setdefault("travellers_adults", 1)
        kwargs.setdefault("travellers_children", 0)
        kwargs.setdefault("total_amount", Decimal("0.00"))

        super().__init__(**kwargs)

    # ═══════════════════════════════════════════════════════════════
    #  Convenience helpers
    # ═══════════════════════════════════════════════════════════════
    @property
    def travellers_total(self) -> int:
        return self.travellers_adults + self.travellers_children

    @property
    def is_cancellable(self) -> bool:
        return self.status in {STATUS_PENDING, STATUS_CONFIRMED}

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Booking id={self.id} ref={self.reference!r} "
            f"product={self.product_type}:{self.product_id} status={self.status!r}>"
        )
