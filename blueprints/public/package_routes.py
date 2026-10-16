"""
blueprints/public/package_routes.py
─────────────────────────────────────
Package listing and detail pages.

ROUTES
    GET /packages              list with filters, sort, pagination
    GET /packages/<slug>       detail page with itinerary + flights

FILTERS (query parameters, all optional)
    destination   slug of a destination
    package_type  one of VALID_PACKAGE_TYPES
    min_nights    integer >= 1
    q             free-text search on package name
    sort          newest (default) | name | price_asc | price_desc | duration
    page          1-based page number
    check_in      ISO date
    check_out     ISO date
    adults        int
    children      int
"""

from __future__ import annotations

from datetime import date as _date, timedelta as _td

from flask import abort, current_app, render_template, request
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from blueprints.public import public_bp
from extensions import db
from models import (
    Destination,
    Flight,
    Hotel,
    Package,
    PackageExclusion,
    PackageFAQ,
    PackageImage,
    PackageInclusion,
    PackageItinerary,
    PackagePrice,
    PackageTip,
    Room,
    VALID_PACKAGE_TYPES,
)


def _int_arg(name: str, default: int, lo: int, hi: int) -> int:
    raw = request.args.get(name, "").strip()
    try:
        return max(lo, min(hi, int(raw)))
    except (TypeError, ValueError):
        return default


def _first_package_price(package_id: int):
    row = db.session.scalar(
        select(PackagePrice)
        .where(PackagePrice.package_id == package_id)
        .order_by(PackagePrice.id)
        .limit(1)
    )
    if row is None:
        return (None, None, None)
    try:
        return (float(row.adult_price), float(row.child_price), row.currency)
    except Exception:
        return (None, None, None)


def _avg_rating(package_id: int):
    try:
        from mongo.reviews import rating_summary
        summary = rating_summary("package", package_id)
        return (summary.get("average"), int(summary.get("count") or 0))
    except Exception:
        return (None, 0)


@public_bp.route("/packages")
def package_list():
    page = _int_arg("page", 1, 1, 10_000)
    per_page = int(current_app.config.get("ITEMS_PER_PAGE", 12) or 12)
    per_page = max(6, min(per_page, 48))

    destination_slug = (request.args.get("destination") or "").strip().lower()
    package_type = (request.args.get("package_type") or "").strip().lower()
    min_nights_raw = request.args.get("min_nights", "").strip()
    query_text = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "newest").strip().lower()

    min_nights = None
    if min_nights_raw:
        try:
            min_nights = max(1, int(min_nights_raw))
        except ValueError:
            min_nights = None

    stmt = (
        select(Package)
        .options(joinedload(Package.images))
        .where(Package.is_active.is_(True))
        .join(Destination, Destination.id == Package.destination_id)
        .where(Destination.is_bookable.is_(True))
    )

    selected_destination = None
    if destination_slug:
        selected_destination = db.session.scalar(
            select(Destination).where(Destination.slug == destination_slug)
        )
        if selected_destination is not None:
            stmt = stmt.where(Package.destination_id == selected_destination.id)

    if package_type and package_type in VALID_PACKAGE_TYPES:
        stmt = stmt.where(Package.package_type == package_type)

    if min_nights is not None:
        stmt = stmt.where(Package.duration_nights >= min_nights)

    if query_text:
        stmt = stmt.where(Package.name.ilike(f"%{query_text}%"))

    if sort == "name":
        stmt = stmt.order_by(Package.name.asc())
    elif sort == "duration":
        stmt = stmt.order_by(Package.duration_nights.desc(), Package.name.asc())
    elif sort == "price_asc":
        stmt = stmt.order_by(
            select(PackagePrice.adult_price)
            .where(PackagePrice.package_id == Package.id)
            .limit(1)
            .scalar_subquery()
            .asc()
        )
    elif sort == "price_desc":
        stmt = stmt.order_by(
            select(PackagePrice.adult_price)
            .where(PackagePrice.package_id == Package.id)
            .limit(1)
            .scalar_subquery()
            .desc()
        )
    else:
        stmt = stmt.order_by(Package.id.desc())

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    rows = list(db.session.scalars(stmt.limit(per_page).offset(offset)).unique())

    items = []
    for p in rows:
        price_adult, price_child, currency = _first_package_price(p.id)
        first_image = p.images[0].url if p.images else None
        items.append({
            "package": p,
            "price_adult": price_adult,
            "price_child": price_child,
            "currency": currency,
            "image_url": first_image,
        })

    destinations = list(db.session.scalars(
        select(Destination).order_by(Destination.name)
    ))

    return render_template(
        "public/package_list.html",
        items=items,
        total=total,
        page=page,
        total_pages=total_pages,
        destinations=destinations,
        package_types=VALID_PACKAGE_TYPES,
        selected_destination=selected_destination,
        selected_package_type=package_type,
        min_nights=min_nights,
        query_text=query_text,
        sort=sort,
    )


