"""
blueprints/public/routes.py
───────────────────────────
Home, About, and Contact pages for the public site.

These are the "front door" pages — the first thing visitors see. They
need to load fast and work without authentication.

ROUTES
    GET /          index        landing page with featured content
    GET /about     about        static about-us page
    GET /contact   contact      contact form (POSTs to enquiry_routes)

DESIGN NOTES
    - Home page queries a small number of featured items from each
      product type. Priority: admin-curated home_offers → cheapest
      per destination fallback.
    - Counts (activities / hotels / packages / destinations) are cheap
      `SELECT COUNT(*)` aggregates — safe to run on every page load.
    - Templates live under templates/public/.
    - No auth required on any of these routes.
"""

from __future__ import annotations

from flask import current_app, render_template
from sqlalchemy import func, select

from blueprints.public import public_bp
from extensions import db
from models import (
    Activity,
    ActivityPrice,
    Destination,
    HomeOffer,
    Hotel,
    Package,
    PackagePrice,
    Room,
    PRODUCT_ACTIVITY,
    PRODUCT_HOTEL,
    PRODUCT_PACKAGE,
)


# ─── Home ──────────────────────────────────────────────────────────
# ─── Home page helpers ────────────────────────────────────────────

# Section keys (mirror models/home_offer.py)
_SECTION_TOP_EXPERIENCE = "top_experience"
_SECTION_BEST_HOTEL = "best_hotel"
_SECTION_AFFORDABLE_PACKAGE = "affordable_package"


def _offers_for_section(section: str, limit: int = 6):
    """
    Read curated home-page offers for a section.

    Returns a list of {"obj": <ORM instance>, "price": float|None}
    dicts (same shape as _cheapest_per_destination), or [] if no
    active offers exist for the section.

    Skips offers whose product has been deleted out from under them.
    """
    rows = (
        db.session.query(HomeOffer)
        .filter(
            HomeOffer.section == section,
            HomeOffer.is_active.is_(True),
        )
        .order_by(HomeOffer.sort_order.asc(), HomeOffer.id.asc())
        .limit(limit)
        .all()
    )
    if not rows:
        return []

    # Group product ids by type, fetch each type once, map back
    model_by_type = {
        PRODUCT_ACTIVITY: Activity,
        PRODUCT_HOTEL: Hotel,
        PRODUCT_PACKAGE: Package,
    }
    ids_by_type: dict[str, list[int]] = {}
    for r in rows:
        ids_by_type.setdefault(r.product_type, []).append(r.product_id)

    products: dict[tuple[str, int], object] = {}
    for ptype, ids in ids_by_type.items():
        model = model_by_type.get(ptype)
        if model is None:
            continue
        for p in db.session.query(model).filter(model.id.in_(ids)).all():
            products[(ptype, p.id)] = p

    out = []
    for r in rows:
        obj = products.get((r.product_type, r.product_id))
        if obj is None:
            # Product was deleted — skip
            continue
        try:
            price = _section_price_for(section, obj.id)
        except Exception:
            price = None
        out.append({
            "obj": obj,
            "price": round(float(price), 2) if price is not None else None,
        })
    return out


def _section_price_for(section: str, product_id: int):
    """Return a Decimal price for a product in a section, or None."""
    if section == _SECTION_TOP_EXPERIENCE:
        sub = (
            select(func.min(ActivityPrice.adult_price))
            .where(ActivityPrice.activity_id == product_id)
            .where(ActivityPrice.adult_price > 0)
        )
    elif section == _SECTION_BEST_HOTEL:
        sub = (
            select(func.min(Room.base_price_per_night))
            .where(Room.hotel_id == product_id, Room.is_active.is_(True),
                   Room.base_price_per_night > 0)
        )
    elif section == _SECTION_AFFORDABLE_PACKAGE:
        sub = (
            select(func.min(PackagePrice.adult_price))
            .where(PackagePrice.package_id == product_id)
        )
    else:
        return None
    return db.session.scalar(sub)


