"""
cloud_function/tasks.py
────────────────────────
Individual task functions for the post-booking pipeline.

Each task is a small, focused operation. Together they form the
"process_booking" workflow that the worker calls for every confirmed
booking that has not yet been notified.

DESIGN
    - Every task raises on failure. The worker wraps the whole
      process_booking call with retry logic.
    - Idempotency is enforced by the worker: notification_sent_at is
      only set AFTER process_booking returns successfully. If the
      worker crashes mid-processing, the next iteration re-runs the
      whole thing — which means the customer could receive TWO emails
      if the crash happens between "email sent" and "mark sent". This
      is acceptable for coursework (at-most-once delivery is a
      distributed systems problem); a production system would use a
      queue with acknowledgment semantics.
    - Email failures are non-fatal for the pipeline: if SMTP is not
      configured (dev), the send_* functions return False and the
      task logs a warning but does not raise. The booking is still
      marked as "notified" — because we tried and the failure is
      environmental, not per-booking.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import current_app

from extensions import db
from models import Booking
from services import booking_service, email_service


# ─── Sub-tasks ────────────────────────────────────────────────────────────
def _task_send_customer_email(booking: Booking) -> bool:
    """Send the customer a confirmation email. Best-effort.

    Returns True if the send succeeded (or if SMTP is simply not
    configured and the send was skipped). Raises only on programmer
    error (bad arguments).
    """
    try:
        ok = email_service.send_booking_confirmed(booking)
    except Exception as exc:  # noqa: BLE001 — SMTP is external
        current_app.logger.warning(
            "email_service.send_booking_confirmed failed for booking=%s: %s",
            booking.reference, exc,
        )
        return False
    if not ok:
        current_app.logger.info(
            "customer email not sent for booking=%s (SMTP probably unconfigured)",
            booking.reference,
        )
    return ok


def _task_send_admin_email(booking: Booking) -> bool:
    """Send the admin notification email. Best-effort, same policy."""
    try:
        ok = email_service.send_admin_new_booking(booking)
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning(
            "email_service.send_admin_new_booking failed for booking=%s: %s",
            booking.reference, exc,
        )
        return False
    if not ok:
        current_app.logger.info(
            "admin email not sent for booking=%s (SMTP or admin inbox unconfigured)",
            booking.reference,
        )
    return ok


def _task_log_to_mongo(booking: Booking) -> bool:
    """Write an activity_logs entry for the confirmation. Best-effort."""
    try:
        from mongo.logs import log_action
        log_action(
            action="booking.confirmed_notified",
            entity_type="booking",
            entity_id=booking.id,
            user_id=booking.user_id,
            user_role="customer" if booking.user_id else "guest",
            new_value={
                "reference": booking.reference,
                "status": booking.status,
                "total_amount": str(booking.total_amount) if booking.total_amount is not None else None,
                "currency": booking.currency,
            },
            context={"source": "cloud_function"},
        )
        return True
    except Exception as exc:  # noqa: BLE001 — Mongo may be down
        current_app.logger.debug("log_action skipped: %s", exc)
        return False


def _task_append_history(booking: Booking) -> bool:
    """Append a booking_status_history row noting the notification."""
    # The status transition (pending -> confirmed) was already recorded
    # by booking_service.mark_confirmed at the time of the API call.
    # This task adds a *second*, informational row that says the
    # worker ran. We use the same to_status as the current one so the
    # transition validation in add_status_history doesn't complain.
    try:
        booking_service.add_status_history(
            booking,
            from_status=booking.status,
            to_status=booking.status,
            by_user=None,
            role="system",
            reason="Confirmed — customer and admin notified by cloud worker",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning(
            "add_status_history failed for booking=%s: %s",
            booking.reference, exc,
        )
        return False


# ─── Composite workflow ──────────────────────────────────────────────────
def process_booking(booking_id: int) -> dict[str, Any]:
    """Run the full post-booking pipeline for one booking.

    Called by the worker for each confirmed-but-not-yet-notified
    booking. Safe to re-run: the worker only invokes this for rows
    where notification_sent_at IS NULL, and we set it at the end.

    Returns a dict summary suitable for logging. Raises on hard
    failures (DB errors) so the worker's retry layer can react.
    """
    booking = db.session.get(Booking, booking_id)
    if booking is None:
        return {"booking_id": booking_id, "status": "not_found"}

    # Refuse to process bookings that aren't in the right state.
    # This shouldn't happen if the worker's query is correct, but
    # we double-check as a defence in depth.
    if booking.status != "confirmed":
        return {
            "booking_id": booking_id,
            "status": "skipped",
            "reason": f"booking is in status {booking.status!r}, not confirmed",
        }

    if booking.notification_sent_at is not None:
        return {
            "booking_id": booking_id,
            "status": "already_sent",
            "notification_sent_at": booking.notification_sent_at.isoformat(),
        }

    # Run all sub-tasks. Each one returns a bool but the pipeline does
    # NOT short-circuit: even if email fails, we still want the audit
    # log and status history to be written.
    result: dict[str, Any] = {
        "booking_id": booking_id,
        "reference": booking.reference,
        "customer_email": False,
        "admin_email": False,
        "mongo_log": False,
        "history_appended": False,
    }

    result["customer_email"] = _task_send_customer_email(booking)
    result["admin_email"] = _task_send_admin_email(booking)
    result["mongo_log"] = _task_log_to_mongo(booking)
    result["history_appended"] = _task_append_history(booking)

    # Mark as notified. This is the only commit in the pipeline; the
    # sub-tasks used the same session so their writes flush together.
    booking.notification_sent_at = datetime.now(timezone.utc)
    db.session.commit()

    result["status"] = "ok"
    return result


__all__: list[str] = ["process_booking"]
