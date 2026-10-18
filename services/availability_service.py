"""
services/availability_service.py
────────────────────────────────
Compute how much capacity remains for a product — the "is there room
left?" service used by the public booking flow and the admin panel.

CAPACITY RULES
    activity   capacity - sum of active booking quantities on that date
    hotel      room.capacity - sum of active room claims overlapping
                                the requested date range
    package    capacity - sum of active booking quantities on that date

"Active" means status IN ('pending', 'confirmed'). Cancelled, completed,
and refunded bookings are excluded.

MULTI-ROOM (Step 5e)
    A hotel booking that has any BookingRoom rows is a MULTI-ROOM booking:
    its primary BookingItem is a header, not a room claim. For those
    bookings, only BookingRoom rows count toward a room's occupancy.
    A booking with no BookingRoom rows is a LEGACY single-room booking:
    its primary BookingItem (product_id = room id) counts.

    This avoids double-counting the first room in multi-room bookings
    and preserves correct occupancy for the existing 14 single-room
    bookings.

PUBLIC API
    activity_availability(activity_id, target_date) -> int
    hotel_room_availability(room_id, check_in, check_out) -> int
    package_availability(package_id, target_date=None) -> int
    check_availability(...)  -> AvailabilityResult
    activity_is_bookable(...) -> bool
    room_is_bookable(...)     -> bool
    package_is_bookable(...)  -> bool

DESIGN NOTES
    - Reads only. Never writes.
    - Overlap test for hotels: existing.check_in < new.check_out AND
      existing.check_out > new.check_in (half-open interval predicate).
    - No Flask request imports — pure business logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from extensions import db
from models import (
    Activity,
    Booking,
    BookingItem,
    BookingRoom,
    Package,
    Room,
    PRODUCT_TYPE_ACTIVITY,
    PRODUCT_TYPE_HOTEL,
    PRODUCT_TYPE_PACKAGE,
    STATUS_PENDING,
    STATUS_CONFIRMED,
    VALID_PRODUCT_TYPES,
)


# ─── Domain exceptions ─────────────────────────────────────────────
class AvailabilityError(Exception):
    """Base class for availability-domain errors."""


class ProductNotFound(AvailabilityError):
    """The product id does not exist."""


class InvalidAvailabilityInput(AvailabilityError):
    """Missing or malformed arguments."""


# ─── Constants ─────────────────────────────────────────────────────
ACTIVE_STATUSES: tuple[str, ...] = (STATUS_PENDING, STATUS_CONFIRMED)


# ─── Result DTO ────────────────────────────────────────────────────
@dataclass(frozen=True)
class AvailabilityResult:
    """Structured result of an availability check."""
    available: bool
    remaining: int
    capacity: int
    used: int
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "available": self.available,
            "remaining": self.remaining,
            "capacity": self.capacity,
            "used": self.used,
            "reason": self.reason,
        }


# ─── Helpers ───────────────────────────────────────────────────────
def _validate_int(value, name: str) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidAvailabilityInput(f"{name} must be an integer") from exc
    if n <= 0:
        raise InvalidAvailabilityInput(f"{name} must be positive")
    return n


def _sum_quantity_for_activity(
    session: Session, activity_id: int, target_date: Optional[date]
) -> int:
    stmt = (
        select(func.coalesce(func.sum(BookingItem.quantity), 0))
        .join(Booking, Booking.id == BookingItem.booking_id)
        .where(
            BookingItem.item_type == "primary",
            BookingItem.product_type == PRODUCT_TYPE_ACTIVITY,
            BookingItem.product_id == activity_id,
            Booking.status.in_(ACTIVE_STATUSES),
        )
    )
    if target_date is not None:
        stmt = stmt.where(Booking.activity_date == target_date)
    return int(session.scalar(stmt) or 0)


def _sum_quantity_for_package(
    session: Session, package_id: int, target_date: Optional[date]
) -> int:
    stmt = (
        select(func.coalesce(func.sum(BookingItem.quantity), 0))
        .join(Booking, Booking.id == BookingItem.booking_id)
        .where(
            BookingItem.item_type == "primary",
            BookingItem.product_type == PRODUCT_TYPE_PACKAGE,
            BookingItem.product_id == package_id,
            Booking.status.in_(ACTIVE_STATUSES),
        )
    )
    if target_date is not None:
        stmt = stmt.where(Booking.activity_date == target_date)
    return int(session.scalar(stmt) or 0)


def _sum_rooms_for_range(
    session: Session,
    room_id: int,
    check_in: date,
    check_out: date,
) -> int:
    """
    Sum rooms occupied for room_id in the given date range.

    Multi-room bookings (those with any BookingRoom rows) contribute via
    their BookingRoom rows only. Legacy single-room bookings contribute
    via their primary BookingItem only. Never both.

    Overlap predicate: existing.check_in < new.check_out AND
    existing.check_out > new.check_in.
    """
    overlap = and_(
        Booking.check_in_date.is_not(None),
        Booking.check_out_date.is_not(None),
        Booking.check_in_date < check_out,
        Booking.check_out_date > check_in,
    )

    # Subquery: bookings that have at least one BookingRoom row.
    # Correlated to the outer Booking.
    has_rooms_subq = (
        select(BookingRoom.booking_id)
        .where(BookingRoom.booking_id == Booking.id)
        .correlate(Booking)
        .exists()
    )

    # 1) Count multi-room allocations for this room.
    multi_total = session.scalar(
        select(func.coalesce(func.count(BookingRoom.id), 0))
        .join(Booking, Booking.id == BookingRoom.booking_id)
        .where(
            BookingRoom.room_id == room_id,
            Booking.status.in_(ACTIVE_STATUSES),
            overlap,
        )
    ) or 0

    # 2) Count legacy single-room bookings for this room.
    legacy_total = session.scalar(
        select(func.coalesce(func.sum(BookingItem.quantity), 0))
        .join(Booking, Booking.id == BookingItem.booking_id)
        .where(
            BookingItem.item_type == "primary",
            BookingItem.product_type == PRODUCT_TYPE_HOTEL,
            BookingItem.product_id == room_id,
            Booking.status.in_(ACTIVE_STATUSES),
            overlap,
            ~has_rooms_subq,
        )
    ) or 0

    return int(multi_total) + int(legacy_total)


# ─── Public API ────────────────────────────────────────────────────
def activity_availability(activity_id: int, target_date: Optional[date]) -> int:
    """Return seats remaining for an activity on a given date."""
    _validate_int(activity_id, "activity_id")

    activity = db.session.get(Activity, activity_id)
    if activity is None:
        raise ProductNotFound(f"activity {activity_id} not found")

    used = _sum_quantity_for_activity(db.session, activity_id, target_date)
    remaining = max(0, int(activity.capacity) - used)
    return remaining


def hotel_room_availability(
    room_id: int, check_in: date, check_out: date
) -> int:
    """Return rooms remaining for a room over a date range."""
    _validate_int(room_id, "room_id")
    if not isinstance(check_in, date) or not isinstance(check_out, date):
        raise InvalidAvailabilityInput("check_in and check_out must be dates")
    if check_out <= check_in:
        raise InvalidAvailabilityInput("check_out must be after check_in")

    room = db.session.get(Room, room_id)
    if room is None:
        raise ProductNotFound(f"room {room_id} not found")

    used = _sum_rooms_for_range(db.session, room_id, check_in, check_out)
    remaining = max(0, int(room.capacity) - used)
    return remaining


def package_availability(
    package_id: int, target_date: Optional[date] = None
) -> int:
    """Return slots remaining for a package (optionally on a given date)."""
    _validate_int(package_id, "package_id")

    package = db.session.get(Package, package_id)
    if package is None:
        raise ProductNotFound(f"package {package_id} not found")

    used = _sum_quantity_for_package(db.session, package_id, target_date)
    remaining = max(0, int(package.capacity) - used)
    return remaining


def check_availability(
    *,
    product_type: str,
    product_id: int,
    quantity: int = 1,
    check_in: Optional[date] = None,
    check_out: Optional[date] = None,
    target_date: Optional[date] = None,
) -> AvailabilityResult:
    """Structured availability check used by the booking flow."""
    if product_type not in VALID_PRODUCT_TYPES:
        raise InvalidAvailabilityInput(
            f"product_type must be one of {VALID_PRODUCT_TYPES}, "
            f"got {product_type!r}"
        )
    _validate_int(product_id, "product_id")
    qty = _validate_int(quantity, "quantity")

    if product_type == PRODUCT_TYPE_ACTIVITY:
        activity = db.session.get(Activity, product_id)
        if activity is None:
            raise ProductNotFound(f"activity {product_id} not found")
        used = _sum_quantity_for_activity(db.session, product_id, target_date)
        capacity = int(activity.capacity)
        remaining = max(0, capacity - used)
        return AvailabilityResult(
            available=remaining >= qty,
            remaining=remaining,
            capacity=capacity,
            used=used,
            reason="" if remaining >= qty else (
                f"only {remaining} seat(s) remaining; {qty} requested"
            ),
        )

    if product_type == PRODUCT_TYPE_HOTEL:
        if not isinstance(check_in, date) or not isinstance(check_out, date):
            raise InvalidAvailabilityInput(
                "hotel availability requires check_in and check_out dates"
            )
        room = db.session.get(Room, product_id)
        if room is None:
            raise ProductNotFound(f"room {product_id} not found")
        used = _sum_rooms_for_range(db.session, product_id, check_in, check_out)
        capacity = int(room.capacity)
        remaining = max(0, capacity - used)
        return AvailabilityResult(
            available=remaining >= qty,
            remaining=remaining,
            capacity=capacity,
            used=used,
            reason="" if remaining >= qty else (
                f"only {remaining} room(s) available for those dates; "
                f"{qty} requested"
            ),
        )

    if product_type == PRODUCT_TYPE_PACKAGE:
        package = db.session.get(Package, product_id)
        if package is None:
            raise ProductNotFound(f"package {product_id} not found")
        used = _sum_quantity_for_package(db.session, product_id, target_date)
        capacity = int(package.capacity)
        remaining = max(0, capacity - used)
        return AvailabilityResult(
            available=remaining >= qty,
            remaining=remaining,
            capacity=capacity,
            used=used,
            reason="" if remaining >= qty else (
                f"only {remaining} slot(s) remaining; {qty} requested"
            ),
        )

    raise InvalidAvailabilityInput(f"unsupported product_type {product_type!r}")


# ─── Convenience wrappers ──────────────────────────────────────────
def activity_is_bookable(
    activity_id: int, target_date: Optional[date], quantity: int = 1
) -> bool:
    return activity_availability(activity_id, target_date) >= quantity


def room_is_bookable(
    room_id: int, check_in: date, check_out: date, quantity: int = 1
) -> bool:
    return hotel_room_availability(room_id, check_in, check_out) >= quantity


def package_is_bookable(
    package_id: int, target_date: Optional[date] = None, quantity: int = 1
) -> bool:
    return package_availability(package_id, target_date) >= quantity