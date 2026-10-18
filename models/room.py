"""
models/room.py
──────────────
The rooms table — bookable room types inside a hotel — plus its child
table room_images.

Rooms live in their own file (separate from models/hotel.py) because they
have their own child (room_images) and their own set of business rules
that would crowd hotel.py.

DESIGN NOTES
    - `hotel_id` is REQUIRED — rooms always belong to a specific hotel.
    - There is deliberately NO unique constraint on `type` at the DB
      level: a hotel can legitimately have two "Deluxe" categories at
      different prices (sea view vs. garden view). Business-level
      matching uses (hotel_id, type, meal_plan).
    - `meal_plan` uses its own CHECK set (includes room_only and
      all_inclusive) — hotels and activities sell under different
      meal-plan vocabularies.
    - `max_occupancy` is how many people sleep in the room (> 0).
    - `capacity` is how many of this room the hotel has (>= 0 — a fully
      booked contract can legitimately be zero).
    - `base_price_per_night` is a base price only; seasonal / date-based
      pricing lives in the booking/pricing layer.
    - `max_adults` / `max_children` (multi-room upgrade):
        * `max_children` is the explicit child cap when set.
        * `max_adults` is the explicit adult cap when set.
        * When unset (or when the migration auto-backfilled
          max_adults = max_occupancy AND max_children is still NULL —
          which we treat as "no explicit override yet"), we DERIVE the
          caps so existing inventory is family-capable out of the box:

              max_occupancy <= 2          -> adults = occ,         children = 0
              max_occupancy >= 3          -> adults = occ - 1,     children = 1

          An admin can override per room by setting max_adults to a
          value != max_occupancy, or by setting max_children
          explicitly. Explicit values always win.
    - Infants do NOT count toward either cap — they sleep in a cot.
    - Child table room_images cascades with the room, at the DB level
      (ondelete="CASCADE") and at the ORM level (delete-orphan +
      passive_deletes).
    - Instance defaults (meal_plan, capacity, max_occupancy, price,
      is_active) are applied in __init__ so unsaved instances read the
      same as DB-loaded ones.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models import Base, TimestampMixin


# ─── Constants ─────────────────────────────────────────────────────
MEAL_ROOM_ONLY: str = "room_only"
MEAL_BREAKFAST: str = "breakfast"
MEAL_HALF_BOARD: str = "half_board"
MEAL_FULL_BOARD: str = "full_board"
MEAL_ALL_INCLUSIVE: str = "all_inclusive"

VALID_ROOM_MEAL_PLANS: tuple[str, ...] = (
    MEAL_ROOM_ONLY,
    MEAL_BREAKFAST,
    MEAL_HALF_BOARD,
    MEAL_FULL_BOARD,
    MEAL_ALL_INCLUSIVE,
)
DEFAULT_ROOM_MEAL_PLAN: str = MEAL_ROOM_ONLY


# ═══════════════════════════════════════════════════════════════════
#  Parent: rooms
# ═══════════════════════════════════════════════════════════════════
class Room(Base, TimestampMixin):
    """
    A bookable room type inside a hotel.

    Columns
    -------
    id                    : surrogate PK
    hotel_id              : REQUIRED FK to hotels
    type                  : marketing name ("Deluxe Sea View")
    meal_plan             : CHECK room_only|breakfast|half_board|full_board|all_inclusive
    max_occupancy         : people who sleep in the room (> 0)
    max_adults            : explicit adult cap (NULL -> derived)
    max_children          : explicit child cap (NULL -> derived)
    capacity              : number of these rooms the hotel has (>= 0)
    base_price_per_night  : base nightly price (>= 0)
    description           : long-form marketing copy
    is_active             : soft-disable flag
    created_at / updated_at : from TimestampMixin
    """

    __tablename__ = "rooms"
    __table_args__ = (
        CheckConstraint("max_occupancy > 0", name="max_occupancy_check"),
        CheckConstraint("capacity >= 0", name="capacity_check"),
        CheckConstraint(
            "base_price_per_night >= 0", name="base_price_per_night_check"
        ),
        CheckConstraint(
            "meal_plan IN ('room_only','breakfast','half_board',"
            "'full_board','all_inclusive')",
            name="meal_plan_check",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    hotel_id: Mapped[int] = mapped_column(
        ForeignKey("hotels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ─── Classification ────────────────────────────────────────────
    type: Mapped[str] = mapped_column(String(120), nullable=False)

    meal_plan: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DEFAULT_ROOM_MEAL_PLAN,
        server_default=DEFAULT_ROOM_MEAL_PLAN,
    )

    # ─── Occupancy / inventory ─────────────────────────────────────
    max_occupancy: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    # Adult / child cap overrides (multi-room upgrade).
    max_adults: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_children: Mapped[int | None] = mapped_column(Integer, nullable=True)

    capacity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # ─── Pricing ───────────────────────────────────────────────────
    base_price_per_night: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )

    # ─── Content ───────────────────────────────────────────────────
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ─── State ─────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )

    # ─── Relationships ─────────────────────────────────────────────
    images: Mapped[list["RoomImage"]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RoomImage.sort_order",
    )

    # Seasonal rate windows (added in Step 11.5)
    rates: Mapped[list["RoomRate"]] = relationship(  # noqa: F821
        back_populates="room",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ═══════════════════════════════════════════════════════════════
    #  Constructor
    # ═══════════════════════════════════════════════════════════════
    def __init__(self, **kwargs: object) -> None:
        for key in ("type", "meal_plan"):
            value = kwargs.get(key)
            if isinstance(value, str):
                kwargs[key] = value.strip()

        if not kwargs.get("meal_plan"):
            kwargs["meal_plan"] = DEFAULT_ROOM_MEAL_PLAN

        kwargs.setdefault("max_occupancy", 1)
        kwargs.setdefault("capacity", 0)
        kwargs.setdefault("base_price_per_night", Decimal("0.00"))
        kwargs.setdefault("is_active", True)

        # Leave max_adults / max_children NULL unless the caller
        # explicitly set them — the properties below decide whether to
        # use the explicit value or the derived policy.
        super().__init__(**kwargs)

    # ── Explicit-override detection ───────────────────────────────
    @property
    def _has_explicit_adult_cap(self) -> bool:
        """
        True when max_adults looks like an admin override, not the
        migration's auto-backfill.

        The migration backfilled max_adults = max_occupancy while
        leaving max_children NULL. We treat that specific pattern as
        "not explicit" so the derivation applies. An admin override
        either sets max_adults != max_occupancy, or sets max_children
        at the same time.
        """
        if self.max_adults is None:
            return False
        if self.max_children is not None:
            return True
        return int(self.max_adults) != int(self.max_occupancy or 0)

    # ── Effective caps ────────────────────────────────────────────
    @property
    def effective_max_adults(self) -> int:
        """
        max_adults if explicit, else derive from max_occupancy:
            occ <= 2  -> occ        (e.g. a 2-bed room is 2 adults)
            occ >= 3  -> occ - 1    (reserve 1 bed for a child)
        """
        if self._has_explicit_adult_cap:
            return int(self.max_adults)  # type: ignore[arg-type]
        occ = int(self.max_occupancy or 1)
        return occ if occ <= 2 else occ - 1

    @property
    def effective_max_children(self) -> int:
        """
        max_children if explicit, else derive from the remaining beds:
            max(0, max_occupancy - effective_max_adults)
        """
        if self.max_children is not None:
            return int(self.max_children)
        derived = int(self.max_occupancy or 0) - self.effective_max_adults
        return derived if derived > 0 else 0

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Room id={self.id} hotel_id={self.hotel_id} "
            f"type={self.type!r} meal_plan={self.meal_plan!r}>"
        )


# ═══════════════════════════════════════════════════════════════════
#  Child: room_images
# ═══════════════════════════════════════════════════════════════════
class RoomImage(Base):
    """A gallery image for a room."""

    __tablename__ = "room_images"

    id: Mapped[int] = mapped_column(primary_key=True)

    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(String(500), nullable=False)

    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    room: Mapped[Room] = relationship(back_populates="images")

    def __init__(self, **kwargs: object) -> None:
        url = kwargs.get("url")
        if isinstance(url, str):
            kwargs["url"] = url.strip()
        super().__init__(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RoomImage id={self.id} room_id={self.room_id}>"