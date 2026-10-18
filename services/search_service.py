"""
services/search_service.py
───────────────────────────
Cross-product search for activities, hotels, and packages.

v5 changes (multi-room upgrade):
  - _search_hotels uses hotel_capacity_service.min_rooms_needed to
    include hotels that can host the party across 1..MAX_ROOMS rooms.
    Previously the filter required a SINGLE room to hold the whole
    party, which hid every multi-room option.
  - Hotel cards gain `min_rooms` (int) and `rooms_note` (str) so the
    template can say "Needs 2 rooms".
  - Paginated fill-up loop keeps `per_page` items even after filtering.
  - Packages / activities are UNCHANGED in behaviour.

Earlier v4 changes (packages only):
  - Package cards now priced from PackageFlight cards via
    services.package_options_service.options_for_package
    (the same source used by /packages/<slug>).
  - Destinations with is_bookable=False are excluded.
  - total is computed AFTER the per-row price filter — pagination
    matches the returned items count.
"""

from __future__ import annotations

import logging
from datetime import timedelta, date

_td = timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from extensions import db
from models.activity import Activity, ActivityPrice
from models.destination import Destination
from models.hotel import Hotel, HotelFacility, HotelImage
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

MAX_ADULTS = 8
MAX_CHILDREN = 8

FACILITY_ICONS = {
    "general":  "bi-water",
    "dining":   "bi-egg-fried",
    "wellness": "bi-flower1",
    "sport":    "bi-bicycle",
    "family":   "bi-people",
    "business": "bi-wifi",
    "other":    "bi-check-circle",
}


def destinations_for_widget() -> list[dict[str, Any]]:
    """Return the list of destinations used by the search widget dropdown."""
    rows = db.session.scalars(
        select(Destination)
        .where(Destination.is_bookable.is_(True))
        .order_by(Destination.name.asc())
    ).all()
    return [
        {"id": d.id, "name": d.name, "slug": d.slug, "country": d.country}
        for d in rows
    ]


