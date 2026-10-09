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
    BookingItem,
    Destination,
    Flight,
    Hotel,
    Package,
    PackageExclusion,
    PackageInclusion,
    PackageItinerary,
    PackagePrice,
    Room,
    PRODUCT_TYPE_PACKAGE,
    VALID_PACKAGE_TYPES,
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

    return render_template(
        "admin/package_form.html",
        package=package,
        destinations=destinations,
        hotels=hotels,
        rooms=rooms,
        package_types=VALID_PACKAGE_TYPES,
        itineraries=itineraries,
        inclusions=inclusions,
        exclusions=exclusions,
        prices=prices,
        flights=flights,
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
