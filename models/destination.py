"""
models/destination.py
──────────────────────
The destinations table — shared geographic reference used by activities,
hotels, and packages.

WHY A SEPARATE TABLE
    A destination (city / region) is referenced by every product type.
    Keeping it in one table means:
      - One canonical name, slug, coordinates per place
      - Filtering products by destination is a plain join
      - Maps and itineraries share coordinates without duplication

DESIGN NOTES
    - `name` is unique — no two destinations share a name.
    - `slug` is auto-derived from `name` via SlugMixin; used for SEO URLs.
    - `country` defaults to "Egypt"; the instance default is set in
      __init__ so it's readable on unsaved instances (matches the pattern
      used by models/user.py for role/is_active/is_verified).
    - `latitude` / `longitude` use NUMERIC(9, 6) for exact decimal
      precision (no float drift when computing distances).
    - `hero_image_url` is a single string; galleries belong on products,
      not destinations.
    - `airport_code` is the IATA code of the nearest commercial airport
      (e.g. HRG for Hurghada). Used by the flight pricing service to look
      up flight_prices rows. Nullable — some destinations (e.g. Nile
      Cruise) have no single airport.
    - `is_bookable` gates the destination from customer-facing search
      and detail pages. Defaults to True. Admins set it False for
      destinations that have packages but no flight_prices data yet
      (Sharm, Luxor, Nile Cruise). Flip back to True once flight CSVs
      are imported — no other code change needed.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, SlugMixin, TimestampMixin


DEFAULT_COUNTRY: str = "Egypt"


class Destination(Base, SlugMixin, TimestampMixin):
    """
    A city, region, or resort area (e.g. Hurghada, Luxor, Sharm El-Sheikh).

    Columns
    -------
    id             : surrogate PK
    name           : unique display name
    slug           : URL-safe identifier, auto-generated from name
    country        : default 'Egypt'; kept free-form for future expansion
    region         : grouping label ('Red Sea', 'Upper Egypt', 'Sinai', ...)
    description    : long-form marketing copy
    hero_image_url : single banner image for destination pages
    latitude       : decimal degrees (-90..90), NUMERIC(9,6)
    longitude      : decimal degrees (-180..180), NUMERIC(9,6)
    airport_code   : IATA code of nearest commercial airport (nullable)
    is_bookable    : customer-facing gate; default True
    created_at / updated_at : from TimestampMixin
    """

    __tablename__ = "destinations"

    __slug_source__ = "name"  # SlugMixin reads this to know what to slugify

    # ─── Identity ─────────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=False, index=True
    )

    # ─── Classification ───────────────────────────────────────────────
    country: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default=DEFAULT_COUNTRY,
        server_default=DEFAULT_COUNTRY,
    )

    region: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # ─── Content ──────────────────────────────────────────────────────
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    hero_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ─── Geography ────────────────────────────────────────────────────
    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6), nullable=True
    )
    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6), nullable=True
    )

    # ─── Flight pricing link ──────────────────────────────────────────
    # IATA code of the nearest commercial airport (e.g. HRG for Hurghada).
    # Nullable because not every destination has one (e.g. Nile Cruise).
    airport_code: Mapped[str | None] = mapped_column(
        String(3), nullable=True, index=True
    )

    # ─── Customer-facing gate ─────────────────────────────────────────
    # False = hidden from search results and detail pages. Used while
    # a destination has no flight_prices rows yet.
    is_bookable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
        index=True,
    )