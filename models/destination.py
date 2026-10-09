"""
models/destination.py
─────────────────────
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
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, String, Text
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
    created_at / updated_at : from TimestampMixin
    """

    __tablename__ = "destinations"

    __slug_source__ = "name"  # SlugMixin reads this to know what to slugify

    # ─── Identity ──────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=False, index=True
    )

    # ─── Classification ────────────────────────────────────────────
    country: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default=DEFAULT_COUNTRY,
        server_default=DEFAULT_COUNTRY,
    )

    region: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # ─── Content ───────────────────────────────────────────────────
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    hero_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ─── Geography ─────────────────────────────────────────────────
    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6), nullable=True
    )
    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6), nullable=True
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor — normalise text + apply instance defaults
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        """
        Apply defaults before SQLAlchemy sets attributes.

        Same pattern as models/user.py:
          - name, country, region are stripped of surrounding whitespace
          - country is set to DEFAULT_COUNTRY if not provided
            (applied AFTER stripping so an explicit "  " becomes the default)
        """
        for key in ("name", "country", "region"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        # After stripping, treat empty country as missing so the default applies.
        if not kwargs.get("country"):
            kwargs["country"] = DEFAULT_COUNTRY

        super().__init__(**kwargs)

    # ─── Cosmetic ──────────────────────────────────────────────────
    def __repr__(self) -> str:  # pragma: no cover
        return f"<Destination id={self.id} name={self.name!r}>"
