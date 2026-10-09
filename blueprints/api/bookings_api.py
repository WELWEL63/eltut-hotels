"""blueprints/api/bookings_api.py - create + retrieve bookings.

Public write surface. No auth, no CSRF. Two endpoints:

  POST /api/v1/bookings                -> create a booking
  GET  /api/v1/bookings/<reference>    -> retrieve one booking

Booking references are high-entropy (BK-XXXXXXXX), so a client that
knows a reference is treated as authorised to read that booking. This
mirrors the airline industry pattern and matches the coursework spec
(guest checkout allowed; bookings.user_id is nullable).

Request body for POST (all required unless marked optional):
  product_type      str    activity | hotel | package
  product_id        int
  start_date        ISO date (YYYY-MM-DD) - check-in for hotels,
                    unused for activities and packages
  end_date          ISO date (YYYY-MM-DD) - check-out for hotels,
                    unused for activities and packages
  activity_date     ISO date - used only for activities
  adults            int    >= 1
  children          int    >= 0, default 0
  rooms             int    >= 1, default 1 (hotel only)
  guest_email       str    required if no authenticated user
  guest_name        str    optional
  guest_phone       str    optional
  special_requests  str    optional
  travellers        list   optional [{full_name, age_at_booking,
                            traveller_type, passport_number, nationality,
                            date_of_birth, special_needs}]
  addons            list   optional [{activity_id, quantity}]

Response for POST (201):
  {"data": {"reference": "BK-A1B2C3", "status": "pending",
            "total_amount": 1234.00, "currency": "GBP",
            "payment_url": "/api/v1/payments/create-order?booking_ref=..."},
   "error": null}

Errors:
  400 invalid_input  - missing or malformed fields
  404 not_found      - product_id does not exist
  409 not_bookable   - availability check failed
  422 pricing_error  - pricing_service could not price the request

WHY call availability BEFORE create_booking: the service would
happily create a booking that overbooks the product. The API is the
boundary where the check belongs; the service assumes its caller has
already validated. This keeps the service layer reusable for admin
overrides that bypass availability.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from flask import jsonify, request
from sqlalchemy import select

from blueprints.api import api_bp
from extensions import db
from models import (
    Booking,
    BookingItem,
    BookingStatusHistory,
    BookingTraveller,
)
from services import availability_service, booking_service, pricing_service


VALID_PRODUCT_TYPES = ("activity", "hotel", "package")


# --- Envelopes ---------------------------------------------------------------
def _ok(data: Any, status: int = 200):
    return jsonify({"data": data, "error": None}), status


def _err(code: str, message: str, status: int):
    return jsonify({"data": None, "error": {"code": code, "message": message}}), status


# --- Parsing helpers ---------------------------------------------------------
def _parse_iso_date(value: Any) -> date | None:
    """Accept a YYYY-MM-DD string or None. Raise ValueError if bad."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid date: {value!r} (expected YYYY-MM-DD)") from exc


def _parse_int(value: Any, *, name: str, minimum: int = 0) -> int:
    """Parse an int from JSON. Raise ValueError with a helpful message."""
    if value is None:
        raise ValueError(f"{name} is required")
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if n < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return n


def _parse_quantity(value: Any) -> int:
    """Parse a booking-item quantity. Defaults to 1 if missing."""
    if value is None:
        return 1
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("quantity must be an integer") from exc
    if n < 1:
        raise ValueError("quantity must be >= 1")
    return n


# --- Serialisers -------------------------------------------------------------
def _serialise_booking_summary(bk: Booking) -> dict[str, Any]:
    """Compact shape used in POST responses."""
    return {
        "reference": bk.reference,
        "status": bk.status,
        "product_type": bk.product_type,
        "product_id": bk.product_id,
        "total_amount": float(bk.total_amount) if bk.total_amount is not None else None,
        "currency": bk.currency,
        "travellers_adults": bk.travellers_adults,
        "travellers_children": bk.travellers_children,
    }


def _serialise_item(item: BookingItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "item_type": item.item_type,
        "product_type": item.product_type,
        "product_id": item.product_id,
        "product_name_snapshot": item.product_name_snapshot,
        "quantity": item.quantity,
        "unit_price": float(item.unit_price) if item.unit_price is not None else None,
        "line_total": float(item.line_total) if item.line_total is not None else None,
        "currency": item.currency,
        "added_during_booking": item.added_during_booking,
        "notes": item.notes,
    }


