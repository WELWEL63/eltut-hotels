"""
blueprints/admin/report_routes.py
──────────────────────────────────
Admin reports: KPI dashboard + CSV export.

ROUTES
    GET  /admin/reports           full report view
    GET  /admin/reports/export    CSV download (same data)

DESIGN NOTES
    - All the heavy lifting is done by services.report_service, which
      is resilient: every function returns an {"_error": ...} dict on
      failure instead of raising. We never need a try/except here.
    - The from/to date filter is applied client-side against the
      bookings table (the report service works in months, not dates).
      This keeps report_service unchanged and lets us do ad-hoc ranges.
    - CSV export streams directly from memory; no temp files.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal

from flask import Response, current_app, render_template, request
from sqlalchemy import func, select

from blueprints.admin import admin_bp, admin_required
from extensions import db
from models import Booking
from services import report_service


# ─── Helpers ─────────────────────────────────────────────────────────────
def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _date_range_from_request() -> tuple[datetime.date | None, datetime.date | None]:
    """Default: last 30 days. Overridable via ?from=YYYY-MM-DD&to=YYYY-MM-DD."""
    date_from = _parse_date(request.args.get("from"))
    date_to = _parse_date(request.args.get("to"))
    if date_from is None and date_to is None:
        date_to = datetime.utcnow().date()
        date_from = date_to - timedelta(days=30)
    return date_from, date_to


def _range_stats(date_from, date_to) -> dict:
    """Extra KPIs for the chosen range, computed client-side."""
    stmt = select(Booking)
    if date_from:
        stmt = stmt.where(Booking.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Booking.created_at <= datetime.combine(date_to, datetime.max.time()))

    total_bookings = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)

    # Revenue excludes cancelled and refunded
    rev_stmt = (
        select(func.coalesce(func.sum(Booking.total_amount), 0))
        .where(Booking.status.notin_(["cancelled", "refunded"]))
    )
    if date_from:
        rev_stmt = rev_stmt.where(Booking.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        rev_stmt = rev_stmt.where(Booking.created_at <= datetime.combine(date_to, datetime.max.time()))
    total_revenue = db.session.scalar(rev_stmt) or Decimal("0")

    return {
        "total_bookings": total_bookings,
        "total_revenue": total_revenue,
        "date_from": date_from,
        "date_to": date_to,
    }


# ─── Main report ─────────────────────────────────────────────────────────
@admin_bp.route("/reports")
@admin_required
def report_index():
    """Full reports dashboard."""
    date_from, date_to = _date_range_from_request()
    range_stats = _range_stats(date_from, date_to)

    # Every function below is resilient: returns _error key on failure.
    try:
        data = report_service.summary()
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("report_service.summary failed: %s", exc)
        data = {"_error": str(exc)}

    return render_template(
        "admin/report_index.html",
        data=data,
        revenue=data.get("revenue") or {},
        bookings=data.get("bookings") or {},
        customers=data.get("customers") or {},
        reviews=data.get("reviews") or {},
        search=data.get("search") or {},
        enquiries=data.get("enquiries") or {},
        range_stats=range_stats,
        date_from=date_from.isoformat() if date_from else "",
        date_to=date_to.isoformat() if date_to else "",
    )


# ─── CSV export ──────────────────────────────────────────────────────────
@admin_bp.route("/reports/export")
@admin_required
def report_export():
    """Export the current date-range bookings as CSV."""
    date_from, date_to = _date_range_from_request()

    stmt = select(Booking)
    if date_from:
        stmt = stmt.where(Booking.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Booking.created_at <= datetime.combine(date_to, datetime.max.time()))
    stmt = stmt.order_by(Booking.created_at.asc())

    rows = list(db.session.scalars(stmt))

    # Stream to memory
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "reference", "created_at", "status", "product_type", "product_id",
        "customer_email", "customer_name", "adults", "children",
        "start_date", "end_date", "total_amount", "currency",
    ])
    for b in rows:
        writer.writerow([
            b.reference,
            b.created_at.isoformat() if b.created_at else "",
            b.status,
            b.product_type,
            b.product_id,
            b.guest_email or "",
            b.guest_name or "",
            b.travellers_adults,
            b.travellers_children,
            (b.check_in_date or b.activity_date).isoformat() if (b.check_in_date or b.activity_date) else "",
            b.check_out_date.isoformat() if b.check_out_date else "",
            str(b.total_amount) if b.total_amount is not None else "",
            b.currency,
        ])

    filename = f"bookings_{date_from or 'all'}_{date_to or 'all'}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
