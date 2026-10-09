"""blueprints/api/activities_api.py - read endpoints for activities.

Public read surface. No auth, no CSRF. Two endpoints:

  GET /api/v1/activities              -> paginated list
  GET /api/v1/activities/<id_or_code> -> single activity detail

Query params for the list endpoint:
  destination_id  int    filter by destination
  category        str    filter by category (snake_case)
  difficulty      str    easy|moderate|challenging
  min_price       float  adult price >=
  max_price       float  adult price <=
  page            int    default 1
  per_page        int    default 20, max 100
  sort            str    name|price|duration (default: name)

The list endpoint never returns 4xx for bad filters - it falls back to
sane defaults and records the ignored filter in the response envelope
under data.meta.ignored_filters. This keeps the endpoint tolerant of
malformed client input while still surfacing the problem.

WHY service-layer lookups instead of raw queries here: the same
serialisation logic will be needed by the recommendation widget and
later by the admin API, so it lives in _serialise_activity() and stays
in one place.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from flask import jsonify, request
from sqlalchemy import func, select

from blueprints.api import api_bp
from extensions import db
from models import (
    Activity,
    ActivityImage,
    ActivityInclusion,
    ActivityPrice,
    Destination,
)


# --- Constants ---------------------------------------------------------------
MAX_PER_PAGE = 100
DEFAULT_PER_PAGE = 20
SORT_CHOICES = ("name", "price", "duration")
DIFFICULTY_CHOICES = ("easy", "moderate", "challenging")


# --- Helpers -----------------------------------------------------------------
def _ok(data: Any, status: int = 200):
    """Return the standard success envelope."""
    return jsonify({"data": data, "error": None}), status


def _err(code: str, message: str, status: int):
    """Return the standard error envelope."""
    return jsonify({"data": None, "error": {"code": code, "message": message}}), status


def _to_int(value: str | None, default: int, *, minimum: int = 1, maximum: int | None = None) -> tuple[int, bool]:
    """Parse a query param as int.

    Returns (value, was_valid). On invalid input returns (default, False)
    so the caller can record it in meta.ignored_filters.
    """
    if value is None:
        return default, True
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default, False
    if n < minimum:
        return default, False
    if maximum is not None and n > maximum:
        return maximum, False
    return n, True


def _to_decimal(value: str | None) -> tuple[Decimal | None, bool]:
    """Parse a query param as Decimal. Returns (value, was_valid)."""
    if value is None:
        return None, True
    try:
        return Decimal(value), True
    except (TypeError, ValueError, ArithmeticError):
        return None, False


def _first_price_for(session, activity_id: int) -> ActivityPrice | None:
    """Return the most recent valid price row for an activity.

    Activities seeded from CSV have exactly one price row, but the
    schema allows date-windowed prices (like room_rates). Order by
    valid_from DESC so the newest window wins.
    """
    return session.scalars(
        select(ActivityPrice)
        .where(ActivityPrice.activity_id == activity_id)
        .order_by(ActivityPrice.valid_from.desc().nullslast())
        .limit(1)
    ).first()


def _serialise_activity(activity: Activity, price: ActivityPrice | None) -> dict[str, Any]:
    """Return the JSON shape for one activity.

    Kept minimal - only fields the public list/detail views need. Extra
    fields can be added later without breaking clients because they
    will only add keys, never remove them.
    """
    return {
        "id": activity.id,
        "code": activity.code,
        "name": activity.name,
        "slug": activity.slug,
        "category": activity.category,
        "difficulty": activity.difficulty,
        "duration_hours": float(activity.duration_hours) if activity.duration_hours is not None else None,
        "capacity": activity.capacity,
        "destination_id": activity.destination_id,
        "meeting_point": activity.meeting_point,
        "description": activity.description,
        "price_adult": float(price.adult_price) if price else None,
        "price_child": float(price.child_price) if price and price.child_price is not None else None,
        "currency": price.currency if price else None,
    }


# --- Endpoints ---------------------------------------------------------------
@api_bp.get("/activities")
def activities_list():
    """Return a paginated, filtered list of activities.

    Never returns 4xx for bad filters - falls back to defaults and
    records each ignored filter in data.meta.ignored_filters.
    """
    session = db.session

    # --- Parse + validate query params ---
    ignored: list[str] = []

    destination_id, ok = _to_int(request.args.get("destination_id"), 0)
    if not ok:
        ignored.append("destination_id")
        destination_id = 0

    category = (request.args.get("category") or "").strip().lower() or None

    difficulty = (request.args.get("difficulty") or "").strip().lower() or None
    if difficulty and difficulty not in DIFFICULTY_CHOICES:
        ignored.append("difficulty")
        difficulty = None

    min_price, ok = _to_decimal(request.args.get("min_price"))
    if not ok:
        ignored.append("min_price")

    max_price, ok = _to_decimal(request.args.get("max_price"))
    if not ok:
        ignored.append("max_price")

    page, ok = _to_int(request.args.get("page"), 1, minimum=1)
    if not ok:
        ignored.append("page")

    per_page, ok = _to_int(
        request.args.get("per_page"),
        DEFAULT_PER_PAGE,
        minimum=1,
        maximum=MAX_PER_PAGE,
    )
    if not ok:
        ignored.append("per_page")

    sort = (request.args.get("sort") or "name").strip().lower()
    if sort not in SORT_CHOICES:
        ignored.append("sort")
        sort = "name"

    # --- Build the base query ---
    # WHY join ActivityPrice: we sort and filter on price, so the
    # price row must be in the query. Activities with no price row
    # are excluded (there are none in our seed data, but the schema
    # permits them, so we filter explicitly).
    stmt = (
        select(Activity, ActivityPrice)
        .join(ActivityPrice, ActivityPrice.activity_id == Activity.id)
        .where(Activity.is_active.is_(True))
    )

    if destination_id:
        stmt = stmt.where(Activity.destination_id == destination_id)
    if category:
        stmt = stmt.where(func.lower(Activity.category) == category)
    if difficulty:
        stmt = stmt.where(Activity.difficulty == difficulty)
    if min_price is not None:
        stmt = stmt.where(ActivityPrice.adult_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(ActivityPrice.adult_price <= max_price)

    if sort == "price":
        stmt = stmt.order_by(ActivityPrice.adult_price.asc(), Activity.name.asc())
    elif sort == "duration":
        stmt = stmt.order_by(Activity.duration_hours.asc().nullslast(), Activity.name.asc())
    else:  # "name"
        stmt = stmt.order_by(Activity.name.asc())

    # --- Total count (before pagination) ---
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.scalar(count_stmt) or 0

    # --- Page slice ---
    offset = (page - 1) * per_page
    rows = session.execute(stmt.offset(offset).limit(per_page)).all()

    items = [_serialise_activity(activity, price) for activity, price in rows]

    # --- Envelope ---
    meta: dict[str, Any] = {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }
    if ignored:
        meta["ignored_filters"] = sorted(set(ignored))

    return _ok({"items": items, "meta": meta})


@api_bp.get("/activities/<identifier>")
def activities_detail(identifier: str):
    """Return one activity by numeric id OR by code (e.g. TRP-0001).

    Both lookup paths supported so clients can use whichever they have.
    """
    session = db.session

    stmt = select(Activity).where(Activity.is_active.is_(True))
    if identifier.isdigit():
        stmt = stmt.where(Activity.id == int(identifier))
    else:
        stmt = stmt.where(Activity.code == identifier.upper())

    activity = session.scalars(stmt).first()
    if activity is None:
        return _err("not_found", f"activity {identifier!r} not found", 404)

    price = _first_price_for(session, activity.id)

    # --- Related collections ---
    destination = session.get(Destination, activity.destination_id) if activity.destination_id else None

    images = session.scalars(
        select(ActivityImage)
        .where(ActivityImage.activity_id == activity.id)
        .order_by(ActivityImage.sort_order.asc().nullslast(), ActivityImage.id.asc())
    ).all()

    inclusions = session.scalars(
        select(ActivityInclusion)
        .where(ActivityInclusion.activity_id == activity.id)
        .order_by(ActivityInclusion.id.asc())
    ).all()

    payload = _serialise_activity(activity, price)
    payload["destination"] = (
        {"id": destination.id, "name": destination.name, "slug": destination.slug}
        if destination else None
    )
    payload["images"] = [
        {"url": img.url, "caption": img.caption, "sort_order": img.sort_order}
        for img in images
    ]
    payload["inclusions"] = [inc.item for inc in inclusions]

    return _ok(payload)
