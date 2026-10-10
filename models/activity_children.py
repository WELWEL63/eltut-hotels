"""
models/activity_children.py
────────────────────────────
Child tables for activities added in the details upgrade:

    activity_faqs   question/answer pairs
    activity_tips   short useful tips for participants

Note: activity_inclusions and activity_exclusions already exist in
models/activity.py (from the original schema). This file only adds
what was missing.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base


# ─── ActivityFAQ ──────────────────────────────────────────────────────────
class ActivityFAQ(Base):
    """A question/answer pair displayed in an accordion on the activity page."""

    __tablename__ = "activity_faqs"
    __table_args__ = (
        CheckConstraint(
            "LENGTH(TRIM(question)) > 0",
            name="question_not_blank_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    question: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )

    activity: Mapped["Activity"] = relationship(back_populates="faqs")  # noqa: F821

    def __init__(self, **kwargs: object) -> None:
        for key in ("question", "answer"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()
        if kwargs.get("sort_order") is None:
            kwargs["sort_order"] = 0
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ActivityFAQ id={self.id} activity_id={self.activity_id} q={self.question[:40]!r}>"


# ─── ActivityTip ──────────────────────────────────────────────────────────
class ActivityTip(Base):
    """A short useful tip for participants booking this activity."""

    __tablename__ = "activity_tips"
    __table_args__ = (
        CheckConstraint(
            "LENGTH(TRIM(tip)) > 0",
            name="tip_not_blank_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tip: Mapped[str] = mapped_column(Text, nullable=False)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )

    activity: Mapped["Activity"] = relationship(back_populates="tips")  # noqa: F821

    def __init__(self, **kwargs: object) -> None:
        tip = kwargs.get("tip")
        if isinstance(tip, str):
            kwargs["tip"] = tip.strip()
        if kwargs.get("sort_order") is None:
            kwargs["sort_order"] = 0
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ActivityTip id={self.id} activity_id={self.activity_id} tip={self.tip[:40]!r}>"


__all__ = [
    "ActivityFAQ",
    "ActivityTip",
]
