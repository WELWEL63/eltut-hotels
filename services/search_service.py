"""
services/search_service.py
"""
from __future__ import annotations
import logging
from datetime import timedelta, date
_td = timedelta
from decimal import Decimal
from typing import Any
from sqlalchemy import func, select
from extensions import db
from models.destination import Destination
from models.hotel import Hotel, HotelFacility, HotelImage
from models.room import Room
from models.room_rate import RoomRate

log = logging.getLogger(__name__)
DEFAULT_PER_PAGE = 12
MAX_PER_PAGE = 48
VALID_TYPES = ("hotel",)
VALID_SORTS = {"hotel": ("newest", "name", "price_asc", "price_desc", "stars_desc")}
MAX_ADULTS = 8
MAX_CHILDREN = 8

FACILITY_ICONS = {
    "general": "bi-water", "dining": "bi-egg-fried", "wellness": "bi-flower1",
    "sport": "bi-bicycle", "family": "bi-people", "business": "bi-wifi", "other": "bi-check-circle",
}

def destinations_for_widget() -> list[dict[str, Any]]:
    rows = db.session.scalars(
        select(Destination).where(Destination.is_bookable.is_(True)).order_by(Destination.name.asc())
    ).all()
    return [{"id": d.id, "name": d.name, "slug": d.slug, "country": d.country} for d in rows]

def search(
    *, product_type: str = "hotel", destination: str | None = None,
    check_in: date | None = None, check_out: date | None = None,
    adults: int = 1, children: int = 0, page: int = 1,
    per_page: int = DEFAULT_PER_PAGE, sort: str = "newest", q: str | None = None,
) -> dict[str, Any]:
    ignored: list[str] = []
    ptype = "hotel"  # Forced to hotel
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 12), MAX_PER_PAGE))
    adults = max(1, min(MAX_ADULTS, int(adults or 1)))
    children = max(0, min(MAX_CHILDREN, int(children or 0)))
    sort = (sort or "newest").strip().lower()
    if sort not in VALID_SORTS["hotel"]: sort = "newest"

    dest_slug = (destination or "").strip().lower() or None
    query_text = (q or "").strip() or None
    selected_destination = None

    if dest_slug:
        selected_destination = db.session.scalars(
            select(Destination).where(Destination.slug == dest_slug, Destination.is_bookable.is_(True))
        ).first()
        if selected_destination is None: dest_slug = None

    items, total = _search_hotels(
        destination_id=selected_destination.id if selected_destination else None,
        check_in=check_in, check_out=check_out, adults=adults, children=children,
        page=page, per_page=per_page, sort=sort, query_text=query_text, ignored=ignored,
    )

    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages: page = total_pages

    return {
        "product_type": "hotel", "items": items, "total": total, "page": page, "per_page": per_page, "total_pages": total_pages,
        "destination": {"id": selected_destination.id, "name": selected_destination.name, "slug": selected_destination.slug} if selected_destination else None,
        "filters": {"destination": dest_slug, "check_in": check_in.isoformat() if check_in else None, "check_out": check_out.isoformat() if check_out else None, "adults": adults, "children": children, "party_size": adults + children, "q": query_text, "sort": sort},
        "ignored": sorted(set(ignored)),
    }

def _rooms_note(min_rooms: int | None) -> str:
    if min_rooms is None: return ""
    return f"Needs {min_rooms} room{'s' if min_rooms > 1 else ''}"

