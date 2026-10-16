"""
blueprints/admin/destination_admin.py
─────────────────────────────────────
Admin UI for managing home-page destination images.

Admin sees a grid of all destinations; uploads an image per destination;
the CMS key `destination_image_<slug>` is updated automatically so the
home page picks it up immediately.

ROUTES
    GET  /admin/destinations/images                     grid page
    POST /admin/destinations/<int:dest_id>/image/upload  upload
    POST /admin/destinations/<int:dest_id>/image/delete  delete

DESIGN
    - Files stored under static/images/destinations/<sha1>.<ext>
    - URL saved to SiteContent key: destination_image_<slug>
    - Same SHA-1 dedupe pattern as airline logos
    - Extension + MIME + size checks
"""

from __future__ import annotations

import hashlib
import logging
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

from blueprints.admin import admin_bp
from blueprints.admin.routes import admin_required
from extensions import db
from models import Destination


log = logging.getLogger(__name__)


# ─── Constants ────────────────────────────────────────────────────
VALID_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_MIME = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


# ─── Helpers ──────────────────────────────────────────────────────
def _images_dir() -> Path:
    """Absolute path to static/images/destinations/, created if missing."""
    root = Path(current_app.root_path)
    d = root / "static" / "images" / "destinations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _current_url_for(slug: str) -> str | None:
    """Read the current CMS key, or None."""
    try:
        from services import content_service
        return content_service.get(f"destination_image_{slug}") or None
    except Exception:
        return None


def _set_url_for(slug: str, url: str | None) -> None:
    """Write the CMS key."""
    from services import content_service
    content_service.set_value(f"destination_image_{slug}", url or "")


def _log(action: str, entity_id, old=None, new=None) -> None:
    try:
        from mongo import logs as mongo_logs
        mongo_logs.log_action(
            action=action,
            entity_type="destination",
            entity_id=entity_id,
            old=old,
            new=new,
        )
    except Exception:
        pass  # best-effort


# ─── Routes ───────────────────────────────────────────────────────
@admin_bp.route("/destinations/images")
@admin_required
def destination_images():
    """Grid page — all destinations with current image + upload form."""
    destinations = list(db.session.query(Destination).order_by(Destination.name))
    # Attach current CMS url + preview to each
    rows = []
    for d in destinations:
        rows.append({
            "dest": d,
            "url": _current_url_for(d.slug),
        })
    return render_template(
        "admin/destination_images.html",
        rows=rows,
        max_bytes=MAX_IMAGE_BYTES,
    )


@admin_bp.route("/destinations/<int:dest_id>/image/upload", methods=["POST"])
@admin_required
def destination_image_upload(dest_id: int):
    """Handle file upload for one destination."""
    dest = db.session.get(Destination, dest_id)
    if dest is None:
        abort(404)

    file = request.files.get("file")
    if file is None or not file.filename:
        flash("Please choose a file.", "danger")
        return redirect(url_for("admin.destination_images"))

    ext = Path(file.filename).suffix.lower()
    if ext not in VALID_IMAGE_EXTS:
        flash(
            f"Unsupported extension '{ext}'. "
            f"Allowed: {', '.join(sorted(VALID_IMAGE_EXTS))}",
            "danger",
        )
        return redirect(url_for("admin.destination_images"))

    if file.mimetype and file.mimetype not in ALLOWED_MIME:
        flash(f"Unsupported MIME type: {file.mimetype}", "danger")
        return redirect(url_for("admin.destination_images"))

    data = file.read()
    if not data:
        flash("File is empty.", "danger")
        return redirect(url_for("admin.destination_images"))
    if len(data) > MAX_IMAGE_BYTES:
        flash(
            f"File too large ({len(data)} bytes > {MAX_IMAGE_BYTES}).",
            "danger",
        )
        return redirect(url_for("admin.destination_images"))

    # SHA-1 dedupe filename (path-traversal safe)
    digest = hashlib.sha1(data).hexdigest()
    filename = f"{digest}{ext}"
    target = _images_dir() / filename
    if not target.exists():
        target.write_bytes(data)

    new_url = f"/static/images/destinations/{filename}"

    # Save to CMS
    old = _current_url_for(dest.slug)
    try:
        _set_url_for(dest.slug, new_url)
    except Exception as exc:
        current_app.logger.exception("CMS save failed: %s", exc)
        flash("Could not save the CMS key.", "danger")
        return redirect(url_for("admin.destination_images"))

    _log("upload_destination_image", dest.id, old=old, new=new_url)
    flash(f"Image uploaded for '{dest.name}'.", "success")
    return redirect(url_for("admin.destination_images"))


@admin_bp.route("/destinations/<int:dest_id>/image/delete", methods=["POST"])
@admin_required
def destination_image_delete(dest_id: int):
    """Remove the CMS key for one destination (file left on disk)."""
    dest = db.session.get(Destination, dest_id)
    if dest is None:
        abort(404)

    old = _current_url_for(dest.slug)
    try:
        _set_url_for(dest.slug, "")
    except Exception as exc:
        current_app.logger.exception("CMS delete failed: %s", exc)
        flash("Could not clear the CMS key.", "danger")
        return redirect(url_for("admin.destination_images"))

    _log("delete_destination_image", dest.id, old=old, new=None)
    flash(f"Image removed for '{dest.name}'.", "success")
    return redirect(url_for("admin.destination_images"))
