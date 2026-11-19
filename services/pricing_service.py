"""
services/pricing_service.py
───────────────────────────
Resolve hotel prices and compute booking totals.

PUBLIC API
    price_hotel(room_id, check_in, check_out, rooms=1,
                adults=1, children=0) -> Decimal
    compute_booking_total(product_type, product_id, adults, children,
                          check_in=None, check_out=None, rooms=1) -> Decimal
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
from typing import Any, Optional

from extensions import db
from models import (
    Room,
    PRODUCT_TYPE_HOTEL,
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
) -> Decimal:
    """
    Compute a hotel booking total.

    Raises InvalidPricingInput if the product type is not hotel or the
    required dates are missing.
    """
    if product_type not in VALID_PRODUCT_TYPES:
        raise InvalidPricingInput(
            f"product_type must be one of {VALID_PRODUCT_TYPES}, "
            f"got {product_type!r}"
        )

    if product_type != PRODUCT_TYPE_HOTEL:
        raise InvalidPricingInput(f"unsupported product_type {product_type!r}")
    if check_in is None or check_out is None:
        raise InvalidPricingInput(
            "check_in and check_out are required for hotel pricing"
        )
    return price_hotel(
        room_id=product_id,
        check_in=check_in,
        check_out=check_out,
        rooms=rooms,
        adults=adults,
        children=children,
    )


# ─── Display helper ────────────────────────────────────────────────
_SYMBOLS = {"USD": "$", "GBP": "£", "GBP": "£"}


def format_currency(amount: Any, currency: str = "USD") -> str:
    """Format an amount as a display string: '$1,200.00'."""
    symbol = _SYMBOLS.get((currency or "USD").upper(), "")
    return f"{symbol}{_dec(amount):,.2f}"
