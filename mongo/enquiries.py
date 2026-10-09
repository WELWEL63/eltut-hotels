"""
mongo/enquiries.py
──────────────────
Repository for the `enquiries` collection.

Two kinds of public messages are stored here:

    type = 'quote_request'   "price me 2 adults + 1 child on X package"
    type = 'contact'         "do you offer airport transfers?"

Why MongoDB (not SQL):
    - semi-structured: metadata payload varies by type
    - low-volume: written rarely, read by admin
    - text-searchable: Mongo's TEXT index on message is a single line
    - write-once / read-occasionally: no transactional pressure

PUBLIC API
    create_enquiry(...)         -> dict
    get_enquiry(id)             -> dict | None
    list_enquiries(...)         -> (list[dict], total)
    list_enquiries_by_status()  -> (list[dict], total)
    mark_handled(id, note=None) -> dict | None
    mark_spam(id)               -> dict | None
    count_by_status()           -> dict[str, int]

DESIGN NOTES
    - All public functions return PLAIN DICTS with "_id" stringified.
      Same convention as mongo/reviews.py — no BSON leaks to templates.
    - `email` is lowercased on write (matches User.email and
      Booking.guest_email casing).
    - No unique index — a user may send multiple enquiries.
    - `metadata` is a free-form dict, stored as-is. The service layer
      is responsible for shaping it (e.g. {adults, children, dates}).
    - `status` is a small closed set: new | handled | spam.
    - Timestamps are UTC datetimes (BSON Date).
    - No Flask imports — testable in a plain Python process.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import DESCENDING

from mongo.client import ENQUIRIES, enquiries_collection


# ─── Types & constants ─────────────────────────────────────────────
EnquiryType = Literal["quote_request", "contact"]
EnquiryStatus = Literal["new", "handled", "spam"]
ProductType = Literal["activity", "hotel", "package"]

TYPE_QUOTE_REQUEST: str = "quote_request"
TYPE_CONTACT: str = "contact"
VALID_ENQUIRY_TYPES: tuple[str, ...] = (TYPE_QUOTE_REQUEST, TYPE_CONTACT)

STATUS_NEW: str = "new"
STATUS_HANDLED: str = "handled"
STATUS_SPAM: str = "spam"
VALID_ENQUIRY_STATUSES: tuple[str, ...] = (STATUS_NEW, STATUS_HANDLED, STATUS_SPAM)

VALID_PRODUCT_TYPES: tuple[str, ...] = ("activity", "hotel", "package")


class EnquiryError(Exception):
    """Base class for enquiry-related errors."""


class InvalidEnquiryInput(EnquiryError):
    """Raised when arguments fail validation."""


# ─── Helpers ───────────────────────────────────────────────────────
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_oid(enquiry_id: str | ObjectId) -> ObjectId:
    if isinstance(enquiry_id, ObjectId):
        return enquiry_id
    try:
        return ObjectId(enquiry_id)
    except (InvalidId, TypeError) as exc:
        raise InvalidEnquiryInput(
            f"Invalid enquiry id: {enquiry_id!r}"
        ) from exc


def _clean(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    return out


def _validate_type(t: str) -> None:
    if t not in VALID_ENQUIRY_TYPES:
        raise InvalidEnquiryInput(
            f"type must be one of {VALID_ENQUIRY_TYPES}, got {t!r}"
        )


def _validate_status(s: str) -> None:
    if s not in VALID_ENQUIRY_STATUSES:
        raise InvalidEnquiryInput(
            f"status must be one of {VALID_ENQUIRY_STATUSES}, got {s!r}"
        )


def _validate_product_type(pt: str | None) -> None:
    if pt is None:
        return
    if pt not in VALID_PRODUCT_TYPES:
        raise InvalidEnquiryInput(
            f"product_type must be None or one of {VALID_PRODUCT_TYPES}, "
            f"got {pt!r}"
        )


# ─── Write operations ──────────────────────────────────────────────
def create_enquiry(
    *,
    type: EnquiryType,
    name: str,
    email: str,
    phone: str | None = None,
    product_type: ProductType | None = None,
    product_id: int | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Insert a new enquiry in 'new' status.

    Raises InvalidEnquiryInput if type/status/product_type are invalid or
    if required fields are missing.
    """
    _validate_type(type)
    _validate_product_type(product_type)

    if not name or not isinstance(name, str) or not name.strip():
        raise InvalidEnquiryInput("name is required")
    if not email or not isinstance(email, str) or "@" not in email:
        raise InvalidEnquiryInput("a valid email is required")

    now = _now_utc()
    doc: dict[str, Any] = {
        "type": type,
        "name": name.strip(),
        "email": email.strip().lower(),
        "phone": (phone or "").strip() or None,
        "product_type": product_type,
        "product_id": int(product_id) if product_id is not None else None,
        "message": (message or "").strip() or None,
        "metadata": dict(metadata) if isinstance(metadata, dict) else {},
        "status": STATUS_NEW,
        "admin_note": None,
        "handled_at": None,
        "created_at": now,
        "updated_at": now,
    }

    result = enquiries_collection().insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


