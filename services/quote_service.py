"""
services/quote_service.py
──────────────────────────
Admin-issued price quotes in response to customer quote requests.

WORKFLOW (mirrors the Quote model docstring)
    1. Customer submits "request a quote" via public form.
       → create_quote_request() writes a Mongo enquiry with
         type='quote_request'. No SQL row yet — the admin hasn't
         priced it.

    2. Admin opens the request in /admin/quotes, clicks "Create quote".
       → create_draft() writes a Quote with status='draft'.
       → update_draft() calculates from room rates, or
         update_manual_draft() stores admin-entered nightly rates.

    3. Admin clicks "Send to customer".
       → send_quote() sends the email and only leaves the quote in
         sent status when the mail service confirms delivery.

    4. Customer opens the link, clicks Accept or Decline.
       → accept_quote() transitions sent → accepted, sets accepted_at,
         AND creates a pending Booking. Returns (quote, booking).
       → decline_quote() transitions sent → declined, sets
         declined_at. Optional reason goes into internal_notes.

    5. expire_all_overdue() is called by the cloud worker on every
       poll: any 'sent' quote whose valid_until is in the past gets
       status='expired', expired_at set.

PUBLIC API
    Reference
        generate_reference(year=None) -> str

    Public form
        create_quote_request(...) -> dict        # Mongo enquiry

    Admin side
        create_draft(...) -> Quote
        update_draft(quote, ...) -> Quote
        update_manual_draft(quote, ...) -> Quote
        send_quote(quote, user=None) -> Quote
        cancel_quote(quote, user=None, reason=None) -> Quote

    Customer side
        accept_quote(quote, customer_user=None, ...) -> (Quote, Booking)
        decline_quote(quote, reason=None) -> Quote

    Bulk + queries
        expire_all_overdue() -> int
        get_quote_by_reference(reference) -> Quote | None
        list_open_quote_requests(limit=50, skip=0) -> (list[dict], int)
        list_quotes(status=None, product_type=None, limit=50, skip=0) -> (list[Quote], int)

DESIGN NOTES
    - No Flask request imports. Reads/writes go through SQLAlchemy
      and Mongo repos only.
    - Domain-specific exceptions for every failure mode.
    - Amounts are always Decimal, never float.
    - Emails are best-effort: a send failure does not roll back the
      status transition (the admin can re-send manually).
    - Accept transitions to Booking creation using
      booking_service.create_booking with the customer as guest, so
      the pipeline reuses all existing validation.
"""

from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select

from extensions import db
from models import (
    Booking,
    Quote,
    STATUS_DRAFT,
    STATUS_SENT,
    STATUS_ACCEPTED,
    STATUS_DECLINED,
    STATUS_EXPIRED,
    STATUS_CANCELLED as STATUS_QUOTE_CANCELLED,
    VALID_QUOTE_PRODUCT_TYPES,
)
from services import booking_service, email_service


log = logging.getLogger(__name__)


# ─── Constants ────────────────────────────────────────────────────────────
QUOTE_REFERENCE_PREFIX = "Q"
REFERENCE_RETRY_LIMIT = 10
MANUAL_QUOTE_CURRENCIES = ("GBP", "EUR", "USD", "EGP")


# ─── Exceptions ───────────────────────────────────────────────────────────
class QuoteError(Exception):
    """Base class for all quote-service failures."""


class InvalidQuoteInput(QuoteError):
    """Caller provided malformed or missing arguments."""


class QuoteNotFound(QuoteError):
    """The requested quote does not exist."""


class InvalidQuoteState(QuoteError):
    """The quote is not in a state that permits the requested action."""


# ─── Reference generation ─────────────────────────────────────────────────
def generate_reference(year: int | None = None) -> str:
    """Return a unique quote reference of the form Q-YYYY-NNNNN.

    Mirrors booking_service.generate_reference but with prefix "Q".
    Retries up to REFERENCE_RETRY_LIMIT times if a collision occurs.
    """
    y = year or datetime.now(timezone.utc).year
    for _ in range(REFERENCE_RETRY_LIMIT):
        n = secrets.randbelow(90000) + 10000  # 10000..99999
        ref = f"{QUOTE_REFERENCE_PREFIX}-{y}-{n:05d}"
        existing = db.session.scalar(
            select(Quote.id).where(Quote.reference == ref).limit(1)
        )
        if existing is None:
            return ref
    raise QuoteError("could not generate a unique quote reference")


