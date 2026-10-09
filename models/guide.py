"""
models/guide.py
───────────────
The guides table — the tour guides who lead activities.

Referenced by activities.guide_id (nullable — an activity may have no
assigned guide yet, or may be self-guided).

DESIGN NOTES
    - `licence_number` is UNIQUE — Egypt's tourism ministry issues one per
      guide. Enforced at the DB level so duplicate data can never slip in.
    - `full_name` is UNIQUE — two guides with the same name is confusing
      for booking staff and for reporting.
    - `languages` uses Postgres ARRAY(Text). Testing runs on SQLite, which
      has no native array type, so we ship a JSON variant for SQLite only.
      Alembic still generates Postgres ARRAY(...) in migrations.
    - `is_active` is a soft-delete flag: guides are never hard-deleted
      because historical activities need a name attached.
    - Instance defaults (is_active) are applied in __init__ so unsaved
      instances behave the same as DB-loaded ones (see models/user.py).
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String, Text, false, true
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from models import Base, TimestampMixin


class Guide(Base, TimestampMixin):
    """
    A licensed tour guide.

    Columns
    -------
    id               : surrogate PK
    full_name        : unique display name
    licence_number   : unique government-issued licence
    languages        : list of spoken languages (ARRAY in Postgres)
    bio              : long-form biography
    photo_url        : single profile image
    years_experience : non-negative integer (CHECK)
    is_active        : soft-disable flag; keeps history intact
    created_at / updated_at : from TimestampMixin
    """

    __tablename__ = "guides"
    __table_args__ = (
        # Suffix-only; Base.metadata naming convention produces
        # ck_guides_years_experience_check
        CheckConstraint(
            "years_experience >= 0",
            name="years_experience_check",
        ),
    )

    # ─── Identity ──────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(primary_key=True)

    full_name: Mapped[str] = mapped_column(
        String(150), unique=True, nullable=False, index=True
    )

    licence_number: Mapped[str] = mapped_column(
        String(80), unique=True, nullable=False, index=True
    )

    # ─── Capability ────────────────────────────────────────────────
    # Postgres: ARRAY(Text). SQLite (tests): JSON. Both store a list[str].
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(Text).with_variant(JSON, "sqlite"),
        nullable=False,
        default=list,
        server_default="{}",
    )

    # ─── Content ───────────────────────────────────────────────────
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)

    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ─── Experience ────────────────────────────────────────────────
    years_experience: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # ─── State ─────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default=true(),
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor — normalise + instance defaults
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        """
        Apply defaults and normalise input before SQLAlchemy sets attrs.

        - full_name and licence_number are stripped of surrounding whitespace
        - languages is coerced to a list; None becomes an empty list
        - years_experience defaults to 0 (avoids None in templates/reports)
        - is_active defaults to True so freshly constructed instances read
          the same as DB-loaded ones
        """
        for key in ("full_name", "licence_number"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        langs = kwargs.get("languages")
        if langs is None:
            kwargs["languages"] = []
        elif isinstance(langs, str):
            # Allow "Arabic, English" or "Arabic;English" to be passed in.
            parts = [p.strip() for p in langs.replace(";", ",").split(",")]
            kwargs["languages"] = [p for p in parts if p]

        kwargs.setdefault("years_experience", 0)
        kwargs.setdefault("is_active", True)

        super().__init__(**kwargs)

    # ─── Cosmetic ──────────────────────────────────────────────────
    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Guide id={self.id} name={self.full_name!r} "
            f"licence={self.licence_number!r}>"
        )