@public_bp.route("/packages/<slug>")
def package_detail(slug: str):
    package = db.session.scalars(
        select(Package)
        .options(joinedload(Package.images))
        .where(Package.slug == slug, Package.is_active.is_(True))
    ).unique().first()
    if package is None:
        abort(404)

    destination = db.session.get(Destination, package.destination_id)
    if destination is not None and not destination.is_bookable:
        abort(404)
    hotel = db.session.get(Hotel, package.hotel_id)
    room = db.session.get(Room, package.room_id)

    images = list(db.session.scalars(
        select(PackageImage)
        .where(PackageImage.package_id == package.id)
        .order_by(PackageImage.sort_order)
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
    itineraries = list(db.session.scalars(
        select(PackageItinerary)
        .where(PackageItinerary.package_id == package.id)
        .order_by(PackageItinerary.day_number)
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
    flights = list(db.session.scalars(
        select(Flight)
        .where(Flight.package_id == package.id, Flight.is_active.is_(True))
    ))

    price_adult, price_child, currency = _first_package_price(package.id)
    avg_rating, review_count = _avg_rating(package.id)

    remaining = None
    try:
        from services.availability_service import package_availability
        remaining = package_availability(package.id)
    except Exception:
        remaining = None

    related = list(db.session.scalars(
        select(Package)
        .where(
            Package.destination_id == package.destination_id,
            Package.id != package.id,
            Package.is_active.is_(True),
        )
        .order_by(Package.id)
        .limit(3)
    ))

    def _parse_date_arg(name: str):
        raw = (request.args.get(name) or "").strip()
        if not raw:
            return None
        try:
            return _date.fromisoformat(raw)
        except ValueError:
            return None

    url_check_in = _parse_date_arg("check_in")
    url_check_out = _parse_date_arg("check_out")

    if url_check_in and url_check_out and url_check_out > url_check_in:
        check_in = url_check_in
        check_out = url_check_out
    else:
        check_in = _date.today() + _td(days=30)
        check_out = check_in + _td(days=package.duration_nights or 7)

    nights = (
        max(1, (check_out - check_in).days)
        if check_in and check_out
        else (package.duration_nights or 7)
    )
    adults = _int_arg("adults", 2, 1, 8)
    children = _int_arg("children", 0, 0, 8)

    _today = _date.today()
    _min_notice_date = _today + _td(days=7)
    _max_horizon_date = _today + _td(days=365)
    _max_checkout_date = _max_horizon_date + _td(days=int(package.duration_nights or 7))

    validation = {"ok": True, "code": "", "message": ""}
    if url_check_in and url_check_out:
        if check_in < _min_notice_date:
            validation = {
                "ok": False,
                "code": "too_soon",
                "message": (
                    "We need at least 7 days' notice to prepare this trip. "
                    "Please choose a departure a week or more from today."
                ),
            }
        elif check_in > _max_horizon_date:
            validation = {
                "ok": False,
                "code": "too_far",
                "message": (
                    "Bookings are open up to 1 year in advance. "
                    "Please choose a nearer date."
                ),
            }

    from services.package_options_service import options_for_package

    options = []
    if validation["ok"]:
        options = options_for_package(
            package=package,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            children=children,
            tolerance_days=3,
        )
        if url_check_in and url_check_out and not options:
            validation = {
                "ok": False,
                "code": "no_flights",
                "message": (
                    "No departures available within 3 days of those dates. "
                    "Try shifting your travel dates by a few days."
                ),
            }

    sidebar_pricing = {
        "adult_rate": None,
        "child_rate": None,
        "nights": nights,
        "total": None,
        "per_person": None,
        "currency": currency or "GBP",
    }
    if options:
        best = options[0]
        sidebar_pricing = {
            "adult_rate": best["price_adult"],
            "child_rate": best["price_child"],
            "nights": best["nights"],
            "total": best["grand_total"],
            "per_person": best["price_adult"],
            "currency": best["currency"],
        }

    reviews: list[dict] = []
    user_has_reviewed = False
    try:
        from flask_login import current_user
        from mongo.reviews import (
            list_reviews_for_product,
            has_reviewed,
        )
        reviews = list_reviews_for_product(
            product_type="package",
            product_id=package.id,
            limit=20,
        )
        if current_user.is_authenticated:
            user_has_reviewed = has_reviewed(
                user_id=current_user.id,
                product_type="package",
                product_id=package.id,
            )
    except Exception as exc:
        current_app.logger.debug("package reviews unavailable: %s", exc)

    # Airline lookup for JS-side logo resolution (template reads it).
    airlines_by_name: dict[str, dict] = {}
    try:
        from models import Airline
        for al in db.session.scalars(select(Airline)):
            if al.name:
                normalized = al.name.strip().lower().replace(" ", "")
                airlines_by_name[normalized] = {
                    "name": al.name,
                    "logo_url": al.logo_url,
                }
    except Exception as exc:
        current_app.logger.debug("airline lookup failed: %s", exc)

    return render_template(
        "public/package_detail.html",
        package=package,
        destination=destination,
        hotel=hotel,
        room=room,
        images=images,
        inclusions=inclusions,
        exclusions=exclusions,
        itineraries=itineraries,
        faqs=faqs,
        tips=tips,
        flights=flights,
        price_adult=price_adult,
        price_child=price_child,
        currency=currency,
        avg_rating=avg_rating,
        review_count=review_count,
        remaining=remaining,
        related=related,
        reviews=reviews,
        user_has_reviewed=user_has_reviewed,
        options=options,
        airline_lookup=airlines_by_name,
        check_in=check_in,
        check_out=check_out,
        nights=nights,
        validation=validation,
        min_notice_date=_min_notice_date,
        max_horizon_date=_max_horizon_date,
        max_checkout_date=_max_checkout_date,
        adults=adults,
        children=children,
        sidebar_pricing=sidebar_pricing,
    )