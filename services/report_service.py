"""
services/report_service.py
──────────────────────────
Admin dashboard aggregates.

Everything the admin dashboard needs in one place so the blueprints stay
thin. SQL aggregates use SQLAlchemy's `func` API (no raw SQL). Mongo
aggregates are best-effort: if Mongo is unavailable we return safe empty
defaults rather than raising.

PUBLIC API
    summary() -> dict                High-level dashboard snapshot
    revenue_by_month(months=12) -> list[dict]
    revenue_by_product_type() -> dict[str, str]
    bookings_by_status() -> dict[str, int]
    top_products(limit=10) -> list[dict]
    customer_stats() -> dict
    top_rated_activities(limit=10) -> list[dict]
    search_analytics(days=30) -> dict
    enquiry_stats() -> dict

DESIGN NOTES
    - Reads only. Never writes.
    - All money amounts returned as Decimal.
    - Mongo helpers wrap their calls in try/except and return {'_error': ...}
      on failure so the dashboard still renders.
    - SQL uses func.count / func.sum / func.coalesce — no raw SQL.
    - Returns plain dicts/lists so templates don't touch ORM objects.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from extensions import db
from models import (
    Booking,
    BookingItem,
    User,
    STATUS_PENDING,
    STATUS_CONFIRMED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_REFUNDED,
    ROLE_CUSTOMER,
    PRODUCT_TYPE_ACTIVITY,
    PRODUCT_TYPE_HOTEL,
    PRODUCT_TYPE_PACKAGE,
)


log = logging.getLogger(__name__)


# ─── Constants ─────────────────────────────────────────────────────
ALL_STATUSES: tuple[str, ...] = (
    STATUS_PENDING,
    STATUS_CONFIRMED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_REFUNDED,
)
ACTIVE_STATUSES: tuple[str, ...] = (STATUS_PENDING, STATUS_CONFIRMED)
ALL_PRODUCT_TYPES: tuple[str, ...] = (
    PRODUCT_TYPE_ACTIVITY,
    PRODUCT_TYPE_HOTEL,
    PRODUCT_TYPE_PACKAGE,
)


# ─── SQL aggregates ────────────────────────────────────────────────
def revenue_by_product_type() -> dict[str, Decimal]:
    """
    Sum of total_amount grouped by product_type.

    Excludes cancelled and refunded bookings — those don't count as
    revenue.
    """
    stmt = (
        select(
            Booking.product_type,
            func.coalesce(func.sum(Booking.total_amount), 0),
        )
        .where(Booking.status.in_(ACTIVE_STATUSES + (STATUS_COMPLETED,)))
        .group_by(Booking.product_type)
    )
    out: dict[str, Decimal] = {pt: Decimal("0.00") for pt in ALL_PRODUCT_TYPES}
    for pt, total in db.session.execute(stmt):
        try:
            out[pt] = Decimal(str(total))
        except Exception:  # noqa: BLE001
            out[pt] = Decimal("0.00")
    return out


def bookings_by_status() -> dict[str, int]:
    """Count of bookings per status (all statuses, including 0)."""
    stmt = select(Booking.status, func.count(Booking.id)).group_by(Booking.status)
    out: dict[str, int] = {s: 0 for s in ALL_STATUSES}
    for status, n in db.session.execute(stmt):
        if status in out:
            out[status] = int(n)
    return out


def revenue_by_month(months: int = 12) -> list[dict[str, Any]]:
    """
    Monthly revenue for the last N months (newest last).

    Uses Postgres date_trunc for grouping. Non-Postgres backends (SQLite
    for tests) will return an empty list — that is acceptable for
    coursework.
    """
    try:
        months = max(1, min(int(months), 36))
    except (TypeError, ValueError):
        months = 12

    since = datetime.now(timezone.utc) - timedelta(days=30 * months)

    # Postgres-specific truncation
    try:
        month_col = func.date_trunc("month", Booking.created_at)
    except Exception:  # noqa: BLE001 — non-Postgres
        return []

    stmt = (
        select(
            month_col.label("month"),
            func.coalesce(func.sum(Booking.total_amount), 0).label("total"),
            func.count(Booking.id).label("count"),
        )
        .where(
            Booking.created_at >= since,
            Booking.status.in_(ACTIVE_STATUSES + (STATUS_COMPLETED,)),
        )
        .group_by(month_col)
        .order_by(month_col)
    )
    try:
        rows = db.session.execute(stmt).all()
    except Exception as exc:  # noqa: BLE001
        log.debug("revenue_by_month failed (likely non-Postgres): %s", exc)
        return []

    out: list[dict[str, Any]] = []
    for month, total, count in rows:
        try:
            out.append({
                "month": month.strftime("%Y-%m") if month else None,
                "total": Decimal(str(total)),
                "count": int(count),
            })
        except Exception:  # noqa: BLE001
            continue
    return out


def top_products(limit: int = 10) -> list[dict[str, Any]]:
    """
    Most-booked items across all product types, ranked by total booking
    quantity. Reads from booking_items.
    """
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 10

    stmt = (
        select(
            BookingItem.product_type,
            BookingItem.product_id,
            func.coalesce(func.sum(BookingItem.quantity), 0).label("qty"),
            func.coalesce(func.sum(BookingItem.line_total), 0).label("revenue"),
        )
        .join(Booking, Booking.id == BookingItem.booking_id)
        .where(
            Booking.status.in_(ACTIVE_STATUSES + (STATUS_COMPLETED,)),
            BookingItem.item_type == "primary",
        )
        .group_by(BookingItem.product_type, BookingItem.product_id)
        .order_by(func.sum(BookingItem.quantity).desc())
        .limit(limit)
    )

    out: list[dict[str, Any]] = []
    for pt, pid, qty, rev in db.session.execute(stmt):
        out.append({
            "product_type": pt,
            "product_id": pid,
            "quantity": int(qty),
            "revenue": Decimal(str(rev)),
        })
    return out


def customer_stats() -> dict[str, Any]:
    """
    Total / active / new-this-month customers (role='customer').
    """
    total = db.session.scalar(
        select(func.count(User.id)).where(User.role == ROLE_CUSTOMER)
    ) or 0
    active = db.session.scalar(
        select(func.count(User.id)).where(
            User.role == ROLE_CUSTOMER, User.is_active.is_(True)
        )
    ) or 0

    since = datetime.now(timezone.utc) - timedelta(days=30)
    new_this_month = db.session.scalar(
        select(func.count(User.id)).where(
            User.role == ROLE_CUSTOMER, User.created_at >= since
        )
    ) or 0

    return {
        "total": int(total),
        "active": int(active),
        "inactive": int(total) - int(active),
        "new_last_30_days": int(new_this_month),
    }


# ─── Mongo aggregates (best-effort) ────────────────────────────────
def top_rated_activities(limit: int = 10) -> list[dict[str, Any]]:
    """
    Top-rated activities by average Mongo review rating.

    Best-effort: returns [] if Mongo is unavailable.
    """
    try:
        from mongo.client import reviews_collection  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return [{"_error": f"mongo unavailable: {exc}"}]

    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 10

    try:
        pipeline = [
            {"$match": {"product_type": "activity"}},
            {
                "$group": {
                    "_id": "$product_id",
                    "avg": {"$avg": "$rating"},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"avg": -1, "count": -1}},
            {"$limit": limit},
        ]
        rows = list(reviews_collection().aggregate(pipeline))
        return [
            {
                "product_id": int(r["_id"]),
                "avg_rating": round(float(r.get("avg") or 0.0), 2),
                "count": int(r.get("count") or 0),
            }
            for r in rows
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("top_rated_activities failed: %s", exc)
        return [{"_error": str(exc)}]


def search_analytics(days: int = 30) -> dict[str, Any]:
    """
    Search-event analytics from Mongo: top destinations, zero-result
    searches, and daily volume. Best-effort.
    """
    try:
        from mongo.search_events import (  # noqa: PLC0415
            top_destinations, zero_result_searches, volume_by_day,
        )
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"mongo unavailable: {exc}"}

    try:
        days = max(1, min(int(days), 365))
    except (TypeError, ValueError):
        days = 30

    out: dict[str, Any] = {}
    try:
        out["top_destinations"] = top_destinations(limit=10)
    except Exception as exc:  # noqa: BLE001
        out["top_destinations"] = [{"_error": str(exc)}]

    try:
        out["zero_result_searches"] = zero_result_searches(limit=10)
    except Exception as exc:  # noqa: BLE001
        out["zero_result_searches"] = [{"_error": str(exc)}]

    try:
        out["volume_by_day"] = volume_by_day(days=days)
    except Exception as exc:  # noqa: BLE001
        out["volume_by_day"] = [{"_error": str(exc)}]

    return out


def enquiry_stats() -> dict[str, Any]:
    """Counts of enquiries by status and type from Mongo. Best-effort."""
    try:
        from mongo.enquiries import count_by_status  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return {"_error": f"mongo unavailable: {exc}"}

    try:
        return {"by_status": count_by_status()}
    except Exception as exc:  # noqa: BLE001
        return {"_error": str(exc)}


# ─── High-level summary ────────────────────────────────────────────
def summary() -> dict[str, Any]:
    """
    One-shot snapshot of every KPI the admin dashboard shows on page 1.
    """
    try:
        return {
            "revenue": {
                "by_product_type": revenue_by_product_type(),
                "by_month": revenue_by_month(months=12),
            },
            "bookings": {
                "by_status": bookings_by_status(),
                "top_products": top_products(limit=5),
            },
            "customers": customer_stats(),
            "reviews": {
                "top_activities": top_rated_activities(limit=5),
            },
            "search": search_analytics(days=30),
            "enquiries": enquiry_stats(),
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("report summary failed: %s", exc)
        return {"_error": str(exc)}
