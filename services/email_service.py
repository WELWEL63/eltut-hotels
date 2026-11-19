"""
services/email_service.py
─────────────────────────
All transactional emails for eltut-tours-platform.

Every outbound message in the app goes through this service. It renders
Jinja templates from templates/emails/ and hands them to Flask-Mail for
delivery via IONOS SMTP.

PUBLIC API
    is_configured() -> bool
    send_raw(to, subject, html=None, text=None) -> bool
    send_welcome(user, verify_token=None) -> bool
    send_verify_email(user, token) -> bool
    send_password_reset(user, token) -> bool
    send_booking_confirmation(booking) -> bool
    send_admin_new_booking(booking) -> bool
    send_booking_confirmed(booking) -> bool
    send_booking_cancelled(booking, reason=None) -> bool
    send_enquiry_received(enquiry) -> bool

DESIGN NOTES
    - Only send_raw() calls Flask-Mail. Everything else builds arguments
      and delegates, which makes mocking trivial.
    - If MAIL_USERNAME / MAIL_PASSWORD are not set, send_raw() logs and
      returns False WITHOUT raising. This lets dev + tests run without
      an SMTP server.
    - Templates live in templates/emails/. If a template is missing,
      send_raw() falls back to a minimal plain-text body so the caller
      still gets an email (useful while templates are being built).
    - Send failures NEVER propagate. A mail-server outage must not
      break booking creation or password reset.
    - No Flask request imports — callers pass the objects.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from flask import current_app, render_template
from flask_mail import Message

from extensions import mail
from services.quote_image_service import hotel_cover_image_url


log = logging.getLogger(__name__)


# ─── Domain exceptions ─────────────────────────────────────────────
class EmailError(Exception):
    """Base class for email-domain errors."""


# ─── Config helpers ────────────────────────────────────────────────
def _cfg() -> dict[str, str]:
    return {
        "username": current_app.config.get("MAIL_USERNAME") or "",
        "password": current_app.config.get("MAIL_PASSWORD") or "",
        "sender": current_app.config.get("MAIL_DEFAULT_SENDER") or "",
        "admin": current_app.config.get("MAIL_ADMIN_RECIPIENT") or "",
        "app_name": current_app.config.get("APP_NAME") or "ElTut Tours",
        "base_url": (current_app.config.get("APP_BASE_URL") or "").rstrip("/"),
    }


_PLACEHOLDER_TOKENS = (
    "your-ionos-smtp-password",
    "changeme",
    "placeholder",
)


def _is_placeholder(value: str) -> bool:
    v = (value or "").strip().lower()
    if not v:
        return True
    return any(tok in v for tok in _PLACEHOLDER_TOKENS)


def is_configured() -> bool:
    """
    True when real SMTP credentials are present.

    Returns False when the username or password is missing or holds a
    placeholder from .env.example.
    """
    cfg = _cfg()
    if _is_placeholder(cfg["username"]) or _is_placeholder(cfg["password"]):
        return False
    return True


# ─── Low-level send ────────────────────────────────────────────────
def send_raw(
    *,
    to: str | list[str],
    subject: str,
    html: str | None = None,
    text: str | None = None,
) -> bool:
    """
    Send an email. Returns True on success, False if mail is not
    configured or if the SMTP call fails.

    Never raises — this is deliberate so a mail outage cannot break a
    user-facing action.
    """
    if not to or not subject:
        log.warning("send_raw called without recipient or subject")
        return False

    if not is_configured():
        log.info(
            "SMTP not configured — skipping email %r to %r", subject, to
        )
        return False

    cfg = _cfg()
    sender = cfg["sender"] or cfg["username"]
    recipients = [to] if isinstance(to, str) else list(to)

    try:
        msg = Message(
            subject=subject,
            sender=sender,
            recipients=recipients,
        )
        if text:
            msg.body = text
        if html:
            msg.html = html
        if not text and not html:
            msg.body = subject
        mail.send(msg)
        log.info("sent email %r to %r", subject, recipients)
        return True
    except Exception as exc:  # noqa: BLE001
        log.exception("send_raw failed for %r -> %r: %s", subject, recipients, exc)
        return False


# ─── Template rendering with fallback ──────────────────────────────
def _render_email(
    template_name: str,
    *,
    context: dict[str, Any],
    fallback_text: str,
) -> tuple[str | None, str]:
    """
    Render a Jinja template for an email.

    Returns (html, text). The HTML is None if the template is missing,
    in which case the caller should use the text fallback.
    """
    path = f"emails/{template_name}"
    try:
        html = render_template(path, **context)
        return html, fallback_text
    except Exception as exc:  # noqa: BLE001 — template may not exist yet
        log.debug("email template %r missing or failed to render: %s", path, exc)
        return None, fallback_text


def _url(path: str) -> str:
    """Build an absolute URL from APP_BASE_URL + a path."""
    base = _cfg()["base_url"]
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def _absolute_url(value: str | None) -> str | None:
    """Make a stored relative URL usable by remote email clients."""
    if not value or value.startswith(("http://", "https://")):
        return value
    return _url(value)


# ─── Public email functions ────────────────────────────────────────
def send_welcome(user: Any, verify_token: Optional[str] = None) -> bool:
    """Welcome email sent right after registration."""
    if user is None or not getattr(user, "email", None):
        return False
    cfg = _cfg()
    verify_url = _url(f"/verify-email/{verify_token}") if verify_token else None
    context = {
        "user": user,
        "app_name": cfg["app_name"],
        "base_url": cfg["base_url"],
        "verify_url": verify_url,
    }
    fallback = (
        f"Welcome to {cfg['app_name']}, {user.full_name}!\n\n"
        "Your account is ready.\n"
    )
    if verify_url:
        fallback += f"Verify your email: {verify_url}\n"
    html, text = _render_email(
        "welcome.html", context=context, fallback_text=fallback
    )
    return send_raw(
        to=user.email,
        subject=f"Welcome to {cfg['app_name']}",
        html=html,
        text=text,
    )


def send_verify_email(user: Any, token: str) -> bool:
    """Email-verification link."""
    if user is None or not getattr(user, "email", None) or not token:
        return False
    cfg = _cfg()
    verify_url = _url(f"/verify-email/{token}")
    context = {
        "user": user,
        "app_name": cfg["app_name"],
        "base_url": cfg["base_url"],
        "verify_url": verify_url,
    }
    fallback = (
        f"Hi {user.full_name},\n\n"
        f"Please verify your email by opening:\n{verify_url}\n"
    )
    html, text = _render_email(
        "verify_email.html", context=context, fallback_text=fallback
    )
    return send_raw(
        to=user.email,
        subject=f"Verify your {cfg['app_name']} email",
        html=html,
        text=text,
    )


def send_password_reset(user: Any, token: str) -> bool:
    """Password-reset link."""
    if user is None or not getattr(user, "email", None) or not token:
        return False
    cfg = _cfg()
    reset_url = _url(f"/reset-password/{token}")
    context = {
        "user": user,
        "app_name": cfg["app_name"],
        "base_url": cfg["base_url"],
        "reset_url": reset_url,
    }
    fallback = (
        f"Hi {user.full_name},\n\n"
        f"Reset your password by opening:\n{reset_url}\n"
        "This link expires in 30 minutes. If you didn't request this, "
        "you can ignore this email.\n"
    )
    html, text = _render_email(
        "password_reset.html", context=context, fallback_text=fallback
    )
    return send_raw(
        to=user.email,
        subject=f"Reset your {cfg['app_name']} password",
        html=html,
        text=text,
    )


def send_booking_confirmation(booking: Any) -> bool:
    """Customer-facing booking confirmation (sent right after creation)."""
    if booking is None:
        return False
    email = (
        getattr(booking, "guest_email", None)
        or getattr(getattr(booking, "user", None), "email", None)
    )
    if not email:
        return False

    cfg = _cfg()
    booking_url = _url(f"/account/bookings/{booking.reference}")
    context = {
        "booking": booking,
        "app_name": cfg["app_name"],
        "base_url": cfg["base_url"],
        "booking_url": booking_url,
    }
    fallback = (
        f"Booking confirmed: {booking.reference}\n"
        f"Product: {booking.product_type} #{booking.product_id}\n"
        f"Total:   {booking.currency} {booking.total_amount}\n"
        f"Details: {booking_url}\n"
    )
    html, text = _render_email(
        "booking_confirmation.html",
        context=context,
        fallback_text=fallback,
    )
    return send_raw(
        to=email,
        subject=f"Booking received — {booking.reference}",
        html=html,
        text=text,
    )


def send_admin_new_booking(booking: Any) -> bool:
    """Internal notification to the admin inbox when a booking is created."""
    if booking is None:
        return False
    admin = _cfg()["admin"]
    if not admin:
        return False

    cfg = _cfg()
    context = {
        "booking": booking,
        "app_name": cfg["app_name"],
        "admin_url": _url(f"/admin/bookings/{booking.id}"),
    }
    fallback = (
        f"New booking: {booking.reference}\n"
        f"Product: {booking.product_type} #{booking.product_id}\n"
        f"Total:   {booking.currency} {booking.total_amount}\n"
    )
    html, text = _render_email(
        "admin_new_booking.html",
        context=context,
        fallback_text=fallback,
    )
    return send_raw(
        to=admin,
        subject=f"[admin] New booking {booking.reference}",
        html=html,
        text=text,
    )


def send_booking_confirmed(booking: Any) -> bool:
    """Sent when a payment is captured — status becomes confirmed."""
    if booking is None:
        return False
    email = (
        getattr(booking, "guest_email", None)
        or getattr(getattr(booking, "user", None), "email", None)
    )
    if not email:
        return False

    cfg = _cfg()
    context = {
        "booking": booking,
        "app_name": cfg["app_name"],
        "booking_url": _url(f"/account/bookings/{booking.reference}"),
    }
    fallback = (
        f"Payment received for booking {booking.reference}.\n"
        f"Total paid: {booking.currency} {booking.total_amount}\n"
    )
    html, text = _render_email(
        "booking_confirmed.html",
        context=context,
        fallback_text=fallback,
    )
    return send_raw(
        to=email,
        subject=f"Payment confirmed — {booking.reference}",
        html=html,
        text=text,
    )


def send_booking_cancelled(booking: Any, reason: str | None = None) -> bool:
    """Sent when a booking is cancelled."""
    if booking is None:
        return False
    email = (
        getattr(booking, "guest_email", None)
        or getattr(getattr(booking, "user", None), "email", None)
    )
    if not email:
        return False

    cfg = _cfg()
    context = {
        "booking": booking,
        "reason": reason or booking.cancellation_reason,
        "app_name": cfg["app_name"],
    }
    fallback = (
        f"Booking {booking.reference} has been cancelled.\n"
        f"Reason: {reason or booking.cancellation_reason or 'not specified'}\n"
    )
    html, text = _render_email(
        "booking_cancelled.html",
        context=context,
        fallback_text=fallback,
    )
    return send_raw(
        to=email,
        subject=f"Booking cancelled — {booking.reference}",
        html=html,
        text=text,
    )


def send_enquiry_received(enquiry: dict[str, Any]) -> bool:
    """Admin notification when a public enquiry is submitted."""
    if not enquiry:
        return False
    admin = _cfg()["admin"]
    if not admin:
        return False

    cfg = _cfg()
    context = {
        "enquiry": enquiry,
        "app_name": cfg["app_name"],
    }
    fallback = (
        f"New enquiry from {enquiry.get('name')} <{enquiry.get('email')}>\n"
        f"Type:    {enquiry.get('type')}\n"
        f"Message: {enquiry.get('message') or '(none)'}\n"
    )
    html, text = _render_email(
        "admin_new_enquiry.html",
        context=context,
        fallback_text=fallback,
    )
    return send_raw(
        to=admin,
        subject=f"[admin] New {enquiry.get('type', 'enquiry')}",
        html=html,
        text=text,
    )


# ─── Quote system emails ──────────────────────────────────────────────────
def send_quote_request_received(enquiry: dict[str, Any]) -> bool:
    """Tell the customer we've received their quote request."""
    to = (enquiry or {}).get("email")
    if not to:
        log.warning("send_quote_request_received: no recipient")
        return False

    cfg = _cfg()
    name = (enquiry.get("name") or "there").strip()

    context = {
        "customer_name": name,
        "product_type": enquiry.get("product_type"),
        "product_id": enquiry.get("product_id"),
        "message": enquiry.get("message"),
        "app_name": cfg["app_name"],
        "base_url": cfg["base_url"],
    }
    fallback = (
        f"Hi {name},\n\n"
        "Thanks for requesting a quote from ElTut Tours. We have "
        "received your request and one of our travel specialists will "
        "reply within 24 hours with pricing and availability.\n\n"
        "If you need to reach us sooner, just reply to this email.\n\n"
        f"— The {cfg['app_name']} team"
    )
    html, text = _render_email(
        "quote_request_received.html",
        context=context,
        fallback_text=fallback,
    )
    return send_raw(
        to=to,
        subject=f"{cfg['app_name']} — we received your quote request",
        html=html,
        text=text,
    )


