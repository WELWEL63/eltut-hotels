"""
services/pricing_service.py
───────────────────────────
Resolve the price for a product and compute booking totals.

Every product type has a different pricing shape:

    activity   one ActivityPrice row (adult + child)   per activity
    hotel      rooms.base_price_per_night × nights × rooms
    package    one PackagePrice row (adult + child)    per package
    add-on     same as activity (upsell items)

This module is the single source of truth for that math. Routes never
do arithmetic — they call a pricing function and pass the result to
booking_service.

PUBLIC API
    price_activity(activity_id, adults, children) -> Decimal
    price_hotel(room_id, check_in, check_out, rooms=1,
                adults=1, children=0) -> Decimal
    price_package(package_id, adults, children) -> Decimal
    price_addons(addons) -> Decimal
    compute_booking_total(product_type, product_id, adults, children,
                          addons=None, check_in=None, check_out=None,
                          rooms=1) -> Decimal
    format_currency(amount, currency="USD") -> str

DESIGN NOTES
    - This service performs READS ONLY. It never inserts/updates rows.
    - Raises PriceNotFound when a product has no price row. Callers
      decide whether to display "on request" or block the booking.
    - All amounts are returned as Decimal. Never float.
    - Hotels: nights is max(1, (check_out - check_in).days).
    - Children under 2 (infants) are generally free; we do not implement
      that rule here (no infant pricing column exists), so callers pass
      the priced children only.
    - No Flask request imports — this is pure business logic.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Optional

from sqlalchemy import select

from extensions import db
from models import (
    Activity,
    ActivityPrice,
    Hotel,
    Package,
    PackagePrice,
    Room,
    PRODUCT_TYPE_ACTIVITY,
    PRODUCT_TYPE_HOTEL,
    PRODUCT_TYPE_PACKAGE,
    VALID_PRODUCT_TYPES,
)


# ─── Domain exceptions ─────────────────────────────────────────────
class PricingError(Exception):
    """Base class for pricing-domain errors."""


class PriceNotFound(PricingError):
    """The product exists but has no price row, or the product is missing."""


class InvalidPricingInput(PricingError):
    """Missing or malformed arguments."""


# ─── Helpers ───────────────────────────────────────────────────────
TWO_PLACES = Decimal("0.01")


def _round(value: Decimal) -> Decimal:
    """Round to 2 decimals using banker-free ROUND_HALF_UP."""
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _dec(value: Any) -> Decimal:
    """Coerce any numeric-ish value to Decimal safely."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value))


def _positive_int(value: Any, name: str) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidPricingInput(f"{name} must be an integer") from exc
    if n < 0:
        raise InvalidPricingInput(f"{name} must not be negative")
    return n


# ─── Activities ────────────────────────────────────────────────────
def price_activity(activity_id: int, adults: int, children: int = 0) -> Decimal:
    """
    Return the total price for an activity given party composition.

    Looks up the first (or only) row in activity_prices for the activity.
    Raises PriceNotFound if the activity does not exist or has no price.
    """
    _positive_int(adults, "adults")
    _positive_int(children, "children")
    if adults == 0 and children == 0:
        raise InvalidPricingInput("at least one adult or child is required")

    row = db.session.scalar(
        select(ActivityPrice)
        .where(ActivityPrice.activity_id == activity_id)
        .order_by(ActivityPrice.id)
        .limit(1)
    )
    if row is None:
        # Distinguish "no such activity" from "no price row" for clarity.
        exists = db.session.scalar(
            select(Activity.id).where(Activity.id == activity_id).limit(1)
        )
        if exists is None:
            raise PriceNotFound(f"activity {activity_id} not found")
        raise PriceNotFound(f"activity {activity_id} has no price row")

    total = (_dec(row.adult_price) * adults) + (_dec(row.child_price) * children)
    return _round(total)


# ─── Hotels ────────────────────────────────────────────────────────
def price_hotel(
    room_id: int,
    check_in: date,
    check_out: date,
    rooms: int = 1,
    adults: int = 1,
    children: int = 0,
) -> Decimal:
    """
    Return the total price for a hotel stay.

    Uses rooms.base_price_per_night × nights × rooms. Occupancy is
    checked against rooms.max_occupancy; if too many guests, we do not
    currently raise but the caller should validate. A dedicated
    availability_service handles capacity checks.

    Parameters
    ----------
    room_id  : int
    check_in : date — required
    check_out: date — required, must be > check_in
    rooms    : number of rooms to book (default 1)
    """
    if not isinstance(check_in, date) or not isinstance(check_out, date):
        raise InvalidPricingInput("check_in and check_out are required dates")
    nights = (check_out - check_in).days
    if nights <= 0:
        raise InvalidPricingInput("check_out must be after check_in")

    rooms_n = _positive_int(rooms, "rooms") or 1
    adults_n = _positive_int(adults, "adults")
    children_n = _positive_int(children, "children")
    if adults_n + children_n == 0:
        raise InvalidPricingInput("at least one guest is required")

    room = db.session.get(Room, room_id)
    if room is None:
        raise PriceNotFound(f"room {room_id} not found")

    per_night = _dec(room.base_price_per_night)
    if per_night <= 0:
        raise PriceNotFound(f"room {room_id} has no price set")

    total = per_night * nights * rooms_n
    return _round(total)


