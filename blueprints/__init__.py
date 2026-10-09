"""
blueprints/__init__.py
──────────────────────
The HTTP layer for eltut-tours-platform.

Four blueprints, each with a distinct audience and URL prefix:

    public      "/"           Customer-facing: browse, search, book, review
    auth        "/"           Register, login, password reset, verify
    account     "/account"    Logged-in customer area: my bookings, profile
    admin       "/admin"      Admin panel: CRUD, bookings, reports, media
    api         "/api/v1"     REST API (JSON)

USAGE IN THE FACTORY (app.py)
    from blueprints.public import public_bp
    app.register_blueprint(public_bp)

    from blueprints.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

Each blueprint is defined in its own __init__.py and imports its routes
modules for side effects. Routes stay thin — they parse requests, call
into services/, and render responses.
"""

from __future__ import annotations

__all__: list[str] = [
    "public",
    "auth",
    "account",
    "admin",
    "api",
]
