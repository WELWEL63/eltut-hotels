"""blueprints/api/payments_api.py - PayPal payment endpoints.

Public write surface. No auth, no CSRF (blueprint is exempted in app.py).

  POST /api/v1/payments/create-order  -> start a PayPal payment for a booking
  POST /api/v1/payments/capture-order -> capture after user approval
  POST /api/v1/payments/paypal/webhook -> PayPal event receiver

The payment row is created by booking_service.create_booking() with
status='created'. This module finds it and drives the PayPal lifecycle.

WHY 503 on unconfigured PayPal: the dev environment has placeholder
credentials. Rather than fabricate a fake approval URL, we return an
honest 503 so the caller knows payment processing is not available.
This is a real, reportable state - not an error to hide.

WHY 200 on the webhook even for unknown events: PayPal retries any
non-2xx response, potentially many times. Returning 200 for events we
do not handle prevents duplicate side effects.
"""
from __future__ import annotations

from typing import Any

from flask import jsonify, request
from sqlalchemy import select

from blueprints.api import api_bp
from extensions import db
from models import Booking, Payment
from services import booking_service, payment_service


VALID_CAPTURE_STATUSES_FOR_BOOKING = ("pending", "confirmed")


def _ok(data: Any, status: int = 200):
    return jsonify({"data": data, "error": None}), status


def _err(code: str, message: str, status: int):
    return jsonify({"data": None, "error": {"code": code, "message": message}}), status


def _get_json() -> dict | None:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else None


def _find_payment_for_booking(booking_id: int) -> Payment | None:
    """Return the most recent Payment row for a booking.

    A booking should have exactly one, but we order by id desc so that
    if a future retry flow creates a new one, we always pick the latest.
    """
    return db.session.scalars(
        select(Payment)
        .where(Payment.booking_id == booking_id)
        .order_by(Payment.id.desc())
        .limit(1)
    ).first()


# --- Endpoint 1: create-order ------------------------------------------------
@api_bp.post("/payments/create-order")
def payments_create_order():
    """Start a PayPal payment for a booking reference.

    Body: {"booking_ref": "ELT-2026-71562"}
    Returns: {approval_url, payment_id, booking_ref, amount, currency}
    """
    if not payment_service.is_configured():
        return _err(
            "payments_not_configured",
            "PayPal is not configured in this environment",
            503,
        )

    body = _get_json()
    if body is None:
        return _err("invalid_input", "JSON body required", 400)

    ref = (body.get("booking_ref") or "").strip()
    if not ref:
        return _err("invalid_input", "booking_ref is required", 400)

    bk = booking_service.get_booking_by_reference(ref)
    if bk is None:
        return _err("not_found", f"booking {ref!r} not found", 404)

    if bk.status not in VALID_CAPTURE_STATUSES_FOR_BOOKING:
        return _err(
            "invalid_booking_status",
            f"booking status is {bk.status!r}, cannot start payment",
            409,
        )

    payment = _find_payment_for_booking(bk.id)
    if payment is None:
        return _err("not_found", "no payment row attached to this booking", 404)

    if payment.status == payment_service.STATUS_COMPLETED:
        return _err("already_paid", "payment for this booking is already completed", 409)

    try:
        approval_url, provider_payment_id = payment_service.create_payment(payment)
    except payment_service.PaymentConfigError as exc:
        return _err("payments_not_configured", str(exc), 503)
    except payment_service.PaymentStateError as exc:
        return _err("invalid_payment_state", str(exc), 409)
    except payment_service.PaymentProviderError as exc:
        db.session.rollback()
        return _err("provider_error", str(exc), 502)
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        return _err("server_error", f"could not create payment: {exc}", 500)

    db.session.commit()

    return _ok(
        {
            "approval_url": approval_url,
            "payment_id": provider_payment_id,
            "booking_ref": bk.reference,
            "amount": float(payment.amount) if payment.amount is not None else None,
            "currency": payment.currency,
        },
        201,
    )


