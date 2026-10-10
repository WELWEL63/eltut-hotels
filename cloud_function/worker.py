"""
cloud_function/worker.py
─────────────────────────
Background worker process. Polls the bookings table every 30 seconds
for confirmed bookings that have not yet been notified, and runs the
process_booking pipeline against each with a bounded retry policy.

USAGE
    Local:
        python -m cloud_function.worker
    Render:
        Procfile: worker: python -m cloud_function.worker

ENVIRONMENT
    Reads the same .env / config as the Flask app. Calls create_app()
    once to wire up extensions, then opens its own sessions per booking.

RETRY POLICY
    3 attempts per booking, exponential backoff 5s / 25s / 125s.
    On success: notification_sent_at is committed.
    On permanent failure: notification_failed_at is set, admin alerted.

SIGNAL HANDLING
    SIGTERM / SIGINT cause a clean shutdown (finish current booking,
    then exit). Render sends SIGTERM on deploy / scale-down.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app import create_app
from extensions import db
from models import Booking


# ─── Configuration ────────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS = int(os.getenv("WORKER_POLL_INTERVAL", "30"))
BATCH_SIZE = int(os.getenv("WORKER_BATCH_SIZE", "20"))
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (5, 25, 125)

log = logging.getLogger("cloud_function.worker")


# ─── Shutdown handling ────────────────────────────────────────────────────
_shutdown = False

def _handle_shutdown(signum, frame):  # noqa: ARG001
    global _shutdown
    log.info("received signal %s — will exit after current batch", signum)
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_shutdown)
signal.signal(signal.SIGINT, _handle_shutdown)


# ─── Query: pending notifications ─────────────────────────────────────────
def _pending_booking_ids() -> list[int]:
    """Return ids of confirmed bookings that haven't been notified yet.

    Also excludes bookings that failed permanently — those are recorded
    with notification_failed_at and should not be retried indefinitely.
    """
    stmt = (
        select(Booking.id)
        .where(Booking.status == "confirmed")
        .where(Booking.notification_sent_at.is_(None))
        .where(Booking.notification_failed_at.is_(None))
        .order_by(Booking.id.asc())
        .limit(BATCH_SIZE)
    )
    return list(db.session.scalars(stmt))


# ─── Retry wrapper ────────────────────────────────────────────────────────
def _process_with_retry(booking_id: int) -> bool:
    """Run process_booking with exponential backoff. Returns True on success."""
    from cloud_function.tasks import process_booking

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            result = process_booking(booking_id)
            log.info("processed booking id=%s attempt=%s result=%s",
                     booking_id, attempt, result)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("attempt %s/%s failed for booking id=%s: %s",
                        attempt, MAX_ATTEMPTS, booking_id, exc)
            if attempt == MAX_ATTEMPTS:
                return False
            wait = BACKOFF_SECONDS[attempt - 1]
            log.info("sleeping %ss before retry", wait)
            time.sleep(wait)
    return False


# ─── Permanent-failure handling ───────────────────────────────────────────
def _mark_failed(booking_id: int) -> None:
    """Record a permanent failure and alert the admin."""
    try:
        booking = db.session.get(Booking, booking_id)
        if booking is None:
            return
        booking.notification_failed_at = datetime.now(timezone.utc)
        db.session.commit()
        log.error("booking id=%s reference=%s marked FAILED after %s attempts",
                  booking.id, booking.reference, MAX_ATTEMPTS)

        try:
            from services import email_service
            email_service.send_admin_new_booking(booking)
        except Exception as exc:  # noqa: BLE001
            log.debug("admin alert skipped: %s", exc)

        try:
            from mongo.logs import log_action
            log_action(
                action="booking.notification_failed",
                entity_type="booking",
                entity_id=booking.id,
                new_value={"reference": booking.reference,
                           "attempts": MAX_ATTEMPTS},
                context={"source": "cloud_function"},
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("mongo log skipped: %s", exc)
    except Exception as exc:  # noqa: BLE001
        log.exception("could not mark booking id=%s as failed: %s", booking_id, exc)


# ─── Batch processing ─────────────────────────────────────────────────────
def _process_one_batch() -> int:
    """Process a single batch of pending bookings. Returns count processed."""
    with db.session.begin():
        ids = _pending_booking_ids()

    if not ids:
        return 0

    log.info("batch: %s pending booking(s) to process", len(ids))
    successes = 0
    for booking_id in ids:
        if _shutdown:
            log.info("shutdown requested — skipping remaining bookings in batch")
            break
        if _process_with_retry(booking_id):
            successes += 1
        else:
            _mark_failed(booking_id)
    return successes


# ─── Main loop ────────────────────────────────────────────────────────────
def main() -> int:
    """Entry point for the worker process."""
    app = create_app()
    log.info("worker started — poll=%ss batch=%s max_attempts=%s",
             POLL_INTERVAL_SECONDS, BATCH_SIZE, MAX_ATTEMPTS)

    processed_total = 0
    with app.app_context():
        while not _shutdown:
            try:
                processed = _process_one_batch()
                processed_total += processed
                if processed == 0:
                    time.sleep(POLL_INTERVAL_SECONDS)
                else:
                    log.info("processed %s booking(s) this iteration", processed)
            except Exception:  # noqa: BLE001
                log.exception("batch iteration failed; sleeping before retry")
                time.sleep(POLL_INTERVAL_SECONDS)

    log.info("worker exiting cleanly — processed %s booking(s) total",
             processed_total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
