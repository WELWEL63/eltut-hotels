"""
blueprints/admin/quote_admin.py
────────────────────────────────
Admin quote management: requests inbox, draft editor, sending.

ROUTES
    GET      /admin/quotes                          list quotes
    GET      /admin/quotes/requests                 incoming requests (Mongo)
    GET      /admin/quotes/new                      create-draft form
    POST     /admin/quotes/new                      create draft
    GET      /admin/quotes/<reference>              detail + edit form
    POST     /admin/quotes/<reference>              save draft (+ maybe send)
    POST     /admin/quotes/<reference>/send         send draft
    POST     /admin/quotes/<reference>/cancel       cancel draft or sent

DESIGN NOTES
    - List reads SQL via quote_service.list_quotes.
    - Requests reads Mongo via quote_service.list_open_quote_requests.
      If Mongo is down we show an empty inbox with a warning banner.
    - Draft edit accepts price/currency/valid_until/message/image_url.
      Sending is a separate explicit action so the admin can review
      before hitting send.
    - Every write is logged to Mongo activity_logs (best-effort).
"""

from __future__ import annotations

from datetime import datetime

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
from services import quote_service
from services.quote_service import (
    InvalidQuoteInput,
    InvalidQuoteState,
    QuoteNotFound,
)


VALID_STATUSES = ("draft", "sent", "accepted", "declined", "expired", "cancelled")
VALID_PRODUCT_TYPES = ("activity", "hotel", "package")


# ─── Logging ──────────────────────────────────────────────────────────────
def _log(action: str, entity_id, new=None) -> None:
    try:
        from mongo.logs import log_action
        log_action(
            action=action,
            entity_type="quote",
            entity_id=str(entity_id),
            user_id=current_user.id,
            user_role="admin",
            new_value=new,
            ip=request.remote_addr,
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.debug("log skipped: %s", exc)


# ─── Parsing helpers ──────────────────────────────────────────────────────
def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# ─── List quotes ──────────────────────────────────────────────────────────
@admin_bp.route("/quotes")
@admin_required
def quote_list():
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 25
    status = (request.args.get("status") or "").strip().lower()
    product_type = (request.args.get("product_type") or "").strip().lower()

    if status not in VALID_STATUSES:
        status = ""
    if product_type not in VALID_PRODUCT_TYPES:
        product_type = ""

    items, total = quote_service.list_quotes(
        status=status or None,
        product_type=product_type or None,
        limit=per_page,
        skip=(page - 1) * per_page,
    )

    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)

    return render_template(
        "admin/quote_list.html",
        items=items,
        total=total,
        page=page,
        total_pages=total_pages,
        status=status,
        product_type=product_type,
    )


# ─── Incoming requests ────────────────────────────────────────────────────
@admin_bp.route("/quotes/requests")
@admin_required
def quote_requests():
    page = max(1, int(request.args.get("page", 1) or 1))
    per_page = 25

    items, total = quote_service.list_open_quote_requests(
        limit=per_page,
        skip=(page - 1) * per_page,
    )

    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)

    mongo_available = True
    if total == 0 and not items:
        # If Mongo is down, list_open_quote_requests returns ([], 0)
        # silently. We can't distinguish empty-inbox from mongo-down
        # by the return value alone, so peek at Mongo availability.
        try:
            from mongo.client import ensure_indexes
            ensure_indexes()
        except Exception:
            mongo_available = False

    return render_template(
        "admin/quote_requests.html",
        items=items,
        total=total,
        page=page,
        total_pages=total_pages,
        mongo_available=mongo_available,
    )


# ─── Create draft ─────────────────────────────────────────────────────────
@admin_bp.route("/quotes/new", methods=["GET", "POST"])
@admin_required
def quote_new():
    # Prefill from query string (the "Create quote" button on the
    # requests inbox passes enquiry fields in).
    prefill = {
        "customer_email": request.args.get("email", ""),
        "customer_name": request.args.get("name", ""),
        "customer_phone": request.args.get("phone", ""),
        "product_type": request.args.get("product_type", "package"),
        "product_id": request.args.get("product_id", ""),
        "product_name_snapshot": request.args.get("product_name", ""),
        "enquiry_id": request.args.get("enquiry_id", ""),
        "adults": request.args.get("adults", "1"),
        "children": request.args.get("children", "0"),
    }

    if request.method == "POST":
        try:
            quote = quote_service.create_draft(
                customer_email=request.form.get("customer_email", ""),
                customer_name=request.form.get("customer_name") or None,
                customer_phone=request.form.get("customer_phone") or None,
                product_type=request.form.get("product_type", ""),
                product_id=request.form.get("product_id", ""),
                product_name_snapshot=request.form.get("product_name_snapshot") or None,
                enquiry_id=request.form.get("enquiry_id") or None,
                adults=int(request.form.get("adults") or 1),
                children=int(request.form.get("children") or 0),
                created_by_user=current_user,
            )
        except InvalidQuoteInput as exc:
            flash(f"Invalid input: {exc}", "danger")
            return render_template(
                "admin/quote_new.html", prefill=prefill,
            )

        _log("quote.draft_created", quote.id, new={"ref": quote.reference})
        flash(f"Draft created: {quote.reference}. Now fill in the price.", "success")
        return redirect(url_for("admin.quote_detail", reference=quote.reference))

    return render_template("admin/quote_new.html", prefill=prefill)


