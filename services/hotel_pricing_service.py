"""
services/hotel_pricing_service.py
─────────────────────────────────
Single source of truth for hotel room pricing.

Why this file exists
    Before the multi-room upgrade, hotel pricing was duplicated in two
    places (search_service._hotel_pricing_for_dates and
    hotel_routes._stay_pricing). Both picked the cheapest room, used the
    same RoomRate window rule, and produced a per-room total. That worked
    for one room, one price, one party. With multi-room bookings, families
    with children of different ages, and an infant band, we need one
    function every caller trusts — so this module owns the rules and the
    rest of the app imports it.

Age bands (locked)
    infant : age <  INFANT_MAX_AGE  (default 2)
    child  : INFANT_MAX_AGE <= age < ADULT_MIN_AGE  (default 2..12)
    adult  : age >= ADULT_MIN_AGE  (default 13)

Pricing rules
    - Pick ONE RoomRate window that covers check_in. If none matches,
      fall back to room.base_price_per_night for adults and 0 for
      children/infants.
    - Per-room total = (adult_price * adults)
                     + (child_price * len(child_ages))
                     + (infant_price * infants)
                     , all multiplied by nights.
    - Infants are priced (infant_price) but never counted toward
      room occupancy — that is the capacity service's job, not ours.

This module is READ-ONLY: it never writes to the DB, never commits,
never opens a transaction it doesn't close. Pure lookups + arithmetic.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from flask import current_app
from sqlalchemy import select

from extensions import db
from models.room import Room
from models.room_rate import RoomRate


# ─── Constants (fallbacks if config is somehow unreadable) ────────
_DEFAULT_INFANT_MAX_AGE = 2
_DEFAULT_ADULT_MIN_AGE = 13
_DEFAULT_MAX_ROOMS = 3


# ─── Config helpers ───────────────────────────────────────────────
def _cfg_int(key: str, default: int) -> int:
    try:
        return int(current_app.config.get(key, default))
    except (TypeError, ValueError, RuntimeError):
        return default


def _infant_max_age() -> int:
    return _cfg_int("INFANT_MAX_AGE", _DEFAULT_INFANT_MAX_AGE)


def _adult_min_age() -> int:
    return _cfg_int("ADULT_MIN_AGE", _DEFAULT_ADULT_MIN_AGE)


def _max_rooms() -> int:
    return _cfg_int("MAX_ROOMS_PER_BOOKING", _DEFAULT_MAX_ROOMS)


# ─── Age classification ──────────────────────────────────────────
def classify_age(age: int) -> str:
    """
    Return 'infant' | 'child' | 'adult' for a given age in whole years.

    Boundaries come from config so a business change does not require a
    code change.
    """
    try:
        a = int(age)
    except (TypeError, ValueError):
        # Treat unparseable input as adult — safest for pricing sanity.
        return "adult"
    if a < 0:
        return "infant"
    if a < _infant_max_age():
        return "infant"
    if a < _adult_min_age():
        return "child"
    return "adult"


def split_child_ages(child_ages: list[int] | None) -> tuple[list[int], list[int]]:
    """
    Given a list of child ages, return (children_2_12, adults_13_plus).

    Used by the capacity service and by callers that want to sanity-check
    that the ages they were handed are actually children. Ages that
    classify as adults or infants are returned in separate buckets so
    the caller can decide what to do (e.g. warn the user).
    """
    children: list[int] = []
    adults: list[int] = []
    if not child_ages:
        return children, adults
    for raw in child_ages:
        kind = classify_age(raw)
        if kind == "child":
            children.append(int(raw))
        elif kind == "adult":
            adults.append(int(raw))
        # infants in a child_ages list are ignored for pricing;
        # callers should pass them via the `infants` count instead.
    return children, adults


# ─── Rate window selection ───────────────────────────────────────
def select_rate_window(room: Room, check_in: date) -> RoomRate | None:
    """
    Return the RoomRate window that covers `check_in` for this room,
    or None if no window matches.

    Rule (matches legacy search/detail code):
        (valid_from IS NULL OR valid_from <= check_in)
        AND (valid_to IS NULL OR valid_to >= check_in)
    Earliest matching window (lowest id) wins.
    """
    if check_in is None:
        return None
    return db.session.scalars(
        select(RoomRate)
        .where(RoomRate.room_id == room.id)
        .where(
            (RoomRate.valid_from.is_(None))
            | (RoomRate.valid_from <= check_in)
        )
        .where(
            (RoomRate.valid_to.is_(None))
            | (RoomRate.valid_to >= check_in)
        )
        .order_by(RoomRate.id.asc())
        .limit(1)
    ).first()


# ─── Single room pricing ─────────────────────────────────────────
def room_stay_pricing(
    room: Room,
    *,
    check_in: date,
    check_out: date,
    adults: int,
    child_ages: list[int] | None = None,
    infants: int = 0,
) -> dict[str, Any]:
    """
    Price one room for one stay.

    Parameters
    ----------
    room : Room
    check_in, check_out : date
        check_out must be strictly after check_in; if not, nights = 0
        and total = 0 (callers should validate, this is a safety net).
    adults : int
        Number of adults in this room (>= 0).
    child_ages : list[int] | None
        Ages of children assigned to this room. Infants < INFANT_MAX_AGE
        are re-classified as infants and added to the infant count.
    infants : int
        Additional infants assigned to this room (e.g. cot-only, no age
        given). Combined with any infant-classified ages.

    Returns a dict with the fields the booking layer needs to snapshot
    into BookingRoom.
    """
    adults = max(0, int(adults or 0))
    infants = max(0, int(infants or 0))

    # Split child_ages: true children (2..12) vs. accidental adults.
    child_list, _excess_adults = split_child_ages(child_ages)
    children_count = len(child_list)

    # Any ages < INFANT_MAX_AGE that a caller put into child_ages should
    # count as infants, not silently vanish.
    if child_ages:
        for raw in child_ages:
            if classify_age(raw) == "infant":
                infants += 1

    # Nights
    nights = 0
    if check_in is not None and check_out is not None and check_out > check_in:
        nights = (check_out - check_in).days

    # Rate window (fallback to base price)
    rate = select_rate_window(room, check_in) if check_in else None
    if rate is not None:
        adult_price = Decimal(rate.adult_price or 0)
        child_price = Decimal(rate.child_price or 0)
        infant_price = Decimal(rate.infant_price or 0)
        currency = (rate.currency or "GBP").strip() or "GBP"
        rate_id = rate.id
    else:
        adult_price = Decimal(room.base_price_per_night or 0)
        child_price = Decimal("0.00")
        infant_price = Decimal("0.00")
        currency = "GBP"
        rate_id = None

    per_night_total = (
        adult_price * adults
        + child_price * children_count
        + infant_price * infants
    )
    total = per_night_total * nights

    return {
        "room_id": room.id,
        "rate_id": rate_id,
        "nights": nights,
        "currency": currency,
        "adult_price": adult_price,
        "child_price": child_price,
        "infant_price": infant_price,
        "adults": adults,
        "children": children_count,
        "infants": infants,
        "child_ages": list(child_list),
        "per_night_total": per_night_total,
        "total": total,
    }


# ─── Multi-room pricing ─────────────────────────────────────────
def booking_pricing(
    selections: list[dict[str, Any]],
    *,
    check_in: date,
    check_out: date,
) -> dict[str, Any]:
    """
    Price a multi-room hotel booking.

    selections: list of dicts, each:
        {
          "room": Room,               # required
          "adults": int,              # default 0
          "child_ages": list[int],    # default []
          "infants": int,             # default 0
          "rate_id": int | None,      # optional — currently informational,
                                      #   room_stay_pricing re-picks by date
        }

    Returns:
        {
          "nights": int,
          "currency": str,           # taken from the first priced room
          "rooms": [ room_stay_pricing(...) , ... ],
          "grand_total": Decimal,
        }

    Enforces <= MAX_ROOMS_PER_BOOKING rooms (extra selections are
    ignored — callers must validate before calling; this is a
    defence-in-depth safety net).
    """
    max_rooms = _max_rooms()
    used = list(selections or [])[:max_rooms]

    priced: list[dict[str, Any]] = []
    currency = "GBP"
    nights: int = 0

    for sel in used:
        room = sel.get("room")
        if room is None:
            continue
        room_priced = room_stay_pricing(
            room,
            check_in=check_in,
            check_out=check_out,
            adults=int(sel.get("adults", 0) or 0),
            child_ages=list(sel.get("child_ages") or []),
            infants=int(sel.get("infants", 0) or 0),
        )
        priced.append(room_priced)
        currency = room_priced["currency"]
        if room_priced["nights"] > nights:
            nights = room_priced["nights"]

    grand_total = sum(
        (p["total"] for p in priced),
        start=Decimal("0.00"),
    )

    return {
        "nights": nights,
        "currency": currency,
        "rooms": priced,
        "grand_total": grand_total,
    }


__all__ = [
    "classify_age",
    "split_child_ages",
    "select_rate_window",
    "room_stay_pricing",
    "booking_pricing",
]