# --- Endpoint 2: capture-order ----------------------------------------------
@api_bp.post("/payments/capture-order")
def payments_capture_order():
    """Capture an approved PayPal payment.

    Body: {"booking_ref": "ELT-2026-71562", "payer_id": "PAYER123"}
    Returns: {booking_ref, booking_status, payment_status, ...}

    Idempotent: if the payment is already completed, returns 200 with
    the current state instead of an error. PayPal can call the return
    URL twice (browser refresh), so this matters.
    """
    if not payment_service.is_configured():
        return _err(
            "payments_not_configured",
            "PayPal is not configured in this environment",
            503,
        )

    body = _get_json()
    if body is None:
        return _err("invalid_input", "JSON body required", 400)

    ref = (body.get("booking_ref") or "").strip()
    payer_id = (body.get("payer_id") or "").strip() or None
    if not ref:
        return _err("invalid_input", "booking_ref is required", 400)
    if not payer_id:
        return _err("invalid_input", "payer_id is required", 400)

    bk = booking_service.get_booking_by_reference(ref)
    if bk is None:
        return _err("not_found", f"booking {ref!r} not found", 404)

    payment = _find_payment_for_booking(bk.id)
    if payment is None:
        return _err("not_found", "no payment row attached to this booking", 404)

    # Idempotent path: already paid, already confirmed
    if payment.status == payment_service.STATUS_COMPLETED:
        return _ok(
            {
                "booking_ref": bk.reference,
                "booking_status": bk.status,
                "payment_status": payment.status,
                "amount": float(payment.amount) if payment.amount is not None else None,
                "currency": payment.currency,
                "idempotent": True,
            }
        )

    try:
        payment_service.execute_payment(payment, payer_id)
    except payment_service.PaymentConfigError as exc:
        return _err("payments_not_configured", str(exc), 503)
    except payment_service.PaymentStateError as exc:
        return _err("invalid_payment_state", str(exc), 409)
    except payment_service.PaymentProviderError as exc:
        db.session.rollback()
        return _err("provider_error", str(exc), 502)
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        return _err("server_error", f"could not capture payment: {exc}", 500)

    # Payment succeeded: move the booking to confirmed.
    try:
        booking_service.mark_confirmed(
            bk,
            by_user=None,
            role="system",
            reason="PayPal capture completed",
        )
    except Exception as exc:  # noqa: BLE001
        # Payment is captured; booking status transition failed. Do not
        # roll back the payment - the money has moved. Log and return
        # 500 so the client can retry the state transition via support.
        db.session.commit()
        return _err(
            "booking_state_error",
            f"payment captured but booking transition failed: {exc}",
            500,
        )

    db.session.commit()

    return _ok(
        {
            "booking_ref": bk.reference,
            "booking_status": bk.status,
            "payment_status": payment.status,
            "amount": float(payment.amount) if payment.amount is not None else None,
            "currency": payment.currency,
        }
    )


# --- Endpoint 3: webhook -----------------------------------------------------
@api_bp.post("/payments/paypal/webhook")
def payments_paypal_webhook():
    """Receive a PayPal webhook event.

    Always returns 200 once the signature is verified - even for unknown
    event types - because PayPal retries non-2xx responses.
    Returns 400 only if the signature verification fails.
    """
    raw_body = request.get_data() or b""
    headers = {k: v for k, v in request.headers.items()}

    # WHY check is_configured() first: verify_webhook() returns False
    # (does not raise) when credentials are missing, which would
    # otherwise be reported as "invalid signature" (400) - blaming the
    # caller for a server-side misconfiguration. Return 503 instead so
    # the response distinguishes "cannot verify" from "signature wrong".
    if not payment_service.is_configured():
        return _err(
            "payments_not_configured",
            "PayPal webhook verification is not available - "
            "PAYPAL_WEBHOOK_ID is not configured for this environment",
            503,
        )

    try:
        verified = payment_service.verify_webhook(headers, raw_body)
    except payment_service.PaymentConfigError as exc:
        return _err("payments_not_configured", str(exc), 503)
    except Exception as exc:  # noqa: BLE001
        return _err("webhook_error", f"verification failed: {exc}", 400)

    if not verified:
        return _err(
            "invalid_signature",
            "webhook signature did not verify - required PayPal "
            "transmission headers are missing",
            400,
        )

    body = _get_json() or {}
    event_type = (body.get("event_type") or "").strip()

    # We only act on capture events. Everything else is acknowledged.
    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        resource = body.get("resource") or {}
        order_id = resource.get("id") or resource.get("order_id")
        if order_id:
            _handle_capture_completed(str(order_id))
    elif event_type == "PAYMENT.CAPTURE.DENIED":
        resource = body.get("resource") or {}
        order_id = resource.get("id") or resource.get("order_id")
        if order_id:
            _handle_capture_denied(str(order_id), resource)

    return _ok({"received": True, "event_type": event_type})


def _handle_capture_completed(order_id: str) -> None:
    """Mark the booking confirmed if we can find it by provider ids."""
    payment = _find_payment_by_provider_id(order_id)
    if payment is None:
        return
    if payment.status == payment_service.STATUS_COMPLETED:
        return
    booking = db.session.get(Booking, payment.booking_id)
    if booking is None:
        return
    try:
        booking_service.mark_confirmed(
            booking,
            by_user=None,
            role="system",
            reason=f"PayPal webhook: capture completed {order_id}",
        )
        db.session.commit()
    except Exception:
        db.session.rollback()


def _handle_capture_denied(order_id: str, resource: dict) -> None:
    """Mark the payment as failed."""
    payment = _find_payment_by_provider_id(order_id)
    if payment is None:
        return
    if payment.status == payment_service.STATUS_COMPLETED:
        return
    try:
        payment.status = payment_service.STATUS_FAILED
        payment.failure_reason = (
            resource.get("status_details", {}).get("reason")
            if isinstance(resource.get("status_details"), dict)
            else "paypal capture denied"
        )
        db.session.commit()
    except Exception:
        db.session.rollback()


def _find_payment_by_provider_id(order_id: str) -> Payment | None:
    """Look up a Payment row by either provider_payment_id or provider_order_id."""
    return db.session.scalars(
        select(Payment)
        .where(
            (Payment.provider_payment_id == order_id)
            | (Payment.provider_order_id == order_id)
        )
        .order_by(Payment.id.desc())
        .limit(1)
    ).first()
