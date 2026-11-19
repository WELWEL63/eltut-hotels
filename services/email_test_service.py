"""Safe sample rendering and delivery for the admin email test page."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from flask import current_app

from services import email_service


EMAIL_TEMPLATES = {
    "welcome.html": "Welcome",
    "verify_email.html": "Verify email",
    "password_reset.html": "Password reset",
    "booking_confirmation.html": "Booking received",
    "admin_new_booking.html": "New booking (admin)",
    "booking_confirmed.html": "Booking confirmed",
    "booking_cancelled.html": "Booking cancelled",
    "admin_new_enquiry.html": "Contact enquiry (admin)",
    "quote_request_received.html": "Quote request received",
    "admin_quote_request.html": "New quote request (admin)",
    "quote_sent.html": "Priced quote sent",
    "review_thanks.html": "Review thanks",
}


class EmailTestError(Exception):
    """Raised when a safe sample email cannot be rendered or sent."""


def _sample_contexts() -> dict[str, dict[str, Any]]:
    config = current_app.config
    app_name = config.get("APP_NAME") or "ElTut Tours"
    base_url = (config.get("APP_BASE_URL") or "https://example.test").rstrip("/")
    sample_user = SimpleNamespace(
        full_name="Sample Guest",
        email="sample-guest@example.invalid",
    )
    sample_booking = SimpleNamespace(
        reference="ELT-TEST-00001",
        guest_name="Sample Guest",
        guest_email="sample-guest@example.invalid",
        guest_phone="+441234567890",
        product_type="hotel",
        product_id=12,
        status="confirmed",
        currency="GBP",
        total_amount=Decimal("125.00"),
        check_in_date=date(2027, 3, 1),
        check_out_date=date(2027, 3, 3),
        travellers_adults=2,
        travellers_children=1,
        travellers_infants=0,
        special_requests="Sample request",
        cancellation_reason="Sample cancellation reason",
        user=sample_user,
    )
    sample_enquiry = {
        "name": "Sample Guest",
        "email": "sample-guest@example.invalid",
        "phone": "+441234567890",
        "type": "contact",
        "product_type": "hotel",
        "product_id": 12,
        "message": "This is sample enquiry content.",
        "_id": "sample-request",
    }

    return {
        "welcome.html": {
            "user": sample_user,
            "app_name": app_name,
            "base_url": base_url,
            "verify_url": f"{base_url}/verify-email/sample-token",
        },
        "verify_email.html": {
            "user": sample_user,
            "app_name": app_name,
            "base_url": base_url,
            "verify_url": f"{base_url}/verify-email/sample-token",
        },
        "password_reset.html": {
            "user": sample_user,
            "app_name": app_name,
            "base_url": base_url,
            "reset_url": f"{base_url}/reset-password/sample-token",
        },
        "booking_confirmation.html": {
            "booking": sample_booking,
            "app_name": app_name,
            "base_url": base_url,
            "booking_url": f"{base_url}/account/bookings/{sample_booking.reference}",
        },
        "admin_new_booking.html": {
            "booking": sample_booking,
            "app_name": app_name,
            "admin_url": f"{base_url}/admin/bookings/12",
        },
        "booking_confirmed.html": {
            "booking": sample_booking,
            "app_name": app_name,
            "booking_url": f"{base_url}/account/bookings/{sample_booking.reference}",
        },
        "booking_cancelled.html": {
            "booking": sample_booking,
            "reason": sample_booking.cancellation_reason,
            "app_name": app_name,
        },
        "admin_new_enquiry.html": {
            "enquiry": sample_enquiry,
            "app_name": app_name,
        },
        "quote_request_received.html": {
            "customer_name": "Sample Guest",
            "product_type": "hotel",
            "product_id": 12,
            "message": "This is sample quote-request content.",
            "app_name": app_name,
            "base_url": base_url,
        },
        "admin_quote_request.html": {
            "name": "Sample Guest",
            "email": "sample-guest@example.invalid",
            "phone": "+441234567890",
            "product_type": "hotel",
            "product_id": 12,
            "message": "This is sample quote-request content.",
            "enquiry_id": "sample-request",
            "base_url": base_url,
        },
        "quote_sent.html": {
            "customer_name": "Sample Guest",
            "reference": "Q-TEST-00001",
            "product_type": "hotel",
            "product_name": "Sample Hotel",
            "price": Decimal("125.00"),
            "currency": "GBP",
            "check_in_date": date(2027, 3, 1),
            "check_out_date": date(2027, 3, 3),
            "valid_until": date(2027, 2, 1),
            "message": "This is a sample priced quote.",
            "image_url": f"{base_url}/static/images/sample-hotel.jpg",
            "view_url": f"{base_url}/quote/Q-TEST-00001",
            "app_name": app_name,
        },
        "review_thanks.html": {
            "customer_name": "Sample Guest",
            "product_type": "hotel",
            "product_id": 12,
            "rating": 5,
            "verified": True,
            "app_name": app_name,
            "base_url": base_url,
        },
    }


def render_sample(template_name: str) -> tuple[str, str]:
    """Render one allow-listed email template using synthetic sample data."""
    if template_name not in EMAIL_TEMPLATES:
        raise EmailTestError("Choose a valid email template.")

    html, text = email_service._render_email(
        template_name,
        context=_sample_contexts()[template_name],
        fallback_text=f"Sample test email for {EMAIL_TEMPLATES[template_name]}.",
    )
    if html is None:
        raise EmailTestError(
            f"The {template_name} template could not be rendered; no email was sent."
        )
    return html, text


def send_sample(template_name: str) -> tuple[str, bool]:
    """Send an allow-listed sample only to the configured admin recipient."""
    recipient = (current_app.config.get("MAIL_ADMIN_RECIPIENT") or "").strip()
    if not recipient:
        raise EmailTestError(
            "MAIL_ADMIN_RECIPIENT is not configured; no email was sent."
        )
    if not email_service.is_configured():
        raise EmailTestError(
            "SMTP credentials are not configured; no email was sent."
        )

    html, text = render_sample(template_name)
    label = EMAIL_TEMPLATES[template_name]
    sent = email_service.send_raw(
        to=recipient,
        subject=f"[TEST] {current_app.config.get('APP_NAME') or 'ElTut Tours'} - {label}",
        html=html,
        text=text,
    )
    return recipient, sent
