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
from models import SiteContent, SLIDESHOW_SLOT_COUNT
from services import content_service
import hashlib
from pathlib import Path
from flask import current_app
from werkzeug.utils import secure_filename


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


# ─── Home slideshow editor ─────────────────────────────────────────────
ALLOWED_SLIDESHOW_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_SLIDESHOW_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_SLIDESHOW_BYTES = 10 * 1024 * 1024  # 10 MB


def _slideshow_dir() -> Path:
    """Return the upload directory and ensure it exists."""
    rel = current_app.config.get("UPLOAD_FOLDER", "static/images/uploads")
    path = Path(current_app.root_path) / rel
    path.mkdir(parents=True, exist_ok=True)
    return path


@admin_bp.route("/content/slideshow")
@admin_required
def content_slideshow():
    """Dedicated editor for the home page hero slideshow.

    Passes per-slot property dicts (image + text + style) plus the
    preset catalogue and style field names so the template can render
    every control without any DB access of its own.
    """
    # Ensure every slideshow key has a row (image + all text + style keys)
    existing = set(db.session.scalars(select(SiteContent.key)).all())
    for i in range(1, SLIDESHOW_SLOT_COUNT + 1):
        # Legacy image key
        img_key = f"home.slideshow.slide.{i}"
        if img_key not in existing:
            db.session.add(SiteContent(
                key=img_key,
                page="slideshow",
                label=f"Slide {i} — image",
                content_type="image_url",
                sort_order=i * 100,
            ))

        # New keys: content + style
        for suffix in ("eyebrow", "title", "subtitle", "cta_text", "cta_url"):
            k = f"home.slideshow.slide.{i}.{suffix}"
            if k not in existing:
                db.session.add(SiteContent(
                    key=k, page="slideshow",
                    label=f"Slide {i} — {suffix.replace('_', ' ')}",
                    content_type="html" if suffix in ("title", "subtitle") else "text",
                    sort_order=i * 100 + {"eyebrow": 1, "title": 2, "subtitle": 3, "cta_text": 4, "cta_url": 5}[suffix],
                ))

        for field in ("title", "subtitle"):
            for j, style in enumerate(content_service.SLIDE_STYLE_FIELDS):
                k = f"home.slideshow.slide.{i}.{field}_{style}"
                if k not in existing:
                    db.session.add(SiteContent(
                        key=k, page="slideshow",
                        label=f"Slide {i} — {field} · {style.replace('_', ' ')}",
                        content_type="text",
                        sort_order=i * 100 + (10 if field == "title" else 20) + j,
                    ))
    db.session.commit()
    content_service.clear_cache()

    # Build per-slot property dicts from the service
    slides = {s["slot"]: s for s in content_service.slideshow_slides()}

    # Fill in missing slots (no image yet) with empty dicts
    slots_data: dict[int, dict] = {}
    for i in range(1, SLIDESHOW_SLOT_COUNT + 1):
        slots_data[i] = slides.get(i) or {
            "slot": i,
            "image_url": "",
            "eyebrow": "",
            "title": "",
            "title_style": {k: "" for k in content_service.SLIDE_STYLE_FIELDS},
            "subtitle": "",
            "subtitle_style": {k: "" for k in content_service.SLIDE_STYLE_FIELDS},
            "cta_text": "",
            "cta_url": "",
        }

    return render_template(
        "admin/content_slideshow.html",
        slots_data=slots_data,
        slot_count=SLIDESHOW_SLOT_COUNT,
        active_count=sum(1 for s in slots_data.values() if s.get("image_url")),
        presets=content_service.SLIDE_PRESETS,
        style_fields=content_service.SLIDE_STYLE_FIELDS,
    )


