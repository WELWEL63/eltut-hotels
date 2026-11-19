"""
mongo/search_events.py
──────────────────────
Repository for the `search_events` collection — anonymous search
analytics from the public site.

Every search on the public site writes one document here. Documents are
never read by end users — they feed admin reports and are TTL-expired
after 180 days (see mongo/client.py).

WHY MONGO (not SQL)
    - high volume, write-mostly
    - semi-structured: filters / dates / ad-hoc context vary by page
    - TTL expiry is one line — no cron required
    - aggregation pipelines are the natural fit for analytics

PRIVACY
    - No user_id column. Events are tied to a session_id (Flask session),
      not an account. This keeps the dataset out of the "personal data"
      scope of GDPR as long as session_id is not correlated to a login.
    - IP is intentionally NOT stored.

PUBLIC API
    record_search(...)                  -> dict
    record_click(event_id, product_id)  -> dict | None
    top_destinations(...)               -> list[dict]
    zero_result_searches(...)           -> list[dict]
    volume_by_day(...)                  -> list[dict]

DESIGN NOTES
    - `dates` is stored as {"from": ISO8601, "to": ISO8601} or None.
      We use ISO strings, not BSON Date, because these values are read
      for display in admin reports, never for range arithmetic.
    - `filters` is a free-form dict.
    - `results_count` is set by the CALLER after running the search.
    - `clicked_product_id` is the ONLY field updated after insert, via
      record_click(). Everything else is immutable.
    - No Flask imports — testable in a plain Python process.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import DESCENDING

from mongo.client import SEARCH_EVENTS, search_events_collection


# ─── Constants ─────────────────────────────────────────────────────

PRODUCT_TYPE_HOTEL: str = "hotel"

PRODUCT_TYPE_ALL: str = "all"

VALID_PRODUCT_TYPES: tuple[str, ...] = (
   
    PRODUCT_TYPE_HOTEL,
   
    PRODUCT_TYPE_ALL,
)


class SearchEventError(Exception):
    """Base class for search-event errors."""


class InvalidSearchEvent(SearchEventError):
    """Raised when arguments fail validation."""


# ─── Helpers ───────────────────────────────────────────────────────
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_oid(event_id: str | ObjectId) -> ObjectId:
    if isinstance(event_id, ObjectId):
        return event_id
    try:
        return ObjectId(event_id)
    except (InvalidId, TypeError) as exc:
        raise InvalidSearchEvent(f"Invalid event id: {event_id!r}") from exc


def _clean(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    return out


def _validate_product_type(pt: str) -> None:
    if pt not in VALID_PRODUCT_TYPES:
        raise InvalidSearchEvent(
            f"product_type must be one of {VALID_PRODUCT_TYPES}, got {pt!r}"
        )


def _validate_counts(adults: int, children: int) -> None:
    if not isinstance(adults, int) or adults < 1:
        raise InvalidSearchEvent("adults must be an int >= 1")
    if not isinstance(children, int) or children < 0:
        raise InvalidSearchEvent("children must be an int >= 0")


# ─── Write operations ──────────────────────────────────────────────
def record_search(
    *,
    session_id: str,
    product_type: str,
    destination: str | None = None,
    dates: dict[str, str] | None = None,
    adults: int = 1,
    children: int = 0,
    filters: dict[str, Any] | None = None,
    results_count: int = 0,
) -> dict[str, Any]:
    """
    Record one anonymous search event.

    `dates` should be {"from": "2026-06-01", "to": "2026-06-08"} or None.
    `results_count` is normally passed in by the caller AFTER running the
    search, so it reflects the real number of matches.
    """
    if not session_id or not isinstance(session_id, str):
        raise InvalidSearchEvent("session_id is required")
    _validate_product_type(product_type)
    _validate_counts(adults, children)

    if results_count is None:
        results_count = 0
    if not isinstance(results_count, int) or results_count < 0:
        raise InvalidSearchEvent("results_count must be an int >= 0")

    now = _now_utc()
    doc: dict[str, Any] = {
        "session_id": session_id.strip(),
        "product_type": product_type,
        "destination": (destination or "").strip() or None,
        "dates": dict(dates) if isinstance(dates, dict) else None,
        "adults": adults,
        "children": children,
        "filters": dict(filters) if isinstance(filters, dict) else {},
        "results_count": results_count,
        "clicked_product_id": None,
        "created_at": now,
    }

    result = search_events_collection().insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


def record_click(
    event_id: str | ObjectId,
    product_id: int,
) -> dict[str, Any] | None:
    """
    Set clicked_product_id on an existing event.

    Called when the user clicks a search result. Only the FIRST click is
    stored — subsequent calls are no-ops so we capture the primary intent.
    """
    if not isinstance(product_id, int) or product_id <= 0:
        raise InvalidSearchEvent("product_id must be a positive int")

    oid = _to_oid(event_id)
    res = search_events_collection().find_one_and_update(
        {"_id": oid, "clicked_product_id": None},
        {"$set": {"clicked_product_id": product_id}},
        return_document=True,
    )
    # If None was returned, either the event doesn't exist OR it already
    # has a click — fetch it to distinguish the two for the caller.
    if res is None:
        return _clean(search_events_collection().find_one({"_id": oid}))
    return _clean(res)


# ─── Read operations ───────────────────────────────────────────────
def get_event(event_id: str | ObjectId) -> dict[str, Any] | None:
    try:
        oid = _to_oid(event_id)
    except InvalidSearchEvent:
        return None
    return _clean(search_events_collection().find_one({"_id": oid}))


def list_recent_events(
    *,
    session_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Recent events, newest first. Optional session filter."""
    query: dict[str, Any] = {}
    if session_id:
        query["session_id"] = session_id

    cursor = (
        search_events_collection()
        .find(query)
        .sort("created_at", DESCENDING)
        .limit(max(1, min(limit, 200)))
    )
    return [_clean(doc) for doc in cursor]  # type: ignore[return-value]


