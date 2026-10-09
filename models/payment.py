"""
models/payment.py
─────────────────
The payments table — a history log of every payment attempt against a
booking, successful or not.

This is NOT a current-state table. If a customer retries payment three
times, we keep three rows. The current paid state of a booking is derived
by querying its payments (latest successful = paid).

DESIGN NOTES
    - `booking_id` is REQUIRED; CASCADEs with the booking.
    - `provider` is CHECK'd to a small set: 'paypal'.
    - `method` distinguishes the two PayPal flows: redirect vs. hosted
      card field.
    - `status` mirrors PayPal's REST API states:
        created → approved → completed
                          ↘ failed
                          ↘ cancelled
        refunded when a completed payment is refunded.
    - `amount` and `currency` are snapshotted.
    - `provider_payment_id` is INDEXED for webhook callbacks.
    - `payload` is a JSON column holding the raw provider response.
    - `failure_reason`, `refunded_amount`, `refunded_at`, `processed_at`
      support failure and refund workflows.
    - NO `is_active` — payments are facts. They cascade with the booking.
    - Instance defaults applied in __init__ so unsaved instances read the
      same as DB-loaded ones.

WHY `JSON` IS IMPORTED EXPLICITLY
    SQLAlchemy 2.x resolves `Mapped[X]` to a Core type only for a known
    set of Python types. `dict[str, Any]` is NOT in that set — so the
    column type must be declared explicitly with `mapped_column(JSON, ...)`.
    On Postgres this maps to JSON; can be swapped to JSONB in a migration
    if indexing on payload fields is ever needed.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, TimestampMixin


# ─── Constants ─────────────────────────────────────────────────────
PROVIDER_PAYPAL: str = "paypal"
VALID_PROVIDERS: tuple[str, ...] = (PROVIDER_PAYPAL,)
DEFAULT_PROVIDER: str = PROVIDER_PAYPAL

METHOD_PAYPAL_REDIRECT: str = "paypal_redirect"
METHOD_PAYPAL_CARD: str = "paypal_card"
VALID_METHODS: tuple[str, ...] = (METHOD_PAYPAL_REDIRECT, METHOD_PAYPAL_CARD)
DEFAULT_METHOD: str = METHOD_PAYPAL_REDIRECT

STATUS_CREATED: str = "created"
STATUS_APPROVED: str = "approved"
STATUS_COMPLETED: str = "completed"
STATUS_FAILED: str = "failed"
STATUS_CANCELLED: str = "cancelled"
STATUS_REFUNDED: str = "refunded"

VALID_PAYMENT_STATUSES: tuple[str, ...] = (
    STATUS_CREATED,
    STATUS_APPROVED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_CANCELLED,
    STATUS_REFUNDED,
)
DEFAULT_PAYMENT_STATUS: str = STATUS_CREATED


class Payment(Base, TimestampMixin):
    """One payment attempt — see module docstring for design notes."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("provider IN ('paypal')", name="provider_check"),
        CheckConstraint(
            "method IN ('paypal_redirect','paypal_card')",
            name="method_check",
        ),
        CheckConstraint(
            "status IN ('created','approved','completed','failed',"
            "'cancelled','refunded')",
            name="status_check",
        ),
        CheckConstraint("amount >= 0", name="amount_check"),
        CheckConstraint(
            "refunded_amount IS NULL OR refunded_amount >= 0",
            name="refunded_amount_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_PROVIDER,
        server_default=DEFAULT_PROVIDER,
    )

    method: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=DEFAULT_METHOD,
        server_default=DEFAULT_METHOD,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_PAYMENT_STATUS,
        server_default=DEFAULT_PAYMENT_STATUS,
        index=True,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )

    provider_payment_id: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True
    )
    provider_order_id: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True
    )
    provider_payer_id: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )

    # Explicit JSON column — SQLAlchemy 2.x does not auto-map
    # dict[str, Any] to a Core type.
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )

    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    refunded_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        for key in (
            "provider", "method", "status", "currency",
            "provider_payment_id", "provider_order_id", "provider_payer_id",
        ):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        if not kwargs.get("provider"):
            kwargs["provider"] = DEFAULT_PROVIDER
        if not kwargs.get("method"):
            kwargs["method"] = DEFAULT_METHOD
        if not kwargs.get("status"):
            kwargs["status"] = DEFAULT_PAYMENT_STATUS
        if not kwargs.get("currency"):
            kwargs["currency"] = "USD"

        kwargs.setdefault("amount", Decimal("0.00"))

        super().__init__(**kwargs)

    # ═══════════════════════════════════════════════════════════════
    #  Helpers
    # ═══════════════════════════════════════════════════════════════
    @property
    def is_settled(self) -> bool:
        return self.status == STATUS_COMPLETED

    @property
    def is_refundable(self) -> bool:
        return self.status == STATUS_COMPLETED

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Payment id={self.id} booking_id={self.booking_id} "
            f"{self.provider}:{self.status} amount={self.amount} {self.currency}>"
        )
