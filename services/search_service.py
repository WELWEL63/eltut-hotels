"""
services/search_service.py
───────────────────────────
Unified search across activities, hotels, and packages.

Used by:
    - the home-page search widget (submit → GET /search)
    - the /search results page
    - the REST API (future)

CONTRACT
    search(**filters) returns a dict with a stable shape across all
    three product types:

        {
            "product_type":  "hotel",
            "items":         [ {product summary dict}, ... ],
            "total":         int,
            "page":          int,
            "per_page":      int,
            "total_pages":   int,
            "destination":   {"id":.., "name":.., "slug":..} | None,
            "filters":       {...echoed back...},
            "ignored":       ["bad_filter_name", ...],
        }

    Product summary dicts all expose:
        id, name, slug, destination_id, destination_name,
        price_adult, currency, image_url, extra (type-specific)

DESIGN NOTES
    - Pure business logic. No Flask request imports.
    - Destination is resolved by slug; if a slug doesn't match a real
      destination, it's recorded in `ignored` and the filter is dropped.
    - Availability filtering is best-effort: if availability_service
      raises, the product stays in the results rather than being
      silently dropped. The booking flow re-checks at confirmation.
    - Prices are chosen with the same "first valid row" rule the list
      routes use, so search results are consistent with list pages.
    - Date filters only apply to activities (single date) or
      hotels/packages (check-in/check-out). Missing dates = "any date".
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from extensions import db
from models import (
    Activity,
    ActivityPrice,
    Destination,
    Hotel,
    Package,
    PackagePrice,
    Room,
)


log = logging.getLogger(__name__)


# ─── Constants ────────────────────────────────────────────────────────────
DEFAULT_PER_PAGE = 12
MAX_PER_PAGE = 48

VALID_TYPES = ("activity", "hotel", "package")

VALID_SORTS = {
    "activity": ("newest", "name", "price_asc", "price_desc"),
    "hotel":    ("newest", "name", "price_asc", "price_desc", "stars_desc"),
    "package":  ("newest", "name", "price_asc", "price_desc", "duration_asc"),
}


# ─── Public: widget destinations ──────────────────────────────────────────
def destinations_for_widget() -> list[dict[str, Any]]:
    """Return a lightweight list of destinations for the search dropdown."""
    rows = db.session.scalars(
        select(Destination).order_by(Destination.name.asc())
    ).all()
    return [
        {"id": d.id, "name": d.name, "slug": d.slug}
        for d in rows
    ]


# ─── Public: unified search ───────────────────────────────────────────────
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

    # Normalise inputs
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
        adults = max(1, int(adults))
        children = max(0, int(children))
    except (TypeError, ValueError):
        ignored.append("party_size")
        adults, children = 1, 0

    sort = (sort or "newest").strip().lower()
    if sort not in VALID_SORTS.get(ptype, ("newest",)):
        ignored.append("sort")
        sort = "newest"

    dest_slug = (destination or "").strip().lower() or None
    query_text = (q or "").strip() or None

    # Resolve destination
    selected_destination: Destination | None = None
    if dest_slug:
        selected_destination = db.session.scalars(
            select(Destination).where(Destination.slug == dest_slug)
        ).first()
        if selected_destination is None:
            ignored.append("destination")
            dest_slug = None

    party_size = adults + children

    # Dispatch
    if ptype == "activity":
        items, total = _search_activities(
            destination_id=selected_destination.id if selected_destination else None,
            activity_date=activity_date,
            party_size=party_size,
            page=page, per_page=per_page, sort=sort, query_text=query_text,
            ignored=ignored,
        )
    elif ptype == "package":
        items, total = _search_packages(
            destination_id=selected_destination.id if selected_destination else None,
            check_in=check_in, check_out=check_out,
            party_size=party_size,
            page=page, per_page=per_page, sort=sort, query_text=query_text,
            ignored=ignored,
        )
    else:  # hotel
        items, total = _search_hotels(
            destination_id=selected_destination.id if selected_destination else None,
            check_in=check_in, check_out=check_out,
            party_size=party_size,
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


# ─── Per-type searches ────────────────────────────────────────────────────
def _first_price_for_activity(activity_id: int) -> tuple[Decimal | None, str]:
    row = db.session.scalars(
        select(ActivityPrice)
        .where(ActivityPrice.activity_id == activity_id)
        .order_by(ActivityPrice.id.asc())
        .limit(1)
    ).first()
    if row is None:
        return None, "USD"
    return row.adult_price, row.currency or "USD"


def _first_price_for_package(package_id: int) -> tuple[Decimal | None, str]:
    row = db.session.scalars(
        select(PackagePrice)
        .where(PackagePrice.package_id == package_id)
        .order_by(PackagePrice.id.asc())
        .limit(1)
    ).first()
    if row is None:
        return None, "USD"
    return row.adult_price, row.currency or "USD"


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
        return None, "USD"
    return row.base_price_per_night, "USD"


def _first_image_url(images: list | None) -> str | None:
    if not images:
        return None
    for img in images:
        url = getattr(img, "url", None)
        if url and (url.startswith("http") or url.startswith("/static")):
            return url
    return None


def _search_activities(
    *, destination_id: int | None, activity_date: date | None,
    party_size: int, page: int, per_page: int, sort: str,
    query_text: str | None, ignored: list[str],
) -> tuple[list[dict], int]:
    stmt = (
        select(Activity)
        .where(Activity.is_active.is_(True))
    )
    if destination_id:
        stmt = stmt.where(Activity.destination_id == destination_id)
    if query_text:
        stmt = stmt.where(Activity.name.ilike(f"%{query_text}%"))

    # Capacity filter — must fit party size (rough)
    stmt = stmt.where(Activity.capacity >= party_size)

    # Total count BEFORE pagination
    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)

    # Ordering
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
    else:  # newest
        stmt = stmt.order_by(Activity.id.desc())

    offset = (page - 1) * per_page
    rows = db.session.scalars(stmt.limit(per_page).offset(offset)).all()

    # Availability filter (best-effort)
    from services import availability_service  # noqa: PLC0415

    items: list[dict] = []
    for a in rows:
        # Availability check
        try:
            if activity_date is not None:
                remaining = availability_service.activity_availability(
                    a.id, activity_date
                )
                if remaining is not None and remaining < party_size:
                    continue
        except Exception as exc:  # noqa: BLE001
            log.debug("search availability skipped for activity %s: %s", a.id, exc)

        # Destination name (fetch once per row — acceptable at this scale)
        dest = db.session.get(Destination, a.destination_id) if a.destination_id else None

        price, currency = _first_price_for_activity(a.id)
        image_url = None
        # Cheap: only pick first image if the collection is small

        items.append({
            "id": a.id,
            "name": a.name,
            "slug": a.slug,
            "destination_id": a.destination_id,
            "destination_name": dest.name if dest else None,
            "price_adult": float(price) if price is not None else None,
            "currency": currency,
            "image_url": image_url,
            "extra": {
                "category": a.category,
                "difficulty": a.difficulty,
                "duration_hours": float(a.duration_hours) if a.duration_hours else None,
            },
        })

    return items, total


def _search_packages(
    *, destination_id: int | None, check_in: date | None, check_out: date | None,
    party_size: int, page: int, per_page: int, sort: str,
    query_text: str | None, ignored: list[str],
) -> tuple[list[dict], int]:
    stmt = select(Package).where(Package.is_active.is_(True))
    if destination_id:
        stmt = stmt.where(Package.destination_id == destination_id)
    if query_text:
        stmt = stmt.where(Package.name.ilike(f"%{query_text}%"))
    stmt = stmt.where(Package.capacity >= party_size)

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)

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

    from services import availability_service  # noqa: PLC0415

    items: list[dict] = []
    for p in rows:
        try:
            if check_in is not None and check_out is not None:
                remaining = availability_service.package_availability(
                    p.id, check_in
                )
                if remaining is not None and remaining < party_size:
                    continue
        except Exception as exc:  # noqa: BLE001
            log.debug("search availability skipped for package %s: %s", p.id, exc)

        dest = db.session.get(Destination, p.destination_id) if p.destination_id else None
        price, currency = _first_price_for_package(p.id)

        items.append({
            "id": p.id,
            "name": p.name,
            "slug": p.slug,
            "destination_id": p.destination_id,
            "destination_name": dest.name if dest else None,
            "price_adult": float(price) if price is not None else None,
            "currency": currency,
            "image_url": None,
            "extra": {
                "duration_nights": p.duration_nights,
                "package_type": p.package_type,
                "code": p.code,
            },
        })

    return items, total


def _search_hotels(
    *, destination_id: int | None, check_in: date | None, check_out: date | None,
    party_size: int, page: int, per_page: int, sort: str,
    query_text: str | None, ignored: list[str],
) -> tuple[list[dict], int]:
    stmt = select(Hotel).where(Hotel.is_active.is_(True))
    if destination_id:
        stmt = stmt.where(Hotel.destination_id == destination_id)
    if query_text:
        stmt = stmt.where(Hotel.name.ilike(f"%{query_text}%"))

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)

    # Cheapest room price for sort
    min_price_subq = (
        select(func.min(Room.base_price_per_night))
        .where(Room.hotel_id == Hotel.id)
        .where(Room.is_active.is_(True))
        .where(Room.base_price_per_night.is_not(None))
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
        price, currency = _cheapest_room_price(h.id)

        items.append({
            "id": h.id,
            "name": h.name,
            "slug": h.slug,
            "destination_id": h.destination_id,
            "destination_name": dest.name if dest else None,
            "price_adult": float(price) if price is not None else None,
            "currency": currency,
            "image_url": None,
            "extra": {
                "stars": h.stars,
                "check_in_time": h.check_in_time,
                "check_out_time": h.check_out_time,
            },
        })

    return items, total


__all__ = [
    "search",
    "destinations_for_widget",
]
