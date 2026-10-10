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

# Images
IMAGE_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Videos (served from the same uploads directory)
VIDEO_MIME = {"video/mp4", "video/webm", "video/quicktime"}
VIDEO_EXT = {".mp4", ".webm", ".mov"}

ALLOWED_MIME = IMAGE_MIME | VIDEO_MIME
ALLOWED_EXT = IMAGE_EXT | VIDEO_EXT

MAX_BYTES = 50 * 1024 * 1024  # 50 MB


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
    """Media hub with per-product-type tabs.

    Query params:
        tab          hotels | packages | activities   (default: hotels)
        q            search by name
        has_images   1 = only with images, 0 = only without, empty = all
        page         1-based
    """
    tab = (request.args.get("tab") or "hotels").strip().lower()
    if tab not in ("hotels", "packages", "activities"):
        tab = "hotels"

    q = (request.args.get("q") or "").strip()
    has_images = (request.args.get("has_images") or "").strip()
    if has_images not in ("", "0", "1"):
        has_images = ""
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 30

    if tab == "hotels":
        rows = _browse_hotels(q, has_images, page, per_page)
    elif tab == "packages":
        rows = _browse_packages(q, has_images, page, per_page)
    else:
        rows = _browse_activities(q, has_images, page, per_page)

    # Small recent-uploads list for debugging (last 8 across all tables)
    recent: list[dict] = []
    for ptype, model, *_ in (
        ("activity", ActivityImage, "activity_id", False, True),
        ("hotel",    HotelImage,    "hotel_id",    True,  False),
        ("package",  PackageImage,  "package_id",  True,  False),
    ):
        for img in db.session.scalars(
            select(model).order_by(model.id.desc()).limit(8)
        ):
            meta = _image_meta(img, ptype)
            meta["parent_label"] = _parent_name(img, ptype)
            recent.append(meta)
    recent.sort(key=lambda r: r["id"], reverse=True)
    recent = recent[:8]

    return render_template(
        "admin/media_index.html",
        tab=tab,
        items=rows["items"],
        total=rows["total"],
        page=page,
        total_pages=rows["total_pages"],
        q=q,
        has_images=has_images,
        recent=recent,
    )


