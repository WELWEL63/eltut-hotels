"""
models/package_flight.py
────────────────────────
One sellable flight option for a package.

WHY THIS EXISTS
    A package can be sold with several different flight options — different
    airlines, different dates, different inbound/outbound legs. Each row
    here is ONE such option, shown to the customer as a "flight card" on
    the package detail page.

    Example for a Hurghada package:
        Option 1: easyJet LGW→HRG on 15 Nov + HRG→LGW on 22 Nov
        Option 2: easyJet MAN→HRG on 15 Nov + HRG→MAN on 22 Nov
        Option 3: Jet2    LGW→HRG on 16 Nov + HRG→LGW on 23 Nov
        ... up to 6 rows per package

DESIGN
    - Both outbound and inbound reference flight_prices rows (with dates).
    - Dates are DERIVED from the flights (outbound.departure_date,
      inbound.departure_date) — nothing stored twice.
    - Nights = (inbound.departure_date - outbound.departure_date).days
    - label is optional — falls back to airline + date auto-label.
    - Cascade-delete with the parent package.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base, TimestampMixin


class PackageFlight(Base, TimestampMixin):
    """One outbound+inbound flight option for a package."""

    __tablename__ = "package_flights"

    id: Mapped[int] = mapped_column(primary_key=True)

    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    outbound_flight_id: Mapped[int | None] = mapped_column(
        ForeignKey("flight_prices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    inbound_flight_id: Mapped[int | None] = mapped_column(
        ForeignKey("flight_prices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    label: Mapped[str | None] = mapped_column(String(200), nullable=True)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # ─── Relationships ────────────────────────────────────────────
    package: Mapped["Package"] = relationship(  # noqa: F821
        foreign_keys=[package_id],
    )
    outbound_flight: Mapped["FlightPrice | None"] = relationship(  # noqa: F821
        foreign_keys=[outbound_flight_id],
    )
    inbound_flight: Mapped["FlightPrice | None"] = relationship(  # noqa: F821
        foreign_keys=[inbound_flight_id],
    )

    def __init__(self, **kwargs: object) -> None:
        label = kwargs.get("label")
        if isinstance(label, str):
            kwargs["label"] = label.strip() or None
        if kwargs.get("sort_order") is None:
            kwargs["sort_order"] = 0
        if kwargs.get("is_active") is None:
            kwargs["is_active"] = True
        super().__init__(**kwargs)

    @property
    def nights(self) -> int | None:
        """Derived nights between outbound and inbound flight dates."""
        if (self.outbound_flight is None
                or self.inbound_flight is None
                or self.outbound_flight.departure_date is None
                or self.inbound_flight.departure_date is None):
            return None
        delta = (self.inbound_flight.departure_date
                 - self.outbound_flight.departure_date)
        return max(0, delta.days)

    @property
    def display_label(self) -> str:
        if self.label:
            return self.label
        parts = []
        if self.outbound_flight is not None:
            if self.outbound_flight.airline:
                parts.append(self.outbound_flight.airline)
            if self.outbound_flight.departure_date:
                parts.append(
                    self.outbound_flight.departure_date.strftime("%d %b %Y")
                )
        return " · ".join(parts) if parts else f"Option #{self.id}"

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PackageFlight id={self.id} pkg={self.package_id} "
            f"out={self.outbound_flight_id} in={self.inbound_flight_id}>"
        )


__all__ = ["PackageFlight"]