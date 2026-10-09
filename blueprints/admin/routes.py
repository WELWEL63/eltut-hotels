"""
blueprints/admin/routes.py
──────────────────────────
Admin dashboard — the entry point to the admin panel.

ROUTES
    GET /admin/            dashboard
    GET /admin/about       small "about this build" page (optional)

DESIGN NOTES
    - Every route relies on the blueprint-wide before_request guard
      (blueprints/admin/__init__.py) so we don't have to repeat
      @admin_required on each one. It's applied twice anyway for
      clarity via the decorator.
    - KPI numbers come from services.report_service. That service is
      resilient: Mongo down → returns {"_error": ...} per section
      and the dashboard still renders.
"""

from __future__ import annotations

from flask import current_app, render_template

from blueprints.admin import admin_bp, admin_required

from services import report_service


@admin_bp.route("/")
@admin_required
def index():
    """Admin dashboard with KPI cards and quick-view tables."""
    try:
        data = report_service.summary()
    except Exception as exc:  # noqa: BLE001 — never 500 the dashboard
        current_app.logger.exception("report_service.summary failed: %s", exc)
        data = {"_error": str(exc)}

    # Unpack the top-level sections with safe defaults so the template
    # can render even if a section failed.
    revenue = data.get("revenue") or {}
    bookings = data.get("bookings") or {}
    customers = data.get("customers") or {}
    reviews = data.get("reviews") or {}
    search = data.get("search") or {}
    enquiries = data.get("enquiries") or {}

    return render_template(
        "admin/index.html",
        data=data,
        revenue=revenue,
        bookings=bookings,
        customers=customers,
        reviews=reviews,
        search=search,
        enquiries=enquiries,
    )
