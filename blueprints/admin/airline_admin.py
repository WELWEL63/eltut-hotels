"""
blueprints/admin/airline_admin.py
──────────────────────────────────
Admin CRUD for the airline master list.

ROUTES
    GET      /admin/airlines                    list (with logos)
    GET/POST /admin/airlines/new                create
    GET/POST /admin/airlines/<id>/edit          edit
    POST     /admin/airlines/<id>/logo          upload logo
    POST     /admin/airlines/<id>/logo/delete   clear logo
    POST     /admin/airlines/<id>/toggle        flip is_active
    POST     /admin/airlines/<id>/delete        delete (guarded)

DESIGN NOTES
    - Logos go to static/images/airlines/<sha1>.<ext> — same SHA-1
      scheme as product media, so uploads are deduplicated and safe.
    - Delete refuses if any Flight row references this airline by name
      (case-insensitive). Prefer deactivation.
    - Every write is logged to Mongo activity_logs (best-effort).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from flask import (
    abort,
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
    Airline,
    Flight,
    VALID_AIRLINE_LOGO_EXT,
    DEFAULT_AIRLINE_LOGO_EXT,
)


ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}
MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB


# ─── Logging ─────────────────────────────────────────────────────────────
def _log(action: str, entity_id, old=None, new=None) -> None:
    try:
        from mongo.logs import log_action
        log_action(
            action=action,
            entity_type="airline",
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
def _logo_dir() -> Path:
    """Resolve static/images/airlines/ and ensure it exists."""
    path = Path(current_app.root_path) / "static" / "images" / "airlines"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _apply_form(airline: Airline) -> None:
    """Copy editable fields from request.form onto the row."""
    f = request.form
    airline.name = (f.get("name") or "").strip() or airline.name
    airline.country = (f.get("country") or "").strip() or None
    airline.notes = (f.get("notes") or "").strip() or None
    airline.is_active = bool(f.get("is_active"))


def _count_referencing_flights(airline: Airline) -> int:
    """Return how many Flight rows reference this airline by name."""
    if not airline.name:
        return 0
    stmt = select(func.count()).select_from(Flight).where(
        func.lower(Flight.airline_name) == airline.name.lower()
    )
    return int(db.session.scalar(stmt) or 0)


# ─── List ────────────────────────────────────────────────────────────────
@admin_bp.route("/airlines")
@admin_required
def airline_list():
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 40
    q = (request.args.get("q") or "").strip()

    stmt = select(Airline)
    if q:
        stmt = stmt.where(Airline.name.ilike(f"%{q}%"))
    stmt = stmt.order_by(Airline.name.asc())

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    rows = list(db.session.scalars(stmt.limit(per_page).offset(offset)))

    # Reference count for each airline (for the delete guard hint)
    ref_counts: dict[int, int] = {}
    for a in rows:
        ref_counts[a.id] = _count_referencing_flights(a)

    return render_template(
        "admin/airline_list.html",
        items=rows,
        ref_counts=ref_counts,
        total=total,
        page=page,
        total_pages=total_pages,
        q=q,
    )


# ─── Create ──────────────────────────────────────────────────────────────
@admin_bp.route("/airlines/new", methods=["GET", "POST"])
@admin_required
def airline_new():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("Airline name is required.", "danger")
            return redirect(url_for("admin.airline_new"))

        existing = db.session.scalars(
            select(Airline).where(func.lower(Airline.name) == name.lower())
        ).first()
        if existing:
            flash(f"An airline named '{name}' already exists.", "warning")
            return redirect(url_for("admin.airline_edit", airline_id=existing.id))

        airline = Airline(name=name)
        _apply_form(airline)
        # Ensure slug is generated (SlugMixin gives the helper)
        airline.slug = Airline._generate_unique_slug(airline.name, db.session)
        db.session.add(airline)
        db.session.commit()

        _log("create", airline.id, new=airline.name)
        flash(f"Airline '{airline.name}' created. Upload a logo below.", "success")
        return redirect(url_for("admin.airline_edit", airline_id=airline.id))

    return render_template("admin/airline_form.html", airline=None)


# ─── Edit ────────────────────────────────────────────────────────────────
@admin_bp.route("/airlines/<int:airline_id>/edit", methods=["GET", "POST"])
@admin_required
def airline_edit(airline_id: int):
    airline = db.session.get(Airline, airline_id)
    if airline is None:
        abort(404)

    if request.method == "POST":
        old_name = airline.name
        _apply_form(airline)
        # If the name changed, regenerate slug (uniqueness-aware)
        if airline.name != old_name:
            airline.slug = Airline._generate_unique_slug(airline.name, db.session)
        db.session.commit()
        _log("update", airline.id, old=old_name, new=airline.name)
        flash("Airline updated.", "success")
        return redirect(url_for("admin.airline_edit", airline_id=airline.id))

    ref_count = _count_referencing_flights(airline)
    return render_template(
        "admin/airline_form.html",
        airline=airline,
        ref_count=ref_count,
    )


# ─── Toggle active ───────────────────────────────────────────────────────
@admin_bp.route("/airlines/<int:airline_id>/toggle", methods=["POST"])
@admin_required
def airline_toggle(airline_id: int):
    airline = db.session.get(Airline, airline_id)
    if airline is None:
        abort(404)
    old = airline.is_active
    airline.is_active = not airline.is_active
    db.session.commit()
    _log("toggle_active", airline.id, old=old, new=airline.is_active)
    flash(
        f"'{airline.name}' is now {'active' if airline.is_active else 'inactive'}.",
        "success",
    )
    return redirect(url_for("admin.airline_list"))


# ─── Logo upload ─────────────────────────────────────────────────────────
@admin_bp.route("/airlines/<int:airline_id>/logo", methods=["POST"])
@admin_required
def airline_logo_upload(airline_id: int):
    airline = db.session.get(Airline, airline_id)
    if airline is None:
        abort(404)

    file = request.files.get("file")
    if file is None or not file.filename:
        flash("Please choose a file.", "danger")
        return redirect(url_for("admin.airline_edit", airline_id=airline.id))

    ext = Path(file.filename).suffix.lower()
    if ext not in VALID_AIRLINE_LOGO_EXT:
        flash(f"Unsupported extension '{ext}'. Allowed: {', '.join(VALID_AIRLINE_LOGO_EXT)}", "danger")
        return redirect(url_for("admin.airline_edit", airline_id=airline.id))

    # MIME check (SVG often reports image/svg+xml; some browsers say octet-stream)
    if file.mimetype and file.mimetype not in ALLOWED_MIME and file.mimetype != "application/octet-stream":
        flash(f"Unsupported MIME type: {file.mimetype}", "danger")
        return redirect(url_for("admin.airline_edit", airline_id=airline.id))

    data = file.read()
    if not data:
        flash("File is empty.", "danger")
        return redirect(url_for("admin.airline_edit", airline_id=airline.id))
    if len(data) > MAX_LOGO_BYTES:
        flash(f"File too large ({len(data)} bytes > {MAX_LOGO_BYTES}).", "danger")
        return redirect(url_for("admin.airline_edit", airline_id=airline.id))

    # SHA-1 filename — dedupe, path-traversal-safe
    digest = hashlib.sha1(data).hexdigest()
    filename = f"{digest}{ext}"
    target = _logo_dir() / filename
    if not target.exists():
        target.write_bytes(data)

    old = airline.logo_url
    airline.logo_url = f"/static/images/airlines/{filename}"
    db.session.commit()

    _log("upload_logo", airline.id, old=old, new=airline.logo_url)
    flash(f"Logo uploaded for '{airline.name}'.", "success")
    return redirect(url_for("admin.airline_edit", airline_id=airline.id))


@admin_bp.route("/airlines/<int:airline_id>/logo/delete", methods=["POST"])
@admin_required
def airline_logo_delete(airline_id: int):
    airline = db.session.get(Airline, airline_id)
    if airline is None:
        abort(404)
    old = airline.logo_url
    airline.logo_url = None
    db.session.commit()
    _log("clear_logo", airline.id, old=old, new=None)
    flash("Logo removed.", "success")
    return redirect(url_for("admin.airline_edit", airline_id=airline.id))


# ─── Delete ──────────────────────────────────────────────────────────────
@admin_bp.route("/airlines/<int:airline_id>/delete", methods=["POST"])
@admin_required
def airline_delete(airline_id: int):
    airline = db.session.get(Airline, airline_id)
    if airline is None:
        abort(404)

    ref = _count_referencing_flights(airline)
    if ref:
        flash(
            f"Cannot delete — {ref} flight(s) reference '{airline.name}'. "
            "Deactivate it instead.",
            "danger",
        )
        return redirect(url_for("admin.airline_edit", airline_id=airline.id))

    name = airline.name
    db.session.delete(airline)
    db.session.commit()
    _log("delete", airline_id, old=name)
    flash(f"Airline '{name}' deleted.", "success")
    return redirect(url_for("admin.airline_list"))
