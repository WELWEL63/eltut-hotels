"""
mongo/client.py
───────────────
Single point of contact between the app and MongoDB Atlas.

Every other module in the mongo/ package asks THIS file for a collection.
The database handle is created by extensions.init_mongo() at app startup;
this module only retrieves it. Importing this file never opens a socket.

Collection names are declared as module constants so nothing else in the
codebase hardcodes strings.
"""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING, TEXT, IndexModel
from pymongo.collection import Collection

from extensions import get_mongo_db


# ─── Collection names ──────────────────────────────────────────────
REVIEWS: str = "reviews"
ENQUIRIES: str = "enquiries"
ACTIVITY_LOGS: str = "activity_logs"
SEARCH_EVENTS: str = "search_events"
HOTEL_DYNAMIC_FACILITIES: str = "hotel_dynamic_facilities"

ALL_COLLECTIONS: tuple[str, ...] = (
    REVIEWS,
    ENQUIRIES,
    ACTIVITY_LOGS,
    SEARCH_EVENTS,
    HOTEL_DYNAMIC_FACILITIES,
)


# ─── Collection accessors ──────────────────────────────────────────
def _col(name: str) -> Collection[dict[str, Any]]:
    """
    Return a typed collection handle.

    Raises RuntimeError (via extensions.get_mongo_db) if the app factory
    has not initialised Mongo yet — this is intentional. Silent fallbacks
    lead to NoneType errors deep inside repository code.
    """
    return get_mongo_db()[name]


def reviews_collection() -> Collection[dict[str, Any]]:
    """User-submitted product reviews."""
    return _col(REVIEWS)


def enquiries_collection() -> Collection[dict[str, Any]]:
    """Quote requests and contact messages."""
    return _col(ENQUIRIES)


def activity_logs_collection() -> Collection[dict[str, Any]]:
    """Admin/system action audit log (TTL-expiring)."""
    return _col(ACTIVITY_LOGS)


def search_events_collection() -> Collection[dict[str, Any]]:
    """Anonymous search analytics (TTL-expiring)."""
    return _col(SEARCH_EVENTS)


def hotel_dynamic_facilities_collection() -> Collection[dict[str, Any]]:
    """Semi-structured hotel amenity extras."""
    return _col(HOTEL_DYNAMIC_FACILITIES)


# ─── Index management ──────────────────────────────────────────────
def ensure_indexes(app: Any = None) -> bool:
    """
    Create every index the app relies on.

    Idempotent: Mongo no-ops existing indexes. Called once by the app
    factory at startup.

    Returns
    -------
    bool
        True  — indexes ensured
        False — Mongo not initialised (URI still placeholder); skipped
                with a warning rather than raising, so the app can boot
                before Atlas is configured.
    """
    try:
        db = get_mongo_db()
    except RuntimeError as exc:
        _log(app, f"Mongo not initialised — skipping index creation ({exc})")
        return False

    _create_review_indexes(db)
    _create_enquiry_indexes(db)
    _create_activity_log_indexes(db)
    _create_search_event_indexes(db)
    _create_hotel_facility_indexes(db)

    _log(app, "Mongo indexes ensured for 5 collections")
    return True


def _create_review_indexes(db: Any) -> None:
    """
    Indexes for the reviews collection.

    WHY the email-based unique index: reviews can be left by guests
    (user_id=NULL). A non-sparse unique index on user_id only allows
    ONE null value, so a second guest review of the same product would
    fail. We enforce uniqueness on (product_type, product_id, user_email)
    instead, which works for both logged-in users and guests.

    The user_id-based index is kept (sparse) so a user's own review
    list can be fetched fast without a scan.
    """
    db[REVIEWS].create_indexes(
        [
            # For listing reviews of a product, newest first.
            IndexModel(
                [("product_type", ASCENDING), ("product_id", ASCENDING),
                 ("created_at", DESCENDING)],
                name="ix_reviews_product_recent",
            ),
            # For the "my reviews" list per user (sparse: guests skipped).
            IndexModel(
                [("user_id", ASCENDING)],
                name="ix_reviews_user",
                sparse=True,
            ),
            # Prevent the same email reviewing the same product twice.
            IndexModel(
                [("product_type", ASCENDING), ("product_id", ASCENDING),
                 ("user_email", ASCENDING)],
                name="ux_reviews_product_email",
                unique=True,
                sparse=True,       # sparse tolerates legacy docs without email
            ),
        ]
    )


def _create_enquiry_indexes(db: Any) -> None:
    db[ENQUIRIES].create_indexes(
        [
            IndexModel(
                [("status", ASCENDING), ("created_at", DESCENDING)],
                name="ix_enquiries_status_recent",
            ),
            IndexModel([("email", ASCENDING)], name="ix_enquiries_email"),
        ]
    )


def _create_activity_log_indexes(db: Any) -> None:
    db[ACTIVITY_LOGS].create_indexes(
        [
            IndexModel(
                [("user_id", ASCENDING), ("created_at", DESCENDING)],
                name="ix_activity_logs_user_recent",
            ),
            IndexModel(
                [("created_at", ASCENDING)],
                name="ttl_activity_logs_created_at",
                expireAfterSeconds=90 * 24 * 60 * 60,
            ),
        ]
    )


def _create_search_event_indexes(db: Any) -> None:
    db[SEARCH_EVENTS].create_indexes(
        [
            IndexModel(
                [("created_at", DESCENDING)], name="ix_search_events_recent"
            ),
            IndexModel(
                [("destination", TEXT)], name="tx_search_events_destination"
            ),
            IndexModel(
                [("created_at", ASCENDING)],
                name="ttl_search_events_created_at",
                expireAfterSeconds=180 * 24 * 60 * 60,
            ),
        ]
    )


def _create_hotel_facility_indexes(db: Any) -> None:
    db[HOTEL_DYNAMIC_FACILITIES].create_indexes(
        [
            IndexModel(
                [("hotel_id", ASCENDING)],
                name="ux_hotel_dynamic_facilities_hotel_id",
                unique=True,
            ),
        ]
    )


def _log(app: Any, message: str) -> None:
    """Log via Flask's logger if an app is provided, else print."""
    if app is not None and hasattr(app, "logger"):
        app.logger.info(message)
    else:
        print(f"[mongo.client] {message}")
