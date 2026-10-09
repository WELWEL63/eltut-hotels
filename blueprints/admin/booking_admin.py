"""
blueprints/admin/booking_admin.py
──────────────────────────────────
Admin booking management: list, detail, status transitions, cancel.

ROUTES
    GET      /admin/bookings                       list (filters)
    GET      /admin/bookings/<reference>           detail
    POST     /admin/bookings/<reference>/status    change status
    POST     /admin/bookings/<reference>/cancel    cancel booking

DESIGN NOTES
    - Status changes go through services.booking_service.mark_* helpers
      (mark_confirmed, mark_completed, mark_refunded) so the audit trail
      in booking_status_history is written consistently.
    - Cancel goes through booking_service.cancel_booking() so the
      cancelled_at + cancellation_reason columns are set.
    - Every action is logged to Mongo activity_logs (best-effort).
    - Reason field is required for status changes so the audit trail
      has context (who did what and why).
"""

from __future__ import annotations

from datetime import datetime

from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy import func, select

from blueprints.admin import admin_bp, admin_required
from extensions import db
from models import (
    Booking,
    BookingItem,
    BookingStatusHistory,
    BookingTraveller,
    Payment,
)
from services import booking_service


VALID_STATUS_FILTERS = ("pending", "confirmed", "cancelled", "completed")
VALID_PRODUCT_TYPES = ("activity", "hotel", "package")

# Statuses that can be set from the admin detail page.
# The exact map controls which buttons appear in the template.
STATUS_TRANSITIONS: dict[str, list[str]] = {
    "pending":   ["confirmed", "cancelled"],
    "confirmed": ["completed", "cancelled"],
    "cancelled": [],
    "completed": ["refunded"],
}


