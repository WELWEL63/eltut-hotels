"""
scripts/seed_cover_images.py
────────────────────────────
Populate a single cover image for every Hotel and Package that has no
image yet. The cover URL is drawn from the existing ActivityImage pool.

Marker: rows we create get a URL suffix "?auto_seed=1" so the companion
cleanup script can find and remove them later.

type values are chosen to satisfy the DB CHECK constraints:
  - HotelImage   -> type = "exterior"   (allowed; closest to a cover shot)
  - PackageImage -> type = "cover"      (allowed)

Idempotent: running it twice does nothing the second time (products with
at least one image are skipped).

Usage:
    python scripts\seed_cover_images.py            # apply
    python scripts\seed_cover_images.py --dry-run  # preview only
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import (  # noqa: E402
    ActivityImage,
    Hotel,
    HotelImage,
    Package,
    PackageImage,
)

SEED_QUERY = "?auto_seed=1"          # URL suffix — the reversal marker
HOTEL_TYPE = "exterior"              # satisfies hotel_images type CHECK
PACKAGE_TYPE = "cover"               # satisfies package_images type CHECK
DRY_RUN = "--dry-run" in sys.argv


def main() -> int:
    app = create_app()
    with app.app_context():
        # ── 1. Collect the activity image pool ──────────────────
        pool_rows = db.session.scalars(
            select(ActivityImage)
            .where(ActivityImage.url.is_not(None))
            .order_by(ActivityImage.activity_id, ActivityImage.sort_order)
        ).all()

        # Skip any URLs that are themselves seeds (defensive)
        pool: list[str] = [
            r.url for r in pool_rows
            if r.url and r.url.strip() and SEED_QUERY not in r.url
        ]
        if not pool:
            print("No activity image URLs available. Nothing to seed.")
            return 1

        print(f"Activity image pool size: {len(pool)} URLs")

        # ── 2. Hotels — one cover each ──────────────────────────
        hotels_with_images = set(
            db.session.scalars(select(HotelImage.hotel_id).distinct()).all()
        )
        all_hotels = db.session.scalars(select(Hotel)).all()
        hotels_to_fill = [h for h in all_hotels if h.id not in hotels_with_images]

        print(f"Hotels missing images:    {len(hotels_to_fill)} / {len(all_hotels)}")

        for i, hotel in enumerate(hotels_to_fill):
            url = pool[i % len(pool)] + SEED_QUERY
            if not DRY_RUN:
                db.session.add(HotelImage(
                    hotel_id=hotel.id,
                    url=url,
                    type=HOTEL_TYPE,
                    sort_order=0,
                    media_type="image",
                ))

        # ── 3. Packages — one cover each ────────────────────────
        packages_with_images = set(
            db.session.scalars(select(PackageImage.package_id).distinct()).all()
        )
        all_packages = db.session.scalars(select(Package)).all()
        packages_to_fill = [
            p for p in all_packages if p.id not in packages_with_images
        ]

        print(f"Packages missing images:  {len(packages_to_fill)} / {len(all_packages)}")

        for i, package in enumerate(packages_to_fill):
            url = pool[i % len(pool)] + SEED_QUERY
            if not DRY_RUN:
                db.session.add(PackageImage(
                    package_id=package.id,
                    url=url,
                    type=PACKAGE_TYPE,
                    sort_order=0,
                    media_type="image",
                ))

        # ── 4. Commit ───────────────────────────────────────────
        if DRY_RUN:
            print("\n[DRY-RUN] No changes written. Re-run without --dry-run to apply.")
        else:
            db.session.commit()
            print(
                f"\nWrote {len(hotels_to_fill)} hotel covers "
                f"and {len(packages_to_fill)} package covers."
            )
            print(f"Marker: url ends with '{SEED_QUERY}', type='{HOTEL_TYPE}' / '{PACKAGE_TYPE}'")

        return 0


if __name__ == "__main__":
    sys.exit(main())