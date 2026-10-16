"""
models/flight_price.py
──────────────────────
Dated, priced flight legs imported from airline CSVs.

Each row is ONE one-way leg: either the outbound or the return.
A round-trip price is outbound + return, summed at pricing time.

The import_batch_id column groups all rows inserted by a single
admin upload, so that batch can be reverted with one query.

Coexistence:
    Same (origin, destination, departure_date, direction) across
    DIFFERENT airlines is ALLOWED — that's how easyJet and Jet2
    both appear for LGW->HRG on 2027-04-01 and the user picks.

    Same airline + route + date + direction = ONE row.
    Re-importing the same CSV updates the price in place.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, TimestampMixin


class FlightPrice(Base, TimestampMixin):
    __tablename__ = "flight_prices"

    id: Mapped[int] = mapped_column(primary_key=True)

    airline: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )

    origin: Mapped[str] = mapped_column(
        String(3), nullable=False
    )
    destination: Mapped[str] = mapped_column(
        String(3), nullable=False
    )

    departure_date: Mapped[date] = mapped_column(
        Date, nullable=False
    )

    # 'out' = origin -> destination ; 'back' = destination -> origin
    direction: Mapped[str] = mapped_column(
        String(4), nullable=False
    )

    price_gbp: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="GBP"
    )

    flight_number: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    departure_time: Mapped[Optional[str]] = mapped_column(
        String(5), nullable=True
    )
    arrival_time: Mapped[Optional[str]] = mapped_column(
        String(5), nullable=True
    )

    passengers_basis: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )

    luggage_kg: Mapped[int] = mapped_column(
        Integer, nullable=False, default=23
    )

    source_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )
    captured_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    import_batch_id: Mapped[Optional[str]] = mapped_column(
        String(40), nullable=True, index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "airline", "origin", "destination",
            "departure_date", "direction",
            name="uq_flight_price_route_date_dir",
        ),
        Index(
            "ix_flight_prices_route_date_dir",
            "origin", "destination", "departure_date", "direction",
        ),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("currency", "GBP")
        kwargs.setdefault("luggage_kg", 23)
        if isinstance(kwargs.get("airline"), str):
            kwargs["airline"] = kwargs["airline"].strip()
        if isinstance(kwargs.get("origin"), str):
            kwargs["origin"] = kwargs["origin"].strip().upper()
        if isinstance(kwargs.get("destination"), str):
            kwargs["destination"] = kwargs["destination"].strip().upper()
        if isinstance(kwargs.get("direction"), str):
            kwargs["direction"] = kwargs["direction"].strip().lower()
        if isinstance(kwargs.get("flight_number"), str):
            kwargs["flight_number"] = kwargs["flight_number"].strip() or None
        if isinstance(kwargs.get("source_url"), str):
            kwargs["source_url"] = kwargs["source_url"].strip() or None
        super().__init__(**kwargs)

    @property
    def route_label(self) -> str:
        return f"{self.origin} -> {self.destination}"

    @property
    def direction_label(self) -> str:
        return "Outbound" if self.direction == "out" else "Return"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "airline": self.airline,
            "origin": self.origin,
            "destination": self.destination,
            "departure_date": self.departure_date.isoformat() if self.departure_date else None,
            "direction": self.direction,
            "price_gbp": str(self.price_gbp) if self.price_gbp is not None else None,
            "currency": self.currency,
            "flight_number": self.flight_number,
            "departure_time": self.departure_time,
            "arrival_time": self.arrival_time,
            "passengers_basis": self.passengers_basis,
            "luggage_kg": self.luggage_kg,
            "source_url": self.source_url,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
            "import_batch_id": self.import_batch_id,
        }

    def __repr__(self) -> str:
        return (
            f"<FlightPrice {self.airline} {self.origin}->{self.destination} "
            f"{self.departure_date} {self.direction} GBP{self.price_gbp}>"
        )


__all__ = ["FlightPrice"]