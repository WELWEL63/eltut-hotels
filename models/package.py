"""
models/package.py
─────────────────
The packages table — the third and most complex product type — plus its
five child tables:

    package_prices       adult/child price per validity window
    package_images       gallery images with sort order + type
    package_inclusions   "what is included" bullet list
    package_exclusions   "what is NOT included" bullet list
    package_itineraries  day_number + title + description (Day 1..N)

Flights (which reference suppliers) live in models/flight.py (File 10).

DESIGN NOTES
    - `code` is UNIQUE — human-friendly booking code (PKG-0001).
    - `name` is UNIQUE — no two packages share a marketing name.
    - `slug` is auto-derived from `name` via SlugMixin (SEO URLs).
    - `hotel_id`, `room_id`, `destination_id` are all REQUIRED. The
      package has a base hotel + room in a destination. They use
      ondelete="RESTRICT" so a hotel/room cannot be deleted while a
      package references it.
    - `package_type` uses a small CHECK set that stays easy to extend.
    - Deposit and visa rules are explicit columns so the pricing service
      and payment flow can read them without parsing free text.
    - `package_itineraries` UNIQUE(package_id, day_number) prevents two
      rows claiming to be "Day 3".
    - All children cascade-delete with the parent (DB + ORM).
    - Instance defaults applied in __init__ so unsaved instances read the
      same as DB-loaded ones.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base, SlugMixin, TimestampMixin


# ─── Constants ─────────────────────────────────────────────────────
PACKAGE_TYPE_HOLIDAY: str = "holiday"
PACKAGE_TYPE_HONEYMOON: str = "honeymoon"
PACKAGE_TYPE_FAMILY: str = "family"
PACKAGE_TYPE_ADVENTURE: str = "adventure"
PACKAGE_TYPE_CRUISE: str = "cruise"
PACKAGE_TYPE_WEEKEND: str = "weekend"
PACKAGE_TYPE_OTHER: str = "other"

VALID_PACKAGE_TYPES: tuple[str, ...] = (
    PACKAGE_TYPE_HOLIDAY,
    PACKAGE_TYPE_HONEYMOON,
    PACKAGE_TYPE_FAMILY,
    PACKAGE_TYPE_ADVENTURE,
    PACKAGE_TYPE_CRUISE,
    PACKAGE_TYPE_WEEKEND,
    PACKAGE_TYPE_OTHER,
)
DEFAULT_PACKAGE_TYPE: str = PACKAGE_TYPE_HOLIDAY

PACKAGE_IMAGE_TYPE_COVER: str = "cover"
PACKAGE_IMAGE_TYPE_HOTEL: str = "hotel"
PACKAGE_IMAGE_TYPE_ROOM: str = "room"
PACKAGE_IMAGE_TYPE_ACTIVITY: str = "activity"
PACKAGE_IMAGE_TYPE_DESTINATION: str = "destination"
PACKAGE_IMAGE_TYPE_OTHER: str = "other"

VALID_PACKAGE_IMAGE_TYPES: tuple[str, ...] = (
    PACKAGE_IMAGE_TYPE_COVER,
    PACKAGE_IMAGE_TYPE_HOTEL,
    PACKAGE_IMAGE_TYPE_ROOM,
    PACKAGE_IMAGE_TYPE_ACTIVITY,
    PACKAGE_IMAGE_TYPE_DESTINATION,
    PACKAGE_IMAGE_TYPE_OTHER,
)
DEFAULT_PACKAGE_IMAGE_TYPE: str = PACKAGE_IMAGE_TYPE_OTHER


# ═══════════════════════════════════════════════════════════════════
#  Parent: packages
# ═══════════════════════════════════════════════════════════════════
class Package(Base, SlugMixin, TimestampMixin):
    """
    A sellable multi-night package.

    Columns
    -------
    id                     : surrogate PK
    code                   : unique booking code (PKG-0001)
    name                   : unique marketing name
    slug                   : SEO URL slug (from name)
    hotel_id               : REQUIRED FK to hotels (RESTRICT delete)
    room_id                : REQUIRED FK to rooms (RESTRICT delete)
    destination_id         : REQUIRED FK to destinations (RESTRICT delete)
    package_type           : CHECK holiday|honeymoon|family|adventure|cruise|weekend|other
    description            : long-form marketing copy
    duration_nights        : positive integer (> 0)
    min_age / max_age      : optional age range; CHECK ordering
    capacity               : positive integer
    deposit_required       : bool
    deposit_percentage     : NUMERIC(5,2), 0..100 when required
    payment_deadline_days  : int >= 0
    visa_required          : bool
    visa_fee               : NUMERIC(10,2) >= 0
    cancellation_policy    : free-form policy text
    booking_terms          : free-form booking terms text
    is_active              : soft-disable flag
    created_at / updated_at : from TimestampMixin
    """

    __tablename__ = "packages"
    __table_args__ = (
        CheckConstraint("duration_nights > 0", name="duration_nights_check"),
        CheckConstraint("capacity > 0", name="capacity_check"),
        CheckConstraint(
            "min_age IS NULL OR max_age IS NULL OR min_age <= max_age",
            name="age_range_check",
        ),
        CheckConstraint(
            "deposit_percentage IS NULL "
            "OR (deposit_percentage >= 0 AND deposit_percentage <= 100)",
            name="deposit_percentage_check",
        ),
        CheckConstraint(
            "payment_deadline_days IS NULL OR payment_deadline_days >= 0",
            name="payment_deadline_days_check",
        ),
        CheckConstraint("visa_fee IS NULL OR visa_fee >= 0", name="visa_fee_check"),
        CheckConstraint(
            "package_type IN ('holiday','honeymoon','family','adventure',"
            "'cruise','weekend','other')",
            name="package_type_check",
        ),
    )

    __slug_source__ = "name"

    # ─── Identity ──────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(primary_key=True)

    code: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(
        String(200), unique=True, nullable=False, index=True
    )

    # ─── References ────────────────────────────────────────────────
    hotel_id: Mapped[int] = mapped_column(
        ForeignKey("hotels.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    destination_id: Mapped[int] = mapped_column(
        ForeignKey("destinations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ─── Classification ────────────────────────────────────────────
    package_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_PACKAGE_TYPE,
        server_default=DEFAULT_PACKAGE_TYPE,
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── Duration & capacity ───────────────────────────────────────
    duration_nights: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    min_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_age: Mapped[int | None] = mapped_column(Integer, nullable=True)

    capacity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    # ─── Deposit rules ─────────────────────────────────────────────
    deposit_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    deposit_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    payment_deadline_days: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # ─── Visa rules ────────────────────────────────────────────────
    visa_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    visa_fee: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    # ─── Policy text ───────────────────────────────────────────────
    cancellation_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    booking_terms: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── State ─────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    # ─── Relationships ─────────────────────────────────────────────
    prices: Mapped[list["PackagePrice"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PackagePrice.id",
    )
    images: Mapped[list["PackageImage"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PackageImage.sort_order",
    )
    inclusions: Mapped[list["PackageInclusion"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PackageInclusion.sort_order",
    )
    exclusions: Mapped[list["PackageExclusion"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PackageExclusion.sort_order",
    )
    itineraries: Mapped[list["PackageItinerary"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PackageItinerary.day_number",
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        for key in ("code", "name", "package_type"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        if not kwargs.get("package_type"):
            kwargs["package_type"] = DEFAULT_PACKAGE_TYPE

        kwargs.setdefault("duration_nights", 1)
        kwargs.setdefault("capacity", 1)
        kwargs.setdefault("deposit_required", False)
        kwargs.setdefault("visa_required", False)
        kwargs.setdefault("is_active", True)

        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Package id={self.id} code={self.code!r} name={self.name!r}>"


# ═══════════════════════════════════════════════════════════════════
#  Child: package_prices
# ═══════════════════════════════════════════════════════════════════
class PackagePrice(Base):
    """
    One price row for a package, valid over a date range.

    Multiple rows allow seasonal pricing. The pricing_service picks the
    row whose window contains the requested departure date.
    """

    __tablename__ = "package_prices"
    __table_args__ = (
        CheckConstraint("adult_price >= 0", name="adult_price_check"),
        CheckConstraint("child_price >= 0", name="child_price_check"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    adult_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    child_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default="USD"
    )

    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    package: Mapped[Package] = relationship(back_populates="prices")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PackagePrice id={self.id} package_id={self.package_id}>"


# ═══════════════════════════════════════════════════════════════════
#  Child: package_images
# ═══════════════════════════════════════════════════════════════════
class PackageImage(Base):
    """A gallery image for a package, tagged with a semantic type."""

    __tablename__ = "package_images"
    __table_args__ = (
        CheckConstraint(
            "type IN ('cover','hotel','room','activity','destination','other')",
            name="type_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(String(500), nullable=False)

    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_PACKAGE_IMAGE_TYPE,
        server_default=DEFAULT_PACKAGE_IMAGE_TYPE,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    package: Mapped[Package] = relationship(back_populates="images")

    def __init__(self, **kwargs: object) -> None:
        for key in ("url", "type"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()
        if not kwargs.get("type"):
            kwargs["type"] = DEFAULT_PACKAGE_IMAGE_TYPE
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PackageImage id={self.id} package_id={self.package_id} type={self.type!r}>"


# ═══════════════════════════════════════════════════════════════════
#  Child: package_inclusions
# ═══════════════════════════════════════════════════════════════════
class PackageInclusion(Base):
    """One bullet item in the 'what's included' list."""

    __tablename__ = "package_inclusions"

    id: Mapped[int] = mapped_column(primary_key=True)

    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item: Mapped[str] = mapped_column(String(255), nullable=False)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    package: Mapped[Package] = relationship(back_populates="inclusions")

    def __init__(self, **kwargs: object) -> None:
        item = kwargs.get("item")
        if isinstance(item, str):
            kwargs["item"] = item.strip()
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PackageInclusion id={self.id} package_id={self.package_id}>"


