"""
services/booking_service.py
───────────────────────────
Create, cancel, complete, and refund bookings — the transactional core
of the platform.

A single call to create_booking() touches five tables in one
transaction:

    bookings               parent row
    booking_items          primary + add-on activities
    booking_travellers     named travellers (optional)
    payments               initial 'created' placeholder
    booking_status_history 'created -> pending' audit row

If any step fails, the whole transaction rolls back. Callers (the public
booking blueprint, the admin panel) are expected to wrap this in their
own try/except and map BookingError subclasses to user-facing messages.

PUBLIC API
    generate_reference() -> str
    create_booking(...) -> Booking
    cancel_booking(booking, reason, by_user=None, ip=None, role=None) -> Booking
    mark_completed(booking, by_user=None, ip=None) -> Booking
    mark_refunded(booking, reason=None, by_user=None, ip=None) -> Booking
    add_status_history(booking, from_status, to_status, ...) -> BookingStatusHistory
    get_booking_by_reference(ref) -> Booking | None
    list_bookings_for_user(user) -> list[Booking]

DESIGN NOTES
    - Amounts and IDs come from the CALLER. This service never reads
      from Flask's request object — it is fully testable.
    - Availability is verified via services.availability_service (imported
      lazily to avoid a circular import at package load).
    - Totals are computed via services.pricing_service.
    - References use the pattern ELT-{year}-{5 digits}, retried on
      collision up to 10 times.
    - The initial Payment row is 'created' (not 'completed'). The PayPal
      flow will update it via payment_service.
    - Status history is written on every state change (created,
      cancelled, completed, refunded).
"""

from __future__ import annotations

import secrets
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from extensions import db
from models import (
    Booking,
    BookingItem,
    BookingStatusHistory,
    BookingTraveller,
    Payment,
    PRODUCT_TYPE_ACTIVITY,
    PRODUCT_TYPE_HOTEL,
    PRODUCT_TYPE_PACKAGE,
    VALID_PRODUCT_TYPES,
    STATUS_PENDING,
    STATUS_CONFIRMED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_REFUNDED,
    DEFAULT_BOOKING_STATUS,
    ROLE_CUSTOMER,
    ROLE_ADMIN,
)


# ─── Domain exceptions ─────────────────────────────────────────────
class BookingError(Exception):
    """Base class for booking-domain errors."""


class InvalidBookingInput(BookingError):
    """Missing or malformed arguments."""


class UnavailableProduct(BookingError):
    """The product does not exist or has no capacity for the dates."""


class BookingNotFound(BookingError):
    """Lookup by reference or id returned nothing."""


class InvalidStatusTransition(BookingError):
    """Attempt to move to a status that is not allowed from the current one."""


# ─── Constants ─────────────────────────────────────────────────────
REFERENCE_PREFIX = "ELT"
REFERENCE_RETRY_LIMIT = 10

ROLE_GUEST = "guest"
ROLE_SYSTEM = "system"


# ─── Reference generation ──────────────────────────────────────────
def generate_reference(year: int | None = None) -> str:
    """
    Return a unique booking reference of the form ELT-YYYY-NNNNN.

    Retries up to REFERENCE_RETRY_LIMIT times if a collision occurs.
    Raises BookingError if no unique value can be found (extremely
    unlikely at coursework scale).
    """
    y = year or datetime.now(timezone.utc).year
    for _ in range(REFERENCE_RETRY_LIMIT):
        n = secrets.randbelow(90000) + 10000  # 10000..99999
        ref = f"{REFERENCE_PREFIX}-{y}-{n:05d}"
        existing = db.session.scalar(
            select(Booking.id).where(Booking.reference == ref).limit(1)
        )
        if existing is None:
            return ref
    raise BookingError("could not generate a unique booking reference")


# ─── Validation helpers ────────────────────────────────────────────
def _validate_product_type(product_type: str) -> None:
    if product_type not in VALID_PRODUCT_TYPES:
        raise InvalidBookingInput(
            f"product_type must be one of {VALID_PRODUCT_TYPES}, "
            f"got {product_type!r}"
        )


