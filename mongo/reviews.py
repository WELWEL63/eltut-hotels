"""
mongo/reviews.py
────────────────
Repository for the `reviews` collection.

Reviews are stored in MongoDB (not SQL) because they are semi-structured:
images, helpful counts, verified-booking flags, and free-form content that
would bloat the relational schema. The polymorphic reference
(product_type + product_id) mirrors the bookings table.

PUBLIC API
    create_review(...)              -> dict
    get_review(review_id)           -> dict | None
    list_reviews_for_product(...)   -> (list[dict], total)
    list_reviews_by_user(...)       -> (list[dict], total)
    update_review(...)              -> dict | None
    delete_review(...)              -> bool
    increment_helpful(...)          -> int   (new helpful_count)
    rating_summary(...)             -> dict  (avg, count, distribution)

DESIGN NOTES
    - All public functions return PLAIN DICTS with "_id" stringified. This
      keeps pymongo and BSON types out of templates and services.
    - `user_name` is snapshotted at write time. If a user renames later,
      historical reviews still show the original name.
    - `verified_booking` is set by the caller (service layer) after it
      checks the bookings table. We do not re-check here.
    - `helpful_count` is incremented with an atomic $inc — never a
      read-modify-write.
    - A unique index on (user_id, product_type, product_id) enforces "one
      review per user per product". We translate DuplicateKeyError into
      ReviewAlreadyExists so the caller sees a domain error, not a driver
      one.
    - Timestamps are timezone-aware UTC datetimes. pymongo serialises
      them to BSON Date, which supports sorting and TTL indexes.
    - No Flask imports, no current_app. This module is testable in a
      plain Python process.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from mongo.client import REVIEWS, reviews_collection


# ─── Types & constants ─────────────────────────────────────────────
ProductType = Literal["activity", "hotel", "package"]
VALID_PRODUCT_TYPES: tuple[str, ...] = ("activity", "hotel", "package")

MIN_RATING: int = 1
MAX_RATING: int = 5


class ReviewError(Exception):
    """Base class for review-related errors."""


class InvalidReviewInput(ReviewError):
    """Raised when arguments fail validation."""


class ReviewAlreadyExists(ReviewError):
    """Raised when a user already reviewed this product."""


# ─── Helpers ───────────────────────────────────────────────────────
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_oid(review_id: str | ObjectId) -> ObjectId:
    """Convert a string or ObjectId to ObjectId, raising InvalidReviewInput."""
    if isinstance(review_id, ObjectId):
        return review_id
    try:
        return ObjectId(review_id)
    except (InvalidId, TypeError) as exc:
        raise InvalidReviewInput(f"Invalid review id: {review_id!r}") from exc


def _clean(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Convert a Mongo document to a plain dict with _id stringified."""
    if doc is None:
        return None
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    return out


def _validate_rating(rating: int) -> None:
    if not isinstance(rating, int) or not (MIN_RATING <= rating <= MAX_RATING):
        raise InvalidReviewInput(
            f"rating must be int in [{MIN_RATING}, {MAX_RATING}], got {rating!r}"
        )


def _validate_product_type(product_type: str) -> None:
    if product_type not in VALID_PRODUCT_TYPES:
        raise InvalidReviewInput(
            f"product_type must be one of {VALID_PRODUCT_TYPES}, got {product_type!r}"
        )


# ─── Write operations ──────────────────────────────────────────────
def _validate_email(value: str | None) -> str:
    """Email is required for every review (used for dedupe + admin)."""
    if not value or not isinstance(value, str):
        raise InvalidReviewInput("email is required")
    email = value.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise InvalidReviewInput("email must be a valid address")
    return email


def create_review(
    *,
    product_type: ProductType,
    product_id: int,
    user_id: int | None,
    user_name: str,
    user_email: str,
    rating: int,
    title: str | None = None,
    body: str | None = None,
    images: list[str] | None = None,
    verified_booking: bool = False,
) -> dict[str, Any]:
    """
    Insert a new review.

    Uniqueness is enforced on (product_type, product_id, user_email)
    via a unique index — this works for both logged-in users and
    guests, unlike a user_id-based index (which is sparse because
    guests have user_id=None).

    Raises ReviewAlreadyExists on duplicate.
    """
    _validate_product_type(product_type)
    _validate_rating(rating)
    if not isinstance(product_id, int) or product_id <= 0:
        raise InvalidReviewInput("product_id must be a positive int")

    clean_email = _validate_email(user_email)
    clean_name = (user_name or "").strip()
    if not clean_name:
        raise InvalidReviewInput("name is required")

    now = _now_utc()
    doc: dict[str, Any] = {
        "product_type": product_type,
        "product_id": product_id,
        "user_id": user_id,
        "user_name": clean_name,
        "user_email": clean_email,
        "rating": rating,
        "title": (title or "").strip() or None,
        "body": (body or "").strip() or None,
        "images": list(images or []),
        "helpful_count": 0,
        "verified_booking": bool(verified_booking),
        "created_at": now,
        "updated_at": now,
    }

    try:
        result = reviews_collection().insert_one(doc)
    except DuplicateKeyError as exc:
        raise ReviewAlreadyExists(
            "This user has already reviewed this product."
        ) from exc

    doc["_id"] = str(result.inserted_id)
    return doc


