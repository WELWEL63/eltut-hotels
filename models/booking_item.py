"""
models/booking_item.py
──────────────────────
The booking_items table — line items that belong to a booking.

Every booking has at least one item (the "primary" item — the thing that
was actually booked). Activities offered as upsells during the booking
flow are added as additional items with item_type='activity_addon'.

WHY LINE ITEMS
    - Prices each component of a booking independently.
    - Keeps a paper trail of what was originally booked vs. what was
      upsold (added_during_booking flag).
    - Allows refunding / removing individual items without touching the
      parent booking.
    - Feeds the recommendation_service with data on which add-ons sell.

DESIGN NOTES
    - `booking_id` is REQUIRED; CASCADEs if a booking is ever purged.
    - `item_type` is deliberately a SMALL closed set: 'primary' or
      'activity_addon'.
    - The polymorphic `product_type` + `product_id` pair mirrors the
      parent booking. There is NO FK on product_id — the target table
      varies by row. Integrity comes from the CHECK constraint, a
      service-layer existence check, and the never-delete-products
      convention.
    - `product_name_snapshot` preserves what was booked even if the
      product is renamed later.
    - `unit_price`, `line_total`, and `currency` are snapshotted.
    - `added_during_booking` lets us measure the upsell feature.
    - line_total auto-computes from unit_price * quantity when not given
      explicitly, so callers cannot forget.

WHY THERE IS NO `booking` RELATIONSHIP HERE
    The reverse side (booking.items and item.booking) is declared on the
    Booking class in models/booking.py using backref="booking". That
    keeps this module import-independent: SQLAlchemy never needs to
    resolve "Booking" while configuring this mapper.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, TimestampMixin


# ─── Constants ─────────────────────────────────────────────────────
ITEM_TYPE_PRIMARY: str = "primary"
ITEM_TYPE_ACTIVITY_ADDON: str = "activity_addon"

VALID_ITEM_TYPES: tuple[str, ...] = (
    ITEM_TYPE_PRIMARY,
    ITEM_TYPE_ACTIVITY_ADDON,
)
DEFAULT_ITEM_TYPE: str = ITEM_TYPE_PRIMARY


class BookingItem(Base, TimestampMixin):
    """
    A line item on a booking.

    Columns
    -------
    id                     : surrogate PK
    booking_id             : REQUIRED FK to bookings
    item_type              : CHECK primary|activity_addon
    product_type           : CHECK activity|hotel|package
    product_id             : polymorphic integer reference (no FK)
    product_name_snapshot  : product name at booking time
    quantity               : positive integer
    unit_price             : NUMERIC(10,2) >= 0
    line_total             : NUMERIC(10,2) >= 0 (unit * qty, or explicit)
    currency               : CHAR(3)
    added_during_booking   : bool — was this an upsell added in-flow?
    notes                  : free-form text
    created_at / updated_at : from TimestampMixin
    """

    __tablename__ = "booking_items"
    __table_args__ = (
        CheckConstraint(
            "item_type IN ('primary','activity_addon')",
            name="item_type_check",
        ),
        CheckConstraint(
            "product_type IN ('activity','hotel','package')",
            name="product_type_check",
        ),
        CheckConstraint("quantity > 0", name="quantity_check"),
        CheckConstraint("unit_price >= 0", name="unit_price_check"),
        CheckConstraint("line_total >= 0", name="line_total_check"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_ITEM_TYPE,
        server_default=DEFAULT_ITEM_TYPE,
        index=True,
    )

    product_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    product_name_snapshot: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )

    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )

    line_total: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )

    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )

    added_during_booking: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ═══════════════════════════════════════════════════════════════
    #  Constructor
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        for key in (
            "item_type", "product_type", "currency", "product_name_snapshot"
        ):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        if not kwargs.get("item_type"):
            kwargs["item_type"] = DEFAULT_ITEM_TYPE
        if not kwargs.get("currency"):
            kwargs["currency"] = "USD"

        kwargs.setdefault("quantity", 1)
        kwargs.setdefault("unit_price", Decimal("0.00"))
        kwargs.setdefault("added_during_booking", False)

        if "line_total" not in kwargs:
            qty = kwargs.get("quantity", 1)
            unit = kwargs.get("unit_price", Decimal("0.00"))
            try:
                kwargs["line_total"] = (
                    Decimal(str(unit)) * Decimal(str(qty))
                )
            except Exception:  # noqa: BLE001 — fall back to zero on bad input
                kwargs["line_total"] = Decimal("0.00")

        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<BookingItem id={self.id} booking_id={self.booking_id} "
            f"{self.item_type}:{self.product_type}:{self.product_id} "
            f"qty={self.quantity} total={self.line_total}>"
        )
