"""
models/home_offer.py
────────────────────
Admin-curated home page offers.

An "offer" is a pointer to a product (activity / hotel / package) that
the admin wants to display in one of the home page sections:

    - top_experience      -> activities
    - best_hotel          -> hotels
    - affordable_package  -> packages

DESIGN
    Polymorphic - one table holds all three product types. The FK is
    not enforced at the DB level (product_id can point at any of three
    tables), so referential integrity is checked in the admin service.

    The home page reads this table per section, ordered by sort_order.
    If a section has no active offers, the public route falls back to
    its previous "cheapest per destination" behaviour so the site never
    shows an empty section.

    Deleting a product out from under an offer is handled at read time
    (missing products are skipped) - no cascade needed.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, TimestampMixin


# Valid section keys - keep in sync with blueprints/admin/offer_admin.py
SECTION_TOP_EXPERIENCE = "top_experience"
SECTION_BEST_HOTEL = "best_hotel"
SECTION_AFFORDABLE_PACKAGE = "affordable_package"

VALID_SECTIONS = {
    SECTION_TOP_EXPERIENCE,
    SECTION_BEST_HOTEL,
    SECTION_AFFORDABLE_PACKAGE,
}

# Valid product types (each section maps to exactly one, but we store
# the type explicitly so lookups are simple and future-proof).
PRODUCT_ACTIVITY = "activity"
PRODUCT_HOTEL = "hotel"
PRODUCT_PACKAGE = "package"

VALID_PRODUCT_TYPES = {PRODUCT_ACTIVITY, PRODUCT_HOTEL, PRODUCT_PACKAGE}


class HomeOffer(Base, TimestampMixin):
    """One admin-selected home page offer slot."""

    __tablename__ = "home_offers"
    __table_args__ = (
        # An offer slot is identified by (section, product_type, product_id)
        # - you cannot add the same product twice to the same section.
        UniqueConstraint(
            "section",
            "product_type",
            "product_id",
            name="section_product_unique",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    section: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    product_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<HomeOffer id={self.id} section={self.section!r} "
            f"{self.product_type}#{self.product_id} sort={self.sort_order} "
            f"active={self.is_active}>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "section": self.section,
            "product_type": self.product_type,
            "product_id": self.product_id,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