def _search_hotels(*, destination_id, check_in, check_out, adults, children, page, per_page, sort, query_text, ignored) -> tuple[list[dict], int]:
    from services.hotel_capacity_service import min_rooms_needed
    base = select(Hotel).where(Hotel.is_active.is_(True))
    if destination_id: base = base.where(Hotel.destination_id == destination_id)
    if query_text: base = base.where(Hotel.name.ilike(f"%{query_text}%"))
    base = base.where(select(Room.id).where(Room.hotel_id == Hotel.id, Room.is_active.is_(True)).correlate(Hotel).exists())

    if children > 0:
        child_cap_expr = ((Room.max_children.is_not(None) & (Room.max_children > 0)) | (Room.max_children.is_(None) & ((Room.max_adults.is_(None) & (Room.max_occupancy >= 3)) | ((Room.max_adults.is_not(None)) & (Room.max_adults == Room.max_occupancy) & (Room.max_occupancy >= 3)) | ((Room.max_adults.is_not(None)) & (Room.max_adults != Room.max_occupancy) & ((Room.max_occupancy - Room.max_adults) > 0)))))
        base = base.where(select(Room.id).where(Room.hotel_id == Hotel.id, Room.is_active.is_(True), child_cap_expr).correlate(Hotel).exists())

    min_price_subq = (select(func.min(Room.base_price_per_night)).where(Room.hotel_id == Hotel.id, Room.is_active.is_(True), Room.base_price_per_night.is_not(None), Room.base_price_per_night > 0).correlate(Hotel).scalar_subquery())
    if sort == "name": base = base.order_by(Hotel.name.asc())
    elif sort == "stars_desc": base = base.order_by(Hotel.stars.desc().nullslast(), Hotel.name.asc())
    elif sort == "price_asc": base = base.order_by(min_price_subq.asc().nullslast(), Hotel.name.asc())
    elif sort == "price_desc": base = base.order_by(min_price_subq.desc().nullslast(), Hotel.name.asc())
    else: base = base.order_by(Hotel.id.desc())

    BATCH = 100
    total = 0
    offset = 0
    while True:
        batch_rows = list(db.session.scalars(base.limit(BATCH).offset(offset)).all())
        if not batch_rows: break
        for h in batch_rows:
            if min_rooms_needed(h.id, adults=adults, child_ages=[10] * children, infants=0) is not None: total += 1
        if len(batch_rows) < BATCH: break
        offset += BATCH
        if offset > 2000: break

    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages: page = total_pages

    needed = per_page
    skip_until = (page - 1) * per_page
    items = []
    offset = 0
    seen_valid = 0
    while needed > 0 and offset < 5000:
        batch_rows = list(db.session.scalars(base.limit(BATCH).offset(offset)).all())
        if not batch_rows: break
        for h in batch_rows:
            m = min_rooms_needed(h.id, adults=adults, child_ages=[10] * children, infants=0)
            if m is None: continue
            if seen_valid < skip_until: seen_valid += 1; continue
            seen_valid += 1
            dest = db.session.get(Destination, h.destination_id) if h.destination_id else None
            pricing = _hotel_pricing_for_dates(hotel_id=h.id, check_in=check_in, check_out=check_out, adults=adults, children=children)
            rich = _hotel_display_data(h.id)
            image_url = _first_image_url(getattr(h, "images", None)) or rich["cover_image"]
            items.append({
                "id": h.id, "name": h.name, "slug": h.slug, "destination_id": h.destination_id, "destination_name": dest.name if dest else None,
                "price_adult": float(pricing["adult_rate"]) if pricing["adult_rate"] is not None else None, "currency": pricing["currency"],
                "image_url": image_url, "extra": {"stars": h.stars, "check_in_time": h.check_in_time, "check_out_time": h.check_out_time},
                "price_child": float(pricing["child_rate"]) if pricing["child_rate"] is not None else None, "nights": pricing["nights"],
                "price_per_night": float(pricing["per_night"]) if pricing["per_night"] is not None else None, "total_price": float(pricing["total"]) if pricing["total"] is not None else None,
                "meal_plan": pricing.get("meal_plan"), "adults": adults, "children": children, "check_in": check_in.isoformat() if check_in else None, "check_out": check_out.isoformat() if check_out else None,
                "price_basis": "per_night", "stars": h.stars, "address": h.address, "check_in_time": h.check_in_time, "check_out_time": h.check_out_time,
                "google_maps_url": h.google_maps_url, "description_snippet": (h.description or "")[:140] + "..." if h.description and len(h.description) > 140 else (h.description or ""),
                "facilities": rich["facilities"], "room_count": rich["room_count"], "min_rooms": m, "rooms_note": _rooms_note(m),
            })
            needed -= 1
            if needed <= 0: break
        if len(batch_rows) < BATCH: break
        offset += BATCH
    return items, total

def _hotel_display_data(hotel_id: int) -> dict[str, Any]:
    cover = db.session.scalars(select(HotelImage).where(HotelImage.hotel_id == hotel_id, HotelImage.media_type == "image").order_by(HotelImage.sort_order.asc()).limit(1)).first()
    facs = db.session.scalars(select(HotelFacility).where(HotelFacility.hotel_id == hotel_id).order_by(HotelFacility.id.asc()).limit(6)).all()
    seen_types = set()
    picked = []
    for f in facs:
        if f.type in seen_types and len(picked) >= 3: continue
        seen_types.add(f.type)
        picked.append({"name": f.name, "type": f.type, "icon": FACILITY_ICONS.get(f.type, "bi-check-circle")})
        if len(picked) >= 3: break
    room_count = int(db.session.scalar(select(func.count(Room.id)).where(Room.hotel_id == hotel_id)) or 0)
    return {"cover_image": cover.url if cover else None, "facilities": picked, "room_count": room_count}

def _hotel_pricing_for_dates(*, hotel_id, check_in, check_out, adults, children) -> dict[str, Any]:
    empty = {"adult_rate": None, "child_rate": None, "nights": None, "per_night": None, "total": None, "currency": "GBP", "meal_plan": None}
    from services import hotel_capacity_service
    try: grouping = hotel_capacity_service.best_room_grouping(hotel_id, adults=adults, child_ages=[6] * children, infants=0, check_in=check_in, check_out=check_out)
    except Exception: grouping = None
    min_rooms = grouping.get("min_rooms", 1) if grouping else 1
    room = db.session.scalars(select(Room).where(Room.hotel_id == hotel_id, Room.is_active.is_(True), Room.base_price_per_night.is_not(None), Room.base_price_per_night > 0).order_by(Room.base_price_per_night.asc()).limit(1)).first()
    if room is None: return empty
    nights = max(1, (check_out - check_in).days) if check_in and check_out else 1
    adult_rate, child_rate, currency = Decimal("0"), Decimal("0"), "GBP"
    if check_in is not None:
        rate = db.session.scalars(select(RoomRate).where(RoomRate.room_id == room.id, (RoomRate.valid_from.is_(None)) | (RoomRate.valid_from <= check_in), (RoomRate.valid_to.is_(None)) | (RoomRate.valid_to >= check_in)).order_by(RoomRate.id.asc()).limit(1)).first()
        if rate: adult_rate, child_rate, currency = rate.adult_price, rate.child_price, rate.currency or "GBP"
        else: adult_rate = room.base_price_per_night
    else: adult_rate = room.base_price_per_night
    per_night = (adult_rate * 2 + child_rate) * min_rooms
    return {"adult_rate": adult_rate, "child_rate": child_rate, "nights": nights, "per_night": per_night, "total": per_night * nights, "currency": currency, "meal_plan": room.meal_plan}

def _first_image_url(images: list | None) -> str | None:
    if not images: return None
    for img in images:
        url = getattr(img, "url", None)
        if url and not url.lower().endswith(".mp4"): return url
    return None

__all__ = ["search", "destinations_for_widget"]