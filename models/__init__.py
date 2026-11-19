"""
models/__init__.py
"""
from __future__ import annotations
from datetime import datetime
from typing import ClassVar
from sqlalchemy import DateTime, MetaData, String, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s", "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s", "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={getattr(self, 'id', None)}>"

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class SlugMixin:
    __slug_source__: ClassVar[str] = "name"
    slug: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True, index=True)

    @classmethod
    def _generate_slug(cls, source_value: str | None) -> str | None:
        if not source_value: return None
        from slugify import slugify
        return slugify(source_value)[:160]

    @classmethod
    def _generate_unique_slug(
        cls,
        source_value: str | None,
        session,
        exclude=None,
    ) -> str | None:
        """Generate a unique, URL-safe slug for a model instance."""
        base_slug = cls._generate_slug(source_value)
        if not base_slug:
            return None

        excluded_id = getattr(exclude, "id", exclude)
        candidate = base_slug
        suffix = 2

        while True:
            stmt = select(cls.id).where(cls.slug == candidate)
            if excluded_id is not None:
                stmt = stmt.where(cls.id != excluded_id)
            if session.scalar(stmt) is None:
                return candidate

            suffix_text = f"-{suffix}"
            candidate = f"{base_slug[:160 - len(suffix_text)]}{suffix_text}"
            suffix += 1

# ─── Model Imports (Hotels Only) ───────────────────────────────────
from models.user import (User, ROLE_ADMIN, ROLE_CUSTOMER, VALID_ROLES, BCRYPT_ROUNDS)
from models.destination import Destination
from models.supplier import Supplier
from models.hotel import (Hotel, HotelFacility, HotelImage, VALID_HOTEL_IMAGE_TYPES, DEFAULT_HOTEL_IMAGE_TYPE)
from models.room import (Room, RoomImage, VALID_ROOM_MEAL_PLANS, DEFAULT_ROOM_MEAL_PLAN)
from models.room_rate import RoomRate
from models.booking import (
    Booking, PRODUCT_TYPE_HOTEL, VALID_PRODUCT_TYPES,
    STATUS_PENDING, STATUS_CONFIRMED, STATUS_CANCELLED, STATUS_COMPLETED,
    STATUS_REFUNDED, VALID_BOOKING_STATUSES, DEFAULT_BOOKING_STATUS,
)
from models.booking_item import BookingItem
from models.booking_room import BookingRoom
from models.booking_traveller import BookingTraveller
from models.payment import Payment
from models.booking_status_history import BookingStatusHistory
from models.newsletter import Newsletter
from models.hotel_children import HotelInclusion, HotelExclusion, HotelFAQ, HotelTip
from models.site_content import (
    SiteContent, CONTENT_TYPE_TEXT, CONTENT_TYPE_HTML, CONTENT_TYPE_IMAGE_URL, CONTENT_TYPE_MARKDOWN,
    VALID_CONTENT_TYPES, DEFAULT_CONTENT_TYPE, PAGE_HOME, PAGE_ABOUT, PAGE_CONTACT,
    PAGE_FOOTER, PAGE_GLOBAL, PAGE_SLIDESHOW, VALID_PAGES, DEFAULT_PAGE, SLIDESHOW_SLOT_COUNT,
)
from models.quote import (
    Quote, STATUS_DRAFT, STATUS_SENT, STATUS_ACCEPTED, STATUS_DECLINED, STATUS_EXPIRED,
    STATUS_CANCELLED as STATUS_QUOTE_CANCELLED, VALID_QUOTE_STATUSES, DEFAULT_QUOTE_STATUS,
    PRODUCT_TYPE_HOTEL as QUOTE_PRODUCT_TYPE_HOTEL, VALID_QUOTE_PRODUCT_TYPES,
)
from models.home_offer import (
    HomeOffer, SECTION_BEST_HOTEL, VALID_SECTIONS, PRODUCT_HOTEL, VALID_PRODUCT_TYPES as HOME_OFFER_PRODUCT_TYPES,
)
