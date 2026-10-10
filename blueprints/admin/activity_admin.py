"""
blueprints/admin/activity_admin.py
──────────────────────────────────
Admin CRUD for activities.

ROUTES
    GET      /admin/activities                list + search + pagination
    GET/POST /admin/activities/new            create
    GET/POST /admin/activities/<int:id>/edit  update
    POST     /admin/activities/<int:id>/toggle  flip is_active
    POST     /admin/activities/<int:id>/delete  hard delete (guarded)

DESIGN NOTES
    - Uses request.form directly (not Flask-WTF) — admin-only surface,
      CSRF still enforced via the hidden csrf_token in every form.
    - Before hard-deleting an activity we check whether any BookingItem
      references it. If so we refuse and suggest deactivation.
    - Every write is logged to Mongo activity_logs (best-effort).
    - Slug is regenerated on name change using
      Activity._generate_unique_slug so it stays unique.
"""

from __future__ import annotations

from datetime import datetime, timezone

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
    Activity,
    ActivityFAQ,
    ActivityPrice,
    ActivityTip,
    BookingItem,
    Destination,
    Guide,
    PRODUCT_TYPE_ACTIVITY,
    VALID_ACTIVITY_CATEGORIES,
    VALID_ACTIVITY_DIFFICULTIES,
    VALID_TRANSPORT_TYPES,
    VALID_MEAL_PLANS,
)


# ─── Logging helper ────────────────────────────────────────────────
def _log(action: str, entity_id, old_value=None, new_value=None):
    """Best-effort write to Mongo activity_logs."""
    try:
        from mongo.logs import log_action
        log_action(
            action=action,
            entity_type="activity",
            entity_id=entity_id,
            user_id=current_user.id,
            user_role="admin",
            old_value=old_value,
            new_value=new_value,
            ip=request.remote_addr,
        )
    except Exception as exc:
        current_app.logger.debug("activity log skipped: %s", exc)


# ─── List ──────────────────────────────────────────────────────────
@admin_bp.route("/activities")
@admin_required
def activity_list():
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 25
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip().lower()
    status = (request.args.get("status") or "").strip().lower()

    stmt = select(Activity)

    if q:
        stmt = stmt.where(Activity.name.ilike(f"%{q}%"))
    if category and category in VALID_ACTIVITY_CATEGORIES:
        stmt = stmt.where(Activity.category == category)
    if status == "active":
        stmt = stmt.where(Activity.is_active.is_(True))
    elif status == "inactive":
        stmt = stmt.where(Activity.is_active.is_(False))

    stmt = stmt.order_by(Activity.id.desc())

    total = int(db.session.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)

    rows = list(db.session.scalars(
        stmt.limit(per_page).offset((page - 1) * per_page)
    ))

    return render_template(
        "admin/activity_list.html",
        items=rows,
        total=total,
        page=page,
        total_pages=total_pages,
        q=q,
        category=category,
        status=status,
        categories=VALID_ACTIVITY_CATEGORIES,
    )


