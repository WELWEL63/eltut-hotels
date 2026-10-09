"""
services/payment_service.py
───────────────────────────
PayPal REST API wrapper.

This service takes a Payment row (created by booking_service), talks to
PayPal, and updates the row's status + provider identifiers + raw
payload. It is the ONLY place PayPal SDK calls happen.

PAYPAL FLOW (redirect mode)
    1. Booking is created → Payment row with status='created'
    2. create_payment(payment) → returns approval URL, PayPal payment id
    3. Customer approves on paypal.com and returns via return_url
    4. execute_payment(payment, payer_id) → captures → status='completed'
    5. booking_service.mark_confirmed(booking)

REFUND FLOW
    1. Admin triggers refund from admin panel
    2. refund_payment(payment, amount=None) → full or partial
    3. status='refunded', refunded_amount, refunded_at set

PUBLIC API
    is_configured() -> bool
    create_payment(payment) -> (approval_url, paypal_payment_id)
    execute_payment(payment, payer_id) -> dict
    refund_payment(payment, amount=None) -> dict
    get_payment_status(payment) -> str | None
    verify_webhook(headers, raw_body) -> bool

DESIGN NOTES
    - No Flask request imports. Caller supplies return_url, cancel_url,
      payer_id, and webhook headers/body.
    - Uses Flask config values (PAYPAL_MODE, PAYPAL_CLIENT_ID,
      PAYPAL_CLIENT_SECRET, PAYPAL_CURRENCY, PAYPAL_RETURN_URL,
      PAYPAL_CANCEL_URL) via current_app.config.
    - Raises PaymentConfigError when credentials are missing so the dev
      sees a clear message.
    - All amounts converted to strings ("12.50") because that is what
      PayPal expects.
    - Updates payment.provider_payment_id, .provider_payer_id,
      .status, .payload, .processed_at, .failure_reason as appropriate.
    - Idempotent-friendly: checks current status before each operation.
    - Reads/writes payment rows only. Never touches bookings — that is
      booking_service's job.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from flask import current_app

from extensions import db
from models import Payment


log = logging.getLogger(__name__)


# ─── Domain exceptions ─────────────────────────────────────────────
class PaymentError(Exception):
    """Base class for payment-domain errors."""


class PaymentConfigError(PaymentError):
    """PayPal credentials missing or invalid."""


class PaymentStateError(PaymentError):
    """Attempted an operation not allowed from the current payment status."""


class PaymentProviderError(PaymentError):
    """PayPal returned an error."""


# ─── Constants ─────────────────────────────────────────────────────
STATUS_CREATED = "created"
STATUS_APPROVED = "approved"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_REFUNDED = "refunded"


# ─── Config / SDK helpers ──────────────────────────────────────────
def _config() -> dict[str, str]:
    return {
        "mode": (current_app.config.get("PAYPAL_MODE") or "sandbox").lower(),
        "client_id": current_app.config.get("PAYPAL_CLIENT_ID") or "",
        "client_secret": current_app.config.get("PAYPAL_CLIENT_SECRET") or "",
        "currency": (current_app.config.get("PAYPAL_CURRENCY") or "USD").upper(),
        "return_url": current_app.config.get("PAYPAL_RETURN_URL") or "",
        "cancel_url": current_app.config.get("PAYPAL_CANCEL_URL") or "",
    }


# Strings that indicate the .env still holds a placeholder, not a real
# PayPal credential.
_PAYPAL_PLACEHOLDER_TOKENS: tuple[str, ...] = (
    "your-paypal-client-id",
    "your-paypal-client-secret",
    "changeme",
    "placeholder",
)


def _is_placeholder_credential(value: str) -> bool:
    v = (value or "").strip().lower()
    if not v:
        return True
    return any(tok in v for tok in _PAYPAL_PLACEHOLDER_TOKENS)


def is_configured() -> bool:
    """True when real (non-placeholder) PayPal credentials are present."""
    cfg = _config()
    if _is_placeholder_credential(cfg["client_id"]):
        return False
    if _is_placeholder_credential(cfg["client_secret"]):
        return False
    return True


def _require_config() -> dict[str, str]:
    cfg = _config()
    # Placeholder strings count as "not configured" — see the
    # _PAYPAL_PLACEHOLDER_TOKENS tuple above.
    if _is_placeholder_credential(cfg["client_id"]):
        raise PaymentConfigError(
            "PayPal credentials are missing or still placeholders. "
            "Set real PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env "
            "before using the payment flow."
        )
    if _is_placeholder_credential(cfg["client_secret"]):
        raise PaymentConfigError(
            "PayPal credentials are missing or still placeholders. "
            "Set real PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env "
            "before using the payment flow."
        )
    return cfg


def _import_sdk():
    """Import paypalrestsdk lazily so the app boots without it configured."""
    try:
        import paypalrestsdk  # noqa: PLC0415
    except ImportError as exc:
        raise PaymentConfigError(
            "paypalrestsdk is not installed. "
            "Run: pip install -r requirements.txt"
        ) from exc
    return paypalrestsdk


def _configure_sdk(cfg: dict[str, str]) -> None:
    sdk = _import_sdk()
    sdk.configure(
        {
            "mode": cfg["mode"],
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
        }
    )


def _amount_str(value: Any) -> str:
    """PayPal expects amounts as strings with two decimal places."""
    try:
        d = Decimal(str(value))
    except Exception as exc:  # noqa: BLE001
        raise PaymentError(f"invalid amount: {value!r}") from exc
    return f"{d:.2f}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ─── Public API ────────────────────────────────────────────────────
def create_payment(payment: Payment) -> tuple[str, str]:
    """
    Create a PayPal payment for the given Payment row.

    Returns (approval_url, paypal_payment_id).

    The Payment row must be in status 'created' (or 'failed' — a retry
    is allowed from 'failed'). Updates the row with provider_payment_id
    and status='created'.
    """
    if payment.status not in {STATUS_CREATED, STATUS_FAILED}:
        raise PaymentStateError(
            f"cannot create a payment from status {payment.status!r}"
        )
    cfg = _require_config()
    _configure_sdk(cfg)
    sdk = _import_sdk()

    paypal_payment = sdk.Payment(
        {
            "intent": "sale",
            "payer": {"payment_method": "paypal"},
            "redirect_urls": {
                "return_url": cfg["return_url"],
                "cancel_url": cfg["cancel_url"],
            },
            "transactions": [
                {
                    "amount": {
                        "total": _amount_str(payment.amount),
                        "currency": payment.currency,
                    },
                    "description": f"ElTut booking payment #{payment.id}",
                    "invoice_number": f"ELT-PAY-{payment.id}",
                }
            ],
        }
    )

    if not paypal_payment.create():
        error_msg = str(paypal_payment.error) if paypal_payment.error else "unknown"
        payment.status = STATUS_FAILED
        payment.failure_reason = error_msg[:500]
        payment.payload = {"create_error": paypal_payment.error}
        db.session.flush()
        raise PaymentProviderError(f"PayPal create failed: {error_msg}")

    approval_url = next(
        (
            link.href
            for link in paypal_payment.links
            if link.rel == "approval_url"
        ),
        None,
    )
    if not approval_url:
        raise PaymentProviderError(
            "PayPal did not return an approval_url"
        )

    payment.provider = "paypal"
    payment.provider_payment_id = paypal_payment.id
    payment.status = STATUS_CREATED
    payment.payload = paypal_payment.to_dict()
    payment.failure_reason = None
    db.session.flush()

    return approval_url, paypal_payment.id


def execute_payment(payment: Payment, payer_id: str) -> dict[str, Any]:
    """
    Execute (capture) an approved PayPal payment.

    Called from the return_url handler once PayPal redirects the user
    back with `paymentId` and `PayerID`.

    On success: status='completed', processed_at set.
    On failure: status='failed', failure_reason set. Raises.
    """
    if payment.status == STATUS_COMPLETED:
        # Idempotent — already captured
        return {"status": "already_completed", "payment_id": payment.provider_payment_id}

    if not payment.provider_payment_id:
        raise PaymentStateError("payment has no PayPal id — call create_payment first")

    if not payer_id or not payer_id.strip():
        raise PaymentError("payer_id is required")

    cfg = _require_config()
    _configure_sdk(cfg)
    sdk = _import_sdk()

    paypal_payment = sdk.Payment.find(payment.provider_payment_id)
    if not paypal_payment.execute({"payer_id": payer_id.strip()}):
        error_msg = str(paypal_payment.error) if paypal_payment.error else "unknown"
        payment.status = STATUS_FAILED
        payment.failure_reason = error_msg[:500]
        payment.payload = {"execute_error": paypal_payment.error}
        db.session.flush()
        raise PaymentProviderError(f"PayPal execute failed: {error_msg}")

    # Extract payment id / payer id from response
    payment.status = STATUS_COMPLETED
    payment.processed_at = _now_utc()
    payment.provider_payer_id = payer_id.strip()
    payment.payload = paypal_payment.to_dict()
    payment.failure_reason = None
    db.session.flush()

    return {
        "status": "completed",
        "payment_id": payment.provider_payment_id,
        "amount": str(payment.amount),
        "currency": payment.currency,
    }


def refund_payment(
    payment: Payment, amount: Decimal | str | float | None = None
) -> dict[str, Any]:
    """
    Refund a completed payment, in full or in part.

    If amount is None or matches payment.amount, does a full refund.
    Updates status to 'refunded' + refunded_amount + refunded_at.

    On failure, sets failure_reason and raises PaymentProviderError.
    """
    if payment.status not in {STATUS_COMPLETED}:
        raise PaymentStateError(
            f"can only refund completed payments, current status is "
            f"{payment.status!r}"
        )

    refund_amount = (
        payment.amount if amount is None else Decimal(str(amount))
    )
    if refund_amount <= 0:
        raise PaymentError("refund amount must be positive")
    if refund_amount > payment.amount:
        raise PaymentError(
            f"refund amount {refund_amount} exceeds payment amount {payment.amount}"
        )

    cfg = _require_config()
    _configure_sdk(cfg)
    sdk = _import_sdk()

    sale_id = _extract_sale_id(payment)
    if not sale_id:
        raise PaymentProviderError(
            "cannot find sale id in payment payload — was the payment captured?"
        )

    refund = sdk.Sale.find(sale_id).refund(
        {
            "amount": {
                "total": _amount_str(refund_amount),
                "currency": payment.currency,
            }
        }
    )

    if not refund.success():
        error_msg = str(refund.error) if refund.error else "unknown"
        payment.failure_reason = error_msg[:500]
        db.session.flush()
        raise PaymentProviderError(f"PayPal refund failed: {error_msg}")

    payment.status = STATUS_REFUNDED
    payment.refunded_amount = refund_amount
    payment.refunded_at = _now_utc()
    # Preserve the previous payload and append the refund
    payload = dict(payment.payload or {})
    payload["refund"] = refund.to_dict()
    payment.payload = payload
    payment.failure_reason = None
    db.session.flush()

    return {
        "status": "refunded",
        "amount": str(refund_amount),
        "currency": payment.currency,
    }


def get_payment_status(payment: Payment) -> str | None:
    """
    Query PayPal for the current status of a payment.

    Returns the PayPal-side state string, or None if the payment has no
    provider id yet.
    """
    if not payment.provider_payment_id:
        return None
    cfg = _require_config()
    _configure_sdk(cfg)
    sdk = _import_sdk()
    try:
        p = sdk.Payment.find(payment.provider_payment_id)
        return p.state
    except Exception as exc:  # noqa: BLE001
        log.warning("PayPal status check failed: %s", exc)
        return None


def verify_webhook(headers: dict[str, str], raw_body: bytes) -> bool:
    """
    Verify a PayPal webhook signature.

    In sandbox, PayPal's verification is best-effort; we accept the
    webhook when credentials are present and the required headers are
    there. In production this should call the SDK's
    WebhookEvent.verify().
    """
    if not is_configured():
        log.warning("PayPal not configured; rejecting webhook")
        return False
    # In a full implementation, call paypalrestsdk.WebhookEvent.verify().
    # For coursework we require the presence of the canonical headers.
    required = {
        "paypal-transmission-id",
        "paypal-transmission-time",
        "paypal-transmission-sig",
        "paypal-cert-url",
    }
    lower = {k.lower() for k in headers.keys()}
    return required.issubset(lower)


# ─── Internal helpers ──────────────────────────────────────────────
def _extract_sale_id(payment: Payment) -> str | None:
    """
    Walk the stored PayPal payload to find the sale id needed for refunds.
    """
    payload = payment.payload or {}
    try:
        transactions = payload.get("transactions") or []
        for tx in transactions:
            related = tx.get("related_resources") or []
            for r in related:
                sale = r.get("sale") or {}
                sale_id = sale.get("id")
                if sale_id:
                    return sale_id
    except Exception:  # noqa: BLE001
        pass
    return None
