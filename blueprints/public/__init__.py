"""
blueprints/public/__init__.py
─────────────────────────────
The customer-facing public blueprint — the site visitors see.

URL PREFIX
    "/" (root) — no prefix. Routes live at the top level:
        /                           home
        /about                      about us
        /contact                    contact form
        /activities                 activity listing (with filters)
        /activities/<slug>          activity detail
        /hotels                     hotel listing
        /hotels/<slug>              hotel detail
        /packages                   package listing
        /packages/<slug>            package detail
        /booking/<product>/<id>     booking flow (auth-aware, guest ok)
        /booking/paypal/return      PayPal return URL
        /booking/paypal/cancel      PayPal cancel URL
        /reviews/submit             POST a review
        /enquiries                  POST a quote request / contact message

DESIGN NOTES
    - Route modules are imported at the bottom of this file so their
      @public_bp.route decorators fire against the blueprint object.
      This is the standard Flask pattern that avoids circular imports.
    - Template lookup uses the top-level templates/ folder; templates
      live under templates/public/*.html.
    - The blueprint deliberately has NO url_prefix so routes are
      top-level. Attach a prefix in app.py if the site ever needs to be
      mounted under a subpath.
"""

from __future__ import annotations

from flask import Blueprint


public_bp = Blueprint(
    "public",
    __name__,
    # template_folder defaults to the app's own templates/ folder —
    # we deliberately do NOT override it so templates/public/*.html
    # resolves against the top-level templates/ directory.
)


# ─── Route registration ────────────────────────────────────────────
# Each import at the bottom registers its routes on public_bp via the
# @public_bp.route decorator. Adding a new route file means adding one
# line here — self-documenting and diff-friendly.

from blueprints.public import routes  # noqa: E402,F401
from blueprints.public import activity_routes  # noqa: E402,F401
from blueprints.public import hotel_routes  # noqa: E402,F401
from blueprints.public import package_routes  # noqa: E402,F401
from blueprints.public import booking_routes  # noqa: E402,F401
from blueprints.public import review_routes  # noqa: E402,F401
from blueprints.public import enquiry_routes  # noqa: E402,F401
from blueprints.public import search_routes   # noqa: E402,F401
from blueprints.public import quote_routes    # noqa: E402,F401
from blueprints.public import chat_routes  # noqa: E402,F401


__all__: list[str] = ["public_bp"]