# ─── Aggregations (for report_service) ─────────────────────────────
def top_destinations(
    *,
    limit: int = 10,
    product_type: str | None = None,
) -> list[dict[str, Any]]:
    """
    Top searched destinations.

    Returns [{destination, count, avg_results}] sorted by count desc.
    Excludes events where destination is null or empty.
    """
    if product_type is not None:
        _validate_product_type(product_type)

    match: dict[str, Any] = {"destination": {"$nin": [None, ""]}}
    if product_type is not None:
        match["product_type"] = product_type

    pipeline = [
        {"$match": match},
        {
            "$group": {
                "_id": "$destination",
                "count": {"$sum": 1},
                "avg_results": {"$avg": "$results_count"},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": max(1, min(limit, 100))},
    ]
    rows = list(search_events_collection().aggregate(pipeline))
    return [
        {
            "destination": r["_id"],
            "count": int(r["count"]),
            "avg_results": round(float(r.get("avg_results") or 0.0), 2),
        }
        for r in rows
    ]


def zero_result_searches(*, limit: int = 20) -> list[dict[str, Any]]:
    """
    Searches that returned 0 results — tells us what inventory to add.

    Aggregated by (destination, product_type).
    """
    pipeline = [
        {"$match": {"results_count": 0, "destination": {"$nin": [None, ""]}}},
        {
            "$group": {
                "_id": {
                    "destination": "$destination",
                    "product_type": "$product_type",
                },
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"count": -1}},
        {"$limit": max(1, min(limit, 100))},
    ]
    rows = list(search_events_collection().aggregate(pipeline))
    return [
        {
            "destination": r["_id"].get("destination"),
            "product_type": r["_id"].get("product_type"),
            "count": int(r["count"]),
        }
        for r in rows
    ]


def volume_by_day(*, days: int = 30) -> list[dict[str, Any]]:
    """
    Daily search volume for the last N days.

    Returns [{date: 'YYYY-MM-DD', count: int}] sorted ascending.
    """
    days = max(1, min(days, 365))
    pipeline = [
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$created_at",
                    }
                },
                "count": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
        {"$limit": days},
    ]
    rows = list(search_events_collection().aggregate(pipeline))
    return [{"date": r["_id"], "count": int(r["count"])} for r in rows]
