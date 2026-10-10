"""
models/airline.py
─────────────────
Master list of airlines and their logos.

WHY THIS EXISTS
    Packages reference airlines by name (Flight.airline_name). We want to
    display the airline's logo next to each flight, but we don't want to
    upload the same logo for every package that uses easyJet. So we keep
    a master list here, keyed by name (case-insensitive), and match
    against it at render time.

MATCHING RULE
    Given a Flight.airline_name like "easyJet", we look up:
        SELECT * FROM airlines WHERE lower(name) = lower('easyJet')
    If a row is found, we render its logo. If not, we render the name
    without a logo (graceful fallback — no broken images).

LOGO STORAGE
    Logos are uploaded to static/images/airlines/<slug>.png (SHA-1 named
    like our product images). The upload endpoint reuses the same
    infrastructure as media_routes.

ADMIN
    Managed from /admin/airlines — list, add, edit, upload logo,
    toggle active, delete (with a guard against airlines still
    referenced by flights).
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, SlugMixin, TimestampMixin


# Uploaded logo extensions we accept
VALID_AIRLINE_LOGO_EXT: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".svg", ".webp")
DEFAULT_AIRLINE_LOGO_EXT: str = ".png"


class Airline(Base, SlugMixin, TimestampMixin):
    """Master list of airlines and their logos."""

    __tablename__ = "airlines"
    __table_args__ = (
        UniqueConstraint("name", name="airline_name_uq"),
        UniqueConstraint("slug", name="airline_slug_uq"),
        CheckConstraint(
            "LENGTH(TRIM(name)) > 0",
            name="name_not_blank_check",
        ),
    )

    __slug_source__ = "name"

    id: Mapped[int] = mapped_column(primary_key=True)

    # ─── Identity ────────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        unique=True,
        index=True,
    )
    # slug from SlugMixin (unique, indexed)

    # ─── Presentation ────────────────────────────────────────────────
    logo_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # ─── Metadata ────────────────────────────────────────────────────
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── State ───────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    def __init__(self, **kwargs: object) -> None:
        for key in ("name", "country"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        if kwargs.get("is_active") is None:
            kwargs["is_active"] = True

        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Airline id={self.id} name={self.name!r}>"


__all__ = [
    "Airline",
    "VALID_AIRLINE_LOGO_EXT",
    "DEFAULT_AIRLINE_LOGO_EXT",
]
