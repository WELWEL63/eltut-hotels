"""
blueprints/admin/hotel_admin.py
───────────────────────────────
Admin CRUD for hotels and their rooms.

ROUTES
    GET      /admin/hotels                          list
    GET/POST /admin/hotels/new                      create
    GET/POST /admin/hotels/<int:id>/edit            edit + rooms inline
    POST     /admin/hotels/<int:id>/toggle          flip is_active
    POST     /admin/hotels/<int:id>/delete          delete (guarded)
    POST     /admin/hotels/<int:id>/rooms/new       add a room
    GET/POST /admin/rooms/<int:id>/edit             edit a room
    POST     /admin/rooms/<int:id>/delete           delete a room (guarded)

DESIGN NOTES
    - Rooms are managed inline from the hotel edit page.
    - Deleting a hotel refuses if any Package.hotel_id, Room, or
      BookingItem references it. Deactivate instead.
    - Deleting a room refuses if any Package.room_id or BookingItem
      references it.
    - Every write is logged to Mongo activity_logs (best-effort).
"""

from __future__ import annotations

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy import func, select

from blueprints.admin import admin_bp, admin_required
from extensions import db
from models import (
    BookingItem,
    Destination,
    Hotel,
    HotelExclusion,
    HotelFAQ,
    HotelImage,
    HotelInclusion,
    HotelTip,
    Package,
    PRODUCT_TYPE_HOTEL,
    Room,
    RoomRate,
    VALID_ROOM_MEAL_PLANS,
)


# ─── Logging ───────────────────────────────────────────────────────
def _log(action: str, entity_type: str, entity_id, old=None, new=None):
    try:
        from mongo.logs import log_action
        log_action(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=current_user.id,
            user_role="admin",
            old_value=old,
            new_value=new,
            ip=request.remote_addr,
        )
    except Exception as exc:
        current_app.logger.debug("log skipped: %s", exc)


# ─── Hotel list ────────────────────────────────────────────────────
@admin_bp.route("/hotels")
@admin_required
def hotel_list():
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 25
    q = (request.args.get("q") or "").strip()
    stars_raw = (request.args.get("stars") or "").strip()
    status = (request.args.get("status") or "").strip().lower()

    stars = None
    if stars_raw:
        try:
            n = int(stars_raw)
            if 1 <= n <= 5:
                stars = n
        except ValueError:
            pass

    stmt = select(Hotel)
    if q:
        stmt = stmt.where(Hotel.name.ilike(f"%{q}%"))
    if stars:
        stmt = stmt.where(Hotel.stars == stars)
    if status == "active":
        stmt = stmt.where(Hotel.is_active.is_(True))
    elif status == "inactive":
        stmt = stmt.where(Hotel.is_active.is_(False))
    stmt = stmt.order_by(Hotel.id.desc())

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)

    rows = list(db.session.scalars(
        stmt.limit(per_page).offset((page - 1) * per_page)
    ))

    return render_template(
        "admin/hotel_list.html",
        items=rows,
        total=total,
        page=page,
        total_pages=total_pages,
        q=q,
        stars=stars,
        status=status,
    )


# ─── Hotel form helpers ────────────────────────────────────────────
def _apply_form_to_hotel(hotel: Hotel):
    f = request.form
    hotel.name = (f.get("name") or "").strip() or hotel.name
    hotel.slug = Hotel._generate_unique_slug(hotel.name, db.session)

    try:
        hotel.stars = max(1, min(5, int(f.get("stars") or 3)))
    except ValueError:
        hotel.stars = 3

    try:
        hotel.destination_id = int(f.get("destination_id") or 0)
    except ValueError:
        pass

    hotel.address = (f.get("address") or "").strip() or None
    hotel.description = (f.get("description") or "").strip() or None
    hotel.check_in_time = (f.get("check_in_time") or "").strip() or None
    hotel.check_out_time = (f.get("check_out_time") or "").strip() or None
    try:
        hotel.total_capacity = max(1, int(f.get("total_capacity") or 1))
    except ValueError:
        hotel.total_capacity = 1
    hotel.is_active = bool(f.get("is_active"))

    # Detail-page content (details upgrade) — all optional free text.
    # Empty string coerces to None so templates can hide empty sections.
    hotel.useful_tips = (f.get("useful_tips") or "").strip() or None
    hotel.house_rules = (f.get("house_rules") or "").strip() or None
    hotel.check_in_details = (f.get("check_in_details") or "").strip() or None
    hotel.cancellation_policy = (f.get("cancellation_policy") or "").strip() or None
    hotel.neighborhood_info = (f.get("neighborhood_info") or "").strip() or None
    hotel.google_maps_url = (f.get("google_maps_url") or "").strip() or None


