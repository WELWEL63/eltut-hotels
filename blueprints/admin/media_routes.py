"""
blueprints/admin/media_routes.py
─────────────────────────────────
Admin media management for product images.

ROUTES
    GET  /admin/media                                   browse all
    GET  /admin/media/product/<type>/<id>               images for one product
    POST /admin/media/product/<type>/<id>/upload        upload image
    POST /admin/media/<type>/<id>/delete                delete image
    POST /admin/media/<type>/<id>/reorder               move up / down

DESIGN NOTES
    - Product types: 'activity' | 'hotel' | 'package'. Each has its own
      image table but a common shape (id, parent_id, url, sort_order)
      plus a small difference:
          ActivityImage has `caption` (free text)
          HotelImage and PackageImage have `type` (constrained enum)
      Both are handled by `_image_meta()` which normalises the shape.
    - Filenames are SHA-1 hashed: prevents path traversal, avoids
      duplicate files when the same image is uploaded twice, and makes
      filenames constant-time predictable. The original name is
      discarded by design.
    - MIME type AND extension must both be in the allow-list, because
      a browser-supplied MIME can be spoofed.
    - Delete order: DB row first, then file. Orphan files are harmless;
      orphan DB rows break the public product pages with 404 images.
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
    ActivityImage,
    Booking,
    HotelImage,
    PackageImage,
    VALID_HOTEL_IMAGE_TYPES,
    VALID_PACKAGE_IMAGE_TYPES,
)


# ─── Constants ───────────────────────────────────────────────────────────
VALID_PRODUCT_TYPES = ("activity", "hotel", "package")
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_BYTES = 5 * 1024 * 1024  # 5 MB — well below config MAX_CONTENT_LENGTH


# ─── Helpers ─────────────────────────────────────────────────────────────
def _model_for(product_type: str):
    """Return (model, parent_fk_col_name, has_type, has_caption) or None."""
    if product_type == "activity":
        return ActivityImage, "activity_id", False, True
    if product_type == "hotel":
        return HotelImage, "hotel_id", True, False
    if product_type == "package":
        return PackageImage, "package_id", True, False
    return None


def _image_meta(image, product_type: str) -> dict:
    """Uniform view of an image row regardless of model.

    Includes the owning product id under a stable key (parent_id) so
    templates can build URLs without caring about the per-model FK
    column name (activity_id / hotel_id / package_id).
    """
    fk_col = {
        "activity": "activity_id",
        "hotel": "hotel_id",
        "package": "package_id",
    }.get(product_type)
    parent_id = getattr(image, fk_col, None) if fk_col else None

    return {
        "id": image.id,
        "url": image.url,
        "sort_order": image.sort_order,
        "type": getattr(image, "type", None),
        "caption": getattr(image, "caption", None),
        "product_type": product_type,
        "parent_id": parent_id,
    }


def _upload_dir() -> Path:
    """Resolve the upload directory and ensure it exists."""
    rel = current_app.config.get("UPLOAD_FOLDER", "static/images/uploads")
    path = Path(current_app.root_path) / rel
    path.mkdir(parents=True, exist_ok=True)
    return path


def _log(action: str, entity_id, new=None) -> None:
    try:
        from mongo.logs import log_action
        log_action(
            action=action,
            entity_type="media",
            entity_id=str(entity_id),
            user_id=current_user.id,
            user_role="admin",
            new_value=new,
            ip=request.remote_addr,
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.debug("log skipped: %s", exc)


def _parent_name(image, product_type: str) -> str:
    """Human-readable label for the owning product, best-effort."""
    try:
        if product_type == "activity":
            from models import Activity
            p = db.session.get(Activity, image.activity_id)
            return p.name if p else f"Activity #{image.activity_id}"
        if product_type == "hotel":
            from models import Hotel
            p = db.session.get(Hotel, image.hotel_id)
            return p.name if p else f"Hotel #{image.hotel_id}"
        if product_type == "package":
            from models import Package
            p = db.session.get(Package, image.package_id)
            return p.name if p else f"Package #{image.package_id}"
    except Exception:  # noqa: BLE001
        pass
    return "—"


# ─── Browse all ──────────────────────────────────────────────────────────
@admin_bp.route("/media")
@admin_required
def media_index():
    """Browse every product image. Filter by product_type."""
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 30
    product_type = (request.args.get("product_type") or "").strip().lower()

    # Collect images from each model
    rows: list[dict] = []
    for ptype, model, *_ in (
        ("activity", ActivityImage, "activity_id", False, True),
        ("hotel",    HotelImage,    "hotel_id",    True,  False),
        ("package",  PackageImage,  "package_id",  True,  False),
    ):
        if product_type and product_type != ptype:
            continue
        images = list(db.session.scalars(
            select(model).order_by(model.id.desc()).limit(500)
        ))
        for img in images:
            meta = _image_meta(img, ptype)
            meta["parent_label"] = _parent_name(img, ptype)
            rows.append(meta)

    # Simple in-memory pagination (data volume is small — under 500 rows per type)
    total = len(rows)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    items = rows[offset:offset + per_page]

    return render_template(
        "admin/media_index.html",
        items=items,
        total=total,
        page=page,
        total_pages=total_pages,
        product_type=product_type,
    )


# ─── Images for one product ──────────────────────────────────────────────
@admin_bp.route("/media/product/<product_type>/<int:parent_id>")
@admin_required
def media_for_product(product_type: str, parent_id: int):
    """Show and manage images for a single product."""
    meta = _model_for(product_type)
    if meta is None:
        abort(404)
    Model, fk_col, has_type, has_caption = meta

    images = list(db.session.scalars(
        select(Model)
        .where(getattr(Model, fk_col) == parent_id)
        .order_by(Model.sort_order.asc().nullslast(), Model.id.asc())
    ))
    items = [_image_meta(img, product_type) for img in images]

    # Fetch the parent for a friendly title
    parent_label = f"{product_type.capitalize()} #{parent_id}"
    try:
        if product_type == "activity":
            from models import Activity
            p = db.session.get(Activity, parent_id)
            if p: parent_label = p.name
        elif product_type == "hotel":
            from models import Hotel
            p = db.session.get(Hotel, parent_id)
            if p: parent_label = p.name
        elif product_type == "package":
            from models import Package
            p = db.session.get(Package, parent_id)
            if p: parent_label = p.name
    except Exception:  # noqa: BLE001
        pass

    # Compute the next sort_order for the upload form
    next_sort = (max((i["sort_order"] or 0) for i in items) + 1) if items else 1

    return render_template(
        "admin/media_product.html",
        items=items,
        total=len(items),
        product_type=product_type,
        parent_id=parent_id,
        parent_label=parent_label,
        has_type=has_type,
        has_caption=has_caption,
        image_types=(VALID_HOTEL_IMAGE_TYPES if product_type == "hotel"
                     else VALID_PACKAGE_IMAGE_TYPES if product_type == "package"
                     else ()),
        next_sort=next_sort,
    )


# ─── Upload ──────────────────────────────────────────────────────────────
@admin_bp.route("/media/product/<product_type>/<int:parent_id>/upload", methods=["POST"])
@admin_required
def media_upload(product_type: str, parent_id: int):
    """Handle multipart upload for a product image."""
    meta = _model_for(product_type)
    if meta is None:
        abort(404)
    Model, fk_col, has_type, has_caption = meta

    file = request.files.get("file")
    if file is None or not file.filename:
        flash("Please choose a file.", "danger")
        return redirect(url_for("admin.media_for_product",
                                product_type=product_type, parent_id=parent_id))

    # MIME + extension validation (both, MIME can be spoofed)
    if file.mimetype not in ALLOWED_MIME:
        flash(f"Unsupported MIME type: {file.mimetype}", "danger")
        return redirect(url_for("admin.media_for_product",
                                product_type=product_type, parent_id=parent_id))

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        flash(f"Unsupported extension: {ext}", "danger")
        return redirect(url_for("admin.media_for_product",
                                product_type=product_type, parent_id=parent_id))

    data = file.read()
    if not data:
        flash("File is empty.", "danger")
        return redirect(url_for("admin.media_for_product",
                                product_type=product_type, parent_id=parent_id))

    if len(data) > MAX_BYTES:
        flash(f"File too large ({len(data)} bytes > {MAX_BYTES}).", "danger")
        return redirect(url_for("admin.media_for_product",
                                product_type=product_type, parent_id=parent_id))

    # SHA-1 filename — dedupes, prevents traversal, no user data in path
    digest = hashlib.sha1(data).hexdigest()
    filename = f"{digest}{ext}"
    upload_dir = _upload_dir()
    target = upload_dir / filename
    if not target.exists():
        target.write_bytes(data)

    # Public URL relative to static/
    public_url = f"/static/images/uploads/{filename}"

    # Build the image row — different columns per model
    kwargs = {
        fk_col: parent_id,
        "url": public_url,
    }
    if has_type:
        t = (request.form.get("type") or "").strip().lower()
        valid = (VALID_HOTEL_IMAGE_TYPES if product_type == "hotel"
                 else VALID_PACKAGE_IMAGE_TYPES)
        if t not in valid:
            t = valid[-1]  # default to "other"
        kwargs["type"] = t
    if has_caption:
        kwargs["caption"] = (request.form.get("caption") or "").strip() or None

    # sort_order: either explicit or max+1
    sort_raw = (request.form.get("sort_order") or "").strip()
    if sort_raw.isdigit():
        kwargs["sort_order"] = int(sort_raw)
    else:
        max_sort = db.session.scalar(
            select(func.coalesce(func.max(Model.sort_order), 0))
            .where(getattr(Model, fk_col) == parent_id)
        ) or 0
        kwargs["sort_order"] = max_sort + 1

    image = Model(**kwargs)
    db.session.add(image)
    db.session.commit()

    _log("media.upload", image.id, new={"url": public_url, "parent": parent_id})
    flash("Image uploaded.", "success")
    return redirect(url_for("admin.media_for_product",
                            product_type=product_type, parent_id=parent_id))


# ─── Delete ──────────────────────────────────────────────────────────────
@admin_bp.route("/media/<product_type>/<int:image_id>/delete", methods=["POST"])
@admin_required
def media_delete(product_type: str, image_id: int):
    """Delete an image row and its file."""
    meta = _model_for(product_type)
    if meta is None:
        abort(404)
    Model, fk_col, *_ = meta

    image = db.session.get(Model, image_id)
    if image is None:
        flash("Image not found.", "warning")
        return redirect(url_for("admin.media_index"))

    parent_id = getattr(image, fk_col)
    url = image.url or ""

    # DB row first — orphan files are harmless, orphan rows break the product page
    db.session.delete(image)
    db.session.commit()

    # Try to remove the file if it lives under our uploads dir.
    # Never trust the URL beyond the "/static/images/uploads/" prefix.
    if url.startswith("/static/images/uploads/"):
        filename = url.split("/")[-1]
        candidate = _upload_dir() / filename
        if candidate.exists():
            try:
                candidate.unlink()
            except OSError as exc:
                current_app.logger.warning("could not delete %s: %s", candidate, exc)

    _log("media.delete", image_id, new={"url": url, "parent": parent_id})
    flash("Image deleted.", "success")
    return redirect(url_for("admin.media_for_product",
                            product_type=product_type, parent_id=parent_id))


# ─── Reorder ─────────────────────────────────────────────────────────────
@admin_bp.route("/media/<product_type>/<int:image_id>/reorder", methods=["POST"])
@admin_required
def media_reorder(product_type: str, image_id: int):
    """Swap this image's sort_order with its neighbour (up or down)."""
    meta = _model_for(product_type)
    if meta is None:
        abort(404)
    Model, fk_col, *_ = meta

    direction = (request.form.get("direction") or "").strip().lower()
    if direction not in ("up", "down"):
        flash("Invalid direction.", "danger")
        return redirect(url_for("admin.media_index"))

    image = db.session.get(Model, image_id)
    if image is None:
        abort(404)
    parent_id = getattr(image, fk_col)

    current_sort = image.sort_order or 0
    fk_col_attr = getattr(Model, fk_col)

    if direction == "up":
        stmt = (
            select(Model)
            .where(fk_col_attr == parent_id, Model.sort_order < current_sort)
            .order_by(Model.sort_order.desc())
            .limit(1)
        )
    else:
        stmt = (
            select(Model)
            .where(fk_col_attr == parent_id, Model.sort_order > current_sort)
            .order_by(Model.sort_order.asc())
            .limit(1)
        )

    neighbour = db.session.scalars(stmt).first()
    if neighbour is None:
        # Nothing to swap with — no-op
        return redirect(url_for("admin.media_for_product",
                                product_type=product_type, parent_id=parent_id))

    image.sort_order, neighbour.sort_order = neighbour.sort_order, image.sort_order
    db.session.commit()

    _log("media.reorder", image_id, new={"direction": direction})
    return redirect(url_for("admin.media_for_product",
                            product_type=product_type, parent_id=parent_id))