# ─── Validation helpers ───────────────────────────────────────────────────
def _require_str(value: Any, name: str) -> str:
    if value is None or not isinstance(value, str) or not value.strip():
        raise InvalidQuoteInput(f"{name} is required")
    return value.strip()


def _require_email(value: Any) -> str:
    s = _require_str(value, "email").lower()
    if "@" not in s:
        raise InvalidQuoteInput("email must contain @")
    return s


def _require_product_type(value: Any) -> str:
    if value is None or not isinstance(value, str):
        raise InvalidQuoteInput("product_type is required")
    v = value.strip().lower()
    if v not in VALID_QUOTE_PRODUCT_TYPES:
        raise InvalidQuoteInput(
            f"product_type must be one of {VALID_QUOTE_PRODUCT_TYPES}"
        )
    return v


def _require_int(value: Any, name: str, minimum: int = 0) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise InvalidQuoteInput(f"{name} must be an integer")
    if n < minimum:
        raise InvalidQuoteInput(f"{name} must be >= {minimum}")
    return n


def _require_stay_dates(
    check_in_date: date | None,
    check_out_date: date | None,
) -> tuple[date, date]:
    if not isinstance(check_in_date, date) or not isinstance(check_out_date, date):
        raise InvalidQuoteInput("check-in and check-out dates are required")
    if check_out_date <= check_in_date:
        raise InvalidQuoteInput("check-out must be after check-in")
    return check_in_date, check_out_date


def _require_money(value: Any, name: str, *, minimum: Decimal) -> Decimal:
    try:
        amount = Decimal(str(value).strip()).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, TypeError, ValueError, AttributeError) as exc:
        raise InvalidQuoteInput(f"{name} must be a valid amount") from exc
    if not amount.is_finite() or amount < minimum:
        raise InvalidQuoteInput(f"{name} must be at least {minimum:.2f}")
    if amount > Decimal("9999999999.99"):
        raise InvalidQuoteInput(f"{name} is too large")
    return amount


def _manual_room_selection(quote: Quote) -> list[dict[str, Any]]:
    """Build room snapshots for a manual quote using capacity only."""
    from models.hotel import Hotel
    from services.hotel_capacity_service import first_room_allocation

    hotel = db.session.get(Hotel, quote.product_id)
    if hotel is None or not hotel.is_active or quote.nights is None:
        return []
    allocation = first_room_allocation(
        hotel.id,
        adults=quote.adults,
        child_ages=[6] * quote.children,
    )
    if not allocation:
        return []

    adult_rate = Decimal(str(quote.price_adult))
    child_rate = Decimal(str(quote.price_child))
    nights = quote.nights
    return [
        {
            "room_id": int(item["room_id"]),
            "room_type": item["room"].type,
            "rate_id": None,
            "adults": int(item["adults"]),
            "children": int(item["children"]),
            "child_ages": list(item["child_ages"]),
            "infants": int(item["infants"]),
            "adult_rate": str(adult_rate),
            "child_rate": str(child_rate),
            "nights": nights,
            "line_total": str(
                (
                    adult_rate * int(item["adults"])
                    + child_rate * int(item["children"])
                ) * nights
            ),
            "currency": quote.currency,
        }
        for item in allocation
    ]