# ─── Logging ─────────────────────────────────────────────────────────────
def _log(action: str, entity_id, old=None, new=None) -> None:
    """Best-effort audit log to Mongo. Never raises."""
    try:
        from mongo.logs import log_action
        log_action(
            action=action,
            entity_type="booking",
            entity_id=str(entity_id),
            user_id=current_user.id,
            user_role="admin",
            old_value=old,
            new_value=new,
            ip=request.remote_addr,
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.debug("log skipped: %s", exc)


# ─── Helpers ─────────────────────────────────────────────────────────────
def _parse_date(value: str | None):
    """Parse YYYY-MM-DD from a filter param. Returns date|None."""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# ─── List ────────────────────────────────────────────────────────────────
@admin_bp.route("/bookings")
@admin_required
def booking_list():
    """Paginated list with filters: status, product_type, date range, q."""
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 25

    status = (request.args.get("status") or "").strip().lower()
    product_type = (request.args.get("product_type") or "").strip().lower()
    q = (request.args.get("q") or "").strip()
    date_from = _parse_date(request.args.get("from"))
    date_to = _parse_date(request.args.get("to"))

    stmt = select(Booking)

    if status in VALID_STATUS_FILTERS:
        stmt = stmt.where(Booking.status == status)
    if product_type in VALID_PRODUCT_TYPES:
        stmt = stmt.where(Booking.product_type == product_type)
    if q:
        # Match reference exactly OR email/name partially. Reference is
        # the fastest lookup; email is a nice-to-have for staff.
        like = f"%{q}%"
        stmt = stmt.where(
            (Booking.reference.ilike(like))
            | (Booking.guest_email.ilike(like))
            | (Booking.guest_name.ilike(like))
        )
    if date_from:
        stmt = stmt.where(Booking.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Booking.created_at <= datetime.combine(date_to, datetime.max.time()))

    stmt = stmt.order_by(Booking.id.desc())

    total = int(db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    rows = list(db.session.scalars(stmt.limit(per_page).offset(offset)))

    # Compute total booked amount for the current filter (a helpful stat)
    sum_stmt = select(func.coalesce(func.sum(Booking.total_amount), 0))
    if status in VALID_STATUS_FILTERS:
        sum_stmt = sum_stmt.where(Booking.status == status)
    if product_type in VALID_PRODUCT_TYPES:
        sum_stmt = sum_stmt.where(Booking.product_type == product_type)
    if date_from:
        sum_stmt = sum_stmt.where(Booking.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        sum_stmt = sum_stmt.where(Booking.created_at <= datetime.combine(date_to, datetime.max.time()))
    filtered_total = db.session.scalar(sum_stmt) or 0

    return render_template(
        "admin/booking_list.html",
        items=rows,
        total=total,
        page=page,
        total_pages=total_pages,
        status=status,
        product_type=product_type,
        q=q,
        date_from=request.args.get("from") or "",
        date_to=request.args.get("to") or "",
        filtered_total=filtered_total,
    )


# ─── Detail ──────────────────────────────────────────────────────────────
@admin_bp.route("/bookings/<reference>")
@admin_required
def booking_detail(reference: str):
    """Full detail view: header, items, travellers, payments, history."""
    booking = db.session.scalars(
        select(Booking).where(Booking.reference == reference)
    ).first()
    if booking is None:
        flash(f"Booking {reference!r} not found.", "warning")
        return redirect(url_for("admin.booking_list"))

    items = list(db.session.scalars(
        select(BookingItem)
        .where(BookingItem.booking_id == booking.id)
        .order_by(BookingItem.id.asc())
    ))
    travellers = list(db.session.scalars(
        select(BookingTraveller)
        .where(BookingTraveller.booking_id == booking.id)
        .order_by(BookingTraveller.sort_order.asc().nullslast(), BookingTraveller.id.asc())
    ))
    payments = list(db.session.scalars(
        select(Payment)
        .where(Payment.booking_id == booking.id)
        .order_by(Payment.id.desc())
    ))
    history = list(db.session.scalars(
        select(BookingStatusHistory)
        .where(BookingStatusHistory.booking_id == booking.id)
        .order_by(BookingStatusHistory.created_at.asc())
    ))

    return render_template(
        "admin/booking_detail.html",
        booking=booking,
        items=items,
        travellers=travellers,
        payments=payments,
        history=history,
        allowed_next=STATUS_TRANSITIONS.get(booking.status, []),
    )


# ─── Status change ───────────────────────────────────────────────────────
@admin_bp.route("/bookings/<reference>/status", methods=["POST"])
@admin_required
def booking_status(reference: str):
    """Transition a booking to a new status via booking_service."""
    booking = db.session.scalars(
        select(Booking).where(Booking.reference == reference)
    ).first()
    if booking is None:
        flash(f"Booking {reference!r} not found.", "warning")
        return redirect(url_for("admin.booking_list"))

    target = (request.form.get("status") or "").strip().lower()
    reason = (request.form.get("reason") or "").strip() or None

    allowed = STATUS_TRANSITIONS.get(booking.status, [])
    if target not in allowed:
        flash(f"Cannot move booking from {booking.status!r} to {target!r}.", "danger")
        return redirect(url_for("admin.booking_detail", reference=reference))

    if not reason:
        flash("A reason is required for status changes (for the audit trail).", "danger")
        return redirect(url_for("admin.booking_detail", reference=reference))

    old_status = booking.status
    try:
        if target == "confirmed":
            # mark_confirmed has no reason= kwarg (checked against the
            # service signature). The reason is captured in the audit log.
            booking_service.mark_confirmed(booking, by_user=current_user, role="admin", ip=request.remote_addr)
        elif target == "completed":
            booking_service.mark_completed(booking, by_user=current_user, role="admin", ip=request.remote_addr)
        elif target == "refunded":
            booking_service.mark_refunded(booking, by_user=current_user, role="admin", reason=reason, ip=request.remote_addr)
        elif target == "cancelled":
            booking_service.cancel_booking(booking, by_user=current_user, role="admin", reason=reason, ip=request.remote_addr)
        else:
            flash(f"Unsupported target status {target!r}.", "danger")
            return redirect(url_for("admin.booking_detail", reference=reference))
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        current_app.logger.exception("status change failed: %s", exc)
        flash(f"Status change failed: {exc}", "danger")
        return redirect(url_for("admin.booking_detail", reference=reference))

    # Reason is included in the log so it survives even when the
    # service helper has no reason= parameter (mark_confirmed,
    # mark_completed).
    _log(
        "booking.status_changed",
        booking.id,
        old=old_status,
        new={"status": target, "reason": reason},
    )
    flash(f"Booking {reference} moved from {old_status} to {target}.", "success")
    return redirect(url_for("admin.booking_detail", reference=reference))


# ─── Cancel shortcut ────────────────────────────────────────────────────
@admin_bp.route("/bookings/<reference>/cancel", methods=["POST"])
@admin_required
def booking_cancel(reference: str):
    """Cancel a booking (shortcut for the common case)."""
    booking = db.session.scalars(
        select(Booking).where(Booking.reference == reference)
    ).first()
    if booking is None:
        flash(f"Booking {reference!r} not found.", "warning")
        return redirect(url_for("admin.booking_list"))

    if booking.status in ("cancelled", "completed"):
        flash(f"Booking is already {booking.status}; cannot cancel.", "warning")
        return redirect(url_for("admin.booking_detail", reference=reference))

    reason = (request.form.get("reason") or "").strip() or "Cancelled by admin"
    old_status = booking.status
    try:
        booking_service.cancel_booking(booking, by_user=current_user, role="admin", reason=reason, ip=request.remote_addr)
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        current_app.logger.exception("cancel failed: %s", exc)
        flash(f"Cancel failed: {exc}", "danger")
        return redirect(url_for("admin.booking_detail", reference=reference))

    _log("booking.cancelled", booking.id, old=old_status, new="cancelled")
    flash(f"Booking {reference} cancelled.", "success")
    return redirect(url_for("admin.booking_detail", reference=reference))
