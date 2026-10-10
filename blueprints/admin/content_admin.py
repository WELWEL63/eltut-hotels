"""
blueprints/admin/content_admin.py
──────────────────────────────────
Admin CRUD for the `site_content` key/value store.

ROUTES
    GET      /admin/content                    list (grouped by page)
    GET      /admin/content/edit/<key>         edit one key
    POST     /admin/content/edit/<key>         save
    POST     /admin/content/seed               backfill missing registry keys
    POST     /admin/content/reset/<key>        reset to code default (value=NULL)

DESIGN NOTES
    - Uses services.content_service for every read/write. This keeps
      the cache-invalidation logic in one place.
    - `key` is passed in the URL with dots (e.g. home.hero.title).
      Flask's default converter handles dots fine.
    - Reset sets value=NULL; the resolution chain falls back to the
      registry default, so pages never go blank.
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
from sqlalchemy import select

from blueprints.admin import admin_bp, admin_required
from extensions import db
from models import SiteContent
from services import content_service


# ─── Logging ──────────────────────────────────────────────────────────────
def _log(action: str, entity_id: str, old=None, new=None) -> None:
    try:
        from mongo.logs import log_action
        log_action(
            action=action,
            entity_type="site_content",
            entity_id=str(entity_id),
            user_id=current_user.id,
            user_role="admin",
            old_value=old,
            new_value=new,
            ip=request.remote_addr,
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.debug("log skipped: %s", exc)


# ─── List ─────────────────────────────────────────────────────────────────
@admin_bp.route("/content")
@admin_required
def content_index():
    """List every site_content row, grouped by page."""
    grouped = content_service.by_page()
    total = db.session.scalar(
        select(db.func.count()).select_from(SiteContent)
    ) or 0

    # Also compute which registry keys are missing a row (for the
    # "seed" hint banner).
    existing_keys = set(db.session.scalars(select(SiteContent.key)).all())
    missing = [k for k in content_service.registry().keys() if k not in existing_keys]

    return render_template(
        "admin/content_index.html",
        grouped=grouped,
        total=total,
        missing=missing,
        registry=content_service.registry(),
    )


# ─── Edit one ─────────────────────────────────────────────────────────────
@admin_bp.route("/content/edit/<path:key>", methods=["GET", "POST"])
@admin_required
def content_edit(key: str):
    """Edit a single content key."""
    spec = content_service.registry().get(key)

    row = db.session.scalars(
        select(SiteContent).where(SiteContent.key == key)
    ).first()

    if row is None:
        # Key hasn't been seeded yet — create it on the fly using the
        # registry spec (if known), else create a generic row.
        if spec is None:
            flash(f"Unknown content key: {key}", "warning")
            return redirect(url_for("admin.content_index"))
        row = SiteContent(
            key=spec.key,
            value=None,
            content_type=spec.content_type,
            page=spec.page,
            label=spec.label,
            notes=spec.notes,
            sort_order=spec.sort_order,
        )
        db.session.add(row)
        db.session.commit()
        flash(f"Created missing key {key}.", "success")

    if request.method == "POST":
        new_value = (request.form.get("value") or "").rstrip()
        old_value = row.value

        # Coerce empty string to NULL so the "reset" semantics apply.
        row.value = new_value or None
        if current_user and getattr(current_user, "id", None):
            row.updated_by_user_id = current_user.id
        db.session.commit()

        # Bust the in-request cache so subsequent renders see the new value
        content_service.clear_cache()

        _log("content.update", key, old=old_value, new=row.value)
        flash(f"Updated {key}.", "success")
        return redirect(url_for("admin.content_edit", key=key))

    # Determine effective value for display (DB value or fallback).
    effective_value = row.value
    if effective_value is None and spec is not None:
        effective_value = spec.default

    # Editor type comes from the registry when available (the DB row
    # may lag behind registry changes). Fall back to row.content_type
    # for unknown keys.
    editor_type = spec.content_type if spec else row.content_type

    return render_template(
        "admin/content_edit.html",
        row=row,
        spec=spec,
        editor_type=editor_type,
        effective_value=effective_value or "",
    )


# ─── Reset to default ─────────────────────────────────────────────────────
@admin_bp.route("/content/reset/<path:key>", methods=["POST"])
@admin_required
def content_reset(key: str):
    """Reset a key to its registry default by setting value=NULL."""
    row = db.session.scalars(
        select(SiteContent).where(SiteContent.key == key)
    ).first()
    if row is None:
        flash(f"Unknown content key: {key}", "warning")
        return redirect(url_for("admin.content_index"))

    old_value = row.value
    row.value = None
    if current_user and getattr(current_user, "id", None):
        row.updated_by_user_id = current_user.id
    db.session.commit()
    content_service.clear_cache()

    _log("content.reset", key, old=old_value, new=None)
    flash(f"Reset {key} to the code default.", "success")
    return redirect(url_for("admin.content_edit", key=key))


# ─── Seed missing keys ────────────────────────────────────────────────────
@admin_bp.route("/content/seed", methods=["POST"])
@admin_required
def content_seed():
    """Insert any registry key that doesn't have a row yet."""
    created = content_service.seed_defaults()
    content_service.clear_cache()
    if created:
        _log("content.seed", "batch", new={"created": created})
        flash(f"Seeded {created} new content key(s).", "success")
    else:
        flash("No missing keys to seed.", "info")
    return redirect(url_for("admin.content_index"))