def _calculate_hotel_quote_pricing(
    *,
    hotel_id: int,
    adults: int,
    children: int,
    check_in_date: date,
    check_out_date: date,
) -> dict[str, Any]:
    """Price the cheapest capacity-fitting room group using stored room rates."""
    from services.hotel_capacity_service import best_room_grouping

    check_in_date, check_out_date = _require_stay_dates(
        check_in_date, check_out_date
    )
    grouping = best_room_grouping(
        hotel_id,
        adults=adults,
        child_ages=[6] * children,
        check_in=check_in_date,
        check_out=check_out_date,
    )
    if grouping is None:
        raise InvalidQuoteInput(
            "no active room grouping can accommodate this party"
        )
    if not grouping["rooms"]:
        raise InvalidQuoteInput(
            "no active room grouping can accommodate this party"
        )

    nights = (check_out_date - check_in_date).days
    room_currencies = {
        (room.get("currency") or grouping.get("currency") or "GBP").strip().upper()
        for room in grouping["rooms"]
    }
    if len(room_currencies) != 1:
        raise InvalidQuoteInput(
            "the selected rooms use different currencies and cannot be quoted together"
        )
    currency = room_currencies.pop()

    adult_total = Decimal("0.00")
    child_total = Decimal("0.00")
    room_total = Decimal("0.00")
    room_selection: list[dict[str, Any]] = []
    for selected in grouping["rooms"]:
        adult_rate = Decimal(str(selected["adult_price"]))
        child_rate = Decimal(str(selected["child_price"]))
        room_adults = int(selected["adults"])
        room_children = int(selected["children"])
        line_total = Decimal(str(selected["total"]))
        room_total += line_total
        adult_total += adult_rate * room_adults * nights
        child_total += child_rate * room_children * nights
        room = selected["room"]
        room_selection.append({
            "room_id": int(selected["room_id"]),
            "room_type": room.type,
            "rate_id": selected["rate_id"],
            "adults": room_adults,
            "children": room_children,
            "child_ages": list(selected["child_ages"]),
            "infants": 0,
            "adult_rate": str(adult_rate),
            "child_rate": str(child_rate),
            "nights": nights,
            "line_total": str(line_total),
            "currency": currency,
        })

    component_total = adult_total + child_total
    if room_total != component_total:
        raise InvalidQuoteInput(
            "the selected room-rate breakdown could not be reconciled"
        )
    total = room_total.quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if total <= 0:
        raise InvalidQuoteInput("the selected room rates do not produce a payable total")

    return {
        "adult_total": adult_total.quantize(Decimal("0.01")),
        "child_total": child_total.quantize(Decimal("0.01")),
        "total": total,
        "currency": currency,
        "nights": nights,
        "check_in_date": check_in_date,
        "check_out_date": check_out_date,
        "room_selection": room_selection,
    }


def preview_hotel_quote(
    *,
    hotel_id: int,
    adults: int,
    children: int,
    check_in_date: date,
    check_out_date: date,
) -> dict[str, Any]:
    """Preview a hotel quote using current database room rates without saving."""
    return _calculate_hotel_quote_pricing(
        hotel_id=hotel_id,
        adults=_require_int(adults, "adults", minimum=1),
        children=_require_int(children, "children", minimum=0),
        check_in_date=check_in_date,
        check_out_date=check_out_date,
    )


# ─── Public form: request a quote ─────────────────────────────────────────
def create_quote_request(
    *,
    product_type: str,
    product_id: int,
    name: str,
    email: str,
    phone: str | None = None,
    preferred_start: date | None = None,
    preferred_end: date | None = None,
    adults: int = 1,
    children: int = 0,
    message: str | None = None,
) -> dict[str, Any]:
    """Create a Mongo enquiry representing a customer's quote request.

    Returns the inserted enquiry dict.
    Raises InvalidQuoteInput on malformed data; RuntimeError if Mongo
    is not configured (the caller must surface this to the user).
    """
    ptype = _require_product_type(product_type)
    pid = _require_int(product_id, "product_id", minimum=1)
    nm = _require_str(name, "name")
    em = _require_email(email)
    a = _require_int(adults, "adults", minimum=1)
    c = _require_int(children, "children", minimum=0)
    preferred_start, preferred_end = _require_stay_dates(
        preferred_start, preferred_end
    )

    # Compose a searchable message from structured fields. The admin
    # sees this in the enquiry list; the individual fields live in
    # metadata for machine consumption.
    lines: list[str] = []
    if message:
        lines.append(message.strip())
    lines.append(f"Party: {a} adult(s), {c} child(ren)")
    if preferred_start:
        lines.append(f"Check-in: {preferred_start.isoformat()}")
        lines.append(f"Check-out: {preferred_end.isoformat()}")
    composed_message = "\n".join(lines)

    metadata = {
        "adults": a,
        "children": c,
        "preferred_start": preferred_start.isoformat() if preferred_start else None,
        "preferred_end": preferred_end.isoformat() if preferred_end else None,
        "source": "public_quote_form",
    }

    from mongo.enquiries import create_enquiry  # noqa: PLC0415

    try:
        enquiry = create_enquiry(
            type="quote_request",
            name=nm,
            email=em,
            phone=phone,
            product_type=ptype,
            product_id=pid,
            message=composed_message,
            metadata=metadata,
        )
    except Exception as exc:  # noqa: BLE001 — surface as domain error
        log.warning("create_quote_request: Mongo write failed: %s", exc)
        raise QuoteError(f"could not store quote request: {exc}") from exc

    # Fire-and-forget confirmation email to the customer.
    _send_quote_request_received(enquiry)

    # Best-effort admin notification.
    _send_admin_quote_request(enquiry)

    return enquiry