# ─── Form helpers ──────────────────────────────────────────────────
def _apply_form_to_activity(activity: Activity) -> None:
    """Copy fields from request.form onto an Activity instance."""
    f = request.form

    activity.name = (f.get("name") or "").strip() or activity.name
    activity.slug = Activity._generate_unique_slug(
        activity.name, db.session
    )

    # Reference fields
    try:
        activity.destination_id = int(f.get("destination_id") or 0)
    except ValueError:
        pass
    try:
        gid = int(f.get("guide_id") or 0)
        activity.guide_id = gid or None
    except ValueError:
        activity.guide_id = None

    # Enums
    cat = (f.get("category") or "").strip().lower()
    activity.category = cat if cat in VALID_ACTIVITY_CATEGORIES else "other"

    diff = (f.get("difficulty") or "").strip().lower()
    activity.difficulty = (
        diff if diff in VALID_ACTIVITY_DIFFICULTIES else "easy"
    )

    trans = (f.get("transportation_type") or "").strip().lower()
    activity.transportation_type = (
        trans if trans in VALID_TRANSPORT_TYPES else "none"
    )

    meals = (f.get("meals_included") or "").strip().lower()
    activity.meals_included = meals if meals in VALID_MEAL_PLANS else "none"

    # Numerics / strings
    activity.description = (f.get("description") or "").strip() or None
    try:
        activity.duration_hours = float(f.get("duration_hours") or 1)
    except ValueError:
        activity.duration_hours = 1
    try:
        activity.capacity = max(1, int(f.get("capacity") or 1))
    except ValueError:
        activity.capacity = 1

    def _maybe_int(key):
        raw = (f.get(key) or "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    activity.min_age = _maybe_int("min_age")
    activity.max_age = _maybe_int("max_age")

    activity.schedule = (f.get("schedule") or "").strip() or None
    activity.meeting_point = (f.get("meeting_point") or "").strip() or None
    activity.departure_time = (f.get("departure_time") or "").strip() or None
    activity.return_time = (f.get("return_time") or "").strip() or None
    activity.what_to_bring = (f.get("what_to_bring") or "").strip() or None
    activity.cancellation_policy = (
        f.get("cancellation_policy") or ""
    ).strip() or None
    activity.accessibility = (f.get("accessibility") or "").strip() or None
    activity.special_offers = (f.get("special_offers") or "").strip() or None
    activity.is_active = bool(f.get("is_active"))

    # Detail-page content (details upgrade) — all optional free text.
    activity.useful_tips = (f.get("useful_tips") or "").strip() or None
    activity.google_maps_url = (f.get("google_maps_url") or "").strip() or None


def _get_form_choices():
    """Destinations + guides for the form dropdowns."""
    destinations = list(db.session.scalars(
        select(Destination).order_by(Destination.name)
    ))
    guides = list(db.session.scalars(
        select(Guide).where(Guide.is_active.is_(True)).order_by(Guide.full_name)
    ))
    return destinations, guides


# ─── Create ────────────────────────────────────────────────────────
@admin_bp.route("/activities/new", methods=["GET", "POST"])
@admin_required
def activity_new():
    if request.method == "POST":
        # Generate a code if missing
        code = (request.form.get("code") or "").strip()
        if not code:
            # ACT-XXXX based on next id
            next_id = (db.session.scalar(select(func.max(Activity.id))) or 0) + 1
            code = f"ACT-{next_id:04d}"

        existing = db.session.scalar(
            select(Activity).where(Activity.code == code)
        )
        if existing:
            flash(f"An activity with code {code} already exists.", "danger")
            destinations, guides = _get_form_choices()
            return render_template(
                "admin/activity_form.html",
                activity=None,
                destinations=destinations,
                guides=guides,
                categories=VALID_ACTIVITY_CATEGORIES,
                difficulties=VALID_ACTIVITY_DIFFICULTIES,
                transports=VALID_TRANSPORT_TYPES,
                meals=VALID_MEAL_PLANS,
            )

        # Require a destination
        try:
            dest_id = int(request.form.get("destination_id") or 0)
        except ValueError:
            dest_id = 0
        if not dest_id:
            flash("Please select a destination.", "danger")
            destinations, guides = _get_form_choices()
            return render_template(
                "admin/activity_form.html",
                activity=None,
                destinations=destinations,
                guides=guides,
                categories=VALID_ACTIVITY_CATEGORIES,
                difficulties=VALID_ACTIVITY_DIFFICULTIES,
                transports=VALID_TRANSPORT_TYPES,
                meals=VALID_MEAL_PLANS,
            )

        activity = Activity(
            code=code,
            name=(request.form.get("name") or "").strip() or "New activity",
            destination_id=dest_id,
        )
        _apply_form_to_activity(activity)
        db.session.add(activity)
        db.session.flush()

        # Optional price row
        try:
            adult = request.form.get("adult_price")
            child = request.form.get("child_price")
            if adult:
                db.session.add(ActivityPrice(
                    activity_id=activity.id,
                    adult_price=float(adult),
                    child_price=float(child or 0),
                    currency=request.form.get("currency") or "USD",
                ))
        except (ValueError, TypeError):
            pass

        db.session.commit()
        _log("create", activity.id, new_value=activity.name)
        flash(f"Activity '{activity.name}' created.", "success")
        return redirect(url_for("admin.activity_list"))

    # GET — show empty form
    destinations, guides = _get_form_choices()
    return render_template(
        "admin/activity_form.html",
        activity=None,
        destinations=destinations,
        guides=guides,
        categories=VALID_ACTIVITY_CATEGORIES,
        difficulties=VALID_ACTIVITY_DIFFICULTIES,
        transports=VALID_TRANSPORT_TYPES,
        meals=VALID_MEAL_PLANS,
    )


# ─── Edit ──────────────────────────────────────────────────────────
@admin_bp.route("/activities/<int:activity_id>/edit", methods=["GET", "POST"])
@admin_required
def activity_edit(activity_id: int):
    activity = db.session.get(Activity, activity_id)
    if activity is None:
        abort(404)

    if request.method == "POST":
        old_name = activity.name
        _apply_form_to_activity(activity)
        db.session.commit()
        _log("update", activity.id, old_value=old_name, new_value=activity.name)
        flash("Activity updated.", "success")
        return redirect(url_for("admin.activity_list"))

    destinations, guides = _get_form_choices()
    price_row = db.session.scalar(
        select(ActivityPrice)
        .where(ActivityPrice.activity_id == activity.id)
        .order_by(ActivityPrice.id)
        .limit(1)
    )
    faqs = list(db.session.scalars(
        select(ActivityFAQ)
        .where(ActivityFAQ.activity_id == activity.id)
        .order_by(ActivityFAQ.sort_order, ActivityFAQ.id)
    ))
    tips = list(db.session.scalars(
        select(ActivityTip)
        .where(ActivityTip.activity_id == activity.id)
        .order_by(ActivityTip.sort_order, ActivityTip.id)
    ))

    return render_template(
        "admin/activity_form.html",
        activity=activity,
        price=price_row,
        destinations=destinations,
        guides=guides,
        categories=VALID_ACTIVITY_CATEGORIES,
        difficulties=VALID_ACTIVITY_DIFFICULTIES,
        transports=VALID_TRANSPORT_TYPES,
        meals=VALID_MEAL_PLANS,
        faqs=faqs,
        tips=tips,
    )


# ─── Toggle active ─────────────────────────────────────────────────
@admin_bp.route("/activities/<int:activity_id>/toggle", methods=["POST"])
@admin_required
def activity_toggle(activity_id: int):
    activity = db.session.get(Activity, activity_id)
    if activity is None:
        abort(404)
    old = activity.is_active
    activity.is_active = not old
    db.session.commit()
    _log("toggle_active", activity.id, old_value=old, new_value=activity.is_active)
    flash(
        f"Activity {'activated' if activity.is_active else 'deactivated'}.",
        "success",
    )
    return redirect(url_for("admin.activity_list"))


# ─── Delete (guarded) ──────────────────────────────────────────────
@admin_bp.route("/activities/<int:activity_id>/delete", methods=["POST"])
@admin_required
def activity_delete(activity_id: int):
    activity = db.session.get(Activity, activity_id)
    if activity is None:
        abort(404)

    # FK guard: refuse if any booking item references this activity
    refs = int(db.session.scalar(
        select(func.count(BookingItem.id))
        .where(
            BookingItem.product_type == PRODUCT_TYPE_ACTIVITY,
            BookingItem.product_id == activity.id,
        )
    ) or 0)
    if refs > 0:
        flash(
            f"Cannot delete — {refs} booking(s) reference this activity. "
            "Deactivate it instead.",
            "danger",
        )
        return redirect(url_for("admin.activity_list"))

    name = activity.name
    db.session.delete(activity)
    db.session.commit()
    _log("delete", activity_id, old_value=name)
    flash(f"Activity '{name}' deleted.", "success")
    return redirect(url_for("admin.activity_list"))


# --- Activity child rows: FAQs / tips ----------------------------------
# Generic helper so we don't need separate routes for each child type.
_CHILD_TYPES: dict[str, dict] = {
    "faqs": {"model": ActivityFAQ, "field": "question", "label": "FAQ"},
    "tips": {"model": ActivityTip, "field": "tip", "label": "Tip"},
}


def _next_child_sort_order(Model, activity_id: int) -> int:
    """Return max(sort_order) + 1 for an activity child table."""
    current_max = db.session.scalar(
        select(func.coalesce(func.max(Model.sort_order), 0))
        .where(Model.activity_id == activity_id)
    ) or 0
    return int(current_max) + 1


@admin_bp.route("/activities/<int:activity_id>/children/<child_type>/new", methods=["POST"])
@admin_required
def activity_child_new(activity_id: int, child_type: str):
    """Add one row to an activity child table (FAQ or tip)."""
    cfg = _CHILD_TYPES.get(child_type)
    if cfg is None:
        abort(404)
    activity = db.session.get(Activity, activity_id)
    if activity is None:
        abort(404)

    Model = cfg["model"]
    field = cfg["field"]

    if child_type == "faqs":
        question = (request.form.get("question") or "").strip()
        answer = (request.form.get("answer") or "").strip() or None
        if not question:
            flash("Question is required.", "danger")
            return redirect(url_for("admin.activity_edit", activity_id=activity.id))
        row = Model(
            activity_id=activity.id,
            question=question,
            answer=answer,
            sort_order=_next_child_sort_order(Model, activity.id),
        )
    else:
        value = (request.form.get(field) or "").strip()
        if not value:
            flash(f"{cfg['label']} text is required.", "danger")
            return redirect(url_for("admin.activity_edit", activity_id=activity.id))
        row = Model(
            activity_id=activity.id,
            **{field: value},
            sort_order=_next_child_sort_order(Model, activity.id),
        )

    db.session.add(row)
    db.session.commit()
    _log("create", row.id, new_value=activity.id)
    flash(f"{cfg['label']} added.", "success")
    return redirect(url_for("admin.activity_edit", activity_id=activity.id))


@admin_bp.route(
    "/activities/<int:activity_id>/children/<child_type>/<int:row_id>/delete",
    methods=["POST"],
)
@admin_required
def activity_child_delete(activity_id: int, child_type: str, row_id: int):
    """Delete one row from an activity child table."""
    cfg = _CHILD_TYPES.get(child_type)
    if cfg is None:
        abort(404)
    activity = db.session.get(Activity, activity_id)
    if activity is None:
        abort(404)

    Model = cfg["model"]
    row = db.session.get(Model, row_id)
    if row is None or getattr(row, "activity_id", None) != activity.id:
        abort(404)

    db.session.delete(row)
    db.session.commit()
    _log("delete", row_id)
    flash(f"{cfg['label']} deleted.", "success")
    return redirect(url_for("admin.activity_edit", activity_id=activity.id))