# ─── Hotel create / edit ───────────────────────────────────────────
@admin_bp.route("/hotels/new", methods=["GET", "POST"])
@admin_required
def hotel_new():
    destinations = list(db.session.scalars(
        select(Destination).order_by(Destination.name)
    ))

    if request.method == "POST":
        try:
            dest_id = int(request.form.get("destination_id") or 0)
        except ValueError:
            dest_id = 0
        if not dest_id:
            flash("Please select a destination.", "danger")
            return render_template(
                "admin/hotel_form.html", hotel=None, destinations=destinations,
            )

        hotel = Hotel(
            name=(request.form.get("name") or "").strip() or "New hotel",
            destination_id=dest_id,
        )
        _apply_form_to_hotel(hotel)
        db.session.add(hotel)
        db.session.flush()
        db.session.commit()
        _log("create", "hotel", hotel.id, new=hotel.name)
        flash(f"Hotel '{hotel.name}' created.", "success")
        return redirect(url_for("admin.hotel_edit", hotel_id=hotel.id))

    return render_template(
        "admin/hotel_form.html", hotel=None, destinations=destinations,
    )


@admin_bp.route("/hotels/<int:hotel_id>/edit", methods=["GET", "POST"])
@admin_required
def hotel_edit(hotel_id: int):
    hotel = db.session.get(Hotel, hotel_id)
    if hotel is None:
        abort(404)

    if request.method == "POST":
        old = hotel.name
        _apply_form_to_hotel(hotel)
        db.session.commit()
        _log("update", "hotel", hotel.id, old=old, new=hotel.name)
        flash("Hotel updated.", "success")
        return redirect(url_for("admin.hotel_edit", hotel_id=hotel.id))

    destinations = list(db.session.scalars(
        select(Destination).order_by(Destination.name)
    ))
    rooms = list(db.session.scalars(
        select(Room)
        .where(Room.hotel_id == hotel.id)
        .order_by(Room.base_price_per_night)
    ))
    images = list(db.session.scalars(
        select(HotelImage)
        .where(HotelImage.hotel_id == hotel.id)
        .order_by(HotelImage.sort_order)
    ))

    # Child rows for the detail-page editor
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
    tips = list(db.session.scalars(
        select(HotelTip)
        .where(HotelTip.hotel_id == hotel.id)
        .order_by(HotelTip.sort_order, HotelTip.id)
    ))

    return render_template(
        "admin/hotel_form.html",
        hotel=hotel,
        destinations=destinations,
        rooms=rooms,
        images=images,
        inclusions=inclusions,
        exclusions=exclusions,
        faqs=faqs,
        tips=tips,
        meal_plans=VALID_ROOM_MEAL_PLANS,
    )


# ─── Hotel toggle / delete ─────────────────────────────────────────
@admin_bp.route("/hotels/<int:hotel_id>/toggle", methods=["POST"])
@admin_required
def hotel_toggle(hotel_id: int):
    hotel = db.session.get(Hotel, hotel_id)
    if hotel is None:
        abort(404)
    hotel.is_active = not hotel.is_active
    db.session.commit()
    _log("toggle_active", "hotel", hotel.id, new=hotel.is_active)
    flash(f"Hotel {'activated' if hotel.is_active else 'deactivated'}.", "success")
    return redirect(url_for("admin.hotel_list"))


@admin_bp.route("/hotels/<int:hotel_id>/delete", methods=["POST"])
@admin_required
def hotel_delete(hotel_id: int):
    hotel = db.session.get(Hotel, hotel_id)
    if hotel is None:
        abort(404)

    # Guard: any packages reference this hotel?
    pkg_refs = int(db.session.scalar(
        select(func.count(Package.id)).where(Package.hotel_id == hotel.id)
    ) or 0)
    if pkg_refs:
        flash(
            f"Cannot delete — {pkg_refs} package(s) use this hotel. "
            "Deactivate it instead.",
            "danger",
        )
        return redirect(url_for("admin.hotel_list"))

    # Guard: any bookings reference one of its rooms?
    room_ids = [r.id for r in db.session.scalars(
        select(Room).where(Room.hotel_id == hotel.id)
    )]
    if room_ids:
        booking_refs = int(db.session.scalar(
            select(func.count(BookingItem.id))
            .where(
                BookingItem.product_type == PRODUCT_TYPE_HOTEL,
                BookingItem.product_id.in_(room_ids),
            )
        ) or 0)
        if booking_refs:
            flash(
                f"Cannot delete — {booking_refs} booking(s) use rooms of "
                "this hotel. Deactivate it instead.",
                "danger",
            )
            return redirect(url_for("admin.hotel_list"))

    name = hotel.name
    db.session.delete(hotel)
    db.session.commit()
    _log("delete", "hotel", hotel_id, old=name)
    flash(f"Hotel '{name}' deleted.", "success")
    return redirect(url_for("admin.hotel_list"))