def _send_quote_request_received(enquiry: dict[str, Any]) -> None:
    """Notify the customer we received their request."""
    try:
        email_service.send_quote_request_received(enquiry)
    except Exception as exc:  # noqa: BLE001
        log.warning("quote request email to customer failed: %s", exc)


def _send_admin_quote_request(enquiry: dict[str, Any]) -> None:
    """Notify the admin inbox of a new request."""
    try:
        email_service.send_admin_quote_request(enquiry)
    except Exception as exc:  # noqa: BLE001
        log.warning("quote request email to admin failed: %s", exc)


# ─── Admin: draft → update → send ─────────────────────────────────────────
def create_draft(
    *,
    customer_email: str,
    product_type: str,
    product_id: int,
    product_name_snapshot: str | None = None,
    customer_name: str | None = None,
    customer_phone: str | None = None,
    customer_user_id: int | None = None,
    enquiry_id: str | None = None,
    adults: int = 1,
    children: int = 0,
    check_in_date: date | None = None,
    check_out_date: date | None = None,
    created_by_user=None,
) -> Quote:
    """Create an empty draft quote. Price and message come later.

    Party composition and stay dates are captured now so the rate lookup
    uses the original request when the admin prepares the quote.
    """
    em = _require_email(customer_email)
    ptype = _require_product_type(product_type)
    pid = _require_int(product_id, "product_id", minimum=1)
    a = _require_int(adults, "adults", minimum=1)
    c = _require_int(children, "children", minimum=0)
    check_in, check_out = _require_stay_dates(check_in_date, check_out_date)

    quote = Quote(
        reference=generate_reference(),
        customer_email=em,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_user_id=customer_user_id,
        product_type=ptype,
        product_id=pid,
        product_name_snapshot=product_name_snapshot,
        enquiry_id=enquiry_id,
        adults=a,
        children=c,
        check_in_date=check_in,
        check_out_date=check_out,
        price_adult=Decimal("0.01"),   # placeholder; set by update_draft
        price_child=Decimal("0"),
        price=Decimal("0.01"),         # placeholder; recomputed by update_draft
        currency="GBP",
        status=STATUS_DRAFT,
        created_by_user_id=getattr(created_by_user, "id", None) if created_by_user else None,
    )
    db.session.add(quote)
    db.session.commit()
    log.info(
        "quote.draft_created ref=%s product=%s/%s party=%da+%dc",
        quote.reference, ptype, pid, a, c,
    )
    return quote


