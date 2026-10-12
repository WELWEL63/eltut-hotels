"""
services/search_service.py
───────────────────────────
Cross-product search for activities, hotels, and packages.

v3 changes:
  - Party size caps: adults 1-8, children 0-8 (silent cap)
  - Hotel filter: only return hotels with a room where max_occupancy >= party_size
  - All other behavior identical to v2
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

# Party size caps (silent — URL values above these are clamped, not rejected)
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
        select(Destination).order_by(Destination.name.asc())
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
    """Run a search. See module docstring for the return shape."""
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

    # ── Party size: cap to safe maximums ────────────────────────────
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
            select(Destination).where(Destination.slug == dest_slug)
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


def _search_hotels(
    *, destination_id: int | None, check_in: date | None, check_out: date | None,
    adults: int, children: int,
    page: int, per_page: int, sort: str,
    query_text: str | None, ignored: list[str],
) -> tuple[list[dict], int]:
    stmt = select(Hotel).where(Hotel.is_active.is_(True))
    if destination_id:
        stmt = stmt.where(Hotel.destination_id == destination_id)
    if query_text:
        stmt = stmt.where(Hotel.name.ilike(f"%{query_text}%"))

    # ── Filter by room capacity ─────────────────────────────────────
    party_size = adults + children
    if party_size > 0:
        stmt = stmt.where(
            select(Room.id)
            .where(Room.hotel_id == Hotel.id)
            .where(Room.is_active.is_(True))
            .where(Room.max_occupancy >= party_size)
            .correlate(Hotel)
            .exists()
        )

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)

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
        stmt = stmt.order_by(Hotel.name.asc())
    elif sort == "stars_desc":
        stmt = stmt.order_by(Hotel.stars.desc().nullslast(), Hotel.name.asc())
    elif sort == "price_asc":
        stmt = stmt.order_by(min_price_subq.asc().nullslast(), Hotel.name.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(min_price_subq.desc().nullslast(), Hotel.name.asc())
    else:
        stmt = stmt.order_by(Hotel.id.desc())

    offset = (page - 1) * per_page
    rows = db.session.scalars(stmt.limit(per_page).offset(offset)).all()

    items: list[dict] = []
    for h in rows:
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
        })

    return items, total


def _hotel_display_data(hotel_id: int) -> dict[str, Any]:
    """Fetch cover image + top facilities + room count for a hotel."""
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
    """Compute the hotel price picture for a stay."""
    empty = {
        "adult_rate": None, "child_rate": None, "nights": None,
        "per_night": None, "total": None, "currency": "EUR",
    }

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

    adult_rate: Decimal | None = None
    child_rate: Decimal | None = None
    currency = "EUR"

    if check_in is not None:
        rate = db.session.scalars(
            select(RoomRate)
            .where(RoomRate.room_id == room.id)
            .where(
                (RoomRate.valid_from.is_(None))
                | (RoomRate.valid_from <= check_in)
            )
            .where(
                (RoomRate.valid_to.is_(None))
                | (RoomRate.valid_to >= check_in)
            )
            .order_by(RoomRate.id.asc())
            .limit(1)
        ).first()
        if rate is not None:
            adult_rate = rate.adult_price
            child_rate = rate.child_price
            currency = rate.currency or "EUR"

    if adult_rate is None:
        adult_rate = room.base_price_per_night
        child_rate = Decimal("0.00")

    try:
        per_night = (adult_rate * adults) + ((child_rate or Decimal("0")) * children)
        total = per_night * nights if nights else None
    except Exception:
        per_night = None
        total = None

    return {
        "adult_rate": adult_rate,
        "child_rate": child_rate,
        "nights": nights,
        "per_night": per_night,
        "total": total,
        "currency": currency,
    }


# ─── Package price-window matching ────────────────────────────────
# Tiers (best to worst):
#   1 = exact        — window contains the full customer range
#   2 = contains_in  — window contains check_in but not check_out
#   3 = contains_out — window contains check_out but not check_in
#   4 = overlap      — window shares at least one day with the range
#   5 = flexible     — NULL valid_from AND NULL valid_to
#
# Sort within a package: tier ASC, then adult_price ASC.

def _package_price_tier(price_row, check_in, check_out):
    """Return an int tier (1-5) or None if the row doesn't match."""
    from datetime import date as _date

    vf = price_row.valid_from
    vt = price_row.valid_to

    # Flexible: no dates on the row -> always matches (tier 5)
    if vf is None and vt is None:
        return 5

    # Customer didn't give dates -> only flexible rows match
    if check_in is None or check_out is None:
        return None

    lo = vf if vf is not None else _date.min
    hi = vt if vt is not None else _date.max

    if hi < check_in or lo > check_out:
        return None

    inside_in = lo <= check_in
    inside_out = hi >= check_out

    if inside_in and inside_out:
        return 1
    if inside_in and not inside_out:
        return 2
    if not inside_in and inside_out:
        return 3
    return 4


