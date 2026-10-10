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
       → update_draft() sets price, currency, validity, message, image.

    3. Admin clicks "Send to customer".
       → send_quote() transitions draft → sent, sets sent_at, sends
         an email to the customer with a link to /quote/<reference>.

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
from decimal import Decimal, InvalidOperation
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


def _to_decimal(value: Any, name: str) -> Decimal:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise InvalidQuoteInput(f"{name} is required")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise InvalidQuoteInput(f"{name} must be a number")
    if d <= 0:
        raise InvalidQuoteInput(f"{name} must be > 0")
    return d.quantize(Decimal("0.01"))


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

    # Compose a searchable message from structured fields. The admin
    # sees this in the enquiry list; the individual fields live in
    # metadata for machine consumption.
    lines: list[str] = []
    if message:
        lines.append(message.strip())
    lines.append(f"Party: {a} adult(s), {c} child(ren)")
    if preferred_start:
        lines.append(f"Preferred start: {preferred_start.isoformat()}")
    if preferred_end:
        lines.append(f"Preferred end: {preferred_end.isoformat()}")
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
    created_by_user=None,
) -> Quote:
    """Create an empty draft quote. Price and message come later.

    Party composition is captured now so the price editor can show the
    correct traveller counts when the admin sets per-person prices.
    """
    em = _require_email(customer_email)
    ptype = _require_product_type(product_type)
    pid = _require_int(product_id, "product_id", minimum=1)
    a = _require_int(adults, "adults", minimum=1)
    c = _require_int(children, "children", minimum=0)

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
    price_adult: Any,
    price_child: Any = 0,
    adults: int | None = None,
    children: int | None = None,
    currency: str = "GBP",
    valid_until: date | None = None,
    message: str | None = None,
    image_url: str | None = None,
    internal_notes: str | None = None,
) -> Quote:
    """Fill in or edit a draft quote. Refuses to touch non-draft quotes.

    The stored `price` is always recomputed from the components:
        adults * price_adult + children * price_child
    so the customer sees a total that matches the breakdown.
    """
    if quote.status != STATUS_DRAFT:
        raise InvalidQuoteState(
            f"cannot edit a quote in status {quote.status!r}; only draft"
        )

    # Party size — optional overrides.
    if adults is not None:
        quote.adults = _require_int(adults, "adults", minimum=1)
    if children is not None:
        quote.children = _require_int(children, "children", minimum=0)

    # Per-person prices.
    quote.price_adult = _to_decimal(price_adult, "price_adult")
    # price_child may legitimately be 0 (free for children).
    try:
        child_dec = Decimal(str(price_child or "0"))
        if child_dec < 0:
            raise InvalidQuoteInput("price_child must be >= 0")
    except (InvalidOperation, ValueError):
        raise InvalidQuoteInput("price_child must be a number")
    quote.price_child = child_dec.quantize(Decimal("0.01"))

    # Currency + metadata.
    quote.currency = (currency or "GBP").strip().upper()[:3]
    quote.valid_until = valid_until
    quote.message = (message or "").strip() or None
    quote.image_url = (image_url or "").strip() or None
    if internal_notes is not None:
        quote.internal_notes = internal_notes.strip() or None

    # Recompute total from components. Store as Decimal, 2dp.
    total = (
        quote.price_adult * quote.adults
        + quote.price_child * quote.children
    )
    quote.price = total.quantize(Decimal("0.01"))

    db.session.commit()
    log.info(
        "quote.draft_updated ref=%s party=%da+%dc adult=%s child=%s total=%s %s",
        quote.reference, quote.adults, quote.children,
        quote.price_adult, quote.price_child, quote.price, quote.currency,
    )
    return quote


def send_quote(quote: Quote, *, user=None) -> Quote:
    """Transition draft → sent and email the customer."""
    if quote.status != STATUS_DRAFT:
        raise InvalidQuoteState(
            f"cannot send a quote in status {quote.status!r}; only draft"
        )

    quote.status = STATUS_SENT
    quote.sent_at = datetime.now(timezone.utc)
    if user is not None and getattr(user, "id", None):
        quote.created_by_user_id = quote.created_by_user_id or user.id
    db.session.commit()

    # Best-effort email — failure does NOT roll back the status change.
    try:
        email_service.send_quote_to_customer(quote)
    except Exception as exc:  # noqa: BLE001
        log.warning("send_quote: email failed for ref=%s: %s", quote.reference, exc)

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

    # Create the booking. Uses the same create_booking the public flow
    # uses, so all validation + audit trail applies. Guest checkout:
    # customer_email from the quote becomes the guest email if no user
    # is attached.
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
