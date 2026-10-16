"""
services/recommendation_service.py
──────────────────────────────────
Rank and return add-on activities for a hotel, package, or booking.

Public API
----------
    recommend_addons_for_hotel(hotel_id, ...)      -> list[dict]
    recommend_addons_for_package(package_id, ...)  -> list[dict]
    recommend_addons_for_booking(booking, ...)     -> list[dict]

Each dict exposes:
    id, code, name, slug, category, difficulty, duration_hours,
    capacity, destination_id, price_adult, price_child, currency,
    image_url, avg_rating, score

Design notes
------------
- Price lookup uses the first ActivityPrice row (mirrors search_service).
- image_url points at ActivityImage.url when available, else None.
- Ranking blends rating and capacity so small-group premium activities
  don't get drowned out by high-capacity mass tourism ones.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import select

from extensions import db
from models import Activity, ActivityPrice, Booking, Hotel, Package, Room
from models.activity import ActivityImage  # noqa: PLC0415
from models.booking_item import BookingItem  # noqa: PLC0415
from models import PRODUCT_TYPE_HOTEL


log = logging.getLogger(__name__)


# ─── Errors ─────────────────────────────────────────────────────────
class RecommendationError(Exception):
    """Base error for the recommendation service."""


class RecommendationProductNotFound(RecommendationError):
    """Raised when the requested product does not exist."""


# ─── Constants ──────────────────────────────────────────────────────
DEFAULT_LIMIT = 6
MAX_LIMIT = 20
CAPACITY_NORM = 20.0


# ─── Internals ──────────────────────────────────────────────────────
def _clamp_limit(limit: int | None) -> int:
    if not limit:
        return DEFAULT_LIMIT
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, n))


def _rating_lookup(product_ids: list[int]) -> dict[int, float]:
    """Best-effort Mongo rating lookup — returns {} if Mongo is down."""
    if not product_ids:
        return {}
    try:
        from mongo.reviews import rating_summary  # noqa: PLC0415
    except Exception:
        return {}
    out: dict[int, float] = {}
    for pid in product_ids:
        try:
            summary = rating_summary("activity", pid)
            out[pid] = float(summary.get("average") or 0.0)
        except Exception:
            out[pid] = 0.0
    return out


def _first_price_for(activity_id: int) -> tuple[float | None, float | None, str]:
    """Return (adult_price, child_price, currency) for the first price row."""
    row = db.session.scalars(
        select(ActivityPrice)
        .where(ActivityPrice.activity_id == activity_id)
        .order_by(ActivityPrice.id.asc())
        .limit(1)
    ).first()
    if row is None:
        return None, None, "GBP"
    adult = float(row.adult_price) if row.adult_price is not None else None
    child = float(row.child_price) if row.child_price is not None else None
    return adult, child, (row.currency or "GBP")


def _first_image_url(activity_id: int) -> str | None:
    """Return the first image URL for an activity, or None."""
    row = db.session.scalars(
        select(ActivityImage)
        .where(ActivityImage.activity_id == activity_id)
        .order_by(ActivityImage.sort_order.asc(), ActivityImage.id.asc())
        .limit(1)
    ).first()
    if row is None or not row.url:
        return None
    url = row.url.strip()
    if not url:
        return None
    # If the URL doesn't start with http or /, assume it's a static-relative path
    if not (url.startswith("http") or url.startswith("/")):
        url = "/" + url
    return url


def _score(avg_rating: float, capacity: int) -> float:
    """Blend rating (0-5) and capacity into a single ranking score."""
    cap_score = min(1.0, (capacity or 0) / CAPACITY_NORM)
    rating_score = (avg_rating or 0.0) / 5.0
    return rating_score * 0.7 + cap_score * 0.3


def _to_public_dict(
    activity: Activity,
    avg_rating: float,
) -> dict:
    """Convert an Activity ORM object into a plain dict for templates."""
    adult_price, child_price, currency = _first_price_for(activity.id)
    # Trim description for the modal (first 400 chars, word boundary)
    desc_raw = activity.description or ""
    if len(desc_raw) > 400:
        desc_short = desc_raw[:400].rsplit(" ", 1)[0] + "..."
    else:
        desc_short = desc_raw

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
        "price_child": child_price,
        "currency": currency,
        "image_url": _first_image_url(activity.id),
        "avg_rating": avg_rating,
        "score": _score(avg_rating, activity.capacity or 0),
        # Modal fields
        "description": desc_short,
        "departure_time": activity.departure_time,
        "return_time": activity.return_time,
        "meeting_point": activity.meeting_point,
        "what_to_bring": activity.what_to_bring,
        "min_age": activity.min_age,
        "max_age": activity.max_age,
    }


# ─── Core ranking ───────────────────────────────────────────────────
def _recommend_for_destination(
    *,
    destination_id: int,
    exclude_ids: Optional[Iterable[int]] = None,
    target_date: Optional[date] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Fetch and rank activities in a destination."""
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

    activities = [a for a in activities if _first_price_for(a.id)[0] is not None]
    if not activities:
        return []

    if target_date is not None:
        try:
            from services import availability_service  # noqa: PLC0415
            filtered: list[Activity] = []
            for a in activities:
                try:
                    remaining = availability_service.activity_availability(
                        a.id, target_date
                    )
                    if remaining is None or remaining > 0:
                        filtered.append(a)
                except Exception:
                    filtered.append(a)
            activities = filtered or activities
        except Exception as exc:
            log.debug("availability filter skipped: %s", exc)

    if exclude_set:
        activities = [a for a in activities if a.id not in exclude_set]

    ids = [a.id for a in activities]
    ratings = _rating_lookup(ids)
    rows = [_to_public_dict(a, ratings.get(a.id, 0.0)) for a in activities]
    rows.sort(key=lambda r: (-r["score"], r["id"]))
    return rows[:limit]


# ─── Public API ─────────────────────────────────────────────────────
def recommend_addons_for_hotel(
    hotel_id: int,
    *,
    check_in: Optional[date] = None,
    check_out: Optional[date] = None,
    exclude_ids: Optional[Iterable[int]] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Suggest activities for a hotel's destination."""
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
    """Dispatch on the booking's product_type and return appropriate add-ons."""
    if booking is None:
        return []

    existing_ids = [
        item.product_id for item in (booking.items or [])
        if item.item_type == "activity_addon"
    ]

    if booking.product_type == PRODUCT_TYPE_HOTEL:
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

    if booking.product_type == "package":
        return recommend_addons_for_package(
            booking.product_id,
            target_date=booking.activity_date,
            exclude_ids=existing_ids,
            limit=limit,
        )

    # Activities don't recommend other activities
    return []


__all__ = [
    "RecommendationError",
    "RecommendationProductNotFound",
    "recommend_addons_for_hotel",
    "recommend_addons_for_package",
    "recommend_addons_for_booking",
]