def _package_price_options(package, check_in, check_out):
    """
    Return the ordered list of PackagePrice rows to display.

    Rules (1A / 2A / 3B):
      - Dates present + >=1 dated match: ALL matching dated rows,
        best tier first then cheapest.
      - Dates present + 0 dated match: cheapest flexible row only.
      - No dates: cheapest flexible row only.
    """
    from models import PackagePrice  # local import avoids cycles

    all_rows = list(db.session.scalars(
        select(PackagePrice)
        .where(PackagePrice.package_id == package.id)
        .order_by(PackagePrice.adult_price.asc(), PackagePrice.id.asc())
    ))
    if not all_rows:
        return []

    has_dates = check_in is not None and check_out is not None

    if has_dates:
        dated_matches = []
        flexible_rows = []
        for pr in all_rows:
            tier = _package_price_tier(pr, check_in, check_out)
            if tier is None:
                continue
            if tier == 5:
                flexible_rows.append((tier, pr))
            else:
                dated_matches.append((tier, pr))

        if dated_matches:
            dated_matches.sort(key=lambda t: (t[0], float(t[1].adult_price or 0)))
            return [pr for _, pr in dated_matches]

        if flexible_rows:
            flexible_rows.sort(key=lambda t: float(t[1].adult_price or 0))
            return [flexible_rows[0][1]]

        return []

    # No dates -> cheapest flexible only
    flexible_only = [
        pr for pr in all_rows
        if pr.valid_from is None and pr.valid_to is None
    ]
    if flexible_only:
        return [flexible_only[0]]

    # Fallback: dated-only package -> cheapest of all
    return [all_rows[0]]


# X3 filter marker — added by patch_search_service_x3
def _has_same_month_overlap(price_row, check_in, check_out):
    """
    Return True if the row's window shares a calendar month with the
    customer's [check_in, check_out] range. Flexible rows (NULL dates)
    return False — they don't count as "same-month".
    """
    vf = price_row.valid_from
    vt = price_row.valid_to
    if vf is None and vt is None:
        return False
    if check_in is None or check_out is None:
        return False

    start = min(vf, vt) if (vf is not None and vt is not None) else (vf or vt)
    end = max(vf, vt) if (vf is not None and vt is not None) else (vf or vt)

    def _months(d1, d2):
        out = set()
        y, m = d1.year, d1.month
        while (y, m) <= (d2.year, d2.month):
            out.add((y, m))
            m += 1
            if m > 12:
                m = 1
                y += 1
        return out

    window_months = _months(start, end)
    customer_months = _months(check_in, check_out)
    return bool(window_months & customer_months)


def _dated_windows_for(package, check_in, check_out):
    """Return only the DATED price rows whose window overlaps check_in..check_out."""
    from models import PackagePrice

    rows = list(db.session.scalars(
        select(PackagePrice)
        .where(PackagePrice.package_id == package.id)
        .where(PackagePrice.valid_from.is_not(None))
        .order_by(PackagePrice.adult_price.asc(), PackagePrice.id.asc())
    ))
    if not rows:
        return []

    out = []
    for pr in rows:
        tier = _package_price_tier(pr, check_in, check_out)
        if tier is not None and tier != 5:
            out.append((tier, pr))
    out.sort(key=lambda t: (t[0], float(t[1].adult_price or 0)))
    return [pr for _, pr in out]