def send_admin_quote_request(enquiry: dict[str, Any]) -> bool:
    """Notify the admin inbox of a new quote request."""
    to = _cfg()["admin"]
    if not to:
        log.info("send_admin_quote_request: no admin recipient configured")
        return False

    cfg = _cfg()
    name = (enquiry.get("name") or "—").strip()
    email = (enquiry.get("email") or "—").strip()
    ptype = enquiry.get("product_type") or "—"
    pid = enquiry.get("product_id")

    context = {
        "name": name,
        "email": email,
        "phone": enquiry.get("phone"),
        "product_type": ptype,
        "product_id": pid,
        "message": enquiry.get("message"),
        "enquiry_id": str(enquiry.get("_id")) if enquiry.get("_id") else None,
        "base_url": cfg["base_url"],
    }
    fallback = (
        "New quote request received.\n\n"
        f"From:  {name} <{email}>\n"
        f"Phone: {enquiry.get('phone') or '—'}\n"
        f"Product: {ptype} #{pid}\n\n"
        f"Message:\n{enquiry.get('message') or '(none)'}\n\n"
        "Open /admin/quotes to respond."
    )
    html, text = _render_email(
        "admin_quote_request.html",
        context=context,
        fallback_text=fallback,
    )
    return send_raw(
        to=to,
        subject=f"[{cfg['app_name']}] New quote request — {ptype} #{pid}",
        html=html,
        text=text,
    )