def update_draft(
    quote: Quote,
    *,
    adults: Any,
    children: Any,
    check_in_date: date | None,
    check_out_date: date | None,
    valid_until: date | None = None,
    message: str | None = None,
    image_url: str | None = None,
    internal_notes: str | None = None,
) -> Quote:
    """Fill in or edit a draft quote. Refuses to touch non-draft quotes.

    The room selection and total are recalculated from database rates
    for the requested stay dates and party.
    """
    if quote.status != STATUS_DRAFT:
        raise InvalidQuoteState(
            f"cannot edit a quote in status {quote.status!r}; only draft"
        )

    adults_count = _require_int(adults, "adults", minimum=1)
    children_count = _require_int(children, "children", minimum=0)
    check_in, check_out = _require_stay_dates(
        check_in_date, check_out_date
    )
    pricing = _calculate_hotel_quote_pricing(
        hotel_id=quote.product_id,
        adults=adults_count,
        children=children_count,
        check_in_date=check_in,
        check_out_date=check_out,
    )

    quote.adults = adults_count
    quote.children = children_count
    quote.check_in_date = check_in
    quote.check_out_date = check_out
    quote.room_selection = pricing["room_selection"]
    quote.manual_pricing = False
    quote.price = pricing["total"]
    quote.currency = pricing["currency"]
    quote.price_adult = max(
        Decimal("0.01"),
        (pricing["adult_total"] / adults_count).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ),
    )
    quote.price_child = (
        (pricing["child_total"] / children_count).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if children_count
        else Decimal("0.00")
    )

    # Metadata.
    quote.valid_until = valid_until
    quote.message = (message or "").strip() or None
    quote.image_url = (image_url or "").strip() or None
    if internal_notes is not None:
        quote.internal_notes = internal_notes.strip() or None

    db.session.commit()
    log.info(
        "quote.draft_updated ref=%s party=%da+%dc total=%s %s nights=%s",
        quote.reference, quote.adults, quote.children,
        quote.price, quote.currency, pricing["nights"],
    )
    return quote


