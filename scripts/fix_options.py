"""
scripts/fix_options.py
──────────────────────
Rebuild PackageOption rows for all packages.

For each package:
    1. Delete all current PackageOption rows (they all have price_id=None)
    2. Group flights by airline_name
    3. Keep up to N distinct airlines (N from CMS key, default 4)
    4. For each airline, pick its first flight
    5. Link the option to the cheapest matching PackagePrice (with dates)

Result: each package has up to 4 priced departure options that the
customer can select on the public detail page.

USAGE
    python scripts/fix_options.py --dry-run
    python scripts/fix_options.py
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import (  # noqa: E402
    Package,
    PackagePrice,
    PackageOption,
    Flight,
)

DEFAULT_MAX = 4


def _lookup_cms_max() -> int:
    """Read package_flights_max from site_content, default 4."""
    try:
        from services import content_service
        raw = content_service.get("package_flights_max")
        if raw:
            return max(1, min(int(raw), 10))
    except Exception:
        pass
    return DEFAULT_MAX


def _cheapest_price(package_id: int):
    """Return the cheapest PackagePrice with dates, or any, or None."""
    # prefer dated rows
    row = (
        db.session.query(PackagePrice)
        .filter(PackagePrice.package_id == package_id)
        .filter(PackagePrice.valid_from.is_not(None))
        .order_by(PackagePrice.adult_price.asc())
        .first()
    )
    if row:
        return row
    return (
        db.session.query(PackagePrice)
        .filter(PackagePrice.package_id == package_id)
        .order_by(PackagePrice.adult_price.asc())
        .first()
    )


def fix(dry_run: bool) -> int:
    app = create_app()
    with app.app_context():
        max_flights = _lookup_cms_max()
        print(f"Max flights per package (from CMS): {max_flights}")

        packages = db.session.query(Package).order_by(Package.id).all()
        print(f"Packages to process: {len(packages)}")

        total_deleted = 0
        total_created = 0

        for p in packages:
            # 1. Delete all existing options
            existing = db.session.query(PackageOption).filter_by(package_id=p.id).all()
            n_del = len(existing)
            if not dry_run:
                for o in existing:
                    db.session.delete(o)
            total_deleted += n_del

            # 2. Group flights by airline
            flights = db.session.query(Flight).filter_by(package_id=p.id).all()
            by_airline: dict[str, list[Flight]] = defaultdict(list)
            for f in flights:
                key = (f.airline_name or "Unknown").strip().lower()
                by_airline[key].append(f)

            # 3. Take up to max_flights airlines (most flights first, then alphabetical)
            ranked = sorted(
                by_airline.items(),
                key=lambda kv: (-len(kv[1]), kv[0]),
            )[:max_flights]

            # 4. Pick a price to link
            price = _cheapest_price(p.id)

            created_here = 0
            for idx, (airline_key, airline_flights) in enumerate(ranked):
                # pick first flight for this airline
                f = airline_flights[0]
                label = (
                    f"{f.airline_name or 'Flight'} · "
                    f"{f.flight_from or '?'} → {f.flight_to or '?'}"
                )
                if not dry_run:
                    db.session.add(PackageOption(
                        package_id=p.id,
                        flight_id=f.id,
                        price_id=price.id if price else None,
                        room_id=p.room_id,
                        departure_date=price.valid_from if price else None,
                        return_date=price.valid_to if price else None,
                        label=label,
                        is_active=True,
                        sort_order=idx * 10,
                    ))
                created_here += 1
            total_created += created_here

            print(
                f"  {p.id:5d} | {p.name[:55]:55s} | "
                f"deleted: {n_del:3d} | created: {created_here} | "
                f"price_id: {price.id if price else '—'}"
            )

        if not dry_run:
            db.session.commit()
            print("\n=== COMMITTED ===")
        else:
            print("\n=== DRY RUN (nothing committed) ===")

        print(f"Total options deleted: {total_deleted}")
        print(f"Total options created: {total_created}")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return fix(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())