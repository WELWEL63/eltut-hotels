"""
blueprints/public/hotel_routes.py
"""
from __future__ import annotations
from datetime import date, timedelta
from flask import abort, current_app, render_template, request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from blueprints.public import public_bp
from extensions import db
from models import (
    Destination, Hotel, HotelFacility, HotelImage, Room, RoomImage,
    VALID_ROOM_MEAL_PLANS, HotelExclusion, HotelFAQ, HotelInclusion, HotelTip, RoomRate
)

def _int_arg(name: str, default: int, lo: int, hi: int) -> int:
    raw = request.args.get(name, "").strip()
    try:
        return max(lo, min(hi, int(raw)))
    except (TypeError, ValueError):
        return default

def _parse_date_arg(name: str) -> date | None:
    raw = (request.args.get(name) or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None

def _parse_child_ages_arg() -> list[int]:
    raw = (request.args.get("child_ages") or "").strip()
    if not raw: return []
    ages = []
    for part in raw.split(","):
        try: ages.append(int(part.strip()))
        except ValueError: pass
    return ages

def _cheapest_room_price(hotel_id: int) -> tuple[float | None, str | None]:
    row = db.session.scalar(
        select(func.min(Room.base_price_per_night))
        .where(Room.hotel_id == hotel_id, Room.is_active.is_(True))
    )
    return (float(row), "GBP") if row is not None else (None, None)

def _avg_rating(hotel_id: int) -> tuple[float | None, int]:
    try:
        from mongo.reviews import rating_summary
        summary = rating_summary("hotel", hotel_id)
        return (summary.get("average"), int(summary.get("count") or 0))
    except Exception:
        return (None, 0)

@public_bp.route("/hotels")
def hotel_list():
    try: _party_adults = max(1, min(8, int(request.args.get("adults", "2") or "2")))
    except (TypeError, ValueError): _party_adults = 2
    try: _party_children = max(0, min(8, int(request.args.get("children", "0") or "0")))
    except (TypeError, ValueError): _party_children = 0
    try: _party_infants = max(0, min(8, int(request.args.get("infants", "0") or "0")))
    except (TypeError, ValueError): _party_infants = 0
    
    _child_ages_raw = (request.args.get("child_ages") or "").strip()
    _party_child_ages = []
    if _child_ages_raw:
        for _p in _child_ages_raw.split(","):
            try: _party_child_ages.append(int(_p.strip()))
            except ValueError: pass
    if _party_children > 0 and len(_party_child_ages) < _party_children:
        _party_child_ages += [6] * (_party_children - len(_party_child_ages))
    _has_party = bool(request.args.get("adults") or request.args.get("children"))

    def _rooms_note_text(_min):
        if _min is None: return ""
        if _min == 1: return "Fits in 1 room"
        if _min == 2: return "Needs 2 rooms"
        if _min == 3: return "Needs 3 rooms"
        return f"Needs {_min} rooms"

    page = _int_arg("page", 1, 1, 10_000)
    per_page = int(current_app.config.get("ITEMS_PER_PAGE", 12) or 12)
    per_page = max(6, min(per_page, 48))

    destination_slug = (request.args.get("destination") or "").strip().lower()
    stars_raw = request.args.get("stars", "").strip()
    meal_plan = (request.args.get("meal_plan") or "").strip().lower()
    query_text = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "newest").strip().lower()

    stars = int(stars_raw) if stars_raw.isdigit() else None

    stmt = select(Hotel).options(joinedload(Hotel.images)).where(Hotel.is_active.is_(True))
    selected_destination = None
    if destination_slug:
        selected_destination = db.session.scalar(select(Destination).where(Destination.slug == destination_slug))
        if selected_destination:
            stmt = stmt.where(Hotel.destination_id == selected_destination.id)

    if stars is not None: stmt = stmt.where(Hotel.stars == stars)
    if meal_plan and meal_plan in VALID_ROOM_MEAL_PLANS:
        stmt = stmt.where(select(Room.id).where(Room.hotel_id == Hotel.id, Room.meal_plan == meal_plan, Room.is_active.is_(True)).exists())
    if query_text: stmt = stmt.where(Hotel.name.ilike(f"%{query_text}%"))

    if sort == "name": stmt = stmt.order_by(Hotel.name.asc())
    elif sort == "stars_desc": stmt = stmt.order_by(Hotel.stars.desc(), Hotel.name.asc())
    elif sort == "price_asc": stmt = stmt.order_by(select(func.min(Room.base_price_per_night)).where(Room.hotel_id == Hotel.id).scalar_subquery().asc())
    elif sort == "price_desc": stmt = stmt.order_by(select(func.min(Room.base_price_per_night)).where(Room.hotel_id == Hotel.id).scalar_subquery().desc())
    else: stmt = stmt.order_by(Hotel.id.desc())

    total = int(db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    rows = list(db.session.scalars(stmt.limit(per_page).offset(offset)).unique())

    items = []
    for h in rows:
        price, currency = _cheapest_room_price(h.id)
        first_image = h.images[0].url if h.images else None
        _min_rooms = None
        if _has_party:
            try:
                from services import hotel_capacity_service as _cap
                _min_rooms = _cap.min_rooms_needed(h.id, adults=_party_adults, child_ages=_party_child_ages, infants=_party_infants)
            except Exception: pass
        items.append({
            "hotel": h, "price": price, "currency": currency, "image_url": first_image,
            "min_rooms": _min_rooms, "rooms_note": _rooms_note_text(_min_rooms),
        })

    destinations = list(db.session.scalars(select(Destination).order_by(Destination.name)))

    return render_template(
        "public/hotel_list.html", items=items, total=total, page=page, total_pages=total_pages,
        destinations=destinations, meal_plans=VALID_ROOM_MEAL_PLANS, selected_destination=selected_destination,
        selected_stars=stars, selected_meal_plan=meal_plan, query_text=query_text, sort=sort,
    )

@public_bp.route("/hotels/<slug>")
def hotel_detail(slug: str):
    hotel = db.session.scalars(select(Hotel).options(joinedload(Hotel.images)).where(Hotel.slug == slug, Hotel.is_active.is_(True))).unique().first()
    if hotel is None: abort(404)

    destination = db.session.get(Destination, hotel.destination_id)
    facilities = list(db.session.scalars(select(HotelFacility).where(HotelFacility.hotel_id == hotel.id).order_by(HotelFacility.name)))
    images = list(db.session.scalars(select(HotelImage).where(HotelImage.hotel_id == hotel.id).order_by(HotelImage.sort_order)))
    rooms = list(db.session.scalars(select(Room).where(Room.hotel_id == hotel.id, Room.is_active.is_(True)).order_by(Room.base_price_per_night)))

    url_check_in = _parse_date_arg("check_in")
    url_check_out = _parse_date_arg("check_out")
    if url_check_in and url_check_out and url_check_out > url_check_in:
        check_in, check_out = url_check_in, url_check_out
    else:
        check_in = date.today()
        check_out = check_in + timedelta(days=7)

    nights = (check_out - check_in).days
    adults = _int_arg("adults", 2, 1, 8)
    children = _int_arg("children", 0, 0, 8)
    infants = _int_arg("infants", 0, 0, 8)
    child_ages = _parse_child_ages_arg()

    if children > 0 and len(child_ages) < children:
        child_ages = list(child_ages) + [6] * (children - len(child_ages))

    # ─── Multi-room grouping ─────────────
    best_grouping = None
    has_stay_dates = bool(url_check_in and url_check_out and url_check_out > url_check_in)
    if has_stay_dates:
        try:
            from services import hotel_capacity_service
            best_grouping = hotel_capacity_service.best_room_grouping(hotel.id, adults=adults, child_ages=child_ages, infants=infants, check_in=check_in, check_out=check_out)
        except Exception: best_grouping = None

    min_rooms_needed = best_grouping.get("min_rooms", 1) if best_grouping else 1

    def _stay_pricing(room: Room) -> dict:
        rate = db.session.scalars(
            select(RoomRate).where(RoomRate.room_id == room.id)
            .where((RoomRate.valid_from.is_(None)) | (RoomRate.valid_from <= check_in))
            .where((RoomRate.valid_to.is_(None)) | (RoomRate.valid_to >= check_in))
            .order_by(RoomRate.id.asc()).limit(1)
        ).first()
        
        adult_rate = float(rate.adult_price or 0) if rate else float(room.base_price_per_night or 0)
        child_rate = float(rate.child_price or 0) if rate else 0.0
        currency = (rate.currency or "GBP") if rate else "GBP"
        
        # We need 2 adults per room (5 adults / 3 rooms = 1.66, round up to 2)
        # We need 1 child per room (1 child / 3 rooms = 0.33, round up to 1)
        adults_per_room = 2
        children_per_room = 1
        
        # If the party is small, just use the exact numbers
        if min_rooms_needed == 1:
            adults_per_room = adults
            children_per_room = len(child_ages)
            
        per_night = (adult_rate * adults_per_room) + (child_rate * children_per_room)
        total = per_night * max(nights, 0)
        
        return {
            "adult_rate": adult_rate, 
            "child_rate": child_rate, 
            "per_night": per_night, 
            "total": total, 
            "currency": currency
        }

    rooms_with_availability = []
    try:
        from services.availability_service import hotel_room_availability
        for room in rooms:
            try: remaining = hotel_room_availability(room.id, check_in, check_out)
            except Exception: remaining = None
            rate_rows = list(db.session.scalars(select(RoomRate).where(RoomRate.room_id == room.id).order_by(RoomRate.valid_from.asc().nullsfirst()).limit(12)))
            rooms_with_availability.append({"room": room, "remaining": remaining, "rates": rate_rows, "pricing": _stay_pricing(room)})
    except Exception:
        for r in rooms:
            rate_rows = list(db.session.scalars(select(RoomRate).where(RoomRate.room_id == r.id).order_by(RoomRate.valid_from.asc().nullsfirst()).limit(12)))
            rooms_with_availability.append({"room": r, "remaining": None, "rates": rate_rows, "pricing": _stay_pricing(r)})

    # ─── Sidebar & Card pricing ───
    cheapest_total = None
    cheapest_per_night = None
    sidebar_currency = "GBP"
    best_rooms_for_panel = []

    try:
        priced = [r for r in rooms_with_availability if r.get("pricing")]
        if priced:
            # Find cheapest room available
            priced.sort(key=lambda r: r["pricing"]["total"] or 0)
            cheapest_room = priced[0]
            
            # The total is the price of 1 room * number of rooms needed
            total = (cheapest_room["pricing"]["total"] or 0) * min_rooms_needed
            cheapest_total = total
            cheapest_per_night = (cheapest_room["pricing"]["per_night"] or 0) * min_rooms_needed
            sidebar_currency = cheapest_room["pricing"]["currency"]

            # Add the required number of rooms to the sidebar list
            for i in range(min_rooms_needed):
                best_rooms_for_panel.append({
                    "room": cheapest_room["room"], 
                    "total": cheapest_room["pricing"]["total"], 
                    "per_night": cheapest_room["pricing"]["per_night"]
                })
    except Exception as e:
        current_app.logger.error(f"Sidebar calc failed: {e}")

    avg_rating, review_count = _avg_rating(hotel.id)
    related_raw = list(db.session.scalars(select(Hotel).where(Hotel.destination_id == hotel.destination_id, Hotel.id != hotel.id, Hotel.is_active.is_(True)).order_by(Hotel.stars.desc(), Hotel.id).limit(3)))
    
    # Compute cheapest room price for each related hotel
    related = []
    for rel_h in related_raw:
        cheapest = db.session.scalar(
            select(func.min(Room.base_price_per_night))
            .where(Room.hotel_id == rel_h.id)
            .where(Room.is_active.is_(True))
            .where(Room.base_price_per_night.is_not(None))
            .where(Room.base_price_per_night > 0)
        )
        rel_h.min_room_price = float(cheapest) if cheapest else None
        related.append(rel_h)
    inclusions = list(db.session.scalars(select(HotelInclusion).where(HotelInclusion.hotel_id == hotel.id).order_by(HotelInclusion.sort_order, HotelInclusion.id)))
    exclusions = list(db.session.scalars(select(HotelExclusion).where(HotelExclusion.hotel_id == hotel.id).order_by(HotelExclusion.sort_order, HotelExclusion.id)))
    faqs = list(db.session.scalars(select(HotelFAQ).where(HotelFAQ.hotel_id == hotel.id).order_by(HotelFAQ.sort_order, HotelFAQ.id)))

    reviews = []
    user_has_reviewed = False
    try:
        from flask_login import current_user
        from mongo.reviews import list_reviews_for_product, has_reviewed
        reviews = list_reviews_for_product(product_type="hotel", product_id=hotel.id, limit=20)
        if current_user.is_authenticated:
            user_has_reviewed = has_reviewed(user_id=current_user.id, product_type="hotel", product_id=hotel.id)
    except Exception: pass

    return render_template(
        "public/hotel_detail.html", inclusions=inclusions, exclusions=exclusions, faqs=faqs,
        cheapest_total=cheapest_total, cheapest_per_night=cheapest_per_night, sidebar_currency=sidebar_currency,
        nights=nights, adults=adults, children=children, infants=infants, child_ages=child_ages, best_grouping=best_grouping,
        best_rooms_for_panel=best_rooms_for_panel, min_rooms_needed=min_rooms_needed,
        reviews=reviews, user_has_reviewed=user_has_reviewed, hotel=hotel, destination=destination, facilities=facilities,
        images=images, rooms_with_availability=rooms_with_availability, check_in=check_in, check_out=check_out,
        avg_rating=avg_rating, review_count=review_count, related=related,
    )