def _serialise_traveller(t: BookingTraveller) -> dict[str, Any]:
    return {
        "id": t.id,
        "full_name": t.full_name,
        "date_of_birth": t.date_of_birth.isoformat() if t.date_of_birth else None,
        "age_at_booking": t.age_at_booking,
        "traveller_type": t.traveller_type,
        "passport_number": t.passport_number,
        "nationality": t.nationality,
        "special_needs": t.special_needs,
        "is_lead_traveller": t.is_lead_traveller,
        "sort_order": t.sort_order,
    }


def _serialise_history(h: BookingStatusHistory) -> dict[str, Any]:
    return {
        "id": h.id,
        "from_status": h.from_status,
        "to_status": h.to_status,
        "changed_by_user_id": h.changed_by_user_id,
        "changed_by_role": h.changed_by_role,
        "reason": h.reason,
        "created_at": h.created_at.isoformat() if h.created_at else None,
    }


def _serialise_booking_full(bk: Booking) -> dict[str, Any]:
    """Full shape used in GET responses. Includes related collections."""
    payload = _serialise_booking_summary(bk)
    payload.update({
        "user_id": bk.user_id,
        "guest_email": bk.guest_email,
        "guest_name": bk.guest_name,
        "guest_phone": bk.guest_phone,
        "check_in_date": bk.check_in_date.isoformat() if bk.check_in_date else None,
        "check_out_date": bk.check_out_date.isoformat() if bk.check_out_date else None,
        "activity_date": bk.activity_date.isoformat() if bk.activity_date else None,
        "special_requests": bk.special_requests,
        "cancelled_at": bk.cancelled_at.isoformat() if bk.cancelled_at else None,
        "cancellation_reason": bk.cancellation_reason,
    })
    return payload


