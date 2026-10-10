"""
models/__init__.py
──────────────────
SQLAlchemy 2.x declarative base, shared mixins, and the single import
surface for every model in the application.

WHY THIS FILE EXISTS
    Flask-Migrate / Alembic can only autogenerate migrations for models
    that have been imported *before* the migration runs. This file imports
    every model exactly once, in dependency order, so a single line is
    enough:

        from models import *          # noqa: F401,F403 — side-effect

    It also makes cross-file relationships "just work": importing any
    one model file triggers this package's __init__, which imports all
    of them, so SQLAlchemy can resolve every string class reference.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from sqlalchemy import DateTime, MetaData, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ═══════════════════════════════════════════════════════════════════
#  Base
# ═══════════════════════════════════════════════════════════════════
class Base(DeclarativeBase):
    """Declarative base for every SQLAlchemy model in the project."""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )

    def __repr__(self) -> str:  # pragma: no cover
        pk = getattr(self, "id", None)
        return f"<{self.__class__.__name__} id={pk}>"


# ═══════════════════════════════════════════════════════════════════
#  Mixins
# ═══════════════════════════════════════════════════════════════════
class TimestampMixin:
    """Adds created_at / updated_at columns with DB-side defaults."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SlugMixin:
    """Adds a nullable unique `slug` column and `_generate_slug()` helper."""

    __slug_source__: ClassVar[str] = "name"

    slug: Mapped[str | None] = mapped_column(
        String(160),
        unique=True,
        nullable=True,
        index=True,
    )

    @classmethod
    def _generate_slug(cls, source_value: str | None) -> str | None:
        """
        Turn a source string into a URL-safe slug.

        This method does NOT check for collisions. Use
        _generate_unique_slug() when inserting into a session and the
        slug column has a UNIQUE constraint — it appends a numeric
        suffix until the slug is free.
        """
        if not source_value:
            return None
        from slugify import slugify  # noqa: PLC0415 — optional dependency

        return slugify(source_value)[:160]

    @classmethod
    def _generate_unique_slug(
        cls, source_value: str | None, session
    ) -> str | None:
        """
        Generate a slug that does not collide with an existing row.

        Used by seeders and any bulk-insert path where the source data
        may contain duplicate names. Falls back to -2, -3, ... suffixes
        until the slug is unique within this table.

        Parameters
        ----------
        source_value : str | None
        session : sqlalchemy.orm.Session
            Any active session bound to the metadata for this model.
        """
        base = cls._generate_slug(source_value)
        if base is None:
            return None

        # Import here to avoid a top-level circular import in the mixin.
        from sqlalchemy import select as _select  # noqa: PLC0415

        table = cls.__table__  # type: ignore[attr-defined]
        slug_col = table.c.slug

        candidate = base
        suffix = 1
        while session.scalar(
            _select(table.c.id).where(slug_col == candidate).limit(1)
        ) is not None:
            suffix += 1
            candidate = f"{base}-{suffix}"
            if suffix > 1000:  # safety net
                candidate = f"{base}-{suffix}-{id(session)}"
                break
        return candidate


# ═══════════════════════════════════════════════════════════════════
#  Model imports — single source of truth for Alembic
# ═══════════════════════════════════════════════════════════════════
# One import per model file. This block is what makes cross-file
# relationships resolvable at mapper-config time, and what Alembic
# reads when autogenerating migrations.

from models.user import (  # noqa: F401,E402
    User,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    VALID_ROLES,
    BCRYPT_ROUNDS,
)
from models.destination import Destination  # noqa: F401,E402
from models.guide import Guide  # noqa: F401,E402
from models.supplier import Supplier  # noqa: F401,E402

from models.activity import (  # noqa: F401,E402
    Activity,
    ActivityImage,
    VALID_ACTIVITY_CATEGORIES,
    VALID_ACTIVITY_DIFFICULTIES,
    VALID_TRANSPORT_TYPES,
    VALID_MEAL_PLANS,
    ActivityInclusion,
    ActivityExclusion,
    ActivityLanguage,
    ActivityPrice,
)

from models.hotel import (  # noqa: F401,E402
    Hotel,
    HotelFacility,
    HotelImage,
    VALID_HOTEL_IMAGE_TYPES,
    DEFAULT_HOTEL_IMAGE_TYPE,
)
from models.room import (  # noqa: F401,E402
    Room,
    RoomImage,
    VALID_ROOM_MEAL_PLANS,
    DEFAULT_ROOM_MEAL_PLAN,
)

from models.package import (  # noqa: F401,E402
    Package,
    VALID_PACKAGE_TYPES,
    DEFAULT_PACKAGE_TYPE,
    PackageImage,
    PackageInclusion,
    PackageExclusion,
    PackageItinerary,
    PackagePrice,
    VALID_PACKAGE_IMAGE_TYPES,
    DEFAULT_PACKAGE_IMAGE_TYPE,
)

from models.flight import Flight  # noqa: F401,E402
from models.room_rate import RoomRate  # noqa: F401,E402

from models.booking import (  # noqa: F401,E402
    Booking,
    PRODUCT_TYPE_ACTIVITY,
    PRODUCT_TYPE_HOTEL,
    PRODUCT_TYPE_PACKAGE,
    VALID_PRODUCT_TYPES,
    STATUS_PENDING,
    STATUS_CONFIRMED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_REFUNDED,
    VALID_BOOKING_STATUSES,
    DEFAULT_BOOKING_STATUS,
)
from models.booking_item import BookingItem  # noqa: F401,E402
from models.booking_traveller import BookingTraveller  # noqa: F401,E402
from models.payment import Payment  # noqa: F401,E402
from models.booking_status_history import BookingStatusHistory  # noqa: F401,E402
from models.newsletter import Newsletter  # noqa: F401,E402

