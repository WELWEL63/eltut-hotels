"""
models/package_option.py
─────────────────────────
A purchaseable departure option for a package.

WHY THIS EXISTS
    A package can be sold in several configurations — different flights,
    different departure dates, different hotel rooms, different seasonal
    prices. Each such configuration is one row here.

    Example for a "Nile Cruise" package:
        Option 1: 02/12/2026 · easyJet MAN→HRG · winter rate €2,025
        Option 2: 02/12/2026 · TUI MAN→HRG    · winter rate €2,500
        Option 3: 15/12/2026 · easyJet MAN→HRG · xmas rate €2,150

    The customer sees these as rows in a table and picks one. The picked
    option's price_id drives pricing, and its flight_id is recorded on
    the booking as a line item.

DESIGN
    - All three component FKs are nullable: an option may be as simple
      as "price only" (package with no flight, e.g. self-drive) or as
      rich as "flight + rate + alternate room".
    - departure_date is optional. When null, the option is treated as
      "any date" — useful for flexible bookings.
    - label is a human string shown on the public table (falls back to
      a generated label like "02/12/2026 · easyJet").
    - The option is what the customer selects. Everything else (Flight,
      PackagePrice, Room) is reference data.

RELATIONSHIPS
    package_options.package_id  → packages.id    (CASCADE)
    package_options.flight_id   → flights.id     (SET NULL on delete)
    package_options.price_id    → package_prices.id (SET NULL)
    package_options.room_id     → rooms.id       (SET NULL)
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base, TimestampMixin


class PackageOption(Base, TimestampMixin):
    """One purchaseable departure option for a package."""

    __tablename__ = "package_options"
    __table_args__ = (
        # At least one of flight / price must be set — an option with
        # neither has nothing to sell.
        CheckConstraint(
            "flight_id IS NOT NULL OR price_id IS NOT NULL",
            name="has_flight_or_price_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    flight_id: Mapped[int | None] = mapped_column(
        ForeignKey("flights.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    price_id: Mapped[int | None] = mapped_column(
        ForeignKey("package_prices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    room_id: Mapped[int | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"),
        nullable=True,
    )

    departure_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    label: Mapped[str | None] = mapped_column(String(200), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # ─── Relationships (declared on the child side, no back_populates
    #     yet on Package because that model is already big enough)
    package: Mapped["Package"] = relationship(  # noqa: F821
        foreign_keys=[package_id],
    )
    flight: Mapped["Flight | None"] = relationship(  # noqa: F821
        foreign_keys=[flight_id],
    )
    price: Mapped["PackagePrice | None"] = relationship(  # noqa: F821
        foreign_keys=[price_id],
    )
    room: Mapped["Room | None"] = relationship(  # noqa: F821
        foreign_keys=[room_id],
    )

    def __init__(self, **kwargs: object) -> None:
        label = kwargs.get("label")
        if isinstance(label, str):
            kwargs["label"] = label.strip() or None
        if kwargs.get("is_active") is None:
            kwargs["is_active"] = True
        if kwargs.get("sort_order") is None:
            kwargs["sort_order"] = 0
        super().__init__(**kwargs)

    @property
    def display_label(self) -> str:
        """Human-readable label for the public options table."""
        if self.label:
            return self.label
        parts: list[str] = []
        if self.departure_date:
            parts.append(self.departure_date.strftime("%d %b %Y"))
        if self.flight is not None and self.flight.airline_name:
            parts.append(self.flight.airline_name)
        return " · ".join(parts) if parts else f"Option #{self.id}"

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PackageOption id={self.id} pkg={self.package_id} "
            f"date={self.departure_date} flight={self.flight_id} price={self.price_id}>"
        )


__all__ = ["PackageOption"]
