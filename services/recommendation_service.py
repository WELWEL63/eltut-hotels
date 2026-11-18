"""
services/recommendation_service.py — Hotels Only
"""

from __future__ import annotations
import logging
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import select
from extensions import db
from models import Booking, Hotel, Room
from models.booking_item import BookingItem
from models import PRODUCT_TYPE_HOTEL

log = logging.getLogger(__name__)

class RecommendationError(Exception):
    pass

class RecommendationProductNotFound(RecommendationError):
    pass

DEFAULT_LIMIT = 6
MAX_LIMIT = 20

def _clamp_limit(limit: int | None) -> int:
    if not limit:
        return DEFAULT_LIMIT
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, n))


def recommend_addons_for_hotel(
    hotel_id: int,
    *,
    check_in: Optional[date] = None,
    check_out: Optional[date] = None,
    exclude_ids: Optional[Iterable[int]] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict]:
    """Return an empty list — add-on activities no longer exist."""
    return []


def recommend_addons_for_package(*args, **kwargs) -> list[dict]:
    return []


def recommend_addons_for_booking(*args, **kwargs) -> list[dict]:
    return []


__all__ = [
    "RecommendationError",
    "RecommendationProductNotFound",
    "recommend_addons_for_hotel",
   
    "recommend_addons_for_booking",
]