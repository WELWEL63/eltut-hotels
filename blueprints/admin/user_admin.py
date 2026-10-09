"""
blueprints/admin/user_admin.py
───────────────────────────────
Admin user management: list, detail, toggle active, change role.

ROUTES
    GET      /admin/users                    list (filters)
    GET      /admin/users/<int:id>           detail
    POST     /admin/users/<int:id>/toggle    activate / deactivate
    POST     /admin/users/<int:id>/role      change role

DESIGN NOTES
    - No hard delete. Users are deactivated instead, so booking history
      and audit trails remain intact.
    - Role changes and deactivations refuse to touch the last remaining
      admin, and refuse to touch the current user's own account. Both
      guards protect against accidental lockout.
    - Every write is logged to Mongo activity_logs (best-effort).
"""

from __future__ import annotations

from flask import (
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy import func, or_, select

from blueprints.admin import admin_bp, admin_required
from extensions import db
from models import Booking, User


VALID_ROLES = ("customer", "admin")


# ─── Logging ─────────────────────────────────────────────────────────────
def _log(action: str, entity_id, old=None, new=None) -> None:
    try:
        from mongo.logs import log_action
        log_action(
            action=action,
            entity_type="user",
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
def _admin_count() -> int:
    """Return the number of active admins. Used for the last-admin guard."""
    return int(db.session.scalar(
        select(func.count()).select_from(User)
        .where(User.role == "admin")
        .where(User.is_active.is_(True))
    ) or 0)


# ─── List ────────────────────────────────────────────────────────────────
@admin_bp.route("/users")
@admin_required
def user_list():
    """Paginated list with role / active / search filters."""
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 25

    role = (request.args.get("role") or "").strip().lower()
    status = (request.args.get("status") or "").strip().lower()
    q = (request.args.get("q") or "").strip()

    stmt = select(User)

    if role in VALID_ROLES:
        stmt = stmt.where(User.role == role)
    if status == "active":
        stmt = stmt.where(User.is_active.is_(True))
    elif status == "inactive":
        stmt = stmt.where(User.is_active.is_(False))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(like),
                User.full_name.ilike(like),
                User.phone.ilike(like),
            )
        )

    stmt = stmt.order_by(User.id.desc())

    total = int(db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    rows = list(db.session.scalars(stmt.limit(per_page).offset(offset)))

    # Booking count per user, so the list can show "N bookings" cheaply.
    counts: dict[int, int] = {}
    if rows:
        ids = [u.id for u in rows]
        crows = db.session.execute(
            select(Booking.user_id, func.count(Booking.id))
            .where(Booking.user_id.in_(ids))
            .group_by(Booking.user_id)
        ).all()
        counts = {uid: n for uid, n in crows if uid is not None}

    return render_template(
        "admin/user_list.html",
        items=rows,
        counts=counts,
        total=total,
        page=page,
        total_pages=total_pages,
        role=role,
        status=status,
        q=q,
    )


# ─── Detail ──────────────────────────────────────────────────────────────
@admin_bp.route("/users/<int:id>")
@admin_required
def user_detail(id: int):
    """User detail with recent bookings."""
    user = db.session.get(User, id)
    if user is None:
        flash(f"User #{id} not found.", "warning")
        return redirect(url_for("admin.user_list"))

    bookings = list(db.session.scalars(
        select(Booking)
        .where(Booking.user_id == user.id)
        .order_by(Booking.id.desc())
        .limit(50)
    ))

    return render_template(
        "admin/user_detail.html",
        user=user,
        bookings=bookings,
        admin_count=_admin_count(),
    )


# ─── Toggle active ───────────────────────────────────────────────────────
@admin_bp.route("/users/<int:id>/toggle", methods=["POST"])
@admin_required
def user_toggle(id: int):
    """Activate or deactivate a user."""
    user = db.session.get(User, id)
    if user is None:
        flash(f"User #{id} not found.", "warning")
        return redirect(url_for("admin.user_list"))

    # Guard 1: can't deactivate yourself
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("admin.user_detail", id=id))

    # Guard 2: can't deactivate the last active admin
    if user.is_active and user.role == "admin" and _admin_count() <= 1:
        flash("Cannot deactivate the last remaining admin.", "danger")
        return redirect(url_for("admin.user_detail", id=id))

    old = user.is_active
    user.is_active = not user.is_active
    db.session.commit()

    _log("user.toggle_active", user.id, old=old, new=user.is_active)
    flash(
        f"User {user.email} is now {'active' if user.is_active else 'inactive'}.",
        "success",
    )
    return redirect(url_for("admin.user_detail", id=id))


# ─── Change role ─────────────────────────────────────────────────────────
@admin_bp.route("/users/<int:id>/role", methods=["POST"])
@admin_required
def user_role(id: int):
    """Promote a customer to admin, or demote an admin to customer."""
    user = db.session.get(User, id)
    if user is None:
        flash(f"User #{id} not found.", "warning")
        return redirect(url_for("admin.user_list"))

    new_role = (request.form.get("role") or "").strip().lower()
    if new_role not in VALID_ROLES:
        flash(f"Invalid role {new_role!r}.", "danger")
        return redirect(url_for("admin.user_detail", id=id))

    if new_role == user.role:
        flash(f"User is already {new_role}.", "warning")
        return redirect(url_for("admin.user_detail", id=id))

    # Guard 1: can't demote yourself (avoids lockout if you're the last admin)
    if user.id == current_user.id and new_role != "admin":
        flash("You cannot demote your own admin account.", "danger")
        return redirect(url_for("admin.user_detail", id=id))

    # Guard 2: can't demote the last active admin
    if user.role == "admin" and new_role != "admin" and _admin_count() <= 1:
        flash("Cannot demote the last remaining admin.", "danger")
        return redirect(url_for("admin.user_detail", id=id))

    old = user.role
    user.role = new_role
    db.session.commit()

    _log("user.change_role", user.id, old=old, new=new_role)
    flash(f"User {user.email} role changed from {old} to {new_role}.", "success")
    return redirect(url_for("admin.user_detail", id=id))
