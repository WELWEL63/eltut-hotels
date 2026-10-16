"""
blueprints/admin/package_admin.py
─────────────────────────────────
Admin CRUD for packages and their inline children.
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
    Airline,
    BookingItem,
    Destination,
    Flight,
    Hotel,
    Package,
    PackageExclusion,
    PackageFAQ,
    PackageInclusion,
    PackageItinerary,
    PackagePrice,
    PackageTip,
    Room,
    PRODUCT_TYPE_PACKAGE,
    VALID_PACKAGE_TYPES,
    PackageOption,
)


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


@admin_bp.route("/packages")
@admin_required
def package_list():
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 25
    q = (request.args.get("q") or "").strip()
    ptype = (request.args.get("package_type") or "").strip().lower()
    status = (request.args.get("status") or "").strip().lower()

    stmt = select(Package)
    if q:
        stmt = stmt.where(Package.name.ilike(f"%{q}%"))
    if ptype and ptype in VALID_PACKAGE_TYPES:
        stmt = stmt.where(Package.package_type == ptype)
    if status == "active":
        stmt = stmt.where(Package.is_active.is_(True))
    elif status == "inactive":
        stmt = stmt.where(Package.is_active.is_(False))
    stmt = stmt.order_by(Package.id.desc())

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)

    rows = list(db.session.scalars(
        stmt.limit(per_page).offset((page - 1) * per_page)
    ))

    return render_template(
        "admin/package_list.html",
        items=rows,
        total=total,
        page=page,
        total_pages=total_pages,
        q=q,
        package_type=ptype,
        status=status,
        package_types=VALID_PACKAGE_TYPES,
    )


def _form_choices():
    destinations = list(db.session.scalars(
        select(Destination).order_by(Destination.name)
    ))
    hotels = list(db.session.scalars(
        select(Hotel).where(Hotel.is_active.is_(True)).order_by(Hotel.name)
    ))
    return destinations, hotels


def _rooms_for_hotel(hotel_id: int):
    return list(db.session.scalars(
        select(Room).where(Room.hotel_id == hotel_id).order_by(Room.type)
    ))


def _apply_form_to_package(package: Package):
    f = request.form
    package.name = (f.get("name") or "").strip() or package.name
    package.slug = Package._generate_unique_slug(package.name, db.session)

    ptype = (f.get("package_type") or "").strip().lower()
    package.package_type = ptype if ptype in VALID_PACKAGE_TYPES else "holiday"

    try:
        package.destination_id = int(f.get("destination_id") or 0)
        package.hotel_id = int(f.get("hotel_id") or 0)
        package.room_id = int(f.get("room_id") or 0)
    except ValueError:
        pass

    package.description = (f.get("description") or "").strip() or None
    try:
        package.duration_nights = max(1, int(f.get("duration_nights") or 1))
    except ValueError:
        package.duration_nights = 1
    try:
        package.capacity = max(1, int(f.get("capacity") or 1))
    except ValueError:
        package.capacity = 1

    def _maybe_int(key):
        raw = (f.get(key) or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    package.min_age = _maybe_int("min_age")
    package.max_age = _maybe_int("max_age")
    package.cancellation_policy = (f.get("cancellation_policy") or "").strip() or None
    package.booking_terms = (f.get("booking_terms") or "").strip() or None
    package.is_active = bool(f.get("is_active"))

    # Detail-page content (details upgrade) — all optional free text.
    package.useful_tips = (f.get("useful_tips") or "").strip() or None
    package.what_to_bring = (f.get("what_to_bring") or "").strip() or None
    package.things_to_know = (f.get("things_to_know") or "").strip() or None
    package.google_maps_url = (f.get("google_maps_url") or "").strip() or None


@admin_bp.route("/packages/new", methods=["GET", "POST"])
@admin_required
def package_new():
    destinations, hotels = _form_choices()

    if request.method == "POST":
        try:
            dest_id = int(request.form.get("destination_id") or 0)
            hotel_id = int(request.form.get("hotel_id") or 0)
            room_id = int(request.form.get("room_id") or 0)
        except ValueError:
            dest_id = hotel_id = room_id = 0
        if not dest_id or not hotel_id or not room_id:
            flash("Destination, hotel, and room are required.", "danger")
            return render_template(
                "admin/package_form.html",
                package=None,
                destinations=destinations,
                hotels=hotels,
                rooms=_rooms_for_hotel(hotel_id) if hotel_id else [],
                package_types=VALID_PACKAGE_TYPES,
            )

        code = (request.form.get("code") or "").strip()
        if not code:
            next_id = (db.session.scalar(select(func.max(Package.id))) or 0) + 1
            code = f"PKG-{next_id:04d}"

        existing = db.session.scalar(select(Package).where(Package.code == code))
        if existing:
            flash(f"A package with code {code} already exists.", "danger")
            return render_template(
                "admin/package_form.html",
                package=None,
                destinations=destinations,
                hotels=hotels,
                rooms=_rooms_for_hotel(hotel_id) if hotel_id else [],
                package_types=VALID_PACKAGE_TYPES,
            )

        package = Package(
            code=code,
            name=(request.form.get("name") or "").strip() or "New package",
            destination_id=dest_id,
            hotel_id=hotel_id,
            room_id=room_id,
        )
        _apply_form_to_package(package)
        db.session.add(package)
        db.session.flush()
        db.session.commit()
        _log("create", "package", package.id, new=package.name)
        flash(f"Package '{package.name}' created.", "success")
        return redirect(url_for("admin.package_edit", package_id=package.id))

    return render_template(
        "admin/package_form.html",
        package=None,
        destinations=destinations,
        hotels=hotels,
        rooms=[],
        package_types=VALID_PACKAGE_TYPES,
    )


@admin_bp.route("/packages/<int:package_id>/edit", methods=["GET", "POST"])
@admin_required
def package_edit(package_id: int):
    package = db.session.get(Package, package_id)
    if package is None:
        abort(404)

    if request.method == "POST":
        old = package.name
        _apply_form_to_package(package)
        db.session.commit()
        _log("update", "package", package.id, old=old, new=package.name)
        flash("Package updated.", "success")
        return redirect(url_for("admin.package_edit", package_id=package.id))

    destinations, hotels = _form_choices()
    rooms = _rooms_for_hotel(package.hotel_id) if package.hotel_id else []

    itineraries = list(db.session.scalars(
        select(PackageItinerary)
        .where(PackageItinerary.package_id == package.id)
        .order_by(PackageItinerary.day_number)
    ))
    inclusions = list(db.session.scalars(
        select(PackageInclusion)
        .where(PackageInclusion.package_id == package.id)
        .order_by(PackageInclusion.sort_order)
    ))
    exclusions = list(db.session.scalars(
        select(PackageExclusion)
        .where(PackageExclusion.package_id == package.id)
        .order_by(PackageExclusion.sort_order)
    ))
    prices = list(db.session.scalars(
        select(PackagePrice).where(PackagePrice.package_id == package.id)
    ))
    flights = list(db.session.scalars(
        select(Flight).where(Flight.package_id == package.id)
    ))

    faqs = list(db.session.scalars(
        select(PackageFAQ)
        .where(PackageFAQ.package_id == package.id)
        .order_by(PackageFAQ.sort_order, PackageFAQ.id)
    ))
    tips = list(db.session.scalars(
        select(PackageTip)
        .where(PackageTip.package_id == package.id)
        .order_by(PackageTip.sort_order, PackageTip.id)
    ))

    # Departure options (link flight + price + date)
    options = list(db.session.scalars(
        select(PackageOption)
        .where(PackageOption.package_id == package.id)
        .order_by(PackageOption.sort_order.asc(), PackageOption.id.asc())
    ))

    # Airlines list for the flight form dropdown
    airlines = list(db.session.scalars(
        select(Airline).where(Airline.is_active.is_(True)).order_by(Airline.name)
    ))

    return render_template(
        "admin/package_form.html",
        package=package,
        options=options,
        airlines=airlines,
        destinations=destinations,
        hotels=hotels,
        rooms=rooms,
        package_types=VALID_PACKAGE_TYPES,
        itineraries=itineraries,
        inclusions=inclusions,
        exclusions=exclusions,
        prices=prices,
        flights=flights,
        faqs=faqs,
        tips=tips,
    )


@admin_bp.route("/packages/<int:package_id>/toggle", methods=["POST"])
@admin_required
def package_toggle(package_id: int):
    package = db.session.get(Package, package_id)
    if package is None:
        abort(404)
    package.is_active = not package.is_active
    db.session.commit()
    _log("toggle_active", "package", package.id, new=package.is_active)
    flash(f"Package {'activated' if package.is_active else 'deactivated'}.", "success")
    return redirect(url_for("admin.package_list"))


@admin_bp.route("/packages/<int:package_id>/delete", methods=["POST"])
@admin_required
def package_delete(package_id: int):
    package = db.session.get(Package, package_id)
    if package is None:
        abort(404)

    refs = int(db.session.scalar(
        select(func.count(BookingItem.id))
        .where(
            BookingItem.product_type == PRODUCT_TYPE_PACKAGE,
            BookingItem.product_id == package.id,
        )
    ) or 0)
    if refs > 0:
        flash(
            f"Cannot delete — {refs} booking(s) reference this package. "
            "Deactivate it instead.",
            "danger",
        )
        return redirect(url_for("admin.package_list"))

    name = package.name
    db.session.delete(package)
    db.session.commit()
    _log("delete", "package", package_id, old=name)
    flash(f"Package '{name}' deleted.", "success")
    return redirect(url_for("admin.package_list"))


@admin_bp.route("/packages/<int:package_id>/itinerary/new", methods=["POST"])
@admin_required
def package_itinerary_new(package_id: int):
    package = db.session.get(Package, package_id)
    if package is None:
        abort(404)

    try:
        day = max(1, int(request.form.get("day_number") or 1))
    except ValueError:
        day = 1
    title = (request.form.get("title") or "").strip() or f"Day {day}"
    description = (request.form.get("description") or "").strip() or None

    existing = db.session.scalar(
        select(PackageItinerary).where(
            PackageItinerary.package_id == package.id,
            PackageItinerary.day_number == day,
        )
    )
    if existing:
        flash(f"Day {day} already exists for this package.", "warning")
        return redirect(url_for("admin.package_edit", package_id=package.id))

    db.session.add(PackageItinerary(
        package_id=package.id,
        day_number=day,
        title=title,
        description=description,
    ))
    db.session.commit()
    _log("create", "package_itinerary", package.id, new=f"day {day}")
    flash("Itinerary day added.", "success")
    return redirect(url_for("admin.package_edit", package_id=package.id))


@admin_bp.route("/itinerary/<int:itinerary_id>/delete", methods=["POST"])
@admin_required
def package_itinerary_delete(itinerary_id: int):
    row = db.session.get(PackageItinerary, itinerary_id)
    if row is None:
        abort(404)
    package_id = row.package_id
    db.session.delete(row)
    db.session.commit()
    _log("delete", "package_itinerary", itinerary_id)
    flash("Itinerary day deleted.", "success")
    return redirect(url_for("admin.package_edit", package_id=package_id))


@admin_bp.route("/packages/<int:package_id>/inclusions/new", methods=["POST"])
@admin_required
def package_inclusion_new(package_id: int):
    package = db.session.get(Package, package_id)
    if package is None:
        abort(404)
    item = (request.form.get("item") or "").strip()
    if not item:
        flash("Inclusion text is required.", "warning")
        return redirect(url_for("admin.package_edit", package_id=package.id))
    db.session.add(PackageInclusion(package_id=package.id, item=item))
    db.session.commit()
    _log("create", "package_inclusion", package.id, new=item)
    flash("Inclusion added.", "success")
    return redirect(url_for("admin.package_edit", package_id=package.id))


@admin_bp.route("/inclusions/<int:inclusion_id>/delete", methods=["POST"])
@admin_required
def package_inclusion_delete(inclusion_id: int):
    row = db.session.get(PackageInclusion, inclusion_id)
    if row is None:
        abort(404)
    package_id = row.package_id
    db.session.delete(row)
    db.session.commit()
    _log("delete", "package_inclusion", inclusion_id)
    flash("Inclusion deleted.", "success")
    return redirect(url_for("admin.package_edit", package_id=package_id))


@admin_bp.route("/packages/<int:package_id>/exclusions/new", methods=["POST"])
@admin_required
def package_exclusion_new(package_id: int):
    package = db.session.get(Package, package_id)
    if package is None:
        abort(404)
    item = (request.form.get("item") or "").strip()
    if not item:
        flash("Exclusion text is required.", "warning")
        return redirect(url_for("admin.package_edit", package_id=package.id))
    db.session.add(PackageExclusion(package_id=package.id, item=item))
    db.session.commit()
    _log("create", "package_exclusion", package.id, new=item)
    flash("Exclusion added.", "success")
    return redirect(url_for("admin.package_edit", package_id=package.id))


@admin_bp.route("/exclusions/<int:exclusion_id>/delete", methods=["POST"])
@admin_required
def package_exclusion_delete(exclusion_id: int):
    row = db.session.get(PackageExclusion, exclusion_id)
    if row is None:
        abort(404)
    package_id = row.package_id
    db.session.delete(row)
    db.session.commit()
    _log("delete", "package_exclusion", exclusion_id)
    flash("Exclusion deleted.", "success")
    return redirect(url_for("admin.package_edit", package_id=package_id))


# --- Package child rows: FAQs / tips -----------------------------------
# Generic helper so we don't need separate routes for each child type.
_CHILD_TYPES: dict[str, dict] = {
    "faqs": {"model": PackageFAQ, "field": "question", "label": "FAQ"},
    "tips": {"model": PackageTip, "field": "tip", "label": "Tip"},
}


def _next_child_sort_order(Model, package_id: int) -> int:
    """Return max(sort_order) + 1 for a package child table."""
    current_max = db.session.scalar(
        select(func.coalesce(func.max(Model.sort_order), 0))
        .where(Model.package_id == package_id)
    ) or 0
    return int(current_max) + 1


@admin_bp.route("/packages/<int:package_id>/children/<child_type>/new", methods=["POST"])
@admin_required
def package_child_new(package_id: int, child_type: str):
    """Add one row to a package child table (FAQ or tip)."""
    cfg = _CHILD_TYPES.get(child_type)
    if cfg is None:
        abort(404)
    package = db.session.get(Package, package_id)
    if package is None:
        abort(404)

    Model = cfg["model"]
    field = cfg["field"]

    if child_type == "faqs":
        question = (request.form.get("question") or "").strip()
        answer = (request.form.get("answer") or "").strip() or None
        if not question:
            flash("Question is required.", "danger")
            return redirect(url_for("admin.package_edit", package_id=package.id))
        row = Model(
            package_id=package.id,
            question=question,
            answer=answer,
            sort_order=_next_child_sort_order(Model, package.id),
        )
    else:
        value = (request.form.get(field) or "").strip()
        if not value:
            flash(f"{cfg['label']} text is required.", "danger")
            return redirect(url_for("admin.package_edit", package_id=package.id))
        row = Model(
            package_id=package.id,
            **{field: value},
            sort_order=_next_child_sort_order(Model, package.id),
        )

    db.session.add(row)
    db.session.commit()
    _log("create", child_type, row.id, new=package.id)
    flash(f"{cfg['label']} added.", "success")
    return redirect(url_for("admin.package_edit", package_id=package.id))


@admin_bp.route(
    "/packages/<int:package_id>/children/<child_type>/<int:row_id>/delete",
    methods=["POST"],
)
@admin_required
def package_child_delete(package_id: int, child_type: str, row_id: int):
    """Delete one row from a package child table."""
    cfg = _CHILD_TYPES.get(child_type)
    if cfg is None:
        abort(404)
    package = db.session.get(Package, package_id)
    if package is None:
        abort(404)

    Model = cfg["model"]
    row = db.session.get(Model, row_id)
    if row is None or getattr(row, "package_id", None) != package.id:
        abort(404)

    db.session.delete(row)
    db.session.commit()
    _log("delete", child_type, row_id)
    flash(f"{cfg['label']} deleted.", "success")
    return redirect(url_for("admin.package_edit", package_id=package.id))


# ─── Package price windows ─────────────────────────────────────────────
@admin_bp.route("/packages/<int:package_id>/prices/new", methods=["POST"])
@admin_required
def package_price_new(package_id: int):
    """Add a new seasonal price window to a package."""
    package = db.session.get(Package, package_id)
    if package is None:
        abort(404)

    def _dec(key, default=None):
        raw = (request.form.get(key) or "").strip()
        if not raw:
            return default
        try:
            from decimal import Decimal as _D
            return _D(raw)
        except Exception:
            return default

    from datetime import datetime as _dt
    def _date(key):
        raw = (request.form.get(key) or "").strip()
        if not raw:
            return None
        try:
            return _dt.strptime(raw, "%Y-%m-%d").date()
        except Exception:
            return None

    adult = _dec("adult_price")
    child = _dec("child_price")
    currency = (request.form.get("currency") or "EUR").strip().upper()[:3]
    valid_from = _date("valid_from")
    valid_to = _date("valid_to")

    if adult is None or adult <= 0:
        flash("Adult price is required and must be positive.", "danger")
        return redirect(url_for("admin.package_edit", package_id=package.id))
    if child is None:
        child = adult
    if valid_from and valid_to and valid_to < valid_from:
        flash("Valid-to date cannot be before valid-from.", "danger")
        return redirect(url_for("admin.package_edit", package_id=package.id))

    price = PackagePrice(
        package_id=package.id,
        adult_price=adult,
        child_price=child,
        currency=currency,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    db.session.add(price)
    db.session.commit()
    _log("create", "package_price", price.id, new=package.id)
    flash("Price window added.", "success")
    return redirect(url_for("admin.package_edit", package_id=package.id))


@admin_bp.route("/package-prices/<int:price_id>/delete", methods=["POST"])
@admin_required
def package_price_delete(price_id: int):
    """Delete a package price window."""
    price = db.session.get(PackagePrice, price_id)
    if price is None:
        abort(404)
    package_id = price.package_id
    db.session.delete(price)
    db.session.commit()
    _log("delete", "package_price", price_id)
    flash("Price window deleted.", "success")
    return redirect(url_for("admin.package_edit", package_id=package_id))


# ─── Package flights ───────────────────────────────────────────────────
@admin_bp.route("/packages/<int:package_id>/flights/new", methods=["POST"])
@admin_required
def package_flight_new(package_id: int):
    """Add a new flight to a package."""
    package = db.session.get(Package, package_id)
    if package is None:
        abort(404)

    flight_from = (request.form.get("flight_from") or "").strip()
    flight_to = (request.form.get("flight_to") or "").strip()
    if not flight_from or not flight_to:
        flash("Flight from and to are required.", "danger")
        return redirect(url_for("admin.package_edit", package_id=package.id))

    # Supplier: try to look up by ID, fall back to None
    supplier_id = None
    raw_supplier = (request.form.get("supplier_id") or "").strip()
    if raw_supplier:
        try:
            supplier_id = int(raw_supplier) or None
        except ValueError:
            supplier_id = None

    # Airline: prefer FK, fall back to free-text airline_name
    airline_id = None
    raw_airline_id = (request.form.get("airline_id") or "").strip()
    if raw_airline_id:
        try:
            airline_id = int(raw_airline_id) or None
        except ValueError:
            airline_id = None

    airline_name = (request.form.get("airline_name") or "").strip() or None
    if airline_id:
        airline_obj = db.session.get(Airline, airline_id)
        if airline_obj:
            airline_name = airline_obj.name

    flight = Flight(
        package_id=package.id,
        supplier_id=supplier_id,
        airline_id=airline_id,
        flight_from=flight_from,
        flight_to=flight_to,
        airline_name=airline_name,
        luggage_allowance=(request.form.get("luggage_allowance") or "").strip() or None,
        included=bool(request.form.get("included")),
        notes=(request.form.get("notes") or "").strip() or None,
    )
    db.session.add(flight)
    db.session.commit()
    _log("create", "flight", flight.id, new=package.id)
    flash("Flight added.", "success")
    return redirect(url_for("admin.package_edit", package_id=package.id))


@admin_bp.route("/flights/<int:flight_id>/delete", methods=["POST"])
@admin_required
def package_flight_delete(flight_id: int):
    """Delete a package flight."""
    flight = db.session.get(Flight, flight_id)
    if flight is None:
        abort(404)
    package_id = flight.package_id
    db.session.delete(flight)
    db.session.commit()
    _log("delete", "flight", flight_id)
    flash("Flight deleted.", "success")
    return redirect(url_for("admin.package_edit", package_id=package_id))


# ─── Package options (departure + flight + rate) ───────────────────────
def _apply_option_form(option: PackageOption) -> None:
    """Copy editable fields from request.form onto the option row."""
    f = request.form

    def _maybe_int(key):
        raw = (f.get(key) or "").strip()
        if not raw:
            return None
        try:
            return int(raw) or None
        except ValueError:
            return None

    from datetime import datetime as _dt
    def _maybe_date(key):
        raw = (f.get(key) or "").strip()
        if not raw:
            return None
        try:
            return _dt.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            return None

    option.flight_id = _maybe_int("flight_id")
    option.price_id = _maybe_int("price_id")
    option.room_id = _maybe_int("room_id")
    option.departure_date = _maybe_date("departure_date")
    option.return_date = _maybe_date("return_date")
    option.label = (f.get("label") or "").strip() or None
    option.is_active = bool(f.get("is_active", True))
    if option.sort_order is None:
        option.sort_order = 0


@admin_bp.route("/packages/<int:package_id>/options/new", methods=["POST"])
@admin_required
def package_option_new(package_id: int):
    """Add a departure option to a package."""
    package = db.session.get(Package, package_id)
    if package is None:
        abort(404)

    flight_id = (request.form.get("flight_id") or "").strip()
    price_id = (request.form.get("price_id") or "").strip()
    if not flight_id and not price_id:
        flash("Pick at least a flight or a price for the option.", "danger")
        return redirect(url_for("admin.package_edit", package_id=package.id))

    option = PackageOption(package_id=package.id)
    _apply_option_form(option)

    # sort_order: append to the end
    current_max = db.session.scalar(
        select(func.coalesce(func.max(PackageOption.sort_order), 0))
        .where(PackageOption.package_id == package.id)
    ) or 0
    option.sort_order = int(current_max) + 10

    db.session.add(option)
    db.session.commit()
    _log("create", "package_option", option.id, new=package.id)
    flash("Departure option added.", "success")
    return redirect(url_for("admin.package_edit", package_id=package.id))


@admin_bp.route("/packages/<int:package_id>/options/<int:option_id>/update", methods=["POST"])
@admin_required
def package_option_update(package_id: int, option_id: int):
    """Update a departure option inline."""
    package = db.session.get(Package, package_id)
    if package is None:
        abort(404)
    option = db.session.get(PackageOption, option_id)
    if option is None or option.package_id != package.id:
        abort(404)

    _apply_option_form(option)
    db.session.commit()
    _log("update", "package_option", option.id, new=package.id)
    flash("Departure option updated.", "success")
    return redirect(url_for("admin.package_edit", package_id=package.id))


@admin_bp.route("/options/<int:option_id>/delete", methods=["POST"])
@admin_required
def package_option_delete(option_id: int):
    """Delete a departure option."""
    option = db.session.get(PackageOption, option_id)
    if option is None:
        abort(404)
    package_id = option.package_id
    db.session.delete(option)
    db.session.commit()
    _log("delete", "package_option", option_id)
    flash("Departure option deleted.", "success")
    return redirect(url_for("admin.package_edit", package_id=package_id))
