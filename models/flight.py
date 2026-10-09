"""
models/flight.py
────────────────
The flights table — flight legs belonging to a package.

Each package can have multiple flight legs (outbound, return, or multi-
leg tours). Flights reference suppliers (the airline) and store flight-
specific fields that do not belong on the package itself.

DESIGN NOTES
    - `package_id` is REQUIRED and CASCADEs with the package.
    - `supplier_id` is OPTIONAL and uses ON DELETE SET NULL. A flight can
      be listed with just an airline name (free-form) before the supplier
      is formally onboarded. Deleting a supplier must NOT destroy the
      flight record.
    - `flight_from` / `flight_to` are free-form strings — packages list
      city names, airport codes, or full airport names interchangeably.
      Forcing a strict IATA column would reject valid input.
    - `airline_name` is duplicated from supplier.name on purpose: the
      printed airline on a ticket can differ from the supplier's trading
      name (e.g. a consolidator vs the airline itself).
    - `luggage_allowance` is a free-form string; airlines phrase this
      differently ("23kg checked + 7kg cabin", "1 x 23kg", "2PC").
    - Departure/arrival DATE-TIMES deliberately live in the booking, not
      here. Products describe WHAT; bookings describe WHEN. This matches
      the architecture rule "dates only in bookings, never in products".
    - `included` says whether the leg is part of the package price or an
      optional paid add-on.
    - Instance defaults applied in __init__ so unsaved instances read the
      same as DB-loaded ones.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    ForeignKey,
    String,
    Text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base, TimestampMixin


class Flight(Base, TimestampMixin):
    """
    A flight leg included in (or offered with) a package.

    Columns
    -------
    id                 : surrogate PK
    package_id         : REQUIRED FK to packages
    supplier_id        : OPTIONAL FK to suppliers (SET NULL on delete)
    flight_from        : origin airport/city (free-form)
    flight_to          : destination airport/city (free-form)
    airline_name       : free-form airline name (may differ from supplier)
    luggage_allowance  : free-form allowance description
    included           : bool — part of package price or optional add-on
    notes              : optional free-form notes (stops, connections, ...)
    is_active          : soft-disable flag
    created_at / updated_at : from TimestampMixin
    """

    __tablename__ = "flights"

    id: Mapped[int] = mapped_column(primary_key=True)

    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ─── Itinerary ─────────────────────────────────────────────────
    flight_from: Mapped[str] = mapped_column(String(150), nullable=False)
    flight_to: Mapped[str] = mapped_column(String(150), nullable=False)

    airline_name: Mapped[str | None] = mapped_column(String(150), nullable=True)

    luggage_allowance: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )

    # ─── Inclusion ─────────────────────────────────────────────────
    included: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── State ─────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    # ─── Relationships ─────────────────────────────────────────────
    # back_populates="flights" is added to Package in a future patch if
    # needed. For now, the FK alone is enough — we do not need the reverse
    # navigation in templates.
    #

    # ═══════════════════════════════════════════════════════════════
    #  Constructor
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        for key in ("flight_from", "flight_to", "airline_name", "luggage_allowance"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        kwargs.setdefault("included", True)
        kwargs.setdefault("is_active", True)

        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Flight id={self.id} package_id={self.package_id} "
            f"{self.flight_from!r}->{self.flight_to!r}>"
        )