def _cheapest_per_destination(model, price_subquery, limit=6):
    """
    Single-query version — returns up to `limit` items, each from a
    DISTINCT destination, keeping the CHEAPEST one per destination.

    Uses PostgreSQL `DISTINCT ON (destination_id)` — 1 query, fast.

    NOTE
    ----
    The subquery form `select(model, price_subquery).subquery()` flattens
    `model` to its raw column values when wrapped and re-selected, so
    `row[0]` ends up being the model's primary key (an int), not an ORM
    instance. We therefore re-fetch real ORM objects by id afterwards so
    relationship attributes (e.g. `.images`) are populated for templates.
    """
    # Subquery: DISTINCT ON picks the row with the minimum price per destination
    inner = (
        select(model, price_subquery.label("cheapest_price"))
        .where(model.is_active.is_(True))
        .where(price_subquery.is_not(None))
        .where(price_subquery > 0)
        .distinct(model.destination_id)
        .order_by(model.destination_id, price_subquery.asc())
        .subquery()
    )
    # Wrap and re-sort by cheapest_price across all destinations
    rows = db.session.execute(
        select(inner).order_by(inner.c.cheapest_price.asc()).limit(limit)
    ).all()

    results = []
    for row in rows:
        # row[0] is the model's PK (int), NOT an ORM instance
        obj_id = row[0]
        price = row[-1]
        results.append({
            "id": obj_id,
            "price": round(float(price), 2) if price is not None else None,
        })

    # Re-fetch real ORM objects (with relationships like .images)
    # by id, then attach them so the template can use .images, .name, etc.
    if results:
        ids = [r["id"] for r in results]
        objs = {
            m.id: m
            for m in db.session.scalars(
                select(model).where(model.id.in_(ids))
            ).unique().all()
        }
        for r in results:
            r["obj"] = objs.get(r["id"])

    return results


def _hotel_price_subquery():
    """Min active room price for a hotel — as SQL subquery."""
    return (
        select(func.min(Room.base_price_per_night))
        .where(Room.hotel_id == Hotel.id, Room.is_active.is_(True),
               Room.base_price_per_night > 0)
        .correlate(Hotel)
        .scalar_subquery()
    )


def _package_price_subquery():
    """Min PackagePrice.adult_price for a package — as SQL subquery."""
    return (
        select(func.min(PackagePrice.adult_price))
        .where(PackagePrice.package_id == Package.id)
        .correlate(Package)
        .scalar_subquery()
    )


def _activity_price_subquery():
    """Min ActivityPrice.adult_price for an activity — as SQL subquery."""
    return (
        select(func.min(ActivityPrice.adult_price))
        .where(ActivityPrice.activity_id == Activity.id)
        .correlate(Activity)
        .scalar_subquery()
    )


@public_bp.route("/")
def index():
    """
    Landing page.

    Shows:
      - Featured activities (6)
      - Featured hotels (3)
      - Featured packages (3)
      - Top destinations (8)
      - Site-wide counts for the hero band
    """
    # ─── Featured content: curated offers first, fallback to cheapest ───
    try:
        featured_hotels = _offers_for_section(_SECTION_BEST_HOTEL, limit=6)
        if not featured_hotels:
            featured_hotels = _cheapest_per_destination(
                Hotel, _hotel_price_subquery(), limit=6
            )
    except Exception as exc:
        current_app.logger.warning("featured_hotels failed: %s", exc)
        featured_hotels = []

    try:
        featured_packages = _offers_for_section(_SECTION_AFFORDABLE_PACKAGE, limit=6)
        if not featured_packages:
            featured_packages = _cheapest_per_destination(
                Package, _package_price_subquery(), limit=6
            )
    except Exception as exc:
        current_app.logger.warning("featured_packages failed: %s", exc)
        featured_packages = []

    try:
        featured_activities = _offers_for_section(_SECTION_TOP_EXPERIENCE, limit=6)
        if not featured_activities:
            featured_activities = _cheapest_per_destination(
                Activity, _activity_price_subquery(), limit=6
            )
    except Exception as exc:
        current_app.logger.warning("featured_activities failed: %s", exc)
        featured_activities = []

    top_destinations = list(
        db.session.scalars(
            select(Destination).order_by(Destination.name).limit(6)
        )
    )

    # ─── Destination images (admin-managed, best-effort) ───
    destination_images = {}
    try:
        from services import content_service
        destination_images = content_service.all_destination_images()
    except Exception as exc:
        current_app.logger.debug("destination images unavailable: %s", exc)

    counts = {
        "activities": db.session.scalar(
            select(func.count(Activity.id)).where(Activity.is_active.is_(True))
        ) or 0,
        "hotels": db.session.scalar(
            select(func.count(Hotel.id)).where(Hotel.is_active.is_(True))
        ) or 0,
        "packages": db.session.scalar(
            select(func.count(Package.id)).where(Package.is_active.is_(True))
        ) or 0,
        "destinations": db.session.scalar(
            select(func.count(Destination.id))
        ) or 0,
    }

    return render_template(
        "public/index.html",
        destination_images=destination_images,
        featured_activities=featured_activities,
        featured_hotels=featured_hotels,
        featured_packages=featured_packages,
        top_destinations=top_destinations,
        counts=counts,
    )


# ─── About ─────────────────────────────────────────────────────────
@public_bp.route("/about")
def about():
    """Static About-us page."""
    return render_template("public/about.html")


# ─── Contact ───────────────────────────────────────────────────────
@public_bp.route("/contact")
def contact():
    """
    Contact page.

    The form on this page POSTs to /enquiries (handled in
    enquiry_routes.py). This GET handler just renders the page.
    """
    return render_template("public/contact.html")