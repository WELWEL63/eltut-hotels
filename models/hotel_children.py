"""
models/hotel_children.py
─────────────────────────
Child tables for hotels added in the details upgrade:

    hotel_inclusions   bullet list of "what is included in the price"
    hotel_exclusions   bullet list of "what is not included"
    hotel_faqs         question/answer pairs
    hotel_tips         short useful tips for guests

These live in their own file (not models/hotel.py) so the parent
model file stays readable; the class shapes are the same, and they
import Hotel lazily via the string FK the same way other children do.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base


# ─── HotelInclusion ───────────────────────────────────────────────────────
class HotelInclusion(Base):
    """One line of "what is included" for a hotel listing."""

    __tablename__ = "hotel_inclusions"
    __table_args__ = (
        CheckConstraint(
            "LENGTH(TRIM(item)) > 0",
            name="item_not_blank_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    hotel_id: Mapped[int] = mapped_column(
        ForeignKey("hotels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item: Mapped[str] = mapped_column(String(255), nullable=False)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )

    hotel: Mapped["Hotel"] = relationship(back_populates="inclusions")  # noqa: F821

    def __init__(self, **kwargs: object) -> None:
        item = kwargs.get("item")
        if isinstance(item, str):
            kwargs["item"] = item.strip()
        if kwargs.get("sort_order") is None:
            kwargs["sort_order"] = 0
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HotelInclusion id={self.id} hotel_id={self.hotel_id} item={self.item!r}>"


# ─── HotelExclusion ───────────────────────────────────────────────────────
class HotelExclusion(Base):
    """One line of "what is NOT included" for a hotel listing."""

    __tablename__ = "hotel_exclusions"
    __table_args__ = (
        CheckConstraint(
            "LENGTH(TRIM(item)) > 0",
            name="item_not_blank_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    hotel_id: Mapped[int] = mapped_column(
        ForeignKey("hotels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item: Mapped[str] = mapped_column(String(255), nullable=False)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )

    hotel: Mapped["Hotel"] = relationship(back_populates="exclusions")  # noqa: F821

    def __init__(self, **kwargs: object) -> None:
        item = kwargs.get("item")
        if isinstance(item, str):
            kwargs["item"] = item.strip()
        if kwargs.get("sort_order") is None:
            kwargs["sort_order"] = 0
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HotelExclusion id={self.id} hotel_id={self.hotel_id} item={self.item!r}>"


# ─── HotelFAQ ─────────────────────────────────────────────────────────────
class HotelFAQ(Base):
    """A question/answer pair displayed in an accordion on the hotel page."""

    __tablename__ = "hotel_faqs"
    __table_args__ = (
        CheckConstraint(
            "LENGTH(TRIM(question)) > 0",
            name="question_not_blank_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    hotel_id: Mapped[int] = mapped_column(
        ForeignKey("hotels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    question: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )

    hotel: Mapped["Hotel"] = relationship(back_populates="faqs")  # noqa: F821

    def __init__(self, **kwargs: object) -> None:
        for key in ("question", "answer"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()
        if kwargs.get("sort_order") is None:
            kwargs["sort_order"] = 0
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HotelFAQ id={self.id} hotel_id={self.hotel_id} q={self.question[:40]!r}>"


# ─── HotelTip ─────────────────────────────────────────────────────────────
class HotelTip(Base):
    """A short useful tip for guests staying at this hotel."""

    __tablename__ = "hotel_tips"
    __table_args__ = (
        CheckConstraint(
            "LENGTH(TRIM(tip)) > 0",
            name="tip_not_blank_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    hotel_id: Mapped[int] = mapped_column(
        ForeignKey("hotels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tip: Mapped[str] = mapped_column(Text, nullable=False)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )

    hotel: Mapped["Hotel"] = relationship(back_populates="tips")  # noqa: F821

    def __init__(self, **kwargs: object) -> None:
        tip = kwargs.get("tip")
        if isinstance(tip, str):
            kwargs["tip"] = tip.strip()
        if kwargs.get("sort_order") is None:
            kwargs["sort_order"] = 0
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HotelTip id={self.id} hotel_id={self.hotel_id} tip={self.tip[:40]!r}>"


__all__ = [
    "HotelInclusion",
    "HotelExclusion",
    "HotelFAQ",
    "HotelTip",
]
