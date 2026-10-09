"""
mongo/__init__.py
─────────────────
MongoDB layer for eltut-tours-platform.

This package owns the five NoSQL collections defined in the architecture:

    reviews                    user-submitted product reviews
    enquiries                  quote requests / contact messages
    activity_logs              audit log of admin/system actions
    search_events              anonymous search analytics (TTL-expiring)
    hotel_dynamic_facilities   semi-structured hotel amenity extras

The database handle itself is created in extensions.init_mongo() and
retrieved here via extensions.get_mongo_db(). This package never opens a
socket by itself — it only asks for the handle the factory already set up.
"""

from __future__ import annotations

from mongo.client import (  # noqa: F401
    ACTIVITY_LOGS,
    ALL_COLLECTIONS,
    ENQUIRIES,
    HOTEL_DYNAMIC_FACILITIES,
    REVIEWS,
    SEARCH_EVENTS,
    activity_logs_collection,
    enquiries_collection,
    ensure_indexes,
    hotel_dynamic_facilities_collection,
    reviews_collection,
    search_events_collection,
)

# ─── Re-export repositories ────────────────────────────────────────
from mongo import (  # noqa: F401
    enquiries,
    facilities_extras,
    logs,
    reviews,
    search_events,
)

__all__: list[str] = [
    "REVIEWS",
    "ENQUIRIES",
    "ACTIVITY_LOGS",
    "SEARCH_EVENTS",
    "HOTEL_DYNAMIC_FACILITIES",
    "ALL_COLLECTIONS",
    "reviews_collection",
    "enquiries_collection",
    "activity_logs_collection",
    "search_events_collection",
    "hotel_dynamic_facilities_collection",
    "ensure_indexes",
    "reviews",
    "enquiries",
    "logs",
    "search_events",
    "facilities_extras",
]
