"""
blueprints/public/enquiry_routes.py
───────────────────────────────────
Public enquiry and contact messages (stored in MongoDB).

ROUTES
    GET  /enquiries/new    standalone enquiry/quote-request form
    POST /enquiries        submit a contact message or quote request
"""

from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from blueprints.public import public_bp
from models import (
    PRODUCT_TYPE_ACTIVITY,
    PRODUCT_TYPE_HOTEL,
    PRODUCT_TYPE_PACKAGE,
    VALID_PRODUCT_TYPES,
)


def _to_int(value, default=0, lo=0, hi=10**6):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


@public_bp.route("/enquiries/new")
def enquiry_form():
    """Standalone enquiry / quote-request form."""
    # Pre-fill from query params (e.g. links from product pages)
    product_type = (request.args.get("product_type") or "").strip().lower()
    if product_type not in VALID_PRODUCT_TYPES:
        product_type = None
    product_id_raw = request.args.get("product_id", "").strip()
    product_id = _to_int(product_id_raw, 0, 0, 10**9) or None

    return render_template(
        "public/enquiry_form.html",
        product_type=product_type,
        product_id=product_id,
    )


@public_bp.route("/enquiries", methods=["POST"])
def enquiry_submit():
    """Receive and store a contact message or quote request."""
    enquiry_type = (request.form.get("type") or "contact").strip().lower()
    if enquiry_type not in ("contact", "quote_request"):
        enquiry_type = "contact"

    name = (request.form.get("name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    phone = (request.form.get("phone") or "").strip() or None
    message = (request.form.get("message") or "").strip() or None

    product_type_raw = (request.form.get("product_type") or "").strip().lower()
    product_type = (
        product_type_raw if product_type_raw in VALID_PRODUCT_TYPES else None
    )
    product_id = _to_int(request.form.get("product_id"), 0, 0, 10**9) or None

    metadata = {
        "adults": _to_int(request.form.get("adults"), 0, 0, 100),
        "children": _to_int(request.form.get("children"), 0, 0, 100),
        "check_in": (request.form.get("check_in") or "").strip() or None,
        "check_out": (request.form.get("check_out") or "").strip() or None,
    }

    if not name or not email or "@" not in email:
        flash("Please provide your name and a valid email address.", "danger")
        return redirect(request.referrer or url_for("public.contact"))

    # Store in Mongo (best-effort)
    try:
        from mongo.enquiries import create_enquiry
        enquiry = create_enquiry(
            type=enquiry_type,
            name=name,
            email=email,
            phone=phone,
            product_type=product_type,
            product_id=product_id,
            message=message,
            metadata=metadata,
        )
    except Exception as exc:
        current_app.logger.warning("mongo.enquiries unavailable: %s", exc)
        enquiry = None

    # Notify admin (best-effort)
    try:
        from services.email_service import send_enquiry_received
        send_enquiry_received({
            "name": name,
            "email": email,
            "type": enquiry_type,
            "message": message or "",
        })
    except Exception as exc:
        current_app.logger.warning("send_enquiry_received failed: %s", exc)

    flash(
        "Thanks — your message has been received. We'll get back to you shortly.",
        "success",
    )
    return redirect(url_for("public.index"))