def send_quote_to_customer(quote: Any) -> bool:
    """Send a priced quote to the customer with accept/decline links."""
    if quote is None:
        return False
    to = getattr(quote, "customer_email", None)
    if not to:
        log.warning("send_quote_to_customer: quote has no customer_email")
        return False

    cfg = _cfg()
    reference = getattr(quote, "reference", "")
    view_url = f"{cfg['base_url']}/quote/{reference}" if cfg["base_url"] else f"/quote/{reference}"

    context = {
        "customer_name": getattr(quote, "customer_name", None) or "there",
        "reference": reference,
        "product_type": getattr(quote, "product_type", None),
        "product_name": getattr(quote, "product_name_snapshot", None),
        "price": getattr(quote, "price", None),
        "currency": getattr(quote, "currency", "GBP"),
        "check_in_date": getattr(quote, "check_in_date", None),
        "check_out_date": getattr(quote, "check_out_date", None),
        "valid_until": getattr(quote, "valid_until", None),
        "message": getattr(quote, "message", None),
        "image_url": (
            _absolute_url(getattr(quote, "image_url", None))
            or (
                _absolute_url(hotel_cover_image_url(quote.product_id))
                if getattr(quote, "product_type", None) == "hotel"
                else None
            )
        ),
        "view_url": view_url,
        "app_name": cfg["app_name"],
    }

    price_str = f"{context['currency']} {context['price']}" if context["price"] is not None else "see link"
    fallback = (
        f"Hi {context['customer_name']},\n\n"
        "Here is your personalised quote from ElTut Tours.\n\n"
        f"Reference: {reference}\n"
        f"Price:     {price_str}\n"
        f"Stay:      {context['check_in_date'] or '—'} to "
        f"{context['check_out_date'] or '—'}\n"
        f"Valid until: {context['valid_until'] or 'no expiry'}\n\n"
        f"{context['message'] or ''}\n\n"
        f"View, accept, or decline online:\n{view_url}\n\n"
        f"— The {cfg['app_name']} team"
    )
    html, text = _render_email(
        "quote_sent.html",
        context=context,
        fallback_text=fallback,
    )
    return send_raw(
        to=to,
        subject=f"Your ElTut Tours quote — {reference}",
        html=html,
        text=text,
    )


# ─── Review emails ───────────────────────────────────────────────────────
def send_review_thanks(
    *,
    to_email: str,
    to_name: str,
    product_type: str,
    product_id: int,
    rating: int,
    verified: bool = False,
) -> bool:
    """Thank the reviewer after a successful submission."""
    if not to_email:
        return False

    cfg = _cfg()
    badge = "verified " if verified else ""
    subject = f"Thanks for your {badge}review — {cfg['app_name']}"

    fallback = (
        f"Hi {to_name or 'there'},\n\n"
        f"Thank you for leaving a {rating}-star {badge}review of "
        f"{product_type} #{product_id} on {cfg['app_name']}.\n\n"
        "Every review helps future travellers and our team. "
        "If you have any issues with your booking, just reply to this email.\n\n"
        f"— The {cfg['app_name']} team"
    )

    context = {
        "customer_name": to_name,
        "product_type": product_type,
        "product_id": product_id,
        "rating": rating,
        "verified": verified,
        "app_name": cfg["app_name"],
        "base_url": cfg["base_url"],
    }
    html, text = _render_email(
        "review_thanks.html",
        context=context,
        fallback_text=fallback,
    )
    return send_raw(to=to_email, subject=subject, html=html, text=text)