def mark_handled(
    enquiry_id: str | ObjectId,
    admin_note: str | None = None,
) -> dict[str, Any] | None:
    """Set status to handled, record when and (optionally) why."""
    oid = _to_oid(enquiry_id)
    now = _now_utc()
    updates: dict[str, Any] = {
        "status": STATUS_HANDLED,
        "handled_at": now,
        "updated_at": now,
    }
    if admin_note is not None:
        updates["admin_note"] = admin_note.strip() or None

    res = enquiries_collection().find_one_and_update(
        {"_id": oid}, {"$set": updates}, return_document=True
    )
    return _clean(res)


def mark_spam(enquiry_id: str | ObjectId) -> dict[str, Any] | None:
    """Set status to spam."""
    oid = _to_oid(enquiry_id)
    now = _now_utc()
    res = enquiries_collection().find_one_and_update(
        {"_id": oid},
        {"$set": {"status": STATUS_SPAM, "updated_at": now}},
        return_document=True,
    )
    return _clean(res)


# ─── Read operations ───────────────────────────────────────────────
def get_enquiry(enquiry_id: str | ObjectId) -> dict[str, Any] | None:
    try:
        oid = _to_oid(enquiry_id)
    except InvalidEnquiryInput:
        return None
    return _clean(enquiries_collection().find_one({"_id": oid}))


def list_enquiries(
    *,
    type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    skip: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """
    List enquiries, newest first, optionally filtered by type and status.

    Returns (items, total).
    """
    if type is not None:
        _validate_type(type)
    if status is not None:
        _validate_status(status)

    query: dict[str, Any] = {}
    if type is not None:
        query["type"] = type
    if status is not None:
        query["status"] = status

    coll = enquiries_collection()
    total = coll.count_documents(query)
    cursor = (
        coll.find(query)
        .sort("created_at", DESCENDING)
        .skip(max(0, skip))
        .limit(max(1, min(limit, 200)))
    )
    items = [_clean(doc) for doc in cursor]
    return items, total  # type: ignore[return-value]


def list_enquiries_by_status(
    status: str,
    *,
    limit: int = 50,
    skip: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Convenience wrapper — list enquiries with a given status."""
    return list_enquiries(status=status, limit=limit, skip=skip)


# ─── Aggregation ───────────────────────────────────────────────────
def count_by_status() -> dict[str, int]:
    """
    Return a dict of {status: count} for every known status.

    Includes zeros for statuses with no documents, so callers can render
    a fixed dashboard without special-casing.
    """
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    result = list(enquiries_collection().aggregate(pipeline))

    out: dict[str, int] = {s: 0 for s in VALID_ENQUIRY_STATUSES}
    for row in result:
        key = row.get("_id")
        if isinstance(key, str) and key in out:
            out[key] = int(row.get("count", 0))
    return out