@admin_bp.route("/content/slideshow/<int:slot>/upload", methods=["POST"])
@admin_required
def content_slideshow_upload(slot: int):
    """Upload or replace the image for one slideshow slot."""
    if slot < 1 or slot > SLIDESHOW_SLOT_COUNT:
        abort(404)

    file = request.files.get("file")
    if file is None or not file.filename:
        flash("Please choose a file.", "danger")
        return redirect(url_for("admin.content_slideshow"))

    if file.mimetype not in ALLOWED_SLIDESHOW_MIME:
        flash(f"Unsupported MIME type: {file.mimetype}", "danger")
        return redirect(url_for("admin.content_slideshow"))

    ext = Path(secure_filename(file.filename)).suffix.lower()
    if ext not in ALLOWED_SLIDESHOW_EXT:
        flash(f"Unsupported extension: {ext}", "danger")
        return redirect(url_for("admin.content_slideshow"))

    data = file.read()
    if not data:
        flash("File is empty.", "danger")
        return redirect(url_for("admin.content_slideshow"))

    if len(data) > MAX_SLIDESHOW_BYTES:
        flash(f"File too large (>{MAX_SLIDESHOW_BYTES} bytes).", "danger")
        return redirect(url_for("admin.content_slideshow"))

    digest = hashlib.sha1(data).hexdigest()
    filename = f"{digest}{ext}"
    target = _slideshow_dir() / filename
    if not target.exists():
        target.write_bytes(data)

    public_url = f"/static/images/uploads/{filename}"

    key = f"home.slideshow.slide.{slot}"
    row = db.session.scalars(
        select(SiteContent).where(SiteContent.key == key)
    ).first()
    if row is None:
        row = SiteContent(
            key=key,
            page="slideshow",
            label=f"Slideshow — image {slot}",
            content_type="image_url",
            sort_order=slot * 10,
        )
        db.session.add(row)

    old = row.value
    row.value = public_url
    if current_user and getattr(current_user, "id", None):
        row.updated_by_user_id = current_user.id
    db.session.commit()
    content_service.clear_cache()

    _log("slideshow.upload", key, old=old, new=public_url)
    flash(f"Slide {slot} updated.", "success")
    return redirect(url_for("admin.content_slideshow"))


@admin_bp.route("/content/slideshow/<int:slot>/delete", methods=["POST"])
@admin_required
def content_slideshow_delete(slot: int):
    """Clear the image for one slideshow slot."""
    if slot < 1 or slot > SLIDESHOW_SLOT_COUNT:
        abort(404)

    key = f"home.slideshow.slide.{slot}"
    row = db.session.scalars(
        select(SiteContent).where(SiteContent.key == key)
    ).first()
    if row is None:
        flash("That slot is already empty.", "info")
        return redirect(url_for("admin.content_slideshow"))

    old = row.value
    row.value = None
    if current_user and getattr(current_user, "id", None):
        row.updated_by_user_id = current_user.id
    db.session.commit()
    content_service.clear_cache()

    _log("slideshow.delete", key, old=old, new=None)
    flash(f"Slide {slot} cleared.", "success")
    return redirect(url_for("admin.content_slideshow"))


@admin_bp.route("/content/slideshow/<int:slot>/update-url", methods=["POST"])
@admin_required
def content_slideshow_update_url(slot: int):
    """Set a slot to a manual image URL (alternative to uploading)."""
    if slot < 1 or slot > SLIDESHOW_SLOT_COUNT:
        abort(404)

    new_url = (request.form.get("image_url") or "").strip() or None

    key = f"home.slideshow.slide.{slot}"
    row = db.session.scalars(
        select(SiteContent).where(SiteContent.key == key)
    ).first()
    if row is None:
        row = SiteContent(
            key=key,
            page="slideshow",
            label=f"Slideshow — image {slot}",
            content_type="image_url",
            sort_order=slot * 10,
        )
        db.session.add(row)

    old = row.value
    row.value = new_url
    if current_user and getattr(current_user, "id", None):
        row.updated_by_user_id = current_user.id
    db.session.commit()
    content_service.clear_cache()

    _log("slideshow.update_url", key, old=old, new=new_url)
    flash(f"Slide {slot} updated.", "success")
    return redirect(url_for("admin.content_slideshow"))

# ─── Save all slide properties in one call ────────────────────────
@admin_bp.route("/content/slideshow/<int:slot>/save", methods=["POST"])
@admin_required
def content_slideshow_save(slot: int):
    """Save every field (image URL + text + styles) for one slide."""
    if slot < 1 or slot > SLIDESHOW_SLOT_COUNT:
        abort(404)

    # Collect string fields
    data: dict = {
        "image_url": (request.form.get("image_url") or "").strip(),
        "eyebrow":   (request.form.get("eyebrow") or "").strip(),
        "title":     (request.form.get("title") or "").strip(),
        "subtitle":  (request.form.get("subtitle") or "").strip(),
        "cta_text":  (request.form.get("cta_text") or "").strip(),
        "cta_url":   (request.form.get("cta_url") or "").strip(),
    }

    # Collect style fields per text field
    for field in ("title", "subtitle"):
        style: dict[str, str] = {}
        for style_key in content_service.SLIDE_STYLE_FIELDS:
            form_field = f"{field}_{style_key}"
            style[style_key] = (request.form.get(form_field) or "").strip()
        data[f"{field}_style"] = style

    written = content_service.set_slide_props(slot, data, user=current_user)

    _log(
        "slideshow.save_props",
        f"home.slideshow.slide.{slot}",
        new={k: v for k, v in data.items() if v},
    )
    flash(f"Slide {slot} saved ({written} field{'s' if written != 1 else ''}).", "success")
    return redirect(url_for("admin.content_slideshow"))