def update_manual_draft(
    quote: Quote,
    *,
    adults: Any,
    children: Any,
    check_in_date: date | None,
    check_out_date: date | None,
    adult_rate: Any,
    child_rate: Any,
    currency: Any,
    valid_until: date | None = None,
    message: str | None = None,
    image_url: str | None = None,
    internal_notes: str | None = None,
) -> Quote:
    """Save a manual per-person nightly rate and calculate the stay total."""
    if quote.status != STATUS_DRAFT:
        raise InvalidQuoteState(
            f"cannot edit a quote in status {quote.status!r}; only draft"
        )

    adults_count = _require_int(adults, "adults", minimum=1)
    children_count = _require_int(children, "children", minimum=0)
    check_in, check_out = _require_stay_dates(
        check_in_date, check_out_date
    )
    adult_price = _require_money(
        adult_rate, "adult nightly rate", minimum=Decimal("0.01")
    )
    child_price = _require_money(
        child_rate, "child nightly rate", minimum=Decimal("0.00")
    )
    currency_code = _require_str(currency, "currency").upper()
    if currency_code not in MANUAL_QUOTE_CURRENCIES:
        raise InvalidQuoteInput(
            f"currency must be one of {', '.join(MANUAL_QUOTE_CURRENCIES)}"
        )

    nights = (check_out - check_in).days
    total = (
        (adult_price * adults_count + child_price * children_count) * nights
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if total <= 0:
        raise InvalidQuoteInput("manual rates do not produce a payable total")
    if total > Decimal("9999999999.99"):
        raise InvalidQuoteInput("manual rates produce a total that is too large")

    quote.adults = adults_count
    quote.children = children_count
    quote.check_in_date = check_in
    quote.check_out_date = check_out
    quote.price_adult = adult_price
    quote.price_child = child_price
    quote.price = total
    quote.currency = currency_code
    quote.manual_pricing = True
    quote.room_selection = []

    quote.valid_until = valid_until
    quote.message = (message or "").strip() or None
    quote.image_url = (image_url or "").strip() or None
    if internal_notes is not None:
        quote.internal_notes = internal_notes.strip() or None

    quote.room_selection = _manual_room_selection(quote)
    db.session.commit()
    log.info(
        "quote.manual_draft_updated ref=%s party=%da+%dc total=%s %s nights=%s",
        quote.reference, adults_count, children_count, total, currency_code, nights,
    )
    return quote


def send_quote(quote: Quote, *, user=None) -> Quote:
    """Transition draft → sent and email the customer."""
    if quote.status != STATUS_DRAFT:
        raise InvalidQuoteState(
            f"cannot send a quote in status {quote.status!r}; only draft"
        )
    if quote.manual_pricing:
        if quote.nights is None:
            raise InvalidQuoteState(
                "save the manual quote with valid stay dates before sending"
            )
        expected_total = (
            Decimal(str(quote.price_adult or 0)) * quote.adults
            + Decimal(str(quote.price_child or 0)) * quote.children
        ) * quote.nights
        if expected_total.quantize(Decimal("0.01")) != Decimal(str(quote.price)):
            raise InvalidQuoteState(
                "the saved manual rates do not match the quote total; save the draft again"
            )
        quote.room_selection = _manual_room_selection(quote)
        if not quote.room_selection:
            raise InvalidQuoteState(
                "manual total saved, but this hotel has no active room grouping for the party; "
                "select a valid hotel and ensure its room capacity is set before sending"
            )
    elif not quote.room_selection or quote.nights is None:
        raise InvalidQuoteState(
            "save the quote with valid stay dates and room rates before sending"
        )

    quote.status = STATUS_SENT
    quote.sent_at = datetime.now(timezone.utc)
    if user is not None and getattr(user, "id", None):
        quote.created_by_user_id = quote.created_by_user_id or user.id
    db.session.commit()

    # Do not leave a quote marked sent when the mail service did not
    # confirm delivery; keeping it as a draft lets the admin retry.
    try:
        email_sent = email_service.send_quote_to_customer(quote)
    except Exception as exc:  # noqa: BLE001
        log.warning("send_quote: email failed for ref=%s: %s", quote.reference, exc)
        email_sent = False

    if not email_sent:
        quote.status = STATUS_DRAFT
        quote.sent_at = None
        db.session.commit()
        raise InvalidQuoteState(
            "email delivery was not confirmed; check the MAIL_* settings and retry"
        )

    log.info("quote.sent ref=%s to=%s", quote.reference, quote.customer_email)
    return quote


def cancel_quote(quote: Quote, *, user=None, reason: str | None = None) -> Quote:
    """Cancel a draft or sent quote. Customer-facing quotes get an email."""
    if quote.status in (STATUS_ACCEPTED, STATUS_DECLINED, STATUS_QUOTE_CANCELLED):
        raise InvalidQuoteState(
            f"cannot cancel a quote in status {quote.status!r}"
        )

    quote.status = STATUS_QUOTE_CANCELLED
    quote.cancelled_at = datetime.now(timezone.utc)
    if reason:
        existing = quote.internal_notes or ""
        quote.internal_notes = (existing + "\n" if existing else "") + f"Cancelled: {reason}"
    db.session.commit()
    log.info("quote.cancelled ref=%s reason=%r", quote.reference, reason)
    return quote


# ─── Customer: accept / decline ───────────────────────────────────────────
def accept_quote(
    quote: Quote,
    *,
    customer_user=None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[Quote, Booking]:
    """Accept a quote and create a pending Booking.

    Returns (updated_quote, created_booking).
    Raises InvalidQuoteState if the quote is not 'sent' or has expired.
    """
    if quote.status != STATUS_SENT:
        raise InvalidQuoteState(
            f"cannot accept a quote in status {quote.status!r}; only sent"
        )
    if quote.valid_until is not None and quote.valid_until < date.today():
        # Auto-expire instead of accepting.
        quote.status = STATUS_EXPIRED
        quote.expired_at = datetime.now(timezone.utc)
        db.session.commit()
        raise InvalidQuoteState("quote has expired")

    if quote.manual_pricing:
        quote.room_selection = _manual_room_selection(quote)
        if not quote.room_selection:
            raise InvalidQuoteState(
                "the hotel no longer has an active room grouping for this party"
            )

    # Create the booking. Uses the same create_booking the public flow
    # uses, so all validation + audit trail applies. Guest checkout:
    # customer_email from the quote becomes the guest email if no user
    # is attached.
    booking_rooms = None
    if quote.room_selection:
        booking_rooms = [
            {
                "room_id": room["room_id"],
                "rate_id": room.get("rate_id"),
                "adults": room["adults"],
                "children": room["children"],
                "child_ages": room.get("child_ages") or [],
                "infants": room.get("infants", 0),
                "line_total": room["line_total"],
                "currency": room["currency"],
            }
            for room in quote.room_selection
        ]

    booking = booking_service.create_booking(
        product_type=quote.product_type,
        product_id=quote.product_id,
        travellers_adults=quote.adults,
        travellers_children=quote.children,
        total_amount=quote.price,
        currency=quote.currency,
        user=customer_user,
        guest_email=None if customer_user else quote.customer_email,
        guest_name=None if customer_user else quote.customer_name,
        guest_phone=None if customer_user else quote.customer_phone,
        check_in_date=quote.check_in_date,
        check_out_date=quote.check_out_date,
        rooms=booking_rooms,
        special_requests=f"From quote {quote.reference}. {(quote.message or '')}".strip(),
        ip=ip,
        user_agent=user_agent,
        role="customer",
    )

    quote.status = STATUS_ACCEPTED
    quote.accepted_at = datetime.now(timezone.utc)
    quote.accepted_booking_id = booking.id
    db.session.commit()

    log.info("quote.accepted ref=%s booking_ref=%s",
             quote.reference, booking.reference)
    return quote, booking


def decline_quote(quote: Quote, *, reason: str | None = None) -> Quote:
    """Decline a sent quote."""
    if quote.status != STATUS_SENT:
        raise InvalidQuoteState(
            f"cannot decline a quote in status {quote.status!r}; only sent"
        )
    quote.status = STATUS_DECLINED
    quote.declined_at = datetime.now(timezone.utc)
    if reason:
        existing = quote.internal_notes or ""
        quote.internal_notes = (existing + "\n" if existing else "") + f"Declined: {reason}"
    db.session.commit()
    log.info("quote.declined ref=%s reason=%r", quote.reference, reason)
    return quote


# ─── Bulk: expire overdue ─────────────────────────────────────────────────
def expire_all_overdue() -> int:
    """Mark every 'sent' quote past its valid_until as 'expired'.

    Called from the cloud worker each poll. Returns the count updated.
    """
    today = date.today()
    stmt = (
        select(Quote)
        .where(Quote.status == STATUS_SENT)
        .where(Quote.valid_until.is_not(None))
        .where(Quote.valid_until < today)
    )
    rows = db.session.scalars(stmt).all()
    if not rows:
        return 0
    now = datetime.now(timezone.utc)
    for q in rows:
        q.status = STATUS_EXPIRED
        q.expired_at = now
    db.session.commit()
    log.info("quote.expire_all_overdue: %s quote(s) expired", len(rows))
    return len(rows)


# ─── Queries ──────────────────────────────────────────────────────────────
def get_quote_by_reference(reference: str) -> Quote | None:
    if not reference:
        return None
    return db.session.scalars(
        select(Quote).where(Quote.reference == reference.strip().upper()).limit(1)
    ).first()


def list_open_quote_requests(*, limit: int = 50, skip: int = 0) -> tuple[list[dict], int]:
    """Return Mongo enquiries that are quote requests and still 'new'.

    Returns (items, total). If Mongo is unavailable, returns ([], 0)
    so the admin page still renders.
    """
    try:
        from mongo.enquiries import list_enquiries  # noqa: PLC0415
        items, total = list_enquiries(
            type="quote_request",
            status="new",
            limit=limit,
            skip=skip,
        )
        return items or [], int(total or 0)
    except Exception as exc:  # noqa: BLE001
        log.warning("list_open_quote_requests: Mongo unavailable: %s", exc)
        return [], 0


def list_quotes(
    *,
    status: str | None = None,
    product_type: str | None = None,
    limit: int = 50,
    skip: int = 0,
) -> tuple[list[Quote], int]:
    """Paginated SQL list of quotes with optional filters. Newest first."""
    stmt = select(Quote)
    if status:
        stmt = stmt.where(Quote.status == status.strip().lower())
    if product_type:
        stmt = stmt.where(Quote.product_type == product_type.strip().lower())

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(db.session.scalar(count_stmt) or 0)

    rows = db.session.scalars(
        stmt.order_by(Quote.id.desc()).limit(limit).offset(skip)
    ).all()
    return list(rows), total


__all__ = [
    "QuoteError",
    "InvalidQuoteInput",
    "QuoteNotFound",
    "InvalidQuoteState",
    "generate_reference",
    "create_quote_request",
    "create_draft",
    "preview_hotel_quote",
    "update_draft",
    "send_quote",
    "cancel_quote",
    "accept_quote",
    "decline_quote",
    "expire_all_overdue",
    "get_quote_by_reference",
    "list_open_quote_requests",
    "list_quotes",
]
