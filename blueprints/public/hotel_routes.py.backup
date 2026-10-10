"""
blueprints/public/hotel_routes.py
─────────────────────────────────
Hotel listing and detail pages.

ROUTES
    GET /hotels              list with filters, sort, pagination
    GET /hotels/<slug>       detail page with rooms + facilities

FILTERS (query parameters, all optional)
    destination  slug of a destination
    stars        integer 1..5
    meal_plan    one of VALID_ROOM_MEAL_PLANS
    q            free-text search on hotel name
    sort         newest (default) | name | stars_desc | price_asc | price_desc
    page         1-based page number

DESIGN NOTES
    - Reads only. No writes.
    - "from price" on a hotel = cheapest room's base_price_per_night.
    - Room availability on the detail page uses default dates
      (today -> today+7) when the visitor hasn't entered dates yet.
    - Mongo rating lookup is best-effort (returns None on Mongo down).
"""

from __future__ import annotations

from datetime import date, timedelta

from flask import abort, current_app, render_template, request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from blueprints.public import public_bp
from extensions import db
from models import (
    Destination,
    Hotel,
    HotelFacility,
    HotelImage,
    Room,
    RoomImage,
    VALID_ROOM_MEAL_PLANS,

    HotelExclusion,
    HotelFAQ,
    HotelInclusion,
    HotelTip,
)


# ─── Helpers ───────────────────────────────────────────────────────
def _int_arg(name: str, default: int, lo: int, hi: int) -> int:
    raw = request.args.get(name, "").strip()
    try:
        return max(lo, min(hi, int(raw)))
    except (TypeError, ValueError):
        return default


def _cheapest_room_price(hotel_id: int) -> tuple[float | None, str | None]:
    """Return (min base_price_per_night, currency) for a hotel, or (None, None)."""
    row = db.session.scalar(
        select(func.min(Room.base_price_per_night))
        .where(Room.hotel_id == hotel_id, Room.is_active.is_(True))
    )
    if row is None:
        return (None, None)
    try:
        return (float(row), "EUR")  # rooms store EUR in the seeded CSV
    except Exception:  # noqa: BLE001
        return (None, None)


def _avg_rating(hotel_id: int) -> tuple[float | None, int]:
    try:
        from mongo.reviews import rating_summary  # noqa: PLC0415
        summary = rating_summary("hotel", hotel_id)
        return (summary.get("average"), int(summary.get("count") or 0))
    except Exception:  # noqa: BLE001
        return (None, 0)


# ─── List ──────────────────────────────────────────────────────────
@public_bp.route("/hotels")
def hotel_list():
    """Browse hotels with filters, sorting, and pagination."""
    page = _int_arg("page", 1, 1, 10_000)
    per_page = int(current_app.config.get("ITEMS_PER_PAGE", 12) or 12)
    per_page = max(6, min(per_page, 48))

    destination_slug = (request.args.get("destination") or "").strip().lower()
    stars_raw = request.args.get("stars", "").strip()
    meal_plan = (request.args.get("meal_plan") or "").strip().lower()
    query_text = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "newest").strip().lower()

    stars: int | None = None
    if stars_raw:
        try:
            stars = int(stars_raw)
            if stars < 1 or stars > 5:
                stars = None
        except ValueError:
            stars = None

    stmt = (
        select(Hotel)
        .options(joinedload(Hotel.images))
        .where(Hotel.is_active.is_(True))
    )

    selected_destination: Destination | None = None
    if destination_slug:
        selected_destination = db.session.scalar(
            select(Destination).where(Destination.slug == destination_slug)
        )
        if selected_destination is not None:
            stmt = stmt.where(Hotel.destination_id == selected_destination.id)

    if stars is not None:
        stmt = stmt.where(Hotel.stars == stars)

    if meal_plan and meal_plan in VALID_ROOM_MEAL_PLANS:
        # Only hotels that have at least one room with this meal plan
        stmt = stmt.where(
            select(Room.id)
            .where(
                Room.hotel_id == Hotel.id,
                Room.meal_plan == meal_plan,
                Room.is_active.is_(True),
            )
            .exists()
        )

    if query_text:
        stmt = stmt.where(Hotel.name.ilike(f"%{query_text}%"))

    # Sorting
    if sort == "name":
        stmt = stmt.order_by(Hotel.name.asc())
    elif sort == "stars_desc":
        stmt = stmt.order_by(Hotel.stars.desc(), Hotel.name.asc())
    elif sort == "price_asc":
        stmt = stmt.order_by(
            select(func.min(Room.base_price_per_night))
            .where(Room.hotel_id == Hotel.id)
            .scalar_subquery()
            .asc()
        )
    elif sort == "price_desc":
        stmt = stmt.order_by(
            select(func.min(Room.base_price_per_night))
            .where(Room.hotel_id == Hotel.id)
            .scalar_subquery()
            .desc()
        )
    else:
        stmt = stmt.order_by(Hotel.id.desc())

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    rows = list(db.session.scalars(stmt.limit(per_page).offset(offset)).unique())

    items: list[dict] = []
    for h in rows:
        price, currency = _cheapest_room_price(h.id)
        first_image = h.images[0].url if h.images else None
        items.append({
            "hotel": h,
            "price": price,
            "currency": currency,
            "image_url": first_image,
        })

    destinations = list(db.session.scalars(
        select(Destination).order_by(Destination.name)
    ))

    return render_template(
        "public/hotel_list.html",
        items=items,
        total=total,
        page=page,
        total_pages=total_pages,
        destinations=destinations,
        meal_plans=VALID_ROOM_MEAL_PLANS,
        selected_destination=selected_destination,
        selected_stars=stars,
        selected_meal_plan=meal_plan,
        query_text=query_text,
        sort=sort,
    )


