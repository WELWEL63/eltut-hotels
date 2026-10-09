"""
blueprints/account/routes.py
────────────────────────────
Account dashboard, my bookings, cancel booking, profile edit.
"""

from __future__ import annotations

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from blueprints.account import account_bp
from blueprints.account.forms import ChangePasswordForm, ProfileForm
from extensions import db

from models import (
    Booking,
    Payment,
)
from services import booking_service


# ─── Dashboard ─────────────────────────────────────────────────────
@account_bp.route("/")
@login_required
def index():
    """Quick overview: recent bookings, count, next trip."""
    recent = list(db.session.scalars(
        __import__("sqlalchemy").select(Booking)
        .where(Booking.user_id == current_user.id)
        .order_by(Booking.created_at.desc())
        .limit(3)
    ))
    total = db.session.scalar(
        __import__("sqlalchemy").select(
            __import__("sqlalchemy").func.count(Booking.id)
        ).where(Booking.user_id == current_user.id)
    ) or 0

    # Upcoming = the earliest confirmed/pending booking
    upcoming = db.session.scalar(
        __import__("sqlalchemy").select(Booking)
        .where(
            Booking.user_id == current_user.id,
            Booking.status.in_(("pending", "confirmed")),
        )
        .order_by(Booking.created_at.desc())
        .limit(1)
    )

    return render_template(
        "account/index.html",
        recent=recent,
        total=total,
        upcoming=upcoming,
    )


# ─── My bookings ───────────────────────────────────────────────────
@account_bp.route("/bookings")
@login_required
def bookings():
    """Paginated list of the customer's bookings."""
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 10

    stmt = (
        __import__("sqlalchemy").select(Booking)
        .where(Booking.user_id == current_user.id)
        .order_by(Booking.created_at.desc())
    )
    total = db.session.scalar(
        __import__("sqlalchemy").select(
            __import__("sqlalchemy").func.count(Booking.id)
        ).where(Booking.user_id == current_user.id)
    ) or 0
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    items = list(db.session.scalars(stmt.limit(per_page).offset(offset)))

    return render_template(
        "account/bookings.html",
        items=items,
        total=total,
        page=page,
        total_pages=total_pages,
    )


# ─── Booking detail ────────────────────────────────────────────────
@account_bp.route("/bookings/<reference>")
@login_required
def booking_detail(reference: str):
    """Detail page for a single booking."""
    booking = db.session.scalar(
        __import__("sqlalchemy").select(Booking)
        .where(Booking.reference == reference)
    )
    if booking is None or booking.user_id != current_user.id:
        abort(404)

    items = list(booking.items) if booking.items else []
    travellers = list(booking.travellers) if booking.travellers else []
    payments = list(db.session.scalars(
        __import__("sqlalchemy").select(Payment)
        .where(Payment.booking_id == booking.id)
        .order_by(Payment.id.desc())
    ))
    history = list(db.session.scalars(
        __import__("sqlalchemy").select(
            __import__("models").BookingStatusHistory
        )
        .where(__import__("models").BookingStatusHistory.booking_id == booking.id)
        .order_by(__import__("models").BookingStatusHistory.created_at.desc())
    ))

    return render_template(
        "account/booking_detail.html",
        booking=booking,
        items=items,
        travellers=travellers,
        payments=payments,
        history=history,
    )


# ─── Cancel booking ────────────────────────────────────────────────
@account_bp.route("/bookings/<reference>/cancel", methods=["POST"])
@login_required
def booking_cancel(reference: str):
    """Customer-initiated cancellation."""
    booking = db.session.scalar(
        __import__("sqlalchemy").select(Booking)
        .where(Booking.reference == reference)
    )
    if booking is None or booking.user_id != current_user.id:
        abort(404)

    if not booking.is_cancellable:
        flash(
            f"This booking is in status '{booking.status}' and cannot be cancelled.",
            "warning",
        )
        return redirect(url_for("account.booking_detail", reference=reference))

    reason = (request.form.get("reason") or "").strip() or "customer cancellation"

    try:
        booking_service.cancel_booking(
            booking,
            reason=reason,
            by_user=current_user,
            role="customer",
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
    except booking_service.InvalidStatusTransition as exc:
        flash(str(exc), "warning")
        return redirect(url_for("account.booking_detail", reference=reference))

    db.session.commit()

    # Fire-and-forget cancellation email
    try:
        from services.email_service import send_booking_cancelled
        send_booking_cancelled(booking, reason=reason)
    except Exception:  # noqa: BLE001
        pass

    flash("Booking cancelled.", "success")
    return redirect(url_for("account.booking_detail", reference=reference))


# ─── Profile ───────────────────────────────────────────────────────
@account_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Edit personal info OR change password (two separate forms)."""
    profile_form = ProfileForm(obj=current_user)
    password_form = ChangePasswordForm()

    # Determine which form was submitted by looking for its unique field
    if "current_password" in request.form:
        if password_form.validate_on_submit():
            if not current_user.check_password(password_form.current_password.data):
                flash("Current password is incorrect.", "danger")
                return render_template(
                    "account/profile.html",
                    profile_form=profile_form,
                    password_form=password_form,
                )
            current_user.set_password(password_form.new_password.data)
            db.session.commit()
            flash("Password changed.", "success")
            return redirect(url_for("account.profile"))
        # Fall through with validation errors
        return render_template(
            "account/profile.html",
            profile_form=profile_form,
            password_form=password_form,
        )

    if profile_form.validate_on_submit():
        current_user.full_name = profile_form.full_name.data.strip()
        current_user.phone = (profile_form.phone.data or "").strip() or None
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("account.profile"))

    return render_template(
        "account/profile.html",
        profile_form=profile_form,
        password_form=password_form,
    )