# ─── Product detail-page children (details upgrade) ────────────────
from models.hotel_children import (  # noqa: F401,E402
    HotelInclusion,
    HotelExclusion,
    HotelFAQ,
    HotelTip,
)
from models.package_children import (  # noqa: F401,E402
    PackageFAQ,
    PackageTip,
)
from models.activity_children import (  # noqa: F401,E402
    ActivityFAQ,
    ActivityTip,
)

# ─── Content management + quotes (details upgrade) ─────────────────
from models.site_content import (  # noqa: F401,E402
    SiteContent,
    CONTENT_TYPE_TEXT,
    CONTENT_TYPE_HTML,
    CONTENT_TYPE_IMAGE_URL,
    CONTENT_TYPE_MARKDOWN,
    VALID_CONTENT_TYPES,
    DEFAULT_CONTENT_TYPE,
    PAGE_HOME,
    PAGE_ABOUT,
    PAGE_CONTACT,
    PAGE_FOOTER,
    PAGE_GLOBAL,
    PAGE_SLIDESHOW,
    VALID_PAGES,
    DEFAULT_PAGE,
    SLIDESHOW_SLOT_COUNT,
)
from models.quote import (  # noqa: F401,E402
    Quote,
    STATUS_DRAFT,
    STATUS_SENT,
    STATUS_ACCEPTED,
    STATUS_DECLINED,
    STATUS_EXPIRED,
    STATUS_CANCELLED as STATUS_QUOTE_CANCELLED,
    VALID_QUOTE_STATUSES,
    DEFAULT_QUOTE_STATUS,
    PRODUCT_TYPE_ACTIVITY as QUOTE_PRODUCT_TYPE_ACTIVITY,
    PRODUCT_TYPE_HOTEL as QUOTE_PRODUCT_TYPE_HOTEL,
    PRODUCT_TYPE_PACKAGE as QUOTE_PRODUCT_TYPE_PACKAGE,
    VALID_QUOTE_PRODUCT_TYPES,
)


__all__: list[str] = [
    "Base",
    "TimestampMixin",
    "SlugMixin",
    "User",
    "ROLE_ADMIN",
    "ROLE_CUSTOMER",
    "VALID_ROLES",
    "BCRYPT_ROUNDS",
    "Destination",
    "Guide",
    "Supplier",
    "Activity",
    "ActivityImage",
    "VALID_ACTIVITY_CATEGORIES",
    "VALID_ACTIVITY_DIFFICULTIES",
    "VALID_TRANSPORT_TYPES",
    "VALID_MEAL_PLANS",
    "ActivityInclusion",
    "ActivityExclusion",
    "ActivityLanguage",
    "ActivityPrice",
    "Hotel",
    "HotelFacility",
    "HotelImage",
    "Room",
    "RoomImage",
    "RoomRate",
    "VALID_ROOM_MEAL_PLANS",
    "DEFAULT_ROOM_MEAL_PLAN",
    "Package",
    "VALID_PACKAGE_TYPES",
    "DEFAULT_PACKAGE_TYPE",
    "PackageImage",
    "PackageInclusion",
    "PackageExclusion",
    "PackageItinerary",
    "PackagePrice",
    "Flight",
    "Booking",
    "PRODUCT_TYPE_ACTIVITY",
    "PRODUCT_TYPE_HOTEL",
    "PRODUCT_TYPE_PACKAGE",
    "VALID_PRODUCT_TYPES",
    "STATUS_PENDING",
    "STATUS_CONFIRMED",
    "STATUS_CANCELLED",
    "STATUS_COMPLETED",
    "STATUS_REFUNDED",
    "VALID_BOOKING_STATUSES",
    "DEFAULT_BOOKING_STATUS",
    "BookingItem",
    "BookingTraveller",
    "Payment",
    "BookingStatusHistory",
    "Newsletter",
    # Content management
    "SiteContent",
    "CONTENT_TYPE_TEXT",
    "CONTENT_TYPE_HTML",
    "CONTENT_TYPE_IMAGE_URL",
    "CONTENT_TYPE_MARKDOWN",
    "VALID_CONTENT_TYPES",
    "DEFAULT_CONTENT_TYPE",
    "PAGE_HOME",
    "PAGE_ABOUT",
    "PAGE_CONTACT",
    "PAGE_FOOTER",
    "PAGE_GLOBAL",
    "PAGE_SLIDESHOW",
    "VALID_PAGES",
    "DEFAULT_PAGE",
    "SLIDESHOW_SLOT_COUNT",
    # Quotes
    "Quote",
    "STATUS_DRAFT",
    "STATUS_SENT",
    "STATUS_ACCEPTED",
    "STATUS_DECLINED",
    "STATUS_EXPIRED",
    "STATUS_QUOTE_CANCELLED",
    "VALID_QUOTE_STATUSES",
    "DEFAULT_QUOTE_STATUS",
    "QUOTE_PRODUCT_TYPE_ACTIVITY",
    "QUOTE_PRODUCT_TYPE_HOTEL",
    "QUOTE_PRODUCT_TYPE_PACKAGE",
    "VALID_QUOTE_PRODUCT_TYPES",
    # Product detail-page children
    "HotelInclusion",
    "HotelExclusion",
    "HotelFAQ",
    "HotelTip",
    "PackageFAQ",
    "PackageTip",
    "ActivityFAQ",
    "ActivityTip",
]
