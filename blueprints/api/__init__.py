"""blueprints/api/__init__.py - REST API blueprint (JSON only)."""
from __future__ import annotations
from flask import Blueprint

api_bp = Blueprint("api", __name__)

def _register_route_modules() -> None:
    modules = (
        "blueprints.api.hotels_api",
        "blueprints.api.bookings_api",
        "blueprints.api.payments_api",
    )
    for name in modules:
        __import__(name) # Force crash if it fails

_register_route_modules()

@api_bp.get("/_health")
def api_health():
    return {"data": {"status": "ok", "scope": "api/v1"}, "error": None}