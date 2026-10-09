"""
models/newsletter.py
────────────────────
The newsletters table — composed newsletter issues written by admins.

This stores CONTENT (the composed issue), not the subscriber list. The
subscriber list is a separate concern outside the current coursework
scope.

DESIGN NOTES
    - `title` is required; the slug is auto-derived from it via
      SlugMixin for SEO-shareable URLs (/newsletters/<slug>).
    - `content` is Text — format (HTML / Markdown / plain) is the
      admin's choice, we do not constrain it.
    - `header_image`, `body_image`, `video` match the exact field names
      in the coursework ERD.
    - `footer_text` is optional free-form text.
    - `is_published` (default False) separates drafting from publishing.
      `published_at` is set the first time an issue is published and is
      not touched on subsequent re-publishes — it records the FIRST
      publication date, which is what newsletter archives display.
    - `author_user_id` is NULLABLE (SET NULL) — the authoring account
      may later be deleted, but the issue must remain.
    - `is_active` is a soft-delete flag; historical newsletters are
      deactivated, never deleted.
    - Instance defaults applied in __init__ so unsaved instances read the
      same as DB-loaded ones.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from models import Base, SlugMixin, TimestampMixin


class Newsletter(Base, SlugMixin, TimestampMixin):
    """
    A composed newsletter issue.

    Columns
    -------
    id             : surrogate PK
    title          : required
    slug           : SEO slug (from title)
    content        : main body (Text)
    header_image   : optional image URL
    body_image     : optional image URL
    video          : optional video URL
    footer_text    : optional free-form footer
    is_published   : draft vs published flag
    published_at   : first publication timestamp (nullable)
    is_active      : soft-delete flag
    author_user_id : nullable FK to users (SET NULL on delete)
    created_at / updated_at : from TimestampMixin
    """

    __tablename__ = "newsletters"

    __slug_source__ = "title"

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    header_image: Mapped[str | None] = mapped_column(String(500), nullable=True)

    body_image: Mapped[str | None] = mapped_column(String(500), nullable=True)

    video: Mapped[str | None] = mapped_column(String(500), nullable=True)

    footer_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    author_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        for key in (
            "title", "header_image", "body_image", "video", "footer_text",
        ):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        kwargs.setdefault("is_published", False)
        kwargs.setdefault("is_active", True)

        super().__init__(**kwargs)

    # ═══════════════════════════════════════════════════════════════
    #  Helpers
    # ═══════════════════════════════════════════════════════════════
    def mark_published(self, when: datetime | None = None) -> None:
        """
        Mark the issue as published.

        Sets `published_at` only on the FIRST publish, so subsequent
        re-publishes do not overwrite the original archive timestamp.
        Pass `when` explicitly for testing; otherwise uses now (UTC).
        """
        from datetime import timezone  # noqa: PLC0415

        self.is_published = True
        if self.published_at is None:
            self.published_at = when or datetime.now(timezone.utc)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Newsletter id={self.id} title={self.title!r} "
            f"published={self.is_published}>"
        )
