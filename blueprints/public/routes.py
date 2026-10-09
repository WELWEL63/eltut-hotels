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

from flask import render_template
from sqlalchemy import func, select

from blueprints.public import public_bp
from extensions import db
from models import (
    Activity,
    Destination,
    Hotel,
    Package,
)


# ─── Home ──────────────────────────────────────────────────────────
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
    featured_activities = list(
        db.session.scalars(
            select(Activity)
            .where(Activity.is_active.is_(True))
            .order_by(Activity.id)
            .limit(6)
        )
    )
    featured_hotels = list(
        db.session.scalars(
            select(Hotel)
            .where(Hotel.is_active.is_(True))
            .order_by(Hotel.id)
            .limit(3)
        )
    )
    featured_packages = list(
        db.session.scalars(
            select(Package)
            .where(Package.is_active.is_(True))
            .order_by(Package.id)
            .limit(3)
        )
    )
    top_destinations = list(
        db.session.scalars(
            select(Destination).order_by(Destination.name).limit(8)
        )
    )

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