# ─── Packages ──────────────────────────────────────────────────────
def price_package(package_id: int, adults: int, children: int = 0) -> Decimal:
    """
    Return the total price for a package given party composition.

    Uses the first row in package_prices for the package.
    """
    _positive_int(adults, "adults")
    _positive_int(children, "children")
    if adults == 0 and children == 0:
        raise InvalidPricingInput("at least one adult or child is required")

    row = db.session.scalar(
        select(PackagePrice)
        .where(PackagePrice.package_id == package_id)
        .order_by(PackagePrice.id)
        .limit(1)
    )
    if row is None:
        exists = db.session.scalar(
            select(Package.id).where(Package.id == package_id).limit(1)
        )
        if exists is None:
            raise PriceNotFound(f"package {package_id} not found")
        raise PriceNotFound(f"package {package_id} has no price row")

    total = (_dec(row.adult_price) * adults) + (_dec(row.child_price) * children)
    return _round(total)


# ─── Add-ons ───────────────────────────────────────────────────────
def price_addons(addons: Iterable[dict[str, Any]]) -> Decimal:
    """
    Sum the price of a list of add-on activity specs.

    Each spec is a dict:
        {"activity_id": int, "adults": int, "children": int}
      or the shorthand:
        {"activity_id": int, "quantity": int}   (treated as all adults)

    Returns Decimal total.
    """
    if not addons:
        return Decimal("0.00")

    total = Decimal("0.00")
    for spec in addons:
        try:
            activity_id = int(spec["activity_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidPricingInput(f"invalid add-on spec: {spec!r}") from exc

        adults = spec.get("adults")
        children = spec.get("children")
        if adults is None and children is None:
            # shorthand: quantity means adults
            adults = int(spec.get("quantity", 1))
            children = 0

        total += price_activity(activity_id, adults or 0, children or 0)

    return _round(total)


# ─── Booking total dispatcher ──────────────────────────────────────
def compute_booking_total(
    *,
    product_type: str,
    product_id: int,
    adults: int,
    children: int = 0,
    rooms: int = 1,
    check_in: Optional[date] = None,
    check_out: Optional[date] = None,
    addons: Optional[Iterable[dict[str, Any]]] = None,
) -> Decimal:
    """
    Compute the total for a booking, product + add-ons combined.

    Dispatches to price_activity / price_hotel / price_package based on
    product_type, then adds price_addons(). Raises InvalidPricingInput
    if the required dates are missing for a hotel booking.
    """
    if product_type not in VALID_PRODUCT_TYPES:
        raise InvalidPricingInput(
            f"product_type must be one of {VALID_PRODUCT_TYPES}, "
            f"got {product_type!r}"
        )

    if product_type == PRODUCT_TYPE_ACTIVITY:
        base = price_activity(product_id, adults, children)
    elif product_type == PRODUCT_TYPE_PACKAGE:
        base = price_package(product_id, adults, children)
    elif product_type == PRODUCT_TYPE_HOTEL:
        if check_in is None or check_out is None:
            raise InvalidPricingInput(
                "check_in and check_out are required for hotel pricing"
            )
        base = price_hotel(
            room_id=product_id,
            check_in=check_in,
            check_out=check_out,
            rooms=rooms,
            adults=adults,
            children=children,
        )
    else:  # pragma: no cover — VALID_PRODUCT_TYPES guard above prevents this
        raise InvalidPricingInput(f"unsupported product_type {product_type!r}")

    extras = price_addons(addons) if addons else Decimal("0.00")
    return _round(base + extras)


# ─── Display helper ────────────────────────────────────────────────
_SYMBOLS = {"USD": "$", "GBP": "£", "GBP": "£"}


def format_currency(amount: Any, currency: str = "USD") -> str:
    """Format an amount as a display string: '$1,200.00'."""
    symbol = _SYMBOLS.get((currency or "USD").upper(), "")
    return f"{symbol}{_dec(amount):,.2f}"
