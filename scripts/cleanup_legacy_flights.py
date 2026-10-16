"""
scripts/cleanup_legacy_flights.py
─────────────────────────────────
Delete the legacy `flights` rows attached to packages whose destination
is not bookable. These are the old "mocked" flight stubs the pre-refactor
code used as a synthetic fallback. The new customer-facing pipeline
reads from `package_flights` -> `flight_prices`, so these rows are dead
weight.

Packages themselves are kept — they become land-only products.

Usage:
    python -m scripts.cleanup_legacy_flights            # dry-run
    python -m scripts.cleanup_legacy_flights --commit   # write
"""

from __future__ import annotations

import argparse
import logging

from app import create_app
from extensions import db
from models import BookingItem, Destination, Flight, Package, Quote
from sqlalchemy import select

log = logging.getLogger("cleanup_legacy_flights")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    app = create_app()
    ctx = app.app_context()
    ctx.push()
    try:
        disabled_ids = [d.id for d in db.session.scalars(
            select(Destination).where(Destination.is_bookable.is_(False))
        )]
        if not disabled_ids:
            print("no disabled destinations — nothing to do")
            return 0

        rows = list(db.session.scalars(
            select(Flight).join(Package, Package.id == Flight.package_id)
            .where(Package.destination_id.in_(disabled_ids))
        ))
        print(f"legacy Flight rows to delete: {len(rows)}")

        bi = db.session.query(BookingItem).filter(BookingItem.product_type == "flight").count()
        q = db.session.query(Quote).filter(Quote.product_type == "flight").count()
        print(f"safety: booking_items referencing flights = {bi}")
        print(f"safety: quotes referencing flights = {q}")
        if bi or q:
            print("ABORT — references exist.")
            return 1

        if not args.commit:
            print("DRY-RUN. Re-run with --commit to apply.")
            return 0

        for r in rows:
            db.session.delete(r)
        db.session.commit()
        print(f"COMMITTED. {len(rows)} legacy Flight rows deleted.")
        return 0
    finally:
        ctx.pop()


if __name__ == "__main__":
    raise SystemExit(main())