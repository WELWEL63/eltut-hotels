"""
blueprints/auth/__init__.py
───────────────────────────
The authentication blueprint — register, login, logout, password reset,
and email verification.

ROUTES
    GET/POST /register                  create account
    GET/POST /login                     sign in
    POST     /logout                    sign out
    GET/POST /forgot-password           request reset email
    GET/POST /reset-password/<token>    set new password
    GET      /verify-email/<token>      confirm email address

DESIGN NOTES
    - Routes are thin: they parse the form and call into
      services.auth_service. Business logic stays in services.
    - CSRF is provided by Flask-WTF forms automatically.
    - Rate limiting for login is enforced by services.auth_service.
    - Successful registration auto-claims guest bookings with the
      same email (see auth_service.claim_guest_bookings).
"""

from __future__ import annotations

from flask import Blueprint


auth_bp = Blueprint(
    "auth",
    __name__,
    # templates resolve against the app's top-level templates/ folder
)


# ─── Route registration ────────────────────────────────────────────
from blueprints.auth import routes  # noqa: E402,F401
from blueprints.auth import password_routes  # noqa: E402,F401


__all__: list[str] = ["auth_bp"]
