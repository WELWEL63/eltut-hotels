"""
models/quote.py
────────────────
Admin-issued price quotes in response to customer quote requests.

WORKFLOW
    1. Customer submits "request a quote" via public form.
       → Mongo `enquiries` gets a row with type='quote_request'.
       → We do NOT create a Quote row yet — the admin hasn't priced it.

    2. Admin sees the request in /admin/quotes?status=requested.
       → Clicks "Create quote" → gets a draft Quote (status='draft').
       → Fills in price, currency, valid_until, message, optional image.
       → Clicks "Send to customer" → status='sent', sent_at set,
         email sent via email_service.send_quote_to_customer().

    3. Customer receives email with a link to /quote/<reference>.
       → Sees price + message + image.
       → Clicks Accept or Decline.

    4. On accept: a Booking row is created (status='pending'),
       the quote transitions to status='accepted', accepted_at set.

    5. On decline: quote → status='declined', declined_at set.

    6. Unactioned quotes expire after valid_until → status='expired'.

LINK TO ENQUIRY
    The originating Mongo enquiry ID is stored as a hex string in
    `enquiry_id`. This is a weak link (Mongo ID vs SQL PK) — Mongo
    could be down when the admin creates the quote, so we tolerate
    NULL. When present, the admin UI can show a "View original
    request" link.

REFERENCE FORMAT
    Q-YYYY-NNNNN — matches booking reference style (ELT-YYYY-NNNNN),
    just a different prefix so staff can tell them apart at a glance.
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, TimestampMixin


# ─── Status machine ───────────────────────────────────────────────────────
# Transitions allowed:
#   draft     -> sent | cancelled
#   sent      -> accepted | declined | expired | cancelled
#   accepted  -> (terminal, but can be cancelled)
#   declined  -> (terminal)
#   expired   -> (terminal, but can be re-issued as a new quote)
#   cancelled -> (terminal)
STATUS_DRAFT: str = "draft"
STATUS_SENT: str = "sent"
STATUS_ACCEPTED: str = "accepted"
STATUS_DECLINED: str = "declined"
STATUS_EXPIRED: str = "expired"
STATUS_CANCELLED: str = "cancelled"

VALID_QUOTE_STATUSES: tuple[str, ...] = (
    STATUS_DRAFT,
    STATUS_SENT,
    STATUS_ACCEPTED,
    STATUS_DECLINED,
    STATUS_EXPIRED,
    STATUS_CANCELLED,
)

DEFAULT_QUOTE_STATUS: str = STATUS_DRAFT


# ─── Product types ────────────────────────────────────────────────────────
# Duplicated from bookings to avoid a circular import; keep in sync.

PRODUCT_TYPE_HOTEL: str = "hotel"


VALID_QUOTE_PRODUCT_TYPES: tuple[str, ...] = (
   
    PRODUCT_TYPE_HOTEL
)


class Quote(Base, TimestampMixin):
    """A price quote issued by an admin in response to a customer request."""

    __tablename__ = "quotes"
    __table_args__ = (
        UniqueConstraint("reference", name="quote_reference_uq"),
        CheckConstraint(
            "status IN ('draft','sent','accepted','declined','expired','cancelled')",
            name="status_check",
        ),
        CheckConstraint(
            "product_type IN ('activity','hotel','package')",
            name="product_type_check",
        ),
        # Money must be positive. Zero would be a giveaway, negative
        # would be nonsense.
        CheckConstraint("price > 0", name="price_check"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # ─── Identity ─────────────────────────────────────────────────────
    reference: Mapped[str] = mapped_column(
        String(40), nullable=False, unique=True, index=True,
    )

    # ─── Customer context (denormalised: quote survives user deletion) ─
    customer_email: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
    )
    customer_name: Mapped[str | None] = mapped_column(
        String(150), nullable=True,
    )
    customer_phone: Mapped[str | None] = mapped_column(
        String(40), nullable=True,
    )
    customer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ─── Product context ──────────────────────────────────────────────
    product_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
    )
    product_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True,
    )
    # Snapshot the product name at quote time so the quote stays
    # meaningful even if the product is later renamed or deactivated.
    product_name_snapshot: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
    )

    # ─── Link to originating Mongo enquiry (weak link, nullable) ──────
    enquiry_id: Mapped[str | None] = mapped_column(
        String(40), nullable=True, index=True,
    )

    # ─── Party composition (snapshot from the request) ────────────────
    adults: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    children: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # ─── Per-person pricing ───────────────────────────────────────────
    # WHY separate adult/child columns: the admin prices each tier, and
    # the total is derived. Keeping them separate lets the customer
    # quote page show a breakdown like "2 × £500 + 1 × £250 = £1,250".
    price_adult: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.01"),
        server_default="0.01",
    )
    price_child: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )

    # ─── Computed total ──────────────────────────────────────────────
    # Stored (not a SQL computed column) so historical quotes keep their
    # original total even if the underlying unit prices are edited later.
    # The service layer keeps this in sync with adults/children/prices.
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="GBP",
        server_default="GBP",
    )

    # ─── Free-form message + optional image ──────────────────────────
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ─── Validity + status timestamps ────────────────────────────────
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_QUOTE_STATUS,
        server_default=DEFAULT_QUOTE_STATUS,
        index=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    declined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    expired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ─── The booking created when the quote is accepted ──────────────
    # WHY nullable: not all accepted quotes result in a booking if the
    # admin decides to handle it out of band. Nullable keeps the door
    # open without a separate join table.
    accepted_booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ─── Audit ────────────────────────────────────────────────────────
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __init__(self, **kwargs: object) -> None:
        # Normalise string fields the same way other models do, so
        # unsaved instances match what we'd get from the DB.
        for key in ("reference", "customer_email", "product_type",
                    "currency", "status"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        if isinstance(kwargs.get("customer_email"), str):
            kwargs["customer_email"] = kwargs["customer_email"].lower()

        # Sensible defaults matching the CHECK constraints.
        if not kwargs.get("status"):
            kwargs["status"] = DEFAULT_QUOTE_STATUS
        if not kwargs.get("currency"):
            kwargs["currency"] = "GBP"

        # Party composition — coerce to sane integers.
        try:
            kwargs["adults"] = max(1, int(kwargs.get("adults") or 1))
        except (TypeError, ValueError):
            kwargs["adults"] = 1
        try:
            kwargs["children"] = max(0, int(kwargs.get("children") or 0))
        except (TypeError, ValueError):
            kwargs["children"] = 0

        # Per-person prices — coerce to Decimal.
        try:
            kwargs["price_adult"] = max(
                Decimal("0.01"),
                Decimal(str(kwargs.get("price_adult") or "0.01")),
            )
        except Exception:  # noqa: BLE001
            kwargs["price_adult"] = Decimal("0.01")
        try:
            kwargs["price_child"] = max(
                Decimal("0"),
                Decimal(str(kwargs.get("price_child") or "0")),
            )
        except Exception:  # noqa: BLE001
            kwargs["price_child"] = Decimal("0")

        # If price wasn't supplied, compute it from the components.
        if kwargs.get("price") in (None, "", "0", "0.00"):
            kwargs["price"] = (
                kwargs["adults"] * kwargs["price_adult"]
                + kwargs["children"] * kwargs["price_child"]
            )

        super().__init__(**kwargs)

    def compute_total(self) -> Decimal:
        """Return adults * price_adult + children * price_child."""
        return (
            (self.price_adult or Decimal("0")) * (self.adults or 0)
            + (self.price_child or Decimal("0")) * (self.children or 0)
        )

    # ─── Convenience predicates (used by services + templates) ────────
    @property
    def party_size(self) -> int:
        """Total travellers (adults + children)."""
        return (self.adults or 0) + (self.children or 0)

    @property
    def is_draft(self) -> bool:
        return self.status == STATUS_DRAFT

    @property
    def is_sent(self) -> bool:
        return self.status == STATUS_SENT

    @property
    def is_accepted(self) -> bool:
        return self.status == STATUS_ACCEPTED

    @property
    def is_declined(self) -> bool:
        return self.status == STATUS_DECLINED

    @property
    def is_expired(self) -> bool:
        return self.status == STATUS_EXPIRED

    @property
    def is_open(self) -> bool:
        """True if the customer can still accept or decline."""
        return self.status == STATUS_SENT and not self._has_expired()

    def _has_expired(self) -> bool:
        """True if valid_until has passed (only meaningful for 'sent')."""
        if self.valid_until is None:
            return False
        return self.valid_until < date.today()

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Quote id={self.id} ref={self.reference!r} "
            f"status={self.status!r} price={self.price} {self.currency}>"
        )


__all__ = [
    "Quote",
    "STATUS_DRAFT",
    "STATUS_SENT",
    "STATUS_ACCEPTED",
    "STATUS_DECLINED",
    "STATUS_EXPIRED",
    "STATUS_CANCELLED",
    "VALID_QUOTE_STATUSES",
    "DEFAULT_QUOTE_STATUS",
    "PRODUCT_TYPE_ACTIVITY",
    "PRODUCT_TYPE_HOTEL",
    "PRODUCT_TYPE_PACKAGE",
    "VALID_QUOTE_PRODUCT_TYPES",
]