# --- Endpoints ---------------------------------------------------------------
@api_bp.post("/bookings")
def bookings_create():
    """Create a booking from a JSON body. Guest or authenticated."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _err("invalid_input", "JSON body required", 400)

    # --- Validate product_type ---
    product_type = (body.get("product_type") or "").strip().lower()
    if product_type not in VALID_PRODUCT_TYPES:
        return _err(
            "invalid_input",
            f"product_type must be one of {VALID_PRODUCT_TYPES}",
            400,
        )

    # --- Validate integers ---
    try:
        product_id = _parse_int(body.get("product_id"), name="product_id", minimum=1)
        adults = _parse_int(body.get("adults"), name="adults", minimum=1)
        children = _parse_int(body.get("children", 0), name="children", minimum=0)
        rooms = _parse_int(body.get("rooms", 1), name="rooms", minimum=1)
    except ValueError as exc:
        return _err("invalid_input", str(exc), 400)

    # --- Validate dates ---
    try:
        check_in = _parse_iso_date(body.get("start_date"))
        check_out = _parse_iso_date(body.get("end_date"))
        activity_date = _parse_iso_date(body.get("activity_date"))
    except ValueError as exc:
        return _err("invalid_input", str(exc), 400)

    # --- Product-type-specific date rules ---
    if product_type == "hotel":
        if not check_in or not check_out:
            return _err("invalid_input", "hotel bookings require start_date and end_date", 400)
        if check_out <= check_in:
            return _err("invalid_input", "end_date must be after start_date", 400)
    elif product_type == "activity":
        if not activity_date:
            return _err("invalid_input", "activity bookings require activity_date", 400)

    # --- Guest contact ---
    # WHY no auth: guest checkout is a first-class flow. If a client
    # wants to link to a user, they can extend this endpoint later with
    # a Bearer token; the service accepts user= for exactly that case.
    guest_email = (body.get("guest_email") or "").strip().lower() or None
    if not guest_email:
        return _err("invalid_input", "guest_email is required", 400)
    if "@" not in guest_email:
        return _err("invalid_input", "guest_email is not a valid email", 400)

    guest_name = (body.get("guest_name") or "").strip() or None
    guest_phone = (body.get("guest_phone") or "").strip() or None
    special_requests = (body.get("special_requests") or "").strip() or None

    # --- Optional traveller and addon lists ---
    travellers_in = body.get("travellers") or []
    if not isinstance(travellers_in, list):
        return _err("invalid_input", "travellers must be a list", 400)

    addons_in = body.get("addons") or []
    if not isinstance(addons_in, list):
        return _err("invalid_input", "addons must be a list", 400)
    for a in addons_in:
        if not isinstance(a, dict) or "activity_id" not in a:
            return _err("invalid_input", "each addon needs activity_id", 400)

    # --- Availability check ---
    # WHY here and not in the service: the API is the boundary. Admin
    # flows legitimately need to bypass availability (e.g. manual
    # override), so the service stays policy-free.
    try:
        if product_type == "activity":
            if not availability_service.activity_is_bookable(
                activity_id=product_id,
                target_date=activity_date,
                quantity=adults + children,
            ):
                return _err("not_bookable", "activity is not available", 409)
        elif product_type == "hotel":
            # hotel lookup needs the room_id, not just the hotel id.
            # The product_id in a hotel booking refers to the ROOM.
            if not availability_service.room_is_bookable(
                room_id=product_id,
                check_in=check_in,
                check_out=check_out,
                quantity=rooms,
            ):
                return _err("not_bookable", "room is not available for those dates", 409)
        else:  # package
            if not availability_service.package_is_bookable(
                package_id=product_id,
                quantity=adults + children,
            ):
                return _err("not_bookable", "package is not available", 409)
    except Exception as exc:  # noqa: BLE001 - defensive; service raises domain errors
        return _err("availability_error", str(exc), 422)

    # --- Compute total ---
    try:
        total = pricing_service.compute_booking_total(
            product_type=product_type,
            product_id=product_id,
            adults=adults,
            children=children,
            rooms=rooms,
            check_in=check_in,
            check_out=check_out,
            addons=addons_in or None,
        )
    except pricing_service.InvalidPricingInput as exc:
        return _err("pricing_error", str(exc), 422)
    except Exception as exc:  # noqa: BLE001
        return _err("pricing_error", f"could not price booking: {exc}", 422)

    # --- Create the booking via the service ---
    try:
        bk = booking_service.create_booking(
            product_type=product_type,
            product_id=product_id,
            travellers_adults=adults,
            travellers_children=children,
            total_amount=total,
            currency="GBP",  # coursework default; extend later to read from price row
            guest_email=guest_email,
            guest_name=guest_name,
            guest_phone=guest_phone,
            check_in_date=check_in,
            check_out_date=check_out,
            activity_date=activity_date,
            special_requests=special_requests,
            addon_items=addons_in or None,
            travellers=travellers_in or None,
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            role="customer",
        )
    except booking_service.BookingError as exc:
        return _err("invalid_input", str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return _err("server_error", f"could not create booking: {exc}", 500)

    db.session.commit()

    # --- Response ---
    payload = _serialise_booking_summary(bk)
    payload["payment_url"] = (
        f"/api/v1/payments/create-order?booking_ref={bk.reference}"
    )
    return _ok(payload, 201)


@api_bp.get("/bookings/<reference>")
def bookings_detail(reference: str):
    """Return a full booking by reference. No auth; reference is secret."""
    bk = booking_service.get_booking_by_reference(reference)
    if bk is None:
        return _err("not_found", f"booking {reference!r} not found", 404)

    session = db.session
    items = session.scalars(
        select(BookingItem)
        .where(BookingItem.booking_id == bk.id)
        .order_by(BookingItem.id.asc())
    ).all()
    travellers = session.scalars(
        select(BookingTraveller)
        .where(BookingTraveller.booking_id == bk.id)
        .order_by(BookingTraveller.sort_order.asc().nullslast(), BookingTraveller.id.asc())
    ).all()
    history = session.scalars(
        select(BookingStatusHistory)
        .where(BookingStatusHistory.booking_id == bk.id)
        .order_by(BookingStatusHistory.created_at.asc())
    ).all()

    payload = _serialise_booking_full(bk)
    payload["items"] = [_serialise_item(i) for i in items]
    payload["travellers"] = [_serialise_traveller(t) for t in travellers]
    payload["status_history"] = [_serialise_history(h) for h in history]

    return _ok(payload)
