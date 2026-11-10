"""
blueprints/admin/__init__.py
────────────────────────────
The admin blueprint — CRUD, bookings, reports, media, users.

URL PREFIX
    "/admin" (mounted in app.py)

ROUTE MODULES
    routes.py            dashboard
    activity_admin.py    activities + children CRUD
    hotel_admin.py       hotels + rooms + facilities CRUD
    package_admin.py     packages + itineraries + flights CRUD
    booking_admin.py     bookings, status changes, refunds
    user_admin.py        users list/toggle/role
    review_admin.py      moderation of Mongo reviews
    report_routes.py     dashboards and charts (report_service)
    media_routes.py      upload + manage images
    offer_admin.py       home-page offers curation

ACCESS CONTROL
    Every admin route is protected by @admin_required, which:
      1. requires an authenticated session (login_required), and
      2. requires current_user.is_admin == True.

    Non-admins receive 403 (Forbidden). Guests are redirected to login.
"""

from __future__ import annotations

from functools import wraps

from flask import abort, redirect, request, url_for
from flask_login import current_user, login_required

from flask import Blueprint


admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
)


# ─── Access control decorator ───────────────────────────────────────
def admin_required(view_func):
    """
    Decorator: require login AND role='admin'.

    Guests → redirect to login with ?next= so they land back where they
    intended. Logged-in non-admins → 403.
    """
    @wraps(view_func)
    @login_required
    def wrapper(*args, **kwargs):
        if not getattr(current_user, "is_admin", False):
            abort(403)
        return view_func(*args, **kwargs)
    return wrapper


# ─── Blueprint-wide guard (defence in depth) ────────────────────────
@admin_bp.before_request
def _admin_guard():
    """
    Runs before EVERY admin request.

    Belt-and-braces: even if we forget @admin_required on a route, this
    catches it. Guests go to login; non-admins get 403.
    """
    # Allow OPTIONS through for CORS/pre-flight; everything else requires auth.
    if request.method == "OPTIONS":
        return None
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login", next=request.full_path))
    if not getattr(current_user, "is_admin", False):
        abort(403)
    return None


# ─── Route registration ─────────────────────────────────────────────
# Modules are imported at the bottom so the @admin_bp.route decorators
# fire against the blueprint object.

from blueprints.admin import routes           # noqa: E402,F401
from blueprints.admin import activity_admin   # noqa: E402,F401
from blueprints.admin import hotel_admin      # noqa: E402,F401
from blueprints.admin import package_admin    # noqa: E402,F401
from blueprints.admin import booking_admin    # noqa: E402,F401
from blueprints.admin import user_admin       # noqa: E402,F401
from blueprints.admin import review_admin     # noqa: E402,F401
from blueprints.admin import report_routes    # noqa: E402,F401
from blueprints.admin import media_routes     # noqa: E402,F401
from blueprints.admin import content_admin    # noqa: E402,F401
from blueprints.admin import airline_admin    # noqa: E402,F401
from blueprints.admin import quote_admin      # noqa: E402,F401
from blueprints.admin import destination_admin  # noqa: E402,F401
from blueprints.admin import offer_admin        # noqa: E402,F401
from blueprints.admin import flight_admin       # noqa: E402,F401
from blueprints.admin import chat_admin  # noqa: E402,F401

__all__: list[str] = ["admin_bp", "admin_required"]

# Imported last — after admin_bp is fully constructed — to avoid
# a circular-import stub where @admin_bp.route() silently no-ops.
from blueprints.admin import hotel_csv_admin    # noqa: E402,F401
