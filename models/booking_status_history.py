"""
models/booking_status_history.py
────────────────────────────────
An immutable audit log of every status transition on a booking.

Every time `bookings.status` changes — by customer cancel, admin hold,
payment confirmation, scheduled system job, or refund — a row is
inserted here recording:

    who     (user id + role at the time of change)
    when    (created_at)
    what    (from_status -> to_status)
    why     (reason)
    how     (ip_address + user_agent)

The service layer (booking_service) is responsible for writing BOTH the
bookings.status update AND the corresponding history row in a single
transaction — this table does not enforce the pairing by itself.

DESIGN NOTES
    - `booking_id` REQUIRED; CASCADEs with the booking.
    - `from_status` is NULLABLE so the very first row can record
      "created -> pending" with no prior status.
    - `to_status` is REQUIRED and CHECK-constrained to the same set used
      on bookings.
    - `changed_by_user_id` is NULLABLE with ON DELETE SET NULL.
    - `changed_by_role` is a free-form string ('customer', 'admin',
      'system', 'guest') rather than a FK: the role at the time of the
      change is a FACT even if the user's role changes later.
    - `reason` is free-form text, stripped in __init__.
    - `ip_address` is VARCHAR(45) to fit IPv6.
    - `user_agent` is VARCHAR(255).
    - NO TimestampMixin. `updated_at` would be meaningless on an
      immutable log. We add `created_at` explicitly.
    - NO is_active. History rows are facts.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from models import Base


# ─── Constants ─────────────────────────────────────────────────────
ROLE_CUSTOMER: str = "customer"
ROLE_ADMIN: str = "admin"
ROLE_SYSTEM: str = "system"
ROLE_GUEST: str = "guest"

VALID_ACTOR_ROLES: tuple[str, ...] = (
    ROLE_CUSTOMER,
    ROLE_ADMIN,
    ROLE_SYSTEM,
    ROLE_GUEST,
)
DEFAULT_ACTOR_ROLE: str = ROLE_SYSTEM


class BookingStatusHistory(Base):
    """
    One transition of a booking's status.

    Columns
    -------
    id                   : surrogate PK
    booking_id           : REQUIRED FK to bookings
    from_status          : nullable; previous status (NULL for first row)
    to_status            : required; new status
    changed_by_user_id   : nullable FK to users (SET NULL on delete)
    changed_by_role      : 'customer' | 'admin' | 'system' | 'guest'
    reason               : free-form text
    ip_address           : optional VARCHAR(45)
    user_agent           : optional VARCHAR(255)
    created_at           : timestamp (log is immutable)
    """

    __tablename__ = "booking_status_history"
    __table_args__ = (
        CheckConstraint(
            "to_status IN ('pending','confirmed','cancelled','completed',"
            "'refunded')",
            name="to_status_check",
        ),
        CheckConstraint(
            "from_status IS NULL OR from_status IN ('pending','confirmed',"
            "'cancelled','completed','refunded')",
            name="from_status_check",
        ),
        CheckConstraint(
            "changed_by_role IN ('customer','admin','system','guest')",
            name="changed_by_role_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    from_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )

    to_status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )

    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    changed_by_role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_ACTOR_ROLE,
        server_default=DEFAULT_ACTOR_ROLE,
    )

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        # reason is now included in the strip list — was missing before.
        for key in (
            "from_status", "to_status",
            "changed_by_role", "ip_address", "user_agent",
            "reason",
        ):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        if not kwargs.get("changed_by_role"):
            kwargs["changed_by_role"] = DEFAULT_ACTOR_ROLE

        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<BookingStatusHistory id={self.id} booking_id={self.booking_id} "
            f"{self.from_status!r}->{self.to_status!r} by={self.changed_by_role!r}>"
        )
