"""
cloud_function/__init__.py
───────────────────────────
Background worker package: asynchronous, decoupled post-booking side
effects.

PURPOSE
    When a booking is confirmed, several things must happen that
    should NOT block the HTTP response:
        1. Send the customer a confirmation email (SMTP, slow)
        2. Write to MongoDB activity_logs (network)
        3. Send an admin notification email (SMTP)
        4. Append a status history row (fast, but grouped with the
           rest for atomicity within the task)

    The cloud function runs as a separate process (Render background
    worker), polling the bookings table every N seconds for confirmed
    bookings that haven't been processed yet.

DESIGN
    - Polling, not pub/sub. Resilient to restarts: if the worker
      crashes, the next start picks up pending rows.
    - Idempotent per-booking: notification_sent_at is set on success
      so the same booking is never emailed twice.
    - Failure recovery: notification_failed_at records permanent
      failures after retries are exhausted; admins can query those.

FILES
    worker.py     main entry point (poll loop, retry policy)
    tasks.py      individual task functions (pure, testable)
"""

from __future__ import annotations

__all__: list[str] = []
