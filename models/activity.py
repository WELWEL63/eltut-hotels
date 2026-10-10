"""
models/activity.py
──────────────────
The activities table — sellable experiences (Pyramids tour, Nile cruise,
desert safari, diving trip, ...).

This file also defines the six child tables that belong to an activity:

    activity_prices       adult/child price per validity window
    activity_images       gallery images with sort order
    activity_inclusions   "what is included" bullet list
    activity_exclusions   "what is NOT included" bullet list
    activity_languages    languages the activity is delivered in

DESIGN NOTES
    - `code` is UNIQUE — human-friendly booking code used in admin/exports.
    - `name` is UNIQUE — no two activities share a marketing name.
    - `slug` is auto-derived from `name` via SlugMixin (SEO URLs).
    - `destination_id` is REQUIRED (an activity always happens somewhere).
    - `guide_id` is OPTIONAL (some activities are self-guided).
    - Enumerated string fields use CHECK constraints over a small known
      set. This keeps reports valid while remaining easy to extend via a
      future migration (no Postgres type migration required).
    - `capacity` is a positive integer used by availability_service.
    - `min_age <= max_age` is enforced when both are present.
    - Child tables use ON DELETE CASCADE so deleting an activity cleans
      up its own children; the ORM relationship uses delete-orphan +
      passive_deletes so SQLAlchemy does not try to NULL the FKs.
    - Instance defaults (is_active, and string stripping) are applied in
      __init__ so unsaved instances behave like DB-loaded ones.
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
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base, SlugMixin, TimestampMixin


# ─── Constants ─────────────────────────────────────────────────────
ACTIVITY_CATEGORY_HISTORY: str = "history"
ACTIVITY_CATEGORY_ADVENTURE: str = "adventure"
ACTIVITY_CATEGORY_CULTURAL: str = "cultural"
ACTIVITY_CATEGORY_WATER: str = "water"
ACTIVITY_CATEGORY_DESERT: str = "desert"
ACTIVITY_CATEGORY_FOOD: str = "food"
ACTIVITY_CATEGORY_OTHER: str = "other"

VALID_ACTIVITY_CATEGORIES: tuple[str, ...] = (
    ACTIVITY_CATEGORY_HISTORY,
    ACTIVITY_CATEGORY_ADVENTURE,
    ACTIVITY_CATEGORY_CULTURAL,
    ACTIVITY_CATEGORY_WATER,
    ACTIVITY_CATEGORY_DESERT,
    ACTIVITY_CATEGORY_FOOD,
    ACTIVITY_CATEGORY_OTHER,
)
DEFAULT_ACTIVITY_CATEGORY: str = ACTIVITY_CATEGORY_OTHER

ACTIVITY_DIFFICULTY_EASY: str = "easy"
ACTIVITY_DIFFICULTY_MODERATE: str = "moderate"
ACTIVITY_DIFFICULTY_CHALLENGING: str = "challenging"

VALID_ACTIVITY_DIFFICULTIES: tuple[str, ...] = (
    ACTIVITY_DIFFICULTY_EASY,
    ACTIVITY_DIFFICULTY_MODERATE,
    ACTIVITY_DIFFICULTY_CHALLENGING,
)
DEFAULT_ACTIVITY_DIFFICULTY: str = ACTIVITY_DIFFICULTY_EASY

TRANSPORT_NONE: str = "none"
TRANSPORT_BUS: str = "bus"
TRANSPORT_CAR: str = "car"
TRANSPORT_BOAT: str = "boat"
TRANSPORT_WALKING: str = "walking"
TRANSPORT_FLIGHT: str = "flight"
TRANSPORT_OTHER: str = "other"

VALID_TRANSPORT_TYPES: tuple[str, ...] = (
    TRANSPORT_NONE,
    TRANSPORT_BUS,
    TRANSPORT_CAR,
    TRANSPORT_BOAT,
    TRANSPORT_WALKING,
    TRANSPORT_FLIGHT,
    TRANSPORT_OTHER,
)
DEFAULT_TRANSPORT_TYPE: str = TRANSPORT_NONE

MEALS_NONE: str = "none"
MEALS_BREAKFAST: str = "breakfast"
MEALS_HALF_BOARD: str = "half_board"
MEALS_FULL_BOARD: str = "full_board"

VALID_MEAL_PLANS: tuple[str, ...] = (
    MEALS_NONE,
    MEALS_BREAKFAST,
    MEALS_HALF_BOARD,
    MEALS_FULL_BOARD,
)
DEFAULT_MEALS: str = MEALS_NONE


# ═══════════════════════════════════════════════════════════════════
#  Parent: activities
# ═══════════════════════════════════════════════════════════════════
class Activity(Base, SlugMixin, TimestampMixin):
    """
    A sellable tour/experience.

    Columns
    -------
    id                  : surrogate PK
    code                : unique booking code (ACT-0001)
    name                : unique marketing name
    slug                : SEO URL slug (from name)
    destination_id      : REQUIRED FK to destinations
    guide_id            : OPTIONAL FK to guides
    category            : CHECK over 7 known values
    description         : long-form marketing copy
    duration_hours      : NUMERIC(5,2) — allows half-hour granularity
    difficulty          : CHECK easy|moderate|challenging
    min_age / max_age   : optional age range; CHECK min <= max
    schedule            : free-form "Daily 09:00" / "Sun/Tue/Thu"
    meeting_point       : free-form pickup point
    departure_time      : free-form "09:00"
    return_time         : free-form "17:00"
    capacity            : REQUIRED, positive (availability uses this)
    transportation_type : CHECK over 7 known values
    meals_included      : CHECK none|breakfast|half_board|full_board
    what_to_bring       : free-form packing notes
    cancellation_policy : free-form policy text
    accessibility       : free-form accessibility notes
    special_offers      : free-form promotional text
    is_active           : soft-disable flag
    created_at / updated_at : from TimestampMixin
    """

    __tablename__ = "activities"
    __table_args__ = (
        CheckConstraint("duration_hours > 0", name="duration_hours_check"),
        CheckConstraint("capacity > 0", name="capacity_check"),
        CheckConstraint(
            "min_age IS NULL OR max_age IS NULL OR min_age <= max_age",
            name="age_range_check",
        ),
        CheckConstraint(
            "category IN ('history','adventure','cultural','water',"
            "'desert','food','other')",
            name="category_check",
        ),
        CheckConstraint(
            "difficulty IN ('easy','moderate','challenging')",
            name="difficulty_check",
        ),
        CheckConstraint(
            "transportation_type IN ('none','bus','car','boat','walking',"
            "'flight','other')",
            name="transportation_check",
        ),
        CheckConstraint(
            "meals_included IN ('none','breakfast','half_board','full_board')",
            name="meals_check",
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
    destination_id: Mapped[int] = mapped_column(
        ForeignKey("destinations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    guide_id: Mapped[int | None] = mapped_column(
        ForeignKey("guides.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ─── Classification ────────────────────────────────────────────
    category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=DEFAULT_ACTIVITY_CATEGORY,
        server_default=DEFAULT_ACTIVITY_CATEGORY,
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── Logistics ─────────────────────────────────────────────────
    duration_hours: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("1.00"),
        server_default="1.00",
    )

    difficulty: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_ACTIVITY_DIFFICULTY,
        server_default=DEFAULT_ACTIVITY_DIFFICULTY,
    )

    min_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_age: Mapped[int | None] = mapped_column(Integer, nullable=True)

    schedule: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meeting_point: Mapped[str | None] = mapped_column(String(255), nullable=True)
    departure_time: Mapped[str | None] = mapped_column(String(20), nullable=True)
    return_time: Mapped[str | None] = mapped_column(String(20), nullable=True)

    capacity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    transportation_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_TRANSPORT_TYPE,
        server_default=DEFAULT_TRANSPORT_TYPE,
    )

    meals_included: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_MEALS,
        server_default=DEFAULT_MEALS,
    )

    # ─── Content ───────────────────────────────────────────────────
    what_to_bring: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    accessibility: Mapped[str | None] = mapped_column(Text, nullable=True)
    special_offers: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── State ─────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    # ─── Relationships ─────────────────────────────────────────────
    prices: Mapped[list["ActivityPrice"]] = relationship(
        back_populates="activity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ActivityPrice.id",
    )
    images: Mapped[list["ActivityImage"]] = relationship(
        back_populates="activity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ActivityImage.sort_order",
    )
    inclusions: Mapped[list["ActivityInclusion"]] = relationship(
        back_populates="activity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ActivityInclusion.sort_order",
    )
    exclusions: Mapped[list["ActivityExclusion"]] = relationship(
        back_populates="activity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ActivityExclusion.sort_order",
    )
    languages: Mapped[list["ActivityLanguage"]] = relationship(
        back_populates="activity",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ActivityLanguage.language",
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        strip_fields = (
            "code", "name", "category", "difficulty",
            "transportation_type", "meals_included",
            "schedule", "meeting_point", "departure_time", "return_time",
        )
        for key in strip_fields:
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        defaults = {
            "category": DEFAULT_ACTIVITY_CATEGORY,
            "difficulty": DEFAULT_ACTIVITY_DIFFICULTY,
            "transportation_type": DEFAULT_TRANSPORT_TYPE,
            "meals_included": DEFAULT_MEALS,
        }
        for key, default in defaults.items():
            if not kwargs.get(key):
                kwargs[key] = default

        kwargs.setdefault("is_active", True)

        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Activity id={self.id} code={self.code!r} name={self.name!r}>"


# ═══════════════════════════════════════════════════════════════════
#  Child: activity_prices
# ═══════════════════════════════════════════════════════════════════
class ActivityPrice(Base):
    """
    One price row for an activity, valid over a date range.

    Multiple rows allow seasonal pricing. The pricing_service picks the
    row whose valid_from/valid_to window contains the requested date.
    Both date columns are optional — a NULL on either side means "open".
    """

    __tablename__ = "activity_prices"
    __table_args__ = (
        CheckConstraint("adult_price >= 0", name="adult_price_check"),
        CheckConstraint("child_price >= 0", name="child_price_check"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="validity_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
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

    activity: Mapped[Activity] = relationship(back_populates="prices")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ActivityPrice id={self.id} activity_id={self.activity_id}>"


# ═══════════════════════════════════════════════════════════════════
#  Child: activity_images
# ═══════════════════════════════════════════════════════════════════
class ActivityImage(Base):
    """A gallery image for an activity."""

    __tablename__ = "activity_images"

    id: Mapped[int] = mapped_column(primary_key=True)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(String(500), nullable=False)
    caption: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # WHY media_type: distinguishes still images from videos. Defaults
    # to 'image' so existing rows and code paths keep working unchanged.
    # WHY poster_url: videos need a preview image. NULL for stills.
    media_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="image",
        server_default="image",
    )
    poster_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    activity: Mapped[Activity] = relationship(back_populates="images")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ActivityImage id={self.id} activity_id={self.activity_id}>"


# ═══════════════════════════════════════════════════════════════════
#  Child: activity_inclusions
# ═══════════════════════════════════════════════════════════════════
class ActivityInclusion(Base):
    """One bullet item in the 'what's included' list."""

    __tablename__ = "activity_inclusions"

    id: Mapped[int] = mapped_column(primary_key=True)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    activity: Mapped[Activity] = relationship(back_populates="inclusions")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ActivityInclusion id={self.id} activity_id={self.activity_id}>"


# ═══════════════════════════════════════════════════════════════════
#  Child: activity_exclusions
# ═══════════════════════════════════════════════════════════════════
class ActivityExclusion(Base):
    """One bullet item in the 'what's NOT included' list."""

    __tablename__ = "activity_exclusions"

    id: Mapped[int] = mapped_column(primary_key=True)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    activity: Mapped[Activity] = relationship(back_populates="exclusions")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ActivityExclusion id={self.id} activity_id={self.activity_id}>"


# ═══════════════════════════════════════════════════════════════════
#  Child: activity_languages
# ═══════════════════════════════════════════════════════════════════
class ActivityLanguage(Base):
    """A language in which an activity is delivered."""

    __tablename__ = "activity_languages"
    __table_args__ = (
        UniqueConstraint("activity_id", "language", name="activity_language_uq"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    language: Mapped[str] = mapped_column(String(60), nullable=False)

    activity: Mapped[Activity] = relationship(back_populates="languages")

    def __init__(self, **kwargs: object) -> None:
        lang = kwargs.get("language")
        if isinstance(lang, str):
            kwargs["language"] = lang.strip()
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ActivityLanguage id={self.id} "
            f"activity_id={self.activity_id} language={self.language!r}>"
        )
