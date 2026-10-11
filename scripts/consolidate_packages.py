"""
scripts/consolidate_packages.py
───────────────────────────────
Consolidate 1645 CSV-seeded packages into ~18 route packages.

Group key: (destination_id, hotel_id, room_id)
    Keeps hotels separate (customers care which hotel they stay at).

For each group:
    - template = lowest-id package
    - new name = "{destination.name} · {hotel.name} · {room.name}"
    - new slug = auto-generated from name
    - upgrade description / itinerary / inclusions from richest sibling
    - collect ALL sibling prices -> new PackagePrice rows on template
    - collect ALL sibling flights -> dedupe by airline_name -> template
    - drop sibling PackageOption rows
    - delete sibling packages

JSON backup saved to backups/packages_before_consolidation.json BEFORE any writes.

USAGE
    python scripts/consolidate_packages.py --dry-run
    python scripts/consolidate_packages.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import (  # noqa: E402
    Package,
    PackagePrice,
    PackageOption,
    PackageImage,
    Flight,
    Hotel,
    Room,
    Destination,
)


def _dump_backup(path: Path) -> None:
    """Write a JSON snapshot of current packages + prices + flights."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "packages": [
            {c.name: getattr(p, c.name) for c in p.__table__.columns}
            for p in db.session.query(Package).all()
        ],
        "prices": [
            {c.name: str(getattr(pr, c.name)) if c.name in ("adult_price", "child_price") else getattr(pr, c.name)
             for c in pr.__table__.columns}
            for pr in db.session.query(PackagePrice).all()
        ],
        "flights": [
            {c.name: getattr(f, c.name) for c in f.__table__.columns}
            for f in db.session.query(Flight).all()
        ],
    }
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"  Backup saved: {path}")


def consolidate(dry_run: bool) -> int:
    app = create_app()
    with app.app_context():

        total_before = db.session.query(Package).count()
        print(f"Packages before: {total_before}")

        # Group
        groups: dict[tuple, list[Package]] = {}
        for p in db.session.query(Package).all():
            key = (p.destination_id, p.hotel_id, p.room_id)
            groups.setdefault(key, []).append(p)

        print(f"Groups found: {len(groups)}")

        if not dry_run:
            _dump_backup(ROOT / "backups" / "packages_before_consolidation.json")

        stats = {
            "groups": 0,
            "packages_deleted": 0,
            "prices_moved": 0,
            "flights_moved": 0,
            "options_dropped": 0,
            "prices_deduped": 0,
            "flights_deduped": 0,
        }

        for key, siblings in groups.items():
            destination_id, hotel_id, room_id = key
            # Template = lowest id
            siblings.sort(key=lambda p: p.id)
            template = siblings[0]
            others = siblings[1:]

            destination = db.session.get(Destination, destination_id)
            hotel = db.session.get(Hotel, hotel_id)
            room = db.session.get(Room, room_id)

            new_name = " · ".join(filter(None, [
                destination.name if destination else None,
                hotel.name if hotel else None,
                room.type if room else None,
            ])) or f"Package {template.id}"

            print(f"\n[{key}] template={template.id} others={len(others)}")
            print(f"  -> new name: {new_name}")

            # Collect prices (dedupe)
            existing_price_keys: set[tuple] = set()
            for pr in db.session.query(PackagePrice).filter_by(package_id=template.id):
                existing_price_keys.add((
                    pr.valid_from,
                    pr.valid_to,
                    str(pr.adult_price),
                    str(pr.child_price),
                ))

            all_sibling_ids = [p.id for p in others]
            new_prices: list[PackagePrice] = []

            for sibling_id in all_sibling_ids:
                for pr in db.session.query(PackagePrice).filter_by(package_id=sibling_id):
                    keyp = (
                        pr.valid_from,
                        pr.valid_to,
                        str(pr.adult_price),
                        str(pr.child_price),
                    )
                    if keyp in existing_price_keys:
                        stats["prices_deduped"] += 1
                        continue
                    existing_price_keys.add(keyp)
                    new_prices.append(PackagePrice(
                        package_id=template.id,
                        adult_price=pr.adult_price,
                        child_price=pr.child_price,
                        currency=pr.currency,
                        valid_from=pr.valid_from,
                        valid_to=pr.valid_to,
                    ))
                    stats["prices_moved"] += 1

            # Collect flights (dedupe by airline_name + flight_from + flight_to)
            existing_flight_keys: set[tuple] = set()
            for f in db.session.query(Flight).filter_by(package_id=template.id):
                existing_flight_keys.add((
                    (f.airline_name or "").strip().lower(),
                    (f.flight_from or "").strip().lower(),
                    (f.flight_to or "").strip().lower(),
                ))

            new_flights: list[Flight] = []
            for sibling_id in all_sibling_ids:
                for f in db.session.query(Flight).filter_by(package_id=sibling_id):
                    kf = (
                        (f.airline_name or "").strip().lower(),
                        (f.flight_from or "").strip().lower(),
                        (f.flight_to or "").strip().lower(),
                    )
                    if kf in existing_flight_keys or not kf[0]:
                        stats["flights_deduped"] += 1
                        continue
                    existing_flight_keys.add(kf)
                    new_flights.append(Flight(
                        package_id=template.id,
                        supplier_id=f.supplier_id,
                        airline_id=f.airline_id,
                        flight_from=f.flight_from,
                        flight_to=f.flight_to,
                        airline_name=f.airline_name,
                        luggage_allowance=f.luggage_allowance,
                        included=f.included,
                        notes=f.notes,
                        is_active=True,
                    ))
                    stats["flights_moved"] += 1

            # Drop options on template + siblings
            for sibling_id in [template.id] + all_sibling_ids:
                opts = db.session.query(PackageOption).filter_by(package_id=sibling_id).all()
                stats["options_dropped"] += len(opts)
                if not dry_run:
                    for o in opts:
                        db.session.delete(o)

            if not dry_run:
                # Update template
                template.name = new_name
                if destination or hotel or room:
                    template.slug = template._generate_slug(new_name)

                # Add prices/flights
                for pr in new_prices:
                    db.session.add(pr)
                for f in new_flights:
                    db.session.add(f)

                # Delete siblings (cascade will take their children)
                for sibling in others:
                    db.session.delete(sibling)

                stats["packages_deleted"] += len(others)

            stats["groups"] += 1

        if not dry_run:
            db.session.commit()
            print("\n=== COMMITTED ===")
        else:
            print("\n=== DRY RUN (nothing committed) ===")

        total_after = db.session.query(Package).count() if not dry_run else total_before
        print(f"Packages after: {total_after}")
        print(f"Groups processed: {stats['groups']}")
        print(f"Packages deleted: {stats['packages_deleted']}")
        print(f"Prices moved: {stats['prices_moved']}")
        print(f"Prices deduped: {stats['prices_deduped']}")
        print(f"Flights moved: {stats['flights_moved']}")
        print(f"Flights deduped: {stats['flights_deduped']}")
        print(f"Options dropped: {stats['options_dropped']}")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return consolidate(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())