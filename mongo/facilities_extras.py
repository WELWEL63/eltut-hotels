"""
mongo/facilities_extras.py
──────────────────────────
Repository for the `hotel_dynamic_facilities` collection — free-form,
per-hotel amenity detail that does not fit the SQL hotel_facilities table.

The SQL hotel_facilities table holds STRUCTURED facilities (name + type +
quantity) that we filter and query. This collection holds the OPEN-ENDED
detail: opening hours, seasonal services, age ranges, themed nights,
anything that varies per hotel and has no fixed shape.

One document per hotel, enforced by a UNIQUE index on hotel_id (created
in mongo/client.py). Example document:

    {
        "_id": ObjectId(...),
        "hotel_id": 12,
        "extras": [
            {"name": "Rooftop Bar",    "open_hours": "18:00-02:00"},
            {"name": "Kids Water Park","suitable_age": "3-12"},
            {"name": "Sunday Brunch",  "price_usd": 25}
        ],
        "updated_at": ISODate(...)
    }

PUBLIC API
    get_extras(hotel_id)                    -> dict | None
    upsert_extras(hotel_id, extras)         -> dict
    append_extra(hotel_id, extra)           -> dict
    remove_extra(hotel_id, name)            -> dict | None
    list_hotel_ids_with_extras()            -> list[int]

DESIGN NOTES
    - Each element of `extras` must be a dict with at least a "name" key.
      Other keys are free-form. The service layer is responsible for
      shaping them; this repo validates the minimum shape.
    - `upsert_extras` REPLACES the list. `append_extra` adds to the list.
      This is the simplest mental model for an admin editing "the extras
      for hotel #12".
    - `hotel_id` is the SQL hotels.id. There is no FK — Mongo cannot
      enforce one across databases. The service layer only calls these
      functions for hotels it has already loaded from SQL.
    - `updated_at` is set on every write.
    - No Flask imports — testable in a plain Python process.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING

from mongo.client import (
    HOTEL_DYNAMIC_FACILITIES,
    hotel_dynamic_facilities_collection,
)


class FacilitiesExtrasError(Exception):
    """Base class for facilities-extras errors."""


class InvalidFacilitiesExtras(FacilitiesExtrasError):
    """Raised when arguments fail validation."""


# ─── Helpers ───────────────────────────────────────────────────────
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _clean(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    return out


def _validate_hotel_id(hotel_id: int) -> None:
    if not isinstance(hotel_id, int) or hotel_id <= 0:
        raise InvalidFacilitiesExtras("hotel_id must be a positive int")


def _validate_extra(extra: Any) -> dict[str, Any]:
    """
    Validate ONE extra entry. Returns a normalised copy.

    An extra is a dict with at least a non-empty string "name".
    """
    if not isinstance(extra, dict):
        raise InvalidFacilitiesExtras("each extra must be a dict")
    name = extra.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InvalidFacilitiesExtras(
            "each extra must have a non-empty 'name' string"
        )
    normalised = dict(extra)
    normalised["name"] = name.strip()
    return normalised


def _validate_extras(extras: Any) -> list[dict[str, Any]]:
    """Validate a whole list of extras. Returns a normalised list."""
    if not isinstance(extras, list):
        raise InvalidFacilitiesExtras("extras must be a list")
    return [_validate_extra(e) for e in extras]


# ─── Read operations ───────────────────────────────────────────────
def get_extras(hotel_id: int) -> dict[str, Any] | None:
    """Return the extras document for a hotel, or None if none exists."""
    _validate_hotel_id(hotel_id)
    doc = hotel_dynamic_facilities_collection().find_one({"hotel_id": hotel_id})
    return _clean(doc)


def list_hotel_ids_with_extras() -> list[int]:
    """
    Return the hotel_ids that have a facilities-extras document.

    Used by admin dashboards — tells us which hotels have been enriched.
    """
    cursor = hotel_dynamic_facilities_collection().find(
        {}, {"hotel_id": 1, "_id": 0}
    ).sort("hotel_id", ASCENDING)
    return [int(d["hotel_id"]) for d in cursor if "hotel_id" in d]


# ─── Write operations ──────────────────────────────────────────────
def upsert_extras(
    hotel_id: int,
    extras: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Replace the ENTIRE extras list for a hotel.

    Idempotent: calling twice with the same list leaves one document.
    Creates the document if it does not exist. Raises if `extras` is not
    a list of dicts with non-empty "name" strings.
    """
    _validate_hotel_id(hotel_id)
    normalised = _validate_extras(extras)

    now = _now_utc()
    coll = hotel_dynamic_facilities_collection()
    coll.update_one(
        {"hotel_id": hotel_id},
        {
            "$set": {
                "extras": normalised,
                "updated_at": now,
            },
            "$setOnInsert": {"hotel_id": hotel_id},
        },
        upsert=True,
    )
    doc = coll.find_one({"hotel_id": hotel_id})
    return _clean(doc)  # type: ignore[return-value]


def append_extra(
    hotel_id: int,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """
    Add one extra to the hotel's list (creating the document if needed).

    Existing extras are preserved. Duplicate names are allowed by the
    repo (the service layer decides whether that is an error).
    """
    _validate_hotel_id(hotel_id)
    normalised = _validate_extra(extra)

    now = _now_utc()
    coll = hotel_dynamic_facilities_collection()
    coll.update_one(
        {"hotel_id": hotel_id},
        {
            "$push": {"extras": normalised},
            "$set": {"updated_at": now},
            "$setOnInsert": {"hotel_id": hotel_id},
        },
        upsert=True,
    )
    doc = coll.find_one({"hotel_id": hotel_id})
    return _clean(doc)  # type: ignore[return-value]


def remove_extra(
    hotel_id: int,
    name: str,
) -> dict[str, Any] | None:
    """
    Remove the FIRST extra whose "name" matches (exact, case-sensitive).

    Returns the updated document, or None if no document exists.
    """
    _validate_hotel_id(hotel_id)
    if not isinstance(name, str) or not name.strip():
        raise InvalidFacilitiesExtras("name must be a non-empty string")

    now = _now_utc()
    coll = hotel_dynamic_facilities_collection()
    res = coll.find_one_and_update(
        {"hotel_id": hotel_id},
        {
            "$pull": {"extras": {"name": name.strip()}},
            "$set": {"updated_at": now},
        },
        return_document=True,
    )
    return _clean(res)
