"""
blueprints/admin/review_admin.py
─────────────────────────────────
Admin moderation for Mongo-backed reviews and enquiries.

ROUTES
    GET      /admin/reviews                       list (paginated)
    POST     /admin/reviews/<id>/delete           delete a review
    GET      /admin/enquiries                     list (paginated)
    POST     /admin/enquiries/<id>/status         mark handled / spam

DESIGN NOTES
    - Mongo may be unconfigured (dev). Every read/write wraps the repo
      call in try/except RuntimeError and passes mongo_available=False
      to the template, which renders a warning banner instead of 500.
    - Reviews: no generic list_reviews() in the repo, so we query the
      collection directly with sort/skip/limit. Server-side pagination
      via count_documents + find.
    - Enquiries: uses the existing list_enquiries() which already
      supports type/status filters and returns (items, total).
    - Deletes are logged to activity_logs (best-effort; also Mongo).
    - ID format: MongoDB ObjectIds, passed as hex strings in URLs.
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

from blueprints.admin import admin_bp, admin_required
from mongo import enquiries as enquiries_repo
from mongo import reviews as reviews_repo
from mongo.client import enquiries_collection, reviews_collection


PAGE_SIZE = 25


# ─── Logging ─────────────────────────────────────────────────────────────
def _log(action: str, entity_type: str, entity_id, new=None) -> None:
    """Best-effort audit log. Silent if Mongo is unavailable."""
    try:
        from mongo.logs import log_action
        log_action(
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            user_id=current_user.id,
            user_role="admin",
            new_value=new,
            ip=request.remote_addr,
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.debug("log skipped: %s", exc)


# ─── Reviews: list ───────────────────────────────────────────────────────
@admin_bp.route("/reviews")
@admin_required
def review_list():
    """List all reviews, newest first, with filters."""
    page = max(1, int(request.args.get("page", 1) or 1))
    product_type = (request.args.get("product_type") or "").strip().lower()
    rating_raw = (request.args.get("rating") or "").strip()
    q = (request.args.get("q") or "").strip()

    rating = None
    if rating_raw:
        try:
            n = int(rating_raw)
            if 1 <= n <= 5:
                rating = n
        except ValueError:
            pass

    items: list[dict] = []
    total = 0
    mongo_available = True
    error: str | None = None

    try:
        col = reviews_collection()

        # Build the filter dict. We control every key here — no injection risk.
        where: dict = {}
        if product_type in ("activity", "hotel", "package"):
            where["product_type"] = product_type
        if rating is not None:
            where["rating"] = rating
        if q:
            # Case-insensitive search on title or body via regex.
            # escape() prevents regex injection if a user types weird chars.
            import re
            pattern = re.escape(q)
            where["$or"] = [
                {"title": {"$regex": pattern, "$options": "i"}},
                {"body":  {"$regex": pattern, "$options": "i"}},
                {"user_name": {"$regex": pattern, "$options": "i"}},
            ]

        total = col.count_documents(where)
        offset = (page - 1) * PAGE_SIZE
        cursor = (
            col.find(where)
            .sort("created_at", -1)
            .skip(offset)
            .limit(PAGE_SIZE)
        )
        # Stringify _id for the template; keep the rest as-is.
        items = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            items.append(doc)
    except RuntimeError as exc:
        mongo_available = False
        error = str(exc)
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("review_list failed: %s", exc)
        mongo_available = False
        error = f"Unexpected error: {exc}"

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)

    return render_template(
        "admin/review_list.html",
        items=items,
        total=total,
        page=page,
        total_pages=total_pages,
        product_type=product_type,
        rating=rating_raw,
        q=q,
        mongo_available=mongo_available,
        mongo_error=error,
    )


# ─── Reviews: delete ─────────────────────────────────────────────────────
@admin_bp.route("/reviews/<review_id>/delete", methods=["POST"])
@admin_required
def review_delete(review_id: str):
    """Delete a review by Mongo ObjectId hex."""
    try:
        ok = reviews_repo.delete_review(review_id)
    except RuntimeError as exc:
        flash(f"MongoDB is not available: {exc}", "danger")
        return redirect(url_for("admin.review_list"))
    except reviews_repo.ReviewError as exc:
        flash(f"Could not delete review: {exc}", "danger")
        return redirect(url_for("admin.review_list"))
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("delete review failed: %s", exc)
        flash(f"Unexpected error: {exc}", "danger")
        return redirect(url_for("admin.review_list"))

    if ok:
        _log("review.delete", "review", review_id)
        flash("Review deleted.", "success")
    else:
        flash("Review not found.", "warning")
    return redirect(url_for("admin.review_list"))


# ─── Enquiries: list ─────────────────────────────────────────────────────
@admin_bp.route("/enquiries")
@admin_required
def enquiry_list():
    """List enquiries with optional type/status filters."""
    page = max(1, int(request.args.get("page", 1) or 1))
    type_filter = (request.args.get("type") or "").strip().lower()
    status_filter = (request.args.get("status") or "").strip().lower()

    items: list[dict] = []
    total = 0
    mongo_available = True
    error: str | None = None

    try:
        items, total = enquiries_repo.list_enquiries(
            type=type_filter or None,
            status=status_filter or None,
            limit=PAGE_SIZE,
            skip=(page - 1) * PAGE_SIZE,
        )
    except RuntimeError as exc:
        mongo_available = False
        error = str(exc)
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("enquiry_list failed: %s", exc)
        mongo_available = False
        error = f"Unexpected error: {exc}"

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)

    return render_template(
        "admin/enquiry_list.html",
        items=items,
        total=total,
        page=page,
        total_pages=total_pages,
        type_filter=type_filter,
        status_filter=status_filter,
        mongo_available=mongo_available,
        mongo_error=error,
    )


# ─── Enquiries: change status ────────────────────────────────────────────
@admin_bp.route("/enquiries/<enquiry_id>/status", methods=["POST"])
@admin_required
def enquiry_status(enquiry_id: str):
    """Mark an enquiry as handled or spam."""
    target = (request.form.get("status") or "").strip().lower()
    note = (request.form.get("note") or "").strip() or None

    try:
        if target == "handled":
            result = enquiries_repo.mark_handled(enquiry_id, admin_note=note)
        elif target == "spam":
            result = enquiries_repo.mark_spam(enquiry_id)
        else:
            flash(f"Unsupported status {target!r}.", "danger")
            return redirect(url_for("admin.enquiry_list"))
    except RuntimeError as exc:
        flash(f"MongoDB is not available: {exc}", "danger")
        return redirect(url_for("admin.enquiry_list"))
    except enquiries_repo.EnquiryError as exc:
        flash(f"Could not update enquiry: {exc}", "danger")
        return redirect(url_for("admin.enquiry_list"))
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("enquiry status change failed: %s", exc)
        flash(f"Unexpected error: {exc}", "danger")
        return redirect(url_for("admin.enquiry_list"))

    if result:
        _log(f"enquiry.{target}", "enquiry", enquiry_id, new=note)
        flash(f"Enquiry marked as {target}.", "success")
    else:
        flash("Enquiry not found.", "warning")
    return redirect(url_for("admin.enquiry_list"))
