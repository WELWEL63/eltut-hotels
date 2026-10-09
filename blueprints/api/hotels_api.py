"""blueprints/api/hotels_api.py - read endpoints for hotels.

Public read surface. No auth, no CSRF. Two endpoints:

  GET /api/v1/hotels              -> paginated list
  GET /api/v1/hotels/<id_or_slug> -> single hotel detail (rooms,
                                     facilities, images, rates)

Query params for the list endpoint:
  destination_id  int    filter by destination
  min_stars       int    1..5
  min_price       float  min room base price per night >=
  max_price       float  min room base price per night <=
  page            int    default 1
  per_page        int    default 20, max 100
  sort            str    name|stars|price (default: name)

WHY a computed min_price_per_night on the list: hotels do not have a
single price - rooms do. Clients want to sort/filter by "cheapest
room in this hotel", so we compute it via a correlated subquery. This
keeps the SQL to one round-trip instead of N+1.

WHY detail returns all rooms with their rates: the seasonal rate
windows added in Step 11.5 are exactly what a booking client needs to
price a stay. Returning them here avoids a second API call.
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
    Hotel,
    HotelFacility,
    HotelImage,
    Room,
    RoomRate,
)


MAX_PER_PAGE = 100
DEFAULT_PER_PAGE = 20
SORT_CHOICES = ("name", "stars", "price")


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


def _min_price_subquery():
    return (
        select(func.min(Room.base_price_per_night))
        .where(Room.hotel_id == Hotel.id)
        .where(Room.is_active.is_(True))
        .where(Room.base_price_per_night.is_not(None))
        .correlate(Hotel)
        .scalar_subquery()
    )


def _serialise_hotel(hotel: Hotel, min_price: Decimal | None) -> dict[str, Any]:
    return {
        "id": hotel.id,
        "name": hotel.name,
        "slug": hotel.slug,
        "stars": hotel.stars,
        "address": hotel.address,
        "latitude": float(hotel.latitude) if hotel.latitude is not None else None,
        "longitude": float(hotel.longitude) if hotel.longitude is not None else None,
        "destination_id": hotel.destination_id,
        "total_capacity": hotel.total_capacity,
        "check_in_time": hotel.check_in_time,
        "check_out_time": hotel.check_out_time,
        "min_price_per_night": float(min_price) if min_price is not None else None,
    }


def _serialise_rate(rate: RoomRate) -> dict[str, Any]:
    """Return the JSON shape for one rate window.

    Column names come from models/room_rate.py:
      adult_price, child_price, currency, valid_from, valid_to.
    """
    return {
        "id": rate.id,
        "valid_from": rate.valid_from.isoformat() if rate.valid_from else None,
        "valid_to": rate.valid_to.isoformat() if rate.valid_to else None,
        "adult_price": float(rate.adult_price) if rate.adult_price is not None else None,
        "child_price": float(rate.child_price) if rate.child_price is not None else None,
        "currency": rate.currency,
    }


def _serialise_room(room: Room, rates: list[RoomRate] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": room.id,
        "type": room.type,
        "meal_plan": room.meal_plan,
        "max_occupancy": room.max_occupancy,
        "capacity": room.capacity,
        "base_price_per_night": float(room.base_price_per_night) if room.base_price_per_night is not None else None,
        "description": room.description,
    }
    if rates is not None:
        payload["rates"] = [_serialise_rate(r) for r in rates]
    return payload


@api_bp.get("/hotels")
def hotels_list():
    session = db.session
    ignored: list[str] = []

    destination_id, ok = _to_int(request.args.get("destination_id"), 0)
    if not ok:
        ignored.append("destination_id")
        destination_id = 0

    min_stars, ok = _to_int(request.args.get("min_stars"), 0, minimum=0, maximum=5)
    if not ok:
        ignored.append("min_stars")
        min_stars = 0

    min_price, ok = _to_decimal(request.args.get("min_price"))
    if not ok:
        ignored.append("min_price")

    max_price, ok = _to_decimal(request.args.get("max_price"))
    if not ok:
        ignored.append("max_price")

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

    min_price_expr = _min_price_subquery()

    stmt = (
        select(Hotel, min_price_expr.label("min_price"))
        .where(Hotel.is_active.is_(True))
    )

    if destination_id:
        stmt = stmt.where(Hotel.destination_id == destination_id)
    if min_stars:
        stmt = stmt.where(Hotel.stars >= min_stars)
    if min_price is not None:
        stmt = stmt.where(min_price_expr >= min_price)
    if max_price is not None:
        stmt = stmt.where(min_price_expr <= max_price)

    if sort == "stars":
        stmt = stmt.order_by(Hotel.stars.desc().nullslast(), Hotel.name.asc())
    elif sort == "price":
        stmt = stmt.order_by(min_price_expr.asc().nullslast(), Hotel.name.asc())
    else:
        stmt = stmt.order_by(Hotel.name.asc())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.scalar(count_stmt) or 0

    offset = (page - 1) * per_page
    rows = session.execute(stmt.offset(offset).limit(per_page)).all()

    items = [_serialise_hotel(hotel, min_p) for hotel, min_p in rows]

    meta: dict[str, Any] = {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }
    if ignored:
        meta["ignored_filters"] = sorted(set(ignored))

    return _ok({"items": items, "meta": meta})


@api_bp.get("/hotels/<identifier>")
def hotels_detail(identifier: str):
    session = db.session

    stmt = select(Hotel).where(Hotel.is_active.is_(True))
    if identifier.isdigit():
        stmt = stmt.where(Hotel.id == int(identifier))
    else:
        stmt = stmt.where(Hotel.slug == identifier)

    hotel = session.scalars(stmt).first()
    if hotel is None:
        return _err("not_found", f"hotel {identifier!r} not found", 404)

    destination = session.get(Destination, hotel.destination_id) if hotel.destination_id else None

    facilities = session.scalars(
        select(HotelFacility)
        .where(HotelFacility.hotel_id == hotel.id)
        .order_by(HotelFacility.name.asc())
    ).all()

    images = session.scalars(
        select(HotelImage)
        .where(HotelImage.hotel_id == hotel.id)
        .order_by(HotelImage.sort_order.asc().nullslast(), HotelImage.id.asc())
    ).all()

    rooms = session.scalars(
        select(Room)
        .where(Room.hotel_id == hotel.id)
        .where(Room.is_active.is_(True))
        .order_by(Room.base_price_per_night.asc().nullslast(), Room.type.asc())
    ).all()

    room_ids = [r.id for r in rooms]
    rates_by_room: dict[int, list[RoomRate]] = {rid: [] for rid in room_ids}
    if room_ids:
        rate_rows = session.scalars(
            select(RoomRate)
            .where(RoomRate.room_id.in_(room_ids))
            .order_by(RoomRate.room_id.asc(), RoomRate.valid_from.asc().nullsfirst())
        ).all()
        for r in rate_rows:
            rates_by_room.setdefault(r.room_id, []).append(r)

    min_price = min(
        (r.base_price_per_night for r in rooms if r.base_price_per_night is not None),
        default=None,
    )

    payload = _serialise_hotel(hotel, min_price)
    payload["description"] = hotel.description
    payload["destination"] = (
        {"id": destination.id, "name": destination.name, "slug": destination.slug}
        if destination else None
    )
    payload["facilities"] = [
        {"name": f.name, "type": f.type, "quantity": f.quantity, "notes": f.notes}
        for f in facilities
    ]
    payload["images"] = [
        {"url": img.url, "type": img.type, "sort_order": img.sort_order}
        for img in images
    ]
    payload["rooms"] = [
        _serialise_room(room, rates=rates_by_room.get(room.id, []))
        for room in rooms
    ]

    return _ok(payload)