def update_review(
    review_id: str | ObjectId,
    *,
    rating: int | None = None,
    title: str | None = None,
    body: str | None = None,
    images: list[str] | None = None,
) -> dict[str, Any] | None:
    """Update editable fields of a review. Returns the updated doc or None."""
    oid = _to_oid(review_id)
    updates: dict[str, Any] = {"updated_at": _now_utc()}

    if rating is not None:
        _validate_rating(rating)
        updates["rating"] = rating
    if title is not None:
        updates["title"] = title.strip() or None
    if body is not None:
        updates["body"] = body.strip() or None
    if images is not None:
        updates["images"] = list(images)

    res = reviews_collection().find_one_and_update(
        {"_id": oid},
        {"$set": updates},
        return_document=True,
    )
    return _clean(res)


def delete_review(review_id: str | ObjectId) -> bool:
    """Delete a review. Returns True if a document was removed."""
    oid = _to_oid(review_id)
    res = reviews_collection().delete_one({"_id": oid})
    return res.deleted_count == 1


def increment_helpful(review_id: str | ObjectId) -> int:
    """
    Atomically increment helpful_count. Returns the NEW value.

    Raises InvalidReviewInput if the id is malformed.
    """
    oid = _to_oid(review_id)
    res = reviews_collection().find_one_and_update(
        {"_id": oid},
        {"$inc": {"helpful_count": 1}, "$set": {"updated_at": _now_utc()}},
        return_document=True,
        projection={"helpful_count": 1},
    )
    if res is None:
        raise InvalidReviewInput(f"Review not found: {review_id!r}")
    return int(res.get("helpful_count", 0))


# ─── Read operations ───────────────────────────────────────────────
def get_review(review_id: str | ObjectId) -> dict[str, Any] | None:
    """Fetch a single review by id."""
    try:
        oid = _to_oid(review_id)
    except InvalidReviewInput:
        return None
    return _clean(reviews_collection().find_one({"_id": oid}))


def list_reviews_for_product(
    product_type: ProductType,
    product_id: int,
    *,
    limit: int = 20,
    skip: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """
    List reviews for a product, newest first.

    Returns (items, total) so callers can render pagination.
    """
    _validate_product_type(product_type)
    query = {"product_type": product_type, "product_id": product_id}
    coll = reviews_collection()

    total = coll.count_documents(query)
    cursor = (
        coll.find(query)
        .sort("created_at", DESCENDING)
        .skip(max(0, skip))
        .limit(max(1, min(limit, 100)))
    )
    items = [_clean(doc) for doc in cursor]
    return items, total  # type: ignore[return-value]


def list_reviews_by_user(
    user_id: int,
    *,
    limit: int = 50,
    skip: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """List reviews written by a user, newest first."""
    query = {"user_id": user_id}
    coll = reviews_collection()

    total = coll.count_documents(query)
    cursor = (
        coll.find(query)
        .sort("created_at", DESCENDING)
        .skip(max(0, skip))
        .limit(max(1, min(limit, 100)))
    )
    items = [_clean(doc) for doc in cursor]
    return items, total  # type: ignore[return-value]


# ─── Aggregation ───────────────────────────────────────────────────
def rating_summary(product_type: ProductType, product_id: int) -> dict[str, Any]:
    """
    Compute aggregate stats for a product's reviews.

    Returns a dict with:
        average   : float | None  (None if no reviews)
        count     : int
        distribution : {1: n1, 2: n2, 3: n3, 4: n4, 5: n5}
    """
    _validate_product_type(product_type)

    pipeline = [
        {"$match": {"product_type": product_type, "product_id": product_id}},
        {
            "$group": {
                "_id": None,
                "average": {"$avg": "$rating"},
                "count": {"$sum": 1},
                "ratings": {"$push": "$rating"},
            }
        },
    ]
    result = list(reviews_collection().aggregate(pipeline))

    distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    if not result:
        return {"average": None, "count": 0, "distribution": distribution}

    row = result[0]
    for r in row.get("ratings", []):
        if isinstance(r, int) and r in distribution:
            distribution[r] += 1

    return {
        "average": round(float(row["average"]), 2) if row.get("average") is not None else None,
        "count": int(row.get("count", 0)),
        "distribution": distribution,
    }


# ─── Convenience ───────────────────────────────────────────────────
def has_reviewed(user_id: int, product_type: ProductType, product_id: int) -> bool:
    """True if this user already reviewed this product."""
    _validate_product_type(product_type)
    res = reviews_collection().find_one(
        {"user_id": user_id, "product_type": product_type, "product_id": product_id},
        projection={"_id": 1},
    )
    return res is not None