def destinations_for_package_widget() -> list[dict[str, Any]]:
    """
    Return only destinations that have at least one active package.
    Used by the package tab of the search widget so customers only
    see destinations they can actually book a package for.
    """
    has_pkg = (
        select(Package.id)
        .where(Package.destination_id == Destination.id)
        .where(Package.is_active.is_(True))
        .correlate(Destination)
        .exists()
    )
    rows = db.session.scalars(
        select(Destination)
        .where(Destination.is_bookable.is_(True))
        .where(has_pkg)
        .order_by(Destination.name.asc())
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
        raw_adults = int(adults)
        raw_children = int(children)
        adults = max(1, min(MAX_ADULTS, raw_adults))
        children = max(0, min(MAX_CHILDREN, raw_children))
        if raw_adults > MAX_ADULTS or raw_children > MAX_CHILDREN:
            ignored.append("party_size_capped")
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
            select(Destination)
            .where(Destination.slug == dest_slug)
            .where(Destination.is_bookable.is_(True))
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


# ═══════════════════════════════════════════════════════════════════
#  Hotels — multi-room aware
# ═══════════════════════════════════════════════════════════════════
def _rooms_note(min_rooms: int | None) -> str:
    if min_rooms is None:
        return ""
    if min_rooms == 1:
        return "Fits in 1 room"
    if min_rooms == 2:
        return "Needs 2 rooms"
    if min_rooms == 3:
        return "Needs 3 rooms"
    return f"Needs {min_rooms} rooms"


def _search_hotels(
    *, destination_id: int | None, check_in: date | None, check_out: date | None,
    adults: int, children: int,
    page: int, per_page: int, sort: str,
    query_text: str | None, ignored: list[str],
) -> tuple[list[dict], int]:
    """
    Hotel search with multi-room capacity.

    Party is (adults, children). Children here are counted, not aged —
    the search widget has no per-child age yet (arrives in Step 4). At
    this layer we treat every child as 2..12 for capacity purposes.

    Strategy
    --------
      1. SQL pre-filter: hotel must have >=1 active room.
      2. Cheap party pre-filter: if children > 0, at least one active
         room in the hotel must derive max_children >= 1 (drops
         adults-only hotels early).
      3. Sort + paginate at the DB level.
      4. For each hotel on the page, call min_rooms_needed. If None,
         drop it. If a page ends up short, top it up by fetching more
         pages (up to MAX_SCAN_PAGES).
      5. total = count of hotels that pass min_rooms_needed, computed
         by scanning the full filtered set in batches.

    This keeps the SQL simple and pushes the non-trivial bin-packing
    into Python where it is testable and cache-friendly.
    """
    from services.hotel_capacity_service import min_rooms_needed

    # ─── 1. Base filtered query ────────────────────────────────
    base = select(Hotel).where(Hotel.is_active.is_(True))
    if destination_id:
        base = base.where(Hotel.destination_id == destination_id)
    if query_text:
        base = base.where(Hotel.name.ilike(f"%{query_text}%"))

    # Require at least one active room
    base = base.where(
        select(Room.id)
        .where(Room.hotel_id == Hotel.id)
        .where(Room.is_active.is_(True))
        .correlate(Hotel)
        .exists()
    )

    # If any children, require at least one active room with
    # effective child capacity. Derivation is in Python, but the raw
    # signal we can rely on in SQL is:
    #   (max_children IS NOT NULL AND max_children > 0) OR
    #   (max_children IS NULL AND max_occupancy - COALESCE(max_adults, max_occupancy) > 0)
    # We also accept the B2 case where max_adults == max_occupancy and
    # max_children IS NULL — derivation gives occ >= 3 -> children >= 1,
    # so require max_occupancy >= 3 in that case.
    if children > 0:
        child_cap_expr = (
            (Room.max_children.is_not(None) & (Room.max_children > 0))
            | (
                Room.max_children.is_(None)
                & (
                    (Room.max_adults.is_(None) & (Room.max_occupancy >= 3))
                    | (
                        (Room.max_adults.is_not(None))
                        & (Room.max_adults == Room.max_occupancy)
                        & (Room.max_occupancy >= 3)
                    )
                    | (
                        (Room.max_adults.is_not(None))
                        & (Room.max_adults != Room.max_occupancy)
                        & ((Room.max_occupancy - Room.max_adults) > 0)
                    )
                )
            )
        )
        base = base.where(
            select(Room.id)
            .where(Room.hotel_id == Hotel.id)
            .where(Room.is_active.is_(True))
            .where(child_cap_expr)
            .correlate(Hotel)
            .exists()
        )

    # ─── 2. Sorting ────────────────────────────────────────────
    min_price_subq = (
        select(func.min(Room.base_price_per_night))
        .where(Room.hotel_id == Hotel.id)
        .where(Room.is_active.is_(True))
        .where(Room.base_price_per_night.is_not(None))
        .where(Room.base_price_per_night > 0)
        .correlate(Hotel)
        .scalar_subquery()
    )

    if sort == "name":
        base = base.order_by(Hotel.name.asc())
    elif sort == "stars_desc":
        base = base.order_by(Hotel.stars.desc().nullslast(), Hotel.name.asc())
    elif sort == "price_asc":
        base = base.order_by(min_price_subq.asc().nullslast(), Hotel.name.asc())
    elif sort == "price_desc":
        base = base.order_by(min_price_subq.desc().nullslast(), Hotel.name.asc())
    else:
        base = base.order_by(Hotel.id.desc())

    # ─── 3. Scan + filter, fill pages ──────────────────────────
    # Total: scan in batches so we don't blow memory on 180 hotels.
    # 180 rows is trivial; the batch loop just keeps the code honest if
    # the catalogue grows.
    BATCH = 100
    MAX_SCAN_PAGES = 20  # safety cap; ~2000 hotels max scan

    # 3a. Compute total by streaming the full filtered set once.
    total = 0
    offset = 0
    scanned_pages = 0
    while True:
        batch_rows = list(db.session.scalars(base.limit(BATCH).offset(offset)).all())
        if not batch_rows:
            break
        for h in batch_rows:
            m = min_rooms_needed(
                h.id, adults=adults,
                child_ages=[10] * children,  # placeholder ages (child class)
                infants=0,
            )
            if m is not None:
                total += 1
        if len(batch_rows) < BATCH:
            break
        offset += BATCH
        scanned_pages += 1
        if scanned_pages >= MAX_SCAN_PAGES:
            break

    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages

    # 3b. Page fill: walk the filtered set, skip hotels that don't fit,
    # stop when we have per_page items or we run out.
    needed = per_page
    skip_until = (page - 1) * per_page  # how many valid hotels to skip first
    items: list[dict] = []
    offset = 0
    seen_valid = 0
    while needed > 0 and offset < 5000:  # hard safety cap on scan
        batch_rows = list(db.session.scalars(base.limit(BATCH).offset(offset)).all())
        if not batch_rows:
            break
        for h in batch_rows:
            m = min_rooms_needed(
                h.id, adults=adults,
                child_ages=[10] * children,
                infants=0,
            )
            if m is None:
                continue
            if seen_valid < skip_until:
                seen_valid += 1
                continue
            seen_valid += 1

            # Build the item
            dest = db.session.get(Destination, h.destination_id) if h.destination_id else None
            pricing = _hotel_pricing_for_dates(
                hotel_id=h.id,
                check_in=check_in,
                check_out=check_out,
                adults=adults,
                children=children,
            )
            rich = _hotel_display_data(h.id)
            image_url = _first_image_url(getattr(h, "images", None)) or rich["cover_image"]

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
                "meal_plan": pricing.get("meal_plan"), 
                "adults": adults,
                "children": children,
                "check_in": check_in.isoformat() if check_in else None,
                "check_out": check_out.isoformat() if check_out else None,
                "price_basis": "per_night",
                
                "stars": h.stars,
                "address": h.address,
                "check_in_time": h.check_in_time,
                "check_out_time": h.check_out_time,
                "google_maps_url": h.google_maps_url,
                "description_snippet": (
                    (h.description or "")[:140].rsplit(" ", 1)[0] + "..."
                    if h.description and len(h.description) > 140
                    else (h.description or "")
                ),
                "facilities": rich["facilities"],
                "room_count": rich["room_count"],
                "min_rooms": m,
                "rooms_note": _rooms_note(m),
            })
            needed -= 1
            if needed <= 0:
                break
        if len(batch_rows) < BATCH:
            break
        offset += BATCH

    return items, total


