"""
services/search_service.py
Cross-product search for activities, hotels, and packages.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from extensions import db
from models.activity import Activity, ActivityPrice
from models.destination import Destination
from models.hotel import Hotel
from models.package import Package, PackagePrice
from models.room import Room
from models.room_rate import RoomRate

log = logging.getLogger(__name__)

DEFAULT_PER_PAGE = 12
MAX_PER_PAGE = 48

VALID_TYPES = ("activity", "hotel", "package")

VALID_SORTS = {
    "activity": ("newest", "name", "price_asc", "price_desc"),
    "hotel":    ("newest", "name", "price_asc", "price_desc", "stars_desc"),
    "package":  ("newest", "name", "price_asc", "price_desc", "duration_asc"),
}


def destinations_for_widget() -> list[dict[str, Any]]:
    """Return the list of destinations used by the search widget dropdown."""
    rows = db.session.scalars(
        select(Destination).order_by(Destination.name.asc())
    ).all()
    return [
        {"id": d.id, "name": d.name, "slug": d.slug, "country": d.country}
        for d in rows
    ]


def search(
    *,
    product_type: str = "hotel",
    destination: str | None = None,
    check_in: date | None = None,
    check_out: date | None = None,
    activity_date: date | None = None,
    adults: int = 1,
    children: int = 0,
    page: int = 1,
    per_page: int = DEFAULT_PER_PAGE,
    sort: str = "newest",
    q: str | None = None,
) -> dict[str, Any]:
    """Run a search. See module docstring for the return shape."""
    ignored: list[str] = []

    ptype = (product_type or "hotel").strip().lower()
    if ptype not in VALID_TYPES:
        ignored.append("product_type")
        ptype = "hotel"

    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        ignored.append("page")
        page = 1

    try:
        per_page = max(1, min(int(per_page), MAX_PER_PAGE))
    except (TypeError, ValueError):
        ignored.append("per_page")
        per_page = DEFAULT_PER_PAGE

    try:
        adults = max(1, int(adults))
        children = max(0, int(children))
    except (TypeError, ValueError):
        ignored.append("party_size")
        adults, children = 1, 0

    sort = (sort or "newest").strip().lower()
    if sort not in VALID_SORTS.get(ptype, ("newest",)):
        ignored.append("sort")
        sort = "newest"

    dest_slug = (destination or "").strip().lower() or None
    query_text = (q or "").strip() or None

    selected_destination: Destination | None = None
    if dest_slug:
        selected_destination = db.session.scalars(
            select(Destination).where(Destination.slug == dest_slug)
        ).first()
        if selected_destination is None:
            ignored.append("destination")
            dest_slug = None

    party_size = adults + children

    if ptype == "activity":
        items, total = _search_activities(
            destination_id=selected_destination.id if selected_destination else None,
            activity_date=activity_date,
            adults=adults, children=children,
            page=page, per_page=per_page, sort=sort, query_text=query_text,
            ignored=ignored,
        )
    elif ptype == "package":
        items, total = _search_packages(
            destination_id=selected_destination.id if selected_destination else None,
            check_in=check_in, check_out=check_out,
            adults=adults, children=children,
            page=page, per_page=per_page, sort=sort, query_text=query_text,
            ignored=ignored,
        )
    else:
        items, total = _search_hotels(
            destination_id=selected_destination.id if selected_destination else None,
            check_in=check_in, check_out=check_out,
            adults=adults, children=children,
            page=page, per_page=per_page, sort=sort, query_text=query_text,
            ignored=ignored,
        )

    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages

    return {
        "product_type": ptype,
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "destination": (
            {"id": selected_destination.id,
             "name": selected_destination.name,
             "slug": selected_destination.slug}
            if selected_destination else None
        ),
        "filters": {
            "destination": dest_slug,
            "check_in": check_in.isoformat() if check_in else None,
            "check_out": check_out.isoformat() if check_out else None,
            "activity_date": activity_date.isoformat() if activity_date else None,
            "adults": adults,
            "children": children,
            "party_size": party_size,
            "q": query_text,
            "sort": sort,
        },
        "ignored": sorted(set(ignored)),
    }


def _search_hotels(
    *, destination_id: int | None, check_in: date | None, check_out: date | None,
    adults: int, children: int,
    page: int, per_page: int, sort: str,
    query_text: str | None, ignored: list[str],
) -> tuple[list[dict], int]:
    stmt = select(Hotel).where(Hotel.is_active.is_(True))
    if destination_id:
        stmt = stmt.where(Hotel.destination_id == destination_id)
    if query_text:
        stmt = stmt.where(Hotel.name.ilike(f"%{query_text}%"))

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)

    min_price_subq = (
        select(func.min(Room.base_price_per_night))
        .where(Room.hotel_id == Hotel.id)
        .where(Room.is_active.is_(True))
        .where(Room.base_price_per_night.is_not(None))
        .correlate(Hotel)
        .scalar_subquery()
    )

    if sort == "name":
        stmt = stmt.order_by(Hotel.name.asc())
    elif sort == "stars_desc":
        stmt = stmt.order_by(Hotel.stars.desc().nullslast(), Hotel.name.asc())
    elif sort == "price_asc":
        stmt = stmt.order_by(min_price_subq.asc().nullslast(), Hotel.name.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(min_price_subq.desc().nullslast(), Hotel.name.asc())
    else:
        stmt = stmt.order_by(Hotel.id.desc())

    offset = (page - 1) * per_page
    rows = db.session.scalars(stmt.limit(per_page).offset(offset)).all()

    items: list[dict] = []
    for h in rows:
        dest = db.session.get(Destination, h.destination_id) if h.destination_id else None
        pricing = _hotel_pricing_for_dates(
            hotel_id=h.id,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            children=children,
        )
        image_url = _first_image_url(getattr(h, "images", None))

        items.append({
            "id": h.id,
            "name": h.name,
            "slug": h.slug,
            "destination_id": h.destination_id,
            "destination_name": dest.name if dest else None,
            "price_adult": (
                float(pricing["adult_rate"])
                if pricing["adult_rate"] is not None else None
            ),
            "currency": pricing["currency"],
            "image_url": image_url,
            "extra": {
                "stars": h.stars,
                "check_in_time": h.check_in_time,
                "check_out_time": h.check_out_time,
            },
            "price_child": (
                float(pricing["child_rate"])
                if pricing["child_rate"] is not None else None
            ),
            "nights": pricing["nights"],
            "price_per_night": (
                float(pricing["per_night"])
                if pricing["per_night"] is not None else None
            ),
            "total_price": (
                float(pricing["total"])
                if pricing["total"] is not None else None
            ),
            "adults": adults,
            "children": children,
            "check_in": check_in.isoformat() if check_in else None,
            "check_out": check_out.isoformat() if check_out else None,
            "price_basis": "per_night",
        })

    return items, total


def _search_packages(
    *, destination_id: int | None, check_in: date | None, check_out: date | None,
    adults: int, children: int,
    page: int, per_page: int, sort: str,
    query_text: str | None, ignored: list[str],
) -> tuple[list[dict], int]:
    stmt = select(Package).where(Package.is_active.is_(True))
    if destination_id:
        stmt = stmt.where(Package.destination_id == destination_id)
    if query_text:
        stmt = stmt.where(Package.name.ilike(f"%{query_text}%"))
    stmt = stmt.where(Package.capacity >= (adults + children))

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)

    if sort == "name":
        stmt = stmt.order_by(Package.name.asc())
    elif sort == "price_asc":
        stmt = stmt.order_by(
            select(PackagePrice.adult_price)
            .where(PackagePrice.package_id == Package.id)
            .order_by(PackagePrice.id.asc()).limit(1)
            .scalar_subquery().asc()
        )
    elif sort == "price_desc":
        stmt = stmt.order_by(
            select(PackagePrice.adult_price)
            .where(PackagePrice.package_id == Package.id)
            .order_by(PackagePrice.id.asc()).limit(1)
            .scalar_subquery().desc()
        )
    elif sort == "duration_asc":
        stmt = stmt.order_by(Package.duration_nights.asc())
    else:
        stmt = stmt.order_by(Package.id.desc())

    offset = (page - 1) * per_page
    rows = db.session.scalars(stmt.limit(per_page).offset(offset)).all()

    from services import availability_service

    items: list[dict] = []
    for p in rows:
        try:
            if check_in is not None and check_out is not None:
                remaining = availability_service.package_availability(p.id, check_in)
                if remaining is not None and remaining < (adults + children):
                    continue
        except Exception as exc:
            log.debug("search availability skipped for package %s: %s", p.id, exc)

        dest = db.session.get(Destination, p.destination_id) if p.destination_id else None
        pricing = _package_pricing(
            package_id=p.id, adults=adults, children=children
        )
        image_url = _first_image_url(getattr(p, "images", None))

        items.append({
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "destination_id": p.destination_id,
            "destination_name": dest.name if dest else None,
            "price_adult": (
                float(pricing["adult_price"])
                if pricing["adult_price"] is not None else None
            ),
            "currency": pricing["currency"],
            "image_url": image_url,
            "extra": {
                "duration_nights": p.duration_nights,
                "package_type": p.package_type,
                "code": p.code,
            },
            "price_child": (
                float(pricing["child_price"])
                if pricing["child_price"] is not None else None
            ),
            "nights": p.duration_nights,
            "price_per_night": None,
            "total_price": (
                float(pricing["total"])
                if pricing["total"] is not None else None
            ),
            "adults": adults,
            "children": children,
            "check_in": check_in.isoformat() if check_in else None,
            "check_out": check_out.isoformat() if check_out else None,
            "price_basis": "per_person_flat",
        })

    return items, total


def _search_activities(
    *, destination_id: int | None, activity_date: date | None,
    adults: int, children: int,
    page: int, per_page: int, sort: str,
    query_text: str | None, ignored: list[str],
) -> tuple[list[dict], int]:
    stmt = select(Activity).where(Activity.is_active.is_(True))
    if destination_id:
        stmt = stmt.where(Activity.destination_id == destination_id)
    if query_text:
        stmt = stmt.where(Activity.name.ilike(f"%{query_text}%"))
    stmt = stmt.where(Activity.capacity >= (adults + children))

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)

    if sort == "name":
        stmt = stmt.order_by(Activity.name.asc())
    elif sort == "price_asc":
        stmt = stmt.order_by(
            select(ActivityPrice.adult_price)
            .where(ActivityPrice.activity_id == Activity.id)
            .order_by(ActivityPrice.id.asc()).limit(1)
            .scalar_subquery().asc()
        )
    elif sort == "price_desc":
        stmt = stmt.order_by(
            select(ActivityPrice.adult_price)
            .where(ActivityPrice.activity_id == Activity.id)
            .order_by(ActivityPrice.id.asc()).limit(1)
            .scalar_subquery().desc()
        )
    else:
        stmt = stmt.order_by(Activity.id.desc())

    offset = (page - 1) * per_page
    rows = db.session.scalars(stmt.limit(per_page).offset(offset)).all()

    from services import availability_service

    items: list[dict] = []
    for a in rows:
        try:
            if activity_date is not None:
                remaining = availability_service.activity_availability(a.id, activity_date)
                if remaining is not None and remaining < (adults + children):
                    continue
        except Exception as exc:
            log.debug("search availability skipped for activity %s: %s", a.id, exc)

        dest = db.session.get(Destination, a.destination_id) if a.destination_id else None
        pricing = _activity_pricing(
            activity_id=a.id, adults=adults, children=children
        )
        image_url = _first_image_url(getattr(a, "images", None))

        items.append({
            "id": a.id,
            "name": a.name,
            "slug": a.slug,
            "destination_id": a.destination_id,
            "destination_name": dest.name if dest else None,
            "price_adult": (
                float(pricing["adult_price"])
                if pricing["adult_price"] is not None else None
            ),
            "currency": pricing["currency"],
            "image_url": image_url,
            "extra": {
                "category": a.category,
                "difficulty": a.difficulty,
                "duration_hours": (
                    float(a.duration_hours) if a.duration_hours else None
                ),
            },
            "price_child": (
                float(pricing["child_price"])
                if pricing["child_price"] is not None else None
            ),
            "nights": None,
            "price_per_night": None,
            "total_price": (
                float(pricing["total"])
                if pricing["total"] is not None else None
            ),
            "adults": adults,
            "children": children,
            "check_in": activity_date.isoformat() if activity_date else None,
            "check_out": None,
            "price_basis": "per_person_flat",
        })

    return items, total


def _hotel_pricing_for_dates(
    *, hotel_id: int,
    check_in: date | None, check_out: date | None,
    adults: int, children: int,
) -> dict[str, Any]:
    """Compute the hotel price picture for a stay."""
    empty = {
        "adult_rate": None, "child_rate": None, "nights": None,
        "per_night": None, "total": None, "currency": "USD",
    }

    room = db.session.scalars(
        select(Room)
        .where(Room.hotel_id == hotel_id)
        .where(Room.is_active.is_(True))
        .where(Room.base_price_per_night.is_not(None))
        .where(Room.base_price_per_night > 0)
        .order_by(Room.base_price_per_night.asc())
        .limit(1)
    ).first()

    if room is None:
        return empty

    nights: int | None = None
    if check_in is not None and check_out is not None:
        delta = (check_out - check_in).days
        nights = max(0, delta)
    else:
        nights = 1

    adult_rate: Decimal | None = None
    child_rate: Decimal | None = None
    currency = "USD"

    if check_in is not None:
        rate = db.session.scalars(
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
        if rate is not None:
            adult_rate = rate.adult_price
            child_rate = rate.child_price
            currency = rate.currency or "USD"

    if adult_rate is None:
        adult_rate = room.base_price_per_night
        child_rate = Decimal("0.00")

    try:
        per_night = (adult_rate * adults) + ((child_rate or Decimal("0")) * children)
        total = per_night * nights if nights is not None else None
    except Exception:
        per_night = None
        total = None

    return {
        "adult_rate": adult_rate,
        "child_rate": child_rate,
        "nights": nights,
        "per_night": per_night,
        "total": total,
        "currency": currency,
    }


def _package_pricing(
    *, package_id: int, adults: int, children: int
) -> dict[str, Any]:
    row = db.session.scalars(
        select(PackagePrice)
        .where(PackagePrice.package_id == package_id)
        .order_by(PackagePrice.id.asc())
        .limit(1)
    ).first()
    if row is None:
        return {
            "adult_price": None, "child_price": None,
            "total": None, "currency": "USD",
        }
    adult_price = row.adult_price
    child_price = row.child_price
    try:
        total = (adult_price * adults) + ((child_price or Decimal("0")) * children)
    except Exception:
        total = None
    return {
        "adult_price": adult_price,
        "child_price": child_price,
        "total": total,
        "currency": row.currency or "USD",
    }


def _activity_pricing(
    *, activity_id: int, adults: int, children: int
) -> dict[str, Any]:
    row = db.session.scalars(
        select(ActivityPrice)
        .where(ActivityPrice.activity_id == activity_id)
        .order_by(ActivityPrice.id.asc())
        .limit(1)
    ).first()
    if row is None:
        return {
            "adult_price": None, "child_price": None,
            "total": None, "currency": "USD",
        }
    adult_price = row.adult_price
    child_price = row.child_price
    try:
        total = (adult_price * adults) + ((child_price or Decimal("0")) * children)
    except Exception:
        total = None
    return {
        "adult_price": adult_price,
        "child_price": child_price,
        "total": total,
        "currency": row.currency or "USD",
    }


def _first_price_for_activity(activity_id: int) -> tuple[Decimal | None, str]:
    row = db.session.scalars(
        select(ActivityPrice)
        .where(ActivityPrice.activity_id == activity_id)
        .order_by(ActivityPrice.id.asc())
        .limit(1)
    ).first()
    if row is None:
        return None, "USD"
    return row.adult_price, row.currency or "USD"


def _first_price_for_package(package_id: int) -> tuple[Decimal | None, str]:
    row = db.session.scalars(
        select(PackagePrice)
        .where(PackagePrice.package_id == package_id)
        .order_by(PackagePrice.id.asc())
        .limit(1)
    ).first()
    if row is None:
        return None, "USD"
    return row.adult_price, row.currency or "USD"


def _cheapest_room_price(hotel_id: int) -> tuple[Decimal | None, str]:
    row = db.session.scalars(
        select(Room)
        .where(Room.hotel_id == hotel_id)
        .where(Room.is_active.is_(True))
        .where(Room.base_price_per_night.is_not(None))
        .order_by(Room.base_price_per_night.asc())
        .limit(1)
    ).first()
    if row is None:
        return None, "USD"
    return row.base_price_per_night, "USD"


def _first_image_url(images: list | None) -> str | None:
    if not images:
        return None
    for img in images:
        url = getattr(img, "url", None)
        if url:
            return url
    return None


__all__ = [
    "search",
    "destinations_for_widget",
]