# ─── Rooms ─────────────────────────────────────────────────────────
def _apply_form_to_room(room: Room):
    f = request.form
    room.type = (f.get("type") or "").strip() or room.type
    meal = (f.get("meal_plan") or "").strip().lower()
    room.meal_plan = meal if meal in VALID_ROOM_MEAL_PLANS else "room_only"
    try:
        room.max_occupancy = max(1, int(f.get("max_occupancy") or 1))
    except ValueError:
        room.max_occupancy = 1
    try:
        room.capacity = max(0, int(f.get("capacity") or 0))
    except ValueError:
        room.capacity = 0
    try:
        room.base_price_per_night = float(f.get("base_price_per_night") or 0)
    except ValueError:
        room.base_price_per_night = 0
    room.description = (f.get("description") or "").strip() or None
    room.is_active = bool(f.get("is_active"))


@admin_bp.route("/hotels/<int:hotel_id>/rooms/new", methods=["POST"])
@admin_required
def room_new(hotel_id: int):
    hotel = db.session.get(Hotel, hotel_id)
    if hotel is None:
        abort(404)

    room = Room(
        hotel_id=hotel.id,
        type=(request.form.get("type") or "").strip() or "New room",
    )
    _apply_form_to_room(room)
    db.session.add(room)
    db.session.commit()
    _log("create", "room", room.id, new=room.type)
    flash("Room added.", "success")
    return redirect(url_for("admin.hotel_edit", hotel_id=hotel.id))


@admin_bp.route("/rooms/<int:room_id>/edit", methods=["GET", "POST"])
@admin_required
def room_edit(room_id: int):
    room = db.session.get(Room, room_id)
    if room is None:
        abort(404)

    if request.method == "POST":
        _apply_form_to_room(room)
        db.session.commit()
        _log("update", "room", room.id, new=room.type)
        flash("Room updated.", "success")
        return redirect(url_for("admin.hotel_edit", hotel_id=room.hotel_id))

    hotel = db.session.get(Hotel, room.hotel_id)
    rates = list(db.session.scalars(
        select(RoomRate).where(RoomRate.room_id == room.id)
        .order_by(RoomRate.valid_from.nullslast())
    ))
    return render_template(
        "admin/room_form.html",
        room=room,
        hotel=hotel,
        rates=rates,
        meal_plans=VALID_ROOM_MEAL_PLANS,
    )


@admin_bp.route("/rooms/<int:room_id>/delete", methods=["POST"])
@admin_required
def room_delete(room_id: int):
    room = db.session.get(Room, room_id)
    if room is None:
        abort(404)

    # Guard: any packages reference this room?
    pkg_refs = int(db.session.scalar(
        select(func.count(Package.id)).where(Package.room_id == room.id)
    ) or 0)
    if pkg_refs:
        flash(
            f"Cannot delete — {pkg_refs} package(s) use this room.",
            "danger",
        )
        return redirect(url_for("admin.hotel_edit", hotel_id=room.hotel_id))

    # Guard: any bookings reference this room?
    booking_refs = int(db.session.scalar(
        select(func.count(BookingItem.id))
        .where(
            BookingItem.product_type == PRODUCT_TYPE_HOTEL,
            BookingItem.product_id == room.id,
        )
    ) or 0)
    if booking_refs:
        flash(
            f"Cannot delete — {booking_refs} booking(s) use this room.",
            "danger",
        )
        return redirect(url_for("admin.hotel_edit", hotel_id=room.hotel_id))

    hotel_id = room.hotel_id
    db.session.delete(room)
    db.session.commit()
    _log("delete", "room", room_id)
    flash("Room deleted.", "success")
    return redirect(url_for("admin.hotel_edit", hotel_id=hotel_id))


