"""
services/hotel_capacity_service.py
──────────────────────────────────
"How many rooms does this party need, and which ones?"

Before the multi-room upgrade, hotel search required ONE room to hold the
whole party (Room.max_occupancy >= adults + children). That excluded every
hotel that could host the same party across 2 or 3 rooms — the exact bug
that motivated this whole upgrade.

This module answers three questions, all with the same rules:

    min_rooms_needed(hotel_id, ...)  -> int | None
        Smallest number of rooms (1..MAX_ROOMS) that can hold the party,
        or None if no valid grouping exists.

    rooms_that_fit(hotel_id, ...)    -> list[list[Room]]
        Every valid room grouping at the smallest size that fits.
        Used by the detail page to show concrete "Room 1 + Room 2"
        options.

    best_room_grouping(hotel_id, ...) -> dict | None
        The cheapest valid grouping, priced via
        hotel_pricing_service.booking_pricing, ready for the UI to
        render and for the booking layer to snapshot.

CAPACITY RULES (locked)
    - Adults       count 1 each toward room.effective_max_adults
    - Children 2-12 count 1 each toward room.effective_max_children
    - Infants <2   do NOT count toward occupancy (cot, not a bed)
    - A grouping is valid if, for EVERY room in the grouping,
          adults_in_room   <= room.effective_max_adults
          children_in_room <= room.effective_max_children
      and the sum of adults across rooms == party adults and
      the sum of children across rooms == party children.
    - Only active rooms are considered.
    - Groupings stop growing at MAX_ROOMS_PER_BOOKING rooms.

Determinism
    Groupings are enumerated in a stable order (adults descending, then
    children descending, then room id) so search results and pagination
    are reproducible between requests.

READ-ONLY
    No writes, no commits. Every function is safe to call from a GET.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Iterable

from flask import current_app
from sqlalchemy import select

from extensions import db
from models.room import Room

from services import hotel_pricing_service as pricing


# ─── Constants ────────────────────────────────────────────────────
_DEFAULT_MAX_ROOMS = 3


def _max_rooms() -> int:
    try:
        return int(current_app.config.get("MAX_ROOMS_PER_BOOKING", _DEFAULT_MAX_ROOMS))
    except (TypeError, ValueError, RuntimeError):
        return _DEFAULT_MAX_ROOMS


# ─── Public: capacity helpers ────────────────────────────────────
def _active_rooms(hotel_id: int) -> list[Room]:
    return list(db.session.scalars(
        select(Room)
        .where(Room.hotel_id == hotel_id)
        .where(Room.is_active.is_(True))
        .order_by(Room.id.asc())
    ))


def _room_adult_cap(room: Room) -> int:
    return max(0, int(room.effective_max_adults))


def _room_child_cap(room: Room) -> int:
    return max(0, int(room.effective_max_children))


def _room_fits(room: Room, adults: int, children: int) -> bool:
    return (
        adults <= _room_adult_cap(room)
        and children <= _room_child_cap(room)
    )


def _distribute(total: int, rooms: list[Room], kind: str) -> Iterable[tuple[int, ...]]:
    """
    Yield non-negative allocations of `total` guests across `rooms`,
    where each room's share does not exceed its cap for that kind.

    Deterministic order: earlier rooms get larger shares first.
    Yielded tuples are capped at the room's capacity so impossible
    allocations are never produced.
    """
    caps = [
        _room_adult_cap(r) if kind == "adult" else _room_child_cap(r)
        for r in rooms
    ]
    n = len(rooms)

    def _walk(i: int, remaining: int, acc: tuple[int, ...]):
        if i == n - 1:
            if 0 <= remaining <= caps[i]:
                yield acc + (remaining,)
            return
        max_here = min(caps[i], remaining)
        for v in range(max_here, -1, -1):
            yield from _walk(i + 1, remaining - v, acc + (v,))

    if total < 0:
        return
    yield from _walk(0, total, ())


def _enumerate_valid_groupings(
    rooms: list[Room],
    adults: int,
    children: int,
    *,
    k: int,
) -> list[tuple[Room, int, int]]:
    """
    Enumerate every valid distribution of (adults, children) across a
    size-k subset of `rooms`. Returns list of tuples
    (room, adults_in_room, children_in_room), one tuple per room in the
    subset. Sorted deterministically.
    """
    from itertools import combinations

    results: list[list[tuple[Room, int, int]]] = []
    for subset in combinations(rooms, k):
        for a_dist in _distribute(adults, list(subset), "adult"):
            for c_dist in _distribute(children, list(subset), "child"):
                group = [
                    (subset[i], a_dist[i], c_dist[i])
                    for i in range(k)
                ]
                # Skip groupings where a room got zero of both types
                # (empty room is not a valid booking line).
                if any(a == 0 and c == 0 for _, a, c in group):
                    continue
                results.append(group)

    # Deterministic ordering:
    #   1) fewer empty-at-the-tail rooms is not applicable here (k fixed)
    #   2) sort by tuple of (room.id, adults, children) so identical
    #      groupings dedupe predictably
    results.sort(key=lambda g: tuple((r.id, a, c) for r, a, c in g))
    return [tuple(g) for g in results]  # type: ignore[return-value]


def _normalize_party(
    adults: int, child_ages: list[int] | None, infants: int,
) -> tuple[int, list[int], int]:
    a = max(0, int(adults or 0))
    ages, _ = pricing.split_child_ages(list(child_ages or []))
    # Note: infants passed via child_ages are also priced as infants later
    # by hotel_pricing_service, but do NOT occupy a bed. The `infants`
    # counter is the authoritative "extra infants" bucket.
    i = max(0, int(infants or 0))
    return a, ages, i


# ─── Public API ──────────────────────────────────────────────────
def min_rooms_needed(
    hotel_id: int,
    *,
    adults: int,
    child_ages: list[int] | None = None,
    infants: int = 0,
) -> int | None:
    """
    Smallest number of rooms (1..MAX_ROOMS) that can hold the party.
    Returns None if no valid grouping exists.
    """
    a, ages, _infants = _normalize_party(adults, child_ages, infants)
    c = len(ages)
    if a == 0 and c == 0:
        # No guests — treat as 1 room, since the UI will show a card.
        return 1

    rooms = _active_rooms(hotel_id)
    if not rooms:
        return None

    max_k = min(_max_rooms(), len(rooms))
    for k in range(1, max_k + 1):
        if _enumerate_valid_groupings(rooms, a, c, k=k):
            return k
    return None


def rooms_that_fit(
    hotel_id: int,
    *,
    adults: int,
    child_ages: list[int] | None = None,
    infants: int = 0,
) -> list[list[Room]]:
    """
    All valid room groupings at the smallest size that fits.
    Empty list means no grouping within MAX_ROOMS.
    """
    a, ages, _infants = _normalize_party(adults, child_ages, infants)
    c = len(ages)

    rooms = _active_rooms(hotel_id)
    if not rooms:
        return []

    max_k = min(_max_rooms(), len(rooms))
    for k in range(1, max_k + 1):
        groups = _enumerate_valid_groupings(rooms, a, c, k=k)
        if groups:
            return [[r for r, _a, _c in g] for g in groups]
    return []


def first_room_allocation(
    hotel_id: int,
    *,
    adults: int,
    child_ages: list[int] | None = None,
    infants: int = 0,
) -> list[dict[str, Any]] | None:
    """Return a deterministic capacity-fitting room allocation without pricing."""
    adult_count, ages, infant_count = _normalize_party(
        adults, child_ages, infants
    )
    rooms = _active_rooms(hotel_id)
    if not rooms:
        return None

    max_k = min(_max_rooms(), len(rooms))
    for room_count in range(1, max_k + 1):
        groups = _enumerate_valid_groupings(
            rooms, adult_count, len(ages), k=room_count
        )
        if not groups:
            continue

        allocation: list[dict[str, Any]] = []
        age_offset = 0
        infants_left = infant_count
        for room, room_adults, room_children in groups[0]:
            assigned_ages = ages[age_offset:age_offset + room_children]
            age_offset += room_children
            room_infants = infants_left
            infants_left = 0
            allocation.append({
                "room": room,
                "room_id": room.id,
                "adults": room_adults,
                "children": room_children,
                "child_ages": assigned_ages,
                "infants": room_infants,
            })
        return allocation
    return None


def best_room_grouping(
    hotel_id: int,
    *,
    adults: int,
    child_ages: list[int] | None = None,
    infants: int = 0,
    check_in: date | None = None,
    check_out: date | None = None,
) -> dict[str, Any] | None:
    """
    Cheapest valid grouping, priced via hotel_pricing_service.
    Returns None if no valid grouping exists.

    Shape:
        {
          'hotel_id': int,
          'rooms': [
            {
              'room': Room,
              'rate_id': int | None,
              'adults': int,
              'children': int,
              'child_ages': [int],
              'infants': int,
              'adult_price': Decimal,
              'child_price': Decimal,
              'total': Decimal,
            }, ...
          ],
          'total': Decimal,
          'nights': int,
          'currency': str,
          'min_rooms': int,
          'reason': 'fits_in_one' | 'needs_two_rooms' | 'needs_three_rooms',
        }
    """
    a, ages, inf = _normalize_party(adults, child_ages, infants)
    c = len(ages)

    rooms = _active_rooms(hotel_id)
    if not rooms:
        return None

    max_k = min(_max_rooms(), len(rooms))
    chosen: tuple | None = None
    for k in range(1, max_k + 1):
        groups = _enumerate_valid_groupings(rooms, a, c, k=k)
        if not groups:
            continue

        # Price each grouping via hotel_pricing_service; pick cheapest.
        # Note: infants are distributed to the FIRST room only (they
        # don't occupy a bed, so their distribution doesn't matter for
        # capacity; pricing treats them per-room).
        priced: list[tuple[Decimal, list[dict[str, Any]], int, str]] = []
        for g in groups:
            selections: list[dict[str, Any]] = []
            remaining_infants = inf
            for idx, (room, a_in, c_in) in enumerate(g):
                room_infants = remaining_infants if idx == 0 else 0
                remaining_infants -= room_infants
                # Split child_ages: first room takes the first c_in ages,
                # remaining rooms take the following slices.
                selections.append({
                    "room": room,
                    "adults": a_in,
                    "child_ages": [],  # filled below
                    "infants": room_infants,
                })
            # Distribute child ages sequentially across the grouping.
            idx = 0
            for sel, (_room, _a, c_in) in zip(selections, g):
                sel["child_ages"] = ages[idx:idx + c_in]
                idx += c_in

            pr = pricing.booking_pricing(
                selections,
                check_in=check_in or date.today(),
                check_out=check_out or (check_in or date.today()),
            )
            total = pr.get("grand_total") or Decimal("0.00")
            currency = pr.get("currency") or "GBP"
            nights = int(pr.get("nights") or 0)
            priced.append((total, pr["rooms"], nights, currency))

        priced.sort(key=lambda t: (t[0], len(t[1])))
        total, rooms_priced, nights, currency = priced[0]
        chosen = (k, total, rooms_priced, nights, currency)
        break

    if chosen is None:
        return None

    k, total, rooms_priced, nights, currency = chosen

    # Reason string for the UI.
    if k == 1:
        reason = "fits_in_one"
    elif k == 2:
        reason = "needs_two_rooms"
    else:
        reason = "needs_three_rooms"

    # Assemble output with per-room metadata (rate_id, ages, infants).
    out_rooms: list[dict[str, Any]] = []
    for idx, (g, rp) in enumerate(zip(
        # Reconstruct the winning grouping from room prices:
        # rooms_priced already carries room_id + adults + child_ages
        [None] * len(rooms_priced),
        rooms_priced,
    )):
        out_rooms.append({
            "room": db.session.get(Room, rp["room_id"]),
            "room_id": rp["room_id"],
            "rate_id": rp["rate_id"],
            "adults": rp["adults"],
            "children": rp["children"],
            "child_ages": rp.get("child_ages") or [],
            "infants": rp["infants"],
            "adult_price": rp["adult_price"],
            "child_price": rp["child_price"],
            "currency": rp["currency"],
            "nights": rp["nights"],
            "total": rp["total"],
        })

    return {
        "hotel_id": hotel_id,
        "rooms": out_rooms,
        "total": total,
        "nights": nights,
        "currency": currency,
        "min_rooms": k,
        "reason": reason,
    }


__all__ = [
    "min_rooms_needed",
    "rooms_that_fit",
    "first_room_allocation",
    "best_room_grouping",
]