"""
blueprints/public/review_routes.py
──────────────────────────────────
Submit a product review (stored in MongoDB).

ROUTES
    POST /reviews/submit    submit a review for an activity/hotel/package
"""

from __future__ import annotations

from flask import current_app, flash, redirect, request, url_for
from flask_login import current_user

from blueprints.public import public_bp
from models import (
    PRODUCT_TYPE_ACTIVITY,
    PRODUCT_TYPE_HOTEL,
    PRODUCT_TYPE_PACKAGE,
    VALID_PRODUCT_TYPES,
)


def _to_int(value, default=0, lo=0, hi=5):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


@public_bp.route("/reviews/submit", methods=["POST"])
def review_submit():
    """Receive a review form POST and write to Mongo."""
    product_type = (request.form.get("product_type") or "").strip().lower()
    if product_type not in VALID_PRODUCT_TYPES:
        flash("Invalid product type.", "danger")
        return redirect(url_for("public.index"))

    product_id = _to_int(request.form.get("product_id"), 0, 1, 10**9)
    if product_id < 1:
        flash("Invalid product.", "danger")
        return redirect(url_for("public.index"))

    rating = _to_int(request.form.get("rating"), 5, 1, 5)
    title = (request.form.get("title") or "").strip() or None
    body = (request.form.get("body") or "").strip() or None

    if current_user.is_authenticated:
        user_id = current_user.id
        user_name = (request.form.get("guest_name") or current_user.full_name or "").strip()
        user_email = (request.form.get("guest_email") or getattr(current_user, "email", "") or "").strip().lower()
    else:
        user_id = None
        user_name = (request.form.get("guest_name") or "").strip()
        user_email = (request.form.get("guest_email") or "").strip().lower()

    if not user_name:
        flash("Please provide your name.", "danger")
        return redirect(request.referrer or url_for("public.index"))
    if not user_email or "@" not in user_email:
        flash("Please provide a valid email address.", "danger")
        return redirect(request.referrer or url_for("public.index"))

    try:
        from mongo.reviews import create_review, ReviewAlreadyExists
    except Exception as exc:
        current_app.logger.warning("mongo.reviews unavailable: %s", exc)
        flash("Reviews are temporarily unavailable.", "warning")
        return redirect(request.referrer or url_for("public.index"))

    try:
        create_review(
            product_type=product_type,
            product_id=product_id,
            user_id=user_id,
            user_name=user_name,
            user_email=user_email,
            rating=rating,
            title=title,
            body=body,
        )
    except ReviewAlreadyExists:
        flash("You've already reviewed this product.", "warning")
        return redirect(request.referrer or url_for("public.index"))
    except Exception as exc:
        current_app.logger.exception("create_review failed: %s", exc)
        flash("Could not save your review.", "danger")
        return redirect(request.referrer or url_for("public.index"))

    flash("Thank you for your review!", "success")
    return redirect(request.referrer or url_for("public.index"))