def _hotel_display_data(hotel_id: int) -> dict[str, Any]:
    cover = db.session.scalars(
        select(HotelImage)
        .where(HotelImage.hotel_id == hotel_id)
        .where(HotelImage.media_type == "image")
        .order_by(HotelImage.sort_order.asc())
        .limit(1)
    ).first()
    cover_url = cover.url if cover else None

    facs = db.session.scalars(
        select(HotelFacility)
        .where(HotelFacility.hotel_id == hotel_id)
        .order_by(HotelFacility.id.asc())
        .limit(6)
    ).all()
    seen_types: set[str] = set()
    picked: list[dict] = []
    for f in facs:
        if f.type in seen_types and len(picked) >= 3:
            continue
        seen_types.add(f.type)
        picked.append({
            "name": f.name,
            "type": f.type,
            "icon": FACILITY_ICONS.get(f.type, "bi-check-circle"),
        })
        if len(picked) >= 3:
            break

    room_count = int(db.session.scalar(
        select(func.count(Room.id)).where(Room.hotel_id == hotel_id)
    ) or 0)

    return {
        "cover_image": cover_url,
        "facilities": picked,
        "room_count": room_count,
    }

def _hotel_pricing_for_dates(
    *, hotel_id: int,
    check_in: date | None, check_out: date | None,
    adults: int, children: int,
) -> dict[str, Any]:
    empty = {
        "adult_rate": None, "child_rate": None, "nights": None,
        "per_night": None, "total": None, "currency": "GBP",
        "meal_plan": None,
    }

    from services import hotel_capacity_service
    child_ages = [6] * children
    
    try:
        grouping = hotel_capacity_service.best_room_grouping(
            hotel_id, adults=adults, child_ages=child_ages, infants=0,
            check_in=check_in, check_out=check_out
        )
    except Exception:
        grouping = None

    min_rooms = grouping.get("min_rooms", 1) if grouping else 1

    # Get the exact cheapest room
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

    nights = 1
    if check_in is not None and check_out is not None:
        nights = max(0, (check_out - check_in).days)

    adult_rate = Decimal("0")
    child_rate = Decimal("0")
    currency = "GBP"

    if check_in is not None:
        rate = db.session.scalars(
            select(RoomRate)
            .where(RoomRate.room_id == room.id)
            .where((RoomRate.valid_from.is_(None)) | (RoomRate.valid_from <= check_in))
            .where((RoomRate.valid_to.is_(None)) | (RoomRate.valid_to >= check_in))
            .order_by(RoomRate.id.asc()).limit(1)
        ).first()
        
        if rate is not None:
            adult_rate = rate.adult_price
            child_rate = rate.child_price
            currency = rate.currency or "GBP"
        else:
            adult_rate = room.base_price_per_night
            child_rate = Decimal("0.00")
    else:
        adult_rate = room.base_price_per_night
        child_rate = Decimal("0.00")

    # Price for 1 room (2 adults, 1 child)
    per_night_one_room = (adult_rate * 2) + child_rate
    per_night = per_night_one_room * min_rooms
    total = per_night * nights

    return {
        "adult_rate": adult_rate,
        "child_rate": child_rate,
        "nights": nights,
        "per_night": per_night,
        "total": total,
        "currency": currency,
        "meal_plan": room.meal_plan,
    }