def _validate_amount(value: Decimal | float | int | str | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    try:
        d = Decimal(str(value))
    except Exception as exc:  # noqa: BLE001
        raise InvalidBookingInput(f"invalid amount: {value!r}") from exc
    if d < 0:
        raise InvalidBookingInput("amount must not be negative")
    return d


def _caller_role(user, explicit_role: str | None) -> str:
    """
    Determine the role string to store in booking_status_history.

    Priority: explicit_role > user.role > 'guest'.
    """
    if explicit_role:
        return explicit_role
    if user is not None and getattr(user, "role", None):
        return user.role
    return ROLE_GUEST


# ─── Status history helper ─────────────────────────────────────────
def add_status_history(
    booking: Booking,
    *,
    from_status: str | None,
    to_status: str,
    by_user=None,
    role: str | None = None,
    reason: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> BookingStatusHistory:
    """
    Write one booking_status_history row.

    This is the ONLY place the history table should be written from.
    """
    row = BookingStatusHistory(
        booking_id=booking.id,
        from_status=from_status,
        to_status=to_status,
        changed_by_user_id=getattr(by_user, "id", None),
        changed_by_role=role or _caller_role(by_user, None),
        reason=(reason or "").strip() or None,
        ip_address=(ip or "").strip() or None,
        user_agent=(user_agent or "").strip() or None,
    )
    db.session.add(row)
    return row


# ─── Create ────────────────────────────────────────────────────────
def create_booking(
    *,
    product_type: str,
    product_id: int,
    travellers_adults: int,
    travellers_children: int,
    total_amount: Decimal | float | int | str | None,
    currency: str = "USD",
    user=None,
    guest_email: str | None = None,
    guest_name: str | None = None,
    guest_phone: str | None = None,
    check_in_date: date | None = None,
    check_out_date: date | None = None,
    activity_date: date | None = None,
    special_requests: str | None = None,
    addon_items: Optional[Iterable[dict[str, Any]]] = None,
    travellers: Optional[Iterable[dict[str, Any]]] = None,
    ip: str | None = None,
    user_agent: str | None = None,
    role: str | None = None,
) -> Booking:
    """
    Create a booking with all its dependent rows in one transaction.

    Parameters
    ----------
    product_type : "activity" | "hotel" | "package"
    product_id   : int
    travellers_adults, travellers_children : int >= 0
    total_amount : Decimal — caller is expected to have computed this via
                   pricing_service, but any non-negative value is accepted.
    user         : User | None — pass None for a guest checkout.
    addon_items  : iterable of dicts, each:
                    {product_id, quantity, unit_price, name}
    travellers   : iterable of dicts, each:
                    {full_name, date_of_birth?, age_at_booking?,
                     traveller_type?, passport_number?, nationality?,
                     special_needs?}

    Returns
    -------
    Booking — flushed and with all children attached.
    """
    _validate_product_type(product_type)
    if not isinstance(product_id, int) or product_id <= 0:
        raise InvalidBookingInput("product_id must be a positive integer")
    if travellers_adults < 0 or travellers_children < 0:
        raise InvalidBookingInput("traveller counts must not be negative")
    if travellers_adults == 0 and travellers_children == 0:
        raise InvalidBookingInput("at least one traveller is required")

    # Guest identity checks
    if user is None:
        if not guest_email or "@" not in guest_email:
            raise InvalidBookingInput(
                "guest_email is required for guest checkout"
            )
        guest_email = guest_email.strip().lower()

    amount = _validate_amount(total_amount)

    reference = generate_reference()

    booking = Booking(
        reference=reference,
        user_id=getattr(user, "id", None),
        guest_email=guest_email,
        guest_name=(guest_name or "").strip() or None,
        guest_phone=(guest_phone or "").strip() or None,
        product_type=product_type,
        product_id=product_id,
        status=DEFAULT_BOOKING_STATUS,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        activity_date=activity_date,
        travellers_adults=travellers_adults,
        travellers_children=travellers_children,
        total_amount=amount,
        currency=currency.upper(),
        special_requests=(special_requests or "").strip() or None,
    )
    db.session.add(booking)
    db.session.flush()

    # ─── Primary booking item ──────────────────────────────────────
    primary = BookingItem(
        booking_id=booking.id,
        item_type="primary",
        product_type=product_type,
        product_id=product_id,
        quantity=1,
        unit_price=amount,       # primary's line item holds the primary value
        line_total=amount,
        currency=booking.currency,
        added_during_booking=False,
    )
    db.session.add(primary)

    # ─── Add-on items (upsell) ─────────────────────────────────────
    if addon_items:
        for raw in addon_items:
            try:
                addon_product_id = int(raw["product_id"])
                qty = int(raw.get("quantity", 1))
                unit = _validate_amount(raw.get("unit_price"))
            except (KeyError, TypeError, ValueError) as exc:
                raise InvalidBookingInput(f"invalid addon item: {raw!r}") from exc

            if qty <= 0:
                raise InvalidBookingInput("addon quantity must be positive")

            item = BookingItem(
                booking_id=booking.id,
                item_type="activity_addon",
                product_type=PRODUCT_TYPE_ACTIVITY,
                product_id=addon_product_id,
                product_name_snapshot=(raw.get("name") or "").strip() or None,
                quantity=qty,
                unit_price=unit,
                line_total=(unit * Decimal(qty)),
                currency=booking.currency,
                added_during_booking=True,
                notes=(raw.get("notes") or "").strip() or None,
            )
            db.session.add(item)

    # ─── Travellers (optional) ─────────────────────────────────────
    if travellers:
        first = True
        for idx, raw in enumerate(travellers):
            try:
                full_name = (raw["full_name"] or "").strip()
            except (KeyError, TypeError) as exc:
                raise InvalidBookingInput(
                    f"traveller missing full_name: {raw!r}"
                ) from exc

            if not full_name:
                raise InvalidBookingInput("traveller full_name is required")

            traveller = BookingTraveller(
                booking_id=booking.id,
                full_name=full_name,
                date_of_birth=raw.get("date_of_birth"),
                age_at_booking=raw.get("age_at_booking"),
                traveller_type=raw.get("traveller_type") or "adult",
                passport_number=raw.get("passport_number"),
                nationality=raw.get("nationality"),
                special_needs=raw.get("special_needs"),
                is_lead_traveller=first,
                sort_order=idx,
            )
            db.session.add(traveller)
            first = False

    # ─── Initial payment placeholder ───────────────────────────────
    payment = Payment(
        booking_id=booking.id,
        provider="paypal",
        method="paypal_redirect",
        status="created",
        amount=amount,
        currency=booking.currency,
    )
    db.session.add(payment)

    # ─── Status history ────────────────────────────────────────────
    add_status_history(
        booking,
        from_status=None,
        to_status=DEFAULT_BOOKING_STATUS,
        by_user=user,
        role=role or _caller_role(user, ROLE_GUEST if user is None else None),
        reason="booking created",
        ip=ip,
        user_agent=user_agent,
    )

    db.session.flush()
    return booking


# ─── State transitions ─────────────────────────────────────────────
def cancel_booking(
    booking: Booking,
    *,
    reason: str | None = None,
    by_user=None,
    role: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Booking:
    """Cancel a pending or confirmed booking. Writes a history row."""
    if not booking.is_cancellable:
        raise InvalidStatusTransition(
            f"a booking in status {booking.status!r} cannot be cancelled"
        )

    old = booking.status
    booking.status = STATUS_CANCELLED
    booking.cancelled_at = datetime.now(timezone.utc)
    booking.cancellation_reason = (reason or "").strip() or None

    add_status_history(
        booking,
        from_status=old,
        to_status=STATUS_CANCELLED,
        by_user=by_user,
        role=role or _caller_role(by_user, None),
        reason=reason,
        ip=ip,
        user_agent=user_agent,
    )

    db.session.flush()
    return booking


def mark_confirmed(
    booking: Booking,
    *,
    by_user=None,
    role: str | None = None,
    ip: str | None = None,
) -> Booking:
    """Transition pending -> confirmed (usually called by payment flow)."""
    if booking.status != STATUS_PENDING:
        raise InvalidStatusTransition(
            f"cannot confirm a booking in status {booking.status!r}"
        )
    old = booking.status
    booking.status = STATUS_CONFIRMED
    add_status_history(
        booking,
        from_status=old,
        to_status=STATUS_CONFIRMED,
        by_user=by_user,
        role=role or _caller_role(by_user, ROLE_SYSTEM if by_user is None else None),
        reason="payment confirmed",
        ip=ip,
    )
    db.session.flush()
    return booking


def mark_completed(
    booking: Booking,
    *,
    by_user=None,
    role: str | None = None,
    ip: str | None = None,
) -> Booking:
    """Mark a booking as completed (travel has happened)."""
    if booking.status not in {STATUS_CONFIRMED, STATUS_PENDING}:
        raise InvalidStatusTransition(
            f"cannot complete a booking in status {booking.status!r}"
        )
    old = booking.status
    booking.status = STATUS_COMPLETED
    add_status_history(
        booking,
        from_status=old,
        to_status=STATUS_COMPLETED,
        by_user=by_user,
        role=role or _caller_role(by_user, ROLE_SYSTEM if by_user is None else None),
        reason="marked completed",
        ip=ip,
    )
    db.session.flush()
    return booking


def mark_refunded(
    booking: Booking,
    *,
    reason: str | None = None,
    by_user=None,
    role: str | None = None,
    ip: str | None = None,
) -> Booking:
    """Mark a booking as refunded (payment_service does the actual refund)."""
    if booking.status not in {STATUS_CANCELLED, STATUS_COMPLETED}:
        raise InvalidStatusTransition(
            f"cannot refund a booking in status {booking.status!r}"
        )
    old = booking.status
    booking.status = STATUS_REFUNDED
    add_status_history(
        booking,
        from_status=old,
        to_status=STATUS_REFUNDED,
        by_user=by_user,
        role=role or _caller_role(by_user, ROLE_ADMIN if by_user else ROLE_SYSTEM),
        reason=reason or "refunded",
        ip=ip,
    )
    db.session.flush()
    return booking


# ─── Lookups ───────────────────────────────────────────────────────
def get_booking_by_reference(reference: str) -> Optional[Booking]:
    """Return a Booking by its human-friendly reference, or None."""
    if not reference:
        return None
    return db.session.scalar(
        select(Booking).where(Booking.reference == reference.strip())
    )


def list_bookings_for_user(user) -> list[Booking]:
    """Return all bookings for a user (newest first)."""
    if user is None or getattr(user, "id", None) is None:
        return []
    return list(db.session.scalars(
        select(Booking)
        .where(Booking.user_id == user.id)
        .order_by(Booking.created_at.desc())
    ))