# ─── Room seasonal rates (Step 11.5) ───────────────────────────────
@admin_bp.route("/rooms/<int:room_id>/rates/new", methods=["POST"])
@admin_required
def room_rate_new(room_id: int):
    """Add a seasonal rate window for a room."""
    room = db.session.get(Room, room_id)
    if room is None:
        abort(404)

    def _float(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    def _date(v):
        v = (v or "").strip()
        if not v:
            return None
        from datetime import datetime as _dt
        try:
            return _dt.strptime(v, "%Y-%m-%d").date()
        except ValueError:
            return None

    rate = RoomRate(
        room_id=room.id,
        adult_price=_float(request.form.get("adult_price")),
        child_price=_float(request.form.get("child_price")),
        currency=(request.form.get("currency") or "EUR").upper(),
        valid_from=_date(request.form.get("valid_from")),
        valid_to=_date(request.form.get("valid_to")),
    )
    db.session.add(rate)
    db.session.commit()
    _log("create", "room_rate", rate.id, new=f"{rate.valid_from}->{rate.valid_to}")
    flash("Rate added.", "success")
    return redirect(url_for("admin.room_edit", room_id=room.id))


@admin_bp.route("/room-rates/<int:rate_id>/delete", methods=["POST"])
@admin_required
def room_rate_delete(rate_id: int):
    """Delete a seasonal rate window."""
    rate = db.session.get(RoomRate, rate_id)
    if rate is None:
        abort(404)
    room_id = rate.room_id
    db.session.delete(rate)
    db.session.commit()
    _log("delete", "room_rate", rate_id)
    flash("Rate deleted.", "success")
    return redirect(url_for("admin.room_edit", room_id=room_id))


# --- Hotel child rows: inclusions / exclusions / FAQs / tips -----------
# Generic helper avoids 16 nearly-identical routes.
_CHILD_TYPES: dict[str, dict] = {
    "inclusions": {"model": HotelInclusion, "field": "item", "label": "Inclusion"},
    "exclusions": {"model": HotelExclusion, "field": "item", "label": "Exclusion"},
    "faqs":       {"model": HotelFAQ,       "field": "question", "label": "FAQ"},
    "tips":       {"model": HotelTip,       "field": "tip", "label": "Tip"},
}


def _next_child_sort_order(Model, hotel_id: int) -> int:
    """Return max(sort_order) + 1 for a hotel child table."""
    current_max = db.session.scalar(
        select(func.coalesce(func.max(Model.sort_order), 0))
        .where(Model.hotel_id == hotel_id)
    ) or 0
    return int(current_max) + 1


@admin_bp.route("/hotels/<int:hotel_id>/children/<child_type>/new", methods=["POST"])
@admin_required
def hotel_child_new(hotel_id: int, child_type: str):
    """Add one row to a hotel child table (inclusion/exclusion/FAQ/tip)."""
    cfg = _CHILD_TYPES.get(child_type)
    if cfg is None:
        abort(404)
    hotel = db.session.get(Hotel, hotel_id)
    if hotel is None:
        abort(404)

    Model = cfg["model"]
    field = cfg["field"]

    if child_type == "faqs":
        question = (request.form.get("question") or "").strip()
        answer = (request.form.get("answer") or "").strip() or None
        if not question:
            flash("Question is required.", "danger")
            return redirect(url_for("admin.hotel_edit", hotel_id=hotel.id))
        row = Model(
            hotel_id=hotel.id,
            question=question,
            answer=answer,
            sort_order=_next_child_sort_order(Model, hotel.id),
        )
    else:
        value = (request.form.get(field) or "").strip()
        if not value:
            flash(f"{cfg['label']} text is required.", "danger")
            return redirect(url_for("admin.hotel_edit", hotel_id=hotel.id))
        row = Model(
            hotel_id=hotel.id,
            **{field: value},
            sort_order=_next_child_sort_order(Model, hotel.id),
        )

    db.session.add(row)
    db.session.commit()
    _log("create", child_type, row.id, new=hotel.id)
    flash(f"{cfg['label']} added.", "success")
    return redirect(url_for("admin.hotel_edit", hotel_id=hotel.id))


@admin_bp.route(
    "/hotels/<int:hotel_id>/children/<child_type>/<int:row_id>/delete",
    methods=["POST"],
)
@admin_required
def hotel_child_delete(hotel_id: int, child_type: str, row_id: int):
    """Delete one row from a hotel child table."""
    cfg = _CHILD_TYPES.get(child_type)
    if cfg is None:
        abort(404)
    hotel = db.session.get(Hotel, hotel_id)
    if hotel is None:
        abort(404)

    Model = cfg["model"]
    row = db.session.get(Model, row_id)
    if row is None or getattr(row, "hotel_id", None) != hotel.id:
        abort(404)

    db.session.delete(row)
    db.session.commit()
    _log("delete", child_type, row_id)
    flash(f"{cfg['label']} deleted.", "success")
    return redirect(url_for("admin.hotel_edit", hotel_id=hotel.id))