# ─── Detail + edit ────────────────────────────────────────────────────────
@admin_bp.route("/quotes/<reference>", methods=["GET", "POST"])
@admin_required
def quote_detail(reference: str):
    quote = quote_service.get_quote_by_reference(reference)
    if quote is None:
        flash(f"Quote {reference!r} not found.", "warning")
        return redirect(url_for("admin.quote_list"))

    if request.method == "POST":
        try:
            quote_service.update_draft(
                quote,
                price_adult=request.form.get("price_adult", ""),
                price_child=request.form.get("price_child", "0"),
                adults=int(request.form.get("adults") or quote.adults or 1),
                children=int(request.form.get("children") or quote.children or 0),
                currency=request.form.get("currency", "GBP"),
                valid_until=_parse_date(request.form.get("valid_until")),
                message=request.form.get("message"),
                image_url=request.form.get("image_url"),
                internal_notes=request.form.get("internal_notes"),
            )
        except InvalidQuoteInput as exc:
            flash(f"Invalid input: {exc}", "danger")
            return redirect(url_for("admin.quote_detail", reference=reference))
        except InvalidQuoteState as exc:
            flash(f"Cannot edit: {exc}", "danger")
            return redirect(url_for("admin.quote_detail", reference=reference))

        # Optional: send immediately if the button was the send-and-save
        if request.form.get("action") == "save_and_send":
            try:
                quote_service.send_quote(quote, user=current_user)
                _log("quote.sent", quote.id, new={"ref": quote.reference})
                flash(f"Quote {quote.reference} sent to {quote.customer_email}.", "success")
            except InvalidQuoteState as exc:
                flash(f"Save OK, but send failed: {exc}", "warning")
                return redirect(url_for("admin.quote_detail", reference=reference))
        else:
            flash("Draft saved.", "success")
            _log("quote.draft_updated", quote.id, new={"ref": quote.reference})

        return redirect(url_for("admin.quote_detail", reference=reference))

    return render_template("admin/quote_detail.html", quote=quote)


# ─── Send draft ───────────────────────────────────────────────────────────
@admin_bp.route("/quotes/<reference>/send", methods=["POST"])
@admin_required
def quote_send(reference: str):
    quote = quote_service.get_quote_by_reference(reference)
    if quote is None:
        flash(f"Quote {reference!r} not found.", "warning")
        return redirect(url_for("admin.quote_list"))

    try:
        quote_service.send_quote(quote, user=current_user)
    except InvalidQuoteState as exc:
        flash(f"Could not send: {exc}", "danger")
        return redirect(url_for("admin.quote_detail", reference=reference))

    _log("quote.sent", quote.id, new={"ref": quote.reference})
    flash(f"Quote {quote.reference} sent to {quote.customer_email}.", "success")
    return redirect(url_for("admin.quote_detail", reference=reference))


# ─── Cancel ───────────────────────────────────────────────────────────────
@admin_bp.route("/quotes/<reference>/cancel", methods=["POST"])
@admin_required
def quote_cancel(reference: str):
    quote = quote_service.get_quote_by_reference(reference)
    if quote is None:
        flash(f"Quote {reference!r} not found.", "warning")
        return redirect(url_for("admin.quote_list"))

    reason = (request.form.get("reason") or "").strip() or None

    try:
        quote_service.cancel_quote(quote, user=current_user, reason=reason)
    except InvalidQuoteState as exc:
        flash(f"Could not cancel: {exc}", "danger")
        return redirect(url_for("admin.quote_detail", reference=reference))

    _log("quote.cancelled", quote.id, new={"ref": quote.reference, "reason": reason})
    flash(f"Quote {quote.reference} cancelled.", "success")
    return redirect(url_for("admin.quote_detail", reference=reference))
