"""
scripts/set_destination_bookable.py
────────────────────────────────────
Flip Destination.is_bookable for destinations based on whether they
have any FlightPrice rows keyed to their airport_code.

By default, dry-run. Pass --commit to actually write.

Rules
─────
  * A destination is "bookable" if:
        - it has a non-null airport_code, AND
        - flight_prices has >= 1 row for that airport_code
  * Nile-cruise and transfer (airport_code is NULL) → not bookable.
  * Hurghada and its HRG siblings remain bookable because HRG has 387 rows.

Usage
─────
  python -m scripts.set_destination_bookable              # dry-run
  python -m scripts.set_destination_bookable --commit     # write

  python -m scripts.set_destination_bookable --force-enable hurghada
  python -m scripts.set_destination_bookable --force-disable luxor
"""

from __future__ import annotations

import argparse
import logging

from app import create_app
from extensions import db
from models import Destination, FlightPrice
from sqlalchemy import func, select

log = logging.getLogger("set_destination_bookable")


def compute_plan() -> list[tuple[Destination, bool, int]]:
    """Return list of (destination, should_be_bookable, flight_price_count)."""
    # count flight_prices per airport code, once
    counts: dict[str, int] = {}
    for code, n in db.session.execute(
        select(FlightPrice.destination, func.count(FlightPrice.id))
        .group_by(FlightPrice.destination)
    ):
        if code:
            counts[code.upper()] = int(n)

    plan: list[tuple[Destination, bool, int]] = []
    for d in db.session.scalars(select(Destination).order_by(Destination.name)):
        code = (d.airport_code or "").upper()
        n = counts.get(code, 0)
        should_be = bool(code) and n > 0
        plan.append((d, should_be, n))
    return plan


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true",
                        help="Actually write (default: dry-run)")
    parser.add_argument("--force-enable", action="append", default=[],
                        help="Slug to force is_bookable=True regardless of rule")
    parser.add_argument("--force-disable", action="append", default=[],
                        help="Slug to force is_bookable=False regardless of rule")
    args = parser.parse_args()

    app = create_app()
    ctx = app.app_context()
    ctx.push()
    try:
        force_on = {s.strip().lower() for s in args.force_enable}
        force_off = {s.strip().lower() for s in args.force_disable}

        plan = compute_plan()
        print()
        print(f"{'slug':<24} {'airport':<8} {'fp_rows':>8} {'now':>5} {'next':>5}  action")
        print("-" * 70)
        changes = 0
        for d, should_be, n in plan:
            slug = (d.slug or "").lower()
            if slug in force_on:
                should_be = True
            elif slug in force_off:
                should_be = False

            now = bool(d.is_bookable)
            if now != should_be:
                changes += 1
                action = "ENABLE" if should_be else "DISABLE"
            else:
                action = ""

            print(f"{(d.slug or ''):<24} {(d.airport_code or '-'):<8} {n:>8} "
                  f"{str(now):>5} {str(should_be):>5}  {action}")

        print("-" * 70)
        print(f"changes: {changes}")

        if not args.commit:
            print()
            print("DRY-RUN. No writes. Re-run with --commit to apply.")
            return 0

        for d, should_be, _ in plan:
            slug = (d.slug or "").lower()
            if slug in force_on:
                should_be = True
            elif slug in force_off:
                should_be = False
            if bool(d.is_bookable) != should_be:
                d.is_bookable = should_be

        db.session.commit()
        print(f"COMMITTED. {changes} destinations updated.")
        return 0
    finally:
        ctx.pop()


if __name__ == "__main__":
    raise SystemExit(main())