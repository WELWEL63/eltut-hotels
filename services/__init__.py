"""
services/__init__.py
────────────────────
Business-logic layer for eltut-tours-platform.

Every module in this package does ONE job and can be tested without a
running Flask server (they only need an app context when they touch the
DB). Blueprints stay thin: they parse requests, call a service, and
render a response. This separation is what makes the code testable and
is explicitly required by the coursework brief.

MODULE MANIFEST
    auth_service           register, login helpers, password reset,
                           email verification, guest booking claim
    booking_service        create/cancel bookings, status history,
                           reference generation
    pricing_service        calculate hotel room stay totals
    availability_service   check hotel room capacity for a date range
    payment_service        PayPal REST API wrapper (create payment,
                           execute payment, handle refunds)
    email_service          transactional email templates via Flask-Mail
    report_service         admin dashboard aggregates (sales, bookings,
                           top products, search analytics)

USAGE FROM A BLUEPRINT

    # Preferred — imports only what is needed:
    from services import booking_service, pricing_service

    # Explicit — one function:
    from services.booking_service import create_booking

The package __init__ itself does NOT import any submodule eagerly. That
keeps `import services` fast and safe (no DB connection is opened just
because the package was loaded). Submodules are imported on first use.
"""

from __future__ import annotations

__all__: list[str] = [
    "auth_service",
    "booking_service",
    "pricing_service",
    "availability_service",
    "payment_service",
    "email_service",
    "report_service",
    "content_service",
    "quote_service",
    "search_service",
]


# ─── Manifest (used by tooling and the coursework report) ──────────
SERVICE_MANIFEST: dict[str, str] = {
    "auth_service": (
        "Register, login helpers, password reset, email verification, "
        "guest booking claim on register."
    ),
    "booking_service": (
        "Create and cancel bookings, generate human-friendly references, "
        "write booking_status_history rows alongside status changes."
    ),
    "pricing_service": (
        "Calculate the total for a hotel room stay."
    ),
    "availability_service": (
        "Check hotel room capacity over a requested date range."
    ),
    "payment_service": (
        "PayPal REST API wrapper: create payment, execute payment, refund, "
        "webhook signature verification."
    ),
    "email_service": (
        "Transactional email templates rendered via Jinja and sent through "
        "Flask-Mail (IONOS SMTP)."
    ),
    "report_service": (
        "Admin dashboard aggregates: sales totals, bookings per status, "
        "top products, search analytics via the Mongo search_events "
        "collection."
    ),
    "content_service": (
        "Admin-editable public page content — key/value store with "
        "in-request cache; falls back to registry defaults."
    ),
    "quote_service": (
        "Create / price / send / accept / decline quotes; "
        "quote-request creation from public forms."
    ),
    "search_service": (
        "Search hotels filtered by destination, dates, and party size."
    ),
}


def service_info(name: str) -> str:
    """Return the one-line description of a service module."""
    return SERVICE_MANIFEST.get(name, "unknown service")
