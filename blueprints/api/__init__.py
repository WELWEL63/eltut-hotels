"""blueprints/api/__init__.py - REST API blueprint (JSON only)."""
from __future__ import annotations
from flask import Blueprint

api_bp = Blueprint("api", __name__)

def _register_route_modules() -> None:
    import logging
    log = logging.getLogger(__name__)
    modules = (
        "blueprints.api.activities_api",
        "blueprints.api.hotels_api",
        "blueprints.api.packages_api",
        "blueprints.api.bookings_api",
        "blueprints.api.payments_api",
    )
    for name in modules:
        try:
            __import__(name)
        except Exception as exc:
            log.warning("API route module %s failed to import: %s", name, exc)

_register_route_modules()

@api_bp.get("/_health")
def api_health():
    return {"data": {"status": "ok", "scope": "api/v1"}, "error": None}
