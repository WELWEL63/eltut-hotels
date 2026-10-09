"""blueprints/api/packages_api.py - read endpoints for packages.

Public read surface. No auth, no CSRF. Two endpoints:

  GET /api/v1/packages              -> paginated list
  GET /api/v1/packages/<id_or_code> -> single package detail

Query params for the list endpoint:
  destination_id  int    filter by destination
  package_type    str    filter by package_type
  min_nights      int    duration_nights >=
  max_nights      int    duration_nights <=
  min_price       float  adult price >=
  max_price       float  adult price <=
  visa_required   bool   "1"/"true" -> require visa_required=True
  page            int    default 1
  per_page        int    default 20, max 100
  sort            str    name|price|duration (default: name)

Package has NO slug column (unlike Activity and Hotel). The detail
endpoint accepts a numeric id OR the business code (e.g. "PKG-0001").
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from flask import jsonify, request
from sqlalchemy import func, select

from blueprints.api import api_bp
from extensions import db
from models import (
    Destination,
    Flight,
    Hotel,
    Package,
    PackageExclusion,
    PackageImage,
    PackageInclusion,
    PackageItinerary,
    PackagePrice,
    Room,
)


MAX_PER_PAGE = 100
DEFAULT_PER_PAGE = 20
SORT_CHOICES = ("name", "price", "duration")


def _ok(data: Any, status: int = 200):
    return jsonify({"data": data, "error": None}), status


def _err(code: str, message: str, status: int):
    return jsonify({"data": None, "error": {"code": code, "message": message}}), status


def _to_int(value: str | None, default: int, *, minimum: int = 1, maximum: int | None = None) -> tuple[int, bool]:
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
    if value is None:
        return None, True
    try:
        return Decimal(value), True
    except (TypeError, ValueError, ArithmeticError):
        return None, False


def _to_bool(value: str | None) -> bool:
    """Accept '1', 'true', 'yes' (case-insensitive) as True."""
    if value is None:
        return False
    return value.strip().lower() in ("1", "true", "yes", "y")


def _serialise_package(pkg: Package, price: PackagePrice | None) -> dict[str, Any]:
    """Return the JSON shape for one package in list context."""
    return {
        "id": pkg.id,
        "code": pkg.code,
        "name": pkg.name,
        "package_type": pkg.package_type,
        "duration_nights": pkg.duration_nights,
        "capacity": pkg.capacity,
        "min_age": pkg.min_age,
        "max_age": pkg.max_age,
        "hotel_id": pkg.hotel_id,
        "room_id": pkg.room_id,
        "destination_id": pkg.destination_id,
        "deposit_required": pkg.deposit_required,
        "visa_required": pkg.visa_required,
        "visa_fee": float(pkg.visa_fee) if pkg.visa_fee is not None else None,
        "price_adult": float(price.adult_price) if price else None,
        "price_child": float(price.child_price) if price and price.child_price is not None else None,
        "currency": price.currency if price else None,
    }


@api_bp.get("/packages")
def packages_list():
    """Return a paginated, filtered list of packages."""
    session = db.session
    ignored: list[str] = []

    destination_id, ok = _to_int(request.args.get("destination_id"), 0)
    if not ok:
        ignored.append("destination_id")
        destination_id = 0

    package_type = (request.args.get("package_type") or "").strip().lower() or None

    min_nights, ok = _to_int(request.args.get("min_nights"), 0, minimum=0)
    if not ok:
        ignored.append("min_nights")
        min_nights = 0

    max_nights, ok = _to_int(request.args.get("max_nights"), 0, minimum=0)
    if not ok:
        ignored.append("max_nights")
        max_nights = 0

    min_price, ok = _to_decimal(request.args.get("min_price"))
    if not ok:
        ignored.append("min_price")

    max_price, ok = _to_decimal(request.args.get("max_price"))
    if not ok:
        ignored.append("max_price")

    visa_required = _to_bool(request.args.get("visa_required"))

    page, ok = _to_int(request.args.get("page"), 1, minimum=1)
    if not ok:
        ignored.append("page")

    per_page, ok = _to_int(request.args.get("per_page"), DEFAULT_PER_PAGE, minimum=1, maximum=MAX_PER_PAGE)
    if not ok:
        ignored.append("per_page")

    sort = (request.args.get("sort") or "name").strip().lower()
    if sort not in SORT_CHOICES:
        ignored.append("sort")
        sort = "name"

    stmt = (
        select(Package, PackagePrice)
        .join(PackagePrice, PackagePrice.package_id == Package.id)
        .where(Package.is_active.is_(True))
    )

    if destination_id:
        stmt = stmt.where(Package.destination_id == destination_id)
    if package_type:
        stmt = stmt.where(func.lower(Package.package_type) == package_type)
    if min_nights:
        stmt = stmt.where(Package.duration_nights >= min_nights)
    if max_nights:
        stmt = stmt.where(Package.duration_nights <= max_nights)
    if min_price is not None:
        stmt = stmt.where(PackagePrice.adult_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(PackagePrice.adult_price <= max_price)
    if visa_required:
        stmt = stmt.where(Package.visa_required.is_(True))

    if sort == "price":
        stmt = stmt.order_by(PackagePrice.adult_price.asc(), Package.name.asc())
    elif sort == "duration":
        stmt = stmt.order_by(Package.duration_nights.asc(), Package.name.asc())
    else:  # "name"
        stmt = stmt.order_by(Package.name.asc())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.scalar(count_stmt) or 0

    offset = (page - 1) * per_page
    rows = session.execute(stmt.offset(offset).limit(per_page)).all()

    items = [_serialise_package(pkg, price) for pkg, price in rows]

    meta: dict[str, Any] = {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }
    if ignored:
        meta["ignored_filters"] = sorted(set(ignored))

    return _ok({"items": items, "meta": meta})


@api_bp.get("/packages/<identifier>")
def packages_detail(identifier: str):
    """Return one package by numeric id OR by business code."""
    session = db.session

    stmt = select(Package).where(Package.is_active.is_(True))
    if identifier.isdigit():
        stmt = stmt.where(Package.id == int(identifier))
    else:
        stmt = stmt.where(Package.code == identifier.upper())

    pkg = session.scalars(stmt).first()
    if pkg is None:
        return _err("not_found", f"package {identifier!r} not found", 404)

    # --- Price (newest window) ---
    price = session.scalars(
        select(PackagePrice)
        .where(PackagePrice.package_id == pkg.id)
        .order_by(PackagePrice.valid_from.desc().nullslast())
        .limit(1)
    ).first()

    # --- Related ---
    destination = session.get(Destination, pkg.destination_id) if pkg.destination_id else None
    hotel = session.get(Hotel, pkg.hotel_id) if pkg.hotel_id else None
    room = session.get(Room, pkg.room_id) if pkg.room_id else None

    itineraries = session.scalars(
        select(PackageItinerary)
        .where(PackageItinerary.package_id == pkg.id)
        .order_by(PackageItinerary.day_number.asc())
    ).all()

    flights = session.scalars(
        select(Flight)
        .where(Flight.package_id == pkg.id)
        .where(Flight.is_active.is_(True))
    ).all()

    inclusions = session.scalars(
        select(PackageInclusion)
        .where(PackageInclusion.package_id == pkg.id)
        .order_by(PackageInclusion.sort_order.asc().nullslast(), PackageInclusion.id.asc())
    ).all()

    exclusions = session.scalars(
        select(PackageExclusion)
        .where(PackageExclusion.package_id == pkg.id)
        .order_by(PackageExclusion.sort_order.asc().nullslast(), PackageExclusion.id.asc())
    ).all()

    images = session.scalars(
        select(PackageImage)
        .where(PackageImage.package_id == pkg.id)
        .order_by(PackageImage.sort_order.asc().nullslast(), PackageImage.id.asc())
    ).all()

    payload = _serialise_package(pkg, price)
    payload["description"] = pkg.description
    payload["cancellation_policy"] = pkg.cancellation_policy
    payload["booking_terms"] = pkg.booking_terms
    payload["deposit_percentage"] = float(pkg.deposit_percentage) if pkg.deposit_percentage is not None else None
    payload["payment_deadline_days"] = pkg.payment_deadline_days

    payload["destination"] = (
        {"id": destination.id, "name": destination.name, "slug": destination.slug}
        if destination else None
    )
    payload["hotel"] = (
        {"id": hotel.id, "name": hotel.name, "slug": hotel.slug, "stars": hotel.stars}
        if hotel else None
    )
    payload["room"] = (
        {"id": room.id, "type": room.type, "meal_plan": room.meal_plan}
        if room else None
    )
    payload["itinerary"] = [
        {"day_number": d.day_number, "title": d.title, "description": d.description}
        for d in itineraries
    ]
    payload["flights"] = [
        {
            "id": f.id,
            "flight_from": f.flight_from,
            "flight_to": f.flight_to,
            "airline_name": f.airline_name,
            "luggage_allowance": f.luggage_allowance,
            "included": f.included,
            "notes": f.notes,
        }
        for f in flights
    ]
    payload["inclusions"] = [i.item for i in inclusions]
    payload["exclusions"] = [e.item for e in exclusions]
    payload["images"] = [
        {"url": img.url, "type": img.type, "sort_order": img.sort_order}
        for img in images
    ]

    return _ok(payload)