# X3-SQL marker — same-month filter applied in SQL
def _search_packages(
    *, destination_id: int | None, check_in: date | None, check_out: date | None,
    adults: int, children: int,
    page: int, per_page: int, sort: str,
    query_text: str | None, ignored: list[str],
) -> tuple[list[dict], int]:
    """
    Package search.

    Date-aware behaviour (X3 rule):
      - When BOTH check_in and check_out are provided, only packages
        that have at least one PackagePrice row whose valid_from /
        valid_to window overlaps the customer's range in the SAME
        calendar month(s) are returned.
      - Total count is computed AFTER this filter, so pagination is
        correct.
      - When no dates are given, all active packages are eligible.
    """
    stmt = select(Package).where(Package.is_active.is_(True))
    if destination_id:
        stmt = stmt.where(Package.destination_id == destination_id)
    if query_text:
        stmt = stmt.where(Package.name.ilike(f"%{query_text}%"))
    stmt = stmt.where(Package.capacity >= (adults + children))

    has_dates = check_in is not None and check_out is not None

    # ─── X3: SQL-level same-month filter ────────────────────────────
    if has_dates:
        month_start = check_in.replace(day=1)
        if check_out.month == 12:
            month_end = check_out.replace(
                year=check_out.year + 1, month=1, day=1
            ) - _td(days=1)
        else:
            month_end = check_out.replace(
                month=check_out.month + 1, day=1
            ) - _td(days=1)

        price_match = (
            select(PackagePrice.id)
            .where(PackagePrice.package_id == Package.id)
            .where(PackagePrice.valid_from.is_not(None))
            .where(PackagePrice.valid_to.is_not(None))
            .where(PackagePrice.valid_from <= month_end)
            .where(PackagePrice.valid_to >= month_start)
            .exists()
        )
        stmt = stmt.where(price_match)

    # ─── total AFTER filter ─────────────────────────────────────────
    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)

    # ─── Sorting ────────────────────────────────────────────────────
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
    rows = db.session.scalars(stmt.limit(per_page).offset(offset)).all()

    from services import availability_service

    items: list[dict] = []
    for p in rows:
        # Capacity check (best-effort)
        try:
            if has_dates:
                remaining = availability_service.package_availability(p.id, check_in)
                if remaining is not None and remaining < (adults + children):
                    continue
        except Exception as exc:
            log.debug("search availability skipped for package %s: %s", p.id, exc)

        # Price windows (best-first). Falls back to cheapest flexible.
        price_options = _package_price_options(p, check_in, check_out)
        if not price_options:
            continue

        best_price_row = price_options[0]

        dest = db.session.get(Destination, p.destination_id) if p.destination_id else None
        pricing = _package_pricing(
            package_id=p.id,
            adults=adults,
            children=children,
            price_row=best_price_row,
        )
        image_url = _first_image_url(getattr(p, "images", None))

        # ─── Package's hotel + room for rich detail ────────────────
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

        items.append({
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "destination_id": p.destination_id,
            "destination_name": dest.name if dest else None,
            "price_adult": (
                float(pricing["adult_price"])
                if pricing["adult_price"] is not None else None
            ),
            "currency": pricing["currency"],
            "image_url": image_url,
            "extra": {
                "duration_nights": p.duration_nights,
                "package_type": p.package_type,
                "code": p.code,
                "hotel_stars": pkg_hotel.stars if pkg_hotel else None,
                "hotel_name": pkg_hotel.name if pkg_hotel else None,
                "room_type": pkg_room.type if pkg_room else None,
                "facilities": pkg_facilities,
                "inclusions": [
                    inc.item for inc in (getattr(p, "inclusions", None) or [])
                ][:6],
                "windows": [
                    {
                        "id": w.id,
                        "valid_from": w.valid_from.isoformat() if w.valid_from else None,
                        "valid_to": w.valid_to.isoformat() if w.valid_to else None,
                        "adult_price": float(w.adult_price) if w.adult_price is not None else None,
                        "child_price": float(w.child_price) if w.child_price is not None else None,
                        "currency": w.currency,
                        "tier": _package_price_tier(w, check_in, check_out),
                    }
                    for w in price_options
                ],
            },
            "price_child": (
                float(pricing["child_price"])
                if pricing["child_price"] is not None else None
            ),
            "nights": (
                max(0, (check_out - check_in).days)
                if (check_in is not None and check_out is not None)
                else p.duration_nights
            ),
            "price_per_night": None,
            "total_price": (
                float(pricing["total"])
                if pricing["total"] is not None else None
            ),
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

    return items, total


def _package_pricing(
    *, package_id: int, adults: int, children: int, price_row=None
) -> dict[str, Any]:
    if price_row is not None:
        row = price_row
    else:
        row = db.session.scalars(
            select(PackagePrice)
            .where(PackagePrice.package_id == package_id)
            .order_by(PackagePrice.id.asc())
            .limit(1)
        ).first()
    if row is None:
        return {"adult_price": None, "child_price": None, "total": None, "currency": "EUR"}
    try:
        total = (row.adult_price * adults) + ((row.child_price or Decimal("0")) * children)
    except Exception:
        total = None
    return {
        "adult_price": row.adult_price,
        "child_price": row.child_price,
        "total": total,
        "currency": row.currency or "EUR",
    }


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
        return {"adult_price": None, "child_price": None, "total": None, "currency": "EUR"}
    try:
        total = (row.adult_price * adults) + ((row.child_price or Decimal("0")) * children)
    except Exception:
        total = None
    return {
        "adult_price": row.adult_price,
        "child_price": row.child_price,
        "total": total,
        "currency": row.currency or "EUR",
    }


def _first_price_for_activity(activity_id: int) -> tuple[Decimal | None, str]:
    row = db.session.scalars(
        select(ActivityPrice)
        .where(ActivityPrice.activity_id == activity_id)
        .order_by(ActivityPrice.id.asc())
        .limit(1)
    ).first()
    if row is None:
        return None, "EUR"
    return row.adult_price, row.currency or "EUR"


def _first_price_for_package(package_id: int) -> tuple[Decimal | None, str]:
    row = db.session.scalars(
        select(PackagePrice)
        .where(PackagePrice.package_id == package_id)
        .order_by(PackagePrice.id.asc())
        .limit(1)
    ).first()
    if row is None:
        return None, "EUR"
    return row.adult_price, row.currency or "EUR"


def _cheapest_room_price(hotel_id: int) -> tuple[Decimal | None, str]:
    row = db.session.scalars(
        select(Room)
        .where(Room.hotel_id == hotel_id)
        .where(Room.is_active.is_(True))
        .where(Room.base_price_per_night.is_not(None))
        .order_by(Room.base_price_per_night.asc())
        .limit(1)
    ).first()
    if row is None:
        return None, "EUR"
    return row.base_price_per_night, "EUR"


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
]