"""
blueprints/public/quote_routes.py
──────────────────────────────────
Public quote-request form and customer-facing quote view.

ROUTES
    GET  /quote/request                    standalone form
    POST /quote/request                    submit request → Mongo enquiry
    GET  /quote/request/thanks             confirmation page
    GET  /quote/<reference>                customer view (accept/decline)
    POST /quote/<reference>/accept         accept → creates pending Booking
    POST /quote/<reference>/decline        decline with optional reason

DESIGN NOTES
    - Guest-friendly. No login required to submit a request or accept
      a quote. The email stored on the quote acts as the auth token
      (quotes reference high-entropy strings — same pattern as
      booking lookups).
    - If Mongo is unconfigured, submission fails cleanly with a flash
      and redirects back to the form so the visitor can retry later.
    - Accept flow reuses quote_service.accept_quote which internally
      calls booking_service.create_booking — all validation + the
      audit trail run through the standard booking pipeline.
    - The reference in the URL is a Q-YYYY-NNNNN string; case
      insensitive on lookup.
"""

from __future__ import annotations

from datetime import date, datetime

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from blueprints.public import public_bp
from services import quote_service
from services.quote_service import InvalidQuoteInput, InvalidQuoteState


# ─── Helpers ──────────────────────────────────────────────────────────────
def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _int_arg(name: str, default: int, minimum: int = 0) -> int:
    raw = (request.form.get(name) if request.method == "POST"
           else request.args.get(name))
    if raw is None or raw == "":
        return default
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        return default


# ─── Form page ────────────────────────────────────────────────────────────
@public_bp.route("/quote/request", methods=["GET", "POST"])
def quote_request():
    """Show / handle the standalone quote-request form.

    Accepts prefill from query string: product_type, product_id,
    product_name.
    """
    prefill = {
        "product_type": request.args.get("product_type", ""),
        "product_id": request.args.get("product_id", ""),
        "product_name": request.args.get("product_name", ""),
    }

    if request.method == "POST":
        product_type = (request.form.get("product_type") or "").strip().lower()
        product_id = _int_arg("product_id", 0, minimum=1)

        # Basic validation before we bother Mongo.
        if product_type not in ("activity", "hotel", "package"):
            flash("Please select a valid product type.", "danger")
            return render_template(
                "public/quote_request_form.html", prefill=prefill,
            )
        if not product_id:
            flash("Missing product id.", "danger")
            return render_template(
                "public/quote_request_form.html", prefill=prefill,
            )

        try:
            enquiry = quote_service.create_quote_request(
                product_type=product_type,
                product_id=product_id,
                name=request.form.get("name", ""),
                email=request.form.get("email", ""),
                phone=request.form.get("phone") or None,
                preferred_start=_parse_date(request.form.get("preferred_start")),
                preferred_end=_parse_date(request.form.get("preferred_end")),
                adults=_int_arg("adults", 1, minimum=1),
                children=_int_arg("children", 0, minimum=0),
                message=request.form.get("message") or None,
            )
        except InvalidQuoteInput as exc:
            flash(f"Please check your details: {exc}", "danger")
            return render_template(
                "public/quote_request_form.html", prefill=prefill,
            )
        except quote_service.QuoteError as exc:
            # Mongo unavailable etc. — friendly message, keep the form.
            current_app.logger.warning("quote_request failed: %s", exc)
            flash(
                "We could not save your request right now. Please try "
                "again in a few minutes or email us directly.",
                "danger",
            )
            return render_template(
                "public/quote_request_form.html", prefill=prefill,
            )

        return redirect(url_for("public.quote_request_thanks"))

    return render_template("public/quote_request_form.html", prefill=prefill)


@public_bp.route("/quote/request/thanks")
def quote_request_thanks():
    """Simple thank-you page after a successful request."""
    return render_template("public/quote_request_thanks.html")


# ─── Customer quote view ──────────────────────────────────────────────────
@public_bp.route("/quote/<reference>")
def quote_view(reference: str):
    """Show a single quote to the customer, with accept/decline actions."""
    quote = quote_service.get_quote_by_reference(reference)
    if quote is None:
        abort(404)

    # If the quote expired since it was sent, auto-transition on view.
    if quote.status == "sent" and quote.valid_until:
        if quote.valid_until < date.today():
            try:
                quote_service.expire_all_overdue()
                current_app.logger.info(
                    "quote %s auto-expired on view", quote.reference
                )
                # Re-fetch so the template sees the updated status
                quote = quote_service.get_quote_by_reference(reference)
            except Exception as exc:  # noqa: BLE001
                current_app.logger.warning(
                    "auto-expire failed for %s: %s", reference, exc
                )

    return render_template("public/quote_view.html", quote=quote)


@public_bp.route("/quote/<reference>/accept", methods=["POST"])
def quote_accept(reference: str):
    """Customer accepts a sent quote → creates a pending Booking."""
    quote = quote_service.get_quote_by_reference(reference)
    if quote is None:
        abort(404)

    try:
        quote, booking = quote_service.accept_quote(
            quote,
            customer_user=current_user_or_none(),
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
    except InvalidQuoteState as exc:
        flash(f"Could not accept: {exc}", "danger")
        return redirect(url_for("public.quote_view", reference=reference))

    flash(
        f"Thank you! Your booking reference is {booking.reference}. "
        "A confirmation email is on its way.",
        "success",
    )
    return redirect(url_for(
        "public.booking_confirmation", reference=booking.reference,
    ))


@public_bp.route("/quote/<reference>/decline", methods=["POST"])
def quote_decline(reference: str):
    """Customer declines a sent quote."""
    quote = quote_service.get_quote_by_reference(reference)
    if quote is None:
        abort(404)

    reason = (request.form.get("reason") or "").strip() or None

    try:
        quote_service.decline_quote(quote, reason=reason)
    except InvalidQuoteState as exc:
        flash(f"Could not decline: {exc}", "danger")
        return redirect(url_for("public.quote_view", reference=reference))

    flash("Your decision has been recorded. Thank you for letting us know.", "info")
    return redirect(url_for("public.quote_view", reference=reference))


# ─── Small helpers ────────────────────────────────────────────────────────
def current_user_or_none():
    """Return the current user if logged in, else None.

    Wrapped so this module does not import flask_login at the top,
    which would pull in session cookies where not needed.
    """
    try:
        from flask_login import current_user
        return current_user if getattr(current_user, "is_authenticated", False) else None
    except Exception:  # noqa: BLE001
        return None