# ─── Detail ────────────────────────────────────────────────────────
@public_bp.route("/hotels/<slug>")
def hotel_detail(slug: str):
    """Single hotel detail page with rooms and facilities."""
    hotel = db.session.scalars(
        select(Hotel)
        .options(joinedload(Hotel.images))
        .where(Hotel.slug == slug, Hotel.is_active.is_(True))
    ).unique().first()
    if hotel is None:
        abort(404)

    destination = db.session.get(Destination, hotel.destination_id)

    facilities = list(db.session.scalars(
        select(HotelFacility)
        .where(HotelFacility.hotel_id == hotel.id)
        .order_by(HotelFacility.name)
    ))

    images = list(db.session.scalars(
        select(HotelImage)
        .where(HotelImage.hotel_id == hotel.id)
        .order_by(HotelImage.sort_order)
    ))

    rooms = list(db.session.scalars(
        select(Room)
        .where(Room.hotel_id == hotel.id, Room.is_active.is_(True))
        .order_by(Room.base_price_per_night)
    ))

    # Room availability + seasonal rates for default dates (today -> today+7)
    from models import RoomRate  # noqa: PLC0415

    check_in = date.today()
    check_out = check_in + timedelta(days=7)
    rooms_with_availability: list[dict] = []
    try:
        from services.availability_service import hotel_room_availability  # noqa: PLC0415
        for room in rooms:
            try:
                remaining = hotel_room_availability(room.id, check_in, check_out)
            except Exception:  # noqa: BLE001
                remaining = None

            # Attach the seasonal rate windows for this room (up to 12,
            # soonest first). These populate the "Rates for this room"
            # sub-table on the detail page.
            rate_rows = list(db.session.scalars(
                __import__("sqlalchemy").select(RoomRate)
                .where(RoomRate.room_id == room.id)
                .order_by(RoomRate.valid_from.asc().nullsfirst())
                .limit(12)
            ))

            rooms_with_availability.append({
                "room": room,
                "remaining": remaining,
                "rates": rate_rows,
            })
    except Exception:  # noqa: BLE001
        rooms_with_availability = []
        for r in rooms:
            rate_rows = list(db.session.scalars(
                __import__("sqlalchemy").select(RoomRate)
                .where(RoomRate.room_id == r.id)
                .order_by(RoomRate.valid_from.asc().nullsfirst())
                .limit(12)
            ))
            rooms_with_availability.append({
                "room": r,
                "remaining": None,
                "rates": rate_rows,
            })

    avg_rating, review_count = _avg_rating(hotel.id)

    related = list(db.session.scalars(
        select(Hotel)
        .where(
            Hotel.destination_id == hotel.destination_id,
            Hotel.id != hotel.id,
            Hotel.is_active.is_(True),
        )
        .order_by(Hotel.stars.desc(), Hotel.id)
        .limit(3)
    ))

    # New detail-page content (Phase 6.7)
    inclusions = list(db.session.scalars(
        select(HotelInclusion)
        .where(HotelInclusion.hotel_id == hotel.id)
        .order_by(HotelInclusion.sort_order, HotelInclusion.id)
    ))
    exclusions = list(db.session.scalars(
        select(HotelExclusion)
        .where(HotelExclusion.hotel_id == hotel.id)
        .order_by(HotelExclusion.sort_order, HotelExclusion.id)
    ))
    faqs = list(db.session.scalars(
        select(HotelFAQ)
        .where(HotelFAQ.hotel_id == hotel.id)
        .order_by(HotelFAQ.sort_order, HotelFAQ.id)
    ))

    # Cheapest base room price for the "From €X / night" sidebar
    min_price = None
    try:
        min_price = db.session.scalar(
            select(func.min(Room.base_price_per_night))
            .where(Room.hotel_id == hotel.id, Room.is_active.is_(True))
        )
    except Exception:
        min_price = None

    # ─── Reviews (from MongoDB, best-effort) ──────────────────────
    reviews: list[dict] = []
    user_has_reviewed = False
    try:
        from flask_login import current_user  # noqa: PLC0415
        from mongo.reviews import (
            list_reviews_for_product,  # noqa: PLC0415
            has_reviewed,  # noqa: PLC0415
        )
        reviews = list_reviews_for_product(
            product_type="hotel",
            product_id=hotel.id,
            limit=20,
        )
        if current_user.is_authenticated:
            user_has_reviewed = has_reviewed(
                user_id=current_user.id,
                product_type="hotel",
                product_id=hotel.id,
            )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.debug("hotel reviews unavailable: %s", exc)

    return render_template(
        "public/hotel_detail.html",
        inclusions=inclusions,
        exclusions=exclusions,
        faqs=faqs,
        min_price=min_price,
        reviews=reviews,
        user_has_reviewed=user_has_reviewed,
        hotel=hotel,
        destination=destination,
        facilities=facilities,
        images=images,
        rooms_with_availability=rooms_with_availability,
        check_in=check_in,
        check_out=check_out,
        avg_rating=avg_rating,
        review_count=review_count,
        related=related,
    )