def _search_packages(
    *, destination_id: int | None, check_in: date | None, check_out: date | None,
    adults: int, children: int,
    page: int, per_page: int, sort: str,
    query_text: str | None, ignored: list[str],
) -> tuple[list[dict], int]:
    """
    Package search.

    Prices come from services.package_options_service — same source
    the detail page uses. A package is only returned if it has at
    least one PackageFlight card whose outbound date is within
    +/-3 days of the requested check_in.
    """
    from services.package_options_service import options_for_package

    stmt = select(Package).where(Package.is_active.is_(True))
    stmt = stmt.join(Destination, Destination.id == Package.destination_id)
    stmt = stmt.where(Destination.is_bookable.is_(True))
    if destination_id:
        stmt = stmt.where(Package.destination_id == destination_id)
    if query_text:
        stmt = stmt.where(Package.name.ilike(f"%{query_text}%"))
    stmt = stmt.where(Package.capacity >= (adults + children))

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

    from services import availability_service

    priced_items: list[dict] = []
    scanned = 0
    max_scan = max(per_page * 6, 60)

    rows = db.session.scalars(stmt.limit(max_scan).offset(0)).all()

    for p in rows:
        scanned += 1

        try:
            if check_in is not None:
                remaining = availability_service.package_availability(p.id, check_in)
                if remaining is not None and remaining < (adults + children):
                    continue
        except Exception as exc:
            log.debug("search availability skipped for package %s: %s", p.id, exc)

        opts = options_for_package(
            package=p,
            check_in=check_in,
            check_out=check_out,
            adults=adults,
            children=children,
            tolerance_days=3,
        )
        if not opts:
            continue

        best = opts[0]

        dest = db.session.get(Destination, p.destination_id) if p.destination_id else None
        image_url = _first_image_url(getattr(p, "images", None))

        pkg_hotel = db.session.get(Hotel, p.hotel_id) if p.hotel_id else None
        pkg_room = db.session.get(Room, p.room_id) if p.room_id else None
        pkg_facilities = []
        if pkg_hotel is not None:
            facs = db.session.scalars(
                select(HotelFacility)
                .where(HotelFacility.hotel_id == pkg_hotel.id)
                .order_by(HotelFacility.id.asc())
                .limit(6)
            ).all()
            pkg_facilities = [f.name for f in facs][:6]

        priced_items.append({
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "destination_id": p.destination_id,
            "destination_name": dest.name if dest else None,
            "price_adult": float(best["price_adult"]),
            "currency": best["currency"],
            "image_url": image_url,
            "extra": {
                "duration_nights": best["nights"],
                "package_type": p.package_type,
                "code": p.code,
                "hotel_stars": pkg_hotel.stars if pkg_hotel else None,
                "hotel_name": pkg_hotel.name if pkg_hotel else None,
                "room_type": pkg_room.type if pkg_room else None,
                "facilities": pkg_facilities,
                "inclusions": [],
                "windows": [],
                "airline_name": best["airline_name"],
                "flight_from": best["flight_from"],
                "flight_to": best["flight_to"],
                "departure_date": best["departure_date"].isoformat() if best["departure_date"] else None,
                "return_date": best["return_date"].isoformat() if best["return_date"] else None,
            },
            "price_child": float(best["price_child"]),
            "nights": best["nights"],
            "price_per_night": None,
            "total_price": float(best["grand_total"]),
            "adults": adults,
            "children": children,
            "check_in": check_in.isoformat() if check_in else None,
            "check_out": check_out.isoformat() if check_out else None,
            "price_basis": "per_person_flat",
            "stars": None,
            "address": None,
            "check_in_time": None,
            "check_out_time": None,
            "google_maps_url": p.google_maps_url,
            "description_snippet": (
                (p.description or "")[:140].rsplit(" ", 1)[0] + "..."
            ) if p.description and len(p.description) > 140 else (p.description or ""),
        })

        if len(priced_items) >= (offset + per_page):
            break

    total = len(priced_items)
    paginated = priced_items[offset:offset + per_page]

    return paginated, total


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
        pricing = _activity_pricing(activity_id=a.id, adults=adults, children=children)
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
                "duration_hours": float(a.duration_hours) if a.duration_hours else None,
                "inclusions": [
                    inc.item for inc in (getattr(a, "inclusions", None) or [])
                ][:6],
                "languages": [
                    lang.language for lang in (getattr(a, "languages", None) or [])
                ][:6],
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
            "stars": None,
            "address": getattr(a, "meeting_point", None),
            "check_in_time": getattr(a, "departure_time", None),
            "check_out_time": getattr(a, "return_time", None),
            "google_maps_url": getattr(a, "google_maps_url", None),
            "description_snippet": (
                (a.description or "")[:140].rsplit(" ", 1)[0] + "..."
                if a.description and len(a.description) > 140
                else (a.description or "")
            ),
            "facilities": [],
            "room_count": None,
        })

    return items, total


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
        return {"adult_price": None, "child_price": None, "total": None, "currency": "GBP"}
    try:
        total = (row.adult_price * adults) + ((row.child_price or Decimal("0")) * children)
    except Exception:
        total = None
    return {
        "adult_price": row.adult_price,
        "child_price": row.child_price,
        "total": total,
        "currency": row.currency or "GBP",
    }


def _first_image_url(images: list | None) -> str | None:
    if not images:
        return None
    for img in images:
        url = getattr(img, "url", None)
        if url and not url.lower().endswith(".mp4"):
            return url
    return None


__all__ = [
    "search",
    "destinations_for_widget",
    "destinations_for_package_widget",
]