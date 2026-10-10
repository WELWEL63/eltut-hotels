"""
models/package_children.py
───────────────────────────
Child tables for packages added in the details upgrade:

    package_faqs   question/answer pairs
    package_tips   short useful tips for travellers

Note: package_inclusions and package_exclusions already exist in
models/package.py (from the original schema). This file only adds
what was missing.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base


# ─── PackageFAQ ───────────────────────────────────────────────────────────
class PackageFAQ(Base):
    """A question/answer pair displayed in an accordion on the package page."""

    __tablename__ = "package_faqs"
    __table_args__ = (
        CheckConstraint(
            "LENGTH(TRIM(question)) > 0",
            name="question_not_blank_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    question: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )

    package: Mapped["Package"] = relationship(back_populates="faqs")  # noqa: F821

    def __init__(self, **kwargs: object) -> None:
        for key in ("question", "answer"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()
        if kwargs.get("sort_order") is None:
            kwargs["sort_order"] = 0
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PackageFAQ id={self.id} package_id={self.package_id} q={self.question[:40]!r}>"


# ─── PackageTip ───────────────────────────────────────────────────────────
class PackageTip(Base):
    """A short useful tip for travellers booking this package."""

    __tablename__ = "package_tips"
    __table_args__ = (
        CheckConstraint(
            "LENGTH(TRIM(tip)) > 0",
            name="tip_not_blank_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    package_id: Mapped[int] = mapped_column(
        ForeignKey("packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tip: Mapped[str] = mapped_column(Text, nullable=False)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )

    package: Mapped["Package"] = relationship(back_populates="tips")  # noqa: F821

    def __init__(self, **kwargs: object) -> None:
        tip = kwargs.get("tip")
        if isinstance(tip, str):
            kwargs["tip"] = tip.strip()
        if kwargs.get("sort_order") is None:
            kwargs["sort_order"] = 0
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PackageTip id={self.id} package_id={self.package_id} tip={self.tip[:40]!r}>"


__all__ = [
    "PackageFAQ",
    "PackageTip",
]
