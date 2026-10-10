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
      product type. We sort by id for determinism and use `limit` to
      keep the query cheap.
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
    Hotel,
    Package,
    PackagePrice,
    Room,
)


# ─── Home ──────────────────────────────────────────────────────────
# ─── Home page helpers ────────────────────────────────────────────
def _cheapest_per_destination(model, price_subquery, limit=6):
    """
    Single-query version — returns up to `limit` items, each from a
    DISTINCT destination, keeping the CHEAPEST one per destination.

    Uses PostgreSQL `DISTINCT ON (destination_id)` — 1 query, fast.
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
        # SQLAlchemy returns the model instance in row[0] when we
        # select(model, ...) inside the subquery
        obj = row[0]
        price = row[-1]
        results.append({
            "obj": obj,
            "price": round(float(price), 2) if price is not None else None,
        })
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
    # ─── Featured content: cheapest per destination, 6 each ───
    try:
        featured_hotels = _cheapest_per_destination(Hotel, _hotel_price_subquery(), limit=6)
    except Exception as exc:
        current_app.logger.warning("featured_hotels failed: %s", exc)
        featured_hotels = []

    try:
        featured_packages = _cheapest_per_destination(Package, _package_price_subquery(), limit=6)
    except Exception as exc:
        current_app.logger.warning("featured_packages failed: %s", exc)
        featured_packages = []

    try:
        featured_activities = _cheapest_per_destination(Activity, _activity_price_subquery(), limit=6)
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
