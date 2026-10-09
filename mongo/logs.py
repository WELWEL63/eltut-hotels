"""
mongo/logs.py
─────────────
Repository for the `activity_logs` collection — the admin/system audit
trail.

Every meaningful action an admin (or a scheduled system job) performs on
SQL entities is recorded here. Logs are semi-structured (old_value /
new_value can be any shape), high volume, and short-lived.

WHY MONGO (not SQL)
    - high volume, write-mostly workload
    - semi-structured payloads (old_value / new_value vary by action)
    - TTL expiry (90 days) is a one-line index config — no cron needed
    - free-form `context` dict for extra fields (path, form, stack)

PUBLIC API
    log_action(...)                     -> dict
    log_change(...)                     -> dict (convenience wrapper)
    get_log(id)                         -> dict | None
    list_logs(user_id=..., ...)         -> (list[dict], total)
    list_recent_actions(user_id, limit) -> list[dict]
    list_for_entity(entity_type, id)    -> (list[dict], total)

DESIGN NOTES
    - `user_id` may be None (system-triggered actions).
    - `user_role` snapshots the role AT THE TIME of the action. If the
      user is later promoted, historical logs still show the old role.
    - `action` is a plain string. We export a set of KNOWN_ACTIONS for
      callers to import, but we do not CHECK-constrain it — new actions
      appear during development and we do not want every new one to
      require a schema change.
    - `old_value` / `new_value` are Any. Use log_change() to set both in
      one call; use log_action() for actions that are not value changes.
    - `context` is a free-form dict for extras. It is stored as-is.
    - Logs are NEVER edited or deleted by the app. The TTL index (90 days)
      configured in mongo/client.py is the only deletion mechanism.
    - No Flask imports — testable in a plain Python process.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import DESCENDING

from mongo.client import ACTIVITY_LOGS, activity_logs_collection


# ─── Common actions (documented conventions, not enforced) ─────────
ACTION_CREATE: str = "create"
ACTION_UPDATE: str = "update"
ACTION_DELETE: str = "delete"
ACTION_TOGGLE_ACTIVE: str = "toggle_active"
ACTION_STATUS_CHANGE: str = "status_change"
ACTION_LOGIN: str = "login"
ACTION_LOGOUT: str = "logout"

# A registry of common actions so callers can import strings instead of
# typing them freehand. NOT enforced at the DB level.
KNOWN_ACTIONS: tuple[str, ...] = (
    ACTION_CREATE,
    ACTION_UPDATE,
    ACTION_DELETE,
    ACTION_TOGGLE_ACTIVE,
    ACTION_STATUS_CHANGE,
    ACTION_LOGIN,
    ACTION_LOGOUT,
)

# Entity types this project logs against. Same convention — not enforced.
ENTITY_USER: str = "user"
ENTITY_DESTINATION: str = "destination"
ENTITY_GUIDE: str = "guide"
ENTITY_SUPPLIER: str = "supplier"
ENTITY_ACTIVITY: str = "activity"
ENTITY_HOTEL: str = "hotel"
ENTITY_ROOM: str = "room"
ENTITY_PACKAGE: str = "package"
ENTITY_BOOKING: str = "booking"
ENTITY_PAYMENT: str = "payment"
ENTITY_NEWSLETTER: str = "newsletter"

KNOWN_ENTITY_TYPES: tuple[str, ...] = (
    ENTITY_USER, ENTITY_DESTINATION, ENTITY_GUIDE, ENTITY_SUPPLIER,
    ENTITY_ACTIVITY, ENTITY_HOTEL, ENTITY_ROOM, ENTITY_PACKAGE,
    ENTITY_BOOKING, ENTITY_PAYMENT, ENTITY_NEWSLETTER,
)


class LogError(Exception):
    """Base class for log-related errors."""


class InvalidLogInput(LogError):
    """Raised when arguments fail validation."""


# ─── Helpers ───────────────────────────────────────────────────────
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_oid(log_id: str | ObjectId) -> ObjectId:
    if isinstance(log_id, ObjectId):
        return log_id
    try:
        return ObjectId(log_id)
    except (InvalidId, TypeError) as exc:
        raise InvalidLogInput(f"Invalid log id: {log_id!r}") from exc


def _clean(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    return out


def _validate_action(action: str) -> None:
    if not isinstance(action, str) or not action.strip():
        raise InvalidLogInput("action must be a non-empty string")


def _validate_entity_type(entity_type: str) -> None:
    if not isinstance(entity_type, str) or not entity_type.strip():
        raise InvalidLogInput("entity_type must be a non-empty string")


# ─── Write operations ──────────────────────────────────────────────
def log_action(
    *,
    action: str,
    entity_type: str,
    entity_id: int | str | None = None,
    user_id: int | None = None,
    user_role: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
    ip: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Write one audit log entry. Returns the inserted document.

    Use this for actions that are not simple value changes (login, logout,
    status_change with a reason). Use log_change() for value diffs.
    """
    _validate_action(action)
    _validate_entity_type(entity_type)

    now = _now_utc()
    doc: dict[str, Any] = {
        "action": action.strip(),
        "entity_type": entity_type.strip(),
        "entity_id": entity_id,
        "user_id": user_id,
        "user_role": user_role,
        "old_value": old_value,
        "new_value": new_value,
        "ip": (ip or "").strip() or None,
        "context": dict(context) if isinstance(context, dict) else {},
        "created_at": now,
    }

    result = activity_logs_collection().insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


def log_change(
    *,
    entity_type: str,
    entity_id: int | str,
    old_value: Any,
    new_value: Any,
    user_id: int | None = None,
    user_role: str | None = None,
    action: str = ACTION_UPDATE,
    ip: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Convenience wrapper for a value change.

    Sets action to 'update' by default. Use log_action() if you need a
    different action label (create, delete, toggle_active, ...).
    """
    return log_action(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        user_role=user_role,
        old_value=old_value,
        new_value=new_value,
        ip=ip,
        context=context,
    )


# ─── Read operations ───────────────────────────────────────────────
def get_log(log_id: str | ObjectId) -> dict[str, Any] | None:
    try:
        oid = _to_oid(log_id)
    except InvalidLogInput:
        return None
    return _clean(activity_logs_collection().find_one({"_id": oid}))


def list_logs(
    *,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    action: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    skip: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """
    List audit log entries, newest first, with optional filters.

    Filters are AND-ed. Returns (items, total).
    """
    query: dict[str, Any] = {}
    if user_id is not None:
        query["user_id"] = user_id
    if entity_type is not None:
        query["entity_type"] = entity_type
    if entity_id is not None:
        query["entity_id"] = entity_id
    if action is not None:
        query["action"] = action

    if since is not None or until is not None:
        rng: dict[str, Any] = {}
        if since is not None:
            rng["$gte"] = since
        if until is not None:
            rng["$lte"] = until
        query["created_at"] = rng

    coll = activity_logs_collection()
    total = coll.count_documents(query)
    cursor = (
        coll.find(query)
        .sort("created_at", DESCENDING)
        .skip(max(0, skip))
        .limit(max(1, min(limit, 500)))
    )
    items = [_clean(doc) for doc in cursor]
    return items, total  # type: ignore[return-value]


def list_recent_actions(
    user_id: int,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Recent actions by a given user — for an admin 'recent activity' widget."""
    items, _ = list_logs(user_id=user_id, limit=limit)
    return items


def list_for_entity(
    entity_type: str,
    entity_id: int | str,
    *,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """Full audit trail for one entity — 'who touched package #7?'."""
    return list_logs(entity_type=entity_type, entity_id=entity_id, limit=limit)
