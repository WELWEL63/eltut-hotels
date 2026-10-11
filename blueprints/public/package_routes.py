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

from collections import namedtuple
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
    PackageOption,
    Airline,
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


# ─── Per-flight surcharge tables ───────────────────────────────────
_AIRLINE_SURCHARGE = {
    "wizz air":  (-30.0, -20.0),
    "wizzair":   (-30.0, -20.0),
    "wizz":      (-30.0, -20.0),
    "easy jet":  (0.0, 0.0),
    "easyjet":   (0.0, 0.0),
    "tui":       (80.0, 50.0),
    "egypt air": (150.0, 100.0),
    "egyptair":  (150.0, 100.0),
}
_ORIGIN_PREMIUM = {
    "london gatwick":  0.0,
    "london luton":    0.0,
    "manchester":      0.0,
    "glasgow":        -20.0,
    "birmingham":      10.0,
    "bristol":         15.0,
    "leeds bradford":  20.0,
    "london heathrow": 80.0,
}


def _surcharge_for(airline_name, origin):
    """Return (adult_surcharge, child_surcharge) for a flight."""
    a = (airline_name or "").strip().lower()
    s_adult, s_child = 0.0, 0.0
    for key, (sa, sc) in _AIRLINE_SURCHARGE.items():
        if key in a:
            s_adult, s_child = sa, sc
            break
    o = (origin or "").strip().lower()
    origin_prem = 0.0
    for key, val in _ORIGIN_PREMIUM.items():
        if key in o:
            origin_prem = val
            break
    return (s_adult + origin_prem, s_child + origin_prem * 0.7)


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

    # Availability (best-effort)
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

    # ─── Read stay params from URL ────────────────────────────────
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

    # ─── Departure options ────────────────────────────────────────
    options_rows = list(db.session.scalars(
        select(PackageOption)
        .where(PackageOption.package_id == package.id)
        .where(PackageOption.is_active.is_(True))
        .order_by(PackageOption.sort_order.asc(), PackageOption.id.asc())
    ))

    _SyntheticOption = namedtuple(
        "SyntheticOption",
        "id flight price departure_date return_date display_label",
    )

    if not options_rows:
        # Fallback: build from flights if no options
        _prices = list(db.session.scalars(
            select(PackagePrice)
            .where(PackagePrice.package_id == package.id)
            .order_by(PackagePrice.adult_price.asc(), PackagePrice.id.asc())
        ))
        _chosen_price = None
        for _pr in _prices:
            if (_pr.valid_from is not None and _pr.valid_to is not None
                    and _pr.valid_from <= check_in and _pr.valid_to >= check_out):
                _chosen_price = _pr
                break
        if _chosen_price is None:
            for _pr in _prices:
                if (_pr.valid_from is not None and _pr.valid_to is not None
                        and _pr.valid_from <= check_out and _pr.valid_to >= check_in):
                    _chosen_price = _pr
                    break
        if _chosen_price is None:
            for _pr in _prices:
                if _pr.valid_from is None and _pr.valid_to is None:
                    _chosen_price = _pr
                    break
        if _chosen_price is None and _prices:
            _chosen_price = _prices[0]

        if flights and _chosen_price is not None:
            options_rows = [
                _SyntheticOption(
                    id=f.id,
                    flight=f,
                    price=_chosen_price,
                    departure_date=check_in,
                    return_date=check_out,
                    display_label=(
                        f"{f.airline_name or 'Flight'} · "
                        f"{f.flight_from or '?'} → {f.flight_to or '?'}"
                    ),
                )
                for f in flights
            ]

    # ─── Cap number of options + dedupe by airline ───────────────
    try:
        from services import content_service  # noqa: PLC0415
        _raw_max = content_service.get("package_flights_max")
        _max_options = max(1, min(int(_raw_max), 10)) if _raw_max else 4
    except Exception:
        _max_options = 4

    _seen_airlines: set[str] = set()
    _capped = []
    for _opt in options_rows:
        _f = getattr(_opt, "flight", None)
        _airline = ((_f.airline_name if _f else "") or "").strip().lower()
        if _airline and _airline in _seen_airlines:
            continue
        if _airline:
            _seen_airlines.add(_airline)
        _capped.append(_opt)
        if len(_capped) >= _max_options:
            break
    options_rows = _capped

    # ─── Airline lookups ─────────────────────────────────────────
    airlines_by_id: dict[int, dict] = {}
    airlines_by_name: dict[str, dict] = {}
    try:
        for al in db.session.scalars(select(Airline)):
            entry = {"name": al.name, "logo_url": al.logo_url}
            airlines_by_id[al.id] = entry
            if al.name:
                normalized = al.name.strip().lower().replace(" ", "")
                airlines_by_name[normalized] = entry
    except Exception as exc:  # noqa: BLE001
        current_app.logger.debug("airline lookup failed: %s", exc)

    def _resolve_airline(flight) -> dict:
        if flight is None:
            return {"name": None, "logo_url": None}
        if getattr(flight, "airline_id", None):
            entry = airlines_by_id.get(flight.airline_id)
            if entry:
                return {
                    "name": entry["name"] or flight.airline_name,
                    "logo_url": entry["logo_url"],
                }
        if flight.airline_name:
            normalized = flight.airline_name.strip().lower().replace(" ", "")
            entry = airlines_by_name.get(normalized)
            if entry:
                return {
                    "name": flight.airline_name,
                    "logo_url": entry["logo_url"],
                }
        return {"name": flight.airline_name, "logo_url": None}

    # ─── Dynamic price resolution for the customer's dates ───────
    _all_prices = list(db.session.scalars(
        select(PackagePrice)
        .where(PackagePrice.package_id == package.id)
        .order_by(PackagePrice.adult_price.asc(), PackagePrice.id.asc())
    ))

    _customer_nights = (check_out - check_in).days if (check_in and check_out) else None

    def _pick_dynamic_price():
        """Find the best matching PackagePrice for the customer's dates."""
        if _customer_nights is not None:
            for _pr in _all_prices:
                if (_pr.valid_from is not None and _pr.valid_to is not None
                        and _pr.valid_from <= check_in
                        and _pr.valid_to >= check_out
                        and (_pr.valid_to - _pr.valid_from).days == _customer_nights):
                    return _pr
            for _pr in _all_prices:
                if (_pr.valid_from is not None and _pr.valid_to is not None
                        and _pr.valid_from <= check_in
                        and _pr.valid_to >= check_out):
                    return _pr
            for _pr in _all_prices:
                if (_pr.valid_from is not None and _pr.valid_to is not None
                        and _pr.valid_from <= check_in <= _pr.valid_to):
                    return _pr
        for _pr in _all_prices:
            if _pr.valid_from is None and _pr.valid_to is None:
                return _pr
        return _all_prices[0] if _all_prices else None

    # Serialise options
    options: list[dict] = []
    for opt in options_rows:
        flight = opt.flight
        dynamic_price = _pick_dynamic_price()
        price = dynamic_price or opt.price
        airline = _resolve_airline(flight)

        base_adult = float(price.adult_price) if price else None
        base_child = float(price.child_price) if price else None

        s_adult, s_child = _surcharge_for(
            flight.airline_name if flight else None,
            flight.flight_from if flight else None,
        )
        final_adult = (base_adult + s_adult) if base_adult is not None else None
        final_child = (base_child + s_child) if base_child is not None else None

        opt_departure = check_in if url_check_in else opt.departure_date
        opt_return = check_out if url_check_out else opt.return_date

        options.append({
            "id": opt.id,
            "label": opt.display_label,
            "departure_date": opt_departure,
            "return_date": opt_return,
            "flight_from": flight.flight_from if flight else None,
            "flight_to": flight.flight_to if flight else None,
            "airline_name": airline["name"],
            "airline_logo": airline["logo_url"],
            "luggage_allowance": flight.luggage_allowance if flight else None,
            "price_adult": final_adult,
            "price_child": final_child,
            "currency": price.currency if price else None,
        })

    # ─── Reviews (MongoDB, best-effort) ──────────────────────────
    reviews: list[dict] = []
    user_has_reviewed = False
    try:
        from flask_login import current_user  # noqa: PLC0415
        from mongo.reviews import (  # noqa: PLC0415
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
    except Exception as exc:  # noqa: BLE001
        current_app.logger.debug("package reviews unavailable: %s", exc)

    # ─── Sidebar pricing ─────────────────────────────────────────
    sidebar_pricing = {
        "adult_rate": price_adult,
        "child_rate": price_child,
        "nights": nights,
        "total": None,
        "currency": currency or "EUR",
    }
    if price_adult is not None:
        child_rate = price_child or 0
        total = (float(price_adult) * adults) + (float(child_rate) * children)
        sidebar_pricing["total"] = total
        sidebar_pricing["per_person"] = price_adult

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
        adults=adults,
        children=children,
        sidebar_pricing=sidebar_pricing,
    )