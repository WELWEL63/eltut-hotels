"""blueprints/api/bookings_api.py - create + retrieve bookings (Hotels Only).

Public write surface. No auth, no CSRF. Two endpoints:

  POST /api/v1/bookings                -> create a booking
  GET  /api/v1/bookings/<reference>    -> retrieve one booking

Request body for POST:
  product_type      str    hotel
  product_id        int    room_id
  start_date        ISO date (YYYY-MM-DD) - check-in
  end_date          ISO date (YYYY-MM-DD) - check-out
  adults            int    >= 1
  children          int    >= 0, default 0
  rooms             int    >= 1, default 1
  guest_email       str    required
  guest_name        str    optional
  guest_phone       str    optional
  special_requests  str    optional
  travellers        list   optional
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

VALID_PRODUCT_TYPES = ("hotel",)


# --- Envelopes ---------------------------------------------------------------
def _ok(data: Any, status: int = 200):
    return jsonify({"data": data, "error": None}), status


def _err(code: str, message: str, status: int):
    return jsonify({"data": None, "error": {"code": code, "message": message}}), status


# --- Parsing helpers ---------------------------------------------------------
def _parse_iso_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid date: {value!r} (expected YYYY-MM-DD)") from exc


def _parse_int(value: Any, *, name: str, minimum: int = 0) -> int:
    if value is None:
        raise ValueError(f"{name} is required")
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if n < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return n


# --- Serialisers -------------------------------------------------------------
def _serialise_booking_summary(bk: Booking) -> dict[str, Any]:
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


def _serialise_booking_full(bk: Booking) -> dict[str, Any]:
    payload = _serialise_booking_summary(bk)
    payload.update({
        "user_id": bk.user_id,
        "guest_email": bk.guest_email,
        "guest_name": bk.guest_name,
        "guest_phone": bk.guest_phone,
        "check_in_date": bk.check_in_date.isoformat() if bk.check_in_date else None,
        "check_out_date": bk.check_out_date.isoformat() if bk.check_out_date else None,
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
        return _err("invalid_input", f"product_type must be 'hotel'", 400)

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
    except ValueError as exc:
        return _err("invalid_input", str(exc), 400)

    if not check_in or not check_out:
        return _err("invalid_input", "hotel bookings require start_date and end_date", 400)
    if check_out <= check_in:
        return _err("invalid_input", "end_date must be after start_date", 400)

    # --- Guest contact ---
    guest_email = (body.get("guest_email") or "").strip().lower() or None
    if not guest_email:
        return _err("invalid_input", "guest_email is required", 400)
    if "@" not in guest_email:
        return _err("invalid_input", "guest_email is not a valid email", 400)

    guest_name = (body.get("guest_name") or "").strip() or None
    guest_phone = (body.get("guest_phone") or "").strip() or None
    special_requests = (body.get("special_requests") or "").strip() or None

    # --- Availability check (Hotels Only) ---
    try:
        if not availability_service.room_is_bookable(
            room_id=product_id,
            check_in=check_in,
            check_out=check_out,
            quantity=rooms,
        ):
            return _err("not_bookable", "room is not available for those dates", 409)
    except Exception as exc:
        return _err("availability_error", str(exc), 422)

    # --- Compute total ---
    try:
        total = pricing_service.compute_booking_total(
            product_type="hotel",
            product_id=product_id,
            adults=adults,
            children=children,
            rooms=rooms,
            check_in=check_in,
            check_out=check_out,
        )
    except pricing_service.InvalidPricingInput as exc:
        return _err("pricing_error", str(exc), 422)
    except Exception as exc:
        return _err("pricing_error", f"could not price booking: {exc}", 422)

    # --- Create the booking via the service ---
    try:
        bk = booking_service.create_booking(
            product_type="hotel",
            product_id=product_id,
            travellers_adults=adults,
            travellers_children=children,
            total_amount=total,
            currency="GBP",
            guest_email=guest_email,
            guest_name=guest_name,
            guest_phone=guest_phone,
            check_in_date=check_in,
            check_out_date=check_out,
            special_requests=special_requests,
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            role="customer",
        )
    except booking_service.BookingError as exc:
        return _err("invalid_input", str(exc), 400)
    except Exception as exc:
        return _err("server_error", f"could not create booking: {exc}", 500)

    db.session.commit()

    payload = _serialise_booking_summary(bk)
    payload["payment_url"] = f"/api/v1/payments/create-order?booking_ref={bk.reference}"
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
    
    # Simple inline serialisers for the response
    payload["items"] = [
        {
            "id": i.id, "item_type": i.item_type, "product_type": i.product_type,
            "product_id": i.product_id, "product_name_snapshot": i.product_name_snapshot,
            "quantity": i.quantity, "unit_price": float(i.unit_price) if i.unit_price is not None else None,
            "line_total": float(i.line_total) if i.line_total is not None else None, "currency": i.currency,
        } for i in items
    ]
    payload["travellers"] = [
        {
            "id": t.id, "full_name": t.full_name, "date_of_birth": t.date_of_birth.isoformat() if t.date_of_birth else None,
            "age_at_booking": t.age_at_booking, "traveller_type": t.traveller_type,
            "passport_number": t.passport_number, "nationality": t.nationality, "special_needs": t.special_needs,
            "is_lead_traveller": t.is_lead_traveller, "sort_order": t.sort_order,
        } for t in travellers
    ]
    payload["status_history"] = [
        {
            "id": h.id, "from_status": h.from_status, "to_status": h.to_status,
            "changed_by_user_id": h.changed_by_user_id, "changed_by_role": h.changed_by_role,
            "reason": h.reason, "created_at": h.created_at.isoformat() if h.created_at else None,
        } for h in history
    ]

    return _ok(payload)