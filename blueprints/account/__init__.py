"""
blueprints/account/__init__.py
──────────────────────────────
The customer account area — logged-in users only.

URL PREFIX
    "/account" (mounted in app.py)

ROUTES
    GET       /account                          dashboard
    GET       /account/bookings                 my bookings list
    GET       /account/bookings/<ref>           booking detail
    POST      /account/bookings/<ref>/cancel    cancel a booking
    GET/POST  /account/profile                  edit name/phone/password

DESIGN NOTES
    - Every route requires login (checked via @login_required).
    - Booking cancellation calls services.booking_service.cancel_booking
      so the status history and audit trail stay consistent.
    - Templates extend base.html.
"""

from __future__ import annotations

from flask import Blueprint


account_bp = Blueprint(
    "account",
    __name__,
    url_prefix="/account",
)


# ─── Route registration ────────────────────────────────────────────
from blueprints.account import routes  # noqa: E402,F401


__all__: list[str] = ["account_bp"]