# ═══════════════════════════════════════════════════════════════════
#  Child: package_exclusions
# ═══════════════════════════════════════════════════════════════════
class PackageExclusion(Base):
    """One bullet item in the 'what's NOT included' list."""

    __tablename__ = "package_exclusions"

    id: Mapped[int] = mapped_column(primary_key=True)

    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item: Mapped[str] = mapped_column(String(255), nullable=False)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    package: Mapped[Package] = relationship(back_populates="exclusions")

    def __init__(self, **kwargs: object) -> None:
        item = kwargs.get("item")
        if isinstance(item, str):
            kwargs["item"] = item.strip()
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PackageExclusion id={self.id} package_id={self.package_id}>"


# ═══════════════════════════════════════════════════════════════════
#  Child: package_itineraries
# ═══════════════════════════════════════════════════════════════════
class PackageItinerary(Base):
    """
    One day in a package itinerary.

    UNIQUE(package_id, day_number) prevents two rows claiming to be
    "Day 3" of the same package. This is the normalised alternative to
    day_1 / day_2 / ... columns, which do not scale.
    """

    __tablename__ = "package_itineraries"
    __table_args__ = (
        UniqueConstraint("package_id", "day_number", name="package_day_uq"),
        CheckConstraint("day_number > 0", name="day_number_check"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    day_number: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str] = mapped_column(String(200), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    package: Mapped[Package] = relationship(back_populates="itineraries")

    def __init__(self, **kwargs: object) -> None:
        title = kwargs.get("title")
        if isinstance(title, str):
            kwargs["title"] = title.strip()
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PackageItinerary id={self.id} package_id={self.package_id} "
            f"day={self.day_number}>"
        )