# ─── Browse helpers (one per product type) ────────────────────────────────
def _browse_hotels(q, has_images, page, per_page):
    """Paginated hotels with image-count + first-image preview."""
    from models import Hotel, Destination

    # Subquery: image count per hotel
    count_sq = (
        select(HotelImage.hotel_id, func.count(HotelImage.id).label("n"))
        .group_by(HotelImage.hotel_id)
        .subquery()
    )
    # Subquery: first image url per hotel (min id)
    first_sq = (
        select(HotelImage.hotel_id, func.min(HotelImage.id).label("min_id"))
        .group_by(HotelImage.hotel_id)
        .subquery()
    )

    stmt = (
        select(Hotel, func.coalesce(count_sq.c.n, 0).label("n_images"),
               HotelImage.url.label("first_url"))
        .outerjoin(count_sq, count_sq.c.hotel_id == Hotel.id)
        .outerjoin(first_sq, first_sq.c.hotel_id == Hotel.id)
        .outerjoin(HotelImage, HotelImage.id == first_sq.c.min_id)
    )
    if q:
        stmt = stmt.where(Hotel.name.ilike(f"%{q}%"))
    if has_images == "1":
        stmt = stmt.where(func.coalesce(count_sq.c.n, 0) > 0)
    elif has_images == "0":
        stmt = stmt.where(func.coalesce(count_sq.c.n, 0) == 0)
    stmt = stmt.order_by(Hotel.name.asc())

    total = int(db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    rows = db.session.execute(stmt.limit(per_page).offset(offset)).all()

    # Destinations lookup
    dest_ids = {h.destination_id for h, *_ in rows if h.destination_id}
    dests = {
        d.id: d.name
        for d in db.session.scalars(
            select(Destination).where(Destination.id.in_(dest_ids))
        )
    } if dest_ids else {}

    items = [{
        "id": h.id,
        "name": h.name,
        "destination": dests.get(h.destination_id, "—"),
        "n_images": int(n),
        "first_url": url,
        "product_type": "hotel",
    } for h, n, url in rows]

    return {"items": items, "total": total, "total_pages": total_pages}


def _browse_packages(q, has_images, page, per_page):
    """Paginated packages with image-count + preview."""
    from models import Package, Destination

    count_sq = (
        select(PackageImage.package_id, func.count(PackageImage.id).label("n"))
        .group_by(PackageImage.package_id)
        .subquery()
    )
    first_sq = (
        select(PackageImage.package_id, func.min(PackageImage.id).label("min_id"))
        .group_by(PackageImage.package_id)
        .subquery()
    )

    stmt = (
        select(Package, func.coalesce(count_sq.c.n, 0).label("n_images"),
               PackageImage.url.label("first_url"))
        .outerjoin(count_sq, count_sq.c.package_id == Package.id)
        .outerjoin(first_sq, first_sq.c.package_id == Package.id)
        .outerjoin(PackageImage, PackageImage.id == first_sq.c.min_id)
    )
    if q:
        stmt = stmt.where(
            (Package.name.ilike(f"%{q}%")) | (Package.code.ilike(f"%{q}%"))
        )
    if has_images == "1":
        stmt = stmt.where(func.coalesce(count_sq.c.n, 0) > 0)
    elif has_images == "0":
        stmt = stmt.where(func.coalesce(count_sq.c.n, 0) == 0)
    stmt = stmt.order_by(Package.name.asc())

    total = int(db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    rows = db.session.execute(stmt.limit(per_page).offset(offset)).all()

    dest_ids = {p.destination_id for p, *_ in rows if p.destination_id}
    dests = {
        d.id: d.name
        for d in db.session.scalars(
            select(Destination).where(Destination.id.in_(dest_ids))
        )
    } if dest_ids else {}

    items = [{
        "id": p.id,
        "name": p.name,
        "code": p.code,
        "destination": dests.get(p.destination_id, "—"),
        "n_images": int(n),
        "first_url": url,
        "product_type": "package",
    } for p, n, url in rows]

    return {"items": items, "total": total, "total_pages": total_pages}


def _browse_activities(q, has_images, page, per_page):
    """Paginated activities with image-count + preview."""
    from models import Activity, Destination

    count_sq = (
        select(ActivityImage.activity_id, func.count(ActivityImage.id).label("n"))
        .group_by(ActivityImage.activity_id)
        .subquery()
    )
    first_sq = (
        select(ActivityImage.activity_id, func.min(ActivityImage.id).label("min_id"))
        .group_by(ActivityImage.activity_id)
        .subquery()
    )

    stmt = (
        select(Activity, func.coalesce(count_sq.c.n, 0).label("n_images"),
               ActivityImage.url.label("first_url"))
        .outerjoin(count_sq, count_sq.c.activity_id == Activity.id)
        .outerjoin(first_sq, first_sq.c.activity_id == Activity.id)
        .outerjoin(ActivityImage, ActivityImage.id == first_sq.c.min_id)
    )
    if q:
        stmt = stmt.where(
            (Activity.name.ilike(f"%{q}%")) | (Activity.code.ilike(f"%{q}%"))
        )
    if has_images == "1":
        stmt = stmt.where(func.coalesce(count_sq.c.n, 0) > 0)
    elif has_images == "0":
        stmt = stmt.where(func.coalesce(count_sq.c.n, 0) == 0)
    stmt = stmt.order_by(Activity.name.asc())

    total = int(db.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    rows = db.session.execute(stmt.limit(per_page).offset(offset)).all()

    dest_ids = {a.destination_id for a, *_ in rows if a.destination_id}
    dests = {
        d.id: d.name
        for d in db.session.scalars(
            select(Destination).where(Destination.id.in_(dest_ids))
        )
    } if dest_ids else {}

    items = [{
        "id": a.id,
        "name": a.name,
        "code": a.code,
        "destination": dests.get(a.destination_id, "—"),
        "n_images": int(n),
        "first_url": url,
        "product_type": "activity",
    } for a, n, url in rows]

    return {"items": items, "total": total, "total_pages": total_pages}



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

    # Detect image vs video from MIME.
    media_type = "video" if file.mimetype in VIDEO_MIME else "image"

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
        "media_type": media_type,
        "poster_url": None,
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
