"""
models/hotel.py
───────────────
The hotels table — the second product type — plus its two small children:

    hotel_facilities   named amenities with optional quantity
    hotel_images       gallery images with sort order + image "type"

Rooms live in models/room.py (File 8) because they have their own
children (room_images).

DESIGN NOTES
    - `name` is UNIQUE — no two hotels share a marketing name.
    - `slug` is auto-derived from `name` via SlugMixin (SEO URLs).
    - `destination_id` is REQUIRED (a hotel always sits somewhere).
    - `stars` is an INTEGER between 1 and 5 (CHECK).
    - `total_capacity` is a positive integer; availability_service uses
      room-level capacity when present, otherwise falls back to this.
    - Check-in/check-out times are free-form strings ("14:00", "after 3pm")
      because hotels often phrase them in prose, and a strict TIME column
      would reject valid input.
    - `latitude` / `longitude` mirror the destination model for consistent
      map markers.
    - Child tables cascade-delete with the parent, at the DB level
      (ondelete="CASCADE") and at the ORM level (delete-orphan +
      passive_deletes).
    - Instance defaults (stars=3, is_active=True) are applied in __init__
      so unsaved instances read the same as DB-loaded ones.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base, SlugMixin, TimestampMixin


# ─── Constants ─────────────────────────────────────────────────────
DEFAULT_HOTEL_STARS: int = 3

FACILITY_TYPE_GENERAL: str = "general"
FACILITY_TYPE_WELLNESS: str = "wellness"
FACILITY_TYPE_DINING: str = "dining"
FACILITY_TYPE_SPORT: str = "sport"
FACILITY_TYPE_FAMILY: str = "family"
FACILITY_TYPE_BUSINESS: str = "business"
FACILITY_TYPE_OTHER: str = "other"

VALID_FACILITY_TYPES: tuple[str, ...] = (
    FACILITY_TYPE_GENERAL,
    FACILITY_TYPE_WELLNESS,
    FACILITY_TYPE_DINING,
    FACILITY_TYPE_SPORT,
    FACILITY_TYPE_FAMILY,
    FACILITY_TYPE_BUSINESS,
    FACILITY_TYPE_OTHER,
)
DEFAULT_FACILITY_TYPE: str = FACILITY_TYPE_GENERAL

HOTEL_IMAGE_TYPE_EXTERIOR: str = "exterior"
HOTEL_IMAGE_TYPE_LOBBY: str = "lobby"
HOTEL_IMAGE_TYPE_ROOM: str = "room"
HOTEL_IMAGE_TYPE_RESTAURANT: str = "restaurant"
HOTEL_IMAGE_TYPE_POOL: str = "pool"
HOTEL_IMAGE_TYPE_BEACH: str = "beach"
HOTEL_IMAGE_TYPE_SPA: str = "spa"
HOTEL_IMAGE_TYPE_OTHER: str = "other"

VALID_HOTEL_IMAGE_TYPES: tuple[str, ...] = (
    HOTEL_IMAGE_TYPE_EXTERIOR,
    HOTEL_IMAGE_TYPE_LOBBY,
    HOTEL_IMAGE_TYPE_ROOM,
    HOTEL_IMAGE_TYPE_RESTAURANT,
    HOTEL_IMAGE_TYPE_POOL,
    HOTEL_IMAGE_TYPE_BEACH,
    HOTEL_IMAGE_TYPE_SPA,
    HOTEL_IMAGE_TYPE_OTHER,
)
DEFAULT_HOTEL_IMAGE_TYPE: str = HOTEL_IMAGE_TYPE_OTHER


# ═══════════════════════════════════════════════════════════════════
#  Parent: hotels
# ═══════════════════════════════════════════════════════════════════
class Hotel(Base, SlugMixin, TimestampMixin):
    """
    A hotel property.

    Columns
    -------
    id             : surrogate PK
    name           : unique marketing name
    slug           : SEO URL slug (from name)
    destination_id : REQUIRED FK to destinations
    stars          : INTEGER 1..5 (CHECK)
    address        : free-form address line
    latitude/longitude : NUMERIC(9,6) — consistent with destinations
    description    : long-form marketing copy
    check_in_time  : free-form string ("14:00", "after 3pm")
    check_out_time : free-form string
    total_capacity : positive integer; fallback for availability
    is_active      : soft-disable flag
    created_at / updated_at : from TimestampMixin
    """

    __tablename__ = "hotels"
    __table_args__ = (
        CheckConstraint("stars BETWEEN 1 AND 5", name="stars_check"),
        CheckConstraint("total_capacity > 0", name="total_capacity_check"),
    )

    __slug_source__ = "name"

    # ─── Identity ──────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(200), unique=True, nullable=False, index=True
    )

    destination_id: Mapped[int] = mapped_column(
        ForeignKey("destinations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ─── Classification ────────────────────────────────────────────
    stars: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_HOTEL_STARS,
        server_default=str(DEFAULT_HOTEL_STARS),
    )

    # ─── Location ──────────────────────────────────────────────────
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6), nullable=True
    )
    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6), nullable=True
    )

    # ─── Content ───────────────────────────────────────────────────
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    check_in_time: Mapped[str | None] = mapped_column(String(40), nullable=True)
    check_out_time: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # ─── Capacity ──────────────────────────────────────────────────
    total_capacity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    # ─── State ─────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    # ─── Detail-page content (added in details upgrade) ──────────
    useful_tips: Mapped[str | None] = mapped_column(Text, nullable=True)
    house_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    check_in_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    neighborhood_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_maps_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ─── Relationships ─────────────────────────────────────────────
    facilities: Mapped[list["HotelFacility"]] = relationship(
        back_populates="hotel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="HotelFacility.name",
    )
    images: Mapped[list["HotelImage"]] = relationship(
        back_populates="hotel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="HotelImage.sort_order",
    )
    inclusions: Mapped[list["HotelInclusion"]] = relationship(
        back_populates="hotel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="HotelInclusion.sort_order",
    )
    exclusions: Mapped[list["HotelExclusion"]] = relationship(
        back_populates="hotel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="HotelExclusion.sort_order",
    )
    faqs: Mapped[list["HotelFAQ"]] = relationship(
        back_populates="hotel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="HotelFAQ.sort_order",
    )
    tips: Mapped[list["HotelTip"]] = relationship(
        back_populates="hotel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="HotelTip.sort_order",
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        for key in ("name", "address", "check_in_time", "check_out_time"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        kwargs.setdefault("stars", DEFAULT_HOTEL_STARS)
        kwargs.setdefault("total_capacity", 1)
        kwargs.setdefault("is_active", True)

        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Hotel id={self.id} name={self.name!r} stars={self.stars}>"


# ═══════════════════════════════════════════════════════════════════
#  Child: hotel_facilities
# ═══════════════════════════════════════════════════════════════════
class HotelFacility(Base):
    """
    A named amenity belonging to a hotel.

    Columns
    -------
    id       : surrogate PK
    hotel_id : FK to hotels (cascade delete)
    name     : free-form amenity name ("Outdoor pool", "Rooftop bar", ...)
    type     : CHECK over a small set of categories (for filtering)
    quantity : optional positive integer ("2 pools")
    notes    : optional free-form context ("heated Oct-Apr")
    """

    __tablename__ = "hotel_facilities"
    __table_args__ = (
        CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name="quantity_check",
        ),
        CheckConstraint(
            "type IN ('general','wellness','dining','sport','family',"
            "'business','other')",
            name="type_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    hotel_id: Mapped[int] = mapped_column(
        ForeignKey("hotels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)

    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_FACILITY_TYPE,
        server_default=DEFAULT_FACILITY_TYPE,
    )

    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    hotel: Mapped[Hotel] = relationship(back_populates="facilities")

    def __init__(self, **kwargs: object) -> None:
        for key in ("name", "type", "notes"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()
        if not kwargs.get("type"):
            kwargs["type"] = DEFAULT_FACILITY_TYPE
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HotelFacility id={self.id} hotel_id={self.hotel_id} name={self.name!r}>"


# ═══════════════════════════════════════════════════════════════════
#  Child: hotel_images
# ═══════════════════════════════════════════════════════════════════
class HotelImage(Base):
    """A gallery image for a hotel, tagged with a semantic type."""

    __tablename__ = "hotel_images"
    __table_args__ = (
        CheckConstraint(
            "type IN ('exterior','lobby','room','restaurant','pool',"
            "'beach','spa','other')",
            name="type_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    hotel_id: Mapped[int] = mapped_column(
        ForeignKey("hotels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(String(500), nullable=False)

    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_HOTEL_IMAGE_TYPE,
        server_default=DEFAULT_HOTEL_IMAGE_TYPE,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    media_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="image",
        server_default="image",
    )
    poster_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    hotel: Mapped[Hotel] = relationship(back_populates="images")

    def __init__(self, **kwargs: object) -> None:
        for key in ("url", "type"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()
        if not kwargs.get("type"):
            kwargs["type"] = DEFAULT_HOTEL_IMAGE_TYPE
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HotelImage id={self.id} hotel_id={self.hotel_id} type={self.type!r}>"
