"""
services/recommendation_service.py
──────────────────────────────────
Suggest add-on activities for a hotel or package booking.

The upsell flow (a core feature of the coursework brief) offers optional
activities for the same destination as the booking. This service selects
and ranks those suggestions.

SELECTION RULES
    1. Same destination as the hotel/package (mandatory).
    2. Activity is_active=True.
    3. Activity has a price row (so the client can add it and know the cost).
    4. Activity is not already in the booking (via exclude_ids).
    5. If a target date is known, there is still capacity for it.

RANKING (highest first)
    score = 0.7 * avg_rating + 0.3 * capacity_norm
    where:
        avg_rating is 0..5 (from Mongo reviews, or 0 if Mongo unavailable)
        capacity_norm is min(activity.capacity / 20, 1.0)

PUBLIC API
    recommend_addons_for_hotel(hotel_id, check_in=None, check_out=None,
                               exclude_ids=None, limit=6) -> list[dict]
    recommend_addons_for_package(package_id, target_date=None,
                                 exclude_ids=None, limit=6) -> list[dict]
    recommend_addons_for_booking(booking, limit=6) -> list[dict]

DESIGN NOTES
    - Reads only. Never writes.
    - Returns PLAIN DICTS so templates don't touch ORM objects.
    - Mongo rating lookups are best-effort: if Mongo is down, ratings
      are treated as 0 and we still return recommendations.
    - availability_service is imported lazily to avoid an import cycle
      at package load time.
    - No Flask request imports — pure business logic.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from extensions import db
from models import (
    Activity,
    ActivityPrice,
    Booking,
    Hotel,
    Package,
    PRODUCT_TYPE_HOTEL,
    PRODUCT_TYPE_PACKAGE,
)


log = logging.getLogger(__name__)


# ─── Domain exceptions ─────────────────────────────────────────────
class RecommendationError(Exception):
    """Base class for recommendation-domain errors."""


class RecommendationProductNotFound(RecommendationError):
    """The hotel/package id passed in does not exist."""


# ─── Constants ─────────────────────────────────────────────────────
DEFAULT_LIMIT = 6
MAX_LIMIT = 20
CAPACITY_NORM = 20.0


# ─── Helpers ───────────────────────────────────────────────────────
def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(n, MAX_LIMIT))


def _rating_lookup(product_ids: list[int]) -> dict[int, float]:
    """
    Fetch average ratings for the given activity ids from Mongo.

    Best-effort: if Mongo is unavailable, returns an empty dict — the
    caller treats missing ratings as 0.
    """
    if not product_ids:
        return {}

    try:
        from mongo.reviews import rating_summary  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — Mongo not ready in dev
        return {}

    out: dict[int, float] = {}
    for pid in product_ids:
        try:
            summary = rating_summary("activity", pid)
            avg = summary.get("average")
            if avg is not None:
                out[pid] = float(avg)
        except Exception:  # noqa: BLE001
            continue
    return out


def _first_price_for(activity_id: int) -> tuple[Optional[float], Optional[str]]:
    """Return (adult_price, currency) from the first ActivityPrice row."""
    row = db.session.scalar(
        select(ActivityPrice)
        .where(ActivityPrice.activity_id == activity_id)
        .order_by(ActivityPrice.id)
        .limit(1)
    )
    if row is None:
        return (None, None)
    try:
        return (float(row.adult_price), row.currency)
    except Exception:  # noqa: BLE001
        return (None, None)


def _score(avg_rating: float, capacity: int) -> float:
    """
    Weighted ranking score.

    70% rating + 30% capacity (normalised so a 20-seat activity hits 1.0).
    """
    cap_norm = min(max(capacity, 0) / CAPACITY_NORM, 1.0)
    return round(0.7 * avg_rating + 0.3 * cap_norm, 4)


def _to_public_dict(
    activity: Activity,
    avg_rating: float,
) -> dict:
    """Convert an Activity ORM object into a plain dict for templates."""
    adult_price, currency = _first_price_for(activity.id)
    return {
        "id": activity.id,
        "code": activity.code,
        "name": activity.name,
        "slug": activity.slug,
        "category": activity.category,
        "difficulty": activity.difficulty,
        "duration_hours": (
            float(activity.duration_hours)
            if activity.duration_hours is not None
            else None
        ),
        "capacity": activity.capacity,
        "destination_id": activity.destination_id,
        "price_adult": adult_price,
        "currency": currency,
        "avg_rating": avg_rating,
        "score": _score(avg_rating, activity.capacity or 0),
    }


# ─── Core ranking ──────────────────────────────────────────────────
def _recommend_for_destination(
    *,
    destination_id: int,
    exclude_ids: Optional[Iterable[int]] = None,
    target_date: Optional[date] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """
    Fetch and rank activities in a destination.

    Target date, if provided, is used to filter activities that have no
    availability left for that day.
    """
    exclude_set = set(exclude_ids or [])
    limit = _clamp_limit(limit)

    stmt = (
        select(Activity)
        .where(
            Activity.destination_id == destination_id,
            Activity.is_active.is_(True),
        )
        .order_by(Activity.id)
    )
    activities = list(db.session.scalars(stmt))
    if not activities:
        return []

    # Filter to those that have a price row
    activities = [a for a in activities if _first_price_for(a.id)[0] is not None]
    if not activities:
        return []

    # Exclude explicit ids
    if exclude_set:
        activities = [a for a in activities if a.id not in exclude_set]
    if not activities:
        return []

    # Availability filter for the target date (best-effort: skip on error)
    if target_date is not None:
        try:
            from services.availability_service import activity_availability  # noqa: PLC0415
            filtered = []
            for a in activities:
                try:
                    if activity_availability(a.id, target_date) > 0:
                        filtered.append(a)
                except Exception:  # noqa: BLE001
                    filtered.append(a)  # keep on error
            activities = filtered
        except Exception:  # noqa: BLE001
            pass

    if not activities:
        return []

    # Fetch Mongo ratings for the surviving set
    ids = [a.id for a in activities]
    ratings = _rating_lookup(ids)

    # Build public dicts + sort by score
    rows = [_to_public_dict(a, ratings.get(a.id, 0.0)) for a in activities]
    rows.sort(key=lambda r: (-r["score"], r["id"]))
    return rows[:limit]


# ─── Public API ────────────────────────────────────────────────────
def recommend_addons_for_hotel(
    hotel_id: int,
    *,
    check_in: Optional[date] = None,
    check_out: Optional[date] = None,
    exclude_ids: Optional[Iterable[int]] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """
    Suggest activities for a hotel's destination.

    check_in / check_out are used to pick a representative date for the
    availability filter (we use check_in). Pass None to skip filtering.
    """
    hotel = db.session.get(Hotel, hotel_id)
    if hotel is None:
        raise RecommendationProductNotFound(f"hotel {hotel_id} not found")

    target_date = check_in if isinstance(check_in, date) else None
    return _recommend_for_destination(
        destination_id=hotel.destination_id,
        exclude_ids=exclude_ids,
        target_date=target_date,
        limit=limit,
    )


def recommend_addons_for_package(
    package_id: int,
    *,
    target_date: Optional[date] = None,
    exclude_ids: Optional[Iterable[int]] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Suggest activities for a package's destination."""
    package = db.session.get(Package, package_id)
    if package is None:
        raise RecommendationProductNotFound(f"package {package_id} not found")

    return _recommend_for_destination(
        destination_id=package.destination_id,
        exclude_ids=exclude_ids,
        target_date=target_date,
        limit=limit,
    )


def recommend_addons_for_booking(
    booking: Booking,
    *,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """
    Dispatch on the booking's product_type and return appropriate add-ons.

    For an activity booking, no add-ons are suggested (an activity is
    already the primary add-on). For a hotel or package booking, use the
    matching helper and exclude activities already on the booking.
    """
    if booking is None:
        return []

    # Gather ids already in the booking
    existing_ids = [
        item.product_id for item in (booking.items or [])
        if item.item_type == "activity_addon"
    ]

    if booking.product_type == PRODUCT_TYPE_HOTEL:
        # product_id refers to a Room, not a Hotel. We need the room's hotel.
        from models import Room  # noqa: PLC0415
        room = db.session.get(Room, booking.product_id)
        if room is None:
            return []
        return recommend_addons_for_hotel(
            room.hotel_id,
            check_in=booking.check_in_date,
            check_out=booking.check_out_date,
            exclude_ids=existing_ids,
            limit=limit,
        )

    if booking.product_type == PRODUCT_TYPE_PACKAGE:
        return recommend_addons_for_package(
            booking.product_id,
            target_date=booking.activity_date,
            exclude_ids=existing_ids,
            limit=limit,
        )

    # activity primary → nothing to add
    return []
