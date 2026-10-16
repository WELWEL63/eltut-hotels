"""
models/airport.py
─────────────────
Reference table for IATA airport codes -> human-readable names.

Used by:
  * flight_service.available_origins()  -- display names in dropdowns
  * Any UI showing a flight route as "London Gatwick (LGW) -> Hurghada (HRG)"

WHY A TABLE (not a dict)
    Airports are reference data, not code. Adding a new one means
    inserting a row, not shipping a new release. Admins can extend
    the list as they collect flight data from new origins.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, TimestampMixin


class Airport(Base, TimestampMixin):
    __tablename__ = "airports"

    iata_code: Mapped[str] = mapped_column(
        String(3), primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(120), nullable=False
    )

    city: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )

    country: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )

    def __init__(self, **kwargs):
        if isinstance(kwargs.get("iata_code"), str):
            kwargs["iata_code"] = kwargs["iata_code"].strip().upper()
        if isinstance(kwargs.get("name"), str):
            kwargs["name"] = kwargs["name"].strip()
        if isinstance(kwargs.get("city"), str):
            kwargs["city"] = kwargs["city"].strip() or None
        if isinstance(kwargs.get("country"), str):
            kwargs["country"] = kwargs["country"].strip() or None
        super().__init__(**kwargs)

    @property
    def display(self) -> str:
        """'London Gatwick (LGW)' — used by templates."""
        return f"{self.name} ({self.iata_code})"

    def to_dict(self) -> dict:
        return {
            "iata_code": self.iata_code,
            "name": self.name,
            "city": self.city,
            "country": self.country,
        }

    def __repr__(self) -> str:
        return f"<Airport {self.iata_code} {self.name!r}>"


__all__ = ["Airport"]