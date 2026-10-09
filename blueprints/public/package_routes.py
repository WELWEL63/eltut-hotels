"""
blueprints/public/package_routes.py
───────────────────────────────────
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
"""

from __future__ import annotations

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
    PackageImage,
    PackageInclusion,
    PackageItinerary,
    PackagePrice,
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
    flights = list(db.session.scalars(
        select(Flight)
        .where(Flight.package_id == package.id, Flight.is_active.is_(True))
    ))

    price_adult, price_child, currency = _first_package_price(package.id)
    avg_rating, review_count = _avg_rating(package.id)

    # Availability (best-effort — never break the page if this fails)
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
        flights=flights,
        price_adult=price_adult,
        price_child=price_child,
        currency=currency,
        avg_rating=avg_rating,
        review_count=review_count,
        remaining=remaining,
        related=related,
    )

