"""
models/booking_traveller.py
───────────────────────────
The booking_travellers table — one row per named person travelling.

A booking has headline counts (travellers_adults / travellers_children),
but the actual named people must be recorded for:
    - airline manifests
    - hotel check-in
    - activity guides
    - age-based pricing justification (child vs adult)

DESIGN NOTES
    - `booking_id` is REQUIRED; CASCADEs with the booking.
    - `full_name` is REQUIRED.
    - `date_of_birth` is OPTIONAL Date — mandatory for airline manifests
      in practice, but optional at the model level so leisure bookings
      without flights still work.
    - `age_at_booking` is a SNAPSHOT integer, computed at booking time
      from date_of_birth and the travel date. We snapshot because:
        * airline manifests need the age AT TRAVEL, even for bookings
          made years in advance
        * age-based pricing must reflect what was charged at booking
          time, not be silently recalculated later
      This is a deliberate denormalisation — the value never changes
      after insert.
    - `traveller_type` is a closed set: adult | child | infant.
      'infant' is reserved for airline manifests and generally free of
      charge in pricing.
    - `passport_number` is stored uppercased and stripped so lookups and
      exports are consistent. `nationality` is free-form.
    - `is_lead_traveller` marks the primary contact. The service layer
      enforces "exactly one lead per booking" rather than a DB
      constraint, to keep the schema flexible for corporate bookings.
    - NO `is_active` — travellers belong to their booking and are
      removed by cascade.

RELATIONSHIPS
    There is NO `booking` relationship declared here. The reverse side is
    declared on the parent (Booking.travellers with backref="booking"),
    so `BookingTraveller.booking` is created implicitly. Declaring it
    here too would cause a backref-name collision (both sides trying to
    define the attribute `booking`).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, TimestampMixin


# ─── Constants ─────────────────────────────────────────────────────
TRAVELLER_TYPE_ADULT: str = "adult"
TRAVELLER_TYPE_CHILD: str = "child"
TRAVELLER_TYPE_INFANT: str = "infant"

VALID_TRAVELLER_TYPES: tuple[str, ...] = (
    TRAVELLER_TYPE_ADULT,
    TRAVELLER_TYPE_CHILD,
    TRAVELLER_TYPE_INFANT,
)
DEFAULT_TRAVELLER_TYPE: str = TRAVELLER_TYPE_ADULT


class BookingTraveller(Base, TimestampMixin):
    """
    A named traveller on a booking.

    Columns
    -------
    id                 : surrogate PK
    booking_id         : REQUIRED FK to bookings
    full_name          : required display name
    date_of_birth      : optional DATE
    age_at_booking     : snapshot integer, computed at booking time
    traveller_type     : CHECK adult|child|infant
    passport_number    : optional, uppercased + stripped
    nationality        : optional free-form
    special_needs      : optional free-form (dietary, mobility, medical)
    is_lead_traveller  : bool — primary contact for the booking
    sort_order         : integer for stable display order
    created_at / updated_at : from TimestampMixin
    """

    __tablename__ = "booking_travellers"
    __table_args__ = (
        CheckConstraint(
            "traveller_type IN ('adult','child','infant')",
            name="traveller_type_check",
        ),
        CheckConstraint(
            "age_at_booking IS NULL OR age_at_booking >= 0",
            name="age_at_booking_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    booking_id: Mapped[int] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)

    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)

    age_at_booking: Mapped[int | None] = mapped_column(Integer, nullable=True)

    traveller_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_TRAVELLER_TYPE,
        server_default=DEFAULT_TRAVELLER_TYPE,
    )

    passport_number: Mapped[str | None] = mapped_column(
        String(40), nullable=True
    )

    nationality: Mapped[str | None] = mapped_column(String(80), nullable=True)

    special_needs: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_lead_traveller: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        # Strip free-text fields.
        for key in ("full_name", "nationality", "traveller_type"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        # Passport number: strip + uppercase.
        passport = kwargs.get("passport_number")
        if isinstance(passport, str):
            kwargs["passport_number"] = passport.strip().upper()

        # Enum fallback.
        if not kwargs.get("traveller_type"):
            kwargs["traveller_type"] = DEFAULT_TRAVELLER_TYPE

        # Instance defaults.
        kwargs.setdefault("is_lead_traveller", False)
        kwargs.setdefault("sort_order", 0)

        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<BookingTraveller id={self.id} booking_id={self.booking_id} "
            f"name={self.full_name!r} type={self.traveller_type!r}>"
        )
